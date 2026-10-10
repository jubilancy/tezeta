# /// script
# requires-python = ">=3.11"
# dependencies = ["firebase-admin>=6.5"]
# ///
"""Upsert data/terms.csv into the Firestore `terms` collection.

Document ids are slugs of the term, so re-running updates in place.

    uv run scripts/import_terms.py --dry-run
    FIREBASE_SERVICE_ACCOUNT='{...json...}' uv run scripts/import_terms.py [--prune]
"""
import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

REQUIRED = ("term", "definition")
FIELDS = ("term", "definition", "vibe")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def read_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"{path}: missing required column(s): {', '.join(missing)}")
        docs: dict[str, dict[str, str]] = {}
        for line, row in enumerate(reader, start=2):
            doc = {k: (row.get(k) or "").strip() for k in FIELDS}
            if not doc["term"] or not doc["definition"]:
                sys.exit(f"{path}:{line}: term and definition are required")
            doc_id = slugify(doc["term"])
            if not doc_id:
                sys.exit(f"{path}:{line}: term {doc['term']!r} has no usable characters")
            if doc_id in docs:
                sys.exit(f"{path}:{line}: duplicate term {doc['term']!r}")
            docs[doc_id] = {k: v for k, v in doc.items() if v or k in REQUIRED}
    return docs


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="?", default="data/terms.csv", type=Path)
    p.add_argument("--dry-run", action="store_true", help="validate and print, write nothing")
    p.add_argument("--prune", action="store_true", help="delete Firestore terms that are not in the CSV")
    args = p.parse_args()

    docs = read_rows(args.csv)
    print(f"{len(docs)} terms in {args.csv}")
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
