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
  function select(id) {
    lock = id; network.selectNodes([id]); applyFocus(neighborhood(id)); showPanel(id);
    network.focus(id, { scale: Math.max(network.getScale(), 1), animation: { duration: 700, easingFunction: "easeInOutQuad" } });
  }
  function clearLock() { lock = null; network.unselectAll(); applyFocus(null); panel.classList.remove("open"); }

  network.on("hoverNode", (p) => { if (!lock) applyFocus(neighborhood(p.node)); });
  network.on("blurNode", () => { if (!lock) applyFocus(null); });
  network.on("click", (p) => { if (p.nodes.length) select(p.nodes[0]); else if (lock) clearLock(); });
  addEventListener("keydown", (e) => { if (e.key === "Escape") clearLock(); });

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
  network.once("stabilizationIterationsDone", () => network.fit({ animation: { duration: 900, easingFunction: "easeInOutQuad" } }));
})();
