/* views.js — the views P1's coverage.base names that stock data-ui does not have, registered with registerView
 * (CONTRACT §1) by register.js, so they sit in the workbench's stock dashboards and redraw from the rows the rail leaves.
 * Copied from round 2's V2 (js/views.js: its occupancy figure engine, helpers verbatim) and adapted:
 *
 *   occupancy          each row lists the cells it visits on a named grid (a list property); the view draws, over the
 *                      rows it is handed, how many rows list each cell. New here: `compact` (a dashboard card: no axes,
 *                      a one-line key) and `splitBy: <property>` (one line of panels per value: datasets side by side,
 *                      one colour scale for all of them).
 *   coverage-numbers   the headline numbers over the rows it is handed, labelled, beside analyze's own when nothing is
 *                      filtered (each spec carries `analyze:`).
 *   dataset-mix        how many of each dataset's rows the rail leaves, split by split, in the dataset's colour: the
 *                      subset's make-up and the colour key at once.
 *
 * Settings (colour map, Reverse, scale) are the workbench's (its gear, the .base's settings:), read through settings.js.
 * Tooltips are drawn inside the workbench, never on <body>, so the component draws nothing outside its box.
 */

import { countCells, cellXY, cellIndex, marginal, summarize } from './aggregate.js';
import { settings, follow, SCALE_NOTES } from './settings.js';

const Color = globalThis.CoverageColor;
const INK = '#18181b';
const SOFT = '#52525b';
const MUTED = '#8a8a93';
const AXIS = '#c4c4cc';
const BAR = '#7f9cc0';
const FONT = '10.5px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const FONT_BOLD = '600 11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';


// ── small helpers ────────────────────────────────────────────────────────────────────────────────────────────────

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
const esc = (text) => String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const minus = (text) => String(text).replace(/^-/, '−');
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
function fmt(value, decimals) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (decimals !== undefined) return minus(value.toFixed(decimals));
  const size = Math.abs(value);
  if (size >= 100) return minus(String(Math.round(value)));
  if (size >= 10) return minus(value.toFixed(1).replace(/\.0$/, ''));
  if (size === 0) return '0';
  return minus(value.toPrecision(2).replace(/\.?0+$/, ''));
}
const pct = (value) => (value > 0 && value < 10 ? value.toFixed(1).replace(/\.0$/, '') : String(Math.round(value))) + ' %';
function nounOf(of, n) { return n === 1 ? of : of === 'trajectory' ? 'trajectories' : `${of}s`; }

function niceStep(span, target) {
  const raw = span / Math.max(1, target);
  const power = 10 ** Math.floor(Math.log10(raw));
  const m = raw / power;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * power;
}
function ticks(lo, hi, target) {
  if (!(hi > lo)) return [lo];
  const step = niceStep(hi - lo, target);
  const out = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return out;
}

function canvasOf(width, height) {
  const ratio = globalThis.devicePixelRatio || 1;
  const canvas = el('canvas', { width: Math.round(width * ratio), height: Math.round(height * ratio) });
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const g = canvas.getContext('2d');
  g.scale(ratio, ratio);
  return { canvas, g };
}

function lut(ramp) {
  const table = new Array(256);
  for (let k = 0; k < 256; k += 1) table[k] = ramp(k / 255);
  return (t) => table[Math.round(clamp(t, 0, 1) * 255)];
}

function rampCss(ramp) {
  const stops = [];
  for (let k = 0; k <= 8; k += 1) { const c = ramp(k / 8); stops.push(`rgb(${c[0]},${c[1]},${c[2]})`); }
  return `linear-gradient(90deg, ${stops.join(', ')})`;
}

/** One panel's counts as an image, one pixel per cell (drawn scaled, unsmoothed). */
function heatImage(panel, t, colour, blocked) {
  const [nx, ny] = panel.shape;
  const off = document.createElement('canvas');
  off.width = nx;
  off.height = ny;
  const g = off.getContext('2d');
  const image = g.createImageData(nx, ny);
  const flip = panel.yAxis && panel.yAxis.flip;
  for (let x = 0; x < nx; x += 1) {
    for (let y = 0; y < ny; y += 1) {
      const cell = cellIndex(x, y, panel.shape, panel.order);
      const row = flip ? y : ny - 1 - y;
      const k = (row * nx + x) * 4;
      const rgb = t[cell] >= 0 ? colour(t[cell]) : blocked && blocked[cell] ? Color.OUTSIDE : Color.EMPTY;
      image.data[k] = rgb[0]; image.data[k + 1] = rgb[1]; image.data[k + 2] = rgb[2]; image.data[k + 3] = 255;
    }
  }
  g.putImageData(image, 0, 0);
  return off;
}

function blockedOf(panel) {
  if (!panel.unreachable || !panel.unreachable.length) return null;
  const size = panel.shape[0] * panel.shape[1];
  const flags = new Uint8Array(size);
  for (const [start, length] of panel.unreachable) flags.fill(1, start, Math.min(size, start + length));
  return flags;
}

