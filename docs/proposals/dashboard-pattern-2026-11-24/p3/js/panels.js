/* panels.js — `type: panels`, a dashboard as a data-ui VIEW (P3's proposal; would live at packages/views/panels/).
 *
 * P3's thesis: data-ui already has the container (one <data-views>, its view tabs, + and Save view, the one all-views
 * filter the <data-facets> rail edits). What it lacks is a view type whose entry lays out OTHER view entries. With it,
 * every dashboard is a preset, so the tabs ARE data-ui's view tabs, a reader adds a dashboard with + like any view,
 * and the rail's filter reaches every panel because every panel is drawn from the rows data-ui hands this view.
 *
 *   - type: panels
 *     name: Overview
 *     vars: [{key: joint, label: Joint, values: [..], value: elbow}]   # optional: this tab's own controls; ${joint}
 *     subset: {noun: trajectory, by: [dataset, split]}                  # optional: the line that says which rows
 *     panels:
 *       - {key: numbers, title: Headline numbers, w: 12, view: {type: numbers, …}}      # an inline view entry
 *       - {key: tool, title: The tool, w: 4, use: Tool position/tool, compact: true}   # another dashboard's panel
 *       - {key: each, repeat: dataset, w: 12, view: {type: panels, panels: […]}}        # one copy per value
 *
 * Panel keys: key, title, w (of 12 columns), view | use, open (a view name: the title opens that tab), repeat (a
 * property: one copy per value of the rows, each over that value's rows; Grafana's repeat), note. Any other key on a
 * `use:` panel overrides the entry it uses (compact: true). A panel is drawn by the registered view of its type, as
 * data-ui draws a tab: loadView(type), new View(subHost, el), update(input) with this view's input, its `view` the
 * panel's entry and its `rows` this view's rows (narrowed by `repeat`). Its host's setView writes into the panel's own
 * entry, so Save view keeps it. Every panel gets `input.settings` (the gear's, settings.js) and `input.inPanel`.
 * Generic: nothing here knows about robots or coverage.
 */

import { loadView } from '../../vendor/data-ui/data-ui.js';
import { settingsFor } from './settings.js';

const PANEL_KEYS = new Set(['key', 'title', 'w', 'view', 'use', 'open', 'repeat', 'note']);
let subsetNote = null;
/** The host app's own words beside the subset line (P3: "✓ = analyze's own counts"). */
export function setSubsetNote(fn) { subsetNote = fn; }

function h(tag, attrs, children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of [].concat(children === undefined ? [] : children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : String(child));
  }
  return node;
}

/** ${name} in every string of an entry, from the dashboard's vars (Grafana's template variables). */
function subst(value, vars) {
  if (typeof value === 'string') return value.replace(/\$\{(\w+)\}/g, (all, name) => (name in vars ? String(vars[name]) : all));
  if (Array.isArray(value)) return value.map((item) => subst(item, vars));
  if (value && typeof value === 'object') {
    const out = {};
    for (const [key, item] of Object.entries(value)) out[key] = subst(item, vars);
    return out;
  }
  return value;
}

const nounOf = (noun, n) => (n === 1 ? noun : noun.endsWith('y') ? `${noun.slice(0, -1)}ies` : `${noun}s`);

export default class PanelsView {
  constructor(host, element) {
    this.host = host;
    this.el = element;
    this.el.classList.add('p3-dashview');
    this.items = new Map();
    this.sig = '';
    this.gen = 0;
    this.closeCatalog = null;
  }

