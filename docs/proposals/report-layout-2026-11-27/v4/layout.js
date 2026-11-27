/* V4 · Signal strips — every chart starts as a 40 px strip (name · sparkline · each run's value at the playhead) and
 * opens into a full chart on click, so a tab reads like a table and 27 channels fit one screen. One sticky ruler with the
 * transport sits over the strips and the playhead runs down all of them. Runs are pills in the page header; the 3D has
 * three looks plus a fine-tune drawer. */
(function () {
  const K = window.Kit, h = K.h;
  const app = h("div", { class: "app" }); document.body.appendChild(app);
  const cur = { tab: location.hash.match(/tab=(\w+)/)?.[1] || K.store.get("tab", "track"), sub: {}, open: K.store.get("open", {}), flat: false };
  const cssv = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  // ---- header with run pills ----
  const pills = h("div", { class: "pills", "data-runpills": "" });
  const pv = {};
  K.RUNS.forEach((r) => {
    pv[r.name] = h("span", { class: "mono pv" });
    const p = h("div", { class: "pill", "data-pill": r.name }, K.eye(r.name), K.swatch(r), h("span", {}, r.title.split(" · ")[0]), pv[r.name],
      h("button", { class: "solo", title: "solo", onclick: () => K.soloRun(r.name) }, "S"));
    pills.appendChild(p);
  });
  K.on("runs", () => pills.querySelectorAll(".pill").forEach((p) => { p.classList.toggle("off", !K.shown(p.dataset.pill)); p.querySelector(".solo").classList.toggle("on", K.state.solo === p.dataset.pill); }));
  app.appendChild(h("header", { class: "top" }, h("b", {}, K.F.report_title), K.pageSelect(), pills, h("div", { class: "grow" }), K.unitsSeg(),
    h("button", { class: "btn primary", "data-rerun": "", onclick: () => K.rerun(cur.tab) }, "Open in Rerun")));

  const main = h("main", { class: "main" }); app.appendChild(main);
  const left = h("section", { class: "left" }); main.appendChild(left);
  const split = h("div", { class: "split v" }); main.appendChild(split);
  const right = h("section", { class: "right" }); main.appendChild(right);
  K.splitter(split, left, { axis: "x", key: "left", def: 560, min: 280, max: 1000 });

  // ---- 3D: looks + fine-tune drawer ----
  const stage = h("div", { class: "stage" }); left.appendChild(stage);
  const v3 = K.viewer3d(stage);
  const LOOKS = { clean: { ghost: false, arrows: false, comet: false, decay: 10, markers: 0 }, comet: { ghost: true, arrows: false, comet: true, decay: 2, markers: 20 },
    arrows: { ghost: true, arrows: true, comet: true, decay: 5, mag: 3, markers: 10 } };
  const lookSeg = h("div", { class: "seg looks", "data-looks": "" });
  let look = K.store.get("look", "arrows");
  [["clean", "Clean"], ["comet", "Ghost + comet"], ["arrows", "Error arrows"]].forEach(([k, w]) => lookSeg.appendChild(h("button", { "data-look": k, onclick: () => setLook(k) }, w)));
  function setLook(k) { look = k; K.store.set("look", k); v3.set(LOOKS[k]); lookSeg.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.look === k)); paintDrawer(); }
  stage.appendChild(h("div", { class: "lookbar" }, lookSeg));
  const drawer = h("details", { class: "drawer", "data-drawer": "" }, h("summary", {}, "Fine-tune the view"));
  const dbody = h("div", { class: "dbody" }); drawer.appendChild(dbody); stage.appendChild(drawer);
  function paintDrawer() { dbody.innerHTML = ""; K.VIEW_SLIDERS.forEach((d) => dbody.appendChild(K.sliderRow(v3, d))); K.VIEW_CHECKS.forEach((d) => dbody.appendChild(K.checkRow(v3, d))); }
  setLook(look);

  // ---- right: tabs, sticky time header, strips ----
  const tabbar = h("nav", { class: "tabs" }); right.appendChild(tabbar);
  K.TABS.forEach((t) => tabbar.appendChild(h("button", { "data-tab": t.id, onclick: () => showTab(t.id) }, t.title)));
  const head = h("div", { class: "timehead", "data-lane": "" });
  const tread = h("b", { class: "mono" }); const playBtn = h("button", { class: "btn icon", "data-play": "", onclick: K.togglePlay }, "▶");
  head.appendChild(h("div", { class: "tp" }, h("button", { class: "btn icon", onclick: () => { K.pause(); K.setTime(0); } }, "⏮"), h("button", { class: "btn icon", onclick: () => K.step(-1) }, "◀"),
    playBtn, h("button", { class: "btn icon", onclick: () => K.step(1) }, "▶|"), tread));
  const rul = h("div", { class: "rul" }); head.appendChild(rul); K.ruler(rul);
  head.appendChild(h("div", { class: "tp2" }, h("button", { class: "btn worst", "data-worst": "", onclick: () => { K.pause(); K.setTime(K.WORST_T); } }, "◆ Worst"),
    h("button", { class: "btn", onclick: () => K.setZoom(null) }, "Full")));
  const body = h("div", { class: "tabbody" }); right.appendChild(body);
  const strips = [];
  function showTab(id) {
    cur.tab = id; K.store.set("tab", id);
    tabbar.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
    K.dropCharts(body); body.innerHTML = ""; strips.length = 0; body.appendChild(head);
    body.insertBefore(h("div", { class: "answer", "data-answer": "" }, h("span", { class: "muted" }, K.TABS.find((t) => t.id === id).heading), h("b", {}, K.answer(id).head)), head);
    if (id === "where" || id === "signals") {
      const ids = id === "where" ? ["error", "pose"] : ["q", "qd", "qdd", "tau", "all"];
      const words = { error: "Tool error", pose: "Tool pose", q: "angle", qd: "speed", qdd: "acceleration", tau: "torque", all: "all four" };
      const s = h("div", { class: "seg sub" }); const sel = cur.sub[id] || (id === "signals" ? "all" : ids[0]);
      ids.forEach((k) => s.appendChild(h("button", { class: sel === k ? "on" : "", onclick: () => { cur.sub[id] = k; showTab(id); } }, words[k])));
      body.appendChild(s);
    }
    if (id === "track") { const d = h("details", { class: "statd" }, h("summary", {}, "Error statistics table")); d.appendChild(K.statsTable()); body.appendChild(d); }
    if (id === "channels") return channelStrips();
    const sub = cur.sub[id] || (id === "where" ? "error" : id === "signals" ? "all" : null);
    K.tabCharts(id, sub === "all" ? null : sub).forEach((s) => body.appendChild(strip(s)));
  }
  function channelStrips() {
    const groups = K.FAMILIES.map((f) => [f, K.channels.filter((c) => c.family === f && c.changed)]).filter((g) => g[1].length);
    groups.forEach(([fam, cs]) => {
      body.appendChild(h("div", { class: "fam" }, fam));
      cs.forEach((c) => K.tabCharts("channels", c.name).forEach((s) => body.appendChild(strip(s, c))));
    });
    const flat = K.channels.filter((c) => !c.changed);
    const fl = h("details", { class: "flat", "data-flat": "" }, h("summary", {}, `${flat.length} channels did not change: ${flat.map((c) => c.title.split(" (")[0]).join(", ")}`));
    fl.addEventListener("toggle", () => { if (fl.open && fl.childElementCount === 1) flat.forEach((c) => K.tabCharts("channels", c.name).forEach((s) => fl.appendChild(strip(s, c)))); });
    body.appendChild(fl);
  }
  function strip(spec, c) {
    const key = cur.tab + ":" + spec.id;
    const row = h("div", { class: "strip" + (cur.open[key] ? " open" : ""), "data-strip": spec.id });
    const lab = h("button", { class: "lab", onclick: () => { cur.open[key] = !cur.open[key]; K.store.set("open", cur.open); row.classList.toggle("open"); paintRow(); } },
      h("span", { class: "car" }, "›"), h("span", { class: "nm", title: spec.title }, spec.joint ? (spec.channel ? spec.group : spec.title.replace(spec.joint + ": ", "")) : spec.title),
      spec.joint ? h("span", { class: "jt" }, spec.joint) : null, h("span", { class: "u faint" }, spec.unit ? `[${spec.unit}]` : ""));
    const spark = h("div", { class: "spark" }); const vals = h("div", { class: "vals mono" });
    row.appendChild(lab); row.appendChild(spark); row.appendChild(vals);
    const full = h("div", { class: "full" }); row.appendChild(full);
    const rec = { spec, spark, vals, row, full, c };
    function paintRow() {
      if (row.classList.contains("open")) { if (!full.childElementCount) requestAnimationFrame(() => K.chart(full, spec, { height: 180, title: false, ySize: 40 })); }
      else { K.dropCharts(full); full.innerHTML = ""; }
    }
    paintRow(); drawSpark(rec); strips.push(rec); new ResizeObserver(() => drawSpark(rec)).observe(spark);
    return row;
  }
  function drawSpark(rec) {
    const el = rec.spark; let cv = el.firstChild; if (!cv) { cv = h("canvas"); el.appendChild(cv); scrub(el); }
    const r = el.getBoundingClientRect(); if (r.width < 10) return; const d = window.devicePixelRatio || 1; cv.width = r.width * d; cv.height = r.height * d;
    const g = cv.getContext("2d"); g.setTransform(d, 0, 0, d, 0, 0);
    const [a, b] = K.state.zoom || [K.T[0], K.T[K.N - 1]]; const GUT = 40; const W = r.width - GUT - 10; const X = (t) => GUT + ((t - a) / (b - a)) * W; const H = r.height;
    let lo = Infinity, hi = -Infinity;
    rec.spec.lines.forEach((l) => K.shown(l.run) && l.y.forEach((v) => { if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
    if (!isFinite(lo)) { lo = 0; hi = 1; } if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    const Y = (v) => H - 4 - ((v - lo) / (hi - lo)) * (H - 8);
    g.fillStyle = cssv("--faint"); g.font = "9px " + cssv("--font"); g.fillText(K.fmt(hi, ""), 2, 10); g.fillText(K.fmt(lo, ""), 2, H - 3);
    rec.spec.lines.forEach((l) => {
      if (!K.shown(l.run)) return; g.strokeStyle = l.color; g.lineWidth = 1.3; g.setLineDash(l.dash ? [4, 3] : []); g.beginPath(); let pen = false;
      l.y.forEach((v, i) => { const t = K.T[i]; if (v == null || t < a || t > b) { pen = false; return; } pen ? g.lineTo(X(t), Y(v)) : g.moveTo(X(t), Y(v)); pen = true; });
      g.stroke();
    });
    g.setLineDash([]); g.fillStyle = cssv("--ph"); g.fillRect(X(K.state.time) - 0.75, 0, 1.5, H);
    rec.vals.innerHTML = "";
    rec.spec.lines.forEach((l) => { if (!K.shown(l.run)) return; const s = h("span", {}, K.fmt(K.specValueAt(rec.spec, l.run), "")); s.style.color = l.color; rec.vals.appendChild(s); });
  }
  function scrub(el) {
    let down = false; const toT = (e) => { const r = el.getBoundingClientRect(); const [a, b] = K.state.zoom || [K.T[0], K.T[K.N - 1]]; return a + ((e.clientX - r.left - 40) / (r.width - 50)) * (b - a); };
    el.addEventListener("pointerdown", (e) => { el.setPointerCapture(e.pointerId); down = true; K.pause(); K.setTime(toT(e)); });
    el.addEventListener("pointermove", (e) => down && K.setTime(toT(e))); el.addEventListener("pointerup", () => (down = false));
  }
  const redraw = () => strips.forEach(drawSpark);
  function syncTime() {
    tread.textContent = ` ${K.state.time.toFixed(2)} s`;
    K.RUNS.forEach((r) => { const v = K.runErrAt(r.name); pv[r.name].textContent = v == null ? "ref" : K.fmt(v, K.angleUnit("°"), 1); });
    redraw();
  }
  K.on("time", syncTime); K.on("runs", redraw); K.on("zoom", redraw); K.on("units", () => { syncTime(); showTab(cur.tab); });
  K.on("play", () => (playBtn.textContent = K.state.playing ? "❚❚" : "▶"));
  showTab(cur.tab); syncTime();
})();
