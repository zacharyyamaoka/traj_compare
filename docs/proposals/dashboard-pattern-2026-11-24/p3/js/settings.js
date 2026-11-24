/* settings.js — component-wide settings, set once behind the gear, read by every view (the colour map, Reverse, scale).
 *
 * WHY not a view key: Zach, Nov 23, "the colors … perhaps those are in a settings gear in the top right corner, things
 * that apply to the entire thing that you set once". A view entry is per view (and per saved view), so a colour map
 * there would differ tab by tab. P3 PROPOSES this as data-ui's: a top-level `settings:` key in the .base (Obsidian's
 * option types: dropdown, toggle, slider), a gear in the bar beside Display, every view handed `input.settings`, kept
 * under `data-ui/settings/<id>`. Until then this module is that store, one per <data-views> element, and the gear is
 * drawn by shims.js; the `panels` view passes `settings` into every panel's input.
 */

const stores = new WeakMap();

function load(key, spec) {
  let raw = {};
  try { raw = JSON.parse(globalThis.localStorage.getItem(key) || 'null') || {}; } catch (error) { raw = {}; }
  const out = {};
  for (const [name, option] of Object.entries(spec || {})) {
    const value = raw[name];
    if (option.type === 'toggle') out[name] = typeof value === 'boolean' ? value : !!option.default;
    else if (option.type === 'dropdown') out[name] = value in (option.options || {}) ? value : option.default;
    else out[name] = value !== undefined ? value : option.default;
  }
  return out;
}

/** The settings store of one <data-views> element: {spec, values, set(patch), on(listener) -> off}. */
export function settingsFor(element, spec) {
  let store = stores.get(element);
  if (store) return store;
  const key = `data-ui/settings/${element.id || 'views'}`;
  const listeners = new Set();
  store = {
    spec: spec || {},
    values: load(key, spec),
    set(patch) {
      Object.assign(store.values, patch);
      try { globalThis.localStorage.setItem(key, JSON.stringify(store.values)); } catch (error) { /* private window */ }
      for (const listener of listeners) listener(store.values);
    },
    on(listener) { listeners.add(listener); return () => listeners.delete(listener); },
  };
  stores.set(element, store);
  return store;
}

/** The settings a view should draw with: input.settings when data-ui hands them (the proposal), else the store's. */
export function settingsOf(input, element) {
  if (input && input.settings) return input.settings;
  const store = element && stores.get(element);
  return store ? store.values : { cmap: 'viridis', reverse: false, scale: 'linear' };
}

export const SCALE_NOTES = {
  linear: 'Linear: colour grows with the count; the top 2 % of cells are clipped so one busy cell does not wash out the rest.',
  log: 'Log: colour follows log(count), so thin cells show too.',
  equalized: 'Equalized: colour = rank among visited cells. It shows WHERE the data is, not HOW MUCH.',
  visited: 'Visited / not: one colour for every cell any trajectory passed through.',
  enough: 'Enough / not: full colour = at least the "enough" count of trajectories; pale = visited, but by fewer.',
};
