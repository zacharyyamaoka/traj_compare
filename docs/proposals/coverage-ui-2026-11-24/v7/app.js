/* app.js — V7 "Splice": V3's host (one .base drawn by data-ui), with V5/V6's one-screen landing and V6's "click a cell →
 * who made it", made data-ui-native. It does what data-ui does not do yet, each the prototype of a part of
 * PROPOSED-CONTRACT.md §52, and nothing else:
 *
 *   1. registers the coverage view types from views/ (registerView, CONTRACT §1), one bundle ("folder": coverage);
 *   2. draws `pages:` as tabs, each page a <data-dashboard> (its panels) or a <data-views> (its saved views as tabs);
 *   3. hands the gear's settings (<data-settings>) to every page through the dashboard's style;
 *   4. V7: owns the cell query (views/query.js): a view's `coverage-cell` event adds or drops a chip in the bar under
 *      the tabs, the chips AND together, and the answer filters both stock tables (the who dock beside the figures and
 *      the Trajectories page) through the all-views filter, while every coverage view fades the cells nobody in the
 *      answer visits;
 *   5. fills the trajectory drill in data-ui's side peek: Open in Rerun through el.openElsewhere (CONTRACT §46) turned
 *      into a POST, and through el.peekExtra (CONTRACT §37) what it alone adds, its tool path and joints over the set,
 *      its joints over time (two stock `chart` views) and its spans against the set.
 */
import { registerView, parseBase, loadDataset, loadView } from '../vendor/data-ui/data-ui.js';
import '../vendor/data-ui/dashboard.js';
import './settings.js';
import Query from './views/query.js';
import { cellWords } from './views/kit.js';

const TYPES = [
  ['coverage-plane', 'Coverage plane', 'grid-3x3', './views/coverage-plane.js'],
  ['coverage-hist', 'Coverage histogram', 'chart-column', './views/coverage-hist.js'],
  ['coverage-projection', 'Coverage projection', 'map', './views/coverage-projection.js'],
  ['coverage-polar', 'Coverage polar', 'compass', './views/coverage-polar.js'],
  ['coverage-sheet', 'Coverage sheet', 'list', './views/coverage-sheet.js'],
];
for (const [type, name, icon, file] of TYPES) registerView(type, { name, icon, folder: 'coverage', load: () => import(file) });

const here = (path) => new URL(path, import.meta.url).href;
const slug = (text) => String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const esc = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const PAGE_IDS = { overview: 'overview', limits: 'limits', 'one-joint': 'joint', 'all-joints': 'joints', 'tool-position': 'position', 'tool-orientation': 'orientation', trajectories: 'trajectories' };
const ICONS = {
  overview: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
  limits: '<path d="M4 20V4M20 20V4M8 16v-4M12 16V8M16 16v-6"/>',
  joint: '<circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
  joints: '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="12" r="2.5"/><path d="M8.5 12h7"/>',
  position: '<path d="M12 21s-6-5.5-6-11a6 6 0 0 1 12 0c0 5.5-6 11-6 11z"/><circle cx="12" cy="10" r="2"/>',
  orientation: '<circle cx="12" cy="12" r="9"/><path d="M12 12l4-6"/>',
  trajectories: '<path d="M3 5h18M3 12h18M3 19h18"/>',
};

// where this round lives on disk (README.md's serve command): only the by-hand Rerun command reads it
const ROUND_DIR = '/home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24';

const app = {
  base: null, meta: null, datasets: {}, pages: [], current: null, settings: null, motion: null, samples: null,
  baseUrl: here('coverage.base'), tables: [], dock: null,
};

