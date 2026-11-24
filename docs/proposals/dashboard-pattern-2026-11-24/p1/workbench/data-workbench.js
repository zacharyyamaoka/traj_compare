/* <data-workbench src="x.base">: a prototype of ONE new data-ui element (dashboard-pattern babble, P1, 2026-11-24).

   It owns the whole "filter rail + tabbed dashboards" pattern inside its own box, so a host drops it into any app as one
   tag:

     ┌ corner: title + "28 of 212 trajectories" ┬ tab strip: Overview · One joint · … · More ▾ ┬ ⚙ ┐
     │ rail: a stock <data-facets>             │ pills: the active filter, always one line        │
     │ (the .base's facets:, Dataset first)    │ the open page: a stock <data-dashboard> (§17)     │
     └──────────────────────────────────────────┴──────────────────────────────────────────────────┘

   The .base declares everything: `data:` (the rows), `facets:` (the rail), `pages:` (one tab per page, each a §17
   `layout:` over the file's `views:`), `settings:` (behind the one gear), `drill:` (actions in a row's record pane),
   `title:` and `noun:`. Nothing here knows about robots; tools/build.mjs and ../coverage/ are the app's part.

   WHY the tab strip sits on the element and not the page (Zach, Nov 24): "I don't like the tabs here at the top top as
   then its harder to put it in another app". WHY one rail for every page: "we are filtering data and then switching
   between dashboards almost" (TensorBoard's left = which data, tabs = which dashboard).

   What is stock data-ui and what is new: every panel is a stock <data-dashboard no-url> (one per page, made the first
   time its tab opens), fed the rail's filter as its default dataset's filter (`setRail`); the rail is a stock
   <data-facets> bound to a small source element (<data-workbench-source>, the target interface data-facets already
   reads: data, base, view, filters, model). New here: the element, its tab strip with overflow into "More", the rail's
   open / narrow / folded widths, the pill line, the gear, `rowHeight: fit`, and the drill's actions.

   Drops into anything: the dashboards column is a containing block for fixed descendants (`contain: layout`), so the
   dashboard's drill sheet (position: fixed in stock data-ui) opens inside the element, and every popover is the
   element's own child. Nothing is appended to <body>. */

import { parseBase, loadDataset, rowModel, facetSpecs, railConfig, toRail, fromRail, properties as labelled, esc, valueText, slug }
  from '../../vendor/data-ui/data-ui.js';
import '../../vendor/data-ui/dashboard.js';

// the element's stylesheet (in data-ui core it would be part of data-ui.css): a <link> in <head>, which draws nothing
if (typeof document !== 'undefined' && !document.querySelector('link[data-workbench-css]')) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = new URL('./data-workbench.css', import.meta.url).href;
  link.dataset.workbenchCss = '';
  document.head.append(link);
}

const RAIL_VIEW = Object.freeze({ type: 'table', name: 'Rail' });
// WHY these widths: the rail is McMaster's ~240 px at full width; at a host slot of ~1000 px it narrows so the dashboards
// keep ~800 px; under ~860 px it folds to a button and opens over the dashboards when asked
const RAIL = { open: 248, narrow: 196, openAt: 1180, narrowAt: 860 };
const STYLE = { gap: 10, pad: 12, radius: 10 };
let count = 0;

const ICON = {
  rail: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="2.5" width="13" height="11" rx="2"/><path d="M6 2.5v11"/></svg>',
  gear: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
  chevron: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4"/></svg>',
};

function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem(key) || 'null');
    if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(value));
  } catch { /* a private window simply forgets */ }
  return null;
}

/** Pack panels into lines as the dashboard's 12-column grid flows them: [{units, panels}] (units = the tallest h). */
function lines(panels, columns) {
  const out = [];
  let line = null;
  for (const p of panels) {
    const w = Math.min(Number(p.w) || columns, columns);
    if (!line || line.used + w > columns) { line = { used: 0, units: 0, panels: [] }; out.push(line); }
    line.used += w;
    line.units = Math.max(line.units, Number(p.h) || 4);
    line.panels.push(p);
  }
  return out;
}