  /** The panels' entries after `use:` and ${vars}: [{panel, entry}] for one panel. */
  resolve(panel, vars, depth = 0) {
    let entry = panel.view || null;
    if (panel.use && depth < 4) {
      const at = String(panel.use).lastIndexOf('/');
      const name = panel.use.slice(0, at);
      const key = panel.use.slice(at + 1);
      const views = [...(this.host.element.presets || []), ...((this.host.element._userViews && this.host.element._userViews()) || [])];
      const source = views.find((view) => view.name === name);
      const target = source && Array.isArray(source.panels) ? source.panels.find((item) => item.key === key) : null;
      // WHY the source's vars: a panel that says ${joint} in its own dashboard draws that dashboard's current pick
      const sourceVars = Object.fromEntries(((source && source.vars) || []).map((v) => [v.key, v.value ?? (v.values || [])[0]]));
      const used = target ? this.resolve(target, sourceVars, depth + 1) : null;
      if (!used) return { error: `“${panel.use}”: no panel ${key} in a dashboard ${name}` };
      entry = { ...used };
      for (const [k, v] of Object.entries(panel)) if (!PANEL_KEYS.has(k)) entry[k] = v;
    }
    if (!entry || !entry.type) return { error: 'this panel names no view (view: {type: …} or use: <dashboard>/<panel>)' };
    return subst(entry, vars);
  }

  /** The values a `repeat:` panel repeats over, in the column's colour order, then first seen. */
  repeatValues(property, rows) {
    const seen = [];
    for (const row of rows) { const v = row[property]; if (v !== null && v !== undefined && !seen.includes(v)) seen.push(v); }
    const colors = this.colorsOf(property);
    const order = Object.keys(colors);
    return seen.sort((a, b) => (order.includes(a) ? order.indexOf(a) : 99) - (order.includes(b) ? order.indexOf(b) : 99));
  }

  colorsOf(property) {
    const column = this.input && this.input.columns && this.input.columns[property];
    const base = this.host.element.base;
    return (column && column.colors) || (base && base.properties && base.properties[property] && base.properties[property].colors) || {};
  }

  /** What to draw: one item per panel, or per value of a repeated panel. */
  plan(input) {
    const view = input.view || {};
    const vars = Object.fromEntries((view.vars || []).map((v) => [v.key, v.value ?? (v.values || [])[0]]));
    const out = [];
    for (const panel of Array.isArray(view.panels) ? view.panels : []) {
      const entry = this.resolve(panel, vars);
      const base = { panel, entry, title: subst(panel.title || '', vars), w: Math.max(1, Math.min(12, Number(panel.w) || 12)) };
      if (panel.repeat) {
        for (const value of this.repeatValues(panel.repeat, input.rows)) {
          out.push({ ...base, id: `${panel.key}=${value}`, value, rows: input.rows.filter((row) => row[panel.repeat] === value) });
        }
      } else out.push({ ...base, id: String(panel.key), rows: input.rows });
    }
    return out;
  }

  update(input) {
    this.input = input;
    const gen = ++this.gen;
    const nested = !!input.inPanel;
    if (!nested && !this.offSettings && this.host.element) {
      // the gear's settings reach every panel (the proposal: data-ui re-renders with input.settings)
      this.store = settingsFor(this.host.element);
      this.offSettings = this.store.on(() => { if (this.input) this.update(this.input); });
    }
    const settings = input.settings || (this.store ? { ...this.store.values } : (this.host.element && settingsFor(this.host.element).values));
    const plan = this.plan(input);
    const sig = JSON.stringify([input.view && input.view.name, plan.map((item) => [item.id, item.entry.type || 'error', item.w])]);
    if (sig !== this.sig) this.rebuild(plan, sig);
    if (!nested) this.drawStrip(input);
    const jobs = [];
    for (const item of plan) {
      const slot = this.items.get(item.id);
      if (!slot) continue;
      slot.titleNode.textContent = item.value !== undefined ? '' : item.title;
      if (item.value !== undefined) this.paintRepeatHead(slot, item);
      if (item.entry.error) { slot.body.replaceChildren(h('p', { class: 'p3-panel-error', text: item.entry.error })); continue; }
      const sub = {
        ...input, rows: item.rows, matched: item.rows.length, groups: null, table: null, pivot: null,
        view: Object.freeze(item.entry), settings, inPanel: true,
      };
      jobs.push(this.mount(slot, item).then((plugin) => {
        if (gen !== this.gen || !plugin) return null;
        try { return plugin.update(sub); } catch (error) { slot.body.replaceChildren(h('p', { class: 'p3-panel-error', text: String(error) })); console.error(error); return null; }
      }));
    }
    if (!plan.length && !nested) this.drawEmpty();
    return Promise.all(jobs);
  }

