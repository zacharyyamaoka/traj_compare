/* The Overview round's host views (CONTRACT §1 of data-ui: registerView). Each is a stock view plugin: the workbench hands
   it the scope's kept runs through the stock pipeline (update(input)), it draws inside its own element only, and it opens
   records through host.open (the stock records peek, whose drill actions reach the target view). What each draws is what
   no stock view can (NOTES.md names the exact data-ui ask per view); every number comes from model.js.

   Types: tc-league (O1; O3's League page) · tc-matrix (O2; O3's Model × dataset page) · tc-sweep (O4; O3's Speed page) ·
   tc-tradeoff (O5; O3's Trade-off page) · tc-tile, tc-worst (O3). Every view's numbers are on its element as
   `el.tcOverview` for the round's check (read-only). */
import { buildModel, FIELDS, RULE, MODEL_TYPE_NOTE, num3, times, speedText, datasetShort, median } from './model.js';
import { CSS } from './views-css.js';

// ── small helpers ──
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private window */ } },
};
const VARIANT = (location.pathname.split('/').filter(Boolean)[0] || 'x');
const swatch = (c) => `<i class="tc-sw" style="--c:${c ? c.color : '#999'}"></i>`;
/** A name whole, or middle-ellipsed with the whole name on hover. WHY the middle (Zach's truthful-rendering rule): BAM FB's
    configs share a long prefix and differ at the end, so a clipped tail would hide the only difference. */
function nameHtml(name, max = 34, cls = 'tc-name') {
  const s = String(name);
  if (s.length <= max) return `<span class="${cls}">${esc(s)}</span>`;
  const head = Math.max(6, Math.floor((max - 1) * 0.45)), tail = max - 1 - head;
  return `<span class="${cls}" title="${esc(s)}">${esc(s.slice(0, head))}…${esc(s.slice(s.length - tail))}</span>`;
}
const DEP_SHORT = { 'UR5e + Conveyor PnP cell': 'UR5e cell', UR5e: 'UR5e alone', 'BAM FB': 'BAM FB', '1-DOF pendulum': 'pendulum' };
const depText = (c) => [...c.deployments].map((d) => DEP_SHORT[d] || d).join(', ');
const depHtml = (c) => `<span class="tc-dep" title="${esc([...c.deployments].join(', '))}">${esc(depText(c))}</span>`;
/** Labels pushed apart: each, in height order, moves down until no placed label overlaps it (a box of ~6 px a character). */
function placeLabels(labels, { gap = 11, top = 0, bottom = Infinity } = {}) {
  labels.sort((a, b) => a.y - b.y);
  const placed = [];
  const w = (l) => 6 * l.text.length;
  for (const l of labels) {
    let moved = true;
    while (moved) {
      moved = false;
      for (const p of placed) {
        // WHY the 0.01 px slack: (y + gap) − y can round below gap, which looped forever (measured: O4 never drew)
        if (Math.abs(p.y - l.y) < gap - 0.01 && l.x < p.x + w(p) && p.x < l.x + w(l)) { l.y = p.y + gap; moved = true; }
      }
    }
    placed.push(l);
  }
  const over = placed.length ? Math.max(...placed.map((l) => l.y)) - bottom : 0;
  if (over > 0) for (const l of placed) l.y = Math.max(top, l.y - over);
  return placed;
}
const unitOf = (f) => FIELDS[f].unit;
const logT = (v, lo, hi) => (hi > lo ? (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) : 0.5);
const linT = (v, lo, hi) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);

// Nov 23's log ramp for the matrices (light → dark; colour is the data, never a verdict)
const RAMP = ['#f3f6fb', '#d7e5f5', '#b3cdea', '#86afdb', '#5a8fca', '#3a70b3', '#285594', '#1c3d70', '#13284b'];
function rampColor(t) {
  t = Math.max(0, Math.min(1, t));
  const at = t * (RAMP.length - 1), lo = Math.floor(at), hi = Math.min(RAMP.length - 1, lo + 1), f = at - lo;
  const hex = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  const a = hex(RAMP[lo]), b = hex(RAMP[hi]);
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(',')})`;
}
function heatCell(v, lo, hi, extra = '') {
  const t = 0.05 + 0.8 * logT(v, lo, hi);
  return `style="background:${rampColor(t)};color:${t > 0.55 ? '#fff' : '#22211f'}" ${extra}`;
}
function rampLegend(lo, hi, unit) {
  const stops = RAMP.map((c, i) => `${c} ${(100 * i) / (RAMP.length - 1)}%`).join(',');
  return `<span class="tc-ramp"><span>${num3(lo)}</span><i style="background:linear-gradient(90deg,${stops})"></i><span>${num3(hi)} ${esc(unit)}</span><span class="tc-mut">log</span></span>`;
}
function sparkline(values, { lo, hi, log, color, title, w = 76, h = 24 }) {
  const pad = 3;
  const y = (v) => (h - pad) - (log ? logT(Math.max(v, lo), lo, hi) : linT(v, lo, hi)) * (h - 2 * pad);
  const x = (i) => pad + (i * (w - 2 * pad)) / Math.max(1, values.length - 1);
  const pts = [];
  values.forEach((v, i) => { if (v !== null && v !== undefined && (!log || v > 0)) pts.push([x(i), y(v)]); });
  const t = `<title>${esc(title || '')}</title>`;
  if (!pts.length) return `<svg class="tc-spark" width="${w}" height="${h}">${t}</svg>`;
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join('');
  const last = pts[pts.length - 1];
  return `<svg class="tc-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${t}<line x1="0" x2="${w}" y1="${h - 1}" y2="${h - 1}" class="tc-axis"/>` +
    `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.6"/><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.4" fill="${color}"/></svg>`;
}
const extent = (vals, positive) => {
  const v = vals.filter((x) => x !== null && x !== undefined && Number.isFinite(x) && (!positive || x > 0));
  return v.length ? { lo: Math.min(...v), hi: Math.max(...v) } : { lo: positive ? 0.001 : 0, hi: 1 };
};
/** The target view of one target (V2's link: the runs the rail kept for it checked, back = this page). */
function targetHref(t) {
  const q = new URLSearchParams({ site: t.site, target: t.slug, keep: t.lines.join(','), back: location.href });
  if (new URLSearchParams(location.search).get('dry') === '1') q.set('dry', '1');
  return `/common/target.html?${q.toString().replace(/%2C/g, ',')}`;
}
/** The run of a target nearest its median (Nov 23's drill shows that one). */
function nearestRun(item, field = 'tcp') {
  const runs = item.t.runs.filter((r) => r.config === item.config && Number.isFinite(r[field]));
  return runs.reduce((a, b) => (Math.abs(b[field] - item.v) < Math.abs(a[field] - item.v) ? b : a), runs[0]);
}
function topText(m) {
  return m.top === null ? '—' : `${speedText(m.top)}${m.speeds.length > 1 && m.top < Math.max(...m.speeds) ? ' (the fastest speed left)' : ''}`;
}
const depNote = (m) => (m.deployments.length > 1
  ? ` · <span class="tc-warn-t" title="A config on one robot ranked against one on another is not a like-for-like comparison; tick one deployment in the rail to compare like with like.">${m.deployments.length} deployments in the filter</span>`
  : '');

