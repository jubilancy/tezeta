# /// script
# requires-python = ">=3.11"
# dependencies = ["python-igraph>=0.11", "pillow>=10.3"]
# ///
"""Build the Tezeta site (dist/) from data/terms.csv.

Terms are glowing nodes colored by vibe. Words shared by several terms become
small hub nodes that pull related terms together. The layout is computed here
(see layout.py) and shipped as coordinates; the browser draws it with Sigma.js
(WebGL), so the page stays fast with thousands of terms.

    uv run scripts/build_graph.py [data/terms.csv] [dist/index.html]
"""
import colorsys
import csv
import html
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from layout import layout
from term_pages import write_site

HERE = Path(__file__).parent
SITE_URL = os.environ.get("SITE_URL", "https://tezeta.web.app").rstrip("/")

STOPWORDS = set(
    "a an and are as at be by for from has have in into is it its of on or that the their this "
    "to was were with which who whose about than then them these those not but can may more most "
    "other some such only own same so too very "
    # boilerplate that opens or links definitions without saying what a term is about
    "used using uses use having being been also each any many much various certain particular another one two "
    "especially usually often typically generally something someone anything thing things kind type form "
    "during between through while within without upon over under into onto such called known "
    "involving relating related characteristic characterized characterised consisting resulting"
    .split()
)
JEWELS = ["#ff7b8a", "#f2c14e", "#5fd4c4", "#a58bff", "#6cb6ff", "#ff9f6b", "#e58bd9", "#9ed98a"]


