"""Per-term pages and social preview images for Tezeta.

Imported by build_graph.py. For every term this writes

    dist/t/<slug>/index.html   a crawlable page with Open Graph / Twitter tags
    dist/og/<slug>.jpg         a 1200x630 preview card

plus dist/og/site.jpg, dist/sitemap.xml and dist/robots.txt. Link previews
(Slack, iMessage, X, Bluesky, ...) read the tags from these static pages, since
crawlers do not run the graph's JavaScript or see #hash links.
"""
import hashlib
import html
import math
import os
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from string import Template

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).parent / "fonts"
W, H = 1200, 630
INNER, OUTER = (26, 16, 48), (5, 3, 12)
CREAM = (239, 231, 214)
HUB = (242, 230, 201)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


@lru_cache(maxsize=None)
def _font(italic: bool, size: int, weight: int) -> ImageFont.FreeTypeFont:
    name = "CormorantGaramond-Italic[wght].ttf" if italic else "CormorantGaramond[wght].ttf"
    f = ImageFont.truetype(str(FONTS / name), size)
    f.set_variation_by_axes([weight])
    return f


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int, max_lines: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" ,.;:") + "…"
    return lines


def _background(seed: str) -> Image.Image:
    base = Image.composite(Image.new("RGB", (W, H), OUTER), Image.new("RGB", (W, H), INNER), Image.radial_gradient("L").resize((W, H)))
    d = ImageDraw.Draw(base)
    rng = random.Random(seed)
    for _ in range(110):
        x, y, a = rng.randrange(W), rng.randrange(H), rng.uniform(0.15, 0.6)
        d.point((x, y), fill=tuple(int(v * a) for v in CREAM))
        if rng.random() < 0.15:
            d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=tuple(int(v * a) for v in CREAM))
    return base


def _constellation(img: Image.Image, nodes: list[tuple[int, int, int, tuple[int, int, int]]], edges: list[tuple[int, int]]) -> Image.Image:
    """Draw nodes (x, y, r, rgb) and edges with an additive glow."""
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for a, b in edges:
        (x1, y1, _, c1), (x2, y2, _, _) = nodes[a], nodes[b]
        gd.line((x1, y1, x2, y2), fill=tuple(int(v * 0.55) for v in c1), width=3)
    for x, y, r, c in nodes:
        R = r * 3.2
        gd.ellipse((x - R, y - R, x + R, y + R), fill=tuple(int(v * 0.26) for v in c))
    img = ImageChops.add(img, glow.filter(ImageFilter.GaussianBlur(34)))
    d = ImageDraw.Draw(img)
    for a, b in edges:
        (x1, y1, _, c1), (x2, y2, _, _) = nodes[a], nodes[b]
        d.line((x1, y1, x2, y2), fill=tuple(int(v * 0.6) for v in c1), width=2)
    for x, y, r, c in nodes:
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)
    return img


def draw_term_card(path: Path, slug: str, term: str, definition: str, vibe: str, color: str) -> None:
    c = _hex(color)
    img = _background(slug)
    rng = random.Random(slug + "layout")
    cx, cy = 905, 315
    nodes = [(cx, cy, 78, c)]
    for k in range(4):  # shared-word satellites, placed deterministically per term
        ang = rng.uniform(0, 6.283)
        dist = rng.uniform(150, 230)
        nodes.append((int(cx + dist * 0.95 * math.cos(ang)), int(cy + dist * 0.8 * math.sin(ang)), rng.choice([9, 11, 14]), HUB))
    edges = [(0, i) for i in range(1, len(nodes))]
    img = _constellation(img, nodes, edges)

    d = ImageDraw.Draw(img)
    size = 150
    while size > 56 and d.textlength(term, font=_font(False, size, 500)) > 640:
        size -= 6
    d.text((80, 118), term, font=_font(False, size, 500), fill=CREAM)
    chip_font = _font(True, 34, 500)
    label = vibe or "unsorted"
    tw = d.textlength(label, font=chip_font)
    chip_y = 118 + int(size * 1.12) + 22
    d.rounded_rectangle((80, chip_y, 80 + tw + 44, chip_y + 54), radius=27, outline=c, width=2)
    d.text((102, chip_y + 5), label, font=chip_font, fill=c)
    body_font = _font(True, 42, 500)
    for n, line in enumerate(_wrap(d, definition, body_font, 640, 3)):
        d.text((80, chip_y + 92 + n * 54), line, font=body_font, fill=tuple(int(v * 0.88) for v in CREAM))
    d.text((80, H - 74), "tezeta, an exploration", font=_font(True, 32, 500), fill=tuple(int(v * 0.55) for v in CREAM))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path, quality=86, subsampling=0)


