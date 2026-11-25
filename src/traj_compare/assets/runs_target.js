/* The target view of traj_compare's runs workbench (traj_compare.runs_workbench): ONE target's runs as summary data,
 * then playback of the ticked ones. Zach, Daily Note 2026-11-24 l.3227: "the dataset view, then the target view (at
 * this point its still just summary data though), Then we can actually open up the playback viewer. either our custom
 * one or the rerun one."
 *
 * target.html?site=<key>&target=<slug>[&keep=<line>,<line>][&back=<url>][&why=pair]
 *
 * - The look of traj_compare's Target level (NAVIGATION.md Part A): a run list with a checkbox per run grouped by
 *   config (regex, config / kind chips), the verdict, repeats as lines or bands, joint error per joint and the feedback
 *   share when a run has a torque breakdown.
 * - "Ticked" = checked AND matching the regex AND its chips on. That one set is what every chart draws, what the
 *   buttons count and what they send. keep= ticks the runs the workbench's rail kept; every other run of the target is
 *   listed unticked (out of the filter), so one tick adds it.
 * - Coverage ↗ (when the site wrote a coverage page): that page, this target's trajectory highlighted (#trajectory=).
 * - Open playback: POST __playback (traj_compare.serve) -> traj_compare's comparison viewer over the target and the
 *   ticked runs, opened in this tab; its breadcrumb returns here with the same runs ticked. Open in Rerun: POST
 *   __rerun/selection -> one recording, one plot per joint, one line per ticked run. Without the server (a static host,
 *   file://) both say what they need.
 * Numbers: the site's own (sites/<key>.js, from its payload) and its drawn series (<site>/targets/<slug>.js, NAVIGATION.md
 * C5); nothing is recomputed but medians and quantiles across the ticked runs at each instant.
 */
