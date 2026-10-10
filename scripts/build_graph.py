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
import shutil
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
        "color": {"inherit": "both", "opacity": 0.5},
        "smooth": {"type": "continuous", "roundness": 0.4},
        "selectionWidth": 1.5,
        "hoverWidth": 1.5,
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
  .tz-title h1 {{ margin: 0; font-weight: 500; font-size: 2.6rem; letter-spacing: .14em; }}
  .tz-title p {{ margin: .25rem 0 0; font-style: italic; font-size: 1.05rem; opacity: .6; }}
  .tz-legend {{ position: fixed; bottom: 28px; left: 36px; z-index: 5; display: flex; gap: 1.2rem; flex-wrap: wrap;
    font-family: "Cormorant Garamond", Georgia, serif; font-style: italic; font-size: 1rem; color: #efe7d6; }}
  .tz-legend span {{ display: inline-flex; align-items: center; gap: .45rem; opacity: .85; }}
  .tz-legend i {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  div.vis-tooltip {{ background: #120a24 !important; color: #efe7d6 !important; border: 1px solid rgba(239,231,214,.25) !important;
    border-radius: 2px !important; font-family: Georgia, serif !important; font-size: 14px !important; padding: 10px 14px !important;
    max-width: 280px; white-space: normal !important; }}
  #mynetwork {{ position: relative; z-index: 1; }}
  #tz-search {{ position: fixed; top: 34px; left: 50%; transform: translateX(-50%); width: min(380px, calc(100vw - 720px)); min-width: 240px; z-index: 7;
    font-family: "Cormorant Garamond", Georgia, serif; color: #efe7d6; }}
  #tz-search input {{ width: 100%; box-sizing: border-box; padding: .55rem 1.1rem; font: italic 1.15rem "Cormorant Garamond", Georgia, serif; color: #efe7d6;
    background: rgba(18, 10, 36, .6); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(239, 231, 214, .2); border-radius: 99px; outline: none; transition: border-color .25s, box-shadow .25s; }}
  #tz-search input::-webkit-search-cancel-button {{ -webkit-appearance: none; display: none; }}
  #tz-search input::placeholder {{ color: rgba(239, 231, 214, .45); }}
  #tz-search input:focus {{ border-color: rgba(156, 175, 136, .8); box-shadow: 0 0 22px rgba(156, 175, 136, .25); }}
  #tz-results {{ list-style: none; margin: .5rem 0 0; padding: .35rem; display: none; background: rgba(18, 10, 36, .85);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border: 1px solid rgba(239, 231, 214, .16); border-radius: 14px; }}
  #tz-results.open {{ display: block; }}
  #tz-results li {{ display: flex; align-items: center; gap: .65rem; padding: .4rem .75rem; border-radius: 9px; cursor: pointer; font-size: 1.15rem; }}
  #tz-results li.on, #tz-results li:hover {{ background: rgba(239, 231, 214, .12); }}
  #tz-results li i {{ width: 9px; height: 9px; border-radius: 50%; flex: none; }}
  #tz-results li em {{ margin-left: auto; opacity: .5; font-size: .95rem; }}
  #tz-panel {{ position: fixed; top: 28px; right: 28px; width: 300px; max-height: calc(100vh - 56px); overflow: auto; z-index: 6;
    padding: 22px 24px 24px; color: #efe7d6; font-family: "Cormorant Garamond", Georgia, serif;
    background: rgba(18, 10, 36, .72); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(239, 231, 214, .16); border-radius: 4px; box-shadow: 0 20px 60px rgba(0, 0, 0, .5);
    opacity: 0; transform: translateX(16px); pointer-events: none; transition: opacity .35s, transform .35s; }}
  #tz-panel.open {{ opacity: 1; transform: none; pointer-events: auto; }}
  #tz-panel h2 {{ margin: 0 0 .5rem; font-weight: 500; font-size: 2rem; letter-spacing: .04em; }}
  #tz-panel h3 {{ margin: 1.3rem 0 .5rem; font-size: .8rem; font-weight: 500; letter-spacing: .22em; text-transform: uppercase; opacity: .55; }}
  #tz-panel .tz-def {{ margin: 1rem 0 0; font-size: 1.2rem; line-height: 1.45; font-style: italic; }}
  #tz-panel .tz-chip {{ --c: #f2e6c9; display: inline-block; padding: .1rem .75rem; border-radius: 99px; font-size: .95rem; font-style: italic;
    border: 1px solid var(--c); color: var(--c); box-shadow: 0 0 14px color-mix(in srgb, var(--c) 40%, transparent); }}
  #tz-panel .tz-tags {{ display: flex; flex-wrap: wrap; gap: .4rem; }}
  #tz-panel .tz-tags span {{ padding: .05rem .6rem; font-size: .95rem; background: rgba(242, 230, 201, .1); border-radius: 99px; }}
  #tz-panel .tz-rel {{ display: flex; flex-wrap: wrap; gap: .4rem; }}
  #tz-panel .tz-rel button {{ font: inherit; font-size: 1.05rem; color: #efe7d6; cursor: pointer; padding: .05rem .75rem;
    background: transparent; border: 1px solid rgba(239, 231, 214, .3); border-radius: 99px; transition: background .2s; }}
  #tz-panel .tz-rel button:hover {{ background: rgba(239, 231, 214, .16); }}
  #tz-panel .tz-x {{ position: absolute; top: 10px; right: 14px; font-size: 1.6rem; line-height: 1; color: #efe7d6; opacity: .6;
    background: none; border: 0; cursor: pointer; }}
  @media (max-width: 640px) {{
    .tz-title {{ top: 18px; left: 20px; }} .tz-title h1 {{ font-size: 1.7rem; }}
    #tz-search {{ top: 84px; left: 20px; right: 20px; width: auto; transform: none; }}
    .tz-legend {{ left: 20px; bottom: 18px; }}
    #tz-panel {{ top: auto; right: 12px; left: 12px; bottom: 12px; width: auto; max-height: 45vh; }}
  }}
</style>
<div class="tz-title"><h1>tezeta</h1><p>{count} terms, {hubs} shared words</p></div>
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
            font={"size": 12, "color": rgba("#efe7d6", 0.55), "face": "Georgia, serif"},
        )
        for i in ix:
            net.add_edge(f"t{i}", f"w:{w}")

    out.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(out), notebook=False)

    legend = "".join(
        f'<span><i style="background:{c};box-shadow:0 0 10px {c}"></i>{html.escape(v)}</span>' for v, c in sorted(colors.items())
    )
    overlay = OVERLAY.format(inner=BG_INNER, outer=BG_OUTER, count=len(terms), hubs=len(hubs), legend=legend)
    page = out.read_text(encoding="utf-8")
    page = page.replace("<head>", '<head>\n<title>tezeta, an exploration</title>\n<link rel="icon" type="image/svg+xml" href="favicon.svg">\n<meta name="viewport" content="width=device-width, initial-scale=1">', 1)
    data = {"terms": terms, "hubs": hubs, "colors": colors}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    fx = (Path(__file__).parent / "graph_fx.js").read_text(encoding="utf-8")
    page = page.replace("</body>", f"{overlay}<script>const TZ = {payload};</script>\n<script>{fx}</script>\n</body>", 1)
    out.write_text(page, encoding="utf-8")
    shutil.copy(Path(__file__).parent / "favicon.svg", out.parent / "favicon.svg")
    print(f"wrote {out}: {len(terms)} terms, {len(hubs)} shared-word hubs")


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/terms.csv")
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else "dist/index.html")
    build(read_terms(src), dest)
