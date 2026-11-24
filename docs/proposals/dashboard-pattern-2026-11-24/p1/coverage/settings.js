/* settings.js — the colour settings every coverage figure reads, from the workbench around it (its gear; the .base's
 * `settings:`). The figure code copied from V2 reads one module object (`settings`); each view fills it from its own
 * workbench right before it draws (use()), so two workbenches on one page each keep their own.
 *
 * WHY behind one gear and not per figure: Zach, Nov 23, "the colors … perhaps those are in a settings gear in the top
 * right corner, things that apply to the entire thing that you set once".
 */

const Color = globalThis.CoverageColor;
const DEFAULTS = { cmap: 'viridis', reverse: false, scale: 'linear' };
export const settings = { ...DEFAULTS };

export const SCALE_NOTES = {
  linear: 'Linear: colour grows with the count; the top 2 % of cells are clipped so one busy cell does not wash out the rest.',
  log: 'Log: colour follows log(count), so thin cells show too.',
  equalized: 'Equalized: colour = rank among visited cells. It shows WHERE the data is, not HOW MUCH.',
  visited: 'Visited / not: one colour for every cell any trajectory passed through.',
  enough: 'Enough / not: full colour = at least the "enough" count of trajectories; pale = visited, but by fewer.',
};

function clean(raw) {
  return {
    cmap: Color.NAMES.includes(raw.cmap) ? raw.cmap : DEFAULTS.cmap,
    reverse: raw.reverse === true,
    scale: Color.SCALES.includes(raw.scale) ? raw.scale : DEFAULTS.scale,
  };
}

/** Bind a view to the workbench around its <data-views>: use() fills `settings` from it, a change calls redraw. */
export function follow(host, redraw) {
  let wb = null;
  const on = () => redraw();
  const find = () => {
    if (!wb && host.element && host.element.closest) {
      wb = host.element.closest('data-workbench');
      if (wb) wb.addEventListener('data-workbench-settings', on);
    }
    return wb;
  };
  return {
    use() { const w = find(); Object.assign(settings, clean(w ? w.settings : {})); },
    off() { if (wb) wb.removeEventListener('data-workbench-settings', on); },
  };
}