(function () {
  'use strict';
  var Q = new URLSearchParams(location.search);
  var CONFIG = JSON.parse(document.getElementById('tc-config').textContent);
  var SITES = {}, TARGET = null;
  var site = null, targetIndex = -1, entries = [], charts = [];
  var state = { mode: 'auto', n: 5, joint: '', regex: '', off: {}, groupBy: 'config' };
  window.TC_SITE = function (key, model) { SITES[key] = model; };
  window.trajCompareTarget = function (slug, data) { TARGET = data; };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, parent, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; if (parent) parent.appendChild(e); return e; }
  function store(key, value) { try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; } return null; }
  function load(src) { return new Promise(function (ok, bad) { var s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = function () { bad(new Error('could not load ' + src)); }; document.head.appendChild(s); }); }
  function nice(x, d) { if (x == null || !isFinite(x)) return '—'; var a = Math.abs(x); return a >= 100 ? x.toFixed(0) : a >= 10 ? x.toFixed(1) : x.toPrecision(d || 2); }
  function hexA(hex, a) { var h = String(hex || '#888888').replace('#', ''); return 'rgba(' + parseInt(h.slice(0, 2), 16) + ',' + parseInt(h.slice(2, 4), 16) + ',' + parseInt(h.slice(4, 6), 16) + ',' + a + ')'; }
  function quant(sorted, p) { if (!sorted.length) return null; var i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo); }
  function median(v) { v = v.filter(function (x) { return x != null && isFinite(x); }).sort(function (a, b) { return a - b; }); return quant(v, 0.5); }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  function entryOf(m, i) {
    var L = m.lines, c = m.configs[L.config[i]] || { name: '?', color: '#888888' };
    var repeat = L.repeat[i];
    var series = m.series[L.series[i]];
    return { line: i, id: L.id[i], config: c.name, color: c.color, kind: L.kind[i] ? 'real' : 'sim', series: series,
      repeat: repeat, run: L.run[i], worst: L.worst[i], worstJoint: m.joints[L.worstJoint[i]] || '', tool: L.tool[i],
      kpis: L.kpis[i] || [], fb: L.fb[i],
      label: c.name + (repeat != null ? ' · r' + repeat : '') + ' · ' + series,
      folder: m.href + '/runs/' + L.run[i] };
  }
  function selected() {
    var re = null; try { re = state.regex ? new RegExp(state.regex, 'i') : null; } catch (e) { re = null; }
    return entries.filter(function (e) { return e.checked && !state.off['c:' + e.config] && !state.off['k:' + e.kind] && (!re || re.test(e.label) || re.test(e.id)); });
  }

  // ---------------------------------------------------------------- data
  function boot() {
    var key = Q.get('site'), slug = Q.get('target');
    if (!key || !slug) return Promise.reject(new Error('target.html needs ?site=<key>&target=<slug> (open it from the workbench)'));
    return load('sites/' + encodeURIComponent(key) + '.js').then(function () {
      site = SITES[key];
      if (!site) throw new Error('no site ' + key);
      targetIndex = site.targets.slug.indexOf(slug);
      if (targetIndex < 0) throw new Error('no target ' + slug + ' in ' + site.deployment);
      var keep = Q.has('keep') ? Q.get('keep').split(',').filter(Boolean).map(Number) : null;
      site.lines.target.forEach(function (t, i) {
        if (t !== targetIndex) return;
        var e = entryOf(site, i);
        e.checked = !keep || keep.indexOf(i) >= 0;
        e.out = !!keep && !e.checked;
        entries.push(e);
      });
      return load(site.href + '/targets/' + encodeURIComponent(slug) + '.js').catch(function () { TARGET = null; });
    });
  }

  function timeAxis(points) {
    var spec = site.targets.t[targetIndex];
    if (spec[0] === 'ms') return spec.slice(1).map(function (ms) { return ms / 1000; });
    var out = new Array(points), step = points > 1 ? (spec[1] - spec[0]) / (points - 1) : 0;
    for (var i = 0; i < points; i++) out[i] = spec[0] + i * step;
    return out;
  }

  // ---------------------------------------------------------------- run list
  function renderPanel() {
    var chips = $('chips'); chips.innerHTML = '';
    [['Config', 'c', 'config'], ['Kind', 'k', 'kind']].forEach(function (spec) {
      el('span', 'tv-k', chips, spec[0]);
      var row = el('div', 'row', chips), seen = {};
      entries.forEach(function (e) { seen[e[spec[2]]] = seen[e[spec[2]]] || { n: 0, color: e.color }; seen[e[spec[2]]].n++; });
      Object.keys(seen).forEach(function (v) {
        var b = el('button', 'tv-chip' + (state.off[spec[1] + ':' + v] ? ' off' : ''), row);
        b.type = 'button';
        if (spec[1] === 'c') el('span', 'sw', b).style.background = seen[v].color;
        b.appendChild(document.createTextNode(v)); el('i', '', b, seen[v].n);
        b.dataset.chip = spec[1] + ':' + v;
        b.onclick = function () { var k = spec[1] + ':' + v; state.off[k] = !state.off[k]; update(); };
      });
    });
    var host = $('lines'); host.innerHTML = '';
    var by = {}, order = [];
    entries.forEach(function (e) { var g = state.groupBy === 'kind' ? e.kind : e.config; if (!by[g]) { by[g] = []; order.push(g); } by[g].push(e); });
    var sel = selected();
    order.forEach(function (g) {
      var members = by[g], on = members.filter(function (e) { return sel.indexOf(e) >= 0; }).length;
      var gh = el('div', 'tv-gh', host);
      var all = el('input', '', gh); all.type = 'checkbox'; all.checked = members.every(function (e) { return e.checked; });
      all.setAttribute('aria-label', 'Tick every run of ' + g);
      all.onchange = function () { members.forEach(function (e) { e.checked = all.checked; e.out = false; }); update(); };
      if (state.groupBy === 'config') el('span', 'sw', gh).style.background = members[0].color;
      el('span', '', gh, g); el('span', 'tv-mut', gh, on + '/' + members.length);
      members.forEach(function (e) {
        var row = el('label', 'tv-line' + (e.out ? ' out' : ''), host);
        row.setAttribute('data-tc-run', ''); row.dataset.line = String(e.line); row.dataset.config = e.config; row.dataset.kind = e.kind;
        var cb = el('input', '', row); cb.type = 'checkbox'; cb.checked = e.checked; cb.style.accentColor = e.color;
        cb.onchange = function () { e.checked = cb.checked; e.out = false; update(); };
        var nm = el('span', 'nm', row, e.label);
        // WHY two words: a "Does sim match real?" row ticks its pair only (why=pair), the rest may well pass the rail
        if (e.out) el('span', 'tv-mut', nm, Q.get('why') === 'pair' ? ' (not in this pair)' : ' (outside the rail filter)');
        el('span', 'v', row, nice(e.worst) + '°').title = 'RMS joint error at the worst joint (' + e.worstJoint + ')';
        var a = el('a', '', row, '↗'); a.href = e.folder + '/report.html'; a.target = '_blank'; a.rel = 'noopener';
        a.title = 'This run\'s report (built on first open by traj_compare.serve)';
      });
    });
    $('lcount').textContent = sel.length + '/' + entries.length;
  }

  function wirePanel() {
    var panel = $('panel'), w = +store('traj-compare/target-view/panel-w') || 300;
    panel.style.setProperty('--panel-w', w + 'px');
    if (store('traj-compare/target-view/panel-fold') === '1') panel.classList.add('folded');
    $('fold').textContent = panel.classList.contains('folded') ? '»' : '«';
    $('fold').onclick = function () { var f = panel.classList.toggle('folded'); $('fold').textContent = f ? '»' : '«'; store('traj-compare/target-view/panel-fold', f ? '1' : '0'); redrawSoon(); };
    var handle = $('resize');
    handle.onpointerdown = function (ev) {
      ev.preventDefault(); handle.setPointerCapture(ev.pointerId); handle.classList.add('drag');
      var x0 = ev.clientX, w0 = panel.getBoundingClientRect().width;
      handle.onpointermove = function (mv) { panel.style.setProperty('--panel-w', Math.max(200, Math.min(560, w0 + mv.clientX - x0)) + 'px'); };
      handle.onpointerup = function () { handle.onpointermove = null; handle.classList.remove('drag'); store('traj-compare/target-view/panel-w', String(Math.round(panel.getBoundingClientRect().width))); redrawSoon(); };
    };
    $('regex').oninput = function () { state.regex = this.value; update(); };
    $('groupby').onchange = function () { state.groupBy = this.value; renderPanel(); };
    Array.prototype.forEach.call($('mode').children, function (b) { b.onclick = function () { state.mode = b.dataset.mode; Array.prototype.forEach.call($('mode').children, function (x) { x.classList.toggle('on', x === b); }); renderCharts(); }; });
    $('linesn').oninput = function () { state.n = +this.value; $('linesnv').textContent = this.value; renderCharts(); };
    $('playback').onclick = openPlayback;
    $('rerun').onclick = openRerun;
  }

  // ---------------------------------------------------------------- head
  function targetName() { return site.targets.name[targetIndex]; }
  function renderHead() {
    var back = Q.get('back');
    var a = $('back'); a.textContent = back ? '‹ All targets (filter kept)' : '‹ All targets'; a.href = back || 'index.html';
    $('crumb-title').textContent = site.deployment + ' · ' + targetName();
    $('title').textContent = targetName();
    var kinds = { sim: 0, real: 0 }; entries.forEach(function (e) { kinds[e.kind]++; });
    $('sub').textContent = site.deployment + ' · ' + plural(entries.length, 'run') + ' (' + kinds.sim + ' sim · ' + kinds.real + ' real) · ' + site.joints.join(', ');
    document.title = targetName() + ' · target view';
    // "Coverage ↗": this target's trajectory on its site's coverage page, highlighted among the deployment's targets
    // (feedback fb-5defddb0: "a page you can see standalone or just quickly get there from the traj compare stuff").
    // WHY by the page's own name (CONFIG.coverage, dataset.coverage_names): a link must name exactly one trajectory there
    var cov = (CONFIG.coverage || {})[Q.get('site')], name = cov && cov.names ? cov.names[Q.get('target')] : null, link = $('coverage');
    if (name) {
      link.href = cov.href + '#tab=trajectories&trajectory=' + encodeURIComponent(name);
      link.hidden = false;
    }
  }

  function renderVerdict() {
    var sel = selected(), by = {}, order = [];
    sel.forEach(function (e) { if (!by[e.config]) { by[e.config] = []; order.push(e.config); } by[e.config].push(e); });
    var v = $('verdict'); v.innerHTML = '';
    el('h2', '', v, 'Which config tracks this target better?');
    if (!order.length) { el('div', 'tv-mut', v, 'Nothing ticked.'); return; }
    var league = CONFIG.league || {}, k = (site.kpis || []).map(function (x) { return x.id; }).indexOf(league.id);
    var rows = order.map(function (c) {
      return { c: c, color: by[c][0].color, n: by[c].length, med: median(by[c].map(function (e) { return e.worst; })),
        kpi: k >= 0 ? median(by[c].map(function (e) { return e.kpis[k]; })) : league.id === 'tool_rms' ? median(by[c].map(function (e) { return e.tool; })) : null };
    }).sort(function (a, b) { return (a.med == null) - (b.med == null) || a.med - b.med; });
    var p = el('div', '', v);
    var sw = function (r) { var s = document.createElement('span'); s.className = 'sw'; s.style.background = r.color; return s; };
    if (rows.length === 1) {
      el('b', '', p, 'Nothing to compare'); p.appendChild(document.createTextNode(': only ')); p.appendChild(sw(rows[0]));
      p.appendChild(document.createTextNode(' ' + rows[0].c + ' is ticked · median ' + nice(rows[0].med) + '° over ' + plural(rows[0].n, 'run')));
    } else {
      p.appendChild(sw(rows[0])); el('b', '', p, ' ' + rows[0].c);
      p.appendChild(document.createTextNode(' tracks best: median ' + nice(rows[0].med) + '° (worst-joint RMS, n=' + rows[0].n + ')' +
        rows.slice(1).map(function (r) { return ' · ' + r.c + ' ' + nice(r.med / rows[0].med) + '×'; }).join('')));
    }
    var kpiText = rows.some(function (r) { return r.kpi != null; }) ? '; ' + (league.label || league.id) + ' ' + rows.map(function (r) { return r.c + ' ' + nice(r.kpi) + (league.unit ? ' ' + league.unit : ''); }).join(' · ') : '';
    el('div', 'tv-mut', v, 'median over the ticked runs of each run\'s RMS joint error at its worst joint' + kpiText);
  }

  // ---------------------------------------------------------------- charts
  function destroy() { charts.forEach(function (c) { c.destroy(); }); charts = []; }
  function chart(host, title, unit, t, layers) {
    var box = el('div', 'tv-chart', host);
    var tt = el('div', 't', box, title); var rate = el('span', '', tt, layers.rate); rate.setAttribute('data-tc-drawn-rate', '');
    var draws = el('div', 'draws', box);
    layers.draws.forEach(function (d) { var s = el('span', '', draws); s.setAttribute('data-tc-draw', ''); s.dataset.config = d.config; s.dataset.draw = d.draw; var w = el('span', 'sw', s); w.style.background = d.color; s.appendChild(document.createTextNode(' ' + d.text)); });
    var plotHost = el('div', '', box);
    var width = Math.max(300, box.getBoundingClientRect().width - 22);
    charts.push(new uPlot({ width: width, height: 210, legend: { show: false }, cursor: { drag: { x: true, y: false } },
      scales: { x: { time: false } },
      axes: [{ values: function (u, v) { return v.map(function (x) { return x + ' s'; }); } }, { values: function (u, v) { return v.map(function (x) { return x + unit; }); }, size: 54 }],
      series: [{}].concat(layers.series), bands: layers.bands }, [t].concat(layers.data), plotHost));
  }
  function layersFor(members, get, n) {
    var by = {}, order = [], series = [], data = [], bands = [], draws = [];
    members.forEach(function (e) { if (!by[e.config]) { by[e.config] = []; order.push(e.config); } by[e.config].push(e); });
    order.forEach(function (c) {
      var g = by[c], color = g[0].color, hasReal = g.some(function (e) { return e.kind === 'real'; });
      var vals = g.map(get).filter(Boolean);
      if (!vals.length) return;
      var asBands = state.mode === 'bands' || (state.mode === 'auto' && vals.length > state.n);
      if (!asBands) {
        // WHY dashed sim beside real: kind is never shown by colour alone (NAVIGATION.md C4)
        g.forEach(function (e) { var v = get(e); if (!v) return; series.push({ stroke: color, width: e.kind === 'real' ? 1.6 : 1.2, dash: hasReal && e.kind === 'sim' ? [5, 4] : undefined }); data.push(v); });
        draws.push({ config: c, color: color, draw: 'lines', text: c + ' · ' + vals.length + ' as lines' + (hasReal ? ' (sim dashed)' : '') });
      } else {
        var lo = [], q1 = [], md = [], q3 = [], hi = [];
        for (var i = 0; i < n; i++) {
          var col = []; for (var j = 0; j < vals.length; j++) { var x = vals[j][i]; if (x != null && isFinite(x)) col.push(x); }
          col.sort(function (a, b) { return a - b; });
          lo.push(quant(col, 0)); q1.push(quant(col, 0.25)); md.push(quant(col, 0.5)); q3.push(quant(col, 0.75)); hi.push(quant(col, 1));
        }
        var base = series.length + 1;
        [hi, q3, md, q1, lo].forEach(function (arr, k) { series.push({ stroke: k === 2 ? color : 'transparent', width: k === 2 ? 1.6 : 0 }); data.push(arr); });
        bands.push({ series: [base, base + 4], fill: hexA(color, 0.10) }, { series: [base + 1, base + 3], fill: hexA(color, 0.25) });
        draws.push({ config: c, color: color, draw: 'bands', text: c + ' · ' + vals.length + ' as median · IQR · min–max' });
      }
    });
    return { series: series, data: data, bands: bands, draws: draws };
  }
  function renderCharts() {
    destroy();
    var host = $('sections'); host.innerHTML = '';
    var sel = selected();
    if (!sel.length) { el('p', 'tv-mut', host, 'No run ticked: tick a run on the left.'); return; }
    if (!TARGET) { el('p', 'tv-mut', host, 'The drawn series of this target did not load (' + site.href + '/targets/' + site.targets.slug[targetIndex] + '.js).'); return; }
    var byId = {}; TARGET.lines.forEach(function (l) { byId[l.id] = l; });
    var t = timeAxis(TARGET.points), rate = 'drawn at ' + nice(TARGET.drawn_hz, 3) + ' Hz';
    var joints = state.joint && site.joints.indexOf(state.joint) >= 0 ? [state.joint] : site.joints;
    var sec = el('section', 'tv-sec', host);
    el('h3', '', sec, 'How repeatable is each config on this target?');
    el('p', '', sec, 'Each chart is one joint\'s error, target − run, over the trajectory. A config draws lines while it has ≤ N ticked runs and a fan past that (median, IQR, min–max at each instant).');
    var grid = el('div', 'tv-grid', sec);
    joints.forEach(function (j) {
      var idx = site.joints.indexOf(j);
      chart(grid, j + ': joint error, target − run [°]', '°', t, Object.assign(layersFor(sel, function (e) { var l = byId[e.id]; return l && l.e_deg ? l.e_deg[idx] : null; }, t.length), { rate: rate }));
    });
    var withTorque = sel.filter(function (e) { var l = byId[e.id]; return l && l.torque && l.torque.fb_share_over_time; });
    if (withTorque.length) {
      var tsec = el('section', 'tv-sec', host);
      el('h3', '', tsec, 'How much of the commanded torque did the feedback supply?');
      el('p', '', tsec, 'FB share = Σ|feedback| / (Σ|feedforward| + Σ|feedback|) over a ±150 ms window, per joint (traj_compare\'s own series). ' + withTorque.length + ' of ' + sel.length + ' ticked runs have a torque breakdown.');
      var tg = el('div', 'tv-grid', tsec);
      joints.forEach(function (j) {
        var idx = site.joints.indexOf(j);
        chart(tg, j + ': feedback share of the command, ±150 ms [%]', '%', t, Object.assign(layersFor(withTorque, function (e) { var s = byId[e.id].torque.fb_share_over_time[idx]; return s ? s.map(function (x) { return x == null ? null : 100 * x; }) : null; }, t.length), { rate: rate }));
      });
    }
  }
  var redrawTimer = null;
  function redrawSoon() { clearTimeout(redrawTimer); redrawTimer = setTimeout(renderCharts, 120); }
  window.addEventListener('resize', redrawSoon);

  // ---------------------------------------------------------------- playback: ours or Rerun
  function needs(what, why) {
    return what + ' needs traj_compare\'s server, and this page has none (' + why + '). Run: ' + CONFIG.serve +
      '  then open ' + CONFIG.page + 'index.html from it.';
  }
  function renderButtons() {
    var n = selected().length;
    $('playback').textContent = 'Open playback · ' + plural(n, 'run');
    $('rerun').textContent = 'Open in Rerun · ' + plural(n, 'run');
    $('playback').disabled = $('rerun').disabled = !n;
  }
  function picks() {
    return selected().map(function (e) { return { folder: e.folder, series: e.series, label: e.label, color: e.color }; });
  }
  /** This page with exactly the ticked runs kept, so playback's breadcrumb returns to the same ticks. */
  function hereWithTicks() {
    var q = new URLSearchParams(location.search);
    q.set('keep', selected().map(function (e) { return e.line; }).join(','));
    return location.pathname + '?' + q.toString().replace(/%2C/g, ',');
  }
  function post(endpoint, body) {
    return fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) {
        return r.json().catch(function () { return null; }).then(function (answer) {
          if (!answer) throw Object.assign(new Error('HTTP ' + r.status + ', no answer from traj_compare.serve'), { static: true });
          return answer;
        });
      });
  }
  function say(text, bad) { var s = $('status'); s.className = 'tv-status' + (bad ? ' bad' : ''); s.textContent = text; }
  function openPlayback() {
    if (!CONFIG.rerunServer) { say(needs('Playback', 'it was written for a static host'), true); return; }
    var n = selected().length;
    say('Building the playback of ' + plural(n, 'run') + ' (traj_compare\'s viewer)…');
    var back = Q.get('back') || 'index.html';
    try { var u = new URL(back, location.href); if (u.origin === location.origin) back = u.pathname + u.search + u.hash; } catch (e) { /* keep it */ }
    post('__playback', { runs: picks(), title: targetName(), crumbs: [['‹ All targets', back], [targetName(), hereWithTicks()]] })
      .then(function (a) {
        window.TV_LAST_PLAYBACK = a;
        if (!a.ok) { say('Playback failed: ' + (a.error || 'unknown'), true); return; }
        location.href = a.href;
      })
      .catch(function (err) { say(needs('Playback', err.message), true); });
  }
  function openRerun() {
    if (!CONFIG.rerunServer) { say(needs('Open in Rerun', 'it was written for a static host'), true); return; }
    var n = selected().length;
    say('Building one recording of ' + plural(n, 'run') + '…');
    post('__rerun/selection', { runs: picks() })
      .then(function (a) {
        window.TV_LAST_RERUN = a;
        if (!a.ok) { say('Open in Rerun failed: ' + (a.error || 'unknown') + (a.command ? ' · run it yourself: ' + a.command : ''), true); return; }
        say((a.dry ? 'Built (not launched): ' : 'Opened in Rerun: ') + plural(a.n, 'line') + ' + target → ' + String(a.rrd).split('/').pop());
      })
      .catch(function (err) { say(needs('Open in Rerun', err.message), true); });
  }

  // ---------------------------------------------------------------- glue
  function update() {
    renderPanel(); renderVerdict(); renderButtons(); renderCharts();
    window.TV_STATE = { selected: selected().map(function (e) { return e.line; }), lines: entries.length, charts: charts.length };
  }

  boot().then(function () {
    if (!entries.length) throw new Error('no runs of this target');
    var js = $('joint');
    el('option', '', js, 'every joint').value = '';
    site.joints.forEach(function (j) { el('option', '', js, j).value = j; });
    if (site.joints.length < 2) js.parentNode.style.display = 'none';
    js.onchange = function () { state.joint = js.value; renderCharts(); };
    wirePanel(); renderHead(); update();
    if (!CONFIG.rerunServer) say(needs('Playback', 'it was written for a static host'));
    document.documentElement.dataset.ready = '1';
  }).catch(function (err) {
    var p = document.createElement('p'); p.className = 'tv-error'; p.textContent = err.message;
    document.body.insertBefore(p, document.body.firstChild);
    document.documentElement.dataset.ready = '1';
  });
})();