/** The target <data-facets for> reads (the same interface as data-dashboard's <data-dashboard-source>). */
class WorkbenchSource extends HTMLElement {
  get data() { return this._wb ? this._wb._data : null; }
  get base() { return this._wb ? this._wb._railBase : null; }
  get view() { return RAIL_VIEW; }
  get model() { return this._wb ? this._wb._model : null; }
  get filters() { return this._wb ? this._wb._filters : undefined; }
  set filters(f) { if (this._wb) this._wb.filters = f; }
  get dataUrl() { return this._wb ? this._wb._dataUrl : null; }
  openMenu() { /* the rail's "Edit" of custom clauses: the workbench has no Filter menu of its own (yet) */ }
}
if (!customElements.get('data-workbench-source')) customElements.define('data-workbench-source', WorkbenchSource);

export class DataWorkbench extends HTMLElement {
  static get observedAttributes() { return ['src']; }

  constructor() {
    super();
    this._filters = undefined;
    this._pages = [];
    this._dash = new Map(); // page slug -> {el, section, rowHeight, stale}
    this._settings = {};
  }

  // ── public API ───────────────────────────────────────────────────────────────────────────────────────────────────

  /** The rail's filter (Bases' filter tree): every page reads it. Setting it redraws the visible page now, the rest
   *  when they are opened. */
  get filters() { return this._filters; }
  set filters(f) {
    this._filters = f === null || f === '' ? undefined : f;
    this._recount();
    this._paintCount();
    this._paintPills();
    if (this._source) this._source.dispatchEvent(new CustomEvent('data-views-change', { detail: { filters: this._filters } }));
    for (const [name, d] of this._dash) {
      if (name === this._page) d.el.setRail(this._dsName, this._filters);
      else d.stale = true;
    }
    this._emit();
  }

  /** The rows the rail leaves, and how many there are of how many. */
  get model() { return this._model; }
  get rows() { return this._model ? this._model.rows : []; }

  /** The open page's name; set it to switch dashboards. */
  get page() { const p = this._pages.find((x) => x.slug === this._page); return p ? p.name : null; }
  set page(name) { const p = this._pages.find((x) => x.name === name || x.slug === name); if (p) this._show(p.slug, { focus: false }); }

  /** Component-wide settings (the .base's settings:, behind the gear). Views read them and listen for
   *  data-workbench-settings. */
  get settings() { return { ...this._settings }; }
  setSetting(key, value) {
    this._settings = { ...this._settings, [key]: value };
    store(this._key('settings'), this._settings);
    this._paintSettings();
    this.dispatchEvent(new CustomEvent('data-workbench-settings', { detail: { settings: this.settings } }));
  }

  // ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────────────

  connectedCallback() {
    if (!this._built) this._build();
    if (!this._ro) {
      this._ro = new ResizeObserver(() => this._layout());
      this._ro.observe(this);
    }
    const src = this.getAttribute('src');
    if (src && this._loadedFrom !== src) this._load();
  }

  disconnectedCallback() { if (this._ro) { this._ro.disconnect(); this._ro = null; } }

  attributeChangedCallback(name, before, after) {
    if (name === 'src' && before !== after && after && this.isConnected && this._built) this._load();
  }

  _key(part) { return `data-workbench/${this.id || this.getAttribute('src') || 'default'}/${part}`; }

  _build() {
    this._built = true;
    this._uid = `dw${++count}`;
    this.classList.add('data-ui');
    if (!this.hasAttribute('theme')) this.setAttribute('theme', 'light');
    this.innerHTML = `
      <div class="dw-head">
        <div class="dw-corner">
          <button type="button" class="dw-railbtn" aria-controls="${this._uid}-rail" aria-expanded="true">${ICON.rail}<span class="dw-railn" hidden></span></button>
          <div class="dw-what"><span class="dw-title"></span><span class="dw-count" data-dw-count aria-live="polite"></span></div>
        </div>
        <div class="dw-tabs" role="tablist" aria-label="Dashboards"></div>
        <button type="button" class="dw-gear" aria-label="Settings" aria-haspopup="dialog" aria-expanded="false" aria-controls="${this._uid}-settings" title="Settings: set once, every dashboard uses them">${ICON.gear}</button>
        <div class="dw-pop dw-moremenu" role="menu" aria-label="More dashboards" hidden></div>
        <div class="dw-pop dw-settings" id="${this._uid}-settings" role="dialog" aria-label="Settings" hidden></div>
      </div>
      <div class="dw-body">
        <aside class="dw-rail" id="${this._uid}-rail" aria-label="Filters"><data-facets for="${this._uid}-src" theme="light"></data-facets></aside>
        <div class="dw-main">
          <div class="dw-pills" aria-label="Active filter"></div>
          <div class="dw-pages"></div>
        </div>
      </div>
      <data-workbench-source id="${this._uid}-src" hidden></data-workbench-source>`;
    this._source = this.querySelector('data-workbench-source');
    this._source._wb = this;
    // WHY: data-facets waits for its target's first draw (data-views-render) unless the target says it is drawn
    this._source.dataset.view = 'rail';
    this._wire();
  }

