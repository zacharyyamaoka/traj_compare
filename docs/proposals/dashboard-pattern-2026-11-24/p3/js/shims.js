/* shims.js — stand-ins for the five small data-ui changes P3 proposes besides `type: panels`, each written against the
 * element's DOM and public methods so a reader can see the behaviour now; each would be a few lines inside data-ui
 * (NOTES.md names where). Delete a shim the day data-ui ships its change: nothing else in P3 calls into them.
 *
 *   tabIcons          a tab, the view chip and the Add view grid show a registered view's own `icon` (registerView's),
 *                     not the table's (toolbar/icons.js layoutIcon falls back to 'table' for any type it doesn't draw)
 *   headerClickSort   header-click="sort": a click on a column header sorts (numbers high first), as Zach's live page
 *                     did; the column menu stays on Enter and in Display › Sort (V2 gap 4)
 *   facetDots         a values facet draws its column's `colors:` slot as a dot (the dataset colour key in the rail)
 *   saveWithFilter    while the all-views filter is set, the pill row ends in "Save as tab…": a view that keeps the
 *                     filter in its own `filters:` (V2 gap 6: Save view saved the view entry only)
 *   settingsGear      a top-level `settings:` in the .base draws a gear in the bar, its values every view's
 *                     input.settings (V2 gap 3: the colour map lived in a page store beside data-ui)
 */

import { viewPlugin, andFilters } from '../../vendor/data-ui/data-ui.js';
import { settingsFor } from './settings.js';

// data-ui's own 16 px strokes (packages/core/src/toolbar/icons.js), for the icon names a registered view may give
const ICON = {
  dashboard: '<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="5" height="5" rx="1"/><rect x="9" y="2.5" width="5" height="5" rx="1"/><rect x="2" y="9" width="12" height="4.5" rx="1"/></svg>',
  chart: '<svg viewBox="0 0 16 16"><path d="M2.5 2.5v11h11"/><circle cx="6" cy="9.5" r="1"/><circle cx="8.5" cy="6.5" r="1"/><circle cx="11.5" cy="4.5" r="1"/><circle cx="10.5" cy="9" r="1"/></svg>',
  kpi: '<svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M4.5 10l2.5-3 2 2 2.5-3.5"/></svg>',
  gear: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
};

const esc = (text) => String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clone = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));

/** One observer per element, one pass per task: every shim's "after data-ui drew" hook. */
function afterDraws(el, pass) {
  let queued = false;
  const run = () => { queued = false; pass(); };
  const observer = new MutationObserver(() => { if (!queued) { queued = true; queueMicrotask(run); } });
  observer.observe(el, { childList: true, subtree: true });
  el.addEventListener('data-views-render', run);
  run();
  return () => observer.disconnect();
}

// ── tabIcons ─────────────────────────────────────────────────────────────────────────────────────────────────────

function iconOf(type) {
  const plugin = viewPlugin(type);
  return plugin && ICON[plugin.icon] ? plugin.icon : null;
}

function typeOfTab(el, kind, name) {
  if (el.origin && el.origin.kind === kind && el.origin.name === name && el.view) return el.view.type;
  const list = kind === 'user' ? ((el._userViews && el._userViews()) || []) : (el.presets || []);
  const view = list.find((v) => v.name === name);
  return view ? view.type : null;
}

function paintIcon(node, name) {
  if (!node || !name || node.dataset.p3Icon === name) return;
  node.dataset.p3Icon = name;
  node.innerHTML = ICON[name];
}

export function tabIcons(el) {
  return () => {
    for (const tab of el.querySelectorAll('.dv-vtab[data-name], .dv-vm-row[data-name]')) {
      const name = iconOf(typeOfTab(el, tab.dataset.kind || 'preset', tab.dataset.name));
      if (name) paintIcon(tab.querySelector('.dv-i'), name);
    }
    const chip = el.querySelector('.dv-viewchip');
    if (chip && el.view) { const name = iconOf(el.view.type); if (name) paintIcon(chip.querySelector('.dv-i'), name); }
    for (const cell of el.querySelectorAll('.dv-layout[data-type]')) {
      const name = iconOf(cell.dataset.type);
      if (name) paintIcon(cell.querySelector('.dv-i'), name);
    }
  };
}

// ── headerClickSort (round 2's V2, app.js) ───────────────────────────────────────────────────────────────────────

