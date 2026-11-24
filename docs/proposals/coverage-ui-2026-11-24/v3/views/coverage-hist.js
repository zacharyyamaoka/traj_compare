/* type: coverage-hist — binned 1-D histograms against their limits (PROPOSED-CONTRACT.md §52.2).
 *
 * Reads hist rows (one row = one histogram: lo, hi, bins, a list cell of counts, optional per-group counts, the limit
 * low/high with its source and kind, an optional planner limit, the data's p0.1/p99.9, span and peak %). Two layouts:
 *
 *   coverage:
 *     layout: multiples | ridgeline   multiples (default): one card per `card` value (default joint), one strip per row
 *                                     in it, on its own axis in display units; ridgeline: one line per card value,
 *                                     one column per signal, every axis put on its own limit (−100 % … +100 %)
 *     card: joint                     the property that makes a card / a ridgeline row
 *     columns: [q, qd, qdd]           ridgeline only: the signals, left to right
 *     pick: joint                     ridgeline only: a row click asks the host to open that value (a bubbling
 *                                     `data-coverage-pick` event; §52.5 maps it onto select: + a page link)
 *
 * Marks: bars (height on the dashboard's scale: linear clips at p98 and caps a clipped bar dark), stacked by group in
 * the group's family colour with an interactive legend (CONTRACT §31: click hides, double-click isolates, Reset), the
 * limit as a solid line in the limit colour, the planner's dashed, the beyond-the-limit band grey, p0.1 / p99.9 as dark
 * ticks. Hover reads the bin. STOCK PARTS: none (canvas 2D); the legend follows data-ui's legend.js rule.
 */
import {
  Color, esc, settingsOf, scaleTitle, tok, groupColour, fmt, pct, count, withUnit, clamp, canvas, font, axes, hline,
  vline, legend, readout, hover, rows as rowsOf, block, emptyHtml, room,
} from './kit.js';
import css from './coverage-css.js';

export { css };

export function options() {
  return [
    { type: 'dropdown', key: 'coverage.layout', displayName: 'Layout', options: { multiples: 'a card per joint', ridgeline: 'ridgeline (% of limit)' }, default: 'multiples' },
    { type: 'property', key: 'coverage.card', displayName: 'Card per', none: 'joint' },
  ];
}

const OUTSIDE = 'rgb(221, 220, 214)';

function stated(row) { return row.limit_source === 'limit' && row.low !== null && row.high !== null; }

/* heights 0..1 on the dashboard's scale; `clipped` marks a bar taller than the scale's top (linear clips at p98) */
function heights(counts, mode, enough) {
  const scaled = Color.scale(counts, mode, { enough });
  return { t: Array.from(scaled.t, (v) => (v < 0 ? 0 : v)), clipped: counts.map((v) => mode === 'linear' && v > scaled.max) };
}

