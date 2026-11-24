/* sections.js — the one view type P4 registers with data-ui: `sections`, a dashboard made of collapsible sections
 * (TensorBoard's tag groups, W&B's panel sections), listed under the view's `figures:` key, each holding one figure that re-aggregates the rows data-ui hands
 * it (`input.rows`: whatever the run list's filter leaves) and COLOURS BY the view's `colorBy:` property (here the
 * dataset), the way TensorBoard colours runs: one row of maps per dataset, one bar per dataset, one column per dataset.
 *
 *   kind: maps        occupancy maps (round 2's V2 `occupancy` drawing, copied): trajectories per cell, rows =
 *                          the colorBy groups (or "Together": one row over every row shown), one colour scale per figure
 *   kind: bars        a share or a count per item, one bar per group in its colour, plus "All shown"
 *   kind: numbers     the headline numbers, one row per group (a runs table) plus "All shown"
 *
 * Counts are trajectories per cell; with nothing filtered they equal the payload exactly (aggregate.js oracle(), run at
 * start, said on every dashboard). The component-wide colours come from settings.js (the gear).
 */

import { countCells, cellIndex, distinct, summarize } from './aggregate.js';
import { settings, onSettings, SCALE_NOTES } from './settings.js';

const Color = globalThis.CoverageColor;
const INK = '#18181b';
const SOFT = '#52525b';
const MUTED = '#8a8a93';
const AXIS = '#c4c4cc';
const ALL = 'rgb(63,63,70)';
const FONT = '10.5px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const FALLBACK = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];

// the page fills this in (app.js): the oracle's verdict, the `.base`, the run list (for the filter in words)
export const context = { oracle: null, base: null, total: 0, enough: 10, runs: null, folded: new Map(), mode: new Map(), pick: new Map(), wideNumbers: false };
const live = new Set();

// ── small helpers ────────────────────────────────────────────────────────────────────────────────────────────────
function el(tag, attrs, children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'style') node.style.cssText = value;
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
const thin = (n) => Math.round(n).toLocaleString('en-US').replace(/,/g, ' ');
function fmt(value, decimals) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (decimals !== undefined) return minus(value.toFixed(decimals));
  const size = Math.abs(value);
  if (size >= 100) return minus(String(Math.round(value)));
  if (size >= 10) return minus(value.toFixed(1).replace(/\.0$/, ''));
  if (size === 0) return '0';
  return minus(value.toPrecision(2).replace(/\.?0+$/, ''));
}
const pct = (value) => `${value > 0 && value < 10 ? value.toFixed(1).replace(/\.0$/, '') : Math.round(value)} %`;
const plural = (n, one, many) => (n === 1 ? one : many);
const swatch = (color, hollow) => el('span', { class: 'p4-sw' + (hollow ? ' p4-sw-all' : ''), style: `--ds:${color}`, 'aria-hidden': 'true' });

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
export function rampCss(ramp) {
  const stops = [];
  for (let k = 0; k <= 8; k += 1) { const c = ramp(k / 8); stops.push(`rgb(${c[0]},${c[1]},${c[2]})`); }
  return `linear-gradient(90deg, ${stops.join(', ')})`;
}
const size = (panel) => panel.shape[0] * panel.shape[1];

/** The colorBy groups of the rows, in the property's colour order: [{key, label, color, rows}]. */
export function groupsOf(rows, by, input) {
  if (!by) return [];
  const column = input.columns && input.columns[by];
  const colors = (column && column.colors) || (context.base && context.base.properties[by] && context.base.properties[by].colors) || {};
  const series = (input.tokens && input.tokens.series) || FALLBACK;
  const order = Object.keys(colors);
  const map = new Map();
  for (const row of rows) { const key = row[by]; if (!map.has(key)) map.set(key, []); map.get(key).push(row); }
  const rank = (key) => { const i = order.indexOf(key); return i < 0 ? 999 : i; };
  return [...map.keys()].sort((a, b) => rank(a) - rank(b)).map((key) => ({
    key, label: String(key), color: colors[key] ? series[colors[key] - 1] || FALLBACK[colors[key] - 1] : MUTED, rows: map.get(key),
  }));
}