export function headerClickSort(el) {
  // WHY a click on a column header sorts (and does not open data-ui's column menu): Zach likes "sorting the table" on
  // the live page, where a header click sorts; data-ui's table opens Notion's column menu on a click and sorts on a
  // shift-click. A first click sorts numbers high-first (the answer you came for) and text A-Z, a second flips it.
  el.addEventListener('click', (event) => {
    const th = event.target.closest('thead th[data-sort]');
    if (!th || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target.closest('.dv-resize, [data-col-menu], .dv-selbox')) return;
    event.stopPropagation();
    event.preventDefault();
    const property = th.dataset.sort;
    const column = el.model && el.model.columns[property];
    const current = (el.view.sort || []).find((item) => item.property === property);
    const first = column && column.type === 'number' ? 'DESC' : 'ASC';
    const direction = current ? (current.direction === 'ASC' ? 'DESC' : 'ASC') : first;
    el.setView({ sort: [{ property, direction }] });
  }, true);
}

// ── facetDots ────────────────────────────────────────────────────────────────────────────────────────────────────

export function facetDots(root, base) {
  const rules = [];
  for (const [property, spec] of Object.entries(base.properties || {})) {
    if (!spec || !spec.colors) continue;
    for (const [value, slot] of Object.entries(spec.colors)) {
      const sel = `data-facets .df-group[data-p="${property.replace(/"/g, '\\"')}"] input[data-value="${String(value).replace(/"/g, '\\"')}"] + .df-label::before`;
      rules.push(`${sel} { content: ""; background: ${slot ? `var(--dv-series-${slot})` : 'var(--dv-muted)'}; }`);
    }
  }
  const style = document.createElement('style');
  style.dataset.p3 = 'facet-dots';
  style.textContent = rules.join('\n');
  root.append(style);
}

// ── saveWithFilter ───────────────────────────────────────────────────────────────────────────────────────────────

function filterWords(el) {
  // the pill row's own words, values only: "Cell · Conveyor PnP, UR5e alone · Workspace · holdout"
  return [...el.querySelectorAll('.dv-pills .dv-pill-body')].map((b) => b.textContent.replace(/^[^:]+:\s*/, '')).join(' · ');
}

