/* scope.js — P5's proposal for data-ui, built as a prototype on top of the vendored build (vendor/data-ui, main 2f08a88).
 *
 * "A filter scope; the host composes." One context element holds the rows and the one filter; every data-ui element
 * inside it shares them, and the host lays the pieces out however its app needs:
 *
 *   <data-scope>      the rows (`data`), the document (`base`: facets, properties, views, and two new keys, `dashboards:`
 *                     and `settings:`) and the ONE filter (`filters`). It wears the surface <data-facets> already reads
 *                     from a <data-views> (data, base, view, filters, model, dataRevision, data-views-change), so the
 *                     stock rail binds to it unchanged. It hands the filter to every part inside it.
 *   <data-tabs>       one row of tabs over the scope's pages: any element inside the scope with a `tab="Name"` attribute
 *                     (a <data-dashboard>, a <data-views>, a host <section>). One is shown; the filter is the scope's,
 *                     so switching keeps it.
 *   <data-count>      "28 of 212 trajectories": what the filter leaves, on every page.
 *   <data-fold>       wraps a part (the rail). Wide, it is the part; when the scope's box is narrow (a container query,
 *                     not the viewport) it folds to a "Filters · 3" chip whose panel opens INSIDE the scope.
 *   <data-settings>   one gear: the controls `settings:` declares, set once per scope; views read scope.settings and
 *                     hear `data-scope-settings`.
 *
 * Existing elements opt in by being inside a scope, through surfaces they already have:
 *   <data-facets>     (no `for=`) binds to the nearest scope. Today: `for=` or the closest <data-views>; here the scope
 *                     gives it `for=<scope id>`. Core: `this.closest('data-scope, data-views')`.
 *   <data-dashboard tab="Overview">  with no `src`: the scope loads `dashboards.Overview` over its own views and rows
 *                     (load(base, datasets), CONTRACT §17) and keeps its default dataset's rail = the scope's filter
 *                     (setRail). It draws no rail of its own: the document gives it no facets.
 *   <data-views tab="Trajectories" view="Trajectories">  with no data of its own: the scope hands it data, base and
 *                     filters (CONTRACT §6's properties).
 *
 * Pages load the first time they are shown (a dashboard never opened costs nothing) and catch up with the filter when
 * shown again, so a filter change repaints only what is on screen.
 */

import { rowModel, normalizeDataset, filterList, toRail, railConfig, facetSpecs, properties as labelled, esc, fmtNum } from '../../vendor/data-ui/data-ui.js';
import '../../vendor/data-ui/dashboard.js';

const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const ROWS = 'rows';
let made = 0;

function store(kind, id) {
  return {
    get() { try { return JSON.parse(globalThis[kind].getItem(id) || 'null'); } catch { return null; } },
    set(value) { try { globalThis[kind].setItem(id, JSON.stringify(value)); } catch { /* a private window forgets it */ } },
  };
}

export class DataScope extends HTMLElement {
  constructor() {
    super();
    this._filters = undefined;
    this._rev = 0;
    this._settings = {};
  }

  connectedCallback() {
    if (!this.id) this.id = `data-scope-${++made}`;
    this.classList.add('data-ui');
    this._wire();
  }

  // ── what <data-facets> reads (the surface of <data-views> and <data-dashboard-source>) ──────────────────────────
  get data() { return this._data; }
  set data(value) { this._data = value ? normalizeDataset(value) : null; this._rev += 1; this._recompute(); this._wire(true); }
  get base() { return this._base; }
  set base(value) {
    this._base = value;
    const saved = store('localStorage', `data-scope/${this.id}/settings`).get() || {};
    this._settings = {};
    for (const s of (value && value.settings) || []) this._settings[s.key] = s.key in saved ? saved[s.key] : s.default;
    this._recompute();
    this._wire(true);
  }
  /** The scope draws no view of its own; the rail counts over every row (its `view` has no filters). */
  get view() { return SCOPE_VIEW; }
  get filters() { return this._filters; }
  set filters(value) {
    const next = value === null || value === '' ? undefined : clone(value);
    if (same(next, this._filters)) return;
    this._filters = next;
    this._recompute();
    this._push();
    this._emit();
  }
  get model() { return this._model; }
  get dataUrl() { return this._data && this._data.url; }
  get dataRevision() { return this._rev; }
  openMenu() { /* the rail's "Edit" for custom clauses: a scope's custom clauses are its host's (or its document's) */ }

