/* V3 Question tabs — the run view as the four questions you bring to it (the same questions as Rerun's
 * "questions" layout): Is it good? · Where does the torque come from? · When did it go wrong? · Which joint?
 * Each tab is one composed screen; the run list, time cursor and zoom carry across tabs. */
(function () {
  'use strict';
  var el = RV.el;
  var state = RV.makeState('v3');
  var tr = RV.makeTransport(state);
  var tab = RV.recall('v3:tab', 'good');
  var heatJoint = 'max';

  var app = document.getElementById('app');
  var head = el('header', 'rv-head', app);
  var titles = el('div', '', head);
  var h1 = el('h1', '', titles);
  var sub = el('div', 'rv-sub', titles);
  el('span', 'rv-spacer', head);
  RV.badge(head);
  var nav = el('nav', 'tc-tabs v3-tabs', app);
  var TABS = [
    { id: 'good', q: 'Is it good?' },
    { id: 'torque', q: 'Where does the torque come from?' },
    { id: 'when', q: 'When did it go wrong?' },
    { id: 'joint', q: 'Which joint?' },
  ];
  TABS.forEach(function (t) {
    var b = el('button', 'v3-tab', nav);
    b.dataset.tab = t.id;
    el('span', 'v3-q', b, t.q);
    t.ans = el('span', 'v3-a', b);
    b.onclick = function () { setTab(t.id); };
  });
  var body = el('div', 'rv-body', app);
  var side = el('aside', 'rv-side', body);
  var list = RV.runList(side, state, {
    metric: { label: 'L2-tip RMS', value: function (r) { return r.tip.rms; }, text: function (v) { return RV.fmt(v, 1) + ' mm'; } },
  });
  var main = el('main', 'rv-main v3-main', body);
  RV.sidePanel(side, 'v3-side', { label: 'Runs', width: 280, foldButton: list.fold, onChange: resize });
  var screen = el('div', 'v3-screen', main);
  var foot = el('div', 'v3-foot', main);
  var worstBtn = el('button', 'rv-worst', null, '⚠ Worst moment'); worstBtn.id = 'worst';
  worstBtn.onclick = jumpWorst;
  var resetZoom = el('button', 'tc-tbtn', null, 'Reset zoom'); resetZoom.style.padding = '0 8px';
  resetZoom.onclick = function () { tr.setZoom(null); };
  RV.transportBar(tr, foot, [worstBtn, resetZoom]);

  function jumpWorst() {
    var w = RV.worstMoments(state, 1)[0];
    if (!w) return;
    state.setFocus(w.run.name);
    tr.focusOn(w.t, 0.7);
  }
  function setTab(id) { tab = id; RV.store('v3:tab', tab); render(); }

  var charts = [], viewer = null, heat = null;
  function clear() {
    charts.forEach(function (c) { c.destroy(); }); charts = [];
    if (viewer) { viewer.destroy(); viewer = null; }
    heat = null;
    screen.innerHTML = '';
  }
  function card(parent, title, unit, right, cls) {
    var c = el('div', 'rv-card ' + (cls || ''), parent);
    var t = el('div', 'ptitle', c);
    el('b', '', t, title);
    if (unit) el('span', 'unit', t, '[' + unit + ']');
    if (right) el('span', 'right', t, right);
    return c;
  }
  function addChart(parent, height, content, extra) {
    var o = Object.assign({ height: height, syncKey: 'v3', content: content }, extra || {});
    var c = RV.chart(parent, o, tr); charts.push(c); return c;
  }

  /* ---------- Is it good? ---------- */
  function good() {
    var v = RV.verdict(state, 0), ve = RV.verdict(state, 1);
    var top = el('div', 'v3-verdict', screen);
    var line = el('div', 'v3-vline', top);
    if (v.v1 && v.v2) {
      var gain = 1 - v.err2 / v.err1;
      el('b', '', line, gain > 0 ? 'Yes with ff v2 calibrated: ' + Math.round(100 * gain) + '% less shoulder error than ff v1.' : 'ff v1 nominal tracks better here.');
      el('span', '', line, ' The real arm still trails the sim (' + RV.deg(state.runs().filter(function (r) { return r.kind === 'sim'; }).map(function (r) { return r.m[0].errRms; })[0] || 0, 3) + ' RMS).');
    } else {
      var g = state.groups().filter(function (x) { return x.key !== 'sim'; })[0];
      el('b', '', line, g ? 'Only ' + g.label + ' was run here: ' + RV.deg(RV.median(g.runs.map(function (r) { return r.m[0].errRms; }))) + ' median shoulder error.' : 'Nothing visible.');
    }
    var tiles = el('div', 'v3-tiles', top);
    function tile(label, value, detail, link, tone) {
      var t = el('div', 'tc-metriccard v3-tile ' + (tone || 'tone-neutral'), tiles);
      el('div', 'label', t, label);
      el('div', 'value', t, value);
      el('div', 'detail', t, detail);
      if (link) { var a = el('button', 'v3-link', t, link[0] + ' →'); a.onclick = function () { setTab(link[1]); }; }
    }
    if (v.v1 && v.v2) {
      tile('Shoulder error · RMS, median run', RV.deg(v.err1) + ' → ' + RV.deg(v.err2), 'ff v1 ×' + v.v1.runs.length + ' → ff v2 ×' + v.v2.runs.length + ' · elbow ' + RV.deg(ve.err1) + ' → ' + RV.deg(ve.err2), ['When did it go wrong?', 'when'], 'tone-action');
      tile('Feedback share of the command', RV.pct(v.share1) + ' → ' + RV.pct(v.share2), 'v1 under-models gravity; feedback makes up the rest', ['Where does the torque come from?', 'torque'], 'tone-action');
    } else {
      var only = v.v1 || v.v2;
      tile('Shoulder error · RMS, median run', RV.deg(v.err1 || v.err2), (only ? only.label + ' ×' + only.runs.length : ''), ['When did it go wrong?', 'when'], 'tone-action');
      tile('Feedback share of the command', RV.pct(v.share1 != null ? v.share1 : v.share2), 'Σ|fb| / (Σ|ff| + Σ|fb|)', ['Where does the torque come from?', 'torque'], 'tone-action');
    }
    tile('Drive & limits', v.sat > 0 ? RV.pct(v.sat, 1) + ' saturated' : 'within limits', 'drive gap ' + RV.nm(RV.median(state.visibleRuns().map(function (r) { return r.m[0].driveGapRms; })), 3) + ' RMS (cmd − applied)', ['Which joint?', 'joint'], v.sat > 0 ? 'tone-warning' : 'tone-neutral');
    // one dot per run: its RMS error, per joint and config
    var strip = el('div', 'v3-dots', screen);
    var sh = el('div', 'v3-dots-h', strip);
    el('b', '', sh, 'Every run');
    el('span', 'muted', sh, ' — RMS error per run, one dot each (click to highlight); bar = median');
    var real = state.visibleRuns();
    RV.F.joints.forEach(function (joint, j) {
      var lanes = el('div', 'v3-lanes', strip);
      el('div', 'v3-lanes-j', lanes, joint);
      var max = Math.max(0.5, Math.max.apply(null, real.map(function (r) { return r.m[j].errRms; })) * 1.08);
      var box = el('div', 'v3-lanes-box', lanes);
      state.groups().forEach(function (g) {
        var lane = el('div', 'v3-lane', box);
        el('span', 'v3-lane-l', lane, g.short + ' ×' + g.runs.length);
        var tk = el('span', 'v3-lane-t', lane);
        g.runs.forEach(function (r) {
          var d = el('i', 'v3-dot' + (r === state.focusRun() ? ' me' : ''), tk);
          d.style.left = (100 * r.m[j].errRms / max) + '%'; d.style.background = r.color;
          d.title = r.title + ': ' + RV.deg(r.m[j].errRms, 3) + ' RMS, max ' + RV.deg(r.m[j].errMax);
          d.onclick = function () { state.setFocus(r.name); };
        });
        if (g.runs.length > 1) { var m = el('i', 'v3-med', tk); m.style.left = (100 * RV.median(g.runs.map(function (r) { return r.m[j].errRms; })) / max) + '%'; m.style.background = g.color; }
      });
      var sc = el('div', 'v3-scale muted', box);
      el('span', '', sc, '0°'); el('span', '', sc, RV.deg(max / 2, 2)); el('span', '', sc, RV.deg(max, 2));
    });
    var grid = el('div', 'v3-grid2', screen);
    var f = state.focusRun();
    RV.F.joints.forEach(function (joint, j) {
      var c = card(grid, joint + ' error over time', '°', bandNote());
      addChart(c, 225, function () { var x = RV.repeatContent(state, 'err', j, { zeroLine: true }); x.markers = [{ t: f.m[j].errMaxT }]; return x; });
    });
  }
  function bandNote() {
    return state.groups().filter(function (g) { return state.asBand(g.runs.length); }).length ? 'median · IQR · p5–p95 · min–max per config' : 'one line per run';
  }

  /* ---------- Where does the torque come from? ---------- */
  function torque() {
    var f = state.focusRun(), T = state.T();
    var intro = el('div', 'v3-intro', screen);
    intro.innerHTML = '';
    el('b', '', intro, 'Commanded = feedforward (the model) + feedback (the correction).');
    el('span', 'muted', intro, ' Left: how much of the command feedback supplies over the motion, every visible run. Right: ' + f.title + ' in full.');
    var grid = el('div', 'v3-tq', screen);
    RV.F.joints.forEach(function (joint, j) {
      var c1 = card(grid, joint + ' — FB share of the command, ±150 ms', '%', bandNote());
      addChart(c1, 170, function () {
        var x = RV.repeatContent(state, 'share', j, {});
        x.y = { min: 0, max: Math.max(40, Math.min(100, Math.ceil(Math.max.apply(null, RV.fbShareSeries(f, j)) / 10) * 10 + 10)) };
        return x;
      });
      var c2 = card(grid, joint + ' — ' + f.title, 'N·m', 'FB share ' + RV.pct(f.m[j].fbShare));
      addChart(c2, 170, function () { return RV.breakdownLines(f, j, null, T); });
    });
    var leg = el('div', 'v3-tq-legend', screen);
    RV.componentLegend(leg, { target: true, cmd: true, ff: true, fb: true, applied: true }, function () {}, f).classList.add('static');
    // per-run budget: 100% bars FF | FB
    var bud = el('div', 'v3-budget', screen);
    var bh = el('div', 'v3-budget-h', bud);
    el('b', '', bh, 'Torque budget per run');
    el('span', 'muted', bh, ' — share of Σ|command| from feedforward vs feedback (shoulder | elbow); drive gap = RMS(commanded − applied)');
    var rows = el('div', 'v3-budget-rows', bud);
    state.visibleRuns().forEach(function (r) {
      var row = el('div', 'v3-brow' + (r === f ? ' me' : ''), rows);
      row.onclick = function () { state.setFocus(r.name); };
      var nm = el('span', 'v3-bname', row); el('i', 'rv-swatch', nm).style.background = r.color; nm.appendChild(document.createTextNode(r.title));
      [0, 1].forEach(function (j) {
        var bar = el('span', 'v3-bbar', row);
        var a = el('i', 'ff', bar); a.style.width = (100 * (1 - r.m[j].fbShare)) + '%';
        var b = el('i', 'fb', bar); b.style.width = (100 * r.m[j].fbShare) + '%';
        el('span', 'v3-bval num', row, RV.pct(r.m[j].fbShare));
      });
      el('span', 'v3-bgap num muted', row, RV.nm(r.m[0].driveGapRms, 3));
    });
  }

  /* ---------- When did it go wrong? ---------- */
  function when() {
    var wrap = el('div', 'v3-when', screen);
    var left = el('div', 'v3-when-l', wrap);
    var right = el('div', 'v3-when-r', wrap);
    var w = RV.worstMoments(state, 3);
    var hh = el('div', 'v3-heat-h', left);
    el('b', '', hh, '|error| per run over time');
    var jsel = el('div', 'rv-seg', hh);
    [['max', 'worst joint'], ['0', 'shoulder'], ['1', 'elbow']].forEach(function (o) {
      var b = el('button', heatJoint === o[0] ? 'on' : '', jsel, o[1]);
      b.onclick = function () { heatJoint = o[0]; render(); };
    });
    el('span', 'muted', hh, 'click a cell to pin that run and time');
    var heatBox = el('div', 'v3-heat', left);
    heat = heatmap(heatBox);
    var cards = el('div', 'v3-worstlist', right);
    el('div', 'v3-wl-h', cards, 'Worst moments');
    w.forEach(function (m, k) {
      var b = el('button', 'v3-wm', cards);
      b.dataset.rank = k;
      el('b', 'num', b, m.t.toFixed(2) + ' s');
      el('span', '', b, m.run.title + ' · ' + RV.F.joints[m.j] + ' ' + RV.deg(m.value));
      b.onclick = function () { state.setFocus(m.run.name); tr.focusOn(m.t, 0.7); };
    });
    var stage = el('div', 'v3-when-3d', right);
    viewer = RV.arm3d(stage, state, tr, { height: 250, exaggerate: 6, dist: 2.1, onPose: function (i, hud) {
      var f = state.focusRun(), T = state.T();
      hud.textContent = 't ' + T.t[i].toFixed(2) + ' s · ' + f.title + ' · error ' + RV.deg(f.err[0][i]) + ' / ' + RV.deg(f.err[1][i]);
    } });
    var j = heatJoint === '1' ? 1 : 0, f = state.focusRun();
    var c = card(left, RV.F.joints[j] + ' error — ' + f.title + ' against the band', '°', bandNote());
    addChart(c, 150, function () { var x = RV.repeatContent(state, 'err', j, { zeroLine: true }); x.markers = w.map(function (m) { return { t: m.t }; }); return x; });
  }
  // a run × time heat strip; the time axis follows the page zoom, the blue line the committed time
  function heatmap(box) {
    var canvas = el('canvas', '', box);
    var tip = el('div', 'v3-heat-tip', box);
    var runs = state.visibleRuns(), T = state.T();
    var rowH = Math.max(12, Math.min(22, Math.floor(300 / Math.max(1, runs.length))));
    var labelW = 132, H = runs.length * rowH + 22;
    var vals = runs.map(function (r) { return heatJoint === 'max' ? RV.absErr(r) : r.err[+heatJoint].map(Math.abs); });
    var vmax = Math.max(0.5, Math.max.apply(null, vals.map(function (v) { return Math.max.apply(null, v); })));
    function color(v) {  // white → slate violet; amber reserved for the worst-moment markers
      var t = Math.min(1, v / vmax);
      var a = [252, 252, 251], b = [62, 48, 112];
      return 'rgb(' + a.map(function (x, k) { return Math.round(x + (b[k] - x) * Math.pow(t, 0.8)); }).join(',') + ')';
    }
    function draw() {
      var W = box.clientWidth; if (!W) return;
      var dpr = window.devicePixelRatio || 1;
      canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
      var ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      var x0 = tr.zoom ? tr.zoom.min : 0, x1 = tr.zoom ? tr.zoom.max : T.duration, pw = W - labelW - 8;
      var X = function (t) { return labelW + (t - x0) / (x1 - x0) * pw; };
      var f = state.focusRun();
      runs.forEach(function (r, k) {
        var y = k * rowH;
        ctx.fillStyle = r === f ? '#eef3fa' : '#fcfcfb'; ctx.fillRect(0, y, labelW, rowH);
        ctx.fillStyle = r.color; ctx.fillRect(4, y + rowH / 2 - 1.5, 12, 3);
        ctx.fillStyle = '#22211f'; ctx.font = (r === f ? '600 ' : '') + '11px -apple-system, Segoe UI, Roboto, sans-serif'; ctx.textBaseline = 'middle';
        ctx.fillText(r.title, 20, y + rowH / 2);
        var v = vals[k];
        for (var i = 0; i < T.t.length - 1; i++) {
          if (T.t[i + 1] < x0 || T.t[i] > x1) continue;
          ctx.fillStyle = color(v[i]);
          var xa = Math.max(labelW, X(T.t[i])), xb = Math.min(labelW + pw, X(T.t[i + 1]) + 0.6);
          ctx.fillRect(xa, y + 1, xb - xa, rowH - 2);
        }
      });
      ctx.fillStyle = '#8a8983'; ctx.font = '10px -apple-system, Segoe UI, Roboto, sans-serif'; ctx.textBaseline = 'top';
      var step = (x1 - x0) > 3 ? 1 : (x1 - x0) > 1 ? 0.25 : 0.1;
      for (var tt = Math.ceil(x0 / step) * step; tt <= x1 + 1e-9; tt += step) { var xx = X(tt); ctx.fillText(tt.toFixed(step < 1 ? 2 : 0), xx - 6, runs.length * rowH + 6); ctx.fillRect(xx, runs.length * rowH, 1, 4); }
      RV.worstMoments(state, 3).forEach(function (m) {
        var k = runs.indexOf(m.run); if (k < 0) return;
        var xm = X(m.t); ctx.strokeStyle = RV.AMBER; ctx.lineWidth = 2; ctx.strokeRect(xm - 4, k * rowH + 1, 8, rowH - 2);
      });
      if (tr.t !== null) { var xt = X(tr.t); ctx.fillStyle = '#2a78d6'; ctx.fillRect(xt - 0.75, 0, 1.5, runs.length * rowH); }
    }
    function at(e) {
      var rect = canvas.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top;
      var k = Math.floor(y / rowH); if (x < labelW || k < 0 || k >= runs.length) return null;
      var x0 = tr.zoom ? tr.zoom.min : 0, x1 = tr.zoom ? tr.zoom.max : T.duration;
      var t = x0 + (x - labelW) / (box.clientWidth - labelW - 8) * (x1 - x0);
      return { run: runs[k], k: k, t: t, i: RV.nearestIndex(T.t, t), x: x, y: y };
    }
    canvas.addEventListener('mousemove', function (e) {
      var h = at(e); if (!h) { tip.style.display = 'none'; tr.setHover(null); return; }
      tip.style.display = 'block'; tip.style.left = Math.min(h.x + 12, box.clientWidth - 220) + 'px'; tip.style.top = (h.y + 12) + 'px';
      tip.textContent = h.run.title + ' · ' + T.t[h.i].toFixed(2) + ' s · |error| ' + RV.deg(vals[h.k][h.i]);
      tr.setHover(T.t[h.i]);
    });
    canvas.addEventListener('mouseleave', function () { tip.style.display = 'none'; tr.setHover(null); });
    canvas.addEventListener('click', function (e) { var h = at(e); if (!h) return; state.setFocus(h.run.name); tr.pause(); tr.setScrub(T.t[h.i]); });
    draw();
    return { draw: draw };
  }

  /* ---------- Which joint? ---------- */
  function joint() {
    var tbl = el('table', 'tc-metrics v3-jtable', el('div', 'tc-tableblock compact', screen));
    var hr = el('tr', '', el('thead', '', tbl));
    var groups = state.groups().filter(function (g) { return g.key !== 'sim'; });
    ['Joint'].concat(groups.map(function (g) { return 'RMS error · ' + g.short; }), groups.map(function (g) { return 'FB share · ' + g.short; }), ['worst |error|', 'peak |cmd| / limit', 'drive gap']).forEach(function (h) { el('th', '', hr, h); });
    var tb = el('tbody', '', tbl);
    var real = state.visibleRuns().filter(function (r) { return r.kind === 'real'; });
    RV.F.joints.forEach(function (joint, j) {
      var row = el('tr', '', tb);
      el('th', '', row, joint);
      groups.forEach(function (g) { el('td', '', row, RV.deg(RV.median(g.runs.map(function (r) { return r.m[j].errRms; })))); });
      groups.forEach(function (g) { el('td', '', row, RV.pct(RV.median(g.runs.map(function (r) { return r.m[j].fbShare; })))); });
      el('td', '', row, RV.deg(Math.max.apply(null, real.map(function (r) { return r.m[j].errMax; }).concat([0]))));
      var peak = Math.max.apply(null, real.map(function (r) { return r.m[j].cmdPeak; }).concat([0])), lim = RV.F.maxTorque[j];
      var td = el('td', peak / lim >= 0.9 ? 'v3-warn' : '', row, RV.nm(peak) + ' / ' + lim + ' (' + RV.pct(peak / lim) + ')');
      el('td', '', row, RV.nm(RV.median(real.map(function (r) { return r.m[j].driveGapRms; })), 3));
    });
    var grid = el('div', 'v3-grid2', screen);
    RV.F.joints.forEach(function (joint, j) {
      var c = card(grid, joint + ' error', '°', bandNote());
      addChart(c, 140, function () { return RV.repeatContent(state, 'err', j, { zeroLine: true }); });
    });
    RV.F.joints.forEach(function (joint, j) {
      var c = card(grid, joint + ' commanded torque vs limit', 'N·m', '±' + RV.F.maxTorque[j] + ' N·m');
      addChart(c, 140, function () {
        var x = RV.repeatContent(state, 'cmd', j, { target: state.T().tau[j] });
        var lim = RV.F.maxTorque[j];
        x.lines.push({ values: state.T().t.map(function () { return lim; }), stroke: RV.rgba(RV.AMBER, 0.8), width: 1, dash: [2, 3] });
        x.lines.push({ values: state.T().t.map(function () { return -lim; }), stroke: RV.rgba(RV.AMBER, 0.8), width: 1, dash: [2, 3] });
        return x;
      });
    });
  }

  function answers() {
    var v = RV.verdict(state, 0);
    var w = RV.worstMoments(state, 1)[0];
    TABS[0].ans.textContent = v.v1 && v.v2 ? (v.err2 < v.err1 ? 'v2 −' + Math.round(100 * (1 - v.err2 / v.err1)) + '% error' : 'v1 better') : RV.deg(v.err1 || v.err2) + ' RMS';
    TABS[1].ans.textContent = 'FB ' + (v.v1 && v.v2 ? RV.pct(v.share1) + ' → ' + RV.pct(v.share2) : RV.pct(v.share1 != null ? v.share1 : v.share2));
    TABS[2].ans.textContent = w ? w.t.toFixed(2) + ' s · ' + w.run.title.split(' · ')[0] : '';
    var real = state.visibleRuns().filter(function (r) { return r.kind === 'real'; });
    var sh = RV.median(real.map(function (r) { return r.m[0].errRms; })), elb = RV.median(real.map(function (r) { return r.m[1].errRms; }));
    TABS[3].ans.textContent = (sh >= elb ? 'shoulder ' : 'elbow ') + RV.deg(Math.max(sh, elb));
  }
  function render() {
    clear();
    var T = state.T();
    h1.textContent = T.title; sub.textContent = T.description;
    nav.querySelectorAll('button').forEach(function (b) { b.classList.toggle('active', b.dataset.tab === tab); });
    answers();
    ({ good: good, torque: torque, when: when, joint: joint })[tab]();
  }
  function resize() { tr.charts.forEach(function (c) { c.resize(); }); if (heat) heat.draw(); }
  tr.on(function (kind) { if (heat && (kind === 'scrub' || kind === 'zoom')) heat.draw(); });
  state.on(function (why) { if (why === 'target') tr.reset(); render(); });
  render();
  RV.onResize(resize);
  window.RVPAGE = { state: state, tr: tr, setTab: setTab };
})();