async function boot() {
  const [text, meta, membership] = await Promise.all([
    fetch(app.baseUrl).then((r) => r.text()),
    fetch(here('rows/meta.json')).then((r) => r.json()),
    fetch(here('../data/membership.json')).then((r) => r.json()),
  ]);
  app.base = parseBase(text);
  app.meta = meta;
  Query.load(membership);
  document.querySelector('[data-cov-title]').textContent = meta.title;
  document.querySelector('[data-cov-subtitle]').textContent = meta.subtitle;
  document.title = `${meta.title} · coverage`;

  // the gear: the .base's settings: block, its style: defaults
  app.settings = document.querySelector('data-settings');
  app.settings.spec = app.base.settings || {};
  app.settings.defaults = app.base.style || {};
  app.settings.render();
  app.settings.addEventListener('data-settings-change', () => applySettings());

  await Promise.all(Object.entries(app.base.datasets).map(async ([name, spec]) => {
    const href = new URL(typeof spec === 'string' ? spec : spec.data, app.baseUrl).href;
    app.datasets[name] = { ...(await loadDataset(href)), url: href };
  }));

  const nav = document.querySelector('[data-cov-nav]');
  const main = document.getElementById('pages');
  main.querySelector('[data-cov-loading]').remove();
  for (const page of app.base.pages) {
    const id = PAGE_IDS[slug(page.name)] || slug(page.name);
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'cv-tab';
    tab.setAttribute('role', 'tab');
    tab.dataset.covTab = id;
    tab.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[id] || ''}</svg>${esc(page.name)}`;
    tab.addEventListener('click', () => show(id));
    nav.append(tab);
    const section = document.createElement('section');
    section.className = 'cv-page';
    section.dataset.page = id;
    section.setAttribute('role', 'tabpanel');
    section.hidden = true;
    main.append(section);
    app.pages.push({ id, page, tab, section, el: null });
  }

  // V7: the query bar under the tabs and the who dock beside the figures
  buildQueryBar();
  buildDock();
  document.addEventListener('coverage-cell', (e) => onCell(e.detail));
  Query.addEventListener('change', () => onQuery());
  // a link reopens its page and its question (read both before either writes the hash back)
  const first = pageFromHash() || 'overview';
  const restored = chipsFromHash();
  document.addEventListener('data-coverage-pick', (e) => openJoint(e.detail.value));
  addEventListener('hashchange', () => { const want = pageFromHash(); if (want && want !== app.current) show(want); });
  show(first);
  if (restored.length) Query.set(restored); else onQuery();
  document.body.dataset.ready = '';
}

function pageFromHash() {
  const m = /(?:^|[#&])page=([\w-]+)/.exec(location.hash);
  return m && app.pages.some((p) => p.id === m[1]) ? m[1] : null;
}

function writeHash() {
  // the page and the chips ride in the URL, so a link (or a bookmark) reopens the same question
  if (!app.current) return;
  const q = Query.chips.map((c) => `${c.key}:${c.cell}`).join(',');
  try { history.replaceState(null, '', `#page=${app.current}${q ? `&q=${encodeURIComponent(q)}` : ''}`); } catch { /* file:// in some browsers */ }
}

function show(id) {
  const entry = app.pages.find((p) => p.id === id);
  if (!entry) return;
  app.current = id;
  document.body.dataset.current = id;
  for (const p of app.pages) {
    p.section.hidden = p !== entry;
    p.tab.setAttribute('aria-selected', String(p === entry));
    p.tab.tabIndex = p === entry ? 0 : -1;
  }
  if (!entry.el) build(entry);
  else if (entry.stale) { entry.stale = false; reloadDashboard(entry); }
  // WHY the query box opens on arrival: under data-ui's tabs form the box folds behind its Search icon (CONTRACT §47,
  // the robotparts look Zach pointed at); a table page is visited to find rows, so the box is open and focused, as "/" does
  if (entry.page.views && entry.el && entry.el._drawnOnce) openQuery(entry.el);
  writeHash();
}

/* ── a dashboard page: the shared datasets, the page's own rail and filters, the views its panels name ────────── */

function pageBase(page) {
  const base = app.base;
  const byName = new Map(base.views.map((v) => [v.name, v]));
  const views = (page.panels || []).map((p) => byName.get(p.view)).filter(Boolean);
  const used = [...new Set(views.map((v) => v.from).filter(Boolean))];
  const datasets = {};
  for (const name of used) {
    const spec = base.datasets[name];
    datasets[name] = { data: typeof spec === 'string' ? spec : spec.data, ...((page.datasets || {})[name] || {}) };
  }
  // WHY the reader's settings go into style: data-ui resolves a dashboard's style for every panel (resolveStyle keeps
  // keys it does not know), so each coverage view reads them in update(input) as input.view.style.colormap today;
  // §52.6 names the field input.settings
  return {
    style: { ...(base.style || {}), ...app.settings.value },
    properties: base.properties || {},
    datasets,
    // V7: a page may carry its own layout keys (the landing turns Arrange off: stock `layout.arrange: false`, §25)
    layout: { ...(base.layout || {}), ...(page.layout || {}), panels: page.panels },
    views,
  };
}