// WHY inside the workbench's dashboards column: a tooltip on <body> would draw outside a host's slot. .dw-main is the
// element's positioned box (contain: layout), so an absolute tip there follows the pointer and stays in the component.
let tip = null;
function showTip(x, y, html, from) {
  const root = (from && from.closest('.dw-main')) || document.body;
  if (!tip || tip.parentElement !== root) { if (tip) tip.remove(); tip = el('div', { class: 'cov-tip', role: 'tooltip' }); root.append(tip); }
  tip.style.position = root === document.body ? 'fixed' : 'absolute';
  tip.innerHTML = html;
  tip.hidden = false;
  const frame = root === document.body ? { left: 0, top: 0, width: globalThis.innerWidth, height: globalThis.innerHeight } : root.getBoundingClientRect();
  const box = tip.getBoundingClientRect();
  tip.style.left = `${Math.max(4, Math.min(frame.width - box.width - 8, x - frame.left + 14))}px`;
  tip.style.top = `${Math.max(4, Math.min(frame.height - box.height - 8, y - frame.top + 14))}px`;
}
function hideTip() { if (tip) tip.hidden = true; }

// ── one panel: a heat grid with its axes ─────────────────────────────────────────────────────────────────────────

function axisValue(axis, n, i) {
  if (axis.edges) return axis.edges[i];
  return axis.lo + ((axis.hi - axis.lo) * i) / n;
}
const unitText = (axis) => (axis.unit ? (axis.unit.startsWith('°') ? axis.unit : ` ${axis.unit}`) : '');

/** Draw one panel into a canvas: {node, box}. `size` is the heat box {w, h}; `compact` drops axis titles. */
function drawPanel(panel, counts, t, colour, size, opts) {
  const compact = !!opts.compact;
  const margin = compact ? { l: 6, r: 4, t: 4, b: 6 } : { l: 52, r: 8, t: 6, b: 38 };
  const width = margin.l + size.w + margin.r;
  const height = margin.t + size.h + margin.b;
  const { canvas, g } = canvasOf(width, height);
  const box = { x: margin.l, y: margin.t, w: size.w, h: size.h };
  const blocked = blockedOf(panel);
  g.imageSmoothingEnabled = false;
  g.drawImage(heatImage(panel, t, colour, blocked), box.x, box.y, box.w, box.h);
  const [nx, ny] = panel.shape;
  const xa = panel.xAxis;
  const ya = panel.yAxis;
  const sx = (v) => box.x + ((v - xa.lo) / (xa.hi - xa.lo)) * box.w;
  const flip = ya.flip;
  const sy = (v) => (flip ? box.y + ((v - ya.lo) / (ya.hi - ya.lo)) * box.h : box.y + box.h - ((v - ya.lo) / (ya.hi - ya.lo)) * box.h);
  // zero lines (dashed) and the origin cross
  g.setLineDash([2, 3]);
  g.strokeStyle = 'rgba(24,24,27,0.3)';
  g.lineWidth = 1;
  if ((panel.zero === 'y' || panel.zero === 'both') && ya.lo < 0 && ya.hi > 0) { g.beginPath(); g.moveTo(box.x, sy(0) + 0.5); g.lineTo(box.x + box.w, sy(0) + 0.5); g.stroke(); }
  if (panel.zero === 'both' && xa.lo < 0 && xa.hi > 0) { g.beginPath(); g.moveTo(sx(0) + 0.5, box.y); g.lineTo(sx(0) + 0.5, box.y + box.h); g.stroke(); }
  g.setLineDash([]);
  if (panel.origin && xa.lo <= 0 && xa.hi >= 0 && ya.lo <= 0 && ya.hi >= 0) {
    g.strokeStyle = INK; g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(sx(0) - 6, sy(0)); g.lineTo(sx(0) + 6, sy(0)); g.moveTo(sx(0), sy(0) - 6); g.lineTo(sx(0), sy(0) + 6); g.stroke();
  }
  // the frame: red when the plot spans exactly the limits (a limit box), else a quiet axis box
  g.strokeStyle = panel.frame === 'limit' ? Color.LIMIT : AXIS;
  g.lineWidth = panel.frame === 'limit' ? 1.5 : 1;
  g.strokeRect(box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1);
  if (!compact) {
    g.font = FONT;
    g.fillStyle = SOFT;
    g.textAlign = 'center';
    g.textBaseline = 'top';
    for (const v of ticks(xa.lo, xa.hi, Math.max(2, Math.round(box.w / 70)))) {
      const x = sx(v);
      g.fillRect(Math.round(x), box.y + box.h, 1, 4);
      g.fillText(minus(fmt(v)), x, box.y + box.h + 6);
    }
    g.fillStyle = INK;
    g.fillText(`${xa.label}${xa.unit ? ` (${xa.unit})` : ''}`, box.x + box.w / 2, box.y + box.h + 22);
    g.textAlign = 'right';
    g.textBaseline = 'middle';
    g.fillStyle = SOFT;
    const yTicks = ya.edges
      ? ya.edges.map((v, i) => ({ v, at: flip ? box.y + (i / ny) * box.h : box.y + box.h - (i / ny) * box.h })).filter((_, i) => i % 2 === 0 || i === ny)
      : ticks(ya.lo, ya.hi, Math.max(2, Math.round(box.h / 44))).map((v) => ({ v, at: sy(v) }));
    for (const tick of yTicks) {
      g.fillRect(box.x - 4, Math.round(tick.at), 4, 1);
      g.fillText(minus(fmt(tick.v)), box.x - 6, tick.at);
    }
    g.save();
    g.translate(12, box.y + box.h / 2);
    g.rotate(-Math.PI / 2);
    g.textAlign = 'center';
    g.fillStyle = INK;
    g.fillText(`${ya.label}${ya.unit ? ` (${ya.unit})` : ''}`, 0, 0);
    g.restore();
  }
  // hover: what the cell is and how many of the rows pass through it; click: those rows, in data-ui's peek
  const cellAt = (event) => {
    const r = canvas.getBoundingClientRect();
    const px = event.clientX - r.left;
    const py = event.clientY - r.top;
    if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
    const x = clamp(Math.floor(((px - box.x) / box.w) * nx), 0, nx - 1);
    const yFromTop = clamp(Math.floor(((py - box.y) / box.h) * ny), 0, ny - 1);
    const y = flip ? yFromTop : ny - 1 - yFromTop;
    return { x, y, cell: cellIndex(x, y, panel.shape, panel.order) };
  };
  const describe = (hit) => {
    const x0 = axisValue(xa, nx, hit.x); const x1 = axisValue(xa, nx, hit.x + 1);
    const y0 = axisValue(ya, ny, hit.y); const y1 = axisValue(ya, ny, hit.y + 1);
    return `${esc(xa.label.split(' · ')[0])} ${fmt(x0)} … ${fmt(x1)}${unitText(xa)}, ${esc(ya.label.split(' · ')[0])} ${fmt(y0)} … ${fmt(y1)}${unitText(ya)}`;
  };
  canvas.addEventListener('mousemove', (event) => {
    const hit = cellAt(event);
    if (!hit) { hideTip(); canvas.style.cursor = ''; return; }
    const n = counts[hit.cell];
    const reach = blocked && blocked[hit.cell] ? '<br>the robot cannot reach it' : '';
    canvas.style.cursor = n > 0 && opts.onCell ? 'pointer' : '';
    showTip(event.clientX, event.clientY, `${describe(hit)}<br><b>${n}</b> of ${opts.n} ${nounOf(opts.of, opts.n)} in this subset${reach}${n > 0 && opts.onCell ? '<br><span class="cov-tip-hint">click: list them</span>' : ''}`, canvas);
  });
  canvas.addEventListener('mouseleave', hideTip);
  if (opts.onCell) canvas.addEventListener('click', (event) => { const hit = cellAt(event); if (hit && counts[hit.cell] > 0) opts.onCell(panel, hit, describe(hit)); });
  return { node: canvas, box, width, height };
}