// ── the base of every host view ──
class Base {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.draws = 0;
    el.classList.add('tc-host');
    this._click = (e) => this.onClick(e);
    this._change = (e) => this.onChange(e);
    el.addEventListener('click', this._click);
    el.addEventListener('change', this._change);
  }
  key(k) { return `tc-overview/${VARIANT}/${this.input && this.input.view ? this.input.view.name : 'view'}/${k}`; }
  update(input) {
    this.input = input;
    this.tc = (input.view && input.view.tc) || {};
    this.m = buildModel(input.rows || [], this.tc.configOrder || []);
    this.draw();
  }
  draw() {
    this.render();
    this.el.tcOverview = this.hook();
    this.draws += 1;
    this.el.dataset.tcView = this.constructor.type;
    this.el.dataset.tcDraws = String(this.draws);
  }
  onClick() {}
  onChange() {}
  hook() { return {}; }
  destroy() { this.el.removeEventListener('click', this._click); this.el.removeEventListener('change', this._change); }
  /** A config's worst targets under `where`, each linking V2's target view (the runs the rail keeps checked, back = here).
      WHY not the stock records peek: it lists records but a row in it opens nothing, so it never reached a target view
      (NOTES.md gap). Toggled: the same config and place again closes it. */
  openWorst(config, where) {
    const same = this.drill && this.drill.config === config && JSON.stringify(this.drill.where) === JSON.stringify(where);
    this.drill = same ? null : { config, where };
    this.draw();
    const card = this.el.querySelector('[data-tc-drill]');
    if (card && card.scrollIntoView) card.scrollIntoView({ block: 'nearest' });
  }
  drillHtml(limit = 10) {
    if (!this.drill) return '';
    const { config, where } = this.drill;
    const cell = this.m.value('tcp', 'config', config, where);
    if (!cell) { this.drill = null; return ''; }
    const c = this.m.configOf.get(config);
    const items = cell.items.slice().sort((a, b) => b.v - a.v).slice(0, limit);
    this.drillRows = items.map((i) => [i.t.key, i.v]);
    const place = [where.speed !== undefined ? `at ${speedText(where.speed)}` : 'over every speed', where.facet ? `on ${where.facet}` : '',
      where.dataset ? `on ${where.dataset}` : '', where.split ? `on ${where.split}` : '', where.deployment ? `in ${where.deployment}` : ''].filter(Boolean).join(' ');
    return `<div class="tc-drill" data-tc-drill><div class="tc-drill-h">${swatch(c)}<b>${esc(config)}</b>: its ${items.length} worst of ${cell.n} targets ${esc(place)} <span class="tc-mut">· median ${num3(cell.v)} mm · a target’s value = the median over its runs</span><span class="tc-sp"></span><button type="button" class="tc-link" data-tc-close>✕ close</button></div>` +
      `<table class="tc-stable"><thead><tr><th class="tc-l">#</th><th class="tc-l">target</th><th class="tc-l">dataset · split</th><th>speed</th><th>tool RMS<span class="tc-u">mm</span></th><th>× its median</th><th>runs</th><th></th></tr></thead><tbody>${items.map((i, k) =>
        `<tr><td class="tc-l tc-rank">${k + 1}</td><td class="tc-l" title="${esc(i.t.target)}">${esc(i.t.task)}</td><td class="tc-l tc-mut">${esc(datasetShort(i.t.dataset))} · ${esc(i.t.split)}</td><td>${speedText(i.t.speed)}</td><td>${num3(i.v)}</td><td>${times(i.v / cell.v)}</td><td>${i.runs.length}</td><td><a class="tc-link" data-tc-target href="${esc(targetHref(i.t))}">Open target view ↗</a></td></tr>`).join('')}</tbody></table></div>`;
  }
  closeDrill(e) {
    if (!e.target.closest('[data-tc-close]')) return false;
    this.drill = null; this.draw(); return true;
  }
}

// ═══ tc-league: Nov 23's answer, League table and dataset · split matrix (O1) ═══
class LeagueView extends Base {
  static type = 'tc-league';
  onClick(e) {
    if (this.closeDrill(e)) return;
    const f = e.target.closest('[data-tc-facet]');
    if (f) { this.facet = f.dataset.tcFacet; store.set(this.key('facet'), this.facet); this.draw(); return; }
    const w = e.target.closest('[data-tc-worst]');
    if (w) { e.preventDefault(); this.openWorst(w.dataset.tcWorst, this.where()); return; }
    const row = e.target.closest('tr[data-tc-config]');
    if (row && !e.target.closest('a,button,select,[data-tc-drill]')) this.openWorst(row.dataset.tcConfig, this.where());
  }
  onChange(e) {
    if (e.target.matches('select[data-tc-facet-select]')) { this.facet = e.target.value; store.set(this.key('facet'), this.facet); this.draw(); }
  }
  where() { return { speed: this.m.top, facet: this.facet === 'all' ? undefined : this.facet }; }
  render() {
    const m = this.m, tc = this.tc;
    const facets = m.columns('facet').sort((a, b) => m.depOrder(a.split(' · ').slice(-2, -1)[0]) - m.depOrder(b.split(' · ').slice(-2, -1)[0]) || (a < b ? -1 : 1));
    if (this.facet === undefined) this.facet = store.get(this.key('facet'), 'all');
    if (this.facet !== 'all' && !facets.includes(this.facet)) this.facet = 'all';
    const where = this.where();
    const L = m.league('tcp', where);
    this.L = L;
    if (this.drill && JSON.stringify(this.drill.where) !== JSON.stringify(where)) this.drill = null;
    let html = '';
    if (!L.length) { this.el.innerHTML = '<div class="tc tc-league"><p class="tc-answer">No run left has a tool tracking RMS: widen the filter.</p></div>'; return; }
    const best = L[0];
    if (tc.answer !== false) html += `<p class="tc-answer" data-tc-answer>${leagueSentence(m, L, this.facet)}</p>`;
    // the dataset · split facet: chips when they fit one line or two, else one select
    if (facets.length > 1) {
      const label = 'Dataset · split';
      if (facets.length <= 14) {
        html += `<div class="tc-chips"><span class="tc-k">${label}</span>${['all', ...facets].map((f) =>
          `<button type="button" data-tc-facet="${esc(f)}" aria-pressed="${f === this.facet}" title="${esc(f)}">${esc(f === 'all' ? 'all' : datasetShort(f.slice(0, f.lastIndexOf(' · '))) + ' · ' + f.slice(f.lastIndexOf(' · ') + 3))}</button>`).join('')}</div>`;
      } else {
        html += `<div class="tc-chips"><span class="tc-k">${label}</span><select data-tc-facet-select aria-label="${label}"><option value="all"${this.facet === 'all' ? ' selected' : ''}>all ${facets.length}</option>${facets.map((f) =>
          `<option value="${esc(f)}"${f === this.facet ? ' selected' : ''}>${esc(f)}</option>`).join('')}</select><span class="tc-mut">or click a column of the matrix below</span></div>`;
      }
    }
    // the League table
    const kpis = ['tcp', 'energy', 'jerk', 'stop'];
    const fw = (s) => ({ ...where, speed: s });
    const scale = {};
    for (const k of kpis) {
      const vals = [];
      for (const r of L) for (const s of m.speeds) { const c = m.value(k, 'config', r.name, fw(s)); if (c) vals.push(c.v); }
      scale[k] = extent(vals, FIELDS[k].log);
    }
    const wins = m.wins();
    this.winsOut = wins;
    const spark = m.speeds.length > 1;
    const sp = `${m.speeds.map(speedText).join(' → ')}`;
    html += `<div class="tc-scroll"><table class="tc-ltable" data-tc-league><thead><tr><th class="tc-l">#</th><th class="tc-l">config<span class="tc-u">its deployment · a row: its worst targets</span></th>` +
      `<th>n<span class="tc-u">targets</span></th><th class="tc-l tc-prim">tool tracking RMS at ${esc(speedText(m.top))}<span class="tc-u">mm · ×best · bar log</span></th>` +
      (spark ? `<th title="${esc(sp)}">vs speed<span class="tc-u">log · ${esc(speedText(m.speeds[0]))} → ${esc(speedText(m.top))}</span></th>` : '') +
      kpis.slice(1).map((k) => `<th>${esc(FIELDS[k].label)}<span class="tc-u">${esc(unitOf(k))} at ${esc(speedText(m.top))}${spark ? ' · vs speed' : ''}</span></th>`).join('') +
      (wins.cells ? `<th title="the (dataset · split, speed) cells with two or more configs where this config has the lowest tool RMS">best in<span class="tc-u">of its cells</span></th>` : '') +
      '<th></th></tr></thead><tbody>';
    const lo = Math.log10(scale.tcp.lo), hi = Math.log10(scale.tcp.hi);
    const kpiRows = {};
    L.forEach((r, at) => {
      const c = r.config;
      const frac = hi > lo ? (Math.log10(r.v) - lo) / (hi - lo) : 0.5;
      const sparkOf = (k) => {
        const values = m.speeds.map((s) => { const x = m.value(k, 'config', r.name, fw(s)); return x ? x.v : null; });
        return sparkline(values, { ...scale[k], log: FIELDS[k].log, color: c.color, w: 56,
          title: `${r.name}: ${FIELDS[k].label} vs speed (${m.speeds.map((s, i) => `${speedText(s)} → ${num3(values[i])}`).join(', ')})` });
      };
      const w = wins.byConfig.get(r.name);
      html += `<tr data-tc-config="${esc(r.name)}" data-rank="${at + 1}"><td class="tc-l tc-rank">${at + 1}</td>` +
        `<td class="tc-l tc-cfg">${swatch(c)}${nameHtml(r.name, 32)}${depHtml(c)}</td><td>${r.n}</td>` +
        `<td class="tc-l tc-prim"><span class="tc-big">${num3(r.v)}</span><span class="tc-x${at === 0 ? ' tc-best' : ''}">${at === 0 ? 'best' : times(r.v / best.v)}</span>` +
        `<span class="tc-bar" style="--c:${c.color}"><i style="width:${Math.max(3, 100 * Math.max(0, Math.min(1, frac))).toFixed(1)}%"></i></span></td>` +
        (spark ? `<td>${sparkOf('tcp')}</td>` : '');
      kpiRows[r.name] = {};
      for (const k of kpis.slice(1)) {
        const x = m.value(k, 'config', r.name, where);
        kpiRows[r.name][k] = x ? x.v : null;
        html += `<td><div class="tc-kcell">${x ? `<span>${num3(x.v)}</span>` : '<span class="tc-mut" title="no run of this config has it here">—</span>'}${spark ? sparkOf(k) : ''}</div></td>`;
      }
      html += (wins.cells ? `<td>${w && w.of ? `<b>${w.wins}</b> <span class="tc-mut">of ${w.of}</span>` : '<span class="tc-mut">—</span>'}</td>` : '') +
        `<td><button type="button" class="tc-link" data-tc-worst="${esc(r.name)}" aria-expanded="${!!(this.drill && this.drill.config === r.name)}">worst targets ${this.drill && this.drill.config === r.name ? '↑' : '→'}</button></td></tr>`;
      if (this.drill && this.drill.config === r.name) html += `<tr class="tc-drillrow"><td colspan="${5 + (spark ? 1 : 0) + 3 + (wins.cells ? 1 : 0) + 1}">${this.drillHtml()}</td></tr>`;
    });
    this.kpiRows = kpiRows;
    html += '</tbody></table></div>';
    html += `<p class="tc-foot">Each value: the ${RULE}, from the run tags tool tracking RMS, energy per task, tool jerk RMS and stop error (max); n = targets of that config at ${esc(speedText(m.top))}${this.facet !== 'all' ? ' on ' + esc(this.facet) : ''}. “best in” counts the (dataset · split, speed) cells with two or more configs where it has the lowest tool tracking RMS. Colour = config.</p>`;
    if (tc.matrix !== false) html += this.matrixHtml(facets);
    this.el.innerHTML = `<div class="tc tc-league">${html}</div>`;
  }
  // Nov 23's "Every dataset · split at 1": a config × dataset · split heatmap, best in each column ringed, hatched = no runs
  matrixHtml(facets) {
    const m = this.m;
    const order = m.league('tcp', { speed: m.top });
    const grid = {};
    const vals = [];
    for (const r of order) {
      grid[r.name] = {};
      for (const f of facets) { const c = m.value('tcp', 'config', r.name, { speed: m.top, facet: f }); grid[r.name][f] = c; if (c) vals.push(c.v); }
    }
    const { lo, hi } = extent(vals, true);
    const bestOf = {};
    for (const f of facets) {
      const present = order.filter((r) => grid[r.name][f]);
      if (present.length) bestOf[f] = Math.min(...present.map((r) => grid[r.name][f].v));
    }
    this.heat = { facets, cells: order.flatMap((r) => facets.filter((f) => grid[r.name][f]).map((f) => [r.name, f, grid[r.name][f].v, grid[r.name][f].n])), best: bestOf };
    const depOf = (f) => f.split(' · ').slice(-2, -1)[0];
    const groups = [];
    for (const f of facets) { const d = depOf(f); if (!groups.length || groups[groups.length - 1].d !== d) groups.push({ d, n: 0 }); groups[groups.length - 1].n += 1; }
    let html = `<section class="tc-card tc-heat"><h3>Every dataset · split at ${esc(speedText(m.top))} <span class="tc-h">tool tracking RMS, mm, the ${RULE} · ring = best in the column · hatched = no runs · click a column to switch the table above</span> ${rampLegend(lo, hi, 'mm')}</h3>`;
    html += '<div class="tc-scroll"><table class="tc-mtable"><thead>';
    if (m.deployments.length > 1) html += `<tr><th class="tc-l tc-stick"></th>${groups.map((g) => `<th class="tc-grp" colspan="${g.n}" title="${esc(g.d)}">${esc(DEP_SHORT[g.d] || g.d)}</th>`).join('')}</tr>`;
    html += `<tr><th class="tc-l tc-stick">config</th>${facets.map((f) => {
      const ds = datasetShort(f.slice(0, f.lastIndexOf(' · ')));
      const split = f.slice(f.lastIndexOf(' · ') + 3);
      return `<th class="tc-col${f === this.facet ? ' tc-on' : ''}" data-tc-facet="${esc(f)}" title="${esc(f)}: click to rank the League on it"><span class="tc-vh">${esc(ds)}</span><span class="tc-u">${esc(split)}</span></th>`;
    }).join('')}</tr></thead><tbody>`;
    for (const r of order) {
      html += `<tr><th class="tc-l tc-stick">${swatch(r.config)}${nameHtml(r.name, 30)}</th>${facets.map((f) => {
        const c = grid[r.name][f];
        if (!c) return `<td class="tc-none" title="${esc(r.name + ' · ' + f)}: no runs"></td>`;
        const isBest = c.v === bestOf[f];
        return `<td class="${isBest ? 'tc-r1' : ''}${f === this.facet ? ' tc-on' : ''}" ${heatCell(c.v, lo, hi, `title="${esc(`${r.name} · ${f}: ${num3(c.v)} mm, median over ${c.n} targets${isBest ? ' · best in the column' : ''}`)}"`)}>${num3(c.v)}</td>`;
      }).join('')}</tr>`;
    }
    return html + '</tbody></table></div></section>';
  }
  hook() {
    const L = this.L || [];
    return { drill: this.drill ? { ...this.drill, rows: this.drillRows } : null, kind: 'league', top: this.m.top, facet: this.facet, configs: L.length,
      best: L[0] ? { config: L[0].name, v: L[0].v, n: L[0].n } : null,
      league: L.map((r) => [r.name, r.v, r.n]),
      kpis: this.kpiRows || {},
      wins: this.winsOut ? { cells: this.winsOut.cells, byConfig: [...this.winsOut.byConfig].filter(([, w]) => w.of).map(([c, w]) => [c, w.wins, w.of]) } : null,
      heat: this.heat || null,
      answer: (this.el.querySelector('[data-tc-answer]') || {}).textContent || null };
  }
}

