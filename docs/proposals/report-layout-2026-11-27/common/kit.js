/* Shared kit for the report-layout round (2026-11-27): data, one time state, uPlot charts with a playhead you drag,
 * a three.js view of the real tool paths, the lane's ruler and run tracks, splitters that remember their size.
 * Every variant composes these; only the layout differs. Data = window.FIXTURE (extract.py, real X1.ElbowStop@-60). */
(function () {
  "use strict";
  const F = window.FIXTURE;
  const T = F.t;
  const N = T.length;
  const DEG = 180 / Math.PI;
  const RUNS = F.runs;
  const byName = Object.fromEntries(RUNS.map((r) => [r.name, r]));
  const JOINTS = F.joints;

  // ---------- storage (per-viewer conveniences only) ----------
  const NS = "tc-layout-" + (document.documentElement.dataset.variant || "x") + ":";
  const store = {
    get(k, d) { try { const v = localStorage.getItem(NS + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(NS + k, JSON.stringify(v)); } catch (e) { /* private window */ } },
  };

  // ---------- state ----------
  const listeners = {};
  const state = {
    time: 0, units: store.get("units", "deg"), visible: new Set(store.get("visible", RUNS.map((r) => r.name))),
    solo: null, zoom: null, playing: false, speed: 1,
  };
  function on(evt, fn) { (listeners[evt] = listeners[evt] || []).push(fn); }
  function emit(evt) { (listeners[evt] || []).forEach((fn) => fn(state)); }
  function idxAt(t) {
    let lo = 0, hi = N - 1;
    while (lo < hi) { const m = (lo + hi) >> 1; if (T[m] < t) lo = m + 1; else hi = m; }
    if (lo > 0 && Math.abs(T[lo - 1] - t) < Math.abs(T[lo] - t)) lo -= 1;
    return lo;
  }
  function setTime(t) {
    const tt = Math.min(Math.max(t, T[0]), T[N - 1]);
    if (tt === state.time) return;
    state.time = tt; emit("time");
  }
  function shown(name) { return state.solo ? state.solo === name : state.visible.has(name); }
  function toggleRun(name) {
    if (state.visible.has(name)) state.visible.delete(name); else state.visible.add(name);
    state.solo = null; store.set("visible", [...state.visible]); emit("runs");
  }
  function soloRun(name) { state.solo = state.solo === name ? null : name; emit("runs"); }
  function setUnits(u) { if (u === state.units) return; state.units = u; store.set("units", u); emit("units"); }
  function setZoom(z) { state.zoom = z; emit("zoom"); }

  // ---------- transport ----------
  let raf = 0, last = 0;
  function frame(ts) {
    if (!state.playing) return;
    const dt = last ? (ts - last) / 1000 : 0; last = ts;
    const next = state.time + dt * state.speed;
    if (next >= T[N - 1]) { setTime(T[N - 1]); pause(); return; }
    setTime(next); raf = requestAnimationFrame(frame);
  }
  function play() { if (state.playing) return; if (state.time >= T[N - 1]) setTime(0); state.playing = true; last = 0; emit("play"); raf = requestAnimationFrame(frame); }
  function pause() { state.playing = false; cancelAnimationFrame(raf); emit("play"); }
  function togglePlay() { state.playing ? pause() : play(); }
  function step(k) { pause(); setTime(T[Math.min(Math.max(idxAt(state.time) + k, 0), N - 1)]); }
  document.addEventListener("keydown", (e) => {
    if (e.target.closest && e.target.closest("input,textarea,select,[contenteditable]")) return;
    if (e.code === "Space") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowRight" && !e.metaKey) { step(e.shiftKey ? 10 : 1); }
    else if (e.key === "ArrowLeft" && !e.metaKey) { step(e.shiftKey ? -10 : -1); }
  });

  // ---------- derived numbers (all computed from the fixture) ----------
  const measuredRuns = RUNS.filter((r) => r.role !== "target");
  function jointErrMax(run) { // largest joint error over joints, |Target − run| [rad]
    const e = run.plot.err_q; if (!e) return null;
    return T.map((_, i) => Math.max(...e.map((col) => Math.abs(col[i] || 0))));
  }
  const errMax = Object.fromEntries(RUNS.map((r) => [r.name, jointErrMax(r)]));
  function argmax(a) { let k = 0; for (let i = 1; i < a.length; i++) if ((a[i] || 0) > (a[k] || 0)) k = i; return k; }
  const worst = {};
  for (const r of measuredRuns) {
    const a = errMax[r.name]; const k = argmax(a); const peak = a[k];
    const rise = a.findIndex((v) => v > peak / 2);
    worst[r.name] = { i: k, t: T[k], v: peak, rise: peak > 1e-9 ? T[rise] : null };
  }
  const worstRun = measuredRuns.reduce((a, b) => (worst[b.name].v > worst[a.name].v ? b : a));
  const WORST_T = worst[worstRun.name].t;

  // ---------- units ----------
  const ANGLE_UNITS = { "°": "rad", "°/s": "rad/s", "°/s²": "rad/s²" };
  function angle(v) { return state.units === "deg" ? v * DEG : v; }
  function angleUnit(base) { return state.units === "deg" ? base : ANGLE_UNITS[base]; }
  function fmt(v, unit, digits) {
    if (v == null || !isFinite(v)) return "—";
    const d = digits != null ? digits : Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : Math.abs(v) >= 1 ? 2 : 3;
    const s = v.toFixed(d).replace("-", "−");
    return unit ? s + (unit === "°" ? "°" : " " + unit) : s;
  }
  const fmtT = (t) => t.toFixed(2) + " s";

  // ---------- channels ----------
  const FAMILY = {
    collision: "Stops and flags", contact: "Stops and flags", blocked: "Stops and flags", settled: "Stops and flags",
    at_cap: "Stops and flags", outcome: "Stops and flags", command_sent: "Stops and flags",
    servo_timeout: "Board faults", servo_fault: "Board faults",
    position_error_rad: "Tracking", velocity_error_rad_s: "Tracking", lead_rad: "Tracking", path_margin_rad: "Tracking",
    command_offset_rad: "Tracking", progress: "Tracking", late_s: "Tracking",
    effort_residual_nm: "Torque and speed", effort_cap_nm: "Torque and speed", drive_power_w: "Torque and speed",
    overspeed_rad_s: "Torque and speed", limit_margin_rad: "Torque and speed",
    tick_period_s: "Timing", missed_ticks: "Timing", state_age_s: "Timing",
    truth_contact: "Plant truth (MuJoCo)", truth_contact_force_n: "Plant truth (MuJoCo)", truth_stop_torque_nm: "Plant truth (MuJoCo)",
  };
  const FAMILIES = ["Stops and flags", "Tracking", "Torque and speed", "Board faults", "Timing", "Plant truth (MuJoCo)"];
  const channels = F.channels.map((c) => {
    const run = RUNS.find((r) => r.channels && r.channels[c.name]);
    const cols = run ? run.channels[c.name] : [];
    const names = c.per_joint ? c.columns : [""];
    let changed = false, peak = null, peakT = null, onsetT = null, peakJoint = null, empty = true;
    cols.forEach((col, j) => {
      const vals = col.filter((v) => v != null);
      if (!vals.length) return;
      empty = false;
      const lo = Math.min(...vals), hi = Math.max(...vals);
      if (hi - lo > 1e-9) {
        changed = true;
        const first = col.findIndex((v, i) => v != null && Math.abs(v - (col.find((x) => x != null))) > 1e-9);
        if (first >= 0 && (onsetT == null || T[first] < onsetT)) onsetT = T[first];
      }
      col.forEach((v, i) => { if (v != null && (peak == null || Math.abs(v) > Math.abs(peak))) { peak = v; peakT = T[i]; peakJoint = names[j]; } });
    });
    const binary = c.unit === "0/1";
    return { ...c, run: run ? run.name : null, cols, names, changed, peak, peakT, peakJoint, onsetT, empty, binary,
      family: FAMILY[c.name] || "Other", angle: c.unit in ANGLE_UNITS };
  });
  const chByName = Object.fromEntries(channels.map((c) => [c.name, c]));
  function chValue(c, v) { return c.angle && state.units === "rad" ? v / DEG : v; }
  function chUnit(c) { return c.angle ? angleUnit(c.unit) : c.unit; }
  function chEventSpans(c) { // [{joint, a, b}] where a 0/1 flag is on
    const spans = [];
    c.cols.forEach((col, j) => {
      let a = null;
      col.forEach((v, i) => {
        const onNow = v != null && v > 0.5;
        if (onNow && a == null) a = T[i];
        if (!onNow && a != null) { spans.push({ joint: c.names[j], a, b: T[i] }); a = null; }
      });
      if (a != null) spans.push({ joint: c.names[j], a, b: T[N - 1] });
    });
    return spans;
  }
  function chNear(t, win) { // channels whose value changes within ±win of t
    const i0 = idxAt(t - win), i1 = idxAt(t + win);
    return channels.filter((c) => c.cols.some((col) => {
      let lo = Infinity, hi = -Infinity;
      for (let i = i0; i <= i1; i++) { const v = col[i]; if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
      return hi - lo > 1e-6 * Math.max(1, Math.abs(hi));
    }));
  }

  // ---------- chart specs per tab ----------
  const sig = {
    q: ["joint angle", "°", true], qd: ["joint speed", "°/s", true], qdd: ["joint acceleration", "°/s²", true],
    tau: ["joint torque", "N·m", false],
  };
  function lineFor(run, y, extra) {
    return { run: run.name, label: run.title.split(" · ")[0], color: run.color, dash: run.role === "target", y, ...(extra || {}) };
  }
  function jointSignal(key, j) {
    const [words, unit, isAngle] = sig[key];
    return {
      id: `${key}-${j}`, group: words, joint: JOINTS[j], unit: isAngle ? angleUnit(unit) : unit,
      title: `${JOINTS[j]}: ${words}${key === "tau" ? "" : ""}`,
      lines: RUNS.filter((r) => r.plot[key]).map((r) => lineFor(r, r.plot[key][j].map((v) => (isAngle ? angle(v) : v)))),
    };
  }
  function jointError(j) {
    return {
      id: `err-${j}`, group: "joint error", joint: JOINTS[j], unit: angleUnit("°"),
      title: `${JOINTS[j]}: joint error, Target − run`,
      lines: measuredRuns.map((r) => lineFor(r, r.plot.err_q[j].map(angle))),
    };
  }
  function tcp(key, title, scale, unit) {
    return { id: key, group: title, unit, title, lines: measuredRuns.filter((r) => r.plot[key]).map((r) => lineFor(r, r.plot[key].map((v) => (v == null ? null : v * scale)))) };
  }
  function pose(key, title) {
    return { id: "pose-" + key, group: "tool pose", unit: "mm", title, lines: RUNS.map((r) => lineFor(r, r.plot[key].map((v) => v * 1000))) };
  }
  function channelCharts(c) {
    const run = byName[c.run];
    return c.cols.map((col, j) => ({
      id: `ch-${c.name}-${j}`, group: c.title, joint: c.names[j], unit: chUnit(c), channel: c.name, step: c.binary,
      title: c.names[j] ? `${c.title}, ${c.names[j]}` : c.title,
      lines: run ? [lineFor(run, col.map((v) => (v == null ? null : chValue(c, v))))] : [],
    }));
  }
  const largestJoint = () => ({
    id: "largest", group: "largest joint error", unit: angleUnit("°"), title: "Largest joint error (max over joints, |Target − run|)",
    lines: measuredRuns.map((r) => lineFor(r, errMax[r.name].map(angle))),
  });
  function tabCharts(tab, sub) {
    switch (tab) {
      case "track": return [tcp("xyz_mag", "Tool position error |Δp|", 1000, "mm"), largestJoint()];
      case "where":
        if (sub === "pose") return [pose("x", "Tool x"), pose("y", "Tool y"), pose("z", "Tool z")];
        return [tcp("xyz_mag", "Tool position error |Δp|", 1000, "mm"), tcp("cross_track", "Off the path (cross-track)", 1000, "mm"),
          tcp("err_x", "Tool error x", 1000, "mm"), tcp("err_z", "Tool error z", 1000, "mm"), tcp("err_y", "Tool error y", 1000, "mm")];
      case "joints": return JOINTS.map((_, j) => jointError(j)).sort((a, b) => maxAbs(b) - maxAbs(a));
      case "timing": return [tcp("lag", "Behind along the path (lag, + = late)", 1000, "mm"), tcp("cross_track", "Off the path (cross-track)", 1000, "mm"),
        tcp("lag_time", "Lag time (+ = late)", 1, "s"), tcp("contour", "Distance to the target path (contour)", 1000, "mm")];
      case "signals": {
        const keys = sub && sig[sub] ? [sub] : ["q", "qd", "qdd", "tau"];
        return keys.flatMap((k) => JOINTS.map((_, j) => jointSignal(k, j)));
      }
      case "channels": return (sub ? [chByName[sub]] : channels).filter(Boolean).flatMap(channelCharts);
    }
    return [];
  }
  function maxAbs(spec) { let m = 0; spec.lines.forEach((l) => l.y.forEach((v) => { if (v != null) m = Math.max(m, Math.abs(v)); })); return m; }

  // ---------- one-line answers (computed) ----------
  function peakOf(run, key, scale) { const a = run.plot[key]; const k = argmax(a.map((v) => Math.abs(v || 0))); return { v: Math.abs(a[k]) * scale, t: T[k] }; }
  function answer(tab) {
    const m = byName.measured, tr = byName.truth, cmd = byName.command;
    const pm = peakOf(m, "xyz_mag", 1000), pc = peakOf(cmd, "xyz_mag", 1000);
    const jPeak = JOINTS.map((_, j) => Math.max(...m.plot.err_q[j].map(Math.abs)));
    const jw = jPeak[0] > jPeak[1] ? 0 : 1;
    const flags = channels.filter((c) => c.binary && c.changed && c.name !== "settled");
    switch (tab) {
      case "track": return { head: `No — Measured missed by up to ${fmt(pm.v, "mm", 1)} at ${fmtT(pm.t)}`, facts: [
        `Command matched the target (${fmt(pc.v, "mm", 1)})`, `MuJoCo truth agrees with Measured`, `worst joint: ${JOINTS[jw]} ${fmt(angle(jPeak[jw]), angleUnit("°"), 1)}`], badge: fmt(pm.v, "mm", 0) };
      case "where": { const px = peakOf(m, "err_x", 1000), pz = peakOf(m, "err_z", 1000), ct = peakOf(m, "cross_track", 1000);
        return { head: `Mostly along x: ${fmt(px.v, "mm", 1)} in x, ${fmt(pz.v, "mm", 1)} in z, peak at ${fmtT(px.t)}`, facts: [`off the path by up to ${fmt(ct.v, "mm", 1)}`, `y and rotation stay 0`], badge: `x ${fmt(px.v, "mm", 0)}` }; }
      case "joints": return { head: `The ${JOINTS[jw]}: ${fmt(angle(jPeak[jw]), angleUnit("°"), 1)} peak vs ${fmt(angle(jPeak[1 - jw]), angleUnit("°"), 2)} on the ${JOINTS[1 - jw]}`,
        facts: [`elbow RMS ${fmt(angle(m.metrics["positions/elbow"].rms), angleUnit("°"), 2)}`, `peak at ${fmtT(T[argmax(m.plot.err_q[jw].map(Math.abs))])}`], badge: JOINTS[jw] };
      case "timing": { const lag = m.metrics.lag, ct = m.metrics.cross_track;
        return { head: ct.rms > lag.rms ? `More off the path than late: cross-track RMS ${fmt(ct.rms * 1000, "mm", 1)} vs lag ${fmt(lag.rms * 1000, "mm", 1)}` : `More late than off the path`,
          facts: [`lag time up to ${fmt(Math.max(...m.plot.lag_time.filter((v) => v != null).map(Math.abs)), "s", 2)}`], badge: "off path" }; }
      case "signals": { const tp = Math.max(...m.plot.tau[1].map(Math.abs));
        return { head: `Elbow torque peaks at ${fmt(tp, "N·m", 1)}; the elbow stops while the target keeps moving`, facts: [`q, qd, qdd, torque · ${JOINTS.length} joints × ${RUNS.length} runs`], badge: "" }; }
      case "channels": { const ch = channels.filter((c) => c.changed); const first = flags.slice().sort((a, b) => a.onsetT - b.onsetT)[0];
        return { head: `${ch.length} of ${channels.length} channels changed; first flag: ${first.title.split(" (")[0]} on the ${first.peakJoint} at ${fmtT(first.onsetT)}`,
          facts: flags.map((c) => `${c.title.split(" (")[0].split(":")[0]} ${fmtT(c.onsetT)}`), badge: `${ch.length} changed` }; }
    }
    return { head: "", facts: [], badge: "" };
  }

  // ---------- charts (uPlot) ----------
  const charts = new Set();
  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function chart(el, spec, opts) {
    opts = opts || {};
    el.classList.add("kit-chart");
    el.innerHTML = "";
    if (opts.title !== false) {
      const t = document.createElement("div"); t.className = "ttl";
      t.innerHTML = `<b>${spec.title}</b> <span>[${spec.unit || "–"}]</span>`; el.appendChild(t);
    }
    const host = document.createElement("div"); el.appendChild(host);
    const height = opts.height || 150;
    const width = Math.max(120, el.clientWidth || 400);
    const data = [T, ...spec.lines.map((l) => l.y)];
    let rec = null;
    const axisFont = "11px " + css("--font");
    const u = new uPlot({
      width, height, legend: { show: false }, padding: [6, 10, 0, 0],
      hooks: { draw: [() => { if (rec) placePH(rec); }] }, // WHY: uPlot lays out after construction; place the playhead once it has drawn
      cursor: { drag: { x: false, y: false }, points: { show: false }, y: false, x: !!opts.hoverLine },
      scales: { x: { time: false, min: state.zoom ? state.zoom[0] : T[0], max: state.zoom ? state.zoom[1] : T[N - 1] },
        y: { range: (u, lo, hi) => {
          if (spec.unit === "0/1") return [-0.1, 1.15];
          if (lo == null || hi == null) return [0, 1];
          if (hi - lo < 1e-9) { const pad = Math.max(1, Math.abs(hi) * 0.1); return [lo - pad, hi + pad]; }
          const pad = (hi - lo) * 0.08; return [lo - pad, hi + pad];
        } } },
      axes: [
        { stroke: css("--axis"), grid: { stroke: css("--grid"), width: 1 }, ticks: { stroke: css("--grid") }, font: axisFont, size: opts.compact ? 18 : 26, show: opts.xAxis !== false },
        { stroke: css("--axis"), grid: { stroke: css("--grid"), width: 1 }, ticks: { show: false }, font: axisFont, size: opts.ySize || 46 },
      ],
      series: [{}, ...spec.lines.map((l) => ({ stroke: l.color, width: l.dash ? 1.4 : 1.6, dash: l.dash ? [5, 4] : undefined,
        show: shown(l.run), spanGaps: false, paths: spec.step ? uPlot.paths.stepped({ align: 1 }) : undefined, points: { show: false } }))],
    }, data, host);
    const ph = document.createElement("div"); ph.className = "kit-ph"; u.over.appendChild(ph);
    let wl = null;
    if (opts.worstLine) { wl = document.createElement("div"); wl.className = "kit-worst"; u.over.appendChild(wl); }
    rec = { el, u, spec, ph, wl, opts };
    placePH(rec);
    // drag anywhere on the plot = scrub the one time; shift-drag = zoom every chart alike; double-click = full range
    let down = null;
    u.over.addEventListener("pointerdown", (e) => {
      u.over.setPointerCapture(e.pointerId); pause();
      down = { x: e.offsetX, shift: e.shiftKey };
      if (!e.shiftKey) setTime(u.posToVal(e.offsetX, "x"));
    });
    u.over.addEventListener("pointermove", (e) => {
      if (!down) { if (opts.onHover) opts.onHover(u.posToVal(e.offsetX, "x")); return; }
      if (!down.shift) setTime(u.posToVal(e.offsetX, "x"));
    });
    u.over.addEventListener("pointerup", (e) => {
      if (down && down.shift && Math.abs(e.offsetX - down.x) > 6) {
        const a = u.posToVal(Math.min(e.offsetX, down.x), "x"), b = u.posToVal(Math.max(e.offsetX, down.x), "x");
        setZoom([a, b]);
      }
      down = null;
    });
    u.over.addEventListener("dblclick", () => setZoom(null));
    u.over.addEventListener("wheel", (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const z = state.zoom || [T[0], T[N - 1]]; const c = u.posToVal(e.offsetX, "x"); const k = e.deltaY > 0 ? 1.25 : 0.8;
      const a = Math.max(T[0], c - (c - z[0]) * k), b = Math.min(T[N - 1], c + (z[1] - c) * k);
      setZoom(b - a >= T[N - 1] - T[0] - 1e-9 ? null : [a, b]);
    }, { passive: false });
    const ro = new ResizeObserver(() => { const w = el.clientWidth; if (w > 50 && Math.abs(w - u.width) > 1) { u.setSize({ width: w, height: u.height }); placePH(rec); } });
    ro.observe(el); rec.ro = ro;
    charts.add(rec);
    return rec;
  }
  function placePH(rec) {
    const x = rec.u.valToPos(state.time, "x");
    rec.ph.style.left = x + "px";
    rec.ph.style.display = x < 0 || x > rec.u.over.clientWidth + 1 ? "none" : "";
    if (rec.wl) rec.wl.style.left = rec.u.valToPos(WORST_T, "x") + "px";
  }
  function dropCharts(container) {
    for (const rec of [...charts]) if (!document.body.contains(rec.el) || (container && container.contains(rec.el))) {
      if (rec.ro) rec.ro.disconnect(); rec.u.destroy(); charts.delete(rec);
    }
  }
  on("time", () => charts.forEach(placePH));
  on("runs", () => charts.forEach((rec) => rec.spec.lines.forEach((l, i) => rec.u.setSeries(i + 1, { show: shown(l.run) }))));
  on("zoom", () => charts.forEach((rec) => { rec.u.setScale("x", { min: state.zoom ? state.zoom[0] : T[0], max: state.zoom ? state.zoom[1] : T[N - 1] }); placePH(rec); }));

  // ---------- value at the playhead ----------
  function runErrAt(name, t) { const a = errMax[name]; return a ? angle(a[idxAt(t == null ? state.time : t)]) : null; }
  function specValueAt(spec, run, t) { const l = spec.lines.find((x) => x.run === run); return l ? l.y[idxAt(t == null ? state.time : t)] : null; }

  // ---------- 3D (three.js r160, z-up) ----------
  const viewers = [];
  function viewer3d(el, init) {
    const o = Object.assign({ decay: 5, ahead: 2, mag: 1, markers: 20, size: 11, arrows: true, ghost: true, comet: true }, init || {});
    el.classList.add("kit-3d");
    const scene = new THREE.Scene();
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    el.appendChild(renderer.domElement);
    const hint = document.createElement("div"); hint.className = "hint"; hint.textContent = "drag: orbit · right-drag: pan · wheel: zoom · double-click: fit"; el.appendChild(hint);
    const camera = new THREE.PerspectiveCamera(24, 1, 0.001, 50); camera.up.set(0, 0, 1);
    const all = []; RUNS.forEach((r) => r.path.forEach((p) => all.push(p)));
    const lo = [0, 1, 2].map((k) => Math.min(...all.map((p) => p[k]))), hi = [0, 1, 2].map((k) => Math.max(...all.map((p) => p[k])));
    const center = new THREE.Vector3((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2);
    const radius = Math.max(0.05, Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2);
    const grid = new THREE.GridHelper(radius * 3, 12, 0x555555, 0x3a3a3a); grid.rotation.x = Math.PI / 2; grid.position.set(center.x, center.y, lo[2] - 0.01);
    scene.add(grid);
    const axes = new THREE.AxesHelper(radius * 0.35); axes.position.set(lo[0] - radius * 0.2, lo[1] - radius * 0.2, lo[2]); scene.add(axes);
    const HOME = { az: -1.3, el: 0.28, dist: radius * 5.6 };
    const fitDist = () => (radius * 1.25) / Math.sin((camera.fov * Math.PI) / 360) / Math.min(1, camera.aspect || 1);
    const view = { ...HOME, target: center.clone() };
    const groups = {};
    RUNS.forEach((r) => {
      const g = new THREE.Group(); scene.add(g); groups[r.name] = g;
      const pts = r.path.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
      const col = new THREE.Color(r.color);
      const ghost = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: r.role === "target" ? 0.5 : 0.3 }));
      g.add(ghost);
      const trailGeo = new THREE.BufferGeometry().setFromPoints(pts);
      trailGeo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(pts.length * 3), 3));
      const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ vertexColors: true }));
      g.add(trail);
      const marker = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshBasicMaterial({ color: col }));
      g.add(marker);
      const ticks = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: col, size: 3, sizeAttenuation: false }));
      g.add(ticks);
      let arrow = null;
      if (r.role !== "target") { arrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 0.01, 0xd79818); g.add(arrow); }
      g.userData = { pts, trail, trailGeo, marker, ghost, arrow, ticks, col, run: r };
    });
    const bg = new THREE.Color();
    function applyTheme() { bg.set(css("--scene") || "#1b1b1a"); scene.background = bg; }
    applyTheme();
    function updateTime() {
      const i = idxAt(state.time);
      const tgt = groups.target.userData.pts;
      for (const name in groups) {
        const g = groups[name], d = g.userData; g.visible = shown(name);
        if (!g.visible) continue;
        const isT = d.run.role === "target";
        const end = isT ? Math.min(N - 1, idxAt(state.time + o.ahead)) : i;
        d.trailGeo.setDrawRange(0, end + 1);
        const c = d.trailGeo.attributes.color;
        for (let k = 0; k <= end; k++) {
          const age = T[i] - T[k];
          let w = isT ? (k > i ? 0.75 : Math.max(0.15, 1 - age / Math.max(0.1, o.decay))) : (o.comet ? Math.max(0, 1 - age / Math.max(0.1, o.decay)) : 1);
          const cc = d.col.clone().lerp(bg, 1 - w);
          c.setXYZ(k, cc.r, cc.g, cc.b);
        }
        c.needsUpdate = true;
        d.ghost.visible = o.ghost;
        const s = radius * 0.012 * (o.size / 11);
        d.marker.scale.setScalar(s); d.marker.position.copy(d.pts[i]);
        const every = Math.max(1, Math.round(N / Math.max(1, o.markers)));
        d.ticks.geometry.setFromPoints(d.pts.filter((_, k) => k % every === 0 && k <= end));
        if (d.arrow) {
          const v = tgt[i].clone().sub(d.pts[i]);
          const len = v.length() * (o.mag || 1);
          d.arrow.visible = o.arrows && len > 1e-5;
          if (d.arrow.visible) { d.arrow.position.copy(d.pts[i]); d.arrow.setDirection(v.normalize()); d.arrow.setLength(len, Math.min(len * 0.3, radius * 0.06), Math.min(len * 0.2, radius * 0.04)); }
        }
      }
      render();
    }
    function place() {
      const ce = Math.cos(view.el);
      camera.position.set(view.target.x + view.dist * ce * Math.cos(view.az), view.target.y + view.dist * ce * Math.sin(view.az), view.target.z + view.dist * Math.sin(view.el));
      camera.lookAt(view.target);
    }
    function render() { place(); renderer.render(scene, camera); }
    function resize() { const w = el.clientWidth, h = el.clientHeight; if (w < 10 || h < 10) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); if (!view.moved) view.dist = fitDist(); render(); }
    new ResizeObserver(resize).observe(el);
    let drag = null;
    const cv = renderer.domElement;
    cv.addEventListener("contextmenu", (e) => e.preventDefault());
    cv.addEventListener("pointerdown", (e) => { cv.setPointerCapture(e.pointerId); drag = { x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey }; });
    cv.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY; view.moved = true;
      if (drag.pan) {
        const k = view.dist * 0.0016; const right = new THREE.Vector3(); camera.getWorldDirection(right); right.cross(camera.up).normalize();
        view.target.addScaledVector(right, -dx * k); view.target.z += dy * k;
      } else { view.az -= dx * 0.008; view.el = Math.min(1.5, Math.max(-1.5, view.el + dy * 0.008)); }
      render();
    });
    cv.addEventListener("pointerup", () => (drag = null));
    cv.addEventListener("wheel", (e) => { e.preventDefault(); view.dist *= e.deltaY > 0 ? 1.1 : 0.9; view.moved = true; render(); }, { passive: false });
    cv.addEventListener("dblclick", () => { Object.assign(view, HOME); view.dist = fitDist(); view.moved = false; view.target.copy(center); render(); });
    on("time", updateTime); on("runs", updateTime);
    resize(); updateTime();
    const probe = () => Object.fromEntries(Object.entries(groups).map(([n, g]) => [n, { visible: g.visible, p: g.userData.marker.position.toArray() }]));
    viewers.push(probe);
    return { set(patch) { Object.assign(o, patch); updateTime(); }, get: () => ({ ...o }), render, resize, el, probe };
  }

  // ---------- the lane: ruler + run tracks ----------
  function canvasIn(el) {
    const c = document.createElement("canvas"); el.appendChild(c);
    const fit = () => { const r = el.getBoundingClientRect(); const d = window.devicePixelRatio || 1; c.width = Math.max(1, r.width * d); c.height = Math.max(1, r.height * d); };
    return { c, fit };
  }
  function xRange() { return state.zoom || [T[0], T[N - 1]]; }
  function scrubbable(el, toT) {
    let down = false;
    el.addEventListener("pointerdown", (e) => { el.setPointerCapture(e.pointerId); down = true; pause(); setTime(toT(e)); });
    el.addEventListener("pointermove", (e) => { if (down) setTime(toT(e)); });
    el.addEventListener("pointerup", () => (down = false));
  }
  function ruler(el, opts) {
    opts = opts || {};
    el.classList.add("kit-ruler");
    const { c, fit } = canvasIn(el);
    function draw() {
      fit(); const g = c.getContext("2d"); const d = window.devicePixelRatio || 1; const w = c.width / d, h = c.height / d;
      g.setTransform(d, 0, 0, d, 0, 0); g.clearRect(0, 0, w, h);
      const [a, b] = xRange(); const X = (t) => ((t - a) / (b - a)) * w;
      g.font = "10px " + css("--font"); g.fillStyle = css("--faint"); g.strokeStyle = css("--edge2");
      const stepS = (b - a) > 3 ? 0.5 : (b - a) > 1.2 ? 0.2 : 0.1;
      for (let t = Math.ceil(a / stepS) * stepS; t <= b + 1e-9; t += stepS) {
        const x = Math.round(X(t)) + 0.5; g.beginPath(); g.moveTo(x, h - 6); g.lineTo(x, h); g.stroke();
        if (x < w - 20) g.fillText(t.toFixed(1), x + 2, h - 8);
      }
      if (opts.events) for (const ev of opts.events()) { g.fillStyle = ev.color || css("--bad"); g.fillRect(X(ev.t) - 1, 0, 2, 5); }
      const wx = X(WORST_T); g.fillStyle = css("--bad"); g.beginPath(); g.moveTo(wx, h - 1); g.lineTo(wx - 4, h - 6); g.lineTo(wx, h - 11); g.lineTo(wx + 4, h - 6); g.fill();
      const x = X(state.time); g.fillStyle = css("--ph"); g.fillRect(x - 1, 0, 2, h);
    }
    scrubbable(el, (e) => { const r = el.getBoundingClientRect(); const [a, b] = xRange(); return a + ((e.clientX - r.left) / r.width) * (b - a); });
    new ResizeObserver(draw).observe(el); on("time", draw); on("zoom", draw); draw();
    return { draw };
  }
  function track(el, name, opts) {
    opts = opts || {};
    el.classList.add("kit-track");
    const { c, fit } = canvasIn(el);
    const run = byName[name]; const a0 = errMax[name]; const gmax = Math.max(...measuredRuns.map((r) => worst[r.name].v)) || 1;
    function draw() {
      fit(); const g = c.getContext("2d"); const d = window.devicePixelRatio || 1; const w = c.width / d, h = c.height / d;
      g.setTransform(d, 0, 0, d, 0, 0); g.clearRect(0, 0, w, h);
      const [a, b] = xRange(); const X = (t) => ((t - a) / (b - a)) * w;
      g.globalAlpha = shown(name) ? 1 : 0.3;
      if (!a0) { g.strokeStyle = run.color; g.setLineDash([5, 4]); g.beginPath(); g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke(); g.setLineDash([]);
        g.fillStyle = css("--faint"); g.font = "10px " + css("--font"); g.fillText(opts.refText || "the reference: every error is Target − run", 6, h / 2 - 3); }
      else {
        g.beginPath(); g.moveTo(X(T[0]), h);
        for (let i = 0; i < N; i++) g.lineTo(X(T[i]), h - 2 - (a0[i] / gmax) * (h - 5));
        g.lineTo(X(T[N - 1]), h); g.closePath(); g.fillStyle = run.color + "55"; g.fill(); g.strokeStyle = run.color; g.lineWidth = 1.2; g.stroke();
        const W = worst[name];
        if (W.v > 1e-9) {
          const wx = X(W.t), wy = h - 2 - (W.v / gmax) * (h - 5);
          g.fillStyle = run.color; g.beginPath(); g.moveTo(wx, wy - 5); g.lineTo(wx + 5, wy); g.lineTo(wx, wy + 5); g.lineTo(wx - 5, wy); g.fill();
          if (W.rise != null) { const rx = X(W.rise); g.beginPath(); g.moveTo(rx, h - 1); g.lineTo(rx - 4, h - 8); g.lineTo(rx + 4, h - 8); g.fill(); }
        }
      }
      g.globalAlpha = 1;
      const x = X(state.time); g.fillStyle = css("--ph"); g.fillRect(x - 0.75, 0, 1.5, h);
    }
    scrubbable(el, (e) => { const r = el.getBoundingClientRect(); const [a, b] = xRange(); return a + ((e.clientX - r.left) / r.width) * (b - a); });
    new ResizeObserver(draw).observe(el); on("time", draw); on("zoom", draw); on("runs", draw); on("units", draw); draw();
    return { draw };
  }

  // ---------- splitters (size remembered) ----------
  function splitter(handle, target, o) {
    // o: {axis: 'x'|'y', key, min, max, invert (drag left grows), prop: 'width'|'height', def}
    const prop = o.prop || (o.axis === "x" ? "width" : "height");
    const saved = store.get("split:" + o.key, o.def);
    if (saved != null) target.style[prop] = saved + "px";
    let start = null;
    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault(); handle.setPointerCapture(e.pointerId); handle.classList.add("drag");
      start = { p: o.axis === "x" ? e.clientX : e.clientY, size: target.getBoundingClientRect()[prop] };
    });
    handle.addEventListener("pointermove", (e) => {
      if (!start) return;
      const dp = (o.axis === "x" ? e.clientX : e.clientY) - start.p;
      const v = Math.min(o.max || 4000, Math.max(o.min || 80, start.size + (o.invert ? -dp : dp)));
      target.style[prop] = v + "px";
    });
    handle.addEventListener("pointerup", () => {
      if (!start) return; start = null; handle.classList.remove("drag");
      store.set("split:" + o.key, Math.round(target.getBoundingClientRect()[prop]));
    });
    handle.addEventListener("dblclick", () => { target.style[prop] = o.def + "px"; store.set("split:" + o.key, o.def); });
  }

  // ---------- Open in Rerun (simulated) ----------
  function rerun(where) {
    const cmd = `traj-compare rerun --report ${F.source.replace("/home/bam/", "~/")} --page "${F.page}" --time ${state.time.toFixed(2)} --tab ${where || "track"}`;
    toast(`<b>Open in Rerun</b> <span class="sim">simulated in this prototype</span><br>The report would write this page's recording at t = ${fmtT(state.time)} and start the stock viewer:<code>${cmd}</code>`);
  }
  let toastEl = null, toastTimer = 0;
  function toast(html) {
    if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "kit-toast"; document.body.appendChild(toastEl); }
    toastEl.innerHTML = html; toastEl.style.display = "";
    clearTimeout(toastTimer); toastTimer = setTimeout(() => (toastEl.style.display = "none"), 4500);
  }

  // ---------- small DOM helper ----------
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) {
      const v = attrs[k];
      if (k === "class") e.className = v; else if (k === "html") e.innerHTML = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v === true) e.setAttribute(k, ""); else if (v !== false && v != null) e.setAttribute(k, v);
    }
    kids.flat(2).forEach((c) => c != null && c !== false && e.appendChild(c instanceof Node ? c : document.createTextNode(String(c))));
    return e;
  }
  function eye(name) {
    const b = h("button", { class: "eye", title: "show / hide " + byName[name].title, "data-eye": name, onclick: (e) => { e.stopPropagation(); toggleRun(name); } });
    const sync = () => b.classList.toggle("off", !shown(name)); on("runs", sync); sync(); return b;
  }
  function unitsSeg() {
    const s = h("div", { class: "seg", title: "angles" });
    ["deg", "rad"].forEach((u) => s.appendChild(h("button", { "data-units": u, onclick: () => setUnits(u) }, u)));
    const sync = () => s.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.units === state.units));
    on("units", sync); sync(); return s;
  }
  function statsTable() {
    const s = F.statistics; const keep = [0, 1, 2, 3, 5, 7];
    return h("table", { class: "stats" }, h("thead", {}, h("tr", {}, keep.map((k) => h("th", {}, s.columns[k])))),
      h("tbody", {}, s.rows.map((r) => h("tr", {}, keep.map((k, i) => h(i ? "td" : "th", { class: i ? "mono" : "" }, r.cells[k]))))));
  }
  function swatch(run) { const s = h("span", { class: "swatch" + (run.role === "target" ? " dash" : "") }); s.style.background = run.color; s.style.color = run.color; return s; }

  function pageSelect() {
    const s = h("select", { class: "pagesel", title: "scenario" });
    F.pages.forEach((p, i) => s.appendChild(h("option", { value: p, disabled: i > 0 }, i ? p + " (not in this prototype)" : p)));
    return s;
  }
  const VIEW_SLIDERS = [
    ["decay", "Trail fades over", 0.5, 10, 0.5, (v) => v + " s"], ["ahead", "Target look-ahead", 0, 4, 0.25, (v) => v + " s"],
    ["mag", "Error arrow magnification", 1, 10, 1, (v) => "×" + v], ["markers", "Marker density", 0, 60, 5, (v) => String(v)],
    ["size", "Marker size", 4, 24, 1, (v) => v + " mm"]];
  const VIEW_CHECKS = [["arrows", "Position error arrows"], ["ghost", "Whole path, faint"], ["comet", "Fade the trail (comet)"]];
  function sliderRow(v3, def, onChange) {
    const [k, label, lo, hi, st, f] = def;
    const val = h("span", {}, f(v3.get()[k]));
    const inp = h("input", { type: "range", min: lo, max: hi, step: st, value: v3.get()[k], "data-slider": k,
      oninput: (e) => { v3.set({ [k]: +e.target.value }); val.textContent = f(+e.target.value); if (onChange) onChange(); } });
    return h("label", { class: "slider-row" }, h("span", {}, label), val, inp);
  }
  function checkRow(v3, def, onChange) {
    const [k, label] = def;
    const cb = h("input", { type: "checkbox", "data-check": k, onchange: (e) => { v3.set({ [k]: e.target.checked }); if (onChange) onChange(); } }); cb.checked = v3.get()[k];
    return h("label", { class: "check" }, cb, " ", label);
  }
  const TABS = F.tabs.map((t) => ({ id: t.id, title: t.title, heading: t.heading, subtabs: t.subtabs }));
  window.Kit = { F, T, N, RUNS, byName, JOINTS, TABS, state, on, emit, setTime, idxAt, shown, toggleRun, soloRun, setUnits, setZoom,
    play, pause, togglePlay, step, worst, worstRun, WORST_T, errMax, angle, angleUnit, fmt, fmtT, channels, chByName, FAMILIES,
    chEventSpans, chNear, chUnit, chValue, tabCharts, answer, chart, dropCharts, charts, runErrAt, specValueAt, viewer3d, ruler, track,
    splitter, rerun, toast, h, eye, viewers, pageSelect, VIEW_SLIDERS, VIEW_CHECKS, sliderRow, checkRow, unitsSeg, statsTable, swatch, store, measuredRuns, maxAbs };
})();