function colorbar(scaled, ramp, title, height) {
  const width = 66;
  const { canvas, g } = canvasOf(width, height + 24);
  const bar = { x: 4, y: 8, w: 12, h: height };
  for (let k = 0; k < bar.h; k += 1) {
    const c = ramp(1 - k / Math.max(1, bar.h - 1));
    g.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`;
    g.fillRect(bar.x, bar.y + k, bar.w, 1);
  }
  g.strokeStyle = AXIS; g.strokeRect(bar.x + 0.5, bar.y + 0.5, bar.w - 1, bar.h - 1);
  g.font = FONT; g.fillStyle = SOFT; g.textBaseline = 'middle'; g.textAlign = 'left';
  for (const tick of scaled.ticks || []) {
    const y = bar.y + bar.h - tick.t * bar.h;
    g.fillRect(bar.x + bar.w, Math.round(y), 3, 1);
    g.fillText(tick.label, bar.x + bar.w + 5, y);
  }
  const wrap = el('div', { class: 'cov-colorbar' }, [canvas, el('div', { class: 'cov-colorbar-title', text: title })]);
  return wrap;
}

function legendItem(kind, label, extra) {
  const mark = kind === 'ramp' ? el('span', { class: 'cov-key-ramp', style: `background:${extra}` })
    : kind === 'empty' ? el('span', { class: 'cov-key-box cov-key-empty' })
      : kind === 'outside' ? el('span', { class: 'cov-key-box cov-key-outside' })
        : kind === 'frame' ? el('span', { class: 'cov-key-box cov-key-frame' })
          : kind === 'dash' ? el('span', { class: 'cov-key-dash' })
            : kind === 'cross' ? el('span', { class: 'cov-key-cross', text: '+' })
              : kind === 'bar' ? el('span', { class: 'cov-key-box', style: `background:${BAR};border-color:${BAR}` })
                : null;
  return el('span', { class: 'cov-key' }, [mark, el('span', { text: label })]);
}

/** Every visible panel of `panels`, sharing one colour scale; returns {node, legend, scaled}. */
function panelGrid(panels, rows, opts) {
  const size = (panel) => panel.shape[0] * panel.shape[1];
  const counts = panels.map((panel) => countCells(rows, panel.cells, size(panel)));
  const all = [];
  for (const list of counts) for (const v of list) all.push(v);
  const enough = opts.enough || 10;
  const scaled = Color.scale(all, settings.scale, { enough });
  const flags = { unreachable: panels.some((p) => p.unreachable && p.unreachable.length), limit: panels.some((p) => p.frame === 'limit') };
  const ramp = Color.ramp(settings.cmap, settings.reverse);
  const colour = lut(ramp);
  const hero = opts.layout === 'hero' && panels.length === 3;
  const columns = hero ? 2 : Math.max(1, Math.min(opts.columns || panels.length, panels.length));
  const gap = opts.compact ? 8 : 18;
  // the colour bar takes the grid's empty slot when there is one (One joint's 3 panels on 2 columns), else a column
  const slot = !opts.compact && !hero && panels.length % columns !== 0;
  const barW = opts.compact || slot ? 0 : 84;
  const width = opts.width - barW;
  const cellW = Math.floor((width - (columns - 1) * gap) / columns);
  const chromeW = opts.compact ? 10 : 62;
  const chromeH = opts.compact ? 22 : 66;
  const rowsOfPanels = hero ? 2 : Math.ceil(panels.length / columns);
  const barsRight = panels.some((p) => p.marginals && p.marginals.y);
  const barsUnder = panels.some((p) => p.marginals && p.marginals.x);
  const withBars = barsRight || barsUnder;
  const maxH = opts.maxH || 420;
  let boxes;
  if (hero) {
    // the first panel (from above) spans both rows; the other two stack beside it; one mm-per-px scale for all three
    const span = (p) => [p.xAxis.hi - p.xAxis.lo, p.yAxis.hi - p.yAxis.lo];
    const [[u0, v0], [u1, v1], [u2, v2]] = panels.map(span);
    const k = Math.min((width - 2 * chromeW - gap) / (u0 + Math.max(u1, u2)), (maxH - 2 * chromeH - gap) / (v1 + v2), (maxH - chromeH) / v0);
    boxes = panels.map((p) => { const [u, v] = span(p); return { w: Math.round(u * k), h: Math.round(v * k) }; });
  } else if (opts.equal) {
    // WHY one scale (mm per px) for all: each sample lands in a pixel of every view, so they compare
    const spans = panels.map((p) => [p.xAxis.hi - p.xAxis.lo, p.yAxis.hi - p.yAxis.lo]);
    const k = Math.min(...spans.map(([u]) => (cellW - chromeW) / u), (maxH / rowsOfPanels - chromeH) / Math.max(...spans.map(([, v]) => v)));
    boxes = spans.map(([u, v]) => ({ w: Math.round(u * k), h: Math.round(v * k) }));
  } else {
    const aspect = opts.aspect || 0.66;
    const w = cellW - chromeW - (barsRight ? 70 : 0);
    const rowH = maxH / rowsOfPanels - chromeH - (barsUnder ? 44 : 0);
    const h = Math.max(opts.compact ? 36 : 110, Math.min(Math.round(w * aspect), Math.round(rowH)));
    boxes = panels.map(() => ({ w: Math.max(60, h < w * aspect ? Math.round(h / aspect) : w), h }));
  }
  const template = hero ? 'max-content max-content' : `repeat(${columns}, minmax(0, 1fr))`;
  const grid = el('div', { class: 'cov-panels' + (opts.compact ? ' cov-compact' : '') + (hero ? ' cov-hero' : ''), style: `grid-template-columns: ${template}` });
  let offset = 0;
  let tallest = 0;
  panels.forEach((panel, index) => {
    const list = counts[index];
    const t = scaled.t.subarray(offset, offset + list.length);
    offset += list.length;
    const drawn = drawPanel(panel, list, t, colour, boxes[index], { ...opts, n: rows.length });
    tallest = Math.max(tallest, boxes[index].h);
    let visited = 0;
    for (const v of list) if (v > 0) visited += 1;
    const lead = `${visited.toLocaleString('en-US').replace(/,/g, ' ')} cells · ${pct((100 * visited) / list.length)}`;
    const head = opts.compact
      ? el('div', { class: 'cov-panel-title' }, [el('b', { text: panel.title })])
      : el('div', { class: 'cov-panel-title', title: `${panel.title} · ${panel.code || ''} · ${visited} of ${list.length} cells visited` }, [
        el('b', { text: panel.title }), el('span', { class: 'cov-code', text: panel.code || '' }), el('span', { class: 'cov-lead', text: lead })]);
    const figure = el('figure', { class: 'cov-panel', 'data-cov-fig': panel.cells, style: hero && index === 0 ? 'grid-row: span 2' : null }, [head]);
    figure.append(panel.marginals && !opts.compact ? withMarginals(panel, rows, drawn) : drawn.node);
    if (!opts.compact) figure.style.width = `${(panel.marginals && panel.marginals.y ? 64 : 0) + drawn.width}px`;
    grid.append(figure);
  });
  const legend = el('div', { class: 'cov-legend' + (slot ? ' cov-legend-col' : '') }, [
    legendItem('ramp', `colour = ${nounOf(opts.of, 2)} per cell (${Color.SCALE_TITLES[settings.scale]})`, rampCss(ramp)),
    legendItem('empty', 'white = no trajectory of this subset'),
    panels.some((p) => p.unreachable && p.unreachable.length) ? legendItem('outside', 'grey = the robot cannot reach it') : null,
    panels.some((p) => p.frame === 'limit') ? legendItem('frame', 'red frame = the limit box (the plot spans exactly the limits)') : null,
    panels.some((p) => p.zero) ? legendItem('dash', 'dashed = zero') : null,
    panels.some((p) => p.origin) ? legendItem('cross', `+ = the origin of frame "${opts.frame || 'cell'}"`) : null,
    withBars && !opts.compact ? legendItem('bar', 'bars = trajectories touching that band (each counted once)') : null,
  ]);
  const bar = colorbar(scaled, ramp, `${nounOf(opts.of, 2)} per cell`, clamp(slot ? 150 : tallest, 80, 300));
  if (slot) {
    grid.append(el('div', { class: 'cov-slot' }, [el('div', { class: 'cov-slot-row' }, [bar, legend]), el('p', { class: 'cov-scale-note', text: SCALE_NOTES[settings.scale] })]));
    return { node: grid, legend: null, scaled, note: null, ramp, flags };
  }
  return { node: el('div', { class: 'cov-panels-row' }, [grid, opts.compact ? null : bar]), legend, scaled, note: SCALE_NOTES[settings.scale], ramp, flags };
}

function withMarginals(panel, rows, drawn) {
  const m = panel.marginals;
  const columns = m.x ? marginal(rows, panel, 0) : null;
  const bands = m.y ? marginal(rows, panel, 1) : null;
  const n = Math.max(1, rows.length);
  const box = drawn.box;
  const right = m.y ? 64 : 0;
  const under = m.x ? 40 : 0;
  const { canvas, g } = canvasOf(drawn.width + right, drawn.height + under);
  g.drawImage(drawn.node, 0, 0, drawn.width, drawn.height);
  g.fillStyle = BAR;
  const [nx, ny] = panel.shape;
  const baseY = drawn.height + under - 14;
  for (let i = 0; columns && i < nx; i += 1) {
    const h = ((under - 16) * columns[i]) / n;
    g.fillRect(box.x + (i * box.w) / nx + 0.5, baseY - h, box.w / nx - 1, h);
  }
  const flip = panel.yAxis.flip;
  for (let j = 0; bands && j < ny; j += 1) {
    const w = ((right - 18) * bands[j]) / n;
    const top = flip ? box.y + (j * box.h) / ny : box.y + box.h - ((j + 1) * box.h) / ny;
    g.fillRect(drawn.width + 4, top + 0.5, w, box.h / ny - 1);
  }
  g.font = FONT; g.fillStyle = MUTED; g.textAlign = 'left'; g.textBaseline = 'alphabetic';
  if (columns) {
    const seen = columns.filter((v) => v > 0).length;
    g.fillText(`${m.x}: ${seen} of ${nx} bands (bar = trajectories, of ${rows.length})`, box.x, drawn.height + under - 2);
  }
  if (bands) g.fillText(m.y, drawn.width + 4, box.y + box.h + 14);
  // keep the heat's own hover: forward events to the drawn canvas' handlers through a hit test on the same box
  const forward = (type) => (event) => drawn.node.dispatchEvent(new MouseEvent(type, event));
  canvas.addEventListener('mousemove', forward('mousemove'));
  canvas.addEventListener('mouseleave', forward('mouseleave'));
  canvas.addEventListener('click', forward('click'));
  // the heat canvas is not in the document: its getBoundingClientRect must be the composite's
  drawn.node.getBoundingClientRect = () => canvas.getBoundingClientRect();
  return canvas;
}


// ── the subset line: which rows a figure is drawing, said on every figure ──────────────────────────────────────────

function subsetLine(n, total, of, compact) {
  const all = n === total;
  const note = all
    ? el('span', { class: 'cov-oracle', title: 'tools/build.mjs rebuilt every grid from the rows and found the payload\'s own counts', text: compact ? '= analyze' : "= analyze's own counts (checked by tools/build.mjs)" })
    : el('span', { class: 'cov-rebuilt', title: 're-aggregated in the page from these rows\' cells (membership.json)', text: compact ? 're-aggregated' : `re-aggregated from these ${nounOf(of, n)}' cells` });
  return el('div', { class: 'cov-subset', 'data-cov-subset': '' }, [
    el('span', { class: 'cov-subset-label', text: all ? 'all' : 'subset' }),
    el('b', { text: all ? `${total}` : `${n} of ${total}` }), ` ${nounOf(of, total)}`, note,
  ]);
}

const SHORT_SCALE = { linear: 'linear, top clipped at p98', log: 'log', equalized: 'rank', visited: 'visited / not', enough: '≥ enough' };

/** A compact figure's one-line key: the ramp, its top, and what white / grey / red mean. */
function miniKey(grid, of) {
  const max = grid.scaled && grid.scaled.max ? grid.scaled.max : 0;
  return el('div', { class: 'cov-minikey' }, [
    el('span', { class: 'cov-key-ramp', style: `background:${rampCss(grid.ramp)}` }),
    el('span', { title: Color.SCALE_TITLES[settings.scale], text: `0 … ${max ? Math.round(max) : '—'} ${nounOf(of, 2)} per cell (${SHORT_SCALE[settings.scale] || settings.scale})` }),
    el('span', { class: 'cov-key-box cov-key-empty' }), el('span', { text: 'none' }),
    grid.flags && grid.flags.unreachable ? el('span', { class: 'cov-key-box cov-key-outside' }) : null,
    grid.flags && grid.flags.unreachable ? el('span', { text: 'cannot reach' }) : null,
    grid.flags && grid.flags.limit ? el('span', { class: 'cov-key-box cov-key-frame' }) : null,
    grid.flags && grid.flags.limit ? el('span', { text: 'limit box' }) : null,
  ]);
}

class Base {
  constructor(host, element, cls) {
    this.host = host;
    this.el = element;
    this.el.classList.add('cov-view', cls);
    this.bound = follow(host, () => this.draw());
    this.resize = new ResizeObserver(() => {
      if (!this.input) return;
      if (Math.abs(this.el.clientWidth - (this.width || 0)) > 4 || Math.abs(this.el.clientHeight - (this.height || 0)) > 4) this.draw();
    });
    this.resize.observe(this.el);
  }

  update(input) { this.input = input; this.draw(); }

  destroy() { this.bound.off(); this.resize.disconnect(); hideTip(); }

  size() {
    this.width = this.el.clientWidth;
    this.height = this.el.clientHeight;
    return { W: this.width, H: this.height };
  }
}

// ── the occupancy view ─────────────────────────────────────────────────────────────────────────────────────────────

export class OccupancyView extends Base {
  constructor(host, element) { super(host, element, 'cov-occupancy'); }

  onCell(panel, hit, where, rows) {
    const through = (rows || this.input.rows).filter((row) => (row[panel.cells] || []).includes(hit.cell));
    if (!through.length) return;
    // WHY host.open with the records: data-ui's own pane lists "the N records behind this cell", as a pivot cell does
    this.host.open(through[0].id, { records: through, title: `${panel.title} · ${where}`, row: { id: `@cell-${panel.cells}-${hit.cell}`, task: `${through.length} ${nounOf('trajectory', through.length)} through ${where}` } });
  }

  draw() {
    if (!this.input) return;
    this.bound.use();
    const input = this.input;
    const config = input.view.occupancy || {};
    const compact = !!config.compact;
    const of = config.of || 'row';
    const { W, H } = this.size();
    if (!W) return;
    const width = Math.max(compact ? 140 : 320, W - (compact ? 2 : 28));
    let panels = config.panels || [];
    const head = el('div', { class: 'cov-viewhead' }, [subsetLine(input.rows.length, input.total, of, compact)]);
    if (config.pick) {
      const groups = [...new Set(panels.map((panel) => panel.group))];
      const picked = groups.includes(input.view.pick) ? input.view.pick : groups[0];
      const picker = el('div', { class: 'cov-picker', role: 'group', 'aria-label': config.pick.label, 'data-cov-joint-picker': '' },
        [el('span', { class: 'cov-picker-label', text: config.pick.label })]);
      for (const group of groups) {
        picker.append(el('button', { type: 'button', class: 'cov-pick' + (group === picked ? ' cov-on' : ''), 'aria-pressed': String(group === picked), 'data-pick': group, text: group,
          onclick: () => { if (group !== picked) this.host.setView({ pick: group }); } }));
      }
      head.prepend(picker);
      panels = panels.filter((panel) => panel.group === picked);
    }
    const parts = [head];
    if (config.splitBy) {
      parts.push(...this.split(config, panels, width, Math.max(160, H - 52), of));
    } else {
      const grid = panelGrid(panels, input.rows, {
        width, columns: config.columns, equal: config.equal, layout: config.layout, frame: config.frame, of, compact,
        maxH: compact ? Math.max(90, H - (config.layout === 'hero' ? 92 : 72)) : Math.max(240, H - 110), aspect: config.columns === 1 ? 0.42 : 0.62, enough: 10,
        onCell: (panel, hit, where) => this.onCell(panel, hit, where),
      });
      parts.push(grid.node);
      if (compact) parts.push(miniKey(grid, of));
      else parts.push(grid.legend, grid.note ? el('p', { class: 'cov-scale-note', text: grid.note }) : null);
    }
    if (config.note) parts.push(el('p', { class: 'cov-note', text: config.note }));
    this.el.replaceChildren(el('div', { class: 'cov-viewbody' + (compact ? ' cov-compactbody' : '') }, parts));
  }

  /** splitBy: one line of the same panels per value of a property (its colours' order), one colour scale for all. */
  split(config, panels, width, height, of) {
    const input = this.input;
    const by = config.splitBy;
    const column = input.columns[by] || {};
    const colors = column.colors || {};
    const whole = (this.host.element.data && this.host.element.data.rows) || input.rows;
    const groups = new Map(Object.keys(colors).map((key) => [key, { rows: [], total: 0 }]));
    for (const row of whole) { const k = row[by]; if (!groups.has(k)) groups.set(k, { rows: [], total: 0 }); groups.get(k).total += 1; }
    for (const row of input.rows) groups.get(row[by]).rows.push(row);
    const shown = [...groups].filter(([, g]) => g.rows.length);
    const size = (panel) => panel.shape[0] * panel.shape[1];
    const counts = shown.map(([, g]) => panels.map((panel) => countCells(g.rows, panel.cells, size(panel))));
    const all = [];
    for (const line of counts) for (const list of line) for (const v of list) all.push(v);
    const scaled = Color.scale(all, settings.scale, { enough: 10 });
    const ramp = Color.ramp(settings.cmap, settings.reverse);
    const colour = lut(ramp);
    // each panel keeps its grid's shape; a line is as tall as its tallest panel; every line the same size
    const aspect = (panel) => (panel.order === 'y-major' ? 0.5 : panel.unreachable ? (panel.yAxis.hi - panel.yAxis.lo) / (panel.xAxis.hi - panel.xAxis.lo) : 0.62);
    // every panel keeps its grid's aspect at one line height: Σ (lineH / aspect + its 10 px margins) + gaps fits the width
    const gap = 6;
    const across = (width - 10 * panels.length - gap * (panels.length - 1) - 4) / panels.reduce((a, p) => a + 1 / aspect(p), 0);
    const lineH = Math.max(30, Math.floor(Math.min(across, height / Math.max(1, shown.length) - 30)));
    const boxes = panels.map((p) => ({ w: Math.max(24, Math.floor(lineH / aspect(p))), h: lineH }));
    const grid = el('div', { class: 'cov-split', style: `grid-template-columns: ${boxes.map((b) => `${b.w + 10}px`).join(' ')}` });
    for (const panel of panels) grid.append(el('div', { class: 'cov-split-col', title: panel.code || panel.title, text: panel.title }));
    let offset = 0;
    shown.forEach(([value, g], gi) => {
      const slot = colors[value];
      grid.append(el('div', { class: 'cov-split-h', style: slot ? `--cov-c: var(--dv-series-${slot})` : null, 'data-cov-split': value }, [
        el('i', { class: 'cov-swatch' }), el('b', { text: value }), el('span', { text: ` ${g.rows.length} of ${g.total} ${nounOf(of, g.total)}` })]));
      panels.forEach((panel, pi) => {
        const list = counts[gi][pi];
        const t = scaled.t.subarray(offset, offset + list.length);
        offset += list.length;
        const drawn = drawPanel(panel, list, t, colour, boxes[pi], { compact: true, n: g.rows.length, of,
          onCell: (p, hit, where) => this.onCell(p, hit, `${where} · ${value}`, g.rows) });
        grid.append(el('figure', { class: 'cov-panel cov-split-cell', style: slot ? `--cov-c: var(--dv-series-${slot})` : null }, [drawn.node]));
      });
    });
    const missing = [...groups].filter(([, g]) => !g.rows.length).map(([value]) => value);
    const key = miniKey({ scaled, ramp, flags: { unreachable: panels.some((p) => p.unreachable && p.unreachable.length), limit: panels.some((p) => p.frame === 'limit') } }, of);
    if (missing.length) key.append(el('span', { class: 'cov-missing', text: `· not in the rail's pick: ${missing.join(', ')}` }));
    return [grid, key];
  }
}

// ── the headline numbers ───────────────────────────────────────────────────────────────────────────────────────────

function numberText(value, spec) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (spec.unit === '%') return `${value.toFixed(spec.decimals ?? 1)}`;
  if (spec.decimals !== undefined) return value.toLocaleString('en-US', { minimumFractionDigits: spec.decimals, maximumFractionDigits: spec.decimals });
  return Math.round(value).toLocaleString('en-US');
}