  // ── what the parts read ───────────────────────────────────────────────────────────────────────────────────────
  /** The rows the filter leaves. */
  get rows() { return this._model ? this._model.rows : []; }
  /** The filter as the rail draws it: [{property, label, text}] for every active facet (a chip's title, a summary). */
  picks() {
    if (!this._data || !this._base) return [];
    const props = labelled(this._data, this._base);
    const specs = facetSpecs(this._base, SCOPE_VIEW, props);
    const { facets, rest } = toRail(this._filters, railConfig(specs));
    const out = [];
    for (const [property, f] of Object.entries(facets)) {
      const label = (specs.find((s) => s.property === property) || {}).label || (props[property] || {}).label || property;
      const parts = [];
      if (f.values && f.values.length) parts.push(f.values.join(', '));
      if (f.exclude && f.exclude.length) parts.push(`not ${f.exclude.join(', ')}`);
      if (f.min !== undefined || f.max !== undefined) parts.push(`${f.min !== undefined ? fmtNum(f.min) : '…'} – ${f.max !== undefined ? fmtNum(f.max) : '…'}`);
      if (f.text) parts.push(`“${f.text}”`);
      if (f.has) parts.push('has a value');
      if (parts.length) out.push({ property, label, text: parts.join('; ') });
    }
    for (const clause of rest) out.push({ property: null, label: 'Custom', text: typeof clause === 'string' ? clause : JSON.stringify(clause) });
    return out;
  }
  /** How many rail groups are set (the fold chip's "Filters · 3"). */
  get active() { return this.picks().length; }

  get settings() { return { ...this._settings }; }
  setSettings(patch) {
    Object.assign(this._settings, patch);
    store('localStorage', `data-scope/${this.id}/settings`).set(this._settings);
    this.dispatchEvent(new CustomEvent('data-scope-settings', { detail: { settings: this.settings } }));
  }

  /** The pages of this scope: elements inside it with a `tab` attribute (not those of a scope nested in it). */
  get pages() { return [...this.querySelectorAll('[tab]')].filter((page) => page.closest('data-scope') === this); }
  get tab() {
    const names = this.pages.map((page) => page.getAttribute('tab'));
    return names.includes(this._tab) ? this._tab : names[0] || null;
  }
  /** Show one page by its tab name; the others are hidden. The filter is the scope's, so nothing else changes. */
  show(name) {
    const pages = this.pages;
    const page = pages.find((p) => p.getAttribute('tab') === name);
    if (!page) return;
    this._tab = name;
    store('sessionStorage', `data-scope/${this.id}/tab`).set(name);
    for (const p of pages) p.hidden = p !== page;
    this._sync(page);
    this.dispatchEvent(new CustomEvent('data-scope-tab', { detail: { tab: name } }));
  }

  // ── inside ────────────────────────────────────────────────────────────────────────────────────────────────────
  _recompute() {
    if (!this._data || !this._base) return;
    // the one row model over the scope's rows: the stock rowModel (CONTRACT §2), with the scope's filter as its
    // all-views filter; `matched` is what <data-facets> prints and <data-count> shows
    const m = rowModel(this._data, this._base, SCOPE_VIEW, { filters: this._filters ?? null });
    this._model = { rows: m.rows, matched: m.matched, total: m.total, error: m.error };
  }

  _wire(fed = false) {
    if (!this.isConnected || !this._data || !this._base) return;
    // the stock rail binds to its target by id: a <data-facets> without `for=` inside this scope gets this scope
    for (const facets of this.querySelectorAll('data-facets:not([for])')) if (facets.closest('data-scope') === this) facets.setAttribute('for', this.id);
    if (!this._first) {
      this._first = true;
      const saved = store('sessionStorage', `data-scope/${this.id}/tab`).get();
      this._tab = saved;
      // WHY data-view + data-views-render: <data-facets> waits for its target's first draw; a scope is ready once fed
      this.dataset.view = 'scope';
      this.dispatchEvent(new CustomEvent('data-views-render'));
      this.dispatchEvent(new CustomEvent('data-scope-pages'));
      this.show(this.tab);
      this._emit();
      return;
    }
    if (fed) {
      for (const page of this.pages) page._scopeLoaded = false;
      this.show(this.tab);
      this._emit();
    }
  }

