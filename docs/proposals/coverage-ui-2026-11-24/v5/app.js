/* V5 · Focus rail — hand-rolled master–detail coverage page (babble round 2026-11-24).
 *
 * Thesis: keep the whole dataset on screen, and let a trajectory list on the left light up what any trajectory (or a
 * few) contributes, everywhere at once. The rail (master) holds filter / sort / group / saved views; selecting rows
 * overlays the selection's cells on every figure (detail) from data/membership.json: the dataset is drawn muted, the
 * selection's cells keep the colour map, and the cells ONLY the selection reaches turn cyan. Double-click (or ▸) opens
 * a trajectory page inside the app with Open in Rerun.
 *
 * Reads only ../data/ (coverage.js, trajectories.js, membership.js via <script>, samples.json via fetch). Every number
 * shown comes from the payload / trajectories.json, except the selection overlays: those are re-aggregated from
 * membership.json (cells) and samples.json (1-D histograms), and the page says "subset count" wherever it shows one.
 *
 * Zach's rules kept here (2026-11-23 coverage feedback): headline numbers only on the overview; every colour beside a
 * trajectory is explained in a legend; the joint picker only on One joint; colours + Reverse + scale behind one gear;
 * white = empty, grey = out of reach, red = a limit; angles in degrees; linear scale first.
 */
