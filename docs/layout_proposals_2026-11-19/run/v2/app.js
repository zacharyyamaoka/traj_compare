/* V2 Torque cockpit — the torque is the page.
 * Per joint, the command is drawn as what it is made of: feedforward as a blue area from zero, feedback as the
 * orange wedge between feedforward and commanded (so its thickness IS the feedback at every instant), target dashed,
 * applied thin. Error sits beneath; the budget column beside. One run at a time, against its group's band. */
(function () {
  'use strict';
  var el = RV.el;
  var state = RV.makeState('v2');
  var tr = RV.makeTransport(state);
  var bandScope = RV.recall('v2:bandScope', 'group');  // group | real

  var app = document.getElementById('app');
  var head = el('header', 'rv-head v2-head', app);
  var titles = el('div', 'v2-titles', head);
  var h1 = el('h1', '', titles);
  var sub = el('div', 'rv-sub', titles);
  el('span', 'rv-spacer', head);
  var picker = el('div', 'v2-picker', head);
  var prev = el('button', 'tc-tbtn', picker, '◀'); prev.title = 'previous visible run'; prev.id = 'prev';
  var focusBox = el('div', 'v2-focus', picker);
  var focusSw = el('span', 'v2-focus-sw', focusBox);
  var focusName = el('span', 'v2-focus-name', focusBox);
  var focusMeta = el('span', 'v2-focus-meta', focusBox);
  var next = el('button', 'tc-tbtn', picker, '▶'); next.title = 'next visible run'; next.id = 'next';
  var scopeBox = el('div', 'v2-scope', head);
  el('span', 'rv-field-label', scopeBox, 'Band');
  var scopeSeg = el('div', 'rv-seg', scopeBox);
  [['group', 'its group'], ['real', 'all real runs']].forEach(function (o) {
    var b = el('button', '', scopeSeg, o[1]); b.dataset.v = o[0];
    b.onclick = function () { bandScope = o[0]; RV.store('v2:bandScope', bandScope); paint(); rebuild(); };
  });
  RV.badge(head);

  var body = el('div', 'rv-body', app);
  var side = el('aside', 'rv-side v2-side', body);
  var list = RV.runList(side, state, {
    metric: { label: 'FB share (shoulder)', value: function (r) { return r.m[0].fbShare; }, text: function (v) { return RV.pct(v); }, bar: true, max: 0.5, barColor: RV.COMP.fb },
    modeControl: false,
  });
  var main = el('main', 'rv-main v2-main', body);
  var right = el('aside', 'rv-side right v2-right', body);
  var leftPanel = RV.sidePanel(side, 'v2-side', { label: 'Runs', width: 280, foldButton: list.fold, onChange: resize });
  var rightHead = el('div', 'v2-right-head', right);
  el('div', 'rv-runs-title', rightHead, 'Torque budget');
  var rfold = el('button', 'rv-fold', rightHead, '»'); rfold.title = 'fold the budget column';
  var budget = el('div', 'v2-budget', right);
  var thumbBox = el('div', 'v2-thumb', right);
  var rightPanel = RV.sidePanel(right, 'v2-right', { side: 'right', label: 'Budget', width: 320, min: 240, max: 480, foldButton: rfold, onChange: resize });

  var cockpits = el('div', 'v2-cockpits', main);
  var foot = el('div', 'v2-foot', main);
  var worst = el('button', 'rv-worst', null, '⚠ Worst moment'); worst.id = 'worst';
  worst.onclick = function () {
    var f = state.focusRun(), j = f.m[0].errMax >= f.m[1].errMax ? 0 : 1;
    tr.focusOn(f.m[j].errMaxT, 0.6);
  };
  var resetZoom = el('button', 'tc-tbtn v2-reset', null, 'Reset zoom'); resetZoom.onclick = function () { tr.setZoom(null); };
  RV.transportBar(tr, foot, [worst, resetZoom]);

  function bandRuns(f) {
    var vis = state.visibleRuns().filter(function (r) { return r.kind === 'real'; });
    return bandScope === 'group' ? vis.filter(function (r) { return r.group === f.group; }) : vis;
  }
  var charts = [], readouts = [];
  function rebuild() {
    charts.forEach(function (c) { c.destroy(); }); charts = []; readouts = [];
    cockpits.innerHTML = '';
    var f = state.focusRun(), T = state.T(), peers = bandRuns(f);
    RV.F.joints.forEach(function (joint, j) {
      var pit = el('section', 'v2-pit', cockpits);
      var top = el('div', 'v2-pit-top', pit);
      el('span', 'v2-joint', top, joint);
      var leg = el('div', 'v2-legend', top);
      [['target', 'dash', RV.COMP.target], ['feedforward', 'area', RV.COMP.ff], ['feedback = commanded − feedforward', 'wedge', RV.COMP.fb],
       ['commanded', 'line', f.color], ['applied', 'thin', RV.mix(f.color, '#000000', 0.35)], [peers.length + '-run band of commanded', 'band', '#8a8983']].forEach(function (it) {
        var s = el('span', 'v2-leg', leg); var sw = el('i', 'v2-sw v2-sw-' + it[1], s);
        sw.style.color = it[2]; if (it[1] !== 'dash') sw.style.background = it[1] === 'band' ? RV.rgba(it[2], 0.25) : it[1] === 'area' ? RV.rgba(it[2], 0.3) : it[1] === 'wedge' ? RV.rgba(it[2], 0.55) : it[2];
        s.appendChild(document.createTextNode(it[0]));
      });
      readouts.push(el('div', 'v2-readout', pit));
      var tq = el('div', 'v2-chart', pit);
      charts.push(RV.chart(tq, { height: 196, xAxis: false, syncKey: 'v2', content: function () {
        var fills = [];
        if (peers.length >= 3) {
          var b = RV.bands(peers, 'cmd', j);
          fills.push({ lo: b.p5, hi: b.p95, color: 'rgba(138,137,131,0.13)' });
          fills.push({ lo: b.p25, hi: b.p75, color: 'rgba(138,137,131,0.22)' });
        }
        var zero = f.ff[j].map(function () { return 0; });
        fills.push({ lo: zero, hi: f.ff[j], color: RV.rgba(RV.COMP.ff, 0.2) });
        fills.push({ lo: f.ff[j], hi: f.cmd[j], color: RV.rgba(RV.COMP.fb, 0.55) });
        return { fills: fills, zeroLine: true, lines: [
          { values: f.ff[j], stroke: RV.rgba(RV.COMP.ff, 0.9), width: 1 },
          { values: T.tau[j], stroke: RV.COMP.target, width: 1.4, dash: [6, 4] },
          { values: f.cmd[j], stroke: f.color, width: 2.2 },
          { values: f.applied[j], stroke: RV.mix(f.color, '#000000', 0.35), width: 0.8 },
        ] };
      } }, tr));
      var lab = el('div', 'v2-sublabel', pit);
      el('span', '', lab, joint + ' error (target − run) [°]');
      el('span', 'muted', lab, f.title + ' against ' + (bandScope === 'group' ? RV.GROUPS[f.group].label : 'all real runs') + ' · median · IQR · p5–p95');
      var ec = el('div', 'v2-chart', pit);
      charts.push(RV.chart(ec, { height: 92, syncKey: 'v2', ySize: 40, content: function () {
        var fills = [], lines = [];
        if (peers.length >= 3) {
          var b = RV.bands(peers, 'err', j);
          fills = RV.bandFills(b, RV.GROUPS[f.group].color, 0.9);
          lines.push({ values: b.med, stroke: RV.GROUPS[f.group].color, width: 1, alpha: 0.8 });
        }
        lines.push({ values: f.err[j], stroke: f.color, width: 1.9 });
        return { fills: fills, lines: lines, zeroLine: true, markers: [{ t: f.m[j].errMaxT }] };
      } }, tr));
    });
    paintBudget();
    paintReadouts();
  }

  function stat(parent, label, value, extra) {
    var r = el('div', 'v2-stat', parent); el('span', 'k', r, label); el('span', 'v num', r, value);
    if (extra) el('span', 'x muted', r, extra);
    return r;
  }
  function paintBudget() {
    budget.innerHTML = '';
    var f = state.focusRun(), real = state.visibleRuns().filter(function (r) { return r.kind === 'real'; });
    RV.F.joints.forEach(function (joint, j) {
      var m = f.m[j], blk = el('div', 'v2-blk', budget);
      var top = el('div', 'v2-blk-top', blk);
      el('span', 'v2-blk-joint', top, joint);
      el('span', 'v2-share num', top, RV.pct(m.fbShare));
      el('span', 'muted', top, 'of the command is feedback');
      var bar = el('div', 'v2-split', blk);
      var ffw = 1 - m.fbShare;
      var a = el('span', 'ff', bar); a.style.width = (100 * ffw) + '%'; a.textContent = 'FF ' + RV.pct(ffw);
      var b = el('span', 'fb', bar); b.style.width = (100 * m.fbShare) + '%'; if (m.fbShare > 0.12) b.textContent = 'FB';
      // where this run sits among every visible real run (FB share, one dot per run)
      var strip = el('div', 'v2-strip', blk);
      var maxShare = Math.max(0.3, Math.max.apply(null, real.map(function (r) { return r.m[j].fbShare; })) * 1.1);
      RV.GROUP_ORDER.forEach(function (gk) {
        var rows = real.filter(function (r) { return r.group === gk; });
        if (!rows.length) return;
        var lane = el('div', 'v2-lane', strip);
        el('span', 'v2-lane-l', lane, RV.GROUPS[gk].short);
        var track = el('span', 'v2-lane-t', lane);
        rows.forEach(function (r) {
          var d = el('i', 'v2-dot' + (r === f ? ' me' : ''), track);
          d.style.left = (100 * r.m[j].fbShare / maxShare) + '%';
          d.style.background = r === f ? r.color : RV.rgba(r.groupColor, 0.55);
          d.title = r.title + ': FB share ' + RV.pct(r.m[j].fbShare, 1);
          d.onclick = function () { state.setFocus(r.name); };
        });
        var med = RV.median(rows.map(function (r) { return r.m[j].fbShare; }));
        var mk = el('i', 'v2-med', track); mk.style.left = (100 * med / maxShare) + '%'; mk.title = 'median ' + RV.pct(med, 1);
      });
      var scale = el('div', 'v2-lane-scale muted', strip);
      el('span', '', scale, '0%'); el('span', '', scale, 'FB share →'); el('span', '', scale, RV.pct(maxShare));
      var stats = el('div', 'v2-stats', blk);
      stat(stats, 'feedforward RMS', RV.nm(m.ffRms, 3));
      stat(stats, 'feedback RMS', RV.nm(m.fbRms, 3));
      stat(stats, 'target − commanded', RV.nm(m.tgtMinusCmdRms, 3), 'RMS');
      stat(stats, 'drive gap (cmd − applied)', RV.nm(m.driveGapRms, 3), 'RMS');
      var lim = RV.F.maxTorque[j], head = m.cmdPeak / lim;
      var pk = stat(stats, 'peak |commanded|', RV.nm(m.cmdPeak, 2), 'of ' + lim + ' limit');
      var hb = el('span', 'v2-head-bar', pk); var hf = el('i', '', hb); hf.style.width = Math.min(100, 100 * head) + '%';
      if (head >= 0.9) { pk.classList.add('warn'); hf.style.background = RV.AMBER; }
    });
  }
  function paintReadouts() {
    var f = state.focusRun(), T = state.T(), i = tr.index();
    readouts.forEach(function (box, j) {
      box.innerHTML = '';
      el('span', 'muted num', box, 't ' + T.t[i].toFixed(2) + ' s');
      function part(label, v, color) { var s = el('span', 'v2-ro', box); var b = el('b', 'num', s, RV.fmt(v, 2)); b.style.color = color; s.appendChild(document.createTextNode(' ' + label)); }
      part('target', T.tau[j][i], '#52514e');
      el('span', 'v2-op', box, '·');
      part('FF', f.ff[j][i], RV.COMP.ff); el('span', 'v2-op', box, '+');
      part('FB', f.fb[j][i], RV.mix(RV.COMP.fb, '#000000', 0.15)); el('span', 'v2-op', box, '=');
      part('commanded', f.cmd[j][i], f.color); el('span', 'v2-op', box, '→');
      part('applied N·m', f.applied[j][i], RV.mix(f.color, '#000000', 0.35));
      var share = Math.abs(f.fb[j][i]) / (Math.abs(f.ff[j][i]) + Math.abs(f.fb[j][i]) + 1e-9);
      el('span', 'v2-ro-share num', box, 'FB ' + RV.pct(share) + ' here');
    });
  }
  RV.arm3d(thumbBox, state, tr, { height: 200, exaggerate: 6, dist: 2.3, ghosts: false, onPose: function (i, hud) {
    var f = state.focusRun();
    hud.textContent = f.title + ' · shoulder ' + RV.deg(RV.runQ(f, 0)[i], 1) + ' · tip error ×6';
  } });

  function paint() {
    var T = state.T(), f = state.focusRun();
    h1.textContent = T.title;
    sub.textContent = T.description;
    focusSw.style.background = f.color;
    focusName.textContent = f.title;
    var vis = state.visibleRuns(), at = vis.indexOf(f);
    focusMeta.textContent = RV.GROUPS[f.group].label + ' · ' + f.tags.date + (at >= 0 ? ' · ' + (at + 1) + ' of ' + vis.length + ' shown' : ' · hidden');
    scopeSeg.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.dataset.v === bandScope); });
  }
  function step(d) {
    var vis = state.visibleRuns(), f = state.focusRun(), at = vis.indexOf(f);
    var nxt = vis[(at + d + vis.length) % vis.length];
    if (nxt) state.setFocus(nxt.name);
  }
  prev.onclick = function () { step(-1); };
  next.onclick = function () { step(1); };
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === '[') step(-1); if (e.key === ']') step(1);
  });
  function resize() { tr.charts.forEach(function (c) { c.resize(); }); }
  tr.on(function (kind) { if (kind !== 'zoom') paintReadouts(); });
  state.on(function (why) { if (why === 'target') tr.reset(); paint(); rebuild(); });
  paint(); rebuild();
  RV.onResize(resize);
  window.RVPAGE = { state: state, tr: tr };
})();
