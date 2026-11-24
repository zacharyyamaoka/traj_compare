/* component.js — P2 "The rail holds the tabs": one left column does both jobs (VS Code's activity bar + side bar,
 * Linear's sidebar). At its top the list of dashboards (vertical tabs: one click each, the open one marked), under it
 * the filters (Dataset first). The main pane is only the open dashboard, under one quiet line that names it, says how
 * many rows the filter leaves and lists the picks. No horizontal tab strip anywhere, so the component is a sidebar plus
 * a canvas and drops into any app's slot.
 *
 * Generic: it knows a `.base` document and its rows, nothing about robots. Every part is stock data-ui —
 *   <data-rail>    the dashboard list (§27): icons, labels, the open one, ↑/↓, collapsed ↔ wide
 *   <data-facets>  the filters (§7), editing the one all-views filter
 *   <data-views>   the open dashboard, toolbar="none" (§47): its presets ARE the dashboards; selectView() switches
 *   makeResizable  the column's right edge (§11)
 * — and this file is the glue a second app would otherwise copy: it lists the views in the rail, follows the open one,
 * puts the facets under the rail, folds the column to an icon strip when the component is narrow (the filters then
 * open as a panel inside it), and hosts one gear. NOTES.md names the data-ui API that would replace it.
 *
 *   const dash = mountRailDashboards(root, {id, base, data, title, icons, settings: {label, build(body)}});
 *   dash.views   // the <data-views>; dash.rail, dash.facets
 */

import { makeResizable, toRail, railConfig, facetSpecs } from '../../vendor/data-ui/data-ui.js';