(function (global) {
  'use strict';

  const DATA = global.COVERAGE_UI || {};
  const P = DATA.coverage;
  const ROWS = DATA.trajectories;
  const MEM = DATA.membership;
  const Color = global.CoverageColor;

  // WHY a constant: from http the page cannot know the round folder's absolute path, and the fallback command must be
  // one runnable line with absolute paths (Zach's copyable-command rule).
  const ROUND_DIR = '/home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24';
  const RERUN_PREFIX = 'uvx --from rerun-sdk==0.40.0 rerun';
  const SERVE_CMD = `/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve ${ROUND_DIR} --port 8815`;
  const STORE = 'coverage-ui-2026-11-24.v5.';

  const INK = '#22211f';
  const SOFT = '#52514e';
  const MUTED = '#8a8983';
  const AXIS = '#b9b8b2';
  const RULE = '#efeee9';
  const FOCUS = '#1f6feb';
  const ONLY = [0, 180, 240];
  const BAR = '#8f9aa6';
  const BAR_MUTED = '#d9dcdf';
  const LIMIT = Color.LIMIT;
  const FONT = '10.5px -apple-system, "Segoe UI", Roboto, sans-serif';
  const FONT_SMALL = '9.5px -apple-system, "Segoe UI", Roboto, sans-serif';
  // WHY no blue among the group colours: blue means "selected" everywhere on this page; no amber/red (= a problem / a limit)
  const GROUP_PALETTE = ['#2f9e44', '#8e5bd1', '#0f9fb3', '#c22f6e', '#6b7a8f', '#8a6d1f', '#5f3dc4', '#3d8b6d'];
  const PLANES = ['q_qd', 'qd_qdd', 'q_qdd'];
  const PLANE_WORDS = { q_qd: 'position × speed', qd_qdd: 'speed × acceleration', q_qdd: 'position × acceleration' };
  const SIGNAL_WORD = { q: 'position', qd: 'speed', qdd: 'acceleration', qddd: 'jerk' };
  const POWER = { q: '', qd: '/s', qdd: '/s²', qddd: '/s³' };
  const SAMPLE_COLUMN = { q: '_q_deg', qd: '_qd_deg_s', qdd: '_qdd_deg_s2' };
  const DEG = 180 / Math.PI;
  const SCALE_NOTES = {
    linear: 'Colour grows in proportion to the count; the top 2 % of cells are clipped so one hot cell does not wash out the rest.',
    log: 'Colour follows log(count), so thin cells show too; equal colour steps are ×10, not +10.',
    equalized: 'Colour = rank among the visited cells: it shows WHERE the data is, not HOW MUCH.',
    visited: 'One colour for every cell with any sample: is it covered at all?',
    enough: `Full colour = at least ${P.enough} samples (enough to trust); pale = visited, but fewer.`,
  };

  // ── small helpers ─────────────────────────────────────────────────────────────────────────────────────────────

  function load(key, fallback) {
    try {
      const raw = global.localStorage.getItem(STORE + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (error) { return fallback; }
  }
  function save(key, value) {
    try { global.localStorage.setItem(STORE + key, JSON.stringify(value)); } catch (error) { /* private window */ }
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'html') node.innerHTML = value;
      else if (key === 'style') node.setAttribute('style', value);
      else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of [].concat(children === undefined ? [] : children)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child.nodeType ? child : String(child));
    }
    return node;
  }
  const $ = (selector, root) => (root || document).querySelector(selector);
  function esc(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function minus(text) { return String(text).replace(/^-/, '−'); }
  function fmt(value) {
    if (value === null || value === undefined || !Number.isFinite(value)) return '—';
    const size = Math.abs(value);
    let text;
    if (size >= 1e4) text = (value / 1e3).toFixed(size >= 1e5 ? 0 : 1) + ' k';
    else if (size >= 100) text = String(Math.round(value));
    else if (size >= 10) text = value.toFixed(1).replace(/\.0$/, '');
    else if (size >= 1) text = value.toFixed(2).replace(/\.?0+$/, '');
    else if (size === 0) text = '0';
    else text = value.toPrecision(2).replace(/\.?0+$/, '');
    return minus(text);
  }
  function pct(value) {
    if (value === null || value === undefined || !Number.isFinite(value)) return '—';
    if (value > 0 && value < 10) return value.toFixed(1).replace(/\.0$/, '') + ' %';
    return Math.round(value) + ' %';
  }
  function count(value) {
    if (value === null || value === undefined || !Number.isFinite(value)) return '—';
    return Math.round(value).toLocaleString('en-US').replace(/,/g, ' ');
  }
  function duration(seconds) {
    if (!Number.isFinite(seconds)) return '—';
    if (seconds < 120) return fmt(seconds) + ' s';
    return (seconds / 60).toFixed(1).replace(/\.0$/, '') + ' min';
  }
  function plural(n, one, many) { return n === 1 ? one : many || one + 's'; }
  function clamp(value, lo, hi) { return Math.min(hi, Math.max(lo, value)); }
  function niceStep(span, target) {
    const raw = span / Math.max(1, target);
    const power = Math.pow(10, Math.floor(Math.log10(raw)));
    const m = raw / power;
    return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * power;
  }
  function ticks(lo, hi, target) {
    if (!(hi > lo)) return [lo];
    const step = niceStep(hi - lo, target);
    const out = [];
    for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    out.step = step;
    return out;
  }
  function tickText(value, step) {
    const decimals = step >= 1 ? 0 : Math.min(4, Math.ceil(-Math.log10(step) - 1e-9));
    return minus(value.toFixed(decimals));
  }
  function rgbCss(rgb, alpha) { return alpha === undefined ? `rgb(${rgb[0]},${rgb[1]},${rgb[2]})` : `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha})`; }
  function quantile(sorted, q) {
    if (!sorted.length) return 0;
    const at = (sorted.length - 1) * q;
    const lo = Math.floor(at);
    const hi = Math.min(sorted.length - 1, lo + 1);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (at - lo);
  }
  function short(name) { return name.replace(/_joint$/, ''); }
  function unitOf(joint, signal) { return (joint.display.unit === 'deg' ? '°' : ' ' + joint.display.unit) + POWER[signal]; }
  function axisOf(joint, signal, spec) {
    return { lo: spec[0] * joint.display.scale, hi: spec[1] * joint.display.scale, label: `${signal} · ${SIGNAL_WORD[signal]} (${unitOf(joint, signal).trim()})` };
  }

  // ── canvas helpers ────────────────────────────────────────────────────────────────────────────────────────────

  function canvasOf(width, height, attrs) {
    const ratio = Math.min(2, global.devicePixelRatio || 1);
    const canvas = el('canvas', attrs);
    canvas.width = Math.max(1, Math.round(width * ratio));
    canvas.height = Math.max(1, Math.round(height * ratio));
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    canvas.style.display = 'block';
    const g = canvas.getContext('2d');
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.font = FONT;
    return { canvas, g, width, height };
  }
  function mapper(box, x, y) {
    return {
      sx: (v) => box.x + ((v - x.lo) / (x.hi - x.lo)) * box.w,
      sy: (v) => box.y + box.h - ((v - y.lo) / (y.hi - y.lo)) * box.h,
    };
  }
  /* x, y: {lo, hi, label?, ticks?, tickText?, show?, labelOffset?}; opts.font, opts.target */
  function drawAxes(g, box, x, y, opts) {
    opts = opts || {};
    g.save();
    g.font = opts.font || FONT;
    g.strokeStyle = AXIS;
    g.fillStyle = MUTED;
    g.lineWidth = 1;
    if (x && x.show !== false) {
      const xt = x.ticks || ticks(x.lo, x.hi, Math.max(2, Math.floor(box.w / (opts.xGap || 64))));
      const step = xt.step || (xt.length > 1 ? Math.abs(xt[1] - xt[0]) : 1);
      g.textAlign = 'center';
      g.textBaseline = 'top';
      for (const v of xt) {
        const px = box.x + ((v - x.lo) / (x.hi - x.lo)) * box.w;
        if (px < box.x - 0.5 || px > box.x + box.w + 0.5) continue;
        g.beginPath(); g.moveTo(Math.round(px) + 0.5, box.y + box.h); g.lineTo(Math.round(px) + 0.5, box.y + box.h + 3); g.stroke();
        g.fillText(x.tickText ? x.tickText(v) : tickText(v, step), px, box.y + box.h + (x.tickPad || 5));
      }
      if (x.label) { g.fillStyle = SOFT; g.fillText(x.label, box.x + box.w / 2, box.y + box.h + (x.labelPad || 18)); g.fillStyle = MUTED; }
    }
    if (y && y.show !== false) {
      const yt = y.ticks || ticks(y.lo, y.hi, Math.max(2, Math.floor(box.h / (opts.yGap || 40))));
      const step = yt.step || (yt.length > 1 ? Math.abs(yt[1] - yt[0]) : 1);
      g.textAlign = 'right';
      g.textBaseline = 'middle';
      for (const v of yt) {
        const py = box.y + box.h - ((v - y.lo) / (y.hi - y.lo)) * box.h;
        if (py < box.y - 0.5 || py > box.y + box.h + 0.5) continue;
        g.beginPath(); g.moveTo(box.x - 3, Math.round(py) + 0.5); g.lineTo(box.x, Math.round(py) + 0.5); g.stroke();
        g.textBaseline = opts.inset && py > box.y + box.h - 4 ? 'bottom' : opts.inset && py < box.y + 4 ? 'top' : 'middle';
        g.fillText(y.tickText ? y.tickText(v) : tickText(v, step), box.x - 5, py);
      }
      if (y.label) {
        g.save();
        g.translate(box.x - (y.labelOffset || 40), box.y + box.h / 2);
        g.rotate(-Math.PI / 2);
        g.textAlign = 'center';
        g.textBaseline = 'middle';
        g.fillStyle = SOFT;
        g.fillText(y.label, 0, 0);
        g.restore();
      }
    }
    g.restore();
  }
  function strokeBox(g, box, colour, width) {
    g.save(); g.strokeStyle = colour; g.lineWidth = width || 1;
    g.strokeRect(Math.round(box.x) + 0.5, Math.round(box.y) + 0.5, Math.round(box.w) - 1, Math.round(box.h) - 1);
    g.restore();
  }
  function hline(g, y, x0, x1, colour, width, dash) {
    g.save(); g.strokeStyle = colour; g.lineWidth = width || 1; if (dash) g.setLineDash(dash);
    g.beginPath(); g.moveTo(x0, Math.round(y) + 0.5); g.lineTo(x1, Math.round(y) + 0.5); g.stroke(); g.restore();
  }
  function vline(g, x, y0, y1, colour, width, dash) {
    g.save(); g.strokeStyle = colour; g.lineWidth = width || 1; if (dash) g.setLineDash(dash);
    g.beginPath(); g.moveTo(Math.round(x) + 0.5, y0); g.lineTo(Math.round(x) + 0.5, y1); g.stroke(); g.restore();
  }

  // ── the data: indexes, cell grids, selection ──────────────────────────────────────────────────────────────────

  const JOINTS = P.joints;
  ROWS.forEach((row, index) => { row.index = index; });
  const byName = new Map(ROWS.map((row) => [row.name, row]));
  // payload per-trajectory arrays (paths, spaghetti, growth) are in payload order; map them by name to be safe
  const payloadIndex = new Map(P.trajectories.map((row, index) => [row.name, index]));

  const GRIDS = new Map();
  function cellsOf(name, key) {
    const m = MEM.trajectories[name];
    if (!m) return [];
    if (key.startsWith('p:')) { const parts = key.split(':'); return m.planes[parts[1]][parts[2]]; }
    if (key === 'vox') return m.voxels;
    if (key === 'dir') return m.directions;
    return m[key] || [];
  }
  function addGrid(key, n) {
    const total = new Uint16Array(n);
    const owners = new Map();
    for (const row of ROWS) {
      for (const cell of cellsOf(row.name, key)) {
        total[cell] += 1;
        let list = owners.get(cell);
        if (!list) owners.set(cell, (list = []));
        list.push(row.index);
      }
    }
    GRIDS.set(key, { n, total, owners });
  }
  for (const joint of JOINTS) for (const plane of PLANES) { const s = P.planes[joint.name][plane].shape; addGrid(`p:${joint.name}:${plane}`, s[0] * s[1]); }
  for (const view of ['xy', 'xz', 'yz']) { const s = P.tool.projections[view].shape; addGrid(view, s[0] * s[1]); }
  addGrid('vox', MEM.voxel_shape.reduce((a, b) => a * b, 1));
  addGrid('dir', MEM.sphere[0] * MEM.sphere[1]);

  const sel = { names: [], set: new Set(), anchor: null };
  const countCache = new Map();
  function counts(key, names) {
    const cacheKey = key + '|' + names.join(',');
    let out = countCache.get(cacheKey);
    if (out) return out;
    out = new Uint16Array(GRIDS.get(key).n);
    for (const name of names) for (const cell of cellsOf(name, key)) out[cell] += 1;
    if (countCache.size > 400) countCache.clear();
    countCache.set(cacheKey, out);
    return out;
  }
  /* reach = cells the names visit; only = cells nobody outside the names visits (a subset count from membership.json) */
  function reachOf(key, names) {
    const c = counts(key, names);
    const total = GRIDS.get(key).total;
    let reach = 0;
    let only = 0;
    for (let k = 0; k < c.length; k++) if (c[k]) { reach += 1; if (c[k] === total[k]) only += 1; }
    return { reach, only };
  }
  function uniqueJointCells(names) {
    return JOINTS.reduce((sum, joint) => sum + reachOf(`p:${joint.name}:q_qd`, names).only, 0);
  }
  function isWhole(names) { return names.length >= ROWS.length; }

  // ── state ─────────────────────────────────────────────────────────────────────────────────────────────────────

  const BUILTIN_VIEWS = [
    { id: 'all', name: 'All', filter: '', where: null, sort: 'name', dir: 1, group: 'split' },
    { id: 'holdout', name: 'Holdout', filter: '', where: { split: 'holdout' }, sort: 'name', dir: 1, group: 'kind' },
    { id: 'adds', name: 'Adds most', filter: '', where: null, sort: 'new_cells', dir: -1, group: 'none' },
    { id: 'unique', name: 'Only-it cells', filter: '', where: null, sort: 'only_it_q_qd_cells', dir: -1, group: 'none' },
  ];
  const SORTS = [
    ['name', 'Name'], ['new_cells', 'New cells (first to visit)'], ['only_it_q_qd_cells', 'Cells only it visits'],
    ['duration_s', 'Duration'], ['samples', 'Samples'], ['tool_path_m', 'Tool path length'],
    ['tool_speed_max_m_s', 'Peak tool speed'], ['tool_tilt_max_deg', 'Largest tool tilt'],
  ];
  const GROUPS = [['split', 'Split'], ['kind', 'Kind'], ['tags', 'Shape'], ['none', 'None']];
  const TABS = [
    ['overview', 'Overview'], ['limits', 'Limits'], ['joint', 'One joint'], ['joints', 'All joints'],
    ['position', 'Tool position'], ['orientation', 'Tool orientation'], ['trajectories', 'Trajectories'],
  ];

  const state = {
    tab: 'overview', page: null, prevTab: 'overview',
    joint: clamp(Number(load('joint', 0)) || 0, 0, JOINTS.length - 1),
    cmap: Color.NAMES.includes(load('cmap', 'viridis')) ? load('cmap', 'viridis') : 'viridis',
    reverse: !!load('reverse', false),
    scale: Color.SCALES.includes(load('scale', 'linear')) ? load('scale', 'linear') : 'linear',
    muted: load('muted', 'grey') === 'faded' ? 'faded' : 'grey',
    metric: load('metric', 'samples') === 'paths' ? 'paths' : 'samples',
    toolShow: load('toolShow', 'cells') === 'paths' ? 'paths' : 'cells',
    view: 'all', filter: '', where: null, sort: 'name', dir: 1, group: 'split', folded: new Set(),
    userViews: (load('views', []) || []).filter((v) => v && v.id && v.name),
  };
  let figs = [];

  // ── colours ───────────────────────────────────────────────────────────────────────────────────────────────────

  let lutCache = null;
  function ramp() {
    const key = state.cmap + (state.reverse ? ':r' : '');
    if (!lutCache || lutCache.key !== key) {
      const f = Color.ramp(state.cmap, state.reverse);
      const table = [];
      for (let k = 0; k < 256; k++) table.push(f(k / 255));
      lutCache = { key, f: (t) => table[Math.round(clamp(t, 0, 1) * 255)] };
    }
    return lutCache.f;
  }
  function rampGradient() {
    const f = ramp();
    const stops = [];
    for (let k = 0; k <= 8; k++) stops.push(rgbCss(f(k / 8)));
    return `linear-gradient(90deg, ${stops.join(', ')})`;
  }
  function mutedRgb(t, f) {
    if (state.muted === 'faded') { const c = f(t); return [0, 1, 2].map((i) => Math.round(c[i] + (255 - c[i]) * 0.74)); }
    const v = Math.round(229 - 108 * clamp(t, 0, 1));
    return [v, v, Math.max(0, v - 3)];
  }
  function mutedGradient() {
    const f = ramp();
    const stops = [];
    for (let k = 0; k <= 4; k++) stops.push(rgbCss(mutedRgb(k / 4, f)));
    return `linear-gradient(90deg, ${stops.join(', ')})`;
  }
  function scaleTitle() { return state.scale === 'enough' ? `≥ ${P.enough} samples / not` : Color.SCALE_TITLES[state.scale]; }

  /* The one colour rule under a selection (the thesis): the selection's cells keep the colour map (the dataset's count
   * there), cells ONLY the selection reaches turn cyan, the rest of the dataset is muted, white = never visited. */
  function painter(key, values, opts) {
    opts = opts || {};
    let focus = opts.focus || sel.names;
    if (isWhole(focus)) focus = [];
    const scaled = opts.scaled || Color.scale(values, state.scale, { enough: P.enough });
    const t = opts.t || scaled.t;
    const f = ramp();
    const grid = GRIDS.get(key);
    const c = focus.length && grid ? counts(key, focus) : null;
    const n = values.length;
    const rgb = new Array(n);
    const only = [];
    let reach = 0;
    for (let k = 0; k < n; k++) {
      const tk = t[k];
      if (c && c[k] > 0) {
        reach += 1;
        if (c[k] === grid.total[k]) { rgb[k] = ONLY; only.push(k); } else rgb[k] = f(tk >= 0 ? tk : 0);
      } else if (tk >= 0) rgb[k] = c ? mutedRgb(tk, f) : f(tk);
      else rgb[k] = opts.outside && opts.outside(k) ? Color.OUTSIDE : Color.EMPTY;
    }
    return { rgb, scaled, focus: c ? focus : [], only, reach, counts: c, grid, key };
  }
  function heatImage(nx, ny, rgb) {
    const image = document.createElement('canvas');
    image.width = nx;
    image.height = ny;
    const ig = image.getContext('2d');
    const data = ig.createImageData(nx, ny);
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < ny; j++) {
        const c = rgb[i * ny + j];
        const p = ((ny - 1 - j) * nx + i) * 4;
        data.data[p] = c[0]; data.data[p + 1] = c[1]; data.data[p + 2] = c[2]; data.data[p + 3] = 255;
      }
    }
    ig.putImageData(data, 0, 0);
    return image;
  }
  function drawHeat(g, box, nx, ny, paint) {
    g.save();
    g.imageSmoothingEnabled = false;
    g.drawImage(heatImage(nx, ny, paint.rgb), box.x, box.y, box.w, box.h);
    g.restore();
    const cw = box.w / nx;
    const ch = box.h / ny;
    if (paint.only.length && cw >= 3.5 && ch >= 3.5) {
      g.save();
      g.strokeStyle = 'rgba(0, 62, 92, 0.8)';
      g.lineWidth = 1;
      for (const k of paint.only) {
        const i = Math.floor(k / ny);
        const j = k % ny;
        g.strokeRect(box.x + i * cw + 0.5, box.y + box.h - (j + 1) * ch + 0.5, Math.max(1, cw - 1), Math.max(1, ch - 1));
      }
      g.restore();
    }
  }
  function cellAt(box, nx, ny, px, py) {
    if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return -1;
    const i = clamp(Math.floor(((px - box.x) / box.w) * nx), 0, nx - 1);
    const j = clamp(Math.floor(((box.y + box.h - py) / box.h) * ny), 0, ny - 1);
    return i * ny + j;
  }

  // ── tooltip + cell clicks ─────────────────────────────────────────────────────────────────────────────────────

  const tip = $('[data-v5-tip]');
  function showTip(clientX, clientY, html) {
    tip.innerHTML = html;
    tip.hidden = false;
    const width = tip.offsetWidth;
    const height = tip.offsetHeight;
    const left = clientX + 14 + width > global.innerWidth ? clientX - width - 12 : clientX + 14;
    const top = clientY + 16 + height > global.innerHeight ? clientY - height - 10 : clientY + 16;
    tip.style.left = Math.max(4, left) + 'px';
    tip.style.top = Math.max(4, top) + 'px';
  }
  function hideTip() { tip.hidden = true; }
  function hover(canvas, find, click) {
    canvas.addEventListener('mousemove', (event) => {
      const rect = canvas.getBoundingClientRect();
      const html = find(event.clientX - rect.left, event.clientY - rect.top);
      if (html) showTip(event.clientX, event.clientY, html); else hideTip();
      if (click) canvas.style.cursor = html ? 'pointer' : 'default';
    });
    canvas.addEventListener('mouseleave', hideTip);
    if (click) {
      canvas.addEventListener('click', (event) => {
        const rect = canvas.getBoundingClientRect();
        click(event.clientX - rect.left, event.clientY - rect.top, event);
      });
    }
  }
  function whoTip(paint, k) {
    const total = paint.grid ? paint.grid.total[k] : 0;
    let html = `<br><b>${total}</b> of ${ROWS.length} trajectories pass here`;
    if (paint.counts) {
      const c = paint.counts[k];
      html += ` · <b>${c}</b> selected`;
      if (c && c === total) html += ' — <b>only the selection</b>';
    }
    if (total) html += `<div class="hintline">click: select ${total === 1 ? 'the trajectory' : `the ${total} trajectories`} through this cell (⇧ adds)</div>`;
    return html;
  }
  function selectCell(paint, k, event) {
    const owners = (paint.grid && paint.grid.owners.get(k)) || [];
    const names = owners.map((index) => ROWS[index].name);
    if (!names.length) return;
    hideTip();
    if (event && (event.shiftKey || event.ctrlKey || event.metaKey)) setSelection(sel.names.concat(names), sel.anchor || names[0]);
    else setSelection(names, names[0]);
  }

  // ── figure scaffolding, legend, colour bar, switches ─────────────────────────────────────────────────────────

  function figure(id, title, opts) {
    opts = opts || {};
    const titleEl = el('span', { class: 'fig-title', text: title });
    const tools = el('div', { class: 'fig-tools' });
    const lead = el('p', { class: 'fig-lead' });
    const body = el('div', { class: 'fig-body' });
    const legend = el('div', { class: 'legend', 'data-v5-legend': '' });
    const how = opts.how ? el('p', { class: 'how', hidden: true, text: opts.how }) : null;
    const howBtn = opts.how ? el('button', { type: 'button', class: 'how-btn', title: 'How to read this', 'aria-label': 'How to read this', 'aria-expanded': 'false', text: '?' }) : null;
    if (howBtn) howBtn.addEventListener('click', () => { how.hidden = !how.hidden; howBtn.setAttribute('aria-expanded', String(!how.hidden)); });
    const node = el('section', { class: 'fig' + (opts.cls ? ' ' + opts.cls : ''), 'data-v5-fig': id }, [
      el('header', { class: 'fig-head' }, [el('h3', null, [titleEl, el('code', { class: 'fig-id', text: id })]), tools, howBtn]),
      how, lead, body, legend]);
    return { id, node, titleEl, tools, lead, body, legend, draw: null };
  }
  function mount(fig, draw) {
    fig.draw = () => {
      const width = Math.max(200, Math.floor(fig.body.clientWidth || fig.node.clientWidth - 30));
      fig.body.replaceChildren();
      try { draw(width); } catch (error) { console.warn('v5 figure', fig.id, error); fig.body.append(el('p', { class: 'loading', text: 'Could not draw: ' + error })); }
    };
    figs.push(fig);
    return fig;
  }
  /* items: {kind, colour?, label, note?}; kinds: ramp | grey | only | empty | outside | line | thin | dash | frame | fill | dot | text */
  function setLegend(fig, items) {
    fig.legend.replaceChildren();
    for (const item of items) {
      if (!item) continue;
      let swatch = null;
      if (item.kind !== 'text') {
        swatch = el('i', { class: 'sw ' + item.kind });
        if (item.kind === 'ramp') swatch.style.background = rampGradient();
        else if (item.kind === 'grey') swatch.style.background = mutedGradient();
        else if (item.kind === 'fill') swatch.style.background = item.colour;
        else if (item.kind === 'dot') { swatch.className = 'dot'; swatch.style.background = item.colour; }
        else if (item.colour) swatch.style.color = item.colour;
      }
      fig.legend.append(el('span', { class: 'li' }, [swatch, el('span', null, [item.label, item.note ? el('span', { class: 'note', text: ' ' + item.note }) : null])]));
    }
  }
  function focusLegend(paint, what, extra) {
    const items = [];
    const n = paint.focus.length;
    if (n) {
      items.push({ kind: 'ramp', label: `selected (${n} ${plural(n, 'trajectory', 'trajectories')})`, note: `— colour = ${what} there` });
      items.push({ kind: 'grey', label: `the rest of all ${ROWS.length}` });
      items.push({ kind: 'only', label: 'only the selection reaches' });
    } else {
      items.push({ kind: 'ramp', label: `colour = ${what}, all ${ROWS.length} trajectories`, note: `(${scaleTitle()})` });
    }
    items.push({ kind: 'empty', label: 'never visited' });
    return items.concat(extra || []);
  }
  function colorbar(scaled, title, height) {
    const h = Math.max(70, Math.round(height));
    const f = ramp();
    const bar = canvasOf(14, h);
    const positions = [];
    if (scaled.mode === 'visited') {
      bar.g.fillStyle = rgbCss(f(1)); bar.g.fillRect(0, 0, 14, h);
      positions.push({ y: 0.5, label: 'visited' });
    } else if (scaled.mode === 'enough') {
      bar.g.fillStyle = rgbCss(f(1)); bar.g.fillRect(0, 0, 14, h / 2);
      bar.g.fillStyle = rgbCss(f(0.25)); bar.g.fillRect(0, h / 2, 14, h / 2);
      for (const tick of scaled.ticks) positions.push({ y: tick.t >= 1 ? 0.75 : 0.25, label: tick.label });
    } else {
      for (let y = 0; y < h; y++) { bar.g.fillStyle = rgbCss(f(1 - y / Math.max(1, h - 1))); bar.g.fillRect(0, y, 14, 1); }
      for (const tick of scaled.ticks || []) positions.push({ y: tick.t, label: tick.label });
    }
    const labels = [];
    let last = -1;
    for (const item of positions.sort((a, b) => a.y - b.y)) {
      if (last >= 0 && (item.y - last) * h < 11) continue;
      labels.push(el('span', { class: 'cb-tick', style: `bottom:${(item.y * h).toFixed(1)}px`, text: minus(item.label) }));
      last = item.y;
    }
    return el('div', { class: 'colorbar' }, [
      el('div', { class: 'cb-title', text: title }),
      el('div', { class: 'cb-body', style: `height:${h}px` }, [bar.canvas, ...labels]),
      el('div', { class: 'cb-note', text: scaled.note || '' }),
    ]);
  }
  function segmented(label, options, value, onChange, attrs) {
    const box = el('div', Object.assign({ class: 'seg', role: 'group', 'aria-label': label }, attrs || {}));
    for (const [optionValue, optionLabel] of options) {
      box.append(el('button', {
        type: 'button', 'data-value': optionValue, 'aria-pressed': String(optionValue === value), text: optionLabel,
        onclick: () => onChange(optionValue),
      }));
    }
    return label ? el('span', { class: 'tool-group' }, [el('span', { class: 'seg-label', text: label }), box]) : box;
  }
  function metricSeg() {
    return segmented('colour =', [['samples', 'samples'], ['paths', 'trajectories']], state.metric, (value) => {
      state.metric = value; save('metric', value); redrawFigures();
    });
  }
  function metricWord(unit) { return state.metric === 'paths' ? `trajectories through the ${unit}` : `samples in the ${unit}`; }

  // ── samples.json: the selection's own 1-D histograms and the trajectory page's time series ───────────────────

  const samples = { state: 'idle', byName: null, error: null };
  function loadSamples() {
    if (samples.state !== 'idle') return;
    if (global.location.protocol === 'file:') { samples.state = 'failed'; samples.error = 'file://'; return; }
    samples.state = 'loading';
    fetch('../data/samples.json').then((response) => {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }).then((rows) => {
      const map = new Map();
      for (const row of rows) {
        let list = map.get(row.trajectory);
        if (!list) map.set(row.trajectory, (list = []));
        list.push(row);
      }
      samples.byName = map;
      samples.state = 'ready';
      if (state.page) renderContent(); else redrawFigures();
    }).catch((error) => {
      samples.state = 'failed';
      samples.error = String(error);
      if (state.page) renderContent(); else redrawFigures();
    });
  }
  function samplesNote() {
    if (samples.state === 'failed') return `samples.json is not reachable here (${samples.error}); serve the round: ${SERVE_CMD}`;
    return 'loading samples.json…';
  }
  /* the focus names' samples binned on the payload's own edges; column in display units, factor -> payload units */
  function subsetHist(names, column, factor, spec) {
    if (samples.state !== 'ready' || !names.length) return null;
    const [lo, hi, n] = spec;
    const out = new Float64Array(n);
    let min = Infinity;
    let max = -Infinity;
    let total = 0;
    for (const name of names) {
      for (const row of samples.byName.get(name) || []) {
        const v = row[column] * factor;
        if (!Number.isFinite(v)) continue;
        total += 1;
        if (v < min) min = v;
        if (v > max) max = v;
        const i = Math.floor(((v - lo) / (hi - lo)) * n);
        if (i >= 0 && i < n) out[i] += 1;
      }
    }
    return { counts: out, min, max, total };
  }

  // ── 1-D histogram with the selection on top ──────────────────────────────────────────────────────────────────

  /* o: {w, h, spec [lo, hi, n], counts, scale, unit, label, limit, p: [p001, p999] | null, sub: subsetHist | null,
   *     focused (bool), xtick (fn)} */
  function hist1d(o) {
    const { canvas, g } = canvasOf(o.w, o.h, { 'data-hist': '' });
    const m = { l: o.left === undefined ? 40 : o.left, r: 8, t: 6, b: o.label ? 34 : 22 };
    const box = { x: m.l, y: m.t, w: o.w - m.l - m.r, h: o.h - m.t - m.b - 6 };
    const [lo, hi, n] = o.spec;
    const x = { lo: lo * o.scale, hi: hi * o.scale, label: o.label, tickPad: 9, labelPad: 21, tickText: o.xtick };
    const nonzero = Array.from(o.counts).filter((v) => v > 0).sort((a, b) => a - b);
    const top = Math.max(1, quantile(nonzero, 0.98) * 1.08);
    const { sx } = mapper(box, x, { lo: 0, hi: 1 });
    const edge = (i) => sx((lo + ((hi - lo) * i) / n) * o.scale);
    if (o.limit && o.limit.source === 'limit') {
      g.fillStyle = 'rgba(221,220,214,0.55)';
      const a = sx(o.limit.low * o.scale);
      const b = sx(o.limit.high * o.scale);
      if (a > box.x) g.fillRect(box.x, box.y, a - box.x, box.h);
      if (b < box.x + box.w) g.fillRect(b, box.y, box.x + box.w - b, box.h);
    }
    const focused = o.focused;
    for (let i = 0; i < n; i++) {
      const c = o.counts[i];
      if (!c) continue;
      const x0 = edge(i);
      const x1 = edge(i + 1);
      const h = Math.min(1, c / top) * box.h;
      g.fillStyle = focused ? BAR_MUTED : BAR;
      g.fillRect(x0, box.y + box.h - h, Math.max(1, x1 - x0 - 0.4), h);
      if (c > top) { g.fillStyle = focused ? '#b9bcc0' : INK; g.fillRect(x0, box.y, Math.max(1, x1 - x0 - 0.4), 2); }
    }
    if (o.sub) {
      g.fillStyle = FOCUS;
      for (let i = 0; i < n; i++) {
        const c = o.sub.counts[i];
        if (!c) continue;
        const x0 = edge(i);
        const x1 = edge(i + 1);
        const h = Math.max(1.5, Math.min(1, c / top) * box.h);
        g.fillRect(x0, box.y + box.h - h, Math.max(1, x1 - x0 - 0.4), h);
      }
      if (Number.isFinite(o.sub.min)) {
        // the selection's reach as a rug under the axis: visible even when its bars are tiny next to the dataset's
        g.fillStyle = FOCUS;
        const a = clamp(sx(o.sub.min * o.scale), box.x, box.x + box.w);
        const b = clamp(sx(o.sub.max * o.scale), box.x, box.x + box.w);
        g.fillRect(a, box.y + box.h + 2, Math.max(2, b - a), 3);
      }
    }
    hline(g, box.y + box.h, box.x, box.x + box.w, AXIS);
    if (o.limit && o.limit.source === 'limit') {
      vline(g, sx(o.limit.low * o.scale), box.y, box.y + box.h, LIMIT, 1.5);
      vline(g, sx(o.limit.high * o.scale), box.y, box.y + box.h, LIMIT, 1.5);
    }
    if (o.p) {
      g.fillStyle = INK;
      for (const v of o.p) { const px = sx(v * o.scale); g.fillRect(Math.round(px), box.y - 1, 1.5, 6); }
    }
    drawAxes(g, box, x, null, { font: FONT_SMALL, xGap: 56 });
    hover(canvas, (px, py) => {
      if (px < box.x || px > box.x + box.w || py < box.y - 4 || py > box.y + box.h + 6) return null;
      const i = clamp(Math.floor(((px - box.x) / box.w) * n), 0, n - 1);
      const a = (lo + ((hi - lo) * i) / n) * o.scale;
      const b = (lo + ((hi - lo) * (i + 1)) / n) * o.scale;
      let html = `${esc(o.title || '')} ${fmt(a)} … ${fmt(b)}${o.unit || ''}<br><b>${count(o.counts[i])}</b> samples, all ${ROWS.length}`;
      if (o.sub) html += ` · <b>${count(o.sub.counts[i])}</b> selected <span style="opacity:.7">(subset count)</span>`;
      return html;
    });
    return canvas;
  }
  function histLegend(focused, extra) {
    const items = [];
    if (focused) {
      items.push({ kind: 'fill', colour: FOCUS, label: `selected (${sel.names.length})`, note: '— subset count, binned from samples.json' });
      items.push({ kind: 'fill', colour: BAR_MUTED, label: `all ${ROWS.length}` });
      items.push({ kind: 'line', colour: FOCUS, label: 'the selection\'s reach (min … max)' });
    } else {
      items.push({ kind: 'fill', colour: BAR, label: `samples, all ${ROWS.length} trajectories` });
    }
    return items.concat(extra || []);
  }

  // ── the joint planes (One joint, All joints, Overview minis) ─────────────────────────────────────────────────

  function planeFigure(fig, width, joint, plane, opts) {
    opts = opts || {};
    const pl = P.planes[joint.name][plane];
    const key = `p:${joint.name}:${plane}`;
    const values = state.metric === 'paths' ? pl.paths : pl.samples;
    const paint = painter(key, values);
    const [nx, ny] = pl.shape;
    const cbW = 96;
    const m = { l: 54, r: 8, t: 6, b: 36 };
    const canvasW = width - cbW - 10;
    const plotW = canvasW - m.l - m.r;
    const plotH = Math.round(Math.min(opts.maxH || 300, plotW * 0.64));
    const { canvas, g } = canvasOf(canvasW, plotH + m.t + m.b, { 'data-heat': '' });
    const box = { x: m.l, y: m.t, w: plotW, h: plotH };
    drawHeat(g, box, nx, ny, paint);
    const x = axisOf(joint, pl.x, pl.x_edges);
    const y = Object.assign(axisOf(joint, pl.y, pl.y_edges), { labelOffset: 44 });
    const { sx, sy } = mapper(box, x, y);
    if (y.lo < 0 && y.hi > 0) hline(g, sy(0), box.x, box.x + box.w, 'rgba(34,33,31,0.25)', 1, [2, 3]);
    if (x.lo < 0 && x.hi > 0 && pl.x !== 'q') vline(g, sx(0), box.y, box.y + box.h, 'rgba(34,33,31,0.25)', 1, [2, 3]);
    strokeBox(g, box, LIMIT, 1.5);
    drawAxes(g, box, x, y);
    const ex = (i) => (pl.x_edges[0] + ((pl.x_edges[1] - pl.x_edges[0]) * i) / nx) * joint.display.scale;
    const ey = (j) => (pl.y_edges[0] + ((pl.y_edges[1] - pl.y_edges[0]) * j) / ny) * joint.display.scale;
    hover(canvas, (px, py) => {
      const k = cellAt(box, nx, ny, px, py);
      if (k < 0) return null;
      const i = Math.floor(k / ny);
      const j = k % ny;
      return `${pl.x} ${fmt(ex(i))} … ${fmt(ex(i + 1))}${unitOf(joint, pl.x)}, ${pl.y} ${fmt(ey(j))} … ${fmt(ey(j + 1))}${unitOf(joint, pl.y)}<br><b>${count(pl.samples[k])}</b> samples${whoTip(paint, k)}`;
    }, (px, py, event) => { const k = cellAt(box, nx, ny, px, py); if (k >= 0) selectCell(paint, k, event); });
    fig.body.append(el('div', { class: 'heatrow' }, [canvas, colorbar(paint.scaled, state.metric === 'paths' ? 'trajectories per cell' : 'samples per cell', box.h)]));
    const lead = [`<b>${pct(pl.visited_pct)}</b> of ${count(nx * ny)} cells visited`, `${pct(pl.sufficient_pct)} with ≥ ${P.enough} samples`, `evenness ${pct(pl.evenness_pct)}`];
    if (paint.focus.length) lead.push(`selection: <b>${count(paint.reach)}</b> cells, <b style="color:#007fae">${count(paint.only.length)}</b> only it <span class="subset">(subset count from membership.json)</span>`);
    fig.lead.innerHTML = lead.join(' · ');
    setLegend(fig, focusLegend(paint, metricWord('cell'), [
      { kind: 'frame', colour: LIMIT, label: 'red frame = the limit box' },
      { kind: 'text', label: 'click a cell to select who goes there' },
    ]));
    return paint;
  }

  /* six small maps, one per joint, of one plane: the "whole dataset at a glance" strip */
  function miniPlanes(width, plane, focus, opts) {
    opts = opts || {};
    const cols = JOINTS.length;
    const gap = 12;
    const colW = Math.floor((width - gap * (cols - 1)) / cols);
    const grid = el('div', { class: 'minis', style: `grid-template-columns: repeat(${cols}, ${colW}px)` });
    let first = null;
    JOINTS.forEach((joint, index) => {
      const pl = P.planes[joint.name][plane];
      const key = `p:${joint.name}:${plane}`;
      const paint = painter(key, pl.samples, { focus });
      if (!first) first = paint;
      const [nx, ny] = pl.shape;
      const m = { l: 30, r: 12, t: 3, b: 16 };
      const plotW = colW - m.l - m.r;
      const plotH = Math.round(plotW * (opts.aspect || 0.62));
      const { canvas, g } = canvasOf(colW, plotH + m.t + m.b, { 'data-heat': '' });
      const box = { x: m.l, y: m.t, w: plotW, h: plotH };
      drawHeat(g, box, nx, ny, paint);
      const x = axisOf(joint, pl.x, pl.x_edges);
      const y = axisOf(joint, pl.y, pl.y_edges);
      const { sy } = mapper(box, x, y);
      if (y.lo < 0 && y.hi > 0) hline(g, sy(0), box.x, box.x + box.w, 'rgba(34,33,31,0.22)', 1, [2, 3]);
      strokeBox(g, box, LIMIT, 1);
      drawAxes(g, box, Object.assign({}, x, { label: null, ticks: [x.lo, 0, x.hi].filter((v, i, a) => a.indexOf(v) === i), tickPad: 3 }),
        Object.assign({}, y, { label: null, ticks: [y.lo, 0, y.hi] }), { font: FONT_SMALL, inset: true });
      const ex = (i) => (pl.x_edges[0] + ((pl.x_edges[1] - pl.x_edges[0]) * i) / nx) * joint.display.scale;
      const ey = (j) => (pl.y_edges[0] + ((pl.y_edges[1] - pl.y_edges[0]) * j) / ny) * joint.display.scale;
      hover(canvas, (px, py) => {
        const k = cellAt(box, nx, ny, px, py);
        if (k < 0) return null;
        const i = Math.floor(k / ny);
        const j = k % ny;
        return `<b>${esc(joint.name)}</b><br>${pl.x} ${fmt(ex(i))} … ${fmt(ex(i + 1))}${unitOf(joint, pl.x)}, ${pl.y} ${fmt(ey(j))} … ${fmt(ey(j + 1))}${unitOf(joint, pl.y)}<br><b>${count(pl.samples[k])}</b> samples${whoTip(paint, k)}`;
      }, (px, py, event) => { const k = cellAt(box, nx, ny, px, py); if (k >= 0) selectCell(paint, k, event); });
      const title = el('div', { class: 'mini-title' }, [
        el('button', { type: 'button', text: short(joint.name), title: `Open ${joint.name} on the One joint tab`, onclick: () => { selectJoint(index); go('joint'); } }),
        el('span', { class: 'muted', text: `${pct(pl.visited_pct)} visited` })]);
      const cap = el('div', { class: 'mini-cap' });
      if (paint.focus.length) cap.innerHTML = `reaches <b>${count(paint.reach)}</b> · <span class="only-n">${count(paint.only.length)} only ${paint.focus.length === 1 ? 'it' : 'these'}</span>`;
      else cap.textContent = `${count(pl.samples.filter((v) => v > 0).length)} of ${count(nx * ny)} cells`;
      grid.append(el('div', { class: 'mini' }, [title, canvas, cap]));
    });
    return { node: grid, paint: first };
  }

  // ── the tool: projections and the direction disk ──────────────────────────────────────────────────────────────

  const VIEWS = [['xy', 'from above', 'x', 'y', [0, 1]], ['xz', 'from the front', 'x', 'z', [0, 2]], ['yz', 'from the side', 'y', 'z', [1, 2]]];

  /* opts: {k px per metre, focus, show: cells|paths, path: name (draw its line), small, scaled (shared), values} */
  function projectionPanel(viewDef, opts) {
    const [key, title, u, v, axes] = viewDef;
    const view = P.tool.projections[key];
    const pixel = P.tool.pixel_m;
    const [nu, nv] = view.shape;
    const w = Math.max(30, Math.round(nu * pixel * opts.k));
    const h = Math.max(30, Math.round(nv * pixel * opts.k));
    const left = opts.small ? 30 : 46;
    const bottom = opts.small ? 16 : 34;
    const { canvas, g } = canvasOf(left + w + 12, h + 4 + bottom, { 'data-heat': '' });
    const box = { x: left, y: 4, w, h };
    const values = state.metric === 'paths' ? view.paths : view.samples;
    const reachable = view.reachable;
    const outside = reachable ? (cell) => !reachable[cell] : null;
    let paint;
    if (opts.show === 'paths') {
      // footprint only: where anyone went (light), where the robot cannot go (grey); the lines carry the story
      const rgb = new Array(nu * nv);
      for (let c = 0; c < nu * nv; c++) rgb[c] = view.samples[c] > 0 ? [236, 235, 231] : outside && outside(c) ? Color.OUTSIDE : Color.EMPTY;
      paint = { rgb, only: [], focus: [], reach: 0, scaled: null, counts: null, grid: GRIDS.get(key) };
      drawHeat(g, box, nu, nv, paint);
    } else {
      paint = painter(key, values, { focus: opts.focus, outside, t: opts.t, scaled: opts.scaled });
      drawHeat(g, box, nu, nv, paint);
    }
    const x = { lo: view.origin[0] * 1000, hi: (view.origin[0] + nu * pixel) * 1000, label: opts.small ? null : `${u} (mm)` };
    const y = { lo: view.origin[1] * 1000, hi: (view.origin[1] + nv * pixel) * 1000, label: opts.small ? null : `${v} (mm)`, labelOffset: 38 };
    const { sx, sy } = mapper(box, x, y);
    const toPx = (point) => [sx(point[axes[0]] * 1000), sy(point[axes[1]] * 1000)];
    if (opts.show === 'paths' || opts.path) {
      const focus = opts.focus || sel.names;
      const focusSet = new Set(focus);
      g.save();
      g.beginPath();
      g.rect(box.x, box.y, box.w, box.h);
      g.clip();
      g.lineJoin = 'round';
      if (opts.show === 'paths') {
        g.strokeStyle = focus.length ? 'rgba(90,90,86,0.13)' : 'rgba(60,60,56,0.28)';
        g.lineWidth = 1;
        for (const row of ROWS) {
          if (focusSet.has(row.name)) continue;
          strokeLine(g, P.tool.spaghetti[payloadIndex.get(row.name)], toPx);
        }
      }
      const drawn = opts.path ? [opts.path] : focus;
      g.strokeStyle = opts.path ? 'rgba(20,20,18,0.75)' : FOCUS;
      g.lineWidth = opts.path ? 1.2 : 1.7;
      for (const name of drawn) strokeLine(g, P.tool.spaghetti[payloadIndex.get(name)], toPx);
      if (drawn.length && drawn.length <= 3) {
        for (const name of drawn) {
          const points = P.tool.spaghetti[payloadIndex.get(name)];
          if (!points || !points.length) continue;
          const [ax, ay] = toPx(points[0]);
          const [bx, by] = toPx(points[points.length - 1]);
          g.fillStyle = '#fff'; g.strokeStyle = INK; g.lineWidth = 1.3;
          g.beginPath(); g.arc(ax, ay, 3.5, 0, 2 * Math.PI); g.fill(); g.stroke();
          g.fillStyle = INK; g.fillRect(bx - 3, by - 3, 6, 6);
        }
      }
      g.restore();
    }
    if (x.lo <= 0 && x.hi >= 0 && y.lo <= 0 && y.hi >= 0) {
      g.strokeStyle = INK; g.lineWidth = 1.2;
      g.beginPath(); g.moveTo(sx(0) - 5, sy(0)); g.lineTo(sx(0) + 5, sy(0)); g.moveTo(sx(0), sy(0) - 5); g.lineTo(sx(0), sy(0) + 5); g.stroke();
    }
    strokeBox(g, box, AXIS, 1);
    drawAxes(g, box, Object.assign({}, x, opts.small ? { ticks: ticks(x.lo, x.hi, 2), tickPad: 3 } : {}),
      Object.assign({}, y, opts.small ? { ticks: ticks(y.lo, y.hi, 2) } : {}), { font: opts.small ? FONT_SMALL : FONT, inset: !!opts.small });
    hover(canvas, (px, py) => {
      const cell = cellAt(box, nu, nv, px, py);
      if (cell < 0) return null;
      const i = Math.floor(cell / nv);
      const j = cell % nv;
      const u0 = (view.origin[0] + i * pixel) * 1000;
      const v0 = (view.origin[1] + j * pixel) * 1000;
      let html = `<b>${title}</b> · ${u} ${fmt(u0)} … ${fmt(u0 + pixel * 1000)} mm, ${v} ${fmt(v0)} … ${fmt(v0 + pixel * 1000)} mm<br><b>${count(view.samples[cell])}</b> samples`;
      if (view.max_speed[cell] !== null) html += ` · fastest ${view.max_speed[cell].toFixed(2)} m/s`;
      if (reachable && !reachable[cell]) html += '<br>the robot cannot reach this pixel';
      return html + (opts.show === 'paths' ? '' : whoTip(paint.counts ? paint : Object.assign({}, paint, { counts: null }), cell));
    }, opts.show === 'paths' ? null : (px, py, event) => { const cell = cellAt(box, nu, nv, px, py); if (cell >= 0) selectCell(paint, cell, event); });
    const visited = view.samples.filter((value) => value > 0).length;
    const head = opts.small
      ? el('div', { class: 'mini-title' }, [el('b', { text: title }), el('span', { class: 'muted', text: `${u}, ${v}` })])
      : el('div', { class: 'mini-title', style: `padding-left:${left}px` }, [el('b', { text: title }), el('span', { class: 'muted', text: `(${u}, ${v}) · ${count(visited)} pixels visited` })]);
    const cap = el('div', { class: 'mini-cap', style: opts.small ? '' : `padding-left:${left}px` });
    if (paint.focus && paint.focus.length) cap.innerHTML = `reaches <b>${count(paint.reach)}</b> px · <span class="only-n">${count(paint.only.length)} only ${paint.focus.length === 1 ? 'it' : 'these'}</span>`;
    else if (opts.small) cap.textContent = `${count(visited)} pixels visited`;
    return { node: el('div', { class: 'mini' }, [head, canvas, cap]), paint, width: left + w + 12 };
  }
  function strokeLine(g, points, toPx) {
    if (!points || points.length < 2) return;
    g.beginPath();
    points.forEach((point, i) => { const [px, py] = toPx(point); if (i) g.lineTo(px, py); else g.moveTo(px, py); });
    g.stroke();
  }
  function sharedProjectionScale() {
    const values = [].concat(...VIEWS.map(([key]) => (state.metric === 'paths' ? P.tool.projections[key].paths : P.tool.projections[key].samples)));
    // WHY one scale over the three views: each sample lands in exactly one pixel of every view, so they compare
    const scaled = Color.scale(values, state.scale, { enough: P.enough });
    let offset = 0;
    const slices = {};
    for (const [key] of VIEWS) { const s = P.tool.projections[key].shape; slices[key] = scaled.t.subarray(offset, offset + s[0] * s[1]); offset += s[0] * s[1]; }
    return { scaled, slices };
  }

  /* the direction disk: the sphere's equal-area cells (rings of base z, sectors of azimuth) on a Lambert disk,
   * centre = the tool pointing straight down (the reference), rim = pointing straight up */
  function directionDisk(size, opts) {
    opts = opts || {};
    const sphere = P.tool.orientation.sphere;
    const rings = sphere.rings;
    const sectors = sphere.sectors;
    const paint = painter('dir', sphere.counts, { focus: opts.focus });
    const pad = opts.small ? 14 : 22;
    const { canvas, g } = canvasOf(size, size, { 'data-heat': '' });
    const cx = size / 2;
    const cy = size / 2;
    const R = size / 2 - pad;
    const onlySet = new Set(paint.only);
    for (let r = 0; r < rings; r++) {
      const r0 = R * Math.sqrt(r / rings);
      const r1 = R * Math.sqrt((r + 1) / rings);
      for (let s = 0; s < sectors; s++) {
        const a0 = -Math.PI + (s * 2 * Math.PI) / sectors;
        const a1 = a0 + (2 * Math.PI) / sectors;
        const k = r * sectors + s;
        g.beginPath();
        g.arc(cx, cy, r1, -a0, -a1, true);
        g.arc(cx, cy, r0, -a1, -a0, false);
        g.closePath();
        g.fillStyle = rgbCss(paint.rgb[k]);
        g.fill();
        g.strokeStyle = onlySet.has(k) ? 'rgba(0,62,92,0.85)' : 'rgba(255,255,255,0.55)';
        g.lineWidth = onlySet.has(k) ? 1.2 : 0.6;
        g.stroke();
      }
    }
    g.save();
    g.strokeStyle = 'rgba(34,33,31,0.55)';
    g.setLineDash([3, 3]);
    g.beginPath(); g.arc(cx, cy, R * Math.sqrt(0.5), 0, 2 * Math.PI); g.stroke();
    g.setLineDash([]);
    g.strokeStyle = AXIS;
    g.beginPath(); g.arc(cx, cy, R, 0, 2 * Math.PI); g.stroke();
    g.restore();
    g.fillStyle = MUTED;
    g.font = opts.small ? FONT_SMALL : FONT;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText('+x', cx + R + pad / 2, cy);
    g.fillText('+y', cx, cy - R - pad / 2 + 1);
    if (!opts.small) {
      g.fillStyle = SOFT;
      g.fillText('horizontal', cx, cy - R * Math.sqrt(0.5) - 7);
      g.fillText('↓ down', cx, cy);
    }
    hover(canvas, (px, py) => {
      const dx = px - cx;
      const dy = cy - py;
      const dist = Math.hypot(dx, dy);
      if (dist > R) return null;
      const r = Math.min(rings - 1, Math.floor((dist / R) ** 2 * rings));
      const az = Math.atan2(dy, dx);
      const s = clamp(Math.floor(((az + Math.PI) / (2 * Math.PI)) * sectors), 0, sectors - 1);
      const k = r * sectors + s;
      const z0 = -1 + (2 * r) / rings;
      const z1 = -1 + (2 * (r + 1)) / rings;
      const t0 = Math.acos(clamp(-z0, -1, 1)) * DEG;
      const t1 = Math.acos(clamp(-z1, -1, 1)) * DEG;
      const a = -180 + (s * 360) / sectors;
      return `tool z: tilt ${Math.round(t0)}° … ${Math.round(t1)}° from straight down, leaning toward azimuth ${Math.round(a)}° … ${Math.round(a + 360 / sectors)}°<br><b>${count(sphere.counts[k])}</b> samples${whoTip(paint, k)}`;
    }, (px, py, event) => {
      const dx = px - cx;
      const dy = cy - py;
      const dist = Math.hypot(dx, dy);
      if (dist > R) return;
      const r = Math.min(rings - 1, Math.floor((dist / R) ** 2 * rings));
      const s = clamp(Math.floor(((Math.atan2(dy, dx) + Math.PI) / (2 * Math.PI)) * sectors), 0, sectors - 1);
      selectCell(paint, r * sectors + s, event);
    });
    return { canvas, paint };
  }

  // ── tabs ──────────────────────────────────────────────────────────────────────────────────────────────────────

  function numberText(row) {
    const value = row.value;
    if (row.unit === '%') return pct(value);
    if (row.unit === 's') return duration(value);
    if (row.unit === 'deg') return Math.round(value) + '°';
    if (row.unit === 'm/s') return value.toFixed(2) + ' m/s';
    if (!row.unit) return Number.isInteger(value) || Math.abs(value) >= 100 ? count(value) : fmt(value);
    return fmt(value) + ' ' + row.unit;
  }
  function numberByKey(key) { const row = P.numbers.find((item) => item.key === key); return row ? row.value : null; }

  function buildStats() {
    const source = P.source;
    const spans = JOINTS.map((joint) => ({ name: joint.name, span: P.hist[joint.name].q.span_pct }));
    const least = spans.reduce((a, b) => (b.span < a.span ? b : a));
    const answer = `<b>${count(source.trajectories)} trajectories</b>, ${duration(source.duration_s)} of motion. The joints use a median <b>${pct(numberByKey('q_span_median_pct'))}</b> of their position range (least: ${esc(short(least.name))}, ${pct(least.span)}); the fastest reaches <b>${pct(numberByKey('qd_peak_max_pct'))}</b> of its speed limit. On average <b>${pct(numberByKey('q_qd_visited_mean_pct'))}</b> of a joint's position × speed cells are visited. The tool passes through <b>${count(numberByKey('tool_voxels_visited'))}</b> 5 cm voxels and points in <b>${pct(numberByKey('tool_directions_visited_pct'))}</b> of all directions.`;
    // WHY a key/value sheet, not 15 cards: the numbers stay readable whole (no clipped labels) in ~100 px, so the
    // overview still shows the whole dataset's maps above the fold
    const sheet = el('dl', { class: 'kv' });
    for (const row of P.numbers) {
      sheet.append(el('div', { title: row.key }, [el('dt', { text: row.label }), el('dd', { text: numberText(row) })]));
    }
    return el('div', { class: 'stats', 'data-v5-stats': '' }, [el('p', { class: 'answer', html: answer }), sheet]);
  }

  function buildOverview(root) {
    root.append(buildStats());
    const joints = figure('ov-joints', 'Every joint at a glance — which positions and speeds does it visit?', {
      how: 'One map per joint: x = position, y = speed, each map spanning exactly the joint\'s limits (red frame). Colour = samples in the cell. Select trajectories in the list on the left: their cells keep the colour, the rest of the dataset goes grey, and the cells only they reach turn cyan. Click a cell to select the trajectories through it; click a joint name to open it on One joint.',
    });
    mount(joints, (width) => {
      const { node, paint } = miniPlanes(width, 'q_qd', sel.names);
      joints.body.append(node);
      setLegend(joints, focusLegend(paint, 'samples in the cell', [{ kind: 'frame', colour: LIMIT, label: 'the limit box' },
        { kind: 'text', label: 'x = position (°), y = speed (°/s)' }]));
    });
    const tool = figure('ov-tool', 'The tool at a glance — where does it go, which way does it point?', {
      how: 'Three projections of the tool path in the cell frame (2 cm pixels, one shared colour scale) and the direction disk: every direction the tool z axis can point, as equal-area cells; centre = straight down (the reference), dashed ring = horizontal, rim = straight up. Grey pixels are out of the robot\'s reach.',
    });
    mount(tool, (width) => {
      const gaps = 3 * 14;
      const side = Math.floor(Math.min(172, (width - gaps - 3 * 42) / 4));
      const disk = side;
      const k = side / (114 * P.tool.pixel_m);
      const shared = sharedProjectionScale();
      const row = el('div', { style: 'display:flex;gap:14px;align-items:flex-start' });
      let paint = null;
      for (const view of VIEWS) {
        const panel = projectionPanel(view, { k, focus: sel.names, small: true, t: shared.slices[view[0]], scaled: shared.scaled });
        if (!paint) paint = panel.paint;
        row.append(panel.node);
      }
      const dir = directionDisk(disk, { focus: sel.names, small: true });
      const cap = el('div', { class: 'mini-cap' });
      if (dir.paint.focus.length) cap.innerHTML = `reaches <b>${dir.paint.reach}</b> · <span class="only-n">${dir.paint.only.length} only ${dir.paint.focus.length === 1 ? 'it' : 'these'}</span>`;
      else cap.textContent = `${pct(numberByKey('tool_directions_visited_pct'))} of directions`;
      row.append(el('div', { class: 'mini' }, [el('div', { class: 'mini-title' }, [el('b', { text: 'pointing' }), el('span', { class: 'muted', text: 'centre = down' })]), dir.canvas, cap]));
      tool.body.append(row);
      setLegend(tool, focusLegend(paint, 'samples', [{ kind: 'outside', label: 'out of reach' }, { kind: 'text', label: `frame "${P.tool.frame}", 2 cm pixels` }]));
    });
    const adds = figure('ov-adds', 'What the selection adds', {
      how: 'Cells summed over every grid of that kind (all six joints for the joint planes). "all 54" counts the cells any trajectory visits (it matches the payload\'s own numbers); "selected" the cells the selection visits; "only these" the cells no other trajectory visits — the ones you would lose without the selection. Counted from membership.json: a subset count, not the payload.',
    });
    mount(adds, () => drawAdds(adds));
    root.append(joints.node, el('div', { class: 'ov-row' }, [tool.node, adds.node]));
  }

  const ADD_ROWS = [
    ['Position × speed', () => JOINTS.map((j) => `p:${j.name}:q_qd`), 'joint cells, all six joints'],
    ['Speed × accel.', () => JOINTS.map((j) => `p:${j.name}:qd_qdd`), 'joint speed × acceleration cells, all six joints'],
    ['Position × accel.', () => JOINTS.map((j) => `p:${j.name}:q_qdd`), 'joint position × acceleration cells, all six joints'],
    ['Tool pixels, xy', () => ['xy'], 'tool pixels seen from above (2 cm)'],
    ['Tool voxels', () => ['vox'], 'tool voxels (5 cm)'],
    ['Tool directions', () => ['dir'], 'tool z directions (equal-area sphere cells)'],
  ];
  function drawAdds(fig) {
    const focus = isWhole(sel.names) ? [] : sel.names;
    const table = el('table', { class: 'adds', 'data-v5-adds': '' });
    table.append(el('thead', null, [el('tr', null, [el('th', { class: 'l', text: 'cells' }), el('th', { text: `all ${ROWS.length}` }), el('th', { text: 'selected' }), el('th', { html: '<i class="sw only"></i> only' })])]));
    const body = el('tbody');
    for (const [label, keys, long] of ADD_ROWS) {
      let all = 0;
      let reach = 0;
      let only = 0;
      for (const key of keys()) {
        const total = GRIDS.get(key).total;
        for (let k = 0; k < total.length; k++) if (total[k]) all += 1;
        if (focus.length) { const r = reachOf(key, focus); reach += r.reach; only += r.only; }
      }
      const share = all ? (reach / all) * 100 : 0;
      body.append(el('tr', null, [
        el('td', { class: 'l', text: label, title: long }),
        el('td', { text: count(all) }),
        el('td', null, focus.length ? [el('span', { class: 'mbar' }, [el('i', { style: `width:${share.toFixed(1)}%` })]), count(reach)] : ['—']),
        el('td', { class: focus.length && only ? 'only-n' : '', text: focus.length ? count(only) : '—' })]));
    }
    table.append(body);
    fig.body.append(table);
    fig.lead.innerHTML = focus.length
      ? `${focus.length === 1 ? esc(focus[0].replace(/^workspace-/, '')) : `${focus.length} selected`} <span class="subset">· subset counts from membership.json</span>`
      : 'Select trajectories on the left: how many cells they reach, and how many only they reach.';
  }

  function buildLimits(root) {
    const fig = figure('limit-bars', 'How much of its limits does each joint use?', {
      how: 'One row per joint, one column per signal: the samples\' histogram on an axis that runs 8 % past the limit, the limits as red lines (shaded beyond), black ticks at the data\'s 0.1st and 99.9th percentile. Bars taller than the scale (linear, clipped at the 98th percentile) get a dark cap. With a selection, its own histogram is drawn in blue on the same scale (binned from samples.json, a subset count), and the blue rug under the axis spans its min … max, so even a short trajectory shows where it went.',
    });
    mount(fig, (width) => {
      const signals = ['q', 'qd', 'qdd', 'qddd'];
      const labelW = 112;
      const colW = Math.floor((width - labelW) / signals.length);
      const focus = isWhole(sel.names) ? [] : sel.names;
      const focused = focus.length > 0;
      const table = el('div', { style: `display:grid;grid-template-columns:${labelW}px repeat(${signals.length}, ${colW}px);align-items:center;row-gap:2px` });
      table.append(el('div'));
      for (const signal of signals) {
        const limit = P.limits[JOINTS[0].name][signal];
        table.append(el('div', { style: 'font-size:11.5px;font-weight:600;color:#52514e;padding:0 0 2px 40px', html: `${signal} · ${SIGNAL_WORD[signal]} <span style="font-weight:400;color:#8a8983">(${unitOf(JOINTS[0], signal).trim()}, limit ±${fmt(Math.abs(limit.high) * JOINTS[0].display.scale)})</span>` }));
      }
      for (const joint of JOINTS) {
        const hq = P.hist[joint.name].q;
        table.append(el('div', { style: 'font-size:12px', html: `<b>${esc(short(joint.name))}</b><br><span style="color:#8a8983;font-size:11px">range used ${pct(hq.span_pct)}</span>` }));
        for (const signal of signals) {
          const h = P.hist[joint.name][signal];
          const sub = focused && SAMPLE_COLUMN[signal] ? subsetHist(focus, short(joint.name) + SAMPLE_COLUMN[signal], 1 / DEG, h.edges) : null;
          table.append(hist1d({ w: colW, h: 74, spec: h.edges, counts: h.counts, scale: joint.display.scale, unit: unitOf(joint, signal),
            title: `${short(joint.name)} ${signal}`, limit: P.limits[joint.name][signal], p: [h.p001, h.p999], sub, focused, left: 40 }));
        }
      }
      fig.body.append(table);
      const notes = [];
      if (focused && samples.state !== 'ready') notes.push(samplesNote());
      if (focused) notes.push('jerk (qddd) has no selection overlay: samples.json carries q, qd, qdd only');
      fig.lead.textContent = notes.join(' · ');
      setLegend(fig, histLegend(focused, [
        { kind: 'line', colour: LIMIT, label: 'the limit (shaded beyond)' },
        { kind: 'thin', colour: INK, label: 'black ticks = p0.1 / p99.9 of the data' },
      ]));
    });
    root.append(fig.node);
  }

  function selectJoint(index) { state.joint = index; save('joint', index); }

  function buildJoint(root) {
    const picker = el('div', { class: 'seg', role: 'group', 'aria-label': 'Joint', 'data-v5-joint-picker': '' });
    JOINTS.forEach((joint, index) => {
      picker.append(el('button', { type: 'button', 'data-joint': String(index), 'aria-pressed': String(index === state.joint), text: short(joint.name),
        title: joint.name, onclick: () => { selectJoint(index); renderContent(); } }));
    });
    const metricBox = el('span');
    const paintMetric = () => metricBox.replaceChildren(segmented('colour =', [['samples', 'samples'], ['paths', 'trajectories']], state.metric, (value) => {
      state.metric = value; save('metric', value); paintMetric(); redrawFigures();
    }));
    paintMetric();
    root.append(el('div', { class: 'toolbar' }, [el('span', { class: 'lbl', text: 'Joint' }), picker,
      el('span', { class: 'help', text: 'the joint every figure on this tab shows' }), el('span', { style: 'margin-left:auto' }, [metricBox])]));
    const joint = JOINTS[state.joint];
    const grid = el('div', { class: 'grid2' });
    const titles = {
      q_qd: `Which positions and speeds does ${short(joint.name)} visit?`,
      qd_qdd: `Which speeds and accelerations does ${short(joint.name)} combine?`,
      q_qdd: `Where in its range does ${short(joint.name)} accelerate?`,
    };
    for (const plane of PLANES) {
      const fig = figure('joint-' + plane.replace('_', '-'), titles[plane], {
        how: `Every ${PLANE_WORDS[plane]} cell of the joint's limit box (the red frame; the plot spans exactly the limits). Colour = samples in the cell (or, switched, distinct trajectories through it). Under a selection the selection's cells keep the colour, the rest goes grey, and cyan cells are reached by the selection and nobody else. Click a cell to select who goes there.`,
      });
      mount(fig, (width) => planeFigure(fig, width, joint, plane));
      grid.append(fig.node);
    }
    const paths = figure('joint-paths', `How does each trajectory move through ${short(joint.name)}'s position × speed?`, {
      how: 'Every trajectory\'s (position, speed) path, up to 400 evenly picked points each (the payload\'s own paths). Grey = the dataset; blue = the selection. Hover a line to name it, click to select it (⇧ adds).',
    });
    mount(paths, (width) => drawPaths(paths, width, joint));
    grid.append(paths.node);
    root.append(grid);
  }

  function drawPaths(fig, width, joint) {
    const pl = P.planes[joint.name].q_qd;
    const m = { l: 54, r: 8, t: 6, b: 36 };
    const plotW = width - m.l - m.r - 106;
    const plotH = Math.round(Math.min(300, plotW * 0.64));
    const { canvas, g } = canvasOf(width, plotH + m.t + m.b, { 'data-paths': '' });
    const box = { x: m.l, y: m.t, w: plotW, h: plotH };
    const x = axisOf(joint, 'q', pl.x_edges);
    const y = Object.assign(axisOf(joint, 'qd', pl.y_edges), { labelOffset: 44 });
    const { sx, sy } = mapper(box, x, y);
    const scale = joint.display.scale;
    const focus = isWhole(sel.names) ? [] : sel.names;
    const focusSet = new Set(focus);
    const screen = [];
    g.save();
    g.beginPath(); g.rect(box.x, box.y, box.w, box.h); g.clip();
    hline(g, sy(0), box.x, box.x + box.w, 'rgba(34,33,31,0.25)', 1, [2, 3]);
    g.lineJoin = 'round';
    const drawOne = (row, colour, widthPx) => {
      const path = P.paths[joint.name][payloadIndex.get(row.name)];
      if (!path) return;
      const [qs, qds] = path;
      g.strokeStyle = colour;
      g.lineWidth = widthPx;
      g.beginPath();
      for (let i = 0; i < qs.length; i++) {
        const px = sx(qs[i] * scale);
        const py = sy(qds[i] * scale);
        if (i) g.lineTo(px, py); else g.moveTo(px, py);
        screen.push([px, py, row.index]);
      }
      g.stroke();
    };
    for (const row of ROWS) if (!focusSet.has(row.name)) drawOne(row, focus.length ? 'rgba(90,90,86,0.14)' : 'rgba(60,60,56,0.3)', 1);
    for (const name of focus) drawOne(byName.get(name), FOCUS, 1.8);
    g.restore();
    strokeBox(g, box, LIMIT, 1.5);
    drawAxes(g, box, x, y);
    const nearest = (px, py) => {
      let best = null;
      let bestD = 64;
      for (const [qx, qy, index] of screen) { const d = (qx - px) ** 2 + (qy - py) ** 2; if (d < bestD) { bestD = d; best = index; } }
      return best;
    };
    hover(canvas, (px, py) => {
      if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
      const index = nearest(px, py);
      if (index === null) return null;
      const row = ROWS[index];
      return `<b>${esc(row.name)}</b> · ${esc(row.tags.kind)}<br>${count(row.new_cells)} new cells · ${count(row.only_it_q_qd_cells)} only it<div class="hintline">click to select (⇧ adds)</div>`;
    }, (px, py, event) => {
      const index = nearest(px, py);
      if (index === null) return;
      const name = ROWS[index].name;
      if (event.shiftKey || event.ctrlKey || event.metaKey) setSelection(sel.names.concat([name]), name); else setSelection([name], name);
    });
    fig.body.append(canvas);
    fig.lead.innerHTML = focus.length ? `${focus.length} selected ${plural(focus.length, 'path')} in blue over the other ${ROWS.length - focus.length}` : `${ROWS.length} paths; hover one to name it`;
    setLegend(fig, [
      { kind: 'line', colour: focus.length ? FOCUS : 'rgba(60,60,56,0.5)', label: focus.length ? 'selected trajectories' : 'one trajectory each' },
      focus.length ? { kind: 'line', colour: 'rgba(90,90,86,0.3)', label: 'the rest' } : null,
      { kind: 'frame', colour: LIMIT, label: 'the limit box' },
    ]);
  }

  function buildJoints(root) {
    const ranges = figure('ranges', 'How far does each joint go, against its limits?', {
      how: 'One row per joint, one column per signal, each on its own limit: the left end is the low limit (−100 %), the right end the high limit (+100 %). The grey bar spans the dataset\'s 0.1st … 99.9th percentile (from the payload). With a selection, the blue bar is its min … max (a subset count from samples.json).',
    });
    mount(ranges, (width) => drawRanges(ranges, width));
    const matrix = figure('matrix', 'Every joint, every plane — the whole joint space side by side', {
      how: 'Rows are joints, columns the three planes (position × speed, speed × acceleration, position × acceleration). Each map spans exactly its limits. Selection colouring as everywhere: colour = the selection\'s cells, grey = the rest, cyan = only the selection.',
    });
    mount(matrix, (width) => {
      const cols = 3;
      const gap = 14;
      const colW = Math.floor((width - 110 - gap * (cols - 1)) / cols);
      const grid = el('div', { style: `display:grid;grid-template-columns:110px repeat(${cols}, ${colW}px);gap:6px ${gap}px;align-items:center` });
      grid.append(el('div'));
      for (const plane of PLANES) grid.append(el('div', { style: 'font-size:11.5px;font-weight:600;color:#52514e;padding-left:30px', text: PLANE_WORDS[plane] }));
      let paint = null;
      JOINTS.forEach((joint, index) => {
        grid.append(el('div', { style: 'font-size:12px' }, [el('button', { type: 'button', class: 'link', style: 'font-weight:600;color:#22211f', text: short(joint.name), onclick: () => { selectJoint(index); go('joint'); } })]));
        for (const plane of PLANES) {
          const pl = P.planes[joint.name][plane];
          const key = `p:${joint.name}:${plane}`;
          const p = painter(key, pl.samples);
          if (!paint) paint = p;
          const [nx, ny] = pl.shape;
          const m = { l: 30, r: 12, t: 3, b: 16 };
          const plotW = colW - m.l - m.r;
          const plotH = Math.round(Math.min(120, plotW * 0.4));
          const { canvas, g } = canvasOf(colW, plotH + m.t + m.b, { 'data-heat': '' });
          const box = { x: m.l, y: m.t, w: plotW, h: plotH };
          drawHeat(g, box, nx, ny, p);
          const x = axisOf(joint, pl.x, pl.x_edges);
          const y = axisOf(joint, pl.y, pl.y_edges);
          strokeBox(g, box, LIMIT, 1);
          drawAxes(g, box, Object.assign({}, x, { label: null, ticks: [x.lo, 0, x.hi], tickPad: 3 }), Object.assign({}, y, { label: null, ticks: [y.lo, 0, y.hi] }), { font: FONT_SMALL, inset: true });
          hover(canvas, (px, py) => {
            const k = cellAt(box, nx, ny, px, py);
            if (k < 0) return null;
            return `<b>${esc(short(joint.name))}</b> · ${PLANE_WORDS[plane]}<br><b>${count(pl.samples[k])}</b> samples${whoTip(p, k)}`;
          }, (px, py, event) => { const k = cellAt(box, nx, ny, px, py); if (k >= 0) selectCell(p, k, event); });
          const cap = p.focus.length ? `${pct(pl.visited_pct)} visited · selection ${p.reach}, <span class="only-n">${p.only.length} only</span>` : `${pct(pl.visited_pct)} of cells visited`;
          grid.append(el('div', { class: 'mini' }, [canvas, el('div', { class: 'mini-cap', style: 'padding-left:30px', html: cap })]));
        }
      });
      matrix.body.append(grid);
      setLegend(matrix, focusLegend(paint, 'samples in the cell', [{ kind: 'frame', colour: LIMIT, label: 'the limit box' }]));
    });
    const growth = figure('growth', 'Does each new trajectory still add coverage?', {
      how: 'Share of all joints\' position × speed cells visited as trajectories are added in the dataset\'s order (blue line), against 32 random orders (dashed mean, grey band p10 … p90). With a selection, each selected trajectory is a dot where it joins, labelled with the new cells it brought.',
    });
    mount(growth, (width) => drawGrowth(growth, width));
    root.append(ranges.node, matrix.node, growth.node);
  }

  function toPct(value, limit) { return (2 * (value - limit.low) / (limit.high - limit.low) - 1) * 100; }

  function drawRanges(fig, width) {
    const signals = ['q', 'qd', 'qdd'];
    const labelW = 110;
    const gap = 26;
    const colW = Math.floor((width - labelW - gap * (signals.length - 1)) / signals.length);
    const rowH = 30;
    const top = 22;
    const height = top + JOINTS.length * rowH + 24;
    const { canvas, g } = canvasOf(width, height, { 'data-ranges': '' });
    const focus = isWhole(sel.names) ? [] : sel.names;
    const focused = focus.length > 0;
    const cells = [];
    g.font = FONT;
    signals.forEach((signal, c) => {
      const x0 = labelW + c * (colW + gap);
      g.fillStyle = SOFT;
      g.textAlign = 'left';
      g.textBaseline = 'alphabetic';
      g.font = '600 11.5px -apple-system, "Segoe UI", Roboto, sans-serif';
      g.fillText(`${signal} · ${SIGNAL_WORD[signal]}`, x0, 14);
      g.font = FONT;
      const box = { x: x0, y: top, w: colW, h: JOINTS.length * rowH };
      const sx = (p) => box.x + ((p + 100) / 200) * box.w;
      vline(g, sx(0), box.y, box.y + box.h, RULE, 1);
      vline(g, sx(-100), box.y, box.y + box.h, LIMIT, 1.5);
      vline(g, sx(100), box.y, box.y + box.h, LIMIT, 1.5);
      g.fillStyle = MUTED;
      g.textAlign = 'center';
      g.textBaseline = 'top';
      for (const p of [-100, -50, 0, 50, 100]) { g.textAlign = p === -100 ? 'left' : p === 100 ? 'right' : 'center'; g.fillText(minus(`${p} %`), sx(p), box.y + box.h + 5); }
      JOINTS.forEach((joint, r) => {
        const y = box.y + r * rowH;
        const limit = P.limits[joint.name][signal];
        const h = P.hist[joint.name][signal];
        const a = sx(clamp(toPct(h.p001, limit), -108, 108));
        const b = sx(clamp(toPct(h.p999, limit), -108, 108));
        g.fillStyle = focused ? '#dcdfe2' : '#9aa5b1';
        roundRect(g, a, y + 8, Math.max(2, b - a), 12, 3);
        let sub = null;
        if (focused && samples.state === 'ready') {
          sub = subsetHist(focus, short(joint.name) + SAMPLE_COLUMN[signal], 1 / DEG, h.edges);
          if (sub && Number.isFinite(sub.min)) {
            const sa = sx(clamp(toPct(sub.min, limit), -108, 108));
            const sb = sx(clamp(toPct(sub.max, limit), -108, 108));
            g.fillStyle = FOCUS;
            roundRect(g, sa, y + 10, Math.max(2, sb - sa), 8, 2);
          }
        }
        cells.push({ x0: box.x, x1: box.x + box.w, y0: y, y1: y + rowH, joint, signal, h, limit, sub });
      });
    });
    g.textAlign = 'left';
    g.textBaseline = 'middle';
    JOINTS.forEach((joint, r) => {
      g.fillStyle = INK;
      g.font = '600 12px -apple-system, "Segoe UI", Roboto, sans-serif';
      g.fillText(short(joint.name), 0, top + r * rowH + 14);
    });
    hover(canvas, (px, py) => {
      const cell = cells.find((c) => px >= c.x0 && px <= c.x1 && py >= c.y0 && py < c.y1);
      if (!cell) return null;
      const s = cell.joint.display.scale;
      const u = unitOf(cell.joint, cell.signal);
      let html = `<b>${esc(short(cell.joint.name))} ${cell.signal}</b>: dataset p0.1 … p99.9 = ${fmt(cell.h.p001 * s)} … ${fmt(cell.h.p999 * s)}${u} (span ${pct(cell.h.span_pct)})<br>limit ${fmt(cell.limit.low * s)} … ${fmt(cell.limit.high * s)}${u}`;
      if (cell.sub && Number.isFinite(cell.sub.min)) html += `<br>selection min … max ${fmt(cell.sub.min * s)} … ${fmt(cell.sub.max * s)}${u} <span style="opacity:.7">(subset)</span>`;
      return html;
    });
    fig.body.append(canvas);
    fig.lead.textContent = focused && samples.state !== 'ready' ? samplesNote() : '';
    setLegend(fig, [
      { kind: 'fill', colour: focused ? '#dcdfe2' : '#9aa5b1', label: `all ${ROWS.length}: p0.1 … p99.9` },
      focused ? { kind: 'fill', colour: FOCUS, label: 'the selection: min … max', note: '(subset count from samples.json)' } : null,
      { kind: 'line', colour: LIMIT, label: 'the limits (±100 %)' },
    ]);
  }
  function roundRect(g, x, y, w, h, r) {
    g.beginPath();
    if (g.roundRect) g.roundRect(x, y, w, h, Math.min(r, w / 2, h / 2)); else g.rect(x, y, w, h);
    g.fill();
  }

  function drawGrowth(fig, width) {
    const growth = P.growth;
    const inOrder = growth.visited_pct;
    const shuffled = growth.shuffled;
    const n = inOrder.length;
    const height = 250;
    const { canvas, g } = canvasOf(width, height, { 'data-growth': '' });
    const box = { x: 54, y: 10, w: width - 54 - 16, h: height - 10 - 40 };
    const topV = Math.max(1, ...inOrder, ...shuffled.p90);
    const x = { lo: 1, hi: Math.max(2, n), label: 'trajectories added, in the dataset\'s order' };
    const y = { lo: 0, hi: Math.min(100, Math.ceil((topV * 1.12) / 5) * 5), label: 'cells visited (%)', labelOffset: 40 };
    const { sx, sy } = mapper(box, x, y);
    for (const v of ticks(y.lo, y.hi, 5)) hline(g, sy(v), box.x, box.x + box.w, RULE);
    g.fillStyle = '#e9e8e3';
    g.beginPath();
    for (let k = 0; k < n; k++) g.lineTo(sx(k + 1), sy(shuffled.p90[k]));
    for (let k = n - 1; k >= 0; k--) g.lineTo(sx(k + 1), sy(shuffled.p10[k]));
    g.closePath();
    g.fill();
    g.save();
    g.strokeStyle = MUTED;
    g.setLineDash([4, 3]);
    g.lineWidth = 1.2;
    g.beginPath();
    for (let k = 0; k < n; k++) g.lineTo(sx(k + 1), sy(shuffled.mean[k]));
    g.stroke();
    g.restore();
    g.strokeStyle = '#4b5563';
    g.lineWidth = 2;
    g.beginPath();
    for (let k = 0; k < n; k++) g.lineTo(sx(k + 1), sy(inOrder[k]));
    g.stroke();
    const focus = isWhole(sel.names) ? [] : sel.names;
    g.font = FONT_SMALL;
    for (const name of focus) {
      const k = payloadIndex.get(name);
      const px = sx(k + 1);
      const py = sy(inOrder[k]);
      vline(g, px, py, box.y + box.h, 'rgba(31,111,235,0.35)', 1);
      g.fillStyle = FOCUS;
      g.beginPath(); g.arc(px, py, 4, 0, 2 * Math.PI); g.fill();
      if (focus.length <= 6) {
        g.fillStyle = FOCUS;
        g.textAlign = 'center';
        g.fillText(`+${byName.get(name).new_cells}`, px, py - 10);
      }
    }
    strokeBox(g, box, AXIS, 1);
    drawAxes(g, box, Object.assign({ ticks: ticks(1, n, 10).filter((v) => Number.isInteger(v)) }, x), y);
    hover(canvas, (px) => {
      if (px < box.x - 4 || px > box.x + box.w + 4) return null;
      const k = clamp(Math.round(x.lo + ((px - box.x) / box.w) * (x.hi - x.lo)) - 1, 0, n - 1);
      const row = byName.get(P.trajectories[k].name);
      return `after <b>${k + 1}</b>: <b>${pct(inOrder[k])}</b> of the cells<br>added ${esc(row.name)} (+${count(row.new_cells)} new cells)<br>random orders: ${pct(shuffled.mean[k])} (p10 … p90 ${pct(shuffled.p10[k])} … ${pct(shuffled.p90[k])})<div class="hintline">click to select it</div>`;
    }, (px, py, event) => {
      const k = clamp(Math.round(x.lo + ((px - box.x) / box.w) * (x.hi - x.lo)) - 1, 0, n - 1);
      const name = P.trajectories[k].name;
      if (event.shiftKey || event.ctrlKey || event.metaKey) setSelection(sel.names.concat([name]), name); else setSelection([name], name);
    });
    fig.body.append(canvas);
    fig.lead.innerHTML = `After all ${n}: <b>${pct(inOrder[n - 1])}</b> of every joint's position × speed cells visited`;
    setLegend(fig, [
      { kind: 'line', colour: '#4b5563', label: 'in the dataset\'s order' },
      { kind: 'dash', colour: MUTED, label: 'mean of 32 random orders' },
      { kind: 'fill', colour: '#e9e8e3', label: 'p10 … p90 of random orders' },
      focus.length ? { kind: 'dot', colour: FOCUS, label: 'a selected trajectory, + the new cells it added' } : null,
    ]);
  }

  function buildPosition(root) {
    const fig = figure('projections', 'Where does the tool go?', {
      how: 'The tool path seen from above (x, y), from the front (x, z) and from the side (y, z) in the cell frame, 2 cm pixels, one colour scale for all three. Colour = samples in the pixel (or distinct trajectories through it). Grey = the robot cannot reach it, white = reachable but never visited. "paths" draws each trajectory\'s line instead (the payload\'s ≤ 400 points each), the selection in blue.',
    });
    mount(fig, (width) => {
      fig.tools.replaceChildren(...[
        segmented('show', [['cells', 'cells'], ['paths', 'paths']], state.toolShow, (value) => { state.toolShow = value; save('toolShow', value); redrawFigures(); }),
        state.toolShow === 'cells' ? metricSeg() : null].filter(Boolean));
      const cbW = 96;
      const available = width - cbW - 10 - 3 * 50 - 2 * 14;
      const k = Math.min(available / (3 * 114 * P.tool.pixel_m), 330 / (114 * P.tool.pixel_m));
      const shared = sharedProjectionScale();
      const panels = el('div', { style: 'display:flex;gap:14px;align-items:flex-start' });
      let paint = null;
      let barH = 120;
      for (const view of VIEWS) {
        const panel = projectionPanel(view, { k, focus: sel.names, show: state.toolShow, t: shared.slices[view[0]], scaled: shared.scaled });
        if (!paint || view[0] === 'xy') paint = panel.paint;
        panels.append(panel.node);
        barH = Math.max(barH, Math.round(114 * P.tool.pixel_m * k) - 20);
      }
      const row = el('div', { class: 'heatrow' }, [panels]);
      if (state.toolShow === 'cells') row.append(colorbar(shared.scaled, state.metric === 'paths' ? 'trajectories per pixel' : 'samples per pixel', Math.min(barH, 280)));
      fig.body.append(row);
      const focus = isWhole(sel.names) ? [] : sel.names;
      const lead = [`frame "${esc(P.tool.frame)}" · ${count(numberByKey('tool_voxels_visited'))} voxels (5 cm) visited, ${pct(numberByKey('tool_voxels_reachable_pct'))} of the reachable ones`];
      if (focus.length) {
        const vox = reachOf('vox', focus);
        lead.push(`selection: <b>${count(vox.reach)}</b> voxels, <b style="color:#007fae">${count(vox.only)}</b> only ${focus.length === 1 ? 'it' : 'these'} reach <span class="subset">(subset count from membership.json)</span>`);
      }
      fig.lead.innerHTML = lead.join(' · ');
      if (state.toolShow === 'paths') {
        setLegend(fig, [
          { kind: 'line', colour: focus.length ? FOCUS : 'rgba(60,60,56,0.5)', label: focus.length ? 'selected trajectories' : 'one tool path each' },
          focus.length ? { kind: 'line', colour: 'rgba(90,90,86,0.3)', label: 'the rest' } : null,
          { kind: 'fill', colour: 'rgb(236,235,231)', label: 'pixels anyone visits' },
          { kind: 'outside', label: 'out of reach' },
          focus.length && focus.length <= 3 ? { kind: 'text', label: '○ start · ■ end' } : null,
        ]);
      } else {
        setLegend(fig, focusLegend(paint, metricWord('pixel'), [{ kind: 'outside', label: 'out of reach' }, { kind: 'text', label: '+ = the frame origin' }]));
      }
    });
    const speed = figure('tool-speed', 'How fast does the tool move?', {
      how: 'The tool\'s linear speed, every sample of the dataset (payload histogram). With a selection, its own samples in blue on the same scale (binned from samples.json, a subset count) and its min … max as the rug under the axis.',
    });
    mount(speed, (width) => {
      const s = P.tool.speed;
      const focus = isWhole(sel.names) ? [] : sel.names;
      const sub = focus.length ? subsetHist(focus, 'tool_speed_m_s', 1, s.edges) : null;
      speed.body.append(hist1d({ w: width, h: 150, spec: s.edges, counts: s.counts, scale: 1, unit: ' m/s', title: 'tool speed', label: 'tool speed (m/s)', sub, focused: focus.length > 0, left: 44 }));
      speed.lead.innerHTML = `99th percentile <b>${numberByKey('tool_speed_p99_m_s').toFixed(2)} m/s</b>` + (focus.length && samples.state !== 'ready' ? ' · ' + esc(samplesNote()) : '');
      setLegend(speed, histLegend(focus.length > 0));
    });
    root.append(fig.node, speed.node);
  }

  function buildOrientation(root) {
    const wrap = el('div', { class: 'cols-side' });
    const disk = figure('directions', 'Which way does the tool point?', {
      how: 'Every direction the tool z axis can point, as the payload\'s 288 equal-area sphere cells (12 bands of base z × 24 azimuth sectors), drawn on an equal-area disk: centre = straight down (the reference), dashed ring = horizontal, rim = straight up; the angle is the azimuth it leans toward (+x right, +y up). Colour = samples in the cell. Under a selection: colour = its cells, grey = the rest, cyan = only it. Click a cell to select who points there.',
    });
    mount(disk, (width) => {
      const size = Math.min(width, 430);
      const result = directionDisk(size, { focus: sel.names });
      disk.body.append(el('div', { class: 'heatrow' }, [result.canvas, colorbar(result.paint.scaled, 'samples per cell', size - 80)]));
      const lead = [`<b>${pct(numberByKey('tool_directions_visited_pct'))}</b> of directions visited, tilting up to <b>${Math.round(numberByKey('tool_tilt_max_deg'))}°</b> from straight down`];
      if (result.paint.focus.length) lead.push(`selection: <b>${result.paint.reach}</b> cells, <b style="color:#007fae">${result.paint.only.length}</b> only ${result.paint.focus.length === 1 ? 'it' : 'these'} <span class="subset">(subset count from membership.json)</span>`);
      disk.lead.innerHTML = lead.join(' · ');
      setLegend(disk, focusLegend(result.paint, 'samples in the cell', [{ kind: 'dash', colour: 'rgba(34,33,31,0.55)', label: 'horizontal' }]));
    });
    const side = el('div');
    const orientation = P.tool.orientation;
    const tilt = figure('tilt', 'How far does it tilt from straight down?', {
      how: 'Angle between the tool z axis and straight down, every sample (payload histogram, 5° bins). Selection in blue, a subset count binned from samples.json.',
    });
    mount(tilt, (width) => {
      const focus = isWhole(sel.names) ? [] : sel.names;
      const sub = focus.length ? subsetHist(focus, 'tilt_deg', 1 / DEG, orientation.tilt.edges) : null;
      tilt.body.append(hist1d({ w: width, h: 150, spec: orientation.tilt.edges, counts: orientation.tilt.counts, scale: DEG, unit: '°', title: 'tilt', label: 'tilt from straight down (°)', sub, focused: focus.length > 0, left: 40 }));
      setLegend(tilt, histLegend(focus.length > 0));
    });
    const yaw = figure('yaw', 'Which way does the jaw face?', {
      how: 'Heading of the tool x axis in the base XY plane (the jaw yaw), every sample, 5° bins, as a straight line rather than a rose. Selection in blue, a subset count binned from samples.json.',
    });
    mount(yaw, (width) => {
      const focus = isWhole(sel.names) ? [] : sel.names;
      const sub = focus.length ? subsetHist(focus, 'yaw_deg', 1 / DEG, orientation.yaw.edges) : null;
      yaw.body.append(hist1d({ w: width, h: 150, spec: orientation.yaw.edges, counts: orientation.yaw.counts, scale: DEG, unit: '°', title: 'yaw', label: 'jaw yaw (°)', sub, focused: focus.length > 0, left: 40 }));
      setLegend(yaw, histLegend(focus.length > 0));
    });
    side.append(tilt.node, yaw.node);
    wrap.append(disk.node, side);
    root.append(wrap);
  }

  // ── the list: filter, sort, group, saved views (shared by the rail and the Trajectories table) ───────────────

  function tagOf(row, key) { return row.tags[key] === undefined ? '' : String(row.tags[key]); }
  function colourKey() { return state.group === 'none' ? 'split' : state.group; }
  const colourCache = new Map();
  function groupValues(key) {
    if (!colourCache.has(key)) colourCache.set(key, Array.from(new Set(ROWS.map((row) => tagOf(row, key)))).sort());
    return colourCache.get(key);
  }
  function colourOf(row) {
    const key = colourKey();
    const index = groupValues(key).indexOf(tagOf(row, key));
    return GROUP_PALETTE[Math.max(0, index) % GROUP_PALETTE.length];
  }
  function colourOfValue(value) {
    const index = groupValues(colourKey()).indexOf(value);
    return GROUP_PALETTE[Math.max(0, index) % GROUP_PALETTE.length];
  }
  function sortValue(row, key) {
    if (key === 'name') return row.name;
    if (['split', 'kind', 'tags', 'rung'].includes(key)) return tagOf(row, key);
    if (key.startsWith('span:')) return row.span_pct[key.slice(5)].q;
    if (key === 'tool_z') return row.tool_z_max_m - row.tool_z_min_m;
    return row[key];
  }
  function matches(row) {
    if (state.where) for (const [key, value] of Object.entries(state.where)) if (tagOf(row, key) !== value) return false;
    const text = state.filter.trim().toLowerCase();
    if (!text) return true;
    const hay = [row.name, ...Object.values(row.tags).map(String)].join(' ').toLowerCase();
    return text.split(/\s+/).every((token) => hay.includes(token));
  }
  /* -> [{group, rows}] in display order */
  function visibleGroups() {
    const rows = ROWS.filter(matches);
    const key = state.sort;
    const dir = state.dir;
    rows.sort((a, b) => {
      const va = sortValue(a, key);
      const vb = sortValue(b, key);
      const c = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return c !== 0 ? c * dir : a.name.localeCompare(b.name);
    });
    if (state.group === 'none') return [{ group: null, rows }];
    const groups = new Map();
    for (const value of groupValues(state.group)) groups.set(value, []);
    for (const row of rows) groups.get(tagOf(row, state.group)).push(row);
    return Array.from(groups, ([group, list]) => ({ group, rows: list })).filter((g) => g.rows.length);
  }
  function visibleNames() {
    const out = [];
    for (const g of visibleGroups()) if (!g.group || !state.folded.has(g.group)) for (const row of g.rows) out.push(row.name);
    return out;
  }
  function allViews() { return BUILTIN_VIEWS.concat(state.userViews); }
  function viewFields() { return { filter: state.filter, where: state.where, sort: state.sort, dir: state.dir, group: state.group }; }
  function sameView(view) {
    return view.filter === state.filter && JSON.stringify(view.where || null) === JSON.stringify(state.where || null)
      && view.sort === state.sort && view.dir === state.dir && view.group === state.group;
  }
  function applyView(id) {
    const view = allViews().find((v) => v.id === id);
    if (!view) return;
    Object.assign(state, { view: id, filter: view.filter || '', where: view.where ? Object.assign({}, view.where) : null, sort: view.sort, dir: view.dir, group: view.group });
    state.folded.clear();
    listChanged(true);
  }
  function saveView(name) {
    const view = Object.assign({ id: 'u' + Date.now().toString(36), name, user: true }, JSON.parse(JSON.stringify(viewFields())));
    state.userViews.push(view);
    save('views', state.userViews);
    state.view = view.id;
    listChanged(true);
  }
  function deleteView(id) {
    state.userViews = state.userViews.filter((v) => v.id !== id);
    save('views', state.userViews);
    if (state.view === id) state.view = 'all';
    listChanged(true);
  }
  function viewChips(attr) {
    const box = el('div', { class: 'views', [attr]: '' });
    for (const view of allViews()) {
      const active = state.view === view.id;
      const dirty = active && !sameView(view);
      const chip = el('button', { type: 'button', class: 'chip', 'data-view': view.id, 'aria-pressed': String(active && !dirty),
        title: dirty ? `${view.name} — changed since it was applied; click to reset` : `Apply the "${view.name}" view`, onclick: () => applyView(view.id) },
      [view.name, dirty ? el('i', { class: 'dirty', title: 'changed' }) : null,
        view.user ? el('span', { class: 'x', title: 'Delete this view', text: '×', onclick: (event) => { event.stopPropagation(); deleteView(view.id); } }) : null]);
      box.append(chip);
    }
    const add = el('button', { type: 'button', class: 'chip add', 'data-v5-save-view': '', text: '+ Save', title: 'Save the current filter, sort and grouping as a view' });
    add.addEventListener('click', () => {
      const input = el('input', { type: 'text', placeholder: 'View name', 'aria-label': 'Name of the new view', 'data-v5-view-name': '' });
      const form = el('span', { class: 'save-box' }, [input]);
      // WHY the guard: Enter re-renders the chips, which blurs the input, which would save the view a second time
      let finished = false;
      const done = (keep) => {
        if (finished) return;
        finished = true;
        const name = input.value.trim();
        if (keep && name) saveView(name); else listChanged(true);
      };
      input.addEventListener('keydown', (event) => { if (event.key === 'Enter') done(true); if (event.key === 'Escape') { event.stopPropagation(); done(false); } });
      input.addEventListener('blur', () => done(true));
      add.replaceWith(form);
      input.focus();
    });
    box.append(add);
    return box;
  }
  function colourLegend(attr) {
    const key = colourKey();
    const label = (GROUPS.find(([k]) => k === key) || [key, key])[1].toLowerCase();
    const box = el('div', { class: 'legend-row', [attr]: '' }, [el('span', { class: 'what', text: `Dot colour = ${label}:` })]);
    const shownRows = ROWS.filter(matches);
    for (const value of groupValues(key)) {
      const n = shownRows.filter((row) => tagOf(row, key) === value).length;
      if (!n) continue;
      box.append(el('span', { class: 'item' }, [el('i', { class: 'dot', style: `background:${colourOfValue(value)}` }), `${value} `, el('span', { class: 'what', text: String(n) })]));
    }
    box.append(el('span', { class: 'item' }, [el('i', { class: 'dot', style: `background:${FOCUS};border-radius:2px;width:3px;height:12px` }), el('span', { class: 'what', text: 'blue = selected' })]));
    return box;
  }

  // ── selection ─────────────────────────────────────────────────────────────────────────────────────────────────

  function setSelection(names, anchor) {
    const set = new Set(names);
    sel.names = ROWS.filter((row) => set.has(row.name)).map((row) => row.name);
    sel.set = new Set(sel.names);
    sel.anchor = anchor && sel.set.has(anchor) ? anchor : sel.names[0] || null;
    selectionChanged();
  }
  function clickRow(name, event) {
    if (event && event.shiftKey && sel.anchor) {
      const order = visibleNames();
      const a = order.indexOf(sel.anchor);
      const b = order.indexOf(name);
      if (a >= 0 && b >= 0) {
        const range = order.slice(Math.min(a, b), Math.max(a, b) + 1);
        const anchor = sel.anchor;
        setSelection(event.ctrlKey || event.metaKey ? sel.names.concat(range) : range, anchor);
        return;
      }
    }
    if (event && (event.ctrlKey || event.metaKey)) {
      if (sel.set.has(name)) setSelection(sel.names.filter((n) => n !== name), sel.anchor === name ? null : sel.anchor);
      else setSelection(sel.names.concat([name]), name);
      return;
    }
    if (state.page) { openPage(name); return; }
    setSelection([name], name);
  }
  function selectionChanged() {
    renderRailList();
    renderFocus();
    if (state.page) return;
    if (state.tab === 'trajectories') renderTableBody();
    else redrawFigures();
  }

  // ── the rail ──────────────────────────────────────────────────────────────────────────────────────────────────

  const app = $('[data-v5-app]');
  const rail = $('[data-v5-rail]');
  const content = $('[data-v5-content]');
  const railParts = {};

  function buildRail() {
    const search = el('input', { type: 'search', placeholder: 'Filter by name or tag…', 'aria-label': 'Filter trajectories', 'data-v5-filter': '', autocomplete: 'off' });
    search.addEventListener('input', () => { state.filter = search.value; listChanged(false); });
    const sortSel = el('select', { class: 'sort-sel', 'aria-label': 'Sort by', 'data-v5-sort': '' });
    sortSel.addEventListener('change', () => { state.sort = sortSel.value; state.dir = state.sort === 'name' ? 1 : -1; listChanged(true); });
    const dirBtn = el('button', { type: 'button', class: 'dir-btn', 'data-v5-dir': '', title: 'Reverse the order' });
    dirBtn.addEventListener('click', () => { state.dir = -state.dir; listChanged(true); });
    const groupSel = el('select', { 'aria-label': 'Group by', 'data-v5-group': '' }, GROUPS.map(([value, label]) => el('option', { value, text: label })));
    groupSel.addEventListener('change', () => { state.group = groupSel.value; state.folded.clear(); listChanged(true); });
    const list = el('div', { class: 'list', 'data-v5-list': '', tabindex: '0', 'aria-label': 'Trajectory list (↑ ↓ to step, Enter to open)' });
    list.addEventListener('keydown', (event) => {
      if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
      event.preventDefault();
      const order = visibleNames();
      if (!order.length) return;
      if (event.key === 'Enter') { if (sel.anchor) openPage(sel.anchor); return; }
      const at = sel.anchor ? order.indexOf(sel.anchor) : -1;
      const next = order[clamp(at + (event.key === 'ArrowDown' ? 1 : -1), 0, order.length - 1)];
      if (state.page) openPage(next); else setSelection([next], next);
      const node = list.querySelector(`[data-name="${next}"]`);
      if (node) node.scrollIntoView({ block: 'nearest' });
    });
    Object.assign(railParts, {
      count: el('span', { class: 'rail-count', 'data-v5-rail-count': '' }),
      views: el('div'), search, sortSel, dirBtn, groupSel, pills: el('div', { class: 'pills' }), legend: el('div'), list,
      foot: el('div', { class: 'rail-foot', 'data-v5-rail-foot': '' }),
    });
    rail.replaceChildren(
      el('div', { class: 'rail-head' }, [el('span', { class: 'rail-title', text: 'Trajectories' }), railParts.count]),
      railParts.views,
      el('div', { class: 'search' }, [el('span', { html: '<svg width="13" height="13" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11 11l4 4" stroke="currentColor" stroke-width="1.6"/></svg>' }), search]),
      el('div', { class: 'rail-ctl' }, ['Sort', sortSel, dirBtn, 'Group', groupSel]),
      railParts.pills, railParts.legend, list, railParts.foot);
  }
  function renderRail() {
    railParts.views.replaceChildren(viewChips('data-v5-views'));
    if (railParts.search.value !== state.filter) railParts.search.value = state.filter;
    const options = SORTS.slice();
    if (!options.some(([k]) => k === state.sort)) options.push([state.sort, sortLabel(state.sort)]);
    railParts.sortSel.replaceChildren(...options.map(([value, label]) => el('option', { value, text: label })));
    railParts.sortSel.value = state.sort;
    railParts.dirBtn.textContent = state.dir > 0 ? '↑' : '↓';
    railParts.dirBtn.title = state.dir > 0 ? 'Ascending — click to reverse' : 'Descending — click to reverse';
    railParts.groupSel.value = state.group;
    railParts.pills.replaceChildren(...Object.entries(state.where || {}).map(([key, value]) => el('span', { class: 'pill' }, [`${key} = ${value}`,
      el('button', { type: 'button', title: 'Remove this filter', text: '×', onclick: () => { const where = Object.assign({}, state.where); delete where[key]; state.where = Object.keys(where).length ? where : null; listChanged(true); } })])));
    railParts.legend.replaceChildren(colourLegend('data-v5-rail-legend'));
    renderRailList();
  }
  function sortLabel(key) {
    const col = COLUMNS.find((c) => c.key === key);
    const fromSorts = SORTS.find(([k]) => k === key);
    return fromSorts ? fromSorts[1] : col ? (col.long || col.label) : key;
  }
  function metricKey() { return state.sort === 'name' || typeof sortValue(ROWS[0], state.sort) === 'string' ? 'new_cells' : state.sort; }
  function metricText(row, key) {
    const v = sortValue(row, key);
    if (key === 'duration_s') return fmt(v) + ' s';
    if (key === 'tool_path_m') return fmt(v) + ' m';
    if (key === 'tool_speed_max_m_s') return v.toFixed(2);
    if (key === 'tool_tilt_max_deg') return Math.round(v) + '°';
    if (key.startsWith('span:')) return pct(v);
    if (key === 'tool_z') return Math.round(v * 1000);
    return count(v);
  }
  function renderRailList() {
    if (!railParts.list) return;
    const groups = visibleGroups();
    const shown = groups.reduce((n, g) => n + g.rows.length, 0);
    railParts.count.textContent = `${shown} of ${ROWS.length}`;
    const key = metricKey();
    const max = Math.max(1e-9, ...ROWS.map((row) => Math.abs(sortValue(row, key))));
    const metricName = (SORTS.find(([k]) => k === key) || [key, sortLabel(key)])[1].replace(/ \(.*\)$/, '');
    const scrollTop = railParts.list.scrollTop;
    const nodes = [el('div', { class: 'list-head' }, [el('span', { text: 'trajectory' }), el('span', { text: metricName.toLowerCase() })])];
    if (!shown) nodes.push(el('div', { class: 'empty-note', text: 'No trajectory matches. Clear the filter or pick the "All" view.' }));
    for (const g of groups) {
      const folded = g.group && state.folded.has(g.group);
      if (g.group !== null) {
        nodes.push(el('div', { class: 'grp', 'data-group': g.group }, [
          el('button', { type: 'button', class: 'fold', text: folded ? '▸' : '▾', title: folded ? 'Unfold' : 'Fold', onclick: () => { if (folded) state.folded.delete(g.group); else state.folded.add(g.group); renderRailList(); } }),
          el('i', { class: 'dot', style: `background:${colourOfValue(g.group)}` }), el('span', { text: g.group }), el('span', { class: 'n', text: String(g.rows.length) }),
          el('button', { type: 'button', class: 'link', 'data-v5-select-group': g.group, text: 'select', title: `Select the ${g.rows.length} ${g.group} trajectories shown`, onclick: () => setSelection(g.rows.map((r) => r.name), g.rows[0].name) })]));
      }
      if (folded) continue;
      for (const row of g.rows) {
        const value = Math.abs(sortValue(row, key));
        const node = el('div', { class: 'row' + (sel.set.has(row.name) ? ' sel' : ''), 'data-v5-rail-row': '', 'data-name': row.name, title: `${row.name} · ${row.tags.kind} · ${row.tags.tags}\nclick: select · ⇧/Ctrl: several · double-click: open` }, [
          el('i', { class: 'dot', style: `background:${colourOf(row)}` }),
          el('span', { class: 'name', html: `<span class="pre">workspace-</span>${esc(row.name.replace(/^workspace-/, ''))}` }),
          el('span', { class: 'metric' }, [el('span', { class: 'bar' }, [el('i', { style: `width:${((value / max) * 100).toFixed(1)}%` })]), el('span', { class: 'val', text: metricText(row, key) })]),
          el('button', { type: 'button', class: 'open', 'data-v5-open-row': '', title: 'Open this trajectory', text: '▸', onclick: (event) => { event.stopPropagation(); openPage(row.name); } }),
        ]);
        node.addEventListener('click', (event) => clickRow(row.name, event));
        node.addEventListener('dblclick', () => openPage(row.name));
        node.addEventListener('mousedown', (event) => { if (event.shiftKey) event.preventDefault(); });
        nodes.push(node);
      }
    }
    railParts.list.replaceChildren(...nodes);
    railParts.list.scrollTop = scrollTop;
    const n = sel.names.length;
    railParts.foot.replaceChildren(
      el('span', { class: 'n', text: `${shown} shown · ${n} selected` }),
      el('button', { type: 'button', class: 'btn small', 'data-v5-select-shown': '', text: 'Select shown', disabled: !shown, onclick: () => { const names = visibleNames(); setSelection(names, names[0]); } }),
      el('button', { type: 'button', class: 'btn small', text: 'Clear', disabled: !n, onclick: () => setSelection([], null) }));
  }
  function listChanged(full) {
    if (full) renderRail(); else { railParts.views.replaceChildren(viewChips('data-v5-views')); renderRailList(); }
    if (state.tab === 'trajectories' && !state.page) renderTable(full);
  }

  // rail width: drag the boundary, remembered (Zach: every panel boundary draggable, width remembered)
  function setupRailHandle() {
    const handle = $('[data-v5-rail-handle]');
    const DEFAULT = 300;
    const apply = (w) => document.documentElement.style.setProperty('--rail-w', w + 'px');
    let width = clamp(Number(load('railWidth', DEFAULT)) || DEFAULT, 220, 520);
    apply(width);
    handle.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      handle.classList.add('dragging');
      const move = (e) => { width = clamp(e.clientX, 220, 520); apply(width); };
      const up = () => {
        handle.classList.remove('dragging');
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', up);
        save('railWidth', width);
        redrawFigures();
      };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', up);
    });
    handle.addEventListener('dblclick', () => { width = DEFAULT; apply(width); save('railWidth', width); redrawFigures(); });
  }

  // ── focus bar ─────────────────────────────────────────────────────────────────────────────────────────────────

  function renderFocus() {
    const bar = $('[data-v5-focusbar]');
    const n = sel.names.length;
    if (!n) {
      bar.replaceChildren(el('span', { class: 'hint', 'data-v5-readout': '', html: 'Select trajectories in the list to light up what they cover in every figure — click one, <kbd>⇧</kbd>/<kbd>Ctrl</kbd> for several, double-click to open it. Click any cell to select who goes there.' }));
      return;
    }
    const names = sel.names;
    const shown = names.slice(0, 2).map((name) => name.replace(/^workspace-/, '')).join(', ') + (n > 2 ? ` +${n - 2}` : '');
    const children = [el('span', { class: 'focus-pill' }, [el('i'), `${n} selected`]), el('span', { class: 'focus-names', title: names.join(', '), text: shown })];
    if (isWhole(names)) {
      children.push(el('span', { class: 'readout', 'data-v5-readout': '', text: `all ${ROWS.length} — the figures show the whole dataset` }));
    } else {
      const unique = uniqueJointCells(names);
      if (n === 1) {
        const row = byName.get(names[0]);
        if (row.only_it_q_qd_cells !== unique) console.warn('v5: membership-derived unique cells differ from trajectories.json', row.name, unique, row.only_it_q_qd_cells);
      }
      children.push(el('span', { class: 'readout', 'data-v5-readout': '', html: `<span class="only-sw"></span>${n === 1 ? 'it adds' : `these ${n} add`} <b>${count(unique)}</b> ${plural(unique, 'cell')} nobody else visits` }));
      children.push(el('span', { class: 'subset', text: 'position × speed, all joints · subset count from membership.json' }));
    }
    children.push(el('span', { class: 'spacer' }));
    children.push(el('button', { type: 'button', class: 'btn', text: 'Clear', onclick: () => setSelection([], null) }));
    if (!state.page) children.push(el('button', { type: 'button', class: 'btn primary', 'data-v5-focus-open': '', text: n === 1 ? 'Open ▸' : 'Open first ▸', onclick: () => openPage(sel.anchor || names[0]) }));
    bar.replaceChildren(...children);
  }

  // ── the Trajectories tab: the rail as a full-width table, every column ───────────────────────────────────────

  const COLUMNS = [
    { key: 'name', label: 'Trajectory', l: true, get: (r) => r.name },
    { key: 'split', label: 'Split', l: true },
    { key: 'kind', label: 'Kind', l: true },
    { key: 'tags', label: 'Shape', l: true },
    { key: 'rung', label: 'Rung', l: true },
    { key: 'duration_s', label: 'Duration', unit: 's' },
    { key: 'samples', label: 'Samples' },
    { key: 'new_cells', label: 'New cells', long: 'New cells (first to visit)', title: 'position × speed cells (all joints) it was the first to visit, in the dataset\'s order' },
    { key: 'only_it_q_qd_cells', label: 'Only it', long: 'Cells only it visits', title: 'position × speed cells (all joints) no other trajectory visits' },
    ...JOINTS.map((joint) => ({ key: 'span:' + joint.name, label: short(joint.name).replace('shoulder_', 'sh_').replace('wrist_', 'wr_'), long: `${short(joint.name)} range used`, title: `${joint.name}: share of its position range used (p0.1 … p99.9)`, span: true })),
    { key: 'tool_path_m', label: 'Tool path', long: 'Tool path length' },
    { key: 'tool_speed_max_m_s', label: 'Peak speed', long: 'Peak tool speed' },
    { key: 'tool_z', label: 'Height', long: 'Tool height range', title: 'tool z min … max in the cell frame (mm); sorts by the range' },
    { key: 'tool_tilt_max_deg', label: 'Max tilt', long: 'Largest tool tilt' },
  ];
  const tableParts = {};
  function cellText(row, col) {
    const v = sortValue(row, col.key);
    switch (col.key) {
      case 'name': return null;
      case 'duration_s': return fmt(v) + ' s';
      case 'tool_path_m': return fmt(v) + ' m';
      case 'tool_speed_max_m_s': return v.toFixed(2) + ' m/s';
      case 'tool_z': return `${Math.round(row.tool_z_min_m * 1000)} … ${Math.round(row.tool_z_max_m * 1000)} mm`;
      case 'tool_tilt_max_deg': return Math.round(v) + '°';
      default: return col.span ? pct(v) : typeof v === 'number' ? count(v) : v;
    }
  }
  function buildTable(root) {
    const search = el('input', { type: 'search', placeholder: 'Filter by name or tag…', 'aria-label': 'Filter the table', 'data-v5-table-filter': '', autocomplete: 'off', value: state.filter });
    search.value = state.filter;
    search.addEventListener('input', () => { state.filter = search.value; listChanged(false); renderTable(false); });
    const groupSel = el('select', { 'aria-label': 'Group by', 'data-v5-table-group': '' }, GROUPS.map(([value, label]) => el('option', { value, text: label })));
    groupSel.addEventListener('change', () => { state.group = groupSel.value; state.folded.clear(); listChanged(true); });
    Object.assign(tableParts, { search, groupSel, views: el('div'), status: el('div', { class: 'tstatus' }), thead: el('thead'), tbody: el('tbody') });
    const table = el('table', { class: 'ttable', 'data-v5-table': '' }, [tableParts.thead, tableParts.tbody]);
    root.append(
      el('div', { class: 'ttoolbar' }, [tableParts.views, el('div', { class: 'search' }, [el('span', { html: '<svg width="13" height="13" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11 11l4 4" stroke="currentColor" stroke-width="1.6"/></svg>' }), search]),
        el('span', { class: 'lbl', text: 'Group' }), groupSel]),
      tableParts.status,
      el('div', { class: 'twrap' }, [table]));
    renderTable(true);
  }
  function renderTable(full) {
    if (!tableParts.tbody || !tableParts.tbody.isConnected) return;
    if (full) {
      tableParts.views.replaceChildren(viewChips('data-v5-table-views'));
      tableParts.groupSel.value = state.group;
    } else tableParts.views.replaceChildren(viewChips('data-v5-table-views'));
    if (tableParts.search.value !== state.filter) tableParts.search.value = state.filter;
    const head1 = el('tr', { class: 'super' }, [el('th', { class: 'nosort', colspan: '10' }), el('th', { class: 'nosort', colspan: String(JOINTS.length), text: 'position range used, % of the limit' }), el('th', { class: 'nosort', colspan: '4', text: 'tool' }), el('th', { class: 'nosort' })]);
    const head2 = el('tr', { class: 'cols' }, [el('th', { class: 'nosort', style: 'width:14px' })]);
    for (const col of COLUMNS) {
      const sorted = state.sort === col.key;
      const th = el('th', { class: col.l ? 'l' : '', 'data-sort': col.key, title: (col.title || col.long || col.label) + ' — click to sort', 'aria-sort': sorted ? (state.dir > 0 ? 'ascending' : 'descending') : null },
        [col.label, sorted ? el('span', { class: 'arrow', text: state.dir > 0 ? '▲' : '▼' }) : null]);
      th.addEventListener('click', () => {
        if (state.sort === col.key) state.dir = -state.dir;
        else { state.sort = col.key; state.dir = typeof sortValue(ROWS[0], col.key) === 'string' ? 1 : -1; }
        listChanged(true);
      });
      head2.append(th);
    }
    head2.append(el('th', { class: 'nosort' }));
    tableParts.thead.replaceChildren(head1, head2);
    renderTableBody();
  }
  function renderTableBody() {
    if (!tableParts.tbody || !tableParts.tbody.isConnected) return;
    const groups = visibleGroups();
    const shown = groups.reduce((n, g) => n + g.rows.length, 0);
    const rows = [];
    for (const g of groups) {
      const folded = g.group && state.folded.has(g.group);
      if (g.group !== null) {
        rows.push(el('tr', { class: 'tgrp' }, [el('td', { colspan: String(COLUMNS.length + 2) }, [
          el('button', { type: 'button', class: 'fold', text: folded ? '▸' : '▾', onclick: () => { if (folded) state.folded.delete(g.group); else state.folded.add(g.group); renderTableBody(); renderRailList(); } }),
          el('i', { class: 'dot', style: `background:${colourOfValue(g.group)};margin-right:6px` }), g.group, el('span', { class: 'n', text: `${g.rows.length} ${plural(g.rows.length, 'row')}` }),
          el('button', { type: 'button', class: 'link', text: 'select all', onclick: () => setSelection(g.rows.map((r) => r.name), g.rows[0].name) })])]));
      }
      if (folded) continue;
      for (const row of g.rows) {
        const tr = el('tr', { 'data-row': '', 'data-name': row.name, class: sel.set.has(row.name) ? 'sel' : '' });
        tr.append(el('td', { class: 'l' }, [el('i', { class: 'dot', style: `background:${colourOf(row)}` })]));
        for (const col of COLUMNS) {
          if (col.key === 'name') { tr.append(el('td', { class: 'l nm', text: row.name })); continue; }
          if (['split', 'kind', 'tags', 'rung'].includes(col.key)) { tr.append(el('td', { class: 'l' }, [el('span', { class: 'tag', text: tagOf(row, col.key) })])); continue; }
          const text = cellText(row, col);
          const v = sortValue(row, col.key);
          if (col.span) {
            tr.append(el('td', { class: 'spanc' + (v === 0 ? ' zero' : '') }, [text, el('i', { style: `width:${Math.max(0, Math.min(100, v)) * 0.42}px` })]));
          } else tr.append(el('td', { class: v === 0 ? 'zero' : '', text }));
        }
        tr.append(el('td', null, [el('button', { type: 'button', class: 'open-btn', 'data-v5-open': '', text: 'Open ▸', title: 'Open this trajectory page', onclick: (event) => { event.stopPropagation(); openPage(row.name); } })]));
        tr.addEventListener('click', (event) => clickRow(row.name, event));
        tr.addEventListener('dblclick', () => openPage(row.name));
        tr.addEventListener('mousedown', (event) => { if (event.shiftKey) event.preventDefault(); });
        rows.push(tr);
      }
    }
    if (!shown) rows.push(el('tr', null, [el('td', { class: 'l', colspan: String(COLUMNS.length + 2), style: 'padding:18px;color:#8a8983', text: 'No trajectory matches. Clear the filter or pick the "All" view.' })]));
    tableParts.tbody.replaceChildren(...rows);
    const nGroups = groups.filter((g) => g.group !== null).length;
    const status = [el('span', { 'data-v5-table-count': '', text: `${shown} of ${ROWS.length} rows${nGroups ? ` · ${nGroups} ${plural(nGroups, 'group')}` : ''} · ${sel.names.length} selected` })];
    if (nGroups) {
      status.push(el('button', { type: 'button', class: 'link', text: 'Unfold all', onclick: () => { state.folded.clear(); renderTableBody(); renderRailList(); } }));
      status.push(el('button', { type: 'button', class: 'link', text: 'Fold all', onclick: () => { for (const g of groups) if (g.group) state.folded.add(g.group); renderTableBody(); renderRailList(); } }));
    }
    const legend = colourLegend('data-v5-table-legend');
    legend.className = 'legend-row legend-inline';
    status.push(legend);
    tableParts.status.replaceChildren(...status);
  }

  // ── the trajectory page (drill-in) ───────────────────────────────────────────────────────────────────────────

  function tabLabel(id) { return (TABS.find(([k]) => k === id) || [id, id])[1]; }
  function rerunCommand(row) {
    let root = ROUND_DIR;
    if (global.location.protocol === 'file:') root = decodeURIComponent(global.location.pathname).replace(/\/v5\/[^/]*$/, '');
    return `${RERUN_PREFIX} ${root}/${row.rrd}`;
  }
  function copyButton(text) {
    const button = el('button', { type: 'button', class: 'btn small', text: 'Copy' });
    button.addEventListener('click', () => {
      const done = () => { button.textContent = 'Copied'; setTimeout(() => { button.textContent = 'Copy'; }, 1400); };
      if (global.navigator.clipboard && global.navigator.clipboard.writeText) global.navigator.clipboard.writeText(text).then(done, () => { fallbackCopy(text); done(); });
      else { fallbackCopy(text); done(); }
    });
    return button;
  }
  function fallbackCopy(text) {
    const area = el('textarea', { style: 'position:fixed;left:-9999px' });
    area.value = text;
    document.body.append(area);
    area.select();
    try { document.execCommand('copy'); } catch (error) { /* nothing more to try */ }
    area.remove();
  }
  async function openRerun(row, status) {
    const command = rerunCommand(row);
    const showCommand = (cls, message) => status.replaceChildren(el('span', { class: cls, text: message }),
      el('span', { class: 'cmd' }, [el('code', { text: command, title: command }), copyButton(command)]));
    if (global.location.protocol === 'file:') { showCommand('fail', 'Opened from disk, so the page cannot start Rerun — run this:'); return; }
    status.replaceChildren(el('span', { text: 'Starting Rerun…' }));
    try {
      const response = await fetch('/__rerun/open?rrd=' + encodeURIComponent(row.rrd), { method: 'POST' });
      let body = {};
      try { body = await response.json(); } catch (error) { body = {}; }
      if (response.ok && body.ok) showCommand('ok', `✓ Rerun is opening ${row.name}.rrd`);
      else showCommand('fail', `Could not start Rerun${body.error ? ` (${body.error})` : ''} — run this:`);
    } catch (error) {
      showCommand('fail', 'No Rerun endpoint here (the page is not served by traj_compare.serve) — run this:');
    }
  }

  function buildPage(root, name) {
    const row = byName.get(name);
    const order = visibleNames();
    const at = order.indexOf(name);
    const prev = at > 0 ? order[at - 1] : null;
    const next = at >= 0 && at < order.length - 1 ? order[at + 1] : null;
    const page = el('div', { 'data-v5-trajpage': '', 'data-name': name });
    page.append(el('div', { class: 'page-crumbs' }, [
      el('button', { type: 'button', 'data-v5-back': '', text: `◂ ${tabLabel(state.prevTab)}`, onclick: () => go(state.prevTab) }),
      el('span', { text: '›' }), el('span', { style: 'color:#22211f', text: name }),
      el('span', { style: 'margin-left:auto;display:flex;gap:6px' }, [
        el('button', { type: 'button', class: 'btn small', text: '‹ Previous', disabled: !prev, title: prev || '', onclick: () => openPage(prev) }),
        el('button', { type: 'button', class: 'btn small', text: 'Next ›', disabled: !next, title: next || '', onclick: () => openPage(next) })])]));
    const status = el('div', { class: 'rerun-status', 'data-v5-rerun-status': '' });
    const rerun = el('button', { type: 'button', class: 'btn primary', 'data-v5-rerun': '', text: 'Open in Rerun', title: `POST /__rerun/open?rrd=${row.rrd}` });
    rerun.addEventListener('click', () => openRerun(row, status));
    const tags = el('div', { class: 'tags' }, Object.entries(row.tags).map(([key, value]) => el('span', null, [el('b', { text: key === 'tags' ? 'shape' : key }), String(value)])));
    page.append(el('div', { class: 'page-head' }, [
      el('div', null, [el('h2', null, [el('i', { class: 'dot', style: `background:${colourOf(row)};width:11px;height:11px`, title: `dot colour = ${colourKey()} (${tagOf(row, colourKey())})` }), name]), tags]),
      el('div', { class: 'page-actions' }, [el('div', { class: 'row-btns' }, [
        el('button', { type: 'button', class: 'btn', text: 'Show in every figure', title: 'Back to the figures with this trajectory selected', onclick: () => { go(state.prevTab === 'trajectories' ? 'overview' : state.prevTab); } }),
        rerun]), status])]));
    const nums = [
      ['Duration', duration(row.duration_s), `${count(row.samples)} samples`],
      ['New cells', count(row.new_cells), 'first to visit, in dataset order'],
      ['Cells only it visits', count(row.only_it_q_qd_cells), 'position × speed, all joints'],
      ['Tool path', fmt(row.tool_path_m) + ' m', 'length of the TCP path'],
      ['Peak tool speed', row.tool_speed_max_m_s.toFixed(2) + ' m/s', `dataset p99 ${numberByKey('tool_speed_p99_m_s').toFixed(2)} m/s`],
      ['Tool height', `${Math.round(row.tool_z_min_m * 1000)} … ${Math.round(row.tool_z_max_m * 1000)}`, 'mm, cell frame z'],
      ['Largest tool tilt', Math.round(row.tool_tilt_max_deg) + '°', 'from straight down'],
      ['Position range used', pct(Math.max(...JOINTS.map((j) => row.span_pct[j.name].q))), 'its busiest joint'],
    ];
    page.append(el('div', { class: 'page-nums' }, nums.map(([label, value, note]) => el('div', { class: 'tile' }, [el('span', { class: 'tile-label', text: label }), el('span', { class: 'tile-value', text: value }), el('small', { text: note })]))));
    const top = el('div', { class: 'cols-side' });
    const motion = figure('motion', 'How do its joints move over time?', {
      how: 'Every sample of this trajectory (samples.json, nothing subsampled): position (left) and speed (right) per joint on its own clock. Each chart is scaled to the trajectory\'s own range; red lines are the limits when they fall inside the view.',
    });
    mount(motion, (width) => drawMotion(motion, width, row));
    const spans = figure('spans', 'How much of each joint does it use, against the dataset?', {
      how: 'Per joint and signal: the share of the limit span used (p0.1 … p99.9) by this trajectory (blue, trajectories.json) and by the whole dataset (grey, the payload).',
    });
    mount(spans, (width) => drawSpans(spans, width, row));
    top.append(motion.node, spans.node);
    page.append(top);
    const path = figure('its-tool', 'Where does its tool go?', {
      how: 'Its pixels in each projection keep the colour map (the dataset\'s samples there), cyan pixels only it visits, grey = the rest of the dataset; the dark line is its path (○ start, ■ end).',
    });
    mount(path, (width) => {
      const available = width - 3 * 50 - 2 * 14;
      const k = Math.min(available / (3 * 114 * P.tool.pixel_m), 260 / (114 * P.tool.pixel_m));
      const shared = sharedProjectionScale();
      const panels = el('div', { style: 'display:flex;gap:14px;align-items:flex-start' });
      let paint = null;
      for (const view of VIEWS) {
        const panel = projectionPanel(view, { k, focus: [name], path: name, t: shared.slices[view[0]], scaled: shared.scaled });
        if (!paint) paint = panel.paint;
        panels.append(panel.node);
      }
      path.body.append(panels);
      setLegend(path, focusLegend(paint, 'samples in the pixel', [{ kind: 'line', colour: 'rgba(20,20,18,0.75)', label: 'its path (○ start · ■ end)' }, { kind: 'outside', label: 'out of reach' }]));
    });
    const cells = figure('its-cells', 'Which position × speed cells does it visit, per joint?', {
      how: 'The overview\'s joint strip with only this trajectory in focus: its cells keep the colour, cyan = cells only it visits, grey = the rest of the dataset.',
    });
    mount(cells, (width) => {
      const { node, paint } = miniPlanes(width, 'q_qd', [name]);
      cells.body.append(node);
      setLegend(cells, focusLegend(paint, 'samples in the cell'));
    });
    page.append(path.node, cells.node);
    root.append(page);
  }

  function drawMotion(fig, width, row) {
    if (samples.state !== 'ready') { fig.body.append(el('p', { class: 'loading', text: samplesNote() })); return; }
    const data = samples.byName.get(row.name) || [];
    const labelW = 92;
    const gap = 16;
    const colW = Math.floor((width - labelW - gap) / 2);
    const rowH = 58;
    const top = 18;
    const height = top + JOINTS.length * rowH + 22;
    const { canvas, g } = canvasOf(width, height, { 'data-motion': '' });
    const t = data.map((s) => s.t_s);
    const tMax = t.length ? t[t.length - 1] : 1;
    const cells = [];
    ['q', 'qd'].forEach((signal, c) => {
      const x0 = labelW + c * (colW + gap);
      g.font = '600 11.5px -apple-system, "Segoe UI", Roboto, sans-serif';
      g.fillStyle = SOFT;
      g.textAlign = 'left';
      g.textBaseline = 'alphabetic';
      g.fillText(signal === 'q' ? 'q · position (°)' : 'qd · speed (°/s)', x0 + 34, 12);
      JOINTS.forEach((joint, r) => {
        const column = short(joint.name) + SAMPLE_COLUMN[signal];
        const values = data.map((s) => s[column]);
        let lo = Math.min(...values);
        let hi = Math.max(...values);
        if (signal === 'qd') { const a = Math.max(Math.abs(lo), Math.abs(hi), 1); lo = -a; hi = a; }
        if (hi - lo < 2) { const mid = (hi + lo) / 2; lo = mid - 1; hi = mid + 1; }
        const pad = (hi - lo) * 0.08;
        lo -= pad; hi += pad;
        const box = { x: x0 + 34, y: top + r * rowH + 4, w: colW - 34 - 10, h: rowH - 14 };
        g.fillStyle = '#fbfbf9';
        g.fillRect(box.x, box.y, box.w, box.h);
        const y = { lo, hi };
        const x = { lo: 0, hi: tMax };
        const { sx, sy } = mapper(box, x, y);
        if (lo < 0 && hi > 0) hline(g, sy(0), box.x, box.x + box.w, RULE, 1);
        const limit = P.limits[joint.name][signal];
        for (const v of [limit.low * DEG, limit.high * DEG]) if (v > lo && v < hi) hline(g, sy(v), box.x, box.x + box.w, LIMIT, 1.2);
        g.strokeStyle = FOCUS;
        g.lineWidth = 1.5;
        g.beginPath();
        values.forEach((v, i) => { if (i) g.lineTo(sx(t[i]), sy(v)); else g.moveTo(sx(t[i]), sy(v)); });
        g.stroke();
        drawAxes(g, box, r === JOINTS.length - 1 ? { lo: 0, hi: tMax, tickPad: 3 } : null, { lo, hi, ticks: ticks(lo, hi, 2) }, { font: FONT_SMALL, xGap: 36 });
        cells.push({ box, joint, signal, values, sx });
      });
    });
    g.textAlign = 'left';
    g.textBaseline = 'middle';
    JOINTS.forEach((joint, r) => {
      g.font = '600 12px -apple-system, "Segoe UI", Roboto, sans-serif';
      g.fillStyle = INK;
      g.fillText(short(joint.name), 0, top + r * rowH + 4 + (rowH - 14) / 2 - 6);
      g.font = FONT_SMALL;
      g.fillStyle = MUTED;
      g.fillText(`uses ${pct(row.span_pct[joint.name].q)}`, 0, top + r * rowH + 4 + (rowH - 14) / 2 + 8);
    });
    g.fillStyle = MUTED;
    g.font = FONT_SMALL;
    g.textAlign = 'right';
    g.fillText('t (s)', width - 2, height - 6);
    hover(canvas, (px, py) => {
      const cell = cells.find((c) => px >= c.box.x && px <= c.box.x + c.box.w && py >= c.box.y && py <= c.box.y + c.box.h);
      if (!cell) return null;
      const time = ((px - cell.box.x) / cell.box.w) * tMax;
      let i = 0;
      while (i < t.length - 1 && t[i] < time) i += 1;
      const q = data[i][short(cell.joint.name) + SAMPLE_COLUMN.q];
      const qd = data[i][short(cell.joint.name) + SAMPLE_COLUMN.qd];
      return `<b>${esc(short(cell.joint.name))}</b> at t = ${fmt(t[i])} s<br>q ${fmt(q)}° · qd ${fmt(qd)}°/s`;
    });
    fig.body.append(canvas);
    fig.lead.textContent = `${count(data.length)} samples over ${fmt(tMax)} s (every sample, from samples.json)`;
    setLegend(fig, [{ kind: 'line', colour: FOCUS, label: 'this trajectory' }, { kind: 'line', colour: LIMIT, label: 'a limit, when inside the view' }]);
  }

  function drawSpans(fig, width, row) {
    const signals = ['q', 'qd', 'qdd'];
    const labelW = 86;
    const gap = 12;
    const colW = Math.floor((width - labelW - gap * 2) / 3);
    const rowH = 40;
    const top = 20;
    const height = top + JOINTS.length * rowH + 20;
    const { canvas, g } = canvasOf(width, height, { 'data-spans': '' });
    signals.forEach((signal, c) => {
      const x0 = labelW + c * (colW + gap);
      g.font = '600 11.5px -apple-system, "Segoe UI", Roboto, sans-serif';
      g.fillStyle = SOFT;
      g.textAlign = 'left';
      g.textBaseline = 'alphabetic';
      g.fillText(`${signal} · ${SIGNAL_WORD[signal]}`, x0, 12);
      const box = { x: x0, y: top, w: colW - 30, h: JOINTS.length * rowH };
      for (const p of [0, 50, 100]) {
        const px = box.x + (p / 100) * box.w;
        vline(g, px, box.y, box.y + box.h, p === 100 ? LIMIT : RULE, 1);
        g.fillStyle = MUTED; g.font = FONT_SMALL; g.textAlign = 'center'; g.textBaseline = 'top';
        g.fillText(`${p} %`, px, box.y + box.h + 4);
      }
      JOINTS.forEach((joint, r) => {
        const y = box.y + r * rowH;
        const dataset = P.hist[joint.name][signal].span_pct;
        const mine = row.span_pct[joint.name][signal];
        g.fillStyle = '#c9ced4';
        roundRect(g, box.x, y + 9, Math.max(1, (Math.min(100, dataset) / 100) * box.w), 9, 2);
        g.fillStyle = FOCUS;
        roundRect(g, box.x, y + 21, Math.max(1, (Math.min(100, mine) / 100) * box.w), 9, 2);
        g.font = FONT_SMALL; g.textAlign = 'left'; g.textBaseline = 'middle';
        g.fillStyle = MUTED;
        g.fillText(pct(dataset), box.x + box.w + 4, y + 13.5);
        g.fillStyle = FOCUS;
        g.fillText(pct(mine), box.x + box.w + 4, y + 25.5);
      });
    });
    g.textAlign = 'left';
    g.textBaseline = 'middle';
    JOINTS.forEach((joint, r) => {
      g.font = '600 12px -apple-system, "Segoe UI", Roboto, sans-serif';
      g.fillStyle = INK;
      g.fillText(short(joint.name), 0, top + r * rowH + 19);
    });
    fig.body.append(canvas);
    setLegend(fig, [{ kind: 'fill', colour: '#c9ced4', label: `all ${ROWS.length} (payload)` }, { kind: 'fill', colour: FOCUS, label: 'this trajectory' }, { kind: 'line', colour: LIMIT, label: '100 % = the whole limit span' }]);
  }

  // ── settings (the gear) ──────────────────────────────────────────────────────────────────────────────────────

  const gear = $('[data-v5-gear]');
  const panel = $('[data-v5-settings]');
  function buildSettings() {
    const cmap = el('select', { 'data-v5-cmap': '', 'aria-label': 'Colour map' }, Color.NAMES.map((name) => el('option', { value: name, text: name })));
    cmap.value = state.cmap;
    const preview = el('div', { class: 'ramp-preview', 'data-v5-ramp': '' });
    const reverse = el('input', { type: 'checkbox', 'data-v5-reverse': '' });
    reverse.checked = state.reverse;
    const scale = el('select', { 'data-v5-scale': '', 'aria-label': 'Colour scale' }, Color.SCALES.map((mode) => el('option', { value: mode, text: mode === 'enough' ? `≥ ${P.enough} samples / not` : Color.SCALE_TITLES[mode] })));
    scale.value = state.scale;
    const note = el('p', { class: 'set-note' });
    const mutedBox = el('span');
    const paintPreview = () => {
      preview.style.background = rampGradient();
      note.textContent = SCALE_NOTES[state.scale];
      mutedBox.replaceChildren(segmented(null, [['grey', 'grey'], ['faded', 'faded colour']], state.muted, (value) => {
        state.muted = value; save('muted', value); paintPreview(); redrawFigures();
      }, { 'data-v5-muted': '' }));
    };
    cmap.addEventListener('change', () => { state.cmap = cmap.value; save('cmap', state.cmap); paintPreview(); redrawFigures(); });
    reverse.addEventListener('change', () => { state.reverse = reverse.checked; save('reverse', state.reverse); paintPreview(); redrawFigures(); });
    scale.addEventListener('change', () => { state.scale = scale.value; save('scale', state.scale); paintPreview(); redrawFigures(); });
    paintPreview();
    panel.replaceChildren(
      el('div', { class: 'set-head' }, [el('b', { text: 'Settings' }), el('span', { text: 'every figure · remembered' }),
        el('button', { type: 'button', class: 'set-close', 'data-v5-settings-close': '', 'aria-label': 'Close settings', text: '×', onclick: () => toggleSettings(false) })]),
      el('label', { class: 'set-row' }, [el('span', { text: 'Colour map' }), cmap]),
      preview,
      el('label', { class: 'set-check' }, [reverse, 'Reverse (high = dark)']),
      el('label', { class: 'set-row' }, [el('span', { text: 'Scale' }), scale]),
      note,
      el('hr', { class: 'set-sep' }),
      el('div', { class: 'set-row' }, [el('span', { text: 'Unselected cells', title: 'how the rest of the dataset is drawn while trajectories are selected' }), mutedBox]),
      el('p', { class: 'set-foot', text: 'White = never visited and grey = out of reach on every map; the selection\'s own cells always keep the colour map, cells only it reaches are cyan.' }));
  }
  function toggleSettings(open) {
    const show = open === undefined ? panel.hidden : open;
    panel.hidden = !show;
    gear.setAttribute('aria-expanded', String(show));
  }
  gear.addEventListener('click', (event) => { event.stopPropagation(); toggleSettings(); });
  // WHY composedPath: a control inside the panel may re-render itself on click, detaching event.target before this runs
  document.addEventListener('click', (event) => {
    if (panel.hidden) return;
    const path = event.composedPath();
    if (!path.includes(panel) && !path.includes(gear)) toggleSettings(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!panel.hidden) { toggleSettings(false); return; }
    if (state.page) go(state.prevTab);
  });

  // ── routing + render ─────────────────────────────────────────────────────────────────────────────────────────

  function writeHash() {
    const hash = state.page ? '#traj=' + encodeURIComponent(state.page) : state.tab === 'overview' ? '' : '#tab=' + state.tab;
    try { global.history.replaceState(null, '', global.location.pathname + global.location.search + hash); } catch (error) { /* file:// in some browsers */ }
  }
  function go(tab) {
    state.tab = tab;
    state.page = null;
    writeHash();
    render();
  }
  function openPage(name) {
    if (!name || !byName.has(name)) return;
    if (!state.page) state.prevTab = state.tab;
    state.page = name;
    sel.names = [name];
    sel.set = new Set(sel.names);
    sel.anchor = name;
    writeHash();
    render();
    const node = railParts.list && railParts.list.querySelector(`[data-name="${name}"]`);
    if (node) node.scrollIntoView({ block: 'nearest' });
  }
  function renderTabs() {
    const nav = $('[data-v5-tabs]');
    nav.replaceChildren(...TABS.map(([id, label]) => el('button', {
      type: 'button', class: 'tab', role: 'tab', 'data-v5-tab': id, 'aria-selected': String(!state.page && state.tab === id),
      onclick: () => go(id),
    }, [label, id === 'trajectories' ? el('span', { class: 'tab-n', text: String(ROWS.length) }) : null])));
  }
  function renderContent() {
    hideTip();
    figs = [];
    for (const key of Object.keys(tableParts)) delete tableParts[key];
    const root = el('div', { 'data-v5-view': state.page ? 'trajectory' : state.tab });
    content.replaceChildren(root);
    if (state.page) buildPage(root, state.page);
    else if (state.tab === 'overview') buildOverview(root);
    else if (state.tab === 'limits') buildLimits(root);
    else if (state.tab === 'joint') buildJoint(root);
    else if (state.tab === 'joints') buildJoints(root);
    else if (state.tab === 'position') buildPosition(root);
    else if (state.tab === 'orientation') buildOrientation(root);
    else if (state.tab === 'trajectories') buildTable(root);
    for (const fig of figs) fig.draw();
    content.scrollTop = 0;
  }
  function redrawFigures() {
    hideTip();
    const keep = content.scrollTop;
    for (const fig of figs) if (fig.node.isConnected) fig.draw();
    content.scrollTop = keep;
  }
  function render() {
    app.classList.toggle('wide', !state.page && state.tab === 'trajectories');
    renderTabs();
    renderRail();
    renderFocus();
    renderContent();
  }

  /* #tab=<id> opens a tab, #traj=<name> a trajectory page; returns true when it rendered */
  function route() {
    const hash = global.location.hash.replace(/^#/, '');
    const tabMatch = /^tab=([a-z]+)$/.exec(hash);
    const trajMatch = /^traj=(.+)$/.exec(hash);
    if (trajMatch && byName.has(decodeURIComponent(trajMatch[1]))) { openPage(decodeURIComponent(trajMatch[1])); return true; }
    state.page = null;
    state.tab = tabMatch && TABS.some(([id]) => id === tabMatch[1]) ? tabMatch[1] : 'overview';
    return false;
  }

  function boot() {
    if (!P || !ROWS || !MEM) {
      content.textContent = 'The round\'s data/ is missing: regenerate it with extract.py.';
      return;
    }
    $('[data-v5-title]').textContent = P.title;
    $('[data-v5-crumb-dataset]').textContent = 'UR5e';
    $('[data-v5-subtitle]').textContent = P.subtitle;
    document.title = `${P.title} · coverage (focus rail)`;
    buildSettings();
    buildRail();
    setupRailHandle();
    if (!route()) render();
    // a pasted or edited #tab= / #traj= link routes without a reload (writeHash uses replaceState, which fires nothing)
    global.addEventListener('hashchange', () => { if (!route()) render(); });
    let resizeTimer = 0;
    global.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(redrawFigures, 150); });
    app.setAttribute('data-v5-ready', '');
    setTimeout(loadSamples, 30);
  }
  boot();
})(window);
