/* Run-view layout round (2026-11-19) — the parts every variant shares, so the five layouts differ in
 * organisation, not in plumbing: fixture access, colours, repeat statistics, the page transport (time cursor +
 * x zoom, the same contract as traj_compare's plots.js makeTransport), a uPlot wrapper with band fills, the
 * TensorBoard-style run list, draggable/foldable side panels and the planar 2R arm in three.js.
 *
 * SIMULATED fixture: window.FIXTURE (fixture.js, written by run/build.py).
 */
var RV = (function () {
  'use strict';

  var F = window.FIXTURE;
  // WHY fixed component colours (CONTRACT.md): the same component reads the same on every card and in Rerun.
  var COMP = { target: '#8a8983', ff: '#3b82f6', fb: '#f97316' };
  var COMP_LABEL = { target: 'target', cmd: 'commanded', ff: 'feedforward', fb: 'feedback', applied: 'applied' };
  // WHY run colours avoid blue/orange: those two belong to feedforward/feedback.
  var GROUPS = {
    'sim': { color: '#52514e', label: 'Sim (ideal plant)', short: 'sim' },
    'ff v1': { color: '#8e5bd1', label: 'ff v1 nominal', short: 'ff v1' },
    'ff v2': { color: '#2f9e44', label: 'ff v2 calibrated', short: 'ff v2' },
  };
  var GROUP_ORDER = ['sim', 'ff v1', 'ff v2'];
  var AMBER = '#d79818';

  /* ---------------- small helpers ---------------- */

  function el(tag, className, parent, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }
  function hexToRgb(hex) {
    var v = parseInt(hex.slice(1), 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  function rgba(hex, alpha) {
    var c = hexToRgb(hex);
    return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + alpha + ')';
  }
  function mix(hex, other, t) {
    var a = hexToRgb(hex), b = hexToRgb(other);
    var c = a.map(function (v, i) { return Math.round(v + (b[i] - v) * t); });
    return '#' + c.map(function (v) { return ('0' + v.toString(16)).slice(-2); }).join('');
  }
  function fmt(value, digits) { return value == null || isNaN(value) ? '—' : value.toFixed(digits); }
  function deg(value, digits) { return fmt(value, digits == null ? 2 : digits) + '°'; }
  function nm(value, digits) { return fmt(value, digits == null ? 2 : digits) + ' N·m'; }
  function pct(value, digits) { return value == null ? '—' : (100 * value).toFixed(digits == null ? 0 : digits) + '%'; }
  function median(values) {
    if (!values.length) return null;
    var s = values.slice().sort(function (a, b) { return a - b; });
    var m = s.length >> 1;
    return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
  }
  function quantileSorted(s, q) {
    if (!s.length) return null;
    var pos = (s.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
    return s[lo] + (s[hi] - s[lo]) * (pos - lo);
  }
  function nearestIndex(grid, time) {
    var lo = 0, hi = grid.length - 1;
    if (time <= grid[0]) return 0;
    if (time >= grid[hi]) return hi;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (grid[mid] <= time) lo = mid; else hi = mid; }
    return time - grid[lo] < grid[hi] - time ? lo : hi;
  }

  /* ---------------- persistence (best effort: file:// may refuse) ---------------- */

  function store(key, value) { try { localStorage.setItem('rv-layouts:' + key, JSON.stringify(value)); } catch (e) {} }
  function recall(key, fallback) {
    try { var raw = localStorage.getItem('rv-layouts:' + key); return raw === null ? fallback : JSON.parse(raw); }
    catch (e) { return fallback; }
  }

  /* ---------------- derived per-run series ---------------- */

  function targetByName(name) {
    return F.targets.filter(function (t) { return t.name === name; })[0] || F.targets[0];
  }
  // run colour: the config group's hue, each repeat a slightly different shade (dark → light)
  F.targets.forEach(function (target) {
    GROUP_ORDER.forEach(function (key) {
      var members = target.runs.filter(function (r) { return r.group === key; });
      members.forEach(function (run, k) {
        var spread = members.length > 1 ? k / (members.length - 1) - 0.5 : 0;
        run.color = spread < 0 ? mix(GROUPS[key].color, '#000000', -spread * 0.5) : mix(GROUPS[key].color, '#ffffff', spread * 0.55);
        run.groupColor = GROUPS[key].color;
        run.target = target;
      });
    });
    target.duration = target.t[target.t.length - 1];
  });
  // q of a run on the grid: target − error (both already on the target's grid)
  function runQ(run, j) {
    if (!run._q) run._q = [];
    if (!run._q[j]) {
      var tq = run.target.q[j], e = run.err[j];
      run._q[j] = tq.map(function (v, i) { return v - e[i]; });
    }
    return run._q[j];
  }
  /* feedback share over time: Σ|fb| / (Σ|ff| + Σ|fb|) over a ±150 ms window. WHY the floor: where the command
     crosses zero both sums vanish and the raw ratio spikes to 100 % on noise; the denominator never drops below
     30 % of the run's mean |ff| + |fb|, so low-torque instants read low instead of spiking. */
  function fbShareSeries(run, j) {
    if (!run._share) run._share = [];
    if (!run._share[j]) {
      var ff = run.ff[j], fb = run.fb[j], n = ff.length, out = new Array(n), W = 15, mean = 0;
      for (var m = 0; m < n; m++) mean += Math.abs(ff[m]) + Math.abs(fb[m]);
      mean /= n;
      for (var i = 0; i < n; i++) {
        var a = 0, b = 0, c = 0;
        for (var k = Math.max(0, i - W); k <= Math.min(n - 1, i + W); k++) { a += Math.abs(ff[k]); b += Math.abs(fb[k]); c++; }
        out[i] = 100 * b / Math.max(a + b, 0.3 * mean * c, 1e-9);
      }
      run._share[j] = out;
    }
    return run._share[j];
  }
  function gapSeries(run, j) {
    if (!run._gap) run._gap = [];
    if (!run._gap[j]) run._gap[j] = run.cmd[j].map(function (v, i) { return v - run.applied[j][i]; });
    return run._gap[j];
  }
  function absErr(run) {  // max over joints of |error| on the grid
    if (!run._abs) {
      run._abs = run.err[0].map(function (v, i) {
        var m = 0; for (var j = 0; j < run.err.length; j++) m = Math.max(m, Math.abs(run.err[j][i]));
        return m;
      });
    }
    return run._abs;
  }
  function series(run, key, j) {
    if (key === 'share') return fbShareSeries(run, j);
    if (key === 'gap') return gapSeries(run, j);
    if (key === 'q') return runQ(run, j);
    if (key === 'tipErr') return run.tipErr;
    return run[key][j];
  }
  // percentile bands across runs at every sample
  function bands(runs, key, j) {
    if (!runs.length) return null;
    var cols = runs.map(function (r) { return series(r, key, j); });
    var n = cols[0].length;
    var out = { min: new Array(n), p5: new Array(n), p25: new Array(n), med: new Array(n), p75: new Array(n), p95: new Array(n), max: new Array(n) };
    var buf = new Array(cols.length);
    for (var i = 0; i < n; i++) {
      for (var c = 0; c < cols.length; c++) buf[c] = cols[c][i];
      buf.sort(function (a, b) { return a - b; });
      out.min[i] = buf[0]; out.max[i] = buf[buf.length - 1];
      out.p5[i] = quantileSorted(buf, 0.05); out.p95[i] = quantileSorted(buf, 0.95);
      out.p25[i] = quantileSorted(buf, 0.25); out.p75[i] = quantileSorted(buf, 0.75);
      out.med[i] = quantileSorted(buf, 0.5);
    }
    return out;
  }
  function metricMedian(runs, fn) { return median(runs.map(fn)); }

  /* ---------------- page state ---------------- */

  function makeState(variant, options) {
    options = options || {};
    var prefix = variant + ':';
    var s = {
      variant: variant,
      target: recall(prefix + 'target', 'full-circle-slow'),
      hidden: recall(prefix + 'hidden', {}),
      solo: null,
      focus: recall(prefix + 'focus', {}),   // per target: run name
      groupBy: recall(prefix + 'groupBy', 'config'),
      filter: '',
      mode: recall(prefix + 'mode', 'auto'),  // auto | lines | bands
      threshold: 5,
      joint: 0,
      listeners: [],
    };
    if (!F.targets.some(function (t) { return t.name === s.target; })) s.target = 'full-circle-slow';
    s.T = function () { return targetByName(s.target); };
    s.runs = function () { return s.T().runs; };
    s.matches = function (run) {
      if (!s.filter) return true;
      try { return new RegExp(s.filter, 'i').test(run.title + ' ' + run.id + ' ' + run.group + ' ' + run.tags.date); }
      catch (e) { return (run.title + ' ' + run.id).toLowerCase().indexOf(s.filter.toLowerCase()) >= 0; }
    };
    s.isVisible = function (run) {
      if (s.solo) return run.name === s.solo;
      return !s.hidden[run.name] && s.matches(run);
    };
    s.visibleRuns = function () { return s.runs().filter(s.isVisible); };
    s.realRuns = function () { return s.runs().filter(function (r) { return r.kind === 'real'; }); };
    // default focus: the worst real run on the scorecard (largest L2-tip RMS), as the contract's Rerun tab does
    s.worstRun = function (runs) {
      runs = (runs || s.visibleRuns()).filter(function (r) { return r.kind === 'real'; });
      if (!runs.length) runs = s.visibleRuns();
      return runs.slice().sort(function (a, b) { return b.tip.rms - a.tip.rms; })[0] || s.runs()[0];
    };
    s.focusRun = function () {
      var name = s.focus[s.target];
      var run = s.runs().filter(function (r) { return r.name === name; })[0];
      return run || s.worstRun(s.realRuns());
    };
    s.groups = function (runs) {
      runs = runs || s.visibleRuns();
      return GROUP_ORDER.map(function (key) {
        return { key: key, label: GROUPS[key].label, short: GROUPS[key].short, color: GROUPS[key].color, runs: runs.filter(function (r) { return r.group === key; }) };
      }).filter(function (g) { return g.runs.length; });
    };
    // how a group draws its repeats: lines for a few, a band for many (or forced)
    s.asBand = function (count) {
      if (count < 3) return false;
      if (s.mode === 'lines') return false;
      if (s.mode === 'bands') return true;
      return count > s.threshold;
    };
    s.set = function (patch, why) {
      Object.keys(patch).forEach(function (k) { s[k] = patch[k]; });
      if ('target' in patch) store(prefix + 'target', s.target);
      if ('hidden' in patch) store(prefix + 'hidden', s.hidden);
      if ('focus' in patch) store(prefix + 'focus', s.focus);
      if ('groupBy' in patch) store(prefix + 'groupBy', s.groupBy);
      if ('mode' in patch) store(prefix + 'mode', s.mode);
      s.emit(why || Object.keys(patch).join(','));
    };
    s.setFocus = function (name) {
      var f = Object.assign({}, s.focus); f[s.target] = name; s.set({ focus: f }, 'focus');
    };
    s.emit = function (why) { s.listeners.slice().forEach(function (fn) { fn(why); }); };
    s.on = function (fn) { s.listeners.push(fn); };
    return s;
  }

  /* ---------------- transport: the page's shared time + zoom ---------------- */

  function makeTransport(state) {
    var tr = { t: null, hover: null, zoom: null, playing: false, listeners: [], charts: [], bars: [] };
    tr.grid = function () { return state.T().t; };
    tr.tMax = function () { var g = tr.grid(); return g[g.length - 1]; };
    tr.committed = function () { return tr.t === null ? tr.tMax() : tr.t; };
    tr.now = function () { return tr.hover !== null ? tr.hover : tr.committed(); };
    tr.index = function () { return nearestIndex(tr.grid(), tr.now()); };
    tr.on = function (fn) { tr.listeners.push(fn); };
    function emit(kind) {
      tr.listeners.forEach(function (fn) { fn(kind); });
      tr.bars.forEach(function (bar) { bar.paint(); });
      if (kind === 'scrub') tr.charts.forEach(function (c) { if (c.u) c.u.redraw(false, false); });
    }
    tr.setHover = function (time) { if (tr.hover === time) return; tr.hover = time; emit('hover'); };
    tr.setScrub = function (time) {
      tr.t = Math.max(0, Math.min(tr.tMax(), time));
      emit('scrub');
    };
    tr.setZoom = function (range, source) {
      tr.zoom = range;
      tr.charts.forEach(function (c) {
        if (!c.u || c === source) return;
        c._syncing = true;
        c.u.setScale('x', range ? { min: range.min, max: range.max } : { min: tr.grid()[0], max: tr.tMax() });
        c._syncing = false;
      });
      emit('zoom');
    };
    tr.focusOn = function (time, halfWidth) {
      halfWidth = halfWidth || 0.6;
      tr.pause();
      tr.setZoom({ min: Math.max(0, time - halfWidth), max: Math.min(tr.tMax(), time + halfWidth) });
      tr.setScrub(time);
    };
    tr.reset = function () { tr.pause(); tr.t = null; tr.hover = null; tr.zoom = null; emit('scrub'); };
    var raf = null, last = null;
    function tick(now) {
      if (!tr.playing) return;
      if (last !== null) {
        var next = tr.committed() + (now - last) / 1000;
        if (next >= tr.tMax()) { tr.t = tr.tMax(); tr.playing = false; emit('scrub'); return; }
        tr.t = next; emit('scrub');
      }
      last = now; raf = requestAnimationFrame(tick);
    }
    tr.play = function () {
      if (tr.playing) return;
      if (tr.committed() >= tr.tMax() - 1e-6) tr.t = 0;
      tr.playing = true; last = null; raf = requestAnimationFrame(tick); emit('play');
    };
    tr.pause = function () { if (!tr.playing) return; tr.playing = false; if (raf) cancelAnimationFrame(raf); emit('play'); };
    tr.toggle = function () { if (tr.playing) tr.pause(); else tr.play(); };
    tr.stepBy = function (n) {
      tr.pause();
      var g = tr.grid(), i = nearestIndex(g, tr.committed());
      tr.setScrub(g[Math.max(0, Math.min(g.length - 1, i + n))]);
    };
    return tr;
  }

  // traj_compare's transport bar markup (tc-transport / tc-tbtn / tc-scrub / tc-time) + optional extras
  function transportBar(tr, parent, extras) {
    var bar = el('div', 'tc-transport rv-transport', parent);
    var handle = { selfDriving: false };
    function btn(label, title, fn) { var b = el('button', 'tc-tbtn', bar, label); b.title = title; b.onclick = fn; return b; }
    btn('⏮', 'to start', function () { tr.pause(); tr.setScrub(0); });
    btn('◀', 'step back', function () { tr.stepBy(-1); });
    var play = btn('▶', 'play / pause', function () { tr.toggle(); });
    btn('▶', 'step forward', function () { tr.stepBy(1); });
    btn('⏭', 'to end', function () { tr.pause(); tr.setScrub(tr.tMax()); });
    var slider = el('input', 'tc-scrub', bar);
    slider.type = 'range'; slider.min = 0; slider.step = 0.001;
    slider.addEventListener('input', function () {
      handle.selfDriving = true; tr.pause(); tr.setScrub(parseFloat(slider.value)); handle.selfDriving = false;
    });
    var readout = el('span', 'tc-time', bar);
    (extras || []).forEach(function (x) { bar.appendChild(x); });
    handle.paint = function () {
      slider.max = tr.tMax();
      if (!handle.selfDriving) slider.value = tr.committed();
      readout.textContent = tr.committed().toFixed(2) + ' / ' + tr.tMax().toFixed(2) + ' s';
      play.textContent = tr.playing ? '⏸' : '▶';
    };
    tr.bars.push(handle);
    handle.paint();
    return bar;
  }

  /* ---------------- chart: uPlot + band fills + transport cursor ---------------- */

  /* content(): {lines: [{values, stroke, width, dash, fill, label}], fills: [{lo, hi, color}],
                 markers: [{t, color}], y: {min, max} | null, zeroLine: bool}
     Fills are drawn under the series by a drawClear hook (robust when the edges cross — the feedback wedge
     between feedforward and commanded changes sign), and their edges ride along as invisible series so the
     y autoscale includes them. */
  function chart(parent, opts, tr) {
    var c = { opts: opts, u: null, el: el('div', 'rv-chart', parent), _syncing: false };
    c.el.style.height = (opts.height || 150) + 'px';
    var downX = null;
    function build() {
      var content = opts.content();
      var grid = tr.grid();
      var data = [grid], ser = [{}];
      (content.fills || []).forEach(function (f) {
        data.push(f.lo); data.push(f.hi);
        ser.push({ stroke: 'transparent', width: 0, points: { show: false } });
        ser.push({ stroke: 'transparent', width: 0, points: { show: false } });
      });
      (content.lines || []).forEach(function (line) {
        data.push(line.values);
        ser.push({
          label: line.label || '', stroke: line.stroke, width: line.width || 1.4, dash: line.dash,
          fill: line.fill || undefined, fillTo: line.fill ? 0 : undefined, points: { show: false },
          alpha: line.alpha == null ? 1 : line.alpha,
        });
      });
      var width = Math.max(120, c.el.clientWidth || parent.clientWidth || 300);
      var height = opts.height || 150;
      var yScale = content.y ? { range: function () { return [content.y.min, content.y.max]; } } : {};
      var u = new uPlot({
        width: width, height: height, series: ser, legend: { show: false },
        scales: { x: { time: false }, y: yScale },
        cursor: { drag: { x: true, y: false }, points: { size: 5 }, sync: { key: opts.syncKey || 'rv' } },
        axes: [
          { stroke: '#8a8983', grid: { stroke: '#e6e5e0', width: 0.5 }, ticks: { stroke: '#c9c8c2', width: 0.5 }, size: opts.xAxis === false ? 4 : 24, show: opts.xAxis !== false, font: '10px -apple-system, Segoe UI, Roboto, sans-serif' },
          { stroke: '#8a8983', grid: { stroke: '#e6e5e0', width: 0.5 }, ticks: { stroke: '#c9c8c2', width: 0.5 }, size: opts.ySize || 40, font: '10px -apple-system, Segoe UI, Roboto, sans-serif', values: opts.yValues },
        ],
        hooks: {
          drawClear: [function (u) {
            var fills = content.fills || [];
            var ctx = u.ctx, xs = u.data[0];
            ctx.save();
            ctx.beginPath(); ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height); ctx.clip();
            if (content.zeroLine) {
              var y0 = Math.round(u.valToPos(0, 'y', true)) + 0.5;
              ctx.strokeStyle = '#c9c8c2'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(u.bbox.left, y0); ctx.lineTo(u.bbox.left + u.bbox.width, y0); ctx.stroke();
            }
            fills.forEach(function (f) {
              ctx.beginPath();
              var first = true;
              for (var i = 0; i < xs.length; i++) {
                if (f.hi[i] == null) continue;
                var x = u.valToPos(xs[i], 'x', true), y = u.valToPos(f.hi[i], 'y', true);
                if (first) { ctx.moveTo(x, y); first = false; } else ctx.lineTo(x, y);
              }
              for (var k = xs.length - 1; k >= 0; k--) {
                if (f.lo[k] == null) continue;
                ctx.lineTo(u.valToPos(xs[k], 'x', true), u.valToPos(f.lo[k], 'y', true));
              }
              ctx.closePath(); ctx.fillStyle = f.color; ctx.fill();
            });
            ctx.restore();
          }],
          draw: [function (u) {
            var ctx = u.ctx;
            ctx.save();
            ctx.beginPath(); ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height); ctx.clip();
            (content.markers || []).forEach(function (m) {
              var x = Math.round(u.valToPos(m.t, 'x', true)) + 0.5;
              ctx.strokeStyle = m.color || AMBER; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
              ctx.beginPath(); ctx.moveTo(x, u.bbox.top); ctx.lineTo(x, u.bbox.top + u.bbox.height); ctx.stroke();
              ctx.setLineDash([]); ctx.fillStyle = m.color || AMBER;
              ctx.beginPath(); ctx.moveTo(x - 4, u.bbox.top); ctx.lineTo(x + 4, u.bbox.top); ctx.lineTo(x, u.bbox.top + 6); ctx.fill();
            });
            if (tr.t !== null) {
              var xt = Math.round(u.valToPos(tr.t, 'x', true)) + 0.5;
              ctx.strokeStyle = '#2a78d6'; ctx.lineWidth = 1.5;
              ctx.beginPath(); ctx.moveTo(xt, u.bbox.top); ctx.lineTo(xt, u.bbox.top + u.bbox.height); ctx.stroke();
            }
            ctx.restore();
          }],
          setScale: [function (u, key) {
            if (key !== 'x' || c._syncing || !u._ready) return;
            var g = tr.grid(), sc = u.scales.x;
            var full = sc.min <= g[0] + 1e-9 && sc.max >= g[g.length - 1] - 1e-9;
            tr.setZoom(full ? null : { min: sc.min, max: sc.max }, c);
          }],
          setCursor: [function (u) {
            if (c._syncing) return;
            var i = u.cursor.idx;
            tr.setHover(i == null ? null : u.data[0][i]);
          }],
          ready: [function (u) { u._ready = true; }],
        },
      }, data, c.el);
      if (tr.zoom) { c._syncing = true; u.setScale('x', tr.zoom); c._syncing = false; }
      u.over.addEventListener('mousedown', function (e) { downX = e.clientX; });
      u.over.addEventListener('click', function (e) {
        if (downX !== null && Math.abs(e.clientX - downX) > 3) return;
        var i = u.cursor.idx;
        if (i != null) { tr.pause(); tr.setScrub(u.data[0][i]); }
      });
      u.over.addEventListener('mouseleave', function () { tr.setHover(null); });
      return u;
    }
    c.refresh = function () {
      if (c.u) c.u.destroy();
      c.el.innerHTML = '';
      c.u = build();
    };
    c.resize = function () {
      if (!c.u) return;
      var w = Math.max(120, c.el.clientWidth);
      if (Math.abs(w - c.u.width) > 1) c.u.setSize({ width: w, height: opts.height || 150 });
    };
    c.destroy = function () {
      if (c.u) c.u.destroy();
      c.u = null;
      var at = tr.charts.indexOf(c); if (at >= 0) tr.charts.splice(at, 1);
      c.el.remove();
    };
    tr.charts.push(c);
    c.refresh();
    return c;
  }
  // one band set (min–max, p5–p95, IQR) + median line for a group
  function bandFills(b, color, strength) {
    var k = strength == null ? 1 : strength;
    return [
      { lo: b.min, hi: b.max, color: rgba(color, 0.07 * k) },
      { lo: b.p5, hi: b.p95, color: rgba(color, 0.13 * k) },
      { lo: b.p25, hi: b.p75, color: rgba(color, 0.24 * k) },
    ];
  }
  // the repeat encoding every variant uses for a signal: per group, lines (few) or bands (many), focus run on top
  function repeatContent(state, key, j, opts) {
    opts = opts || {};
    var lines = [], fills = [];
    var focus = state.focusRun();
    state.groups().forEach(function (g) {
      if (state.asBand(g.runs.length)) {
        var b = bands(g.runs, key, j);
        fills = fills.concat(bandFills(b, g.color, opts.bandStrength));
        lines.push({ values: b.med, stroke: g.color, width: 1.3, label: g.label + ' median' });
      } else {
        g.runs.forEach(function (r) {
          if (r === focus) return;
          lines.push({ values: series(r, key, j), stroke: r.color, width: 1.1, alpha: g.runs.length > 3 ? 0.7 : 0.9, label: r.title });
        });
      }
    });
    if (opts.target) lines.unshift({ values: opts.target, stroke: COMP.target, width: 1.3, dash: [6, 4], label: 'target' });
    if (focus && state.isVisible(focus) && opts.focus !== false) {
      lines.push({ values: series(focus, key, j), stroke: focus.color, width: 2.1, label: focus.title });
    }
    return { lines: lines, fills: fills, zeroLine: !!opts.zeroLine };
  }

  /* ---------------- panels: draggable width (remembered) + fold ---------------- */

  /* panel: the side element; side: 'left' | 'right'; the handle is inserted on the inner edge.
     WHY (Zach's UI rule): every side-panel boundary is draggable, its width remembered, the panel foldable. */
  function sidePanel(panel, key, options) {
    options = options || {};
    var side = options.side || 'left';
    var min = options.min || 200, max = options.max || 520;
    var width = recall('w:' + key, options.width || 270);
    var folded = recall('fold:' + key, false);
    var handle = el('div', 'rv-split rv-split-' + side);
    handle.title = 'drag to resize · double-click to fold';
    if (side === 'left') panel.after(handle); else panel.before(handle);
    var rail = el('button', 'rv-rail rv-rail-' + side);
    rail.title = 'show ' + (options.label || 'panel');
    el('span', 'rv-rail-icon', rail, side === 'left' ? '»' : '«');
    el('span', 'rv-rail-label', rail, options.label || 'Panel');
    if (side === 'left') panel.before(rail); else panel.after(rail);
    var api = { onChange: options.onChange || function () {} };
    function apply(initial) {
      panel.style.width = width + 'px';
      panel.style.flex = '0 0 ' + width + 'px';
      panel.style.display = folded ? 'none' : '';
      handle.style.display = folded ? 'none' : '';
      rail.style.display = folded ? '' : 'none';
      if (!initial) api.onChange();
    }
    api.fold = function (value) { folded = value; store('fold:' + key, folded); apply(); };
    api.folded = function () { return folded; };
    api.width = function () { return width; };
    rail.onclick = function () { api.fold(false); };
    handle.addEventListener('dblclick', function () { api.fold(true); });
    handle.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      handle.classList.add('dragging');
      var startX = e.clientX, startW = width;
      function move(ev) {
        var dx = ev.clientX - startX;
        width = Math.max(min, Math.min(max, startW + (side === 'left' ? dx : -dx)));
        panel.style.width = width + 'px'; panel.style.flex = '0 0 ' + width + 'px';
        api.onChange();
      }
      function up() {
        handle.classList.remove('dragging');
        handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', up);
        store('w:' + key, width);
        api.onChange();
      }
      handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', up);
    });
    if (options.foldButton) options.foldButton.onclick = function () { api.fold(true); };
    apply(true);
    return api;
  }

  /* ---------------- the run list (TensorBoard's left sidebar, grouped by target) ---------------- */

  /* options: {metric: {label, value(run) -> number, text(run) -> string, bar: bool, max}, compact: bool, title} */
  function runList(parent, state, options) {
    options = options || {};
    var root = el('div', 'rv-runs', parent);
    var head = el('div', 'rv-runs-head', root);
    el('div', 'rv-runs-title', head, options.title || 'Runs');
    var count = el('span', 'rv-runs-count', head);
    var fold = el('button', 'rv-fold', head, '«');
    fold.title = 'fold the run list';
    var tsel = el('label', 'rv-field', root);
    if (options.targetSelect === false) tsel.style.display = 'none';
    el('span', 'rv-field-label', tsel, 'Target');
    var select = el('select', 'rv-select', tsel);
    F.targets.forEach(function (t) {
      var o = el('option', '', select, t.title + '  ·  ' + t.runs.length + ' runs');
      o.value = t.name;
    });
    select.onchange = function () { state.set({ target: select.value, solo: null }, 'target'); };
    var filter = el('input', 'rv-filter', root);
    filter.placeholder = 'Filter runs (regex)';
    filter.oninput = function () { state.set({ filter: filter.value }, 'filter'); };
    var gb = el('div', 'rv-groupby', root);
    el('span', 'rv-field-label', gb, 'Group by');
    var gbs = el('div', 'rv-seg', gb);
    [['config', 'config'], ['date', 'date'], ['kind', 'kind']].forEach(function (opt) {
      var b = el('button', '', gbs, opt[1]);
      b.dataset.v = opt[0];
      b.onclick = function () { state.set({ groupBy: opt[0] }, 'groupBy'); };
    });
    if (options.metric) {
      var mh = el('div', 'rv-metric-head', root);
      el('span', '', mh, 'run');
      el('span', '', mh, options.metric.label);
    }
    var list = el('div', 'rv-runs-list', root);
    var foot = el('div', 'rv-runs-foot', root);
    if (options.modeControl !== false) {
      el('span', 'rv-field-label', foot, 'Repeats');
      var seg = el('div', 'rv-seg', foot);
      [['auto', 'Auto'], ['lines', 'Lines'], ['bands', 'Bands']].forEach(function (m) {
        var b = el('button', '', seg, m[1]);
        b.dataset.v = m[0];
        b.title = m[0] === 'auto' ? 'lines for ≤ ' + state.threshold + ' runs in a group, bands past that' : m[0] === 'lines' ? 'every run as its own line' : 'median + IQR + p5–p95 + min–max';
        b.onclick = function () { state.set({ mode: m[0] }, 'mode'); };
      });
    }
    var keyNote = el('div', 'rv-keynote', foot);

    function groupKey(run) {
      if (state.groupBy === 'date') return run.tags.date;
      if (state.groupBy === 'kind') return run.kind;
      return run.group;
    }
    function groupLabel(key) {
      if (state.groupBy === 'config') return GROUPS[key].label;
      if (state.groupBy === 'kind') return key === 'sim' ? 'sim' : 'real';
      return key;
    }
    function paint() {
      select.value = state.target;
      if (filter.value !== state.filter) filter.value = state.filter;
      gbs.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.dataset.v === state.groupBy); });
      if (seg) seg.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.dataset.v === state.mode); });
      var runs = state.runs();
      var vis = state.visibleRuns();
      count.textContent = vis.length + ' / ' + runs.length;
      list.innerHTML = '';
      var keys = [];
      runs.forEach(function (r) { var k = groupKey(r); if (keys.indexOf(k) < 0) keys.push(k); });
      var focus = state.focusRun();
      var metricMax = options.metric ? (options.metric.max || Math.max.apply(null, runs.map(options.metric.value))) : 1;
      keys.forEach(function (k) {
        var members = runs.filter(function (r) { return groupKey(r) === k; });
        var shown = members.filter(state.isVisible);
        var g = el('div', 'rv-group', list);
        var gh = el('div', 'rv-group-head', g);
        var cb = el('input', '', gh); cb.type = 'checkbox';
        cb.checked = shown.length === members.length && !state.solo;
        cb.indeterminate = shown.length > 0 && shown.length < members.length;
        cb.title = 'select all / none in this group';
        cb.onclick = function (e) {
          e.stopPropagation();
          var hidden = Object.assign({}, state.hidden), on = !(shown.length === members.length);
          members.forEach(function (r) { if (on) delete hidden[r.name]; else hidden[r.name] = true; });
          state.set({ hidden: hidden, solo: null }, 'hidden');
        };
        if (state.groupBy === 'config') el('span', 'rv-gswatch', gh).style.background = GROUPS[k].color;
        el('span', 'rv-gname', gh, groupLabel(k));
        var med = options.metric ? median(shown.map(options.metric.value)) : null;
        el('span', 'rv-gmeta', gh, members.length + (options.metric && med != null && shown.length > 1 ? ' · med ' + options.metric.text(med) : ''));
        members.forEach(function (r) {
          var row = el('div', 'rv-run' + (state.isVisible(r) ? '' : ' off') + (r === focus ? ' focus' : ''), g);
          row.dataset.run = r.name;
          var rcb = el('input', '', row); rcb.type = 'checkbox';
          rcb.checked = state.isVisible(r);
          rcb.title = 'show / hide';
          rcb.onclick = function (e) {
            e.stopPropagation();
            var hidden = Object.assign({}, state.hidden);
            if (state.solo) { state.set({ solo: null }, 'solo'); return; }
            if (hidden[r.name]) delete hidden[r.name]; else hidden[r.name] = true;
            state.set({ hidden: hidden }, 'hidden');
          };
          el('span', 'rv-swatch', row).style.background = r.color;
          var name = el('span', 'rv-rname', row, r.title);
          name.title = r.name + ' · ' + r.tags.date + ' · kt error ' + (100 * r.tags.kt_error).toFixed(1) + '% · offset ' + r.tags.start_offset_ms + ' ms';
          if (options.metric) {
            var mv = options.metric.value(r);
            var cell = el('span', 'rv-rmetric', row);
            if (options.metric.bar) {
              var track = el('span', 'rv-mbar', cell);
              var fillEl = el('span', 'rv-mfill', track);
              fillEl.style.width = Math.max(2, 100 * mv / metricMax) + '%';
              fillEl.style.background = options.metric.barColor || COMP.fb;
            }
            el('span', 'rv-mval', cell, options.metric.text(mv));
          }
          var solo = el('button', 'rv-solo' + (state.solo === r.name ? ' on' : ''), row, 'S');
          solo.title = state.solo === r.name ? 'un-solo' : 'solo: show only this run';
          solo.onclick = function (e) { e.stopPropagation(); state.set({ solo: state.solo === r.name ? null : r.name }, 'solo'); };
          row.onclick = function () { state.setFocus(r.name); };
          row.title = 'click: highlight this run against the band';
        });
      });
      keyNote.textContent = state.solo ? 'Solo: ' + state.runs().filter(function (r) { return r.name === state.solo; })[0].title : 'Click a run to highlight it against its band';
    }
    state.on(paint);
    paint();
    return { root: root, fold: fold, paint: paint };
  }

  /* ---------------- component legend chips (toggle a component on every card) ---------------- */

  function componentLegend(parent, shown, onToggle, run) {
    var box = el('div', 'rv-complegend', parent);
    var items = [
      ['target', 'target', COMP.target, 'dashed'],
      ['cmd', 'commanded', run ? run.color : '#22211f', 'thick'],
      ['ff', 'feedforward', COMP.ff, ''],
      ['fb', 'feedback', COMP.fb, 'fill'],
      ['applied', 'applied', run ? mix(run.color, '#000000', 0.35) : '#555', 'thin'],
    ];
    items.forEach(function (it) {
      var chip = el('button', 'chip rv-comp ' + (shown[it[0]] ? 'on' : 'off'), box);
      var sw = el('span', 'swatch rv-sw-' + it[3], chip);
      sw.style.background = it[3] === 'dashed' ? 'none' : it[2];
      sw.style.color = it[2];
      chip.appendChild(document.createTextNode(it[1]));
      chip.onclick = function () { shown[it[0]] = !shown[it[0]]; onToggle(); };
    });
    return box;
  }
  // the contract's five traces for one run and joint
  function breakdownLines(run, j, shown, target) {
    var lines = [], fills = [];
    shown = shown || { target: true, cmd: true, ff: true, fb: true, applied: true };
    if (shown.fb) fills.push({ lo: run.fb[j].map(function () { return 0; }), hi: run.fb[j], color: rgba(COMP.fb, 0.16) });
    if (shown.target) lines.push({ values: target.tau[j], stroke: COMP.target, width: 1.4, dash: [6, 4], label: 'target' });
    if (shown.ff) lines.push({ values: run.ff[j], stroke: COMP.ff, width: 1.4, label: 'feedforward' });
    if (shown.fb) lines.push({ values: run.fb[j], stroke: COMP.fb, width: 1.3, label: 'feedback' });
    if (shown.cmd) lines.push({ values: run.cmd[j], stroke: run.color, width: 2.4, label: 'commanded' });
    if (shown.applied) lines.push({ values: run.applied[j], stroke: mix(run.color, '#000000', 0.35), width: 0.9, label: 'applied' });
    return { lines: lines, fills: fills, zeroLine: true };
  }

  /* ---------------- the planar 2R arm (three.js) ---------------- */

  /* The fixture's arm is vertical (gravity −y): links rotate about z by q1 and q1 + q2, so the camera looks
     along −z with y up. Target = grey ghost; focus run = its colour; other visible runs = faint stick ghosts. */
  function arm3d(parent, state, tr, options) {
    options = options || {};
    var box = el('div', 'rv-3d', parent);
    var canvas = el('canvas', '', box);
    var hud = el('div', 'rv-3dhud', box);
    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(options.background || 0xfcfcfb);
    var camera = new THREE.PerspectiveCamera(32, 1.5, 0.01, 20);
    var view = recall('3dview:' + state.variant, { az: 0.35, el: 0.18, dist: options.dist || 1.75 });
    scene.add(new THREE.AmbientLight(0xffffff, 1.6));
    var sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(0.6, 1.0, 1.4); scene.add(sun);
    var wall = new THREE.GridHelper(1.3, 13, 0xd0cfc9, 0xe6e5e0);
    wall.rotation.x = Math.PI / 2; wall.position.z = -0.04; scene.add(wall);
    var floorMat = new THREE.LineBasicMaterial({ color: 0xb9b8b2 });
    var axisY = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, -0.62, -0.04), new THREE.Vector3(0, 0.62, -0.04)]);
    scene.add(new THREE.Line(axisY, floorMat));
    var base = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.07, 0.06), new THREE.MeshLambertMaterial({ color: 0x3a3a37 }));
    base.position.z = -0.02; scene.add(base);
    var grav = new THREE.ArrowHelper(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0.5, 0.42, 0), 0.14, 0x8a8983, 0.035, 0.022);
    scene.add(grav);
    var gLabel = textSprite('g', '#8a8983'); gLabel.position.set(0.535, 0.38, 0); scene.add(gLabel);
    var L1 = F.links[0], L2 = F.links[1];

    function makeArm(color, opacity, thick) {
      var mat = opacity < 1
        ? new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: opacity, depthWrite: false })
        : new THREE.MeshLambertMaterial({ color: color });
      var g1 = new THREE.Group(), g2 = new THREE.Group();
      var m1 = new THREE.Mesh(new THREE.BoxGeometry(L1, thick, thick), mat); m1.position.x = L1 / 2; g1.add(m1);
      var m2 = new THREE.Mesh(new THREE.BoxGeometry(L2, thick * 0.8, thick * 0.8), mat); m2.position.x = L2 / 2; g2.add(m2);
      var jm = new THREE.Mesh(new THREE.CylinderGeometry(thick * 0.75, thick * 0.75, thick * 1.3, 18), mat);
      jm.rotation.x = Math.PI / 2; g2.add(jm);
      g2.position.x = L1; g1.add(g2); scene.add(g1);
      return { g1: g1, g2: g2, mat: mat, set: function (q1, q2) { g1.rotation.z = q1; g2.rotation.z = q2; } };
    }
    var ghost = makeArm(0x8a8983, 0.32, 0.034);
    var arm = makeArm(0x8e5bd1, 1, 0.03);
    // stick ghosts for other visible runs
    var sticksGeo = new THREE.BufferGeometry();
    var sticksMat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.45 });
    var sticks = new THREE.LineSegments(sticksGeo, sticksMat); scene.add(sticks);
    var paths = new THREE.Group(); scene.add(paths);
    var marker = new THREE.Mesh(new THREE.SphereGeometry(0.011, 16, 12), new THREE.MeshBasicMaterial({ color: 0xd79818 }));
    scene.add(marker);

    function tipXY(q1, q2) { return [L1 * Math.cos(q1) + L2 * Math.cos(q1 + q2), L1 * Math.sin(q1) + L2 * Math.sin(q1 + q2)]; }
    function rebuildPaths() {
      while (paths.children.length) { var ch = paths.children.pop(); ch.geometry.dispose(); }
      var T = state.T(), focus = state.focusRun();
      var tp = T.t.map(function (_, i) { var p = tipXY(T.q[0][i] * Math.PI / 180, T.q[1][i] * Math.PI / 180); return new THREE.Vector3(p[0], p[1], 0); });
      var tl = new THREE.Line(new THREE.BufferGeometry().setFromPoints(tp), new THREE.LineDashedMaterial({ color: 0x8a8983, dashSize: 0.012, gapSize: 0.008 }));
      tl.computeLineDistances(); paths.add(tl);
      if (focus) {
        var fq0 = runQ(focus, 0), fq1 = runQ(focus, 1);
        // error is a few degrees: the run's tip path drawn 6× exaggerated off the target path, so it is visible
        var k = options.exaggerate || 1;
        var fp = T.t.map(function (_, i) {
          var a = tipXY(T.q[0][i] * Math.PI / 180, T.q[1][i] * Math.PI / 180), b = tipXY(fq0[i] * Math.PI / 180, fq1[i] * Math.PI / 180);
          return new THREE.Vector3(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, 0.002);
        });
        paths.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(fp), new THREE.LineBasicMaterial({ color: new THREE.Color(focus.color) })));
        var wi = nearestIndex(T.t, focus.tip.maxT);
        marker.position.set(fp[wi].x, fp[wi].y, 0.004);
        marker.visible = options.worstMarker !== false;
        arm.mat.color = new THREE.Color(focus.color);
      }
    }
    function pose() {
      var T = state.T(), i = tr.index(), focus = state.focusRun();
      ghost.set(T.q[0][i] * Math.PI / 180, T.q[1][i] * Math.PI / 180);
      if (focus) arm.set(runQ(focus, 0)[i] * Math.PI / 180, runQ(focus, 1)[i] * Math.PI / 180);
      arm.g1.visible = !!focus && state.isVisible(focus);
      var pos = [], col = [];
      if (options.ghosts !== false) {
        state.visibleRuns().forEach(function (r) {
          if (r === focus) return;
          var q1 = runQ(r, 0)[i] * Math.PI / 180, q2 = runQ(r, 1)[i] * Math.PI / 180;
          var e = [L1 * Math.cos(q1), L1 * Math.sin(q1)], t = tipXY(q1, q2);
          var c = new THREE.Color(r.color);
          pos.push(0, 0, 0.02, e[0], e[1], 0.02, e[0], e[1], 0.02, t[0], t[1], 0.02);
          for (var k = 0; k < 4; k++) col.push(c.r, c.g, c.b);
        });
      }
      sticksGeo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      sticksGeo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
      if (options.onPose) options.onPose(i, hud);
      else hud.textContent = 't = ' + T.t[i].toFixed(2) + ' s';
      render();
    }
    function applyCamera() {
      var d = view.dist;
      camera.position.set(d * Math.sin(view.az) * Math.cos(view.el), d * Math.sin(view.el) + 0.02, d * Math.cos(view.az) * Math.cos(view.el));
      camera.up.set(0, 1, 0);
      camera.lookAt(0, options.lookY || 0, 0);
    }
    function render() { applyCamera(); renderer.render(scene, camera); }
    function resize() {
      var w = box.clientWidth, h = options.height ? options.height : box.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
      camera.aspect = w / h; camera.updateProjectionMatrix();
      render();
    }
    if (options.height) box.style.height = options.height + 'px';
    var drag = null;
    canvas.addEventListener('pointerdown', function (e) { drag = { x: e.clientX, y: e.clientY, az: view.az, el: view.el }; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener('pointermove', function (e) {
      if (!drag) return;
      view.az = drag.az - (e.clientX - drag.x) * 0.008;
      view.el = Math.max(-1.2, Math.min(1.2, drag.el + (e.clientY - drag.y) * 0.008));
      render();
    });
    canvas.addEventListener('pointerup', function () { drag = null; store('3dview:' + state.variant, view); });
    canvas.addEventListener('wheel', function (e) { e.preventDefault(); view.dist = Math.max(0.7, Math.min(4, view.dist * (1 + Math.sign(e.deltaY) * 0.1))); render(); store('3dview:' + state.variant, view); }, { passive: false });
    canvas.addEventListener('dblclick', function () { view = { az: 0.35, el: 0.18, dist: options.dist || 1.75 }; render(); store('3dview:' + state.variant, view); });
    var dead = false, ro = null;
    tr.on(function (kind) { if (!dead && kind !== 'zoom') pose(); });
    state.on(function () { if (!dead) { rebuildPaths(); pose(); } });
    if (window.ResizeObserver) { ro = new ResizeObserver(function () { if (!dead) resize(); }); ro.observe(box); }
    rebuildPaths(); resize(); pose();
    // WHY destroy: tabbed layouts rebuild their screens; a leaked WebGL context per rebuild hits Chrome's ~16 limit
    function destroy() {
      dead = true; if (ro) ro.disconnect();
      renderer.dispose(); if (renderer.forceContextLoss) renderer.forceContextLoss();
      box.remove();
    }
    return { box: box, hud: hud, resize: resize, pose: pose, render: render, destroy: destroy };
  }
  function textSprite(text, color) {
    var c = document.createElement('canvas'); c.width = 64; c.height = 64;
    var ctx = c.getContext('2d'); ctx.fillStyle = color; ctx.font = 'italic 44px Georgia, serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(text, 32, 34);
    var sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
    sprite.scale.set(0.05, 0.05, 1);
    return sprite;
  }

  /* ---------------- badge + header bits ---------------- */

  function badge(parent) {
    var b = el('span', 'rv-badge', parent, 'SIMULATED fixture');
    b.title = 'Every number on this page comes from the shared simulated fixture (fixture.py): vertical 2R arm, moteus-style loop, 3 targets, 27 real repeats + 3 sims.';
    return b;
  }
  // the calm answer: v2 vs v1 on this target, median over the visible real runs of each config
  function verdict(state, j) {
    var gs = state.groups().filter(function (g) { return g.key !== 'sim'; });
    var by = {}; gs.forEach(function (g) { by[g.key] = g; });
    function med(g, fn) { return g ? median(g.runs.map(fn)) : null; }
    var v1 = by['ff v1'], v2 = by['ff v2'];
    return {
      v1: v1, v2: v2,
      err1: med(v1, function (r) { return r.m[j].errRms; }), err2: med(v2, function (r) { return r.m[j].errRms; }),
      share1: med(v1, function (r) { return r.m[j].fbShare; }), share2: med(v2, function (r) { return r.m[j].fbShare; }),
      gap1: med(v1, function (r) { return r.m[j].driveGapRms; }), gap2: med(v2, function (r) { return r.m[j].driveGapRms; }),
      tip1: med(v1, function (r) { return r.tip.rms; }), tip2: med(v2, function (r) { return r.tip.rms; }),
      sat: Math.max.apply(null, state.visibleRuns().map(function (r) { return Math.max(r.m[0].satFrac, r.m[1].satFrac); }).concat([0])),
    };
  }
  // the worst moments across the visible runs: [{run, t, j, value}] sorted by |error|, one per run
  function worstMoments(state, count) {
    var out = state.visibleRuns().filter(function (r) { return r.kind === 'real'; }).map(function (r) {
      var j = r.m[0].errMax >= r.m[1].errMax ? 0 : 1;
      return { run: r, t: r.m[j].errMaxT, j: j, value: r.m[j].errMax };
    });
    out.sort(function (a, b) { return b.value - a.value; });
    return out.slice(0, count || 3);
  }

  function onResize(fn) {
    var pending = false;
    window.addEventListener('resize', function () {
      if (pending) return; pending = true;
      requestAnimationFrame(function () { pending = false; fn(); });
    });
  }

  return {
    F: F, COMP: COMP, COMP_LABEL: COMP_LABEL, GROUPS: GROUPS, GROUP_ORDER: GROUP_ORDER, AMBER: AMBER,
    el: el, rgba: rgba, mix: mix, fmt: fmt, deg: deg, nm: nm, pct: pct, median: median, nearestIndex: nearestIndex,
    store: store, recall: recall, series: series, bands: bands, metricMedian: metricMedian, runQ: runQ,
    fbShareSeries: fbShareSeries, gapSeries: gapSeries, absErr: absErr,
    makeState: makeState, makeTransport: makeTransport, transportBar: transportBar, chart: chart,
    bandFills: bandFills, repeatContent: repeatContent, sidePanel: sidePanel, runList: runList,
    componentLegend: componentLegend, breakdownLines: breakdownLines, arm3d: arm3d, badge: badge,
    verdict: verdict, worstMoments: worstMoments, onResize: onResize,
  };
})();