/** Nov 23's sentence, over whatever the rail left. */
function leagueSentence(m, L, facet = 'all') {
  const best = L[0];
  const others = L.slice(1);
  const item = (r) => `${swatch(r.config)}<b>${esc(r.name.length > 40 ? r.name.slice(0, 18) + '…' + r.name.slice(-18) : r.name)}</b> ${times(r.v / best.v)}`;
  let list = '';
  if (others.length && others.length <= 5) list = others.map(item).join(', ');
  else if (others.length) list = `${others.slice(0, 3).map(item).join(', ')}, … ${others.length - 4} more, up to ${item(others[others.length - 1])}`;
  return `At <b>${esc(topText(m))}</b>${facet !== 'all' ? ` on <b>${esc(facet)}</b>` : ''}, ${swatch(best.config)}<b>${esc(best.name)}</b> <span class="tc-mut">(${esc(depText(best.config))})</span> ` +
    `has the lowest tool tracking RMS: <b>${num3(best.v)} mm</b>${list ? `; the others are at ${list} of it` : ''}. ` +
    `<span class="tc-mut">Median over ${best.n} targets of each target’s median over its runs${depNote(m)}.</span>`;
}

// ═══ tc-matrix: model type → config × deployment → dataset, the column switchable (O2) ═══
const AXES = [
  { id: 'dataset', label: 'Deployment › dataset' },
  { id: 'split', label: 'Split' },
  { id: 'speed', label: 'Speed' },
  { id: 'deployment', label: 'Deployment' },
];
class MatrixView extends Base {
  static type = 'tc-matrix';
  onClick(e) {
    if (this.closeDrill(e)) return;
    const a = e.target.closest('[data-tc-axis]');
    if (a) { this.axis = a.dataset.tcAxis; this.drill = null; store.set(this.key('axis'), this.axis); this.draw(); return; }
    const g = e.target.closest('[data-tc-fold]');
    if (g) { const k = g.dataset.tcFold; this.folds[k] = !this.folds[k]; store.set(this.key('folds'), this.folds); this.draw(); return; }
    const all = e.target.closest('[data-tc-foldall]');
    if (all) { const close = all.dataset.tcFoldall === 'fold'; this.folds = Object.fromEntries(this.m.modelTypes.map((t) => [t, close])); store.set(this.key('folds'), this.folds); this.draw(); return; }
    const cell = e.target.closest('td[data-tc-cfg]');
    if (cell) {
      const col = cell.dataset.tcCol !== undefined ? this.cols[Number(cell.dataset.tcCol)] : null;
      this.openWorst(cell.dataset.tcCfg, col ? col.where : this.allWhere);
    }
  }
  cols_() {
    const m = this.m, top = m.top;
    if (this.axis === 'split') return m.columns('split', { speed: top }).sort().map((s) => ({ key: s, label: s, where: { speed: top, split: s } }));
    if (this.axis === 'speed') return m.speeds.map((s) => ({ key: String(s), label: speedText(s), where: { speed: s } }));
    if (this.axis === 'deployment') return m.deployments.filter((d) => m.columns('deployment', { speed: top }).includes(d)).map((d) => ({ key: d, label: DEP_SHORT[d] || d, title: d, where: { speed: top, deployment: d } }));
    const ds = m.columns('dataset', { speed: top });
    const depOf = (d) => { const t = [...m.targets.values()].find((x) => x.dataset === d); return t ? t.deployment : ''; };
    return ds.map((d) => ({ d, dep: depOf(d) })).sort((a, b) => m.depOrder(a.dep) - m.depOrder(b.dep) || (a.d < b.d ? -1 : 1))
      .map((x) => ({ key: x.d, label: datasetShort(x.d), title: x.d, group: x.dep, where: { speed: top, dataset: x.d } }));
  }
  render() {
    const m = this.m;
    if (this.axis === undefined) this.axis = store.get(this.key('axis'), this.tc.axis || 'dataset');
    if (!AXES.some((a) => a.id === this.axis)) this.axis = 'dataset';
    if (!this.folds) this.folds = store.get(this.key('folds'), {});
    if (m.top === null) { this.el.innerHTML = '<div class="tc tc-matrix"><p class="tc-answer">No run left has a tool tracking RMS: widen the filter.</p></div>'; return; }
    const cols = this.cols = this.cols_();
    const allWhere = this.allWhere = this.axis === 'speed' ? {} : { speed: m.top };
    const rows = [];
    for (const mt of m.modelTypes) {
      const cfgs = m.configs.filter((c) => c.modelType === mt && m.value('tcp', 'config', c.name, allWhere));
      if (!cfgs.length) continue;
      rows.push({ kind: 'group', key: mt, cfgs });
      if (!this.folds[mt]) for (const c of cfgs) rows.push({ kind: 'config', key: c.name, c });
    }
    const cell = (r, where) => (r.kind === 'group' ? m.value('tcp', 'mt', r.key, where) : m.value('tcp', 'config', r.key, where));
    // every leaf (also folded ones) for the column best and the answer
    const leaves = m.configs.filter((c) => m.value('tcp', 'config', c.name, allWhere));
    const vals = [];
    const out = [];
    for (const r of rows) for (const [i, col] of cols.entries()) { const x = cell(r, col.where); if (x) { vals.push(x.v); out.push([r.kind, r.key, col.key, x.v, x.n]); } }
    for (const c of leaves) for (const col of cols) { const x = m.value('tcp', 'config', c.name, col.where); if (x) vals.push(x.v); }
    const { lo, hi } = extent(vals, true);
    const colBest = cols.map((col) => {
      let best = null;
      for (const c of leaves) { const x = m.value('tcp', 'config', c.name, col.where); if (x && (!best || x.v < best.v)) best = { c, v: x.v, n: x.n }; }
      return best;
    });
    const mtBest = cols.map((col) => {
      let best = null;
      for (const mt of m.modelTypes) { const x = m.value('tcp', 'mt', mt, col.where); if (x && (!best || x.v < best.v)) best = { mt, v: x.v }; }
      return best;
    });
    // the answer, read off the matrix: who holds the most column bests
    const countBy = (list, k) => { const n = new Map(); for (const b of list) if (b) n.set(k(b), (n.get(k(b)) || 0) + 1); return [...n].sort((a, b) => b[1] - a[1]); };
    const cfgWins = countBy(colBest, (b) => b.c.name);
    const mtWins = countBy(mtBest, (b) => b.mt);
    const filled = colBest.filter(Boolean).length;
    const axisWord = { dataset: 'dataset', split: 'split', speed: 'speed', deployment: 'deployment' }[this.axis];
    const cfgOf = (name) => m.configOf.get(name);
    const overall = m.league('tcp', allWhere)[0];
    let answer = '';
    if (cfgWins.length) {
      answer = `${swatch(cfgOf(cfgWins[0][0]))}<b>${esc(cfgWins[0][0])}</b> <span class="tc-mut">(${esc(depText(cfgOf(cfgWins[0][0])))})</span> is the best config in <b>${cfgWins[0][1]}</b> of the <b>${filled}</b> ${axisWord} columns` +
        (cfgWins[1] ? `, ${swatch(cfgOf(cfgWins[1][0]))}<b>${esc(cfgWins[1][0])}</b> in ${cfgWins[1][1]}` : '') +
        (mtWins.length ? `; the best model type <span class="tc-mut">(proposed)</span> is <b>${esc(mtWins[0][0])}</b> in <b>${mtWins[0][1]}</b>` : '') +
        `. <span class="tc-mut">Overall ${this.axis === 'speed' ? 'over every speed' : 'at ' + esc(topText(m))}: ${esc(overall.name)} ${num3(overall.v)} mm${depNote(m)}.</span>`;
    }
    this.answer = { cfgWins, mtWins, filled };
    let html = `<p class="tc-answer" data-tc-answer>${answer}</p>`;
    html += `<div class="tc-chips"><span class="tc-k">Columns</span>${AXES.map((a) => `<button type="button" data-tc-axis="${a.id}" aria-pressed="${a.id === this.axis}">${esc(a.label)}</button>`).join('')}` +
      `<span class="tc-sp"></span><button type="button" class="tc-link" data-tc-foldall="unfold">Unfold all</button><button type="button" class="tc-link" data-tc-foldall="fold">Fold all</button>${rampLegend(lo, hi, 'mm')}</div>`;
    const groups = [];
    if (this.axis === 'dataset') for (const col of cols) { if (!groups.length || groups[groups.length - 1].d !== col.group) groups.push({ d: col.group, n: 0 }); groups[groups.length - 1].n += 1; }
    html += `<div class="tc-scroll"><table class="tc-mtable tc-nested" data-tc-matrix data-axis="${this.axis}"><thead>`;
    if (groups.length) html += `<tr><th class="tc-l tc-stick"></th>${groups.map((g) => `<th class="tc-grp" colspan="${g.n}" title="${esc(g.d)}">${esc(DEP_SHORT[g.d] || g.d)}</th>`).join('')}<th class="tc-grp"></th></tr>`;
    html += `<tr><th class="tc-l tc-stick">model type <span class="tc-u">(proposed) › config</span></th>${cols.map((c) => `<th class="tc-col" title="${esc(c.title || c.label)}"><span class="tc-vh">${esc(c.label)}</span></th>`).join('')}<th class="tc-col tc-roll" title="the row over every column"><span class="tc-vh">every ${axisWord}</span></th></tr>`;
    // the roll-up row: each column's best config
    html += `<tr class="tc-rollrow"><th class="tc-l tc-stick">best config in the column</th>${colBest.map((b, i) => (b
      ? `<td title="${esc(`${cols[i].title || cols[i].label}: best ${b.c.name} ${num3(b.v)} mm over ${b.n} targets`)}"><i class="tc-sw" style="--c:${b.c.color}"></i>${num3(b.v)}</td>`
      : '<td class="tc-none" title="no runs"></td>')).join('')}<td></td></tr></thead><tbody>`;
    for (const r of rows) {
      const isG = r.kind === 'group';
      const head = isG
        ? `<button type="button" class="tc-chev" data-tc-fold="${esc(r.key)}" aria-expanded="${!this.folds[r.key]}">${this.folds[r.key] ? '▸' : '▾'}</button>${nameHtml(r.key, 40, 'tc-name tc-gname')} <span class="tc-mut">${r.cfgs.length} config${r.cfgs.length === 1 ? '' : 's'}</span>`
        : `<span class="tc-indent"></span>${swatch(r.c)}${nameHtml(r.key, 30)}${depHtml(r.c)}`;
      html += `<tr class="${isG ? 'tc-grow' : 'tc-leaf'}"><th class="tc-l tc-stick">${head}</th>${cols.map((col, i) => {
        const x = cell(r, col.where);
        if (!x) return `<td class="tc-none" title="${esc(`${r.key} · ${col.title || col.label}`)}: no runs"></td>`;
        const ring = !isG && colBest[i] && colBest[i].c.name === r.key;
        const tip = `${r.key} · ${col.title || col.label}: ${num3(x.v)} mm, median over ${x.n} targets${isG ? ' (every run of this model type on a target, then over targets)' : ''}${ring ? ' · best in the column' : ''}`;
        return `<td class="${ring ? 'tc-r1' : ''}${isG ? ' tc-gcell' : ''}" ${isG ? '' : `data-tc-cfg="${esc(r.key)}" data-tc-col="${i}"`} ${heatCell(x.v, lo, hi, `title="${esc(tip)}"`)}>${num3(x.v)}</td>`;
      }).join('')}${(() => {
        const x = cell(r, allWhere);
        return x ? `<td class="tc-roll${isG ? ' tc-gcell' : ''}" ${isG ? '' : `data-tc-cfg="${esc(r.key)}"`} ${heatCell(x.v, lo, hi, `title="${esc(`${r.key} over every ${axisWord}: ${num3(x.v)} mm, median over ${x.n} targets`)}"`)}>${num3(x.v)}</td>` : '<td class="tc-none"></td>';
      })()}</tr>`;
    }
    html += '</tbody></table></div>';
    html += this.drillHtml();
    html += `<p class="tc-foot">Cell: tool tracking RMS, mm, the ${RULE}${this.axis === 'speed' ? '' : `, at ${esc(topText(m))}`}. A model type’s row: every run of its configs on a target, then over targets. Ring = best config in the column; hatched = no runs; a cell opens that config’s worst targets there. Model type is ${MODEL_TYPE_NOTE}.</p>`;
    this.out = out;
    this.colBest = colBest;
    this.el.innerHTML = `<div class="tc tc-matrix">${html}</div>`;
  }
  hook() {
    if (!this.cols) return { kind: 'matrix', empty: true };
    return { drill: this.drill ? { ...this.drill, rows: this.drillRows } : null, kind: 'matrix', axis: this.axis, top: this.m.top, columns: this.cols.map((c) => c.key),
      cells: this.out, best: this.colBest.map((b, i) => (b ? [this.cols[i].key, b.c.name, b.v] : null)).filter(Boolean),
      rows: this.el.querySelectorAll('[data-tc-matrix] tbody tr').length, answer: this.answer,
      answerText: (this.el.querySelector('[data-tc-answer]') || {}).textContent || null };
  }
}

