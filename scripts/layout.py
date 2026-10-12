"""Build-time graph layout for Tezeta.

The browser never simulates physics: positions are computed here, once, so the
page loads instantly, the picture is identical for everyone, and the cost stays
flat as the term count grows.

For a big connected component the layout is two-level, so thousands of nodes read
as a map instead of a hairball:

1. Louvain community detection groups terms that share vocabulary.
2. Each community is laid out on its own (Fruchterman-Reingold, igraph's C core).
3. The communities become "islands": placed by a layout of the community graph,
   then pushed apart until none overlap.

Components are then packed on a spiral, largest first, and small ones (single
terms, pairs, trios) are tucked into the gaps around them node by node.
"""
import math
import random
from collections import Counter

import igraph

MIN_GAP = 1.15      # minimum distance between any two nodes, in layout units
BIG = 4             # components with at least this many nodes are packed as blobs
SPLIT = 40          # components at least this big are split into communities
MIN_COMMUNITY = 6   # smaller communities are merged into their best-connected neighbour
ISLAND_GAP = 2.2    # clear space kept between community islands


def _relax(pts: list[tuple[float, float]], gap: float, rounds: int = 12) -> list[tuple[float, float]]:
    """Push apart nodes closer than `gap` (grid-hashed, so it stays fast for thousands of nodes)."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(pts)
    for _ in range(rounds):
        grid: dict[tuple[int, int], list[int]] = {}
        for i in range(n):
            grid.setdefault((int(xs[i] // gap), int(ys[i] // gap)), []).append(i)
        moved = False
        for i in range(n):
            gx, gy = int(xs[i] // gap), int(ys[i] // gap)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid.get((gx + dx, gy + dy), ()):
                        if j <= i:
                            continue
                        ddx, ddy = xs[j] - xs[i], ys[j] - ys[i]
                        d = math.hypot(ddx, ddy)
                        if d < gap:
                            if d < 1e-6:
                                ddx, ddy, d = random.random() - 0.5, random.random() - 0.5, 1.0
                            push = (gap - d) / 2 / d
                            xs[i] -= ddx * push; ys[i] -= ddy * push
                            xs[j] += ddx * push; ys[j] += ddy * push
                            moved = True
        if not moved:
            break
    return list(zip(xs, ys))


def _fr(g: igraph.Graph, vertices: list[int]) -> list[tuple[float, float]]:
    """Fruchterman-Reingold for an induced subgraph, centred and scaled to a roughly constant node spacing."""
    size = len(vertices)
    if size == 1:
        return [(0.0, 0.0)]
    if size == 2:
        return [(-0.6, 0.0), (0.6, 0.0)]
    lay = g.induced_subgraph(vertices).layout_fruchterman_reingold(niter=500 if size < 2000 else 300)
    xs, ys = [p[0] for p in lay.coords], [p[1] for p in lay.coords]
    cx, cy = sum(xs) / size, sum(ys) / size
    rms = math.sqrt(sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in zip(xs, ys)) / size) or 1.0
    scale = (0.55 * math.sqrt(size) + 0.8) / rms
    pts = _relax([((x - cx) * scale, (y - cy) * scale) for x, y in zip(xs, ys)], MIN_GAP)
    mx, my = sum(p[0] for p in pts) / size, sum(p[1] for p in pts) / size
    return [(x - mx, y - my) for x, y in pts]


def _radius(pts: list[tuple[float, float]]) -> float:
    return max(math.hypot(x, y) for x, y in pts) + MIN_GAP


def _communities(g: igraph.Graph, vertices: list[int]) -> list[list[int]]:
    """Split a component into communities (lists of global vertex ids)."""
    sub = g.induced_subgraph(vertices)
    memb = sub.community_multilevel().membership
    sizes = Counter(memb)
    # fold tiny communities into whichever neighbour community they touch most
    target: dict[int, int] = {}
    for c, sz in sizes.items():
        if sz >= MIN_COMMUNITY:
            continue
        touch: Counter = Counter()
        for v in (i for i, m in enumerate(memb) if m == c):
            for nb in sub.neighbors(v):
                if memb[nb] != c:
                    touch[memb[nb]] += 1
        if touch:
            target[c] = touch.most_common(1)[0][0]
    memb = [target.get(m, m) for m in memb]
    groups: dict[int, list[int]] = {}
    for local_id, m in enumerate(memb):
        groups.setdefault(m, []).append(vertices[local_id])
    return sorted(groups.values(), key=len, reverse=True)


def _separate_islands(centers: list[list[float]], radii: list[float]) -> None:
    """Compact circles toward their common centre, then push them apart (in place) until none overlap.

    Gravity first: without it an outlier in the community-graph layout stays stranded far from the rest
    and the camera zooms out to fit it. Overlaps are resolved every round and once more at the end.
    """
    k = len(centers)
    weight = [r * r for r in radii]
    total = sum(weight) or 1.0

    def resolve() -> bool:
        moved = False
        for i in range(k):
            for j in range(i + 1, k):
                dx, dy = centers[j][0] - centers[i][0], centers[j][1] - centers[i][1]
                d = math.hypot(dx, dy) or 1e-6
                need = radii[i] + radii[j] + ISLAND_GAP
                if d < need:
                    push = (need - d) / 2 / d
                    centers[i][0] -= dx * push; centers[i][1] -= dy * push
                    centers[j][0] += dx * push; centers[j][1] += dy * push
                    moved = True
        return moved

    rounds = max(20, min(150, int(3e6 / (k * k))))
    for _ in range(rounds):
        gx = sum(c[0] * w for c, w in zip(centers, weight)) / total
        gy = sum(c[1] * w for c, w in zip(centers, weight)) / total
        for c in centers:
            c[0] += (gx - c[0]) * 0.06
            c[1] += (gy - c[1]) * 0.06
        resolve()
    for _ in range(100 if k < 400 else 20):
        if not resolve():
            break


def _island_layout(g: igraph.Graph, vertices: list[int]) -> tuple[list[tuple[float, float]], list[dict]]:
    """Two-level layout of one big component. Returns local points (aligned with `vertices`) and island geometry."""
    groups = _communities(g, vertices)
    if len(groups) < 2:
        return _fr(g, vertices), []
    where = {v: gi for gi, grp in enumerate(groups) for v in grp}

    # layout of the community graph decides which islands sit next to each other
    sub = g.induced_subgraph(vertices)
    idx = {v: i for i, v in enumerate(vertices)}
    super_g = igraph.Graph(n=len(groups), edges=list({tuple(sorted((where[vertices[a]], where[vertices[b]]))) for a, b in sub.get_edgelist() if where[vertices[a]] != where[vertices[b]]}))
    sl = super_g.layout_fruchterman_reingold(niter=400).coords if super_g.ecount() else [(random.random(), random.random()) for _ in groups]

    local = [_fr(g, grp) for grp in groups]
    radii = [_radius(pts) if len(pts) > 1 else MIN_GAP * 1.2 for pts in local]
    sx, sy = [p[0] for p in sl], [p[1] for p in sl]
    cx, cy = sum(sx) / len(sx), sum(sy) / len(sy)
    rms = math.sqrt(sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in zip(sx, sy)) / len(sx)) or 1.0
    area = sum(math.pi * (r + ISLAND_GAP) ** 2 for r in radii)
    spread = math.sqrt(area / math.pi) * 0.9 / rms  # start roughly as dense as the islands allow, then separate
    centers = [[(x - cx) * spread, (y - cy) * spread] for x, y in zip(sx, sy)]
    _separate_islands(centers, radii)

    pts: list[tuple[float, float]] = [(0.0, 0.0)] * len(vertices)
    islands = []
    for gi, grp in enumerate(groups):
        for v, (x, y) in zip(grp, local[gi]):
            pts[idx[v]] = (centers[gi][0] + x, centers[gi][1] + y)
        islands.append({"vertices": grp, "x": centers[gi][0], "y": centers[gi][1], "r": radii[gi]})
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    for isl in islands:
        isl["x"] -= mx
        isl["y"] -= my
    return [(x - mx, y - my) for x, y in pts], islands


class _NodeIndex:
    """Spatial hash of placed nodes, for gap-filling placement."""

    def __init__(self, cell: float) -> None:
        self.cell = cell
        self.grid: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def add(self, x: float, y: float) -> None:
        self.grid.setdefault((int(x // self.cell), int(y // self.cell)), []).append((x, y))

    def free(self, x: float, y: float, gap: float) -> bool:
        gx, gy = int(x // self.cell), int(y // self.cell)
        reach = int(gap // self.cell) + 1
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for ox, oy in self.grid.get((gx + dx, gy + dy), ()):
                    if math.hypot(x - ox, y - oy) < gap:
                        return False
        return True


def layout(n_terms: int, hubs: dict[str, list[int]], seed: int = 7):
    """Lay out terms (vertices 0..n-1) and shared words (the rest, in dict order).

    Returns (term positions, hub positions, islands, membership). Each island is
    {"x", "y", "r", "vertices"}: a community of a big component, for labelling.
    `membership` gives every vertex its island number (-1 for vertices outside any island),
    which the browser uses to tell short links inside a cluster from long links between clusters.
    """
    words = list(hubs)
    n = n_terms + len(words)
    edges = [(i, n_terms + k) for k, w in enumerate(words) for i in hubs[w]]
    g = igraph.Graph(n=n, edges=edges)
    random.seed(seed)  # python-igraph draws its random starts from `random`

    comps = sorted(g.connected_components(), key=len, reverse=True)
    big, small = [c for c in comps if len(c) >= BIG], [c for c in comps if len(c) < BIG]

    local: list[list[tuple[float, float]]] = []
    comp_islands: list[list[dict]] = []
    radius: list[float] = []
    for comp in big:
        if len(comp) >= SPLIT:
            pts, islands = _island_layout(g, list(comp))
        else:
            pts, islands = _fr(g, list(comp)), []
        local.append(pts)
        comp_islands.append(islands)
        radius.append(_radius(pts))

    pos: list[tuple[float, float]] = [(0.0, 0.0)] * n
    index = _NodeIndex(MIN_GAP * 2)
    all_islands: list[dict] = []

    # big components: circle-pack on an outward Archimedean spiral
    placed: list[tuple[float, float, float]] = []
    for ci, comp in enumerate(big):
        r = radius[ci]
        cx = cy = 0.0
        if placed:
            theta, rad = 0.0, 0.0
            while True:
                cx, cy = rad * math.cos(theta), rad * math.sin(theta)
                if all(math.hypot(cx - ox, cy - oy) >= r + orad + 1.0 for ox, oy, orad in placed):
                    break
                theta += 0.15
                rad += (r + 1.0) * 0.012
        placed.append((cx, cy, r))
        for v, (x, y) in zip(comp, local[ci]):
            pos[v] = (cx + x, cy + y)
            index.add(*pos[v])
        for isl in comp_islands[ci]:
            all_islands.append({"x": cx + isl["x"], "y": cy + isl["y"], "r": isl["r"], "vertices": isl["vertices"]})

    # small components: fill gaps node by node, spiralling out from the centre
    for comp in small:
        shape = {1: [(0.0, 0.0)], 2: [(-0.6, 0.0), (0.6, 0.0)], 3: [(-0.7, -0.4), (0.7, -0.4), (0.0, 0.8)]}[len(comp)]
        theta, rad = random.random() * 6.28, 0.0
        while True:
            cx, cy = rad * math.cos(theta), rad * math.sin(theta)
            if all(index.free(cx + x, cy + y, MIN_GAP * 1.6) for x, y in shape):
                break
            theta += 0.35
            rad += 0.045
        for v, (x, y) in zip(comp, shape):
            pos[v] = (cx + x, cy + y)
            index.add(*pos[v])

    member = [-1] * n
    for k, isl in enumerate(all_islands):
        for v in isl["vertices"]:
            member[v] = k
    pos = [(round(x, 2), round(y, 2)) for x, y in pos]
    for isl in all_islands:
        isl["x"], isl["y"], isl["r"] = round(isl["x"], 2), round(isl["y"], 2), round(isl["r"], 2)
    return pos[:n_terms], {w: pos[n_terms + k] for k, w in enumerate(words)}, all_islands, member
