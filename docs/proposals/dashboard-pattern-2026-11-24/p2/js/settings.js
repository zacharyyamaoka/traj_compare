/* settings.js — the page-wide colour settings behind the gear (top right), set once and read by every coverage view.
 *
 * WHY one store and not a view key: Zach, Nov 23, "the colors … perhaps those are in a settings gear in the top right
 * corner, things that apply to the entire thing that you set once". A data-ui view entry is per view (and per saved
 * view), so the colour map lives beside data-ui, and the views subscribe. Kept in localStorage (try/catch: a private
 * window simply forgets it).
 */

const KEY = 'dashboard-pattern-p2.settings';
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
