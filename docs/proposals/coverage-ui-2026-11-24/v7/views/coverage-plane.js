/* type: coverage-plane — a binned 2-D grid (PROPOSED-CONTRACT.md §52.1).
 *
 * Reads grid rows (one row = one grid: x/y edges, shape, a list cell of counts per cell, the scalars around it) and
 * draws each as a heat image under the dashboard's colour settings: the colormap and Reverse, the scale (linear clipped
 * at p98, log, equalized, visited, enough), white = never visited, the limit box framed in the limit colour, a
 * colorbar with the scale's real numbers, a legend naming every mark, and a hover readout of the cell. One row draws
 * large; several draw as small multiples on ONE colour scale (a cell twice as busy is twice as bright in every panel).
 *
 *   coverage:
 *     value: samples | paths | max_other      the list column the colour reads (default samples); the figure's own
 *                                             "colour =" switch writes it with host.setView
 *     title: <property>                        what names each small multiple (default: the slab band, the joint, the id)
 *     columns: 5                               small multiples per line (default: as many as fit at 150 px)
 *     share: true                              one scale over every panel (default true)
 *
 * Rows (rows.py "grid row"): x, y, x_label, y_label, x_lo, x_hi, nx, y_lo, y_hi, ny, x_scale, y_scale, x_unit,
 * y_unit (display = SI × scale), samples [nx*ny], paths?, max_other?, visited_pct?, sufficient_pct?, evenness_pct?,
 * outside?, enough, box: limit | none.
 *
 * Prior art: traj_compare's coverage page heat-q-qd / slabs (canvas, same rules); Rerun's TensorView colormap; BAM
 * Reach's colormap control. STOCK PARTS: none (canvas 2D; no chart engine: a 36 × 24 grid is one ImageData).
 */
import {
  Color, esc, settingsOf, scaleTitle, tok, rgbOf, fmt, pct, count, withUnit, clamp, canvas, font, axes, heatImage,
  drawImage, frame, hline, vline, colorbar, legend, readout, hover, rows as rowsOf, block, emptyHtml, room,
  Query, gridKey, cellFrame, hitLayer, wrapCanvas, askCell, askLine, queryLegend, clean,
} from './kit.js';
import css from './coverage-css.js';

export { css };

export function options() {
  return [
    { type: 'dropdown', key: 'coverage.value', displayName: 'Colour =', options: { samples: 'samples per cell', paths: 'trajectories per cell', max_other: 'max |qdd| in the cell' }, default: 'samples' },
    { type: 'slider', key: 'coverage.columns', displayName: 'Panels per line', min: 1, max: 8, step: 1 },
    { type: 'toggle', key: 'coverage.share', displayName: 'One colour scale for every panel', default: true },
  ];
}

const VALUE_WORD = { samples: 'samples in the cell', paths: 'distinct trajectories through the cell', max_other: 'max |qdd| reached in the cell' };
const VALUE_BAR = { samples: 'samples per cell', paths: 'trajectories per cell', max_other: 'max |qdd| per cell' };

function titleOf(row, all, key) {
  if (key && row[key] !== undefined && row[key] !== null) return String(row[key]);
  if (row.slab !== null && row.slab !== undefined) {
    return `${row.by || 'qdd'} ${fmt(row.slab_lo * row.by_scale)} … ${fmt(row.slab_hi * row.by_scale)} ${row.by_unit}`;
  }
  const joints = new Set(all.map((r) => r.joint));
  if (row.joint && joints.size > 1) return row.joint_short || row.joint;
  return `${row.x} × ${row.y}`;
}

