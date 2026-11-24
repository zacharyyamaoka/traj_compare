/* kit.js — what the four coverage views share (V3, PROPOSED-CONTRACT.md §52): the settings they read, tokens, canvas,
 * axes, the heat image, the colorbar, the legend and the hover readout.
 *
 * WHY one module and not four copies: data-ui's rule is "never a second copy" of a helper (CONTRACT §1); in data-ui
 * this file would live in the coverage view folder (packages/views/coverage/src/kit.js), one bundle for four types,
 * as scene3d's bundle registers scene3d, trajectory3d and voxels.
 *
 * Colour rule (traj_compare docs/COVERAGE.md, copied, never re-derived): coverage_color.js's five maps, its scales,
 * white (the page's surface) = never visited, grey = beyond the limit / not reachable, the limit drawn in the limit
 * colour. Zach: "Linear to me is BY far the most informative" (linear default); "lets make it easy for the user to
 * change ... to other good cmap and switch from high to low" (the gear).
 */
import { esc } from '../../vendor/data-ui/data-ui.js';
import './coverage_color.js';

export const Color = globalThis.CoverageColor;
export { esc };

export const SCALE_NOTES = {
  linear: 'Linear: colour grows in proportion to the count; the top 2 % of cells are clipped so one hot cell does not wash out the rest.',
  log: 'Log: colour follows log(count), so thin cells show too; equal colour steps are ×10, not +10.',
  equalized: 'Equalized: colour = rank among the visited cells. It shows WHERE the data is, not HOW MUCH: thin areas look as strong as busy ones.',
  visited: 'Visited / not: one colour for every cell with any sample. Is it covered at all?',
  enough: 'Enough / not: full colour = at least the "enough" count of samples; pale = visited, but fewer.',
};

/* The dashboard-wide settings, as a view reads them (PROPOSED-CONTRACT §52.3).
 * WHY three places, first wins: `input.settings` is the field §52 adds (a host's <data-settings> resolved); until data-ui
 * hands it over, the prototype host writes the reader's picks into the dashboard's `style:` and data-ui already resolves
 * style for every panel into `input.view.style` (resolveStyle keeps unknown keys); last, the defaults. */
export function settingsOf(input) {
  const s = (input && input.settings) || {};
  const st = (input && input.view && input.view.style) || {};
  const pick = (key, fallback) => (s[key] !== undefined && s[key] !== null ? s[key] : st[key] !== undefined && st[key] !== null ? st[key] : fallback);
  const colormap = Color.NAMES.includes(pick('colormap', 'viridis')) ? pick('colormap', 'viridis') : 'viridis';
  const scale = Color.SCALES.includes(pick('scale', 'linear')) ? pick('scale', 'linear') : 'linear';
  return { colormap, reverse: pick('reverse', false) === true || pick('reverse', false) === 'true', scale, ramp: Color.ramp(colormap, pick('reverse', false) === true || pick('reverse', false) === 'true') };
}

export function scaleTitle(mode, enough) {
  return mode === 'enough' ? `≥ ${enough || 10} samples / not` : Color.SCALE_TITLES[mode];
}

/* tokens as canvas colours (input.tokens is resolved rgb() text, CONTRACT §4) */
export function tok(input) {
  const t = (input && input.tokens) || {};
  const css = t.css || {};
  return {
    fg: t.fg || 'rgb(24,24,27)', muted: t.muted || 'rgb(113,113,122)', border: t.border || 'rgb(228,228,231)',
    rule: t.rule || t.border || 'rgb(228,228,231)', subtle: t.subtle || 'rgb(244,244,245)', bg: t.bg || 'rgb(255,255,255)',
    accent: t.accent || 'rgb(37,99,235)', series: t.series || [], dark: !!t.dark,
    font: t.font || 'system-ui, sans-serif', mono: t.mono || 'ui-monospace, monospace',
    // the limit: a §52 token (--data-limit), defaulting to COVERAGE.md's limit red
    limit: css['data-limit'] || Color.LIMIT,
  };
}

export function rgbOf(text) {
  const m = /rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)/.exec(String(text || ''));
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])];
  const h = /^#([0-9a-f]{6})$/i.exec(String(text || ''));
  if (h) return [0, 2, 4].map((i) => parseInt(h[1].slice(i, i + 2), 16));
  return [255, 255, 255];
}

