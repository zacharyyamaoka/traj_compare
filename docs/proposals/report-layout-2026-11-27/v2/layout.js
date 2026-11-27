/* V2 · Editor timeline — a video-editor dock across the bottom is the page's spine: the ruler, one track per run
 * (eye, solo, value), then one lane per diagnostic event (every flag that fired, as bars) and any channel you add as a
 * waveform lane. Click a lane to open its charts in Diagnostics. The 3D's settings are an edge toolbar whose buttons
 * show their current value; each opens one slider. */
(function () {
  const K = window.Kit, h = K.h;
  const app = h("div", { class: "app" });
  document.body.appendChild(app);
  const cur = { tab: location.hash.match(/tab=(\w+)/)?.[1] || K.store.get("tab", "track"), sub: {}, ch: K.store.get("ch", null),
    lanes: K.store.get("lanes", null) };

  app.appendChild(h("header", { class: "top" }, h("b", {}, K.F.report_title), K.pageSelect(), h("div", { class: "grow" }),
    h("span", { class: "muted small" }, "Angles"), K.unitsSeg(),
    h("button", { class: "btn primary", "data-rerun": "", onclick: () => K.rerun(cur.tab) }, "Open in Rerun")));

  const upper = h("div", { class: "upper" }); app.appendChild(upper);
  const left = h("section", { class: "left" }); upper.appendChild(left);
  const split = h("div", { class: "split v" }); upper.appendChild(split);
  const right = h("section", { class: "right" }); upper.appendChild(right);
  K.splitter(split, left, { axis: "x", key: "left", def: 600, min: 280, max: 1100 });

  // ---- 3D + edge toolbar ----
  const tool = h("div", { class: "toolbar", "data-toolbar": "" });
  const stage = h("div", { class: "stage" });
  left.appendChild(tool); left.appendChild(stage);
  const v3 = K.viewer3d(stage);
  const fly = h("div", { class: "fly" }); stage.appendChild(fly);
  const toolBtns = [];
  K.VIEW_SLIDERS.forEach((def) => {
    const [k, label, , , , f] = def;
    const b = h("button", { class: "tb", "data-tool": k, title: label, onclick: () => openFly(k, b, [K.sliderRow(v3, def, refresh)]) },
      h("small", {}, { decay: "Trail", ahead: "Ahead", mag: "Arrow", markers: "Marks", size: "Size" }[k]), h("b", {}, f(v3.get()[k])));
    b._f = () => (b.lastChild.textContent = f(v3.get()[k])); toolBtns.push(b); tool.appendChild(b);
  });
  const drawBtn = h("button", { class: "tb", "data-tool": "draw", title: "what to draw", onclick: () => openFly("draw", drawBtn, K.VIEW_CHECKS.map((d) => K.checkRow(v3, d, refresh))) },
    h("small", {}, "Draw"), h("b", {}, "")); drawBtn._f = () => (drawBtn.lastChild.textContent = ["arrows", "ghost", "comet"].filter((k) => v3.get()[k]).length + "/3");
  toolBtns.push(drawBtn); tool.appendChild(drawBtn);
  function refresh() { toolBtns.forEach((b) => b._f()); }
  refresh();
  let openKey = null;
  function openFly(k, btn, rows) {
    toolBtns.forEach((b) => b.classList.toggle("on", b === btn && openKey !== k));
    if (openKey === k) { fly.style.display = "none"; openKey = null; return; }
    openKey = k; fly.innerHTML = ""; rows.forEach((r) => fly.appendChild(r)); fly.style.display = "block"; fly.style.top = (btn.offsetTop) + "px";
  }

  // ---- tabs: dense stacked charts (the dock is the overview) ----
  const tabbar = h("nav", { class: "tabs" }); const body = h("div", { class: "tabbody" });
  right.appendChild(tabbar); right.appendChild(body);
  K.TABS.forEach((t) => tabbar.appendChild(h("button", { "data-tab": t.id, onclick: () => showTab(t.id) }, t.title)));
  function showTab(id) {
    cur.tab = id; K.store.set("tab", id);
    tabbar.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
    K.dropCharts(body); body.innerHTML = "";
    const t = K.TABS.find((x) => x.id === id);
    body.appendChild(h("div", { class: "qline" }, h("span", { class: "muted" }, t.heading), h("b", {}, K.answer(id).head)));
    if (id === "channels") return diagnostics();
    if (id === "where" || id === "signals") {
      const ids = id === "where" ? ["error", "pose"] : ["q", "qd", "qdd", "tau"];
      const words = { error: "Tool error", pose: "Tool pose", q: "angle", qd: "speed", qdd: "acceleration", tau: "torque" };
      const s = h("div", { class: "seg sub" }); const sel = cur.sub[id] || ids[0];
      ids.forEach((k) => s.appendChild(h("button", { class: sel === k ? "on" : "", onclick: () => { cur.sub[id] = k; showTab(id); } }, words[k])));
      body.appendChild(s);
    }
    if (id === "track") body.appendChild(h("div", { class: "statwrap" }, K.statsTable()));
    const specs = K.tabCharts(id, cur.sub[id] || (id === "where" ? "error" : id === "signals" ? "q" : null));
    specs.forEach((s) => { const d = h("div", { class: "cell" }); body.appendChild(d); K.chart(d, s, { height: specs.length > 2 ? 132 : 190 }); });
  }
  function diagnostics() {
    const c = cur.ch && K.chByName[cur.ch];
    if (!c) {
      body.appendChild(h("div", { class: "empty" }, h("b", {}, "Pick a lane in the timeline below."),
        h("p", { class: "muted" }, `Every flag that fired already has a lane (${eventLanes().length}). Add any of the ${K.channels.length} channels as a waveform lane with “+ Add a lane”.`)));
      return;
    }
    body.appendChild(h("div", { class: "chtitle" }, h("b", {}, c.title), h("span", { class: "faint" }, ` [${K.chUnit(c) || "–"}] · ${c.family}`),
      h("span", { class: "grow" }), h("button", { class: "btn", onclick: () => { cur.ch = null; K.store.set("ch", null); showTab("channels"); paintLanes(); } }, "Close")));
    K.tabCharts("channels", c.name).forEach((s) => { const d = h("div", { class: "cell" }); body.appendChild(d); K.chart(d, s, { height: 170 }); });
    if (c.run) body.appendChild(h("p", { class: "faint small" }, "recorded by " + K.byName[c.run].title + (c.changed ? "" : " · did not change during the run")));
  }

  // ---- the dock ----
  const split2 = h("div", { class: "split h" }); app.appendChild(split2);
  const dock = h("footer", { class: "dock", "data-lane": "" }); app.appendChild(dock);
  K.splitter(split2, dock, { axis: "y", key: "dock", def: 330, min: 120, max: 640, invert: true });
  const tread = h("b", { class: "mono tread" });
  const playBtn = h("button", { class: "btn icon", "data-play": "", onclick: K.togglePlay }, "▶");
  dock.appendChild(h("div", { class: "transport" },
    h("button", { class: "btn icon", onclick: () => { K.pause(); K.setTime(0); } }, "⏮"), h("button", { class: "btn icon", onclick: () => K.step(-1) }, "◀"), playBtn,
    h("button", { class: "btn icon", onclick: () => K.step(1) }, "▶|"), h("button", { class: "btn icon", onclick: () => { K.pause(); K.setTime(K.T[K.N - 1]); } }, "⏭"), tread,
    h("button", { class: "btn", "data-prev-event": "", onclick: () => jumpEvent(-1) }, "‹ event"),
    h("button", { class: "btn worst", "data-worst": "", onclick: () => { K.pause(); K.setTime(K.WORST_T); } }, "◆ Worst moment"),
    h("button", { class: "btn", "data-next-event": "", onclick: () => jumpEvent(1) }, "event ›"),
    h("span", { class: "grow" }), h("button", { class: "btn", onclick: () => K.setZoom(null) }, "Full range")));
  const grid = h("div", { class: "tl" }); dock.appendChild(grid);

  function eventLanes() {
    const lanes = [];
    K.channels.filter((c) => c.binary && c.changed).forEach((c) => c.names.forEach((jn, j) => {
      const spans = K.chEventSpans(c).filter((s) => s.joint === jn);
      if (spans.length) lanes.push({ id: `${c.name}:${j}`, ch: c.name, label: c.title.split(" (")[0] + (jn ? " · " + jn : ""), spans, tone: c.name === "settled" ? "good" : "bad" });
    }));
    const derived = [["outcome", (v) => v != null && v !== 0, "Outcome ≠ running"], ["path_margin_rad", (v) => v != null && v < 0, "Path tolerance violated"],
      ["overspeed_rad_s", (v) => v != null && v > 0, "Over the speed limit"]];
    derived.forEach(([name, test, words]) => {
      const c = K.chByName[name]; c.cols.forEach((col, j) => {
        const spans = []; let a = null;
        col.forEach((v, i) => { const onNow = test(v); if (onNow && a == null) a = K.T[i]; if (!onNow && a != null) { spans.push({ a, b: K.T[i] }); a = null; } });
        if (a != null) spans.push({ a, b: K.T[K.N - 1] });
        if (spans.length) lanes.push({ id: `${name}:${j}`, ch: name, label: words + (c.names[j] ? " · " + c.names[j] : ""), spans, tone: "warn" });
      });
    });
    return lanes;
  }
  const EV = eventLanes();
  if (!cur.lanes) cur.lanes = ["effort_residual_nm", "drive_power_w"];
  const events = () => EV.flatMap((l) => l.spans.map((s) => s.a)).sort((a, b) => a - b);
  function jumpEvent(dir) {
    const t = K.state.time, evs = [...new Set(events())];
    const next = dir > 0 ? evs.find((x) => x > t + 1e-6) : evs.reverse().find((x) => x < t - 1e-6);
    if (next != null) { K.pause(); K.setTime(next); }
  }
  const vals = {};
  function paintLanes() {
    grid.innerHTML = "";
    grid.appendChild(h("div", { class: "th faint" }, "time [s]"));
    const r = h("div", {}); grid.appendChild(r); K.ruler(r, { events: () => events().map((t) => ({ t })) });
    grid.appendChild(h("div", { class: "sect" }, "Runs"));
    K.RUNS.forEach((run) => {
      vals[run.name] = h("span", { class: "mono val" });
      const solo = h("button", { class: "solo" + (K.state.solo === run.name ? " on" : ""), title: "solo", onclick: () => K.soloRun(run.name) }, "S");
      grid.appendChild(h("div", { class: "th" }, K.eye(run.name), solo, K.swatch(run), h("span", { class: "nm" }, run.title.split(" · ")[0]), vals[run.name]));
      const t = h("div", {}); grid.appendChild(t); K.track(t, run.name);
    });
    grid.appendChild(h("div", { class: "sect" }, `Events · ${EV.length} lanes, from the Diagnostics flags that fired`));
    EV.forEach((l) => laneRow(l.label, l.ch, (el) => bars(el, l), l.tone));
    grid.appendChild(h("div", { class: "sect" }, "Waveform lanes"));
    cur.lanes.forEach((name) => { const c = K.chByName[name]; laneRow(c.title.split(" (")[0], name, (el) => wave(el, c), "", () => { cur.lanes = cur.lanes.filter((x) => x !== name); K.store.set("lanes", cur.lanes); paintLanes(); }); });
    const add = h("details", { class: "add", "data-addlane": "" }, h("summary", {}, "+ Add a lane"));
    const pick = h("div", { class: "pick" }); add.appendChild(pick);
    K.FAMILIES.forEach((fam) => {
      pick.appendChild(h("div", { class: "fam" }, fam));
      K.channels.filter((c) => c.family === fam).forEach((c) => pick.appendChild(h("button", { class: "pk" + (cur.lanes.includes(c.name) ? " on" : ""), "data-pick": c.name,
        onclick: () => { if (!cur.lanes.includes(c.name)) cur.lanes.push(c.name); K.store.set("lanes", cur.lanes); paintLanes(); } },
        h("span", { class: "dot" + (c.changed ? " ch" : "") }), c.title.split(" (")[0])));
    });
    grid.appendChild(h("div", { class: "th" }, add)); grid.appendChild(h("div", {}));
    syncTime();
  }
  function laneRow(label, ch, draw, tone, remove) {
    const head = h("div", { class: "th lane" + (cur.ch === ch ? " sel" : ""), "data-lanehead": ch, onclick: () => { cur.ch = ch; K.store.set("ch", ch); showTab("channels"); paintLanes(); } },
      h("span", { class: "dot " + tone }), h("span", { class: "nm" }, label), remove ? h("button", { class: "x", title: "remove lane", onclick: (e) => { e.stopPropagation(); remove(); } }, "×") : null);
    grid.appendChild(head);
    const el = h("div", { class: "lanebody" }); grid.appendChild(el); draw(el);
  }
  function canvasLane(el, paint) {
    const c = h("canvas"); el.appendChild(c);
    const draw = () => { const r = el.getBoundingClientRect(); const d = window.devicePixelRatio || 1; c.width = r.width * d; c.height = r.height * d;
      const g = c.getContext("2d"); g.setTransform(d, 0, 0, d, 0, 0); const [a, b] = K.state.zoom || [K.T[0], K.T[K.N - 1]];
      const X = (t) => ((t - a) / (b - a)) * r.width; paint(g, X, r.width, r.height);
      g.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--ph"); g.fillRect(X(K.state.time) - 0.75, 0, 1.5, r.height); };
    new ResizeObserver(draw).observe(el); K.on("time", draw); K.on("zoom", draw); draw();
    let down = false; const toT = (e) => { const r = el.getBoundingClientRect(); const [a, b] = K.state.zoom || [K.T[0], K.T[K.N - 1]]; return a + ((e.clientX - r.left) / r.width) * (b - a); };
    el.addEventListener("pointerdown", (e) => { el.setPointerCapture(e.pointerId); down = true; K.pause(); K.setTime(toT(e)); });
    el.addEventListener("pointermove", (e) => down && K.setTime(toT(e))); el.addEventListener("pointerup", () => (down = false));
  }
  const cssv = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function bars(el, l) { canvasLane(el, (g, X, w, hh) => { g.fillStyle = cssv("--" + (l.tone === "good" ? "good" : l.tone === "warn" ? "warn" : "bad")); l.spans.forEach((s) => g.fillRect(X(s.a), 4, Math.max(2, X(s.b) - X(s.a)), hh - 8)); }); }
  function wave(el, c) {
    canvasLane(el, (g, X, w, hh) => {
      const run = K.byName[c.run]; const colors = [run ? run.color : "#888", "#9a7fd1"];
      c.cols.forEach((col, j) => { const v = col.filter((x) => x != null); if (!v.length) return; const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
        g.strokeStyle = colors[j % 2]; g.lineWidth = 1.2; g.beginPath(); let pen = false;
        col.forEach((x, i) => { if (x == null) { pen = false; return; } const y = hh - 3 - ((x - lo) / span) * (hh - 6); pen ? g.lineTo(X(K.T[i]), y) : g.moveTo(X(K.T[i]), y); pen = true; }); g.stroke(); });
    });
  }
  function syncTime() {
    tread.textContent = `${K.state.time.toFixed(2)} / ${K.T[K.N - 1].toFixed(2)} s`;
    K.RUNS.forEach((r) => { if (vals[r.name]) { const v = K.runErrAt(r.name); vals[r.name].textContent = v == null ? "ref" : K.fmt(v, K.angleUnit("°"), 2); } });
  }
  K.on("time", syncTime); K.on("runs", () => grid.querySelectorAll(".solo").forEach((b, i) => b.classList.toggle("on", K.state.solo === K.RUNS[i].name)));
  K.on("units", () => { syncTime(); showTab(cur.tab); });
  K.on("play", () => (playBtn.textContent = K.state.playing ? "❚❚" : "▶"));
  paintLanes(); showTab(cur.tab);
})();