  async _load() {
    const src = this.getAttribute('src');
    this._loadedFrom = src;
    try {
      const url = new URL(src, document.baseURI).href;
      const text = await (await fetch(url)).text();
      const base = parseBase(text);
      if (!base.data) throw new Error('a workbench .base names its rows with data:');
      this._dataUrl = new URL(base.data, url).href;
      const data = await loadDataset(this._dataUrl);
      this._base = base;
      this._srcUrl = url;
      this._data = { ...data, url: this._dataUrl };
      // the default dataset's name inside each page's dashboard: the data file's stem, as data-dashboard names it
      this._dsName = String(base.data).split('/').pop().replace(/\.[^.]+$/, '');
      this._railBase = { facets: base.facets || [], properties: base.properties || {} };
      this._filters = base.filters;
      this._pages = (base.pages || []).map((p, i) => ({ ...p, slug: slug(p.name || `page-${i + 1}`) }));
      if (!this._pages.length) throw new Error('a workbench .base lists its dashboards under pages:');
      const kept = store(this._key('settings')) || {};
      this._settings = Object.fromEntries((base.settings || []).map((s) => [s.key, kept[s.key] !== undefined ? kept[s.key] : s.default]));
      this._recount();
      this._paintStatic();
      this._paintCount();
      this._paintPills();
      this._paintSettings();
      this._source.dispatchEvent(new CustomEvent('data-views-change', { detail: { filters: this._filters } }));
      this._source.dispatchEvent(new CustomEvent('data-views-render', { detail: {} }));
      this._layout();
      const asked = this.hasAttribute('no-url') ? null : new URLSearchParams(location.hash.slice(1)).get('page');
      const first = this._pages.find((p) => p.slug === asked) || this._pages[0];
      this._show(first.slug, { focus: false });
      this.dataset.ready = '';
      this._emit();
    } catch (error) {
      console.error(`data-workbench could not load ${src}:`, error);
      this.querySelector('.dw-pages').innerHTML = `<p class="dw-err">data-workbench could not load ${esc(src)}: ${esc(error.message)}</p>`;
    }
  }

  _recount() {
    if (!this._data) return;
    this._model = rowModel(this._data, this._railBase, RAIL_VIEW, { filters: this._filters });
  }

  _emit() {
    this.dispatchEvent(new CustomEvent('data-workbench-change', {
      detail: { page: this.page, filters: this._filters, matched: this._model ? this._model.matched : 0, total: this._data ? this._data.rows.length : 0 },
    }));
  }

  // ── painting ─────────────────────────────────────────────────────────────────────────────────────────────────────

  _noun(n) {
    const noun = this._base && this._base.noun;
    const [one, many] = Array.isArray(noun) ? noun : noun ? [noun, `${noun}s`] : ['row', 'rows'];
    return n === 1 ? one : many;
  }