/* a group's colour (dev, holdout): the dashboard's style.families slot when it names one, else series slot by order.
 * WHY families: data-ui's own rule for "one colour per family across every card" (CONTRACT §32); the table's badge
 * reads the same slots from properties.split.colors (PROPOSED-CONTRACT §52.6 asks the table to read families too). */
export function groupColour(input, name, index) {
  const t = (input && input.tokens) || {};
  const fam = input && input.view && input.view.style && input.view.style.families;
  const series = t.series || ['#2a78d6', '#eb6834', '#1baf7a'];
  const pick = fam && fam.colors ? fam.colors[name] : undefined;
  if (typeof pick === 'number' || /^\d+$/.test(String(pick || ''))) return series[Number(pick) - 1] || series[0];
  if (typeof pick === 'string' && pick.startsWith('#')) return pick;
  return series[[0, 2, 6, 4][index % 4]] || series[0];
}

/* ── numbers ─────────────────────────────────────────────────────────────────────────────────────────────────── */

export function fmt(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const a = Math.abs(value);
  const text = a >= 1000 ? Math.round(value).toLocaleString('en-US').replace(/,/g, ' ') : a >= 100 ? value.toFixed(0)
    : a >= 10 ? value.toFixed(1).replace(/\.0$/, '') : a >= 1 ? value.toFixed(2).replace(/\.?0+$/, '') : a === 0 ? '0' : value.toPrecision(2);
  return text.replace(/^-/, '−');
}
export function pct(value) { return value === null || value === undefined ? '—' : `${value >= 10 || value === 0 ? Math.round(value) : value.toFixed(1)} %`; }
export function count(value) { return value === null || value === undefined ? '—' : Math.round(value).toLocaleString('en-US').replace(/,/g, ' '); }
export function withUnit(value, unit) {
  const text = fmt(value);
  return unit && unit.startsWith('°') ? text + unit : unit ? `${text} ${unit}` : text;
}
export function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

export function ticks(lo, hi, target) {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const raw = span / Math.max(1, target);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
  const build = (st) => {
    const out = [];
    for (let v = Math.ceil(lo / st) * st; v <= hi + st * 1e-9; v += st) out.push(Math.abs(v) < st * 1e-9 ? 0 : v);
    out.step = st;
    return out;
  };
  let out = build(step);
  // WHY: a small panel asks for few ticks, and a step past half the span leaves only "0"; halve until two show
  for (let k = 0; k < 4 && out.length < 3; k++) out = build(out.step / 2);
  return out;
}
function tickText(v, step) {
  const d = step >= 1 ? 0 : Math.min(4, Math.ceil(-Math.log10(step)));
  return v.toFixed(d).replace(/^-/, '−');
}

/* ── canvas ──────────────────────────────────────────────────────────────────────────────────────────────────── */

export function canvas(width, height, cls) {
  const ratio = Math.min(2, globalThis.devicePixelRatio || 1);
  const c = document.createElement('canvas');
  c.className = cls || 'dv-coverage-canvas';
  c.width = Math.max(1, Math.round(width * ratio));
  c.height = Math.max(1, Math.round(height * ratio));
  c.style.width = `${width}px`;
  c.style.height = `${height}px`;
  const g = c.getContext('2d');
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { canvas: c, g, width, height };
}

export function font(t, size, weight) { return `${weight || 400} ${size || 10.5}px ${t.font}`; }

/* x, y: {lo, hi, label, ticks?, labels?, show?} in display units */
export function axes(g, t, box, x, y) {
  g.save();
  g.font = font(t, 10.5);
  g.strokeStyle = t.border;
  g.fillStyle = t.muted;
  g.lineWidth = 1;
  if (x && x.show !== false) {
    const xt = x.ticks || ticks(x.lo, x.hi, Math.max(3, Math.floor(box.w / 64)));
    const step = xt.step || 1;
    g.textAlign = 'center';
    g.textBaseline = 'top';
    for (const v of xt) {
      const px = box.x + ((v - x.lo) / (x.hi - x.lo)) * box.w;
      if (px < box.x - 0.5 || px > box.x + box.w + 0.5) continue;
      g.beginPath(); g.moveTo(Math.round(px) + 0.5, box.y + box.h); g.lineTo(Math.round(px) + 0.5, box.y + box.h + 4); g.stroke();
      if (x.labels !== false) g.fillText(x.text ? x.text(v) : tickText(v, step), px, box.y + box.h + 6);
    }
    if (x.label) { g.fillStyle = t.fg; g.fillText(x.label, box.x + box.w / 2, box.y + box.h + 20); g.fillStyle = t.muted; }
  }
  if (y && y.show !== false) {
    const yt = y.ticks || ticks(y.lo, y.hi, Math.max(3, Math.floor(box.h / 38)));
    const step = yt.step || 1;
    g.textAlign = 'right';
    g.textBaseline = 'middle';
    for (const v of yt) {
      const py = box.y + box.h - ((v - y.lo) / (y.hi - y.lo)) * box.h;
      if (py < box.y - 0.5 || py > box.y + box.h + 0.5) continue;
      g.beginPath(); g.moveTo(box.x - 4, Math.round(py) + 0.5); g.lineTo(box.x, Math.round(py) + 0.5); g.stroke();
      if (y.labels !== false) g.fillText(y.text ? y.text(v) : tickText(v, step), box.x - 6, py);
    }
    if (y.label) {
      g.save();
      g.translate(box.x - (y.offset || 40), box.y + box.h / 2);
      g.rotate(-Math.PI / 2);
      g.textAlign = 'center';
      g.fillStyle = t.fg;
      g.fillText(y.label, 0, 0);
      g.restore();
    }
  }
  g.restore();
}

