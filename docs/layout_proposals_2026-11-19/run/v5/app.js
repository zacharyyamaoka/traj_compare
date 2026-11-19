/* V5 The moment — one scrubbable stage.
 * A big 3D arm (target ghost, highlighted run, every other visible run as a stick ghost) and, at the cursor, a torque
 * waterfall per joint: target → Δ model → feedforward → + feedback → commanded → Δ drive → applied, each total with
 * the spread of every visible run at that same instant. Time plots sit small underneath; worst moments are one click. */
(function () {
  'use strict';
  var el = RV.el;
  var state = RV.makeState('v5');
  var tr = RV.makeTransport(state);

  var app = document.getElementById('app');
  var head = el('header', 'rv-head', app);
  var titles = el('div', '', head);
  var h1 = el('h1', '', titles); var sub = el('div', 'rv-sub', titles);
  el('span', 'rv-spacer', head);
  RV.badge(head);
  var body = el('div', 'rv-body', app);
  var side = el('aside', 'rv-side', body);
  var list = RV.runList(side, state, {
    metric: { label: 'shoulder max |err|', value: function (r) { return r.m[0].errMax; }, text: function (v) { return RV.deg(v, 2); } },
  });
  var main = el('main', 'rv-main v5-main', body);
  RV.sidePanel(side, 'v5-side', { label: 'Runs', width: 260, foldButton: list.fold, onChange: resize });

  var top = el('div', 'v5-top', main);
  var stageWrap = el('div', 'v5-stagewrap', top);
  var falls = el('aside', 'rv-side right v5-falls', top);
  var fallsPanel = RV.sidePanel(falls, 'v5-falls', { side: 'right', label: 'Torque at the cursor', width: 470, min: 340, max: 640, onChange: resize });
  var fh = el('div', 'v5-falls-head', falls);
  el('div', 'rv-runs-title', fh, 'Torque at the cursor');
  var ffold = el('button', 'rv-fold', fh, '»'); ffold.title = 'fold'; ffold.onclick = function () { fallsPanel.fold(true); };
  var fallBoxes = RV.F.joints.map(function (joint) { return el('div', 'v5-fall', falls); });
  var fallLegend = el('div', 'v5-fall-legend', falls);

  var bottom = el('div', 'v5-bottom', main);
  var strips = el('div', 'v5-strips', bottom);
  var foot = el('div', 'v5-foot', bottom);
  var resetZoom = el('button', 'tc-tbtn', null, 'Reset zoom'); resetZoom.style.padding = '0 8px';
  resetZoom.onclick = function () { tr.setZoom(null); };
  RV.transportBar(tr, foot, [resetZoom]);

  // stage + HUD + worst-moment chips
  var hudBig = null, hudSub = null, moments = null;
  var viewer = RV.arm3d(stageWrap, state, tr, { exaggerate: 6, dist: 2.05, lookY: 0.0, onPose: function (i, hud) {
    var T = state.T(), f = state.focusRun();
    if (!hudBig) {
      hud.innerHTML = '';
      hudBig = el('div', 'v5-hud-t num', hud);
      hudSub = el('div', 'v5-hud-s', hud);
    }
    hudBig.textContent = T.t[i].toFixed(2) + ' s';
    var load = Math.abs(Math.cos(T.q[0][i] * Math.PI / 180));
    hudSub.innerHTML = '';
    el('div', '', hudSub, 'shoulder ' + RV.deg(T.q[0][i], 1) + ' · elbow ' + RV.deg(T.q[1][i], 1) + ' · gravity load ' + RV.pct(load) + ' of max');
    var e = el('div', '', hudSub);
    var sw = el('i', 'v5-hud-sw', e); sw.style.background = f.color;
    e.appendChild(document.createTextNode(f.title + ' — error ' + RV.deg(f.err[0][i]) + ' / ' + RV.deg(f.err[1][i]) + ' · tip ' + RV.fmt(f.tipErr[i], 1) + ' mm'));
    el('div', 'muted', hudSub, 'grey ghost = target · sticks = ' + (state.visibleRuns().length - 1) + ' other runs · tip path ×6');
    paintFalls(i);
  } });
  moments = el('div', 'v5-moments', stageWrap);

  function paintMoments() {
    moments.innerHTML = '';
    el('div', 'v5-moments-h', moments, 'Worst moments');
    RV.worstMoments(state, 3).forEach(function (m, k) {
      var b = el('button', 'v5-moment', moments);
      b.dataset.rank = k;
      el('b', 'num', b, '⚠ ' + m.t.toFixed(2) + ' s');
      el('span', '', b, m.run.title + ' · ' + RV.F.joints[m.j] + ' ' + RV.deg(m.value));
      b.onclick = function () { state.setFocus(m.run.name); tr.focusOn(m.t, 0.8); };
    });
  }

  /* ---------- the waterfall (SVG) ---------- */
  function paintFalls(i) {
    var T = state.T(), f = state.focusRun(), vis = state.visibleRuns();
    RV.F.joints.forEach(function (joint, j) {
      var box = fallBoxes[j];
      var tgt = T.tau[j][i], ff = f.ff[j][i], fb = f.fb[j][i], cmd = f.cmd[j][i], ap = f.applied[j][i];
      var clip = cmd - (ff + fb);
      var steps = [
        { label: 'target', kind: 'total', from: 0, to: tgt, color: RV.COMP.target },
        { label: 'Δ model', kind: 'delta', from: tgt, to: ff, color: RV.rgba(RV.COMP.ff, 0.45) },
        { label: 'feedforward', kind: 'total', from: 0, to: ff, color: RV.COMP.ff, key: 'ff' },
        { label: '+ feedback', kind: 'delta', from: ff, to: ff + fb, color: RV.COMP.fb, key: 'fb' },
      ];
      if (Math.abs(clip) > 1e-3) steps.push({ label: 'clamp', kind: 'delta', from: ff + fb, to: cmd, color: RV.AMBER });
      steps.push({ label: 'commanded', kind: 'total', from: 0, to: cmd, color: f.color, key: 'cmd' });
      steps.push({ label: 'Δ drive', kind: 'delta', from: cmd, to: ap, color: '#8a8983' });
      steps.push({ label: 'applied', kind: 'total', from: 0, to: ap, color: RV.mix(f.color, '#000000', 0.35), key: 'applied', outline: true });
      // repeat spread at this instant, for each total that varies across runs
      var spread = {};
      ['ff', 'cmd', 'applied', 'fb'].forEach(function (k) {
        var vals = vis.filter(function (r) { return r.kind === 'real'; }).map(function (r) { return r[k][j][i]; }).sort(function (a, b) { return a - b; });
        if (vals.length < 2) return;
        var q = function (p) { var pos = (vals.length - 1) * p, lo = Math.floor(pos), hi = Math.ceil(pos); return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo); };
        spread[k] = { min: vals[0], max: vals[vals.length - 1], p5: q(0.05), p95: q(0.95), p25: q(0.25), p75: q(0.75), runs: vis.filter(function (r) { return r.kind === 'real'; }) };
      });
      var lo = 0, hi = 0;
      steps.forEach(function (s) { lo = Math.min(lo, s.from, s.to); hi = Math.max(hi, s.from, s.to); });
      Object.keys(spread).forEach(function (k) { if (k !== 'fb') { lo = Math.min(lo, spread[k].min); hi = Math.max(hi, spread[k].max); } });
      var lim = RV.F.maxTorque[j];
      var nearLimit = Math.max(Math.abs(lo), Math.abs(hi)) > 0.75 * lim;
      if (nearLimit) { lo = Math.min(lo, -0.05); hi = Math.max(hi, 0.05); if (hi > 0) hi = Math.max(hi, lim * 1.02); if (lo < 0 && Math.abs(lo) > 0.5 * lim) lo = Math.min(lo, -lim * 1.02); }
      var pad = 0.12 * (hi - lo || 1); lo -= pad; hi += pad;
      var W = Math.max(300, box.clientWidth - 4), H = 244, L = 44, R = 8, Tp = 26, B = 44;
      var pw = W - L - R, ph = H - Tp - B, n = steps.length, slot = pw / n, bw = Math.min(40, slot * 0.56);
      var Y = function (v) { return Tp + (hi - v) / (hi - lo) * ph; };
      var svg = ['<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" font-family="-apple-system, Segoe UI, Roboto, sans-serif">'];
      var share = Math.abs(fb) / (Math.abs(ff) + Math.abs(fb) + 1e-9);
      svg.push('<text x="0" y="14" font-size="13" font-weight="650" fill="#0b0b0b" style="text-transform:capitalize">' + joint + '</text>');
      svg.push('<text x="' + W + '" y="14" font-size="11.5" text-anchor="end" fill="#52514e">feedback ' + RV.fmt(fb, 2) + ' of ' + RV.fmt(cmd, 2) + ' N·m commanded · <tspan fill="#c2410c" font-weight="650">' + RV.pct(share) + '</tspan></text>');
      // axis
      var ticks = niceTicks(lo, hi, 5);
      ticks.forEach(function (t) {
        svg.push('<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(t) + '" y2="' + Y(t) + '" stroke="#e6e5e0" stroke-width="' + (t === 0 ? 0 : 0.6) + '"/>');
        svg.push('<text x="' + (L - 6) + '" y="' + (Y(t) + 3.5) + '" font-size="10" text-anchor="end" fill="#8a8983">' + fmtTick(t) + '</text>');
      });
      svg.push('<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(0) + '" y2="' + Y(0) + '" stroke="#b9b8b2" stroke-width="1"/>');
      [lim, -lim].forEach(function (l) {
        if (l > lo && l < hi) svg.push('<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(l) + '" y2="' + Y(l) + '" stroke="' + RV.AMBER + '" stroke-dasharray="3 3" stroke-width="1"/><text x="' + (L + 3) + '" y="' + (Y(l) + (l > 0 ? -3 : 10)) + '" font-size="9.5" fill="#8a5a00">limit ' + (l > 0 ? '+' : '') + l + ' N·m</text>');
      });
      svg.push('<text x="' + (L - 38) + '" y="' + (Tp + ph / 2) + '" font-size="10" fill="#8a8983" transform="rotate(-90 ' + (L - 34) + ' ' + (Tp + ph / 2) + ')">N·m</text>');
      steps.forEach(function (s, k) {
        var cx = L + slot * (k + 0.5), x = cx - bw / 2, y1 = Y(Math.max(s.from, s.to)), y2 = Y(Math.min(s.from, s.to));
        var h = Math.max(1, y2 - y1);
        if (s.outline) svg.push('<rect x="' + x + '" y="' + y1 + '" width="' + bw + '" height="' + h + '" fill="' + RV.rgba('#ffffff', 0) + '" stroke="' + s.color + '" stroke-width="1.6"/>');
        else svg.push('<rect x="' + x + '" y="' + y1 + '" width="' + bw + '" height="' + h + '" fill="' + s.color + '" ' + (s.kind === 'delta' ? 'opacity="0.95"' : '') + ' rx="1.5"/>');
        if (k < steps.length - 1) {
          var nxt = steps[k + 1], join = s.to, nx = L + slot * (k + 1.5) - bw / 2;
          if (nxt.kind === 'delta' || nxt.from === join) svg.push('<line x1="' + (x + bw) + '" x2="' + nx + '" y1="' + Y(join) + '" y2="' + Y(join) + '" stroke="#8a8983" stroke-dasharray="2 2" stroke-width="0.8"/>');
        }
        var sp = s.key && spread[s.key];
        if (sp && s.kind === 'total') {
          var wx = cx + bw / 2 + 5;
          svg.push('<line x1="' + wx + '" x2="' + wx + '" y1="' + Y(sp.max) + '" y2="' + Y(sp.min) + '" stroke="#8a8983" stroke-width="0.8"/>');
          svg.push('<rect x="' + (wx - 2.5) + '" y="' + Y(sp.p95) + '" width="5" height="' + Math.max(1, Y(sp.p5) - Y(sp.p95)) + '" fill="#8a8983" opacity="0.35"/>');
          svg.push('<rect x="' + (wx - 2.5) + '" y="' + Y(sp.p75) + '" width="5" height="' + Math.max(1, Y(sp.p25) - Y(sp.p75)) + '" fill="#52514e" opacity="0.7"/>');
        }
        var val = s.kind === 'delta' ? s.to - s.from : s.to;
        var ly = val >= 0 || s.kind === 'delta' ? y1 - 4 : y2 + 11;
        svg.push('<text x="' + cx + '" y="' + ly + '" font-size="10.5" text-anchor="middle" fill="#22211f" font-weight="' + (s.kind === 'total' ? 600 : 400) + '">' + (s.kind === 'delta' && val > 0 ? '+' : '') + RV.fmt(val, 2) + '</text>');
        svg.push('<text x="' + cx + '" y="' + (H - B + 15 + (k % 2) * 13) + '" font-size="10.5" text-anchor="middle" fill="' + (s.kind === 'total' ? '#22211f' : '#52514e') + '">' + s.label + '</text>');
      });
      svg.push('</svg>');
      box.innerHTML = svg.join('');
      if (spread.fb) {
        var note = el('div', 'v5-fall-note', box);
        note.textContent = 'feedback across ' + spread.fb.runs.length + ' real runs at this instant: p5–p95 ' + RV.fmt(spread.fb.p5, 2) + ' … ' + RV.fmt(spread.fb.p95, 2) + ' N·m (whiskers on the totals: min–max, p5–p95, IQR)';
      }
    });
  }
  function niceTicks(lo, hi, n) {
    var span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / n))), err = span / n / step;
    if (err >= 7.5) step *= 10; else if (err >= 3.5) step *= 5; else if (err >= 1.5) step *= 2;
    var out = []; for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v / step) * step);
    return out;
  }
  function fmtTick(v) { return Math.abs(v) < 1e-9 ? '0' : Math.abs(v) >= 1 ? v.toFixed(Math.abs(v) % 1 ? 1 : 0) : v.toFixed(2); }
  (function legend() {
    [['target', RV.COMP.target], ['Δ model = feedforward − target', RV.rgba(RV.COMP.ff, 0.45)], ['feedforward', RV.COMP.ff], ['+ feedback', RV.COMP.fb], ['commanded (run colour)', '#8e5bd1'], ['Δ drive = applied − commanded', '#8a8983']].forEach(function (it) {
      var s = el('span', 'v5-lg', fallLegend); el('i', '', s).style.background = it[1]; s.appendChild(document.createTextNode(it[0]));
    });
  })();

  /* ---------- small time strips ---------- */
  var charts = [];
  function rebuildStrips() {
    charts.forEach(function (c) { c.destroy(); }); charts = [];
    strips.innerHTML = '';
    var f = state.focusRun(), w = RV.worstMoments(state, 3);
    [['shoulder error', '°', function () { var x = RV.repeatContent(state, 'err', 0, { zeroLine: true }); x.markers = w.filter(function (m) { return m.j === 0; }).map(function (m) { return { t: m.t }; }); return x; }],
     ['elbow error', '°', function () { var x = RV.repeatContent(state, 'err', 1, { zeroLine: true }); x.markers = w.filter(function (m) { return m.j === 1; }).map(function (m) { return { t: m.t }; }); return x; }],
     ['shoulder FB share', '%', function () { var x = RV.repeatContent(state, 'share', 0, {}); x.y = { min: 0, max: 60 }; return x; }]].forEach(function (row, k) {
      var r = el('div', 'v5-strip', strips);
      var lab = el('div', 'v5-strip-l', r); el('b', '', lab, row[0]); el('span', 'muted', lab, ' [' + row[1] + ']');
      var host = el('div', 'v5-strip-c', r);
      charts.push(RV.chart(host, { height: 66, xAxis: k === 2, syncKey: 'v5', ySize: 36, content: row[2] }, tr));
    });
  }

  function paint() { var T = state.T(); h1.textContent = T.title; sub.textContent = T.description; }
  function resize() { tr.charts.forEach(function (c) { c.resize(); }); viewer.resize(); paintFalls(tr.index()); }
  state.on(function (why) { if (why === 'target') { tr.reset(); } paint(); paintMoments(); rebuildStrips(); paintFalls(tr.index()); });
  paint(); paintMoments(); rebuildStrips();
  // open on the worst moment: the stage is about an instant, so it starts at the one that matters
  var f0 = state.focusRun(), j0 = f0.m[0].errMax >= f0.m[1].errMax ? 0 : 1;
  tr.t = f0.m[j0].errMaxT;
  viewer.pose(); tr.bars.forEach(function (b) { b.paint(); }); tr.charts.forEach(function (c) { if (c.u) c.u.redraw(false, false); });
  RV.onResize(resize);
  window.RVPAGE = { state: state, tr: tr };
})();