// ═══ tc-sweep: speed is the x axis, one line per config, small multiples (O4) ═══
class SweepView extends Base {
  static type = 'tc-sweep';
  onClick(e) {
    if (this.closeDrill(e)) return;
    const f = e.target.closest('[data-tc-by]');
    if (f) { this.by = f.dataset.tcBy; store.set(this.key('by'), this.by); this.draw(); return; }
    const w = e.target.closest('[data-tc-worst]');
    if (w) this.openWorst(w.dataset.tcWorst, { speed: Number(w.dataset.tcSpeed) });
  }
  render() {
    const m = this.m;
    if (this.by === undefined) this.by = store.get(this.key('by'), this.tc.by || 'model_type');
    if (m.top === null) { this.el.innerHTML = '<div class="tc tc-sweep"><p class="tc-answer">No run left has a tool tracking RMS: widen the filter.</p></div>'; return; }
    const facets = this.by === 'deployment' ? m.deployments : m.modelTypes;
    const panels = [];
    const vals = [];
    for (const f of facets) {
      const lines = [];
      for (const c of m.configs) {
        if (this.by === 'deployment' ? !c.deployments.has(f) : c.modelType !== f) continue;
        const pts = m.speeds.map((s) => { const x = m.value('tcp', 'config', c.name, this.by === 'deployment' ? { speed: s, deployment: f } : { speed: s }); return x ? { s, v: x.v, n: x.n } : null; }).filter(Boolean);
        if (!pts.length) continue;
        for (const p of pts) vals.push(p.v);
        lines.push({ c, pts });
      }
      if (lines.length) panels.push({ f, lines });
    }
    const { lo, hi } = extent(vals, true);
    this.panels = panels;
    // the answer: the best config at the slowest and at the fastest speed, and how the fastest one's error grows
    const slow = m.league('tcp', { speed: m.slowest })[0];
    const fast = m.league('tcp', { speed: m.top })[0];
    const fastSlow = fast ? m.value('tcp', 'config', fast.name, { speed: m.slowest }) : null;
    this.answer = { slow: slow ? [slow.name, slow.v] : null, fast: fast ? [fast.name, fast.v] : null, growth: fastSlow ? fast.v / fastSlow.v : null };
    let html = `<p class="tc-answer" data-tc-answer>At <b>${speedText(m.slowest)}</b> the best is ${swatch(slow.config)}<b>${esc(slow.name)}</b> (${num3(slow.v)} mm); at <b>${speedText(m.top)}</b> ${swatch(fast.config)}<b>${esc(fast.name)}</b> (${num3(fast.v)} mm)` +
      (fastSlow && m.slowest !== m.top ? `, whose error grows <b>${times(fast.v / fastSlow.v)}</b> from ${speedText(m.slowest)} to ${speedText(m.top)}` : '') +
      `. <span class="tc-mut">Each point: the ${RULE} at that speed${depNote(m)}.</span></p>`;
    html += `<div class="tc-chips"><span class="tc-k">One panel per</span><button type="button" data-tc-by="model_type" aria-pressed="${this.by === 'model_type'}">model type (proposed)</button><button type="button" data-tc-by="deployment" aria-pressed="${this.by === 'deployment'}">deployment</button>` +
      `<span class="tc-sp"></span><span class="tc-mut">one line per config · log y, shared by every panel · a name at each line’s end (hover for the whole name and every point)</span></div>`;
    const width = Math.max(600, (this.el.clientWidth || 1100) - 8);
    const per = panels.length <= 2 ? panels.length || 1 : panels.length <= 4 ? 2 : 3;
    const W = Math.floor((width - (per - 1) * 12) / per), H = 250;
    html += `<div class="tc-multiples" style="grid-template-columns:repeat(${per}, ${W}px)">${panels.map((p) => this.panelSvg(p, W, H, lo, hi)).join('')}</div>`;
    // the sweep table under it: config × speed, best per speed marked
    const order = [...m.league('tcp', { speed: m.top }).map((r) => r.config), ...m.configs.filter((c) => !m.value('tcp', 'config', c.name, { speed: m.top }))];
    const bestAt = new Map(m.speeds.map((s) => { const b = m.league('tcp', { speed: s })[0]; return [s, b ? b.name : null]; }));
    this.table = [];
    html += `<div class="tc-scroll"><table class="tc-stable"><thead><tr><th class="tc-l">config</th><th class="tc-l">model type <span class="tc-u">(proposed)</span></th>${m.speeds.map((s) => `<th>${speedText(s)}<span class="tc-u">mm · n targets</span></th>`).join('')}</tr></thead><tbody>`;
    for (const c of order) {
      html += `<tr><td class="tc-l tc-cfg">${swatch(c)}${nameHtml(c.name, 40)}${depHtml(c)}</td><td class="tc-l tc-mut">${esc(c.modelType)}</td>${m.speeds.map((s) => {
        const x = m.value('tcp', 'config', c.name, { speed: s });
        if (!x) return '<td class="tc-mut">—</td>';
        this.table.push([c.name, s, x.v, x.n]);
        const best = bestAt.get(s) === c.name;
        return `<td><button type="button" class="tc-cellbtn" data-tc-worst="${esc(c.name)}" data-tc-speed="${s}" title="${esc(c.name)} at ${speedText(s)}: its worst targets">${num3(x.v)}</button> <span class="tc-mut">n ${x.n}</span>${best ? ' <span class="tc-bestchip">best</span>' : ''}</td>`;
      }).join('')}</tr>`;
      if (this.drill && this.drill.config === c.name) html += `<tr class="tc-drillrow"><td colspan="${2 + m.speeds.length}">${this.drillHtml()}</td></tr>`;
    }
    html += `</tbody></table></div><p class="tc-foot">Each value: the ${RULE} at that speed; n = targets. “best” = the lowest at that speed among every config left. A value opens that config’s worst targets at that speed. Model type is ${MODEL_TYPE_NOTE}.</p>`;
    this.el.innerHTML = `<div class="tc tc-sweep">${html}</div>`;
  }
  panelSvg(p, W, H, lo, hi) {
    const m = this.m;
    const L = 40, R = 150, T = 10, B = 30;
    const s0 = Math.min(...m.speeds), s1 = Math.max(...m.speeds);
    const x = (s) => L + (s1 > s0 ? (s - s0) / (s1 - s0) : 0.5) * (W - L - R);
    const y = (v) => T + (1 - logT(v, lo, hi)) * (H - T - B);
    const decades = [];
    for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e += 1) { const v = 10 ** e; if (v >= lo * 0.999 && v <= hi * 1.001) decades.push(v); }
    let svg = `<svg class="tc-panel" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(p.f)}">`;
    svg += decades.map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="tc-grid"/><text x="${L - 4}" y="${(y(v) + 3).toFixed(1)}" class="tc-tick" text-anchor="end">${num3(v)}</text>`).join('');
    svg += m.speeds.map((s) => `<text x="${x(s).toFixed(1)}" y="${H - B + 14}" class="tc-tick" text-anchor="middle">${speedText(s)}</text>`).join('');
    svg += `<text x="${L}" y="${H - 4}" class="tc-tick">speed (× fastest) →</text>`;
    const labels = [];
    const short = (s) => (s.length > 22 ? `${s.slice(0, 9)}…${s.slice(-12)}` : s);
    let singles = 0;
    for (const ln of p.lines) {
      const d = ln.pts.map((pt, i) => `${i ? 'L' : 'M'}${x(pt.s).toFixed(1)} ${y(pt.v).toFixed(1)}`).join('');
      const one = ln.pts.length === 1;
      if (!one) svg += `<path d="${d}" fill="none" stroke="${ln.c.color}" stroke-width="1.8"/>`;
      svg += ln.pts.map((pt) => `<circle cx="${x(pt.s).toFixed(1)}" cy="${y(pt.v).toFixed(1)}" r="${one ? 2.6 : 3}" fill="${ln.c.color}"${one ? ' fill-opacity="0.55"' : ''}><title>${esc(`${ln.c.name} · ${speedText(pt.s)}: ${num3(pt.v)} mm, median over ${pt.n} targets${one ? ' (its only speed)' : ''}`)}</title></circle>`).join('');
      // WHY a single-speed config gets no label: BAM FB's one-off rig configs ran at one speed only, and their names
      // (up to 120 characters) crowded the lines that do sweep; each dot still names itself on hover
      if (one && p.lines.length > 6) { singles += 1; continue; }
      const last = ln.pts[ln.pts.length - 1];
      labels.push({ y: y(last.v) + 3, x: W - R + 6, c: ln.c, text: short(ln.c.name) });
    }
    placeLabels(labels, { gap: 11, top: T + 6, bottom: H - B });
    svg += labels.map((l) => `<text x="${l.x}" y="${l.y.toFixed(1)}" class="tc-dl" fill="${l.c.color}">${esc(l.text)}<title>${esc(l.c.name)}</title></text>`).join('');
    svg += '</svg>';
    return `<figure class="tc-fig"><figcaption>${nameHtml(p.f, 44, 'tc-name tc-gname')} <span class="tc-mut">${p.lines.length} config${p.lines.length === 1 ? '' : 's'}${singles ? ` · ${singles} ran at one speed only: dots, hover for names` : ''}</span></figcaption>${svg}</figure>`;
  }
  hook() {
    return { drill: this.drill ? { ...this.drill, rows: this.drillRows } : null, kind: 'sweep', by: this.by, panels: (this.panels || []).map((p) => p.f),
      cells: (this.panels || []).flatMap((p) => p.lines.flatMap((ln) => ln.pts.map((pt) => [p.f, ln.c.name, pt.s, pt.v, pt.n]))),
      table: this.table || [], answer: this.answer, answerText: (this.el.querySelector('[data-tc-answer]') || {}).textContent || null };
  }
}

// ═══ tc-tradeoff: accuracy vs a cost, one point per config, the Pareto frontier (O5) ═══
const COSTS = ['energy', 'jerk', 'stop'];
class TradeoffView extends Base {
  static type = 'tc-tradeoff';
  onClick(e) {
    if (this.closeDrill(e)) return;
    const f = e.target.closest('[data-tc-cost]');
    if (f) { this.cost = f.dataset.tcCost; store.set(this.key('cost'), this.cost); this.draw(); return; }
    const w = e.target.closest('[data-tc-worst]');
    if (w) this.openWorst(w.dataset.tcWorst, { speed: this.m.top, deployment: w.dataset.tcDep });
  }
  facets() {
    const m = this.m, cost = this.cost, top = m.top;
    return m.deployments.map((d) => {
      const pts = [];
      for (const c of m.configs) {
        if (!c.deployments.has(d)) continue;
        const yv = m.value('tcp', 'config', c.name, { speed: top, deployment: d });
        const xv = m.value(cost, 'config', c.name, { speed: top, deployment: d });
        if (!yv || !xv || (FIELDS[cost].log && !(xv.v > 0))) continue;
        pts.push({ c, x: xv.v, y: yv.v, n: yv.n });
      }
      const front = m.pareto(pts).sort((a, b) => a.x - b.x);
      return { d, pts, front };
    }).filter((f) => f.pts.length);
  }
  render() {
    const m = this.m;
    if (this.cost === undefined) this.cost = store.get(this.key('cost'), this.tc.cost || 'energy');
    if (!COSTS.includes(this.cost)) this.cost = 'energy';
    if (m.top === null) { this.el.innerHTML = '<div class="tc tc-tradeoff"><p class="tc-answer">No run left has a tool tracking RMS: widen the filter.</p></div>'; return; }
    const F = this.F = this.facets();
    const cu = FIELDS[this.cost];
    const sentence = F.map((f) => {
      const acc = f.front.reduce((a, b) => (b.y < a.y ? b : a));
      const cheap = f.front[0];
      const lead = `In <b>${esc(DEP_SHORT[f.d] || f.d)}</b> the frontier is ${f.front.length} config${f.front.length === 1 ? '' : 's'}`;
      if (acc === cheap) return `${lead}: ${swatch(acc.c)}<b>${esc(acc.c.name)}</b> is both the most accurate (${num3(acc.y)} mm) and the least ${esc(cu.short)} (${num3(acc.x)} ${esc(cu.unit)})`;
      return `${lead}: the most accurate ${swatch(acc.c)}<b>${esc(acc.c.name)}</b> (${num3(acc.y)} mm at ${num3(acc.x)} ${esc(cu.unit)}) … the least ${esc(cu.short)} ${swatch(cheap.c)}<b>${esc(cheap.c.name)}</b> (${num3(cheap.x)} ${esc(cu.unit)} at ${times(cheap.y / acc.y)} the RMS)`;
    });
    this.sentences = sentence;
    let html = `<p class="tc-answer" data-tc-answer>${sentence[0] || ''}.${F.length > 1 ? ` <span class="tc-mut">${F.length - 1} more deployment${F.length > 2 ? 's' : ''} below, each with its own frontier.</span>` : ''} <span class="tc-mut">Each point: a config’s ${RULE} at ${esc(topText(m))}; on the frontier = no other config of that deployment is both more accurate and cheaper${depNote(m)}.</span></p>`;
    html += `<div class="tc-chips"><span class="tc-k">Cost (x)</span>${COSTS.map((c) => `<button type="button" data-tc-cost="${c}" aria-pressed="${c === this.cost}">${esc(FIELDS[c].label)} <span class="tc-u">${esc(FIELDS[c].unit)}</span></button>`).join('')}` +
      '<span class="tc-sp"></span><span class="tc-mut">one panel per deployment · point size = n targets · ringed = on the frontier · y log, shared</span></div>';
    const vals = F.flatMap((f) => f.pts.map((p) => p.y));
    const { lo, hi } = extent(vals, true);
    const width = Math.max(600, (this.el.clientWidth || 1100) - 8);
    const per = F.length <= 1 ? 1 : 2;
    const W = Math.floor((width - (per - 1) * 12) / per), H = F.length <= 2 ? 330 : 260;
    html += `<div class="tc-multiples" style="grid-template-columns:repeat(${per}, ${W}px)">${F.map((f, i) => this.panelSvg(f, W, H, lo, hi, F.length > 1 ? sentence[i] : '')).join('')}</div>`;
    html += `<div class="tc-scroll"><table class="tc-stable"><thead><tr><th class="tc-l">deployment</th><th class="tc-l">config</th><th>tool tracking RMS<span class="tc-u">mm at ${esc(speedText(m.top))}</span></th><th>${esc(cu.label)}<span class="tc-u">${esc(cu.unit)} at ${esc(speedText(m.top))}</span></th><th>n<span class="tc-u">targets</span></th><th>frontier</th><th></th></tr></thead><tbody>`;
    for (const f of F) {
      for (const p of f.pts.slice().sort((a, b) => a.y - b.y)) {
        const on = f.front.includes(p);
        const open = this.drill && this.drill.config === p.c.name && this.drill.where.deployment === f.d;
        html += `<tr${on ? ' class="tc-onfront"' : ''}><td class="tc-l tc-mut">${esc(DEP_SHORT[f.d] || f.d)}</td><td class="tc-l tc-cfg">${swatch(p.c)}${nameHtml(p.c.name, 44)}</td><td>${num3(p.y)}</td><td>${num3(p.x)}</td><td>${p.n}</td><td>${on ? '● on it' : ''}</td><td><button type="button" class="tc-link" data-tc-worst="${esc(p.c.name)}" data-tc-dep="${esc(f.d)}" aria-expanded="${!!open}">worst targets ${open ? '↑' : '→'}</button></td></tr>`;
        if (open) html += `<tr class="tc-drillrow"><td colspan="7">${this.drillHtml()}</td></tr>`;
      }
    }
    html += `</tbody></table></div><p class="tc-foot">Each value: the ${RULE}, at ${esc(topText(m))}, within its deployment (a config on two deployments is a point in each). A config with no ${esc(cu.label)} tag is left out of that panel.</p>`;
    this.el.innerHTML = `<div class="tc tc-tradeoff">${html}</div>`;
  }
  panelSvg(f, W, H, lo, hi, sentence = '') {
    const cu = FIELDS[this.cost];
    const L = 48, R = 16, T = 12, B = 34;
    const xs = f.pts.map((p) => p.x);
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    if (cu.log) { x0 /= 1.4; x1 *= 1.4; } else { const pad = (x1 - x0) * 0.08 || Math.abs(x0) * 0.1 || 1; x0 -= pad; x1 += pad; }
    const X = (v) => L + (cu.log ? logT(v, x0, x1) : linT(v, x0, x1)) * (W - L - R);
    const yl = lo / 1.6, yh = hi * 1.6;
    const Y = (v) => T + (1 - logT(v, yl, yh)) * (H - T - B);
    const nmax = Math.max(...f.pts.map((p) => p.n));
    const short = (s) => (s.length > 24 ? `${s.slice(0, 10)}…${s.slice(-13)}` : s);
    const r = (n) => 3 + 7 * Math.sqrt(n / nmax);
    let svg = `<svg class="tc-panel" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(f.d)}">`;
    for (let e = Math.floor(Math.log10(yl)); e <= Math.ceil(Math.log10(yh)); e += 1) {
      const v = 10 ** e; if (v < yl || v > yh) continue;
      svg += `<line x1="${L}" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" class="tc-grid"/><text x="${L - 4}" y="${(Y(v) + 3).toFixed(1)}" class="tc-tick" text-anchor="end">${num3(v)}</text>`;
    }
    const ticks = cu.log ? (() => { const t = []; for (let e = Math.floor(Math.log10(x0)); e <= Math.ceil(Math.log10(x1)); e += 1) { const v = 10 ** e; if (v >= x0 && v <= x1) t.push(v); } return t; })()
      : (() => { let step = 10 ** Math.floor(Math.log10((x1 - x0) / 3)); while ((x1 - x0) / step > 6) step *= (String(step)[0] === '2' ? 2.5 : 2); const t = []; for (let v = Math.ceil(x0 / step) * step; v <= x1; v += step) t.push(Number(v.toPrecision(6))); return t; })();
    svg += ticks.map((v) => `<text x="${X(v).toFixed(1)}" y="${H - B + 14}" class="tc-tick" text-anchor="middle">${num3(v)}</text>`).join('');
    svg += `<text x="${W - R}" y="${H - 4}" class="tc-tick" text-anchor="end">${esc(cu.label)}, ${esc(cu.unit)} → (less is cheaper)</text><text x="${L}" y="${T - 2}" class="tc-tick">↓ more accurate (tool RMS, mm, log)</text>`;
    // the frontier: a staircase through its points, left to right
    if (f.front.length > 1) {
      let d = `M${X(f.front[0].x).toFixed(1)} ${Y(f.front[0].y).toFixed(1)}`;
      for (const p of f.front.slice(1)) d += `H${X(p.x).toFixed(1)}V${Y(p.y).toFixed(1)}`;
      svg += `<path d="${d}" class="tc-front"/>`;
    }
    const labels = [];
    for (const p of f.pts) {
      const on = f.front.includes(p);
      svg += `<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="${r(p.n).toFixed(1)}" fill="${p.c.color}" fill-opacity="${on ? 0.9 : 0.45}" class="${on ? 'tc-onring' : ''}"><title>${esc(`${p.c.name} (${f.d}): ${num3(p.y)} mm at ${num3(p.x)} ${cu.unit}, median over ${p.n} targets${on ? ' · on the frontier' : ''}`)}</title></circle>`;
      if (on || f.pts.length <= 6) labels.push({ x: X(p.x) + r(p.n) + 3, y: Y(p.y) + 3, c: p.c, on, text: short(p.c.name) });
    }
    for (const l of labels) l.x = Math.min(l.x, W - R - 6 * l.text.length);
    placeLabels(labels, { gap: 11, top: T + 8, bottom: H - B });
    svg += labels.map((l) => `<text x="${l.x.toFixed(1)}" y="${l.y.toFixed(1)}" class="tc-dl${l.on ? ' tc-dl-on' : ''}">${esc(l.text)}<title>${esc(l.c.name)}</title></text>`).join('');
    return `<figure class="tc-fig"><figcaption><b>${esc(f.d)}</b> <span class="tc-mut">${f.pts.length} config${f.pts.length === 1 ? '' : 's'} · ${f.front.length} on the frontier</span><div class="tc-figans">${sentence}</div></figcaption>${svg}</svg></figure>`;
  }
  hook() {
    return { drill: this.drill ? { ...this.drill, rows: this.drillRows } : null, kind: 'tradeoff', cost: this.cost, top: this.m.top,
      points: (this.F || []).flatMap((f) => f.pts.map((p) => [f.d, p.c.name, p.x, p.y, p.n])),
      frontier: (this.F || []).flatMap((f) => f.front.map((p) => [f.d, p.c.name])),
      answerText: (this.el.querySelector('[data-tc-answer]') || {}).textContent || null };
  }
}

