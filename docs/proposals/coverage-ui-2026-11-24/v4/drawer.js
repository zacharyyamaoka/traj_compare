/* drawer.js — V4 "Tidy": the drill drawer for one trajectory (Zach, Nov 23: "There is no drill in option in the
 * trajectories page … I want the option to open in Rerun").
 *
 * A row click opens it on the right; Esc or × closes it; ↑ / ↓ (or the arrows in its head) step through the rows the
 * table shows. What it holds, top to bottom: Open in Rerun (POST /__rerun/open?rrd=data/rrd/<name>.rrd, the command +
 * Copy when that fails), the trajectory's numbers, what it alone adds, its per-joint spans against the whole dataset's,
 * its tool path among all the others (payload.tool.spaghetti), and its joints over time (data/samples.json, fetched
 * once on the first open; every sample of the trajectory, not subsampled).
 * Every number is a field of the payload or of data/trajectories.js; the drawer only ranks and draws them.
 */
(function (global) {
  'use strict';

  const RERUN_SDK = '0.40.0';
  let api = null;
  let panel = null;
  let body = null;
  let current = null;
  let order = [];
  let samples = null;
  let samplesError = null;
  let samplesPromise = null;

  function init(pageApi) {
    api = pageApi;
    const { el } = api;
    panel = el('aside', { class: 'v4-drawer', 'data-v4-drawer': '', role: 'dialog', 'aria-label': 'Trajectory', hidden: true });
    body = el('div', { class: 'v4-drawer-body' });
    panel.append(body);
    document.body.append(panel);
    document.addEventListener('keydown', (event) => {
      if (panel.hidden) return;
      if (event.key === 'Escape') { close(); return; }
      const typing = /^(INPUT|SELECT|TEXTAREA)$/.test((event.target && event.target.tagName) || '');
      if (typing) return;
      if (event.key === 'ArrowDown' || event.key === 'j') { event.preventDefault(); step(1); }
      if (event.key === 'ArrowUp' || event.key === 'k') { event.preventDefault(); step(-1); }
    });
    if (global.TrajCoverage && global.TrajCoverage.onTab) global.TrajCoverage.onTab((id) => { if (id !== 'trajectories') close(); });
  }

  function isOpen() { return panel && !panel.hidden; }
  function setOrder(names) { order = names; if (isOpen()) paintNav(); }

  function close() {
    if (!panel || panel.hidden) return;
    panel.hidden = true;
    document.body.classList.remove('v4-drawer-open');
  }

  function step(delta) {
    if (!current || !order.length) return;
    const at = order.indexOf(current);
    const next = order[(at < 0 ? 0 : at + delta + order.length) % order.length];
    const index = api.payload.trajectories.findIndex((row) => row.name === next);
    if (index >= 0 && api.state.highlight !== index) api.setHighlight(index);
    open(next, order);
    const tr = document.querySelector(`tr[data-row][data-name="${next}"]`);
    if (tr) tr.scrollIntoView({ block: 'nearest' });
  }

  function rowOf(name) { return api.trajectories.find((row) => row.name === name); }

  let navBox = null;
  function paintNav() {
    if (!navBox) return;
    const at = order.indexOf(current);
    navBox.lastChild.textContent = at < 0 ? 'not in the table\'s rows' : `${at + 1} of ${order.length} shown`;
  }

  function open(name, names) {
    const { el, count, duration, pct } = api;
    const row = rowOf(name);
    if (!row) return;
    current = name;
    if (names) order = names;
    panel.hidden = false;
    document.body.classList.add('v4-drawer-open');
    const index = api.payload.trajectories.findIndex((item) => item.name === name);
    const groupKey = api.payload.source.group_by;
    const split = groupKey ? (row.tags || {})[groupKey] : null;
    const tags = Object.entries(row.tags || {}).filter(([key]) => key !== groupKey);

    navBox = el('div', { class: 'v4-drawer-nav' }, [
      el('button', { type: 'button', class: 'v4-icon', title: 'Previous row (↑)', text: '↑', onclick: () => step(-1) }),
      el('button', { type: 'button', class: 'v4-icon', title: 'Next row (↓)', text: '↓', onclick: () => step(1) }),
      el('span', { class: 'v4-note' }),
    ]);
    const head = el('header', { class: 'v4-drawer-head' }, [
      navBox,
      el('button', { type: 'button', class: 'v4-x', 'data-v4-drawer-close': '', title: 'Close (Esc)', text: '×', onclick: close }),
      el('h2', null, [el('span', { 'data-v4-drawer-name': '', text: name }), split ? el('span', { class: 'v4-split', style: `--c:${api.groupColour(split)}`, title: `${groupKey} = ${split}` }, [el('i'), split]) : null]),
      el('p', { class: 'v4-drawer-meta', text: [...tags.map(([key, value]) => `${key} ${value}`), `#${index + 1} in the dataset's order`].join(' · ') }),
    ]);

    // WHY two columns: the whole trajectory at a glance in one screen (Zach: "at a glance being able to see ... the
    // tool position"), numbers on the left, its pictures (tool path, joints over time) on the right
    body.replaceChildren(head, rerunBar(row), el('div', { class: 'v4-drawer-cols' }, [
      el('div', { class: 'v4-drawer-col' }, [numbers(row), alone(row), spans(row, index)].filter(Boolean)),
      el('div', { class: 'v4-drawer-col' }, [toolPaths(index), overTime(row)].filter(Boolean)),
    ]));
    body.append(el('footer', { class: 'v4-drawer-foot' }, [
      el('button', { type: 'button', class: 'v4-link', text: 'See its path on One joint ›', title: 'it stays highlighted there and in the 3-D views',
        onclick: () => { close(); api.show('joint'); } }),
    ]));
    body.scrollTop = 0;
    paintNav();
  }

  // ── Open in Rerun ─────────────────────────────────────────────────────────────────────────────────────────────

  function fallbackCommand(rrd) {
    // WHY derived here: the command needs the .rrd's absolute path, which only file:// can tell the page; served pages
    // get it from the endpoint's own answer (viewer_command) and use this only when that answer has none
    let path = rrd;
    try {
      const url = new URL('../' + rrd, global.location.href);
      if (url.protocol === 'file:') path = decodeURIComponent(url.pathname);
      else path = '/home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/' + rrd;
    } catch (error) { /* keep the relative path */ }
    return `uvx --from rerun-sdk==${RERUN_SDK} rerun ${path}`;
  }

  function copyText(text) {
    try {
      if (global.navigator.clipboard && global.isSecureContext) return global.navigator.clipboard.writeText(text).then(() => true, () => false);
    } catch (error) { /* fall through */ }
    try {
      const area = document.createElement('textarea');
      area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
      document.body.append(area); area.select();
      const ok = document.execCommand('copy');
      area.remove();
      return Promise.resolve(ok);
    } catch (error) { return Promise.resolve(false); }
  }

  function rerunBar(row) {
    const { el } = api;
    const rrd = row.rrd || `data/rrd/${row.name}.rrd`;
    const status = el('span', { class: 'v4-rerun-status', 'data-v4-rerun-status': '' });
    const command = el('code', { class: 'v4-rerun-cmd', hidden: true });
    const copy = el('button', { type: 'button', class: 'v4-btn', hidden: true, text: 'Copy', onclick: () => {
      copyText(command.textContent).then((ok) => say(ok ? 'Copied: paste it in a terminal' : 'Copy failed: select the command', !ok));
    } });
    const say = (text, bad) => { status.textContent = text; status.classList.toggle('bad', !!bad); };
    const showCommand = (text) => { command.textContent = text; command.hidden = false; copy.hidden = false; };
    const open = el('button', { type: 'button', class: 'v4-btn primary', 'data-v4-rerun': '', title: `POST /__rerun/open?rrd=${rrd}: the round's server starts the native Rerun viewer`, onclick: () => {
      say('Opening Rerun…');
      const served = /^https?:$/.test(global.location.protocol);
      if (!served) { say('No launcher on file://: run this command', true); showCommand(fallbackCommand(rrd)); return; }
      fetch(global.location.origin + '/__rerun/open?rrd=' + encodeURIComponent(rrd), { method: 'POST' })
        .then((response) => response.text().then((text) => {
          let answer = null;
          try { answer = JSON.parse(text); } catch (error) { answer = null; }
          if (answer && answer.ok) { say('Opening Rerun… (the window can take a few seconds)'); if (answer.command) showCommand(answer.command); return; }
          say(answer && answer.error ? `${answer.error}: run this command` : 'No launcher on this server: run this command', true);
          showCommand((answer && answer.command) || fallbackCommand(rrd));
        }), () => { say('No launcher reachable: run this command', true); showCommand(fallbackCommand(rrd)); });
    } }, ['Open in Rerun']);
    return el('section', { class: 'v4-rerun' }, [
      el('div', { class: 'v4-rerun-row' }, [open, el('span', { class: 'v4-note', text: `${rrd.split('/').pop()} · q, qd, qdd per joint (°) + the tool path` })]),
      el('div', { class: 'v4-rerun-row' }, [status]),
      el('div', { class: 'v4-rerun-row' }, [command, copy]),
    ]);
  }

  // ── numbers ───────────────────────────────────────────────────────────────────────────────────────────────────

  function numbers(row) {
    const { el, count, duration, minus } = api;
    const tile = (value, label, key) => el('div', { class: 'v4-dstat', title: key }, [el('span', { class: 'value', text: value }), el('span', { class: 'label', text: label })]);
    const mm = (m) => minus(String(Math.round(m * 1000)));
    return el('section', null, [
      el('h3', { text: 'In numbers' }),
      el('div', { class: 'v4-dstats' }, [
        tile(duration(row.duration_s), 'duration', 'duration_s'),
        tile(count(row.samples), 'samples', 'samples'),
        tile(count(row.new_cells), 'new cells, first to visit', 'new_cells'),
        tile(count(row.only_it_q_qd_cells), 'cells only it visits', 'only_it_q_qd_cells'),
        tile(`${row.tool_path_m.toFixed(2)} m`, 'tool path length', 'tool_path_m'),
        tile(`${row.tool_speed_max_m_s.toFixed(2)} m/s`, 'fastest tool speed', 'tool_speed_max_m_s'),
        tile(`${mm(row.tool_z_min_m)} … ${mm(row.tool_z_max_m)}`, 'tool height z, mm', 'tool_z_min_m / tool_z_max_m'),
        tile(`${Math.round(row.tool_tilt_max_deg)}°`, 'largest tool tilt', 'tool_tilt_max_deg'),
      ]),
    ]);
  }

  // ── what it alone adds: its number, ranked among all, on a strip of everyone's ────────────────────────────────

  function rankOf(value, values) { return 1 + values.filter((v) => v > value).length; }

  function strip(values, value, label) {
    const { canvasOf, INK } = api;
    const width = 220;
    const height = 26;
    const { canvas, g } = canvasOf(width, height);
    const hi = Math.max(1, ...values);
    const sx = (v) => 6 + (v / hi) * (width - 12);
    g.strokeStyle = '#dddcd6';
    g.beginPath(); g.moveTo(6, 13.5); g.lineTo(width - 6, 13.5); g.stroke();
    g.strokeStyle = 'rgba(82,81,78,0.45)';
    for (const v of values) { g.beginPath(); g.moveTo(Math.round(sx(v)) + 0.5, 8); g.lineTo(Math.round(sx(v)) + 0.5, 19); g.stroke(); }
    g.strokeStyle = INK; g.lineWidth = 2.5;
    g.beginPath(); g.moveTo(sx(value), 3); g.lineTo(sx(value), 24); g.stroke();
    canvas.setAttribute('aria-label', label);
    canvas.title = label;
    return canvas;
  }

  function alone(row) {
    const { el, count } = api;
    const all = api.trajectories;
    const only = all.map((item) => item.only_it_q_qd_cells || 0);
    const fresh = all.map((item) => item.new_cells || 0);
    const rOnly = rankOf(row.only_it_q_qd_cells || 0, only);
    const rNew = rankOf(row.new_cells || 0, fresh);
    return el('section', null, [
      el('h3', { text: 'What it alone adds' }),
      el('div', { class: 'v4-alone' }, [
        el('div', null, [
          el('p', { html: `<b>${count(row.only_it_q_qd_cells)}</b> position × speed cells (all joints) that <b>no other</b> trajectory visits: drop it and the dataset loses them. Rank <b>${rOnly}</b> of ${all.length}.` }),
          strip(only, row.only_it_q_qd_cells || 0, 'cells only it visits: every trajectory a grey tick, this one black'),
        ]),
        el('div', null, [
          el('p', { html: `<b>${count(row.new_cells)}</b> cells it was the <b>first</b> to visit, in the dataset's order. Rank <b>${rNew}</b> of ${all.length}.` }),
          strip(fresh, row.new_cells || 0, 'new cells: every trajectory a grey tick, this one black'),
        ]),
      ]),
      el('p', { class: 'v4-note', text: 'Strips: every trajectory a grey tick, this one black, 0 at the left, the most at the right.' }),
    ]);
  }

  // ── its spans against the dataset's ───────────────────────────────────────────────────────────────────────────

  function short(value) {
    if (value === null || value === undefined || !Number.isFinite(value)) return '—';
    return value > 0 && value < 10 ? value.toFixed(1).replace(/\.0$/, '') : String(Math.round(value));
  }

  function spans(row) {
    const { el, pct, ACCENT } = api;
    const signals = [['q', 'position'], ['qd', 'speed'], ['qdd', 'acceleration']];
    const head = el('tr', null, [el('th', { class: 'left', text: 'joint' }), ...signals.map(([, word]) => el('th', { text: word }))]);
    const tbody = el('tbody');
    for (const joint of api.joints()) {
      const hist = api.payload.hist[joint.name];
      tbody.append(el('tr', null, [
        el('td', { class: 'left', text: joint.name }),
        ...signals.map(([signal]) => {
          const mine = ((row.span_pct || {})[joint.name] || {})[signal];
          const whole = hist[signal] ? hist[signal].span_pct : null;
          const track = el('span', { class: 'v4-span-track' }, [
            el('span', { class: 'all', style: `width:${Math.max(0, Math.min(100, whole || 0)).toFixed(1)}%` }),
            el('span', { class: 'mine', style: `width:${Math.max(0, Math.min(100, mine || 0)).toFixed(1)}%;background:${ACCENT}` }),
          ]);
          return el('td', { title: `${joint.name} ${signal}: this trajectory ${pct(mine)}, the whole dataset ${pct(whole)} of the limit range` },
            el('span', { class: 'v4-span-cell' }, [track, el('span', { class: 'v4-span-text', text: `${short(mine)} / ${short(whole)} %` })]));
        }),
      ]));
    }
    return el('section', null, [
      el('h3', { text: 'Its span against the whole dataset\'s' }),
      el('p', { class: 'v4-note v4-spans-note', text: 'share of each joint\'s limit range, this trajectory / all together (p0.1–p99.9)' }),
      el('table', { class: 'v4-spans' }, [el('thead', null, head), tbody]),
      el('div', { class: 'cov-legend' }, [
        el('span', { class: 'cov-li' }, [el('i', { class: 'cov-sw fill', style: `background:${ACCENT}` }), 'this trajectory (p0.1–p99.9 of its own samples)']),
        el('span', { class: 'cov-li' }, [el('i', { class: 'cov-sw fill', style: 'background:#d9d8d2' }), `all ${api.trajectories.length} together`]),
        el('span', { class: 'cov-li' }, ['bar = share of the joint\'s limit range, 0 – 100 %']),
      ]),
    ]);
  }

  // ── its tool path among all the others ────────────────────────────────────────────────────────────────────────

  function toolPaths(index) {
    const { el, canvasOf, INK, payload } = api;
    const tool = payload.tool;
    if (!tool || !tool.spaghetti || !tool.spaghetti[index]) return null;
    const paths = tool.spaghetti;
    const lo = [Infinity, Infinity, Infinity];
    const hi = [-Infinity, -Infinity, -Infinity];
    for (const path of paths) for (const p of path) for (let a = 0; a < 3; a++) { if (p[a] < lo[a]) lo[a] = p[a]; if (p[a] > hi[a]) hi[a] = p[a]; }
    const pad = 0.04;
    for (let a = 0; a < 3; a++) { lo[a] -= pad; hi[a] += pad; }
    const views = [['from above', 0, 1, 'x', 'y'], ['from the front', 0, 2, 'x', 'z']];
    const totalW = 156;
    const k = Math.min(totalW / (hi[0] - lo[0]), 156 / Math.max(hi[1] - lo[1], hi[2] - lo[2]));
    const panels = views.map(([title, u, v, nu, nv]) => {
      const w = Math.round((hi[u] - lo[u]) * k) + 2;
      const h = Math.round((hi[v] - lo[v]) * k) + 2;
      const { canvas, g } = canvasOf(w, h);
      const sx = (x) => 1 + (x - lo[u]) * k;
      const sy = (y) => h - 1 - (y - lo[v]) * k;
      g.fillStyle = '#ffffff'; g.fillRect(0, 0, w, h);
      g.strokeStyle = '#dddcd6'; g.strokeRect(0.5, 0.5, w - 1, h - 1);
      if (lo[u] < 0 && hi[u] > 0 && lo[v] < 0 && hi[v] > 0) {
        g.strokeStyle = 'rgba(34,33,31,0.5)'; g.lineWidth = 1;
        g.beginPath(); g.moveTo(sx(0) - 5, sy(0)); g.lineTo(sx(0) + 5, sy(0)); g.moveTo(sx(0), sy(0) - 5); g.lineTo(sx(0), sy(0) + 5); g.stroke();
      }
      const stroke = (path) => { g.beginPath(); path.forEach((p, n) => (n ? g.lineTo(sx(p[u]), sy(p[v])) : g.moveTo(sx(p[u]), sy(p[v])))); g.stroke(); };
      g.lineWidth = 1; g.strokeStyle = 'rgba(138,137,131,0.28)';
      paths.forEach((path, n) => { if (n !== index) stroke(path); });
      const mine = paths[index];
      g.lineWidth = 2; g.strokeStyle = INK; stroke(mine);
      const first = mine[0];
      const last = mine[mine.length - 1];
      g.fillStyle = '#ffffff'; g.lineWidth = 1.6;
      g.beginPath(); g.arc(sx(first[u]), sy(first[v]), 3.6, 0, 2 * Math.PI); g.fill(); g.stroke();
      g.fillStyle = INK; g.beginPath(); g.arc(sx(last[u]), sy(last[v]), 3.4, 0, 2 * Math.PI); g.fill();
      return el('div', { class: 'v4-thumb' }, [el('div', { class: 'v4-thumb-title', html: `<b>${title}</b> (${nu}, ${nv})` }), canvas]);
    });
    return el('section', null, [
      el('h3', { text: 'Its tool path' }),
      el('div', { class: 'v4-thumbs' }, panels),
      el('div', { class: 'cov-legend' }, [
        el('span', { class: 'cov-li' }, [el('i', { class: 'cov-sw line', style: `color:${INK}` }), 'this trajectory']),
        el('span', { class: 'cov-li' }, [el('i', { class: 'cov-sw line', style: 'color:rgba(138,137,131,0.6)' }), `the other ${paths.length - 1}`]),
        el('span', { class: 'cov-li' }, ['○ start · ● end']),
        el('span', { class: 'cov-li' }, [el('i', { class: 'cov-sw cross', style: 'color:#52514e' }), `origin of frame "${tool.frame}"`]),
      ]),
    ]);
  }

  // ── its joints over time (data/samples.json) ──────────────────────────────────────────────────────────────────

  function loadSamples() {
    if (!samplesPromise && global.location.protocol === 'file:') {
      // WHY not even try: Chrome blocks fetch on file:// (and logs it as an error); say so instead
      samplesError = new Error('a page opened from file:// cannot fetch it');
      samplesPromise = Promise.resolve();
    }
    if (!samplesPromise) {
      samplesPromise = fetch('../data/samples.json')
        .then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
        .then((all) => {
          const by = new Map();
          for (const sample of all) { if (!by.has(sample.trajectory)) by.set(sample.trajectory, []); by.get(sample.trajectory).push(sample); }
          samples = by;
        })
        .catch((error) => { samplesError = error; });
    }
    return samplesPromise;
  }

  function overTime(row) {
    const { el } = api;
    const box = el('div', { class: 'v4-overtime' });
    const section = el('section', null, [
      el('h3', { text: 'Its joints over time' }), box,
      el('p', { class: 'v4-note', text: 'Every sample of this trajectory from data/samples.json (100 Hz, not subsampled); each chart on its own y range, labelled at its left. Dashed = zero.' }),
    ]);
    const paint = () => {
      if (current !== row.name) return;
      if (samplesError || !samples) {
        box.replaceChildren(el('p', { class: 'v4-note', text: `data/samples.json could not be loaded (${samplesError ? samplesError.message : 'unknown'}); open the page through the round's server.` }));
        return;
      }
      drawOverTime(box, samples.get(row.name) || []);
    };
    if (samples || samplesError) paint();
    else { box.append(el('p', { class: 'v4-note', text: 'Loading data/samples.json…' })); loadSamples().then(paint); }
    return section;
  }

  function drawOverTime(box, rows) {
    const { el, canvasOf, INK, minus } = api;
    box.replaceChildren();
    if (!rows.length) { box.append(el('p', { class: 'v4-note', text: 'No samples for this trajectory.' })); return; }
    const t = rows.map((sample) => sample.t_s);
    const tMax = t[t.length - 1] || 1;
    const grid = el('div', { class: 'v4-otgrid' }, [el('span'), el('span', { class: 'v4-othead', text: 'position q (°)' }), el('span', { class: 'v4-othead', text: 'speed qd (°/s)' })]);
    const chart = (values) => {
      const width = 116;
      const height = 34;
      const { canvas, g } = canvasOf(width, height);
      let lo = Math.min(...values);
      let hi = Math.max(...values);
      if (!(hi > lo)) { lo -= 1; hi += 1; }
      const sx = (x) => 30 + (x / tMax) * (width - 32);
      const sy = (y) => height - 3 - ((y - lo) / (hi - lo)) * (height - 6);
      g.fillStyle = '#fcfcfb'; g.fillRect(30, 0, width - 30, height);
      if (lo < 0 && hi > 0) { g.strokeStyle = 'rgba(34,33,31,0.3)'; g.setLineDash([2, 3]); g.beginPath(); g.moveTo(30, Math.round(sy(0)) + 0.5); g.lineTo(width, Math.round(sy(0)) + 0.5); g.stroke(); g.setLineDash([]); }
      g.strokeStyle = INK; g.lineWidth = 1.2; g.beginPath();
      values.forEach((v, n) => (n ? g.lineTo(sx(t[n]), sy(v)) : g.moveTo(sx(t[n]), sy(v))));
      g.stroke();
      g.fillStyle = '#8a8983'; g.font = '9.5px -apple-system, "Segoe UI", Roboto, sans-serif'; g.textAlign = 'right';
      g.textBaseline = 'top'; g.fillText(minus(String(Math.round(hi))), 27, 0);
      g.textBaseline = 'bottom'; g.fillText(minus(String(Math.round(lo))), 27, height);
      return canvas;
    };
    for (const joint of api.joints()) {
      const short = joint.name.replace(/_joint$/, '');
      const q = rows.map((sample) => sample[`${short}_q_deg`]);
      const qd = rows.map((sample) => sample[`${short}_qd_deg_s`]);
      if (q.some((v) => v === undefined)) continue;
      grid.append(el('span', { class: 'v4-otname', text: joint.name }), chart(q), chart(qd));
    }
    grid.append(el('span'), el('span', { class: 'v4-otaxis', text: `0 … ${tMax.toFixed(2)} s` }), el('span', { class: 'v4-otaxis', text: `0 … ${tMax.toFixed(2)} s` }));
    box.append(grid);
  }

  global.V4Drawer = { init, open, close, isOpen, setOrder };
})(typeof window !== 'undefined' ? window : globalThis);
