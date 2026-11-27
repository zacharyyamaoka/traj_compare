/* V5 · Moment first — the page opens AT the worst moment and is organised around "now": a moment card on the 3D
 * (time, what happened, each run's error, ‹ previous / next event ›), a video-player scrubber on the 3D's bottom edge,
 * question tabs as a vertical rail with their answers, and every tab leading with an "at this moment" readout. Channels
 * are found by typing (a command palette) and pinned; "near this moment" suggests the ones that move around the playhead. */
(function () {
  const K = window.Kit, h = K.h;
  const app = h("div", { class: "app" }); document.body.appendChild(app);
  const cur = { tab: location.hash.match(/tab=(\w+)/)?.[1] || K.store.get("tab", "track"), sub: {},
    pins: K.store.get("pins", ["collision", "position_error_rad"]) };
  const cssv = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  // events: every flag onset + the worst moment
  const EVENTS = [];
  K.channels.filter((c) => c.binary && c.changed && c.name !== "settled").forEach((c) => K.chEventSpans(c).forEach((s) => EVENTS.push({ t: s.a, what: `${c.title.split(" (")[0]} on the ${s.joint}`, ch: c.name })));
  EVENTS.push({ t: K.WORST_T, what: `worst moment: ${K.worstRun.title.split(" · ")[0]} at its largest joint error`, worst: true });
  const settle = K.chEventSpans(K.chByName.settled)[0]; if (settle) EVENTS.push({ t: settle.a, what: `settled at goal (${settle.joint})`, ch: "settled" });
  EVENTS.sort((a, b) => a.t - b.t);

  app.appendChild(h("header", { class: "top" }, h("b", {}, K.F.report_title), K.pageSelect(), h("div", { class: "grow" }),
    h("span", { class: "faint small" }, "keys: space play · ←/→ step · [ ] events · 1–4 runs · / find a channel"), K.unitsSeg(),
    h("button", { class: "btn primary", "data-rerun": "", onclick: () => K.rerun(cur.tab) }, "Open in Rerun")));
  const main = h("main", { class: "main" }); app.appendChild(main);
  const left = h("section", { class: "left" }); main.appendChild(left);
  const split = h("div", { class: "split v" }); main.appendChild(split);
  const right = h("section", { class: "right" }); main.appendChild(right);
  K.splitter(split, left, { axis: "x", key: "left", def: 640, min: 320, max: 1100 });

  // ---- 3D with moment card, HUD and the player bar ----
  const stage = h("div", { class: "stage" }); left.appendChild(stage);
  const v3 = K.viewer3d(stage);
  const card = h("div", { class: "card", "data-moment": "" }); stage.appendChild(card);
  const ctime = h("div", { class: "ct mono" }), cwhat = h("div", { class: "cw" }), crows = h("div", { class: "cr" });
  card.appendChild(ctime); card.appendChild(cwhat); card.appendChild(crows);
  card.appendChild(h("div", { class: "cnav" }, h("button", { class: "btn", "data-prev-event": "", onclick: () => jump(-1) }, "‹ previous event"),
    h("button", { class: "btn worst", "data-worst": "", onclick: () => { K.pause(); K.setTime(K.WORST_T); } }, "◆ worst"),
    h("button", { class: "btn", "data-next-event": "", onclick: () => jump(1) }, "next event ›")));
  const rv = {};
  K.RUNS.forEach((r, i) => { rv[r.name] = h("span", { class: "mono" }); crows.appendChild(h("div", { class: "crow" }, h("kbd", {}, String(i + 1)), K.eye(r.name), K.swatch(r), h("span", { class: "nm" }, r.title.split(" · ")[0]), rv[r.name])); });
  const hud = h("div", { class: "hud", "data-hud": "" });
  const gear = h("button", { class: "btn gear", "data-viewsettings": "", title: "view settings", onclick: () => hud.classList.toggle("open") }, "View ⚙");
  stage.appendChild(gear); stage.appendChild(hud);
  K.VIEW_SLIDERS.forEach((d) => hud.appendChild(K.sliderRow(v3, d))); K.VIEW_CHECKS.forEach((d) => hud.appendChild(K.checkRow(v3, d)));
  const player = h("div", { class: "player", "data-lane": "" }); stage.appendChild(player);
  const playBtn = h("button", { class: "pbtn", "data-play": "", onclick: K.togglePlay }, "▶");
  const bar = h("div", { class: "pbar" }); const ptime = h("span", { class: "mono pt" });
  player.appendChild(playBtn); player.appendChild(bar); player.appendChild(ptime);
  const pc = h("canvas"); bar.appendChild(pc);
  function drawBar() {
    const r = bar.getBoundingClientRect(); const d = window.devicePixelRatio || 1; pc.width = r.width * d; pc.height = r.height * d;
    const g = pc.getContext("2d"); g.setTransform(d, 0, 0, d, 0, 0); const W = r.width, H = r.height; const X = (t) => (t / K.T[K.N - 1]) * W;
    g.fillStyle = "rgba(255,255,255,.18)"; g.fillRect(0, H / 2 - 2, W, 4);
    g.fillStyle = cssv("--accent"); g.fillRect(0, H / 2 - 2, X(K.state.time), 4);
    const a = K.errMax[K.worstRun.name], mx = K.worst[K.worstRun.name].v;
    g.strokeStyle = K.worstRun.color + "aa"; g.beginPath(); a.forEach((v, i) => { const y = H / 2 - 4 - (v / mx) * (H / 2 - 6); i ? g.lineTo(X(K.T[i]), y) : g.moveTo(X(K.T[i]), y); }); g.stroke();
    EVENTS.forEach((e) => { g.fillStyle = e.worst ? cssv("--bad") : e.ch === "settled" ? cssv("--good") : cssv("--warn"); const x = X(e.t);
      if (e.worst) { g.beginPath(); g.moveTo(x, H / 2 + 3); g.lineTo(x + 5, H / 2 + 8); g.lineTo(x, H / 2 + 13); g.lineTo(x - 5, H / 2 + 8); g.fill(); } else g.fillRect(x - 1, H / 2 + 4, 2, 8); });
    g.fillStyle = "#fff"; g.beginPath(); g.arc(X(K.state.time), H / 2, 6, 0, 7); g.fill();
  }
  let down = false; const toT = (e) => { const r = bar.getBoundingClientRect(); return ((e.clientX - r.left) / r.width) * K.T[K.N - 1]; };
  bar.addEventListener("pointerdown", (e) => { bar.setPointerCapture(e.pointerId); down = true; K.pause(); K.setTime(toT(e)); });
  bar.addEventListener("pointermove", (e) => down && K.setTime(toT(e))); bar.addEventListener("pointerup", () => (down = false));
  new ResizeObserver(drawBar).observe(bar);
  function jump(dir) {
    const t = K.state.time; const ts = [...new Set(EVENTS.map((e) => e.t))];
    const n = dir > 0 ? ts.find((x) => x > t + 1e-6) : ts.reverse().find((x) => x < t - 1e-6);
    if (n != null) { K.pause(); K.setTime(n); }
  }
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input")) return;
    if (e.key === "]") jump(1); else if (e.key === "[") jump(-1);
    else if (/^[1-4]$/.test(e.key)) K.toggleRun(K.RUNS[+e.key - 1].name);
    else if (e.key === "/") { e.preventDefault(); if (cur.tab !== "channels") showTab("channels"); setTimeout(() => body.querySelector("[data-palette]")?.focus(), 0); }
  });

  // ---- right: vertical rail + content ----
  const rail = h("nav", { class: "rail" }); right.appendChild(rail);
  const body = h("div", { class: "content" }); right.appendChild(body);
  K.TABS.forEach((t) => { const a = K.answer(t.id); rail.appendChild(h("button", { "data-tab": t.id, onclick: () => showTab(t.id) }, h("span", {}, t.title), h("small", {}, a.badge || ""))); });
  function showTab(id) {
    cur.tab = id; K.store.set("tab", id);
    rail.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
    K.dropCharts(body); body.innerHTML = "";
    body.appendChild(h("div", { class: "answer" }, h("span", { class: "muted" }, K.TABS.find((t) => t.id === id).heading), h("b", {}, K.answer(id).head)));
    if (id === "where" || id === "signals") {
      const ids = id === "where" ? ["error", "pose"] : ["q", "qd", "qdd", "tau"];
      const words = { error: "Tool error", pose: "Tool pose", q: "angle", qd: "speed", qdd: "acceleration", tau: "torque" };
      const s = h("div", { class: "seg sub" }); const sel = cur.sub[id] || ids[0];
      ids.forEach((k) => s.appendChild(h("button", { class: sel === k ? "on" : "", onclick: () => { cur.sub[id] = k; showTab(id); } }, words[k])));
      body.appendChild(s);
    }
    let specs;
    if (id === "channels") { palette(); specs = cur.pins.flatMap((n) => K.tabCharts("channels", n)); }
    else specs = K.tabCharts(id, cur.sub[id] || (id === "where" ? "error" : id === "signals" ? "q" : null));
    const read = h("table", { class: "readout", "data-readout": "" }); body.appendChild(h("div", { class: "rhead" }, h("b", {}, "At this moment"), h("span", { class: "muted mono rt" })));
    body.appendChild(read);
    const runs = K.RUNS.filter((r) => specs.some((s) => s.lines.some((l) => l.run === r.name)));
    read.appendChild(h("thead", {}, h("tr", {}, h("th", {}, ""), runs.map((r) => h("th", {}, K.swatch(r), " ", r.title.split(" · ")[0])))));
    const tb = h("tbody"); read.appendChild(tb);
    const cells = specs.map((s) => { const tr = h("tr", {}, h("th", {}, s.title, h("span", { class: "faint" }, ` [${s.unit || "–"}]`))); const cs = runs.map((r) => { const td = h("td", { class: "mono" }); tr.appendChild(td); return [s, r.name, td]; }); tb.appendChild(tr); return cs; }).flat();
    body._cells = cells; syncRead();
    if (id === "track") body.appendChild(h("details", { class: "statd" }, h("summary", {}, "Error statistics over the whole run"), K.statsTable()));
    const grid = h("div", { class: "charts" }); body.appendChild(grid);
    specs.forEach((s) => { const d = h("div", { class: "cell" }); grid.appendChild(d); K.chart(d, s, { height: specs.length > 2 ? 140 : 200, worstLine: true }); });
  }
  function syncRead() {
    (body._cells || []).forEach(([s, run, td]) => (td.textContent = K.shown(run) ? K.fmt(K.specValueAt(s, run), "") : "hidden"));
    const rt = body.querySelector(".rt"); if (rt) rt.textContent = `t = ${K.fmtT(K.state.time)}`;
  }
  // ---- the channel palette ----
  function palette() {
    const box = h("div", { class: "palette" });
    const inp = h("input", { type: "search", placeholder: "Find a channel… (press /)", "data-palette": "", autocomplete: "off" });
    const res = h("div", { class: "results" });
    box.appendChild(inp); box.appendChild(res); body.appendChild(box);
    const paint = () => {
      const q = inp.value.trim().toLowerCase(); res.innerHTML = "";
      if (!q && document.activeElement !== inp) { res.style.display = "none"; return; }
      const hits = K.channels.map((c) => ({ c, s: score(c, q) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s).slice(0, 8);
      hits.forEach(({ c }, i) => res.appendChild(h("button", { class: "hit" + (i === 0 ? " first" : ""), "data-hit": c.name, onmousedown: (e) => { e.preventDefault(); pin(c.name); inp.value = ""; inp.blur(); } },
        h("span", { class: "dot" + (c.changed ? " ch" : "") }), h("span", { class: "nm" }, c.title), h("span", { class: "faint" }, c.family), cur.pins.includes(c.name) ? h("span", { class: "tag" }, "pinned") : null)));
      res.style.display = hits.length ? "block" : "none";
    };
    inp.addEventListener("input", paint); inp.addEventListener("focus", paint); inp.addEventListener("blur", () => setTimeout(paint, 0));
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { const f = res.querySelector(".hit"); if (f) { pin(f.dataset.hit); inp.value = ""; inp.blur(); } } if (e.key === "Escape") inp.blur(); });
    const pinsRow = h("div", { class: "pins" }, h("span", { class: "muted small" }, "Pinned"));
    cur.pins.forEach((n) => pinsRow.appendChild(h("span", { class: "pinchip", "data-pin": n }, K.chByName[n].title.split(" (")[0], h("button", { onclick: () => unpin(n), title: "unpin" }, "×"))));
    body.appendChild(pinsRow);
    const near = h("div", { class: "near", "data-near": "" }); body.appendChild(near); body._near = near; paintNear();
  }
  function paintNear() {
    const near = body._near; if (!near || !document.body.contains(near)) return;
    const list = K.chNear(K.state.time, 0.25).filter((c) => !cur.pins.includes(c.name));
    near.innerHTML = ""; near.appendChild(h("span", { class: "muted small" }, `Moving within ±0.25 s of ${K.fmtT(K.state.time)}`));
    list.slice(0, 10).forEach((c) => near.appendChild(h("button", { class: "sugg", "data-suggest": c.name, onclick: () => pin(c.name) }, "+ " + c.title.split(" (")[0])));
    if (!list.length) near.appendChild(h("span", { class: "faint small" }, "nothing else moves here"));
  }
  function score(c, q) {
    if (!q) return c.changed ? 2 : 1;
    const hay = (c.title + " " + c.name.replace(/_/g, " ") + " " + c.family).toLowerCase();
    if (hay.includes(q)) return 10 - hay.indexOf(q) / 100 + (c.changed ? 1 : 0);
    let i = 0; for (const ch of hay) if (ch === q[i]) i++; return i === q.length ? 2 + (c.changed ? 1 : 0) : 0;
  }
  function pin(n) { if (!cur.pins.includes(n)) cur.pins.push(n); K.store.set("pins", cur.pins); showTab("channels"); }
  function unpin(n) { cur.pins = cur.pins.filter((x) => x !== n); K.store.set("pins", cur.pins); showTab("channels"); }

  let lastNear = -1;
  function syncTime() {
    const t = K.state.time; ctime.textContent = `t = ${K.fmtT(t)} / ${K.fmtT(K.T[K.N - 1])}`; ptime.textContent = K.fmtT(t);
    const e = EVENTS.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a));
    cwhat.innerHTML = Math.abs(e.t - t) < 0.015 ? `<b>${e.what}</b>` : `<span class="muted">nearest event: ${e.what} (${(e.t - t > 0 ? "in " : "") + Math.abs(e.t - t).toFixed(2)} s${e.t - t < 0 ? " ago" : ""})</span>`;
    K.RUNS.forEach((r) => { const v = K.runErrAt(r.name); rv[r.name].textContent = v == null ? "reference" : K.fmt(v, K.angleUnit("°"), 2) + " joint error"; });
    drawBar(); syncRead();
    const k = Math.round(t / 0.05); if (k !== lastNear) { lastNear = k; paintNear(); }
  }
  K.on("time", syncTime); K.on("runs", syncRead); K.on("units", () => { showTab(cur.tab); syncTime(); });
  K.on("play", () => (playBtn.textContent = K.state.playing ? "❚❚" : "▶"));
  showTab(cur.tab);
  K.setTime(K.WORST_T); syncTime();
})();