  /** Every page catches up with the filter; hidden ones when they are next shown. */
  _push() {
    for (const page of this.pages) {
      page._scopeStale = true;
      if (!page.hidden) this._sync(page);
    }
  }

  _sync(page) {
    if (!this._data || !this._base) return;
    const tag = page.tagName.toLowerCase();
    if (!page._scopeLoaded) {
      page._scopeLoaded = true;
      page._scopeStale = false;
      if (tag === 'data-dashboard') {
        page.setAttribute('no-url', '');
        const entry = (this._base.dashboards || {})[page.getAttribute('tab')] || { layout: { panels: [] } };
        // a dashboard document over the scope's views and rows: its default dataset is the scope's, with the scope's
        // filter as its rail (and no facets: the scope's rail is the one rail)
        const doc = { data: `${ROWS}.json`, properties: this._base.properties, views: this._base.views, ...clone(entry), filters: clone(this._filters) };
        page.load(doc, { [ROWS]: this._data });
      } else if (tag === 'data-views') {
        page.setAttribute('no-url', '');
        page.base = { properties: this._base.properties, views: this._base.views };
        page.filters = clone(this._filters);
        page.data = this._data;
      }
      page.dispatchEvent(new CustomEvent('data-scope-load', { bubbles: true, detail: { tab: page.getAttribute('tab') } }));
      return;
    }
    if (!page._scopeStale) return;
    page._scopeStale = false;
    if (tag === 'data-dashboard' && page.dash) page.setRail(ROWS, clone(this._filters));
    else if (tag === 'data-views') page.filters = clone(this._filters);
    else page.dispatchEvent(new CustomEvent('data-scope-change', { detail: this._detail() }));
  }

  _detail() { return { filters: clone(this._filters), matched: this._model ? this._model.matched : 0, total: this._model ? this._model.total : 0 }; }

  _emit() {
    this.dispatchEvent(new CustomEvent('data-views-change', { detail: { filters: clone(this._filters) } }));
    this.dispatchEvent(new CustomEvent('data-scope-change', { detail: this._detail() }));
  }
}

const SCOPE_VIEW = Object.freeze({ type: 'table', name: 'scope' });

/** The scope a part belongs to, once both are defined and the part is in the page. */
function scopeOf(part) { return part.closest('data-scope'); }

// ── <data-tabs> ─────────────────────────────────────────────────────────────────────────────────────────────────

export class DataTabs extends HTMLElement {
  connectedCallback() {
    this.scope = scopeOf(this);
    if (!this.scope) return;
    this.setAttribute('role', 'tablist');
    if (!this.hasAttribute('aria-label')) this.setAttribute('aria-label', 'Dashboards');
    this._draw = () => this.draw();
    for (const type of ['data-scope-tab', 'data-scope-pages']) this.scope.addEventListener(type, this._draw);
    if (!this._wired) {
      this._wired = true;
      this.addEventListener('click', (e) => { const b = e.target.closest('[data-tab]'); if (b) this.scope.show(b.dataset.tab); });
      this.addEventListener('keydown', (e) => this.key(e));
    }
    this.draw();
  }

  disconnectedCallback() { if (this.scope) for (const type of ['data-scope-tab', 'data-scope-pages']) this.scope.removeEventListener(type, this._draw); }