export default class CoverageHistView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.classList.add('dv-coverage');
    this.tip = readout(el);
    this.hidden = new Set();
    this.width = 0;
    this.ro = new ResizeObserver(() => {
      const w = Math.floor(el.clientWidth);
      if (this.input && w > 0 && Math.abs(w - this.width) > 2) this.draw();
    });
    this.ro.observe(el);
  }

  update(input) {
    this.input = input;
    // CONTRACT §31: the host's hidden set when it changed since the host last said (Back / Forward, a link)
    const given = input.hiddenSeries ? [...input.hiddenSeries].sort().join('\n') : null;
    if (given !== null && given !== this.lastGiven) { this.hidden = new Set(input.hiddenSeries); this.lastGiven = given; }
    this.draw();
  }

  setHidden(next) {
    this.hidden = next;
    if (typeof this.host.setHiddenSeries === 'function') this.host.setHiddenSeries([...next]);
    this.lastGiven = [...next].sort().join('\n');
    this.draw();
  }

  draw() {
    const el = this.el;
    const width = Math.floor(el.clientWidth);
    this.width = width;
    if (!width || !this.input) return;
    for (const node of [...el.children]) if (!node.classList.contains('dv-coverage-tip')) node.remove();
    const list = rowsOf(this.input);
    if (!list.length) { el.insertAdjacentHTML('afterbegin', emptyHtml('No histogram matches this view.')); return; }
    const b = block(this.input);
    if (b.layout === 'ridgeline') this.ridgeline(list, b, width); else this.multiples(list, b, width);
  }

  groupsOf(list) {
    const first = list.find((r) => Array.isArray(r.groups) && r.groups.length);
    return first ? first.groups : [];
  }

  /* counts of the shown groups (a hidden group leaves the drawing only; CONTRACT §31's "truthful") */
  shownCounts(row, groups) {
    if (!groups.length || !this.hidden.size || !Array.isArray(row.group_counts) || !row.group_counts.length) return row.counts;
    return row.counts.map((_, i) => groups.reduce((n, g, k) => n + (this.hidden.has(g) ? 0 : (row.group_counts[k][i] || 0)), 0));
  }

  multiples(list, b, width) {
    const input = this.input;
    const t = tok(input);
    const settings = settingsOf(input);
    const enough = 10;
    const cardKey = b.card || 'joint';
    const groups = this.groupsOf(list);
    const order = [];
    const byCard = new Map();
    for (const r of list) {
      const key = r[cardKey] === null || r[cardKey] === undefined ? r.id : r[cardKey];
      if (!byCard.has(key)) { byCard.set(key, []); order.push(key); }
      byCard.get(key).push(r);
    }
    const perLine = Math.max(1, Math.min(order.length, b.columnsPerLine || Math.floor((width + 14) / (380 + 14))));
    const cardW = Math.floor((width - 14 * (perLine - 1)) / perLine);
    const grid = document.createElement('div');
    grid.className = 'dv-coverage-hist-grid';
    grid.style.gridTemplateColumns = `repeat(${perLine}, minmax(0, 1fr))`;
    const availH = room(this.el, 0) ? room(this.el, 0) - 44 : 0;
    const lines = Math.ceil(order.length / perLine);
    const maxStrips = Math.max(...order.map((k) => byCard.get(k).length));
    const rowH = availH ? clamp(Math.floor((availH / lines - 36) / maxStrips), 40, maxStrips === 1 ? 130 : 64) : 58;
    let anyPlanner = false; let anyBeyond = false; let anyCap = false; let anyLimit = false; let anyTicks = false;
    for (const key of order) {
      const strips = byCard.get(key);
      const card = document.createElement('div');
      card.className = 'dv-coverage-card';
      const r0 = strips[0];
      const kind = r0.family === 'joint' ? 'revolute · degrees' : '';
      card.innerHTML = `<div class="dv-coverage-card-head"><b>${esc(String(key))}</b>${kind ? `<span>${esc(kind)}</span>` : ''}</div>`;
      const innerW = cardW - 18;
      const labelW = 66; const noteW = 82;
      const { canvas: c, g } = canvas(innerW, rowH * strips.length + 2, 'dv-coverage-heat');
      c.setAttribute('data-cov-heat', '');
      const hit = [];
      strips.forEach((row, k) => {
        const box = { x: labelW, y: k * rowH + 4, w: innerW - labelW - noteW, h: rowH - 26 };
        const sc = row.scale || 1;
        const x = { lo: row.lo * sc, hi: row.hi * sc };
        const sx = (v) => box.x + ((v - x.lo) / (x.hi - x.lo)) * box.w;
        const base = box.y + box.h;
        if (stated(row)) {
          anyLimit = true;
          g.fillStyle = OUTSIDE;
          g.fillRect(box.x, box.y, Math.max(0, sx(row.low * sc) - box.x), box.h);
          g.fillRect(sx(row.high * sc), box.y, Math.max(0, box.x + box.w - sx(row.high * sc)), box.h);
        }
        const counts = this.shownCounts(row, groups);
        const bars = heights(counts, settings.scale, enough);
        if (bars.clipped.some(Boolean)) anyCap = true;
        const step = (row.hi - row.lo) / row.bins;
        const at = (i) => (row.lo + i * step) * sc;
        for (let i = 0; i < row.bins; i++) {
          const hgt = bars.t[i];
          if (!(hgt > 0)) continue;
          const x0 = sx(at(i)); const x1 = sx(at(i + 1));
          const w = Math.max(0.8, x1 - x0 + 0.25);
          const total = hgt * (box.h - 2);
          if (!groups.length || !row.group_counts || !row.group_counts.length) {
            g.fillStyle = t.series[0] || t.accent;
            g.fillRect(x0, base - total, w, total);
            continue;
          }
          let y = base;
          groups.forEach((name, gi) => {
            if (this.hidden.has(name)) return;
            const share = counts[i] > 0 ? (row.group_counts[gi][i] || 0) / counts[i] : 0;
            if (!(share > 0)) return;
            g.fillStyle = groupColour(input, name, gi);
            g.fillRect(x0, y - total * share, w, total * share);
            y -= total * share;
          });
        }
        g.fillStyle = t.fg;
        for (let i = 0; i < row.bins; i++) {
          if (!bars.clipped[i]) continue;
          g.fillRect(sx(at(i)) - 1, base - (box.h - 2) * bars.t[i] - 1, Math.max(2.5, sx(at(i + 1)) - sx(at(i)) + 2), 2.5);
        }
        hline(g, base, box.x, box.x + box.w, t.border);
        if (stated(row)) {
          vline(g, sx(row.low * sc), box.y - 2, base, t.limit, 1.4);
          vline(g, sx(row.high * sc), box.y - 2, base, t.limit, 1.4);
        }
        if (row.planner_low !== null && row.planner_low !== undefined) {
          anyPlanner = true;
          vline(g, sx(row.planner_low * sc), box.y - 2, base, t.limit, 1.2, [4, 3]);
          vline(g, sx(row.planner_high * sc), box.y - 2, base, t.limit, 1.2, [4, 3]);
        }
        for (const v of [row.p001, row.p999]) if (Number.isFinite(v)) { anyTicks = true; vline(g, sx(v * sc), box.y + 2, base + 3, t.fg, 1.2); }
        axes(g, t, box, { lo: x.lo, hi: x.hi }, { show: false });
        g.textAlign = 'left'; g.textBaseline = 'alphabetic';
        g.font = font(t, 11.5, 600); g.fillStyle = t.fg;
        g.fillText(row.signal, 0, box.y + 12);
        g.font = font(t, 10.5); g.fillStyle = t.muted;
        g.fillText(row.signal_word, 0, box.y + 24);
        g.fillText(row.unit, 0, box.y + 36);
        const noteX = box.x + box.w + 8;
        if (row.family === 'joint' && !stated(row)) g.fillText('no limit stated', noteX, box.y + 12);
        else if (row.family === 'joint') {
          g.fillStyle = t.fg;
          g.fillText(row.signal === 'q' ? `${pct(row.span_pct)} of range` : `peak ${pct(row.peak_pct)}`, noteX, box.y + 12);
          if (row.outside > 0) { anyBeyond = true; g.fillStyle = t.limit; g.fillText(`${count(row.outside)} beyond`, noteX, box.y + 25); }
        }
        hit.push({ box, row, sc, step, counts });
      });
      hover(c, this.tip, (px, py) => {
        const h = hit.find((item) => py >= item.box.y - 4 && py <= item.box.y + item.box.h + 18);
        if (!h || px < h.box.x || px > h.box.x + h.box.w) return null;
        const r = h.row;
        const i = clamp(Math.floor(((px - h.box.x) / h.box.w) * r.bins), 0, r.bins - 1);
        let html = `<b>${esc(r.label)}</b> ${withUnit((r.lo + i * h.step) * h.sc, r.unit)} … ${withUnit((r.lo + (i + 1) * h.step) * h.sc, r.unit)}<br>${count(r.counts[i])} samples`;
        if (groups.length && r.group_counts && r.group_counts.length) groups.forEach((name, gi) => { html += `<br>${esc(name)}: ${count(r.group_counts[gi][i])}${this.hidden.has(name) ? ' (hidden)' : ''}`; });
        return html;
      });
      card.append(c);
      grid.append(card);
    }
    this.el.prepend(grid);
    const items = [];
    if (groups.length) {
      groups.forEach((name, gi) => items.push({ kind: 'fill', colour: groupColour(input, name, gi), label: `split = ${name}`, button: true, series: name, pressed: !this.hidden.has(name) }));
    } else items.push({ kind: 'fill', colour: t.series[0] || t.accent, label: 'samples' });
    items.push({ kind: 'text', label: `bar height: ${scaleTitle(settings.scale, enough)}${groups.length ? ', stacked by split' : ''}` });
    if (anyLimit) items.push({ kind: 'line', colour: t.limit, label: 'the limit' });
    if (anyPlanner) items.push({ kind: 'dash', colour: t.limit, label: "the planner's limit" });
    if (anyLimit) items.push({ kind: 'outside', label: 'beyond the limit' });
    if (anyTicks) items.push({ kind: 'tick', colour: t.fg, label: 'p0.1 / p99.9 of the data' });
    if (anyCap) items.push({ kind: 'line', colour: t.fg, label: 'dark cap = a bar taller than the scale top (linear clips at p98)' });
    if (anyBeyond) items.push({ kind: 'text', label: 'red count = samples past the limit', problem: true });
    const lg = legend(items, settings.ramp);
    this.wireLegend(lg, groups);
    this.el.append(lg);
  }

  wireLegend(lg, groups) {
    if (!groups.length) return;
    let clickTimer = 0;
    lg.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-series]');
      if (btn) {
        if (e.altKey) { this.isolate(btn.dataset.series, groups); return; }
        clearTimeout(clickTimer);
        // WHY a short wait: a double-click's two clicks must not leave a toggle behind (CONTRACT §31)
        clickTimer = setTimeout(() => {
          const next = new Set(this.hidden);
          if (next.has(btn.dataset.series)) next.delete(btn.dataset.series); else next.add(btn.dataset.series);
          if (next.size >= groups.length) return;
          this.setHidden(next);
        }, 220);
        return;
      }
      if (e.target.closest('[data-reset]')) this.setHidden(new Set());
    });
    lg.addEventListener('dblclick', (e) => {
      const btn = e.target.closest('button[data-series]');
      if (!btn) return;
      clearTimeout(clickTimer);
      this.isolate(btn.dataset.series, groups);
    });
    if (this.hidden.size) lg.insertAdjacentHTML('beforeend', '<button type="button" class="dv-coverage-li" data-reset>Reset</button>');
  }

  isolate(name, groups) {
    const only = groups.filter((g) => g !== name);
    const isOnly = this.hidden.size === only.length && only.every((g) => this.hidden.has(g));
    this.setHidden(isOnly ? new Set() : new Set(only));
  }

  ridgeline(list, b, width) {
    const input = this.input;
    const t = tok(input);
    const settings = settingsOf(input);
    const cardKey = b.card || 'joint';
    const signals = b.columns || ['q', 'qd', 'qdd'];
    const names = [];
    const by = new Map();
    for (const r of list) {
      if (!signals.includes(r.signal) || r[cardKey] === null || r[cardKey] === undefined) continue;
      if (!by.has(r[cardKey])) { by.set(r[cardKey], {}); names.push(r[cardKey]); }
      by.get(r[cardKey])[r.signal] = r;
    }
    const availH = room(this.el, 0) ? room(this.el, 0) - 52 : 0;
    const rowH = availH ? clamp(Math.floor((availH - 24) / names.length), 26, 44) : 36;
    const labelW = clamp(Math.round(width * 0.14), 92, 150);
    const gap = 26;
    const top = 20;
    const colW = Math.floor((width - labelW - gap * signals.length) / signals.length);
    const height = top + rowH * names.length + 22;
    const { canvas: c, g } = canvas(width, height, 'dv-coverage-heat');
    c.setAttribute('data-cov-heat', '');
    const titles = { q: 'q · position in its range', qd: 'qd · speed against its limit', qdd: 'qdd · acceleration against its limit', qddd: 'qddd · jerk against its limit' };
    g.font = font(t, 11.5, 600); g.fillStyle = t.fg; g.textAlign = 'center'; g.textBaseline = 'alphabetic';
    signals.forEach((s, ci) => g.fillText(titles[s] || s, labelW + ci * (colW + gap) + colW / 2, 13));
    const hits = [];
    names.forEach((name, ri) => {
      const y0 = top + ri * rowH;
      if (ri % 2 === 1) { g.fillStyle = t.subtle; g.fillRect(0, y0, width, rowH); }
      g.font = font(t, 11.5); g.fillStyle = t.fg; g.textAlign = 'right'; g.textBaseline = 'middle';
      g.fillText(String(by.get(name)[signals[0]] ? by.get(name)[signals[0]].joint_short || name : name), labelW - 12, y0 + rowH / 2);
      signals.forEach((s, ci) => {
        const row = by.get(name)[s];
        const x0 = labelW + ci * (colW + gap);
        if (!row) return;
        // the axis: −100 % (low limit) … +100 % (high limit); the histogram's edges reach ±8 % past it
        const lo = row.low; const hi = row.high;
        const toPct = (v) => (2 * (v - lo) / (hi - lo) - 1) * 100;
        const P = 108;
        const px = (p) => x0 + ((p + P) / (2 * P)) * colW;
        const base = y0 + rowH - 7;
        const hBox = rowH - 10;
        const counts = row.counts;
        const bars = heights(counts, settings.scale, 10);
        const step = (row.hi - row.lo) / row.bins;
        g.fillStyle = t.series[0] || t.accent;
        for (let i = 0; i < row.bins; i++) {
          if (!(bars.t[i] > 0)) continue;
          const a = px(toPct(row.lo + i * step)); const bb = px(toPct(row.lo + (i + 1) * step));
          g.fillRect(a, base - bars.t[i] * hBox, Math.max(0.8, bb - a + 0.2), bars.t[i] * hBox);
        }
        vline(g, px(-100), y0 + 3, base, t.limit, 1.2);
        vline(g, px(100), y0 + 3, base, t.limit, 1.2);
        if (Number.isFinite(row.p001) && Number.isFinite(row.p999)) {
          const a = px(toPct(row.p001)); const bb = px(toPct(row.p999));
          hline(g, base + 2, a, bb, t.fg, 1);
          vline(g, a, base - 1, base + 4, t.fg, 1); vline(g, bb, base - 1, base + 4, t.fg, 1);
        }
        hits.push({ x0, y0, w: colW, h: rowH, row, px, toPct, step });
      });
    });
    g.font = font(t, 10); g.fillStyle = t.muted; g.textBaseline = 'top';
    signals.forEach((s, ci) => {
      const x0 = labelW + ci * (colW + gap);
      const px = (p) => x0 + ((p + 108) / 216) * colW;
      // WHY the ends point inward: the next column's −100 % sits one gap away, so centred end labels collide
      for (const [p, align] of [[-100, 'left'], [-50, 'center'], [0, 'center'], [50, 'center'], [100, 'right']]) {
        g.textAlign = align;
        g.fillText(`${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p)}${Math.abs(p) === 100 ? ' %' : ''}`, px(p) + (align === 'left' ? -3 : align === 'right' ? 3 : 0), top + rowH * names.length + 5);
      }
    });
    hover(c, this.tip, (mx, my) => {
      const h = hits.find((it) => mx >= it.x0 && mx <= it.x0 + it.w && my >= it.y0 && my <= it.y0 + it.h);
      if (!h) return null;
      const r = h.row;
      const p = ((mx - h.x0) / h.w) * 216 - 108;
      const v = r.low + ((p / 100 + 1) / 2) * (r.high - r.low);
      const i = clamp(Math.floor((v - r.lo) / h.step), 0, r.bins - 1);
      return `<b>${esc(r.joint)} · ${esc(r.signal)}</b> ${r.signal === 'q' ? `${pct(r.span_pct)} of its range used` : `peak ${pct(r.peak_pct)} of its limit`}<br>${withUnit((r.lo + i * h.step) * r.scale, r.unit)} … ${withUnit((r.lo + (i + 1) * h.step) * r.scale, r.unit)}: ${count(r.counts[i])} samples<br><span style="opacity:.75">click: open this joint</span>`;
    });
    if (b.pick) {
      c.style.cursor = 'pointer';
      c.addEventListener('click', (e) => {
        const r = c.getBoundingClientRect();
        const my = e.clientY - r.top;
        const ri = Math.floor((my - top) / rowH);
        if (ri < 0 || ri >= names.length) return;
        this.el.dispatchEvent(new CustomEvent('data-coverage-pick', { bubbles: true, detail: { property: b.pick, value: names[ri] } }));
      });
    }
    this.el.prepend(c);
    this.el.append(legend([
      { kind: 'fill', colour: t.series[0] || t.accent, label: `samples (bar height: ${scaleTitle(settings.scale, 10)})` },
      { kind: 'line', colour: t.limit, label: 'the limit: −100 % low, +100 % high' },
      { kind: 'tick', colour: t.fg, label: 'black hairline = where the data went (p0.1 … p99.9)' },
    ], settings.ramp));
  }

  selected() {}

  destroy() { this.ro.disconnect(); }
}
