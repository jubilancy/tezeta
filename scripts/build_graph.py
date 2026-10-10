# /// script
# requires-python = ">=3.11"
# dependencies = ["pyvis>=0.3.2", "setuptools<81"]
# ///
"""Build the Tezeta knowledge graph (dist/index.html) from data/terms.csv.

Terms are glowing nodes colored by vibe. Words shared by two or more terms
become small hub nodes that pull related terms together into constellations.

    uv run scripts/build_graph.py [data/terms.csv] [dist/index.html]
"""
import colorsys
import csv
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from pyvis.network import Network

STOPWORDS = set(
    "a an and are as at be by for from has have in into is it its of on or that the their this "
    "to was were with which who whose about than then them these those not but can may more most "
    "other some such only own same so too very".split()
)

BG_INNER, BG_OUTER = "#1a1030", "#05030c"
HUB = "#f2e6c9"


def stem(word: str) -> str:
    return re.sub(r"(ing|ed|es|s)$", lambda m: "" if m.start() >= 3 else m.group(), word)


def tokenize(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


JEWELS = ["#ff7b8a", "#f2c14e", "#5fd4c4", "#a58bff", "#6cb6ff", "#ff9f6b", "#e58bd9", "#9ed98a"]


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


def rgba(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


OPTIONS = {
    "nodes": {"borderWidth": 0, "font": {"face": "Georgia, serif", "color": "#efe7d6", "strokeWidth": 0}},
    "edges": {
        "width": 1,
        "color": {"inherit": "from", "opacity": 0.35},
        "smooth": {"type": "continuous", "roundness": 0.4},
        "selectionWidth": 2,
    },
    "physics": {
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
            "gravitationalConstant": -70,
            "centralGravity": 0.008,
            "springLength": 130,
            "springConstant": 0.06,
            "damping": 0.55,
            "avoidOverlap": 0.6,
        },
        "stabilization": {"iterations": 250},
    },
    "interaction": {"hover": True, "tooltipDelay": 80, "hideEdgesOnDrag": True, "navigationButtons": False},
}

OVERLAY = """
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;1,400&display=swap" rel="stylesheet">
<style>
  html, body {{ margin: 0; height: 100%; overflow: hidden;
    background: {outer} radial-gradient(ellipse at 50% 40%, {inner} 0%, {outer} 75%) fixed; }}
  .card {{ background: transparent !important; border: 0 !important; }}
  #mynetwork {{ border: 0 !important; }}
  .tz-title {{ position: fixed; top: 28px; left: 36px; z-index: 5; pointer-events: none; color: #efe7d6;
    font-family: "Cormorant Garamond", Georgia, serif; }}
  .tz-title h1 {{ margin: 0; font-weight: 500; font-size: 2.4rem; letter-spacing: .32em; text-transform: uppercase; }}
  .tz-title p {{ margin: .25rem 0 0; font-style: italic; font-size: 1.05rem; opacity: .6; }}
  .tz-legend {{ position: fixed; bottom: 28px; left: 36px; z-index: 5; display: flex; gap: 1.2rem; flex-wrap: wrap;
    font-family: "Cormorant Garamond", Georgia, serif; font-style: italic; font-size: 1rem; color: #efe7d6; }}
  .tz-legend span {{ display: inline-flex; align-items: center; gap: .45rem; opacity: .85; }}
  .tz-legend i {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  div.vis-tooltip {{ background: #120a24 !important; color: #efe7d6 !important; border: 1px solid rgba(239,231,214,.25) !important;
    border-radius: 2px !important; font-family: Georgia, serif !important; font-size: 14px !important; padding: 10px 14px !important;
    max-width: 280px; white-space: normal !important; }}
</style>
<div class="tz-title"><h1>Tezeta</h1><p>{count} terms, {hubs} shared words</p></div>
<div class="tz-legend">{legend}</div>
"""


def read_terms(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [
            {k: (r.get(k) or "").strip() for k in ("term", "definition", "vibe")}
            for r in csv.DictReader(f)
            if (r.get("term") or "").strip()
        ]


def build(terms: list[dict[str, str]], out: Path) -> None:
    colors = palette(list({t["vibe"] or "unsorted" for t in terms}))
    words = [tokenize(f"{t['term']} {t['definition']}") for t in terms]

    by_word: dict[str, list[int]] = defaultdict(list)
    for i, ws in enumerate(words):
        for w in ws:
            by_word[w].append(i)
    # a hub needs 2+ terms; skip words that appear almost everywhere
    cap = max(3, int(len(terms) * 0.6))
    hubs = {w: ix for w, ix in by_word.items() if 2 <= len(ix) <= cap}

    net = Network(height="100vh", width="100%", bgcolor="rgba(0,0,0,0)", font_color="#efe7d6", cdn_resources="in_line")
    net.set_options(json.dumps(OPTIONS))

    degree = defaultdict(int)
    for ix in hubs.values():
        for i in ix:
            degree[i] += 1

    for i, t in enumerate(terms):
        c = colors[t["vibe"] or "unsorted"]
        net.add_node(
            f"t{i}",
            label=t["term"],
            title=f"{t['term']}  ·  {t['vibe'] or 'unsorted'}\n{t['definition']}",
            size=16 + 7 * degree[i],
            shape="dot",
            color={"background": c, "border": c, "highlight": {"background": "#fff", "border": c}, "hover": {"background": "#fff", "border": c}},
            shadow={"enabled": True, "color": rgba(c, 0.85), "size": 28 + 6 * degree[i], "x": 0, "y": 0},
            font={"size": 17 + 2 * degree[i], "color": "#efe7d6", "face": "Georgia, serif"},
        )
    for w, ix in hubs.items():
        net.add_node(
            f"w:{w}",
            label=w,
            title=f"shared word: {w}\n{', '.join(terms[i]['term'] for i in ix)}",
            size=5 + 2 * len(ix),
            shape="dot",
            color={"background": HUB, "border": HUB},
            shadow={"enabled": True, "color": rgba(HUB, 0.5), "size": 14, "x": 0, "y": 0},
            font={"size": 12, "color": rgba(HUB, 0.55), "face": "Georgia, serif"},
        )
        for i in ix:
            net.add_edge(f"t{i}", f"w:{w}", color=rgba(colors[terms[i]["vibe"] or "unsorted"], 0.4))

    out.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(out), notebook=False)

    legend = "".join(
        f'<span><i style="background:{c};box-shadow:0 0 10px {c}"></i>{html.escape(v)}</span>' for v, c in sorted(colors.items())
    )
    overlay = OVERLAY.format(inner=BG_INNER, outer=BG_OUTER, count=len(terms), hubs=len(hubs), legend=legend)
    page = out.read_text(encoding="utf-8")
    page = page.replace("<head>", '<head>\n<title>Tezeta</title>\n<meta name="viewport" content="width=device-width, initial-scale=1">', 1)
    page = page.replace("</body>", overlay + "</body>", 1)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out}: {len(terms)} terms, {len(hubs)} shared-word hubs")


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/terms.csv")
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else "dist/index.html")
    build(read_terms(src), dest)