  draw() {
    const pages = this.scope.pages;
    const current = this.scope.tab;
    const focus = this.contains(document.activeElement);
    this.innerHTML = pages.map((page) => {
      const name = page.getAttribute('tab');
      if (!page.id) page.id = `${this.scope.id}-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
      page.setAttribute('role', 'tabpanel');
      const on = name === current;
      return `<button type="button" role="tab" class="dt-tab" data-tab="${esc(name)}" aria-selected="${on}" aria-controls="${esc(page.id)}" tabindex="${on ? 0 : -1}">${esc(name)}</button>`;
    }).join('');
    if (focus) { const on = this.querySelector('[aria-selected="true"]'); if (on) on.focus(); }
  }

  key(e) {
    const tabs = [...this.querySelectorAll('[role=tab]')];
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    const next = tabs[(to + tabs.length) % tabs.length];
    this.scope.show(next.dataset.tab);
  }
}

// ── <data-count> ────────────────────────────────────────────────────────────────────────────────────────────────

export class DataCount extends HTMLElement {
  connectedCallback() {
    this.scope = scopeOf(this);
    if (!this.scope) return;
    this.setAttribute('aria-live', 'polite');
    this._draw = () => this.draw();
    this.scope.addEventListener('data-scope-change', this._draw);
    this.draw();
  }

  disconnectedCallback() { if (this.scope) this.scope.removeEventListener('data-scope-change', this._draw); }

  draw() {
    const m = this.scope.model;
    if (!m) return;
    const one = this.getAttribute('noun') || 'row';
    const many = this.getAttribute('plural') || (one.endsWith('y') ? `${one.slice(0, -1)}ies` : `${one}s`);
    const all = m.matched === m.total;
    this.classList.toggle('dc-filtered', !all);
    this.innerHTML = `<b>${m.matched.toLocaleString()}</b> of ${m.total.toLocaleString()} ${esc(m.total === 1 ? one : many)}`;
    const picks = this.scope.picks();
    this.title = all ? `Nothing is filtered: every dashboard shows all ${m.total}` : `Every dashboard shows these ${m.matched}:\n${picks.map((p) => `${p.label}: ${p.text}`).join('\n')}`;
  }
}

// ── <data-fold> ─────────────────────────────────────────────────────────────────────────────────────────────────

const FUNNEL = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 3h12l-4.6 5.4V13l-2.8 1.2V8.4z"/></svg>';

export class DataFold extends HTMLElement {
  connectedCallback() {
    this.scope = scopeOf(this);
    if (!this._built) {
      this._built = true;
      const label = this.getAttribute('label') || 'Filters';
      const body = document.createElement('div');
      body.className = 'fold-body';
      body.id = `${(this.scope && this.scope.id) || 'scope'}-fold-${Math.random().toString(36).slice(2, 7)}`;
      body.setAttribute('role', 'region');
      body.setAttribute('aria-label', label);
      body.append(...this.childNodes);
      const head = document.createElement('div');
      head.className = 'fold-head';
      head.innerHTML = `<b>${esc(label)}</b><span class="fold-head-n"></span><button type="button" class="fold-x" aria-label="Close ${esc(label)}">✕</button>`;
      body.prepend(head);
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'fold-chip';
      chip.setAttribute('aria-expanded', 'false');
      chip.setAttribute('aria-controls', body.id);
      chip.innerHTML = `${FUNNEL}<span class="fold-label">${esc(label)}</span><span class="fold-n"></span>`;
      this.append(chip, body);
      this.chip = chip;
      this.body = body;
      chip.addEventListener('click', () => this.toggle());
      head.querySelector('.fold-x').addEventListener('click', () => { this.toggle(false); chip.focus(); });
      this._key = (e) => { if (e.key === 'Escape' && this.hasAttribute('open')) { this.toggle(false); this.chip.focus(); } };
      this._outside = (e) => { if (this.hasAttribute('open') && !this.contains(e.target)) this.toggle(false); };
    }
    document.addEventListener('keydown', this._key);
    document.addEventListener('pointerdown', this._outside);
    if (this.scope) { this._draw = () => this.draw(); this.scope.addEventListener('data-scope-change', this._draw); }
    this.draw();
  }

  disconnectedCallback() {
    document.removeEventListener('keydown', this._key);
    document.removeEventListener('pointerdown', this._outside);
    if (this.scope && this._draw) this.scope.removeEventListener('data-scope-change', this._draw);
  }

  /** Folded = the chip is showing (the scope's box is narrow, or fold="always"); decided by CSS container queries. */
  get folded() { return !!this.chip && getComputedStyle(this.chip).display !== 'none'; }

  toggle(open = !this.hasAttribute('open')) {
    this.toggleAttribute('open', open);
    this.chip.setAttribute('aria-expanded', String(open));
    if (open) { const first = this.body.querySelector('input, button:not(.fold-x), select'); if (first) first.focus({ preventScroll: true }); }
  }

  draw() {
    if (!this.scope || !this.chip) return;
    const picks = this.scope.picks();
    const n = picks.length;
    this.chip.classList.toggle('fold-on', n > 0);
    this.chip.querySelector('.fold-n').textContent = n ? ` · ${n}` : '';
    this.body.querySelector('.fold-head-n').textContent = n ? `${n} set` : 'none set';
    this.chip.title = n ? picks.map((p) => `${p.label}: ${p.text}`).join('\n') : 'No filter: every dashboard shows every row';
  }
}

// ── <data-settings> ─────────────────────────────────────────────────────────────────────────────────────────────

const GEAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>';

export class DataSettings extends HTMLElement {
  connectedCallback() {
    this.scope = scopeOf(this);
    if (!this.scope) return;
    if (!this._built) {
      this._built = true;
      const id = `${this.scope.id}-settings`;
      this.innerHTML = `<button type="button" class="ds-gear" aria-label="Settings" aria-haspopup="dialog" aria-expanded="false" aria-controls="${id}" title="Settings: set once, every dashboard in this view uses them">${GEAR}</button>
        <div class="ds-pop" id="${id}" role="dialog" aria-label="Settings" hidden></div>`;
      this.gear = this.querySelector('.ds-gear');
      this.pop = this.querySelector('.ds-pop');
      this.gear.addEventListener('click', () => this.open(this.pop.hidden));
      this.pop.addEventListener('change', (e) => {
        const c = e.target.closest('[data-setting]');
        if (!c) return;
        this.scope.setSettings({ [c.dataset.setting]: c.type === 'checkbox' ? c.checked : c.value });
        this.paint();
      });
      this.pop.addEventListener('click', (e) => { if (e.target.closest('.ds-x')) { this.open(false); this.gear.focus(); } });
      this._key = (e) => { if (e.key === 'Escape' && !this.pop.hidden) { this.open(false); this.gear.focus(); } };
      this._outside = (e) => { if (!this.pop.hidden && !this.contains(e.target)) this.open(false); };
    }
    document.addEventListener('keydown', this._key);
    document.addEventListener('pointerdown', this._outside);
    this._paint = () => this.paint();
    this.scope.addEventListener('data-scope-change', this._paint);
    this.paint();
  }

  disconnectedCallback() {
    document.removeEventListener('keydown', this._key);
    document.removeEventListener('pointerdown', this._outside);
    if (this.scope) this.scope.removeEventListener('data-scope-change', this._paint);
  }

  open(on) {
    this.pop.hidden = !on;
    this.gear.setAttribute('aria-expanded', String(on));
    if (on) { this.paint(); const first = this.pop.querySelector('select, input'); if (first) first.focus(); }
  }

  paint() {
    const base = this.scope.base;
    if (!base || this.pop.hidden) return;
    const now = this.scope.settings;
    const field = (s) => {
      const v = now[s.key];
      if (s.as === 'toggle') return `<label class="ds-check"><input type="checkbox" data-setting="${esc(s.key)}"${v ? ' checked' : ''}> ${esc(s.label)}</label>`;
      const options = (s.options || []).map((o) => `<option value="${esc(o)}"${o === v ? ' selected' : ''}>${esc((s.labels && s.labels[o]) || o)}</option>`).join('');
      return `<label class="ds-field"><span>${esc(s.label)}</span><select data-setting="${esc(s.key)}" aria-label="${esc(s.label)}">${options}</select></label>`;
    };
    const extra = typeof this.describe === 'function' ? this.describe(now) : '';
    this.pop.innerHTML = `<div class="ds-head"><div><b>Settings</b><span>Set once: every dashboard in this view uses them.</span></div><button type="button" class="ds-x" aria-label="Close settings">✕</button></div>
      ${(base.settings || []).map(field).join('')}${extra}`;
  }
}

for (const [name, cls] of [['data-scope', DataScope], ['data-tabs', DataTabs], ['data-count', DataCount], ['data-fold', DataFold], ['data-settings', DataSettings]]) {
  if (!customElements.get(name)) customElements.define(name, cls);
}
