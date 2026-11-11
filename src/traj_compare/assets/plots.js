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
 * A "Camera" section stacks a real video and a selectable sim render in one
 * box (opacity slider, mix/difference blend, flicker toggle); those videos
 * join the page's video list, so the same transport drives them.
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
    A: { label: 'A' },
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
      queueVideoSeek(page, transport.t);
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
      var next = followVideos(page, transport.t === null ? transport.tMin : transport.t, dt, now);
      if (next >= transport.tMax) {
        transport.setScrub(transport.tMax);
        transport.pause();
        return;
      }
      transport.t = next;
      paintCursors(page, next);
      emit('scrub');
      requestAnimationFrame(tick);
    }

    // The videos start from the tick, once each one sits on the clock.
    transport.play = function () {
      if (transport.playing) return;
      if (transport.t === null || transport.t >= transport.tMax - 1e-9) {
        transport.t = transport.tMin;
      }
      transport.playing = true;
      lastTick = performance.now();
      emit('play');
      requestAnimationFrame(tick);
    };

    // Nothing changed when we were already paused, and emitting anyway
    // repainted the bars — which wrote the *stale* time straight back into
    // the slider the user was dragging. Pausing is a no-op when paused.
    // A paused page shows exactly the cursor's frame: the videos ran on for
    // up to a display frame after the last tick, so they are put back on it.
    transport.pause = function () {
      if (!transport.playing) return;
      transport.playing = false;
      pauseVideos(page);
      if (transport.t !== null) queueVideoSeek(page, transport.t);
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

  /* One video follows the trajectory clock. ``entry.t0`` (camera overlays
     only; 0 for a plain situation video) is the trajectory time shown at
     video time 0, so the video position is t - t0. */
  function seekEntry(entry, time) {
    var video = entry.el;
    if (!video.duration) return;
    video.currentTime = Math.min(video.duration - 0.001, Math.max(0, time - (entry.t0 || 0)));
  }

  function seekVideos(page, time) {
    page.videos.forEach(function (entry) { seekEntry(entry, time); });
  }

  /* A drag fires input events far faster than a decoder can honour seeks, and
     ten <video> elements re-seeking per event stalls the whole page. Coalesce
     to one seek per frame — the last position asked for is the only one that
     matters. */
  function queueVideoSeek(page, time) {
    page.pendingSeek = { time: time };
    if (page.seekQueued) return;
    page.seekQueued = true;
    requestAnimationFrame(function () {
      page.seekQueued = false;
      var pending = page.pendingSeek;
      if (pending) seekVideos(page, pending.time);
    });
  }

  function pauseVideos(page) {
    page.videos.forEach(function (entry) {
      entry.el.pause();
      entry.el.playbackRate = 1;
    });
  }

  /* Playback: the clock follows the videos, never the other way round.

     WHY: a seek lands on the keyframe before its target and decodes forward
     from it, 150-500 ms in the rack's mp4s (a keyframe every 8.3 s). The old
     loop advanced a wall clock and re-seeked any video 0.12 s off it, so a
     seek still in flight was restarted every tick: the picture froze on its
     last frame until the clock crossed a keyframe while the plot cursor ran
     on (measured 2026-10-21 on the rack sensors report: no frame presented
     for the first 3.2 s of play), and a video that did keep up was left up
     to 0.12 s off the cursor. Now the clock holds while any video is seeking
     or starved, every video is put exactly on it before it plays, and then
     the first playing video IS the clock: the cursor is the time of the
     frame it has on screen. The others follow it by playbackRate, seeking
     only when they are far off. "On screen" is the frame the compositor
     PRESENTED (requestVideoFrameCallback, which runs just before this
     frame's animation callbacks), not currentTime: currentTime wandered 1-2
     frames off the picture, and with four 720p decoders a follower's
     currentTime sat on the clock while its picture ran two frames late
     (67 ms, headless Chrome, 2026-10-21). A
     video whose recording does not cover the time is parked on its
     first/last frame instead of playing ahead of it. */
  var PLAY_ALIGN_S = 0.015;   // a video this close to the clock may start playing
  var PLAY_RESEEK_S = 0.25;   // a follower further off than this is re-seeked
  var PLAY_NUDGE_GAIN = 2.0;  // rate = 1 - gain * drift: ~0.5 s to converge
  var PLAY_NUDGE_LIMIT = 0.25;

  function videoPlayable(page, entry) {
    return entry.el.duration > 0 && !entry.el.error && page.visible[entry.sit.name] !== false;
  }

  function videoCovers(entry, time) {
    var position = time - (entry.t0 || 0);
    return position >= 0 && position < entry.el.duration - 0.05;
  }

  function watchPresented(entry) {
    if (entry.watching || !entry.el.requestVideoFrameCallback) return;
    entry.watching = true;
    var onFrame = function (now, meta) {
      entry.presented = { media: meta.mediaTime, now: now };
      entry.el.requestVideoFrameCallback(onFrame);
    };
    entry.el.requestVideoFrameCallback(onFrame);
  }

  // Video time of the picture on screen at ``now``: the last presented frame,
  // run on at the playback rate since (capped), else currentTime.
  function shownTime(entry, now) {
    var shown = entry.presented;
    if (!shown || entry.el.paused) return entry.el.currentTime;
    return shown.media + Math.min(0.1, Math.max(0, (now - shown.now) / 1000)) * entry.el.playbackRate;
  }

  function followVideos(page, time, dt, now) {
    var active = [];
    page.videos.forEach(function (entry) {
      if (!videoPlayable(page, entry)) return;
      if (videoCovers(entry, time)) { active.push(entry); return; }
      entry.el.pause();
      var parked = Math.min(entry.el.duration - 0.001, Math.max(0, time - (entry.t0 || 0)));
      if (!entry.el.seeking && Math.abs(entry.el.currentTime - parked) > 0.001) entry.el.currentTime = parked;
    });
    if (!active.length) return time + dt;
    function target(entry) { return time - (entry.t0 || 0); }
    var waiting = active.some(function (entry) {
      return entry.el.seeking || (!entry.el.paused && entry.el.readyState < 3);
    });
    if (waiting) {
      active.forEach(function (entry) { entry.el.pause(); });
      return time;
    }
    var stopped = active.some(function (entry) { return entry.el.paused; });
    if (stopped) {
      var off = active.filter(function (entry) {
        return Math.abs(entry.el.currentTime - target(entry)) > PLAY_ALIGN_S;
      });
      active.forEach(function (entry) { entry.el.pause(); });
      if (off.length) {
        off.forEach(function (entry) { entry.el.currentTime = target(entry); });
        return time;
      }
      active.forEach(function (entry) {
        watchPresented(entry);
        entry.presented = null;  // the paused frame's presentation says nothing about playback
        entry.el.playbackRate = 1;
        entry.el.play().catch(function () {});
      });
      return time;
    }
    var clock = active[0];
    var next = shownTime(clock, now) + (clock.t0 || 0);
    active.slice(1).forEach(function (entry) {
      var drift = shownTime(entry, now) + (entry.t0 || 0) - next;
      if (Math.abs(drift) > PLAY_RESEEK_S) {
        entry.el.currentTime = next - (entry.t0 || 0);
        return;
      }
      entry.el.playbackRate = 1 - Math.max(-PLAY_NUDGE_LIMIT, Math.min(PLAY_NUDGE_LIMIT, PLAY_NUDGE_GAIN * drift));
    });
    return next;
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

  /* What an error is measured against: the run sitting in ``target`` (sim vs real has no
     target, so the report names whichever run is the reference). */
  function referenceTitle(data) {
    return data.reference_title || 'Target';
  }

  /* Difference on the display grid, reference - value (target - run, the ROS 2
     convention robot_msgs.compare uses): both columns are already resampled
     onto plot_t, and a null on either side (outside a run's own recorded
     span) stays a null so the gap survives instead of becoming a fake zero. */
  function difference(values, reference) {
    var out = new Array(values.length);
    for (var index = 0; index < values.length; index++) {
      var value = values[index], base = reference[index];
      out[index] = (value === null || base === null) ? null : base - value;
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

  // The frame fk / poses describe (Comparison.tcp_frame): "TCP", "L2 tip", ...
  function frameName(page) {
    return page.data.tcp_frame || 'TCP';
  }

  function tcpPoseBuilder(page, body) {
    var grid = el('div', 'tc-grid', body);
    var frame = frameName(page);
    [['x', frame + ' x', 'm'], ['y', frame + ' y', 'm'], ['z', frame + ' z', 'm'],
     ['rx', frame + ' rx', 'angle'], ['ry', frame + ' ry', 'angle'], ['rz', frame + ' rz', 'angle']]
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
    var frame = frameName(page);
    var minus = referenceTitle(page.data) + ' − run';
    // Combined magnitudes, then the path split (off the path vs behind along it),
    // then each world axis on its own (rotation as a rotation vector, not RPY).
    // Every error is target - run, as robot_msgs.compare computes it.
    [['xyz_mag', frame + ' position error |Δp|', 'mm'],
     ['rot_mag', frame + ' rotation error', 'angle'],
     ['cross_track', frame + ' cross-track error (off path)', 'mm'],
     ['lag', frame + ' lag (+ behind target)', 'mm'],
     ['err_x', frame + ' x error (' + minus + ')', 'mm'],
     ['err_y', frame + ' y error (' + minus + ')', 'mm'],
     ['err_z', frame + ' z error (' + minus + ')', 'mm'],
     ['err_rx', frame + ' rx error (' + minus + ')', 'angle'],
     ['err_ry', frame + ' ry error (' + minus + ')', 'angle'],
     ['err_rz', frame + ' rz error (' + minus + ')', 'angle']].forEach(function (row) {
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
        { title: jointName + ' — q error (' + referenceTitle(page.data) + ' − run)', kind: 'angle', series: series });
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

  /* ---------------- camera overlay: real video + sim render ---------------- */

  var FLICKER_PERIOD_MS = 250;  // real <-> sim swap, i.e. a 2 Hz blink

  function overlayLayer(stack, className) {
    var video = el('video', className, stack);
    video.muted = true;
    video.playsInline = true;
    video.preload = 'auto';
    return { el: video, path: '', failed: false };
  }

  function overlaySetSource(layer, path) {
    layer.path = path || '';
    layer.failed = !path;
    if (path) {
      layer.el.src = path;
    } else {
      layer.el.removeAttribute('src');
      layer.el.load();
    }
  }

  function overlayControl(parent, labelText) {
    var group = el('label', 'tc-ovl-ctl', parent);
    el('span', 'ctl-label', group, labelText);
    return group;
  }

  function buildOverlayCard(page, parent, overlay) {
    var key = 'overlay:' + overlay.name + ':';
    var card = el('div', 'tc-overlaycard', parent);
    card.dataset.overlay = overlay.name;
    var heading = el('div', 'vlabel', card, overlay.name);
    if (overlay.note) el('span', 'vnote', heading, ' — ' + overlay.note);

    // Real sits underneath at full opacity; only the sim layer carries the
    // slider. WHY: fading both layers lets the black box show through and
    // darkens the middle of the slider, and a single opacity makes 0 and 1
    // exactly "only real" / "only sim" — which is the comparison being made.
    var stack = el('div', 'tc-ovl-stack', card);
    var real = overlayLayer(stack, 'tc-ovl-real');
    var sim = overlayLayer(stack, 'tc-ovl-sim');
    var missing = el('div', 'tc-ovl-missing', stack);
    var user = { opacity: 0.5, sim: overlay.sims[0].label, blend: 'normal', flicker: false };
    var flickerPhase = false;
    var flickerTimer = null;

    var controls = el('div', 'tc-ovl-controls', card);
    var opacityGroup = overlayControl(controls, 'Real ◀ ▶ Sim');
    var slider = el('input', 'tc-ovl-opacity', opacityGroup);
    slider.type = 'range';
    slider.min = 0; slider.max = 1; slider.step = 0.01;
    var opacityOut = el('output', '', opacityGroup);
    var simGroup = overlayControl(controls, 'Sim');
    var simSelect = el('select', 'tc-ovl-simsel', simGroup);
    overlay.sims.forEach(function (entry) {
      var option = el('option', '', simSelect, entry.label);
      option.value = entry.label;
    });
    simSelect.disabled = overlay.sims.length < 2;
    var blendGroup = overlayControl(controls, 'Blend');
    var blendSelect = el('select', 'tc-ovl-blendsel', blendGroup);
    [['normal', 'Mix (normal)'], ['difference', 'Difference']].forEach(function (pair) {
      var option = el('option', '', blendSelect, pair[1]);
      option.value = pair[0];
    });
    var flickerChip = el('button', 'chip tc-ovl-flicker', controls, 'Flicker');
    flickerChip.title = 'alternate real and sim at 2 Hz for a blink comparison';

    function simPath(label) {
      for (var i = 0; i < overlay.sims.length; i++) {
        if (overlay.sims[i].label === label) return overlay.sims[i].video;
      }
      return overlay.sims[0].video;
    }

    function paint() {
      var flicker = user.flicker;
      sim.el.style.opacity = flicker ? (flickerPhase ? 1 : 0) : user.opacity;
      // the blend only reads sensibly against a steady layer, so a blink is plain
      sim.el.style.mixBlendMode = (user.blend === 'difference' && !flicker) ? 'difference' : 'normal';
      slider.value = user.opacity;
      slider.disabled = flicker;
      opacityOut.textContent = user.opacity.toFixed(2);
      simSelect.value = user.sim;
      blendSelect.value = user.blend;
      flickerChip.className = 'chip tc-ovl-flicker ' + (flicker ? 'on' : 'off');
      card.dataset.flickerPhase = flicker ? (flickerPhase ? 'sim' : 'real') : '';
      var lines = [];
      if (real.failed) lines.push('no video — real: ' + (real.path || '(no path)'));
      if (sim.failed) lines.push('no video — sim: ' + (sim.path || '(no path)'));
      missing.textContent = lines.join('\n');
      missing.style.display = lines.length ? '' : 'none';
      card.classList.toggle('missing', real.failed);
      real.el.style.visibility = real.failed ? 'hidden' : '';
      sim.el.style.visibility = sim.failed ? 'hidden' : '';
    }

    function setFlicker(on) {
      user.flicker = on;
      if (flickerTimer !== null) { clearInterval(flickerTimer); flickerTimer = null; }
      flickerPhase = false;
      if (on) {
        flickerTimer = setInterval(function () {
          flickerPhase = !flickerPhase;
          paint();
        }, FLICKER_PERIOD_MS);
      }
    }

    // The overlay videos join the page's video list, so seek/play/drag
    // coalescing is the Videos section's own code, not a copy of it.
    var realEntry = { sit: { name: 'overlay:' + overlay.name + ':real' }, el: real.el, card: card, t0: overlay.t0_s };
    var simEntry = { sit: { name: 'overlay:' + overlay.name + ':sim' }, el: sim.el, card: card, t0: overlay.t0_s };
    page.videos.push(realEntry, simEntry);

    function catchUp(layer, entry) {
      var transport = page.transport;
      if (!transport) return;
      // while playing, the transport's tick starts it once it sits on the clock
      seekEntry(entry, transport.t === null ? transport.tMax : transport.t);
    }
    [[real, realEntry], [sim, simEntry]].forEach(function (pair) {
      var layer = pair[0], entry = pair[1];
      layer.el.addEventListener('error', function () { layer.failed = true; paint(); });
      layer.el.addEventListener('loadedmetadata', function () {
        layer.failed = false;
        // one box, one aspect: the real stream decides it
        if (layer === real && layer.el.videoWidth) {
          stack.style.aspectRatio = layer.el.videoWidth + ' / ' + layer.el.videoHeight;
        }
        paint();
        catchUp(layer, entry);
      });
    });
    stack.addEventListener('click', function () {
      if (page.transport) page.transport.toggle();
    });

    slider.addEventListener('input', function () {
      user.opacity = parseFloat(slider.value);
      state.prefs.set(key + 'opacity', user.opacity);
      paint();
    });
    simSelect.addEventListener('change', function () {
      user.sim = simSelect.value;
      state.prefs.set(key + 'sim', user.sim);
      overlaySetSource(sim, simPath(user.sim));
      paint();
    });
    blendSelect.addEventListener('change', function () {
      user.blend = blendSelect.value;
      state.prefs.set(key + 'blend', user.blend);
      paint();
    });
    flickerChip.onclick = function () {
      setFlicker(!user.flicker);
      state.prefs.set(key + 'flicker', user.flicker);
      paint();
    };

    // Pull report-level choices (made on another scenario tab, or remembered
    // from last time) into this card; the sim source reloads only on a change.
    function applyShared() {
      user.opacity = Number(state.prefs.get(key + 'opacity', 0.5));
      user.blend = state.prefs.get(key + 'blend', 'normal') === 'difference' ? 'difference' : 'normal';
      var wantSim = state.prefs.get(key + 'sim', overlay.sims[0].label);
      var known = overlay.sims.some(function (entry) { return entry.label === wantSim; });
      if (!known) wantSim = overlay.sims[0].label;
      var simChanged = wantSim !== user.sim || !sim.path;
      user.sim = wantSim;
      var wantFlicker = !!state.prefs.get(key + 'flicker', false);
      if (wantFlicker !== user.flicker) setFlicker(wantFlicker);
      if (simChanged) overlaySetSource(sim, simPath(user.sim));
      paint();
    }

    overlaySetSource(real, overlay.real_video);
    page.overlayCards.push({ overlay: overlay, applyShared: applyShared });
    applyShared();
  }

  function cameraBuilder(page, body) {
    var grid = el('div', 'tc-overlaygrid', body);
    page.data.overlays.forEach(function (overlay) { buildOverlayCard(page, grid, overlay); });
    if (page.transport) buildTransportBar(page, body);
    el('div', 'tc-videonote', body,
      'The real stream is the base layer; the slider fades the sim render over it ' +
      '(Difference shows where they disagree). The scrubber drives both, offset by t0.');
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
    if (data.has_current) {
      defs.push({ id: 'joint-current', label: 'Motor current i', on: sectionStartsOn(data, 'joint-current', false), build: jointSectionBuilder('current', 'A', 'i') });
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
    if (data.has_overlay) {
      defs.push({ id: 'camera', label: 'Camera', on: sectionStartsOn(data, 'camera', true), build: cameraBuilder });
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
  var DELTA_SECTIONS = ['joint-q', 'joint-qd', 'joint-qdd', 'joint-tau', 'joint-current', 'tcp-pose', 'path'];

  function sectionHint(id, data) {
    var hint = '';
    if (id === 'path') {
      var reference = data.pct_reference === 'target' ? 'target path length' : 'own path length';
      hint = '% is of ' + reference + '; Vec is signed progress along the labeled direction';
    }
    if (id === 'tcp-err') {
      hint = (data.tcp_frame || 'TCP') + ' frame, error = ' + referenceTitle(data) + ' − run at the run\'s own sample times; ' +
        'axis errors are world-frame, rotation as a world-axis rotation vector; ' +
        'lag is + when the run is behind the target';
    }
    if (id === 'tcp-pose') hint = (data.tcp_frame || 'TCP') + ' frame';
    if (id === 'videos') hint = 'always played together, seeked by the scrubber';
    if (id === 'camera') hint = 'real video under the sim render; both follow the scrubber';
    if (id === 'viewer3d') hint = 'hover any plot to preview that instant; scrub below the canvas';
    // tau and current are optional on the target; no target trace, no Δ to draw
    var needs = { 'joint-tau': 'tau', 'joint-current': 'current' }[id];
    var hasTarget = data.situations.some(function (sit) {
      return sit.role === 'target' && sit.plot && (!needs || sit.plot[needs]);
    });
    if (hasTarget && DELTA_SECTIONS.indexOf(id) !== -1) {
      hint += (hint ? ' · ' : '') +
        'Error (' + referenceTitle(data) + ' − run) draws a dotted Δ here; hide target + measured to read it on its own axis';
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
    (data.images || []).forEach(function (image) { buildFigure(page.el, image); });
    buildInsightCards(page.el, data.insights);
  }

  function buildFigure(parent, image) {
    var figure = el('figure', 'tc-figure', parent);
    el('h3', '', figure, image.title);
    var img = el('img', '', figure);
    img.src = image.src;
    img.alt = image.title;
    if (image.width_px) img.style.width = image.width_px + 'px';
    if (image.caption) el('figcaption', '', figure, image.caption);
  }

  /* ---- Open in Rerun ------------------------------------------------------------------------
     The .rrd beside this report is the same data in Rerun (WHY: Tracking-Run Data — data-ui vs
     Rerun, 2026-10-26: the viewer is one projection, Rerun the other). Served by
     ``python -m traj_compare.serve`` the primary button starts the pinned viewer through the
     server; from file:// or a plain static server there is nothing to start it, so it copies the
     command instead. Either way the command stays on screen. */
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; },
        function () { return copyTextFallback(text); });
    }
    return Promise.resolve(copyTextFallback(text));
  }

  function copyTextFallback(text) {
    var area = el('textarea', '', document.body, text);
    area.style.cssText = 'position:fixed;left:-9999px;top:0';
    area.select();
    var done = false;
    try { done = document.execCommand('copy'); } catch (error) { done = false; }
    document.body.removeChild(area);
    return done;
  }

  function buildRerunBar(root, info) {
    var served = location.protocol === 'http:' || location.protocol === 'https:';
    var rrdUrl = new URL(info.rrd, location.href);
    var bar = el('div', 'tc-rerun', root);
    var row = el('div', 'tc-rerun-row', bar);
    var open = el('button', 'tc-rerun-open', row, 'Open in Rerun');
    var copy = el('button', 'tc-rerun-btn', row, 'Copy command');
    var download = el('a', 'tc-rerun-btn', row, 'Download .rrd');
    download.href = info.rrd;
    download.setAttribute('download', '');
    if (served) {
      var web = el('a', 'tc-rerun-btn', row, 'Rerun in browser');
      web.href = 'https://app.rerun.io/version/' + info.sdk + '/index.html?url=' +
        encodeURIComponent(rrdUrl.href);
      web.target = '_blank';
      web.rel = 'noopener';
      web.title = 'the web viewer fetches the .rrd from this server; it needs the serve command';
    }
    var status = el('span', 'tc-rerun-status', row);
    var command = el('code', 'tc-rerun-cmd', bar, info.command);
    command.title = 'Rerun ' + info.sdk + ' (an .rrd needs a viewer at least as new as its SDK)';

    function say(text, bad) {
      status.textContent = text;
      status.classList.toggle('bad', !!bad);
    }
    function copyCommand(prefix) {
      return Promise.resolve(copyText(info.command)).then(function (ok) {
        say(ok ? prefix + 'command copied — paste it in a terminal' : prefix + 'copy failed — select the command below');
      });
    }
    copy.onclick = function () { copyCommand(''); };
    open.onclick = function () {
      if (!served) { copyCommand('No launcher on file:// — '); return; }
      say('Opening Rerun…');
      // The endpoint wants a path relative to the served root, not to this page.
      var relative = decodeURIComponent(rrdUrl.pathname.replace(/^\//, ''));
      fetch(location.origin + '/__rerun/open?rrd=' + encodeURIComponent(relative), { method: 'POST' })
        .then(function (response) {
          return response.text().then(function (text) {
            var body = null;
            try { body = JSON.parse(text); } catch (error) { body = null; }
            if (body && body.ok) { say('Opening Rerun… (the window can take a few seconds)'); return; }
            if (body && body.error) { say(body.error, true); return; }
            // Not our server: a plain static server answers 404/405/501 for the POST.
            return copyCommand('No launcher on this server — ');
          });
        }, function () { return copyCommand('No launcher reachable — '); });
    };
  }

  function buildPage(page) {
    var data = page.data;
    var root = page.el;

    if (data.plot_t) page.transport = makeTransport(page);

    el('h2', 'tc-page-title', root, data.title);
    if (data.description) el('p', 'tc-desc', root, data.description);
    if (data.rerun) buildRerunBar(root, data.rerun);
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
      page.overlayCards.forEach(function (card) { card.applyShared(); });
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
    // Robot link meshes are stored once per report; links carry an index.
    var meshLibrary = payload.mesh_library || [];
    payload.comparisons.forEach(function (data) {
      (data.robots || []).forEach(function (model) {
        model.links.forEach(function (link) {
          if (typeof link.tris === 'number') link.tris = meshLibrary[link.tris];
        });
      });
    });
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
        overlayCards: [],
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