  /** One panel's view: loaded and constructed once per type (as <data-views> does for a tab). */
  async mount(slot, item) {
    const type = item.entry.type;
    if (slot.plugin && slot.type === type) return slot.plugin;
    if (slot.loading && slot.loadingType === type) return slot.loading;
    slot.loadingType = type;
    slot.loading = loadView(type).then(({ View }) => {
      if (slot.plugin) { try { slot.plugin.destroy(); } catch (error) { /* a view's own cleanup */ } }
      const body = h('div', { class: `dv-view dv-view-${type}` });
      slot.body.replaceChildren(body);
      slot.plugin = new View(this.subHost(item.panel), body);
      slot.type = type;
      return slot.plugin;
    }).catch((error) => { slot.body.replaceChildren(h('p', { class: 'p3-panel-error', text: `${type}: ${error.message}` })); return null; });
    return slot.loading;
  }

  /** The panel's host: data-ui's host calls, with setView writing into this panel's entry of this view. */
  subHost(panel) {
    const host = this.host;
    return {
      element: host.element,
      open: (id, opts) => host.open(id, opts),
      propose: (edit) => host.propose(edit),
      setStatus: () => {},
      setView: (patch) => {
        const panels = (this.input.view.panels || []).map((item) => (item.key !== panel.key ? item
          : item.use ? { ...item, ...patch } : { ...item, view: { ...item.view, ...patch } }));
        return host.setView({ panels });
      },
    };
  }

  rebuild(plan, sig) {
    this.sig = sig;
    for (const slot of this.items.values()) if (slot.plugin) { try { slot.plugin.destroy(); } catch (error) { /* ignore */ } }
    this.items.clear();
    const user = this.host.element.origin && this.host.element.origin.kind === 'user' && !(this.input && this.input.inPanel);
    const grid = h('div', { class: 'p3-grid' });
    for (const item of plan) {
      const titleNode = h('b', { class: 'p3-panel-title' });
      const open = item.panel.open ? h('button', { type: 'button', class: 'p3-panel-open', 'data-p3-open': item.panel.open, title: `Open the ${item.panel.open} tab`, 'aria-label': `Open the ${item.panel.open} tab`, text: 'Open ›',
        onclick: () => this.host.element.selectView(item.panel.open) }) : null;
      const remove = user ? h('button', { type: 'button', class: 'p3-panel-x', 'aria-label': 'Remove this panel', title: 'Remove this panel (Save view keeps it)', text: '✕',
        onclick: () => this.host.setView({ panels: (this.input.view.panels || []).filter((p) => p.key !== item.panel.key) }) }) : null;
      const head = h('header', { class: 'p3-panel-head' }, [titleNode, item.panel.note ? h('span', { class: 'p3-panel-note', text: item.panel.note }) : null, h('span', { class: 'p3-grow' }), open, remove]);
      const body = h('div', { class: 'p3-panel-body' });
      const section = h('section', { class: 'p3-panel' + (item.value !== undefined ? ' p3-repeat' : '') + (item.title || item.value !== undefined || open ? '' : ' p3-untitled'),
        'data-key': item.id, style: `--w:${item.w}` }, [head, body]);
      grid.append(section);
      this.items.set(item.id, { section, head, titleNode, body, plugin: null, type: null });
    }
    const nested = this.input && this.input.inPanel;
    const parts = nested ? [grid] : [h('div', { class: 'p3-strip', 'data-p3-strip': '' }), grid];
    this.el.replaceChildren(h('div', { class: 'p3-dash' + (nested ? ' p3-dash-nested' : '') }, parts));
  }

  paintRepeatHead(slot, item) {
    const slotNo = this.colorsOf(item.panel.repeat)[item.value];
    slot.section.style.setProperty('--p3-stripe', slotNo ? `var(--dv-series-${slotNo})` : 'var(--dv-border)');
    slot.titleNode.replaceChildren(h('span', { class: `dv-badge dv-h${slotNo ?? 0}`, text: String(item.value) }),
      h('span', { class: 'p3-repeat-n', text: ` ${item.rows.length} ${nounOf((this.input.view.subset || (this.host.element.base || {}).subset || {}).noun || 'row', item.rows.length)}` }));
  }

