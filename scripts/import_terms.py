# /// script
# requires-python = ">=3.11"
# dependencies = ["firebase-admin>=6.5"]
# ///
"""Upsert data/terms.csv into the Firestore `terms` collection.

Document ids are the term slugs from terms_csv.py, so re-running updates in place.
Repeated words never fail the run (see terms_csv.py): identical rows are skipped, and a word
with a different definition is kept under its own slug.

    uv run scripts/import_terms.py --dry-run
    FIREBASE_SERVICE_ACCOUNT='{...json...}' uv run scripts/import_terms.py [--prune]
"""
import argparse
import json
import os
import sys
from pathlib import Path

from terms_csv import REQUIRED, announce, load_terms
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="?", default="data/terms.csv", type=Path)
    p.add_argument("--dry-run", action="store_true", help="validate and print, write nothing")
    p.add_argument("--prune", action="store_true", help="delete Firestore terms that are not in the CSV")
    args = p.parse_args()

    rows, report = load_terms(args.csv)
    announce(args.csv, report)
    docs = {r["slug"]: {k: v for k, v in r.items() if k != "slug" and (v or k in REQUIRED)} for r in rows}
    skipped = f", {len(report["skipped"])} identical rows skipped" if report["skipped"] else ""
    print(f"{len(docs)} terms in {args.csv}{skipped}")
    if args.dry_run:
        for doc_id, doc in docs.items():
            print(f"  {doc_id}: {json.dumps(doc)}")
        return

    import firebase_admin
    from firebase_admin import credentials, firestore

    key = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not key:
        sys.exit("FIREBASE_SERVICE_ACCOUNT is not set")
    firebase_admin.initialize_app(credentials.Certificate(json.loads(key)))
    col = firestore.client().collection("terms")

    writer = firestore.client().batch()
    pending = 0
    for doc_id, doc in docs.items():
        writer.set(col.document(doc_id), doc)  # full replace: CSV is the source of truth
        pending += 1
        if pending == 400:
            writer.commit()
            writer, pending = firestore.client().batch(), 0
    if pending:
        writer.commit()
    print(f"upserted {len(docs)} documents")

    if args.prune:
        stale = [d.reference for d in col.stream() if d.id not in docs]
        for ref in stale:
            ref.delete()
        print(f"pruned {len(stale)} documents not in the CSV")


if __name__ == "__main__":
    main()