  _paintStatic() {
    const title = this._base.title || '';
    this.querySelector('.dw-title').textContent = title;
    this.querySelector('.dw-title').title = title;
    const strip = this.querySelector('.dw-tabs');
    strip.innerHTML = this._pages.map((p) => `<button type="button" role="tab" class="dw-tab" id="${this._uid}-tab-${p.slug}" data-dw-tab="${p.slug}" aria-selected="false" aria-controls="${this._uid}-page-${p.slug}" tabindex="-1">${esc(p.name)}</button>`).join('')
      + `<button type="button" class="dw-more" aria-haspopup="menu" aria-expanded="false" hidden><span></span>${ICON.chevron}</button>`;
    this.querySelector('.dw-pages').innerHTML = this._pages.map((p) => `<section class="dw-page" id="${this._uid}-page-${p.slug}" data-dw-page="${p.slug}" role="tabpanel" aria-labelledby="${this._uid}-tab-${p.slug}" hidden></section>`).join('');
    // the rail's values carry their column's colour (properties.<p>.colors), so the dataset key is the rail itself
    const rules = [];
    for (const facet of this._railBase.facets) {
      const p = typeof facet === 'string' ? facet : facet.property;
      const colors = p && this._railBase.properties[p] && this._railBase.properties[p].colors;
      if (!colors) continue;
      for (const [value, slot] of Object.entries(colors)) {
        if (!slot) continue;
        rules.push(`#${this.id || (this.id = this._uid)} section.df-group[data-p="${CSS.escape(p)}"] input[data-value="${CSS.escape(value)}"] + .df-label::before { width: 9px; margin-right: 6px; background: var(--dv-series-${slot}); }`);
      }
    }
    let style = this.querySelector(':scope > style[data-dw-colors]');
    if (!style) { style = document.createElement('style'); style.dataset.dwColors = ''; this.prepend(style); }
    style.textContent = rules.join('\n');
    this.toggleAttribute('data-dw-keyed', rules.length > 0);
  }

  _paintCount() {
    if (!this._model) return;
    const n = this._model.matched;
    const total = this._data.rows.length;
    const node = this.querySelector('[data-dw-count]');
    node.innerHTML = `<b>${n.toLocaleString('en-US')}</b> of ${total.toLocaleString('en-US')} ${esc(this._noun(total))}`;
    node.classList.toggle('dw-subset', n !== total);
    node.title = n === total ? 'Nothing is filtered: every dashboard draws every row' : 'Every dashboard draws these rows (the rail on the left)';
  }

  /** The active filter as one line of pills (always one line, so a page never jumps): what the rail says, readable from
   *  every tab and when the rail is folded. */
  _paintPills() {
    if (!this._data) return;
    const box = this.querySelector('.dw-pills');
    const props = labelled(this._data, this._railBase);
    const specs = facetSpecs(this._railBase, RAIL_VIEW, props);
    let rail;
    try { rail = toRail(this._filters, railConfig(specs)); } catch { rail = { facets: {}, rest: [] }; }
    this._railState = { rail, specs };
    const pills = [];
    for (const s of specs) {
      const owned = s.as === 'search' || s.as === 'has' ? s.properties : [s.property];
      const parts = [];
      for (const p of owned) {
        const f = rail.facets[p];
        if (!f) continue;
        const prop = props[p] || {};
        const colors = (this._railBase.properties[p] || {}).colors || {};
        if (f.values && f.values.length) {
          parts.push(f.values.map((v) => `${colors[v] ? `<i class="dw-dot" style="background:var(--dv-series-${colors[v]})"></i>` : ''}${esc(valueText(String(v), prop) || v)}`).join(' <span class="dw-or">or</span> '));
        }
        if (f.exclude && f.exclude.length) parts.push(`not ${f.exclude.map((v) => esc(String(v))).join(', ')}`);
        if (f.min !== undefined || f.max !== undefined) parts.push(`${f.min ?? '…'} – ${f.max ?? '…'}${s.unit ? ` ${esc(s.unit)}` : ''}`);
        if (f.text) parts.push(`“${esc(f.text)}”`);
        if (f.has) parts.push('has a value');
      }
      if (parts.length) pills.push(`<span class="dw-pill" data-dw-pill="${esc(s.key)}"><span class="dw-pill-k">${esc(s.label)}</span> ${parts.join(' · ')}<button type="button" class="dw-pill-x" data-dw-unpick="${esc(s.key)}" aria-label="Remove the ${esc(s.label)} filter" title="Remove">✕</button></span>`);
    }
    if (rail.rest && rail.rest.length) pills.push(`<span class="dw-pill">+${rail.rest.length} custom</span>`);
    const total = this._data.rows.length;
    box.innerHTML = pills.length
      ? `<span class="dw-pills-lead">Showing</span>${pills.join('')}<button type="button" class="dw-link" data-dw-clear>Clear all</button>`
      : `<span class="dw-pills-lead">No filter:</span><span class="dw-pills-none">all ${total.toLocaleString('en-US')} ${esc(this._noun(total))}, every dashboard</span>`;
    const n = Object.keys(rail.facets).length + (rail.rest ? rail.rest.length : 0);
    const badge = this.querySelector('.dw-railn');
    badge.hidden = !n;
    badge.textContent = String(n);
  }

