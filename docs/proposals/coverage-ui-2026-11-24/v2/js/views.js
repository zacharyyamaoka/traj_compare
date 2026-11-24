/* views.js — the two views V2 registers with data-ui (CONTRACT §1, registerView), so the coverage figures sit in
 * data-ui's frame (its tabs, its rail, its query bar, its status line) and redraw from whatever rows those leave.
 *
 *   occupancy          a generic view: each row lists the cells it visits on a named grid (a list property); the view
 *                      draws, over the rows it is handed, how many rows list each cell. Grids, axes, the limit frame,
 *                      unreachable cells and a picker over panel groups come from the view entry (`occupancy:`), so it
 *                      knows nothing about robots. One colour scale is shared by every panel the view shows.
 *   coverage-overview  the headline numbers of the rows it is handed (stock <data-kpi> cards) and small copies of the
 *                      other views' panels; the only place the numbers show (Zach, Nov 24 #1).
 *
 * Counts are trajectories per cell (rows per cell), the payload's `paths` measure. With nothing filtered they equal the
 * payload exactly (aggregate.js oracle(), run at start); every panel says which subset it is drawing.
 */

import { countCells, cellXY, cellIndex, marginal, summarize } from './aggregate.js';
import { settings, onSettings, SCALE_NOTES } from './settings.js';

const Color = globalThis.CoverageColor;
const INK = '#18181b';
const SOFT = '#52525b';
const MUTED = '#8a8a93';
const AXIS = '#c4c4cc';
const BAR = '#7f9cc0';
const FONT = '10.5px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const FONT_BOLD = '600 11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

// the page tells the views what the oracle found and where the base document is (app.js)
export const context = { oracle: null, base: null, total: 0 };

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

let tip = null;
function showTip(x, y, html) {
  if (!tip) { tip = el('div', { class: 'v2-tip', role: 'tooltip' }); document.body.append(tip); }
  tip.innerHTML = html;
  tip.hidden = false;
  const box = tip.getBoundingClientRect();
  tip.style.left = `${Math.min(globalThis.innerWidth - box.width - 8, x + 14)}px`;
  tip.style.top = `${Math.min(globalThis.innerHeight - box.height - 8, y + 14)}px`;
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
    showTip(event.clientX, event.clientY, `${describe(hit)}<br><b>${n}</b> of ${opts.n} ${nounOf(opts.of, opts.n)} in this subset${reach}${n > 0 && opts.onCell ? '<br><span class="v2-tip-hint">click: list them</span>' : ''}`);
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
  const wrap = el('div', { class: 'v2-colorbar' }, [canvas, el('div', { class: 'v2-colorbar-title', text: title })]);
  return wrap;
}

function legendItem(kind, label, extra) {
  const mark = kind === 'ramp' ? el('span', { class: 'v2-key-ramp', style: `background:${extra}` })
    : kind === 'empty' ? el('span', { class: 'v2-key-box v2-key-empty' })
      : kind === 'outside' ? el('span', { class: 'v2-key-box v2-key-outside' })
        : kind === 'frame' ? el('span', { class: 'v2-key-box v2-key-frame' })
          : kind === 'dash' ? el('span', { class: 'v2-key-dash' })
            : kind === 'cross' ? el('span', { class: 'v2-key-cross', text: '+' })
              : kind === 'bar' ? el('span', { class: 'v2-key-box', style: `background:${BAR};border-color:${BAR}` })
                : null;
  return el('span', { class: 'v2-key' }, [mark, el('span', { text: label })]);
}

function subsetLine(n, total, of) {
  const all = n === total;
  const oracle = context.oracle;
  const note = all
    ? (oracle && !oracle.failures.length
      ? el('span', { class: 'v2-oracle', title: oracle.lines.join('\n'), text: "= analyze's own counts (checked at load)" })
      : el('span', { class: 'v2-oracle v2-bad', text: 'does NOT match the payload: see the console' }))
    : el('span', { class: 'v2-rebuilt', text: `re-aggregated from these ${nounOf(of, n)}' cells (membership.json)` });
  return el('div', { class: 'v2-subset', 'data-v2-subset': '' }, [
    el('span', { class: 'v2-subset-label', text: 'subset' }),
    el('b', { text: `${n} of ${total}` }), ` ${nounOf(of, total)}`, note,
  ]);
}

