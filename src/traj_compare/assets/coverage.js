/* coverage.js — the trajectory coverage page (docs/COVERAGE.md, "The custom page").
 *
 * Reads ONLY the payload "traj_compare.coverage/1" embedded as <script id="cov-payload">, and draws every 2-D view on
 * <canvas>; the three.js views come from coverage3d.js (window.Coverage3D) when it is in the page. Every colour comes
 * from coverage_color.js (window.CoverageColor), so the page, Matplotlib, Viser and W&B can never disagree.
 *
 * Zach's rules this page keeps (2026-11-19 / 11-23 coverage feedback):
 *  - one calm answer first, detail on demand; titles are the question a figure answers, the code id beside it;
 *  - "This is good as long as you show the legend of the meaning of the lines": every mark is named in a legend;
 *  - "Linear to me is BY far the most informative": linear is the default scale;
 *  - "lets make it easy for the user to change ... to other good cmap and switch from high to low": cmap + Reverse;
 *  - white = empty, grey = beyond the limit, red = the limit, amber/red otherwise only for problems; angles in degrees.
 */
(function (global) {
  'use strict';

  const Color = global.CoverageColor;
  const STORE = 'traj_compare.coverage.';
  const FONT = '10.5px -apple-system, "Segoe UI", Roboto, sans-serif';
  const FONT_BOLD = '600 11.5px -apple-system, "Segoe UI", Roboto, sans-serif';
  const INK = '#22211f';
  const SOFT = '#52514e';
  const MUTED = '#8a8983';
  const AXIS = '#b9b8b2';
  const RULE = '#efeee9';
  const ACCENT = '#2a78d6';
  const ALLOWED = '#e3ecf7';
  const HIGHLIGHT = '#0b0b0b';
  // WHY no orange/amber/red among the group colours: amber and red mean "a problem" on this page (and red = a limit)
  const GROUP_COLOURS = ['#2a78d6', '#2f9e44', '#8e5bd1', '#17a2b8', '#6b7a8f', '#c22f6e'];
  const POWER = { q: '', qd: '/s', qdd: '/s²', qddd: '/s³' };
  const WORD = { q: 'position', qd: 'speed', qdd: 'acceleration', qddd: 'jerk' };
  const SCALE_NOTES = {
    linear: 'Linear: colour grows in proportion to the count; the top 2 % of cells are clipped so one hot cell does not wash out the rest.',
    log: 'Log: colour follows log(count), so thin cells show too; equal colour steps are ×10, not +10.',
    // WHY spelled out: Zach 2026-11-23, "why are more areas stronger in the histogram equalizer"
    equalized: 'Equalized: colour = rank among the visited cells, so every visited cell gets an even share of the colours. It shows WHERE the data is, not HOW MUCH: thin areas look as strong as busy ones.',
    visited: 'Visited / not: one colour for every cell with any sample. Is it covered at all?',
    enough: 'Enough / not: full colour = at least the "enough" count of samples (enough to trust); pale = visited, but fewer.',
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
      else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of [].concat(children === undefined ? [] : children)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child.nodeType ? child : String(child));
    }
    return node;
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function minus(text) { return String(text).replace(/^-/, '−'); }

  function fmt(value) {
    if (value === null || value === undefined || !Number.isFinite(value)) return '—';
    const size = Math.abs(value);
    let text;
    if (size >= 1e6) text = (value / 1e6).toFixed(size >= 1e7 ? 0 : 1) + ' M';
    else if (size >= 1e4) text = (value / 1e3).toFixed(size >= 1e5 ? 0 : 1) + ' k';
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
    return Math.round(value).toLocaleString('en-US').replace(/,/g, ' ');
  }

  function duration(seconds) {
    if (!Number.isFinite(seconds)) return '—';
    if (seconds < 120) return fmt(seconds) + ' s';
    if (seconds < 7200) return (seconds / 60).toFixed(1).replace(/\.0$/, '') + ' min';
    return (seconds / 3600).toFixed(1).replace(/\.0$/, '') + ' h';
  }

  function numberText(row) {
    const value = row.value;
    if (row.unit === '%') return pct(value);
    if (row.unit === 's') return duration(value);
    if (row.unit === 'deg') return Math.round(value) + '°';
    if (row.unit === 'm/s') return value.toFixed(2) + ' m/s';
    if (!row.unit) return Number.isInteger(value) || Math.abs(value) >= 100 ? count(value) : fmt(value);
    return fmt(value) + ' ' + row.unit;
  }

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

  function clamp(value, lo, hi) { return Math.min(hi, Math.max(lo, value)); }

  function edges(spec) {
    const [lo, hi, n] = spec;
    return { lo, hi, n, step: (hi - lo) / n, at: (i) => lo + (i * (hi - lo)) / n };
  }

  function lut(ramp) {
    const table = new Array(256);
    for (let k = 0; k < 256; k++) table[k] = ramp(k / 255);
    return (t) => table[Math.round(clamp(t, 0, 1) * 255)];
  }

  function rgbCss(rgb) { return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`; }

  function rampGradient(ramp) {
    const stops = [];
    for (let k = 0; k <= 8; k++) stops.push(rgbCss(ramp(k / 8)));
    return `linear-gradient(90deg, ${stops.join(', ')})`;
  }

  // ── the page's state ──────────────────────────────────────────────────────────────────────────────────────────

  let payload = null;
  const state = { cmap: 'viridis', reverse: false, scale: 'linear', joint: 0, tab: 'overview', highlight: null, enough: 10 };
  const tabs = [];
  const figures = [];
  const bodies = new Map();
  const mounts = [];
  const highlightListeners = [];
  let pending = new Set();
  let frame = 0;
  let tip = null;

  function joints() { return payload.joints; }
  function jointName(index) { return payload.joints[index].name; }
  function selectedJoint() { return payload.joints[state.joint]; }
  function rampNow() { return Color.ramp(state.cmap, state.reverse); }
  function ctx() {
    return { cmap: state.cmap, reverse: state.reverse, scale: state.scale, enough: state.enough, joint: state.joint,
      ramp: Color.ramp(state.cmap, state.reverse) };
  }
  function scaleTitle(mode) {
    return mode === 'enough' ? `≥ ${state.enough} samples / not` : Color.SCALE_TITLES[mode];
  }

  function unitOf(joint, signal) {
    const base = joint.display.unit === 'deg' ? '°' : joint.display.unit;
    return base + POWER[signal];
  }
  function withUnit(joint, signal, value) {
    const unit = unitOf(joint, signal);
    return fmt(value * joint.display.scale) + (unit.startsWith('°') ? unit : ' ' + unit);
  }
  function limitOf(name, signal) { return payload.limits[name][signal]; }
  function stated(limit) { return limit && limit.source === 'limit'; }
  function groupNames() { return (payload.source.groups || []); }
  function groupColour(name) {
    const index = groupNames().indexOf(name);
    return GROUP_COLOURS[(index < 0 ? 0 : index) % GROUP_COLOURS.length];
  }
  function trajectoryGroup(index) {
    const by = payload.source.group_by;
    if (!by) return null;
    const tags = (payload.trajectories[index] || {}).tags || {};
    return tags[by] === undefined ? null : String(tags[by]);
  }

  // ── canvas drawing ────────────────────────────────────────────────────────────────────────────────────────────

  function canvasOf(width, height, attrs) {
    const ratio = Math.min(2, global.devicePixelRatio || 1);
    const canvas = el('canvas', attrs);
    canvas.width = Math.max(1, Math.round(width * ratio));
    canvas.height = Math.max(1, Math.round(height * ratio));
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
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

  /* x, y: {lo, hi, label, ticks?, tickText?, show?} in display units */
  function drawAxes(g, box, x, y) {
    g.save();
    g.font = FONT;
    g.strokeStyle = AXIS;
    g.fillStyle = MUTED;
    g.lineWidth = 1;
    if (x && x.show !== false) {
      const xt = x.ticks || ticks(x.lo, x.hi, Math.max(2, Math.floor(box.w / 64)));
      const step = xt.step || (xt.length > 1 ? Math.abs(xt[1] - xt[0]) : 1);
      g.textAlign = 'center';
      g.textBaseline = 'top';
      for (const v of xt) {
        const px = box.x + ((v - x.lo) / (x.hi - x.lo)) * box.w;
        if (px < box.x - 0.5 || px > box.x + box.w + 0.5) continue;
        g.beginPath(); g.moveTo(Math.round(px) + 0.5, box.y + box.h); g.lineTo(Math.round(px) + 0.5, box.y + box.h + 4); g.stroke();
        g.fillText(x.tickText ? x.tickText(v) : tickText(v, step), px, box.y + box.h + 6);
      }
      if (x.label) { g.fillStyle = SOFT; g.fillText(x.label, box.x + box.w / 2, box.y + box.h + 20); g.fillStyle = MUTED; }
    }
    if (y && y.show !== false) {
      const yt = y.ticks || ticks(y.lo, y.hi, Math.max(2, Math.floor(box.h / 40)));
      const step = yt.step || (yt.length > 1 ? Math.abs(yt[1] - yt[0]) : 1);
      g.textAlign = 'right';
      g.textBaseline = 'middle';
      for (const v of yt) {
        const py = box.y + box.h - ((v - y.lo) / (y.hi - y.lo)) * box.h;
        if (py < box.y - 0.5 || py > box.y + box.h + 0.5) continue;
        g.beginPath(); g.moveTo(box.x - 4, Math.round(py) + 0.5); g.lineTo(box.x, Math.round(py) + 0.5); g.stroke();
        if (y.labels !== false) g.fillText(y.tickText ? y.tickText(v) : tickText(v, step), box.x - 6, py);
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

  /* t: Float32Array (-1 = empty), cell (i, j) at t[i * ny + j], i along x, j along y (j = 0 at the bottom) */
  function heatImage(nx, ny, t, colour, outside, rows) {
    const shown = rows === undefined ? ny : rows;
    const image = document.createElement('canvas');
    image.width = nx;
    image.height = shown;
    const ig = image.getContext('2d');
    const data = ig.createImageData(nx, shown);
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < shown; j++) {
        const k = i * ny + j;
        const rgb = t[k] >= 0 ? colour(t[k]) : outside && outside(k) ? Color.OUTSIDE : Color.EMPTY;
        const p = ((shown - 1 - j) * nx + i) * 4;
        data.data[p] = rgb[0]; data.data[p + 1] = rgb[1]; data.data[p + 2] = rgb[2]; data.data[p + 3] = 255;
      }
    }
    ig.putImageData(data, 0, 0);
    return image;
  }

  function drawImage(g, image, box) {
    g.save();
    g.imageSmoothingEnabled = false;
    g.drawImage(image, box.x, box.y, box.w, box.h);
    g.restore();
  }

  function strokeBox(g, box, colour, width) {
    g.save();
    g.strokeStyle = colour;
    g.lineWidth = width || 1;
    const half = (width || 1) / 2;
    g.strokeRect(box.x - half + 0.5, box.y - half + 0.5, box.w + 2 * half - 1, box.h + 2 * half - 1);
    g.restore();
  }

  function vline(g, x, y0, y1, colour, width, dash) {
    g.save();
    g.strokeStyle = colour;
    g.lineWidth = width || 1;
    if (dash) g.setLineDash(dash);
    g.beginPath(); g.moveTo(Math.round(x) + 0.5, y0); g.lineTo(Math.round(x) + 0.5, y1); g.stroke();
    g.restore();
  }

  function hline(g, y, x0, x1, colour, width, dash) {
    g.save();
    g.strokeStyle = colour;
    g.lineWidth = width || 1;
    if (dash) g.setLineDash(dash);
    g.beginPath(); g.moveTo(x0, Math.round(y) + 0.5); g.lineTo(x1, Math.round(y) + 0.5); g.stroke();
    g.restore();
  }

  /* bar heights (0..1, < 0 = none) over [lo, hi] as a step outline filled; `stack` splits each bar by group */
  function drawBars(g, sx, base, height, e, heights, fill, stack) {
    for (let i = 0; i < e.n; i++) {
      const h = heights[i];
      if (!(h > 0)) continue;
      const x0 = sx(e.at(i));
      const x1 = sx(e.at(i + 1));
      const w = Math.max(0.8, x1 - x0 + 0.25);
      const total = h * height;
      if (!stack) {
        g.fillStyle = fill;
        g.fillRect(x0, base - total, w, total);
        continue;
      }
      let y = base;
      for (const part of stack) {
        const share = part.total[i] > 0 ? part.counts[i] / part.total[i] : 0;
        if (!(share > 0)) continue;
        g.fillStyle = part.colour;
        g.fillRect(x0, y - total * share, w, total * share);
        y -= total * share;
      }
    }
  }

  function heights(counts, mode) {
    // WHY the page's scale also sets bar heights: one switch, the same meaning in 1-D and 2-D. Linear clips at p98
    // here too: the rest pose (qd = 0, tool speed 0) is one bin holding most samples, and unclipped it flattens every
    // other bar to a sliver. A clipped bar gets a dark cap (drawBars), so the clip is never hidden.
    const scaled = Color.scale(counts, mode, { enough: state.enough });
    const clipped = counts.map((v) => mode === 'linear' && v > scaled.max);
    return { t: Array.from(scaled.t, (v) => (v < 0 ? 0 : v)), clipped, scaled };
  }

  function drawCaps(g, sx, base, height, e, bars) {
    g.fillStyle = INK;
    for (let i = 0; i < e.n; i++) {
      if (!bars.clipped[i]) continue;
      const x0 = sx(e.at(i));
      const x1 = sx(e.at(i + 1));
      g.fillRect(x0 - 1, base - height * bars.t[i] - 1, Math.max(2.5, x1 - x0 + 2), 2.5);
    }
  }

  function anyClipped(bars) { return bars.clipped.some(Boolean); }

  const CAP_LEGEND = { kind: 'line', colour: INK, label: 'dark cap = a bar taller than the scale\'s top (linear clips at p98: the rest pose is one huge bin)' };

  // ── tooltip ───────────────────────────────────────────────────────────────────────────────────────────────────

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

  function hideTip() { if (tip) tip.hidden = true; }

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
        click(event.clientX - rect.left, event.clientY - rect.top);
      });
    }
  }

  // ── figure, legend, colorbar, switches ────────────────────────────────────────────────────────────────────────

  function figure(id, title, how, prior) {
    const titleText = el('span', { text: title });
    const tools = el('div', { class: 'cov-figtools' });
    const lead = el('p', { class: 'cov-lead' });
    const body = el('div', { class: 'cov-figbody' });
    const legendBox = el('div', { class: 'cov-legend', 'data-cov-legend': '' });
    const details = el('details', { class: 'cov-how' }, [
      el('summary', { text: 'How to read this' }),
      el('p', { text: how }),
      prior ? el('p', { class: 'cov-prior', text: 'Prior art: ' + prior }) : null,
    ]);
    const node = el('figure', { class: 'cov-figure', 'data-cov-figure': id }, [
      el('header', { class: 'cov-fighead' }, [el('h3', null, [titleText, el('code', { class: 'cov-id', text: id })]), tools]),
      lead, body, legendBox, details,
    ]);
    return { id, node, titleText, tools, lead, body, legend: legendBox };
  }

  /* items: {kind, colour?, label, note?, problem?}; kind: fill | empty | outside | line | thin | dash | tick | frame |
   * ramp | cross | text */
  function setLegend(fig, items) {
    fig.legend.replaceChildren();
    for (const item of items) {
      if (!item) continue;
      const swatch = item.kind === 'text' ? null : el('i', { class: 'cov-sw ' + item.kind });
      if (swatch) {
        if (item.kind === 'fill') swatch.style.background = item.colour;
        else if (item.kind === 'ramp') swatch.style.background = rampGradient(rampNow());
        else if (item.colour) swatch.style.color = item.colour;
        if (item.alpha !== undefined) swatch.style.opacity = item.alpha;
      }
      fig.legend.append(el('span', { class: 'cov-li' + (item.problem ? ' problem' : '') }, [
        swatch, el('span', null, [item.label, item.note ? el('span', { class: 'note', text: ' ' + item.note }) : null]),
      ]));
    }
  }

  function colorbar(scaled, title, height) {
    const h = Math.max(70, Math.round(height));
    const ramp = rampNow();
    const bar = canvasOf(14, h);
    const g = bar.g;
    const positions = [];
    if (scaled.mode === 'visited') {
      g.fillStyle = rgbCss(ramp(1)); g.fillRect(0, 0, 14, h);
      positions.push({ y: 0.5, label: 'visited' });
    } else if (scaled.mode === 'enough') {
      g.fillStyle = rgbCss(ramp(1)); g.fillRect(0, 0, 14, h / 2);
      g.fillStyle = rgbCss(ramp(0.25)); g.fillRect(0, h / 2, 14, h / 2);
      for (const tick of scaled.ticks) positions.push({ y: tick.t >= 1 ? 0.75 : 0.25, label: tick.label });
    } else {
      for (let y = 0; y < h; y++) { g.fillStyle = rgbCss(ramp(1 - y / Math.max(1, h - 1))); g.fillRect(0, y, 14, 1); }
      for (const tick of scaled.ticks) positions.push({ y: tick.t, label: tick.label });
    }
    const labels = [];
    let last = -1;
    for (const item of positions.sort((a, b) => a.y - b.y)) {
      // WHY skip a label that would overlap the one below it (log's 1, 10, 100 can crowd near the bottom)
      if (last >= 0 && (item.y - last) * h < 11) continue;
      labels.push(el('span', { class: 'cov-cb-tick', style: `bottom:${(item.y * h).toFixed(1)}px`, text: minus(item.label) }));
      last = item.y;
    }
    return el('div', { class: 'cov-colorbar' }, [
      el('div', { class: 'cov-cb-title', text: title }),
      el('div', { class: 'cov-cb-body', style: `height:${h}px` }, [bar.canvas, ...labels]),
      el('div', { class: 'cov-cb-note', text: scaled.note }),
    ]);
  }

  function segmented(label, options, value, onChange) {
    const box = el('div', { class: 'cov-seg', role: 'group', 'aria-label': label });
    for (const [optionValue, optionLabel] of options) {
      box.append(el('button', {
        type: 'button', 'data-value': optionValue, 'aria-pressed': String(optionValue === value), text: optionLabel,
        onclick: () => {
          for (const button of box.children) button.setAttribute('aria-pressed', String(button.dataset.value === optionValue));
          onChange(optionValue);
        },
      }));
    }
    return el('span', { class: 'cov-figtools' }, [el('span', { class: 'cov-seg-label', text: label }), box]);
  }

  /* two figures side by side; the boundary drags (Zach: every panel boundary draggable), width remembered */
  function split(left, right, key, initial) {
    const handle = el('div', { class: 'cov-split-handle', role: 'separator', 'aria-orientation': 'vertical',
      title: 'Drag to resize · double-click to reset' });
    const box = el('div', { class: 'cov-split' }, [left.node, handle, right.node]);
    right.node.classList.add('cov-pane-right');
    const start = initial || 0.5;
    let share = clamp(Number(load('split.' + key, start)) || start, 0.2, 0.8);
    const apply = () => { left.node.style.flex = `0 0 calc(${(share * 100).toFixed(2)}% - 6px)`; };
    apply();
    handle.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      handle.classList.add('dragging');
      const rect = box.getBoundingClientRect();
      const move = (e) => { share = clamp((e.clientX - rect.left) / rect.width, 0.2, 0.8); apply(); };
      const up = () => {
        handle.classList.remove('dragging');
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', up);
        save('split.' + key, share);
      };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', up);
    });
    handle.addEventListener('dblclick', () => { share = start; apply(); save('split.' + key, share); });
    return box;
  }

  // ── figure registry: draw on show, redraw on control change and on resize ─────────────────────────────────────

  function register(tab, fig, draw) {
    const entry = { tab, fig, draw, width: -1 };
    figures.push(entry);
    bodies.set(fig.body, entry);
    if (global.ResizeObserver) observer.observe(fig.body);
    return entry;
  }

  function drawFigure(entry) {
    const width = Math.floor(entry.fig.body.clientWidth);
    if (width <= 0) return;
    entry.width = width;
    entry.fig.body.replaceChildren();
    hideTip();
    try {
      entry.draw(width);
    } catch (error) {
      console.error(error);
      entry.fig.body.append(el('p', { class: 'cov-error', text: 'This figure failed to draw: ' + error.message }));
    }
  }

  const observer = global.ResizeObserver ? new ResizeObserver((entries) => {
    for (const item of entries) {
      const entry = bodies.get(item.target);
      if (!entry) continue;
      const width = Math.floor(item.target.clientWidth);
      if (width > 0 && Math.abs(width - entry.width) > 1) pending.add(entry);
    }
    // WHY drawn in the next frame, not here: drawing inside the observer's callback re-triggers it
    if (pending.size && !frame) {
      frame = requestAnimationFrame(() => {
        frame = 0;
        const batch = pending;
        pending = new Set();
        for (const entry of batch) if (entry.fig.body.clientWidth > 0) drawFigure(entry);
      });
    }
  }) : null;

  function drawTab(tab) {
    for (const entry of figures) if (entry.tab === tab.id) drawFigure(entry);
    for (const mount of mounts) {
      if (mount.tab !== tab.id || !mount.handle || !mount.handle.update) continue;
      try { mount.handle.update(ctx()); } catch (error) { console.error(error); }
    }
    tab.dirty = false;
  }

  function refresh() {
    for (const tab of tabs) {
      if (!tab.built) continue;
      if (tab.id === state.tab) drawTab(tab); else tab.dirty = true;
    }
  }

  function mount3d(tab, fig, viewId) {
    if (!global.Coverage3D || typeof global.Coverage3D.mount !== 'function') {
      fig.body.append(el('div', { class: 'cov-missing', text: 'The 3-D view is not in this build of the page.' }));
      setLegend(fig, [{ kind: 'text', label: 'The 3-D views need coverage3d.js, which was not found when this page was written; rewrite the page once it is installed.' }]);
      return;
    }
    try {
      const handle = global.Coverage3D.mount(fig.body, viewId, payload, ctx());
      mounts.push({ tab, handle });
      if (handle && handle.highlight && state.highlight !== null) handle.highlight(state.highlight);
    } catch (error) {
      console.error(error);
      fig.body.append(el('p', { class: 'cov-error', text: 'The 3-D view failed to start: ' + error.message }));
    }
  }

  function setHighlight(index) {
    state.highlight = index === state.highlight ? null : index;
    for (const mount of mounts) {
      if (!mount.handle || !mount.handle.highlight) continue;
      try { mount.handle.highlight(state.highlight); } catch (error) { console.error(error); }
    }
    for (const listener of highlightListeners) listener(state.highlight);
  }

  // ── header: siblings, the answer, the numbers, the sticky bar ─────────────────────────────────────────────────

  function buildSiblings() {
    const box = document.getElementById('cov-siblings');
    if (!box || !payload.siblings || !payload.siblings.length) return;
    const groups = new Map();
    for (const sibling of payload.siblings) {
      const group = sibling.group || '';
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(sibling);
    }
    for (const [group, items] of groups) {
      const row = el('div', { class: 'cov-sibgroup' }, group ? el('span', { class: 'grouplabel', text: group }) : null);
      for (const item of items) {
        row.append(item.current
          ? el('a', { class: 'chip on', 'aria-current': 'page', text: item.label })
          : el('a', { class: 'chip', href: item.href, text: item.label }));
      }
      box.append(row);
    }
  }

  function numberByKey(key) {
    const row = (payload.numbers || []).find((item) => item.key === key);
    return row ? row.value : null;
  }

  function buildAnswer() {
    const source = payload.source;
    const parts = [];
    const trajectories = source.trajectories;
    parts.push(`<b>${count(trajectories)} ${trajectories === 1 ? 'trajectory' : 'trajectories'}</b>, ${duration(source.duration_s)} of motion.`);
    const spans = joints().map((joint) => ({ name: joint.name, span: payload.hist[joint.name].q.span_pct }))
      .filter((item) => Number.isFinite(item.span));
    if (spans.length) {
      const least = spans.reduce((a, b) => (b.span < a.span ? b : a));
      const median = numberByKey('q_span_median_pct');
      parts.push(`The joints use a median <b>${pct(median)}</b> of their position range (least: ${escapeHtml(least.name)}, ${pct(least.span)}).`);
    }
    const speed = numberByKey('qd_peak_max_pct');
    const accel = numberByKey('qdd_peak_max_pct');
    if (speed !== null) parts.push(`The fastest joint reaches <b>${pct(speed)}</b> of its speed limit, the hardest-accelerating <b>${pct(accel)}</b> of its acceleration limit.`);
    const plane = numberByKey('q_qd_visited_mean_pct');
    if (plane !== null) parts.push(`On average <b>${pct(plane)}</b> of a joint's position × speed cells are visited.`);
    if (payload.tool) {
      const voxels = numberByKey('tool_voxels_visited');
      const directions = numberByKey('tool_directions_visited_pct');
      const tilt = numberByKey('tool_tilt_max_deg');
      parts.push(`The tool passes through <b>${count(voxels)}</b> 5 cm voxels and points in <b>${pct(directions)}</b> of all directions, tilting up to <b>${Math.round(tilt)}°</b>.`);
    }
    const beyond = [];
    for (const joint of joints()) {
      for (const signal of payload.signals) {
        const h = payload.hist[joint.name][signal];
        if (stated(limitOf(joint.name, signal)) && h.outside > 0) beyond.push(`${joint.name} ${signal}`);
      }
    }
    if (beyond.length) {
      parts.push(`<span class="cov-problem">${count(beyond.length)} joint signal${beyond.length === 1 ? '' : 's'} go past a stated limit (${escapeHtml(beyond.slice(0, 4).join(', '))}${beyond.length > 4 ? ', …' : ''}); see Limits.</span>`);
    }
    return el('div', { class: 'cov-answer', html: parts.join(' ') });
  }

  function buildNumbers() {
    const box = el('div', { class: 'cov-numbers', 'data-cov-numbers': '' });
    for (const row of payload.numbers || []) {
      box.append(el('div', { class: 'cov-number', title: row.key }, [
        el('span', { class: 'label', text: row.label }),
        el('span', { class: 'value', text: numberText(row) }),
        el('span', { class: 'key', text: row.key }),
      ]));
    }
    return box;
  }

  function buildBar(available) {
    const nav = el('nav', { class: 'cov-tabs', 'data-cov-nav': '', role: 'tablist' });
    for (const tab of available) {
      tab.button = el('button', { class: 'cov-tab', type: 'button', role: 'tab', 'data-cov-tab': tab.id, text: tab.label,
        title: tab.hint, onclick: () => show(tab.id) });
      nav.append(tab.button);
    }
    const cmap = el('select', { 'data-cov-cmap': '', 'aria-label': 'Colour map' },
      Color.NAMES.map((name) => el('option', { value: name, text: name })));
    cmap.value = state.cmap;
    const reverse = el('input', { type: 'checkbox', 'data-cov-reverse': '' });
    reverse.checked = state.reverse;
    const scale = el('select', { 'data-cov-scale': '', 'aria-label': 'Colour scale' },
      Color.SCALES.map((mode) => el('option', { value: mode, text: scaleTitle(mode) })));
    scale.value = state.scale;
    const joint = el('select', { 'data-cov-joint': '', 'aria-label': 'Joint' },
      joints().map((item, index) => el('option', { value: String(index), text: item.name })));
    joint.value = String(state.joint);
    const swatch = el('span', { class: 'cov-ramp', title: 'the colour map now in use: low → high' });
    const note = el('span', { class: 'cov-scale-note' });
    const chip = el('span', { class: 'cov-highlight', hidden: true });
    const paint = () => {
      swatch.style.background = rampGradient(rampNow());
      note.textContent = SCALE_NOTES[state.scale].replace('the "enough" count', `${state.enough}`);
    };
    paint();
    cmap.addEventListener('change', () => { state.cmap = cmap.value; save('cmap', state.cmap); paint(); refresh(); });
    reverse.addEventListener('change', () => { state.reverse = reverse.checked; save('reverse', state.reverse); paint(); refresh(); });
    scale.addEventListener('change', () => { state.scale = scale.value; save('scale', state.scale); paint(); refresh(); });
    joint.addEventListener('change', () => { state.joint = Number(joint.value); save('joint', jointName(state.joint)); refresh(); });
    state.jointSelect = joint;
    highlightListeners.push((index) => {
      chip.hidden = index === null;
      chip.replaceChildren();
      if (index === null) return;
      chip.append(el('span', { text: 'Highlighted: ' + payload.trajectories[index].name }),
        el('button', { type: 'button', title: 'Clear the highlight', text: '×', onclick: () => setHighlight(index) }));
    });
    const controls = el('div', { class: 'cov-controls' }, [
      el('label', { class: 'cov-ctl' }, [el('span', { class: 'ctl-label', text: 'Colours' }), cmap, swatch]),
      el('label', { class: 'cov-ctl' }, [reverse, 'Reverse (high = dark)']),
      el('label', { class: 'cov-ctl' }, [el('span', { class: 'ctl-label', text: 'Scale' }), scale]),
      el('label', { class: 'cov-ctl', title: 'the joint the One joint tab shows' }, [el('span', { class: 'ctl-label', text: 'Joint' }), joint]),
      chip,
      note,
    ]);
    return el('div', { class: 'cov-bar' }, [nav, controls]);
  }

  function selectJoint(index) {
    state.joint = index;
    save('joint', jointName(index));
    if (state.jointSelect) state.jointSelect.value = String(index);
    refresh();
  }

  // ── overview ──────────────────────────────────────────────────────────────────────────────────────────────────

  function toPct(value, limit) { return (2 * (value - limit.low) / (limit.high - limit.low) - 1) * 100; }

  function buildOverview(section) {
    const ridge = figure('ridgeline', 'How much of its limits does each joint use?',
      'One row per joint, one column per signal. Each signal is put on its own limit: −100 % is the low limit, +100 % the high limit (for speed and acceleration, minus and plus the limit). The bars are the samples, each row scaled to its own tallest bar; the black hairline under a row spans where the data really went (its 0.1st to 99.9th percentile, so one noisy sample cannot set it). A row that fills the space between the red lines uses its whole range; a narrow ridge in the middle means the joint barely moves. Click a row to open that joint.',
      'TensorBoard histograms (offset mode) / joy plots, normalized per axis like a robot limit dashboard; the Nov 19 coverage gallery "fleet ridgeline".');
    register('overview', ridge, (width) => drawRidgeline(ridge, width));
    const table = figure('summary-table', 'Each joint in numbers: range, speed and acceleration used',
      'One row per joint. "Range used" is the share of the position range between the data\'s 0.1st and 99.9th percentile; "peak" is the largest speed / acceleration / jerk reached (99.9th percentile) as a share of its limit. "Cells visited" counts the cells of the joint\'s position × speed and speed × acceleration grids with any sample. A dash means no limit is stated for that signal, so there is nothing to be a share of. Click a row to open that joint.',
      'TFDV / Facets Overview: one row per feature with its range against the schema.');
    register('overview', table, (width) => drawSummaryTable(table, width));
    section.append(ridge.node, table.node);
  }

  function drawRidgeline(fig, width) {
    const signals = ['q', 'qd', 'qdd'];
    const titles = { q: 'q · position in its range', qd: 'qd · speed against its limit', qdd: 'qdd · acceleration against its limit' };
    const rowH = 38;
    const labelW = Math.min(150, Math.max(90, Math.round(width * 0.1)));
    const noteW = 62;
    const gap = 14;
    const top = 22;
    const bottom = 40;
    const colW = (width - labelW - signals.length * noteW - (signals.length - 1) * gap) / signals.length;
    const height = top + joints().length * rowH + bottom;
    const { canvas, g } = canvasOf(width, height);
    const domain = { lo: -118, hi: 118 };
    let anyData = false;
    let anyBeyond = false;
    let anyCap = false;
    const samples = Math.max(1, payload.source.samples);
    const columns = signals.map((signal, c) => {
      const x0 = labelW + c * (colW + noteW + gap);
      return { signal, box: { x: x0, y: top, w: colW, h: joints().length * rowH } };
    });
    g.font = FONT_BOLD;
    g.fillStyle = INK;
    g.textBaseline = 'alphabetic';
    for (const column of columns) { g.textAlign = 'left'; g.fillText(titles[column.signal], column.box.x, 14); }
    joints().forEach((joint, r) => {
      const base = top + (r + 1) * rowH - 9;
      if (r === state.joint) { g.fillStyle = '#f2f6fb'; g.fillRect(0, top + r * rowH, width, rowH); }
      if (r > 0) hline(g, top + r * rowH, 0, width, RULE);
      g.font = r === state.joint ? FONT_BOLD : '11.5px -apple-system, "Segoe UI", Roboto, sans-serif';
      g.fillStyle = INK;
      g.textAlign = 'right';
      g.textBaseline = 'middle';
      g.fillText(fitText(g, joint.name, labelW - 12), labelW - 12, base - 10);
      for (const column of columns) {
        const limit = limitOf(joint.name, column.signal);
        const h = payload.hist[joint.name][column.signal];
        const { sx } = mapper(column.box, domain, { lo: 0, hi: 1 });
        const e = edges(h.edges);
        const pe = { n: e.n, at: (i) => toPct(e.at(i), limit) };
        const bars = heights(h.counts, state.scale);
        drawBars(g, sx, base, rowH - 14, pe, bars.t, ACCENT);
        drawCaps(g, sx, base, rowH - 14, pe, bars);
        if (anyClipped(bars)) anyCap = true;
        if (h.counts.some((v) => v > 0)) anyData = true;
        if (stated(limit)) {
          vline(g, sx(-100), base - rowH + 12, base + 3, Color.LIMIT, 1.2);
          vline(g, sx(100), base - rowH + 12, base + 3, Color.LIMIT, 1.2);
        } else {
          vline(g, sx(-100), base - rowH + 12, base + 3, MUTED, 1, [3, 3]);
          vline(g, sx(100), base - rowH + 12, base + 3, MUTED, 1, [3, 3]);
        }
        if (Number.isFinite(h.p001) && Number.isFinite(h.p999)) {
          const a = sx(clamp(toPct(h.p001, limit), domain.lo, domain.hi));
          const b = sx(clamp(toPct(h.p999, limit), domain.lo, domain.hi));
          hline(g, base + 3, a, b, INK, 1);
          vline(g, a, base, base + 6, INK, 1);
          vline(g, b, base, base + 6, INK, 1);
        }
        g.font = FONT;
        g.textAlign = 'left';
        g.textBaseline = 'middle';
        if (!stated(limit)) {
          g.fillStyle = MUTED;
          g.fillText('no limit', column.box.x + colW + 6, base - 10);
        } else if (h.outside > 0) {
          anyBeyond = true;
          g.fillStyle = Color.LIMIT;
          g.fillText(`▸ ${pct((100 * h.outside) / samples)}`, column.box.x + colW + 6, base - 10);
        }
      }
    });
    for (const column of columns) {
      const box = { x: column.box.x, y: top, w: colW, h: joints().length * rowH };
      drawAxes(g, box, { lo: domain.lo, hi: domain.hi, ticks: [-100, -50, 0, 50, 100],
        tickText: (v) => (v === -100 ? '−100 %' : v === 100 ? '+100 %' : minus(String(v))),
        label: column.signal === 'q' ? '−100 % = low limit, +100 % = high limit' : '± 100 % = ± the limit' }, { show: false });
    }
    fig.body.append(canvas);
    hover(canvas, (px, py) => {
      const r = Math.floor((py - top) / rowH);
      if (r < 0 || r >= joints().length) return null;
      const column = columns.find((c) => px >= c.box.x - 4 && px <= c.box.x + colW + noteW);
      const joint = joints()[r];
      if (!column) return `<b>${escapeHtml(joint.name)}</b> · click to open this joint`;
      const h = payload.hist[joint.name][column.signal];
      const limit = limitOf(joint.name, column.signal);
      const used = column.signal === 'q' ? `${pct(h.span_pct)} of the range used` : `peak ${pct(h.peak_pct)} of the limit`;
      const lim = stated(limit) ? `limit ${withUnit(joint, column.signal, limit.low)} … ${withUnit(joint, column.signal, limit.high)}` : 'no limit stated';
      return `<b>${escapeHtml(joint.name)} · ${column.signal}</b> (${WORD[column.signal]})<br>${used}<br>data p0.1–p99.9: ${withUnit(joint, column.signal, h.p001)} … ${withUnit(joint, column.signal, h.p999)}<br>${lim}${h.outside > 0 ? `<br>${count(h.outside)} samples beyond the limit` : ''}<br>click to open this joint`;
    }, (px, py) => {
      const r = Math.floor((py - top) / rowH);
      if (r < 0 || r >= joints().length) return;
      selectJoint(r);
      show('joint');
    });
    setLegend(fig, [
      { kind: 'fill', colour: ACCENT, label: `samples (bar height: ${scaleTitle(state.scale)}, each row scaled to its own tallest bar)` },
      { kind: 'line', colour: Color.LIMIT, label: 'the joint\'s limit (−100 % low, +100 % high)' },
      joints().some((j) => payload.signals.slice(0, 3).some((s) => !stated(limitOf(j.name, s))))
        ? { kind: 'dash', colour: MUTED, label: 'no limit stated: ±100 % = the data\'s p0.1–p99.9 widened ×1.15' } : null,
      { kind: 'thin', colour: INK, label: 'black hairline = p0.1 – p99.9 of the data (where it really went)' },
      anyCap ? CAP_LEGEND : null,
      anyBeyond ? { kind: 'text', label: '▸ x % = share of samples beyond the limit', problem: true } : null,
      { kind: 'fill', colour: '#f2f6fb', label: 'the joint picked in the Joint control' },
      anyData ? null : { kind: 'text', label: 'no samples' },
    ]);
  }

  function fitText(g, text, width) {
    if (g.measureText(text).width <= width) return text;
    let cut = text;
    while (cut.length > 1 && g.measureText(cut + '…').width > width) cut = cut.slice(0, -1);
    return cut + '…';
  }

  function minibar(value) {
    const share = Number.isFinite(value) ? clamp(value, 0, 100) : 0;
    return el('span', { class: 'cov-minibar' }, el('span', { style: `width:${share.toFixed(1)}%` }));
  }

  function pctCell(value, limit) {
    if (!stated(limit)) return el('td', { class: 'muted', title: 'no limit stated', text: '—' });
    return el('td', null, el('span', { class: 'cov-cell' }, [pct(value), minibar(value)]));
  }

  function drawSummaryTable(fig) {
    const head = el('tr', null, [
      el('th', { class: 'left', text: 'Joint' }),
      el('th', null, ['Position range used', el('span', { class: 'sub', text: 'q span, p0.1–p99.9' })]),
      el('th', null, ['Peak speed', el('span', { class: 'sub', text: 'qd, of its limit' })]),
      el('th', null, ['Peak acceleration', el('span', { class: 'sub', text: 'qdd, of its limit' })]),
      el('th', null, ['Peak jerk', el('span', { class: 'sub', text: 'qddd, of its limit' })]),
      el('th', null, ['Position × speed cells', el('span', { class: 'sub', text: 'q_qd visited' })]),
      el('th', null, ['Speed × acceleration cells', el('span', { class: 'sub', text: 'qd_qdd visited' })]),
      el('th', null, ['Samples beyond a limit', el('span', { class: 'sub', text: 'any signal' })]),
    ]);
    const body = el('tbody');
    let anyBeyond = false;
    joints().forEach((joint, index) => {
      const hist = payload.hist[joint.name];
      const planes = payload.planes[joint.name];
      let beyond = 0;
      for (const signal of payload.signals) if (stated(limitOf(joint.name, signal))) beyond += hist[signal].outside || 0;
      if (beyond > 0) anyBeyond = true;
      const row = el('tr', { class: index === state.joint ? 'selected' : null, title: 'open this joint' }, [
        el('td', { class: 'left', text: joint.name }),
        pctCell(hist.q.span_pct, limitOf(joint.name, 'q')),
        pctCell(hist.qd.peak_pct, limitOf(joint.name, 'qd')),
        pctCell(hist.qdd.peak_pct, limitOf(joint.name, 'qdd')),
        pctCell(hist.qddd.peak_pct, limitOf(joint.name, 'qddd')),
        el('td', null, el('span', { class: 'cov-cell' }, [pct(planes.q_qd.visited_pct), minibar(planes.q_qd.visited_pct)])),
        el('td', null, el('span', { class: 'cov-cell' }, [pct(planes.qd_qdd.visited_pct), minibar(planes.qd_qdd.visited_pct)])),
        el('td', { class: beyond > 0 ? 'problem' : 'muted', text: beyond > 0 ? count(beyond) : '0' }),
      ]);
      row.addEventListener('click', () => { selectJoint(index); show('joint'); });
      body.append(row);
    });
    fig.body.append(el('div', { class: 'cov-tablewrap' }, el('table', { class: 'cov-table' }, [el('thead', null, head), body])));
    setLegend(fig, [
      { kind: 'fill', colour: '#7f9cc0', label: 'bar = the share, 0 – 100 %' },
      { kind: 'text', label: '— = no limit stated for that signal' },
      anyBeyond ? { kind: 'text', label: 'red count = samples past a stated limit', problem: true } : null,
      { kind: 'text', label: 'highlighted row = the joint picked in the Joint control' },
    ]);
  }

  // ── limits ────────────────────────────────────────────────────────────────────────────────────────────────────

  function buildLimits(section) {
    const fig = figure('limit-bars', 'Where does each joint\'s data sit against its limits?',
      'One card per joint, one row per signal: position (q), speed (qd), acceleration (qdd) and jerk (qddd), in degrees (or mm). The bars are the samples; the x axis runs 8 % past each limit so overshoot shows. Between the red lines is what the limit allows; grey is beyond it (the robot should never be there). Black ticks mark where the data really went (its 0.1st and 99.9th percentile). On the right: the share of the range used (q) or the peak reached as a share of the limit (qd, qdd, qddd), and in red how many samples went past the limit. When the dataset is split (e.g. by split), the bars are stacked in one colour per group, named in the legend.',
      'TFDV / Facets Overview (one row per feature, the schema range = the limit); the Nov 19 gallery "limit bars".');
    register('limits', fig, (width) => drawLimitBars(fig, width));
    section.append(fig.node);
  }

  function drawLimitBars(fig, width) {
    const columns = Math.max(1, Math.floor((width + 14) / (400 + 14)));
    const cardW = Math.floor((width - 14 * (columns - 1)) / columns);
    const grid = el('div', { class: 'cov-cards', style: `grid-template-columns: repeat(${columns}, minmax(0, 1fr))` });
    const groups = groupNames();
    const stacked = payload.source.group_by && groups.length > 0;
    let anyPlanner = false;
    let anyUnstated = false;
    let anyBeyond = false;
    let anyCap = false;
    for (const joint of joints()) {
      const card = el('div', { class: 'cov-card' }, el('div', { class: 'cov-cardhead' }, [
        el('b', { text: joint.name }), el('span', { class: 'unit', text: `${joint.kind} · ${joint.display.unit === 'deg' ? 'degrees' : joint.display.unit}` })]));
      const innerW = cardW - 18;
      const labelW = 64;
      const noteW = 86;
      const rowH = 62;
      const { canvas, g } = canvasOf(innerW, rowH * payload.signals.length + 4);
      payload.signals.forEach((signal, r) => {
        const h = payload.hist[joint.name][signal];
        const limit = limitOf(joint.name, signal);
        const planner = payload.planner_limits && payload.planner_limits[joint.name] ? payload.planner_limits[joint.name][signal] : null;
        const scale = joint.display.scale;
        const e = edges(h.edges);
        const box = { x: labelW, y: r * rowH + 6, w: innerW - labelW - noteW, h: 34 };
        const x = { lo: e.lo * scale, hi: e.hi * scale };
        const { sx } = mapper(box, x, { lo: 0, hi: 1 });
        const base = box.y + box.h;
        if (stated(limit)) {
          g.fillStyle = rgbCss(Color.OUTSIDE);
          g.fillRect(box.x, box.y, sx(limit.low * scale) - box.x, box.h);
          g.fillRect(sx(limit.high * scale), box.y, box.x + box.w - sx(limit.high * scale), box.h);
        } else {
          anyUnstated = true;
        }
        const bars = heights(h.counts, state.scale);
        const de = { n: e.n, at: (i) => e.at(i) * scale };
        const stack = stacked && h.groups ? groups.map((name) => ({ colour: groupColour(name), counts: h.groups[name] || [], total: h.counts })) : null;
        drawBars(g, sx, base, box.h - 2, de, bars.t, ACCENT, stack);
        drawCaps(g, sx, base, box.h - 2, de, bars);
        if (anyClipped(bars)) anyCap = true;
        hline(g, base, box.x, box.x + box.w, AXIS);
        if (stated(limit)) {
          vline(g, sx(limit.low * scale), box.y - 2, base, Color.LIMIT, 1.4);
          vline(g, sx(limit.high * scale), box.y - 2, base, Color.LIMIT, 1.4);
        }
        if (planner && stated(planner)) {
          anyPlanner = true;
          vline(g, sx(planner.low * scale), box.y - 2, base, Color.LIMIT, 1.2, [4, 3]);
          vline(g, sx(planner.high * scale), box.y - 2, base, Color.LIMIT, 1.2, [4, 3]);
        }
        for (const value of [h.p001, h.p999]) if (Number.isFinite(value)) vline(g, sx(value * scale), box.y + 2, base + 3, INK, 1.2);
        drawAxes(g, box, { lo: x.lo, hi: x.hi }, { show: false });
        g.font = FONT_BOLD;
        g.fillStyle = INK;
        g.textAlign = 'left';
        g.textBaseline = 'alphabetic';
        g.fillText(signal, 0, box.y + 14);
        g.font = FONT;
        g.fillStyle = MUTED;
        g.fillText(WORD[signal], 0, box.y + 27);
        g.fillText(unitOf(joint, signal), 0, box.y + 40);
        const noteX = box.x + box.w + 8;
        if (!stated(limit)) {
          g.fillText('no limit stated', noteX, box.y + 14);
        } else {
          g.fillStyle = SOFT;
          g.fillText(signal === 'q' ? `${pct(h.span_pct)} of range` : `peak ${pct(h.peak_pct)}`, noteX, box.y + 14);
          if (h.outside > 0) {
            anyBeyond = true;
            g.fillStyle = Color.LIMIT;
            g.fillText(`${count(h.outside)} beyond`, noteX, box.y + 28);
          }
        }
        canvas._rows = canvas._rows || [];
        canvas._rows.push({ box, signal, h, limit, sx, scale, e });
      });
      hover(canvas, (px, py) => {
        const row = canvas._rows.find((item) => py >= item.box.y - 4 && py <= item.box.y + item.box.h + 16);
        if (!row || px < row.box.x || px > row.box.x + row.box.w) return null;
        const value = row.e.lo * row.scale + ((px - row.box.x) / row.box.w) * (row.e.hi - row.e.lo) * row.scale;
        const i = clamp(Math.floor(((value / row.scale) - row.e.lo) / row.e.step), 0, row.e.n - 1);
        let text = `<b>${escapeHtml(joint.name)} · ${row.signal}</b> ${withUnit(joint, row.signal, row.e.at(i))} … ${withUnit(joint, row.signal, row.e.at(i + 1))}<br>${count(row.h.counts[i])} samples`;
        if (row.h.groups) for (const name of groups) text += `<br>${escapeHtml(name)}: ${count((row.h.groups[name] || [])[i] || 0)}`;
        return text;
      });
      card.append(canvas);
      grid.append(card);
    }
    fig.body.append(grid);
    const items = [];
    if (stacked) {
      for (const name of groups) items.push({ kind: 'fill', colour: groupColour(name), label: `${payload.source.group_by} = ${name}` });
      items.push({ kind: 'text', label: `(bars stacked by ${payload.source.group_by}; height: ${scaleTitle(state.scale)})` });
    } else {
      items.push({ kind: 'fill', colour: ACCENT, label: `samples (bar height: ${scaleTitle(state.scale)})` });
    }
    items.push({ kind: 'line', colour: Color.LIMIT, label: 'the limit' });
    if (anyPlanner) items.push({ kind: 'dash', colour: Color.LIMIT, label: 'the planner\'s limit' });
    items.push({ kind: 'outside', label: 'beyond the limit' });
    items.push({ kind: 'tick', colour: INK, label: 'p0.1 / p99.9 of the data' });
    if (anyCap) items.push(CAP_LEGEND);
    if (anyUnstated) items.push({ kind: 'text', label: '"no limit stated": the axis spans the data instead' });
    if (anyBeyond) items.push({ kind: 'text', label: 'red count = samples past the limit', problem: true });
    setLegend(fig, items);
  }

  // ── one joint ─────────────────────────────────────────────────────────────────────────────────────────────────

  function buildJoint(section) {
    section.append(el('p', { class: 'cov-intro', text: 'One joint at a time (pick it in the Joint control above): which combinations of position, speed and acceleration it visits, inside its limit box.' }));
    const qqd = figure('heat-q-qd', 'Which positions and speeds does the joint visit?',
      'Each cell is one band of position (x) and one band of speed (y); the plot spans exactly the joint\'s limits, so the red frame is the limit box and every cell is a state the joint is allowed to be in. Colour = samples in the cell (or, switched, how many distinct trajectories passed through it: a long dwell then counts once). White = never visited. The colour bar on the right carries the real numbers.',
      'Phase-portrait occupancy grids; the Nov 19 gallery "q × qd, linear"; Strava-style trajectories per cell.');
    const qdqdd = figure('heat-qd-qdd', 'Which speeds and accelerations does the joint combine?',
      'Each cell is one band of speed (x) and one band of acceleration (y), spanning exactly the limits (red frame). Hard acceleration at high speed is where motors run out of torque; white there means the data never asked for it.',
      'Actuator torque-speed envelopes; the Nov 19 gallery "qd × qdd".');
    register('joint', qqd, (width) => drawPlane(qqd, 'q_qd', width));
    register('joint', qdqdd, (width) => drawPlane(qdqdd, 'qd_qdd', width));
    section.append(split(qqd, qdqdd, 'joint-planes'));
    const slabs = figure('slabs', 'At each acceleration, which positions and speeds?',
      'The position × speed grid split into five bands of acceleration, side by side, from hardest braking (left) to hardest accelerating (right); one colour scale shared by all five, so they compare. The end bands also hold the few samples past the acceleration limit, so the five add back up to the position × speed grid.',
      'Small multiples / conditional slices (Tufte); the Nov 19 gallery "qdd slices" ("cool idea to show many slices at a single time").');
    register('joint', slabs, (width) => drawSlabs(slabs, width));
    section.append(slabs.node);
    const spaghetti = figure('spaghetti', 'What paths do the trajectories trace in position × speed?',
      'Every trajectory\'s path through position (x) and speed (y), drawn faint so overlaps darken. Hover a line to see its name, click it (or a row in the Trajectories tab) to highlight it here and in the 3-D views. Grey is beyond the limit, the red frame is the limit box.',
      'Phase portraits; the Nov 19 gallery "phase spaghetti".');
    const envelope = figure('envelope', 'Does the joint accelerate as hard as allowed at every position?',
      'For each band of position (x), the blue bar spans the lowest to the highest acceleration the data reached there; the pale band is what the acceleration limit allows. Here the limit is a box (one number, ± the max acceleration), so the allowed band is flat: the same at every position. With a torque limit, gravity would eat part of the budget and the allowed band would wave with position (that was the "wave" in the Nov 19 figure). Fill = how much of the allowed band the data used.',
      'TOPP-RA admissible acceleration bounds; the Nov 19 gallery "acceleration envelope".');
    register('joint', spaghetti, (width) => drawSpaghetti(spaghetti, width));
    register('joint', envelope, (width) => drawEnvelope(envelope, width));
    section.append(split(spaghetti, envelope, 'joint-paths', 0.55));
  }

  function planeAxis(joint, signal, e) {
    const scale = joint.display.scale;
    return { lo: e.lo * scale, hi: e.hi * scale, label: `${signal} · ${WORD[signal]} (${unitOf(joint, signal)})` };
  }

  function heatSize(width, aspect, maxH) {
    const plotW = Math.max(160, width - 92 - 8);
    const height = clamp(Math.round((plotW - 64) * aspect) + 50, 180, maxH);
    return { plotW, height };
  }

  function drawPlane(fig, key, width) {
    const joint = selectedJoint();
    const plane = payload.planes[joint.name][key];
    const mode = load('count.' + fig.id, 'samples');
    fig.titleText.textContent = key === 'q_qd' ? `Which positions and speeds does ${joint.name} visit?`
      : `Which speeds and accelerations does ${joint.name} combine?`;
    fig.tools.replaceChildren(segmented('colour =', [['samples', 'samples'], ['paths', 'trajectories']], mode,
      (value) => { save('count.' + fig.id, value); drawFigure(bodies.get(fig.body)); }));
    const [nx, ny] = plane.shape;
    const values = mode === 'paths' ? plane.paths : plane.samples;
    const scaled = Color.scale(values, state.scale, { enough: state.enough });
    const colour = lut(rampNow());
    const ex = edges(plane.x_edges);
    const ey = edges(plane.y_edges);
    const { plotW, height } = heatSize(width, 0.62, 420);
    const margin = { l: 58, r: 8, t: 6, b: 38 };
    const { canvas, g } = canvasOf(plotW, height, { 'data-cov-heat': '' });
    const box = { x: margin.l, y: margin.t, w: plotW - margin.l - margin.r, h: height - margin.t - margin.b };
    drawImage(g, heatImage(nx, ny, scaled.t, colour, null), box);
    const x = planeAxis(joint, plane.x, ex);
    const y = planeAxis(joint, plane.y, ey);
    const { sx, sy } = mapper(box, x, y);
    if (y.lo < 0 && y.hi > 0) hline(g, sy(0), box.x, box.x + box.w, 'rgba(34,33,31,0.25)', 1, [2, 3]);
    if (x.lo < 0 && x.hi > 0 && plane.x !== 'q') vline(g, sx(0), box.y, box.y + box.h, 'rgba(34,33,31,0.25)', 1, [2, 3]);
    strokeBox(g, box, Color.LIMIT, 1.5);
    drawAxes(g, box, x, Object.assign({ labelOffset: 46 }, y));
    hover(canvas, (px, py) => {
      if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
      const i = clamp(Math.floor(((px - box.x) / box.w) * nx), 0, nx - 1);
      const j = clamp(Math.floor(((box.y + box.h - py) / box.h) * ny), 0, ny - 1);
      const k = i * ny + j;
      let text = `${plane.x} ${withUnit(joint, plane.x, ex.at(i))} … ${withUnit(joint, plane.x, ex.at(i + 1))}<br>${plane.y} ${withUnit(joint, plane.y, ey.at(j))} … ${withUnit(joint, plane.y, ey.at(j + 1))}<br><b>${count(plane.samples[k])}</b> sample${plane.samples[k] === 1 ? '' : 's'} · <b>${count(plane.paths[k])}</b> trajector${plane.paths[k] === 1 ? 'y' : 'ies'}`;
      if (plane.max_other && plane.max_other[k] !== null && plane.max_other[k] !== undefined) text += `<br>max |qdd| here ${withUnit(joint, 'qdd', plane.max_other[k])}`;
      return text;
    });
    const row = el('div', { class: 'cov-heatrow' }, [canvas, colorbar(scaled, mode === 'paths' ? 'trajectories per cell' : 'samples per cell', box.h)]);
    fig.body.append(row);
    const lead = [`<b>${pct(plane.visited_pct)}</b> of ${count(nx * ny)} cells visited`, `${pct(plane.sufficient_pct)} with ≥ ${state.enough} samples`,
      `evenness ${pct(plane.evenness_pct)}`];
    if (plane.outside > 0) lead.push(`<span class="cov-problem">${count(plane.outside)} samples beyond the limit box (not drawn)</span>`);
    fig.lead.innerHTML = lead.join(' · ');
    setLegend(fig, [
      { kind: 'ramp', label: `colour = ${mode === 'paths' ? 'distinct trajectories through the cell' : 'samples in the cell'}`, note: `(${scaleTitle(state.scale)})` },
      { kind: 'empty', label: 'white = never visited' },
      { kind: 'frame', colour: Color.LIMIT, label: 'red frame = the limit box (the plot spans exactly the limits)' },
      { kind: 'dash', colour: 'rgba(34,33,31,0.45)', label: 'zero line' },
    ]);
  }

  function drawSlabs(fig, width) {
    const joint = selectedJoint();
    const slab = payload.slabs[joint.name];
    const plane = payload.planes[joint.name].q_qd;
    const [S, nx, ny] = slab.shape;
    fig.titleText.textContent = `At each acceleration, which positions and speeds does ${joint.name} visit?`;
    // WHY one scale over all five (concatenated): the panels must compare, a cell twice as busy is twice as bright
    const scaled = Color.scale(slab.samples, state.scale, { enough: state.enough });
    const colour = lut(rampNow());
    const ex = edges(plane.x_edges);
    const ey = edges(plane.y_edges);
    const eb = edges(slab.by_edges);
    const x = planeAxis(joint, 'q', ex);
    const y = planeAxis(joint, 'qd', ey);
    const available = width - 92 - 8;
    const firstLeft = 52;
    const otherLeft = 10;
    const gap = 8;
    const plotTotal = available - firstLeft - (S - 1) * (otherLeft + gap) - S * 6;
    const plotW = Math.max(60, Math.floor(plotTotal / S));
    const plotH = clamp(Math.round(plotW * 0.75), 90, 240);
    const panels = el('div', { class: 'cov-panels' });
    for (let s = 0; s < S; s++) {
      const left = s === 0 ? firstLeft : otherLeft;
      const w = left + plotW + 6;
      const h = plotH + 36;
      const { canvas, g } = canvasOf(w, h, { 'data-cov-heat': '' });
      const box = { x: left, y: 4, w: plotW, h: plotH };
      const offset = s * nx * ny;
      const t = scaled.t.subarray(offset, offset + nx * ny);
      drawImage(g, heatImage(nx, ny, t, colour, null), box);
      strokeBox(g, box, Color.LIMIT, 1.2);
      drawAxes(g, box, { lo: x.lo, hi: x.hi, label: s === 2 ? x.label : '' },
        Object.assign({}, y, { labels: s === 0, label: s === 0 ? `qd (${unitOf(joint, 'qd')})` : '', labelOffset: 40 }));
      hover(canvas, (px, py) => {
        if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
        const i = clamp(Math.floor(((px - box.x) / box.w) * nx), 0, nx - 1);
        const j = clamp(Math.floor(((box.y + box.h - py) / box.h) * ny), 0, ny - 1);
        return `qdd ${withUnit(joint, 'qdd', eb.at(s))} … ${withUnit(joint, 'qdd', eb.at(s + 1))}<br>q ${withUnit(joint, 'q', ex.at(i))} … ${withUnit(joint, 'q', ex.at(i + 1))}<br>qd ${withUnit(joint, 'qd', ey.at(j))} … ${withUnit(joint, 'qd', ey.at(j + 1))}<br><b>${count(slab.samples[offset + i * ny + j])}</b> samples`;
      });
      const title = el('div', { class: 'cov-panel-title', style: `padding-left:${left}px`,
        html: `<b>qdd ${escapeHtml(withUnit(joint, 'qdd', eb.at(s)))} … ${escapeHtml(withUnit(joint, 'qdd', eb.at(s + 1)))}</b> · ${pct(slab.visited_pct[s])}` });
      panels.append(el('div', { class: 'cov-panel' }, [title, canvas]));
    }
    fig.body.append(el('div', { class: 'cov-heatrow' }, [panels, colorbar(scaled, 'samples per cell (all five)', plotH)]));
    fig.lead.textContent = `Cells visited per band, hardest braking → hardest accelerating: ${slab.visited_pct.map(pct).join(', ')}`;
    setLegend(fig, [
      { kind: 'ramp', label: 'colour = samples in the cell, one scale shared by all five panels', note: `(${scaleTitle(state.scale)})` },
      { kind: 'empty', label: 'white = never visited' },
      { kind: 'frame', colour: Color.LIMIT, label: 'red frame = the position × speed limit box' },
      { kind: 'text', label: 'panel title = its acceleration band · share of its cells visited' },
    ]);
  }

  function drawSpaghetti(fig, width) {
    const joint = selectedJoint();
    const paths = payload.paths[joint.name] || [];
    const plane = payload.planes[joint.name].q_qd;
    fig.titleText.textContent = `What paths do the trajectories trace in ${joint.name}'s position × speed?`;
    const scale = joint.display.scale;
    const ex = edges(plane.x_edges);
    const ey = edges(plane.y_edges);
    const mx = 0.06 * (ex.hi - ex.lo);
    const my = 0.08 * (ey.hi - ey.lo);
    const x = { lo: (ex.lo - mx) * scale, hi: (ex.hi + mx) * scale, label: `q · position (${unitOf(joint, 'q')})` };
    const y = { lo: (ey.lo - my) * scale, hi: (ey.hi + my) * scale, label: `qd · speed (${unitOf(joint, 'qd')})`, labelOffset: 46 };
    const height = clamp(Math.round(width * 0.62), 220, 420);
    const margin = { l: 58, r: 10, t: 6, b: 38 };
    const base = canvasOf(width, height);
    const top = canvasOf(width, height);
    top.canvas.style.position = 'absolute';
    top.canvas.style.left = '0';
    top.canvas.style.top = '0';
    const box = { x: margin.l, y: margin.t, w: width - margin.l - margin.r, h: height - margin.t - margin.b };
    const { sx, sy } = mapper(box, x, y);
    const g = base.g;
    g.fillStyle = rgbCss(Color.OUTSIDE);
    g.fillRect(box.x, box.y, box.w, box.h);
    const limitBox = { x: sx(ex.lo * scale), y: sy(ey.hi * scale), w: sx(ex.hi * scale) - sx(ex.lo * scale), h: sy(ey.lo * scale) - sy(ey.hi * scale) };
    g.fillStyle = '#ffffff';
    g.fillRect(limitBox.x, limitBox.y, limitBox.w, limitBox.h);
    const n = paths.length;
    // WHY faint: overlaps darken, so a well-trodden path reads as one dark stroke and a one-off as a ghost
    const alpha = clamp(20 / Math.max(1, n), 0.32, 0.8);
    const screen = paths.map((path) => {
      const q = path[0];
      const qd = path[1];
      const points = new Float32Array(q.length * 2);
      for (let k = 0; k < q.length; k++) {
        points[2 * k] = q[k] === null ? NaN : sx(q[k] * scale);
        points[2 * k + 1] = qd[k] === null ? NaN : sy(qd[k] * scale);
      }
      return points;
    });
    g.save();
    g.beginPath(); g.rect(box.x, box.y, box.w, box.h); g.clip();
    g.lineWidth = 1.2;
    g.lineJoin = 'round';
    screen.forEach((points, index) => {
      const group = trajectoryGroup(index);
      g.strokeStyle = group === null ? INK : groupColour(group);
      g.globalAlpha = alpha;
      strokePath(g, points);
    });
    g.restore();
    strokeBox(g, limitBox, Color.LIMIT, 1.5);
    drawAxes(g, box, x, y);
    const overlay = (hovered) => {
      const o = top.g;
      o.clearRect(0, 0, width, height);
      o.save();
      o.beginPath(); o.rect(box.x, box.y, box.w, box.h); o.clip();
      for (const [index, colour, lineWidth] of [[state.highlight, HIGHLIGHT, 2.2], [hovered, '#2a6bb8', 1.8]]) {
        if (index === null || index === undefined || !screen[index]) continue;
        o.strokeStyle = colour;
        o.lineWidth = lineWidth;
        o.globalAlpha = 1;
        strokePath(o, screen[index]);
      }
      o.restore();
    };
    overlay(null);
    const nearest = (px, py) => {
      let best = null;
      let bestDistance = 100;
      screen.forEach((points, index) => {
        for (let k = 0; k < points.length; k += 2) {
          const dx = points[k] - px;
          const dy = points[k + 1] - py;
          const d = dx * dx + dy * dy;
          if (d < bestDistance) { bestDistance = d; best = index; }
        }
      });
      return best;
    };
    const wrap = el('div', { style: `position:relative;width:${width}px;height:${height}px` }, [base.canvas, top.canvas]);
    hover(top.canvas, (px, py) => {
      const index = nearest(px, py);
      overlay(index);
      if (index === null) return null;
      const item = payload.trajectories[index];
      const group = trajectoryGroup(index);
      return `<b>${escapeHtml(item.name)}</b>${group !== null ? ` · ${escapeHtml(payload.source.group_by)} ${escapeHtml(group)}` : ''}<br>${duration(item.duration_s)} · click to highlight`;
    }, (px, py) => {
      const index = nearest(px, py);
      if (index !== null) setHighlight(index);
    });
    top.canvas.addEventListener('mouseleave', () => overlay(null));
    fig.body.append(wrap);
    fig.lead.textContent = `${count(n)} trajectories, up to ${count(Math.max(0, ...paths.map((p) => p[0].length)))} points each`;
    const items = [];
    const groups = payload.source.group_by ? groupNames() : [];
    if (groups.length) for (const name of groups) items.push({ kind: 'line', colour: groupColour(name), label: `${payload.source.group_by} = ${name}`, alpha: 0.8 });
    else items.push({ kind: 'line', colour: INK, alpha: 0.35, label: `one faint line per trajectory (${count(n)}): darker = more overlap` });
    items.push({ kind: 'line', colour: HIGHLIGHT, label: state.highlight === null ? 'black = the highlighted trajectory (click a line or a table row)' : `black = highlighted: ${payload.trajectories[state.highlight].name}` });
    items.push({ kind: 'line', colour: '#2a6bb8', label: 'blue = under the mouse' });
    items.push({ kind: 'frame', colour: Color.LIMIT, label: 'red frame = the limit box' });
    items.push({ kind: 'outside', label: 'beyond the limit' });
    setLegend(fig, items);
    fig._redrawOverlay = () => overlay(null);
  }

  function strokePath(g, points) {
    g.beginPath();
    let pen = false;
    for (let k = 0; k < points.length; k += 2) {
      const px = points[k];
      const py = points[k + 1];
      if (!Number.isFinite(px) || !Number.isFinite(py)) { pen = false; continue; }
      if (pen) g.lineTo(px, py); else { g.moveTo(px, py); pen = true; }
    }
    g.stroke();
  }

  function drawEnvelope(fig, width) {
    const joint = selectedJoint();
    const name = joint.name;
    const scale = joint.display.scale;
    const limit = limitOf(name, 'qdd');
    const planner = payload.planner_limits && payload.planner_limits[name] ? payload.planner_limits[name].qdd : null;
    fig.titleText.textContent = `Does ${name} accelerate as hard as allowed at every position?`;
    const plane = payload.planes[name].q_qdd;
    const qPlane = payload.planes[name].q_qd;
    const ex = edges((plane || qPlane).x_edges);
    const columns = [];
    if (plane) {
      const [nx, ny] = plane.shape;
      const ey = edges(plane.y_edges);
      for (let i = 0; i < nx; i++) {
        let lowest = -1;
        let highest = -1;
        for (let j = 0; j < ny; j++) if (plane.samples[i * ny + j] > 0) { if (lowest < 0) lowest = j; highest = j; }
        columns.push(lowest < 0 ? null : { low: ey.at(lowest), high: ey.at(highest + 1) });
      }
    } else {
      // WHY the fallback: an older payload without q_qdd still has max |qdd| per (q, qd) cell
      const [nx, ny] = qPlane.shape;
      for (let i = 0; i < nx; i++) {
        let top = null;
        for (let j = 0; j < ny; j++) { const v = qPlane.max_other[i * ny + j]; if (v !== null && (top === null || v > top)) top = v; }
        columns.push(top === null ? null : { low: -top, high: top });
      }
    }
    const span = limit.high - limit.low;
    const margin = 0.12 * span;
    const x = { lo: ex.lo * scale, hi: ex.hi * scale, label: `q · position (${unitOf(joint, 'q')})` };
    const y = { lo: (limit.low - margin) * scale, hi: (limit.high + margin) * scale, label: `qdd · acceleration (${unitOf(joint, 'qdd')})`, labelOffset: 48 };
    const height = clamp(Math.round(width * 0.62), 220, 420);
    const { canvas, g } = canvasOf(width, height);
    const box = { x: 60, y: 6, w: width - 60 - 10, h: height - 6 - 38 };
    const { sx, sy } = mapper(box, x, y);
    g.fillStyle = stated(limit) ? ALLOWED : '#f1f1ee';
    g.fillRect(box.x, sy(limit.high * scale), box.w, sy(limit.low * scale) - sy(limit.high * scale));
    let filled = 0;
    let visited = 0;
    g.fillStyle = ACCENT;
    g.globalAlpha = 0.8;
    columns.forEach((column, i) => {
      if (!column) return;
      visited++;
      filled += clamp((column.high - column.low) / span, 0, 1);
      const x0 = sx(ex.at(i) * scale);
      const x1 = sx(ex.at(i + 1) * scale);
      g.fillRect(x0, sy(column.high * scale), Math.max(1, x1 - x0 - 0.5), sy(column.low * scale) - sy(column.high * scale));
    });
    g.globalAlpha = 1;
    if (stated(limit)) {
      hline(g, sy(limit.high * scale), box.x, box.x + box.w, Color.LIMIT, 1.4);
      hline(g, sy(limit.low * scale), box.x, box.x + box.w, Color.LIMIT, 1.4);
    } else {
      hline(g, sy(limit.high * scale), box.x, box.x + box.w, MUTED, 1, [3, 3]);
      hline(g, sy(limit.low * scale), box.x, box.x + box.w, MUTED, 1, [3, 3]);
    }
    if (planner && stated(planner)) {
      hline(g, sy(planner.high * scale), box.x, box.x + box.w, Color.LIMIT, 1.2, [4, 3]);
      hline(g, sy(planner.low * scale), box.x, box.x + box.w, Color.LIMIT, 1.2, [4, 3]);
    }
    hline(g, sy(0), box.x, box.x + box.w, 'rgba(34,33,31,0.25)', 1, [2, 3]);
    strokeBox(g, box, AXIS, 1);
    drawAxes(g, box, x, y);
    hover(canvas, (px, py) => {
      if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
      const i = clamp(Math.floor(((px - box.x) / box.w) * ex.n), 0, ex.n - 1);
      const column = columns[i];
      const where = `q ${withUnit(joint, 'q', ex.at(i))} … ${withUnit(joint, 'q', ex.at(i + 1))}`;
      if (!column) return `${where}<br>never visited`;
      return `${where}<br>reached qdd ${withUnit(joint, 'qdd', column.low)} … ${withUnit(joint, 'qdd', column.high)}<br>${pct((100 * (column.high - column.low)) / span)} of the allowed band`;
    });
    fig.body.append(canvas);
    const fill = visited ? (100 * filled) / visited : 0;
    fig.lead.innerHTML = `Mean fill <b>${pct(fill)}</b>: in the average visited position band, the reached accelerations cover ${pct(fill)} of what the limit allows · ${count(visited)} of ${count(ex.n)} position bands visited`;
    const bound = `${withUnit(joint, 'qdd', limit.low)} … ${withUnit(joint, 'qdd', limit.high)}`;
    setLegend(fig, [
      stated(limit)
        ? { kind: 'fill', colour: ALLOWED, label: `allowed: qdd within ${bound}`, note: '— a box limit, so the band is flat, the same at every position (a torque limit minus gravity would make it wave with q)' }
        : { kind: 'fill', colour: '#f1f1ee', label: `no acceleration limit stated: band = the data's p0.1–p99.9 widened ×1.15 (${bound})` },
      { kind: 'fill', colour: ACCENT, label: plane ? `reached: lowest to highest qdd seen in each ${fmt(ex.step * scale)}${unitOf(joint, 'q')} position band` : 'reached: ± the largest |qdd| seen in each position band' },
      stated(limit) ? { kind: 'line', colour: Color.LIMIT, label: 'the acceleration limit' } : null,
      planner && stated(planner) ? { kind: 'dash', colour: Color.LIMIT, label: 'the planner\'s acceleration limit' } : null,
      { kind: 'dash', colour: 'rgba(34,33,31,0.45)', label: 'zero' },
    ]);
  }

  // ── all joints ────────────────────────────────────────────────────────────────────────────────────────────────

  function buildJoints(section) {
    const parallel = figure('parallel', 'Which joint combinations make up the set?',
      'Parallel coordinates drawn as a picture: every sample is a line through all joint axes, and each axis runs from that joint\'s low limit (bottom red tick) to its high limit (top red tick). Colour = how many sample lines pass through a pixel, so a million lines read as one picture and white means no configuration ever went there. A bright band hugging one height = that joint barely moves; lines fanning across the whole gap = the two joints are combined freely. Switch between position, speed and acceleration above. Equalized often reads best here.',
      'Inselberg\'s parallel coordinates (1985); density parallel coordinates (Wegman 1990, Heinrich & Weiskopf 2009); HiPlot; the Nov 19 gallery ("it almost looks like the arm").');
    register('joints', parallel, (width) => drawParallel(parallel, width));
    const growth = figure('growth', 'Does each new trajectory still add new ground?',
      'Every joint\'s position × speed cells together: the share visited after the first 1, 2, … trajectories, in the dataset\'s order (blue), and the same averaged over 32 random orders (grey, with the band where 80 % of random orders fall). Still climbing at the right: more trajectories of this kind still buy coverage. Flat below 100 %: the rest needs a different kind of trajectory, not more of the same.',
      'The species-accumulation (rarefaction) curve from ecology.');
    register('joints', growth, (width) => drawGrowth(growth, width));
    section.append(parallel.node, growth.node);
  }

  function drawParallel(fig, width) {
    const signal = load('parallel.signal', 'q');
    fig.tools.replaceChildren(segmented('signal', [['q', 'position q'], ['qd', 'speed qd'], ['qdd', 'acceleration qdd']], signal,
      (value) => { save('parallel.signal', value); drawFigure(bodies.get(fig.body)); }));
    const block = payload.parallel[signal];
    const names = block.axes;
    if (names.length < 2) {
      fig.body.append(el('div', { class: 'cov-missing', text: 'Parallel coordinates need at least two joints.' }));
      setLegend(fig, [{ kind: 'text', label: 'one joint only: nothing to connect' }]);
      return;
    }
    const W = block.width;
    const H = block.height;
    const all = [].concat(...block.gaps);
    const scaled = Color.scale(all, state.scale, { enough: state.enough });
    const colour = lut(rampNow());
    const plotW = width - 92 - 8;
    const height = 380;
    // WHY wide side margins: the first and last joint names are centred under their axes and must not be cut
    const margin = { l: 74, r: 74, t: 18, b: 44 };
    const { canvas, g } = canvasOf(plotW, height, { 'data-cov-heat': '' });
    const box = { x: margin.l, y: margin.t, w: plotW - margin.l - margin.r, h: height - margin.t - margin.b };
    const xs = names.map((_, k) => box.x + (k * box.w) / (names.length - 1));
    block.gaps.forEach((gap, k) => {
      const t = scaled.t.subarray(k * W * H, (k + 1) * W * H);
      drawImage(g, heatImage(W, H, t, colour, null), { x: xs[k], y: box.y, w: xs[k + 1] - xs[k], h: box.h });
    });
    const jointsByName = new Map(joints().map((joint) => [joint.name, joint]));
    names.forEach((name, k) => {
      const joint = jointsByName.get(name);
      const limit = limitOf(name, signal);
      vline(g, xs[k], box.y, box.y + box.h, INK, 1);
      const limitColour = stated(limit) ? Color.LIMIT : MUTED;
      hline(g, box.y, xs[k] - 5, xs[k] + 5, limitColour, 2);
      hline(g, box.y + box.h, xs[k] - 5, xs[k] + 5, limitColour, 2);
      g.font = FONT;
      g.fillStyle = limitColour;
      g.textAlign = k === names.length - 1 ? 'right' : 'left';
      g.textBaseline = 'bottom';
      const dx = k === names.length - 1 ? -6 : 6;
      g.fillText(withUnit(joint, signal, limit.high), xs[k] + dx, box.y - 2);
      g.textBaseline = 'top';
      g.fillText(withUnit(joint, signal, limit.low), xs[k] + dx, box.y + box.h + 2);
      g.font = FONT_BOLD;
      g.fillStyle = INK;
      g.textAlign = 'center';
      g.fillText(fitText(g, name, Math.max(60, Math.min(140, box.w / (names.length - 1) - 8))), xs[k], box.y + box.h + 18);
    });
    hover(canvas, (px, py) => {
      if (py < box.y || py > box.y + box.h) return null;
      const k = xs.findIndex((x, index) => index < xs.length - 1 && px >= x && px < xs[index + 1]);
      if (k < 0) return null;
      const column = clamp(Math.floor(((px - xs[k]) / (xs[k + 1] - xs[k])) * W), 0, W - 1);
      const row = clamp(Math.floor(((box.y + box.h - py) / box.h) * H), 0, H - 1);
      return `between <b>${escapeHtml(names[k])}</b> and <b>${escapeHtml(names[k + 1])}</b><br>${count(block.gaps[k][column * H + row])} sample lines through this pixel`;
    });
    fig.body.append(el('div', { class: 'cov-heatrow' }, [canvas, colorbar(scaled, 'sample lines per pixel', box.h)]));
    const subsampled = block.subsampled ? ` (an even ${count(block.subsampled)} of the ${count(payload.source.samples)} samples)` : '';
    fig.lead.textContent = `${WORD[signal]} of all ${names.length} joints, every sample one line${subsampled}`;
    setLegend(fig, [
      { kind: 'ramp', label: 'colour = how many sample lines pass through the pixel', note: `(${scaleTitle(state.scale)})` },
      { kind: 'empty', label: 'white = no configuration went there' },
      { kind: 'line', colour: INK, label: 'a joint axis' },
      { kind: 'line', colour: Color.LIMIT, label: 'red ticks = the joint\'s low limit (bottom) and high limit (top); lines past a limit leave the frame' },
    ]);
  }

  function drawGrowth(fig, width) {
    const growth = payload.growth;
    const inOrder = growth.visited_pct || [];
    const shuffled = growth.shuffled || { mean: [], p10: [], p90: [] };
    const n = inOrder.length;
    const height = 280;
    const { canvas, g } = canvasOf(width, height);
    const box = { x: 58, y: 10, w: width - 58 - 16, h: height - 10 - 40 };
    const top = Math.max(1, ...inOrder, ...shuffled.p90.filter((v) => v !== null));
    const x = { lo: n > 1 ? 1 : 0, hi: Math.max(2, n), label: 'trajectories added' };
    const y = { lo: 0, hi: Math.min(100, Math.ceil((top * 1.12) / 5) * 5), label: 'cells visited (%)', labelOffset: 44 };
    const { sx, sy } = mapper(box, x, y);
    for (const v of ticks(y.lo, y.hi, 5)) hline(g, sy(v), box.x, box.x + box.w, RULE);
    if (shuffled.p10.length === n && n > 0) {
      g.fillStyle = '#e6e5e0';
      g.beginPath();
      for (let k = 0; k < n; k++) g.lineTo(sx(k + 1), sy(shuffled.p90[k]));
      for (let k = n - 1; k >= 0; k--) g.lineTo(sx(k + 1), sy(shuffled.p10[k]));
      g.closePath();
      g.fill();
      g.save();
      g.strokeStyle = MUTED;
      g.setLineDash([4, 3]);
      g.lineWidth = 1.3;
      g.beginPath();
      for (let k = 0; k < n; k++) g.lineTo(sx(k + 1), sy(shuffled.mean[k]));
      g.stroke();
      g.restore();
    }
    g.strokeStyle = ACCENT;
    g.lineWidth = 2;
    g.beginPath();
    for (let k = 0; k < n; k++) g.lineTo(sx(k + 1), sy(inOrder[k]));
    g.stroke();
    if (n === 1) { g.fillStyle = ACCENT; g.beginPath(); g.arc(sx(1), sy(inOrder[0]), 3, 0, 2 * Math.PI); g.fill(); }
    strokeBox(g, box, AXIS, 1);
    drawAxes(g, box, Object.assign({ ticks: ticks(x.lo, x.hi, Math.min(n, Math.max(2, Math.floor(box.w / 60)))).filter((v) => Number.isInteger(v)) }, x), y);
    const guide = canvasOf(width, height);
    guide.canvas.style.position = 'absolute';
    guide.canvas.style.left = '0';
    guide.canvas.style.top = '0';
    hover(guide.canvas, (px) => {
      guide.g.clearRect(0, 0, width, height);
      if (!n || px < box.x - 4 || px > box.x + box.w + 4) return null;
      const k = clamp(Math.round(x.lo + ((px - box.x) / box.w) * (x.hi - x.lo)) - 1, 0, n - 1);
      vline(guide.g, sx(k + 1), box.y, box.y + box.h, INK, 1, [2, 2]);
      const name = payload.trajectories[k] ? payload.trajectories[k].name : '';
      let text = `after <b>${k + 1}</b> trajectories: <b>${pct(inOrder[k])}</b> of the cells<br>added: ${escapeHtml(name)} (+${count((payload.trajectories[k] || {}).new_cells || 0)} new cells)`;
      if (shuffled.mean.length === n) text += `<br>random orders: ${pct(shuffled.mean[k])} (80 % within ${pct(shuffled.p10[k])} – ${pct(shuffled.p90[k])})`;
      return text;
    });
    guide.canvas.addEventListener('mouseleave', () => guide.g.clearRect(0, 0, width, height));
    fig.body.append(el('div', { style: `position:relative;width:${width}px;height:${height}px` }, [canvas, guide.canvas]));
    const last = n ? inOrder[n - 1] : 0;
    const tenth = Math.max(1, Math.round(n * 0.1));
    const earlier = n > tenth ? inOrder[n - 1 - tenth] : 0;
    fig.lead.innerHTML = n ? `After all ${count(n)}: <b>${pct(last)}</b> of every joint's position × speed cells visited; the last ${count(tenth)} trajector${tenth === 1 ? 'y' : 'ies'} added <b>${fmt(last - earlier)}</b> percentage points` : 'no trajectories';
    setLegend(fig, [
      { kind: 'line', colour: ACCENT, label: 'in the dataset\'s order' },
      { kind: 'dash', colour: MUTED, label: 'mean of 32 random orders' },
      { kind: 'fill', colour: '#e6e5e0', label: 'where 80 % of random orders fall (p10 – p90)' },
      { kind: 'text', label: 'y = share of all joints\' position × speed cells visited' },
    ]);
  }

  // ── the tool in Cartesian space ───────────────────────────────────────────────────────────────────────────────

  function buildCartesian(section) {
    const projections = figure('projections', 'Where does the tool go?',
      'The tool\'s path seen from above (x, y), from the front (x, z) and from the side (y, z), in the payload\'s frame (named above the views), in 2 cm pixels, all three at the same scale. Colour = samples in the pixel, or (switched) how many distinct trajectories passed through it: the Strava view, where a route walked by many trajectories glows and a long pause counts once. White = never visited; when the robot\'s reachable space is known, grey marks where it cannot go.',
      'Strava global heatmap (paths per pixel); the Nov 19 gallery "workspace holes" ("showing x y but also x z and y z").');
    register('cartesian', projections, (width) => drawProjections(projections, width));
    section.append(projections.node);
    const speed = figure('tool-speed', 'How fast does the tool move, and where?',
      'Left: from above, the fastest the tool went through each 2 cm pixel (white = never visited). Right: all tool speeds as one histogram, with the 99th percentile marked. Fast pixels in the middle of the workspace and slow ones near the edges is the usual shape; a region only ever crossed slowly has not been tested at speed.',
      'The Nov 19 gallery "max speed per pixel".');
    register('cartesian', speed, (width) => drawToolSpeed(speed, width));
    section.append(speed.node);
    const voxels = figure('voxels-3d', 'Where does the tool go, in 3-D?',
      'The tool\'s path in 5 cm voxels, coloured by count; drag to orbit, scroll to zoom, right-drag to pan, double-click to fit. The threshold slider hides voxels with fewer samples.',
      'Occupancy voxel grids; the Nov 19 gallery 3-D workspace.');
    const paths = figure('spaghetti-3d', 'What paths does the tool trace?',
      'Every trajectory\'s tool path in 3-D, faint so overlaps darken; a trajectory picked in the Trajectories tab is drawn in black. Drag to orbit, double-click to fit.',
      'Phase spaghetti, lifted to 3-D.');
    section.append(split(voxels, paths, 'cartesian-3d'));
    mount3d('cartesian', voxels, 'voxels-3d');
    mount3d('cartesian', paths, 'spaghetti-3d');
  }

  const VIEWS = [['xy', 'from above', 'x', 'y'], ['xz', 'from the front', 'x', 'z'], ['yz', 'from the side', 'y', 'z']];

  function drawProjections(fig, width) {
    const tool = payload.tool;
    const mode = load('count.projections', 'samples');
    fig.tools.replaceChildren(segmented('colour =', [['samples', 'samples'], ['paths', 'trajectories']], mode,
      (value) => { save('count.projections', value); drawFigure(bodies.get(fig.body)); }));
    const pixel = tool.pixel_m;
    const views = VIEWS.map(([key, title, u, v]) => Object.assign({ key, title, u, v }, tool.projections[key]));
    const values = [].concat(...views.map((view) => (mode === 'paths' ? view.paths : view.samples)));
    // WHY one scale over all three views: each sample lands in exactly one pixel of every view, so they compare
    const scaled = Color.scale(values, state.scale, { enough: state.enough });
    const colour = lut(rampNow());
    const left = 52;
    const right = 8;
    const gap = 10;
    const available = width - 92 - 8 - views.length * (left + right) - (views.length - 1) * gap;
    const spanU = views.reduce((sum, view) => sum + view.shape[0] * pixel, 0);
    const spanV = Math.max(...views.map((view) => view.shape[1] * pixel));
    const k = Math.max(20, Math.min(available / spanU, 380 / spanV));
    const panels = el('div', { class: 'cov-panels' });
    let offset = 0;
    let anyReachable = false;
    let barHeight = 120;
    for (const view of views) {
      const [nu, nv] = view.shape;
      const w = Math.max(40, Math.round(nu * pixel * k));
      const h = Math.max(40, Math.round(nv * pixel * k));
      barHeight = Math.max(barHeight, h);
      const { canvas, g } = canvasOf(left + w + right, h + 40, { 'data-cov-heat': '' });
      const box = { x: left, y: 4, w, h };
      const t = scaled.t.subarray(offset, offset + nu * nv);
      offset += nu * nv;
      const reachable = view.reachable;
      if (reachable) anyReachable = true;
      drawImage(g, heatImage(nu, nv, t, colour, reachable ? (cell) => !reachable[cell] : null), box);
      const x = { lo: view.origin[0] * 1000, hi: (view.origin[0] + nu * pixel) * 1000, label: `${view.u} (mm)` };
      const y = { lo: view.origin[1] * 1000, hi: (view.origin[1] + nv * pixel) * 1000, label: `${view.v} (mm)`, labelOffset: 44 };
      const { sx, sy } = mapper(box, x, y);
      if (x.lo <= 0 && x.hi >= 0 && y.lo <= 0 && y.hi >= 0) {
        g.strokeStyle = INK; g.lineWidth = 1.5;
        g.beginPath(); g.moveTo(sx(0) - 6, sy(0)); g.lineTo(sx(0) + 6, sy(0)); g.moveTo(sx(0), sy(0) - 6); g.lineTo(sx(0), sy(0) + 6); g.stroke();
      }
      strokeBox(g, box, AXIS, 1);
      drawAxes(g, box, x, y);
      const counts = view;
      hover(canvas, (px, py) => {
        if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
        const i = clamp(Math.floor(((px - box.x) / box.w) * nu), 0, nu - 1);
        const j = clamp(Math.floor(((box.y + box.h - py) / box.h) * nv), 0, nv - 1);
        const cell = i * nv + j;
        const u0 = (view.origin[0] + i * pixel) * 1000;
        const v0 = (view.origin[1] + j * pixel) * 1000;
        let text = `${view.u} ${fmt(u0)} … ${fmt(u0 + pixel * 1000)} mm, ${view.v} ${fmt(v0)} … ${fmt(v0 + pixel * 1000)} mm<br><b>${count(counts.samples[cell])}</b> sample${counts.samples[cell] === 1 ? '' : 's'} · <b>${count(counts.paths[cell])}</b> trajector${counts.paths[cell] === 1 ? 'y' : 'ies'}`;
        if (counts.max_speed[cell] !== null) text += `<br>fastest ${counts.max_speed[cell].toFixed(2)} m/s`;
        if (reachable) text += reachable[cell] ? '<br>reachable' : '<br>not reachable';
        return text;
      });
      const visited = (mode === 'paths' ? view.paths : view.samples).filter((v) => v > 0).length;
      panels.append(el('div', { class: 'cov-panel' }, [
        el('div', { class: 'cov-panel-title', style: `padding-left:${left}px`, html: `<b>${view.title}</b> (${view.u}, ${view.v}) · ${count(visited)} pixels` }),
        canvas]));
    }
    fig.body.append(el('div', { class: 'cov-heatrow' }, [panels, colorbar(scaled, mode === 'paths' ? 'trajectories per pixel' : 'samples per pixel', Math.min(barHeight, 300))]));
    fig.lead.textContent = `Frame "${tool.frame}", ${fmt(pixel * 100)} cm pixels, all three views at one scale`;
    setLegend(fig, [
      { kind: 'ramp', label: `colour = ${mode === 'paths' ? 'distinct trajectories through the pixel (Strava)' : 'samples in the pixel'}`, note: `(${scaleTitle(state.scale)})` },
      { kind: 'empty', label: anyReachable ? 'white = reachable, never visited' : 'white = never visited' },
      anyReachable ? { kind: 'outside', label: 'grey = the robot cannot reach it' } : null,
      // WHY the frame's own name: the UR5e cell pages use the cell frame (the arm hangs upside down there), so "robot base"
      // would be false on them (2026-11-23).
      { kind: 'cross', colour: INK, label: `the origin of frame "${tool.frame}"` },
    ]);
  }

  function drawToolSpeed(fig, width) {
    const tool = payload.tool;
    const view = tool.projections.xy;
    const pixel = tool.pixel_m;
    const [nu, nv] = view.shape;
    // WHY "enough" falls back to linear here: the cells hold a speed, not a count, so a sample threshold means nothing
    const mode = state.scale === 'enough' ? 'linear' : state.scale;
    const scaled = Color.scale(view.max_speed, mode, {});
    const colour = lut(rampNow());
    const histW = clamp(Math.round(width * 0.36), 220, 460);
    const heatW = width - histW - 92 - 24;
    const left = 52;
    const k = Math.min((heatW - left - 8) / (nu * pixel), 340 / (nv * pixel));
    const w = Math.max(40, Math.round(nu * pixel * k));
    const h = Math.max(40, Math.round(nv * pixel * k));
    const { canvas, g } = canvasOf(left + w + 8, h + 40, { 'data-cov-heat': '' });
    const box = { x: left, y: 4, w, h };
    drawImage(g, heatImage(nu, nv, scaled.t, colour, view.reachable ? (cell) => !view.reachable[cell] : null), box);
    const x = { lo: view.origin[0] * 1000, hi: (view.origin[0] + nu * pixel) * 1000, label: 'x (mm)' };
    const y = { lo: view.origin[1] * 1000, hi: (view.origin[1] + nv * pixel) * 1000, label: 'y (mm)', labelOffset: 44 };
    strokeBox(g, box, AXIS, 1);
    drawAxes(g, box, x, y);
    hover(canvas, (px, py) => {
      if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
      const i = clamp(Math.floor(((px - box.x) / box.w) * nu), 0, nu - 1);
      const j = clamp(Math.floor(((box.y + box.h - py) / box.h) * nv), 0, nv - 1);
      const cell = i * nv + j;
      const u0 = (view.origin[0] + i * pixel) * 1000;
      const v0 = (view.origin[1] + j * pixel) * 1000;
      const speed = view.max_speed[cell];
      return `x ${fmt(u0)} … ${fmt(u0 + pixel * 1000)} mm, y ${fmt(v0)} … ${fmt(v0 + pixel * 1000)} mm<br>${speed === null ? 'never visited' : `fastest <b>${speed.toFixed(2)} m/s</b>`}`;
    });
    const scaledForBar = Object.assign({}, scaled, { ticks: scaled.ticks.map((tick) => ({ t: tick.t, label: tick.label })) });
    // the histogram of every tool speed
    const hist = tool.speed;
    const e = edges(hist.edges);
    const hh = Math.max(180, h + 40);
    const histCanvas = canvasOf(histW, hh);
    const hg = histCanvas.g;
    const hbox = { x: 44, y: 18, w: histW - 44 - 10, h: hh - 18 - 40 };
    const hx = { lo: 0, hi: e.hi, label: 'tool speed (m/s)' };
    const { sx } = mapper(hbox, hx, { lo: 0, hi: 1 });
    const bars = heights(hist.counts, state.scale);
    drawBars(hg, sx, hbox.y + hbox.h, hbox.h, e, bars.t, ACCENT);
    drawCaps(hg, sx, hbox.y + hbox.h, hbox.h, e, bars);
    hline(hg, hbox.y + hbox.h, hbox.x, hbox.x + hbox.w, AXIS);
    const p99 = numberByKey('tool_speed_p99_m_s');
    if (p99 !== null) {
      vline(hg, sx(p99), hbox.y - 4, hbox.y + hbox.h, INK, 1.2, [4, 3]);
      hg.font = FONT; hg.fillStyle = INK; hg.textAlign = sx(p99) > hbox.x + hbox.w * 0.7 ? 'right' : 'left'; hg.textBaseline = 'bottom';
      hg.fillText(`p99 ${p99.toFixed(2)} m/s`, sx(p99) + (hg.textAlign === 'right' ? -4 : 4), hbox.y + 8);
    }
    drawAxes(hg, hbox, hx, { show: false });
    hover(histCanvas.canvas, (px, py) => {
      if (px < hbox.x || px > hbox.x + hbox.w || py < hbox.y - 4 || py > hbox.y + hbox.h) return null;
      const i = clamp(Math.floor(((px - hbox.x) / hbox.w) * e.n), 0, e.n - 1);
      return `${e.at(i).toFixed(3)} … ${e.at(i + 1).toFixed(3)} m/s<br><b>${count(hist.counts[i])}</b> samples`;
    });
    fig.body.append(el('div', { class: 'cov-heatrow' }, [
      el('div', { class: 'cov-panel' }, [el('div', { class: 'cov-panel-title', style: `padding-left:${left}px`, html: '<b>fastest speed through each pixel</b>, from above (x, y)' }), canvas]),
      colorbar(scaledForBar, 'max tool speed (m/s)', Math.min(h, 300)),
      el('div', { class: 'cov-panel', style: 'margin-left:16px' }, [el('div', { class: 'cov-panel-title', html: '<b>every tool speed</b>, all samples' }), histCanvas.canvas]),
    ]));
    fig.lead.textContent = `Fastest: ${fmt(e.hi)} m/s; 99 % of samples at or below ${p99 === null ? '—' : p99.toFixed(2)} m/s`;
    setLegend(fig, [
      { kind: 'ramp', label: 'colour = the fastest the tool went through the pixel (m/s)', note: `(${Color.SCALE_TITLES[mode]}${state.scale === 'enough' ? '; "enough" does not apply to a speed' : ''})` },
      { kind: 'empty', label: 'white = never visited' },
      view.reachable ? { kind: 'outside', label: 'grey = not reachable' } : null,
      { kind: 'fill', colour: ACCENT, label: `samples per speed band (bar height: ${scaleTitle(state.scale)})` },
      anyClipped(bars) ? CAP_LEGEND : null,
      { kind: 'dash', colour: INK, label: '99th percentile of the tool speed' },
    ]);
  }

  // ── tool orientation ──────────────────────────────────────────────────────────────────────────────────────────

  function referenceText(reference) {
    const [x, y, z] = reference;
    if (Math.abs(x) < 1e-6 && Math.abs(y) < 1e-6) return z < 0 ? 'straight down (−z)' : 'straight up (+z)';
    return `(${reference.map((v) => fmt(v)).join(', ')})`;
  }

  function shownTilt(grid, nt, na, full) {
    if (full) return nt;
    let deepest = -1;
    for (let i = 0; i < nt; i++) for (let j = 0; j < na; j++) if (grid.counts[i * na + j] > 0) deepest = Math.max(deepest, i);
    const binDeg = 180 / nt;
    const reached = (deepest + 1) * binDeg;
    // WHY cut the disk at the data (rounded up to 30°, at least 60°): a tool that tilts 20° would be a dot in a 180° disk
    const shown = clamp(Math.ceil(reached / 30) * 30, 60, 180);
    return Math.min(nt, Math.round(shown / binDeg));
  }

  function buildOrientation(section) {
    const disk = figure('tilt-map', 'Which way does the tool tilt, and how far?',
      'Looking down the reference axis: the centre is the tool pointing along the reference (normally straight down), the distance from the centre is the tilt away from it, and the angle around is which way, in the base\'s x-y plane, the tool leans (+x to the right, +y up, as in the top view). Colour = samples. The disk is cut where the data stops (tick "show the full 0–180°" for the whole sphere of tilts).',
      'Polar / stereographic plots of tool axes (pole figures in crystallography); Zach 2026-11-23, "a single angle away from z and then the yaw angle".');
    const grid = figure('tilt-yaw', 'Which tilts and jaw headings occur together?',
      'Tilt (y, from the reference) against yaw (x), the heading of the tool\'s x axis (the jaw) in the base\'s x-y plane, −180° … 180°. A full row means the tool takes every heading at that tilt; a narrow column means it always grasps from one side.',
      'Two-angle coverage grids; Zach 2026-11-23, "coverage in terms of 2 angles".');
    register('orientation', disk, (width) => drawTiltMap(disk, width));
    register('orientation', grid, (width) => drawTiltYaw(grid, width));
    const sphere = figure('sphere-3d', 'Which directions does the tool point, on a sphere?',
      'The tool\'s z axis as a point on a sphere in the payload\'s frame (axes drawn), in equal-area cells coloured by count: you see on which side of the sphere the tool tilts. Drag to orbit, double-click to fit.',
      'Equal-area sphere cells (Archimedes\' equal z bands); Zach 2026-11-23, "I can also see helpful to see it like a sphere".');
    const line = figure('yaw-line', 'Which jaw headings and tilts occur?',
      'Top: yaw, the heading of the tool\'s x axis (the jaw) in the base\'s x-y plane, as a histogram along a straight line from −180° to 180°. Bottom: tilt from the reference, 0° (along it) to 180°.',
      'Zach 2026-11-23: "Yaw as a straight line actually works" (instead of a rose).');
    register('orientation', line, (width) => drawYawLine(line, width));
    // WHY the disk beside the sphere: the same question (which way does it point), flat and round; Zach 2026-11-23
    // wanted both ("a single angle away from z and then the yaw angle ... But I can also see helpful to see it like a sphere")
    section.append(split(disk, sphere, 'orientation-where', 0.5));
    section.append(split(grid, line, 'orientation-yaw', 0.55));
    mount3d('orientation', sphere, 'sphere-3d');
  }

  function drawTiltMap(fig, width) {
    const orientation = payload.tool.orientation;
    const grid = orientation.tilt_azimuth;
    const [nt, na] = grid.shape;
    const full = Boolean(load('tilt.full', false));
    const toggle = el('input', { type: 'checkbox' });
    toggle.checked = full;
    toggle.addEventListener('change', () => { save('tilt.full', toggle.checked); refresh(); });
    fig.tools.replaceChildren(el('label', null, [toggle, 'show the full 0–180°']));
    const rows = shownTilt(grid, nt, na, full);
    const shownDeg = (rows * 180) / nt;
    const scaled = Color.scale(grid.counts, state.scale, { enough: state.enough });
    const colour = lut(rampNow());
    const size = clamp(width - 92 - 12, 200, 440);
    const { canvas, g } = canvasOf(size, size, { 'data-cov-heat': '' });
    const cx = size / 2;
    const cy = size / 2;
    const R = size / 2 - 28;
    g.fillStyle = '#ffffff';
    g.beginPath(); g.arc(cx, cy, R, 0, 2 * Math.PI); g.fill();
    const ea = edges(grid.azimuth_edges);
    for (let i = 0; i < rows; i++) {
      const r0 = (i / rows) * R;
      const r1 = ((i + 1) / rows) * R;
      for (let j = 0; j < na; j++) {
        const t = scaled.t[i * na + j];
        if (!(t >= 0)) continue;
        const a0 = ea.at(j);
        const a1 = ea.at(j + 1);
        g.fillStyle = rgbCss(colour(t));
        g.beginPath();
        g.arc(cx, cy, r1, -a0, -a1, true);
        g.arc(cx, cy, r0, -a1, -a0, false);
        g.closePath();
        g.fill();
        g.strokeStyle = g.fillStyle; g.lineWidth = 0.6; g.stroke();
      }
    }
    g.strokeStyle = 'rgba(34,33,31,0.22)';
    g.lineWidth = 1;
    g.font = FONT;
    g.fillStyle = MUTED;
    g.textAlign = 'left';
    g.textBaseline = 'bottom';
    for (let deg = 30; deg <= shownDeg; deg += 30) {
      const r = (deg / shownDeg) * R;
      g.beginPath(); g.arc(cx, cy, r, 0, 2 * Math.PI); g.stroke();
    }
    for (let k = 0; k < 8; k++) {
      const a = (k * Math.PI) / 4;
      g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + R * Math.cos(a), cy - R * Math.sin(a)); g.stroke();
    }
    // ring labels on a white halo along the empty-looking spoke between +x and +y, so they read over any colour
    g.font = FONT_BOLD;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.lineJoin = 'round';
    // WHY every 60° when rings are close: labels 30° apart would overlap on a small disk
    const labelStep = (30 / shownDeg) * R >= 40 ? 30 : 60;
    for (let deg = labelStep; deg <= shownDeg; deg += labelStep) {
      const r = (deg / shownDeg) * R;
      const lx = cx + r * Math.cos(Math.PI / 8);
      const ly = cy - r * Math.sin(Math.PI / 8);
      g.strokeStyle = 'rgba(255,255,255,0.92)';
      g.lineWidth = 3.5;
      g.strokeText(`${deg}°`, lx, ly);
      g.fillStyle = INK;
      g.fillText(`${deg}°`, lx, ly);
    }
    g.strokeStyle = AXIS;
    g.beginPath(); g.arc(cx, cy, R, 0, 2 * Math.PI); g.stroke();
    g.font = FONT_BOLD;
    g.fillStyle = INK;
    g.textBaseline = 'middle';
    for (const [label, a] of [['+x', 0], ['+y', Math.PI / 2], ['−x', Math.PI], ['−y', -Math.PI / 2]]) {
      g.textAlign = 'center';
      g.fillText(label, cx + (R + 14) * Math.cos(a), cy - (R + 14) * Math.sin(a));
    }
    g.fillStyle = INK;
    g.beginPath(); g.arc(cx, cy, 2.5, 0, 2 * Math.PI); g.fill();
    hover(canvas, (px, py) => {
      const dx = px - cx;
      const dy = cy - py;
      const r = Math.hypot(dx, dy);
      if (r > R) return null;
      const i = clamp(Math.floor((r / R) * rows), 0, rows - 1);
      const angle = Math.atan2(dy, dx);
      const j = clamp(Math.floor((angle - ea.lo) / ea.step), 0, na - 1);
      const tiltLo = (i * 180) / nt;
      const tiltHi = ((i + 1) * 180) / nt;
      const a0 = (ea.at(j) * 180) / Math.PI;
      return `tilt ${fmt(tiltLo)}° … ${fmt(tiltHi)}°, leaning toward ${minus(Math.round(a0))}° … ${minus(Math.round(a0 + (ea.step * 180) / Math.PI))}° (0° = +x, 90° = +y)<br><b>${count(grid.counts[i * na + j])}</b> samples`;
    });
    fig.body.append(el('div', { class: 'cov-heatrow' }, [canvas, colorbar(scaled, 'samples per cell', size * 0.6)]));
    const tiltMax = numberByKey('tool_tilt_max_deg');
    fig.lead.innerHTML = `Largest tilt <b>${tiltMax === null ? '—' : Math.round(tiltMax) + '°'}</b> from the reference, ${referenceText(orientation.reference)}`;
    setLegend(fig, [
      { kind: 'ramp', label: 'colour = samples', note: `(${scaleTitle(state.scale)})` },
      { kind: 'empty', label: 'white = never pointed there' },
      { kind: 'text', label: `centre = tool z along the reference, ${referenceText(orientation.reference)}` },
      { kind: 'thin', colour: 'rgba(34,33,31,0.4)', label: `rings = tilt, every 30°; the rim = ${fmt(shownDeg)}°` },
      { kind: 'text', label: 'angle = which way the tool leans in the base x-y plane' },
      full || rows === nt ? null : { kind: 'text', label: `disk cut at ${fmt(shownDeg)}°: no samples tilt further` },
    ]);
  }

  function drawTiltYaw(fig, width) {
    const orientation = payload.tool.orientation;
    const grid = orientation.tilt_yaw;
    const [nt, ny] = grid.shape;
    const rows = shownTilt(grid, nt, ny, Boolean(load('tilt.full', false)));
    const shownDeg = (rows * 180) / nt;
    const scaled = Color.scale(grid.counts, state.scale, { enough: state.enough });
    const colour = lut(rampNow());
    // the grid is [tilt][yaw]: transpose so yaw runs along x and tilt up the y axis
    const t = new Float32Array(ny * rows);
    for (let i = 0; i < rows; i++) for (let j = 0; j < ny; j++) t[j * rows + i] = scaled.t[i * ny + j];
    const { plotW, height } = heatSize(width, 0.55, 380);
    const { canvas, g } = canvasOf(plotW, height, { 'data-cov-heat': '' });
    const box = { x: 52, y: 6, w: plotW - 52 - 10, h: height - 6 - 38 };
    drawImage(g, heatImage(ny, rows, t, colour, null), box);
    strokeBox(g, box, AXIS, 1);
    const ey = edges(grid.yaw_edges);
    drawAxes(g, box, { lo: -180, hi: 180, ticks: [-180, -90, 0, 90, 180], tickText: (v) => `${minus(v)}°`, label: 'yaw · jaw heading in the base x-y plane (°)' },
      { lo: 0, hi: shownDeg, tickText: (v) => `${v}°`, ticks: ticks(0, shownDeg, 6).filter((v) => v % 10 === 0), label: 'tilt from the reference (°)', labelOffset: 40 });
    hover(canvas, (px, py) => {
      if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
      const j = clamp(Math.floor(((px - box.x) / box.w) * ny), 0, ny - 1);
      const i = clamp(Math.floor(((box.y + box.h - py) / box.h) * rows), 0, rows - 1);
      const y0 = (ey.at(j) * 180) / Math.PI;
      return `yaw ${minus(Math.round(y0))}° … ${minus(Math.round(y0 + (ey.step * 180) / Math.PI))}°, tilt ${fmt((i * 180) / nt)}° … ${fmt(((i + 1) * 180) / nt)}°<br><b>${count(grid.counts[i * ny + j])}</b> samples`;
    });
    fig.body.append(el('div', { class: 'cov-heatrow' }, [canvas, colorbar(scaled, 'samples per cell', box.h)]));
    const visited = grid.counts.filter((v) => v > 0).length;
    fig.lead.textContent = `${count(visited)} of ${count(nt * ny)} tilt × yaw cells visited`;
    setLegend(fig, [
      { kind: 'ramp', label: 'colour = samples', note: `(${scaleTitle(state.scale)})` },
      { kind: 'empty', label: 'white = never visited' },
      rows === nt ? null : { kind: 'text', label: `tilt axis cut at ${fmt(shownDeg)}° (as in the disk): no samples tilt further` },
    ]);
  }

  function drawYawLine(fig, width) {
    const orientation = payload.tool.orientation;
    const parts = [
      { key: 'yaw', hist: orientation.yaw, lo: -180, hi: 180, ticks: [-180, -90, 0, 90, 180], label: 'yaw · jaw heading in the base x-y plane (°)' },
      { key: 'tilt', hist: orientation.tilt, lo: 0, hi: 180, ticks: [0, 30, 60, 90, 120, 150, 180], label: 'tilt from the reference (°)' },
    ];
    const row = el('div');
    let capped = false;
    for (const part of parts) {
      const w = width;
      const h = 176;
      const { canvas, g } = canvasOf(w, h);
      const box = { x: 12, y: 10, w: w - 24, h: h - 10 - 40 };
      const e = edges(part.hist.edges);
      const de = { n: e.n, at: (i) => (e.at(i) * 180) / Math.PI };
      const { sx } = mapper(box, { lo: part.lo, hi: part.hi }, { lo: 0, hi: 1 });
      const bars = heights(part.hist.counts, state.scale);
      drawBars(g, sx, box.y + box.h, box.h, de, bars.t, ACCENT);
      drawCaps(g, sx, box.y + box.h, box.h, de, bars);
      if (anyClipped(bars)) capped = true;
      hline(g, box.y + box.h, box.x, box.x + box.w, AXIS);
      drawAxes(g, box, { lo: part.lo, hi: part.hi, ticks: part.ticks, tickText: (v) => `${minus(v)}°`, label: part.label }, { show: false });
      hover(canvas, (px, py) => {
        if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
        const i = clamp(Math.floor(((px - box.x) / box.w) * e.n), 0, e.n - 1);
        return `${part.key} ${minus(Math.round(de.at(i)))}° … ${minus(Math.round(de.at(i + 1)))}°<br><b>${count(part.hist.counts[i])}</b> samples`;
      });
      const visited = part.hist.counts.filter((v) => v > 0).length;
      row.append(el('div', { class: 'cov-panel', style: 'margin-bottom:6px' }, [
        el('div', { class: 'cov-panel-title', html: `<b>${part.key}</b> · ${count(visited)} of ${count(e.n)} bins visited` }), canvas]));
    }
    fig.body.append(row);
    setLegend(fig, [
      { kind: 'fill', colour: ACCENT, label: `samples per ${fmt((360 / orientation.yaw.edges[2]))}° (yaw) / ${fmt(180 / orientation.tilt.edges[2])}° (tilt) band`, note: `(bar height: ${scaleTitle(state.scale)})` },
      capped ? CAP_LEGEND : null,
      { kind: 'text', label: 'yaw: −180° … 180°, 0° = the jaw along base +x' },
    ]);
  }

  // ── 3-D proposals ─────────────────────────────────────────────────────────────────────────────────────────────

  function buildSpace(section) {
    section.append(el('p', { class: 'cov-intro', text: 'Proposals: the same counts as 3-D shapes (height maps, stacked slabs, skylines, a hedgehog of directions). Pick one in the drop-down at the bottom right; the pick is remembered. Each says what it shows and when it wins over the flat figures.' }));
    if (!global.Coverage3D || typeof global.Coverage3D.mountProposals !== 'function') {
      const fig = figure('space3d-missing', '3-D proposals', 'The 3-D proposals are drawn by coverage3d.js.', null);
      fig.body.append(el('div', { class: 'cov-missing', text: 'The 3-D proposals are not in this build of the page.' }));
      setLegend(fig, [{ kind: 'text', label: 'needs coverage3d.js, which was not found when this page was written' }]);
      section.append(fig.node);
      return;
    }
    try {
      const handle = global.Coverage3D.mountProposals(section, payload, ctx());
      mounts.push({ tab: 'space3d', handle });
      if (handle && handle.highlight && state.highlight !== null) handle.highlight(state.highlight);
    } catch (error) {
      console.error(error);
      section.append(el('p', { class: 'cov-error', text: 'The 3-D proposals failed to start: ' + error.message }));
    }
  }

  // ── trajectories ──────────────────────────────────────────────────────────────────────────────────────────────

  function buildTrajectories(section) {
    const fig = figure('table', 'What does each trajectory add?',
      'One row per trajectory, in the dataset\'s order. "Span" is the share of each joint\'s limit range this trajectory alone covers (its 0.1st to 99.9th percentile; switch position / speed / acceleration above). "New cells" counts the position × speed cells (all joints) this trajectory was the first to visit, in the dataset\'s order: 0 means everything it did was already covered by the ones before it. Click a column title to sort; click a row to highlight that trajectory in the One joint paths and the 3-D views.',
      'Dataset cards / data-coverage reports; the growth curve\'s "new species per sample".');
    register('trajectories', fig, (width) => drawTable(fig, width));
    section.append(fig.node);
  }

  function drawTable(fig) {
    const signal = load('table.signal', 'q');
    fig.tools.replaceChildren(segmented('span of', [['q', 'position'], ['qd', 'speed'], ['qdd', 'acceleration']], signal,
      (value) => { save('table.signal', value); drawFigure(bodies.get(fig.body)); }));
    const rows = payload.trajectories;
    const tagKeys = [];
    for (const row of rows) for (const key of Object.keys(row.tags || {})) if (!tagKeys.includes(key)) tagKeys.push(key);
    const names = joints().map((joint) => joint.name);
    const sort = fig._sort || { key: 'index', descending: false };
    const value = (row, index, key) => {
      if (key === 'index') return index;
      if (key === 'name') return row.name;
      if (key === 'duration') return row.duration_s;
      if (key === 'samples') return row.samples;
      if (key === 'new') return row.new_cells;
      if (key.startsWith('tag:')) return (row.tags || {})[key.slice(4)];
      if (key.startsWith('span:')) { const v = ((row.span_pct || {})[key.slice(5)] || {})[signal]; return v === null || v === undefined ? -1 : v; }
      return 0;
    };
    const order = rows.map((_, index) => index);
    order.sort((a, b) => {
      const va = value(rows[a], a, sort.key);
      const vb = value(rows[b], b, sort.key);
      const c = typeof va === 'string' || typeof vb === 'string' ? String(va).localeCompare(String(vb), undefined, { numeric: true }) : va - vb;
      return sort.descending ? -c : c;
    });
    const header = (key, label, sub, left) => el('th', {
      class: 'sortable' + (left ? ' left' : ''), title: 'sort by this column',
      onclick: () => { fig._sort = { key, descending: sort.key === key ? !sort.descending : key !== 'index' && key !== 'name' }; drawFigure(bodies.get(fig.body)); },
    }, [label + (sort.key === key ? (sort.descending ? ' ↓' : ' ↑') : ''), sub ? el('span', { class: 'sub', text: sub }) : null]);
    const head = el('tr', null, [
      header('index', '#', null, true), header('name', 'Trajectory', null, true),
      ...tagKeys.map((key) => header('tag:' + key, key, 'tag', true)),
      header('duration', 'Duration'), header('samples', 'Samples'),
      ...names.map((name) => header('span:' + name, name, `${signal} span`)),
      header('new', 'New cells', 'first to visit'),
    ]);
    const maxNew = Math.max(1, ...rows.map((row) => row.new_cells || 0));
    const body = el('tbody');
    const rowNodes = [];
    for (const index of order) {
      const row = rows[index];
      const group = trajectoryGroup(index);
      const tr = el('tr', { class: index === state.highlight ? 'selected' : null, 'data-index': String(index) }, [
        el('td', { class: 'left muted', text: String(index + 1) }),
        el('td', { class: 'left' }, [group !== null ? el('span', { class: 'cov-dot', style: `background:${groupColour(group)}` }) : null, row.name]),
        ...tagKeys.map((key) => el('td', { class: 'left', text: (row.tags || {})[key] === undefined ? '' : String(row.tags[key]) })),
        el('td', { text: duration(row.duration_s) }),
        el('td', { text: count(row.samples) }),
        ...names.map((name) => {
          const v = ((row.span_pct || {})[name] || {})[signal];
          if (v === null || v === undefined) return el('td', { class: 'muted', text: '—' });
          return el('td', null, el('span', { class: 'cov-cell' }, [pct(v), minibar(v)]));
        }),
        el('td', null, el('span', { class: 'cov-cell' }, [count(row.new_cells), minibar((100 * (row.new_cells || 0)) / maxNew)])),
      ]);
      tr.addEventListener('click', () => setHighlight(index));
      rowNodes.push(tr);
      body.append(tr);
    }
    fig._rows = rowNodes;
    fig.body.append(el('div', { class: 'cov-tablewrap' }, el('table', { class: 'cov-table' }, [el('thead', null, head), body])));
    fig.lead.textContent = `${count(rows.length)} trajectories · ${count(rows.filter((row) => (row.new_cells || 0) === 0).length)} add no new position × speed cell`;
    const groups = payload.source.group_by ? groupNames() : [];
    setLegend(fig, [
      { kind: 'fill', colour: '#7f9cc0', label: `span bar = share of the joint's ${WORD[signal]} range this trajectory alone covers (p0.1–p99.9), 0 – 100 %` },
      { kind: 'text', label: 'new cells = position × speed cells (all joints) it was first to visit, in the dataset\'s order; bar relative to the most' },
      ...groups.map((name) => ({ kind: 'fill', colour: groupColour(name), label: `${payload.source.group_by} = ${name}` })),
      { kind: 'text', label: 'black outline = the highlighted trajectory (click a row; click again to clear)' },
    ]);
  }

  // ── tabs ──────────────────────────────────────────────────────────────────────────────────────────────────────

  const TAB_LIST = [
    { id: 'overview', label: 'Overview', hint: 'every joint against its limits, in one look', build: buildOverview },
    { id: 'limits', label: 'Limits', hint: 'each joint\'s position, speed, acceleration and jerk against its limits', build: buildLimits },
    { id: 'joint', label: 'One joint', hint: 'position × speed × acceleration of the joint picked in the Joint control', build: buildJoint },
    { id: 'joints', label: 'All joints', hint: 'joint combinations and how coverage grows', build: buildJoints },
    { id: 'cartesian', label: 'Tool position', hint: 'where the tool goes, and how fast', build: buildCartesian, tool: true },
    { id: 'orientation', label: 'Tool orientation', hint: 'which way the tool points and turns', build: buildOrientation, tool: true },
    { id: 'space3d', label: '3-D proposals', hint: 'the same counts as 3-D shapes, behind a drop-down', build: buildSpace },
    { id: 'trajectories', label: 'Trajectories', hint: 'one row per trajectory: what each adds', build: buildTrajectories },
  ];

  function show(id) {
    const tab = tabs.find((item) => item.id === id) || tabs[0];
    for (const item of tabs) {
      item.section.hidden = item !== tab;
      item.button.setAttribute('aria-selected', String(item === tab));
    }
    state.tab = tab.id;
    save('tab', tab.id);
    try { global.history.replaceState(null, '', '#tab=' + tab.id); } catch (error) { /* file:// in some browsers */ }
    if (!tab.built) {
      tab.built = true;
      try { tab.build(tab.section); } catch (error) { console.error(error); tab.section.append(el('p', { class: 'cov-error', text: 'This tab failed to build: ' + error.message })); }
      tab.dirty = true;
    }
    if (tab.dirty) drawTab(tab);
  }

  function hashTab() {
    const match = /(?:^#|&)tab=([\w-]+)/.exec(global.location.hash || '');
    return match ? match[1] : null;
  }

  function restore() {
    const cmap = load('cmap', 'viridis');
    state.cmap = Color.NAMES.includes(cmap) ? cmap : 'viridis';
    state.reverse = load('reverse', false) === true;
    const scale = load('scale', 'linear');
    state.scale = Color.SCALES.includes(scale) ? scale : 'linear';
    const joint = joints().findIndex((item) => item.name === load('joint', null));
    state.joint = joint < 0 ? 0 : joint;
    state.enough = Number(payload.enough) > 0 ? Number(payload.enough) : 10;
  }

  function boot() {
    const node = document.getElementById('cov-payload');
    payload = JSON.parse(node.textContent);
    const root = document.getElementById('cov-root');
    tip = el('div', { class: 'cov-tip', hidden: true });
    document.body.append(tip);
    restore();
    buildSiblings();
    const available = TAB_LIST.filter((tab) => !tab.tool || payload.tool);
    const main = el('main', { class: 'cov-main' });
    for (const item of available) {
      const section = el('section', { class: 'cov-view', 'data-cov-view': item.id, hidden: true });
      main.append(section);
      tabs.push(Object.assign({ section, built: false, dirty: true, button: null }, item));
    }
    const top = el('div', { class: 'cov-top' }, [buildAnswer(), buildNumbers()]);
    root.append(top, buildBar(tabs), main);
    highlightListeners.push(() => {
      for (const entry of figures) {
        if (entry.fig.id === 'table' && entry.fig._rows) {
          for (const tr of entry.fig._rows) tr.classList.toggle('selected', Number(tr.dataset.index) === state.highlight);
        }
        if (entry.fig.id === 'spaghetti' && entry.fig._redrawOverlay && entry.width > 0) {
          // the legend names the highlighted trajectory, so the whole figure redraws (cheap) when it is on screen
          if (entry.tab === state.tab) drawFigure(entry); else tabs.find((tab) => tab.id === entry.tab).dirty = true;
        }
      }
    });
    global.addEventListener('hashchange', () => { const id = hashTab(); if (id && id !== state.tab) show(id); });
    const wanted = hashTab() || load('tab', 'overview');
    show(tabs.some((tab) => tab.id === wanted) ? wanted : 'overview');
  }

  global.TrajCoverage = { boot };
})(typeof window !== 'undefined' ? window : globalThis);
