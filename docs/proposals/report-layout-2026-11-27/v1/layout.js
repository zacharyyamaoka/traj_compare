/* V1 · Answer first — one answer bar over the page, every tab opens on its answer + one chart, the rest folded;
 * Diagnostics = changed channels first, grouped in plain words; the time lane is the page footer under both panels;
 * the 3D's sliders live in one "View" popover. */
(function () {
  const K = window.Kit, h = K.h;
  const app = h("div", { class: "app" });
  document.body.appendChild(app);

  // ---- header + answer bar ----
  const top = K.answer("track");
  app.appendChild(h("header", { class: "top" },
    h("div", { class: "brand" }, h("b", {}, K.F.report_title), h("span", { class: "muted" }, " · ")),
    pageSelect(),
    h("div", { class: "grow" }),
    h("span", { class: "muted small" }, "Angles"), K.unitsSeg(),
    h("button", { class: "btn primary", "data-rerun": "", onclick: () => K.rerun(cur.tab) }, "Open in Rerun")));
  const bar = h("section", { class: "answerbar", "data-answerbar": "" },
    h("div", { class: "verdict" }, h("span", { class: "q" }, "Did it track the target?"), h("b", { class: "big" }, top.head)),
    h("div", { class: "facts" }, top.facts.map((f) => h("span", { class: "tag" }, f)),
      K.answer("channels").facts.slice(0, 3).map((f) => h("span", { class: "tag bad" }, f))),
    h("button", { class: "btn worstbtn", "data-worst": "", onclick: () => { K.pause(); K.setTime(K.WORST_T); } }, "◆ Jump to the worst moment"));
  app.appendChild(bar);

  // ---- main: 3D | tabs ----
  const main = h("main", { class: "main" });
  app.appendChild(main);
  const left = h("section", { class: "left" });
  const stage = h("div", { class: "stage" });
  const fold = h("button", { class: "btn icon fold", title: "fold the 3D view", "data-fold3d": "", onclick: () => toggleFold() }, "‹");
  const viewBtn = h("button", { class: "btn", "data-viewsettings": "", onclick: () => pop.classList.toggle("open") }, "View ▾");
  left.appendChild(h("div", { class: "lefthead" }, h("b", {}, "3D view"), h("span", { class: "muted" }, "robot tool paths"), h("div", { class: "grow" }), viewBtn, fold));
  left.appendChild(stage);
  const legend = h("div", { class: "legend3d" });
  K.RUNS.forEach((r) => legend.appendChild(h("div", { class: "lrow" }, K.eye(r.name), K.swatch(r), h("span", {}, r.title.split(" · ")[0]))));
  stage.appendChild(legend);
  const pop = h("div", { class: "pop", "data-pop": "" });
  stage.appendChild(pop);
  main.appendChild(left);
  const split = h("div", { class: "split v" });
  main.appendChild(split);
  const right = h("section", { class: "right" });
  main.appendChild(right);
  K.splitter(split, left, { axis: "x", key: "left", def: 560, min: 300, max: 1000 });
  let folded = K.store.get("fold3d", false);
  function toggleFold() { folded = !folded; K.store.set("fold3d", folded); app.classList.toggle("folded", folded); fold.textContent = folded ? "›" : "‹"; }
  if (folded) { folded = !folded; toggleFold(); }

  const v3 = K.viewer3d(stage);
  const sliders = [
    ["decay", "Trail fades over", 0.5, 10, 0.5, (v) => v + " s"], ["ahead", "Target look-ahead", 0, 4, 0.25, (v) => v + " s ahead"],
    ["mag", "Error arrow magnification", 1, 10, 1, (v) => "×" + v], ["markers", "Marker density", 0, 60, 5, (v) => v],
    ["size", "Marker size", 4, 24, 1, (v) => v + " mm"]];
  pop.appendChild(h("div", { class: "pophead" }, h("b", {}, "View settings"), h("button", { class: "btn icon", onclick: () => pop.classList.remove("open") }, "×")));
  sliders.forEach(([k, label, lo, hi, st, f]) => {
    const val = h("span", {}, f(v3.get()[k]));
    const inp = h("input", { type: "range", min: lo, max: hi, step: st, value: v3.get()[k], "data-slider": k,
      oninput: (e) => { v3.set({ [k]: +e.target.value }); val.textContent = f(+e.target.value); } });
    pop.appendChild(h("label", { class: "slider-row" }, h("span", {}, label), val, inp));
  });
  [["arrows", "Position error arrows"], ["ghost", "Whole path, faint"], ["comet", "Fade the trail (comet)"]].forEach(([k, label]) => {
    const cb = h("input", { type: "checkbox", onchange: (e) => v3.set({ [k]: e.target.checked }) }); cb.checked = v3.get()[k];
    pop.appendChild(h("label", { class: "check" }, cb, " ", label));
  });

  // ---- tabs ----
  const cur = { tab: location.hash.match(/tab=(\w+)/)?.[1] || K.store.get("tab", "track"), sub: {}, open: K.store.get("open", {}), ch: null };
  const tabbar = h("nav", { class: "tabs" });
  const body = h("div", { class: "tabbody" });
  right.appendChild(tabbar); right.appendChild(body);
  K.TABS.forEach((t) => {
    const a = K.answer(t.id);
    tabbar.appendChild(h("button", { "data-tab": t.id, onclick: () => showTab(t.id) }, h("span", {}, t.title), a.badge ? h("i", {}, a.badge) : null));
  });
  function showTab(id) {
    cur.tab = id; K.store.set("tab", id);
    tabbar.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
    K.dropCharts(body); body.innerHTML = ""; body.scrollTop = 0;
    const t = K.TABS.find((x) => x.id === id); const a = K.answer(id);
    body.appendChild(h("p", { class: "question" }, t.heading));
    body.appendChild(h("div", { class: "answer", "data-answer": "" }, h("b", {}, a.head)));
    if (id === "channels") return diagnostics();
    if (t.subtabs && t.subtabs.length && id !== "signals") subSeg(t, ["error", "pose"]);
    if (id === "signals") subSeg(t, ["q", "qd", "qdd", "tau"]);
    const sub = cur.sub[id] || (id === "where" ? "error" : id === "signals" ? "q" : null);
    const specs = K.tabCharts(id, sub);
    const hero = h("div", { class: "hero" }); body.appendChild(hero);
    K.chart(hero, specs[0], { height: 250, worstLine: true });
    const rest = specs.slice(1);
    const more = h("details", { class: "more", "data-more": "" }); if (cur.open[id]) more.open = true;
    more.appendChild(h("summary", {}, id === "track" ? `Error statistics + ${rest.length} more chart${rest.length > 1 ? "s" : ""}` : `${rest.length} more chart${rest.length !== 1 ? "s" : ""}: ` + rest.map((s) => s.joint || s.title).join(" · ")));
    const grid = h("div", { class: "grid" }); more.appendChild(grid);
    const fill = () => { if (grid.childElementCount) return; if (id === "track") grid.appendChild(h("div", { class: "statwrap" }, K.statsTable())); rest.forEach((s) => { const d = h("div", { class: "cell" }); grid.appendChild(d); K.chart(d, s, { height: 150 }); }); };
    more.addEventListener("toggle", () => { cur.open[id] = more.open; K.store.set("open", cur.open); if (more.open) fill(); });
    if (more.open) requestAnimationFrame(fill);
    if (rest.length || id === "track") body.appendChild(more);
  }
  function subSeg(t, ids) {
    const s = h("div", { class: "seg sub" });
    const words = { error: "Tool error", pose: "Tool pose", q: "angle", qd: "speed", qdd: "acceleration", tau: "torque" };
    ids.forEach((k) => s.appendChild(h("button", { class: (cur.sub[t.id] || ids[0]) === k ? "on" : "", onclick: () => { cur.sub[t.id] = k; showTab(t.id); } }, words[k])));
    body.appendChild(s);
  }

  // ---- Diagnostics: changed first, grouped, one open at a time ----
  function diagnostics() {
    const changed = K.channels.filter((c) => c.changed), flat = K.channels.filter((c) => !c.changed);
    if (!cur.ch) cur.ch = changed.filter((c) => c.binary).sort((a, b) => a.onsetT - b.onsetT)[0].name;
    const list = h("div", { class: "chlist" }); body.appendChild(list);
    list.appendChild(h("div", { class: "chhead" }, h("b", {}, `Changed during the run · ${changed.length}`), h("span", { class: "muted" }, "first change · peak")));
    K.FAMILIES.forEach((fam) => {
      const rows = changed.filter((c) => c.family === fam); if (!rows.length) return;
      list.appendChild(h("div", { class: "fam" }, fam));
      rows.forEach((c) => list.appendChild(chRow(c)));
    });
    const fl = h("details", { class: "flat", "data-flat": "" }, h("summary", {}, `Did not change · ${flat.length}: ` + flat.map((c) => c.title.split(" (")[0]).join(", ")));
    flat.forEach((c) => fl.appendChild(chRow(c)));
    list.appendChild(fl);
  }
  function chRow(c) {
    const row = h("div", { class: "chrow" + (cur.ch === c.name ? " open" : ""), "data-channel": c.name });
    const tone = c.binary && c.changed && c.name !== "settled" ? "bad" : "";
    const head = h("button", { class: "chbtn", onclick: () => { cur.ch = cur.ch === c.name ? null : c.name; showTab("channels"); } },
      h("span", { class: "dot " + tone }), h("span", { class: "nm" }, c.title), h("span", { class: "unit faint" }, c.unit ? `[${K.chUnit(c)}]` : ""),
      h("span", { class: "grow" }),
      h("span", { class: "mono muted" }, c.changed ? (c.onsetT != null ? `${c.peakJoint ? c.peakJoint + " · " : ""}${K.fmtT(c.onsetT)}` : "") : c.empty ? "no samples" : "constant"),
      h("span", { class: "mono pk" }, c.peak != null ? K.fmt(K.chValue(c, c.peak), "") : "—"));
    row.appendChild(head);
    if (cur.ch === c.name) {
      const charts = h("div", { class: "chcharts" }); row.appendChild(charts);
      K.tabCharts("channels", c.name).forEach((s) => { const d = h("div", { class: "cell" }); charts.appendChild(d); requestAnimationFrame(() => K.chart(d, s, { height: 120 })); });
      if (c.run) charts.appendChild(h("div", { class: "faint small" }, "recorded by " + K.byName[c.run].title));
    }
    return row;
  }

  // ---- footer: the time lane under both panels ----
  const split2 = h("div", { class: "split h" });
  app.appendChild(split2);
  const lane = h("footer", { class: "lane", "data-lane": "" });
  app.appendChild(lane);
  K.splitter(split2, lane, { axis: "y", key: "lane", def: 178, min: 64, max: 420, invert: true });
  const tread = h("b", { class: "mono tread" });
  const playBtn = h("button", { class: "btn icon", "data-play": "", title: "play / pause (space)", onclick: K.togglePlay }, "▶");
  lane.appendChild(h("div", { class: "transport" },
    h("button", { class: "btn icon", title: "start", onclick: () => { K.pause(); K.setTime(0); } }, "⏮"),
    h("button", { class: "btn icon", title: "step back", onclick: () => K.step(-1) }, "◀"), playBtn,
    h("button", { class: "btn icon", title: "step", onclick: () => K.step(1) }, "▶|"),
    h("button", { class: "btn icon", title: "end", onclick: () => { K.pause(); K.setTime(K.T[K.N - 1]); } }, "⏭"), tread,
    h("span", { class: "grow" }), h("span", { class: "faint small" }, "drag the ruler, a track or any chart · shift-drag a chart to zoom"),
    h("button", { class: "btn", onclick: () => K.setZoom(null) }, "Full range")));
  const tracks = h("div", { class: "tracks" });
  lane.appendChild(tracks);
  tracks.appendChild(h("div", { class: "thead faint" }, "time [s]"));
  const rul = h("div", {}); tracks.appendChild(rul); K.ruler(rul);
  const vals = {};
  K.RUNS.forEach((r) => {
    vals[r.name] = h("span", { class: "mono val" });
    tracks.appendChild(h("div", { class: "thead" }, K.eye(r.name), K.swatch(r), h("span", { class: "nm" }, r.title.split(" · ")[0]), vals[r.name]));
    const tr = h("div", {}); tracks.appendChild(tr); K.track(tr, r.name);
  });
  function syncTime() {
    tread.textContent = `${K.state.time.toFixed(2)} / ${K.T[K.N - 1].toFixed(2)} s`;
    K.RUNS.forEach((r) => { const v = K.runErrAt(r.name); vals[r.name].textContent = v == null ? "ref" : K.fmt(v, K.angleUnit("°"), 2); });
  }
  K.on("time", syncTime); K.on("units", () => { syncTime(); showTab(cur.tab); }); syncTime();
  K.on("play", () => (playBtn.textContent = K.state.playing ? "❚❚" : "▶"));

  function pageSelect() {
    const s = h("select", { class: "pagesel", title: "scenario" });
    K.F.pages.forEach((p, i) => s.appendChild(h("option", { value: p, disabled: i > 0 }, i ? p + " (not in this prototype)" : p)));
    return s;
  }
  showTab(cur.tab);
})();
