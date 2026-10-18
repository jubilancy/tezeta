"""Read data/terms.csv, the one place that decides what a row is and what its address is.

Both the Firestore import and the site build use this, so a term's slug (its page
address, `/#slug`, and its Firestore document id) is always the same in both.

Repeated words never fail the run:

- A row that repeats an earlier row (same word, same definition) is skipped.
- The same word with a different definition is a different entry and is kept. Its
  slug is the word plus its vibe (`love-quote-topics`), or a number (`love-2`) if the
  vibe is empty or already taken. The first row for a word keeps the plain slug.
"""
import csv
import itertools
import re
import sys
from pathlib import Path

REQUIRED = ("term", "definition")
FIELDS = ("term", "definition", "vibe")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _same(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def _unique_slug(base: str, vibe: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    tag = slugify(vibe)
    numbered = (f"{base}-{n}" for n in itertools.count(2))  # a generator: the count never ends
    for candidate in itertools.chain([f"{base}-{tag}"] if tag else [], numbered):
        if candidate not in taken:
            return candidate
    raise AssertionError("unreachable")


def load_terms(path: Path) -> tuple[list[dict[str, str]], dict[str, list]]:
    """Return (rows, report). Each row has term, definition, vibe and slug.

    `report` lists what was done about repeats: "skipped" holds (line, term, earlier_line)
    for exact repeats that were dropped; "kept" holds (line, term, slug) for same-word,
    different-definition rows that were kept under a distinct slug.
    """
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"{path}: missing required column(s): {', '.join(missing)}")
        rows: list[dict[str, str]] = []
        report: dict[str, list] = {"skipped": [], "kept": []}
        seen: dict[str, list[tuple[int, str]]] = {}  # base slug -> [(line, definition)] of rows kept
        taken: set[str] = set()
        for line, raw in enumerate(reader, start=2):
            row = {k: (raw.get(k) or "").strip() for k in FIELDS}
            if not row["term"] or not row["definition"]:
                sys.exit(f"{path}:{line}: term and definition are required")
            base = slugify(row["term"])
            if not base:
                sys.exit(f"{path}:{line}: term {row['term']!r} has no usable characters")
            earlier = next((ln for ln, d in seen.get(base, []) if _same(d, row["definition"])), None)
            if earlier is not None:
                report["skipped"].append((line, row["term"], earlier))
                continue
            slug = _unique_slug(base, row["vibe"], taken)
            if seen.get(base):
                report["kept"].append((line, row["term"], slug))
            seen.setdefault(base, []).append((line, row["definition"]))
            taken.add(slug)
            rows.append({**row, "slug": slug})
    return rows, report


def announce(path: Path, report: dict[str, list], limit: int = 20) -> None:
    """Print what happened to repeated words, as GitHub Actions annotations (plain lines elsewhere)."""
    name = path.as_posix()
    for line, term, earlier in report["skipped"][:limit]:
        print(f"::warning file={name},line={line}::skipped {term!r}: identical to line {earlier}")
    if len(report["skipped"]) > limit:
        print(f"::warning file={name}::...and {len(report['skipped']) - limit} more identical rows skipped")
    if report["kept"]:
        sample = ", ".join(f"{t!r} (line {ln}) as {s}" for ln, t, s in report["kept"][:3])
        print(f"::notice file={name}::{len(report['kept'])} words appear more than once with different content; all kept, "
              f"extra copies get their own address, e.g. {sample}")