// ═══ tc-tile: one calm headline number and a small figure; its panel's Open goes to the full view's page (O3) ═══
class TileView extends Base {
  static type = 'tc-tile';
  render() {
    const m = this.m, kind = this.tc.tile;
    const t = TILES[kind];
    if (!t || m.top === null) { this.el.innerHTML = '<div class="tc tc-tile"><p class="tc-mut">No run left has a tool tracking RMS.</p></div>'; this.nums = null; return; }
    const out = t(m);
    this.nums = out.numbers;
    this.el.innerHTML = `<div class="tc tc-tile" data-tile="${esc(kind)}"><div class="tc-tnum" data-tc-answer>${out.big}</div><div class="tc-tsub">${out.sub}</div><div class="tc-tfig">${out.fig || ''}</div></div>`;
  }
  hook() { return { kind: 'tile', tile: this.tc.tile, numbers: this.nums, answerText: (this.el.querySelector('.tc-tile') || {}).textContent || null }; }
}
function dotStrip(items, { lo, hi, ring, W = 300, H = 34 }) {
  const X = (v) => 8 + logT(v, lo, hi) * (W - 16);
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" class="tc-strip tc-mini"><line x1="8" x2="${W - 8}" y1="${H / 2}" y2="${H / 2}" class="tc-axis"/>` +
    items.map((it) => `<circle cx="${X(it.v).toFixed(1)}" cy="${H / 2}" r="${it === ring ? 6 : 4}" fill="${it.color}" ${it === ring ? 'class="tc-onring"' : 'fill-opacity="0.75"'}><title>${esc(it.title)}</title></circle>`).join('') +
    `<text x="8" y="${H - 1}" class="tc-tick">${num3(lo)} mm</text><text x="${W - 8}" y="${H - 1}" class="tc-tick" text-anchor="end">${num3(hi)} mm · log</text></svg>`;
}
const TILES = {
  best(m) {
    const L = m.league('tcp', { speed: m.top });
    const b = L[0], n2 = L[1];
    return {
      numbers: { config: b.name, v: b.v, n: b.n, next: n2 ? [n2.name, n2.v / b.v] : null, configs: L.length },
      big: `${swatch(b.config)}${nameHtml(b.name, 26)} <span class="tc-tval">${num3(b.v)} mm</span>`,
      sub: `the lowest tool tracking RMS at ${esc(topText(m))} of ${L.length} config${L.length === 1 ? '' : 's'}${n2 ? `; next ${esc(n2.name)} at ${times(n2.v / b.v)}` : ''}<span class="tc-mut"> · ${RULE}, n ${b.n}${depNote(m)}</span>`,
      fig: `<div class="tc-top5">${L.slice(0, 5).map((r, i) => `<span class="tc-r">${i + 1}</span><span>${swatch(r.config)}${nameHtml(r.name, 30)} <span class="tc-mut">${esc(depText(r.config))}</span></span><span class="tc-v">${num3(r.v)} mm</span><span class="tc-mut">${i ? times(r.v / b.v) : 'best'}</span>`).join('')}</div>${L.length > 5 ? `<div class="tc-mut" style="font-size:11.5px">… ${L.length - 5} more up to ${num3(L[L.length - 1].v)} mm (${times(L[L.length - 1].v / b.v)})</div>` : ''}`,
    };
  },
  coverage(m) {
    const datasets = [...new Set([...m.targets.values()].map((t) => t.dataset))];
    const depOf = new Map([...m.targets.values()].map((t) => [t.dataset, t.deployment]));
    datasets.sort((a, b) => m.depOrder(depOf.get(a)) - m.depOrder(depOf.get(b)) || (a < b ? -1 : 1));
    const filled = new Set();
    for (const r of m.rows) if (Number.isFinite(r.tcp) && r.tcp > 0) filled.add(`${r.model_type}\u0001${r.dataset}`);
    const cells = m.modelTypes.length * datasets.length;
    const pct = cells ? (100 * filled.size) / cells : 0;
    const cw = Math.max(4, Math.min(36, Math.floor(480 / Math.max(1, datasets.length))));
    const ch = 14;
    const fig = `<svg width="${cw * datasets.length}" height="${m.modelTypes.length * ch}" class="tc-mini">${m.modelTypes.map((mt, i) => datasets.map((d, j) =>
      `<rect x="${j * cw}" y="${i * ch}" width="${cw - 2}" height="${ch - 2}" rx="2" class="${filled.has(`${mt}\u0001${d}`) ? 'tc-fill' : 'tc-empty'}"><title>${esc(`${mt} · ${d}: ${filled.has(`${mt}\u0001${d}`) ? 'runs' : 'no runs'}`)}</title></rect>`).join('')).join('')}</svg><div class="tc-mut" style="font-size:11.5px">a row per model type, a column per dataset (hover one); the full matrix behind Open</div>`;
    return {
      numbers: { pct, filled: filled.size, cells, modelTypes: m.modelTypes.length, datasets: datasets.length },
      big: `${Math.round(pct)} % <span class="tc-tval">of model × dataset cells have runs</span>`,
      sub: `${filled.size} of ${cells} cells: ${m.modelTypes.length} model type${m.modelTypes.length === 1 ? '' : 's'} <span class="tc-mut">(proposed)</span> × ${datasets.length} dataset${datasets.length === 1 ? '' : 's'}; filled = at least one run`,
      fig,
    };
  },
  speed(m) {
    const b = m.league('tcp', { speed: m.top })[0];
    const values = m.speeds.map((s) => { const x = m.value('tcp', 'config', b.name, { speed: s }); return x ? x.v : null; });
    const first = values.find((v) => v !== null);
    const firstSpeed = m.speeds[values.indexOf(first)];
    const ratio = first ? b.v / first : null;
    const { lo, hi } = extent(values, true);
    return {
      numbers: { config: b.name, from: firstSpeed, v0: first, v1: b.v, ratio },
      big: `${times(ratio)} <span class="tc-tval">more error at ${speedText(m.top)}</span>`,
      sub: `${swatch(b.config)}<b>${esc(b.name)}</b>, ${num3(first)} → ${num3(b.v)} mm from ${speedText(firstSpeed)} to ${speedText(m.top)}`,
      fig: sparkline(values, { lo, hi, log: true, color: b.config.color, w: 260, h: 44, title: `${b.name} vs speed` }),
    };
  },
  cost(m) {
    const b = m.league('tcp', { speed: m.top })[0];
    const d = [...b.config.deployments].sort((x, y) => m.depOrder(x) - m.depOrder(y))[0];
    const pts = [];
    for (const c of m.configs) {
      if (!c.deployments.has(d)) continue;
      const y = m.value('tcp', 'config', c.name, { speed: m.top, deployment: d });
      const x = m.value('energy', 'config', c.name, { speed: m.top, deployment: d });
      if (x && y) pts.push({ c, x: x.v, y: y.v });
    }
    const front = m.pareto(pts).sort((a, b2) => a.x - b2.x);
    const acc = front.reduce((a, p) => (p.y < a.y ? p : a), front[0]);
    const cheap = front[0];
    const fig = `<div class="tc-top5">${front.map((p, i) => `<span class="tc-r">${i + 1}</span><span>${swatch(p.c)}${nameHtml(p.c.name, 28)}</span><span class="tc-v">${num3(p.x)} J</span><span class="tc-mut">${num3(p.y)} mm</span>`).join('')}</div><div class="tc-mut" style="font-size:11.5px">the frontier, least energy first; ${pts.length - front.length} more config${pts.length - front.length === 1 ? '' : 's'} in ${esc(DEP_SHORT[d] || d)} are beaten on both</div>`;
    return {
      numbers: { deployment: d, frontier: front.map((p) => p.c.name), accurate: [acc.c.name, acc.x, acc.y], cheapest: [cheap.c.name, cheap.x, cheap.y] },
      big: `${front.length} <span class="tc-tval">config${front.length === 1 ? '' : 's'} on the energy frontier</span>`,
      sub: `in <b>${esc(d)}</b>${m.deployments.length > 1 ? ' (the best config’s)' : ''}: no other config there is both more accurate and cheaper; ${acc === cheap ? `${esc(acc.c.name)} is both` : `${esc(cheap.c.name)} costs ${times(cheap.x / acc.x)} the energy of ${esc(acc.c.name)} at ${times(cheap.y / acc.y)} its RMS`}`,
      fig,
    };
  },
  worst(m) {
    const b = m.league('tcp', { speed: m.top })[0];
    const items = b.items.slice().sort((x, y) => y.v - x.v);
    const w = items[0];
    const { lo, hi } = extent(items.map((i) => i.v), true);
    const strip = dotStrip(items.map((i) => ({ v: i.v, color: b.config.color, title: `${i.t.task}: ${num3(i.v)} mm` })), { lo, hi, ring: null });
    return {
      numbers: { config: b.name, target: w.t.key, v: w.v, ratio: w.v / b.v, targets: items.length },
      big: `${num3(w.v)} mm <span class="tc-tval">${times(w.v / b.v)} its median</span>`,
      sub: `${swatch(b.config)}<b>${esc(b.name)}</b>’s worst target: <a href="${esc(targetHref(w.t))}" title="${esc(w.t.target)}: open its target view">${esc(w.t.task)} ↗</a> <span class="tc-mut">${esc(datasetShort(w.t.dataset))} · ${esc(w.t.split)}, of ${items.length}</span>`,
      fig: strip,
    };
  },
  left(m) {
    const runs = m.rows.length;
    const byDep = m.deployments.map((d) => [d, m.rows.filter((r) => r.deployment === d).length]);
    const datasets = new Set([...m.targets.values()].map((t) => t.dataset)).size;
    const W = 260;
    let x = 0;
    const fig = `<svg width="${W}" height="14" class="tc-mini">${byDep.map(([d, n], i) => { const w = (W * n) / runs; const s = `<rect x="${x.toFixed(1)}" y="0" width="${Math.max(1, w - 1).toFixed(1)}" height="12" class="tc-dep${i % 4}"><title>${esc(`${d}: ${n.toLocaleString('en-US')} runs`)}</title></rect>`; x += w; return s; }).join('')}</svg>`;
    return {
      numbers: { runs, targets: m.targets.size, configs: m.configs.length, deployments: m.deployments.length, datasets },
      big: `${runs.toLocaleString('en-US')} <span class="tc-tval">runs left</span>`,
      sub: `${m.targets.size.toLocaleString('en-US')} targets · ${m.configs.length} configs · ${datasets} datasets · ${m.deployments.length} deployment${m.deployments.length === 1 ? '' : 's'} <span class="tc-mut">(${byDep.map(([d, n]) => `${esc(DEP_SHORT[d] || d)} ${n.toLocaleString('en-US')}`).join(' · ')})</span>`,
      fig,
    };
  },
};

