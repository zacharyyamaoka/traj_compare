/* V4 Joint × signal grid — a spreadsheet of small multiples.
 * Rows are joints, columns are signals (error, commanded, feedforward, feedback, FB share, …); every cell carries
 * the repeat band of each config with the highlighted run on top. Torque columns share one y scale per row, so the
 * feedforward and feedback cells compare by size at a glance. Click ⤢ (or double-click a cell) to expand it. */
(function () {
  'use strict';
  var el = RV.el;
  var state = RV.makeState('v4');
  var tr = RV.makeTransport(state);
  var COLS = [
    { id: 'err', label: 'Error', unit: '°', def: 'target − run', key: 'err', zero: true },
    { id: 'cmd', label: 'Commanded τ', unit: 'N·m', def: 'to the FOC current loop', key: 'cmd', torque: true, target: true },
    { id: 'ff', label: 'Feedforward τ', unit: 'N·m', def: 'model part of the command', key: 'ff', torque: true, target: true, color: RV.COMP.ff },
    { id: 'fb', label: 'Feedback τ', unit: 'N·m', def: 'kp·e + kd·ė + ki∫e', key: 'fb', torque: true, zero: true, color: RV.COMP.fb },
    { id: 'share', label: 'FB share', unit: '%', def: 'Σ|fb| / Σ(|ff| + |fb|), ±150 ms', key: 'share' },
    { id: 'gap', label: 'Drive gap', unit: 'N·m', def: 'commanded − applied', key: 'gap', torque: true, zero: true },
    { id: 'applied', label: 'Applied τ', unit: 'N·m', def: 'measured at the joint', key: 'applied', torque: true, target: true },
    { id: 'q', label: 'Joint q', unit: '°', def: 'angle, target dashed', key: 'q' },
  ];
  var on = RV.recall('v4:cols', { err: true, cmd: true, ff: true, fb: true, share: true });
  var sharedY = RV.recall('v4:sharedY', true);
  var expanded = null;  // {j, col}

  var app = document.getElementById('app');
  var head = el('header', 'rv-head', app);
  var titles = el('div', '', head);
  var h1 = el('h1', '', titles); var sub = el('div', 'rv-sub', titles);
  el('span', 'rv-spacer', head);
  var colBox = el('div', 'v4-colpick', head);
  el('span', 'rv-field-label', colBox, 'Columns');
  var colChips = el('div', 'v4-colchips', colBox);
  var yBox = el('label', 'v4-ytoggle', head);
  var yCb = el('input', '', yBox); yCb.type = 'checkbox'; yCb.checked = sharedY;
  yBox.appendChild(document.createTextNode(' one torque scale per row'));
  yCb.onchange = function () { sharedY = yCb.checked; RV.store('v4:sharedY', sharedY); rebuild(); };
  RV.badge(head);

  var body = el('div', 'rv-body', app);
  var side = el('aside', 'rv-side', body);
  var list = RV.runList(side, state, {
    metric: { label: 'max |error|', value: function (r) { return Math.max(r.m[0].errMax, r.m[1].errMax); }, text: function (v) { return RV.deg(v, 2); } },
  });
  var main = el('main', 'rv-main v4-main', body);
  RV.sidePanel(side, 'v4-side', { label: 'Runs', width: 260, foldButton: list.fold, onChange: resize });
  var gridHost = el('div', 'v4-gridhost', main);
  var grid = el('div', 'v4-grid', gridHost);
  var overlay = el('div', 'v4-overlay', gridHost);
  var foot = el('div', 'v4-foot', main);
  var worst = el('button', 'rv-worst', null, '⚠ Worst moment'); worst.id = 'worst';
  worst.onclick = function () { var w = RV.worstMoments(state, 1)[0]; if (w) { state.setFocus(w.run.name); tr.focusOn(w.t, 0.7); } };
  var resetZoom = el('button', 'tc-tbtn', null, 'Reset zoom'); resetZoom.style.padding = '0 8px';
  resetZoom.onclick = function () { tr.setZoom(null); };
  RV.transportBar(tr, foot, [worst, resetZoom]);

  COLS.forEach(function (c) {
    var b = el('button', 'chip', colChips, c.label);
    b.dataset.col = c.id;
    b.onclick = function () {
      on[c.id] = !on[c.id];
      if (!COLS.some(function (x) { return on[x.id]; })) on[c.id] = true;
      RV.store('v4:cols', on); rebuild();
    };
  });

  var charts = [], viewer = null;
  function activeCols() { return COLS.filter(function (c) { return on[c.id]; }); }
  function rowTorqueRange(j) {
    var lo = 0, hi = 0, runs = state.visibleRuns(), T = state.T();
    activeCols().filter(function (c) { return c.torque; }).forEach(function (c) {
      runs.forEach(function (r) { RV.series(r, c.key, j).forEach(function (v) { if (v < lo) lo = v; if (v > hi) hi = v; }); });
      if (c.target) T.tau[j].forEach(function (v) { if (v < lo) lo = v; if (v > hi) hi = v; });
    });
    var pad = 0.06 * (hi - lo || 1);
    return { min: lo - pad, max: hi + pad };
  }
  function cellContent(col, j, local) {
    var T = state.T();
    return function () {
      var x;
      if (col.key === 'q') x = RV.repeatContent(state, 'q', j, { target: T.q[j] });
      else x = RV.repeatContent(state, col.key, j, { target: col.target ? T.tau[j] : null, zeroLine: col.zero || col.torque });
      // WHY local in the expanded view: the shared row scale is for comparing cells; one big cell reads best on its own
      if (col.torque && sharedY && !local) x.y = rowTorqueRange(j);
      if (col.key === 'share') x.y = { min: 0, max: 60 };
      if (col.id === 'err') { var f = state.focusRun(); x.markers = [{ t: f.m[j].errMaxT }]; }
      return x;
    };
  }
  function summary(col, j) {
    var gs = state.groups().filter(function (g) { return g.key !== 'sim'; });
    var fn = {
      err: function (r) { return r.m[j].errRms; }, cmd: function (r) { return r.m[j].cmdRms; }, ff: function (r) { return r.m[j].ffRms; },
      fb: function (r) { return r.m[j].fbRms; }, share: function (r) { return r.m[j].fbShare; }, gap: function (r) { return r.m[j].driveGapRms; },
      applied: function (r) { return r.m[j].appliedRms; }, q: function (r) { return r.m[j].errRms; },
    }[col.id];
    var text = function (v) { return col.id === 'share' ? RV.pct(v) : col.unit === '°' ? RV.deg(v) : RV.fmt(v, col.id === 'gap' ? 3 : 2); };
    return gs.map(function (g) { return { label: g.short, color: g.color, value: text(RV.median(g.runs.map(fn))) }; });
  }
  function rebuild() {
    charts.forEach(function (c) { c.destroy(); }); charts = [];
    if (viewer) { viewer.destroy(); viewer = null; }
    grid.innerHTML = '';
    colChips.querySelectorAll('button').forEach(function (b) { b.className = 'chip ' + (on[b.dataset.col] ? 'on' : 'off'); });
    var cols = activeCols();
    grid.style.gridTemplateColumns = '150px repeat(' + cols.length + ', minmax(0, 1fr))';
    var corner = el('div', 'v4-corner', grid);
    viewer = RV.arm3d(corner, state, tr, { height: 106, exaggerate: 6, dist: 2.25, ghosts: false, worstMarker: false, onPose: function (i, hud) { hud.textContent = state.T().t[i].toFixed(2) + ' s'; } });
    cols.forEach(function (c) {
      var h = el('div', 'v4-colhead', grid);
      var name = el('div', 'v4-colname', h);
      if (c.color) el('i', 'v4-colsw', name).style.background = c.color;
      name.appendChild(document.createTextNode(c.label + ' '));
      el('span', 'unit', name, '[' + c.unit + ']');
      el('div', 'v4-coldef', h, c.def);
      var keys = el('div', 'v4-colkeys', h);
      state.groups().forEach(function (g) {
        var k = el('span', 'v4-key', keys); el('i', '', k).style.background = g.color;
        k.appendChild(document.createTextNode(g.short + (state.asBand(g.runs.length) ? ' band' : g.runs.length > 1 ? ' lines' : '')));
      });
    });
    var f = state.focusRun();
    RV.F.joints.forEach(function (joint, j) {
      var rh = el('div', 'v4-rowhead', grid);
      el('div', 'v4-joint', rh, joint);
      var rs = el('div', 'v4-rowstats', rh);
      el('div', '', rs, 'highlighted: ' + f.title);
      el('div', '', rs, 'RMS ' + RV.deg(f.m[j].errRms) + ' · max ' + RV.deg(f.m[j].errMax));
      el('div', '', rs, 'FB share ' + RV.pct(f.m[j].fbShare) + ' · gap ' + RV.nm(f.m[j].driveGapRms, 3));
      var lim = RV.F.maxTorque[j], hr = f.m[j].cmdPeak / lim;
      el('div', hr >= 0.9 ? 'v4-warn' : '', rs, 'peak ' + RV.nm(f.m[j].cmdPeak) + ' of ' + lim);
      cols.forEach(function (c) {
        var cell = el('div', 'v4-cell', grid);
        cell.dataset.cell = j + '-' + c.id;
        var ch = el('div', 'v4-cellhead', cell);
        summary(c, j).forEach(function (s) {
          var t = el('span', 'v4-sum', ch); el('i', '', t).style.background = s.color;
          t.appendChild(document.createTextNode(s.label + ' ')); el('b', 'num', t, s.value);
        });
        el('span', 'v4-rmslabel muted', ch, c.id === 'share' ? 'median' : 'median RMS');
        var ex = el('button', 'v4-expand', ch, '⤢'); ex.title = 'expand this cell';
        ex.onclick = function (e) { e.stopPropagation(); expand(j, c); };
        cell.addEventListener('dblclick', function () { expand(j, c); });
        charts.push(RV.chart(cell, { height: chartHeight(), syncKey: 'v4', ySize: 36, content: cellContent(c, j) }, tr));
      });
    });
    if (expanded) expand(expanded.j, COLS.filter(function (c) { return c.id === expanded.col; })[0], true);
  }
  function chartHeight() {
    var avail = gridHost.clientHeight || 700;
    return Math.max(120, Math.floor((avail - 116) / 2) - 58);
  }
  var bigChart = null;
  function expand(j, col, keep) {
    if (!col) return;
    expanded = { j: j, col: col.id };
    if (bigChart) { bigChart.destroy(); bigChart = null; }
    overlay.innerHTML = '';
    overlay.classList.add('open');
    var top = el('div', 'v4-ovtop', overlay);
    el('b', '', top, RV.F.joints[j] + ' · ' + col.label + ' ');
    el('span', 'unit muted', top, '[' + col.unit + '] — ' + col.def);
    var tabs = el('div', 'v4-ovtabs', top);
    COLS.forEach(function (c) {
      var b = el('button', 'chip ' + (c.id === col.id ? 'on' : 'off'), tabs, c.label);
      b.onclick = function () { expand(j, c); };
    });
    var jb = el('button', 'chip', tabs, RV.F.joints[1 - j] + ' ↕');
    jb.onclick = function () { expand(1 - j, col); };
    var close = el('button', 'v4-close', top, '✕'); close.title = 'close (Esc)';
    close.onclick = collapse;
    var sums = el('div', 'v4-ovsums', overlay);
    summary(col, j).forEach(function (s) { var t = el('span', 'v4-sum big', sums); el('i', '', t).style.background = s.color; t.appendChild(document.createTextNode(s.label + ' ')); el('b', 'num', t, s.value); });
    el('span', 'muted', sums, (col.id === 'share' ? 'median' : 'median RMS') + ' over the visible runs · bands: median · IQR · p5–p95 · min–max');
    var host = el('div', 'v4-ovchart', overlay);
    bigChart = RV.chart(host, { height: Math.max(260, overlay.clientHeight - 110), syncKey: 'v4', content: cellContent(col, j, true) }, tr);
  }
  function collapse() {
    expanded = null; overlay.classList.remove('open'); overlay.innerHTML = '';
    if (bigChart) { bigChart.destroy(); bigChart = null; }
  }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && expanded) collapse(); });

  function paint() { var T = state.T(); h1.textContent = T.title; sub.textContent = T.description; }
  function resize() { tr.charts.forEach(function (c) { c.resize(); }); if (viewer) viewer.resize(); }
  state.on(function (why) { if (why === 'target') tr.reset(); paint(); rebuild(); });
  paint(); rebuild();
  var resizeTimer = null;
  window.addEventListener('resize', function () { clearTimeout(resizeTimer); resizeTimer = setTimeout(rebuild, 120); });
  window.RVPAGE = { state: state, tr: tr };
})();