export class NumbersView extends Base {
  constructor(host, element) { super(host, element, 'cov-numbers'); }

  draw() {
    if (!this.input) return;
    this.size();
    const input = this.input;
    const rows = input.rows;
    const all = rows.length === input.total;
    const head = el('div', { class: 'cov-viewhead' }, [subsetLine(rows.length, input.total, 'trajectory', true)]);
    // WHY two layouts: label-over-value cards read best with room; in a short card (a 680 px host slot) the same numbers
    // become a dense label · value list, so all ten stay in view instead of scrolling inside the card
    const { W, H } = { W: this.width, H: this.height };
    const specs = input.view.numbers || [];
    const cols = Math.max(1, Math.floor(W / 164));
    const dense = H && 30 + Math.ceil(specs.length / cols) * 62 + 40 > H;
    const grid = el('div', { class: 'cov-nums' + (dense ? ' cov-nums-dense' : ''), 'data-cov-numbers': '' });
    for (const spec of specs) {
      const value = rows.length ? summarize(spec, rows) : null;
      const unit = spec.unit ? el('span', { class: 'cov-num-u', text: spec.unit === '%' ? ' %' : ` ${spec.unit}` }) : null;
      let check = null;
      if (all && spec.analyze !== undefined) {
        const tolerance = spec.tolerance ?? 1e-6 * Math.max(1, Math.abs(spec.analyze));
        const same = Math.abs(value - spec.analyze) <= tolerance;
        check = el('span', { class: same ? 'cov-num-ok' : 'cov-num-bad', title: `analyze: ${spec.analyze}`, text: same ? '= analyze' : `≠ analyze ${spec.analyze}` });
      }
      grid.append(el('div', { class: 'cov-num', title: `${spec.label}${spec.note ? ` (${spec.note})` : ''}: ${all ? 'every trajectory' : `the ${rows.length} the rail leaves, re-aggregated`}` }, [
        el('span', { class: 'cov-num-k', text: spec.label }),
        el('span', { class: 'cov-num-v' }, [el('b', { text: numberText(value, spec) }), unit]),
        el('span', { class: 'cov-num-n' }, [spec.note ? `${spec.note} ` : '', all ? check : el('span', { class: 'cov-num-sub', text: '~ subset' })]),
      ]));
    }
    const whole = input.view.whole || [];
    const line = el('p', { class: 'cov-whole' }, [
      el('span', { class: 'cov-whole-label', text: all ? 'Also from analyze:' : 'Whole set only (need every sample, not re-aggregated):' }),
      ...whole.map((row) => el('span', { class: 'cov-whole-item', title: row.label }, [row.label.replace(/ \(.*\)$/, ''), ' ',
        el('b', { text: row.unit === '%' ? `${Math.round(row.value)} %` : `${Number(row.value).toFixed(2)} ${row.unit || ''}` })])),
    ]);
    this.el.replaceChildren(el('div', { class: 'cov-viewbody cov-compactbody' }, [head, grid, line]));
  }
}