const svg = (body, cls = '') => `<svg class="${cls}" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

// lucide (ISC) icon bodies by the names a view's `icon:` uses
export const ICONS = {
  'layout-dashboard': '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
  grid: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
  crosshair: '<circle cx="12" cy="12" r="10"/><path d="M22 12h-4M6 12H2M12 6V2M12 22v-4"/>',
  'map-pin': '<path d="M20 10c0 5-5.5 10.2-7.4 11.8a1 1 0 0 1-1.2 0C9.5 20.2 4 15 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
  compass: '<path d="m16.24 7.76-1.8 5.41a2 2 0 0 1-1.27 1.27L7.76 16.24l1.8-5.41a2 2 0 0 1 1.27-1.27z"/><circle cx="12" cy="12" r="10"/>',
  table: '<path d="M12 3v18"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M3 15h18"/>',
  filter: '<path d="M22 3H2l8 9.46V19l4 2v-8.54z"/>',
  gear: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  pages: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
};

const esc = (text) => String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const slug = (text) => String(text).trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const plural = (n, one, many) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

/**
 * Mount the component into `root` (any element; the component fills it).
 * @param {HTMLElement} root
 * @param {{id: string, base: object, baseText?: string, data: object, title?: string, noun?: [string, string],
 *          icons?: object, collapseBelow?: number, noUrl?: boolean, settings?: {label: string, build: Function}}} opts
 */
export function mountRailDashboards(root, opts) {
  const icons = { ...ICONS, ...(opts.icons || {}) };
  const iconOf = (name) => svg(icons[name] || icons.table);
  const [one, many] = opts.noun || ['row', 'rows'];
  const pages = opts.base.views.filter((view) => view.rail !== false);
  const id = opts.id;
  const collapseBelow = opts.collapseBelow || 1100;

  root.classList.add('p2');
  root.setAttribute('data-p2-root', '');
  root.innerHTML = `
    <aside class="p2-side" aria-label="Dashboards and filters">
      <div class="p2-side-scroll">
        <div class="p2-pages" data-resizable="off">
          <data-rail id="${id}-rail" mode="wide" storage-key="${id}-pages" brand="${esc(opts.title || 'Dashboards')}" label="Dashboards" hotkey="off" theme="light">
            <span data-brand-icon>${svg(icons.pages)}</span>
            ${pages.map((view) => `<a href="#view=${slug(view.name)}" data-id="${slug(view.name)}">${iconOf(view.icon)}${esc(view.name)}</a>`).join('')}
          </data-rail>
        </div>
        <button type="button" class="p2-filter-btn" aria-expanded="false" aria-controls="${id}-filters" title="Filters" data-p2-filter-btn>
          ${svg(icons.filter)}<span class="p2-filter-word">Filters</span><span class="p2-badge" data-p2-badge hidden></span>
        </button>
        <section class="p2-filters" id="${id}-filters" aria-label="Filters" data-p2-filters>
          <header class="p2-filters-head">
            <b>Filters</b><span class="p2-filters-count" data-p2-filter-count></span>
            <button type="button" class="p2-link" data-p2-clear hidden>Clear</button>
            <button type="button" class="p2-x" data-p2-filters-close aria-label="Close the filters" title="Close (Esc)">${svg(icons.x)}</button>
          </header>
          <data-facets for="${id}" theme="light"></data-facets>
        </section>
      </div>
      <div class="p2-side-foot">
        <button type="button" class="p2-gear" aria-haspopup="dialog" aria-expanded="false" aria-controls="${id}-settings" title="${esc(opts.settings ? opts.settings.label : 'Settings')}: set once, every dashboard uses them" data-p2-gear>
          ${svg(icons.gear)}<span class="p2-gear-word">${esc(opts.settings ? opts.settings.label : 'Settings')}</span>
        </button>
      </div>
    </aside>
    <main class="p2-main">
      <header class="p2-dash-head">
        <span class="p2-dash-icon" data-p2-dash-icon></span>
        <h2 class="p2-dash-name" data-p2-dash-name></h2>
        <span class="p2-count" data-p2-count aria-live="polite"></span>
        <span class="p2-chips" data-p2-chips></span>
      </header>
      <data-views id="${id}" theme="light" toolbar="none" status="off" open="side" frame="flush"${opts.noUrl ? ' no-url' : ''}></data-views>
    </main>
    <div class="p2-settings" id="${id}-settings" role="dialog" aria-label="${esc(opts.settings ? opts.settings.label : 'Settings')}" data-p2-settings hidden>
      <div class="p2-settings-head">
        <div><b>${esc(opts.settings ? opts.settings.label : 'Settings')}</b><span>Set once: every dashboard uses them.</span></div>
        <button type="button" class="p2-x" data-p2-settings-close aria-label="Close">${svg(icons.x)}</button>
      </div>
      <div class="p2-settings-body" data-p2-settings-body></div>
    </div>`;

  const q = (sel) => root.querySelector(sel);
  const side = q('.p2-side');
  const rail = q('data-rail');
  const facets = q('data-facets');
  const views = q('data-views');
  const filterBtn = q('[data-p2-filter-btn]');
  const filterPanel = q('[data-p2-filters]');
  const gear = q('[data-p2-gear]');
  const settings = q('[data-p2-settings]');

  // a facet over a property with `colors:` shows each value's colour slot beside it (the same key as the table's badges
  // and the figures), so the dataset you tick is the colour you then see. data-ui gap: the values facet could draw it.
  const SERIES = ['#a1a1aa', '#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
  const swatches = document.createElement('style');
  swatches.textContent = Object.entries(opts.base.properties || {}).filter(([, prop]) => prop && prop.colors).flatMap(([property, prop]) =>
    Object.entries(prop.colors).map(([value, slot]) => `.p2 data-facets label:has(> input[data-p="${CSS.escape(property)}"][data-value="${String(value).replace(/["\\]/g, '\\$&')}"]) .df-label::before`
      + ` { content: ""; background: ${slot ? `var(--data-series-${slot}, ${SERIES[slot]})` : SERIES[0]}; }`)).join('\n');
  root.append(swatches);

  views.base = opts.base;
  if (opts.baseText) views.baseText = opts.baseText;
  views.data = opts.data;
  if (opts.settings && opts.settings.build) opts.settings.build(q('[data-p2-settings-body]'));

  // ── the dashboards: a rail pick opens that view; the open view marks its rail item ─────────────────────────────
  const byId = new Map(pages.map((view) => [slug(view.name), view]));
  rail.addEventListener('data-rail-navigate', (event) => {
    event.preventDefault(); // WHY: the host routes; the link stays a real one for ⌘/middle-click
    const view = byId.get(event.detail.id);
    if (view) views.selectView(view.name);
    openFilters(false);
  });

  // ── the layout: wide (labels + filters inline) or narrow (an icon strip; filters as a panel inside) ────────────
  // WHY the rail's own mode decides, and the width only flips it when it crosses the line: a container query cannot
  // set an attribute, and a reader who expands the strip (the rail's ⇥) keeps that until the component is resized
  // across `collapseBelow` again (data-rail's rule: a person's choice wins).
  let lastNarrow = null;
  const applyLayout = () => {
    const narrow = rail.mode === 'collapsed';
    root.dataset.p2Layout = narrow ? 'narrow' : 'wide';
    if (!narrow) openFilters(false);
  };
  const fit = () => {
    const narrow = root.clientWidth < collapseBelow;
    if (narrow !== lastNarrow) {
      lastNarrow = narrow;
      if (customElements.get('data-rail') && 'mode' in rail) rail.mode = narrow ? 'collapsed' : 'wide';
    }
    applyLayout();
  };
  rail.addEventListener('data-rail-mode-change', applyLayout);
  new ResizeObserver(fit).observe(root);
  customElements.whenDefined('data-rail').then(fit);
  // the column's right edge drags (data-ui §11), remembered per component; in the strip it is hidden (p2.css)
  requestAnimationFrame(() => makeResizable(side, { edge: 'right', min: 200, max: 420, keep: 480, key: `${id}-side`, label: 'the dashboards and filters' }));

  // ── the filters panel (narrow only) ─────────────────────────────────────────────────────────────────────────────
  function openFilters(open) {
    const narrow = root.dataset.p2Layout === 'narrow';
    const on = !!open && narrow;
    filterPanel.toggleAttribute('data-open', on);
    filterBtn.setAttribute('aria-expanded', String(on));
    if (on) openSettings(false);
  }
  filterBtn.addEventListener('click', () => openFilters(!filterPanel.hasAttribute('data-open')));
  q('[data-p2-filters-close]').addEventListener('click', () => { openFilters(false); filterBtn.focus(); });

  // ── the gear: one settings popover, inside the component, anchored to the gear at the column's foot ────────────
  function openSettings(open) {
    settings.hidden = !open;
    gear.setAttribute('aria-expanded', String(open));
    if (open) {
      openFilters(false);
      const frame = root.getBoundingClientRect();
      const at = gear.getBoundingClientRect();
      settings.style.left = `${Math.round(Math.min(at.right - frame.left + 8, frame.width - settings.offsetWidth - 8))}px`;
      settings.style.bottom = `${Math.round(Math.max(8, frame.bottom - at.bottom))}px`;
      const first = settings.querySelector('select, input, button:not(.p2-x)');
      if (first) first.focus();
    }
  }
  gear.addEventListener('click', () => openSettings(settings.hidden));
  q('[data-p2-settings-close]').addEventListener('click', () => { openSettings(false); gear.focus(); });
  root.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!settings.hidden) { openSettings(false); gear.focus(); event.stopPropagation(); } else if (filterPanel.hasAttribute('data-open')) { openFilters(false); filterBtn.focus(); event.stopPropagation(); }
  });
  // WHY on the document too: check.cjs and a keyboard user press Escape with focus on the select inside the popover
  // (inside root) or on the page body after a click elsewhere
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !settings.hidden) openSettings(false); });
  document.addEventListener('pointerdown', (event) => {
    if (!settings.hidden && !settings.contains(event.target) && !gear.contains(event.target)) openSettings(false);
    if (filterPanel.hasAttribute('data-open') && !filterPanel.contains(event.target) && !filterBtn.contains(event.target)) openFilters(false);
  });

  // ── the line over the dashboard: its name, how many rows the filter leaves, the picks (removable) ──────────────
  const count = q('[data-p2-count]');
  const chips = q('[data-p2-chips]');
  const badge = q('[data-p2-badge]');
  const filterCount = q('[data-p2-filter-count]');
  const clear = q('[data-p2-clear]');
  const labelOf = (property) => {
    const prop = opts.base.properties && opts.base.properties[property];
    const facet = (opts.base.facets || []).find((spec) => spec === property || spec.property === property);
    return (facet && facet.label) || (prop && prop.displayName) || property;
  };
  function picks() {
    // the rail's own reading of the all-views filter (data-ui facets.js): {facets: {property: pick}, rest: [clauses]}
    try {
      const specs = facetSpecs(opts.base, views.view, views.model ? views.model.columns : {});
      return toRail(views.filters, railConfig(specs));
    } catch (error) { return { facets: {}, rest: [] }; }
  }
  function describe(facetsState) {
    const out = [];
    for (const [property, pick] of Object.entries(facetsState || {})) {
      if (!pick) continue;
      const parts = [];
      if (Array.isArray(pick.values) && pick.values.length) parts.push(pick.values.join(', '));
      if (Array.isArray(pick.exclude) && pick.exclude.length) parts.push(`not ${pick.exclude.join(', ')}`);
      if (pick.min !== undefined || pick.max !== undefined) parts.push(`${pick.min ?? '…'} – ${pick.max ?? '…'}`);
      for (const key of ['text', 'search', 'contains', 'startsWith']) if (typeof pick[key] === 'string' && pick[key]) parts.push(`“${pick[key]}”`);
      if (pick.has) parts.push('has a value');
      out.push({ property, label: labelOf(property), text: parts.join(' · ') || 'set' });
    }
    return out;
  }
  function paintHead() {
    const model = views.model;
    if (!model) return;
    const n = model.rows.length;
    const total = model.total;
    const view = views.view || {};
    q('[data-p2-dash-name]').textContent = view.name || '';
    q('[data-p2-dash-icon]').innerHTML = iconOf(view.icon);
    rail.current = slug(view.name || '');
    count.innerHTML = `<b>${n.toLocaleString('en-US')}</b> of ${plural(total, one, many)}`;
    count.classList.toggle('p2-count-sub', n !== total);
    count.title = n === total ? `Nothing is filtered: every dashboard draws all ${total}` : `Every dashboard draws these ${n} (the rail's filters)`;
    const state = picks();
    const list = describe(state.facets);
    const extra = Array.isArray(state.rest) ? state.rest.length : 0;
    chips.innerHTML = list.map((pick) => `<span class="p2-chip" title="${esc(pick.label)}: ${esc(pick.text)}"><span class="p2-chip-k">${esc(pick.label)}</span> ${esc(pick.text)}</span>`).join('')
      + (extra ? `<span class="p2-chip">+${extra} custom</span>` : '');
    const active = list.length + extra;
    badge.hidden = !active;
    badge.textContent = String(active);
    filterBtn.title = active ? `Filters: ${active} active · ${n} of ${total} ${many}` : 'Filters';
    filterCount.textContent = `${n.toLocaleString('en-US')} of ${total.toLocaleString('en-US')}`;
    clear.hidden = !active;
    root.dataset.p2Filtered = active ? 'yes' : 'no';
  }
  clear.addEventListener('click', () => { views.filters = { and: [] }; });
  views.addEventListener('data-views-change', () => queueMicrotask(paintHead));
  views.addEventListener('data-views-render', paintHead);

  return { root, views, rail, facets, openFilters, openSettings, paintHead };
}