  _paintSettings() {
    const pop = this.querySelector('.dw-settings');
    const specs = (this._base && this._base.settings) || [];
    if (!specs.length) { this.querySelector('.dw-gear').hidden = true; return; }
    const v = this._settings;
    const rows = specs.map((s) => {
      const id = `${this._uid}-set-${slug(s.key)}`;
      const label = esc(s.displayName || s.key);
      if (s.type === 'toggle') return `<label class="dw-set dw-set-toggle" for="${id}"><input type="checkbox" id="${id}" data-dw-setting="${esc(s.key)}"${v[s.key] ? ' checked' : ''}><span>${label}</span></label>`;
      if (s.type === 'slider') return `<label class="dw-set" for="${id}"><span>${label}</span><input type="range" id="${id}" data-dw-setting="${esc(s.key)}" min="${esc(s.min ?? 0)}" max="${esc(s.max ?? 100)}" step="${esc(s.step ?? 1)}" value="${esc(v[s.key] ?? s.min ?? 0)}"></label>`;
      const options = Object.entries(s.options || {}).map(([value, text]) => `<option value="${esc(value)}"${String(v[s.key]) === value ? ' selected' : ''}>${esc(text)}</option>`).join('');
      return `<label class="dw-set" for="${id}"><span>${label}</span><select id="${id}" data-dw-setting="${esc(s.key)}">${options}</select></label>`;
    });
    pop.innerHTML = `<div class="dw-pop-head"><b>Settings</b><span>Set once: every dashboard uses them. Kept in this browser.</span></div>${rows.join('')}<button type="button" class="dw-link dw-set-reset" data-dw-reset-settings>Reset to the file's defaults</button>`;
  }

  // ── pages ────────────────────────────────────────────────────────────────────────────────────────────────────────

  _show(slugName, { focus = true } = {}) {
    const page = this._pages.find((p) => p.slug === slugName);
    if (!page) return;
    this._page = page.slug;
    for (const tab of this.querySelectorAll('.dw-tab')) {
      const on = tab.dataset.dwTab === page.slug;
      tab.setAttribute('aria-selected', String(on));
      tab.tabIndex = on ? 0 : -1;
      if (on && focus) tab.focus();
    }
    for (const section of this.querySelectorAll('.dw-page')) section.hidden = section.dataset.dwPage !== page.slug;
    this._closePops();
    this._closeOverlay();
    this._layoutTabs();
    const d = this._dash.get(page.slug);
    if (!d) this._mount(page);
    else {
      if (d.stale) { d.stale = false; d.el.setRail(this._dsName, this._filters); }
      if (d.unfit) this._fit(page);
    }
    if (!this.hasAttribute('no-url')) {
      const params = new URLSearchParams(location.hash.slice(1));
      params.set('page', page.slug);
      history.replaceState(history.state, '', `#${params}`);
    }
    this._emit();
  }

  _pageBase(page, rowHeight) {
    const named = new Set();
    for (const p of (page.layout && page.layout.panels) || []) for (const v of p.views || (p.view ? [p.view] : [])) named.add(v);
    return {
      data: this._base.data,
      properties: this._base.properties,
      filters: this._filters,
      style: { ...STYLE, ...(this._base.style || {}), ...(page.style || {}) },
      views: (this._base.views || []).filter((v) => named.has(v.name)),
      layout: { ...page.layout, rowHeight, arrange: false },
    };
  }

