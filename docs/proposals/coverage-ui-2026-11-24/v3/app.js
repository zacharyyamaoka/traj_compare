/* app.js — V3's host: one .base, drawn by data-ui. It does four things data-ui does not do yet, each the prototype of a
 * part of PROPOSED-CONTRACT.md §52, and nothing else:
 *
 *   1. registers the four coverage view types from views/ (registerView, CONTRACT §1), one bundle ("folder": coverage);
 *   2. draws `pages:` as tabs, each page a <data-dashboard> (its panels) or a <data-views> (its saved views as tabs);
 *   3. hands the gear's settings (<data-settings>) to every page through the dashboard's style;
 *   4. fills the trajectory drill: "Open in Rerun" through el.openElsewhere (CONTRACT §46) turned into a POST, and the
 *      trajectory's motion over the set through el.peekExtra (CONTRACT §37), drawn by the same coverage views.
 */
import { registerView, parseBase, loadDataset, loadView } from '../vendor/data-ui/data-ui.js';
import '../vendor/data-ui/dashboard.js';
import './settings.js';

const TYPES = [
  ['coverage-plane', 'Coverage plane', 'grid-3x3', './views/coverage-plane.js'],
  ['coverage-hist', 'Coverage histogram', 'chart-column', './views/coverage-hist.js'],
  ['coverage-projection', 'Coverage projection', 'map', './views/coverage-projection.js'],
  ['coverage-polar', 'Coverage polar', 'compass', './views/coverage-polar.js'],
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

const app = { base: null, meta: null, datasets: {}, pages: [], current: null, settings: null, motion: null, baseUrl: here('coverage.base') };

async function boot() {
  const [text, meta] = await Promise.all([fetch(app.baseUrl).then((r) => r.text()), fetch(here('rows/meta.json')).then((r) => r.json())]);
  app.base = parseBase(text);
  app.meta = meta;
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
  document.addEventListener('data-coverage-pick', (e) => openJoint(e.detail.value));
  addEventListener('hashchange', () => { const want = pageFromHash(); if (want && want !== app.current) show(want); });
  show(pageFromHash() || 'overview');
  document.body.dataset.ready = '';
}

function pageFromHash() {
  const m = /(?:^|[#&])page=([\w-]+)/.exec(location.hash);
  return m && app.pages.some((p) => p.id === m[1]) ? m[1] : null;
}

function show(id) {
  const entry = app.pages.find((p) => p.id === id);
  if (!entry) return;
  app.current = id;
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
  try { history.replaceState(null, '', `#page=${id}`); } catch { /* file:// in some browsers */ }
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
    layout: { ...(base.layout || {}), panels: page.panels },
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

/* the Overview ridgeline's row click: the joint's own page, its rail moved to that joint (§52.5's page link) */
function openJoint(joint) {
  show('joint');
  const entry = app.pages.find((p) => p.id === 'joint');
  if (entry && entry.el && typeof entry.el.setRail === 'function') entry.el.setRail('planes', `joint == "${joint}"`);
}

/* ── the Trajectories page: data-ui's stock table, its saved views as tabs, its side peek as the drill ─────────── */

function buildViewsPage(entry) {
  const { page, section } = entry;
  const byName = new Map(app.base.views.map((v) => [v.name, v]));
  const views = page.views.map((n) => byName.get(n)).filter(Boolean);
  const data = app.datasets[views[0].from];
  const colours = (data.properties.split && data.properties.split.colors) || {};
  // G3: the one colour beside a trajectory (its split badge) keyed where it is shown, in the families' slots
  section.insertAdjacentHTML('beforeend', `<div class="cv-rowlegend" data-row-legend><span>Split badge colours, the same as the split bars on Limits:</span>${Object.entries(colours).map(([value, slot]) => `<span class="cv-sw"><i style="background:var(--data-series-${slot}, var(--dv-series-${slot}))"></i>${esc(value)}</span>`).join('')}<span>· click a row to drill in (its numbers, its motion, Open in Rerun)</span></div>`);
  const el = document.createElement('data-views');
  el.id = 'cov-trajectories';
  for (const [k, v] of [['views', 'tabs'], ['toolbar', 'bar'], ['no-url', ''], ['open', 'side'], ['filters', 'pills'], ['search', 'box'], ['view-counts', '']]) el.setAttribute(k, v);
  el.base = { properties: app.base.properties || {}, views };
  el.data = data;
  // CONTRACT §46: where else a record opens; the host's to say. Rerun's is a POST, so the click is taken over below.
  el.openElsewhere = (row) => (row && row.rrd ? { href: new URL(`../${row.rrd}`, location.href).href, label: 'Rerun' } : null);
  // CONTRACT §37: the host's own pane at the foot of the record: what it adds and its motion over the set
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
  el.addEventListener('data-views-render', () => { if (!el._drawnOnce) { el._drawnOnce = true; if (app.current === entry.id) openQuery(el); } });
  section.append(el);
  entry.el = el;
}

function openQuery(el) {
  try { el.openMenu('query'); } catch { /* an older kit: the Search icon still opens it */ }
}

function drillHtml(row) {
  return `<section class="cv-drill" data-drill="${esc(row.name)}">
    <h3>What it adds to the set</h3>
    <div class="cv-drill-adds">
      <div><b>${esc(row.new_cells)}</b><span>q×qd cells it was first to visit</span></div>
      <div><b>${esc(row.only_it_q_qd_cells)}</b><span>q×qd cells only it visits</span></div>
      <div><b>${esc(Number(row.tool_path_m).toFixed(2))} m</b><span>tool path, ${esc(Number(row.duration_s).toFixed(2))} s</span></div>
    </div>
    <h3>Its tool path, over every trajectory</h3>
    <div class="cv-drill-proj"></div>
    <h3>Its joints in position × speed, over every trajectory</h3>
    <div class="cv-drill-joints"></div>
  </section>`;
}

async function mountDrill(el, row) {
  const box = el.querySelector(`.cv-drill[data-drill="${CSS.escape(row.name)}"]`);
  if (!box) return;
  if (!app.motion) app.motion = await fetch(here('rows/motion.json')).then((r) => r.json());
  const motion = app.motion[row.name];
  if (!motion) return;
  // through data-ui's registry, so the bundle's stylesheet is in the page even when no dashboard page drew a coverage view yet
  const [{ View: Projection }, { View: Plane }] = await Promise.all([loadView('coverage-projection'), loadView('coverage-plane')]);
  const tokens = el.tokens();
  const host = { element: el, setView() {}, open() {}, setStatus() {} };
  const style = { ...(app.base.style || {}), ...app.settings.value };
  // the same stock views, handed this trajectory as an overlay (§52's `overlay`, from a layer dataset in data-ui)
  const projEl = box.querySelector('.cv-drill-proj');
  projEl.classList.add('dv-view');
  const proj = new Projection(host, projEl);
  proj.update({ rows: app.datasets.projections.rows, tokens, view: { style, coverage: { muted: true, switch: false, overlay: motion.tool_path } } });
  const jointsEl = box.querySelector('.cv-drill-joints');
  jointsEl.classList.add('dv-view');
  const plane = new Plane(host, jointsEl);
  const overlay = Object.fromEntries(Object.entries(motion.joint_paths).map(([joint, p]) => [joint, [p[0], p[1]]]));
  const rows = app.datasets.planes.rows.filter((r) => r.grid === 'q_qd').sort((a, b) => a.joint_order - b.joint_order);
  plane.update({ rows, tokens, view: { style, coverage: { muted: true, overlay, columns: 3, title: 'joint_short', switch: false } } });
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
  const fallback = `uvx --from rerun-sdk==0.40.0 rerun ${decodeURIComponent(new URL(`../${row.rrd}`, location.href).pathname)}`;
  try {
    const res = await fetch(`/__rerun/open?rrd=${encodeURIComponent(row.rrd)}`, { method: 'POST' });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.ok) throw Object.assign(new Error(body.error || `HTTP ${res.status}`), { command: body.command });
    msg.innerHTML = `Rerun is opening <b>${esc(row.name)}</b> in its own window.`;
  } catch (error) {
    const command = error.command || fallback;
    msg.className = 'cv-rerun-cmd';
    msg.innerHTML = `Could not start Rerun from this page (${esc(error.message)}). Run it yourself:<code>${esc(command)}</code><button type="button" class="dv-btn" data-copy>Copy</button>`;
    msg.querySelector('[data-copy]').addEventListener('click', (e) => {
      navigator.clipboard?.writeText(command).then(() => { e.target.textContent = 'Copied'; }).catch(() => { e.target.textContent = 'Select and copy'; });
    });
  } finally {
    link.classList.remove('cv-rerun-busy');
  }
}

boot().catch((error) => {
  console.error(error);
  document.getElementById('pages').innerHTML = `<p class="cv-page-error">The coverage page could not start: ${esc(error.message)}</p>`;
});
