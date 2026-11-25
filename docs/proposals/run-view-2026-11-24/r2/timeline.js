/* RUN-VIEW ROUND 2026-11-24 · R2 "One timeline for the page": the docked time lane (new in this variant; plots.js calls
 * TrajCompareTimeline.create(page, hosts, kit) from buildPage, every call site marked `RV:`).
 *
 * One time control for the whole page, docked under the question tabs, like a video editor's timeline:
 *   - transport (to start, step back, play / pause, step forward, to end) and the time readout `t / tMax s`;
 *   - a time ruler whose x pixels are EXACTLY the charts' plotting x range (measured from a shown chart's `.u-over`), so
 *     the ONE playhead line through the charts (`[data-rv-playhead]`, in the sheet) and the ruler's grip line up.
 *     Press and drag on the ruler, on its grip or on any run's track scrubs, live. The ruler IS the page's slider:
 *     `[data-rv-slider]` with `data-rv-time` = the committed time (role="slider", arrow keys step);
 *   - one thin track per run: its colour, its full name (ellipsized, whole in `title`), an eye (`[data-rv-run]`: the
 *     run's on/off everywhere), its Δ overlay toggle, its error at the playhead, a band of its largest joint error over
 *     time and its moments (worst moment, error rises, limit violations): click one to go there;
 *   - a zoom bar over the full time range: drag a range = zoom every chart, drag the window = pan, its edges = resize,
 *     the wheel over the ruler or the zoom bar = zoom around the pointer, Full range = reset.
 * The lane's height drags and folds, and the boundary between the names and the time drags (the charts' title column
 * follows): all three are remembered (kit.store: localStorage inside try/catch).
 */