export default class CoveragePlaneView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.classList.add('dv-coverage');
    this.tip = readout(el);
    this.width = 0;
    this.ro = new ResizeObserver(() => {
      const w = Math.floor(el.clientWidth);
      if (this.input && w > 0 && Math.abs(w - this.width) > 2) this.draw();
    });
    this.ro.observe(el);
    // V7: the cell query repaints this view in place (fade + framed chips), no dashboard reload
    this.onQuery = () => { if (this.input && !block(this.input).muted) this.draw(); };
    Query.addEventListener('change', this.onQuery);
  }

  update(input) {
    this.input = input;
    this.draw();
  }

  draw() {
    const input = this.input;
    const el = this.el;
    const list = rowsOf(input);
    const width = Math.floor(el.clientWidth);
    this.width = width;
    if (!width) return;
    for (const node of [...el.children]) if (!node.classList.contains('dv-coverage-tip')) node.remove();
    if (!list.length) { el.insertAdjacentHTML('afterbegin', emptyHtml('No grid matches this view.')); return; }
    const b = block(input);
    const settings = settingsOf(input);
    const t = tok(input);
    const available = list.filter((r) => Array.isArray(r[b.value || 'samples']));
    const value = available.length === list.length ? (b.value || 'samples') : 'samples';
    const hasPaths = list.every((r) => Array.isArray(r.paths));
    const hasOther = list.every((r) => Array.isArray(r.max_other));
    const enough = list[0].enough || 10;
    const empty = rgbOf(t.bg);
    // the drill's form: the set in grey, one trajectory's path over it (coverage.overlay: {<joint>: [[x…], [y…]]})
    const muted = !!b.muted;
    const overlay = b.overlay && typeof b.overlay === 'object' ? b.overlay : null;
    // V7, the drill: {<joint>: {cells, only}}: this trajectory's cells (accent) and the cells only it visits (ink)
    const own = b.own && typeof b.own === 'object' ? b.own : null;
    // V7, the landing: small multiples at landing size drop the long legend words
    const compact = !!b.compact;
    const grey = (tt) => { const v = Math.round(228 - 110 * tt); return [v, v, v]; };
    if (muted) settings.ramp = grey;

    // the figure's own switch: what the colour counts (a view setting, written to the view entry; shown only here)
    const head = document.createElement('div');
    head.className = 'dv-coverage-head';
    const choices = [['samples', 'samples'], ...(hasPaths ? [['paths', 'trajectories']] : []), ...(hasOther ? [['max_other', 'max |qdd|']] : [])];
    if (choices.length > 1 && !muted && b.switch !== false) {
      head.innerHTML = `<span class="dv-coverage-switch"><span class="dv-coverage-seg-label">colour =</span><span class="dv-coverage-seg" role="group" aria-label="What the colour counts">${choices.map(([v, l]) => `<button type="button" data-value="${v}" aria-pressed="${v === value}">${esc(l)}</button>`).join('')}</span></span>`;
      head.querySelector('.dv-coverage-seg').addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-value]');
        if (!btn || btn.dataset.value === value) return;
        this.host.setView({ coverage: { ...b, value: btn.dataset.value } });
      });
    }
    const lead = document.createElement('p');
    lead.className = 'dv-coverage-lead';
    head.prepend(lead);
    // V7, the landing: each small multiple names itself and its visited share; the lead line would cost a row
    if (!compact || muted) el.prepend(head);

    // WHY one scale over all panels (concatenated counts): small multiples must compare
    const share = b.share !== false;
    const values = list.map((r) => r[value]);
    const opts = { enough };
    const scaledAll = share ? Color.scale(values.flat().map((v) => (v === null ? 0 : v)), settings.scale, opts) : null;
    const scaledOf = (k) => {
      if (scaledAll) {
        const offset = values.slice(0, k).reduce((n, v) => n + v.length, 0);
        return { ...scaledAll, t: scaledAll.t.subarray(offset, offset + values[k].length) };
      }
      return Color.scale(values[k].map((v) => (v === null ? 0 : v)), settings.scale, opts);
    };

    // the lead: the grid's own numbers (the payload's, never recomputed)
    const single = list.length === 1;
    const r0 = list[0];
    if (single) {
      const parts = [];
      if (r0.visited_pct !== null && r0.visited_pct !== undefined) parts.push(`<b>${pct(r0.visited_pct)}</b> of ${count(r0.cells)} cells visited`);
      if (r0.sufficient_pct !== null && r0.sufficient_pct !== undefined) parts.push(`${pct(r0.sufficient_pct)} with ≥ ${enough} samples`);
      if (r0.evenness_pct !== null && r0.evenness_pct !== undefined) parts.push(`evenness ${pct(r0.evenness_pct)}`);
      if (r0.outside > 0) parts.push(`<span class="dv-coverage-problem">${count(r0.outside)} samples beyond the limit box (not drawn)</span>`);
      lead.innerHTML = parts.join(' · ') || `${count(r0.cells)} cells`;
    } else {
      const same = new Set(list.map((r) => r.joint)).size === 1 && list[0].joint;
      lead.innerHTML = same && r0.slab !== null && r0.slab !== undefined
        ? `<b>${esc(r0.joint)}</b> · cells visited per band, hardest braking → hardest accelerating`
        : `${list.length} grids · cells visited beside each name`;
    }
    if (muted && overlay) lead.innerHTML = 'Its path through each joint\'s position × speed plane, over every trajectory\'s cells';
    const boxed = list.some((r) => r.box === 'limit');
    let leg;
    if (muted) {
      leg = legend([
        own ? { kind: 'own', colour: t.accent, label: 'its cells' } : null,
        own ? { kind: 'fill', colour: t.fg, label: 'cells no other trajectory visits' } : null,
        overlay ? { kind: 'path', colour: t.accent, label: 'its path (dot = its start)' } : null,
        { kind: 'fill', colour: 'rgb(160,160,160)', label: 'every trajectory\'s cells (darker = more samples)' },
        boxed ? { kind: 'frame', colour: t.limit, label: 'red frame = the limit box' } : null,
      ], settings.ramp);
    } else {
      const asked = list.some((r) => gridKey(r) && Query.indexed(gridKey(r)));
      leg = legend([
        { kind: 'ramp', label: `colour = ${VALUE_WORD[value]}${list.length > 1 && share ? ', one scale for every panel' : ''} (${scaleTitle(settings.scale, enough)})` },
        { kind: 'empty', label: 'white = never visited' },
        boxed ? { kind: 'frame', colour: t.limit, label: compact ? 'red frame = the limit box' : 'red frame = the limit box (the plot spans exactly the limits)' } : null,
        boxed ? { kind: 'dash', colour: t.muted, label: 'zero line' } : null,
        ...(asked ? queryLegend(t).map((it) => ({ ...it, bg: empty })) : []),
        asked && !Query.active ? { kind: 'text', label: 'click a coloured cell: who made it' } : null,
      ], settings.ramp);
    }
    // WHY the legend is built and measured before the figure: the figure gets the panel's height left after its head
    // and legend, so a longer legend (the query's two lines, a narrow panel's wraps) never pushes it past the panel
    el.append(leg);
    const body = document.createElement('div');
    body.className = 'dv-coverage-body';
    el.insertBefore(body, leg);
    const cbW = 96;
    const plotArea = width - cbW - 8;
    const headH = head.isConnected ? head.offsetHeight + 6 : 0;
    const availH = room(el, 470) - headH - leg.offsetHeight - 22;
    const panels = document.createElement('div');
    panels.className = single ? 'dv-coverage-single' : 'dv-coverage-multiples';
    let plotH = 0;
    if (single) {
      const r = list[0];
      const aspect = r.box === 'none' ? 0.5 : 0.62;
      const plotW = plotArea;
      const h = clamp(Math.round(Math.min(plotW * aspect, availH)), 150, 520);
      plotH = h - 44;
      panels.append(this.panel(r, 0, plotW, h, { l: 58, r: 10, t: 6, b: 38 }, scaledOf(0), settings, t, empty, value, true, true, overlay, own, muted));
    } else {
      const per = b.columns || clamp(Math.floor(plotArea / 150), 1, list.length);
      const lines = Math.ceil(list.length / per);
      const cellW = Math.floor((plotArea - (per - 1) * 6) / per);
      const plotW = cellW - 12;
      const perLineH = Math.floor((availH - 10) / lines);
      const pH = clamp(Math.min(Math.round(plotW * 0.72), perLineH - 38), 70, 260);
      plotH = pH;
      panels.style.gridTemplateColumns = `repeat(${per}, ${cellW}px)`;
      list.forEach((r, k) => {
        const first = k % per === 0;
        const margin = { l: first ? 44 : 10, r: 4, t: 4, b: 18 };
        const w = margin.l + plotW - (first ? 34 : 0) + margin.r;
        const node = this.panel(r, k, w, pH + margin.t + margin.b, margin, scaledOf(k), settings, t, empty, value, first, false, overlay, own, muted);
        node.style.marginLeft = first ? '0' : '0';
        const title = document.createElement('div');
        title.className = 'dv-coverage-panel-title';
        title.style.paddingLeft = `${margin.l}px`;
        title.innerHTML = `<b>${esc(titleOf(r, list, b.title))}</b>${r.visited_pct !== null && r.visited_pct !== undefined ? ` · ${pct(r.visited_pct)}` : ''}`;
        node.prepend(title);
        panels.append(node);
      });
    }
    const row = document.createElement('div');
    row.className = 'dv-coverage-heatrow';
    row.append(panels, colorbar(scaledAll || scaledOf(0), (list.length > 1 && share ? '' : '') + VALUE_BAR[value], Math.max(80, plotH), settings.ramp));
    body.append(row);


  }

  panel(r, k, w, h, margin, scaled, settings, t, empty, value, yLabels, big, overlay, own, muted) {
    const node = document.createElement('div');
    node.className = 'dv-coverage-panel';
    const { canvas: c, g } = canvas(w, h, 'dv-coverage-heat');
    c.setAttribute('data-cov-heat', '');
    const box = { x: margin.l, y: margin.t, w: w - margin.l - margin.r, h: h - margin.t - margin.b };
    const key = muted ? null : gridKey(r);
    const answer = key ? Query.visited(key) : null;
    drawImage(g, heatImage(r.nx, r.ny, scaled.t, settings.ramp, empty, null, answer ? (idx) => !answer.has(idx) : null), box);
    const cw = box.w / r.nx; const ch = box.h / r.ny;
    const cellBox = (idx) => { const i = Math.floor(idx / r.ny); const j = idx % r.ny; return [box.x + i * cw, box.y + box.h - (j + 1) * ch]; };
    const mine = own && own[r.joint];
    if (mine) {
      g.save();
      g.fillStyle = t.accent; g.globalAlpha = 0.55;
      for (const idx of mine.cells || []) { const [x, y] = cellBox(idx); g.fillRect(x, y, cw, ch); }
      g.globalAlpha = 1; g.fillStyle = t.fg;
      for (const idx of mine.only || []) { const [x, y] = cellBox(idx); g.fillRect(x, y, cw, ch); }
      g.restore();
    }
    const x = { lo: r.x_lo * r.x_scale, hi: r.x_hi * r.x_scale };
    const y = { lo: r.y_lo * r.y_scale, hi: r.y_hi * r.y_scale };
    const sx = (v) => box.x + ((v - x.lo) / (x.hi - x.lo)) * box.w;
    const sy = (v) => box.y + box.h - ((v - y.lo) / (y.hi - y.lo)) * box.h;
    if (r.box === 'limit') {
      if (y.lo < 0 && y.hi > 0) hline(g, sy(0), box.x, box.x + box.w, t.muted, 1, [2, 3]);
      if (x.lo < 0 && x.hi > 0 && r.x !== 'q') vline(g, sx(0), box.y, box.y + box.h, t.muted, 1, [2, 3]);
      frame(g, box, t.limit, big ? 1.5 : 1.2);
    } else {
      frame(g, box, t.border, 1);
    }
    axes(g, t, box,
      { lo: x.lo, hi: x.hi, label: big ? `${r.x_label} (${r.x_unit})` : '', labels: true },
      { lo: y.lo, hi: y.hi, label: yLabels ? (big ? `${r.y_label} (${r.y_unit})` : `${r.y} (${r.y_unit})`) : '', labels: yLabels, offset: big ? 46 : 34 });
    const path = overlay && overlay[r.joint];
    if (path && Array.isArray(path[0])) {
      g.save();
      g.beginPath(); g.rect(box.x, box.y, box.w, box.h); g.clip();
      g.strokeStyle = t.accent; g.lineWidth = 1.6; g.lineJoin = 'round';
      g.beginPath();
      path[0].forEach((xv, n) => { const X = sx(xv * r.x_scale); const Y = sy(path[1][n] * r.y_scale); if (n === 0) g.moveTo(X, Y); else g.lineTo(X, Y); });
      g.stroke();
      g.fillStyle = t.accent;
      g.beginPath(); g.arc(sx(path[0][0] * r.x_scale), sy(path[1][0] * r.y_scale), 3, 0, Math.PI * 2); g.fill();
      g.restore();
    }
    for (const chip of key ? Query.on(key) : []) { const [x, y] = cellBox(chip.cell); cellFrame(g, x, y, cw, ch, t); }
    const nx = r.nx; const ny = r.ny;
    const dx = (r.x_hi - r.x_lo) / nx; const dy = (r.y_hi - r.y_lo) / ny;
    const cellAt = (px, py) => {
      const i = clamp(Math.floor(((px - box.x) / box.w) * nx), 0, nx - 1);
      const j = clamp(Math.floor(((box.y + box.h - py) / box.h) * ny), 0, ny - 1);
      return i * ny + j;
    };
    const find = (px, py) => {
      if (px < box.x || px > box.x + box.w || py < box.y || py > box.y + box.h) return null;
      const i = clamp(Math.floor(((px - box.x) / box.w) * nx), 0, nx - 1);
      const j = clamp(Math.floor(((box.y + box.h - py) / box.h) * ny), 0, ny - 1);
      const idx = i * ny + j;
      const xa = (r.x_lo + i * dx) * r.x_scale; const xb = (r.x_lo + (i + 1) * dx) * r.x_scale;
      const ya = (r.y_lo + j * dy) * r.y_scale; const yb = (r.y_lo + (j + 1) * dy) * r.y_scale;
      let html = `${esc(r.x)} ${withUnit(clean(xa), r.x_unit)} … ${withUnit(clean(xb), r.x_unit)}<br>${esc(r.y)} ${withUnit(clean(ya), r.y_unit)} … ${withUnit(clean(yb), r.y_unit)}<br><b>${count(r.samples[idx])}</b> sample${r.samples[idx] === 1 ? '' : 's'}`;
      if (Array.isArray(r.paths)) html += ` · <b>${count(r.paths[idx])}</b> trajector${r.paths[idx] === 1 ? 'y' : 'ies'}`;
      if (Array.isArray(r.max_other) && r.max_other[idx] !== null) html += `<br>${esc(r.other_label)} here ${withUnit(r.max_other[idx] * r.other_scale, r.other_unit)}`;
      if (key && Query.indexed(key)) html += askLine(key, idx, r.samples[idx] > 0);
      return html;
    };
    const wrap = wrapCanvas(c);
    if (key && Query.indexed(key)) {
      hitLayer(wrap, box, cw, ch, {
        id: key, tip: this.tip, find, label: `${r.joint_short || r.joint} ${r.x} × ${r.y}: click a cell to ask who made it`,
        click: (px, py) => { const idx = cellAt(px, py); askCell(this.el, r, idx, !(r.samples[idx] > 0)); },
      });
    } else {
      hover(c, this.tip, find);
    }
    node.append(wrap);
    return node;
  }

  selected() { /* a grid has no record marks to repaint; the dashboard's picks reach it as filtered rows */ }

  destroy() {
    this.ro.disconnect();
    Query.removeEventListener('change', this.onQuery);
  }
}