  /** The line under the bar: which rows every panel is drawing, the dashboard's own controls, Add panel. */
  drawStrip(input) {
    const strip = this.el.querySelector('[data-p3-strip]');
    if (!strip) return;
    const view = input.view || {};
    const fileBase = this.host.element.base || {};
    const subset = view.subset || fileBase.subset || {};
    const noun = subset.noun || 'row';
    const n = input.rows.length;
    const total = input.total;
    const parts = [];
    parts.push(h('span', { class: 'p3-subset', 'data-p3-subset': '' }, [
      h('span', { class: 'p3-subset-label', text: n === total ? 'all' : 'subset' }), h('b', { text: String(n) }), n === total ? ` ${nounOf(noun, total)}` : ` of ${total} ${nounOf(noun, total)}`,
      subsetNote ? subsetNote(n, total) : null]));
    // a tab that keeps its own subset (Save as tab… with the filter, or `filters:` in its entry) says so here: the pill
    // row under the bar shows only the rail's filter, which every tab shares
    const own = [].concat(view.filters ? (view.filters.and || [view.filters]) : []).map((clause) => (typeof clause === 'string'
      ? clause.replace(/^\s*[\w.]+\s*==\s*"(.*)"\s*$/, '$1') : JSON.stringify(clause)));
    if (own.length) parts.push(h('span', { class: 'p3-ownfilter', 'data-p3-own-filter': '', title: `this tab's own filters: (its .base entry), ANDed with the rail` }, [h('span', { class: 'p3-subset-label', text: 'this tab keeps' }), own.join(' · ')]));
    for (const property of subset.by || []) {
      const counts = new Map();
      for (const row of input.rows) counts.set(row[property], (counts.get(row[property]) || 0) + 1);
      const colors = this.colorsOf(property);
      const order = Object.keys(colors);
      const rank = (v) => (order.includes(v) ? order.indexOf(v) : 99);
      const values = [...counts.keys()].sort((a, b) => rank(a) - rank(b));
      const label = (input.columns[property] && input.columns[property].label) || property;
      // a dot in the column's colour slot, the value, its count: the colour key every panel's stripe and badge uses
      parts.push(h('span', { class: 'p3-composition', 'data-p3-by': property, title: `${label}: the rows every panel draws, by ${label.toLowerCase()}` },
        values.map((value) => h('span', { class: 'p3-chip', title: `${label}: ${value}, ${counts.get(value)} ${nounOf(noun, counts.get(value))}` }, [
          h('i', { class: 'p3-dot', style: `background:${colors[value] ? `var(--dv-series-${colors[value]})` : 'var(--dv-muted)'}` }),
          h('span', { class: 'p3-chip-label', text: String(value) }), h('b', { text: String(counts.get(value)) })]))));
    }
    // the dashboard's own controls (vars): drawn only on the tab that has them
    for (const spec of view.vars || []) {
      const current = spec.value ?? (spec.values || [])[0];
      const group = h('span', { class: 'p3-vars', role: 'group', 'aria-label': spec.label || spec.key, 'data-p3-vars': spec.key }, [
        h('span', { class: 'p3-vars-label', text: spec.label || spec.key })]);
      for (const value of spec.values || []) {
        group.append(h('button', { type: 'button', class: 'p3-var' + (value === current ? ' p3-on' : ''), 'aria-pressed': String(value === current), 'data-var': spec.key, 'data-value': value, text: value,
          onclick: () => { if (value !== current) this.host.setView({ vars: (view.vars || []).map((v) => (v.key === spec.key ? { ...v, value } : v)) }); } }));
      }
      parts.push(group);
    }
    parts.push(h('span', { class: 'p3-grow' }));
    parts.push(h('button', { type: 'button', class: 'p3-addpanel', 'data-p3-add-panel': '', 'aria-haspopup': 'dialog', title: 'Add a panel from any dashboard to this one',
      text: '+ Panel', onclick: (event) => this.openCatalog(event.currentTarget) }));
    strip.replaceChildren(...parts);
  }