/* t: Float32Array (-1 = empty), cell (i, j) at t[i * ny + j], i along x, j along y (j = 0 at the bottom).
 * outside(k): true = beyond the limit / not reachable (grey); empty is the surface colour. */
export function heatImage(nx, ny, values, ramp, emptyRgb, outside) {
  const image = document.createElement('canvas');
  image.width = nx;
  image.height = ny;
  const ig = image.getContext('2d');
  const data = ig.createImageData(nx, ny);
  for (let i = 0; i < nx; i++) {
    for (let j = 0; j < ny; j++) {
      const k = i * ny + j;
      const rgb = values[k] >= 0 ? ramp(values[k]) : outside && outside(k) ? Color.OUTSIDE : emptyRgb;
      const p = ((ny - 1 - j) * nx + i) * 4;
      data.data[p] = rgb[0]; data.data[p + 1] = rgb[1]; data.data[p + 2] = rgb[2]; data.data[p + 3] = 255;
    }
  }
  ig.putImageData(data, 0, 0);
  return image;
}

export function drawImage(g, image, box) {
  g.save();
  g.imageSmoothingEnabled = false;
  g.drawImage(image, box.x, box.y, box.w, box.h);
  g.restore();
}

export function frame(g, box, colour, width, dash) {
  g.save();
  g.strokeStyle = colour;
  g.lineWidth = width || 1;
  if (dash) g.setLineDash(dash);
  g.strokeRect(box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1);
  g.restore();
}

export function vline(g, x, y0, y1, colour, width, dash) {
  g.save(); g.strokeStyle = colour; g.lineWidth = width || 1; if (dash) g.setLineDash(dash);
  g.beginPath(); g.moveTo(Math.round(x) + 0.5, y0); g.lineTo(Math.round(x) + 0.5, y1); g.stroke(); g.restore();
}
export function hline(g, y, x0, x1, colour, width, dash) {
  g.save(); g.strokeStyle = colour; g.lineWidth = width || 1; if (dash) g.setLineDash(dash);
  g.beginPath(); g.moveTo(x0, Math.round(y) + 0.5); g.lineTo(x1, Math.round(y) + 0.5); g.stroke(); g.restore();
}

