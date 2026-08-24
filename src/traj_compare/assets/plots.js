/* traj_compare — plot grid engine.
 *
 * Consumes the JSON payload embedded by report.py and builds, per comparison
 * page: situation legend chips, section show/hide chips, a rad/deg unit
 * toggle (degrees by default), a reset-zoom button, and lazily-built uPlot
 * grids whose x zoom and cursor stay synchronized within a page.
 *
 * A per-page transport carries the shared time state: hovering any plot
 * previews that instant in the 3D viewer; the scrubbers (one under the 3D
 * canvas, one under the videos) and their step/play buttons commit a scrub
 * time that drives the cursor line on every plot, the video players (always
 * seeked together), and the 3D truncation + robot pose.
 *
 * Which plots, which situations, which 3D elements and which units are on is
 * *report-level* state, not page-level: pick a layout once and every scenario
 * tab you switch to shows the same one (see makePrefs / applyShared).
 */

var TrajCompare = (function () {
  'use strict';

  var RAD2DEG = 180 / Math.PI;

  // kind -> {angle: uses the global rad/deg toggle, scale: fixed multiplier}
  var KINDS = {
    angle: { angle: true, rad: 'rad', deg: '°' },
    angle_rate: { angle: true, rad: 'rad/s', deg: '°/s' },
    angle_acc: { angle: true, rad: 'rad/s²', deg: '°/s²' },
    m: { label: 'm' },
    mm: { label: 'mm', scale: 1000 },
    m_s: { label: 'm/s' },
    m_s2: { label: 'm/s²' },
    Nm: { label: 'Nm' },
    pct: { label: '%' },
    pct_s: { label: '%/s' },
    pct_s2: { label: '%/s²' },
  };

  var PLOT_HEIGHT = 150;

  var state = {
    unit: 'deg',
    pages: [],
    groups: [],
    reportPages: [],
    activePage: 0,
    prefs: null,   // report-level view configuration shared by every page
  };

  function store(key, value) {
    try { localStorage.setItem('traj-compare:' + key, JSON.stringify(value)); } catch (e) {}
  }
  function recall(key, fallback) {
    try {
      var raw = localStorage.getItem('traj-compare:' + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (e) { return fallback; }
  }

  /* One view configuration for the whole report, so switching scenario tabs
     keeps the plots/situations/3D elements you chose. Held in memory (the
     part that must work) and mirrored to localStorage (best effort — a
     file:// page may refuse it). A pref nobody has touched reads back null,
     which lets each page fall back to its own default. */
  function makePrefs(namespace) {
    var cache = {};
    return {
      get: function (key, fallback) {
        if (!(key in cache)) cache[key] = recall(namespace + ':' + key, null);
        return cache[key] === null ? fallback : cache[key];
      },
      set: function (key, value) {
        cache[key] = value;
        store(namespace + ':' + key, value);
      },
    };
  }

  function el(tag, className, parent, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function unitLabel(kind) {
    var meta = KINDS[kind];
    return meta.angle ? (state.unit === 'deg' ? meta.deg : meta.rad) : meta.label;
  }

  function convert(kind, values) {
    var meta = KINDS[kind];
    var factor = meta.angle ? (state.unit === 'deg' ? RAD2DEG : 1) : (meta.scale || 1);
    if (factor === 1) return values;
    var out = new Array(values.length);
    for (var i = 0; i < values.length; i++) {
      out[i] = values[i] === null ? null : values[i] * factor;
    }
    return out;
  }

  /* ---------------- transport: the page's shared time state ---------------- */

  function makeTransport(page) {
    var grid = page.data.plot_t;
    var transport = {
      tMin: grid[0],
      tMax: grid[grid.length - 1],
      t: null,       // committed scrub time; null = end (everything shown)
      hoverT: null,  // transient preview while hovering a plot
      playing: false,
      listeners: [],
      bars: [],
    };

    transport.eff = function () {
      if (transport.hoverT !== null) return transport.hoverT;
      if (transport.t !== null) return transport.t;
      return transport.tMax;
    };

    transport.onChange = function (listener) { transport.listeners.push(listener); };

    function emit(kind) {
      transport.listeners.forEach(function (listener) { listener(kind); });
      transport.bars.forEach(function (bar) { bar.paint(); });
    }

    transport.setHover = function (time) {
      if (time === transport.hoverT) return;
      transport.hoverT = time;
      emit('hover');
    };

    transport.setScrub = function (time, fromCursor) {
      transport.t = Math.min(transport.tMax, Math.max(transport.tMin, time));
      if (!fromCursor) paintCursors(page, transport.t);
      queueVideoSeek(page, transport.t, false);
      emit('scrub');
    };

    transport.stepBy = function (samples) {
      transport.pause();
      var current = transport.eff();
      var index = nearestIndex(grid, current) + samples;
      index = Math.min(grid.length - 1, Math.max(0, index));
      transport.setScrub(grid[index]);
    };

    var lastTick = 0;
    function tick(now) {
      if (!transport.playing) return;
      var dt = Math.min(0.1, (now - lastTick) / 1000);
      lastTick = now;
      var next = (transport.t === null ? transport.tMin : transport.t) + dt;
      if (next >= transport.tMax) {
        transport.setScrub(transport.tMax);
        transport.pause();
        return;
      }
      transport.t = next;
      paintCursors(page, next);
      seekVideos(page, next, true);
      emit('scrub');
      requestAnimationFrame(tick);
    }

    transport.play = function () {
      if (transport.playing) return;
      if (transport.t === null || transport.t >= transport.tMax - 1e-9) {
        transport.t = transport.tMin;
      }
      transport.playing = true;
      lastTick = performance.now();
      playVideos(page, true);
      emit('play');
      requestAnimationFrame(tick);
    };

    // Nothing changed when we were already paused, and emitting anyway
    // repainted the bars — which wrote the *stale* time straight back into
    // the slider the user was dragging. Pausing is a no-op when paused.
    transport.pause = function () {
      if (!transport.playing) return;
      transport.playing = false;
      playVideos(page, false);
      emit('pause');
    };

    transport.toggle = function () {
      if (transport.playing) transport.pause(); else transport.play();
    };

    return transport;
  }

  function nearestIndex(sorted, value) {
    var lo = 0, hi = sorted.length - 1;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (sorted[mid] < value) lo = mid + 1; else hi = mid;
    }
    if (lo > 0 && Math.abs(sorted[lo - 1] - value) < Math.abs(sorted[lo] - value)) return lo - 1;
    return lo;
  }

  function paintCursors(page, time) {
    page.cursorDriven = true;
    page.charts.forEach(function (chart) {
      if (!chart.u) return;
      var left = chart.u.valToPos(time, 'x');
      chart.u.setCursor({ left: left, top: 8 });
    });
    page.cursorDriven = false;
  }

  function seekVideos(page, time, playing) {
    page.videos.forEach(function (entry) {
      var video = entry.el;
      if (!video.duration) return;
      var clamped = Math.min(video.duration - 0.001, Math.max(0, time));
      if (playing) {
        // drift-correct only; constant seeking stutters playback
        if (Math.abs(video.currentTime - clamped) > 0.12) video.currentTime = clamped;
      } else {
        video.currentTime = clamped;
      }
    });
  }

  /* A drag fires input events far faster than a decoder can honour seeks, and
     ten <video> elements re-seeking per event stalls the whole page. Coalesce
     to one seek per frame — the last position asked for is the only one that
     matters. */
  function queueVideoSeek(page, time, playing) {
    page.pendingSeek = { time: time, playing: playing };
    if (page.seekQueued) return;
    page.seekQueued = true;
    requestAnimationFrame(function () {
      page.seekQueued = false;
      var pending = page.pendingSeek;
      if (pending) seekVideos(page, pending.time, pending.playing);
    });
  }

  function playVideos(page, play) {
    page.videos.forEach(function (entry) {
      if (play && page.visible[entry.sit.name] !== false) {
        entry.el.play().catch(function () {});
      } else {
        entry.el.pause();
      }
    });
  }

  /* Scrubber bar: one under the 3D canvas, one under the videos. Every bar of
     a page stays in sync through the transport. */
  function buildTransportBar(page, parent) {
    var transport = page.transport;
    if (!transport) return null;
    var bar = el('div', 'tc-transport', parent);
    var handle = { selfDriving: false };

    function iconButton(label, title, onClick) {
      var button = el('button', 'tc-tbtn', bar, label);
      button.title = title;
      button.onclick = onClick;
      return button;
    }

    iconButton('⏮', 'to start', function () { transport.pause(); transport.setScrub(transport.tMin); });
    iconButton('◀', 'step back', function () { transport.stepBy(-1); });
    var playButton = iconButton('▶', 'play / pause', function () { transport.toggle(); });
    iconButton('▶', 'step forward', function () { transport.stepBy(1); });
    iconButton('⏭', 'to end', function () { transport.pause(); transport.setScrub(transport.tMax); });

    var slider = document.createElement('input');
    slider.type = 'range';
    slider.className = 'tc-scrub';
    slider.min = transport.tMin;
    slider.max = transport.tMax;
    slider.step = (transport.tMax - transport.tMin) / 2000;
    slider.value = transport.tMax;
    slider.title = 'drag to scrub · click the track to jump · arrow keys step';
    bar.appendChild(slider);
    slider.addEventListener('input', function () {
      // Read before anything can repaint us, and refuse to be repainted for
      // the duration: writing slider.value mid-drag cancels the drag.
      var time = parseFloat(slider.value);
      handle.selfDriving = true;
      transport.pause();
      transport.setScrub(time);
      handle.selfDriving = false;
    });

    var readout = el('span', 'tc-time', bar);

    handle.paint = function () {
      var time = transport.t === null ? transport.tMax : transport.t;
      if (!handle.selfDriving) slider.value = time;
      readout.textContent = time.toFixed(2) + ' / ' + transport.tMax.toFixed(2) + ' s';
      playButton.textContent = transport.playing ? '⏸' : '▶';
    };
    transport.bars.push(handle);
    handle.paint();
    return bar;
  }

  /* ---------------- chart registry + x-sync ---------------- */

  function makeChart(page, card, spec) {
    var titleEl = el('div', 'ptitle', card);
    var chartEl = el('div', '', card);

    var chart = {
      page: page, card: card, spec: spec, titleEl: titleEl, chartEl: chartEl, u: null,
    };

    function seriesOpts() {
      var opts = [{}];
      spec.series.forEach(function (entry) {
        if (entry.error) {
          opts.push({
            label: 'Δ ' + entry.sit.title,
            stroke: entry.sit.color,
            width: 1.2,
            dash: [2, 3],
            points: { show: false },
            show: !!page.errorOn[entry.sit.name],
          });
          return;
        }
        opts.push({
          label: entry.sit.title,
          stroke: entry.sit.color,
          width: entry.sit.role === 'target' ? 1.4 : 1.7,
          dash: entry.sit.role === 'target' ? [7, 4] : undefined,
          points: { show: false },
          show: page.visible[entry.sit.name] !== false,
        });
      });
      return opts;
    }

    function data() {
      var columns = [page.data.plot_t];
      spec.series.forEach(function (entry) {
        columns.push(convert(spec.kind, entry.values));
      });
      return columns;
    }

    function width() {
      return Math.max(220, card.clientWidth - 18);
    }

    chart.build = function () {
      titleEl.innerHTML = '';
      titleEl.appendChild(document.createTextNode(spec.title + ' '));
      el('span', 'unit', titleEl, '[' + unitLabel(spec.kind) + ']');
      var opts = {
        width: width(),
        height: PLOT_HEIGHT,
        series: seriesOpts(),
        scales: { x: { time: false } },
        legend: { show: false },
        cursor: {
          drag: { x: true, y: false },
          points: { size: 6 },
          sync: { key: 'tc-page-' + page.index },
        },
        axes: [
          { stroke: '#8a8983', grid: { stroke: '#e6e5e0', width: 0.5 }, ticks: { stroke: '#c9c8c2' }, size: 28 },
          { stroke: '#8a8983', grid: { stroke: '#e6e5e0', width: 0.5 }, ticks: { stroke: '#c9c8c2' }, size: 44 },
        ],
        hooks: {
          setScale: [function (u, key) {
            if (key !== 'x' || !u._tcReady || page.syncing) return;
            var scale = u.scales.x;
            page.syncing = true;
            page.charts.forEach(function (other) {
              if (other.u && other.u !== u) other.u.setScale('x', { min: scale.min, max: scale.max });
            });
            page.xZoom = { min: scale.min, max: scale.max };
            page.syncing = false;
          }],
          setCursor: [function (u) {
            // hover preview for the 3D view; ignore our own programmatic sets
            if (page.cursorDriven || !page.transport) return;
            var index = u.cursor.idx;
            page.transport.setHover(index == null ? null : page.data.plot_t[index]);
          }],
          ready: [function (u) { u._tcReady = true; }],
        },
      };
      chart.u = new uPlot(opts, data(), chartEl);
      if (page.xZoom) chart.u.setScale('x', page.xZoom);
    };

    chart.refreshUnits = function () {
      if (!chart.u) return;
      var keep = page.xZoom;
      chart.u._tcReady = false;
      chart.u.setData(data(), true);
      if (keep) chart.u.setScale('x', keep);
      chart.u._tcReady = true;
      titleEl.innerHTML = '';
      titleEl.appendChild(document.createTextNode(spec.title + ' '));
      el('span', 'unit', titleEl, '[' + unitLabel(spec.kind) + ']');
    };

    // A run's own trace and its Δ curve toggle independently — that is what
    // lets you hide target + measured and read the error off a y axis that
    // has rescaled to the error alone.
    chart.setSituation = function (name, show) {
      if (!chart.u) return;
      spec.series.forEach(function (entry, index) {
        if (entry.sit.name === name && !entry.error) chart.u.setSeries(index + 1, { show: show });
      });
    };

    chart.setError = function (name, show) {
      if (!chart.u) return;
      spec.series.forEach(function (entry, index) {
        if (entry.sit.name === name && entry.error) chart.u.setSeries(index + 1, { show: show });
      });
    };

    chart.hasError = function (name) {
      return spec.series.some(function (entry) {
        return entry.error && entry.sit.name === name;
      });
    };

    chart.resetZoom = function () {
      if (!chart.u) return;
      chart.u._tcReady = false;
      chart.u.setScale('x', { min: page.transport ? page.transport.tMin : null, max: page.transport ? page.transport.tMax : null });
      chart.u._tcReady = true;
    };

    chart.resize = function () {
      if (chart.u) chart.u.setSize({ width: width(), height: PLOT_HEIGHT });
    };

    chart.build();
    page.charts.push(chart);
    return chart;
  }

  /* ---------------- sections ---------------- */

  function sitsWith(page, field) {
    return page.data.situations.filter(function (sit) {
      return sit.plot && sit.plot[field];
    });
  }

  /* Difference on the display grid: both columns are already resampled onto
     plot_t, and a null on either side (outside a run's own recorded span)
     stays a null so the gap survives instead of becoming a fake zero. */
  function difference(values, reference) {
    var out = new Array(values.length);
    for (var index = 0; index < values.length; index++) {
      var value = values[index], base = reference[index];
      out[index] = (value === null || base === null) ? null : value - base;
    }
    return out;
  }

  /* Append one Δ-to-target series per measured run to a chart's series list.
     ``precomputed`` lets a channel hand over an error the analysis already
     computed on the native grid (q does: err_q); everything else differences
     the display columns. */
  function withErrors(series, precomputed) {
    var target = null;
    series.forEach(function (entry) {
      if (entry.sit.role === 'target') target = entry;
    });
    var out = series.slice();
    series.forEach(function (entry) {
      if (entry.sit.role === 'target') return;
      var values = precomputed ? precomputed(entry.sit) : (target && difference(entry.values, target.values));
      if (values) out.push({ sit: entry.sit, values: values, error: true });
    });
    return out;
  }

  function jointSectionBuilder(field, kind, titleSuffix) {
    return function (page, body) {
      var grid = el('div', 'tc-grid', body);
      page.data.joint_names.forEach(function (jointName, dof) {
        var series = sitsWith(page, field).map(function (sit) {
          return { sit: sit, values: sit.plot[field][dof] };
        });
        if (!series.length) return;
        // q has a native-grid error channel already; reuse it so the overlay
        // and the Joint error section can never disagree.
        var precomputed = field !== 'q' ? null : function (sit) {
          return sit.plot.err_q ? sit.plot.err_q[dof] : null;
        };
        makeChart(page, el('div', 'tc-plotcard', grid),
          { title: jointName + ' — ' + titleSuffix, kind: kind,
            series: withErrors(series, precomputed) });
      });
      observeGrid(page, grid);
    };
  }

  function tcpPoseBuilder(page, body) {
    var grid = el('div', 'tc-grid', body);
    [['x', 'TCP x', 'm'], ['y', 'TCP y', 'm'], ['z', 'TCP z', 'm'],
     ['rx', 'TCP rx', 'angle'], ['ry', 'TCP ry', 'angle'], ['rz', 'TCP rz', 'angle']]
      .forEach(function (row) {
        var series = sitsWith(page, row[0]).map(function (sit) {
          return { sit: sit, values: sit.plot[row[0]] };
        });
        if (!series.length) return;
        makeChart(page, el('div', 'tc-plotcard', grid),
          { title: row[1], kind: row[2], series: withErrors(series) });
      });
    observeGrid(page, grid);
  }

  function tcpErrBuilder(page, body) {
    var grid = el('div', 'tc-grid', body);
    [['xyz_mag', 'TCP position error |Δp|', 'mm'],
     ['rot_mag', 'TCP rotation error', 'angle']].forEach(function (row) {
      var series = sitsWith(page, row[0]).map(function (sit) {
        return { sit: sit, values: sit.plot[row[0]] };
      });
      if (!series.length) return;
      makeChart(page, el('div', 'tc-plotcard', grid),
        { title: row[1], kind: row[2], series: series });
    });
    observeGrid(page, grid);
  }

  function jointErrBuilder(page, body) {
    var grid = el('div', 'tc-grid', body);
    page.data.joint_names.forEach(function (jointName, dof) {
      var series = sitsWith(page, 'err_q').map(function (sit) {
        return { sit: sit, values: sit.plot.err_q[dof] };
      });
      if (!series.length) return;
      makeChart(page, el('div', 'tc-plotcard', grid),
        { title: jointName + ' — q error vs target', kind: 'angle', series: series });
    });
    observeGrid(page, grid);
  }

  function pathBuilder(page, body) {
    var channels = [
      { key: 'pct', label: '% of path', kinds: ['pct', 'pct_s', 'pct_s2'] },
      { key: 'xyz', label: 'XYZ path', kinds: ['m', 'm_s', 'm_s2'] },
      { key: 'rpy', label: 'RPY path', kinds: ['angle', 'angle_rate', 'angle_acc'] },
    ];
    page.data.vec_labels.forEach(function (label, index) {
      channels.push({ key: 'vec' + index, label: 'Vec ' + label, kinds: ['m', 'm_s', 'm_s2'] });
    });
    var grid = el('div', 'tc-grid pathgrid', body);
    grid.style.setProperty('--path-cols', String(channels.length));
    [['', 0], ['_d', 1], ['_dd', 2]].forEach(function (level) {
      channels.forEach(function (channel) {
        var field = channel.key + level[0];
        var series = sitsWith(page, field).map(function (sit) {
          return { sit: sit, values: sit.plot[field] };
        });
        if (!series.length) return;
        makeChart(page, el('div', 'tc-plotcard', grid),
          { title: channel.label + level[0], kind: channel.kinds[level[1]],
            series: withErrors(series) });
      });
    });
    observeGrid(page, grid);
  }

  function videosBuilder(page, body) {
    var grid = el('div', 'tc-videogrid', body);
    page.data.situations.forEach(function (sit) {
      if (!sit.video) return;
      var card = el('div', 'tc-videocard', grid);
      card.dataset.situation = sit.name;
      var label = el('div', 'vlabel', card);
      var swatch = el('span', 'swatch', label);
      swatch.style.background = sit.color;
      label.appendChild(document.createTextNode(sit.title));
      var video = document.createElement('video');
      video.src = sit.video;
      video.muted = true;
      video.playsInline = true;
      video.preload = 'auto';
      card.appendChild(video);
      video.addEventListener('click', function () {
        if (page.transport) page.transport.toggle();
      });
      page.videos.push({ sit: sit, el: video, card: card });
      if (page.visible[sit.name] === false) card.style.display = 'none';
    });
    // One transport for every video on the page — the videos are frames of
    // the same run, so they are never scrubbed or played independently.
    if (page.transport) buildTransportBar(page, body);
    el('div', 'tc-videonote', body,
      'One scrubber drives every video, the plot cursors and the 3D view together; ' +
      'clicking a video plays/pauses them all.');
  }

  function viewer3dBuilder(page, body) {
    var wrap = el('div', '', body);
    page.viewer3d = Viewer3D.create(page, wrap);
  }

  function observeGrid(page, grid) {
    if (typeof ResizeObserver === 'undefined') return;
    var pending = false;
    var observer = new ResizeObserver(function () {
      if (pending) return;
      pending = true;
      requestAnimationFrame(function () {
        pending = false;
        page.charts.forEach(function (chart) {
          if (grid.contains(chart.card)) chart.resize();
        });
      });
    });
    observer.observe(grid);
  }

  /* ---------------- page assembly ---------------- */

  function sectionStartsOn(data, id, fallback) {
    if (!Array.isArray(data.default_sections)) return fallback;
    return data.default_sections.indexOf(id) !== -1;
  }

  function sectionDefs(data) {
    var defs = [
      { id: 'joint-q', label: 'Joint q', on: sectionStartsOn(data, 'joint-q', true), build: jointSectionBuilder('q', 'angle', 'q') },
      { id: 'joint-qd', label: 'Joint qd', on: sectionStartsOn(data, 'joint-qd', false), build: jointSectionBuilder('qd', 'angle_rate', 'qd') },
      { id: 'joint-qdd', label: 'Joint qdd', on: sectionStartsOn(data, 'joint-qdd', false), build: jointSectionBuilder('qdd', 'angle_acc', 'qdd') },
    ];
    if (data.has_tau) {
      defs.push({ id: 'joint-tau', label: 'Motor / joint τ', on: sectionStartsOn(data, 'joint-tau', false), build: jointSectionBuilder('tau', 'Nm', 'τ') });
    }
    var anyErr = data.situations.some(function (sit) { return sit.plot && sit.plot.err_q; });
    if (anyErr) {
      defs.push({ id: 'joint-err', label: 'Joint error', on: sectionStartsOn(data, 'joint-err', false), build: jointErrBuilder });
    }
    if (data.has_cartesian) {
      defs.push({ id: 'tcp-pose', label: 'TCP pose', on: sectionStartsOn(data, 'tcp-pose', false), build: tcpPoseBuilder });
      var anyMag = data.situations.some(function (sit) { return sit.plot && sit.plot.xyz_mag; });
      if (anyMag) defs.push({ id: 'tcp-err', label: 'TCP error', on: sectionStartsOn(data, 'tcp-err', true), build: tcpErrBuilder });
      defs.push({ id: 'path', label: 'Path progress', on: sectionStartsOn(data, 'path', true), build: pathBuilder });
    }
    if (data.has_video) {
      defs.push({ id: 'videos', label: 'Videos', on: sectionStartsOn(data, 'videos', true), build: videosBuilder });
    }
    if (data.has_cartesian) {
      defs.push({ id: 'viewer3d', label: '3D paths', on: sectionStartsOn(data, 'viewer3d', true), build: viewer3dBuilder });
    }
    return defs;
  }

  // Sections whose plots carry the optional Δ-to-target overlay.
  var DELTA_SECTIONS = ['joint-q', 'joint-qd', 'joint-qdd', 'joint-tau', 'tcp-pose', 'path'];

  function sectionHint(id, data) {
    var hint = '';
    if (id === 'path') {
      var reference = data.pct_reference === 'target' ? 'target path length' : 'own path length';
      hint = '% is of ' + reference + '; Vec is signed progress along the labeled direction';
    }
    if (id === 'tcp-err') hint = 'magnitudes vs target at the same time instant';
    if (id === 'videos') hint = 'always played together, seeked by the scrubber';
    if (id === 'viewer3d') hint = 'hover any plot to preview that instant; scrub below the canvas';
    var hasTarget = data.situations.some(function (sit) {
      return sit.role === 'target' && sit.plot;
    });
    if (hasTarget && DELTA_SECTIONS.indexOf(id) !== -1) {
      hint += (hint ? ' · ' : '') +
        'Error vs target draws a dotted Δ here; hide target + measured to read it on its own axis';
    }
    return hint;
  }

  function buildTable(parent, table, compact) {
    var block = el('section', 'tc-tableblock' + (compact ? ' compact' : ''), parent);
    if (table.title) el('h3', '', block, table.title);
    if (table.description) el('p', 'tc-table-desc', block, table.description);
    var scroll = el('div', 'tc-table-scroll', block);
    var tableEl = el('table', 'tc-metrics', scroll);
    var head = el('thead', '', tableEl);
    var headRow = el('tr', '', head);
    table.columns.forEach(function (column) { el('th', '', headRow, column); });
    var body = el('tbody', '', tableEl);
    table.rows.forEach(function (row) {
      var tr = el('tr', row.tone ? 'tone-' + row.tone : '', body);
      row.cells.forEach(function (cell, index) {
        el(index === 0 ? 'th' : 'td', '', tr, cell);
      });
    });
    return block;
  }

  function buildMetricCards(parent, metrics) {
    if (!metrics || !metrics.length) return;
    var grid = el('div', 'tc-metriccards', parent);
    metrics.forEach(function (metric) {
      var card = el('div', 'tc-metriccard tone-' + (metric.tone || 'neutral'), grid);
      el('div', 'label', card, metric.label);
      el('div', 'value', card, metric.value);
      if (metric.detail) el('div', 'detail', card, metric.detail);
    });
  }

  function buildBarChart(parent, chart) {
    var section = el('section', 'tc-summary-chart', parent);
    el('h3', '', section, chart.title);
    if (chart.description) el('p', 'tc-table-desc', section, chart.description);
    var values = [];
    chart.series.forEach(function (series) {
      series.values.forEach(function (value) { if (value !== null) values.push(value); });
    });
    var maximum = values.length ? Math.max.apply(null, values) : 1;
    if (!(maximum > 0)) maximum = 1;
    var colors = ['#2a78d6', '#eb6834', '#2f9e44', '#8e5bd1', '#c22f6e'];
    chart.categories.forEach(function (category, categoryIndex) {
      var group = el('div', 'tc-bar-group', section);
      el('div', 'tc-bar-category', group, category);
      chart.series.forEach(function (series, seriesIndex) {
        var row = el('div', 'tc-bar-row', group);
        el('div', 'tc-bar-label', row, series.name);
        var track = el('div', 'tc-bar-track', row);
        var value = series.values[categoryIndex];
        var fill = el('span', 'tc-bar-fill', track);
        fill.style.background = series.color || colors[seriesIndex % colors.length];
        fill.style.width = value === null ? '0' : Math.max(1, value / maximum * 100) + '%';
        var formatted = value === null ? '—' : value.toFixed(chart.decimals);
        el('div', 'tc-bar-value', row, formatted + (chart.unit ? ' ' + chart.unit : ''));
      });
    });
  }

  function buildInsightCards(parent, insights) {
    if (!insights || !insights.length) return;
    var grid = el('div', 'tc-insights', parent);
    insights.forEach(function (insight) {
      var card = el('article', 'tc-insight tone-' + (insight.tone || 'neutral'), grid);
      el('h3', '', card, insight.title);
      el('p', 'finding', card, insight.finding);
      if (insight.evidence && insight.evidence.length) {
        var list = el('ul', 'evidence', card);
        insight.evidence.forEach(function (item) { el('li', '', list, item); });
      }
      if (insight.recommendation) {
        var recommendation = el('p', 'recommendation', card);
        el('strong', '', recommendation, 'Recommendation: ');
        recommendation.appendChild(document.createTextNode(insight.recommendation));
      }
    });
  }

  function buildReportPage(page) {
    var data = page.data;
    el('h2', 'tc-page-title', page.el, data.title);
    if (data.description) el('p', 'tc-report-desc', page.el, data.description);
    buildMetricCards(page.el, data.metrics);
    data.charts.forEach(function (chart) { buildBarChart(page.el, chart); });
    data.tables.forEach(function (table) { buildTable(page.el, table, false); });
    buildInsightCards(page.el, data.insights);
  }

  function buildPage(page) {
    var data = page.data;
    var root = page.el;

    if (data.plot_t) page.transport = makeTransport(page);

    el('h2', 'tc-page-title', root, data.title);
    if (data.description) el('p', 'tc-desc', root, data.description);
    if (data.statistics) buildTable(root, data.statistics, true);

    var summary = data.meta && data.meta.summary;
    if (summary) {
      var summaryCard = el('section', 'tc-summary', root);
      el('h3', '', summaryCard, summary.title || 'Performance summary');
      if (summary.facts && summary.facts.length) {
        var facts = el('div', 'tc-facts', summaryCard);
        summary.facts.forEach(function (fact) {
          var item = el('div', 'tc-fact', facts);
          el('span', 'label', item, fact.label);
          el('strong', '', item, String(fact.value));
        });
      }
      if (summary.columns && summary.rows) {
        var tableWrap = el('div', 'tc-summary-table-wrap', summaryCard);
        var table = el('table', 'tc-summary-table', tableWrap);
        var head = el('thead', '', table);
        var headRow = el('tr', '', head);
        summary.columns.forEach(function (column) {
          el('th', '', headRow, column.label + (column.unit ? ' (' + column.unit + ')' : ''));
        });
        var body = el('tbody', '', table);
        summary.rows.forEach(function (row) {
          var tr = el('tr', '', body);
          summary.columns.forEach(function (column) {
            var value = row[column.key];
            el('td', '', tr, value === undefined || value === null ? '—' : String(value));
          });
        });
      }
    }

    var controls = el('div', 'tc-controls', root);

    // Situation chips are grouped semantically instead of becoming one long,
    // permutation-heavy list. Visibility is keyed by situation name across
    // the report, so hiding "Real" on one scenario hides it on all of them.
    var situationGroups = [];
    var situationGroupsByName = {};
    data.situations.forEach(function (sit) {
      var name = sit.group || 'situations';
      if (!situationGroupsByName[name]) {
        situationGroupsByName[name] = {
          name: name,
          title: sit.group_title || 'Situations',
          situations: [],
        };
        situationGroups.push(situationGroupsByName[name]);
      }
      situationGroupsByName[name].situations.push(sit);
    });
    var situationsHost = el('div', 'tc-situation-groups', controls);
    situationGroups.forEach(function (definition) {
      var situationGroup = el('div', 'group situation-group', situationsHost);
      el('span', 'grouplabel', situationGroup, definition.title);
      definition.situations.forEach(function (sit) {
        if (!sit.has_data) {
          var dead = el('span', 'chip nodata', situationGroup);
          var swatchOff = el('span', 'swatch', dead);
          swatchOff.style.background = sit.color;
          dead.appendChild(document.createTextNode(sit.title + ' '));
          el('span', 'note', dead, '(no data' + (sit.note ? ' — ' + sit.note : '') + ')');
          return;
        }
        var chip = el('button', 'chip on', situationGroup);
        var swatch = el('span', 'swatch' + (sit.role === 'target' ? ' dashed' : ''), chip);
        swatch.style.background = sit.color;
        swatch.style.color = sit.color;
        chip.appendChild(document.createTextNode(sit.title));

        function apply(show, remember) {
          page.visible[sit.name] = show;
          chip.className = 'chip ' + (show ? 'on' : 'off');
          if (remember) state.prefs.set('sit:' + sit.name, show);
          setSituationVisible(page, sit.name, show);
        }
        page.sitChips.push({ sit: sit, apply: apply });
        chip.onclick = function () { apply(page.visible[sit.name] === false, true); };
        apply(state.prefs.get('sit:' + sit.name, true), false);
      });
    });

    // Δ-to-target chips: one per measured run, off by default. Independent of
    // the run's own chip, so the useful move — hide target *and* measured,
    // leave Δ — is two clicks and the y axis rescales to the error.
    var hasTarget = data.situations.some(function (sit) {
      return sit.role === 'target' && sit.plot;
    });
    var errorCandidates = !hasTarget ? [] : data.situations.filter(function (sit) {
      return sit.has_data && sit.role !== 'target' && sit.plot;
    });
    if (errorCandidates.length) {
      var errorGroup = el('div', 'group', controls);
      el('span', 'grouplabel', errorGroup, 'Error vs target');
      errorGroup.title = 'overlay each measured run minus the target on every plot';
      errorCandidates.forEach(function (sit) {
        var chip = el('button', 'chip', errorGroup);
        var swatch = el('span', 'swatch dotted', chip);
        swatch.style.background = sit.color;
        swatch.style.color = sit.color;
        chip.appendChild(document.createTextNode('Δ ' + sit.title));

        function apply(show, remember) {
          page.errorOn[sit.name] = show;
          chip.className = 'chip ' + (show ? 'on' : 'off');
          if (remember) state.prefs.set('err:' + sit.name, show);
          page.charts.forEach(function (chart) { chart.setError(sit.name, show); });
        }
        page.errChips.push({ sit: sit, apply: apply });
        chip.onclick = function () { apply(!page.errorOn[sit.name], true); };
        apply(state.prefs.get('err:' + sit.name, false), false);
      });
    }

    // unit toggle + reset zoom
    var unitGroup = el('div', 'group', controls);
    el('span', 'grouplabel', unitGroup, 'Angles');
    var degChip = el('button', 'chip', unitGroup, 'deg');
    var radChip = el('button', 'chip', unitGroup, 'rad');
    function paintUnits() {
      degChip.className = 'chip ' + (state.unit === 'deg' ? 'on' : 'off');
      radChip.className = 'chip ' + (state.unit === 'rad' ? 'on' : 'off');
    }
    function setUnit(unit) {
      if (state.unit === unit) return;
      state.unit = unit;
      store('unit', unit);
      state.pages.forEach(function (other) {
        other.charts.forEach(function (chart) { chart.refreshUnits(); });
        if (other.paintUnits) other.paintUnits();
      });
    }
    degChip.onclick = function () { setUnit('deg'); };
    radChip.onclick = function () { setUnit('rad'); };
    page.paintUnits = paintUnits;
    paintUnits();

    var zoomGroup = el('div', 'group', controls);
    el('span', 'grouplabel', zoomGroup, 'Zoom');
    var resetButton = el('button', 'chip', zoomGroup, 'Reset zoom');
    resetButton.title = 'restore the full time range on every plot (double-clicking a plot works too)';
    resetButton.onclick = function () {
      page.xZoom = null;
      page.charts.forEach(function (chart) { chart.resetZoom(); });
    };

    // section chips
    var sectionGroup = el('div', 'group', controls);
    el('span', 'grouplabel', sectionGroup, 'Plots');
    page.sections = sectionDefs(data).map(function (def) {
      var section = {
        def: def,
        // A section nobody has touched keeps this page's own default; once
        // it is toggled the choice is shared by every scenario tab.
        on: state.prefs.get('section:' + def.id, def.on),
        built: false,
        chip: el('button', 'chip', sectionGroup, def.label),
        el: null,
        body: null,
      };
      section.chip.onclick = function () { setSection(section, !section.on, true); };
      return section;
    });

    // derived-channel footnote
    var derivedBits = data.situations
      .filter(function (sit) { return sit.derived && sit.derived.length; })
      .map(function (sit) { return sit.title + ': ' + sit.derived.join(', '); });
    if (derivedBits.length) {
      el('div', 'tc-derived', root,
        'Finite-difference derived — ' + derivedBits.join(' · '));
    }

    var sectionHost = el('div', '', root);
    page.sections.forEach(function (section) {
      section.el = el('div', 'tc-section', sectionHost);
      var heading = el('h3', '', section.el, section.def.label + ' ');
      var hint = sectionHint(section.def.id, data);
      if (hint) el('span', 'hint', heading, '— ' + hint);
      section.body = el('div', '', section.el);
      paintSection(section);
    });

    function paintSection(section) {
      section.chip.className = 'chip ' + (section.on ? 'on' : 'off');
      section.el.style.display = section.on ? '' : 'none';
      if (section.on && !section.built) {
        section.built = true;
        section.def.build(page, section.body);
      }
      if (section.def.id === 'viewer3d' && page.viewer3d) {
        page.viewer3d.setActive(section.on && page.el.classList.contains('active'));
      }
    }

    function setSection(section, on, remember) {
      section.on = on;
      if (remember) state.prefs.set('section:' + section.def.id, on);
      paintSection(section);
    }

    page.paintSections = function () {
      page.sections.forEach(paintSection);
    };

    /* Pull in choices made on another scenario tab. Pages are built lazily,
       so this is what keeps an already-built page in step. */
    page.applyShared = function () {
      page.sections.forEach(function (section) {
        var want = state.prefs.get('section:' + section.def.id, section.def.on);
        if (want !== section.on) setSection(section, want, false);
      });
      page.sitChips.forEach(function (entry) {
        var want = state.prefs.get('sit:' + entry.sit.name, true);
        if (want !== (page.visible[entry.sit.name] !== false)) entry.apply(want, false);
      });
      page.errChips.forEach(function (entry) {
        var want = state.prefs.get('err:' + entry.sit.name, false);
        if (want !== !!page.errorOn[entry.sit.name]) entry.apply(want, false);
      });
      if (page.viewer3d && page.viewer3d.applyShared) page.viewer3d.applyShared();
    };
  }

  function setSituationVisible(page, name, show) {
    page.charts.forEach(function (chart) { chart.setSituation(name, show); });
    if (page.viewer3d) page.viewer3d.setSituationVisible(name, show);
    page.videos.forEach(function (entry) {
      if (entry.sit.name === name) {
        entry.card.style.display = show ? '' : 'none';
        if (!show) entry.el.pause();
        else if (page.transport && page.transport.playing) entry.el.play().catch(function () {});
      }
    });
  }

  /* ---------------- boot ---------------- */

  function paintPrimaryTabs(activeGroup, activeReport) {
    state.groups.forEach(function (group) {
      group.tab.classList.toggle('active', group.name === activeGroup);
    });
    state.reportPages.forEach(function (page) {
      page.tab.classList.toggle('active', page.data.name === activeReport);
    });
  }

  function paintSubtabs(group) {
    var nav = document.getElementById('tc-subtabs');
    nav.innerHTML = '';
    if (!group || group.pages.length < 2) {
      nav.style.display = 'none';
      return;
    }
    nav.style.display = '';
    group.pages.forEach(function (page) {
      nav.appendChild(page.tab);
      page.tab.classList.toggle('active', page.index === group.activeIndex);
    });
  }

  function activatePage(index) {
    state.activePage = index;
    var selected = state.pages[index];
    var group = selected.group;
    group.activeIndex = index;
    paintPrimaryTabs(group.name, null);
    paintSubtabs(group);
    state.reportPages.forEach(function (page) { page.el.classList.remove('active'); });
    state.pages.forEach(function (page, pageIndex) {
      var active = pageIndex === index;
      page.el.classList.toggle('active', active);
      page.tab.classList.toggle('active', active);
      if (active && !page.builtPage) {
        page.builtPage = true;
        buildPage(page);
      } else if (active && page.applyShared) {
        page.applyShared();
      }
      if (active && page.charts) {
        page.charts.forEach(function (chart) { chart.resize(); });
      }
      if (page.viewer3d) page.viewer3d.setActive(active);
      if (!active && page.transport) page.transport.pause();
    });
  }

  function activateReportPage(index) {
    var selected = state.reportPages[index];
    paintPrimaryTabs(null, selected.data.name);
    paintSubtabs(null);
    state.pages.forEach(function (page) {
      page.el.classList.remove('active');
      page.tab.classList.remove('active');
      if (page.transport) page.transport.pause();
      if (page.viewer3d) page.viewer3d.setActive(false);
    });
    state.reportPages.forEach(function (page, pageIndex) {
      var active = pageIndex === index;
      page.el.classList.toggle('active', active);
      if (active && !page.builtPage) {
        page.builtPage = true;
        buildReportPage(page);
      }
    });
  }

  function boot() {
    var payload = JSON.parse(document.getElementById('traj-compare-data').textContent);
    state.unit = recall('unit', 'deg');
    state.prefs = makePrefs(payload.title || 'report');

    var nav = document.getElementById('tc-tabs');
    var main = document.getElementById('tc-main');
    var groupsByName = {};

    state.pages = payload.comparisons.map(function (data, index) {
      var page = {
        index: index,
        data: data,
        el: el('section', 'tc-page', main),
        tab: null,
        charts: [],
        sections: [],
        sitChips: [],
        errChips: [],
        errorOn: {},   // situation name -> its Δ-to-target curve is drawn
        videos: [],
        visible: {},
        syncing: false,
        cursorDriven: false,
        seekQueued: false,
        pendingSeek: null,
        xZoom: null,
        builtPage: false,
        viewer3d: null,
        transport: null,
        group: null,
      };
      page.el.id = 'page-' + data.name;
      page.tab = el('button', '', null, data.tab_title || data.title);
      page.tab.onclick = function () { activatePage(index); };
      var groupName = data.group || data.name;
      if (!groupsByName[groupName]) {
        groupsByName[groupName] = {
          name: groupName,
          title: data.group_title || data.title,
          pages: [],
          activeIndex: index,
          tab: null,
        };
      }
      page.group = groupsByName[groupName];
      page.group.pages.push(page);
      return page;
    });

    state.groups = [];
    payload.comparisons.forEach(function (data) {
      var group = groupsByName[data.group || data.name];
      if (state.groups.indexOf(group) !== -1) return;
      group.tab = el('button', '', nav, group.title);
      group.tab.onclick = function () { activatePage(group.activeIndex); };
      state.groups.push(group);
    });

    state.reportPages = (payload.report_pages || []).map(function (data, index) {
      var page = {
        data: data,
        el: el('section', 'tc-page tc-report-page', main),
        tab: el('button', '', nav, data.title),
        builtPage: false,
      };
      page.el.id = 'report-page-' + data.name;
      page.tab.onclick = function () { activateReportPage(index); };
      return page;
    });
    if (state.groups.length + state.reportPages.length < 2) nav.style.display = 'none';

    activatePage(0);
  }

  return {
    boot: boot,
    state: state,
    buildTransportBar: buildTransportBar,
    prefs: function () { return state.prefs; },
  };
})();