var TrajCompareTimeline = (function () {
  'use strict';

  var ROW_H = 22;          // a run's track
  var GROUP_H = 19;        // a config's row above its runs
  var VISIBLE_TRACKS = 6;  // WHY (R2 brief): the lane shows about six tracks, then its track list scrolls
  var HEAD_W = { fallback: 216, min: 140, max: 440 };
  var LANE_MIN_PX = 120;
  var GRID_MIN_TICK_PX = 64;

  function svg(body, size) {
    var s = size || 14;
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' + body + '</svg>';
  }
  var ICON = {
    start: svg('<rect x="4" y="5" width="2.4" height="14" rx="1"/><path d="M13 5.5v13L6.8 12z"/><path d="M20 5.5v13L13.8 12z"/>'),
    back: svg('<path d="M15 5.5v13L6 12z"/><rect x="16.6" y="5" width="2.4" height="14" rx="1"/>'),
    play: svg('<path d="M7.5 4.8v14.4L19.5 12z"/>'),
    pause: svg('<rect x="6.5" y="5" width="3.8" height="14" rx="1"/><rect x="13.7" y="5" width="3.8" height="14" rx="1"/>'),
    forward: svg('<rect x="5" y="5" width="2.4" height="14" rx="1"/><path d="M9 5.5v13L18 12z"/>'),
    end: svg('<path d="M4 5.5v13L10.2 12z"/><path d="M11 5.5v13L17.2 12z"/><rect x="17.6" y="5" width="2.4" height="14" rx="1"/>'),
    prev: svg('<path d="M15.5 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>', 12),
    next: svg('<path d="M8.5 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>', 12),
    worst: svg('<path d="M12 3.5l8.5 8.5-8.5 8.5L3.5 12z"/>', 11),
    fold: svg('<path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>', 13),
    unfold: svg('<path d="M6 15l6-6 6 6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>', 13),
  };
  // the stage's own eye (viewer3d.js), so the lane's run toggle reads as the same control
  var EYE_OPEN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">' +
    '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.6"/></svg>';
  var EYE_CLOSED = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">' +
    '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/><line x1="4" y1="20" x2="20" y2="4"/></svg>';

  // A 1-2-5 step that leaves at least ``minPx`` between ticks.
  function niceStep(span, px, minPx) {
    var raw = span / Math.max(1, px / minPx);
    var pow = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var mantissa = raw / pow;
    return (mantissa <= 1 ? 1 : mantissa <= 2 ? 2 : mantissa <= 5 ? 5 : 10) * pow;
  }
  function decimalsFor(step) { return Math.max(0, -Math.floor(Math.log(step) / Math.LN10 + 1e-9)); }

  function withAlpha(colour, alpha) {
    var hex = /^#([0-9a-f]{6})$/i.exec(colour || '');
    if (!hex) return colour;
    var n = parseInt(hex[1], 16);
    return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
  }

  function create(page, hosts, kit) {
    var el = kit.el;
    var transport = page.transport;
    var data = page.data;
    var grid = data.plot_t;
    var fullSpan = transport.tMax - transport.tMin;
    var minStep = Infinity;
    for (var i = 1; i < grid.length; i++) minStep = Math.min(minStep, grid[i] - grid[i - 1]);
    var minSpan = Math.max(minStep * 8, fullSpan * 0.01);

    var T = { page: page };
    var G = { x0: null, xw: null, chart: null, overLeft: 0, top: 0, ok: false };
    var drawnKey = '';
    var queued = false;
    var hoverT = null;
    var following = false;

    function committed() { return transport.t === null ? transport.tMax : transport.t; }
    function snap(time) { return grid[kit.nearestIndex(grid, time)]; }
    function store(key, value) { kit.store('rv2:' + key, value); }
    function recall(key, fallback) { return kit.recall('rv2:' + key, fallback); }

    /* ---------------- run data: error bands and moments ---------------- */

    var sits = data.situations;
    var runs = sits.filter(function (sit) { return sit.role !== 'target'; });
    var reference = kit.referenceTitle(data);
    var envelope = {};   // run name -> largest |reference − run| over every joint, per plot sample (radians)
    var peakAll = 0;
    runs.forEach(function (sit) {
      if (!sit.has_data || !sit.plot || !sit.plot.err_q) return;
      var env = kit.maxAbsOverJoints(sit.plot.err_q);
      envelope[sit.name] = env;
      env.forEach(function (value) { if (value !== null && value > peakAll) peakAll = value; });
    });

    // The moments a run's track marks. WHY these three (R2 brief): "when was it worst?" is the page's first question;
    // where the error starts to climb is the cause to look at; a broken limit is the verdict's own evidence.
    function momentsOf(sit) {
      var out = [];
      var env = envelope[sit.name];
      if (env) {
        var worst = kit.worstMoment(data, sit);
        if (worst) out.push({ kind: 'worst', t: worst.t, size: worst.size, joint: worst.joint });
        var peak = worst ? worst.size : 0;
        for (var index = 0; index < env.length && peak > 0; index++) {
          if (env[index] !== null && env[index] > peak / 2) {
            // a spike: the first sample above half the peak IS the worst moment, so one marker says both
            if (!worst || Math.abs(grid[index] - worst.t) > minStep * 1.5) out.push({ kind: 'rise', t: grid[index], size: peak / 2 });
            break;
          }
        }
      }
      // limit violations (robot_msgs.compare.check, Situation.verdict): each broken limit at its own time
      if (sit.verdict) {
        ['joint', 'tcp'].forEach(function (key) {
          var outcome = sit.verdict[key];
          ((outcome && outcome.violations) || []).forEach(function (violation) {
            if (isFinite(violation.t)) out.push({ kind: 'limit', t: violation.t, violation: violation });
          });
        });
      }
      return out;
    }

    function momentTitle(sit, moment) {
      var go = ' · click to go there';
      if (moment.kind === 'worst') {
        var where = page.parts.length > 1 ? page.parts[kit.partIndexOf(page, moment.joint)].name + ' · ' + moment.joint : moment.joint;
        return sit.title + ': worst moment, ' + kit.angleText(moment.size) + ' on ' + where + ' at t = ' + moment.t.toFixed(2) +
          ' s (largest |' + reference + ' − run| over every joint)' + go;
      }
      if (moment.kind === 'rise') {
        return sit.title + ': error rises, first above half its own peak (' + kit.angleText(moment.size) + ') at t = ' +
          moment.t.toFixed(2) + ' s' + go;
      }
      return sit.title + ': limit broken, ' + (moment.violation.phase ? moment.violation.phase + ' · ' : '') +
        kit.violationText(moment.violation) + go;
    }

    /* ---------------- DOM ---------------- */

    var lane = el('section', 'rv-lane', hosts.column);
    lane.setAttribute('data-rv-lane', '');
    lane.setAttribute('aria-label', 'Time lane: one time control for every chart and the 3D view');
    var sizer = el('div', 'rv-lane-resize', lane);
    sizer.setAttribute('role', 'separator');
    sizer.setAttribute('aria-orientation', 'horizontal');
    sizer.title = 'drag to resize the time lane · double-click for the default height';

    // toolbar
    var bar = el('div', 'rv-lane-bar', lane);
    function tool(parent, html, title, onClick, cls) {
      var button = el('button', 'tc-tbtn rv-tool' + (cls ? ' ' + cls : ''), parent);
      button.type = 'button';
      button.innerHTML = html;
      button.title = title;
      button.setAttribute('aria-label', title);
      button.onclick = onClick;
      return button;
    }
    var transportGroup = el('div', 'rv-bar-group', bar);
    tool(transportGroup, ICON.start, 'to start', function () { transport.pause(); transport.setScrub(transport.tMin); });
    tool(transportGroup, ICON.back, 'step back one sample (← on the ruler)', function () { transport.stepBy(-1); });
    var playButton = tool(transportGroup, ICON.play, 'play / pause (Space on the ruler)', function () { transport.toggle(); }, 'rv-play');
    tool(transportGroup, ICON.forward, 'step forward one sample (→ on the ruler)', function () { transport.stepBy(1); });
    tool(transportGroup, ICON.end, 'to end', function () { transport.pause(); transport.setScrub(transport.tMax); });
    var readout = el('span', 'tc-time rv-readout', bar);
    readout.title = 'the committed time / the end of the motion';

    var momentGroup = el('div', 'rv-bar-group rv-moments', bar);
    tool(momentGroup, ICON.prev, 'previous marked moment of a shown run', function () { jumpMoment(-1); });
    var worstButton = tool(momentGroup, ICON.worst + '<span>Worst moment</span>', '', function () { jumpWorst(); }, 'rv-worst');
    tool(momentGroup, ICON.next, 'next marked moment of a shown run', function () { jumpMoment(1); });

    el('span', 'rv-bar-spacer', bar);
    var viewText = el('span', 'rv-view-text', bar);
    var fullButton = tool(bar, 'Full range', 'show the whole motion on every chart (the zoom bar\'s whole width)', function () { reset(); }, 'rv-full');
    fullButton.setAttribute('data-rv-zoom-reset', '');
    if (hosts.units) { hosts.units.classList.add('rv-units'); bar.appendChild(hosts.units); }  // the Angles deg / rad chips
    var foldButton = tool(bar, ICON.fold, '', function () { setFolded(!folded, true); }, 'rv-fold');

    // body: ruler, tracks, zoom bar
    var body = el('div', 'rv-lane-body', lane);
    // the tracks' header (how many runs, what a band means) sits above the ruler, so the ruler touches the tracks and
    // the lane's playhead runs from the ruler's grip straight down through them
    var legendRow = el('div', 'rv-row rv-legend-row', body);
    var legendHead = el('div', 'rv-rhead', legendRow);
    el('span', 'rv-grouplabel', legendHead, 'Runs');
    var countText = el('span', 'rv-count-text', legendHead);
    var legend = el('div', 'rv-time rv-legend', legendRow);

    var rulerRow = el('div', 'rv-row rv-ruler-row', body);
    var rulerHead = el('div', 'rv-rhead', rulerRow);
    el('span', 'rv-grouplabel', rulerHead, 'Time [s]');
    var nowLabel = el('span', 'rv-now-label', rulerHead, 'error at t');
    nowLabel.title = 'each run\'s largest joint error at the committed time, max over joints of |' + reference + ' − run|';
    var ruler = el('div', 'rv-time rv-ruler', rulerRow);
    ruler.setAttribute('data-rv-slider', '');
    ruler.setAttribute('role', 'slider');
    ruler.setAttribute('tabindex', '0');
    ruler.setAttribute('aria-label', 'Time');
    ruler.setAttribute('aria-valuemin', String(transport.tMin));
    ruler.setAttribute('aria-valuemax', String(transport.tMax));
    ruler.title = 'press and drag: move the time on every chart and the 3D · wheel: zoom · ← →: step · Space: play';
    var rulerCanvas = el('canvas', 'rv-canvas', ruler);
    var grip = el('div', 'rv-grip', ruler);
    grip.title = 'the time is outside the zoomed range: click to bring it into view';
    grip.addEventListener('pointerdown', function (event) {
      if (!grip.classList.contains('edge')) return;
      event.stopPropagation();
      event.preventDefault();
      var v = view(), span = v[1] - v[0], t = committed();
      setView(t - span / 2, t + span / 2);
    });
    var gripTip = el('div', 'rv-grip-tip', ruler);

    var tracks = el('div', 'rv-tracks', body);
    tracks.setAttribute('data-rv-tracks', '');
    tracks.title = '';

    var rangeRow = el('div', 'rv-row rv-range-row', body);
    var rangeHead = el('div', 'rv-rhead', rangeRow);
    el('span', 'rv-grouplabel', rangeHead, 'Zoom');
    var rangeHint = el('span', 'rv-range-hint', rangeHead, 'drag a range');
    var range = el('div', 'rv-time rv-range', rangeRow);
    range.setAttribute('data-rv-range', '');
    range.title = 'the whole motion: drag a range to zoom every chart · drag the window to pan, its edges to resize · wheel: zoom · double-click: full range';
    var rangeCanvas = el('canvas', 'rv-canvas', range);
    var rangeWindow = el('div', 'rv-window', range);
    el('span', 'rv-window-edge left', rangeWindow);
    el('span', 'rv-window-edge right', rangeWindow);
    var rangeTick = el('div', 'rv-range-tick', range);

    var laneLine = el('div', 'rv-lane-line', body);
    var laneGhost = el('div', 'rv-lane-line ghost', body);
    var colHandle = el('div', 'rv-col-resize', body);
    colHandle.setAttribute('role', 'separator');
    colHandle.setAttribute('aria-orientation', 'vertical');
    colHandle.title = 'drag: widen the names column (the charts\' title column follows) · double-click: default';

    // the ONE playhead line through every chart, and its hover ghost
    var line = el('div', 'rv-line', hosts.sheet);
    line.setAttribute('data-rv-playhead', '');
    line.setAttribute('aria-hidden', 'true');
    var ghost = el('div', 'rv-line ghost', hosts.sheet);
    ghost.setAttribute('aria-hidden', 'true');

    /* ---------------- tracks ---------------- */

    var rows = [];
    var groupRows = [];
    function chipOf(list, name) { return list.filter(function (entry) { return entry.sit.name === name; })[0] || null; }

    function addTrack(sit, group) {
      var row = el('div', 'rv-row rv-track', tracks);
      row.setAttribute('data-rv-track', sit.name);
      var head = el('div', 'rv-rhead', row);
      var record = { sit: sit, el: row, group: group, moments: [], markEls: [] };
      var isTarget = sit.role === 'target';
      if (!sit.has_data) {
        row.classList.add('nodata');
        el('span', 'rv-eye-gap', head);
        var deadSwatch = el('span', 'rv-swatch', head);
        deadSwatch.style.background = sit.color;
        var deadName = el('span', 'rv-name', head, sit.title);
        deadName.title = sit.title + ' (no data' + (sit.note ? ' — ' + sit.note : '') + ')';
        el('div', 'rv-time rv-track-note', row, 'no data' + (sit.note ? ' — ' + sit.note : ''));
        rows.push(record);
        return;
      }
      var chip = chipOf(page.sitChips, sit.name);
      var eye = el('button', 'rv-eye', head);
      eye.type = 'button';
      eye.setAttribute('data-rv-run', sit.name);
      eye.onclick = function () {
        if (!chip) return;
        chip.apply(page.visible[sit.name] === false, true);
        paintSelection();
      };
      record.eye = eye;
      var swatch = el('span', 'rv-swatch' + (isTarget ? ' dashed' : ''), head);
      swatch.style.background = sit.color;
      swatch.style.color = sit.color;
      // WHY two parts (Zach's rule: never truncate a name silently): under its config's row the config prefix is the
      // part that may ellipsize; the repeat and sim/real that tell the lines apart always stay; the whole name is the title
      var name = el('span', 'rv-name', head);
      var prefix = group && group.title && sit.title.indexOf(group.title) === 0 ? group.title : '';
      if (prefix && sit.title.length > prefix.length) {
        el('span', 'rv-name-pre', name, prefix);
        el('span', 'rv-name-post', name, sit.title.slice(prefix.length));
      } else {
        el('span', 'rv-name-pre', name, sit.title);
      }
      var badge = kit.verdictBadge ? kit.verdictBadge(sit) : null;
      if (badge) head.appendChild(badge);
      name.title = sit.title + (sit.time_offset_s ? ' · errors taken with its clock shifted ' + sit.time_offset_s * 1000 + ' ms earlier' : '') +
        (isTarget ? ' · the reference every error is measured against' : '');
      if (!isTarget) record.value = el('span', 'rv-value', head);
      var errChip = chipOf(page.errChips, sit.name);
      if (isTarget) {
        // the reference has no error of its own: its name takes the value and Δ columns
      } else if (errChip) {
        var delta = el('button', 'rv-delta', head, 'Δ');
        delta.type = 'button';
        delta.title = 'Δ: draw ' + reference + ' − ' + sit.title + ' on every plot that has it (dotted)';
        delta.onclick = function () { errChip.apply(!page.errorOn[sit.name], true); paintSelection(); };
        record.delta = delta;
      } else {
        el('span', 'rv-delta-gap', head);
      }
      var time = el('div', 'rv-time rv-track-time', row);
      record.time = time;
      record.canvas = el('canvas', 'rv-canvas', time);
      if (isTarget) {
        record.note = el('span', 'rv-track-note', time, 'the reference: every error is ' + reference + ' − run');
      }
      record.moments = isTarget ? [] : momentsOf(sit);
      record.moments.forEach(function (moment) {
        var mark = el('button', 'rv-mark ' + moment.kind, time);
        mark.type = 'button';
        mark.innerHTML = moment.kind === 'worst' ? '<i></i>' : moment.kind === 'rise' ? '<i></i>' : '×';
        mark.style.color = sit.color;
        mark.setAttribute('data-rv-moment', moment.kind);
        mark.onpointerdown = function (event) { event.stopPropagation(); };
        mark.onclick = function (event) {
          event.stopPropagation();
          transport.pause();
          transport.setScrub(moment.t);
        };
        moment.el = mark;
        record.markEls.push(mark);
      });
      rows.push(record);
    }

    /* A config's row: like a DAW's folder track it collapses its runs' tracks (remembered; a config none of whose runs
       arrived in keep= starts collapsed, so 17 runs in 8 configs open as one screen) and its eye toggles all of them. */
    function addGroup(group) {
      var row = el('div', 'rv-row rv-group', tracks);
      row.setAttribute('data-rv-group', group.key);
      var head = el('div', 'rv-rhead', row);
      var fold = el('button', 'rv-group-fold', head);
      fold.type = 'button';
      var remembered = recall('group-collapsed:' + group.key, null);
      group.collapsed = remembered === null ? !group.sits.some(function (sit) { return page.visible[sit.name] !== false; }) : !!remembered;
      fold.onclick = function () {
        group.collapsed = !group.collapsed;
        store('group-collapsed:' + group.key, group.collapsed);
        paintSelection();
      };
      var eye = el('button', 'rv-eye small', head);
      eye.type = 'button';
      eye.onclick = function () {
        var shown = group.sits.filter(function (sit) { return page.visible[sit.name] !== false; });
        var show = shown.length === 0;
        group.sits.forEach(function (sit) {
          var chip = chipOf(page.sitChips, sit.name);
          if (chip && (page.visible[sit.name] !== false) !== show) chip.apply(show, true);
        });
        paintSelection();
      };
      var label = el('span', 'rv-group-name', head, group.title || 'Runs');
      label.title = group.title;
      var count = el('span', 'rv-group-count', head);
      groupRows.push({ group: group, el: row, eye: eye, count: count, fold: fold });
    }

    (function buildTracks() {
      var target = sits.filter(function (sit) { return sit.role === 'target'; })[0];
      if (target) addTrack(target, null);
      var groups = [], byKey = {};
      runs.forEach(function (sit) {
        var key = sit.group || '';
        if (!byKey[key]) { byKey[key] = { key: key, title: sit.group_title || sit.group || '', sits: [] }; groups.push(byKey[key]); }
        byKey[key].sits.push(sit);
      });
      var grouped = groups.length > 1;
      groups.forEach(function (group) {
        if (grouped) addGroup(group);
        group.sits.forEach(function (sit) { addTrack(sit, grouped ? group : null); });
      });
    })();

    var anyLimit = rows.some(function (row) { return row.moments.some(function (moment) { return moment.kind === 'limit'; }); });
    (function buildLegend() {
      var unitWord = function () { return kit.state.unit === 'deg' ? '°' : 'rad'; };
      var band = el('span', 'rv-legend-item', legend);
      el('i', 'rv-key band', band);
      var bandText = el('span', '', band);
      var worst = el('span', 'rv-legend-item', legend);
      el('i', 'rv-key worst', worst);
      el('span', '', worst, 'worst moment');
      var rise = el('span', 'rv-legend-item', legend);
      el('i', 'rv-key rise', rise);
      el('span', '', rise, 'error rises (first above half its peak)');
      if (anyLimit) {
        var limit = el('span', 'rv-legend-item', legend);
        el('i', 'rv-key limit', limit, '×');
        el('span', '', limit, 'limit broken');
      }
      function paint() {
        bandText.textContent = 'largest joint error, max over joints of |' + reference + ' − run| [' + unitWord() + ']' +
          (peakAll ? ', one scale, top = ' + kit.angleText(peakAll) : '');
        legend.title = 'Each run\'s band: ' + bandText.textContent + '. ◆ its worst moment; ▲ where its error first passes ' +
          'half of its own peak' + (anyLimit ? '; × a limit it broke' : '') + '. Click a marker to go there.';
      }
      paint();
      page.unitRepaints.push(paint);
    })();

    /* ---------------- geometry: the charts' x pixels ---------------- */

    function refChart() {
      var tab = kit.activeTab(page);
      if (!tab) return null;
      for (var index = 0; index < page.charts.length; index++) {
        var chart = page.charts[index];
        if (chart.u && tab.panel.contains(chart.card) && chart.card.offsetParent && chart.card.offsetWidth) return chart;
      }
      return null;
    }

    function view() {
      var chart = G.chart && G.chart.u ? G.chart : refChart();
      if (chart && chart.u && isFinite(chart.u.scales.x.min) && chart.u.scales.x.max > chart.u.scales.x.min) {
        return [chart.u.scales.x.min, chart.u.scales.x.max];
      }
      var zoom = page.xZoom;
      if (zoom && isFinite(zoom.min) && isFinite(zoom.max) && zoom.max > zoom.min) return [zoom.min, zoom.max];
      return [transport.tMin, transport.tMax];
    }
    function isZoomed(v) { return v[1] - v[0] < fullSpan - 1e-9; }

    function headWidth() { return Number(recall('head-w', null)) || HEAD_W.fallback; }
    function setHeadWidth(width, remember) {
      var w = Math.round(Math.max(HEAD_W.min, Math.min(HEAD_W.max, Number(width) || HEAD_W.fallback)));
      page.el.style.setProperty('--rv-head-w', w + 'px');
      T.headW = w;
      if (remember) store('head-w', width === null ? null : w);
      var tab = kit.activeTab(page);
      if (tab) kit.resizeChartsIn(page, tab.panel);
      queue();
    }

    function measure() {
      var chart = refChart();
      var bodyBox = body.getBoundingClientRect();
      G.chart = chart;
      if (chart) {
        var over = chart.u.over.getBoundingClientRect();
        var sheetBox = hosts.sheet.getBoundingClientRect();
        G.x0 = over.left - bodyBox.left;
        G.xw = over.width;
        G.overLeft = over.left - sheetBox.left;
        G.top = over.top - sheetBox.top;
        G.ok = true;
      } else if (G.x0 === null) {
        // no chart on this tab yet: the stacked chart's geometry (card border + title column + y axis)
        G.x0 = 1 + (T.headW || HEAD_W.fallback) + 56;
        G.xw = Math.max(120, bodyBox.width - G.x0 - 34);
      }
      if (!chart) G.ok = false;
    }

    function sizeCanvas(canvas, w, h) {
      var ratio = window.devicePixelRatio || 1;
      var W = Math.max(1, Math.round(w * ratio)), H = Math.max(1, Math.round(h * ratio));
      if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
      canvas.style.width = w + 'px';
      canvas.style.height = h + 'px';
      var ctx = canvas.getContext('2d');
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, w, h);
      return ctx;
    }

    function cssVar(name, fallback) {
      var value = getComputedStyle(lane).getPropertyValue(name);
      return value && value.trim() ? value.trim() : fallback;
    }

    function drawRuler(v) {
      var w = G.xw, h = ruler.clientHeight || 26;
      var ctx = sizeCanvas(rulerCanvas, w, h);
      var span = v[1] - v[0];
      var step = niceStep(span, w, GRID_MIN_TICK_PX);
      var minor = step / (Math.abs(step / Math.pow(10, Math.floor(Math.log(step) / Math.LN10)) - 2) < 1e-9 ? 4 : 5);
      var decimals = decimalsFor(step);
      ctx.strokeStyle = cssVar('--rv-tick', '#c9c8c2');
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (var t = Math.ceil(v[0] / minor - 1e-9) * minor; t <= v[1] + 1e-9; t += minor) {
        var x = Math.round((t - v[0]) / span * w) + 0.5;
        ctx.moveTo(x, h - 4);
        ctx.lineTo(x, h);
      }
      ctx.stroke();
      ctx.strokeStyle = cssVar('--rv-tick-major', '#a8a7a2');
      ctx.fillStyle = cssVar('--rv-tick-text', '#6f6e69');
      ctx.font = '10.5px -apple-system, "Segoe UI", Roboto, sans-serif';
      ctx.textBaseline = 'alphabetic';
      ctx.beginPath();
      for (var major = Math.ceil(v[0] / step - 1e-9) * step; major <= v[1] + 1e-9; major += step) {
        var xm = Math.round((major - v[0]) / span * w) + 0.5;
        ctx.moveTo(xm, h - 8);
        ctx.lineTo(xm, h);
        var label = (Math.abs(major) < 1e-12 ? 0 : major).toFixed(decimals);
        var tw = ctx.measureText(label).width;
        ctx.fillText(label, Math.max(1, Math.min(w - tw - 1, xm - tw / 2)), h - 11);
      }
      ctx.stroke();
    }

    function drawBand(record, v) {
      var w = G.xw, h = ROW_H - 1;
      var ctx = sizeCanvas(record.canvas, w, h);
      var env = envelope[record.sit.name];
      if (!env || !peakAll) {
        if (record.sit.role === 'target') {  // the reference: a dashed midline in its own grey
          ctx.strokeStyle = withAlpha(record.sit.color, 0.55);
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          ctx.moveTo(0, Math.round(h / 2) + 0.5);
          ctx.lineTo(w, Math.round(h / 2) + 0.5);
          ctx.stroke();
        }
        return;
      }
      var on = page.visible[record.sit.name] !== false;
      var colour = on ? record.sit.color : cssVar('--rv-off', '#b9b8b2');
      var span = v[1] - v[0];
      var lo = Math.max(0, kit.nearestIndex(grid, v[0]) - 1), hi = Math.min(grid.length - 1, kit.nearestIndex(grid, v[1]) + 1);
      var base = h - 2.5, room = h - 5;
      ctx.beginPath();
      var started = false, lastX = 0;
      for (var index = lo; index <= hi; index++) {
        var value = env[index];
        if (value === null || value === undefined) continue;
        var x = (grid[index] - v[0]) / span * w;
        var y = base - value / peakAll * room;
        if (!started) { ctx.moveTo(x, base); started = true; }
        ctx.lineTo(x, y);
        lastX = x;
      }
      if (!started) return;
      ctx.lineTo(lastX, base);
      ctx.closePath();
      ctx.fillStyle = withAlpha(colour, on ? 0.2 : 0.14);
      ctx.fill();
      ctx.beginPath();
      started = false;
      for (var j = lo; j <= hi; j++) {
        var val = env[j];
        if (val === null || val === undefined) continue;
        var xj = (grid[j] - v[0]) / span * w, yj = base - val / peakAll * room;
        if (!started) { ctx.moveTo(xj, yj); started = true; } else ctx.lineTo(xj, yj);
      }
      ctx.strokeStyle = withAlpha(colour, on ? 0.9 : 0.5);
      ctx.lineWidth = 1.1;
      ctx.stroke();
    }

    function placeMarks(record, v) {
      var span = v[1] - v[0];
      record.moments.forEach(function (moment) {
        var x = (moment.t - v[0]) / span * G.xw;
        var inside = x >= -1 && x <= G.xw + 1;
        moment.el.style.display = inside ? '' : 'none';
        if (inside) moment.el.style.left = x + 'px';
      });
    }

    function drawRange(v) {
      var w = G.xw, h = range.clientHeight || 22;
      var ctx = sizeCanvas(rangeCanvas, w, h);
      // the overview: the largest joint error of the shown runs, so the zoom bar is a map of where to look
      var shown = runs.filter(function (sit) { return envelope[sit.name] && page.visible[sit.name] !== false; });
      if (shown.length && peakAll) {
        var top = 0, maxOf = new Array(grid.length);
        for (var index = 0; index < grid.length; index++) {
          var best = null;
          shown.forEach(function (sit) { var value = envelope[sit.name][index]; if (value !== null && (best === null || value > best)) best = value; });
          maxOf[index] = best;
          if (best !== null && best > top) top = best;
        }
        ctx.beginPath();
        ctx.moveTo(0, h - 2);
        for (var k = 0; k < grid.length; k++) {
          if (maxOf[k] === null) continue;
          ctx.lineTo((grid[k] - transport.tMin) / fullSpan * w, h - 2 - maxOf[k] / (top || 1) * (h - 6));
        }
        ctx.lineTo(w, h - 2);
        ctx.closePath();
        ctx.fillStyle = cssVar('--rv-overview', 'rgba(82, 81, 78, 0.16)');
        ctx.fill();
      }
      // full-range ticks, light
      var step = niceStep(fullSpan, w, 90);
      ctx.strokeStyle = cssVar('--rv-tick', '#c9c8c2');
      ctx.beginPath();
      for (var t = Math.ceil(transport.tMin / step) * step; t <= transport.tMax + 1e-9; t += step) {
        var x = Math.round((t - transport.tMin) / fullSpan * w) + 0.5;
        ctx.moveTo(x, 0);
        ctx.lineTo(x, 4);
      }
      ctx.stroke();
      var left = (v[0] - transport.tMin) / fullSpan * w, right = (v[1] - transport.tMin) / fullSpan * w;
      rangeWindow.style.left = left + 'px';
      rangeWindow.style.width = Math.max(2, right - left) + 'px';
      rangeWindow.classList.toggle('full', !isZoomed(v));
    }

    // uPlot's own cursor marks the committed time too: after a zoom it must move with it (or hide when the time is out of
    // the zoomed range), else it stays at its old pixel, i.e. at a wrong time
    function syncCursors(v) {
      var t = committed();
      var inside = t >= v[0] - 1e-9 && t <= v[1] + 1e-9;
      page.cursorDriven = true;
      page.charts.forEach(function (chart) {
        if (chart.u) chart.u.setCursor(inside ? { left: chart.u.valToPos(t, 'x'), top: 8 } : { left: -10, top: -10 });
      });
      page.cursorDriven = false;
    }

    function drawStatic(v) {
      if (!page.hoverChart) syncCursors(v);
      lane.style.setProperty('--rv-x0', G.x0 + 'px');
      lane.style.setProperty('--rv-xw', G.xw + 'px');
      drawRuler(v);
      rows.forEach(function (record) {
        if (!record.canvas) return;
        drawBand(record, v);
        placeMarks(record, v);
      });
      drawRange(v);
      viewText.textContent = isZoomed(v) ? 'Showing ' + v[0].toFixed(2) + '–' + v[1].toFixed(2) + ' s of ' + fullSpan.toFixed(2) + ' s' : '';
      viewText.title = isZoomed(v) ? 'every chart shows this part of the motion; Full range shows all of it' : '';
      fullButton.disabled = !isZoomed(v);
      rangeHint.textContent = isZoomed(v) ? (v[1] - v[0]).toFixed(2) + ' s shown' : 'drag a range';
      colHandle.style.left = (G.x0 - 7) + 'px';
    }

    /* ---------------- paint ---------------- */

    function xOf(time, v) { return (time - v[0]) / (v[1] - v[0]) * G.xw; }

    function paintTime(v) {
      var t = committed();
      var inside = t >= v[0] - 1e-9 && t <= v[1] + 1e-9;
      // the line through the charts: the reference chart's own mapping, so it sits exactly where uPlot draws time t
      if (G.ok && inside) {
        var x = G.overLeft + G.chart.u.valToPos(t, 'x');
        line.style.display = '';
        line.style.left = (x - 1) + 'px';
        line.style.top = (G.top - 7) + 'px';
      } else {
        line.style.display = 'none';
      }
      var px = xOf(t, v);
      ruler.setAttribute('data-rv-time', String(t));
      ruler.setAttribute('aria-valuenow', String(t));
      ruler.setAttribute('aria-valuetext', t.toFixed(2) + ' seconds');
      grip.classList.toggle('edge', !inside);
      gripTip.style.display = laneLine.style.display = inside ? '' : 'none';
      if (!inside) {
        // the time is outside the zoomed range: its grip waits at that edge, pointing to it (click: bring it into view)
        grip.textContent = t < v[0] ? '‹ ' + t.toFixed(2) : t.toFixed(2) + ' ›';
        grip.style.left = (t < v[0] ? 0 : Math.max(0, G.xw - (grip.offsetWidth || 44))) + 'px';
      } else {
        grip.textContent = t.toFixed(2);
        var gw = grip.offsetWidth || 36;
        grip.style.left = Math.max(0, Math.min(G.xw - gw, px - gw / 2)) + 'px';
        gripTip.style.left = px + 'px';
        laneLine.style.left = (G.x0 + px - 1) + 'px';
        laneLine.style.top = (rulerRow.offsetTop + ruler.clientHeight - 6) + 'px';
        laneLine.style.height = Math.max(0, (folded ? rulerRow.offsetTop + rulerRow.offsetHeight : rangeRow.offsetTop) -
          (rulerRow.offsetTop + ruler.clientHeight - 6)) + 'px';
      }
      rangeTick.style.left = ((t - transport.tMin) / fullSpan * G.xw) + 'px';
      readout.textContent = t.toFixed(2) + ' / ' + transport.tMax.toFixed(2) + ' s';
      playButton.innerHTML = transport.playing ? ICON.pause : ICON.play;
      playButton.classList.toggle('on', transport.playing);
      paintValues(t);
      paintGhost(v);
    }

    function paintValues(t) {
      var index = kit.nearestIndex(grid, t);
      rows.forEach(function (record) {
        if (!record.value) return;
        var env = envelope[record.sit.name];
        var value = env ? env[index] : null;
        record.value.textContent = value === null || value === undefined ? '' : kit.angleText(value);
      });
    }

    function paintGhost(v) {
      var show = hoverT !== null && hoverT >= v[0] && hoverT <= v[1];
      laneGhost.style.display = ghost.style.display = show ? '' : 'none';
      if (!show) return;
      var px = xOf(hoverT, v);
      laneGhost.style.left = (G.x0 + px - 0.5) + 'px';
      laneGhost.style.top = rulerRow.offsetTop + 'px';
      laneGhost.style.height = Math.max(0, (folded ? rulerRow.offsetTop + rulerRow.offsetHeight : rangeRow.offsetTop) - rulerRow.offsetTop) + 'px';
      if (G.ok) {
        ghost.style.left = (G.overLeft + G.chart.u.valToPos(hoverT, 'x') - 0.5) + 'px';
        ghost.style.top = G.top + 'px';
      } else {
        ghost.style.display = 'none';
      }
    }

    function paint() {
      measure();
      var v = view();
      var key = [G.x0, G.xw, v[0], v[1], folded, kit.state.unit].join('|');
      if (key !== drawnKey) { drawnKey = key; drawStatic(v); }
      paintTime(v);
      // playing past a zoomed window: page the window along, as a video editor does
      if (transport.playing && !following && isZoomed(v)) {
        var t = committed();
        if (t > v[1] || t < v[0]) {
          following = true;
          var span = v[1] - v[0];
          setView(t - span * 0.05, t - span * 0.05 + span);
          following = false;
        }
      }
    }

    function queue() {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () { queued = false; paint(); });
    }

    function paintSelection() {
      var shownRuns = 0, all = 0;
      rows.forEach(function (record) {
        if (!record.eye) return;
        var on = page.visible[record.sit.name] !== false;
        record.el.classList.toggle('off', !on);
        record.eye.innerHTML = on ? EYE_OPEN : EYE_CLOSED;
        record.eye.setAttribute('aria-pressed', on ? 'true' : 'false');
        record.eye.title = (on ? 'Hide ' : 'Show ') + record.sit.title + ' on every chart and in the 3D view';
        record.eye.setAttribute('aria-label', record.eye.title);
        if (record.delta) {
          var deltaOn = !!page.errorOn[record.sit.name];
          record.delta.classList.toggle('on', deltaOn);
          record.delta.setAttribute('aria-pressed', deltaOn ? 'true' : 'false');
        }
        if (record.sit.role !== 'target') { all += 1; if (on) shownRuns += 1; }
      });
      rows.forEach(function (record) { record.el.style.display = record.group && record.group.collapsed ? 'none' : ''; });
      groupRows.forEach(function (entry) {
        var collapsed = !!entry.group.collapsed;
        entry.el.classList.toggle('collapsed', collapsed);
        entry.fold.innerHTML = collapsed ? ICON.next : ICON.fold;
        entry.fold.title = (collapsed ? 'Show the tracks of ' : 'Collapse the tracks of ') + entry.group.title;
        entry.fold.setAttribute('aria-label', entry.fold.title);
        entry.fold.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        var shown = entry.group.sits.filter(function (sit) { return page.visible[sit.name] !== false; }).length;
        entry.count.textContent = shown + ' of ' + entry.group.sits.length;
        entry.el.classList.toggle('off', shown === 0);
        entry.eye.innerHTML = shown ? EYE_OPEN : EYE_CLOSED;
        entry.eye.title = (shown ? 'Hide every run of ' : 'Show every run of ') + entry.group.title;
        entry.eye.setAttribute('aria-label', entry.eye.title);
      });
      countText.textContent = shownRuns + ' of ' + all + ' shown';
      var worst = worstShown();
      worstButton.disabled = !worst;
      worstButton.title = worst ? 'go to the worst moment of the shown runs: ' + worst.record.sit.title + ', ' + kit.angleText(worst.moment.size) +
        ' on ' + worst.moment.joint + ' at t = ' + worst.moment.t.toFixed(2) + ' s' : 'no shown run has a joint error';
      worstButton.setAttribute('aria-label', worstButton.title);
      drawnKey = '';
      queue();
    }

    function paintTitles() {
      rows.forEach(function (record) {
        record.moments.forEach(function (moment) {
          moment.el.title = momentTitle(record.sit, moment);
          moment.el.setAttribute('aria-label', moment.el.title);
        });
      });
      paintSelection();
    }

    /* ---------------- moments ---------------- */

    function shownMoments() {
      var out = [];
      rows.forEach(function (record) {
        if (page.visible[record.sit.name] === false) return;
        record.moments.forEach(function (moment) { out.push({ record: record, moment: moment }); });
      });
      return out.sort(function (a, b) { return a.moment.t - b.moment.t; });
    }
    function worstShown() {
      var best = null;
      shownMoments().forEach(function (entry) {
        if (entry.moment.kind === 'worst' && (!best || entry.moment.size > best.moment.size)) best = entry;
      });
      return best;
    }
    function jumpTo(time) {
      transport.pause();
      transport.setScrub(time);
      var v = view();
      if (isZoomed(v) && (time < v[0] || time > v[1])) {
        var span = v[1] - v[0];
        setView(time - span / 2, time + span / 2);
      }
    }
    function jumpWorst() { var worst = worstShown(); if (worst) jumpTo(worst.moment.t); }
    function jumpMoment(direction) {
      var t = committed(), list = shownMoments(), eps = minStep / 2;
      var pick = null;
      if (direction > 0) list.some(function (entry) { if (entry.moment.t > t + eps) { pick = entry; return true; } return false; });
      else list.slice().reverse().some(function (entry) { if (entry.moment.t < t - eps) { pick = entry; return true; } return false; });
      if (pick) jumpTo(pick.moment.t);
    }

    /* ---------------- zoom ---------------- */

    function setView(min, max) {
      if (!(max > min)) return;
      if (max - min < minSpan) { var mid = (min + max) / 2; min = mid - minSpan / 2; max = mid + minSpan / 2; }
      if (min < transport.tMin) { max += transport.tMin - min; min = transport.tMin; }
      if (max > transport.tMax) { min -= max - transport.tMax; max = transport.tMax; }
      min = Math.max(transport.tMin, min);
      if (max - min >= fullSpan - 1e-9) { reset(); return; }
      page.syncing = true;
      page.charts.forEach(function (chart) { if (chart.u) chart.u.setScale('x', { min: min, max: max }); });
      page.syncing = false;
      page.xZoom = { min: min, max: max };
      paint();
    }
    function reset() {
      page.xZoom = null;
      page.charts.forEach(function (chart) { chart.resetZoom(); });
      paint();
    }
    function zoomAround(at, factor) {
      var v = view();
      setView(at - (at - v[0]) * factor, at + (v[1] - at) * factor);
    }
    function onWheel(event, timeAtPointer) {
      event.preventDefault();
      var v = view();
      if (event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
        var shift = (v[1] - v[0]) * 0.12 * Math.sign(event.deltaX || event.deltaY);
        setView(v[0] + shift, v[1] + shift);
        return;
      }
      zoomAround(timeAtPointer, event.deltaY > 0 ? 1.25 : 0.8);
    }

    /* ---------------- gestures ---------------- */

    function timeOnView(clientX, box) {
      var v = view();
      var x = Math.max(0, Math.min(box.width, clientX - box.left));
      return v[0] + x / box.width * (v[1] - v[0]);
    }

    // press and drag on the ruler or on a track: the time follows the pointer, live (snapped to the plot grid)
    function scrubSurface(surface) {
      surface.addEventListener('pointerdown', function (event) {
        if (event.button !== 0) return;
        event.preventDefault();
        var box = surface.getBoundingClientRect();
        transport.pause();
        try { surface.setPointerCapture(event.pointerId); } catch (error) {}
        document.body.classList.add('rv-scrubbing');
        setHover(null);
        transport.setScrub(snap(timeOnView(event.clientX, box)));
        if (surface === ruler) ruler.focus({ preventScroll: true });
        function move(moveEvent) { transport.setScrub(snap(timeOnView(moveEvent.clientX, box))); }
        function up() {
          surface.removeEventListener('pointermove', move);
          surface.removeEventListener('pointerup', up);
          surface.removeEventListener('pointercancel', up);
          document.body.classList.remove('rv-scrubbing');
        }
        surface.addEventListener('pointermove', move);
        surface.addEventListener('pointerup', up);
        surface.addEventListener('pointercancel', up);
      });
      // hover: a preview of that instant in the 3D view (the committed time stays), and a dashed ghost line
      surface.addEventListener('pointermove', function (event) {
        if (event.buttons) return;
        setHover(snap(timeOnView(event.clientX, surface.getBoundingClientRect())));
      });
      surface.addEventListener('pointerleave', function () { setHover(null); });
    }
    function setHover(time) {
      if (time === hoverT) return;
      hoverT = time;
      transport.setHover(time);
      paintGhost(view());
    }
    scrubSurface(ruler);
    rows.forEach(function (record) { if (record.time) scrubSurface(record.time); });

    ruler.addEventListener('wheel', function (event) {
      onWheel(event, timeOnView(event.clientX, ruler.getBoundingClientRect()));
    }, { passive: false });
    // WHY the tracks scroll on a plain wheel (17 runs do not fit): Ctrl / Alt + wheel zooms there
    tracks.addEventListener('wheel', function (event) {
      if (!(event.ctrlKey || event.altKey) || !event.target.closest('.rv-track-time')) return;
      onWheel(event, timeOnView(event.clientX, event.target.closest('.rv-track-time').getBoundingClientRect()));
    }, { passive: false });

    function fullTimeAt(clientX) {
      var box = range.getBoundingClientRect();
      var x = Math.max(0, Math.min(box.width, clientX - box.left));
      return transport.tMin + x / box.width * fullSpan;
    }
    range.addEventListener('wheel', function (event) { onWheel(event, fullTimeAt(event.clientX)); }, { passive: false });
    range.addEventListener('dblclick', function () { reset(); });
    range.addEventListener('pointerdown', function (event) {
      if (event.button !== 0) return;
      event.preventDefault();
      var box = range.getBoundingClientRect();
      var v = view();
      var zoomed = isZoomed(v);
      var startX = event.clientX - box.left;
      var left = (v[0] - transport.tMin) / fullSpan * box.width, right = (v[1] - transport.tMin) / fullSpan * box.width;
      var mode = 'new';
      if (zoomed && Math.abs(startX - left) <= 6) mode = 'left';
      else if (zoomed && Math.abs(startX - right) <= 6) mode = 'right';
      else if (zoomed && startX > left && startX < right) mode = 'pan';
      var t0 = fullTimeAt(event.clientX);
      var moved = false;
      try { range.setPointerCapture(event.pointerId); } catch (error) {}
      range.classList.add('dragging');
      function move(moveEvent) {
        var x = moveEvent.clientX - box.left;
        if (Math.abs(x - startX) > 2) moved = true;
        if (!moved) return;
        var t = fullTimeAt(moveEvent.clientX);
        if (mode === 'pan') setView(v[0] + (t - t0), v[1] + (t - t0));
        else if (mode === 'left') setView(Math.min(t, v[1] - minSpan), v[1]);
        else if (mode === 'right') setView(v[0], Math.max(t, v[0] + minSpan));
        else setView(Math.min(t0, t), Math.max(t0, t));
      }
      function up() {
        range.removeEventListener('pointermove', move);
        range.removeEventListener('pointerup', up);
        range.removeEventListener('pointercancel', up);
        range.classList.remove('dragging');
        // a plain click on the zoom bar while zoomed: centre the window there
        if (!moved && zoomed) { var span = v[1] - v[0]; setView(t0 - span / 2, t0 + span / 2); }
      }
      range.addEventListener('pointermove', move);
      range.addEventListener('pointerup', up);
      range.addEventListener('pointercancel', up);
    });

    // keyboard on the ruler (it is the page's slider): arrows step one sample (Shift: ten), Home / End, Space plays
    ruler.addEventListener('keydown', function (event) {
      var handled = true;
      if (event.key === 'ArrowLeft') transport.stepBy(event.shiftKey ? -10 : -1);
      else if (event.key === 'ArrowRight') transport.stepBy(event.shiftKey ? 10 : 1);
      else if (event.key === 'Home') { transport.pause(); transport.setScrub(transport.tMin); }
      else if (event.key === 'End') { transport.pause(); transport.setScrub(transport.tMax); }
      else if (event.key === ' ' || event.key === 'k') transport.toggle();
      else handled = false;
      if (handled) event.preventDefault();
    });

    /* ---------------- lane size, fold, names column ---------------- */

    var folded = !!recall('lane-folded', false);
    function listedHeight() {
      var px = 0;
      rows.forEach(function (record) { if (!(record.group && record.group.collapsed)) px += ROW_H; });
      return px + groupRows.length * GROUP_H;
    }
    function defaultHeight() {
      var all = listedHeight();
      var cap = VISIBLE_TRACKS * ROW_H + 2 * GROUP_H + Math.round(ROW_H / 2);  // a half row says "it scrolls"
      return bar.offsetHeight + rulerRow.offsetHeight + legendRow.offsetHeight + rangeRow.offsetHeight + Math.min(all, cap) + 4;
    }
    function setLaneHeight(height, remember) {
      // the app layout (style.css, >= 901 px) gives the column the viewport's height; below it the page flows
      var app = window.matchMedia && window.matchMedia('(min-width: 901px)').matches;
      var room = (app && hosts.column.clientHeight) || window.innerHeight;
      var natural = defaultHeight();
      var want = height === null || height === undefined ? natural : Number(height);
      var tallest = Math.max(LANE_MIN_PX, Math.min(room - 140, bar.offsetHeight + rulerRow.offsetHeight + legendRow.offsetHeight +
        rangeRow.offsetHeight + listedHeight() + 4));
      T.laneH = Math.round(Math.max(LANE_MIN_PX, Math.min(tallest, want)));
      if (!folded) lane.style.height = T.laneH + 'px';
      if (remember) store('lane-h', height === null ? null : T.laneH);
      queue();
    }
    function setFolded(value, remember) {
      folded = value;
      lane.classList.toggle('folded', folded);
      lane.style.height = folded ? '' : (T.laneH || defaultHeight()) + 'px';
      foldButton.innerHTML = folded ? ICON.unfold : ICON.fold;
      foldButton.title = folded ? 'Unfold the lane: the runs\' tracks and the zoom bar' : 'Fold the lane: keep the transport and the time ruler';
      foldButton.setAttribute('aria-label', foldButton.title);
      foldButton.setAttribute('aria-expanded', folded ? 'false' : 'true');
      if (remember) store('lane-folded', folded);
      drawnKey = '';
      queue();
    }

    sizer.addEventListener('pointerdown', function (event) {
      if (folded || event.button !== 0) return;
      event.preventDefault();
      var startY = event.clientY, startH = lane.offsetHeight;
      sizer.classList.add('dragging');
      try { sizer.setPointerCapture(event.pointerId); } catch (error) {}
      function move(moveEvent) { setLaneHeight(startH - (moveEvent.clientY - startY), false); }
      function up() {
        sizer.classList.remove('dragging');
        sizer.removeEventListener('pointermove', move);
        sizer.removeEventListener('pointerup', up);
        sizer.removeEventListener('pointercancel', up);
        store('lane-h', T.laneH);
      }
      sizer.addEventListener('pointermove', move);
      sizer.addEventListener('pointerup', up);
      sizer.addEventListener('pointercancel', up);
    });
    sizer.addEventListener('dblclick', function () { setLaneHeight(null, true); });

    colHandle.addEventListener('pointerdown', function (event) {
      if (event.button !== 0) return;
      event.preventDefault();
      var startX = event.clientX, startW = T.headW;
      colHandle.classList.add('dragging');
      try { colHandle.setPointerCapture(event.pointerId); } catch (error) {}
      function move(moveEvent) { setHeadWidth(startW + moveEvent.clientX - startX, false); }
      function up() {
        colHandle.classList.remove('dragging');
        colHandle.removeEventListener('pointermove', move);
        colHandle.removeEventListener('pointerup', up);
        colHandle.removeEventListener('pointercancel', up);
        store('head-w', T.headW);
      }
      colHandle.addEventListener('pointermove', move);
      colHandle.addEventListener('pointerup', up);
      colHandle.addEventListener('pointercancel', up);
    });
    colHandle.addEventListener('dblclick', function () { setHeadWidth(null, true); });

    /* ---------------- wiring ---------------- */

    setHeadWidth(headWidth(), false);
    setFolded(folded, false);
    setLaneHeight(recall('lane-h', null), false);
    page.unitRepaints.push(paintTitles);
    window.addEventListener('rv-selection', paintSelection);
    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(function () { drawnKey = ''; queue(); }).observe(hosts.scroller);
      new ResizeObserver(function () { drawnKey = ''; queue(); }).observe(lane);
    }
    window.addEventListener('resize', function () { setLaneHeight(T.laneH, false); });
    paintTitles();

    T.paint = paint;
    T.queue = queue;
    T.setView = setView;
    T.reset = reset;
    T.view = view;
    T.jumpWorst = jumpWorst;
    T.lane = lane;
    T.line = line;
    T.geometry = function () { measure(); return { x0: G.x0, xw: G.xw, overLeft: G.overLeft, top: G.top, ok: G.ok }; };
    return T;
  }

  return { create: create };
})();