function css(rgb) { return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`; }
export function rampGradient(ramp) {
  const stops = [];
  for (let i = 0; i <= 8; i++) stops.push(`${css(ramp(i / 8))} ${(i / 8) * 100}%`);
  return `linear-gradient(90deg, ${stops.join(', ')})`;
}

/* the colorbar beside a heat image: the scale's real numbers, the clip note (data-ui would call it the view's key) */
export function colorbar(scaled, title, height, ramp) {
  const h = Math.max(70, Math.round(height));
  const bar = canvas(12, h, 'dv-coverage-cb-canvas');
  const g = bar.g;
  const positions = [];
  if (scaled.mode === 'visited') {
    g.fillStyle = css(ramp(1)); g.fillRect(0, 0, 12, h);
    positions.push({ y: 0.5, label: 'visited' });
  } else if (scaled.mode === 'enough') {
    g.fillStyle = css(ramp(1)); g.fillRect(0, 0, 12, h / 2);
    g.fillStyle = css(ramp(0.25)); g.fillRect(0, h / 2, 12, h / 2);
    for (const tick of scaled.ticks) positions.push({ y: tick.t >= 1 ? 0.75 : 0.25, label: tick.label });
  } else {
    for (let y = 0; y < h; y++) { g.fillStyle = css(ramp(1 - y / Math.max(1, h - 1))); g.fillRect(0, y, 12, 1); }
    for (const tick of scaled.ticks) positions.push({ y: tick.t, label: tick.label });
  }
  const box = document.createElement('div');
  box.className = 'dv-coverage-colorbar';
  let last = -1;
  const labels = [];
  for (const item of positions.sort((a, b) => a.y - b.y)) {
    if (last >= 0 && (item.y - last) * h < 11) continue;
    labels.push(`<span class="dv-coverage-cb-tick" style="bottom:${(item.y * h).toFixed(1)}px">${esc(String(item.label).replace(/^-/, '−'))}</span>`);
    last = item.y;
  }
  box.innerHTML = `<div class="dv-coverage-cb-title">${esc(title)}</div><div class="dv-coverage-cb-body" style="height:${h}px"></div><div class="dv-coverage-cb-note">${esc(scaled.note || '')}</div>`;
  const body = box.querySelector('.dv-coverage-cb-body');
  body.append(bar.canvas);
  body.insertAdjacentHTML('beforeend', labels.join(''));
  return box;
}

/* items: {kind: fill | empty | outside | frame | line | dash | tick | ramp | path | text, colour?, label, button?} */
export function legend(items, ramp) {
  const box = document.createElement('div');
  box.className = 'dv-coverage-legend';
  box.setAttribute('data-cov-legend', '');
  for (const item of items) {
    if (!item) continue;
    const tag = item.button ? 'button' : 'span';
    const node = document.createElement(tag);
    node.className = `dv-coverage-li${item.problem ? ' dv-coverage-problem' : ''}`;
    if (item.button) {
      node.type = 'button';
      node.setAttribute('aria-pressed', String(item.pressed !== false));
      node.dataset.series = item.series;
      node.title = 'Click: show / hide · double-click: only this one';
    }
    if (item.kind !== 'text') {
      const sw = document.createElement('i');
      sw.className = `dv-coverage-sw dv-coverage-sw-${item.kind}`;
      if (item.kind === 'fill') sw.style.background = item.colour;
      else if (item.kind === 'ramp') sw.style.background = rampGradient(ramp);
      else if (item.colour) sw.style.color = item.colour;
      node.append(sw);
    }
    const text = document.createElement('span');
    text.textContent = item.label;
    node.append(text);
    box.append(node);
  }
  return box;
}

/* one readout per view, inside its own element (a view never writes outside el, CONTRACT §1) */
export function readout(el) {
  let tip = el.querySelector(':scope > .dv-coverage-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'dv-coverage-tip';
    tip.hidden = true;
    tip.setAttribute('role', 'status');
    el.append(tip);
  }
  return {
    show(cx, cy, html) {
      tip.innerHTML = html;
      tip.hidden = false;
      const w = tip.offsetWidth; const h = tip.offsetHeight;
      const left = cx + 14 + w > innerWidth ? cx - w - 12 : cx + 14;
      const top = cy + 16 + h > innerHeight ? cy - h - 10 : cy + 16;
      tip.style.left = `${Math.max(4, left)}px`;
      tip.style.top = `${Math.max(4, top)}px`;
    },
    hide() { tip.hidden = true; },
  };
}

export function hover(c, tip, find) {
  c.addEventListener('mousemove', (e) => {
    const r = c.getBoundingClientRect();
    const html = find(e.clientX - r.left, e.clientY - r.top);
    if (html) tip.show(e.clientX, e.clientY, html); else tip.hide();
  });
  c.addEventListener('mouseleave', () => tip.hide());
}

/* The height a view may fill: inside a sized dashboard panel, from the view's top to the panel's padded bottom (so a
 * figure grows into the panel the reader dragged to that size); else its own height, else `fallback`. Read-only. */
export function room(el, fallback) {
  const panel = el.closest('.dd-panel[data-sized]');
  if (!panel) return el.clientHeight > 160 ? el.clientHeight : fallback;
  const pad = parseFloat(getComputedStyle(panel).paddingBottom) || 12;
  return Math.max(120, Math.floor(panel.getBoundingClientRect().bottom - el.getBoundingClientRect().top - pad));
}

export function rows(input) { return (input && input.rows) || []; }
export function block(input) { return (input && input.view && input.view.coverage) || {}; }
export function emptyHtml(text) { return `<p class="dv-coverage-empty">${esc(text)}</p>`; }