export function saveWithFilter(el, root) {
  let pop = null;
  const close = () => { if (pop) { pop.remove(); pop = null; } };
  const open = (button) => {
    close();
    const n = el.model ? el.model.matched : 0;
    pop = document.createElement('div');
    pop.className = 'p3-pop p3-savepop';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'Save as a tab');
    pop.innerHTML = `<b>Save as a tab</b>
      <label class="p3-field"><span>Name</span><input data-p3-save-name value="${esc(filterWords(el).slice(0, 48) || `${el.origin.name} (mine)`)}"></label>
      <label class="p3-check"><input type="checkbox" data-p3-save-keep checked> Keep this filter in the tab (${n} trajectories), whatever the rail says later</label>
      <p class="p3-hint">A tab of “${esc(el.origin.name)}”, saved in this browser like any data-ui view; ⋯ › Copy puts it in the .base.</p>
      <div class="p3-row"><button type="button" class="p3-btn" data-p3-save-cancel>Cancel</button><button type="button" class="p3-btn p3-primary" data-p3-save-ok>Save tab</button></div>`;
    root.append(pop);
    const a = button.getBoundingClientRect();
    const r = root.getBoundingClientRect();
    pop.style.top = `${a.bottom - r.top + 6}px`;
    pop.style.left = `${Math.max(6, Math.min(r.width - 330, a.left - r.left))}px`;
    pop.querySelector('[data-p3-save-cancel]').addEventListener('click', close);
    pop.querySelector('[data-p3-save-ok]').addEventListener('click', () => {
      const name = pop.querySelector('[data-p3-save-name]').value.trim();
      const keep = pop.querySelector('[data-p3-save-keep]').checked;
      if (!name) return;
      const view = clone(el.view);
      // WHY the view's own filters: the rail is the one all-views filter every tab shares; a tab that keeps a subset
      // ANDs it into its entry (a .base view's `filters:`), so it stays that subset when the rail changes
      if (keep) view.filters = andFilters(view.filters, clone(el.filters));
      close();
      el.addView({ ...view, name });
    });
    pop.querySelector('[data-p3-save-name]').select();
  };
  document.addEventListener('pointerdown', (event) => { if (pop && !pop.contains(event.target) && !event.target.closest('[data-p3-save]')) close(); }, true);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); }, true);
  return () => {
    const pills = el.querySelector('.dv-pills');
    if (!pills || !pills.querySelector('.dv-pill') || pills.querySelector('[data-p3-save]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'dv-pill-add p3-savetab';
    button.dataset.p3Save = '';
    button.setAttribute('aria-haspopup', 'dialog');
    button.title = 'Save this subset as a tab of its own';
    button.textContent = 'Save as tab…';
    button.addEventListener('click', (event) => { event.stopPropagation(); if (pop) close(); else open(button); });
    pills.append(button);
  };
}

// ── settingsGear ─────────────────────────────────────────────────────────────────────────────────────────────────

export function settingsGear(el, root, spec, extra) {
  const store = settingsFor(el, spec);
  const panel = document.createElement('div');
  panel.className = 'p3-settings p3-pop';
  panel.id = `${el.id}-settings`;
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', 'Settings');
  panel.hidden = true;
  const rows = Object.entries(spec).map(([key, option]) => {
    if (option.type === 'toggle') return `<label class="p3-check"><input type="checkbox" data-p3-setting="${esc(key)}"> ${esc(option.displayName || key)}</label>`;
    const options = Object.entries(option.options || {}).map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join('');
    return `<label class="p3-field"><span>${esc(option.displayName || key)}</span><select data-p3-setting="${esc(key)}" aria-label="${esc(option.displayName || key)}">${options}</select></label>`;
  }).join('');
  panel.innerHTML = `<div class="p3-settings-head"><div><b>Settings</b><span>Set once: every figure on every tab uses them.</span></div><button type="button" class="p3-x" data-p3-settings-close aria-label="Close settings">✕</button></div>${rows}<div class="p3-settings-extra"></div>`;
  root.append(panel);
  const paint = () => {
    for (const input of panel.querySelectorAll('[data-p3-setting]')) {
      const key = input.dataset.p3Setting;
      if (input.type === 'checkbox') input.checked = !!store.values[key]; else input.value = store.values[key];
    }
    if (extra) extra(panel.querySelector('.p3-settings-extra'), store.values);
  };
  paint();
  panel.addEventListener('change', (event) => {
    const input = event.target.closest('[data-p3-setting]');
    if (!input) return;
    store.set({ [input.dataset.p3Setting]: input.type === 'checkbox' ? input.checked : input.value });
    paint();
  });
  let gear = null;
  const place = () => {
    const bar = el.querySelector('.dv-bar');
    const r = root.getBoundingClientRect();
    const b = bar ? bar.getBoundingClientRect() : r;
    panel.style.top = `${b.bottom - r.top + 4}px`;
    panel.style.right = `${Math.max(6, r.right - b.right + 6)}px`;
  };
  const show = (open) => {
    panel.hidden = !open;
    if (gear) gear.setAttribute('aria-expanded', String(open));
    if (open) { place(); const first = panel.querySelector('select, input'); if (first) first.focus(); }
  };
  panel.querySelector('[data-p3-settings-close]').addEventListener('click', () => show(false));
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !panel.hidden) { show(false); if (gear) gear.focus(); } }, true);
  document.addEventListener('pointerdown', (event) => { if (!panel.hidden && !panel.contains(event.target) && !(gear && gear.contains(event.target))) show(false); }, true);
  // the gear sits in the bar's own row, in room the bar keeps for it (styles: .dv-bar padding-right), so data-ui's
  // one-row fitting (bar.js measures the padding) folds its tabs and tools around it
  return () => {
    const bar = el.querySelector('.dv-bar');
    if (!bar || bar.querySelector('[data-p3-gear]')) return;
    gear = document.createElement('button');
    gear.type = 'button';
    gear.className = 'p3-gear';
    gear.dataset.p3Gear = '';
    gear.setAttribute('aria-label', 'Settings');
    gear.setAttribute('aria-haspopup', 'dialog');
    gear.setAttribute('aria-expanded', 'false');
    gear.setAttribute('aria-controls', panel.id);
    gear.title = 'Settings: colour map, Reverse, scale (every figure, every tab)';
    gear.innerHTML = ICON.gear;
    gear.addEventListener('click', (event) => { event.stopPropagation(); show(panel.hidden); });
    bar.append(gear);
  };
}

/** Run every shim's pass after each data-ui draw. */
export function installShims(el, passes) {
  return afterDraws(el, () => { for (const pass of passes) pass(); });
}
