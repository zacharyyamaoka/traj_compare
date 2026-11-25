/* The playback viewer's shared shell (run-view round 2026-11-24). Every variant loads this after its own plots.js.
 *
 * - Loads the fixture named by ``?fixture=tta|bam_fb`` (data/<name>.js, built by fixtures.py) and boots the variant's
 *   TrajCompare with it.
 * - Draws the header every variant shares: ‹ back to the target view (with its state: the runs ticked now), the target's
 *   name, how many runs are shown, and **Open the same in Rerun** (the same runs, the playhead time; serve.py writes the
 *   recording with traj_compare's own rerun_export and starts the pinned viewer; ``?dry=1`` builds without launching).
 *   A variant may move the header's pieces (``RunView.headerParts``) but never drops them.
 * - Exposes ``window.__runView``, the readback the checks use: the committed time, the stage slider, per chart the time
 *   its DRAWN playhead marks (measured from the element's box, never from state), the 3D's drawn time and arm poses.
 */
(function () {
  'use strict';
  var Q = new URLSearchParams(location.search);
  var FIXTURE = Q.get('fixture') || 'tta';
  var meta = null;

  function el(tag, cls, parent, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function page() { return window.TrajCompare && TrajCompare.state.pages[0]; }
  function runs() { var p = page(); return p ? p.data.situations.filter(function (s) { return s.role !== 'target' && s.has_data; }) : []; }
  function shown() { var p = page(); return runs().filter(function (s) { return p.visible[s.name] !== false; }); }
  function keepKey(sit) { return /^L\d+$/.test(sit.name) ? sit.name.slice(1) : sit.name; }
  function nowT() { var p = page(); var tr = p && p.transport; return tr ? (tr.t === null ? tr.tMax : tr.t) : null; }

  function backHref() {
    var base = Q.get('back') || (meta && meta.target_view) || '';
    if (!base) return '';
    if (base.indexOf('site=') === -1) return base;  // a hash-routed target page (TTA's) takes no selection
    var url = new URL(base, location.href);
    url.searchParams.set('keep', shown().map(keepKey).join(','));
    return url.pathname + '?' + url.searchParams.toString().replace(/%2C/g, ',') + url.hash;
  }

  var parts = {};
  function buildHeader() {
    var host = document.getElementById('rv-head');
    host.innerHTML = '';
    host.setAttribute('data-rv-head', '');
    var back = el('a', 'rv-back', host, '‹ Target view');
    back.setAttribute('data-rv-back', '');
    back.title = 'Back to the target view, with the runs ticked here';
    var where = el('div', 'rv-where', host);
    el('span', 'rv-kicker', where, 'Playback viewer');
    var title = el('span', 'rv-title', where, meta ? meta.target : '');
    title.title = meta ? meta.fixture : '';
    var count = el('span', 'rv-count', host);
    count.setAttribute('data-rv-count', '');
    var rerun = el('button', 'rv-rerun', host, 'Open the same in Rerun');
    rerun.setAttribute('data-rv-rerun', '');
    rerun.title = 'Opens these runs at this time in the Rerun viewer, with the same question tabs';
    var status = el('span', 'rv-status', host);
    status.setAttribute('data-rv-status', '');
    rerun.onclick = openRerun;
    parts = { host: host, back: back, where: where, title: title, count: count, rerun: rerun, status: status };
    paintHeader();
  }
  function paintHeader() {
    if (!parts.back) return;
    var href = backHref();
    parts.back.href = href || '#';
    parts.back.classList.toggle('dead', !href);
    var n = shown().length, all = runs().length;
    parts.count.textContent = n + ' of ' + all + ' run' + (all === 1 ? '' : 's') + ' shown';
    parts.rerun.disabled = !n;
  }

  function openRerun() {
    var p = page();
    var body = { fixture: FIXTURE, keep: shown().map(function (s) { return s.name; }), t: nowT(), tab: p && p.activeTab };
    parts.status.className = 'rv-status';
    parts.status.textContent = 'Writing the recording…';
    fetch('/__rerun/open' + (Q.get('dry') === '1' ? '?dry=1' : ''), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then(function (r) { return r.json(); }).then(function (answer) {
      if (!answer.ok) throw new Error(answer.error || 'failed');
      parts.status.className = 'rv-status ok';
      parts.status.textContent = (answer.launched ? 'Opened in Rerun: ' : 'Recording ready: ') + answer.runs + ' run' +
        (answer.runs === 1 ? '' : 's') + ', time t = ' + Number(answer.t).toFixed(2) + ' s';
      parts.status.title = answer.command;
      parts.status.setAttribute('data-rv-rrd', answer.rrd);
      window.__runViewLastRerun = answer;
    }).catch(function (error) {
      parts.status.className = 'rv-status bad';
      parts.status.textContent = 'Open in Rerun needs serve.py (' + error.message + ')';
    });
  }

  // ---------------------------------------------------------------- readback (checks only; reads what is DRAWN)
  function playheadAt(chart) {
    var over = chart.u && chart.u.over;
    if (!over || !over.offsetParent) return null;
    var box = over.getBoundingClientRect();
    if (!box.width) return null;
    var marks = Array.prototype.filter.call(document.querySelectorAll('[data-rv-playhead]'), function (mark) {
      if (!mark.offsetParent && getComputedStyle(mark).position !== 'fixed') return false;
      var r = mark.getBoundingClientRect();
      return r.height > 0 && r.bottom > box.top + 1 && r.top < box.bottom - 1 && r.left + r.width / 2 >= box.left - 1 &&
        r.left + r.width / 2 <= box.right + 1;
    });
    var own = marks.filter(function (mark) { return chart.card.contains(mark); });
    var mark = (own.length ? own : marks)[0];
    if (!mark) return null;
    var r = mark.getBoundingClientRect();
    var core = mark.querySelector('[data-rv-playhead-core]');
    if (core) r = core.getBoundingClientRect();
    return chart.u.posToVal(r.left + r.width / 2 - box.left, 'x');
  }
  function tabOf(node) {
    var panel = node.closest('[data-tc-panel]');
    return panel ? panel.getAttribute('data-tc-panel') : null;
  }
  window.__runView = {
    ready: false,
    fixture: FIXTURE,
    meta: function () { return meta; },
    t: nowT,
    activeTab: function () { var p = page(); return p && p.activeTab; },
    grid: function () { var p = page(); return p ? p.data.plot_t : []; },
    sliders: function () {
      return Array.prototype.map.call(document.querySelectorAll('input.tc-scrub, [data-rv-slider]'), function (s) {
        return s.value !== undefined && s.value !== '' ? parseFloat(s.value) : parseFloat(s.getAttribute('data-rv-time'));
      });
    },
    charts: function () {
      var p = page();
      return p ? p.charts.map(function (chart, index) {
        var on = !!(chart.card.offsetParent && chart.card.offsetWidth);
        return {
          index: index, title: chart.spec.title, tab: tabOf(chart.card), shown: on,
          playhead: on ? playheadAt(chart) : null,
          zoom: chart.u ? [chart.u.scales.x.min, chart.u.scales.x.max] : null,
          series: chart.u ? chart.spec.series.map(function (entry, i) {
            return { sit: entry.sit.name, error: !!entry.error, show: !!(chart.u.series[i + 1] && chart.u.series[i + 1].show) };
          }) : [],
          box: on ? chart.u.over.getBoundingClientRect().toJSON() : null,
        };
      }) : [];
    },
    pose3d: function () {
      var p = page();
      if (!p || !p.viewer3d || !p.viewer3d.debug) return null;
      var d = p.viewer3d.debug();
      d.robots.forEach(function (robot) {
        var sit = p.data.situations.filter(function (s) { return s.name === robot.name; })[0];
        var track = sit.robot_track, i = robot.index, last = track.p[i][track.p[i].length - 1];
        robot.expected = last;  // the payload's pose of that sample: the drawn arm must stand there
      });
      return d;
    },
    selection: function () { return shown().map(function (s) { return s.name; }); },
    runs: function () { return runs().map(function (s) { return { name: s.name, title: s.title, color: s.color }; }); },
    backHref: backHref,
  };

  window.RunView = { headerParts: function () { return parts; }, paintHeader: paintHeader, openRerun: openRerun, meta: function () { return meta; } };

  window.__runViewFixture = function (body) {
    meta = body.meta || null;
    document.title = 'Playback viewer · ' + (meta ? meta.target : body.title);
    if (window.RunViewVariant && window.RunViewVariant.beforeBoot) window.RunViewVariant.beforeBoot(body);
    TrajCompare.boot(body);
    buildHeader();
    window.addEventListener('rv-selection', paintHeader);
    var foot = document.getElementById('rv-foot');
    if (foot && meta) foot.textContent = 'fixture: ' + meta.fixture + ' · ' + meta.deployment + ' · viewer: traj_compare 38b5967 + this variant\'s copy (uPlot 1.6.30, three.js r160)';
    if (window.RunViewVariant && window.RunViewVariant.afterBoot) window.RunViewVariant.afterBoot(body);
    requestAnimationFrame(function () { window.__runView.ready = true; document.body.setAttribute('data-rv-ready', '1'); });
  };

  var script = document.createElement('script');
  script.src = '../data/' + encodeURIComponent(FIXTURE) + '.js';
  script.onerror = function () {
    document.getElementById('tc-main').textContent = 'No fixture "' + FIXTURE + '": run fixtures.py (data/ is gitignored).';
  };
  document.head.appendChild(script);
})();