  _mount(page) {
    const section = this.querySelector(`.dw-page[data-dw-page="${CSS.escape(page.slug)}"]`);
    const el = document.createElement('data-dashboard');
    el.setAttribute('no-url', '');
    el.id = `${this._uid}-${page.slug}`;
    section.append(el);
    const d = { el, section, rowHeight: 110, stale: false, unfit: false };
    this._dash.set(page.slug, d);
    // the drill (a row's record pane) gets the .base's drill.actions under its fields; stock data-ui's dashboard has no
    // hook for it, so the prototype wraps its drill() (in core: a `drill:` key the dashboard passes to peekExtra)
    const drill = el.drill.bind(el);
    el.drill = (...args) => {
      drill(...args);
      const sheet = el.querySelector(':scope > data-views.dd-drill');
      if (!sheet) return;
      // WHY the rail's filter on the sheet too: stock drill() clears it, so ‹ n of N › stepped through all 212 rows
      // while the dashboards showed 28; the pane steps through the subset the reader is looking at
      const again = !sheet._dwExtra || JSON.stringify(sheet.filters ?? null) !== JSON.stringify(this._filters ?? null);
      sheet._dwExtra = true;
      sheet.peekExtra = (row) => this._drillHtml(row);
      if (again) { sheet.filters = this._filters; sheet.openPeek(args[2], args[3] || {}); }
    };
    this._fit(page);
  }

  /** rowHeight: fit — the page's rows of panels share the box's height, so the same page fills a 900 px window and a
   *  680 px host slot without scrolling (min 56 px a row, then it scrolls). */
  _fit(page) {
    const d = this._dash.get(page.slug);
    if (!d) return;
    const layout = page.layout || {};
    const fit = layout.rowHeight === 'fit' || layout.rowHeight === undefined;
    if (!fit) { d.el.load(this._pageBase(page, Number(layout.rowHeight) || 110), { [this._dsName]: this._data }, { keepState: !!d.loaded }); d.loaded = true; return; }
    if (d.section.hidden || !d.section.clientHeight) { d.unfit = true; if (!d.loaded) { d.el.load(this._pageBase(page, d.rowHeight), { [this._dsName]: this._data }); d.loaded = true; } return; }
    d.unfit = false;
    const panels = (layout.panels || []).filter((p) => !p.hidden);
    const packed = lines(panels, Number(layout.columns) || 12);
    const units = packed.reduce((a, l) => a + l.units, 0) || 1;
    if (!d.loaded) { d.el.load(this._pageBase(page, d.rowHeight), { [this._dsName]: this._data }); d.loaded = true; }
    // a sized panel's outer box is h × rowHeight (its title and padding inside it), so the lines share what is left
    // of the page box after the grid's offset, the dashboard's padding and the gaps between lines
    const grid = d.el.querySelector('.dd-grid');
    const gap = Number((this._base.style || {}).gap ?? STYLE.gap);
    const top = grid ? grid.getBoundingClientRect().top - d.section.getBoundingClientRect().top + d.section.scrollTop : 0;
    const below = parseFloat(getComputedStyle(d.el).paddingBottom) || 0;
    const avail = d.section.clientHeight - top - below - 2;
    const rowHeight = Math.max(56, Math.floor((avail - gap * (packed.length - 1)) / units));
    if (Math.abs(rowHeight - d.rowHeight) >= 2) {
      d.rowHeight = rowHeight;
      d.el.load(this._pageBase(page, rowHeight), { [this._dsName]: this._data }, { keepState: true });
    }
  }

  _refit() {
    clearTimeout(this._refitTimer);
    this._refitTimer = setTimeout(() => {
      for (const page of this._pages) {
        const d = this._dash.get(page.slug);
        if (!d) continue;
        if (page.slug === this._page) this._fit(page); else d.unfit = true;
      }
    }, 120);
  }

  // ── layout: the rail's width and the tab strip's overflow, from the element's own box ──────────────────────────

  _layout() {
    if (!this._data) return;
    const width = this.clientWidth;
    const auto = width >= RAIL.openAt ? 'open' : width >= RAIL.narrowAt ? 'narrow' : 'folded';
    const asked = store(this._key('rail'));
    const mode = asked === 'folded' ? 'folded' : asked === 'shown' && auto === 'folded' ? 'overlay' : auto;
    if (this.dataset.rail !== mode) {
      this.dataset.rail = mode;
      this.style.setProperty('--dw-rail', `${mode === 'narrow' ? RAIL.narrow : RAIL.open}px`);
      const btn = this.querySelector('.dw-railbtn');
      const shown = mode !== 'folded';
      btn.setAttribute('aria-expanded', String(shown));
      btn.title = shown ? 'Hide the filters' : 'Show the filters';
      btn.setAttribute('aria-label', btn.title);
    }
    this._layoutTabs();
    const box = this.querySelector('.dw-pages');
    const h = box.clientHeight;
    const w = box.clientWidth;
    if (this._box && (Math.abs(this._box[0] - w) > 4 || Math.abs(this._box[1] - h) > 4)) this._refit();
    this._box = [w, h];
  }