def draw_site_card(path: Path, colors: list[str]) -> None:
    img = _background("site")
    rng = random.Random("site-constellation")
    palette = [_hex(c) for c in colors] or [(156, 175, 136)]
    nodes: list[tuple[int, int, int, tuple[int, int, int]]] = []
    specs = [(rng.choice([22, 30, 40, 52]), palette[i % len(palette)]) for i in range(9)] + [(rng.choice([8, 10, 12]), HUB) for _ in range(9)]
    for r, c in specs:  # rejection-sample positions so nothing overlaps
        for _ in range(400):
            x, y = int(rng.uniform(640, 1140)), int(rng.uniform(70, 560))
            if all(math.hypot(x - x2, y - y2) > r + r2 + 34 for x2, y2, r2, _ in nodes):
                break
        nodes.append((x, y, r, c))
    edges = [(i, 9 + (i * 2) % 9) for i in range(9)] + [(i, 9 + (i * 2 + 1) % 9) for i in range(9)]
    img = _constellation(img, nodes, edges)
    d = ImageDraw.Draw(img)
    d.text((80, 190), "tezeta", font=_font(False, 170, 500), fill=CREAM)
    d.text((86, 392), "an exploration", font=_font(True, 62, 500), fill=tuple(int(v * 0.8) for v in CREAM))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path, quality=86, subsampling=0)


PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$term · tezeta</title>
<meta name="description" content="$definition">
<link rel="canonical" href="$url">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:type" content="article">
<meta property="og:site_name" content="tezeta, an exploration">
<meta property="og:title" content="$term · tezeta">
<meta property="og:description" content="$definition">
<meta property="og:url" content="$url">
<meta property="og:image" content="$image">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="$term, a $vibe term in the tezeta graph">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="$term · tezeta">
<meta name="twitter:description" content="$definition">
<meta name="twitter:image" content="$image">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;1,400&display=swap" rel="stylesheet">
<style>
  :root { --c: $color; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; color: #efe7d6; font-family: "Cormorant Garamond", Georgia, serif;
    background: #05030c radial-gradient(ellipse at 50% 30%, #1a1030 0%, #05030c 75%) fixed; }
  body::before { content: ""; position: fixed; inset: 0; pointer-events: none;
    background: radial-gradient(circle at 50% 38%, color-mix(in srgb, var(--c) 22%, transparent), transparent 46%); }
  .top { position: relative; padding: 28px 36px; }
  .top a { color: #efe7d6; text-decoration: none; font-size: 2rem; letter-spacing: .14em; opacity: .85; }
  main { position: relative; max-width: 680px; margin: 6vh auto 0; padding: 0 24px 80px; }
  h1 { margin: 0 0 .6rem; font-weight: 500; font-size: clamp(3rem, 11vw, 5.5rem); line-height: 1; letter-spacing: .02em; }
  .chip { display: inline-block; padding: .1rem .9rem; border: 1px solid var(--c); border-radius: 99px; color: var(--c); font-style: italic; font-size: 1.2rem;
    box-shadow: 0 0 18px color-mix(in srgb, var(--c) 40%, transparent); }
  .def { margin: 1.6rem 0 0; font-size: clamp(1.5rem, 4.5vw, 2.1rem); line-height: 1.4; font-style: italic; }
  h2 { margin: 2.4rem 0 .7rem; font-size: .85rem; font-weight: 500; letter-spacing: .24em; text-transform: uppercase; opacity: .55; }
  .tags, .rel { display: flex; flex-wrap: wrap; gap: .5rem; }
  .tags span { padding: .1rem .75rem; font-size: 1.1rem; background: rgba(242, 230, 201, .1); border-radius: 99px; }
  .rel a { padding: .1rem .85rem; font-size: 1.25rem; color: #efe7d6; text-decoration: none; border: 1px solid rgba(239, 231, 214, .3); border-radius: 99px; }
  .rel a:hover { background: rgba(239, 231, 214, .14); }
  .more { margin: .7rem 0 0; font-style: italic; opacity: .55; }
  .go { display: inline-block; margin-top: 2.6rem; padding: .55rem 1.5rem; font-size: 1.3rem; font-style: italic; color: #05030c; text-decoration: none;
    background: var(--c); border-radius: 99px; box-shadow: 0 0 28px color-mix(in srgb, var(--c) 55%, transparent); }
  footer { position: relative; text-align: center; padding: 0 0 40px; font-style: italic; opacity: .45; }
</style>
</head>
<body>
<div class="top"><a href="/" aria-label="tezeta, back to the graph">tezeta</a></div>
<main>
  <h1>$term</h1>
  <span class="chip">$vibe</span>
  <p class="def">$definition</p>
  $shares
  $related
  <a class="go" href="/#$slug">see it in the graph &rarr;</a>
</main>
<footer>tezeta, an exploration</footer>
</body>
</html>
""")


def _section(title: str, inner: str) -> str:
    return f"<h2>{title}</h2>\n  {inner}" if inner else ""


MAX_WORDS, MAX_RELATED = 14, 20
CARD_VERSION = "1"  # bump to force every preview card to be redrawn


def _card_job(job: tuple) -> str:
    path, slug, term, definition, vibe, color = job
    draw_term_card(Path(path), slug, term, definition, vibe, color)
    return path


def _render_cards(out_dir: Path, terms: list[dict], slugs: list[str], colors: dict[str, str]) -> None:
    """Draw one 1200x630 card per term into out_dir/og, reusing cached cards.

    A card is only redrawn when its term, definition or color changes, so a deploy after
    adding ten terms to a library of thousands draws ten cards, not thousands. Drawing
    runs on every CPU core. Set TZ_CARD_CACHE to keep the cache between CI runs.
    """
    cache = Path(os.environ.get("TZ_CARD_CACHE", ".cache/og"))
    cache.mkdir(parents=True, exist_ok=True)
    og = out_dir / "og"
    og.mkdir(parents=True, exist_ok=True)
    jobs, wanted = [], {}
    for t, slug in zip(terms, slugs):
        color = colors[t["vibe"] or "unsorted"]
        key = hashlib.sha1("|".join([CARD_VERSION, slug, t["term"], t["definition"], t["vibe"], color]).encode()).hexdigest()[:12]
        cached = cache / f"{slug}-{key}.jpg"
        wanted[cached.name] = (cached, og / f"{slug}.jpg")
        if not cached.exists():
            jobs.append((str(cached), slug, t["term"], t["definition"], t["vibe"], color))
    if jobs:
        workers = min(os.cpu_count() or 1, len(jobs))
        if workers > 1 and len(jobs) > 8:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                list(pool.map(_card_job, jobs, chunksize=16))
        else:
            for job in jobs:
                _card_job(job)
    for cached, target in wanted.values():
        shutil.copyfile(cached, target)
    for stale in cache.glob("*.jpg"):  # keep the cache from growing without bound
        if stale.name not in wanted:
            stale.unlink()
    print(f"preview cards: {len(jobs)} drawn, {len(terms) - len(jobs)} reused from cache")


def write_site(terms: list[dict], slugs: list[str], hubs: dict[str, list[int]], colors: dict[str, str], out_dir: Path, site_url: str) -> int:
    site_url = site_url.rstrip("/")
    words_of: dict[int, list[str]] = {}
    for w, ix in hubs.items():
        for i in ix:
            words_of.setdefault(i, []).append(w)
    _render_cards(out_dir, terms, slugs, colors)

    for i, t in enumerate(terms):
        slug, vibe = slugs[i], t["vibe"] or "unsorted"
        words = sorted(words_of.get(i, []), key=lambda w: (len(hubs[w]), w))  # rarest (most specific) first
        score: dict[int, int] = {}
        for w in words:
            for j in hubs[w]:
                if j != i:
                    score[j] = score.get(j, 0) + 1
        ranked = sorted(score, key=lambda j: (-score[j], terms[j]["term"].lower()))
        related = ranked[:MAX_RELATED]
        tags = "".join("<span>" + html.escape(w) + "</span>" for w in words[:MAX_WORDS])
        tags_html = f'<div class="tags">{tags}</div>' if words else ""
        links = "".join('<a href="/t/' + slugs[j] + '/">' + html.escape(terms[j]["term"]) + "</a>" for j in related)
        extra = f'<p class="more">and {len(ranked) - MAX_RELATED} more, in the graph</p>' if len(ranked) > MAX_RELATED else ""
        related_html = f'<div class="rel">{links}</div>{extra}' if related else ""
        page = PAGE.substitute(
            term=html.escape(t["term"]),
            definition=html.escape(t["definition"], quote=True),
            vibe=html.escape(vibe),
            color=colors[vibe],
            slug=html.escape(slug),
            url=f"{site_url}/t/{slug}/",
            image=f"{site_url}/og/{slug}.jpg",
            shares=_section("Shares words", tags_html),
            related=_section("Related", related_html),
        )
        target = out_dir / "t" / slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")

    draw_site_card(out_dir / "og" / "site.jpg", list(colors.values()))
    urls = [f"{site_url}/"] + [f"{site_url}/t/{s}/" for s in slugs]
    (out_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
        + "</urlset>\n",
        encoding="utf-8",
    )
    (out_dir / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site_url}/sitemap.xml\n", encoding="utf-8")
    return len(terms)
