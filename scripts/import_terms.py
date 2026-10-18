# /// script
# requires-python = ">=3.11"
# dependencies = ["firebase-admin>=6.5"]
# ///
"""Sync data/terms.csv into the Firestore `terms` collection, writing only what changed.

Firestore's free tier allows 20,000 document writes a day, so the import reads what is
already there (reads have their own, larger allowance), compares it with the CSV row by row,
and writes only new and changed documents. Pushing a CSV that differs by ten rows costs ten
writes, not thousands. If the daily quota runs out partway, nothing is lost: the next run
sees what is already written and finishes the rest.

Document ids are the term slugs from terms_csv.py. Repeated words never fail the run:
identical rows are skipped, and a word with a different definition keeps its own slug.

    uv run scripts/import_terms.py --dry-run     # validate the CSV only; no credentials needed
    FIREBASE_SERVICE_ACCOUNT='{...json...}' uv run scripts/import_terms.py --plan    # show what would be written
    FIREBASE_SERVICE_ACCOUNT='{...json...}' uv run scripts/import_terms.py           # write the difference
    ... --prune   also delete Firestore terms that are no longer in the CSV
    ... --force   rewrite every document, changed or not
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from terms_csv import REQUIRED, announce, load_terms

BATCH = 400  # Firestore allows 500 operations per batch


@dataclass
class Plan:
    new: list[str]
    changed: list[str]
    unchanged: int
    stale: list[str]  # in Firestore, no longer in the CSV


def make_plan(docs: dict[str, dict], existing: dict[str, dict], force: bool = False) -> Plan:
    new = [d for d in docs if d not in existing]
    changed = [d for d in docs if d in existing and (force or existing[d] != docs[d])]
    return Plan(new, changed, len(docs) - len(new) - len(changed), [d for d in existing if d not in docs])


def _is_quota(error: Exception) -> bool:
    return any(c.__name__ == "ResourceExhausted" for c in type(error).__mro__)


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _step_summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def sync(client, col, docs: dict[str, dict], *, prune=False, force=False, plan_only=False, out=print) -> int:
    """Write the difference between `docs` and what Firestore holds. Returns a process exit code."""
    existing = {snap.id: (snap.to_dict() or {}) for snap in col.stream()}
    plan = make_plan(docs, existing, force)
    todo = plan.new + plan.changed
    out(f"{len(docs)} terms in the CSV, {len(existing)} documents in Firestore")
    out(f"  new {len(plan.new)}, changed {len(plan.changed)}, unchanged {plan.unchanged}, in Firestore but not in the CSV {len(plan.stale)}")
    _step_summary([
        "### Firestore import", "", "| | documents |", "|---|---|",
        f"| new | {len(plan.new)} |", f"| changed | {len(plan.changed)} |", f"| unchanged (not written) | {plan.unchanged} |",
        f"| in Firestore, not in the CSV | {len(plan.stale)}{' (deleted)' if prune else ' (kept; run with prune to delete)'} |",
        f"| **writes this run** | **{0 if plan_only else len(todo) + (len(plan.stale) if prune else 0)}** |",
    ])
    if plan_only:
        out("plan only: nothing was written")
        return 0

    written = 0
    try:
        for chunk in _chunks(todo, BATCH):
            batch = client.batch()
            for doc_id in chunk:
                batch.set(col.document(doc_id), docs[doc_id])  # full replace: the CSV is the source of truth
            batch.commit()
            written += len(chunk)
            if len(todo) > BATCH:
                out(f"  wrote {written}/{len(todo)}")
        out(f"wrote {written} documents" + (f", left {plan.unchanged} untouched" if plan.unchanged else ""))
        if prune and plan.stale:
            for chunk in _chunks(plan.stale, BATCH):
                batch = client.batch()
                for doc_id in chunk:
                    batch.delete(col.document(doc_id))
                batch.commit()
            out(f"deleted {len(plan.stale)} documents that are not in the CSV")
    except Exception as error:  # noqa: BLE001 - quota errors are expected, everything else is re-raised
        if not _is_quota(error):
            raise
        out(f"Firestore's daily write quota ran out after {written} of {len(todo)} documents. Nothing is lost: "
            f"the import only writes what differs, so run it again after the quota resets (midnight Pacific time) "
            f"and it finishes the rest.")
        return 1
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="?", default="data/terms.csv", type=Path)
    p.add_argument("--dry-run", action="store_true", help="validate the CSV and print it; touch nothing")
    p.add_argument("--plan", action="store_true", help="compare with Firestore and report what would be written; write nothing")
    p.add_argument("--prune", action="store_true", help="delete Firestore terms that are not in the CSV")
    p.add_argument("--force", action="store_true", help="rewrite every document, even unchanged ones")
    args = p.parse_args()

    rows, report = load_terms(args.csv)
    announce(args.csv, report)
    docs = {r["slug"]: {k: v for k, v in r.items() if k != "slug" and (v or k in REQUIRED)} for r in rows}
    skipped = f", {len(report['skipped'])} identical rows skipped" if report["skipped"] else ""
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
    client = firestore.client()
    sys.exit(sync(client, client.collection("terms"), docs, prune=args.prune, force=args.force, plan_only=args.plan))


if __name__ == "__main__":
    main()
