/* V3 · Inspector column — three panes: the 3D with the time lane under it (time belongs to the picture), the
 * question tabs as a dense chart grid, and a foldable inspector on the right that owns every setting: runs (eye, solo,
 * value, worst), angles, Rerun, the 3D view's sliders, and a searchable channel list whose ticks choose what
 * Diagnostics shows. */
(function () {
  const K = window.Kit, h = K.h;
  const app = h("div", { class: "app" }); document.body.appendChild(app);
  const changedFlags = K.channels.filter((c) => c.changed && c.binary).map((c) => c.name);
  const cur = { tab: location.hash.match(/tab=(\w+)/)?.[1] || K.store.get("tab", "track"), sub: {},
    picked: new Set(K.store.get("picked", [...changedFlags, "position_error_rad", "effort_residual_nm"])), q: "", onlyChanged: K.store.get("onlyChanged", false),
    insp: K.store.get("insp", true), secs: K.store.get("secs", { runs: true, view: false, channels: true, units: true }) };

  const inspBtn = h("button", { class: "btn", "data-insp-toggle": "", onclick: () => setInsp(!cur.insp) }, "Inspector");
  app.appendChild(h("header", { class: "top" }, h("b", {}, K.F.report_title), K.pageSelect(), h("span", { class: "muted small ans" }, K.answer("track").head), h("div", { class: "grow" }), inspBtn));
  const main = h("main", { class: "main" }); app.appendChild(main);

  // ---- left: 3D over its time lane ----
  const left = h("section", { class: "left" }); main.appendChild(left);
  const stage = h("div", { class: "stage" }); left.appendChild(stage);
  const sh = h("div", { class: "split h" }); left.appendChild(sh);
  const lane = h("div", { class: "lane", "data-lane": "" }); left.appendChild(lane);
  K.splitter(sh, lane, { axis: "y", key: "lane", def: 190, min: 90, max: 520, invert: true });
  const v3 = K.viewer3d(stage);
  const tread = h("b", { class: "mono" }); const playBtn = h("button", { class: "btn icon", "data-play": "", onclick: K.togglePlay }, "▶");
  lane.appendChild(h("div", { class: "transport" }, h("button", { class: "btn icon", onclick: () => { K.pause(); K.setTime(0); } }, "⏮"),
    h("button", { class: "btn icon", onclick: () => K.step(-1) }, "◀"), playBtn, h("button", { class: "btn icon", onclick: () => K.step(1) }, "▶|"), tread,
    h("span", { class: "grow" }), h("button", { class: "btn worst", "data-worst": "", onclick: () => { K.pause(); K.setTime(K.WORST_T); } }, "◆ Worst"),
    h("button", { class: "btn", onclick: () => K.setZoom(null) }, "Full")));
  const tracks = h("div", { class: "tracks" }); lane.appendChild(tracks);
  const rul = h("div", {}); tracks.appendChild(h("div", { class: "thd faint" }, "s")); tracks.appendChild(rul); K.ruler(rul);
  K.RUNS.forEach((r) => { tracks.appendChild(h("div", { class: "thd" }, K.swatch(r))); const t = h("div", {}); tracks.appendChild(t); K.track(t, r.name, { refText: "Target (reference)" }); });

  const s1 = h("div", { class: "split v" }); main.appendChild(s1);
  K.splitter(s1, left, { axis: "x", key: "left", def: 520, min: 280, max: 1000 });

  // ---- center: tabs as a dense grid ----
  const center = h("section", { class: "center" }); main.appendChild(center);
  const tabbar = h("nav", { class: "tabs" }); const body = h("div", { class: "tabbody" }); center.appendChild(tabbar); center.appendChild(body);
  K.TABS.forEach((t) => tabbar.appendChild(h("button", { "data-tab": t.id, onclick: () => showTab(t.id) }, t.title)));
  function showTab(id) {
    cur.tab = id; K.store.set("tab", id);
    tabbar.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
    K.dropCharts(body); body.innerHTML = "";
    body.appendChild(h("div", { class: "qline" }, h("b", {}, K.answer(id).head)));
    if (id === "where" || id === "signals") {
      const ids = id === "where" ? ["error", "pose"] : ["q", "qd", "qdd", "tau", "all"];
      const words = { error: "Tool error", pose: "Tool pose", q: "angle", qd: "speed", qdd: "acceleration", tau: "torque", all: "all four" };
      const s = h("div", { class: "seg sub" }); const sel = cur.sub[id] || ids[0];
      ids.forEach((k) => s.appendChild(h("button", { class: sel === k ? "on" : "", onclick: () => { cur.sub[id] = k; showTab(id); } }, words[k])));
      body.appendChild(s);
    }
    const grid = h("div", { class: "grid" }); body.appendChild(grid);
    if (id === "track") grid.appendChild(h("div", { class: "statwrap" }, K.statsTable()));
    let specs;
    if (id === "channels") {
      specs = K.channels.filter((c) => cur.picked.has(c.name)).flatMap((c) => K.tabCharts("channels", c.name));
      if (!specs.length) grid.appendChild(h("p", { class: "muted" }, "Tick channels in the inspector’s Channels list."));
      body.insertBefore(h("p", { class: "muted small" }, `${cur.picked.size} of ${K.channels.length} channels ticked in the inspector · ${specs.length} charts`), grid);
    } else {
      const sub = cur.sub[id] || (id === "where" ? "error" : id === "signals" ? "q" : null);
      specs = K.tabCharts(id, sub === "all" ? null : sub);
    }
    specs.forEach((s) => { const d = h("div", { class: "cell" }); grid.appendChild(d); K.chart(d, s, { height: 150, compact: true }); });
  }

  // ---- right: the inspector ----
  const s2 = h("div", { class: "split v" }); main.appendChild(s2);
  const insp = h("aside", { class: "insp", "data-inspector": "" }); main.appendChild(insp);
  K.splitter(s2, insp, { axis: "x", key: "insp", def: 320, min: 240, max: 560, invert: true });
  function setInsp(v) { cur.insp = v; K.store.set("insp", v); app.classList.toggle("noinsp", !v); inspBtn.classList.toggle("on", v); }
  setInsp(cur.insp);
  function section(key, title, ...kids) {
    const d = h("details", { class: "sec", "data-sec": key }, h("summary", {}, title), ...kids); d.open = cur.secs[key] !== false;
    d.addEventListener("toggle", () => { cur.secs[key] = d.open; K.store.set("secs", cur.secs); }); return d;
  }
  // runs
  const rv = {}, rows = h("div", { class: "runs" });
  K.RUNS.forEach((r) => {
    rv[r.name] = h("span", { class: "mono val" });
    const solo = h("button", { class: "solo", "data-solo": r.name, title: "solo", onclick: () => K.soloRun(r.name) }, "S");
    const w = K.worst[r.name];
    rows.appendChild(h("div", { class: "run" }, K.eye(r.name), solo, K.swatch(r), h("span", { class: "nm", title: r.title }, r.title.split(" · ")[0]), rv[r.name],
      w && w.v > 1e-9 ? h("button", { class: "wj", title: "jump to this run's worst moment", onclick: () => { K.pause(); K.setTime(w.t); } }, "◆ " + w.t.toFixed(2)) : h("span", { class: "wj faint" }, w ? "—" : "ref")));
  });
  K.on("runs", () => rows.querySelectorAll(".solo").forEach((b) => b.classList.toggle("on", K.state.solo === b.dataset.solo)));
  insp.appendChild(section("runs", "Runs · error at the playhead", rows));
  insp.appendChild(section("units", "Units and export", h("div", { class: "row" }, h("span", {}, "Angles"), K.unitsSeg()),
    h("button", { class: "btn primary wide", "data-rerun": "", onclick: () => K.rerun(cur.tab) }, "Open in Rerun")));
  insp.appendChild(section("view", "3D view", ...K.VIEW_SLIDERS.map((d) => K.sliderRow(v3, d)), ...K.VIEW_CHECKS.map((d) => K.checkRow(v3, d))));
  // channels
  const search = h("input", { class: "search", type: "search", placeholder: "Search 27 channels", "data-search": "", oninput: (e) => { cur.q = e.target.value.toLowerCase(); paintList(); } });
  const only = h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => { cur.onlyChanged = e.target.checked; K.store.set("onlyChanged", cur.onlyChanged); paintList(); } }), " only channels that changed");
  only.firstChild.checked = cur.onlyChanged;
  const list = h("div", { class: "chlist" });
  const tools = h("div", { class: "row" }, h("button", { class: "btn small", onclick: () => setPicked(K.channels.filter((c) => c.changed).map((c) => c.name)) }, "Tick changed"),
    h("button", { class: "btn small", onclick: () => setPicked([]) }, "Clear"));
  insp.appendChild(section("channels", "Channels · what Diagnostics shows", search, only, tools, list));
  function setPicked(names) { cur.picked = new Set(names); K.store.set("picked", [...cur.picked]); paintList(); if (cur.tab === "channels") showTab("channels"); }
  function paintList() {
    list.innerHTML = "";
    K.FAMILIES.forEach((fam) => {
      const cs = K.channels.filter((c) => c.family === fam && (!cur.onlyChanged || c.changed) && (!cur.q || (c.title + " " + c.name + " " + fam).toLowerCase().includes(cur.q)));
      if (!cs.length) return;
      list.appendChild(h("div", { class: "fam" }, `${fam} · ${cs.filter((c) => c.changed).length}/${cs.length} changed`));
      cs.forEach((c) => {
        const cb = h("input", { type: "checkbox", "data-pick": c.name, onchange: (e) => { e.target.checked ? cur.picked.add(c.name) : cur.picked.delete(c.name); setPicked([...cur.picked]); } });
        cb.checked = cur.picked.has(c.name);
        list.appendChild(h("label", { class: "ch" }, cb, h("span", { class: "dot" + (c.changed ? (c.binary && c.name !== "settled" ? " bad" : " ch") : "") }),
          h("span", { class: "nm", title: c.title }, c.title), h("span", { class: "faint mono" }, c.changed && c.onsetT != null ? K.fmtT(c.onsetT) : c.changed ? "" : "flat")));
      });
    });
  }
  paintList();

  function syncTime() {
    tread.textContent = ` ${K.state.time.toFixed(2)} s`;
    K.RUNS.forEach((r) => { const v = K.runErrAt(r.name); rv[r.name].textContent = v == null ? "" : K.fmt(v, K.angleUnit("°"), 2); });
  }
  K.on("time", syncTime); K.on("units", () => { syncTime(); showTab(cur.tab); }); syncTime();
  K.on("play", () => (playBtn.textContent = K.state.playing ? "❚❚" : "▶"));
  showTab(cur.tab);
})();