  /** Every tab that fits shows; the rest fold into "N more ▾" (Notion's overflow). The open tab always shows. */
  _layoutTabs() {
    const strip = this.querySelector('.dw-tabs');
    const more = strip.querySelector('.dw-more');
    const tabs = [...strip.querySelectorAll('.dw-tab')];
    for (const tab of tabs) tab.hidden = false;
    more.hidden = true;
    const over = () => strip.scrollWidth > strip.clientWidth + 1;
    if (!over()) { this._folded = []; this.dataset.tabsFolded = '0'; strip.scrollLeft = 0; return; }
    more.hidden = false;
    const folded = [];
    const label = more.querySelector('span');
    // WHY the label inside the loop: "2 more" is wider than "1 more" only by a digit, but measuring with an empty label
    // let the strip overflow by a few px, and focusing More then scrolled the open tab half out of view
    for (let i = tabs.length - 1; i >= 0 && over(); i -= 1) {
      if (tabs[i].getAttribute('aria-selected') === 'true') continue;
      tabs[i].hidden = true;
      folded.unshift(tabs[i].dataset.dwTab);
      label.textContent = `${folded.length} more`;
    }
    strip.scrollLeft = 0;
    this._folded = folded;
    more.title = folded.map((s) => this._pages.find((p) => p.slug === s).name).join(', ');
    this.dataset.tabsFolded = String(folded.length);
  }

  // ── the drill's actions ──────────────────────────────────────────────────────────────────────────────────────────