  /** Every panel of every dashboard in the file, as `use:` entries a reader can add. */
  catalog() {
    const out = [];
    for (const view of this.host.element.presets || []) {
      if (view.type !== 'panels' || !Array.isArray(view.panels)) continue;
      for (const panel of view.panels) {
        if (panel.repeat || !panel.title || (panel.view && panel.view.type === 'coverage-key')) continue;
        const vars = Object.fromEntries((view.vars || []).map((v) => [v.key, v.value ?? (v.values || [])[0]]));
        out.push({ dashboard: view.name, key: panel.key, title: subst(panel.title, vars), w: panel.w || 6 });
      }
    }
    return out;
  }

  add(item) {
    const current = Array.isArray(this.input.view.panels) ? this.input.view.panels : [];
    let key = item.key;
    for (let k = 2; current.some((p) => p.key === key); k += 1) key = `${item.key}-${k}`;
    // WHY half width: two picks sit side by side, the way a reader composes a comparison; the .base text sets any w
    this.host.setView({ panels: [...current, { key, title: item.title, w: 6, use: `${item.dashboard}/${item.key}`, open: item.dashboard }] });
  }

  catalogHtml(onPick) {
    const list = h('div', { class: 'p3-catalog-list', role: 'list' });
    let last = null;
    for (const item of this.catalog()) {
      if (item.dashboard !== last) { list.append(h('div', { class: 'p3-catalog-group', text: item.dashboard })); last = item.dashboard; }
      list.append(h('button', { type: 'button', role: 'listitem', class: 'p3-catalog-item', 'data-p3-catalog': `${item.dashboard}/${item.key}`, text: item.title,
        onclick: () => onPick(item) }));
    }
    return list;
  }

  openCatalog(anchor) {
    if (this.closeCatalog) { this.closeCatalog(); return; }
    const dash = this.el.querySelector('.p3-dash');
    const pop = h('div', { class: 'p3-catalog p3-pop', role: 'dialog', 'aria-label': 'Add a panel' }, [
      h('div', { class: 'p3-catalog-head' }, [h('b', { text: 'Add a panel' }), h('span', { text: 'from any dashboard of this file; it draws over the same rows' })]),
      this.catalogHtml((item) => { close(); this.add(item); })]);
    dash.append(pop);
    const a = anchor.getBoundingClientRect();
    const d = dash.getBoundingClientRect();
    pop.style.top = `${a.bottom - d.top + 4}px`;
    pop.style.right = `${Math.max(4, d.right - a.right)}px`;
    anchor.setAttribute('aria-expanded', 'true');
    const onDown = (event) => { if (!pop.contains(event.target) && event.target !== anchor) close(); };
    const onKey = (event) => { if (event.key === 'Escape') close(); };
    const close = () => {
      pop.remove();
      anchor.setAttribute('aria-expanded', 'false');
      document.removeEventListener('pointerdown', onDown, true);
      document.removeEventListener('keydown', onKey, true);
      this.closeCatalog = null;
    };
    document.addEventListener('pointerdown', onDown, true);
    document.addEventListener('keydown', onKey, true);
    this.closeCatalog = close;
  }

  /** A new dashboard (+ in the bar → Dashboard) starts here: the catalog, inline. */
  drawEmpty() {
    const grid = this.el.querySelector('.p3-grid');
    if (!grid) return;
    grid.replaceChildren(h('div', { class: 'p3-empty', 'data-p3-empty': '' }, [
      h('b', { text: 'An empty dashboard.' }),
      h('p', { text: 'Pick panels from the other dashboards. Each draws over the rows the filter rail leaves; Save view keeps your pick as this tab.' }),
      this.catalogHtml((item) => this.add(item))]));
  }

  destroy() {
    if (this.offSettings) this.offSettings();
    if (this.closeCatalog) this.closeCatalog();
    for (const slot of this.items.values()) if (slot.plugin) { try { slot.plugin.destroy(); } catch (error) { /* ignore */ } }
    this.items.clear();
  }
}