function build(entry) {
  const { page, section } = entry;
  if (page.views && page.views.length) { buildViewsPage(entry); return; }
  const dash = document.createElement('data-dashboard');
  dash.id = `cov-${entry.id}`;
  dash.setAttribute('no-url', '');
  section.append(dash);
  entry.el = dash;
  entry.base = pageBase(page);
  const sets = Object.fromEntries(Object.keys(entry.base.datasets).map((n) => [n, app.datasets[n]]));
  entry.sets = sets;
  dash.baseUrl = app.baseUrl;
  dash.load(entry.base, sets);
}

function reloadDashboard(entry) {
  entry.base = pageBase(entry.page);
  entry.el.load(entry.base, entry.sets, { keepState: true });
}

function applySettings() {
  for (const entry of app.pages) {
    if (!entry.el || entry.el.tagName !== 'DATA-DASHBOARD') continue;
    if (entry.id === app.current) reloadDashboard(entry); else entry.stale = true;
  }
}

/* the All joints ridgeline's row click, and a plane chip's click: the joint's own page, its rail moved to that joint */
function openJoint(joint) {
  show('joint');
  const entry = app.pages.find((p) => p.id === 'joint');
  if (entry && entry.el && typeof entry.el.setRail === 'function') entry.el.setRail('planes', `joint == "${joint}"`);
}

/* ── V7: the cell query — the bar under the tabs ───────────────────────────────────────────────────────────────── */

function gridRow(key) {
  if (key.startsWith('plane/')) {
    const [, joint, grid] = key.split('/');
    return app.datasets.planes.rows.find((r) => r.joint === joint && r.grid === grid);
  }
  if (key === 'directions') return app.datasets.directions.rows.find((r) => r.grid === 'sphere');
  return app.datasets.projections.rows.find((r) => r.view === key);
}

