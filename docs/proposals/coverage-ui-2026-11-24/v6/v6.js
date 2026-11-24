/* V6 · "Who goes there" — the coverage figures are the query (coverage-UI babble round 2026-11-24, hand-rolled).
 *
 * Every coloured cell answers "which trajectories made this?" and every empty one "who comes closest?": a click on a
 * q×qd cell, a tool pixel, a direction cell or a histogram bar adds a query chip; chips AND together; the trajectories
 * that satisfy all of them are listed in the dock beside the figures (and filter the full table). It reads only data/:
 * the payload (coverage.js), membership.js (which cells each trajectory visits, on the payload's own grids) and
 * trajectories.js. The cell counts drawn are the payload's; the only numbers this page derives are the subset ones the
 * query asks for (how many trajectories match, and nearest-cell distances), and the page says so where it shows them.
 */
(function () {
  'use strict';

  const DATA = window.COVERAGE_UI || {};
  const P = DATA.coverage;
  const MEM = DATA.membership;
  const TRAJ = DATA.trajectories;
  const Color = window.CoverageColor;

  const STORE = 'coverage-ui-v6.';
  const INK = '#22211f';
  const SOFT = '#52514e';
  const MUTED = '#8a8983';
  const AXIS = '#b9b8b2';
  const SEL = '#0b0b0b';
  const ACCENT = '#2a78d6';
  const INK_RGB = [34, 33, 31];
  const ACCENT_RGB = [42, 120, 214];
  const HOLE = [249, 222, 176];
  const FADE = 0.8;
  const BAR = '#6f8fb8';
  const BAR_FADED = '#dfe4ec';
  const OUT_BG = '#eeede8';
  const JOINT_COLOURS = ['#2a78d6', '#2f9e44', '#8e5bd1', '#17a2b8', '#6b7a8f', '#c22f6e'];
  const NEAR_K = 8;
  const FONT = '10.5px -apple-system, "Segoe UI", Roboto, sans-serif';
  const DEG = 180 / Math.PI;
  const NNBSP = ' ';
  const WORD = { q: 'position', qd: 'speed', qdd: 'acceleration', qddd: 'jerk' };
  const VIEW_NAME = { xy: 'top view', xz: 'front view', yz: 'side view' };
  const VIEW_AXES = { xy: ['x', 'y'], xz: ['x', 'z'], yz: ['y', 'z'] };
  const SEARCH_WORD = { proj: 'nearest-pixel search', plane: 'nearest-cell search', dir: 'nearest-direction search' };

  const $ = (sel, root) => (root || document).querySelector(sel);

  // ── small helpers ────────────────────────────────────────────────────────────────────────────────────────────────
  function load(key, fallback) {
    try { const raw = localStorage.getItem(STORE + key); return raw === null ? fallback : JSON.parse(raw); } catch (e) { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(STORE + key, JSON.stringify(value)); } catch (e) { /* private mode: not remembered */ }
  }
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k === 'html') node.innerHTML = v;
        else if (k === 'style') node.style.cssText = v;
        else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? '' : v);
      }
    }
    if (children !== undefined && children !== null) {
      for (const c of [].concat(children)) {
        if (c === null || c === undefined || c === false) continue;
        node.append(c instanceof Node ? c : document.createTextNode(String(c)));
      }
    }
    return node;
  }
  function esc(text) { return String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function minus(text) { return String(text).replace(/^-/, '−'); }
  function int(v) { return minus(Math.round(v).toLocaleString('en-US').replace(/,/g, NNBSP)); }
  function fixed(v, digits) { const s = (Math.abs(v) < Math.pow(10, -digits) / 2 ? 0 : v).toFixed(digits); return minus(s); }
  function pctText(v) { return (v >= 99.95 ? '100' : v >= 10 ? String(Math.round(v)) : v.toFixed(1).replace(/\.0$/, '')) + NNBSP + '%'; }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
  function short(joint) { return joint.replace(/_joint$/, ''); }
  function fadeRGB(c, f) { return [c[0] + (255 - c[0]) * f, c[1] + (255 - c[1]) * f, c[2] + (255 - c[2]) * f]; }
  function rgb(c) { return `rgb(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])})`; }
  function niceStep(span, target) {
    const raw = span / Math.max(1, target);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const f = raw / mag;
    return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag;
  }
  function niceTicks(lo, hi, target) {
    const step = niceStep(hi - lo, target);
    const out = [];
    for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    return { values: out, step };
  }
  function digitsFor(step) {
    if (step >= 1) return (Math.abs(step - Math.round(step)) < 1e-9 || step >= 10) ? 0 : 1;
    return clamp(Math.ceil(-Math.log10(step) - 1e-9), 1, 3);
  }
  function setupCanvas(canvas, w, h) {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    const g = canvas.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return g;
  }

  // ── the tooltip ──────────────────────────────────────────────────────────────────────────────────────────────────
  const tip = $('#v6-tip');
  function showTip(e, html) {
    tip.innerHTML = html;
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let x = e.clientX + 14;
    let y = e.clientY + 14;
    if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - 14;
    if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - 14;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  function hideTip() { tip.hidden = true; }

  if (!P || !MEM || !TRAJ || !Color) {
    $('#v6-views').textContent = 'The round\'s data/ is missing: run extract.py (see CONTRACT.md).';
    return;
  }

  // ── the data, indexed ────────────────────────────────────────────────────────────────────────────────────────────
  const JOINTS = P.joints.map((j) => j.name);
  const DISPLAY = Object.fromEntries(P.joints.map((j) => [j.name, j.display]));
  const NAMES = TRAJ.map((r) => r.name);
  const ROW = {};
  TRAJ.forEach((r, i) => { ROW[r.name] = r; r._i = i; });
  const [RINGS, SECTORS] = MEM.sphere;

  function unitText(joint, signal) {
    const d = DISPLAY[joint];
    const base = d.unit === 'deg' ? '°' : ' ' + d.unit;
    return base + { q: '', qd: '/s', qdd: '/s²', qddd: '/s³' }[signal];
  }
  // a linear axis of n bins over [lo, hi] (SI), shown as lo*scale .. hi*scale in `unit`
  function linearAxis(lo, hi, n, scale, unit, title) {
    const a = lo * scale;
    const b = hi * scale;
    const step = (b - a) / n;
    return {
      n, lo: a, hi: b, step, unit, title,
      range: (k) => [a + k * step, a + (k + 1) * step],
      ticks: (target) => { const t = niceTicks(a, b, target); return t.values.map((v) => ({ pos: (v - a) / step, label: fixed(v, digitsFor(t.step)) })); },
    };
  }
  function rangeText(axis, k) {
    const [a, b] = axis.range(k);
    const d = digitsFor(axis.step);
    const A = fixed(a, d);
    const B = fixed(b, d);
    return (a < -1e-9 || b < -1e-9) ? `${A} to ${B}${axis.unit}` : `${A}–${B}${axis.unit}`;
  }

  const GRIDS = {};
  for (const joint of JOINTS) {
    for (const key of Object.keys(P.planes[joint])) {
      const pl = P.planes[joint][key];
      const [nx, ny] = pl.shape;
      const s = DISPLAY[joint].scale;
      const g = {
        key: `plane:${joint}:${key}`, kind: 'plane', joint, plane: key, nx, ny, xs: pl.x, ys: pl.y,
        samples: pl.samples, paths: pl.paths, outside: null, block: pl,
        xa: linearAxis(pl.x_edges[0], pl.x_edges[1], nx, s, unitText(joint, pl.x), `${pl.x} · ${WORD[pl.x]} (${unitText(joint, pl.x).trim()})`),
        ya: linearAxis(pl.y_edges[0], pl.y_edges[1], ny, s, unitText(joint, pl.y), `${pl.y} · ${WORD[pl.y]} (${unitText(joint, pl.y).trim()})`),
        index: (x, y) => x * ny + y,
        coords: (c) => [Math.floor(c / ny), c % ny],
      };
      g.label = (c) => { const [x, y] = g.coords(c); return `${short(joint)} ${g.xs} ${rangeText(g.xa, x)}, ${g.ys} ${rangeText(g.ya, y)}`; };
      g.nearText = (c) => `the empty cell ${g.label(c)}`;
      GRIDS[g.key] = g;
    }
  }
  const tool = P.tool;
  for (const view of ['xy', 'xz', 'yz']) {
    const pr = tool.projections[view];
    const [nx, ny] = pr.shape;
    const px = tool.pixel_m;
    const [ua, va] = VIEW_AXES[view];
    const g = {
      key: view, kind: 'proj', view, nx, ny, samples: pr.samples, paths: pr.paths, outside: pr.reachable,
      xa: linearAxis(pr.origin[0], pr.origin[0] + nx * px, nx, 1, ' m', `${ua} (m)`),
      ya: linearAxis(pr.origin[1], pr.origin[1] + ny * px, ny, 1, ' m', `${va} (m)`),
      index: (x, y) => x * ny + y,
      coords: (c) => [Math.floor(c / ny), c % ny],
    };
    g.label = (c) => { const [x, y] = g.coords(c); return `tool at ${ua} ${rangeText(g.xa, x)}, ${va} ${rangeText(g.ya, y)} (${VIEW_NAME[view]})`; };
    g.nearText = (c) => { const [x, y] = g.coords(c); return `the hole at ${ua} ${rangeText(g.xa, x)}, ${va} ${rangeText(g.ya, y)} (${VIEW_NAME[view]})`; };
    GRIDS[view] = g;
  }
  // tool directions: the payload's equal-area sphere, ring = band of base z (tilt from straight down), sector = azimuth
  const tiltEdge = (k) => Math.acos(clamp(1 - 2 * k / RINGS, -1, 1)) * DEG;
  {
    const g = {
      key: 'dir', kind: 'dir', nx: SECTORS, ny: RINGS, samples: tool.orientation.sphere.counts, paths: null, outside: null,
      xa: linearAxis(-Math.PI, Math.PI, SECTORS, DEG, '°', 'azimuth · which way it leans (°)'),
      ya: {
        n: RINGS, title: 'tilt from straight down (°)',
        ticks: () => [0, 2, 4, 6, 8, 10, 12].filter((k) => k <= RINGS).map((k) => ({ pos: k, label: String(Math.round(tiltEdge(k))) })),
      },
      index: (x, y) => y * SECTORS + x,
      coords: (c) => [c % SECTORS, Math.floor(c / SECTORS)],
    };
    g.label = (c) => { const [s, r] = g.coords(c); return `tool pointing tilt ${Math.round(tiltEdge(r))}–${Math.round(tiltEdge(r + 1))}°, azimuth ${rangeText(g.xa, s)}`; };
    g.nearText = (c) => `the unvisited direction ${g.label(c).replace('tool pointing ', '')}`;
    GRIDS.dir = g;
  }

  // membership: CELLS[name][grid] the array, SETS[name][grid] the same as a Set
  const CELLS = {};
  const SETS = {};
  for (const name of NAMES) {
    const m = MEM.trajectories[name];
    const arrays = {};
    for (const joint of JOINTS) for (const key of Object.keys(m.planes[joint])) arrays[`plane:${joint}:${key}`] = m.planes[joint][key];
    arrays.xy = m.xy; arrays.xz = m.xz; arrays.yz = m.yz; arrays.dir = m.directions;
    CELLS[name] = arrays;
    SETS[name] = {};
    for (const k of Object.keys(arrays)) SETS[name][k] = new Set(arrays[k]);
  }

  // ── state ────────────────────────────────────────────────────────────────────────────────────────────────────────
  const pick = (value, allowed, fallback) => (allowed.includes(value) ? value : fallback);
  const state = {
    tab: 'overview',
    joint: clamp(Number(load('joint', 0)) || 0, 0, JOINTS.length - 1),
    plane: 'q_qd',
    cmap: pick(load('cmap', 'viridis'), Color.NAMES, 'viridis'),
    reverse: !!load('reverse', false),
    scale: pick(load('scale', 'linear'), Color.SCALES, 'linear'),
    count: pick(load('count', 'paths'), ['paths', 'samples'], 'paths'),
    chips: [],
    near: null,
    holes: false,
    hover: null,
    drill: null,
    drillList: [],
    table: { text: '', sort: { key: 'idx', dir: 1 }, group: '', filters: {}, folded: new Set(), span: 'q', view: 'all' },
  };

  // ── the query: chips AND together; an empty-cell chip ranks who comes closest ────────────────────────────────────
  let answer = { names: NAMES.slice(), set: new Set(NAMES), dist: null, nearest: null, pool: NAMES.length, active: false, version: 0, unions: {} };

  function dirVector(cell) {
    const [s, r] = GRIDS.dir.coords(cell);
    const z = -1 + (r + 0.5) * 2 / RINGS;
    const az = -Math.PI + (s + 0.5) * 2 * Math.PI / SECTORS;
    const xy = Math.sqrt(Math.max(0, 1 - z * z));
    return [xy * Math.cos(az), xy * Math.sin(az), z];
  }
  // the nearest cell this trajectory visits on grid g, and how far (m on the tool views, cells on a plane, deg on directions)
  function nearestCell(name, g, cell) {
    const cells = CELLS[name][g.key];
    if (!cells.length) return { d: Infinity, cell: null };
    let best = Infinity;
    let at = null;
    if (g.kind === 'dir') {
      const v = dirVector(cell);
      for (const c of cells) {
        const w = dirVector(c);
        const angle = Math.acos(clamp(v[0] * w[0] + v[1] * w[1] + v[2] * w[2], -1, 1));
        if (angle < best) { best = angle; at = c; }
      }
      return { d: best * DEG, cell: at };
    }
    const [x0, y0] = g.coords(cell);
    for (const c of cells) {
      const [x, y] = g.coords(c);
      const d2 = (x - x0) * (x - x0) + (y - y0) * (y - y0);
      if (d2 < best) { best = d2; at = c; }
    }
    const d = Math.sqrt(best);
    return { d: g.kind === 'proj' ? d * tool.pixel_m : d, cell: at };
  }
  function distText(gridKey, d) {
    const g = GRIDS[gridKey];
    if (!Number.isFinite(d)) return '—';
    if (g.kind === 'proj') return `${Math.round(d * 100)}${NNBSP}cm`;
    if (g.kind === 'dir') return `${Math.round(d)}°`;
    return `${d.toFixed(1)} cells`;
  }

  function computeAnswer() {
    let names = NAMES.filter((n) => state.chips.every((c) => c.cells.some((cell) => SETS[n][c.grid].has(cell))));
    const pool = names.length;
    let dist = null;
    let nearest = null;
    if (state.near) {
      const g = GRIDS[state.near.grid];
      dist = {};
      nearest = {};
      for (const n of names) { const r = nearestCell(n, g, state.near.cell); dist[n] = r.d; nearest[n] = r.cell; }
      names = names.filter((n) => Number.isFinite(dist[n])).sort((a, b) => dist[a] - dist[b] || ROW[a]._i - ROW[b]._i).slice(0, NEAR_K);
    }
    answer = { names, set: new Set(names), dist, nearest, pool, active: state.chips.length > 0 || !!state.near, version: answer.version + 1, unions: {} };
  }
  function unionOf(gridKey) {
    if (!answer.unions[gridKey]) {
      const u = new Set();
      for (const n of answer.names) for (const c of CELLS[n][gridKey]) u.add(c);
      answer.unions[gridKey] = u;
    }
    return answer.unions[gridKey];
  }

  let chipSeq = 0;
  function sameCells(a, b) { return a.length === b.length && a.every((v, i) => v === b[i]); }
  function addVisit(grid, cells, label, meta) {
    const i = state.chips.findIndex((c) => c.grid === grid && sameCells(c.cells, cells));
    if (i >= 0) state.chips.splice(i, 1);
    else state.chips.push({ id: ++chipSeq, grid, cells, label, meta: meta || null });
    update();
  }
  function setNear(grid, cell) {
    if (state.near && state.near.grid === grid && state.near.cell === cell) state.near = null;
    else state.near = { grid, cell, label: GRIDS[grid].nearText(cell) };
    update();
  }
  function onCell(g, cell) {
    if (g.outside && !g.outside[cell]) return;
    const visited = (g.paths ? g.paths[cell] : g.samples[cell]) > 0;
    if (visited) addVisit(g.key, [cell], g.label(cell));
    else setNear(g.key, cell);
  }
  function removeChip(id) { state.chips = state.chips.filter((c) => c.id !== id); update(); }
  function clearQuery() { state.chips = []; state.near = null; update(); }

  // ── settings (the gear) ──────────────────────────────────────────────────────────────────────────────────────────
  const SCALE_NOTES = {
    linear: 'Colour grows in proportion to the count; the top 2 % of cells are clipped so one hot cell does not wash out the rest.',
    log: 'Log: thin cells and busy cells both readable.',
    equalized: 'Colour = rank among visited cells: shows where, not how much.',
    visited: 'One colour for every visited cell.',
    enough: `Dark = at least ${P.enough} samples, light = visited but fewer.`,
  };
  function rampCss() {
    const r = Color.ramp(state.cmap, state.reverse);
    const stops = [];
    for (let i = 0; i <= 10; i++) stops.push(`${rgb(r(i / 10))} ${i * 10}%`);
    return `linear-gradient(90deg, ${stops.join(', ')})`;
  }
  function initSettings() {
    const gear = $('#v6-gear');
    const panel = $('#v6-settings');
    const cmap = $('#v6-cmap');
    const reverse = $('#v6-reverse');
    const scale = $('#v6-scale');
    const count = $('#v6-count');
    const sync = () => {
      cmap.value = state.cmap; reverse.checked = state.reverse; scale.value = state.scale; count.value = state.count;
      $('#v6-ramp').style.background = rampCss();
      $('#v6-scale-note').textContent = SCALE_NOTES[state.scale];
    };
    const open = (yes) => { panel.hidden = !yes; gear.setAttribute('aria-expanded', yes ? 'true' : 'false'); if (yes) sync(); };
    gear.addEventListener('click', () => open(panel.hidden));
    $('#v6-settings-close').addEventListener('click', () => open(false));
    document.addEventListener('mousedown', (e) => { if (!panel.hidden && !panel.contains(e.target) && !gear.contains(e.target)) open(false); });
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      if (!panel.hidden) { open(false); return; }
      if (state.drill) closeDrill();
    });
    const changed = () => {
      state.cmap = cmap.value; state.reverse = reverse.checked; state.scale = scale.value; state.count = count.value;
      save('cmap', state.cmap); save('reverse', state.reverse); save('scale', state.scale); save('count', state.count);
      sync();
      repaint();
      if (state.drill) renderDrill();
    };
    for (const c of [cmap, reverse, scale, count]) c.addEventListener('change', changed);
    sync();
  }

  // ── colour bars ──────────────────────────────────────────────────────────────────────────────────────────────────
  function countWord(mode) { return mode === 'paths' ? 'trajectories per cell' : 'samples per cell'; }
  function scaleFor(counts, peers) {
    const opts = { enough: P.enough };
    if (peers && (state.scale === 'linear' || state.scale === 'log')) {
      opts.max = Math.max(1, ...peers.map((c) => Color.scale(c, state.scale, { enough: P.enough }).max));
    }
    return Color.scale(counts, state.scale, opts);
  }
  function vbar(node, scaled, title, height) {
    node.innerHTML = '';
    node.append(el('div', { class: 'v6-cb-title', text: title }));
    const body = el('div', { class: 'v6-cb-body', style: `height:${height}px` });
    const c = el('canvas');
    const g = setupCanvas(c, 10, height);
    const r = Color.ramp(state.cmap, state.reverse);
    for (let y = 0; y < height; y++) { g.fillStyle = rgb(r(1 - y / Math.max(1, height - 1))); g.fillRect(0, y, 10, 1); }
    body.append(c);
    for (const t of scaled.ticks) body.append(el('span', { class: 'v6-cb-tick', style: `bottom:${(t.t * (height - 1)).toFixed(1)}px`, text: t.label }));
    node.append(body);
  }
  function hbar(node, scaled, title, width) {
    node.innerHTML = '';
    const wrap = el('span', { class: 'v6-hbar' });
    wrap.append(el('span', { text: title }));
    const box = el('span', { style: `display:inline-block;width:${width}px` });
    const c = el('canvas');
    const g = setupCanvas(c, width, 9);
    const r = Color.ramp(state.cmap, state.reverse);
    for (let x = 0; x < width; x++) { g.fillStyle = rgb(r(x / Math.max(1, width - 1))); g.fillRect(x, 0, 1, 9); }
    const ticks = el('span', { class: 'ticks', style: `display:block;width:${width}px` });
    for (const t of scaled.ticks) ticks.append(el('span', { style: `left:${(t.t * width).toFixed(1)}px`, text: t.label }));
    box.append(c, ticks);
    wrap.append(box);
    node.append(wrap);
  }

  // ── a clickable heatmap over one grid ────────────────────────────────────────────────────────────────────────────
  // WHY the hit box is one cell wider (right) and taller (top) than the plot: its centre then lands in the MIDDLE of a
  // cell rather than on the corner of four, so a click on "the figure" (the walkthrough's) picks one cell, not a tie.
  function Heat(g, o) {
    this.g = g;
    this.o = Object.assign({ cw: 6, ch: 6, axes: true, interactive: true, colorbar: true, legend: true, holes: false, peers: null, focus: null, samplesOnly: false }, o);
    const { cw, ch } = this.o;
    this.m = this.o.axes ? { l: 46, r: Math.max(8, cw + 2), t: Math.max(6, ch + 2), b: 30 } : { l: 1, r: this.o.interactive ? Math.max(1, cw) : 1, t: this.o.interactive ? Math.max(1, ch) : 1, b: 1 };
    this.root = el('div', { class: 'v6-heat' });
    this.stage = el('div', { class: 'v6-stage' });
    this.canvas = el('canvas', { class: 'v6-canvas' });
    this.stage.append(this.canvas);
    if (this.o.interactive) {
      this.hit = el('div', { class: 'v6-hit', role: 'img', 'aria-label': `${g.key}: click a cell to ask which trajectories made it` });
      this.pins = el('div', { class: 'v6-pins' });
      this.stage.append(this.hit, this.pins);
      this.hit.addEventListener('mousemove', (e) => {
        const cell = this.cellAt(e);
        if (cell === null) { hideTip(); this.hit.style.cursor = 'default'; return; }
        this.hit.style.cursor = (g.outside && !g.outside[cell]) ? 'not-allowed' : 'pointer';
        showTip(e, this.tipHtml(cell));
      });
      this.hit.addEventListener('mouseleave', hideTip);
      this.hit.addEventListener('click', (e) => { const cell = this.cellAt(e); if (cell !== null) { hideTip(); onCell(g, cell); } });
    }
    const row = el('div', { class: 'v6-heatrow' }, [this.stage]);
    if (this.o.colorbar === 'h') this.hcb = el('div', { class: 'v6-hcb' });
    else if (this.o.colorbar) { this.cbar = el('div', { class: 'v6-cbar' }); row.append(this.cbar); }
    this.root.append(row);
    if (this.hcb) this.root.append(this.hcb);
    if (this.o.legend) { this.legend = el('div', { class: 'v6-legend' }); this.root.append(this.legend); }
  }
  Heat.prototype.mode = function () { return this.g.paths && state.count === 'paths' && !this.o.samplesOnly ? 'paths' : 'samples'; };
  Heat.prototype.countsOf = function (g) { return this.mode() === 'paths' && g.paths ? g.paths : g.samples; };
  Heat.prototype.cellAt = function (e) {
    const g = this.g;
    const r = this.hit.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left) / this.o.cw);
    const top = Math.floor((e.clientY - r.top - this.o.ch) / this.o.ch);
    if (x < 0 || x >= g.nx || top < 0 || top >= g.ny) return null;
    return g.index(x, g.ny - 1 - top);
  };
  Heat.prototype.tipHtml = function (cell) {
    const g = this.g;
    if (g.outside && !g.outside[cell]) return `<b>${esc(g.label(cell))}</b><br>outside the reachable set: the tool cannot get here`;
    const paths = g.paths ? g.paths[cell] : null;
    const samples = g.samples[cell];
    const visited = (paths !== null ? paths : samples) > 0;
    const counts = paths !== null ? `${int(paths)} trajector${paths === 1 ? 'y' : 'ies'} · ${int(samples)} samples` : `${int(samples)} samples`;
    if (!visited) return `<b>${esc(g.label(cell))}</b><br>never visited${g.kind === 'proj' ? ' (reachable: a hole)' : ''}<br><span class="act">click: who comes closest? (${SEARCH_WORD[g.kind]})</span>`;
    const inAnswer = answer.active ? ` · ${answer.names.filter((n) => SETS[n][g.key].has(cell)).length} of them in the current answer` : '';
    return `<b>${esc(g.label(cell))}</b><br>${counts}${inAnswer}<br><span class="act">click: which trajectories made it?</span>`;
  };
  Heat.prototype.cellRect = function (cell) {
    const [x, y] = this.g.coords(cell);
    return [this.m.l + x * this.o.cw, this.m.t + (this.g.ny - 1 - y) * this.o.ch, this.o.cw, this.o.ch];
  };
  Heat.prototype.cellCentre = function (cell) { const r = this.cellRect(cell); return [r[0] + r[2] / 2, r[1] + r[3] / 2]; };
  Heat.prototype.draw = function () {
    const g = this.g;
    const o = this.o;
    const { cw, ch } = o;
    const m = this.m;
    const pw = g.nx * cw;
    const ph = g.ny * ch;
    const W = Math.ceil(m.l + pw + m.r);
    const H = Math.ceil(m.t + ph + m.b);
    const ctx = setupCanvas(this.canvas, W, H);
    const mode = this.mode();
    const counts = this.countsOf(g);
    const scaled = scaleFor(counts, o.peers ? o.peers.map((pg) => this.countsOf(pg)) : null);
    this.scaled = scaled;
    const ramp = Color.ramp(state.cmap, state.reverse);
    const focus = o.focus;
    const focusSet = focus ? SETS[focus][g.key] : null;
    const fade = !focus && answer.active ? unionOf(g.key) : null;
    const holes = state.holes && o.holes && g.kind === 'proj';
    const img = new ImageData(g.nx, g.ny);
    for (let x = 0; x < g.nx; x++) {
      for (let y = 0; y < g.ny; y++) {
        const idx = g.index(x, y);
        const p = ((g.ny - 1 - y) * g.nx + x) * 4;
        let c;
        if (g.outside && !g.outside[idx]) c = Color.OUTSIDE;
        else if (focusSet && focusSet.has(idx)) c = (g.paths && g.paths[idx] === 1) ? ACCENT_RGB : INK_RGB;
        else if (scaled.t[idx] < 0) c = holes ? HOLE : Color.EMPTY;
        else {
          c = ramp(scaled.t[idx]);
          if (focus) c = fadeRGB(c, 0.72);
          else if (fade && !fade.has(idx)) c = fadeRGB(c, FADE);
        }
        img.data[p] = c[0]; img.data[p + 1] = c[1]; img.data[p + 2] = c[2]; img.data[p + 3] = 255;
      }
    }
    const off = document.createElement('canvas');
    off.width = g.nx; off.height = g.ny;
    off.getContext('2d').putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, m.l, m.t, pw, ph);

    if (!focus) {
      // the chips' cells on this grid: a black frame (with a white halo so it reads on dark cells)
      for (const chip of state.chips) {
        if (chip.grid !== g.key) continue;
        let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
        for (const c of chip.cells) { const r = this.cellRect(c); x0 = Math.min(x0, r[0]); y0 = Math.min(y0, r[1]); x1 = Math.max(x1, r[0] + r[2]); y1 = Math.max(y1, r[1] + r[3]); }
        const pad = Math.max(1.5, Math.min(3, cw / 3), (10 - Math.min(x1 - x0, y1 - y0)) / 2);
        ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(255,255,255,0.95)'; ctx.strokeRect(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad);
        ctx.lineWidth = 2; ctx.strokeStyle = SEL; ctx.strokeRect(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad);
      }
      // the empty cell asked about: a dashed ring, and a line to the nearest cell of each trajectory in the answer
      if (state.near && state.near.grid === g.key) {
        const [tx, ty] = this.cellCentre(state.near.cell);
        ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(11,11,11,0.65)';
        for (const n of answer.names) {
          const c = answer.nearest && answer.nearest[n];
          if (c === null || c === undefined) continue;
          const [x, y] = this.cellCentre(c);
          ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(x, y); ctx.stroke();
          ctx.fillStyle = SEL; ctx.beginPath(); ctx.arc(x, y, 2.2, 0, 2 * Math.PI); ctx.fill();
        }
        const rad = Math.max(7, cw * 1.6);
        ctx.setLineDash([3, 2]); ctx.lineWidth = 2; ctx.strokeStyle = SEL;
        ctx.beginPath(); ctx.arc(tx, ty, rad, 0, 2 * Math.PI); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = SEL; ctx.beginPath(); ctx.arc(tx, ty, 2, 0, 2 * Math.PI); ctx.fill();
      }
      // the row under the mouse in the dock: its own cells, in ink
      const inked = state.hover || state.drill;
      if (inked) {
        ctx.fillStyle = SEL;
        for (const c of CELLS[inked][g.key]) {
          const r = this.cellRect(c);
          if (cw <= 4) ctx.fillRect(r[0], r[1], r[2], r[3]);
          else { const s = Math.max(3, cw * 0.42); ctx.fillRect(r[0] + (r[2] - s) / 2, r[1] + (r[3] - s) / 2, s, s); }
        }
      }
    }
    ctx.lineWidth = 1; ctx.strokeStyle = AXIS; ctx.strokeRect(m.l - 0.5, m.t - 0.5, pw + 1, ph + 1);
    if (o.axes) drawAxes(ctx, m.l, m.t, pw, ph, g.xa, g.ya);
    if (this.hit) {
      this.hit.style.left = m.l + 'px';
      this.hit.style.top = (m.t - ch) + 'px';
      this.hit.style.width = (pw + cw) + 'px';
      this.hit.style.height = (ph + ch) + 'px';
    }
    if (this.cbar) vbar(this.cbar, scaled, countWord(mode), Math.max(60, Math.min(ph, 220)));
    if (this.hcb) hbar(this.hcb, scaled, countWord(mode), Math.max(80, Math.min(pw - 90, 150)));
    if (this.pins) this.drawPins(holes);
    if (this.legend) this.drawLegend(mode, holes);
  };
  Heat.prototype.drawPins = function (holes) {
    this.pins.innerHTML = '';
    if (!holes) return;
    holePins(this.g).forEach((p, k) => {
      const [x, y] = this.cellCentre(p.cell);
      const b = el('button', {
        class: 'v6-pin' + (state.near && state.near.grid === this.g.key && state.near.cell === p.cell ? ' on' : ''), type: 'button', 'data-pin': `${this.g.key}-${k}`, style: `left:${x}px;top:${y}px`,
        title: `Hole ${k + 1}: the reachable spot farthest from any path, ${Math.round(p.d * 100)} cm (${SEARCH_WORD.proj}). Click: who comes closest?`,
        'aria-label': `hole ${k + 1}, ${Math.round(p.d * 100)} cm from any path`,
        text: String(k + 1),
      });
      b.addEventListener('click', (e) => { e.stopPropagation(); setNear(this.g.key, p.cell); });
      this.pins.append(b);
    });
  };
  Heat.prototype.drawLegend = function (mode, holes) {
    const g = this.g;
    const items = [];
    const li = (sw, text, cls) => items.push(el('span', { class: 'v6-li' + (cls ? ' ' + cls : '') }, [sw, text]));
    const sw = (cls, style, text) => el('span', { class: 'v6-sw ' + cls, style, text });
    if (this.o.focus) {
      li(sw('ink'), 'its cells');
      if (g.paths) li(sw('accent'), 'cells only it visits');
      li(sw('', `background:${rampCss()};opacity:.35;width:30px`), 'the whole dataset, faded');
      this.legend.replaceChildren(...items);
      return;
    }
    li(sw('', `background:${rampCss()};width:30px`), `${countWord(mode)}${g.kind === 'dir' && state.count === 'paths' ? ' (directions: samples; the payload keeps no per-direction trajectory count)' : ''}`);
    if (g.kind === 'proj') {
      li(sw(holes ? 'hole' : 'empty'), holes ? 'hole: reachable, never visited' : 'reachable, never visited');
      li(sw('outside'), 'outside the reachable set');
    } else {
      li(sw('empty'), 'never visited');
    }
    if (state.chips.some((c) => c.grid === g.key)) li(sw('frame'), 'your query cell');
    if (answer.active) li(sw('', `background:${rgb(fadeRGB(Color.ramp(state.cmap, state.reverse)(0.6), FADE))};border:1px solid #dddcd6`), 'faded: no trajectory in the answer visits it');
    if (state.near && state.near.grid === g.key) li(sw('ring'), `the empty cell you asked about; lines to each answer trajectory's nearest ${g.kind === 'proj' ? 'pixel' : 'cell'}`);
    if (holes) li(sw('pin', '', '1'), 'the reachable spots farthest from any path');
    li(sw('dot'), state.drill ? `cells of ${state.drill.replace('workspace-', '')} (open) or the row under your mouse` : 'cells of the row under your mouse in the list', 'muted');
    this.legend.replaceChildren(...items);
  };

  function drawAxes(ctx, x0, y0, pw, ph, xa, ya) {
    ctx.font = FONT;
    ctx.lineWidth = 1;
    ctx.strokeStyle = AXIS;
    ctx.fillStyle = SOFT;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (const t of xa.ticks(Math.max(2, Math.round(pw / 64)))) {
      const x = x0 + t.pos / xa.n * pw;
      if (x < x0 - 0.5 || x > x0 + pw + 0.5) continue;
      ctx.beginPath(); ctx.moveTo(x, y0 + ph); ctx.lineTo(x, y0 + ph + 4); ctx.stroke();
      ctx.fillText(t.label, x, y0 + ph + 5);
    }
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (const t of ya.ticks(Math.max(2, Math.round(ph / 36)))) {
      const y = y0 + ph - t.pos / ya.n * ph;
      if (y < y0 - 0.5 || y > y0 + ph + 0.5) continue;
      ctx.beginPath(); ctx.moveTo(x0 - 4, y); ctx.lineTo(x0, y); ctx.stroke();
      ctx.fillText(t.label, x0 - 6, y);
    }
    ctx.fillStyle = MUTED;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    ctx.fillText(xa.title, x0 + pw, y0 + ph + 18);
    ctx.save();
    ctx.translate(9, y0 + ph / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(ya.title, 0, 0);
    ctx.restore();
  }

  // the reachable-but-never-visited pixels farthest from any visited pixel (a nearest-pixel search on the payload)
  const PIN_CACHE = {};
  function holePins(g) {
    if (PIN_CACHE[g.key]) return PIN_CACHE[g.key];
    const visited = [];
    const holes = [];
    for (let c = 0; c < g.paths.length; c++) {
      if (g.paths[c] > 0) visited.push(g.coords(c));
      else if (g.outside && g.outside[c]) holes.push(c);
    }
    const far = holes.map((c) => {
      const [x, y] = g.coords(c);
      let best = Infinity;
      for (const [vx, vy] of visited) { const d = (vx - x) * (vx - x) + (vy - y) * (vy - y); if (d < best) best = d; }
      return { cell: c, d: Math.sqrt(best) * tool.pixel_m, x, y };
    }).sort((a, b) => b.d - a.d);
    const picked = [];
    for (const h of far) {
      if (picked.every((p) => Math.hypot(p.x - h.x, p.y - h.y) > 14)) picked.push(h);
      if (picked.length === 3) break;
    }
    PIN_CACHE[g.key] = picked;
    return picked;
  }

  // ── the direction disc: the same equal-area cells, seen from above (Lambert azimuthal equal-area) ─────────────────
  function Disc(o) {
    this.o = Object.assign({ size: 300, legend: true, interactive: true, focus: null, colorbar: false }, o);
    this.g = GRIDS.dir;
    this.root = el('div', { class: 'v6-heat' });
    this.canvas = el('canvas', { class: 'v6-canvas' });
    this.stage = el('div', { class: 'v6-stage' }, [this.canvas]);
    const row = el('div', { class: 'v6-heatrow' }, [this.stage]);
    if (this.o.colorbar) { this.cbar = el('div', { class: 'v6-cbar' }); row.append(this.cbar); }
    this.root.append(row);
    if (this.o.legend) { this.legend = el('div', { class: 'v6-legend' }); this.root.append(this.legend); }
    if (this.o.interactive) {
      this.canvas.style.cursor = 'pointer';
      this.canvas.addEventListener('mousemove', (e) => {
        const cell = this.cellAt(e);
        if (cell === null) { hideTip(); return; }
        showTip(e, Heat.prototype.tipHtml.call({ g: this.g }, cell));
      });
      this.canvas.addEventListener('mouseleave', hideTip);
      this.canvas.addEventListener('click', (e) => { const cell = this.cellAt(e); if (cell !== null) { hideTip(); onCell(this.g, cell); } });
    }
  }
  Disc.prototype.geom = function () { const S = this.o.size; return { S, cx: S / 2, cy: S / 2, R: S / 2 - 20 }; };
  Disc.prototype.cellAt = function (e) {
    const { cx, cy, R } = this.geom();
    const r = this.canvas.getBoundingClientRect();
    const dx = e.clientX - r.left - cx;
    const dy = e.clientY - r.top - cy;
    const ru = Math.hypot(dx, dy) / R;
    if (ru > 1) return null;
    const ring = Math.min(RINGS - 1, Math.floor(ru * ru * RINGS));
    const az = Math.atan2(-dy, dx);
    const sector = Math.min(SECTORS - 1, Math.floor((az + Math.PI) / (2 * Math.PI) * SECTORS));
    return this.g.index(sector, ring);
  };
  Disc.prototype.path = function (ctx, cell) {
    const { cx, cy, R } = this.geom();
    const [s, r] = this.g.coords(cell);
    const r0 = R * Math.sqrt(r / RINGS);
    const r1 = R * Math.sqrt((r + 1) / RINGS);
    const a0 = -Math.PI + s * 2 * Math.PI / SECTORS;
    const a1 = a0 + 2 * Math.PI / SECTORS;
    ctx.beginPath();
    ctx.arc(cx, cy, r1, -a0, -a1, true);
    ctx.arc(cx, cy, r0, -a1, -a0, false);
    ctx.closePath();
  };
  Disc.prototype.centre = function (cell) {
    const { cx, cy, R } = this.geom();
    const [s, r] = this.g.coords(cell);
    const rr = R * Math.sqrt((r + 0.5) / RINGS);
    const a = -Math.PI + (s + 0.5) * 2 * Math.PI / SECTORS;
    return [cx + rr * Math.cos(a), cy - rr * Math.sin(a)];
  };
  Disc.prototype.draw = function () {
    const g = this.g;
    const { S, cx, cy, R } = this.geom();
    const ctx = setupCanvas(this.canvas, S, S);
    const scaled = Color.scale(g.samples, state.scale, { enough: P.enough });
    const ramp = Color.ramp(state.cmap, state.reverse);
    const focus = this.o.focus;
    const focusSet = focus ? SETS[focus].dir : null;
    const fade = !focus && answer.active ? unionOf('dir') : null;
    for (let c = 0; c < RINGS * SECTORS; c++) {
      let col;
      if (focusSet && focusSet.has(c)) col = INK_RGB;
      else if (scaled.t[c] < 0) col = Color.EMPTY;
      else {
        col = ramp(scaled.t[c]);
        if (focus) col = fadeRGB(col, 0.72);
        else if (fade && !fade.has(c)) col = fadeRGB(col, FADE);
      }
      this.path(ctx, c);
      ctx.fillStyle = rgb(col);
      ctx.fill();
      ctx.lineWidth = 0.5; ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.stroke();
    }
    ctx.lineWidth = 1; ctx.strokeStyle = AXIS;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, 2 * Math.PI); ctx.stroke();
    // tilt guides: equal-area radius R·sin(tilt / 2)
    ctx.font = FONT;
    ctx.setLineDash([2, 3]); ctx.strokeStyle = 'rgba(34,33,31,0.45)';
    for (const t of [45, 90, 135]) {
      const rr = R * Math.sin(t / 2 / DEG);
      ctx.beginPath(); ctx.arc(cx, cy, rr, 0, 2 * Math.PI); ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.fillStyle = INK; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    for (const t of [45, 90, 135]) {
      const rr = R * Math.sin(t / 2 / DEG);
      const x = cx + rr * Math.cos(Math.PI / 4);
      const y = cy + rr * Math.sin(Math.PI / 4);
      ctx.fillStyle = 'rgba(252,252,251,0.85)'; ctx.fillRect(x - 1, y - 6, 30, 12);
      ctx.fillStyle = INK; ctx.fillText(`${t}°`, x + 1, y);
    }
    ctx.fillStyle = SOFT; ctx.textAlign = 'center';
    ctx.fillText('+x', cx + R + 11, cy); ctx.fillText('−x', cx - R - 11, cy);
    ctx.fillText('+y', cx, cy - R - 10); ctx.fillText('−y', cx, cy + R + 10);
    if (!focus) {
      for (const chip of state.chips) {
        if (chip.grid !== 'dir') continue;
        for (const c of chip.cells) {
          this.path(ctx, c);
          ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(255,255,255,0.95)'; ctx.stroke();
          ctx.lineWidth = 2; ctx.strokeStyle = SEL; ctx.stroke();
        }
      }
      if (state.near && state.near.grid === 'dir') {
        const [tx, ty] = this.centre(state.near.cell);
        ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(11,11,11,0.65)';
        for (const n of answer.names) {
          const c = answer.nearest && answer.nearest[n];
          if (c === null || c === undefined) continue;
          const [x, y] = this.centre(c);
          ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(x, y); ctx.stroke();
          ctx.fillStyle = SEL; ctx.beginPath(); ctx.arc(x, y, 2.2, 0, 2 * Math.PI); ctx.fill();
        }
        ctx.setLineDash([3, 2]); ctx.lineWidth = 2; ctx.strokeStyle = SEL;
        ctx.beginPath(); ctx.arc(tx, ty, 8, 0, 2 * Math.PI); ctx.stroke(); ctx.setLineDash([]);
      }
      const inked = state.hover || state.drill;
      if (inked) {
        ctx.fillStyle = SEL;
        for (const c of CELLS[inked].dir) { const [x, y] = this.centre(c); ctx.beginPath(); ctx.arc(x, y, 2.6, 0, 2 * Math.PI); ctx.fill(); }
      }
    }
    if (this.cbar) vbar(this.cbar, scaled, 'samples per cell', Math.min(200, S - 40));
    if (this.legend) {
      const items = [];
      const li = (swEl, text, cls) => items.push(el('span', { class: 'v6-li' + (cls ? ' ' + cls : '') }, [swEl, text]));
      const sw = (cls, style) => el('span', { class: 'v6-sw ' + cls, style });
      if (focus) {
        li(sw('ink'), 'its directions'); li(sw('', `background:${rampCss()};opacity:.35;width:30px`), 'the whole dataset, faded');
      } else {
        li(sw('', `background:${rampCss()};width:30px`), 'samples per cell');
        li(sw('empty'), 'never pointed there');
        li(sw('dashline', 'color:#555'), 'tilt 45° / 90° / 135° from straight down');
        if (state.chips.some((c) => c.grid === 'dir')) li(sw('frame'), 'your query cell');
        if (answer.active) li(sw('', `background:${rgb(fadeRGB(Color.ramp(state.cmap, state.reverse)(0.6), FADE))};border:1px solid #dddcd6`), 'faded: no trajectory in the answer points there');
        if (state.near && state.near.grid === 'dir') li(sw('ring'), 'the empty direction you asked about');
        li(sw('dot'), state.drill ? `directions of ${state.drill.replace('workspace-', '')} (open) or the row under your mouse` : 'directions of the row under your mouse', 'muted');
      }
      this.legend.replaceChildren(...items);
    }
  };

  // ── a joint histogram (samples per bin, the payload's) whose bars ask about the q×qd / qd×qdd grid's band ───────
  function Hist(joint, signal, o) {
    this.joint = joint; this.signal = signal;
    this.o = Object.assign({ w: 220, h: 60, compact: true, stats: false }, o);
    this.h = P.hist[joint][signal];
    this.limit = P.limits[joint][signal];
    this.scale = DISPLAY[joint].scale;
    const map = { q: ['q_qd', 'x'], qd: ['q_qd', 'y'], qdd: ['qd_qdd', 'y'] }[signal];
    this.grid = map ? GRIDS[`plane:${joint}:${map[0]}`] : null;
    this.axis = map ? map[1] : null;
    const [lo, hi, n] = this.h.edges;
    this.barK = new Int32Array(n).fill(-1);
    if (this.grid) {
      const ax = this.axis === 'x' ? this.grid.xa : this.grid.ya;
      for (let b = 0; b < n; b++) {
        const v = (lo + (b + 0.5) * (hi - lo) / n) * this.scale;
        const k = Math.floor((v - ax.lo) / ax.step);
        if (k >= 0 && k < ax.n) this.barK[b] = k;
      }
    }
    this.root = el('div', { class: 'v6-hist' });
    this.canvas = el('canvas', { 'data-hist': `${joint}:${signal}` });
    this.root.append(this.canvas);
    if (this.o.stats) { this.stat = el('div', { class: 'v6-hstat' }); this.root.append(this.stat); }
    this.canvas.addEventListener('mousemove', (e) => { const b = this.barAt(e); if (b === null) { hideTip(); return; } showTip(e, this.tipHtml(b)); });
    this.canvas.addEventListener('mouseleave', hideTip);
    this.canvas.addEventListener('click', (e) => {
      const b = this.barAt(e);
      if (b === null || this.barK[b] < 0) return;
      hideTip();
      const k = this.barK[b];
      addVisit(this.grid.key, this.cellsOfK(k), this.label(k), { axis: this.axis, k });
    });
  }
  Hist.prototype.ax = function () { return this.axis === 'x' ? this.grid.xa : this.grid.ya; };
  Hist.prototype.cellsOfK = function (k) {
    const g = this.grid;
    const out = [];
    if (this.axis === 'x') for (let y = 0; y < g.ny; y++) out.push(g.index(k, y));
    else for (let x = 0; x < g.nx; x++) out.push(g.index(x, k));
    return out;
  };
  Hist.prototype.label = function (k) {
    const other = this.axis === 'x' ? this.grid.ys : this.grid.xs;
    return `${short(this.joint)} ${this.signal} ${rangeText(this.ax(), k)} (any ${WORD[other]})`;
  };
  Hist.prototype.box = function () {
    const { w, h, compact } = this.o;
    const m = compact ? { l: 2, r: 2, t: 3, b: 12 } : { l: 4, r: 4, t: 4, b: 15 };
    return { m, pw: w - m.l - m.r, ph: h - m.t - m.b };
  };
  Hist.prototype.barAt = function (e) {
    const { m, pw } = this.box();
    const r = this.canvas.getBoundingClientRect();
    const n = this.h.edges[2];
    const b = Math.floor((e.clientX - r.left - m.l) / pw * n);
    return b >= 0 && b < n ? b : null;
  };
  Hist.prototype.tipHtml = function (b) {
    const [lo, hi, n] = this.h.edges;
    const a = (lo + b * (hi - lo) / n) * this.scale;
    const c = (lo + (b + 1) * (hi - lo) / n) * this.scale;
    const unit = unitText(this.joint, this.signal);
    const d = digitsFor(c - a);
    const head = `<b>${short(this.joint)} ${this.signal} ${fixed(a, d)} to ${fixed(c, d)}${unit}</b><br>${int(this.h.counts[b])} samples`;
    if (!this.grid) return `${head}<br>jerk has no membership grid: not clickable`;
    const k = this.barK[b];
    if (k < 0) return `${head}<br>beyond the limit: no grid cell to ask about`;
    return `${head}<br><span class="act">click: who visits ${esc(rangeText(this.ax(), k))} (the ${this.grid.plane.replace('_', '×')} grid's ${this.axis === 'x' ? 'column' : 'row'})?</span>`;
  };
  Hist.prototype.draw = function () {
    const { w, h, compact } = this.o;
    const { m, pw, ph } = this.box();
    const ctx = setupCanvas(this.canvas, w, h);
    const [lo, hi, n] = this.h.edges;
    const a = lo * this.scale;
    const b = hi * this.scale;
    const X = (v) => m.l + (v - a) / (b - a) * pw;
    const lim = this.limit;
    const L0 = lim.low * this.scale;
    const L1 = lim.high * this.scale;
    ctx.fillStyle = OUT_BG; ctx.fillRect(m.l, m.t, pw, ph);
    ctx.fillStyle = '#ffffff'; ctx.fillRect(X(L0), m.t, X(L1) - X(L0), ph);
    // bar heights: the gear's scale (log stays log; the others are linear, clipped at p98 like the heatmaps)
    const counts = this.h.counts;
    const nonzero = counts.filter((c) => c > 0).sort((x, y) => x - y);
    const top = nonzero.length ? nonzero[nonzero.length - 1] : 1;
    const logMode = state.scale === 'log';
    const cap = logMode ? top : Math.max(1, Color.quantile(nonzero, 0.98));
    const height = (c) => (c <= 0 ? 0 : logMode ? Math.log1p(c) / Math.log1p(top) : Math.min(1, c / cap));
    const union = this.grid && answer.active ? unionOf(this.grid.key) : null;
    const kSet = union ? new Set([...union].map((c) => { const [x, y] = this.grid.coords(c); return this.axis === 'x' ? x : y; })) : null;
    const inked = state.hover || state.drill;
    const hoverK = this.grid && inked ? new Set(CELLS[inked][this.grid.key].map((c) => { const [x, y] = this.grid.coords(c); return this.axis === 'x' ? x : y; })) : null;
    const bw = pw / n;
    for (let i = 0; i < n; i++) {
      const hh = height(counts[i]) * ph;
      if (hh <= 0) continue;
      const k = this.barK[i];
      ctx.fillStyle = kSet && !(k >= 0 && kSet.has(k)) ? BAR_FADED : BAR;
      ctx.fillRect(m.l + i * bw, m.t + ph - hh, Math.max(1, bw - 0.3), hh);
      if (!logMode && counts[i] > cap) { ctx.fillStyle = INK; ctx.fillRect(m.l + i * bw, m.t, Math.max(1, bw - 0.3), 2); }
    }
    if (hoverK) {
      ctx.fillStyle = SEL;
      for (let i = 0; i < n; i++) if (this.barK[i] >= 0 && hoverK.has(this.barK[i])) ctx.fillRect(m.l + i * bw, m.t + ph + 1, Math.max(1, bw), 3);
    }
    // chip bands: the grid band a click asked about
    if (this.grid) {
      const ax = this.ax();
      for (const chip of state.chips) {
        if (chip.grid !== this.grid.key) continue;
        // a bar chip constrains one axis only (a q column says nothing about qd); a cell chip marks its band on both
        let ks;
        if (chip.meta) { if (chip.meta.axis !== this.axis) continue; ks = [chip.meta.k]; }
        else ks = [...new Set(chip.cells.map((c) => { const [x, y] = this.grid.coords(c); return this.axis === 'x' ? x : y; }))];
        for (const k of ks) {
          const [r0, r1] = ax.range(k);
          const x0 = X(r0); const x1 = X(r1);
          ctx.fillStyle = 'rgba(11,11,11,0.08)'; ctx.fillRect(x0, m.t, x1 - x0, ph);
          ctx.lineWidth = 1.5; ctx.strokeStyle = SEL; ctx.strokeRect(x0, m.t + 0.75, x1 - x0, ph - 1.5);
        }
      }
    }
    // the limits
    ctx.strokeStyle = Color.LIMIT; ctx.lineWidth = 1.5;
    for (const v of [L0, L1]) { ctx.beginPath(); ctx.moveTo(X(v), m.t); ctx.lineTo(X(v), m.t + ph); ctx.stroke(); }
    ctx.strokeStyle = AXIS; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(m.l, m.t + ph + 0.5); ctx.lineTo(m.l + pw, m.t + ph + 0.5); ctx.stroke();
    ctx.font = FONT; ctx.fillStyle = MUTED; ctx.textBaseline = 'top';
    const unit = unitText(this.joint, this.signal);
    ctx.textAlign = 'left'; ctx.fillText(fixed(L0, 0) + unit, X(L0) + 2, m.t + ph + 2);
    ctx.textAlign = 'right'; ctx.fillText(fixed(L1, 0) + unit, X(L1) - 2, m.t + ph + 2);
    if (!compact) {
      ctx.textAlign = 'center'; ctx.fillStyle = SOFT;
      ctx.fillText('0', X(0), m.t + ph + 2);
    }
    if (this.stat) {
      const hs = this.h;
      const out = hs.outside ? ` · ${int(hs.outside)} past the limit` : '';
      this.stat.textContent = `${this.signal === 'q' ? 'span' : 'peak'} ${pctText(this.signal === 'q' ? hs.span_pct : hs.peak_pct)} of the limit${out}`;
    }
  };

  // ── a small line chart (the drill's q / qd over time) ────────────────────────────────────────────────────────────
  function lineChart(canvas, series, w, h, yTitle) {
    const ctx = setupCanvas(canvas, w, h);
    const m = { l: 46, r: 8, t: 6, b: 26 };
    const pw = w - m.l - m.r;
    const ph = h - m.t - m.b;
    let x0 = Infinity; let x1 = -Infinity; let y0 = Infinity; let y1 = -Infinity;
    for (const s of series) for (let i = 0; i < s.xs.length; i++) { x0 = Math.min(x0, s.xs[i]); x1 = Math.max(x1, s.xs[i]); y0 = Math.min(y0, s.ys[i]); y1 = Math.max(y1, s.ys[i]); }
    if (!(x1 > x0)) x1 = x0 + 1;
    if (!(y1 > y0)) { y0 -= 1; y1 += 1; }
    const pad = (y1 - y0) * 0.06; y0 -= pad; y1 += pad;
    const X = (v) => m.l + (v - x0) / (x1 - x0) * pw;
    const Y = (v) => m.t + ph - (v - y0) / (y1 - y0) * ph;
    ctx.font = FONT; ctx.strokeStyle = '#efeee9'; ctx.fillStyle = SOFT; ctx.lineWidth = 1;
    const yt = niceTicks(y0, y1, 4);
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const v of yt.values) { const y = Y(v); ctx.beginPath(); ctx.moveTo(m.l, y); ctx.lineTo(m.l + pw, y); ctx.stroke(); if (y < m.t + ph - 7) ctx.fillText(fixed(v, digitsFor(yt.step)), m.l - 5, y); }
    const xt = niceTicks(x0, x1, 6);
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (const v of xt.values) { const x = X(v); ctx.fillText(fixed(v, digitsFor(xt.step)), x, m.t + ph + 4); }
    ctx.strokeStyle = AXIS; ctx.strokeRect(m.l - 0.5, m.t - 0.5, pw + 1, ph + 1);
    ctx.fillStyle = MUTED; ctx.textAlign = 'right'; ctx.fillText('t (s)', m.l + pw, m.t + ph + 15);
    ctx.save(); ctx.translate(9, m.t + ph / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(yTitle, 0, 0); ctx.restore();
    ctx.lineWidth = 1.4;
    for (const s of series) {
      ctx.strokeStyle = s.colour; ctx.beginPath();
      for (let i = 0; i < s.xs.length; i++) { const x = X(s.xs[i]); const y = Y(s.ys[i]); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); }
      ctx.stroke();
    }
  }

  // ── tabs ─────────────────────────────────────────────────────────────────────────────────────────────────────────
  const TABS = [
    ['overview', 'Overview'], ['limits', 'Limits'], ['joint', 'One joint'], ['joints', 'All joints'],
    ['cartesian', 'Tool position'], ['orientation', 'Tool orientation'], ['trajectories', 'Trajectories'],
  ];
  const VIEWS = {};
  const FIGS = {};
  const BUILT = {};
  function card(title, lead, children) {
    return el('div', { class: 'v6-card' }, [el('h3', { text: title }), lead ? el('p', { class: 'v6-lead', html: lead }) : null].concat(children || []));
  }
  function viewWidth() { return Math.max(600, $('#v6-views').clientWidth); }

  function buildTabs() {
    const nav = $('#v6-tabs');
    for (const [id, label] of TABS) {
      nav.append(el('button', { class: 'v6-tab', type: 'button', role: 'tab', 'data-tab': id, 'aria-selected': 'false', text: label, onclick: () => showTab(id) }));
      const section = el('section', { class: 'v6-view', 'data-view': id, hidden: true });
      VIEWS[id] = section;
      $('#v6-views').append(section);
    }
  }
  function showTab(id) {
    state.tab = id;
    for (const b of document.querySelectorAll('.v6-tab')) b.setAttribute('aria-selected', b.dataset.tab === id ? 'true' : 'false');
    for (const [k, v] of Object.entries(VIEWS)) v.hidden = k !== id;
    $('#v6-main').classList.toggle('wide', id === 'trajectories');
    hideTip();
    if (!BUILT[id]) { BUILT[id] = true; BUILDERS[id](VIEWS[id]); }
    if (id === 'trajectories') renderTable();
    repaint();
    fitDock();
  }
  function repaint() { for (const f of FIGS[state.tab] || []) f.draw(); }
  let hoverFrame = 0;
  function setHover(name) {
    if (state.hover === name) return;
    state.hover = name;
    cancelAnimationFrame(hoverFrame);
    hoverFrame = requestAnimationFrame(repaint);
  }

  // Overview: the calm answer, the headline numbers (only here), and the dataset at a glance, every figure clickable
  function numberText(row) {
    const v = row.value;
    if (row.key === 'duration_s') return v >= 90 ? `${(v / 60).toFixed(1)} min` : `${v.toFixed(1)} s`;
    if (row.unit === '%') return pctText(v);
    if (row.unit === 'deg') return `${Math.round(v)}°`;
    if (row.unit === 'm/s') return `${v.toFixed(2)} m/s`;
    if (row.unit === 's') return `${v.toFixed(1)} s`;
    return int(v);
  }
  function answerSentence() {
    const by = Object.fromEntries(P.numbers.map((r) => [r.key, r.value]));
    const least = JOINTS.slice().sort((x, y) => P.hist[x].q.span_pct - P.hist[y].q.span_pct)[0];
    const parts = [
      `<b>${int(by.trajectories)} trajectories</b>, ${(by.duration_s / 60).toFixed(1)} min of motion.`,
      `The joints use a median <b>${pctText(by.q_span_median_pct)}</b> of their position range (least: ${short(least)}, <b>${pctText(P.hist[least].q.span_pct)}</b>)`,
      `and on average <b>${pctText(by.q_qd_visited_mean_pct)}</b> of a joint's position × speed cells.`,
    ];
    if (by.tool_voxels_visited !== undefined) parts.push(`The tool passes through <b>${int(by.tool_voxels_visited)}</b> 5 cm voxels${by.tool_voxels_reachable_pct !== undefined ? ` (<b>${pctText(by.tool_voxels_reachable_pct)}</b> of the reachable ones)` : ''} and points in <b>${pctText(by.tool_directions_visited_pct)}</b> of all directions.`);
    return parts.join(' ');
  }
  function histLegend() {
    const li = (style, cls, text) => el('span', { class: 'v6-li' + (cls === 'muted' ? ' muted' : '') }, [el('span', { class: 'v6-sw' + (cls && cls !== 'muted' ? ' ' + cls : ''), style }), text]);
    return el('div', { class: 'v6-legend' }, [
      li(`background:${BAR}`, '', 'samples per bin'),
      li(`color:${Color.LIMIT}`, 'line', 'the limit'),
      li(`background:${OUT_BG};border:1px solid #dddcd6`, '', 'past the limit'),
      li(`background:${BAR_FADED}`, '', 'faded: no trajectory in the answer goes there'),
      li('', 'frame', 'the band (or cell) you asked about'),
      li('background:#22211f;height:3px', '', 'dark cap: taller than the scale (the rest pose)'),
      li('background:#0b0b0b;height:3px', 'muted', 'under the axis: bands of the row under your mouse'),
    ]);
  }
  function buildOverview(view) {
    view.append(el('p', { class: 'v6-answer', html: answerSentence() }));
    const nums = el('div', { id: 'v6-numbers', class: 'v6-numbers' });
    for (const row of P.numbers) nums.append(el('div', { class: 'v6-num', title: `${row.label} (${row.key})` }, [el('span', { class: 'label', text: row.label }), el('span', { class: 'value', text: numberText(row) })]));
    view.append(nums);
    // three cards in one row: every joint (bars), the tool from above, the tool's directions; all clickable
    const W = viewWidth();
    const xyCell = 1.7;
    const xyW = Math.ceil(46 + 114 * xyCell + xyCell + 2) + 26;
    const discSize = 224;
    const discW = discSize + 26;
    const ridgeW = W - xyW - discW - 24;
    const figs = [];
    const ridge = el('div', { class: 'v6-ridge' });
    ridge.append(el('span'));
    for (const s of ['q', 'qd', 'qdd']) ridge.append(el('span', { class: 'head', text: `${s} · ${WORD[s]}` }));
    const histW = Math.floor((ridgeW - 26 - 84 - 2 * 8) / 3);
    for (const joint of JOINTS) {
      ridge.append(el('span', { class: 'jname', text: short(joint) }));
      for (const s of ['q', 'qd', 'qdd']) { const hs = new Hist(joint, s, { w: histW, h: 52 }); figs.push(hs); ridge.append(hs.root); }
    }
    const ridgeCard = card('Does every joint use its range?', 'Samples per bin against the limit. <b>Click a bar</b>: who visits that band.', [ridge, histLegend()]);
    ridgeCard.style.flex = `0 0 ${ridgeW}px`;
    ridgeCard.id = 'v6-ov-ridge';
    const xy = new Heat(GRIDS.xy, { cw: xyCell, ch: xyCell, holes: true, colorbar: 'h' });
    figs.push(xy);
    const disc = new Disc({ size: discSize });
    figs.push(disc);
    const cxy = card('Where does the tool go?', 'From above, 2 cm pixels. <b>Click one</b>: who passed it.', [xy.root]);
    cxy.style.flex = `0 0 ${xyW}px`;
    cxy.id = 'v6-ov-xy';
    const cdisc = card('Which way does it point?', 'Equal-area cells; centre = straight down. <b>Click one</b>.', [disc.root]);
    cdisc.style.flex = `0 0 ${discW}px`;
    cdisc.id = 'v6-ov-disc';
    view.append(el('div', { class: 'v6-row', id: 'v6-overview-figs' }, [ridgeCard, cxy, cdisc]));
    FIGS.overview = figs;
  }

  function buildLimits(view) {
    view.append(el('div', { class: 'v6-toolbar' }, [el('span', { class: 'v6-intro', html: 'Every joint\'s position, speed, acceleration and jerk against its limit (red). <b>Click a bar</b> (q, qd, qdd) to ask who visits that band; jerk has no membership grid.' })]));
    const W = viewWidth() - 26;
    const grid = el('div', { class: 'v6-limits' });
    grid.append(el('span'));
    for (const s of ['q', 'qd', 'qdd', 'qddd']) grid.append(el('span', { class: 'head', text: `${s} · ${WORD[s]} (${unitText(JOINTS[0], s).trim()})` }));
    const figs = [];
    const w = Math.floor((W - 96 - 48) / 4);
    for (const joint of JOINTS) {
      grid.append(el('span', { class: 'jname', text: short(joint) }));
      for (const s of ['q', 'qd', 'qdd', 'qddd']) { const hs = new Hist(joint, s, { w, h: 66, compact: false, stats: true }); figs.push(hs); grid.append(hs.root); }
    }
    view.append(card('How much of its limits does each joint use?', null, [grid, histLegend()]));
    FIGS.limits = figs;
  }

  function buildJoint(view) {
    view.replaceChildren();
    const joint = JOINTS[state.joint];
    const picker = el('div', { class: 'v6-seg', id: 'v6-joint-picker', role: 'group', 'aria-label': 'Joint' });
    JOINTS.forEach((j, i) => picker.append(el('button', { type: 'button', 'data-joint': String(i), 'aria-pressed': i === state.joint ? 'true' : 'false', text: short(j),
      onclick: () => { state.joint = i; save('joint', i); buildJoint(view); repaint(); } })));
    view.append(el('div', { class: 'v6-toolbar' }, [el('span', { class: 'v6-seg-label', text: 'Joint' }), picker,
      el('span', { class: 'v6-intro', html: '<b>Click a cell</b>: which trajectories made it. An empty cell: who comes closest.' })]));
    const W = viewWidth();
    const qqd = GRIDS[`plane:${joint}:q_qd`];
    const qdd = GRIDS[`plane:${joint}:qd_qdd`];
    const extras = 2 * (46 + 14 + 6 + 74 + 26) + 12;
    const cell = clamp(Math.floor((W - extras) / (qqd.nx + qdd.nx + 2)), 5, 14);
    const a = new Heat(qqd, { cw: cell, ch: cell });
    const b = new Heat(qdd, { cw: cell, ch: cell });
    const lead = (g) => `<b>${pctText(g.block.visited_pct)}</b> of ${int(g.nx * g.ny)} cells visited · ${pctText(g.block.sufficient_pct)} with ≥ ${P.enough} samples · evenness ${pctText(g.block.evenness_pct)}`;
    const ca = card(`Which positions and speeds does ${short(joint)} visit?`, lead(qqd), [a.root]);
    ca.id = 'v6-fig-qqd';
    const cb = card(`Which speeds and accelerations does it combine?`, lead(qdd), [b.root]);
    cb.id = 'v6-fig-qdqdd';
    view.append(el('div', { class: 'v6-row', style: 'margin-bottom:12px' }, [ca, cb]));
    const hw = Math.floor((W - 26 - 3 * 12) / 4);
    const hists = ['q', 'qd', 'qdd', 'qddd'].map((s) => new Hist(joint, s, { w: hw, h: 62, compact: false, stats: true }));
    view.append(card(`${short(joint)} against its limits`, 'Samples per bin; red = the limit. <b>Click a bar</b> (q, qd, qdd): who visits that band.',
      [el('div', { class: 'v6-row' }, hists.map((hs) => el('div', null, [el('div', { class: 'v6-mini-title', html: `<b>${hs.signal}</b> <span>${WORD[hs.signal]} (${unitText(joint, hs.signal).trim()})</span>` }), hs.root]))), histLegend()]));
    FIGS.joint = [a, b, ...hists];
  }

  function buildJoints(view) {
    view.replaceChildren();
    const seg = el('div', { class: 'v6-seg', role: 'group', 'aria-label': 'Plane' });
    for (const [k, label] of [['q_qd', 'position × speed'], ['qd_qdd', 'speed × acceleration']]) {
      seg.append(el('button', { type: 'button', 'aria-pressed': state.plane === k ? 'true' : 'false', text: label, onclick: () => { state.plane = k; buildJoints(view); repaint(); } }));
    }
    const bar = el('span', { class: 'v6-cbslot' });
    view.append(el('div', { class: 'v6-toolbar' }, [el('span', { class: 'v6-seg-label', text: 'Plane' }), seg,
      el('span', { class: 'v6-intro', html: 'Every joint at once, one colour scale. <b>Click a cell</b>: who made it.' }), bar]));
    const W = viewWidth();
    const grids = JOINTS.map((j) => GRIDS[`plane:${j}:${state.plane}`]);
    const colW = Math.floor((W - 2 * 10) / 3) - 26;
    const nx = grids[0].nx;
    const cell = clamp(Math.floor((colW - 46 - 12) / (nx + 1)), 4, 10);
    const figs = [];
    const wrap = el('div', { class: 'v6-grid3' });
    grids.forEach((g, i) => {
      const f = new Heat(g, { cw: cell, ch: cell, colorbar: false, legend: false, peers: grids });
      figs.push(f);
      wrap.append(el('div', { class: 'v6-card' }, [el('div', { class: 'v6-mini-title', html: `<b>${short(JOINTS[i])}</b> <span>· ${pctText(g.block.visited_pct)} of cells visited</span>` }), f.root]));
    });
    const legendHost = el('div', { class: 'v6-legend' });
    view.append(wrap, legendHost);
    const first = figs[0];
    const drawAll = { draw: () => {
      first.legend = legendHost;
      first.drawLegend(first.mode(), false);
      first.legend = null;
      hbar(bar, first.scaled || scaleFor(first.countsOf(first.g), grids.map((g) => first.countsOf(g))), countWord(first.mode()), 160);
    } };
    FIGS.joints = figs.concat([drawAll]);
  }

  function buildCartesian(view) {
    const W = viewWidth();
    const sw = el('label', { class: 'v6-switch' + (state.holes ? ' on' : ''), id: 'v6-holes' }, [el('input', { type: 'checkbox', id: 'v6-holes-box' }), 'Holes']);
    const box = sw.querySelector('input');
    box.checked = state.holes;
    box.addEventListener('change', () => { state.holes = box.checked; sw.classList.toggle('on', state.holes); repaint(); });
    const bar = el('span');
    view.append(el('div', { class: 'v6-toolbar' }, [sw,
      el('span', { class: 'v6-intro', html: 'Frame “cell”, 2 cm pixels, one colour scale. <b>Click a pixel</b>: who passed it. <b>Holes</b> marks reachable pixels no trajectory visits; click one: who comes closest.' }), bar]));
    const xyG = GRIDS.xy; const xzG = GRIDS.xz; const yzG = GRIDS.yz;
    const peers = [xyG, xzG, yzG];
    // xy big on the left, xz over yz on the right: both columns about the same height
    const s = clamp((W - 2 * (46 + 14 + 26) - 12) / (xyG.nx + 0.8 * xzG.nx), 1.5, 5);
    const big = Math.floor(s * 10) / 10;
    const small = Math.floor(s * 0.8 * 10) / 10;
    const xy = new Heat(xyG, { cw: big, ch: big, holes: true, colorbar: false, peers });
    const xz = new Heat(xzG, { cw: small, ch: small, holes: true, colorbar: false, peers });
    const yz = new Heat(yzG, { cw: small, ch: small, holes: true, colorbar: false, peers });
    const lead = (g) => `${int(g.paths.filter((v) => v > 0).length)} pixels visited · ${int(g.paths.filter((v, i) => v === 0 && g.outside[i]).length)} reachable never visited`;
    const cxy = card('From above (x, y)', lead(xyG), [xy.root]);
    cxy.id = 'v6-fig-xy';
    const cxz = card('From the front (x, z)', lead(xzG), [xz.root]);
    cxz.id = 'v6-fig-xz';
    const cyz = card('From the side (y, z)', lead(yzG), [yz.root]);
    cyz.id = 'v6-fig-yz';
    xz.legend.remove(); yz.legend.remove(); xz.legend = null; yz.legend = null;
    view.append(el('div', { class: 'v6-row' }, [cxy, el('div', { class: 'v6-col' }, [cxz, cyz])]));
    FIGS.cartesian = [xy, xz, yz, { draw: () => hbar(bar, xy.scaled, countWord(xy.mode()), 160) }];
  }

  function buildOrientation(view) {
    const W = viewWidth();
    view.append(el('div', { class: 'v6-toolbar' }, [el('span', { class: 'v6-intro', html: `Which way the tool's z axis points, in the base frame, on the payload's ${RINGS} × ${SECTORS} equal-area sphere cells (every cell is the same share of all directions). The disc and the map are the same cells. <b>Click one</b>: who points there; an empty one: who comes closest.` })]));
    const size = clamp(Math.floor(W * 0.42), 280, 430);
    const disc = new Disc({ size, colorbar: true });
    const mapCell = clamp(Math.floor((W - size - 74 - 28 * 2 - 12 - 46 - 26 - 74) / (SECTORS + 1)), 8, 22);
    const map = new Heat(GRIDS.dir, { cw: mapCell, ch: mapCell * 1.5, samplesOnly: true });
    const cd = card('Seen from above the tool', 'Centre = straight down (tilt 0°), edge = straight up (180°), angle = azimuth.', [disc.root]);
    cd.id = 'v6-fig-disc';
    const cm = card('Unrolled: azimuth × tilt', 'The same cells as a map: each row is one equal-area band of tilt.', [map.root]);
    cm.id = 'v6-fig-dirmap';
    view.append(el('div', { class: 'v6-row' }, [cd, cm]));
    FIGS.orientation = [disc, map];
  }

  // ── the dock: who made the cells you clicked ─────────────────────────────────────────────────────────────────────
  function dockSentence() {
    if (!answer.active) return 'Every trajectory. Click a cell in a figure to ask who made it.';
    if (state.near) {
      const word = SEARCH_WORD[GRIDS[state.near.grid].kind];
      return `The ${answer.names.length} of ${answer.pool} ${state.chips.length ? 'matching ' : ''}trajectories that come closest to the empty cell (${word}).`;
    }
    return `${answer.names.length} of ${NAMES.length} trajectories visit every cell in your query (a subset count from membership).`;
  }
  function renderDock() {
    const dock = $('#v6-dock');
    const head = el('div', { class: 'v6-dock-head' }, [
      el('div', { class: 'v6-dock-title' }, ['Who goes there', el('span', { class: 'v6-dock-count', html: `<b>${answer.names.length}</b> of ${NAMES.length} trajectories` })]),
      el('div', { class: 'v6-dock-sub', text: dockSentence() }),
    ]);
    const body = el('div', { class: 'v6-dock-body' });
    if (!answer.names.length) {
      body.append(el('div', { class: 'v6-empty', text: 'No trajectory visits all of these cells. Remove a chip above to widen the question.' }));
    } else {
      const near = !!state.near;
      const table = el('table', { class: 'v6-mini' });
      table.append(el('thead', null, el('tr', null, [
        el('th', { text: '#' }), el('th', { class: 'left', text: 'Trajectory' }), el('th', { class: 'left', text: 'kind' }), el('th', { text: 's' }),
        near ? el('th', { text: 'comes within', title: SEARCH_WORD[GRIDS[state.near.grid].kind] }) : el('th', { text: 'new cells', title: 'q×qd cells it was first to visit' }),
      ])));
      const tbody = el('tbody');
      for (const n of answer.names) {
        const r = ROW[n];
        const tr = el('tr', { 'data-name': n, class: state.drill === n ? 'open' : null }, [
          el('td', { class: 'muted', text: String(r._i + 1) }),
          el('td', { class: 'left v6-name', text: n.replace('workspace-', '') }),
          el('td', { class: 'left', text: r.tags.kind }),
          el('td', { text: r.duration_s.toFixed(2) }),
          el('td', { text: near ? distText(state.near.grid, answer.dist[n]) : String(r.new_cells) }),
        ]);
        tr.title = `${n} · click: open it`;
        tr.addEventListener('mouseenter', () => setHover(n));
        tr.addEventListener('mouseleave', () => setHover(null));
        tr.addEventListener('click', () => openDrill(n, answer.names));
        tbody.append(tr);
      }
      table.append(tbody);
      body.append(table);
    }
    const foot = el('div', { class: 'v6-dock-foot' }, [
      el('button', { class: 'v6-link', type: 'button', text: 'Open in the full table →', onclick: () => showTab('trajectories') }),
      el('span', { text: 'hover a row: its cells show in ink' }),
    ]);
    dock.replaceChildren(head, body, foot);
  }

  // ── the query bar ────────────────────────────────────────────────────────────────────────────────────────────────
  function gridTab(gridKey) {
    const g = GRIDS[gridKey];
    if (g.kind === 'plane') return ['joint', JOINTS.indexOf(g.joint)];
    if (g.kind === 'proj') return ['cartesian', null];
    return ['orientation', null];
  }
  function goToGrid(gridKey) {
    const [tab, joint] = gridTab(gridKey);
    if (tab === 'joint' && joint !== state.joint) { state.joint = joint; save('joint', joint); if (BUILT.joint) buildJoint(VIEWS.joint); }
    showTab(tab);
  }
  function renderQuery() {
    const bar = $('#v6-querybar');
    const items = [el('span', { class: 'v6-qlabel', text: 'Who goes there' })];
    if (!answer.active) {
      items.push(el('span', { class: 'v6-qhint', html: '<b>Click any coloured cell</b> in a figure to ask which trajectories made it — or an <b>empty</b> one to ask who comes closest. Clicks add up (AND).' }));
    }
    state.chips.forEach((chip, i) => {
      if (i) items.push(el('span', { class: 'v6-and', text: 'AND' }));
      items.push(el('span', { class: 'v6-chip', 'data-grid': chip.grid, 'data-chip': String(chip.id) }, [
        el('button', { class: 'v6-chip-text', type: 'button', title: 'show this cell in its figure', text: 'visits ' + chip.label, onclick: () => goToGrid(chip.grid) }),
        el('button', { class: 'v6-x v6-chip-x', type: 'button', 'aria-label': 'remove', text: '✕', onclick: () => removeChip(chip.id) }),
      ]));
    });
    if (state.near) {
      if (state.chips.length) items.push(el('span', { class: 'v6-and', text: 'THEN' }));
      const word = SEARCH_WORD[GRIDS[state.near.grid].kind];
      items.push(el('span', { class: 'v6-chip near', 'data-grid': state.near.grid, 'data-chip': 'near' }, [
        el('button', { class: 'v6-chip-text', type: 'button', title: 'show this cell in its figure', text: `closest ${NEAR_K} to ${state.near.label} · ${word}`, onclick: () => goToGrid(state.near.grid) }),
        el('button', { class: 'v6-x v6-chip-x', type: 'button', 'aria-label': 'remove', text: '✕', onclick: () => { state.near = null; update(); } }),
      ]));
    }
    items.push(el('span', { class: 'v6-qcount', id: 'v6-answer-count', html: `<b>${answer.names.length}</b> of ${NAMES.length} trajectories` }));
    if (answer.active) items.push(el('button', { class: 'v6-qclear', type: 'button', text: 'Clear', onclick: clearQuery }));
    bar.replaceChildren(...items);
  }

  // ── the full table: text + column filters, sort, group with fold, saved views (which can keep the figure query) ──
  const BUILTIN_VIEWS = [
    { id: 'all', name: 'All', cfg: { text: '', sort: { key: 'idx', dir: 1 }, group: '', filters: {} } },
    { id: 'holdout', name: 'Holdout', cfg: { text: '', sort: { key: 'idx', dir: 1 }, group: '', filters: { split: 'holdout' } } },
    { id: 'adds', name: 'Adds most', cfg: { text: '', sort: { key: 'new_cells', dir: -1 }, group: '', filters: {} } },
    { id: 'bykind', name: 'By kind', cfg: { text: '', sort: { key: 'idx', dir: 1 }, group: 'kind', filters: {} } },
  ];
  let userViews = (load('views', []) || []).filter((v) => v && v.id && v.name && v.cfg);
  function columns() {
    const span = state.table.span;
    const cols = [
      { key: 'idx', label: '#', get: (r) => r._i + 1 },
      { key: 'name', label: 'Trajectory', left: true, get: (r) => r.name },
      { key: 'split', label: 'split', sub: 'tag', left: true, get: (r) => r.tags.split, filter: true },
      { key: 'kind', label: 'kind', sub: 'tag', left: true, get: (r) => r.tags.kind, filter: true },
      { key: 'tags', label: 'tags', sub: 'tag', left: true, get: (r) => r.tags.tags, filter: true },
      { key: 'duration_s', label: 'Duration', sub: 's', get: (r) => r.duration_s, fmt: (v) => v.toFixed(2) },
      { key: 'samples', label: 'Samples', get: (r) => r.samples, fmt: int },
    ];
    for (const j of JOINTS) cols.push({ key: 'span:' + j, label: short(j), sub: `${span} span`, get: (r) => r.span_pct[j][span], bar: true });
    cols.push(
      { key: 'new_cells', label: 'New cells', sub: 'first to visit', get: (r) => r.new_cells },
      { key: 'only_it_q_qd_cells', label: 'Only it', sub: 'no other visits', get: (r) => r.only_it_q_qd_cells },
      { key: 'tool_path_m', label: 'Tool path', sub: 'm', get: (r) => r.tool_path_m, fmt: (v) => v.toFixed(2) },
      { key: 'tool_speed_max_m_s', label: 'Tool speed', sub: 'max m/s', get: (r) => r.tool_speed_max_m_s, fmt: (v) => v.toFixed(2) },
      { key: 'tool_z', label: 'Tool height', sub: 'min–max m', get: (r) => r.tool_z_min_m, fmt: (v, r) => `${r.tool_z_min_m.toFixed(2)}–${r.tool_z_max_m.toFixed(2)}` },
      { key: 'tool_tilt_max_deg', label: 'Tilt', sub: 'max °', get: (r) => r.tool_tilt_max_deg, fmt: (v) => String(Math.round(v)) },
    );
    if (state.near) cols.push({ key: 'dist', label: 'Comes within', sub: SEARCH_WORD[GRIDS[state.near.grid].kind], get: (r) => answer.dist[r.name], fmt: (v) => distText(state.near.grid, v) });
    return cols;
  }
  function tableRows() {
    const t = state.table;
    const tokens = t.text.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const cols = columns();
    let rows = answer.names.map((n) => ROW[n]);
    if (tokens.length) rows = rows.filter((r) => { const hay = `${r.name} ${r.tags.split} ${r.tags.kind} ${r.tags.tags} ${r.tags.rung}`.toLowerCase(); return tokens.every((tk) => hay.includes(tk)); });
    for (const [k, v] of Object.entries(t.filters)) { if (!v) continue; const c = cols.find((x) => x.key === k); if (c) rows = rows.filter((r) => String(c.get(r)) === v); }
    const col = cols.find((c) => c.key === t.sort.key) || cols[0];
    rows = rows.slice().sort((a, b) => {
      const x = col.get(a); const y = col.get(b);
      const d = typeof x === 'string' ? x.localeCompare(y) : x - y;
      return (d || a._i - b._i) * (d ? t.sort.dir : 1);
    });
    return { rows, cols };
  }
  function viewCfg() { const t = state.table; return { text: t.text, sort: { ...t.sort }, group: t.group, filters: { ...t.filters }, span: t.span }; }
  function applyView(v) {
    const t = state.table;
    t.text = v.cfg.text || ''; t.sort = { ...(v.cfg.sort || { key: 'idx', dir: 1 }) }; t.group = v.cfg.group || ''; t.filters = { ...(v.cfg.filters || {}) };
    if (v.cfg.span) t.span = v.cfg.span;
    t.folded = new Set(); t.view = v.id;
    if (v.cfg.chips) { state.chips = v.cfg.chips.map((c) => ({ ...c, id: ++chipSeq })); state.near = v.cfg.near ? { ...v.cfg.near } : null; update(); return; }
    renderTable();
  }
  let saving = false;
  function renderTable() {
    const view = VIEWS.trajectories;
    if (!view || !BUILT.trajectories) return;
    const t = state.table;
    const { rows, cols } = tableRows();
    // view tabs, + save, search
    const tabs = el('div', { class: 'v6-viewtabs' });
    for (const v of BUILTIN_VIEWS.concat(userViews)) {
      const b = el('button', { class: 'v6-vtab' + (t.view === v.id ? ' on' : ''), type: 'button', 'data-view': v.id, title: v.cfg.chips && v.cfg.chips.length ? 'keeps a figure query' : null, onclick: () => applyView(v) }, [v.name]);
      if (v.cfg.chips && (v.cfg.chips.length || v.cfg.near)) b.append(el('span', { class: 'q', text: '● query' }));
      if (v.id.startsWith('u')) b.append(el('span', { class: 'del', title: 'delete this view', text: '✕', onclick: (e) => { e.stopPropagation(); userViews = userViews.filter((x) => x.id !== v.id); save('views', userViews); if (t.view === v.id) t.view = 'all'; renderTable(); } }));
      tabs.append(b);
    }
    if (saving) {
      const input = el('input', { id: 'v6-save-name', placeholder: 'name this view', value: '' });
      const doSave = () => {
        const name = input.value.trim(); if (!name) return;
        const cfg = viewCfg();
        cfg.chips = state.chips.map((c) => ({ grid: c.grid, cells: c.cells.slice(), label: c.label, meta: c.meta }));
        cfg.near = state.near ? { ...state.near } : null;
        const v = { id: 'u' + Date.now(), name, cfg };
        userViews.push(v); save('views', userViews); t.view = v.id; saving = false; renderTable();
      };
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSave(); if (e.key === 'Escape') { saving = false; renderTable(); } });
      tabs.append(el('span', { class: 'v6-savebox' }, [input, el('button', { type: 'button', text: 'Save', onclick: doSave }), el('button', { type: 'button', text: 'Cancel', onclick: () => { saving = false; renderTable(); } })]));
      setTimeout(() => input.focus(), 0);
    } else {
      tabs.append(el('button', { class: 'v6-vtab add', type: 'button', id: 'v6-save-view', title: 'save the filter, sort, grouping and the figure query as a view', text: '+ Save current', onclick: () => { saving = true; renderTable(); } }));
    }
    const search = el('input', { id: 'v6-search', type: 'search', placeholder: 'Filter trajectories…', value: t.text, 'aria-label': 'Filter trajectories' });
    search.addEventListener('input', () => { t.text = search.value; renderBody(); });
    tabs.append(el('span', { class: 'v6-search' }, [search]));

    const status = el('div', { class: 'v6-tablebar' });
    const tableEl = el('table', { class: 'v6-full', 'data-v6-table': '' });
    const wrap = el('div', { class: 'v6-tablewrap' }, [tableEl]);
    view.replaceChildren(el('div', { class: 'v6-tablecard' }, [tabs, status, wrap]));

    function renderBody() {
      const { rows: rs, cols: cs } = tableRows();
      const groups = [];
      if (t.group) {
        const gc = cs.find((c) => c.key === t.group);
        const byKey = new Map();
        for (const r of rs) { const k = String(gc.get(r)); if (!byKey.has(k)) { byKey.set(k, []); groups.push(k); } byKey.get(k).push(r); }
        groups.rows = byKey;
      }
      // status bar
      const parts = [el('span', { html: `<b>${rs.length}</b> of ${NAMES.length} rows${t.group ? ` · <b>${groups.length}</b> groups` : ''}` })];
      if (answer.active) parts.push(el('span', { text: `· the figure query keeps ${answer.names.length}` }));
      if (t.group) {
        parts.push(el('button', { class: 'v6-link', type: 'button', text: 'Unfold all', onclick: () => { t.folded = new Set(); renderBody(); } }));
        parts.push(el('button', { class: 'v6-link', type: 'button', text: 'Fold all', onclick: () => { t.folded = new Set(groups); renderBody(); } }));
      }
      parts.push(el('span', { class: 'spacer' }));
      const groupSel = el('select', { id: 'v6-groupby', 'aria-label': 'Group by' }, [['', 'none'], ['split', 'split'], ['kind', 'kind'], ['tags', 'tags']].map(([v, l]) => el('option', { value: v, text: l })));
      groupSel.value = t.group;
      groupSel.addEventListener('change', () => { t.group = groupSel.value; t.folded = new Set(); renderBody(); });
      parts.push(el('label', null, ['Group by ', groupSel]));
      const spanSeg = el('span', { class: 'v6-seg' });
      for (const [k, l] of [['q', 'position'], ['qd', 'speed'], ['qdd', 'acceleration']]) spanSeg.append(el('button', { type: 'button', 'aria-pressed': t.span === k ? 'true' : 'false', text: l, onclick: () => { t.span = k; renderBody(); } }));
      parts.push(el('span', { class: 'v6-seg-label', text: 'Span of' }), spanSeg);
      parts.push(el('span', { class: 'v6-li' }, [el('span', { class: 'v6-minibar', style: 'width:22px;margin:0' }, el('span', { style: 'width:60%' })), 'bar = share of the joint\'s limit it spans']));
      status.replaceChildren(...parts);
      // header
      const thead = el('thead');
      const hr = el('tr');
      for (const c of cs) {
        const on = t.sort.key === c.key;
        const th = el('th', { class: (c.left ? 'left ' : '') + 'sortable', 'data-sort': c.key, title: 'sort' }, [c.label, on ? el('span', { class: 'arrow', text: t.sort.dir > 0 ? ' ↑' : ' ↓' }) : null, c.sub ? el('span', { class: 'sub', text: c.sub }) : null]);
        th.addEventListener('click', () => { if (t.sort.key === c.key) t.sort.dir = -t.sort.dir; else t.sort = { key: c.key, dir: typeof c.get(TRAJ[0]) === 'string' ? 1 : (c.key === 'idx' || c.key === 'dist' ? 1 : -1) }; renderBody(); });
        hr.append(th);
      }
      const fr = el('tr', { class: 'v6-colfilters' });
      for (const c of cs) {
        const th = el('th', { class: c.left ? 'left' : null });
        if (c.filter) {
          const values = [...new Set(TRAJ.map((r) => String(c.get(r))))].sort();
          const sel = el('select', { 'data-filter': c.key, 'aria-label': `filter ${c.label}` }, [el('option', { value: '', text: 'all' })].concat(values.map((v) => el('option', { value: v, text: v }))));
          sel.value = t.filters[c.key] || '';
          sel.addEventListener('change', () => { t.filters[c.key] = sel.value; renderBody(); });
          th.append(sel);
        }
        fr.append(th);
      }
      thead.append(hr, fr);
      const tbody = el('tbody');
      const rowEl = (r) => {
        const tr = el('tr', { class: 'v6-trow' + (state.drill === r.name ? ' open' : ''), 'data-name': r.name });
        for (const c of cs) {
          const v = c.get(r);
          const td = el('td', { class: c.left ? 'left' : null });
          if (c.key === 'name') td.append(el('span', { class: 'v6-name', text: v }));
          else if (c.key === 'split') td.append(el('span', { class: 'v6-tag', text: v }));
          else if (c.bar) { td.append(pctText(v)); td.append(el('span', { class: 'v6-minibar' }, el('span', { style: `width:${clamp(v, 0, 100)}%` }))); }
          else td.textContent = c.fmt ? c.fmt(v, r) : String(v);
          tr.append(td);
        }
        tr.addEventListener('click', () => openDrill(r.name, rs.map((x) => x.name)));
        return tr;
      };
      if (t.group) {
        for (const k of groups) {
          const members = groups.rows.get(k);
          const folded = t.folded.has(k);
          const gr = el('tr', { class: 'v6-group', 'data-group': k }, el('td', { colspan: String(cs.length) }, [folded ? '▸ ' : '▾ ', k, el('span', { class: 'n', text: `${members.length} rows` })]));
          gr.addEventListener('click', () => { if (folded) t.folded.delete(k); else t.folded.add(k); renderBody(); });
          tbody.append(gr);
          if (!folded) for (const r of members) tbody.append(rowEl(r));
        }
      } else {
        for (const r of rs) tbody.append(rowEl(r));
      }
      if (!rs.length) tbody.append(el('tr', null, el('td', { colspan: String(cs.length), class: 'left', style: 'color:#8a8983;padding:14px', text: 'No trajectory matches the filter and the figure query.' })));
      tableEl.replaceChildren(thead, tbody);
    }
    renderBody();
  }
  function buildTrajectories(view) { /* drawn by renderTable() */ void view; }

  // ── the drill: one trajectory over the dataset, its motion, and Open in Rerun ───────────────────────────────────
  let SAMPLES = null;
  let samplesLoading = null;
  function loadSamples() {
    if (samplesLoading) return samplesLoading;
    samplesLoading = fetch('../data/samples.json').then((r) => { if (!r.ok) throw new Error(`samples.json: ${r.status}`); return r.json(); }).then((rows) => {
      const by = {};
      for (const row of rows) { (by[row.trajectory] = by[row.trajectory] || []).push(row); }
      SAMPLES = by;
      return by;
    });
    return samplesLoading;
  }
  function localCommand(rrd) {
    let root = document.body.dataset.round;
    if (location.protocol === 'file:') root = decodeURIComponent(location.pathname).replace(/\/v6\/[^/]*$/, '');
    return `uvx --from rerun-sdk==0.40.0 rerun ${root}/${rrd}`;
  }
  async function openRerun(name, status, cmdBox) {
    const rrd = ROW[name].rrd;
    const show = (text) => {
      const code = el('code', { text });
      const copy = el('button', { class: 'v6-btn', type: 'button', text: 'Copy' });
      copy.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(text); copy.textContent = 'Copied'; } catch (e) {
          const range = document.createRange(); range.selectNodeContents(code); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); copy.textContent = 'Selected: Ctrl+C';
        }
      });
      cmdBox.replaceChildren(el('div', { class: 'v6-cmd' }, [code, copy]));
    };
    status.className = 'v6-rerun-status';
    status.textContent = 'Asking the server to open it…';
    try {
      if (location.protocol === 'file:') throw new Error('this page was opened from a file, so there is no server to start Rerun');
      const res = await fetch('/__rerun/open?rrd=' + encodeURIComponent(rrd), { method: 'POST' });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.ok) throw new Error(body.error || `the server answered ${res.status}`);
      status.textContent = 'Opened in the native Rerun viewer ✓ — the same command, to run it again:';
      show(body.command && /\.rrd/.test(body.command) ? body.command : localCommand(rrd));
    } catch (e) {
      status.className = 'v6-rerun-status bad';
      status.textContent = `Could not open it from here (${e.message}). Run this yourself:`;
      show(localCommand(rrd));
    }
  }
  function openDrill(name, list) {
    state.drill = name;
    state.drillList = (list && list.length ? list : answer.names).slice();
    renderDrill();
    renderDock();
    repaint();
    if (state.tab === 'trajectories') for (const tr of document.querySelectorAll('.v6-full tr.v6-trow')) tr.classList.toggle('open', tr.dataset.name === name);
  }
  function closeDrill() {
    state.drill = null;
    $('#v6-drill').hidden = true;
    renderDock();
    repaint();
    for (const tr of document.querySelectorAll('.v6-full tr.v6-trow.open')) tr.classList.remove('open');
  }
  function renderDrill() {
    const name = state.drill;
    const host = $('#v6-drill');
    if (!name) { host.hidden = true; return; }
    const r = ROW[name];
    const list = state.drillList.includes(name) ? state.drillList : [name];
    const at = list.indexOf(name);
    const nav = el('div', { class: 'v6-dr-nav' }, [
      el('button', { class: 'v6-btn', type: 'button', id: 'v6-drill-back', text: '← Back to the dataset', onclick: closeDrill }),
      el('span', { class: 'spacer' }),
      el('span', { class: 'pos', text: `${at + 1} of ${list.length} in the ${answer.active ? 'answer' : 'list'}` }),
      el('button', { class: 'v6-btn', type: 'button', text: '‹', title: 'previous', disabled: at <= 0 ? true : null, onclick: () => openDrill(list[at - 1], list) }),
      el('button', { class: 'v6-btn', type: 'button', text: '›', title: 'next', disabled: at >= list.length - 1 ? true : null, onclick: () => openDrill(list[at + 1], list) }),
      el('button', { class: 'v6-x', type: 'button', id: 'v6-drill-close', 'aria-label': 'Close', text: '✕', onclick: closeDrill }),
    ]);
    const status = el('span', { class: 'v6-rerun-status', text: `data/rrd/${name}.rrd · q, qd, qdd per joint + the tool path` });
    const cmdBox = el('div', { style: 'width:100%' });
    const rerun = el('div', { class: 'v6-rerun' }, [
      el('button', { class: 'v6-btn primary', type: 'button', 'data-open-rerun': '', text: 'Open in Rerun', onclick: () => openRerun(name, status, cmdBox) }),
      status, cmdBox,
    ]);
    const nums = [
      ['Duration', `${r.duration_s.toFixed(2)} s`], ['Samples', int(r.samples)], ['Tool path', `${r.tool_path_m.toFixed(2)} m`], ['Tool speed, max', `${r.tool_speed_max_m_s.toFixed(2)} m/s`],
      ['Tool height', `${r.tool_z_min_m.toFixed(2)}–${r.tool_z_max_m.toFixed(2)} m`], ['Tilt, max', `${Math.round(r.tool_tilt_max_deg)}°`],
      ['New cells', `${r.new_cells}`, 'q×qd cells (all joints) it was first to visit, in dataset order'], ['Only it', `${r.only_it_q_qd_cells}`, 'q×qd cells no other trajectory visits'],
    ];
    const numsEl = el('div', { class: 'v6-dr-nums' }, nums.map(([l, v, t]) => el('div', { class: 'v6-num', title: t || null }, [el('span', { class: 'label', text: l }), el('span', { class: 'value', text: v })])));
    // its cells over the dataset, then its motion, then its spans and directions
    const xy = new Heat(GRIDS.xy, { cw: 1.5, ch: 1.5, axes: false, interactive: false, colorbar: false, legend: false, focus: name });
    const planes = JOINTS.map((j) => new Heat(GRIDS[`plane:${j}:q_qd`], { cw: 3.5, ch: 3.5, axes: false, interactive: false, colorbar: false, legend: false, focus: name }));
    const disc = new Disc({ size: 150, legend: false, interactive: false, focus: name });
    const planeGrid = el('div', { class: 'v6-dr-planes' }, planes.map((p, i) => el('div', null, [el('div', { class: 'v6-mini-title', html: `<b>${short(JOINTS[i])}</b> <span>q × qd</span>` }), p.root])));
    const maps = el('div', { class: 'v6-dr-maps' }, [el('div', null, [el('div', { class: 'v6-mini-title', html: '<b>tool</b> <span>from above</span>' }), xy.root]), planeGrid]);
    const mapsLegend = el('div', { class: 'v6-legend' }, [
      el('span', { class: 'v6-li' }, [el('span', { class: 'v6-sw ink' }), 'its cells']),
      el('span', { class: 'v6-li' }, [el('span', { class: 'v6-sw accent' }), 'cells no other trajectory visits']),
      el('span', { class: 'v6-li' }, [el('span', { class: 'v6-sw', style: `background:${rampCss()};opacity:.35;width:30px` }), 'the whole dataset, faded']),
      el('span', { class: 'v6-li' }, [el('span', { class: 'v6-sw outside' }), 'outside the reachable set']),
    ]);
    const motion = el('div', { class: 'v6-loading', text: 'Loading its samples (data/samples.json, every sample of this trajectory)…' });
    const spans = el('table', { class: 'v6-spans' }, [
      el('thead', null, el('tr', null, [el('th', { class: 'left', text: 'joint' }), el('th', { text: 'q span' }), el('th', { text: 'qd span' }), el('th', { text: 'qdd span' })])),
      el('tbody', null, JOINTS.map((j) => el('tr', null, [el('td', { class: 'left', text: short(j) }), ...['q', 'qd', 'qdd'].map((s) => el('td', null, [pctText(r.span_pct[j][s]), el('span', { class: 'v6-minibar' }, el('span', { style: `width:${clamp(r.span_pct[j][s], 0, 100)}%` }))]))]))),
    ]);
    const motionHead = el('h4', null, ['Its motion ', el('span', { class: 'sub', text: '' })]);
    const body = el('div', { class: 'v6-dr-body' }, [
      el('div', { class: 'v6-dr-title' }, [el('h2', { text: name }), el('div', { class: 'v6-dr-tags' }, [r.tags.split, r.tags.kind, `rung ${r.tags.rung}`, r.tags.tags].map((t) => el('span', { class: 'v6-tag', text: t })))]),
      rerun, numsEl,
      el('div', { class: 'v6-dr-sec' }, [el('h4', null, ['What it adds ', el('span', { class: 'sub', text: 'its cells over the dataset (trajectories per cell, faded)' })]), maps, mapsLegend]),
      el('div', { class: 'v6-dr-sec' }, [motionHead, motion]),
      el('div', { class: 'v6-dr-sec v6-dr-maps' }, [
        el('div', null, [el('h4', { text: 'How much of each limit it spans' }), spans]),
        el('div', null, [el('h4', null, ['Where it points ', el('span', { class: 'sub', text: 'ink over the dataset' })]), disc.root]),
      ]),
    ]);
    host.replaceChildren(nav, body);
    host.hidden = false;
    host.scrollTop = 0;
    xy.draw(); disc.draw(); planes.forEach((p) => p.draw());
    const drawMotion = (by) => {
      if (state.drill !== name) return;
      const rows = by[name] || [];
      const t = rows.map((row) => row.t_s);
      const legend = el('div', { class: 'v6-legend' }, JOINTS.map((j, i) => el('span', { class: 'v6-li' }, [el('span', { class: 'v6-sw line', style: `color:${JOINT_COLOURS[i]}` }), short(j)])));
      const qc = el('canvas');
      const qdc = el('canvas');
      motion.className = '';
      motionHead.querySelector('.sub').textContent = `q and qd per joint, all ${rows.length} samples (not subsampled), on its own clock; colour = joint`;
      motion.replaceChildren(qc, qdc, legend);
      const series = (suffix) => JOINTS.map((j, i) => ({ colour: JOINT_COLOURS[i], xs: t, ys: rows.map((row) => row[`${short(j)}${suffix}`]) }));
      lineChart(qc, series('_q_deg'), 624, 124, 'q (°)');
      lineChart(qdc, series('_qd_deg_s'), 624, 124, 'qd (°/s)');
    };
    if (SAMPLES) drawMotion(SAMPLES);
    else loadSamples().then(drawMotion).catch((e) => { motion.textContent = `Could not load data/samples.json (${e.message}); the rest of the drill is from trajectories.json and membership.`; });
  }

  // ── wiring ───────────────────────────────────────────────────────────────────────────────────────────────────────
  const BUILDERS = { overview: buildOverview, limits: buildLimits, joint: buildJoint, joints: buildJoints, cartesian: buildCartesian, orientation: buildOrientation, trajectories: buildTrajectories };
  // WHY measured: the dock fills the window below the sticky bar, whose height grows when the chips wrap
  function fitDock() {
    const dock = $('#v6-dock');
    const top = document.querySelector('.v6-bar').offsetHeight + 12;
    dock.style.top = top + 'px';
    const at = Math.max(dock.getBoundingClientRect().top, top);
    dock.style.height = Math.max(300, window.innerHeight - at - 12) + 'px';
  }
  function update() {
    computeAnswer();
    renderQuery();
    renderDock();
    fitDock();
    if (state.tab === 'trajectories') renderTable();
    if (state.drill && !answer.set.has(state.drill)) { /* keep the drill open: it is the user's context */ }
    repaint();
  }
  function boot() {
    $('#v6-title').textContent = P.title || 'Trajectory coverage';
    $('#v6-subtitle').textContent = P.subtitle || '';
    document.title = `${P.title} · who goes there`;
    buildTabs();
    initSettings();
    computeAnswer();
    renderQuery();
    renderDock();
    showTab('overview');
    window.addEventListener('resize', () => {
      for (const id of Object.keys(BUILT)) { if (id !== 'trajectories') { BUILT[id] = false; VIEWS[id].replaceChildren(); } }
      showTab(state.tab);
    });
    $('#v6-app').dataset.ready = '1';
  }
  boot();
})();