def slugify(text: str) -> str:
    """Same rule as scripts/import_terms.py, so a term's slug is its Firestore doc id."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def unique_slugs(terms: list[dict[str, str]]) -> list[str]:
    seen: set[str] = set()
    out = []
    for t in terms:
        base = slugify(t["term"]) or "term"
        slug, n = base, 2
        while slug in seen:
            slug, n = f"{base}-{n}", n + 1
        seen.add(slug)
        out.append(slug)
    return out


def stem(word: str) -> str:
    return re.sub(r"(ing|ed|es|s)$", lambda m: "" if m.start() >= 3 else m.group(), word)


def tokenize(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


def palette(keys: list[str]) -> dict[str, str]:
    """Jewel tones first; golden-ratio hues keep any extra vibes distinct."""
    out = {}
    for i, key in enumerate(sorted(keys)):
        if i < len(JEWELS):
            out[key] = JEWELS[i]
            continue
        r, g, b = colorsys.hls_to_rgb((0.07 + i * 0.381966) % 1, 0.68, 0.7)
        out[key] = "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    return out


MAX_HUBS_PER_TERM = 6  # edge budget: each term links to at most its 6 most specific shared words


def pick_hubs(words: list[set[str]], n_terms: int) -> dict[str, list[int]]:
    """Shared words that connect 2+ terms, minus words so common they connect everything.

    The ceiling is 1% of the term count (at least 8), so a big library keeps specific links
    instead of a hairball held together by words like "used". Each term then keeps only its
    rarest (most specific) shared words, which caps the edge count at 6 per term.
    """
    by_word: dict[str, list[int]] = defaultdict(list)
    for i, ws in enumerate(words):
        for w in ws:
            by_word[w].append(i)
    cap = max(8, min(int(n_terms * 0.6), int(n_terms * 0.01)))
    hubs = {w: ix for w, ix in by_word.items() if 2 <= len(ix) <= cap}
    if n_terms > 40:
        keep: dict[int, set[str]] = {}
        for i, ws in enumerate(words):
            mine = sorted((w for w in ws if w in hubs), key=lambda w: (len(hubs[w]), w))
            keep[i] = set(mine[:MAX_HUBS_PER_TERM])
        hubs = {w: [i for i in ix if w in keep[i]] for w, ix in hubs.items()}
        hubs = {w: ix for w, ix in hubs.items() if len(ix) >= 2}
    return hubs


def surface_forms(terms: list[dict[str, str]]) -> dict[str, str]:
    """For each stem, the most common word it came from, so labels read as words ("plant") not stems."""
    seen: dict[str, Counter] = defaultdict(Counter)
    for t in terms:
        for w in re.findall(r"[a-z]+", f"{t['term']} {t['definition']}".lower()):
            if len(w) > 2 and w not in STOPWORDS:
                seen[stem(w)][w] += 1
    return {s: c.most_common(1)[0][0] for s, c in seen.items()}


def island_labels(islands: list[dict], hubs: dict[str, list[int]], n_terms: int, names: list[str]) -> list[dict]:
    """Name each community after the words that most distinctively tie its terms together."""
    out = []
    for isl in islands:
        members = {v for v in isl["vertices"] if v < n_terms}
        if len(members) < 12:
            continue
        scored = []
        for k, w in enumerate(names):
            inside = len(members.intersection(hubs[w]))
            if inside >= 3:
                scored.append((inside * inside / len(hubs[w]), inside, w))
        scored.sort(reverse=True)
        label = " · ".join(w for _, _, w in scored[:2]) or ""
        if label:
            out.append({"x": isl["x"], "y": isl["y"], "r": isl["r"], "n": len(members), "label": label})
    return out


def read_terms(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [
            {k: (r.get(k) or "").strip() for k in ("term", "definition", "vibe")}
            for r in csv.DictReader(f)
            if (r.get("term") or "").strip()
        ]


def head_meta(n_terms: int) -> str:
    desc = html.escape(f"{n_terms} terms and the words they share. Search, wander, and share a single term.", quote=True)
    return "\n".join(
        [
            f'<meta name="description" content="{desc}">',
            f'<link rel="canonical" href="{SITE_URL}/">',
            '<meta property="og:type" content="website">',
            '<meta property="og:site_name" content="tezeta, an exploration">',
            '<meta property="og:title" content="tezeta, an exploration">',
            f'<meta property="og:description" content="{desc}">',
            f'<meta property="og:url" content="{SITE_URL}/">',
            f'<meta property="og:image" content="{SITE_URL}/og/site.jpg">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            '<meta name="twitter:card" content="summary_large_image">',
            '<meta name="twitter:title" content="tezeta, an exploration">',
            f'<meta name="twitter:description" content="{desc}">',
            f'<meta name="twitter:image" content="{SITE_URL}/og/site.jpg">',
        ]
    )


def build(terms: list[dict[str, str]], out: Path) -> None:
    t0 = time.time()
    slugs = unique_slugs(terms)
    colors = palette(list({t["vibe"] or "unsorted" for t in terms}))
    hubs = pick_hubs([tokenize(f"{t['term']} {t['definition']}") for t in terms], len(terms))
    shown = surface_forms(terms)
    renamed: dict[str, list[int]] = {}
    for w, ix in hubs.items():
        name = shown.get(w, w)
        renamed[name if name not in renamed else w] = ix  # keep the stem if two stems share a spelling
    hubs = renamed
    term_pos, hub_pos, islands, member = layout(len(terms), hubs)
    labels = island_labels(islands, hubs, len(terms), list(hubs))
    t_layout = time.time() - t0

    data = {
        "terms": [{**t, "slug": s, "x": x, "y": y} for t, s, (x, y) in zip(terms, slugs, term_pos)],
        "hubs": hubs,
        "hubPos": {w: list(p) for w, p in hub_pos.items()},
        "colors": colors,
        "tc": member[: len(terms)],
        "hc": member[len(terms) :],
        "islands": sorted(labels, key=lambda i: -i["n"]),
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    legend = "".join(
        f'<span><i style="background:{c};box-shadow:0 0 10px {c}"></i>{html.escape(v)}</span>' for v, c in sorted(colors.items())
    )

    page = (HERE / "graph.html").read_text(encoding="utf-8")
    for token, value in {
        "__HEAD_META__": head_meta(len(terms)),
        "__CSS__": (HERE / "graph.css").read_text(encoding="utf-8"),
        "__COUNT__": str(len(terms)),
        "__HUBS__": str(len(hubs)),
        "__LEGEND__": legend,
        "__GRAPHOLOGY__": next((HERE / "vendor").glob("graphology-*.umd.min.js")).read_text(encoding="utf-8"),
        "__SIGMA__": next((HERE / "vendor").glob("sigma-*.min.js")).read_text(encoding="utf-8"),
        "__DATA__": payload,
        "__FX__": (HERE / "graph_fx.js").read_text(encoding="utf-8"),
    }.items():
        page = page.replace(token, value, 1)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    shutil.copy(HERE / "favicon.svg", out.parent / "favicon.svg")
    t_graph = time.time() - t0
    pages = write_site(terms, slugs, hubs, colors, out.parent, SITE_URL)
    print(
        f"wrote {out}: {len(terms)} terms, {len(hubs)} shared-word hubs, {pages} term pages, {len(labels)} named clusters "
        f"(layout {t_layout:.1f}s, graph {t_graph:.1f}s, pages and cards {time.time() - t0 - t_graph:.1f}s, "
        f"index.html {out.stat().st_size // 1024} KB)"
    )


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/terms.csv")
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else "dist/index.html")
    build(read_terms(src), dest)