function chipsFromHash() {
  const m = /(?:^|[#&])q=([^&]+)/.exec(location.hash);
  if (!m) return [];
  return decodeURIComponent(m[1]).split(',').map((part) => {
    const at = part.lastIndexOf(':');
    const key = part.slice(0, at); const cell = Number(part.slice(at + 1));
    const row = gridRow(key);
    return row && Number.isInteger(cell) && Query.indexed(key) ? { key, cell, label: cellWords(row, cell) } : null;
  }).filter(Boolean);
}

function onCell(detail) {
  if (!detail || !detail.key) return;
  if (detail.empty) { flash(`Nobody visits that cell (${detail.label.replace(/^visits |^tool /, '')}); click a coloured one.`); return; }
  Query.toggle({ key: detail.key, cell: detail.cell, label: detail.label });
}

let flashTimer = 0;
function flash(text) {
  const note = document.querySelector('[data-query-note]');
  if (!note) return;
  note.textContent = text;
  note.hidden = false;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => { note.hidden = true; }, 3200);
}

function buildQueryBar() {
  const bar = document.querySelector('[data-querybar]');
  bar.innerHTML = `<span class="cv7-q-label">Who made it</span>
    <div class="cv7-chips" data-chips></div>
    <span class="cv7-q-note" data-query-note role="status" hidden></span>
    <span class="cv7-q-count" data-answer-count title="A subset count from data/membership.json: the trajectories that visit every cell you asked about (the figures keep the payload's own counts)"></span>`;
  bar.addEventListener('click', (e) => {
    const x = e.target.closest('[data-chip-x]');
    if (x) { Query.remove(Number(x.dataset.chipX)); return; }
    if (e.target.closest('[data-chips-clear]')) { Query.clear(); return; }
    const go = e.target.closest('[data-chip-go]');
    if (go) goToChip(Query.chips[Number(go.dataset.chipGo)]);
  });
}

function goToChip(chip) {
  if (!chip) return;
  if (chip.key.startsWith('plane/')) openJoint(chip.key.split('/')[1]);
  else if (chip.key === 'directions') show('orientation');
  else show('position');
}

function renderQueryBar() {
  const chips = document.querySelector('[data-chips]');
  const n = Query.active ? Query.answer.length : Query.total;
  if (!Query.active) {
    chips.innerHTML = '<span class="cv7-q-hint"><b>Click any coloured cell</b> in a figure to ask which trajectories made it. Clicks add up (AND); the list beside the figures and the Trajectories table keep only the answer.</span>';
  } else {
    chips.innerHTML = Query.chips.map((c, i) => `${i ? '<span class="cv7-and">and</span>' : ''}<span class="cv7-chip" data-chip="${esc(c.key)}:${c.cell}"><button type="button" class="cv7-chip-go" data-chip-go="${i}" title="Show this cell on its own tab">${esc(c.label)}</button><button type="button" class="cv7-chip-x" data-chip-x="${i}" aria-label="Drop: ${esc(c.label)}" title="Drop this question">✕</button></span>`).join('')
      + '<button type="button" class="cv7-q-clear" data-chips-clear>Clear</button>';
  }
  document.querySelector('[data-answer-count]').innerHTML = `<b>${n}</b> of ${Query.total} trajectories${Query.active ? '' : ''}`;
  const dockCount = document.querySelector('[data-dock-count]');
  if (dockCount) dockCount.innerHTML = `<b>${n}</b> of ${Query.total}`;
}

/* The answer as data-ui's all-views filter (an or-group of `name ==`, Bases' own grammar), composed with whatever the
 * reader filtered there, so both stock tables (the dock, the Trajectories page) show "8 of 54 rows" and ‹ n of N ›
 * steps through the answer. WHY the filter and not new rows: the table keeps its sort, groups, saved views and counts. */
function answerExpr() {
  if (!Query.active) return '';
  const names = Query.answer;
  return names.length ? names.map((n) => `name == "${n}"`).join(' || ') : 'name == "(no trajectory visits every asked cell)"';
}

function withoutAnswer(filters, prev) {
  if (!filters || !prev) return filters || '';
  if (typeof filters === 'string') return filters === prev ? '' : filters;
  if (Array.isArray(filters.and)) {
    const rest = filters.and.filter((f) => f !== prev);
    return rest.length === 0 ? '' : rest.length === 1 ? rest[0] : { and: rest };
  }
  return filters;
}

function applyAnswer(el) {
  if (!el) return;
  const expr = answerExpr();
  const base = withoutAnswer(el.filters, el._answerExpr);
  el._answerExpr = expr;
  el._settingAnswer = true;
  el.filters = expr ? (base ? { and: [base, expr] } : expr) : base;
  el._settingAnswer = false;
  labelAnswerPill(el);
}

/* the all-views pill shows the clause as written; the host says it in words (§52.8 asks data-ui for a pill label) */
function labelAnswerPill(el) {
  if (!el._answerExpr) return;
  for (const body of el.querySelectorAll('.dv-pill-body')) {
    if (body.textContent.trim() !== el._answerExpr && !body.textContent.includes('name == "workspace-') && !body.textContent.includes('(no trajectory visits')) continue;
    body.textContent = `Who made it: the ${Query.answer.length} that visit every asked cell`;
    body.title = `The query bar's answer (${Query.chips.map((c) => c.label).join(' AND ')}). ✕ clears the question.`;
    body.closest('.dv-pill')?.classList.add('cv7-answer-pill');
  }
}

function watchAnswerPill(el) {
  el.addEventListener('data-views-render', () => labelAnswerPill(el));
  el.addEventListener('data-views-change', () => {
    if (el._settingAnswer || !Query.active || !el._answerExpr) return;
    // the reader removed the answer's pill (its ✕): that clears the question everywhere
    if (!JSON.stringify(el.filters || '').includes(JSON.stringify(Query.answer[0] || '(no trajectory').slice(1, -1))) {
      el._answerExpr = '';
      Query.clear();
    }
    labelAnswerPill(el);
  });
}

function onQuery() {
  renderQueryBar();
  for (const el of app.tables) applyAnswer(el);
  writeHash();
}

/* ── V7: the who dock — a compact stock table beside every figure page ─────────────────────────────────────────── */

function trajectoryData(id) {
  const data = app.datasets.trajectories;
  // its own dataset id, so its view state and the Trajectories page's saved views (localStorage, per data.id) never mix
  return id ? { ...data, id } : data;
}

function splitLegend(data) {
  const colours = (data.properties.split && data.properties.split.colors) || {};
  return Object.entries(colours).map(([value, slot]) => `<span class="cv-sw"><i style="background:var(--data-series-${slot}, var(--dv-series-${slot}))"></i>${esc(value)}</span>`).join('');
}

function buildDock() {
  const aside = document.querySelector('[data-who]');
  const data = trajectoryData('coverage-trajectories-who');
  const view = app.base.views.find((v) => v.name === (app.base.dock || 'Who made it'));
  aside.innerHTML = `<header class="cv7-dock-head">
      <div class="cv7-dock-title"><span>Who made it</span><span class="cv7-dock-count" data-dock-count></span></div>
      <div class="cv7-dock-legend" data-dock-legend>${splitLegend(data)}<span>= split</span><span class="cv7-bar-key"><i></i>= new cells</span></div>
    </header>`;
  const el = document.createElement('data-views');
  el.id = 'cov-who';
  for (const [k, v] of [['toolbar', 'none'], ['status', 'off'], ['no-url', ''], ['open', 'side']]) el.setAttribute(k, v);
  el.base = { properties: app.base.properties || {}, views: [view] };
  el.data = data;
  wireTrajectoryViews(el);
  aside.append(el);
  app.dock = el;
  app.tables.push(el);
  // the drill drawer: while data-ui's peek is open in the dock, the dock widens over the figures' right edge (V6's
  // drawer), so the dataset stays in view on the left and the peek has its usual 540 px
  const sync = () => aside.classList.toggle('cv7-drilling', !!el.querySelector('.dv-peek:not([hidden])'));
  new MutationObserver(sync).observe(el, { childList: true, subtree: true });
  el.addEventListener('keydown', (e) => { if (e.key === 'Escape') setTimeout(sync, 0); });
}

/* ── the Trajectories page: data-ui's stock table, its saved views as tabs, its side peek as the drill ─────────── */

function buildViewsPage(entry) {
  const { page, section } = entry;
  const byName = new Map(app.base.views.map((v) => [v.name, v]));
  const views = page.views.map((n) => byName.get(n)).filter(Boolean);
  const data = app.datasets[views[0].from];
  // G3: the one colour beside a trajectory (its split badge) keyed where it is shown, in the families' slots
  section.insertAdjacentHTML('beforeend', `<div class="cv-rowlegend" data-row-legend><span>Split badge colours, the same as the split bars on Limits:</span>${splitLegend(data)}<span>· the bar in New cells = q×qd cells it was first to visit · click a row to drill in (its numbers, its motion, Open in Rerun)</span></div>`);
  const el = document.createElement('data-views');
  el.id = 'cov-trajectories';
  for (const [k, v] of [['views', 'tabs'], ['toolbar', 'bar'], ['no-url', ''], ['open', 'side'], ['filters', 'pills'], ['search', 'box'], ['view-counts', '']]) el.setAttribute(k, v);
  el.base = { properties: app.base.properties || {}, views };
  el.data = data;
  wireTrajectoryViews(el);
  el.addEventListener('data-views-render', () => { if (!el._drawnOnce) { el._drawnOnce = true; if (app.current === entry.id) openQuery(el); } });
  section.append(el);
  entry.el = el;
  app.tables.push(el);
  applyAnswer(el);
}

/* what both stock tables share: the drill (peek extra, Open in Rerun), a plain header click sorts, the answer's pill */
function wireTrajectoryViews(el) {
  // CONTRACT §46: where else a record opens; the host's to say. Rerun's is a POST, so the click is taken over below.
  el.openElsewhere = (row) => (row && row.rrd ? { href: new URL(`../${row.rrd}`, location.href).href, label: 'Rerun' } : null);
  // CONTRACT §37: the host's own pane at the foot of the record
  el.peekExtra = (row) => drillHtml(row);
  el.addEventListener('data-views-open', (e) => { if (e.detail && e.detail.row && !e.detail.records) mountDrill(el, e.detail.row); });
  el.addEventListener('click', (e) => {
    const a = e.target.closest('[data-open-elsewhere]');
    if (!a || !el.contains(a)) return;
    e.preventDefault();
    const rec = a.closest('.dv-open-rec');
    const row = rec && el.row(rec.dataset.id);
    if (row) openInRerun(a, row);
  }, true);
  // §52.7's `columnClick: sort`, host-side: a plain header click sorts (ASC, DESC, off: the table's own shift-click
  // rule, the same host.setView), and the header's ⋯ still opens Notion's column menu. WHY: on this page sorting is
  // the act ("sorting the table" was one of Zach's likes), and data-ui's default puts it one menu away
  el.addEventListener('click', (e) => {
    const th = e.target.closest('thead th[data-sort]');
    if (!th || !el.contains(th) || e.shiftKey || e.target.closest('[data-col-menu], .dv-resize, button, input')) return;
    e.preventDefault();
    e.stopPropagation();
    const id = th.dataset.sort;
    const sort = (el.view && el.view.sort) || [];
    const cur = sort.find((x) => x.property === id);
    const next = !cur ? 'ASC' : cur.direction === 'ASC' ? 'DESC' : null;
    el.setView({ sort: next ? [{ property: id, direction: next }] : [] });
  }, true);
  watchAnswerPill(el);
}

function openQuery(el) {
  try { el.openMenu('query'); } catch { /* an older kit: the Search icon still opens it */ }
}

/* ── the drill: data-ui's peek, with the host's pane at its foot ──────────────────────────────────────────────── */

const SIGNALS = [['q', 'position'], ['qd', 'speed'], ['qdd', 'acceleration']];

function spansHtml(row) {
  const hists = app.datasets.hists.rows;
  const joints = app.meta.joints || [];
  const setSpan = (joint, signal) => { const h = hists.find((r) => r.joint === joint && r.signal === signal); return h ? h.span_pct : null; };
  const cell = (its, set) => {
    if (its === null || its === undefined) return '<td>—</td>';
    const w = Math.max(0, Math.min(100, its)); const sw = Math.max(0, Math.min(100, set ?? 0));
    return `<td class="cv7-span"><span class="cv7-span-bar" title="it spans ${its.toFixed(1)} % of the range; the whole set ${set == null ? '—' : set.toFixed(1)} %"><i class="cv7-span-set" style="width:${sw}%"></i><i class="cv7-span-its" style="width:${w}%"></i></span><b>${Math.round(its)}</b><span class="cv7-span-of">/${set == null ? '—' : Math.round(set)}</span></td>`;
  };
  const body = joints.map((joint) => {
    const short = joint.replace(/_joint$/, '');
    return `<tr><th>${esc(short)}</th>${SIGNALS.map(([s]) => cell(row[`${short}_${s}_span_pct`], setSpan(joint, s))).join('')}</tr>`;
  }).join('');
  return `<table class="cv7-spans"><thead><tr><th></th>${SIGNALS.map(([s, w]) => `<th>${s} · ${w}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>
    <p class="cv7-drill-key"><i class="cv7-key-its"></i> it · <i class="cv7-key-set"></i> every trajectory together · numbers: its % / the set's %, of the range between the data's p0.1 and p99.9 (payload span_pct)</p>`;
}

function drillHtml(row) {
  const num = (v, d, unit) => (v === null || v === undefined ? '—' : `${Number(v).toFixed(d)}${unit}`);
  const tiles = [
    ['Samples', num(row.samples, 0, '')], ['Tool speed, max', num(row.tool_speed_max_m_s, 2, ' m/s')],
    ['Tool height', `${num(row.tool_z_min_m, 2, '')}–${num(row.tool_z_max_m, 2, ' m')}`], ['Tilt, max', num(row.tool_tilt_max_deg, 0, '°')],
  ];
  return `<section class="cv-drill" data-drill="${esc(row.name)}">
    <h3>Its numbers</h3>
    <div class="cv7-drill-tiles">${tiles.map(([l, v]) => `<div><span>${esc(l)}</span><b>${esc(v)}</b></div>`).join('')}</div>
    <h3>What it alone adds to the set</h3>
    <div class="cv-drill-adds">
      <div><b>${esc(row.new_cells)}</b><span>q×qd cells it was first to visit (in file order)</span></div>
      <div><b>${esc(row.only_it_q_qd_cells)}</b><span>q×qd cells only it visits: drop it and they are gone</span></div>
      <div><b>${esc(Number(row.tool_path_m).toFixed(2))} m</b><span>tool path, ${esc(Number(row.duration_s).toFixed(2))} s</span></div>
    </div>
    <div class="cv-drill-joints"></div>
    <h3>Its tool path, over every trajectory</h3>
    <div class="cv-drill-proj"></div>
    <h3>Its joints over time <span class="cv7-drill-sub">every sample, from data/samples.json; colour = joint</span></h3>
    <div class="cv7-drill-motion" data-drill-motion><p class="cv7-drill-wait">Loading its samples…</p></div>
    <h3>How much of each joint's range it spans, against the whole set</h3>
    ${spansHtml(row)}
  </section>`;
}

async function mountDrill(el, row) {
  const box = el.querySelector(`.cv-drill[data-drill="${CSS.escape(row.name)}"]`);
  if (!box) return;
  if (!app.motion) app.motion = await fetch(here('rows/motion.json')).then((r) => r.json());
  const motion = app.motion[row.name];
  if (!motion || !box.isConnected) return;
  // through data-ui's registry, so the bundle's stylesheet is in the page even when no dashboard page drew a coverage view yet
  const [{ View: Projection }, { View: Plane }] = await Promise.all([loadView('coverage-projection'), loadView('coverage-plane')]);
  const tokens = el.tokens();
  const host = { element: el, setView() {}, open() {}, setStatus() {} };
  const style = { ...(app.base.style || {}), ...app.settings.value };
  // its cells per joint (membership) and the cells only it visits (it visits them and the payload's paths there is 1)
  const rows = app.datasets.planes.rows.filter((r) => r.grid === 'q_qd').sort((a, b) => a.joint_order - b.joint_order);
  const own = {};
  let only = 0;
  for (const r of rows) {
    const cells = Query.cells(row.name, `plane/${r.joint}/q_qd`) || [];
    const mine = cells.filter((c) => r.paths[c] === 1);
    only += mine.length;
    own[r.joint] = { cells, only: mine };
  }
  // the oracle: the ink must count exactly the table's "Only it" (extract.py's own count); a mismatch is an error
  if (only !== row.only_it_q_qd_cells) console.error(`drill ${row.name}: ${only} only-it cells from membership, the table says ${row.only_it_q_qd_cells}`);
  const jointsEl = box.querySelector('.cv-drill-joints');
  jointsEl.classList.add('dv-view');
  const plane = new Plane(host, jointsEl);
  const overlay = Object.fromEntries(Object.entries(motion.joint_paths).map(([joint, p]) => [joint, [p[0], p[1]]]));
  plane.update({ rows, tokens, view: { style, coverage: { muted: true, own, overlay, columns: 3, title: 'joint_short', switch: false } } });
  const projEl = box.querySelector('.cv-drill-proj');
  projEl.classList.add('dv-view');
  const proj = new Projection(host, projEl);
  proj.update({ rows: app.datasets.projections.rows, tokens, view: { style, coverage: { muted: true, switch: false, overlay: motion.tool_path } } });
  mountMotion(box.querySelector('[data-drill-motion]'), row);
}

/* its joints over time: two stock data-ui `chart` views (Vega-Lite) on its own samples, colour = joint with its legend */
async function mountMotion(slot, row) {
  if (!slot) return;
  try {
    if (!app.samples) app.samples = fetch(here('../data/samples.json')).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); });
    const all = await app.samples;
    if (!slot.isConnected) return;
    const mine = all.filter((s) => s.trajectory === row.name);
    const joints = (app.meta.joints || []).map((j) => j.replace(/_joint$/, ''));
    const long = [];
    for (const s of mine) for (const j of joints) long.push({ t_s: s.t_s, joint: j, q_deg: s[`${j}_q_deg`], qd_deg_s: s[`${j}_qd_deg_s`] });
    const data = {
      id: `drill-motion-${row.name}`, title: `${row.name} motion`, titleProperty: 'joint',
      properties: { t_s: { type: 'number', label: 't', unitText: 's' }, joint: { type: 'text', label: 'Joint' }, q_deg: { type: 'number', label: 'q', unitText: '°' }, qd_deg_s: { type: 'number', label: 'qd', unitText: '°/s' } },
      rows: long,
    };
    const chart = (field, title) => ({
      type: 'chart', name: title, status: false, controls: false,
      chart: {
        mark: { type: 'line', strokeWidth: 1.4 },
        encoding: {
          x: { field: 't_s', type: 'quantitative', title: 't (s)' },
          y: { field, type: 'quantitative', title },
          color: { field: 'joint', type: 'nominal', title: null, sort: joints },
        },
      },
    });
    slot.innerHTML = `<p class="cv7-drill-sub">${mine.length} samples on its own clock (not subsampled)</p>`;
    for (const [field, title] of [['q_deg', 'q (°)'], ['qd_deg_s', 'qd (°/s)']]) {
      const v = document.createElement('data-views');
      for (const [k, val] of [['toolbar', 'none'], ['status', 'off'], ['controls', 'off'], ['no-url', '']]) v.setAttribute(k, val);
      v.className = 'cv7-drill-chart';
      v.base = { views: [chart(field, title)] };
      v.data = data;
      slot.append(v);
    }
  } catch (error) {
    slot.innerHTML = `<p class="cv7-drill-wait">Its samples could not load (${esc(error.message)}); serve the round with traj_compare.serve, or open it in Rerun.</p>`;
  }
}

async function openInRerun(link, row) {
  const rec = link.closest('.dv-open-rec');
  let msg = rec.querySelector('.cv-rerun-cmd');
  if (!msg) {
    msg = document.createElement('div');
    msg.className = 'cv-rerun-cmd';
    msg.setAttribute('role', 'status');
    const actions = rec.querySelector('.dv-open-actions');
    (actions || link).insertAdjacentElement('afterend', msg);
  }
  link.classList.add('cv-rerun-busy');
  msg.className = 'cv-rerun-cmd cv-ok';
  msg.textContent = `Opening ${row.name} in Rerun…`;
  // the by-hand command: on file:// the page's own path is the file system's; served, the round's folder (V5's rule)
  const file = location.protocol === 'file:' ? decodeURIComponent(new URL(`../${row.rrd}`, location.href).pathname) : `${ROUND_DIR}/${row.rrd}`;
  const fallback = `uvx --from rerun-sdk==0.40.0 rerun ${file}`;
  const copy = (command) => {
    msg.querySelector('[data-copy]').addEventListener('click', (e) => {
      navigator.clipboard?.writeText(command).then(() => { e.target.textContent = 'Copied'; }).catch(() => { e.target.textContent = 'Select and copy'; });
    });
  };
  try {
    const res = await fetch(`/__rerun/open?rrd=${encodeURIComponent(row.rrd)}`, { method: 'POST' });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.ok) throw Object.assign(new Error(body.error || `HTTP ${res.status}`), { command: body.command });
    // V6's rule: say what ran, with the command and Copy, so it can be run again by hand. The server's own command
    // when it sent one; else (a server that answers without one) the round's pinned rerun-sdk on the file's path.
    const command = /^(uvx|rerun|python)/.test(String(body.command || '')) ? body.command : fallback;
    msg.innerHTML = `Rerun is opening <b>${esc(row.name)}</b> in its own window${body.command && body.command !== command ? ` (the server: ${esc(body.command)})` : ''}. To run it yourself:<code>${esc(command)}</code><button type="button" class="dv-btn" data-copy>Copy</button>`;
    copy(command);
  } catch (error) {
    const command = error.command || fallback;
    msg.className = 'cv-rerun-cmd';
    msg.innerHTML = `Could not start Rerun from this page (${esc(error.message)}). Run it yourself:<code>${esc(command)}</code><button type="button" class="dv-btn" data-copy>Copy</button>`;
    copy(command);
  } finally {
    link.classList.remove('cv-rerun-busy');
  }
}

boot().catch((error) => {
  console.error(error);
  document.getElementById('pages').innerHTML = `<p class="cv-page-error">The coverage page could not start: ${esc(error.message)}</p>`;
});
