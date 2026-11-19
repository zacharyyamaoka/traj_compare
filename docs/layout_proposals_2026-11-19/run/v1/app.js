/* V1 Sidebar + sections — today's run view, TensorBoard-ified.
 * Left: the run tree (group by tag, solo, hide, colour key). Right: traj_compare's own control bar and sections,
 * plus the new Torque breakdown section (the contract's five traces). Repeats collapse into percentile bands
 * once a group has more than five visible runs. */
(function () {
  'use strict';
  var el = RV.el;
  var state = RV.makeState('v1');
  var tr = RV.makeTransport(state);
  var shown = { target: true, cmd: true, ff: true, fb: true, applied: true };

  RV.badge(document.getElementById('badge'));
  var side = document.getElementById('side');
  var list = RV.runList(side, state, {
    targetSelect: false,
    metric: { label: 'shoulder RMS err', value: function (r) { return r.m[0].errRms; }, text: function (v) { return RV.deg(v, 2); } },
  });
  var panel = RV.sidePanel(side, 'v1-side', { label: 'Runs', width: 290, foldButton: list.fold, onChange: resizeAll });

  // target tabs, as traj_compare's scenario tabs
  var tabs = document.getElementById('tabs');
  RV.F.targets.forEach(function (t) {
    var b = el('button', '', tabs, t.title);
    b.dataset.target = t.name;
    b.onclick = function () { tr.reset(); state.set({ target: t.name, solo: null }, 'target'); };
  });

  /* ---- control bar: plot sections, repeat encoding, zoom, worst moment ---- */
  var controls = document.getElementById('controls');
  var defs = [
    { id: 'answer', label: 'Answer', on: true },
    { id: 'torque', label: 'Torque breakdown', on: true },
    { id: 'err', label: 'Joint error', on: true },
    { id: 'q', label: 'Joint q', on: false },
    { id: 'three', label: '3D paths', on: true },
  ];
  var plotsGroup = el('div', 'group', controls);
  el('span', 'grouplabel', plotsGroup, 'Plots');
  var zoomGroup = el('div', 'group', controls);
  el('span', 'grouplabel', zoomGroup, 'Zoom');
  var resetZoom = el('button', 'chip', zoomGroup, 'Reset zoom');
  resetZoom.onclick = function () { tr.setZoom(null); };
  var worst = el('button', 'rv-worst', zoomGroup, '⚠ Worst moment');
  worst.id = 'worst';
  worst.onclick = function () {
    var f = state.focusRun();
    var j = f.m[0].errMax >= f.m[1].errMax ? 0 : 1;
    tr.focusOn(f.m[j].errMaxT, 0.6);
  };
  var unitGroup = el('div', 'group', controls);
  el('span', 'grouplabel', unitGroup, 'Units');
  el('span', 'chip on', unitGroup, '° · N·m');

  var host = document.getElementById('sections');
  var sections = defs.map(function (def) {
    var sec = { def: def, on: RV.recall('v1:sec:' + def.id, def.on), charts: [] };
    sec.chip = el('button', 'chip', plotsGroup, def.label);
    sec.chip.onclick = function () { sec.on = !sec.on; RV.store('v1:sec:' + def.id, sec.on); paintSection(sec); };
    sec.el = el('div', 'tc-section v1-sec', host);
    sec.el.id = 'sec-' + def.id;
    sec.head = el('h3', '', sec.el, def.label + ' ');
    sec.hint = el('span', 'hint', sec.head);
    sec.body = el('div', '', sec.el);
    return sec;
  });
  function byId(id) { return sections.filter(function (s) { return s.def.id === id; })[0]; }
  function paintSection(sec) {
    sec.chip.className = 'chip ' + (sec.on ? 'on' : 'off');
    sec.el.style.display = sec.on ? '' : 'none';
    if (sec.on) build(sec);
  }

  function clearCharts(sec) { sec.charts.forEach(function (c) { c.destroy(); }); sec.charts = []; sec.body.innerHTML = ''; }
  function card(parent, title, unit, right) {
    var c = el('div', 'rv-card', parent);
    var t = el('div', 'ptitle', c);
    var b = el('b', '', t, title); b.title = title;
    el('span', 'unit', t, '[' + unit + ']');
    if (right) el('span', 'right', t, right);
    return c;
  }
  function encodingNote() {
    return state.groups().map(function (g) {
      return g.label + ' ×' + g.runs.length + ' → ' + (state.asBand(g.runs.length) ? 'band' : g.runs.length === 1 ? 'line' : 'lines');
    }).join(' · ');
  }

  var builders = {
    answer: function (sec) {
      sec.hint.textContent = '— the median run of each feedforward model on this target';
      var v = RV.verdict(state, 0), ve = RV.verdict(state, 1);
      var box = el('div', 'v1-answer', sec.body);
      var line = el('div', 'v1-verdict', box);
      if (v.v1 && v.v2) {
        var better = v.err2 < v.err1;
        line.innerHTML = '';
        el('b', '', line, (better ? 'ff v2 calibrated tracks better' : 'ff v1 nominal tracks better') + ' on this target');
        line.appendChild(document.createTextNode(' — shoulder error ' + RV.deg(v.err1) + ' → ' + RV.deg(v.err2) +
          ', and feedback now supplies ' + RV.pct(v.share2) + ' of the command instead of ' + RV.pct(v.share1) + '.'));
      } else {
        el('b', '', line, 'One feedforward model on this target');
        line.appendChild(document.createTextNode(' — ' + state.groups().map(function (g) { return g.label + ' ×' + g.runs.length; }).join(', ') + '.'));
      }
      var facts = el('div', 'tc-facts', box);
      function fact(label, value, tone) {
        var f = el('div', 'tc-fact' + (tone ? ' v1-' + tone : ''), facts);
        el('span', 'label', f, label); el('strong', '', f, value);
      }
      var groups = state.groups().filter(function (g) { return g.key !== 'sim'; });
      groups.forEach(function (g) {
        var med = function (fn) { return RV.median(g.runs.map(fn)); };
        fact(g.label + ' ×' + g.runs.length, 'shoulder ' + RV.deg(med(function (r) { return r.m[0].errRms; })) + ' · elbow ' + RV.deg(med(function (r) { return r.m[1].errRms; })) + ' RMS');
        fact('FB share · ' + RV.GROUPS[g.key].short, 'shoulder ' + RV.pct(med(function (r) { return r.m[0].fbShare; })) + ' · elbow ' + RV.pct(med(function (r) { return r.m[1].fbShare; })));
      });
      fact('Drive gap (cmd − applied)', RV.nm(RV.median(state.visibleRuns().filter(function (r) { return r.kind === 'real'; }).map(function (r) { return r.m[0].driveGapRms; })), 3) + ' RMS');
      fact('Saturation', v.sat > 0 ? RV.pct(v.sat, 1) + ' of samples at the limit' : 'none', v.sat > 0 ? 'warn' : '');
    },
    torque: function (sec) {
      var f = state.focusRun(), T = state.T();
      sec.hint.textContent = '— commanded = feedforward (model) + feedback (correction); highlighted run vs every run\'s feedback';
      var legendRow = el('div', 'v1-legendrow', sec.body);
      RV.componentLegend(legendRow, shown, function () { build(sec); }, f);
      el('span', 'v1-enc', legendRow, encodingNote());
      var grid = el('div', 'v1-torquegrid', sec.body);
      RV.F.joints.forEach(function (joint, j) {
        var c1 = card(grid, joint + ' — ' + f.title, 'N·m', 'FB share ' + RV.pct(f.m[j].fbShare) + ' · gap ' + RV.nm(f.m[j].driveGapRms, 3));
        sec.charts.push(RV.chart(c1, { height: 150, content: function () { return RV.breakdownLines(f, j, shown, T); } }, tr));
        var c2 = card(grid, joint + ' feedback — every visible run', 'N·m', encodingNote().indexOf('band') >= 0 ? 'median · IQR · p5–p95 · min–max' : 'lines');
        sec.charts.push(RV.chart(c2, { height: 150, content: function () { return RV.repeatContent(state, 'fb', j, { zeroLine: true }); } }, tr));
      });
      var det = el('details', 'v1-budget', sec.body);
      var real = state.visibleRuns().filter(function (r) { return r.kind === 'real' || r.kind === 'sim'; });
      el('summary', '', det, 'Torque budget table · ' + real.length + ' runs × ' + RV.F.joints.length + ' joints');
      var wrap = el('div', 'tc-table-scroll', det);
      var table = el('table', 'tc-metrics v1-table', wrap);
      var thead = el('thead', '', table), hr = el('tr', '', thead);
      ['Run', 'Joint', 'FB share', 'cmd RMS', 'FF RMS', 'FB RMS', 'target − cmd RMS', 'cmd − applied RMS', 'peak |cmd|'].forEach(function (h) { el('th', '', hr, h); });
      var tbody = el('tbody', '', table);
      real.forEach(function (r) {
        RV.F.joints.forEach(function (joint, j) {
          var m = r.m[j], row = el('tr', r === f ? 'tone-highlight' : '', tbody);
          el('th', '', row, j === 0 ? r.title : '');
          el('td', '', row, joint);
          [RV.pct(m.fbShare, 1), RV.nm(m.cmdRms, 3), RV.nm(m.ffRms, 3), RV.nm(m.fbRms, 3), RV.nm(m.tgtMinusCmdRms, 3), RV.nm(m.driveGapRms, 3), RV.nm(m.cmdPeak, 2)]
            .forEach(function (v) { el('td', '', row, v); });
        });
      });
    },
    err: function (sec) {
      sec.hint.textContent = '— target − run; ' + encodingNote();
      var grid = el('div', 'v1-grid2', sec.body);
      var f = state.focusRun();
      RV.F.joints.forEach(function (joint, j) {
        var c = card(grid, joint + ' error (target − run)', '°', f.title + ': RMS ' + RV.deg(f.m[j].errRms) + ' · max ' + RV.deg(f.m[j].errMax));
        sec.charts.push(RV.chart(c, { height: 150, content: function () {
          var content = RV.repeatContent(state, 'err', j, { zeroLine: true });
          content.markers = [{ t: f.m[j].errMaxT }];
          return content;
        } }, tr));
      });
    },
    q: function (sec) {
      sec.hint.textContent = '— joint angle, target dashed';
      var grid = el('div', 'v1-grid2', sec.body), T = state.T();
      RV.F.joints.forEach(function (joint, j) {
        var c = card(grid, joint + ' q', '°');
        sec.charts.push(RV.chart(c, { height: 150, content: function () { return RV.repeatContent(state, 'q', j, { target: T.q[j] }); } }, tr));
      });
    },
    three: function (sec) {
      sec.hint.textContent = '— target ghost (grey), highlighted run (colour), other visible runs as sticks; tip error ×6';
      var wrap = el('div', 'v1-3dwrap', sec.body);
      var stage = el('div', 'v1-3dstage', wrap);
      var info = el('div', 'v1-3dinfo', wrap);
      sec.viewer = RV.arm3d(stage, state, tr, { height: 300, exaggerate: 6, dist: 1.95, onPose: function (i, hud) {
        var T = state.T(), f = state.focusRun();
        hud.textContent = 't = ' + T.t[i].toFixed(2) + ' s · shoulder ' + RV.deg(T.q[0][i], 1) + ' · ' + f.title + ' error ' + RV.deg(f.err[0][i]) + ' / ' + RV.deg(f.err[1][i]);
        info.innerHTML = '';
        el('div', 'v1-3dinfo-h', info, 'At the cursor · ' + f.title);
        var tbl = el('table', 'v1-instant', info);
        var hr = el('tr', '', tbl); ['', 'shoulder', 'elbow'].forEach(function (h) { el('th', '', hr, h); });
        [['target τ', function (j) { return T.tau[j][i]; }], ['feedforward', function (j) { return f.ff[j][i]; }], ['feedback', function (j) { return f.fb[j][i]; }],
         ['commanded', function (j) { return f.cmd[j][i]; }], ['applied', function (j) { return f.applied[j][i]; }]].forEach(function (row) {
          var r = el('tr', '', tbl); el('td', '', r, row[0]);
          [0, 1].forEach(function (j) { el('td', 'num', r, RV.fmt(row[1](j), 2)); });
        });
        el('div', 'muted v1-3dnote', info, 'N·m · hover a plot to preview, click to pin the time');
      } });
      RV.transportBar(tr, sec.body);
    },
  };
  function build(sec) {
    // WHY: the 3D view keeps one WebGL context and follows state/transport itself; rebuilding it would leak contexts
    if (sec.def.id === 'three') { if (!sec.viewer) builders.three(sec); return; }
    clearCharts(sec);
    builders[sec.def.id](sec);
  }
  function rebuildAll() { sections.forEach(function (sec) { if (sec.on) build(sec); }); }
  function resizeAll() { tr.charts.forEach(function (c) { c.resize(); }); sections.forEach(function (s) { if (s.viewer) s.viewer.resize(); }); }

  function paintHeader() {
    var T = state.T();
    document.getElementById('title').textContent = T.title;
    document.getElementById('desc').textContent = T.description + ' · ' + T.runs.length + ' runs (' +
      state.groups(T.runs).map(function (g) { return g.runs.length + ' ' + g.label; }).join(', ') + ')';
    tabs.querySelectorAll('button').forEach(function (b) { b.classList.toggle('active', b.dataset.target === state.target); });
  }
  state.on(function () { paintHeader(); rebuildAll(); });
  sections.forEach(paintSection);
  paintHeader();
  RV.onResize(resizeAll);
  window.RVPAGE = { state: state, tr: tr, panel: panel };
})();