// ═══ tc-worst: a config's worst targets, each linking its target view (O3's page) ═══
class WorstView extends Base {
  static type = 'tc-worst';
  onChange(e) { if (e.target.matches('select[data-tc-pick]')) { this.pick = e.target.value; this.draw(); } }
  render() {
    const m = this.m;
    if (m.top === null) { this.el.innerHTML = '<div class="tc"><p class="tc-answer">No run left has a tool tracking RMS.</p></div>'; return; }
    const L = m.league('tcp', { speed: m.top });
    if (!this.pick || !L.some((r) => r.name === this.pick)) this.pick = L[0].name;
    const r = L.find((x) => x.name === this.pick);
    const items = r.items.slice().sort((a, b) => b.v - a.v).slice(0, 25);
    this.rows = items.map((i) => [i.t.key, i.v]);
    let html = `<p class="tc-answer" data-tc-answer>${swatch(r.config)}<b>${esc(r.name)}</b>’s ${items.length} worst of ${r.n} targets at ${esc(speedText(m.top))}: the worst is <b>${num3(items[0].v)} mm</b>, ${times(items[0].v / r.v)} its median of ${num3(r.v)} mm. <span class="tc-mut">A target’s value: the median over its runs of this config.</span></p>`;
    html += `<div class="tc-chips"><span class="tc-k">Config</span><select data-tc-pick aria-label="Config">${L.map((x) => `<option value="${esc(x.name)}"${x.name === r.name ? ' selected' : ''}>${esc(x.name)} · ${num3(x.v)} mm</option>`).join('')}</select></div>`;
    html += `<div class="tc-scroll"><table class="tc-stable"><thead><tr><th class="tc-l">#</th><th class="tc-l">target</th><th class="tc-l">dataset · split</th><th>tool RMS<span class="tc-u">mm, median over its runs</span></th><th>× the config’s median</th><th>runs</th><th></th></tr></thead><tbody>`;
    items.forEach((i, k) => {
      html += `<tr><td class="tc-l tc-rank">${k + 1}</td><td class="tc-l">${nameHtml(i.t.task, 40)}</td><td class="tc-l tc-mut">${esc(datasetShort(i.t.dataset))} · ${esc(i.t.split)}</td><td>${num3(i.v)}</td><td>${times(i.v / r.v)}</td><td>${i.runs.length}</td><td><a class="tc-link" href="${esc(targetHref(i.t))}">Open target view ↗</a></td></tr>`;
    });
    this.el.innerHTML = `<div class="tc tc-worst">${html}</tbody></table></div><p class="tc-foot">Open target view: V2’s target page with the runs the rail keeps for that target checked, and ‹ All targets back to this filter.</p></div>`;
  }
  hook() { return { kind: 'worst', config: this.pick, rows: this.rows || [] }; }
}

// ── registration (data-ui CONTRACT §1: registerView(type, {name, icon, load})) ──
const VIEWS = [
  [LeagueView, 'League (host)', 'table'],
  [MatrixView, 'Model × dataset matrix (host)', 'grid'],
  [SweepView, 'Speed sweep (host)', 'chart-line'],
  [TradeoffView, 'Trade-off map (host)', 'chart-scatter'],
  [TileView, 'Headline tile (host)', 'gauge'],
  [WorstView, 'Worst targets (host)', 'list'],
];
export function registerOverviewViews(registerView) {
  for (const [cls, name, icon] of VIEWS) registerView(cls.type, { name, icon, load: async () => ({ default: cls, css: CSS }) });
}
export { median };
