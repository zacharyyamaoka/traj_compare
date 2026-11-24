/* query.js — "click a cell → who made it" (V7; the prototype of PROPOSED-CONTRACT.md §52.8, a cell query).
 *
 * The protocol is V6's, made data-ui-shaped: a coverage view never writes outside its element, so a click on a cell
 * dispatches `coverage-cell` {key, cell, label, empty} from the view's element; the host owns the chips and calls
 * toggle(); every coverage view listens for `change` and fades the cells no trajectory in the answer visits. In data-ui
 * the chips would be the dashboard's state and reach a view as `input.query` (as a panel's picks reach it today, §39).
 *
 * A chip is {key, cell, label}. key names a grid membership.json indexes:
 *   plane/<joint>/<q_qd | qd_qdd | q_qdd>   flat cell x_bin * ny + y_bin, the payload's planes
 *   xy | xz | yz                             flat pixel u * nv + v, the payload's projections
 *   directions                               flat sphere cell ring * sectors + sector, the payload's sphere
 * and cell is that flat index, so a chip's cell IS the payload's cell (extract.py rebuilds every grid's per-cell
 * trajectory count from membership and asserts it equals the payload's `paths`).
 *
 * The answer = the trajectories whose membership holds every chip's cell (chips AND together). Nothing else is
 * recounted: the figures keep the payload's counts; the only derived numbers are the answer's size ("n of 54", a subset
 * count from membership.json) and which cells its trajectories visit (for the fade).
 */
class CoverageQuery extends EventTarget {
  constructor() {
    super();
    this.chips = [];
    this.byName = null;
    this.names = [];
    this.answer = null;
    this._visited = new Map();
  }

  /** membership.json as extract.py writes it: {voxel_shape, sphere, trajectories: {name: {...}}} */
  load(membership) {
    this.byName = membership.trajectories || {};
    this.names = Object.keys(this.byName);
    this.sphere = membership.sphere;
    this._compute();
  }

  get ready() { return !!this.byName; }
  get active() { return this.chips.length > 0; }
  get total() { return this.names.length; }

  /** the cells one trajectory visits on a grid (sorted ints), or null when membership does not index that grid */
  cells(name, key) {
    const m = this.byName && this.byName[name];
    if (!m || !key) return null;
    if (key.startsWith('plane/')) {
      const [, joint, grid] = key.split('/');
      return (m.planes && m.planes[joint] && m.planes[joint][grid]) || null;
    }
    return Array.isArray(m[key]) ? m[key] : null;
  }

  indexed(key) { return !!(this.names.length && this.cells(this.names[0], key)); }
  has(key, cell) { return this.chips.some((c) => c.key === key && c.cell === cell); }
  on(key) { return this.chips.filter((c) => c.key === key); }

  /** the cells the answer's trajectories visit on this grid; null while no chip is set (nothing fades) */
  visited(key) {
    if (!this.active || !this.ready) return null;
    if (this._visited.has(key)) return this._visited.get(key);
    const out = new Set();
    for (const name of this.answer) for (const c of this.cells(name, key) || []) out.add(c);
    this._visited.set(key, out);
    return out;
  }

  /** who visits one cell (for the readout's "click: N trajectories") */
  who(key, cell) {
    if (!this.ready) return [];
    return this.names.filter((name) => (this.cells(name, key) || []).includes(cell));
  }

  toggle(chip) {
    const i = this.chips.findIndex((c) => c.key === chip.key && c.cell === chip.cell);
    this.set(i >= 0 ? this.chips.filter((_, k) => k !== i) : [...this.chips, chip]);
  }

  remove(i) { this.set(this.chips.filter((_, k) => k !== i)); }
  clear() { this.set([]); }

  set(chips) {
    this.chips = chips.filter((c) => c && c.key && Number.isInteger(c.cell));
    this._compute();
    this.dispatchEvent(new CustomEvent('change', { detail: { chips: this.chips, answer: this.answer } }));
  }

  _compute() {
    this._visited.clear();
    if (!this.ready || !this.chips.length) { this.answer = null; return; }
    // AND: every chip's cell must be in the trajectory's own list for that grid
    const sets = this.chips.map((c) => c);
    this.answer = this.names.filter((name) => sets.every((c) => (this.cells(name, c.key) || []).includes(c.cell)));
  }
}

const Query = globalThis.CoverageQuery || (globalThis.CoverageQuery = new CoverageQuery());
export default Query;