  _drillHtml(row) {
    const actions = (this._base.drill && this._base.drill.actions) || [];
    if (!actions.length || !row) return '';
    const fill = (template, encode) => String(template).replace(/\{([^}]+)\}/g, (_, p) => (encode ? encodeURIComponent(row[p] ?? '') : String(row[p] ?? '')));
    const buttons = actions.map((a, i) => `<button type="button" class="dw-act${i ? '' : ' dw-act-main'}" data-dw-action="${i}" data-dw-row="${esc(row.id)}" title="${esc(fill(a.title || a.label, false))}">${esc(a.label)}</button>`).join('');
    return `<div class="dw-acts" data-dw-acts="${esc(row.id)}">${buttons}<span class="dw-act-status" role="status"></span></div>`;
  }

  async _act(button) {
    const action = this._base.drill.actions[Number(button.dataset.dwAction)];
    const row = this._data.rows.find((r) => String(r.id) === button.dataset.dwRow);
    const status = button.parentElement.querySelector('.dw-act-status');
    if (!action || !row) return;
    const url = String(action.post || action.href).replace(/\{([^}]+)\}/g, (_, p) => encodeURIComponent(row[p] ?? ''));
    if (!action.post) { window.open(url, '_blank', 'noopener'); return; }
    status.textContent = 'Starting…';
    try {
      const response = await fetch(url, { method: 'POST' });
      const answer = await response.json().catch(() => ({}));
      if (!response.ok || answer.ok === false) throw Object.assign(new Error(answer.error || `HTTP ${response.status}`), { command: answer.command });
      status.textContent = 'Opened ✓';
    } catch (error) {
      status.textContent = `Could not: ${error.message}${error.command ? ` · run it yourself: ${error.command}` : ''}`;
    }
  }

  // ── events ───────────────────────────────────────────────────────────────────────────────────────────────────────

  _closePops() {
    for (const pop of this.querySelectorAll('.dw-pop')) pop.hidden = true;
    for (const b of this.querySelectorAll('.dw-gear, .dw-more')) b.setAttribute('aria-expanded', 'false');
  }

  /** The rail opened over the dashboards (a narrow host) closes again on a click beside it, Escape or a tab switch. */
  _closeOverlay() {
    if (this.dataset.rail !== 'overlay') return;
    store(this._key('rail'), null);
    this._layout();
  }

  _wire() {
    this.addEventListener('click', (event) => {
      const t = event.target;
      const tab = t.closest('.dw-tab');
      if (tab) { this._show(tab.dataset.dwTab); return; }
      const more = t.closest('.dw-more');
      if (more) {
        const menu = this.querySelector('.dw-moremenu');
        const open = menu.hidden;
        this._closePops();
        if (open) {
          menu.innerHTML = (this._folded || []).map((s) => `<button type="button" role="menuitem" class="dw-menuitem" data-dw-go="${s}">${esc(this._pages.find((p) => p.slug === s).name)}</button>`).join('');
          const r = more.getBoundingClientRect();
          const host = this.getBoundingClientRect();
          menu.style.left = `${Math.max(0, Math.min(r.left - host.left, this.clientWidth - 220))}px`;
          menu.hidden = false;
          more.setAttribute('aria-expanded', 'true');
          const first = menu.querySelector('button');
          if (first) first.focus();
        }
        return;
      }
      const go = t.closest('[data-dw-go]');
      if (go) { this._show(go.dataset.dwGo); return; }
      const gear = t.closest('.dw-gear');
      if (gear) {
        const pop = this.querySelector('.dw-settings');
        const open = pop.hidden;
        this._closePops();
        pop.hidden = !open;
        gear.setAttribute('aria-expanded', String(open));
        if (open) { const first = pop.querySelector('select, input'); if (first) first.focus(); }
        return;
      }
      const railbtn = t.closest('.dw-railbtn');
      if (railbtn) {
        this._closePops();
        const shown = this.dataset.rail !== 'folded';
        store(this._key('rail'), shown ? 'folded' : 'shown');
        this._layout();
        this._refit();
        return;
      }
      const unpick = t.closest('[data-dw-unpick]');
      if (unpick && this._railState) {
        const { rail, specs } = this._railState;
        const s = specs.find((x) => x.key === unpick.dataset.dwUnpick);
        const facets = { ...rail.facets };
        for (const p of s.as === 'search' || s.as === 'has' ? s.properties : [s.property]) delete facets[p];
        this.filters = fromRail(facets, rail.rest);
        return;
      }
      if (t.closest('[data-dw-clear]') && this._railState) { this.filters = fromRail({}, this._railState.rail.rest); return; }
      if (t.closest('[data-dw-reset-settings]')) {
        for (const s of this._base.settings || []) this._settings[s.key] = s.default;
        this.setSetting(this._base.settings[0].key, this._base.settings[0].default);
        return;
      }
      const act = t.closest('[data-dw-action]');
      if (act) { this._act(act); return; }
      if (!t.closest('.dw-pop')) this._closePops();
      if (!t.closest('.dw-rail')) this._closeOverlay();
    });
    this.addEventListener('change', (event) => {
      const input = event.target.closest('[data-dw-setting]');
      if (!input) return;
      const value = input.type === 'checkbox' ? input.checked : input.type === 'range' ? Number(input.value) : input.value;
      this.setSetting(input.dataset.dwSetting, value);
    });
    this.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        const open = this.querySelector('.dw-pop:not([hidden])');
        if (open) {
          event.stopPropagation();
          const owner = open.classList.contains('dw-settings') ? this.querySelector('.dw-gear') : this.querySelector('.dw-more');
          this._closePops();
          if (owner) owner.focus();
        } else this._closeOverlay();
        return;
      }
      const tab = event.target.closest('.dw-tab');
      if (tab && (event.key === 'ArrowRight' || event.key === 'ArrowLeft')) {
        const shown = [...this.querySelectorAll('.dw-tab:not([hidden])')];
        const i = shown.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : -1);
        if (shown[i]) { event.preventDefault(); this._show(shown[i].dataset.dwTab); }
      }
    });
    // a click outside the element closes its popovers (listening on the document, never drawing there)
    document.addEventListener('pointerdown', (event) => { if (!this.contains(event.target)) { this._closePops(); this._closeOverlay(); } });
  }
}

if (!customElements.get('data-workbench')) customElements.define('data-workbench', DataWorkbench);