// ── the hover tip lives INSIDE the component (it must never draw outside a host's slot) ─────────────────────────
function tipOf(node) {
  const root = node.closest('[data-p4-root]') || document.body;
  let tip = root.querySelector(':scope > .p4-tip');
  if (!tip) { tip = el('div', { class: 'p4-tip', role: 'tooltip', hidden: true }); root.append(tip); }
  return { root, tip };
}
function showTip(node, event, html) {
  const { root, tip } = tipOf(node);
  tip.innerHTML = html;
  tip.hidden = false;
  const box = root.getBoundingClientRect();
  const w = tip.offsetWidth; const h = tip.offsetHeight;
  tip.style.left = `${clamp(event.clientX - box.left + 14, 4, box.width - w - 4)}px`;
  tip.style.top = `${clamp(event.clientY - box.top + 14, 4, box.height - h - 4)}px`;
}
function hideTip(node) { const { tip } = tipOf(node); tip.hidden = true; }

// ── one occupancy panel (V2's drawPanel, with ticks only where a small-multiple grid needs them) ────────────────
function blockedOf(panel) {
  if (!panel.unreachable || !panel.unreachable.length) return null;
  const flags = new Uint8Array(size(panel));
  for (const [start, length] of panel.unreachable) flags.fill(1, start, Math.min(flags.length, start + length));
  return flags;
}
function heatImage(panel, t, colour, blocked) {
  const [nx, ny] = panel.shape;
  const off = document.createElement('canvas');
  off.width = nx; off.height = ny;
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
const axisValue = (axis, n, i) => (axis.edges ? axis.edges[i] : axis.lo + ((axis.hi - axis.lo) * i) / n);
const unitText = (axis) => (axis.unit ? (axis.unit.startsWith('°') ? axis.unit : ` ${axis.unit}`) : '');

function margins(opts) {
  return { l: opts.ticksY ? 40 : 3, r: 3, t: 3, b: opts.ticksX ? 30 : 3 };
}

function drawPanel(panel, counts, t, colour, box0, opts) {
  const m = margins(opts);
  const width = m.l + box0.w + m.r;
  const height = m.t + box0.h + m.b;
  const { canvas, g } = canvasOf(width, height);
  const box = { x: m.l, y: m.t, w: box0.w, h: box0.h };
  const blocked = blockedOf(panel);
  g.imageSmoothingEnabled = false;
  g.drawImage(heatImage(panel, t, colour, blocked), box.x, box.y, box.w, box.h);
  const [nx, ny] = panel.shape;
  const xa = panel.xAxis; const ya = panel.yAxis; const flip = ya.flip;
  const sx = (v) => box.x + ((v - xa.lo) / (xa.hi - xa.lo)) * box.w;
  const sy = (v) => (flip ? box.y + ((v - ya.lo) / (ya.hi - ya.lo)) * box.h : box.y + box.h - ((v - ya.lo) / (ya.hi - ya.lo)) * box.h);
  g.setLineDash([2, 3]); g.strokeStyle = 'rgba(24,24,27,0.3)'; g.lineWidth = 1;
  if ((panel.zero === 'y' || panel.zero === 'both') && ya.lo < 0 && ya.hi > 0) { g.beginPath(); g.moveTo(box.x, sy(0) + 0.5); g.lineTo(box.x + box.w, sy(0) + 0.5); g.stroke(); }
  if (panel.zero === 'both' && xa.lo < 0 && xa.hi > 0) { g.beginPath(); g.moveTo(sx(0) + 0.5, box.y); g.lineTo(sx(0) + 0.5, box.y + box.h); g.stroke(); }
  g.setLineDash([]);
  if (panel.origin && xa.lo <= 0 && xa.hi >= 0 && ya.lo <= 0 && ya.hi >= 0) {
    g.strokeStyle = INK; g.lineWidth = 1.2;
    g.beginPath(); g.moveTo(sx(0) - 4, sy(0)); g.lineTo(sx(0) + 4, sy(0)); g.moveTo(sx(0), sy(0) - 4); g.lineTo(sx(0), sy(0) + 4); g.stroke();
  }
  g.strokeStyle = panel.frame === 'limit' ? Color.LIMIT : AXIS;
  g.lineWidth = panel.frame === 'limit' ? 1.3 : 1;
  g.strokeRect(box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1);
  g.font = FONT; g.fillStyle = SOFT;
  if (opts.ticksX) {
    g.textAlign = 'center'; g.textBaseline = 'top';
    for (const v of ticks(xa.lo, xa.hi, Math.max(2, Math.round(box.w / 60)))) {
      const x = sx(v); g.fillRect(Math.round(x), box.y + box.h, 1, 3); g.fillText(minus(fmt(v)), x, box.y + box.h + 4);
    }
    g.fillStyle = INK;
    g.fillText(`${xa.label}${xa.unit ? ` (${xa.unit})` : ''}`, box.x + box.w / 2, box.y + box.h + 17);
  }
  if (opts.ticksY) {
    g.fillStyle = SOFT; g.textAlign = 'right'; g.textBaseline = 'middle';
    const list = ya.edges
      ? ya.edges.map((v, i) => ({ v, at: flip ? box.y + (i / ny) * box.h : box.y + box.h - (i / ny) * box.h })).filter((_, i) => i % 3 === 0 || i === ny)
      : ticks(ya.lo, ya.hi, Math.max(2, Math.round(box.h / 36))).map((v) => ({ v, at: sy(v) }));
    for (const tick of list) { g.fillRect(box.x - 3, Math.round(tick.at), 3, 1); g.fillText(minus(fmt(tick.v)), box.x - 5, tick.at); }
    g.save(); g.translate(9, box.y + box.h / 2); g.rotate(-Math.PI / 2); g.textAlign = 'center'; g.fillStyle = INK;
    g.fillText(`${ya.label}${ya.unit ? ` (${ya.unit})` : ''}`, 0, 0); g.restore();
  }
  const cellAt = (event) => {
    const r = canvas.getBoundingClientRect();
    const px = event.clientX - r.left; const py = event.clientY - r.top;
    if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
    const x = clamp(Math.floor(((px - box.x) / box.w) * nx), 0, nx - 1);
    const top = clamp(Math.floor(((py - box.y) / box.h) * ny), 0, ny - 1);
    const y = flip ? top : ny - 1 - top;
    return { x, y, cell: cellIndex(x, y, panel.shape, panel.order) };
  };
  const describe = (hit) => `${esc(xa.label.split(' · ')[0])} ${fmt(axisValue(xa, nx, hit.x))} … ${fmt(axisValue(xa, nx, hit.x + 1))}${unitText(xa)}, `
    + `${esc(ya.label.split(' · ')[0])} ${fmt(axisValue(ya, ny, hit.y))} … ${fmt(axisValue(ya, ny, hit.y + 1))}${unitText(ya)}`;
  canvas.addEventListener('mousemove', (event) => {
    const hit = cellAt(event);
    if (!hit) { hideTip(canvas); canvas.style.cursor = ''; return; }
    const n = counts[hit.cell];
    canvas.style.cursor = n > 0 ? 'pointer' : '';
    showTip(canvas, event, `<b>${esc(opts.group)}</b> · ${esc(panel.title)}<br>${describe(hit)}<br><b>${n}</b> of its ${opts.n} ${plural(opts.n, 'trajectory', 'trajectories')}`
      + `${blocked && blocked[hit.cell] ? '<br>the robot cannot reach it' : ''}${n > 0 ? '<br><span class="p4-tip-hint">click: list them</span>' : ''}`);
  });
  canvas.addEventListener('mouseleave', () => hideTip(canvas));
  canvas.addEventListener('click', (event) => { const hit = cellAt(event); if (hit && counts[hit.cell] > 0 && opts.onCell) opts.onCell(panel, hit, describe(hit)); });
  return { node: canvas, width, height };
}

function colorbar(scaled, ramp, height) {
  const { canvas, g } = canvasOf(58, height + 16);
  const bar = { x: 3, y: 6, w: 10, h: height };
  for (let k = 0; k < bar.h; k += 1) {
    const c = ramp(1 - k / Math.max(1, bar.h - 1));
    g.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; g.fillRect(bar.x, bar.y + k, bar.w, 1);
  }
  g.strokeStyle = AXIS; g.strokeRect(bar.x + 0.5, bar.y + 0.5, bar.w - 1, bar.h - 1);
  g.font = FONT; g.fillStyle = SOFT; g.textBaseline = 'middle'; g.textAlign = 'left';
  for (const tick of scaled.ticks || []) {
    const y = bar.y + bar.h - tick.t * bar.h;
    g.fillRect(bar.x + bar.w, Math.round(y), 3, 1); g.fillText(tick.label, bar.x + bar.w + 5, y);
  }
  return el('div', { class: 'p4-colorbar', title: scaled.note || '' }, [canvas, el('div', { class: 'p4-colorbar-title', text: 'trajectories per cell' })]);
}

function legendItem(kind, label, extra) {
  const mark = kind === 'ramp' ? el('span', { class: 'p4-key-ramp', style: `background:${extra}` })
    : kind === 'empty' ? el('span', { class: 'p4-key-box' })
      : kind === 'outside' ? el('span', { class: 'p4-key-box p4-key-outside' })
        : kind === 'frame' ? el('span', { class: 'p4-key-box p4-key-frame' })
          : kind === 'rows' ? el('span', { class: 'p4-key-rows' }) : null;
  return el('span', { class: 'p4-key' }, [mark, el('span', { text: label })]);
}

// ── figure: maps ─────────────────────────────────────────────────────────────────────────────────────────────────
function mapsFigure(figure, ctx) {
  let panels = figure.panels;
  if (figure.pickBy) panels = panels.filter((panel) => panel[figure.pickBy] === ctx.pick);
  const together = ctx.mode === 'together' || ctx.groups.length < 2;
  const groups = together
    ? [{ key: '@all', label: ctx.groups.length === 1 ? ctx.groups[0].label : `All ${ctx.rows.length} shown`, color: ctx.groups.length === 1 ? ctx.groups[0].color : ALL, rows: ctx.rows, all: ctx.groups.length !== 1 }]
    : ctx.groups;
  const counts = groups.map((group) => panels.map((panel) => countCells(group.rows, panel.cells, size(panel))));
  const flat = [];
  for (const list of counts) for (const one of list) for (const v of one) flat.push(v);
  const scaled = Color.scale(flat, settings.scale, { enough: context.enough });
  const ramp = Color.ramp(settings.cmap, settings.reverse);
  const colour = lut(ramp);
  const dense = !!figure.compact;
  const small = ctx.compact;
  const single = panels.length === 1;
  const barW = 66;
  const avail = Math.max(280, ctx.width - barW - 10);
  const gap = dense ? 8 : 14;
  const fewRows = ctx.mode === 'together' || ctx.groups.length <= 2;
  const maxH = dense ? (small ? 64 : 104) : (small ? 150 : fewRows ? 260 : 210);
  const figureNode = el('div', { class: 'p4-maps' + (dense ? ' p4-dense' : '') + (single ? ' p4-single' : ''), 'data-p4-fig': 'maps' });
  const grid = el('div', { class: 'p4-maps-grid' });
  const onCell = (group) => (panel, hit, where) => {
    const rows = group.rows.filter((row) => (row[panel.cells] || []).includes(hit.cell));
    if (rows.length) ctx.host.open(rows[0].id, { records: rows, title: `${group.label} · ${panel.title} · ${where}`, row: { id: `@cell-${panel.cells}-${hit.cell}`, task: `${rows.length} ${plural(rows.length, 'trajectory', 'trajectories')} of ${group.label} through ${where}` } });
  };
  let offset = 0;
  const slice = (list) => { const t = scaled.t.subarray(offset, offset + list.length); offset += list.length; return t; };
  const lead = (list) => { let v = 0; for (const c of list) if (c > 0) v += 1; return `${thin(v)} cells · ${pct((100 * v) / list.length)}`; };
  let tallest = 0;
  if (single) {
    // one panel: the groups side by side (TensorBoard's images, one per run)
    const panel = panels[0];
    const cols = Math.max(1, Math.min(groups.length, Math.floor((avail + gap) / (small ? 200 : 250))));
    const cellW = Math.floor((avail - gap * (cols - 1)) / cols);
    const opts0 = { ticksX: !dense, ticksY: !dense };
    const m = margins(opts0);
    let w = cellW - m.l - m.r; let h = Math.round(w * (panel.aspect || 0.62));
    if (h > maxH + 40) { h = maxH + 40; w = Math.round(h / (panel.aspect || 0.62)); }
    grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
    groups.forEach((group, gi) => {
      const list = counts[gi][0];
      const drawn = drawPanel(panel, list, slice(list), colour, { w, h }, { ...opts0, group: group.label, n: group.rows.length, onCell: onCell(group) });
      tallest = Math.max(tallest, h);
      grid.append(el('figure', { class: 'p4-cell p4-card', style: `--ds:${group.color}` }, [
        el('figcaption', { class: 'p4-cell-head' }, [swatch(group.color, group.all), el('b', { text: group.label }),
          el('span', { class: 'p4-muted', text: `${group.rows.length} traj.` })]),
        drawn.node, dense ? null : el('div', { class: 'p4-lead', text: lead(list) })]));
    });
  } else {
    const labelW = dense ? (small ? 100 : 112) : (small ? 100 : 124);
    const n = panels.length;
    const colW = Math.floor((avail - labelW - gap * n) / n);
    // the panels' boxes: equal-scale panels share one mm-per-px; the rest keep their aspect; all capped at maxH
    const opt = (first, last) => ({ ticksX: !dense && last, ticksY: !dense && first });
    const inner = (i) => { const m = margins(opt(i === 0, true)); return colW - m.l - m.r; };
    const spans = panels.map((p) => [p.xAxis.hi - p.xAxis.lo, p.yAxis.hi - p.yAxis.lo]);
    const equal = panels.map((p, i) => (p.equal ? i : -1)).filter((i) => i >= 0);
    const k = equal.length ? Math.min(...equal.map((i) => inner(i) / spans[i][0]), ...equal.map((i) => maxH / spans[i][1])) : 0;
    const boxes = panels.map((p, i) => {
      if (p.equal) return { w: Math.round(spans[i][0] * k), h: Math.round(spans[i][1] * k) };
      let w = inner(i); let h = Math.round(w * (p.aspect || 0.62));
      if (h > maxH) { h = maxH; w = Math.round(h / (p.aspect || 0.62)); }
      return { w, h };
    });
    // each column as wide as its panel (an equal-scale panel bound by height leaves no dead gap beside it)
    grid.style.gridTemplateColumns = `${labelW}px ${boxes.map((box, i) => { const m = margins(opt(i === 0, true)); return `${Math.max(box.w + m.l + m.r, 60)}px`; }).join(' ')}`;
    grid.append(el('div', { class: 'p4-corner' }));
    for (const panel of panels) grid.append(el('div', { class: 'p4-colhead', title: `${panel.title} · ${panel.code || ''}` }, [el('b', { text: panel.title }), dense ? null : el('span', { class: 'p4-code', text: panel.code || '' })]));
    groups.forEach((group, gi) => {
      const last = gi === groups.length - 1;
      grid.append(el('div', { class: 'p4-rowlab', style: `--ds:${group.color}`, title: `${group.label}: ${group.rows.length} trajectories shown` }, [
        el('div', { class: 'p4-rowlab-top' }, [swatch(group.color, group.all), el('b', { text: group.label })]),
        el('span', { class: 'p4-muted', text: `${group.rows.length} traj.` })]));
      panels.forEach((panel, pi) => {
        const list = counts[gi][pi];
        const drawn = drawPanel(panel, list, slice(list), colour, boxes[pi], { ...opt(pi === 0, last), group: group.label, n: group.rows.length, onCell: onCell(group) });
        tallest = Math.max(tallest, boxes[pi].h);
        grid.append(el('figure', { class: 'p4-cell', style: `--ds:${group.color}` }, [drawn.node, dense ? null : el('div', { class: 'p4-lead', text: lead(list) })]));
      });
    });
  }
  const wrap = el('div', { class: 'p4-maps-row' }, [grid, colorbar(scaled, ramp, clamp(tallest, 60, 200))]);
  figureNode.append(wrap);
  const blocked = panels.some((p) => p.unreachable && p.unreachable.length);
  figureNode.append(el('div', { class: 'p4-legend' }, [
    legendItem('ramp', `colour = trajectories per cell, one scale for the figure (${Color.SCALE_TITLES[settings.scale]})`, rampCss(ramp)),
    legendItem('empty', 'white = none of them'),
    blocked ? legendItem('outside', 'grey = neither deployment can reach it') : null,
    panels.some((p) => p.frame === 'limit') ? legendItem('frame', 'red frame = the joint\'s limits') : null,
    together ? null : legendItem('rows', 'one row per dataset, in its run-list colour'),
  ]));
  return figureNode;
}

// ── figure: bars ─────────────────────────────────────────────────────────────────────────────────────────────────
function barsFigure(figure, ctx) {
  let items = figure.items;
  if (figure.pickBy) items = items.filter((item) => item.group === ctx.pick);
  const groups = ctx.groups.length > 1 ? [{ key: '@all', label: `All ${ctx.rows.length} shown`, color: ALL, rows: ctx.rows, all: true }, ...ctx.groups] : ctx.groups;
  const node = el('div', { class: 'p4-bars', 'data-p4-fig': 'bars' });
  for (const item of items) {
    const values = groups.map((group) => { const d = distinct(group.rows, item.cells); return item.total ? (100 * d) / item.total : d; });
    const max = item.total ? 100 : Math.max(1, ...values);
    const box = el('div', { class: 'p4-bars-item' }, [el('div', { class: 'p4-bars-title', text: item.label })]);
    groups.forEach((group, i) => {
      const v = values[i];
      box.append(el('div', { class: 'p4-bar' + (group.all ? ' p4-bar-all' : ''), style: `--ds:${group.color}`, title: `${group.label}: ${item.total ? pct(v) : thin(v)}` }, [
        el('span', { class: 'p4-bar-label' }, [swatch(group.color, group.all), el('span', { text: group.label })]),
        el('span', { class: 'p4-bar-track' }, [el('span', { class: 'p4-bar-fill', style: `width:${(100 * v) / max}%` })]),
        el('span', { class: 'p4-bar-val', text: item.total ? pct(v) : thin(v) })]));
    });
    node.append(box);
  }
  return node;
}

// ── figure: numbers (a runs table: a row per dataset, a column per number) ──────────────────────────────────────
function numberText(spec, value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (spec.unit === '%') return `${value.toFixed(spec.decimals ?? 1)} %`;
  const text = spec.decimals === 0 || spec.decimals === undefined ? thin(value) : value.toFixed(spec.decimals);
  return spec.unit === '°' ? `${text}°` : spec.unit ? `${text} ${spec.unit}` : text;
}
function numbersFigure(figure, ctx) {
  // WHY fewer columns in a small slot: the runs table must fit beside the rail without scrolling sideways; the rest
  // are one click away (`wide: true` numbers)
  const narrow = ctx.compact && !context.wideNumbers;
  const numbers = narrow ? figure.numbers.filter((spec) => !spec.wide) : figure.numbers;
  const hidden = figure.numbers.length - numbers.length;
  const all = ctx.rows.length === context.total;
  const groups = ctx.groups.length > 1 ? [{ key: '@all', label: `All ${ctx.rows.length} shown`, color: ALL, rows: ctx.rows, all: true }, ...ctx.groups] : ctx.groups;
  const values = groups.map((group) => numbers.map((spec) => (group.rows.length ? summarize(spec, group.rows) : null)));
  const maxOf = numbers.map((_, j) => Math.max(1e-9, ...groups.filter((g) => !g.all).map((g, i) => values[groups.indexOf(g)][j] || 0)));
  const head = el('tr', {}, [el('th', { class: 'p4-num-corner', text: ctx.groups.length > 1 ? 'Dataset' : 'Shown' }),
    ...numbers.map((spec) => el('th', { title: [spec.label, spec.note].filter(Boolean).join(' · ') }, [el('span', { text: spec.label }), spec.note ? el('small', { text: spec.note }) : null]))]);
  const body = groups.map((group, i) => el('tr', { class: group.all ? 'p4-num-all' : '', style: `--ds:${group.color}` }, [
    el('th', { class: 'p4-num-name', title: group.label }, [swatch(group.color, group.all), el('span', { text: group.label }),
      group.all || groups.length === 1 ? (all ? el('span', { class: 'p4-ok', title: (context.oracle && context.oracle.lines.join('\n')) || '', text: '= analyze ✓' }) : el('span', { class: 'p4-derived', text: 're-aggregated' })) : null]),
    ...numbers.map((spec, j) => el('td', { title: `${group.label} · ${spec.label}: ${numberText(spec, values[i][j])}` }, [
      el('span', { class: 'p4-num-v', text: numberText(spec, values[i][j]) }),
      group.all ? null : el('span', { class: 'p4-num-bar', style: `width:${clamp((100 * (values[i][j] || 0)) / maxOf[j], 0, 100)}%` })]))]));
  const table = el('table', { class: 'p4-num' }, [el('thead', {}, [head]), el('tbody', {}, body)]);
  const more = ctx.compact ? el('button', { type: 'button', class: 'p4-more-cols', text: narrow ? `+ ${hidden} more numbers` : 'fewer numbers',
    onclick: () => { context.wideNumbers = narrow; ctx.redraw(); } }) : null;
  return el('div', { class: 'p4-numwrap', 'data-p4-fig': 'numbers', 'data-p4-stats': '' }, [table,
    el('p', { class: 'p4-note' }, [all
      ? "Every number re-aggregates from the trajectories' cells; with all 212 shown the top row equals analyze's own (checked at load). "
      : 'Re-aggregated over the trajectories the run list leaves: each dataset row is its part of the subset. ', more])]);
}

// ── the view ─────────────────────────────────────────────────────────────────────────────────────────────────────
export class SectionsView {
  constructor(host, element) {
    this.host = host;
    this.el = element;
    this.el.classList.add('p4-view');
    this.off = onSettings(() => this.draw());
    this.resize = new ResizeObserver(() => { if (this.input && Math.abs(this.el.clientWidth - (this.width || 0)) > 4) this.draw(); });
    this.resize.observe(this.el);
    live.add(this);
  }

  update(input) { this.input = input; this.draw(); }

  destroy() { this.off(); this.resize.disconnect(); live.delete(this); }

  compact() { const root = this.el.closest('[data-p4-root]'); return !!(root && root.dataset.size === 'compact'); }

  folded(view, section, index) {
    const key = `${view.name}/${section.key}`;
    if (context.folded.has(key)) return context.folded.get(key);
    // WHY folded by default in a small slot: the dashboard's outline (every section's title) fits the host's slot,
    // and the reader unfolds what they came for; a full page opens everything (measured in NOTES.md)
    return this.compact() && index >= 2;
  }

  draw() {
    if (!this.input) return;
    const input = this.input;
    const view = input.view;
    const rows = input.rows;
    this.width = this.el.clientWidth;
    this.el.dataset.p4View = view.name;
    const compact = this.compact();
    const width = Math.max(300, this.el.clientWidth - (compact ? 24 : 36));
    const groups = groupsOf(rows, view.colorBy, input);
    const pickKey = view.name;
    const pick = view.pick ? (context.pick.get(pickKey) || view.pick.options[0]) : null;
    const scroll = this.el.scrollTop;

    // the subset, in words, on every dashboard: which rows, which datasets (in their colours), which toggles
    const all = rows.length === input.total;
    const oracle = context.oracle;
    const words = context.runs ? context.runs.describe() : { rest: [] };
    const head = el('div', { class: 'p4-viewhead' }, [
      el('div', { class: 'p4-subset', 'data-p4-subset': '' }, [
        el('b', { text: String(rows.length) }), ` of ${input.total} trajectories`,
        all ? el('span', { class: 'p4-ok', title: oracle ? oracle.lines.join('\n') : '', text: oracle && !oracle.failures.length ? "= analyze's own counts ✓" : 'does NOT match the payload' })
          : el('span', { class: 'p4-derived', text: 're-aggregated from their cells' }),
      ]),
      el('div', { class: 'p4-compo' }, groups.map((group) => el('span', { class: 'p4-compo-item', title: `${group.label}: ${group.rows.length} shown` }, [swatch(group.color), group.label, el('b', { text: ` ${group.rows.length}` })]))),
      words.rest.length ? el('div', { class: 'p4-filterwords', text: words.rest.join(' · ') }) : null,
    ]);
    const parts = [head];
    if (view.pick) {
      const picker = el('div', { class: 'p4-picker', role: 'group', 'aria-label': view.pick.label, 'data-p4-joint-picker': '' }, [el('span', { class: 'p4-picker-label', text: view.pick.label })]);
      for (const option of view.pick.options) {
        picker.append(el('button', { type: 'button', class: 'p4-pick' + (option === pick ? ' p4-on' : ''), 'aria-pressed': String(option === pick), 'data-pick': option, text: option,
          onclick: () => { context.pick.set(pickKey, option); this.draw(); } }));
      }
      parts.push(picker);
    }
    const ctx = { rows, groups, width, compact, pick, host: this.host, redraw: () => this.draw() };
    (view.figures || []).forEach((section, index) => {
      const key = `${view.name}/${section.key}`;
      const closed = this.folded(view, section, index);
      const mode = context.mode.get(key) || 'split';
      const title = section.title.replace('{pick}', pick || '');
      const tools = section.kind === 'maps' && groups.length > 1 ? el('div', { class: 'p4-seg', role: 'group', 'aria-label': 'Compare datasets' }, [
        ['split', 'Per dataset', 'One row per dataset, in its colour'], ['together', 'Together', 'One row over every trajectory shown'],
      ].map(([value, label, tip]) => el('button', { type: 'button', class: mode === value ? 'p4-on' : '', 'aria-pressed': String(mode === value), title: tip, text: label,
        onclick: () => { context.mode.set(key, value); this.draw(); } }))) : null;
      const sec = el('section', { class: 'p4-sec', 'data-p4-sec': section.key, 'data-open': String(!closed) }, [
        el('div', { class: 'p4-sec-head' }, [
          el('button', { type: 'button', class: 'p4-sec-toggle', 'aria-expanded': String(!closed), title: closed ? 'Unfold this section' : 'Fold this section',
            onclick: () => { context.folded.set(key, !closed); this.draw(); } }, [
            el('svg', { viewBox: '0 0 16 16', 'aria-hidden': 'true', html: '<path d="M6 4l4 4-4 4"/>' }),
            el('span', { class: 'p4-sec-title', text: title }), section.note ? el('span', { class: 'p4-sec-note', text: section.note }) : null]),
          closed ? null : tools,
        ]),
      ]);
      if (!closed) {
        let figure = null;
        if (!rows.length) figure = el('p', { class: 'p4-empty', text: 'No trajectory is left: untick something in the run list.' });
        else if (section.kind === 'maps') figure = mapsFigure(section, { ...ctx, mode });
        else if (section.kind === 'bars') figure = barsFigure(section, ctx);
        else if (section.kind === 'numbers') figure = numbersFigure(section, ctx);
        sec.append(el('div', { class: 'p4-sec-body' }, [figure]));
      }
      parts.push(sec);
    });
    parts.push(el('p', { class: 'p4-hint', text: `Colours: ${Color.SCALE_TITLES[settings.scale]} · ${settings.cmap}${settings.reverse ? ' reversed' : ''} (the gear). Hover a cell for its count; click it to list the trajectories through it.` }));
    this.el.replaceChildren(el('div', { class: 'p4-viewbody' }, parts));
    this.el.scrollTop = scroll;
  }
}

export function repaintAll() { for (const view of live) view.draw(); }
export { SCALE_NOTES };