/** Every visible panel of `panels`, sharing one colour scale; returns {node, legend, scaled}. */
function panelGrid(panels, rows, opts) {
  const size = (panel) => panel.shape[0] * panel.shape[1];
  const counts = panels.map((panel) => countCells(rows, panel.cells, size(panel)));
  const all = [];
  for (const list of counts) for (const v of list) all.push(v);
  const enough = context.enough || 10;
  const scaled = Color.scale(all, settings.scale, { enough });
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
  const grid = el('div', { class: 'v2-panels' + (opts.compact ? ' v2-compact' : '') + (hero ? ' v2-hero' : ''), style: `grid-template-columns: ${template}` });
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
      ? el('div', { class: 'v2-panel-title' }, [el('b', { text: panel.title })])
      : el('div', { class: 'v2-panel-title', title: `${panel.title} · ${panel.code || ''} · ${visited} of ${list.length} cells visited` }, [
        el('b', { text: panel.title }), el('span', { class: 'v2-code', text: panel.code || '' }), el('span', { class: 'v2-lead', text: lead })]);
    const figure = el('figure', { class: 'v2-panel', 'data-v2-fig': panel.cells, style: hero && index === 0 ? 'grid-row: span 2' : null }, [head]);
    figure.append(panel.marginals && !opts.compact ? withMarginals(panel, rows, drawn) : drawn.node);
    if (!opts.compact) figure.style.width = `${(panel.marginals && panel.marginals.y ? 64 : 0) + drawn.width}px`;
    grid.append(figure);
  });
  const legend = el('div', { class: 'v2-legend' + (slot ? ' v2-legend-col' : '') }, [
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
    grid.append(el('div', { class: 'v2-slot' }, [el('div', { class: 'v2-slot-row' }, [bar, legend]), el('p', { class: 'v2-scale-note', text: SCALE_NOTES[settings.scale] })]));
    return { node: grid, legend: null, scaled, note: null };
  }
  return { node: el('div', { class: 'v2-panels-row' }, [grid, opts.compact ? null : bar]), legend, scaled, note: SCALE_NOTES[settings.scale] };
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

// ── the occupancy view ───────────────────────────────────────────────────────────────────────────────────────────

const live = new Set();

export class OccupancyView {
  constructor(host, element) {
    this.host = host;
    this.el = element;
    this.el.classList.add('v2-view', 'v2-occupancy');
    this.off = onSettings(() => this.draw());
    this.resize = new ResizeObserver(() => { if (this.input && Math.abs(this.el.clientWidth - (this.width || 0)) > 4) this.draw(); });
    this.resize.observe(this.el);
    live.add(this);
  }

  update(input) { this.input = input; this.draw(); }

  destroy() { this.off(); this.resize.disconnect(); live.delete(this); hideTip(); }

  onCell(panel, hit, where) {
    const rows = this.input.rows.filter((row) => (row[panel.cells] || []).includes(hit.cell));
    if (!rows.length) return;
    // WHY host.open with the records: data-ui's own peek lists "the N records behind this cell" (§1, §13), as a pivot
    // cell does; a row there is a trajectory, and the drill into it is the table's
    this.host.open(rows[0].id, { records: rows, title: `${panel.title} · ${where}`, row: { id: `@cell-${panel.cells}-${hit.cell}`, name: `${rows.length} ${nounOf('trajectory', rows.length)} through ${where}` } });
  }

  draw() {
    if (!this.input) return;
    const input = this.input;
    const config = input.view.occupancy || {};
    const of = config.of || 'row';
    const width = Math.max(320, this.el.clientWidth - 40);
    this.width = this.el.clientWidth;
    let panels = config.panels || [];
    const head = el('div', { class: 'v2-viewhead' }, [subsetLine(input.rows.length, input.total, of)]);
    if (config.pick) {
      const groups = [...new Set(panels.map((panel) => panel.group))];
      const picked = groups.includes(input.view.pick) ? input.view.pick : groups[0];
      const picker = el('div', { class: 'v2-picker', role: 'group', 'aria-label': config.pick.label, 'data-v2-joint-picker': '' },
        [el('span', { class: 'v2-picker-label', text: config.pick.label })]);
      for (const group of groups) {
        picker.append(el('button', { type: 'button', class: 'v2-pick' + (group === picked ? ' v2-on' : ''), 'aria-pressed': String(group === picked), 'data-pick': group, text: group,
          onclick: () => { if (group !== picked) this.host.setView({ pick: group }); } }));
      }
      head.prepend(picker);
      panels = panels.filter((panel) => panel.group === picked);
    }
    const height = Math.max(360, this.el.clientHeight || 600);
    const grid = panelGrid(panels, input.rows, {
      width, columns: config.columns, equal: config.equal, layout: config.layout, frame: config.frame, of,
      maxH: height - 120, aspect: config.columns === 1 ? 0.42 : 0.62,
      onCell: (panel, hit, where) => this.onCell(panel, hit, where),
    });
    this.el.replaceChildren(el('div', { class: 'v2-viewbody' }, [head, grid.node, grid.legend,
      grid.note ? el('p', { class: 'v2-scale-note', text: grid.note }) : null,
      el('p', { class: 'v2-hint', text: 'Hover a cell for its count; click it to list the trajectories through it (data-ui\'s record pane).' })]));
  }
}

// ── the overview ─────────────────────────────────────────────────────────────────────────────────────────────────

function payloadNumber(key) {
  const coverage = globalThis.COVERAGE_UI && globalThis.COVERAGE_UI.coverage;
  return coverage ? coverage.numbers.find((row) => row.key === key) : null;
}

function wholeText(row) {
  if (!row) return '';
  if (row.unit === '%') return pct(row.value);
  if (row.unit === 'm/s') return `${row.value.toFixed(2)} m/s`;
  return fmt(row.value) + (row.unit ? ` ${row.unit}` : '');
}

export class OverviewView {
  constructor(host, element) {
    this.host = host;
    this.el = element;
    this.el.classList.add('v2-view', 'v2-overview');
    this.off = onSettings(() => this.draw());
    this.resize = new ResizeObserver(() => { if (this.input && Math.abs(this.el.clientWidth - (this.width || 0)) > 4) this.draw(); });
    this.resize.observe(this.el);
  }

  update(input) { this.input = input; this.draw(); }

  destroy() { this.off(); this.resize.disconnect(); hideTip(); }

  draw() {
    if (!this.input) return;
    const input = this.input;
    const config = input.view.overview || {};
    const rows = input.rows;
    const all = rows.length === input.total;
    this.width = this.el.clientWidth;
    const width = Math.max(320, this.el.clientWidth - 40);
    const splits = {};
    for (const row of rows) splits[row.split] = (splits[row.split] || 0) + 1;
    const colours = (context.base && context.base.properties.split.colors) || {};
    const composition = el('span', { class: 'v2-composition' }, Object.entries(splits).map(([name, n]) =>
      el('span', { class: `dv-badge dv-h${colours[name] || 0}`, title: `split = ${name}`, text: `${name} ${n}` })));
    const head = el('div', { class: 'v2-viewhead' }, [subsetLine(rows.length, input.total, 'trajectory'), composition]);

    // the headline numbers: stock <data-kpi> cards, over THIS subset; equal to analyze's when nothing is filtered
    const cards = el('div', { class: 'v2-kpis', 'data-v2-stats': '' });
    for (const spec of config.numbers || []) {
      const value = rows.length ? summarize(spec, rows) : null;
      const payload = payloadNumber(spec.payload);
      const card = document.createElement('data-kpi');
      const decimals = spec.decimals ?? (spec.unit === '%' ? 1 : 0);
      card.card = {
        label: spec.label,
        value: { value, unit: spec.unit === '%' ? '%' : spec.unit, basis: all ? undefined : 'derived', note: all ? `analyze: ${payload ? payload.value : '—'}` : 're-aggregated over the rows the filters leave' },
        column: { decimals },
        format: { compact: false },
        from: [spec.note, all ? 'analyze' : `subset of ${rows.length}`].filter(Boolean).join(' · '),
      };
      cards.append(card);
    }
    const whole = (config.whole || []).map(payloadNumber).filter(Boolean);
    const wholeLine = el('p', { class: 'v2-whole' }, [
      el('span', { class: 'v2-whole-label', text: all ? 'Also from analyze:' : 'Whole set only (analyze; needs every sample, so it does not re-aggregate):' }),
      ...whole.map((row) => el('span', { class: 'v2-whole-item', title: row.key }, [row.label.replace(/ \(.*\)$/, ''), ' ', el('b', { text: wholeText(row) })])),
    ]);

    // small copies of the other views' panels: the whole dataset at a glance, one click from each focus area
    const minis = el('div', { class: 'v2-minis' });
    const views = (context.base && context.base.views) || [];
    // WHY these shares: six joint maps want the most room; the three tool views share one scale; the sphere is one map
    const shares = { 'All joints': 0.4, 'Tool position': 0.36, 'Tool orientation': 0.24 };
    const room = width - 2 * 14 - 3 * 18;
    for (const name of config.minis || []) {
      const view = views.find((item) => item.name === name);
      if (!view || !view.occupancy) continue;
      const w = Math.floor(room * (shares[name] || 0.3));
      const panels = view.occupancy.panels;
      const grid = panelGrid(panels, rows, {
        width: w, columns: name === 'All joints' ? 3 : panels.length, equal: view.occupancy.equal, layout: view.occupancy.layout,
        of: 'trajectory', compact: true, maxH: 300, aspect: name === 'Tool orientation' ? 0.5 : 0.62,
      });
      const open = el('button', { type: 'button', class: 'v2-mini-open', 'data-v2-open-view': name, text: `${name} ›`, title: `Open the ${name} view`,
        onclick: () => this.host.element.selectView(name) });
      minis.append(el('section', { class: 'v2-mini', style: `width:${w + 18}px` }, [open, grid.node]));
    }
    const ramp = Color.ramp(settings.cmap, settings.reverse);
    const key = el('div', { class: 'v2-legend' }, [
      legendItem('ramp', `colour = trajectories per cell, one scale per figure (${Color.SCALE_TITLES[settings.scale]})`, rampCss(ramp)),
      legendItem('empty', 'white = no trajectory of this subset'),
      legendItem('outside', 'grey = the robot cannot reach it'),
      legendItem('frame', 'red frame = the joint\'s limit box'),
    ]);
    this.el.replaceChildren(el('div', { class: 'v2-viewbody' }, [head, cards, wholeLine,
      el('h3', { class: 'v2-section', text: all ? 'What the whole set covers' : `What these ${rows.length} trajectories cover` }), minis, key]));
  }
}

/** Repaint every live coverage view (the gear changed a colour). */
export function repaintAll() { for (const view of live) view.draw(); }
