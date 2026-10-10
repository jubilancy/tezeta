// Visual layer for the Tezeta graph. Injected after the Pyvis script, which
// leaves `nodes`, `edges` and `network` as page globals. `TZ` is injected too.
(function () {
  const hexToRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const rgba = (h, a) => { const [r, g, b] = hexToRgb(h); return `rgba(${r},${g},${b},${a})`; };
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nodeColor = (n) => (n.color && n.color.background) || "#f2e6c9";
  const isTerm = (id) => id[0] === "t";
  const phase = {};
  nodes.getIds().forEach((id) => (phase[id] = Math.random() * 6.28));

  // ---- starfield: three parallax layers that drift with the camera ----
  const sky = document.createElement("canvas");
  sky.style.cssText = "position:fixed;inset:0;width:100%;height:100%;z-index:0;pointer-events:none";
  document.body.prepend(sky);
  const sctx = sky.getContext("2d");
  const stars = Array.from({ length: 220 }, () => ({
    x: Math.random(), y: Math.random(), z: 0.15 + Math.random() * 0.85,
    r: Math.random() * 1.2 + 0.2, p: Math.random() * 6.28, s: 0.4 + Math.random() * 1.4,
  }));
  function resizeSky() {
    const d = devicePixelRatio || 1;
    sky.width = innerWidth * d; sky.height = innerHeight * d;
    sctx.setTransform(d, 0, 0, d, 0, 0);
  }
  addEventListener("resize", resizeSky); resizeSky();
  function drawSky(t) {
    sctx.clearRect(0, 0, innerWidth, innerHeight);
    const v = network.getViewPosition(), sc = network.getScale();
    for (const s of stars) {
      const x = (((s.x * innerWidth - v.x * sc * s.z * 0.06) % innerWidth) + innerWidth) % innerWidth;
      const y = (((s.y * innerHeight - v.y * sc * s.z * 0.06) % innerHeight) + innerHeight) % innerHeight;
      const tw = reduceMotion ? 0.7 : 0.55 + 0.45 * Math.sin(t * 0.001 * s.s + s.p);
      sctx.fillStyle = `rgba(239,231,214,${0.55 * s.z * tw})`;
      sctx.beginPath(); sctx.arc(x, y, s.r * s.z + 0.2, 0, 6.283); sctx.fill();
    }
  }

  // ---- focus state ----
  let focus = null; // Set of ids kept bright, or null for all
  let lock = null;  // clicked node id
  function neighborhood(id) {
    const set = new Set([id]);
    network.getConnectedNodes(id).forEach((n) => {
      set.add(n);
      if (isTerm(id)) network.getConnectedNodes(n).forEach((m) => set.add(m));
    });
    return set;
  }
  function applyFocus(set) {
    focus = set;
    nodes.update(nodes.get().map((n) => {
      const on = !set || set.has(n.id);
      const base = n.id[0] === "w" ? 0.55 : 1;
      return { id: n.id, font: { ...n.font, color: rgba("#efe7d6", on ? base : 0.1) },
               color: { ...n.color, background: nodeColor(n), border: nodeColor(n) }, opacity: on ? 1 : 0.12 };
    }));
    edges.update(edges.get().map((e) => {
      const on = !set || (set.has(e.from) && set.has(e.to));
      return { id: e.id, color: { inherit: "both", opacity: on ? (set ? 0.9 : 0.5) : 0.04 } };
    }));
  }

  // ---- info panel ----
  const panel = document.createElement("aside");
  panel.id = "tz-panel";
  document.body.appendChild(panel);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  function showPanel(id) {
    panel.replaceChildren();
    const close = el("button", "tz-x", "×"); close.onclick = clearLock; panel.append(close);
    if (isTerm(id)) {
      const t = TZ.terms[+id.slice(1)], c = TZ.colors[t.vibe || "unsorted"];
      panel.append(el("h2", null, t.term));
      const chip = el("span", "tz-chip", t.vibe || "unsorted"); chip.style.setProperty("--c", c); panel.append(chip);
      panel.append(el("p", "tz-def", t.definition));
      const words = Object.keys(TZ.hubs).filter((w) => TZ.hubs[w].includes(+id.slice(1)));
      if (words.length) {
        panel.append(el("h3", null, "Shares words"));
        const row = el("div", "tz-tags"); words.forEach((w) => row.append(el("span", null, w))); panel.append(row);
        const rel = new Set(); words.forEach((w) => TZ.hubs[w].forEach((i) => i !== +id.slice(1) && rel.add(i)));
        panel.append(el("h3", null, "Related"));
        const list = el("div", "tz-rel");
        rel.forEach((i) => { const b = el("button", null, TZ.terms[i].term); b.onclick = () => select("t" + i); list.append(b); });
        panel.append(list);
      }
    } else {
      const w = id.slice(2);
      panel.append(el("h2", null, w));
      panel.append(el("span", "tz-chip", "shared word"));
      panel.append(el("h3", null, "Appears in"));
      const list = el("div", "tz-rel");
      TZ.hubs[w].forEach((i) => { const b = el("button", null, TZ.terms[i].term); b.onclick = () => select("t" + i); list.append(b); });
      panel.append(list);
    }
    panel.classList.add("open");
  }
  // ---- deep links: tezeta.web.app/#index opens straight to that term ----
  const slugIndex = {};
  TZ.terms.forEach((t, i) => (slugIndex[t.slug] = "t" + i));
  const hashId = () => { try { return slugIndex[decodeURIComponent(location.hash.slice(1)).toLowerCase()] || null; } catch { return null; } };
  function syncHash(id) {
    const want = id && isTerm(id) ? "#" + TZ.terms[+id.slice(1)].slug : "";
    if (location.hash !== want) history.replaceState(null, "", location.pathname + location.search + want);
  }

  function select(id) {
    lock = id; syncHash(id); network.selectNodes([id]); applyFocus(neighborhood(id)); showPanel(id);
    network.focus(id, { scale: Math.max(network.getScale(), 1), animation: { duration: 700, easingFunction: "easeInOutQuad" } });
  }
  function clearLock() { lock = null; syncHash(null); network.unselectAll(); applyFocus(null); panel.classList.remove("open"); }

  network.on("hoverNode", (p) => { if (!lock) applyFocus(neighborhood(p.node)); });
  network.on("blurNode", () => { if (!lock) applyFocus(null); });
  network.on("click", (p) => { if (p.nodes.length) select(p.nodes[0]); else if (lock) clearLock(); });
  addEventListener("keydown", (e) => { if (e.key === "Escape") clearLock(); });

  // ---- search: type a term, arrow keys + enter (or click) to fly to it ----
  const box = el("div"); box.id = "tz-search";
  const input = el("input"); input.type = "search"; input.placeholder = "search terms  ( / )";
  input.setAttribute("aria-label", "Search terms"); input.autocomplete = "off"; input.spellcheck = false;
  const results = el("ul"); results.id = "tz-results"; results.setAttribute("role", "listbox");
  box.append(input, results); document.body.appendChild(box);
  let hits = [], cursor = 0;

  function search(q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    const out = [];
    TZ.terms.forEach((t, i) => {
      const n = t.term.toLowerCase(), v = (t.vibe || "").toLowerCase();
      const s = n === q ? 0 : n.startsWith(q) ? 1 : n.includes(q) ? 2 : v === q ? 3 : (t.definition || "").toLowerCase().includes(q) ? 4 : -1;
      if (s >= 0) out.push({ id: "t" + i, label: t.term, note: t.vibe || "", color: TZ.colors[t.vibe || "unsorted"], s });
    });
    Object.keys(TZ.hubs).forEach((w) => {
      if (w.includes(q)) out.push({ id: "w:" + w, label: w, note: "shared word", color: "#f2e6c9", s: 2.5 });
    });
    return out.sort((a, b) => a.s - b.s || a.label.localeCompare(b.label)).slice(0, 7);
  }
  function renderHits() {
    results.replaceChildren(...hits.map((h, k) => {
      const li = el("li", k === cursor ? "on" : ""); li.setAttribute("role", "option");
      const dot = el("i"); dot.style.background = h.color; dot.style.boxShadow = "0 0 8px " + h.color;
      li.append(dot, el("span", null, h.label), el("em", null, h.note));
      li.onmousedown = (e) => { e.preventDefault(); pick(h); };
      return li;
    }));
    results.classList.toggle("open", hits.length > 0);
  }
  function resetSearch() { input.value = ""; hits = []; renderHits(); applyFocus(lock ? neighborhood(lock) : null); }
  function pick(h) { resetSearch(); input.blur(); select(h.id); }
  input.addEventListener("input", () => {
    hits = search(input.value); cursor = 0; renderHits();
    // preview: while typing, light up the matches and dim the rest
    applyFocus(hits.length ? new Set(hits.map((h) => h.id)) : lock ? neighborhood(lock) : null);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (hits.length) { cursor = (cursor + (e.key === "ArrowDown" ? 1 : hits.length - 1)) % hits.length; renderHits(); }
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

  // ---- painting: nebula clouds + additive halos behind the nodes ----
  network.on("beforeDrawing", (ctx) => {
    const t = performance.now(), pos = network.getPositions();
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    const groups = {};
    nodes.get().forEach((n) => {
      if (!isTerm(n.id) || !pos[n.id]) return;
      const c = nodeColor(n); (groups[c] = groups[c] || []).push(pos[n.id]);
    });
    for (const c in groups) {
      const g = groups[c], cx = g.reduce((s, p) => s + p.x, 0) / g.length, cy = g.reduce((s, p) => s + p.y, 0) / g.length;
      const spread = Math.max(...g.map((p) => Math.hypot(p.x - cx, p.y - cy)), 0);
      const R = 170 + spread * 1.15, a = focus ? 0.025 : 0.075;
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
      grad.addColorStop(0, rgba(c, a)); grad.addColorStop(1, rgba(c, 0));
      ctx.fillStyle = grad; ctx.beginPath(); ctx.arc(cx, cy, R, 0, 6.283); ctx.fill();
    }
    nodes.get().forEach((n) => {
      const p = pos[n.id]; if (!p) return;
      const on = !focus || focus.has(n.id), c = nodeColor(n), hub = !isTerm(n.id);
      const breathe = reduceMotion ? 1 : 1 + 0.12 * Math.sin(t * 0.0016 + phase[n.id]);
      const R = n.size * (hub ? 2.6 : 3.4) * breathe, a = (hub ? 0.2 : 0.42) * (on ? 1 : 0.12);
      const g = ctx.createRadialGradient(p.x, p.y, n.size * 0.4, p.x, p.y, R);
      g.addColorStop(0, rgba(c, a)); g.addColorStop(1, rgba(c, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, R, 0, 6.283); ctx.fill();
    });
    ctx.restore();
  });

  // ---- animation loop (~30fps; pauses with the tab) ----
  let last = 0;
  function frame(t) {
    requestAnimationFrame(frame);
    if (t - last < 33) return;
    last = t; drawSky(t);
    if (!reduceMotion) network.redraw();
  }
  requestAnimationFrame(frame);
  // once the layout settles: fly to the deep-linked term, or fit everything
  let started = false;
  function start() {
    if (started) return;
    started = true;
    const id = hashId();
    if (id) select(id); else network.fit({ animation: { duration: 900, easingFunction: "easeInOutQuad" } });
  }
  if (network.physics && network.physics.stabilized) start(); else network.once("stabilizationIterationsDone", start);
  setTimeout(start, 5000);
  addEventListener("hashchange", () => {
    const id = hashId();
    if (id && id !== lock) select(id); else if (!id && lock) clearLock();
  });
})();
