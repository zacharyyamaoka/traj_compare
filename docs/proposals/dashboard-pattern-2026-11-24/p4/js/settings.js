/* settings.js — the component-wide colour settings behind its one gear: colour map, Reverse, scale. Set once, read by
 * every figure on every dashboard (V2's store, copied).
 *
 * WHY beside data-ui and not a view key: a view entry is per view (and per saved view); "things that apply to the entire
 * thing that you set once" (Zach, Nov 23) are the component's. data-ui gap: `configure({settings})` → `input.settings`.
 */

const KEY = 'coverage-p4.settings';
const Color = globalThis.CoverageColor;
const DEFAULTS = { cmap: 'viridis', reverse: false, scale: 'linear' };
const listeners = new Set();

function load() {
  try {
    const raw = JSON.parse(globalThis.localStorage.getItem(KEY) || 'null') || {};
    return {
      cmap: Color.NAMES.includes(raw.cmap) ? raw.cmap : DEFAULTS.cmap,
      reverse: raw.reverse === true,
      scale: Color.SCALES.includes(raw.scale) ? raw.scale : DEFAULTS.scale,
    };
  } catch (error) { return { ...DEFAULTS }; }
}

export const settings = load();

export function setSettings(patch) {
  Object.assign(settings, patch);
  try { globalThis.localStorage.setItem(KEY, JSON.stringify(settings)); } catch (error) { /* private window */ }
  for (const listener of listeners) listener(settings);
}

export function onSettings(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export const SCALE_NOTES = {
  linear: 'Linear: colour grows with the count; the top 2 % of cells are clipped so one busy cell does not wash out the rest.',
  log: 'Log: colour follows log(count), so thin cells show too.',
  equalized: 'Equalized: colour = rank among visited cells. It shows WHERE the data is, not HOW MUCH.',
  visited: 'Visited / not: one colour for every cell any trajectory passed through.',
  enough: 'Enough / not: full colour = at least the "enough" count of trajectories; pale = visited, but by fewer.',
};
