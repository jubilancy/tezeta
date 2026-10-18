// Tezeta front end. Sigma.js draws the graph with WebGL; this file adds the look
// (glow, nebulae, stars), focus mode, search, deep links and the info panel.
// `TZ` (terms, hubs, positions, colors) is injected by build_graph.py. Layout is
// precomputed at build time, so nothing here simulates physics.
(function () {
  "use strict";
  const BG = [5, 3, 12], CREAM = "#efe7d6", HUB = "#f2e6c9";
  const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const rgba = (h, a) => { const [r, g, b] = hexRgb(h); return `rgba(${r},${g},${b},${a})`; };
  const mix = (h, k) => { const [r, g, b] = hexRgb(h); const m = (c, bg) => Math.round(c * (1 - k) + bg * k); return `rgb(${m(r, BG[0])},${m(g, BG[1])},${m(b, BG[2])})`; };
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  // ---- links inside definitions ---------------------------------------------------
  // Only http(s) addresses become links; long ones get a break point after each / ? & = # so they wrap neatly.
  const URL_RE = /(?:https?:\/\/|www\.)[^\s<>"']+/gi;
  const CLOSERS = { ")": "(", "]": "[", "}": "{" };
  const count = (str, ch) => str.split(ch).length - 1;
  const trimUrl = (u) => {
    while (u) {
      const c = u[u.length - 1];
      if (".,;:!?'\"".includes(c) || (CLOSERS[c] && count(u, c) > count(u, CLOSERS[c]))) u = u.slice(0, -1); else break;
    }
    return u;
  };
  const hrefOf = (u) => { try { const x = new URL(/^www\./i.test(u) ? "https://" + u : u); return /^https?:$/.test(x.protocol) && x.hostname ? x.href : null; } catch { return null; } };
  const hostOf = (u) => { const h = hrefOf(u); return h ? new URL(h).hostname.replace(/^www\./, "") : u; };
  function linkify(text) {
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of text.matchAll(URL_RE)) {
      const url = trimUrl(m[0]), href = url && hrefOf(url);
      if (!href) continue;
      frag.append(text.slice(last, m.index));
      const a = document.createElement("a");
      a.className = "tz-link"; a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer nofollow";
      const shown = url.replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/$/, "");
      shown.split(/(?<=[\/?&=#])/).forEach((part, i) => { if (i) a.append(document.createElement("wbr")); a.append(part); });
      frag.append(a);
      last = m.index + url.length;
    }
    frag.append(text.slice(last));
    return frag;
  }
  const plainText = (text) => text.replace(URL_RE, (m) => { const u = trimUrl(m); return u && hrefOf(u) ? hostOf(u) + m.slice(u.length) : m; });
  const isTerm = (id) => id[0] === "t";
  const colorOf = (t) => TZ.colors[t.vibe || "unsorted"];

  // ---- build the graph -------------------------------------------------------
  const words = Object.keys(TZ.hubs), nT = TZ.terms.length, total = nT + words.length;
  const deg = new Array(nT).fill(0);
  words.forEach((w) => TZ.hubs[w].forEach((i) => deg[i]++));
  // node radius scales with how much room each node has, so 20 terms and 5,000 both look right
  const base = Math.min(18, 0.25 * Math.sqrt(1.1e6 / total));
  const crowded = total > 400;
  let linked = 0; // edges inside a cluster; long links between clusters are only drawn for what you hover or select
  const graph = new graphology.Graph({ type: "undirected" });
  TZ.terms.forEach((t, i) => {
    const c = colorOf(t);
    graph.addNode("t" + i, { x: t.x, y: t.y, label: t.term, size: base * (0.7 + 0.18 * Math.sqrt(deg[i])), color: c, dim: mix(c, 0.8), ph: Math.random() * 6.28 });
  });
  words.forEach((w, k) => {
    const [x, y] = TZ.hubPos[w];
    graph.addNode("w:" + w, { x, y, label: w, size: base * (0.3 + 0.03 * Math.sqrt(TZ.hubs[w].length)), color: HUB, dim: mix(HUB, 0.85), ph: Math.random() * 6.28 });
    TZ.hubs[w].forEach((i) => {
      const cross = crowded && TZ.tc[i] !== TZ.hc[k];
      if (!cross) linked++;
      graph.addEdge("t" + i, "w:" + w, { rgb: hexRgb(colorOf(TZ.terms[i])).join(","), size: crowded ? 0.55 : 0.7, cross });
    });
  });

  // ---- level of detail: zoomed out you see clusters, zoomed in you see the links ----
  // A few hundred edges are fine at a glance; thousands turn into a white smear, so edges
  // (and the shared-word nodes that carry them) fade in as you zoom, and are always shown
  // for whatever you hover or select.
  const edgeBase = Math.min(0.32, (0.32 * 600) / Math.max(linked, 1));
  const edgeAlpha = (ratio) => Math.min(crowded ? 0.26 : 0.5, edgeBase * Math.pow(1 / Math.max(ratio, 0.02), 1.5));
  const hubsShown = (ratio) => !crowded || ratio < 0.6;
  let zoom = 1; // camera ratio, mirrored here because reducers can run before `camera` exists
  let band = 0; // zoom band; reducers are re-run only when it changes
  const bandOf = (ratio) => Math.round(Math.log2(1 / Math.max(ratio, 0.01)) * 2);

  // ---- focus state (used by hover, selection and search preview) -------------
  let focus = null; // Set of node ids kept bright, or null for everything
  let lock = null;  // selected node id
  const hubRank = (i) => words.filter((w) => TZ.hubs[w].includes(i));
  function neighborhood(id) {
    const set = new Set([id]);
    graph.forEachNeighbor(id, (n) => {
      set.add(n);
      if (isTerm(id)) graph.forEachNeighbor(n, (m) => set.add(m));
    });
    return set;
  }
  function setFocus(set) { focus = set; renderer.refresh({ skipIndexation: true }); }

  // ---- renderer --------------------------------------------------------------
  const renderer = new Sigma(graph, $("tz-graph"), {
    allowInvalidContainer: true,
    stagePadding: 90,
    renderEdgeLabels: false,
    labelFont: "Georgia, serif",
    labelSize: 13,
    labelColor: { color: CREAM },
    labelDensity: crowded ? 0.4 : 0.7,
    labelGridCellSize: crowded ? 150 : 120,
    labelRenderedSizeThreshold: 4.5,
    minCameraRatio: 0.012,
    maxCameraRatio: 2.5,
    zIndex: true,
    hideEdgesOnMove: graph.size > 15000,
    defaultEdgeColor: "rgba(239,231,214,.2)",
    nodeReducer: (id, d) => {
      if (!focus) return id[0] === "w" && !hubsShown(zoom) ? { ...d, hidden: true } : d;
      if (id === lock) return { ...d, color: "#ffffff", zIndex: 3, forceLabel: true };
      if (focus.has(id)) return { ...d, zIndex: 2, forceLabel: true };
      return { ...d, color: d.dim, label: null, zIndex: 0 };
    },
    edgeReducer: (e, d) => {
      if (!focus) {
        const a = edgeAlpha(zoom);
        return d.cross || a < 0.02 ? { ...d, hidden: true } : { ...d, color: `rgba(${d.rgb},${a.toFixed(3)})` };
      }
      const [a, b] = graph.extremities(e);
      return focus.has(a) && focus.has(b) ? { ...d, color: `rgba(${d.rgb},0.7)`, size: 1, zIndex: 1 } : { ...d, hidden: true };
    },
    defaultDrawNodeHover: (ctx, d, s) => {
      ctx.font = `${s.labelWeight} ${s.labelSize + 1}px ${s.labelFont}`;
      ctx.fillStyle = "#fff";
      ctx.fillText(d.label || "", d.x + d.size + 4, d.y + s.labelSize / 3);
    },
  });
  const camera = renderer.getCamera();
  zoom = camera.ratio;
  band = bandOf(zoom);
  camera.on("updated", () => {
    zoom = camera.ratio;
    const b = bandOf(zoom);
    if (b !== band) { band = b; renderer.refresh({ skipIndexation: true }); }
  });

  // ---- backdrop: stars, glow halos, nebula clouds (2D canvases behind WebGL) -
  const sky = $("tz-sky"), skyCtx = sky.getContext("2d");
  const glow = $("tz-glow"), gctx = glow.getContext("2d");
  const names = $("tz-names"), nctx = names.getContext("2d");
  const dpr = Math.min(devicePixelRatio || 1, 2);
  function resize() {
    for (const c of [sky, glow, names]) { c.width = innerWidth * dpr; c.height = innerHeight * dpr; c.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0); }
  }
  addEventListener("resize", resize); resize();

  const stars = Array.from({ length: 240 }, () => ({
    x: Math.random(), y: Math.random(), z: 0.15 + Math.random() * 0.85, r: Math.random() * 1.2 + 0.2, p: Math.random() * 6.28, s: 0.4 + Math.random() * 1.4,
  }));
  function drawSky(t) {
    skyCtx.clearRect(0, 0, innerWidth, innerHeight);
    const st = camera.getState();
    for (const s of stars) {
      const x = (((s.x * innerWidth - st.x * innerWidth * s.z * 0.6) % innerWidth) + innerWidth) % innerWidth;
      const y = (((s.y * innerHeight + st.y * innerHeight * s.z * 0.6) % innerHeight) + innerHeight) % innerHeight;
      const tw = reduceMotion ? 0.7 : 0.55 + 0.45 * Math.sin(t * 0.001 * s.s + s.p);
      skyCtx.fillStyle = `rgba(239,231,214,${0.55 * s.z * tw})`;
      skyCtx.beginPath(); skyCtx.arc(x, y, s.r * s.z + 0.2, 0, 6.283); skyCtx.fill();
    }
  }

  const sprites = {}; // one pre-rendered soft glow per color; drawImage is far cheaper than a gradient per node
  function sprite(color) {
    if (sprites[color]) return sprites[color];
    const c = document.createElement("canvas"); c.width = c.height = 96;
    const x = c.getContext("2d"), g = x.createRadialGradient(48, 48, 6, 48, 48, 48);
    g.addColorStop(0, rgba(color, 1)); g.addColorStop(1, rgba(color, 0));
    x.fillStyle = g; x.fillRect(0, 0, 96, 96);
    return (sprites[color] = c);
  }
  const breathing = !reduceMotion && total <= 2500;
  // Everything per node is cached once; each frame is then one affine transform plus drawImage calls.
  let N = null;
  function cacheNodes() {
    const ids = [], x = [], y = [], size = [], color = [], hub = [], ph = [];
    graph.forEachNode((id, a) => {
      const d = renderer.getNodeDisplayData(id);
      if (!d) return;
      ids.push(id); x.push(d.x); y.push(d.y); size.push(a.size); color.push(a.color); hub.push(id[0] === "w"); ph.push(a.ph);
    });
    N = { ids, x, y, size, color, hub, ph, n: ids.length };
  }
  // nebula clouds are blurry by nature, so they are drawn at quarter resolution and scaled up
  const cloud = document.createElement("canvas"), cctx = cloud.getContext("2d");
  const CLOUD = 4;
  function drawGlow(t) {
    if (!N) cacheNodes();
    if (!N) return;
    const W = innerWidth, H = innerHeight;
    gctx.clearRect(0, 0, W, H);
    const cw = Math.ceil(W / CLOUD), ch = Math.ceil(H / CLOUD);
    if (cloud.width !== cw || cloud.height !== ch) { cloud.width = cw; cloud.height = ch; }
    cctx.clearRect(0, 0, cw, ch);
    cctx.globalCompositeOperation = "lighter";
    gctx.globalCompositeOperation = "lighter";
    const k = 1 / Math.sqrt(camera.ratio);
    const o = renderer.framedGraphToViewport({ x: 0, y: 0 });
    const ex = renderer.framedGraphToViewport({ x: 1, y: 0 }), ey = renderer.framedGraphToViewport({ x: 0, y: 1 });
    const ax = ex.x - o.x, ay = ey.y - o.y;
    const g0 = renderer.graphToViewport({ x: 0, y: 0 }), g1 = renderer.graphToViewport({ x: 1, y: 0 });
    const pxu = Math.abs(g1.x - g0.x); // screen pixels per layout unit
    // Additive glow saturates to white when thousands of terms overlap, so strength falls with how crowded the view is
    let visible = 0;
    for (let i = 0; i < N.n; i++) {
      if (N.hub[i]) continue;
      const px = o.x + ax * N.x[i], py = o.y + ay * N.y[i];
      if (px >= 0 && px <= W && py >= 0 && py <= H) visible++;
    }
    const dens = Math.min(1, Math.pow(250 / Math.max(visible, 1), 0.7));
    const haloA = 0.42 * Math.max(dens, 0.06), haloK = 0.55 + 0.45 * dens;
    const cloudA = 0.03 * Math.min(1, Math.pow(250 / Math.max(visible, 1), 0.4));
    for (let i = 0; i < N.n; i++) {
      const px = o.x + ax * N.x[i], py = o.y + ay * N.y[i];
      const hub = N.hub[i], s = N.size[i] * k;
      const R = s * (hub ? 2.6 : 3.4 * haloK) * (breathing ? 1 + 0.12 * Math.sin(t * 0.0016 + N.ph[i]) : 1) + 4;
      const C = hub ? 0 : Math.max(s * 8, pxu * 3.5);
      const reach = Math.max(R, C);
      if (px < -reach || px > W + reach || py < -reach || py > H + reach) continue;
      const on = !focus || focus.has(N.ids[i]) ? 1 : 0.1;
      const img = sprite(N.color[i]);
      if (!hub || s > 2) {
        gctx.globalAlpha = (hub ? 0.2 * Math.max(dens, 0.1) : haloA) * on;
        gctx.drawImage(img, px - R, py - R, 2 * R, 2 * R);
      }
      if (!hub && on === 1) { // nebula: wide faint clouds that pool where terms cluster
        cctx.globalAlpha = cloudA;
        cctx.drawImage(img, (px - C) / CLOUD, (py - C) / CLOUD, (2 * C) / CLOUD, (2 * C) / CLOUD);
      }
    }
    gctx.globalAlpha = 1;
    gctx.imageSmoothingEnabled = true;
    gctx.drawImage(cloud, 0, 0, cw, ch, 0, 0, cw * CLOUD, ch * CLOUD);
    drawClusterNames(W, H, pxu);
  }
  // cluster names, like constellation labels on a star chart; they fade out as you zoom in
  function drawClusterNames(W, H, pxu) {
    nctx.clearRect(0, 0, W, H);
    if (!TZ.islands.length || focus) return;
    const fade = Math.min(1, Math.max(0, (camera.ratio - 0.16) / 0.3));
    if (fade < 0.01) return;
    nctx.textAlign = "center"; nctx.textBaseline = "middle";
    nctx.shadowColor = "rgba(5,3,12,0.95)"; nctx.shadowBlur = 10;
    const taken = [];
    for (const isl of TZ.islands) { // sorted biggest first, so big clusters win label collisions
      const c = renderer.graphToViewport({ x: isl.x, y: isl.y }), rpx = isl.r * pxu;
      if (rpx < 26 || rpx * 2 > W * 0.95 || c.x < -rpx || c.x > W + rpx || c.y < -rpx || c.y > H + rpx) continue;
      const size = Math.max(13, Math.min(40, rpx * 0.2));
      nctx.font = `italic ${size}px "Cormorant Garamond", Georgia, serif`;
      const w = nctx.measureText(isl.label).width, h = size * 1.2;
      const box = [c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2];
      if (taken.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
      taken.push(box);
      nctx.fillStyle = `rgba(239,231,214,${(0.8 * fade * Math.min(1, (rpx - 26) / 30)).toFixed(3)})`;
      nctx.fillText(isl.label, c.x, c.y);
    }
    nctx.shadowBlur = 0;
  }
  // The backdrop repaints after every Sigma render, but never more often than it can afford:
  // cheap on small graphs (every frame), spaced out on huge ones so panning stays smooth.
  let glowCost = 0, glowAt = 0, glowTimer = null;
  function paintBackdrop() {
    const t0 = performance.now();
    drawGlow(t0); drawSky(t0);
    const cost = performance.now() - t0;
    glowCost = glowCost ? glowCost * 0.6 + cost * 0.4 : cost;
    glowAt = t0;
  }
  function backdropSoon() {
    if (glowTimer) return;
    const wait = Math.min(200, glowCost * 2) - (performance.now() - glowAt);
    if (wait <= 0) paintBackdrop();
    else glowTimer = setTimeout(() => { glowTimer = null; paintBackdrop(); }, wait);
  }
  renderer.on("afterRender", backdropSoon);
  // Sigma renders once inside its constructor, before the listener above exists, so paint the first frame by hand
  setTimeout(paintBackdrop, 0);
  if (breathing) {
    let last = 0;
    (function frame(t) {
      requestAnimationFrame(frame);
      if (t - last < 40) return;
      last = t; drawGlow(t); drawSky(t);
    })(0);
  }

  // ---- hover tooltip ---------------------------------------------------------
  const tip = $("tz-tip"); let mx = 0, my = 0;
  addEventListener("mousemove", (e) => {
    mx = e.clientX; my = e.clientY;
    if (tip.classList.contains("on")) { tip.style.left = Math.min(mx + 16, innerWidth - 300) + "px"; tip.style.top = my + 16 + "px"; }
  });
  function showTip(id) {
    tip.replaceChildren();
    if (isTerm(id)) {
      const t = TZ.terms[+id.slice(1)];
      const b = el("b", null, t.term); tip.append(b, document.createTextNode("  "), el("i", null, "· " + (t.vibe || "unsorted")), el("div", null, plainText(t.definition)));
    } else {
      const w = id.slice(2);
      tip.append(el("b", null, w), document.createTextNode("  "), el("i", null, "· shared word"), el("div", null, TZ.hubs[w].length + " terms"));
    }
    tip.style.left = Math.min(mx + 16, innerWidth - 300) + "px"; tip.style.top = my + 16 + "px";
    tip.classList.add("on");
  }
  renderer.on("enterNode", ({ node }) => {
    $("tz-graph").style.cursor = "pointer"; showTip(node);
    if (!lock) setFocus(neighborhood(node));
  });
  renderer.on("leaveNode", () => { $("tz-graph").style.cursor = ""; tip.classList.remove("on"); if (!lock) setFocus(null); });
  renderer.on("clickNode", ({ node }) => select(node));
  renderer.on("clickStage", () => { if (lock) clearLock(); });

  // ---- info panel ------------------------------------------------------------
  const panel = el("aside"); panel.id = "tz-panel"; document.body.appendChild(panel);
  const MAX_RELATED = 20;
  function relatedOf(i) { // other terms ranked by how many words they share with term i
    const score = new Map();
    hubRank(i).forEach((w) => TZ.hubs[w].forEach((j) => j !== i && score.set(j, (score.get(j) || 0) + 1)));
    return [...score.entries()].sort((a, b) => b[1] - a[1] || TZ.terms[a[0]].term.localeCompare(TZ.terms[b[0]].term)).map((e) => e[0]);
  }
  function termButtons(ix) {
    const list = el("div", "tz-rel");
    ix.slice(0, MAX_RELATED).forEach((j) => { const b = el("button", null, TZ.terms[j].term); b.onclick = () => select("t" + j); list.append(b); });
    return list;
  }
  function more(n) { return n > MAX_RELATED ? el("p", null, `and ${n - MAX_RELATED} more, in the graph`) : null; }
  function showPanel(id) {
    panel.replaceChildren();
    const close = el("button", "tz-x", "×"); close.onclick = clearLock; panel.append(close);
    if (isTerm(id)) {
      const i = +id.slice(1), t = TZ.terms[i], c = colorOf(t);
      panel.append(el("h2", null, t.term));
      const chip = el("span", "tz-chip", t.vibe || "unsorted"); chip.style.setProperty("--c", c); panel.append(chip);
      const def = el("p", "tz-def"); def.style.setProperty("--c", c); def.append(linkify(t.definition)); panel.append(def);
      const act = el("div", "tz-actions");
      const open = el("a", null, "open page ↗"); open.href = "t/" + t.slug + "/";
      const copy = el("button", null, "copy link");
      copy.onclick = async () => {
        const url = new URL("t/" + t.slug + "/", location.href).href;
        try { await navigator.clipboard.writeText(url); copy.textContent = "copied ✓"; } catch { copy.textContent = "press Ctrl+C on the address bar"; }
        setTimeout(() => (copy.textContent = "copy link"), 1800);
      };
      act.append(open, copy); panel.append(act);
      const ws = hubRank(i).sort((a, b) => TZ.hubs[a].length - TZ.hubs[b].length || a.localeCompare(b));
      if (ws.length) {
        panel.append(el("h3", null, "Shares words"));
        const row = el("div", "tz-tags"); ws.slice(0, 14).forEach((w) => row.append(el("span", null, w))); panel.append(row);
        const rel = relatedOf(i);
        panel.append(el("h3", null, "Related"), termButtons(rel));
        const m = more(rel.length); if (m) { m.id = "tz-more"; panel.append(m); }
      }
    } else {
      const w = id.slice(2), ix = [...TZ.hubs[w]].sort((a, b) => TZ.terms[a].term.localeCompare(TZ.terms[b].term));
      panel.append(el("h2", null, w), el("span", "tz-chip", "shared word"), el("h3", null, "Appears in"), termButtons(ix));
      const m = more(ix.length); if (m) { m.id = "tz-more"; panel.append(m); }
    }
    panel.classList.add("open");
  }

  // ---- deep links: tezeta.web.app/#index opens straight to that term ---------
  const slugIndex = {};
  TZ.terms.forEach((t, i) => (slugIndex[t.slug] = "t" + i));
  const hashId = () => { try { return slugIndex[decodeURIComponent(location.hash.slice(1)).toLowerCase()] || null; } catch { return null; } };
  function syncHash(id) {
    const want = id && isTerm(id) ? "#" + TZ.terms[+id.slice(1)].slug : "";
    if (location.hash !== want) history.replaceState(null, "", location.pathname + location.search + want);
  }

  const focusRatio = total <= 80 ? 0.55 : 0.22;
  function select(id) {
    lock = id; syncHash(id); setFocus(neighborhood(id)); showPanel(id);
    const d = renderer.getNodeDisplayData(id);
    if (d) camera.animate({ x: d.x, y: d.y, ratio: Math.min(camera.ratio, focusRatio) }, { duration: 700 });
  }
  function clearLock() { lock = null; syncHash(null); setFocus(null); panel.classList.remove("open"); }
  addEventListener("keydown", (e) => { if (e.key === "Escape") clearLock(); });
  addEventListener("hashchange", () => {
    const id = hashId();
    if (id && id !== lock) select(id); else if (!id && lock) clearLock();
  });

  // ---- search: type a term, arrow keys + enter (or click) to fly to it ------
  const box = el("div"); box.id = "tz-search";
  const input = el("input"); input.type = "search"; input.placeholder = "search terms  ( / )";
  input.setAttribute("aria-label", "Search terms"); input.autocomplete = "off"; input.spellcheck = false;
  const results = el("ul"); results.id = "tz-results"; results.setAttribute("role", "listbox");
  box.append(input, results); document.body.appendChild(box);
  let hits = [], cursor = 0;

  const lowerNames = TZ.terms.map((t) => t.term.toLowerCase());
  const lowerDefs = TZ.terms.map((t) => (t.definition || "").toLowerCase());
  function search(q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    const out = [];
    for (let i = 0; i < nT; i++) {
      const n = lowerNames[i], v = (TZ.terms[i].vibe || "").toLowerCase();
      const s = n === q ? 0 : n.startsWith(q) ? 1 : n.includes(q) ? 2 : v === q ? 3 : lowerDefs[i].includes(q) ? 4 : -1;
      if (s >= 0) out.push({ id: "t" + i, label: TZ.terms[i].term, note: TZ.terms[i].vibe || "", color: colorOf(TZ.terms[i]), s });
    }
    for (const w of words) if (w.includes(q)) out.push({ id: "w:" + w, label: w, note: "shared word", color: HUB, s: 2.5 });
    return out.sort((a, b) => a.s - b.s || a.label.localeCompare(b.label));
  }
  function renderHits() {
    results.replaceChildren(...hits.slice(0, 7).map((h, k) => {
      const li = el("li", k === cursor ? "on" : ""); li.setAttribute("role", "option");
      const dot = el("i"); dot.style.background = h.color; dot.style.boxShadow = "0 0 8px " + h.color;
      li.append(dot, el("span", null, h.label), el("em", null, h.note));
      li.onmousedown = (e) => { e.preventDefault(); pick(h); };
      return li;
    }));
    results.classList.toggle("open", hits.length > 0);
  }
  function resetSearch() { input.value = ""; hits = []; renderHits(); setFocus(lock ? neighborhood(lock) : null); }
  function pick(h) { resetSearch(); input.blur(); select(h.id); }
  input.addEventListener("input", () => {
    hits = search(input.value); cursor = 0; renderHits();
    // preview: while typing, light up the matches and dim the rest
    setFocus(hits.length ? new Set(hits.slice(0, 400).map((h) => h.id)) : lock ? neighborhood(lock) : null);
  });
  input.addEventListener("keydown", (e) => {
    const shown = Math.min(hits.length, 7);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (shown) { cursor = (cursor + (e.key === "ArrowDown" ? 1 : shown - 1)) % shown; renderHits(); }
    } else if (e.key === "Enter") {
      if (hits[cursor]) pick(hits[cursor]);
    } else if (e.key === "Escape") {
      e.stopPropagation(); resetSearch(); input.blur();
    }
  });
  input.addEventListener("blur", () => { if (input.value) resetSearch(); });
  addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== input && !e.metaKey && !e.ctrlKey) { e.preventDefault(); input.focus(); }
  });

  // ---- start: fly to the deep-linked term, otherwise show everything --------
  setTimeout(() => { const id = hashId(); if (id) select(id); }, 60);
  window.__tz = { renderer, graph, select, camera, drawGlow, drawSky, getN: () => N }; // handy for debugging in the console
})();
