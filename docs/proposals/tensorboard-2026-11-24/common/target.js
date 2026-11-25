/* The target view (2026-11-24 workbench round). One target's lines (or a basket of lines from several targets), the
 * look of traj_compare's Target level: a Lines panel with a checkbox per line grouped by config, repeats as lines or
 * bands, joint error and feedback-share charts per joint, and Open in Rerun for exactly the selected lines.
 *
 * "Selected" = checked AND matching the regex AND its config/kind chip on. That one set is what every chart draws, what
 * the button counts and what it sends (POST ../__rerun/selection). Numbers: the site's own payload (data/<site>.js,
 * extract.py) and its drawn series (bench <site>/targets/<slug>.js, NAVIGATION.md C5); nothing is recomputed but
 * medians and quantiles across the selected lines at each instant.
 */
(function () {
  'use strict';
  var Q = new URLSearchParams(location.search);
  var EMBED = Q.get('embed') === '1';
  var SITES = {}, TARGETS = {};
  var DEPLOYMENT = { ur5e: 'UR5e + Conveyor PnP cell', ur5e_alone: 'UR5e', bam_fb: 'BAM FB', pendulum: '1-DOF pendulum' }; // arm_motion_bench playback.py DEPLOYMENT_TITLES
  var entries = [], groups = [], charts = [];
  var state = { mode: 'auto', n: 5, joint: '', regex: '', off: {}, groupBy: 'config' };
  if (EMBED) document.body.classList.add('embed');

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, parent, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; if (parent) parent.appendChild(e); return e; }
  function store(key, value) { try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; } }
  function load(src) { return new Promise(function (ok, bad) { var s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = function () { bad(new Error('could not load ' + src)); }; document.head.appendChild(s); }); }
  function nice(x, d) { if (x == null || !isFinite(x)) return '—'; var a = Math.abs(x); return a >= 100 ? x.toFixed(0) : a >= 10 ? x.toFixed(1) : x.toPrecision(d || 2); }
  function hexA(hex, a) { var h = hex.replace('#', ''); return 'rgba(' + parseInt(h.slice(0, 2), 16) + ',' + parseInt(h.slice(2, 4), 16) + ',' + parseInt(h.slice(4, 6), 16) + ',' + a + ')'; }
  function quant(sorted, p) { if (!sorted.length) return null; var i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo); }
  function median(v) { v = v.filter(function (x) { return x != null && isFinite(x); }).sort(function (a, b) { return a - b; }); return quant(v, 0.5); }

  window.TC_SITE = function (name, model) { SITES[name] = model; };
  var pendingSite = null;
  window.trajCompareTarget = function (slug, obj) { TARGETS[pendingSite + '|' + slug] = obj; };

  function entryOf(site, line) {
    var m = SITES[site], L = m.lines, c = m.configs[L.config[line]];
    return { site: site, line: line, model: m, target: L.target[line], config: c.name, color: c.color,
      kind: L.kind[line] ? 'real' : 'sim', series: m.series[L.series[line]], repeat: L.repeat[line], id: L.id[line],
      worst: L.worst[line], worstJoint: m.joints[L.worstJoint[line]] || '', tcp: L.tcp[line], fb: L.fb[line], report: L.report[line] };
  }
  function key(e) { return e.site + ':' + e.line; }
  function selected() {
    var re = null; try { re = state.regex ? new RegExp(state.regex, 'i') : null; } catch (e) { re = null; }
    return entries.filter(function (e) { return e.checked && !state.off['c:' + e.config] && !state.off['k:' + e.kind] && (!re || re.test(e.id)); });
  }

  // ---------------------------------------------------------------- data
  function boot() {
    var basket = (Q.get('basket') || '').split(',').filter(Boolean).map(function (t) { var i = t.lastIndexOf(':'); return { site: t.slice(0, i), line: +t.slice(i + 1) }; });
    var sites = basket.length ? basket.map(function (b) { return b.site; }) : [Q.get('site') || 'ur5e'];
    sites = sites.filter(function (s, i) { return sites.indexOf(s) === i; });
    return Promise.all(sites.map(function (s) { return load('../data/' + s + '.js'); })).then(function () {
      if (basket.length) {
        entries = basket.map(function (b) { var e = entryOf(b.site, b.line); e.checked = true; return e; });
      } else {
        var site = sites[0], m = SITES[site], slug = Q.get('target'), t = m.targets.slug.indexOf(slug);
        if (t < 0) throw new Error('no target ' + slug + ' in ' + site);
        var keep = Q.get('keep') ? Q.get('keep').split(',').map(Number) : null;
        m.lines.target.forEach(function (tt, i) { if (tt === t) { var e = entryOf(site, i); e.checked = !keep || keep.indexOf(i) >= 0; e.out = keep && !e.checked; entries.push(e); } });
      }
      var pairs = [];
      entries.forEach(function (e) { var k = e.site + '|' + e.model.targets.slug[e.target]; if (pairs.indexOf(k) < 0) pairs.push(k); });
      return pairs.reduce(function (p, k) {
        return p.then(function () { var s = k.split('|'); pendingSite = s[0]; return load('../bench/' + s[0] + '/targets/' + s[1] + '.js').catch(function () {}); });
      }, Promise.resolve());
    });
  }

  function timeAxis(m, t, points) {
    var spec = m.targets.t[t];
    if (spec.length === points && points !== 3) return spec.map(function (ms) { return ms / 1000; });
    var out = new Array(points), step = points > 1 ? (spec[1] - spec[0]) / (points - 1) : 0;
    for (var i = 0; i < points; i++) out[i] = spec[0] + i * step;
    return out;
  }

  // ---------------------------------------------------------------- panel
  function renderPanel() {
    var chips = $('chips'); chips.innerHTML = '';
    [['Config', 'c', 'config'], ['Kind', 'k', 'kind']].forEach(function (spec) {
      el('span', 'tv-k', chips, spec[0]);
      var row = el('div', 'row', chips), seen = {};
      entries.forEach(function (e) { seen[e[spec[2]]] = seen[e[spec[2]]] || { n: 0, color: e.color }; seen[e[spec[2]]].n++; });
      Object.keys(seen).forEach(function (v) {
        var b = el('button', 'tv-chip' + (state.off[spec[1] + ':' + v] ? ' off' : ''), row);
        if (spec[1] === 'c') el('span', 'sw', b).style.background = seen[v].color;
        b.appendChild(document.createTextNode(v)); el('i', '', b, seen[v].n);
        b.dataset.chip = spec[1] + ':' + v;
        b.onclick = function () { var k = spec[1] + ':' + v; state.off[k] = !state.off[k]; update(); };
      });
    });
    var host = $('lines'); host.innerHTML = '';
    var by = {}, order = [];
    entries.forEach(function (e) {
      var g = state.groupBy === 'kind' ? e.kind : state.groupBy === 'target' ? e.site + ' · ' + e.model.targets.task[e.target] : e.config;
      if (!by[g]) { by[g] = []; order.push(g); } by[g].push(e);
    });
    var sel = selected();
    order.forEach(function (g) {
      var members = by[g], on = members.filter(function (e) { return sel.indexOf(e) >= 0; }).length;
      var gh = el('div', 'tv-gh', host);
      var all = el('input', '', gh); all.type = 'checkbox'; all.checked = members.every(function (e) { return e.checked; });
      all.onchange = function () { members.forEach(function (e) { e.checked = all.checked; }); update(); };
      if (state.groupBy === 'config') el('span', 'sw', gh).style.cssText = 'display:inline-block;width:9px;height:9px;border-radius:2px;background:' + members[0].color;
      el('span', '', gh, g); el('span', 'tv-mut', gh, on + '/' + members.length);
      members.forEach(function (e) {
        var row = el('label', 'tv-line' + (e.out ? ' out' : ''), host); row.dataset.line = key(e);
        var cb = el('input', '', row); cb.type = 'checkbox'; cb.checked = e.checked; cb.style.accentColor = e.color;
        cb.onchange = function () { e.checked = cb.checked; e.out = false; update(); };
        var nm = el('span', 'nm', row);
        nm.textContent = (entries.length > 1 && state.groupBy !== 'target' && Q.get('basket') ? e.site + ' · ' + e.model.targets.task[e.target] + ' · ' : '') + e.config + ' · r' + e.repeat + ' · ' + e.series;
        if (e.out) el('span', 'tv-mut', nm, ' (outside the rail filter)');
        el('span', 'v', row, nice(e.worst) + '°').title = 'RMS joint error, worst joint (' + e.worstJoint + ')';
        var a = el('a', '', row, '↗'); a.href = '../bench/' + e.site + '/runs/' + e.report + '/report.html'; a.target = '_blank'; a.title = 'Open the run report (built on first open)';
      });
    });
    $('lcount').textContent = sel.length + '/' + entries.length;
  }

  function wirePanel() {
    var panel = $('panel'), w = +store('tv-panel-w') || 300;
    panel.style.setProperty('--panel-w', w + 'px');
    if (store('tv-panel-fold') === '1') panel.classList.add('folded');
    $('fold').onclick = function () { var f = panel.classList.toggle('folded'); $('fold').textContent = f ? '»' : '«'; store('tv-panel-fold', f ? '1' : '0'); redrawSoon(); };
    if (panel.classList.contains('folded')) $('fold').textContent = '»';
    var handle = $('resize');
    handle.onpointerdown = function (ev) {
      ev.preventDefault(); handle.setPointerCapture(ev.pointerId); handle.classList.add('drag');
      var x0 = ev.clientX, w0 = panel.getBoundingClientRect().width;
      handle.onpointermove = function (mv) { var nw = Math.max(200, Math.min(560, w0 + mv.clientX - x0)); panel.style.setProperty('--panel-w', nw + 'px'); };
      handle.onpointerup = function () { handle.onpointermove = null; handle.classList.remove('drag'); store('tv-panel-w', String(Math.round(panel.getBoundingClientRect().width))); redrawSoon(); };
    };
    $('regex').oninput = function () { state.regex = this.value; update(); };
    $('groupby').onchange = function () { state.groupBy = this.value; renderPanel(); };
    if (!Q.get('basket')) $('groupby').querySelector('[value=target]').remove();
    Array.prototype.forEach.call($('mode').children, function (b) { b.onclick = function () { state.mode = b.dataset.mode; Array.prototype.forEach.call($('mode').children, function (x) { x.classList.toggle('on', x === b); }); renderCharts(); }; });
    $('linesn').oninput = function () { state.n = +this.value; $('linesnv').textContent = this.value; renderCharts(); };
    $('rerun').onclick = openRerun;
  }

  // ---------------------------------------------------------------- head
  function renderHead() {
    var first = entries[0], m = first.model, sites = {}, targets = {};
    entries.forEach(function (e) { sites[e.site] = 1; targets[e.site + e.target] = 1; });
    var nT = Object.keys(targets).length, nS = Object.keys(sites).length;
    var crumb = $('crumb'); crumb.innerHTML = '';
    var back = Q.get('back');
    var a = el('a', '', crumb, back ? '‹ All targets (filter kept)' : '‹ All targets'); a.href = back || '../v2/index.html';
    crumb.appendChild(document.createTextNode(' › '));
    el('b', '', crumb, nT === 1 ? DEPLOYMENT[first.site] + ' · ' + m.targets.title[first.target] : 'Selection · ' + entries.length + ' lines from ' + nT + ' targets');
    $('title').textContent = nT === 1 ? m.targets.title[first.target] : 'Selection: ' + entries.length + ' lines, ' + nT + ' targets';
    var kinds = { sim: 0, real: 0 }; entries.forEach(function (e) { kinds[e.kind]++; });
    $('sub').textContent = (nS === 1 ? DEPLOYMENT[first.site] : nS + ' deployments') + ' · ' + entries.length + ' lines (' + kinds.sim + ' sim · ' + kinds.real + ' real) · ' +
      (nS === 1 ? m.joints.join(', ') : 'joints per deployment');
    document.title = (nT === 1 ? m.targets.task[first.target] : 'Selection') + ' · target view';
  }

  function renderVerdict() {
    var sel = selected(), by = {}, order = [];
    sel.forEach(function (e) { if (!by[e.config]) { by[e.config] = []; order.push(e.config); } by[e.config].push(e); });
    var v = $('verdict'); v.innerHTML = '';
    var sites = {}, tg = {}; sel.forEach(function (e) { sites[e.site] = 1; tg[e.site + e.target] = 1; });
    el('h2', '', v, Object.keys(tg).length > 1 ? 'Which config tracks best across the selection?' : 'Which config tracks this target better?');
    if (Object.keys(sites).length > 1) el('div', 'tv-warn', v, '⚠ The selection spans ' + Object.keys(sites).length + ' deployments: different robots and targets, so their errors compare as numbers only, not as the same motion.');
    if (!order.length) { el('div', 'tv-mut', v, 'Nothing selected.'); return; }
    var rows = order.map(function (c) { return { c: c, color: by[c][0].color, n: by[c].length, med: median(by[c].map(function (e) { return e.worst; })), tcp: median(by[c].map(function (e) { return e.tcp; })) }; })
      .sort(function (a, b) { return (a.med == null) - (b.med == null) || a.med - b.med; });
    var p = el('div', '', v);
    if (rows.length === 1) p.innerHTML = '<b>Nothing to compare</b>: only <span class="sw" style="display:inline-block;width:9px;height:9px;background:' + rows[0].color + '"></span> ' + rows[0].c + ' is selected · median ' + nice(rows[0].med) + '° over ' + rows[0].n + ' line' + (rows[0].n > 1 ? 's' : '');
    else p.innerHTML = '<b>' + rows[0].c + '</b> tracks best: median ' + nice(rows[0].med) + '° (worst-joint RMS, n=' + rows[0].n + ')' + rows.slice(1).map(function (r) { return ' · ' + r.c + ' ' + nice(r.med / rows[0].med) + '×'; }).join('');
    el('div', 'tv-mut', v, 'median over the selected lines of each line\'s RMS joint error at its worst joint; tool RMS ' + rows.map(function (r) { return r.c + ' ' + nice(r.tcp) + ' mm'; }).join(' · '));
  }

  // ---------------------------------------------------------------- charts
  function destroy() { charts.forEach(function (c) { c.destroy(); }); charts = []; }
  function chart(host, title, unit, t, layers) {
    var box = el('div', 'tv-chart', host);
    var tt = el('div', 't', box, title); el('span', '', tt, layers.rate);
    var draws = el('div', 'draws', box);
    layers.draws.forEach(function (d) { var s = el('span', '', draws); s.innerHTML = '<span class="sw" style="display:inline-block;width:8px;height:8px;border-radius:2px;background:' + d.color + '"></span> ' + d.text; s.dataset.draw = d.draw; });
    var plotHost = el('div', '', box);
    var width = Math.max(300, box.getBoundingClientRect().width - 22);
    var u = new uPlot({ width: width, height: 210, legend: { show: false }, cursor: { drag: { x: true, y: false } },
      scales: { x: { time: false } },
      axes: [{ values: function (u, v) { return v.map(function (x) { return x + ' s'; }); } }, { values: function (u, v) { return v.map(function (x) { return x + unit; }); }, size: 54 }],
      series: [{}].concat(layers.series), bands: layers.bands }, [t].concat(layers.data), plotHost);
    charts.push(u);
  }
  function layersFor(members, idx, get, n) {
    var by = {}, order = [], series = [], data = [], bands = [], draws = [];
    members.forEach(function (e) { if (!by[e.config]) { by[e.config] = []; order.push(e.config); } by[e.config].push(e); });
    order.forEach(function (c) {
      var g = by[c], color = g[0].color, hasReal = g.some(function (e) { return e.kind === 'real'; });
      var vals = g.map(get).filter(Boolean);
      if (!vals.length) return;
      var asBands = state.mode === 'bands' || (state.mode === 'auto' && vals.length > state.n);
      if (!asBands) {
        g.forEach(function (e) { var v = get(e); if (!v) return; series.push({ stroke: color, width: e.kind === 'real' ? 1.6 : 1.2, dash: hasReal && e.kind === 'sim' ? [5, 4] : undefined }); data.push(v); });
        draws.push({ color: color, draw: 'lines', text: c + ' · ' + vals.length + ' as lines' + (hasReal ? ' (sim dashed)' : '') });
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
        draws.push({ color: color, draw: 'bands', text: c + ' · ' + vals.length + ' as median · IQR · min–max' });
      }
    });
    return { series: series, data: data, bands: bands, draws: draws };
  }
  function renderCharts() {
    destroy();
    var host = $('sections'); host.innerHTML = '';
    var sel = selected(), byT = {}, order = [];
    sel.forEach(function (e) { var k = e.site + '|' + e.target; if (!byT[k]) { byT[k] = []; order.push(k); } byT[k].push(e); });
    if (!order.length) { el('p', 'tv-mut', host, 'No line selected: tick a line on the left.'); return; }
    order.forEach(function (k) {
      var members = byT[k], e0 = members[0], m = e0.model, slug = m.targets.slug[e0.target], file = TARGETS[e0.site + '|' + slug];
      var multi = order.length > 1;
      if (!file) { el('p', 'tv-mut', host, 'The drawn series of ' + slug + ' did not load (bench targets/' + slug + '.js).'); return; }
      var byId = {}; file.lines.forEach(function (l) { byId[l.id] = l; });
      var t = timeAxis(m, e0.target, file.points), rate = 'drawn at ' + nice(file.drawn_hz, 3) + ' Hz';
      var joints = state.joint && m.joints.indexOf(state.joint) >= 0 ? [state.joint] : m.joints;
      var sec = el('section', 'tv-sec', host);
      el('h3', '', sec, (multi ? DEPLOYMENT[e0.site] + ' · ' + m.targets.task[e0.target] + ': ' : '') + 'How repeatable is each config on this target?');
      el('p', '', sec, 'Each chart is one joint\'s error, target − line, over the trajectory. A config draws lines while it has ≤ N selected lines and a fan past that (median, IQR, min–max at each instant).');
      var grid = el('div', 'tv-grid', sec);
      joints.forEach(function (j) {
        var idx = m.joints.indexOf(j);
        chart(grid, j + ': joint error, target − line [°]', '°', t, Object.assign(layersFor(members, idx, function (e) { var l = byId[e.id]; return l && l.e_deg ? l.e_deg[idx] : null; }, t.length), { rate: rate }));
      });
      var withTorque = members.filter(function (e) { var l = byId[e.id]; return l && l.torque && l.torque.fb_share_over_time; });
      if (withTorque.length) {
        var tsec = el('section', 'tv-sec', host);
        el('h3', '', tsec, 'How much of the commanded torque did the feedback supply?');
        el('p', '', tsec, 'FB share = Σ|feedback| / (Σ|feedforward| + Σ|feedback|) over a ±150 ms window, per joint (traj_compare\'s own series). ' + withTorque.length + ' of ' + members.length + ' selected lines have a torque breakdown.');
        var tg = el('div', 'tv-grid', tsec);
        joints.forEach(function (j) {
          var idx = m.joints.indexOf(j);
          chart(tg, j + ': feedback share of the command, ±150 ms [%]', '%', t, Object.assign(layersFor(withTorque, idx, function (e) { var s = byId[e.id].torque.fb_share_over_time[idx]; return s ? s.map(function (x) { return x == null ? null : 100 * x; }) : null; }, t.length), { rate: rate }));
        });
      }
    });
  }
  var redrawTimer = null;
  function redrawSoon() { clearTimeout(redrawTimer); redrawTimer = setTimeout(renderCharts, 120); }
  window.addEventListener('resize', redrawSoon);

  // ---------------------------------------------------------------- rerun
  function renderButton() {
    var n = selected().length, b = $('rerun');
    b.disabled = !n; b.textContent = 'Open in Rerun · ' + n + ' line' + (n === 1 ? '' : 's');
    b.title = 'One recording: the target and every selected line (joint angles and joint error, one plot per joint, one line per run)';
  }
  function openRerun() {
    var sel = selected(), st = $('status');
    st.className = 'tv-status'; st.textContent = 'Building one recording of ' + sel.length + ' lines…';
    var dry = Q.get('dry') === '1' ? '?dry=1' : '';
    fetch('../__rerun/selection' + dry, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ runs: sel.map(function (e) { return { site: e.site, line: e.line }; }) }) })
      .then(function (r) { return r.json(); })
      .then(function (a) {
        window.TV_LAST_RERUN = a;
        if (!a.ok) { st.className = 'tv-status bad'; st.textContent = a.error || 'failed'; return; }
        st.textContent = (dry ? 'Built (not launched): ' : 'Opened in Rerun: ') + a.n + ' lines + target → ' + a.rrd.split('/').pop();
      })
      .catch(function (err) { st.className = 'tv-status bad'; st.textContent = 'Open in Rerun needs serve_round.py (' + err.message + ')'; });
  }

  // ---------------------------------------------------------------- glue
  function update() {
    renderPanel(); renderVerdict(); renderButton(); renderCharts();
    var sel = selected();
    window.TV_STATE = { selected: sel.length, lines: entries.length, charts: charts.length };
    if (EMBED && window.parent !== window) window.parent.postMessage({ type: 'tc-target', site: entries[0].site, target: entries[0].model.targets.slug[entries[0].target], selected: sel.map(function (e) { return { site: e.site, line: e.line }; }) }, '*');
  }

  boot().then(function () {
    if (!entries.length) throw new Error('no lines');
    var m = entries[0].model, js = $('joint');
    el('option', '', js, 'every joint').value = '';
    m.joints.forEach(function (j) { el('option', '', js, j).value = j; });
    if (m.joints.length < 2) js.parentNode.style.display = 'none';
    js.onchange = function () { state.joint = js.value; renderCharts(); };
    wirePanel(); renderHead(); update();
    document.documentElement.dataset.ready = '1';
  }).catch(function (err) {
    document.body.insertAdjacentHTML('afterbegin', '<p style="color:#a4372a;padding:12px">' + err.message + '</p>');
    document.documentElement.dataset.ready = '1';
  });
})();
