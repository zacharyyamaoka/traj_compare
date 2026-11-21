/* Outer-view proposals (babble round 2026-11-20) — what every variant shares.
 *
 * Loads data/<site>.js (window.OUTER_DATA, written by extract.py; a <script src> loads from file://, a fetch does not),
 * draws the shared chrome (title, counts, tabs) and the two drill tabs every variant lands on: Targets (a config's
 * worst targets, each linking to today's Target level and its run report) and Runs. A variant only supplies its
 * Overview (and any extra tab). Routing is the hash, so every state is a link: #/<tab>?k=v&...
 *
 * WHY shared drill tabs: the five variants differ on the Overview's primary object (the frozen CONTRACT.md); the drill
 * destination is the same real site, so it is built once and every variant is judged on how it gets there.
 */
(function () {
  'use strict';

  var OV = window.OV = {};
  var SITES = ['ur5e', 'pendulum', 'bam_fb'];
  var params = new URLSearchParams(location.search);
  OV.site = SITES.indexOf(params.get('site')) >= 0 ? params.get('site') : 'ur5e';

  // ── small helpers ─────────────────────────────────────────────────────────
  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  OV.esc = esc;
  OV.el = function (tag, cls, parent, html) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html !== undefined) node.innerHTML = html;
    if (parent) parent.appendChild(node);
    return node;
  };
  OV.median = function (values) {
    var v = values.filter(function (x) { return x !== null && x !== undefined && isFinite(x); }).sort(function (a, b) { return a - b; });
    if (!v.length) return null;
    var m = v.length >> 1;
    return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  };
  OV.quantile = function (sorted, q) {
    if (!sorted.length) return null;
    var at = (sorted.length - 1) * q, lo = Math.floor(at), hi = Math.ceil(at);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (at - lo);
  };
  // 3 significant digits, no exponent for the ranges the bench produces (1e-4 … 1e3).
  OV.num = function (value, digits) {
    if (value === null || value === undefined || !isFinite(value)) return '—';
    if (value === 0) return '0';
    var d = digits || 3, abs = Math.abs(value);
    if (abs >= 1000) return Math.round(value).toLocaleString('en-US');
    if (abs >= 100) return value.toFixed(0);
    var text = Number(value.toPrecision(d)).toString();
    if (/e/.test(text)) text = value.toFixed(Math.min(8, d - 1 - Math.floor(Math.log10(abs))));
    return text;
  };
  OV.unit = function (unit) { return unit === 'm/s^3' ? 'm/s³' : unit; };
  OV.withUnit = function (value, unit) { return OV.num(value) + (unit === '%' ? ' %' : ' ' + OV.unit(unit)); };
  // A ratio as "25×" / "1.2×" / "0.52×".
  OV.times = function (ratio) {
    if (ratio === null || !isFinite(ratio)) return '—';
    if (ratio >= 100) return Math.round(ratio).toLocaleString('en-US') + '×';
    if (ratio >= 10) return ratio.toFixed(0) + '×';
    // Near 1× two digits would print "1×" for a 4 % gap; three keep it ("1.04×").
    if (ratio > 0.9 && ratio < 1.1) return Number(ratio.toPrecision(3)) + '×';
    return Number(ratio.toPrecision(2)) + '×';
  };
  OV.pct = function (share) { return (100 * share).toFixed(share < 0.1 && share > 0 ? 1 : 0) + ' %'; };

  // ── routing ───────────────────────────────────────────────────────────────
  OV.route = function () {
    var hash = location.hash.replace(/^#\/?/, '');
    var at = hash.indexOf('?');
    var tab = (at >= 0 ? hash.slice(0, at) : hash) || 'overview';
    var q = {};
    new URLSearchParams(at >= 0 ? hash.slice(at + 1) : '').forEach(function (v, k) { q[k] = v; });
    return { tab: tab, q: q };
  };
  OV.href = function (tab, q) {
    var query = Object.keys(q || {}).filter(function (k) { return q[k] !== undefined && q[k] !== null && q[k] !== ''; })
      .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(q[k]); }).join('&');
    return '#/' + tab + (query ? '?' + query : '');
  };
  OV.go = function (tab, q) { location.hash = OV.href(tab, q); };
  // Update the current tab's query without a new history entry for every hover-free control change.
  OV.setQuery = function (patch) {
    var r = OV.route();
    Object.keys(patch).forEach(function (k) { r.q[k] = patch[k]; });
    location.hash = OV.href(r.tab, r.q);
  };

  // ── data model (built once from OUTER_DATA) ───────────────────────────────
  function build(D) {
    var M = OV.M = D;
    M.nT = D.targets.slug.length;
    M.multiDomain = D.domains.length > 1;
    M.seriesByKey = {};
    M.configByName = {};
    D.configs.forEach(function (c) { M.configByName[c.name] = c; });
    D.series.forEach(function (s) {
      s.color = (M.configByName[s.config] || {}).color || '#6b7a8f';
      s.label = M.multiDomain ? s.config + ' · ' + s.domain : s.config;
      M.seriesByKey[s.key] = s;
    });
    // Scorecard series that have no lines in the payload still get a row (labelled as scorecard-only).
    Object.keys(D.score || {}).forEach(function (kpi) {
      Object.keys(D.score[kpi]).forEach(function (g) {
        Object.keys(D.score[kpi][g]).forEach(function (key) {
          if (M.seriesByKey[key]) return;
          var parts = key.split('|');
          var s = { key: key, config: parts[0], domain: parts[1], scorecardOnly: true };
          s.color = (M.configByName[s.config] || {}).color || '#6b7a8f';
          s.label = M.multiDomain ? s.config + ' · ' + s.domain : s.config;
          M.seriesByKey[key] = s;
          D.series.push(s);
        });
      });
    });
    M.kpiById = {};
    D.kpis.forEach(function (k) { M.kpiById[k.id] = k; k.log = k.id === 'rms' || k.id === 'jerk'; });
    M.top = D.speeds.length - 1;                 // full speed = the last speed index
    M.scoreGroups = D.groups.filter(function (g) { return g.scorecard; });
    M.rmsLabel = 'tool tracking RMS';
    // Targets per series, and the shared-target set.
    M.count = {};
    D.series.forEach(function (s) {
      var arr = D.rms[s.key] || [], n = 0;
      for (var i = 0; i < arr.length; i++) if (arr[i] !== null) n++;
      M.count[s.key] = n;
    });
  }
  OV.dash = function (domain) {
    if (!OV.M.multiDomain) return null;
    return domain === 'real' ? null : domain === 'rehearsal' ? [2, 3] : [6, 4];
  };
  OV.swatch = function (s) {
    var dash = OV.dash(s.domain);
    return '<span class="ov-sw' + (dash ? ' ov-sw-' + s.domain : '') + '" style="--c:' + s.color + '"></span>';
  };
  // Config names can be long (BAM FB: "fullarm_jtc model-FF+LA, static-load FF at rest + kp hold ×2"): an explicit
  // ellipsis with the full name one hover away, never a silent clip.
  // The ellipsis sits in the middle: BAM FB's configs share a long prefix and differ at the end ("… + kp hold ×2 · real").
  OV.short = function (label, max) {
    max = max || 30;
    if (label.length <= max) return label;
    var head = Math.max(6, Math.floor((max - 1) * 0.4)), tail = max - 1 - head;
    return label.slice(0, head) + '…' + label.slice(label.length - tail);
  };
  OV.name = function (s, max) {
    var label = s.label || s;
    max = max || 30;
    if (label.length <= max) return '<span class="ov-name">' + esc(label) + '</span>';
    return '<span class="ov-name" title="' + esc(label) + '">' + esc(OV.short(label, max)) + '</span>';
  };
  OV.score = function (kpi, group, key) { return ((OV.M.score[kpi] || {})[group] || {})[key] || null; };
  OV.scoreN = function (group, key) { return ((OV.M.scoreN || {})[group] || {})[key] || null; };
  OV.seriesIn = function (kpi, group) {
    var by = (OV.M.score[kpi] || {})[group] || {};
    return OV.M.series.filter(function (s) { return by[s.key]; });
  };
  // "1.0", not "1": the bench's own tiles say "speed 1.0" and "1.0 × speed limit".
  function sp(x) { return Number.isInteger(x) ? x.toFixed(1) : String(x); }
  OV.sp = sp;
  OV.speedLabel = function (i) {
    var M = OV.M, s = M.speeds[i];
    return M.speedKey === 'speed_fraction' ? sp(s) + ' × speed limit' : 'speed ' + sp(s);
  };
  OV.speedShort = function (i) { return sp(OV.M.speeds[i]); };
  OV.groupLabel = function (gi) { return OV.M.groups[gi].key; };
  OV.targetUrl = function (i) { return OV.M.siteUrl + 'index.html#/target/' + encodeURIComponent(OV.M.targets.slug[i]); };
  OV.runUrl = function (key, i) {
    var suffix = (OV.M.run[key] || [])[i];
    return suffix ? OV.M.siteUrl + 'runs/' + OV.M.targets.slug[i] + suffix + '/report.html' : null;
  };
  OV.reps = function (key, i) { var r = OV.M.reps[key]; return r ? r[i] : 1; };
  // Values of one series over a filtered set of target indices.
  OV.targetsWhere = function (fn) {
    var out = [];
    for (var i = 0; i < OV.M.nT; i++) if (fn(i)) out.push(i);
    return out;
  };
  OV.sourceNote = function () {
    var M = OV.M, o = M.oracle || {};
    var src = M.rmsSource.indexOf('bench tag') === 0 && M.rmsSource.indexOf('else') < 0
      ? 'the bench’s per-run tag <code>&lt;domain&gt;_tcp_rms_mm</code>' : esc(M.rmsSource);
    var text = 'Per-target tool RMS = ' + src + ', median over a config’s repeats.';
    if (o.cells) {
      text += ' Re-aggregated the scorecard’s way (median over the split’s tasks) it reproduces ' + o.within1pct + ' of ' + o.cells +
        ' scorecard RMS cells within 1 % (largest gap ' + OV.pct(o.maxRelErr) + ').';
    }
    if (o.unbacked) text += ' <span class="ds-warn">' + o.unbacked + ' scorecard cells have no runs in this site behind them</span> (' +
      esc(o.unbackedSeries.slice(0, 3).join('; ')) + (o.unbackedSeries.length > 3 ? '; …' : '') + ').';
    return text;
  };

  // ── chrome: header + tabs ─────────────────────────────────────────────────
  OV.boot = function (variant) {
    var script = document.createElement('script');
    script.src = 'data/' + OV.site + '.js';
    script.onload = function () { build(window.OUTER_DATA); start(variant); };
    script.onerror = function () { document.body.innerHTML = '<p style="padding:20px">Could not load data/' + esc(OV.site) + '.js — run extract.py.</p>'; };
    document.head.appendChild(script);
  };

  function start(variant) {
    var M = OV.M;
    var tabs = variant.tabs.concat([
      { id: 'targets', label: 'Targets', render: renderTargets },
      { id: 'runs', label: 'Runs', render: renderRuns },
    ]);
    document.title = variant.name + ' · ' + M.title;
    var body = document.body;
    body.innerHTML = '';
    var head = OV.el('header', 'ov-head', body);
    var c = M.counts;
    head.innerHTML =
      '<div class="ov-titles"><h1>' + esc(M.title) + '</h1><p class="ds-sub">' +
      c.targets + ' targets · ' + c.runs + ' runs · ' + c.lines + ' lines (' + c.sim + ' sim · ' + c.real + ' real) · ' +
      M.configs.length + ' configs · generated ' + esc(M.generated) + '</p></div>' +
      '<div class="ov-site"><label title="Prototype only: the same page on another bench site">site ' +
      '<select id="ov-site">' + SITES.map(function (s) { return '<option' + (s === OV.site ? ' selected' : '') + '>' + s + '</option>'; }).join('') +
      '</select></label><a class="ds-link" target="_blank" rel="noopener" href="' + esc(M.siteUrl) + 'index.html">today’s page ↗</a></div>';
    document.getElementById('ov-site').addEventListener('change', function (e) {
      var p = new URLSearchParams(location.search); p.set('site', e.target.value);
      location.href = location.pathname + '?' + p.toString() + '#/overview';
    });
    var nav = OV.el('nav', 'tc-tabs ov-tabs', body);
    tabs.forEach(function (t) {
      var b = OV.el('button', '', nav, esc(t.label));
      b.dataset.tab = t.id;
      b.addEventListener('click', function () {
        var r = OV.route();
        // Carry the shared filter (config, group, speed) between tabs; the overview keeps its own.
        var keep = {};
        ['cfg', 'g', 'v', 'sort', 'vs'].forEach(function (k) { if (r.q[k] !== undefined) keep[k] = r.q[k]; });
        OV.go(t.id, t.id === 'overview' ? {} : keep);
      });
    });
    var main = OV.el('main', 'ds ov-main', body);
    main.id = 'ov-main';
    function show() {
      var r = OV.route();
      var tab = tabs.filter(function (t) { return t.id === r.tab; })[0] || tabs[0];
      [].forEach.call(nav.children, function (b) { b.classList.toggle('active', b.dataset.tab === tab.id); });
      OV.destroyCharts();
      main.innerHTML = '';
      main.dataset.tab = tab.id;
      tab.render(main, r.q);
    }
    window.addEventListener('hashchange', show);
    show();
    document.documentElement.dataset.ready = '1';
  }

  // uPlot instances a tab made; destroyed on every tab change.
  var charts = [];
  OV.track = function (chart) { charts.push(chart); return chart; };
  OV.destroyCharts = function () { charts.forEach(function (c) { try { c.destroy(); } catch (e) {} }); charts = []; };

  // ── shared drill tab 1: Targets ───────────────────────────────────────────
  // ?cfg=<series key>&g=<group index|all>&v=<speed index|all>&sort=abs|best|vs&vs=<series key>&n=<rows>
  function defaultSeries() {
    var M = OV.M, best = null;
    M.series.forEach(function (s) { if (!s.scorecardOnly && (!best || M.count[s.key] > M.count[best.key])) best = s; });
    return best;
  }
  function renderTargets(main, q) {
    var M = OV.M;
    var s = M.seriesByKey[q.cfg] && !M.seriesByKey[q.cfg].scorecardOnly ? M.seriesByKey[q.cfg] : defaultSeries();
    var g = q.g !== undefined && q.g !== 'all' ? +q.g : null;
    var v = q.v !== undefined && q.v !== 'all' ? +q.v : null;
    var sort = q.sort || 'abs';
    var vs = M.seriesByKey[q.vs] && q.vs !== s.key ? M.seriesByKey[q.vs] : null;
    if (sort === 'vs' && !vs) sort = 'best';
    var limit = +q.n || 40;
    var mine = M.rms[s.key];
    var live = M.series.filter(function (x) { return !x.scorecardOnly; });
    var rows = OV.targetsWhere(function (i) {
      return mine[i] !== null && (g === null || M.targets.g[i] === g) && (v === null || M.targets.v[i] === v);
    }).map(function (i) {
      var others = live.filter(function (x) { return x.key !== s.key && M.rms[x.key][i] !== null; });
      var bestOther = null;
      others.forEach(function (x) { if (bestOther === null || M.rms[x.key][i] < M.rms[bestOther.key][i]) bestOther = x; });
      var ref = sort === 'vs' ? (vs && M.rms[vs.key][i] !== null ? M.rms[vs.key][i] : null) : bestOther ? M.rms[bestOther.key][i] : null;
      return { i: i, value: mine[i], ratio: ref ? mine[i] / ref : null, bestOther: bestOther };
    });
    if (sort !== 'abs') rows = rows.filter(function (r) { return r.ratio !== null; });
    rows.sort(function (a, b) { return sort === 'abs' ? b.value - a.value : b.ratio - a.ratio; });

    var bar = OV.el('div', 'ds-bar ov-filter', main);
    bar.innerHTML =
      '<label><span class="ds-k">config</span><select data-k="cfg">' + live.map(function (x) {
        return '<option value="' + esc(x.key) + '"' + (x.key === s.key ? ' selected' : '') + '>' + esc(x.label) + ' (' + M.count[x.key] + ')</option>';
      }).join('') + '</select></label>' +
      '<label><span class="ds-k">dataset · split</span><select data-k="g"><option value="all">all</option>' + M.groups.map(function (gr, gi) {
        return '<option value="' + gi + '"' + (gi === g ? ' selected' : '') + '>' + esc(gr.key) + '</option>';
      }).join('') + '</select></label>' +
      '<label><span class="ds-k">' + (M.speedKey === 'speed_fraction' ? 'speed fraction' : 'speed') + '</span><select data-k="v"><option value="all">all</option>' + M.speeds.map(function (sp, vi) {
        return '<option value="' + vi + '"' + (vi === v ? ' selected' : '') + '>' + OV.sp(sp) + '</option>';
      }).join('') + '</select></label>' +
      '<label><span class="ds-k">worst by</span><select data-k="sort">' +
      '<option value="abs"' + (sort === 'abs' ? ' selected' : '') + '>its own tool RMS</option>' +
      '<option value="best"' + (sort === 'best' ? ' selected' : '') + '>ratio to the best other config</option>' +
      '<option value="vs"' + (sort === 'vs' ? ' selected' : '') + '>ratio to one config…</option></select></label>' +
      (sort === 'vs' ? '<label><span class="ds-k">vs</span><select data-k="vs">' + live.filter(function (x) { return x.key !== s.key; }).map(function (x) {
        return '<option value="' + esc(x.key) + '"' + (vs && x.key === vs.key ? ' selected' : '') + '>' + esc(x.label) + '</option>';
      }).join('') + '</select></label>' : '');
    bar.querySelectorAll('select').forEach(function (sel) {
      sel.addEventListener('change', function () {
        var patch = {}; patch[sel.dataset.k] = sel.value; patch.n = '';
        if (sel.dataset.k === 'sort' && sel.value === 'vs' && !q.vs) patch.vs = live.filter(function (x) { return x.key !== s.key; })[0].key;
        OV.setQuery(patch);
      });
    });

    var scope = (g === null ? 'all dataset·splits' : M.groups[g].key) + (v === null ? ', every speed' : ', ' + OV.speedLabel(v));
    var head = OV.el('div', 'ov-answer', main);
    var by = sort === 'abs' ? 'its own tool RMS' : sort === 'best' ? 'its tool RMS ÷ the best other config on the same target' : 'its tool RMS ÷ ' + esc(vs.label) + '’s on the same target';
    head.innerHTML = OV.swatch(s) + '<b>' + esc(s.label) + '</b>: its ' + Math.min(limit, rows.length) + ' worst of <b>' + rows.length + '</b> targets (' + esc(scope) +
      '), worst first by ' + by + '. <span class="ds-mut">Each value: tool RMS [mm], median over the config’s repeats on that target.</span>';

    var wrap = OV.el('div', 'ds-scroll ov-tscroll', main);
    var others = live.filter(function (x) { return x.key !== s.key; });
    var shown = others.length > 6 ? others.filter(function (x) { return M.count[x.key] >= 20; }).slice(0, 6) : others;
    var html = '<table class="ds-table ov-ttable"><thead><tr><th class="ds-text">#</th><th class="ds-text">target</th><th class="ds-text">kind</th>' +
      '<th class="ds-text">dataset · split</th><th>' + (M.speedKey === 'speed_fraction' ? 'speed fraction' : 'speed') + '</th>' +
      '<th>' + esc(OV.short(s.label, 22)) + '<span class="ds-unit">tool RMS [mm]</span></th>' +
      (sort !== 'abs' ? '<th>ratio<span class="ds-unit">÷ ' + (sort === 'vs' ? esc(vs.label) : 'best other') + '</span></th>' : '') +
      shown.map(function (x) { return '<th class="ov-other" title="' + esc(x.label) + '">' + OV.swatch(x) + esc(OV.short(x.label, 16)) + '<span class="ds-unit">[mm]</span></th>'; }).join('') +
      '<th class="ds-text">open</th></tr></thead><tbody>';
    rows.slice(0, limit).forEach(function (r, at) {
      var i = r.i, run = OV.runUrl(s.key, i), reps = OV.reps(s.key, i);
      html += '<tr><td class="ds-text ds-mut">' + (at + 1) + '</td>' +
        '<td class="ds-text"><a class="ov-tlink" target="_blank" rel="noopener" href="' + esc(OV.targetUrl(i)) + '">' + esc(M.targets.task[i]) + '</a></td>' +
        '<td class="ds-text ds-mut">' + esc(M.kinds[M.targets.kind[i]] || '') + '</td>' +
        '<td class="ds-text">' + esc(M.groups[M.targets.g[i]].key) + '</td>' +
        '<td>' + (M.targets.v[i] >= 0 ? OV.sp(M.speeds[M.targets.v[i]]) : '—') + '</td>' +
        '<td><b>' + OV.num(r.value) + '</b>' + (reps > 1 ? ' <span class="ds-mut ov-reps" title="median of ' + reps + ' repeats">' + reps + ' rep</span>' : '') + '</td>' +
        (sort !== 'abs' ? '<td>' + OV.times(r.ratio) + '</td>' : '') +
        shown.map(function (x) { var val = M.rms[x.key][i]; return '<td class="' + (val === null ? 'ds-mut' : '') + '">' + (val === null ? '—' : OV.num(val)) + '</td>'; }).join('') +
        '<td class="ds-text ds-actions"><a class="ds-link" target="_blank" rel="noopener" href="' + esc(OV.targetUrl(i)) + '">Target ↗</a>' +
        (run ? '<a class="ds-link ov-runlink" target="_blank" rel="noopener" href="' + esc(run) + '">run ↗</a>' : '') + '</td></tr>';
    });
    wrap.innerHTML = html + '</tbody></table>';
    if (rows.length > limit) {
      var more = OV.el('button', 'ds-btn ds-more', main, 'Show ' + Math.min(40, rows.length - limit) + ' more');
      more.addEventListener('click', function () { OV.setQuery({ n: limit + 40 }); });
    }
    OV.el('p', 'ds-note', main, 'Target ↗ opens today’s Target level (all configs’ lines on that target); run ↗ opens this config’s run report ' +
      '(the repeat closest to the median). ' + (others.length > shown.length ? 'Columns show ' + shown.length + ' of ' + others.length + ' other configs (those with ≥ 20 targets). ' : '') + OV.sourceNote());
  }

  // ── shared drill tab 2: Runs ──────────────────────────────────────────────
  function renderRuns(main, q) {
    var M = OV.M;
    var live = M.series.filter(function (x) { return !x.scorecardOnly; });
    var s = M.seriesByKey[q.cfg] && !M.seriesByKey[q.cfg].scorecardOnly ? M.seriesByKey[q.cfg] : null;
    var g = q.g !== undefined && q.g !== 'all' ? +q.g : null;
    var v = q.v !== undefined && q.v !== 'all' ? +q.v : null;
    var bar = OV.el('div', 'ds-bar ov-filter', main);
    bar.innerHTML =
      '<label><span class="ds-k">config</span><select data-k="cfg"><option value="">all</option>' + live.map(function (x) {
        return '<option value="' + esc(x.key) + '"' + (s && x.key === s.key ? ' selected' : '') + '>' + esc(x.label) + '</option>';
      }).join('') + '</select></label>' +
      '<label><span class="ds-k">dataset · split</span><select data-k="g"><option value="all">all</option>' + M.groups.map(function (gr, gi) {
        return '<option value="' + gi + '"' + (gi === g ? ' selected' : '') + '>' + esc(gr.key) + '</option>';
      }).join('') + '</select></label>' +
      '<label><span class="ds-k">speed</span><select data-k="v"><option value="all">all</option>' + M.speeds.map(function (sp, vi) {
        return '<option value="' + vi + '"' + (vi === v ? ' selected' : '') + '>' + OV.sp(sp) + '</option>';
      }).join('') + '</select></label>' +
      '<a class="ds-link" target="_blank" rel="noopener" href="' + esc(M.siteUrl) + 'index.html">today’s full runs table (Dataset › Runs) ↗</a>';
    bar.querySelectorAll('select').forEach(function (sel) {
      sel.addEventListener('change', function () { var p = {}; p[sel.dataset.k] = sel.value; OV.setQuery(p); });
    });
    var list = [];
    (s ? [s] : live).forEach(function (x) {
      var arr = M.rms[x.key];
      for (var i = 0; i < M.nT; i++) {
        if (arr[i] === null || (g !== null && M.targets.g[i] !== g) || (v !== null && M.targets.v[i] !== v)) continue;
        list.push({ s: x, i: i, value: arr[i] });
      }
    });
    list.sort(function (a, b) { return b.value - a.value; });
    OV.el('div', 'ov-answer', main, '<b>' + list.length + '</b> runs' + (s ? ' of ' + OV.swatch(s) + esc(s.label) : '') +
      ' (one per target and config: the repeat closest to the median), worst tool RMS first. <span class="ds-mut">Showing the first 60.</span>');
    var wrap = OV.el('div', 'ds-scroll ov-tscroll', main);
    var html = '<table class="ds-table"><thead><tr><th class="ds-text">run</th><th class="ds-text">config</th><th class="ds-text">dataset · split</th><th>speed</th><th>tool RMS<span class="ds-unit">[mm] · median of repeats</span></th><th class="ds-text">open</th></tr></thead><tbody>';
    list.slice(0, 60).forEach(function (r) {
      var url = OV.runUrl(r.s.key, r.i);
      var slug = M.targets.slug[r.i] + (M.run[r.s.key][r.i] || '');
      html += '<tr><td class="ds-text ov-mono">' + esc(slug) + '</td><td class="ds-text">' + OV.swatch(r.s) + OV.name(r.s, 26) + '</td><td class="ds-text">' + esc(M.groups[M.targets.g[r.i]].key) +
        '</td><td>' + (M.targets.v[r.i] >= 0 ? OV.sp(M.speeds[M.targets.v[r.i]]) : '—') + '</td><td>' + OV.num(r.value) + '</td><td class="ds-text">' +
        (url ? '<a class="ds-link" target="_blank" rel="noopener" href="' + esc(url) + '">report ↗</a>' : '') + '</td></tr>';
    });
    wrap.innerHTML = html + '</tbody></table>';
  }

  // ── tiny SVG sparkline (log or linear y), shared by several overviews ─────
  OV.spark = function (values, opts) {
    var w = opts.w || 96, h = opts.h || 26, pad = 3;
    var lo = opts.lo, hi = opts.hi, log = opts.log;
    function y(val) {
      var a = log ? Math.log10(lo) : lo, b = log ? Math.log10(hi) : hi, t = log ? Math.log10(Math.max(val, lo)) : val;
      return (h - pad) - (b > a ? (t - a) / (b - a) : 0.5) * (h - 2 * pad);
    }
    function x(i) { return pad + i * (w - 2 * pad) / Math.max(1, values.length - 1); }
    var pts = [];
    values.forEach(function (val, i) { if (val !== null && val !== undefined) pts.push([x(i), y(val)]); });
    if (!pts.length) return '<svg class="ov-spark" width="' + w + '" height="' + h + '"></svg>';
    var d = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join('');
    var last = pts[pts.length - 1];
    return '<svg class="ov-spark" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '"><line x1="0" x2="' + w + '" y1="' + (h - 1) + '" y2="' + (h - 1) + '" stroke="#e6e5e0"/>' +
      '<path d="' + d + '" fill="none" stroke="' + opts.color + '" stroke-width="1.6"' + (opts.dash ? ' stroke-dasharray="' + opts.dash.join(' ') + '"' : '') + '/>' +
      '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="2.4" fill="' + opts.color + '"/></svg>';
  };

  // Log-scale colour ramp for tool RMS (light → dark; colour is reserved for data).
  var RAMP = ['#f3f6fb', '#d7e5f5', '#b3cdea', '#86afdb', '#5a8fca', '#3a70b3', '#285594', '#1c3d70', '#13284b'];
  OV.ramp = RAMP;
  OV.rampColor = function (t) {
    t = Math.max(0, Math.min(1, t));
    var at = t * (RAMP.length - 1), lo = Math.floor(at), hi = Math.min(RAMP.length - 1, lo + 1), f = at - lo;
    function hex(c) { return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]; }
    var a = hex(RAMP[lo]), b = hex(RAMP[hi]);
    return 'rgb(' + a.map(function (v, k) { return Math.round(v + (b[k] - v) * f); }).join(',') + ')';
  };
})();