// ── the subset's make-up by dataset (and the dataset colour key) ───────────────────────────────────────────────────

export class DatasetMixView extends Base {
  constructor(host, element) { super(host, element, 'cov-mix'); }

  draw() {
    if (!this.input) return;
    this.size();
    const input = this.input;
    const config = input.view.mix || {};
    const by = config.by;
    const split = config.split;
    const of = config.of || 'row';
    const colors = (input.columns[by] && input.columns[by].colors) || {};
    const whole = (this.host.element.data && this.host.element.data.rows) || input.rows;
    const groups = new Map(Object.keys(colors).map((key) => [key, { total: 0, n: 0, parts: {} }]));
    for (const row of whole) { const k = row[by]; if (!groups.has(k)) groups.set(k, { total: 0, n: 0, parts: {} }); groups.get(k).total += 1; }
    for (const row of input.rows) { const g = groups.get(row[by]); g.n += 1; g.parts[row[split]] = (g.parts[row[split]] || 0) + 1; }
    const splits = [...new Set(whole.map((row) => row[split]))].sort();
    const most = Math.max(1, ...[...groups.values()].map((g) => g.total));
    const picked = [...groups.values()].filter((g) => g.n).length;
    const head = el('div', { class: 'cov-viewhead' }, [el('div', { class: 'cov-subset' }, [
      el('b', { text: `${input.rows.length} of ${input.total}` }), ` ${nounOf(of, input.total)} · ${picked} of ${groups.size} datasets`])]);
    const list = el('div', { class: 'cov-mixrows', 'data-cov-mix': '' });
    for (const [value, g] of groups) {
      const slot = colors[value];
      const bar = el('div', { class: 'cov-mixbar', style: `width:${(100 * g.total) / most}%` });
      splits.forEach((s, i) => {
        const n = g.parts[s] || 0;
        if (n) bar.append(el('span', { class: `cov-mixseg cov-mixseg-${i}`, style: `width:${(100 * n) / g.total}%`, title: `${value} · ${s}: ${n}` }));
      });
      list.append(el('div', { class: 'cov-mixrow' + (g.n ? '' : ' cov-mixrow-off'), style: slot ? `--cov-c: var(--dv-series-${slot})` : null, 'data-cov-mix-row': value }, [
        el('span', { class: 'cov-mixname' }, [el('i', { class: 'cov-swatch' }), value]),
        el('span', { class: 'cov-mixtrack' }, [bar]),
        el('span', { class: 'cov-mixn' }, [el('b', { text: String(g.n) }), ` of ${g.total}`]),
      ]));
    }
    const key = el('div', { class: 'cov-minikey' }, [
      ...splits.flatMap((s, i) => [el('span', { class: `cov-key-box cov-mixkey-${i}` }), el('span', { text: s })]),
      el('span', { class: 'cov-key-box cov-mixkey-track' }), el('span', { text: 'left out' }),
    ]);
    this.el.replaceChildren(el('div', { class: 'cov-viewbody cov-compactbody' }, [head, list, key]));
  }
}
