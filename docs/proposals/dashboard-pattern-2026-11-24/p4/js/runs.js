/* runs.js — <p4-runs for="<data-views id>">: the run selector, TensorBoard / Weights & Biases style. The rail IS the
 * rows: the dataset groups first (a checkbox, its colour swatch, its count; unfold it for its trajectories, each with a
 * checkbox), a regex box over the names, and Split / Kind as quick toggles that apply across every dataset ticked.
 *
 * It owns no data and draws no figure: it reads the linked <data-views>' rows and its `.base`'s `runs:` keys, and writes
 * ONE all-views filter (`el.filters`), the same object data-ui's own rail, pills and query bar write. Every view of the
 * <data-views> (the dashboards) then redraws from the rows that filter leaves. This is the element P4 proposes for
 * data-ui as `<data-runs>`; nothing in it knows about trajectories or robots.
 *
 * Semantics (data-ui's facets', and the round's gate P1): nothing ticked = everything; a tick narrows. A dataset ticked
 * with none of its trajectories ticked is the whole dataset; ticking trajectories narrows it to them (its box shows −).
 * Split and Kind apply to every dataset (Zach, Nov 24: "I don't want the option to like include dev of one particular
 * dataset and not of the other").
 */

const esc = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const lit = (value) => JSON.stringify(String(value));
const FALLBACK = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];

/** data-ui's own idiom for "one of these values" (add-to-dashboard.js inClause): a clause, or {or: [...]}. */
export function inClause(property, values) {
  const list = [...new Set(values)];
  if (!list.length) return 'false';
  const one = (v) => `${property} == ${lit(v)}`;
  return list.length === 1 ? one(list[0]) : { or: list.map(one) };
}

export class RunList extends HTMLElement {
  constructor() {
    super();
    this.state = { picked: new Set(), traj: new Map(), toggles: {}, regex: '', open: new Set() };
    this.reError = null;
  }

  /** Called once the linked <data-views> has its data and `.base`. */
  bind(views, dataset, base) {
    this.views = views;
    this.rows = dataset.rows;
    this.spec = base.runs;
    const group = this.spec.group;
    const colors = (base.properties[group] && base.properties[group].colors) || {};
    const seen = [...new Set(this.rows.map((row) => row[group]))];
    this.groups = Object.keys(colors).filter((key) => seen.includes(key)).concat(seen.filter((key) => !(key in colors)));
    this.slots = colors;
    for (const toggle of this.spec.toggles) this.state.toggles[toggle.property] = new Set();
    this.byGroup = new Map(this.groups.map((key) => [key, this.rows.filter((row) => row[group] === key)]));
    this.build();
    this.apply();
  }

  /** The group's colour: data-ui's series token for its slot (the same one the table's badge and every figure use). */
  colour(key) {
    const slot = this.slots[key];
    let series = null;
    try { series = this.views.tokens().series; } catch (error) { /* not started */ }
    if (!slot) return 'rgb(113,113,122)';
    return (series && series[slot - 1]) || FALLBACK[slot - 1];
  }

  // ── what is included ──────────────────────────────────────────────────────────────────────────────────────────
  regex() {
    const text = this.state.regex.trim();
    if (!text) { this.reError = null; return null; }
    try { this.reError = null; return new RegExp(text, 'i'); } catch (error) { this.reError = error.message; return null; }
  }
  haystack(row) { return this.spec.regex.map((p) => row[p]).join('/'); }
  passes(row, { except } = {}) {
    const { picked, traj, toggles } = this.state;
    const group = row[this.spec.group];
    if (except !== 'group' && picked.size && !picked.has(group)) return false;
    const ticks = traj.get(group);
    if (except !== 'group' && ticks && ticks.size && !ticks.has(row.id)) return false;
    for (const [property, set] of Object.entries(toggles)) if (property !== except && set.size && !set.has(row[property])) return false;
    if (this._re && !this._re.test(this.haystack(row))) return false;
    return true;
  }

  /** The one all-views filter: Bases clauses data-ui's grammar compiles (an id list where the grammar has no word). */
  filter() {
    const { picked, traj, toggles } = this.state;
    const clauses = [];
    if (picked.size) clauses.push(inClause(this.spec.group, [...picked]));
    for (const [property, set] of Object.entries(toggles)) if (set.size) clauses.push(inClause(property, [...set]));
    const narrowed = [...traj.values()].some((set) => set.size);
    if (this._re || narrowed) {
      // WHY an id list: data-ui's grammar has no regex (Bases' /re/.matches() is a NEW grammar word P4 asks for), and
      // a per-dataset trajectory pick is "rows of A among these, every row of B": both are said as data-ui says a
      // selection it cannot otherwise word (inClause('id', …)).
      const ids = this.rows.filter((row) => {
        const ticks = traj.get(row[this.spec.group]);
        if (ticks && ticks.size && !ticks.has(row.id)) return false;
        return !this._re || this._re.test(this.haystack(row));
      }).map((row) => row.id);
      clauses.push(inClause('id', ids));
    }
    return clauses.length ? { and: clauses } : null;
  }

  apply() {
    this._re = this.regex();
    const filter = this.filter();
    this.views.filters = filter;
    this.draw();
    this.dispatchEvent(new CustomEvent('p4-runs-change', { bubbles: true, detail: { filter, shown: this.shown() } }));
  }

  shown() { return this.rows.filter((row) => this.passes(row)).length; }

  /** In words, the active filter: what the dashboards say under their tabs. */
  describe() {
    const { picked, traj, toggles } = this.state;
    const rest = [];
    const narrowed = [...traj.entries()].filter(([, set]) => set.size);
    const groups = picked.size ? [...picked].map((key) => { const set = traj.get(key); return set && set.size ? `${key} (${set.size} picked)` : key; }).join(' + ') : '';
    for (const toggle of this.spec.toggles) { const set = toggles[toggle.property]; if (set.size) rest.push([...set].join(' or ')); }
    if (this._re) rest.push(`name ~ /${this.state.regex.trim()}/`);
    return { groups, rest, parts: [groups, ...rest].filter(Boolean), narrowed: narrowed.length };
  }

  // ── drawing ───────────────────────────────────────────────────────────────────────────────────────────────────
  build() {
    const toggles = this.spec.toggles.map((toggle) => `
      <div class="p4-tg" data-p4-group="${esc(toggle.property)}" role="group" aria-label="${esc(toggle.label)}">
        <div class="p4-tg-label">${esc(toggle.label)}</div><div class="p4-chips" data-chips="${esc(toggle.property)}"></div>
      </div>`).join('');
    this.innerHTML = `
      <div class="p4-runs-head">
        <div class="p4-runs-title"><span class="p4-runs-name">Trajectories</span>
          <button type="button" class="p4-linkbtn" data-act="clear" title="Untick everything: every dataset, every trajectory, every toggle, no regex">Clear</button></div>
        <div class="p4-count" data-p4-count aria-live="polite"></div>
        <label class="p4-regex"><span class="p4-visually-hidden">Filter trajectories by regex</span>
          <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>
          <input type="search" data-p4-regex placeholder="Filter (regex): holdout|-00[0-4]" spellcheck="false" autocomplete="off"></label>
        <div class="p4-regex-error" data-p4-regex-error hidden></div>
      </div>
      <div class="p4-runs-body" data-p4-group="${esc(this.spec.group)}" role="group" aria-label="${esc(this.spec.label)}">
        <div class="p4-group-label"><span>${esc(this.spec.label)}</span><span class="p4-hint" title="Tick a dataset to narrow to it; nothing ticked = all of them">none ticked = all</span>
          <button type="button" class="p4-linkbtn" data-act="fold" title="Unfold or fold every dataset's trajectories">Unfold all</button></div>
        <div class="p4-tree" data-p4-tree></div>
      </div>
      <div class="p4-runs-foot">
        <div class="p4-foot-note">Applies to every dataset ticked</div>
        ${toggles}
      </div>`;
    const input = this.querySelector('[data-p4-regex]');
    let timer = 0;
    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { this.state.regex = input.value; this.apply(); }, 160); });
    this.addEventListener('change', (event) => this.onChange(event));
    this.addEventListener('click', (event) => this.onClick(event));
    this.addEventListener('dblclick', (event) => {
      const row = event.target.closest('[data-p4-row]');
      if (row) { event.preventDefault(); this.dispatchEvent(new CustomEvent('p4-open-row', { bubbles: true, detail: { id: row.dataset.p4Row } })); }
    });
  }

  onChange(event) {
    const box = event.target;
    if (box.matches('[data-p4-dataset]')) {
      const key = box.dataset.p4Dataset;
      const { picked, traj } = this.state;
      const partial = picked.has(key) && traj.get(key) && traj.get(key).size;
      // tri-state, as a file tree's: − (some of its trajectories) → ✓ (all of it) → ☐ (not ticked)
      if (partial) traj.delete(key);
      else if (picked.has(key)) { picked.delete(key); traj.delete(key); } else picked.add(key);
      this.apply();
    } else if (box.matches('[data-p4-traj]')) {
      const id = box.dataset.p4Traj;
      const row = this.rows.find((r) => r.id === id);
      const key = row[this.spec.group];
      const set = this.state.traj.get(key) || new Set();
      if (set.has(id)) set.delete(id); else set.add(id);
      this.state.traj.set(key, set);
      // WHY ticking a trajectory ticks its dataset: "I want to look at this one" must show it, not it plus the rest
      if (set.size) this.state.picked.add(key);
      this.apply();
    }
  }

  onClick(event) {
    const chev = event.target.closest('[data-p4-chev]');
    if (chev) {
      const key = chev.dataset.p4Chev;
      if (this.state.open.has(key)) this.state.open.delete(key); else this.state.open.add(key);
      this.draw();
      return;
    }
    const chip = event.target.closest('[data-p4-toggle]');
    if (chip) {
      const set = this.state.toggles[chip.dataset.p4Toggle];
      const value = chip.dataset.value;
      if (set.has(value)) set.delete(value); else set.add(value);
      this.apply();
      return;
    }
    const act = event.target.closest('[data-act]');
    if (!act) return;
    if (act.dataset.act === 'clear') {
      this.state.picked.clear(); this.state.traj.clear(); this.state.regex = '';
      for (const set of Object.values(this.state.toggles)) set.clear();
      this.querySelector('[data-p4-regex]').value = '';
      this.apply();
    } else if (act.dataset.act === 'fold') {
      const all = this.groups.every((key) => this.state.open.has(key));
      this.state.open = all ? new Set() : new Set(this.groups);
      this.draw();
    }
  }

  draw() {
    const { picked, traj, toggles, open } = this.state;
    const total = this.rows.length;
    const shown = this.shown();
    this.querySelector('[data-p4-count]').innerHTML = `<b>${shown}</b> of ${total} trajectories${shown === total ? ' · all' : ''}`;
    const err = this.querySelector('[data-p4-regex-error]');
    err.hidden = !this.reError;
    err.textContent = this.reError ? `not a regex, ignored: ${this.reError}` : '';
    this.querySelector('[data-p4-regex]').classList.toggle('p4-bad', !!this.reError);
    this.querySelector('[data-act="fold"]').textContent = this.groups.every((key) => open.has(key)) ? 'Fold all' : 'Unfold all';

    const tree = this.querySelector('[data-p4-tree]');
    const scroll = this.querySelector('.p4-runs-body').scrollTop;
    tree.innerHTML = this.groups.map((key) => {
      const rows = this.byGroup.get(key);
      const ticks = traj.get(key) || new Set();
      const isPicked = picked.has(key);
      const out = picked.size && !isPicked;
      const passing = rows.filter((row) => this.passes(row, { except: 'group' }));
      const inSubset = out ? 0 : passing.filter((row) => !ticks.size || ticks.has(row.id)).length;
      const colour = this.colour(key);
      const expanded = open.has(key);
      const n = out ? `<span class="p4-n-out">${passing.length}</span>` : inSubset === rows.length ? `${rows.length}` : `<b>${inSubset}</b><span class="p4-n-of">/${rows.length}</span>`;
      let list = '';
      if (expanded) {
        const items = passing.map((row) => {
          const ticked = ticks.has(row.id);
          const off = out || (ticks.size && !ticked);
          return `<label class="p4-tr${off ? ' p4-off' : ''}" data-p4-row="${esc(row.id)}" title="${esc(row.task)} · ${esc(row.split)} · ${esc(row.kind)}${row.tags ? ` · ${esc(row.tags)}` : ''}&#10;double-click: open it in Trajectories">
            <input type="checkbox" data-p4-traj="${esc(row.id)}"${ticked ? ' checked' : ''}>
            <span class="p4-dot" style="--ds:${colour}"></span><span class="p4-tr-name">${esc(row[this.spec.title])}</span></label>`;
        }).join('');
        const hidden = rows.length - passing.length;
        list = `<div class="p4-trs">${items || '<div class="p4-empty">none passes the toggles / regex</div>'}${hidden ? `<div class="p4-more">${hidden} hidden by Split · Kind · regex</div>` : ''}</div>`;
      }
      return `<div class="p4-ds${out ? ' p4-out' : ''}${isPicked ? ' p4-picked' : ''}" data-label="${esc(key)}" style="--ds:${colour}">
          <button type="button" class="p4-chev" data-p4-chev="${esc(key)}" aria-expanded="${expanded}" aria-label="${expanded ? 'Fold' : 'Unfold'} ${esc(key)}'s trajectories">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4"/></svg></button>
          <label class="p4-ds-main" title="${esc(key)}: ${rows.length} trajectories${out ? ' · not shown (another dataset is ticked)' : ''}">
            <input type="checkbox" data-p4-dataset="${esc(key)}"${isPicked ? ' checked' : ''}>
            <span class="p4-sw" aria-hidden="true"></span><span class="p4-ds-name">${esc(key)}</span></label>
          <span class="p4-ds-n">${n}</span>
        </div>${list}`;
    }).join('');
    for (const key of this.groups) {
      const box = tree.querySelector(`[data-p4-dataset="${CSS.escape(key)}"]`);
      const ticks = traj.get(key);
      box.indeterminate = !!(picked.has(key) && ticks && ticks.size);
    }
    this.querySelector('.p4-runs-body').scrollTop = scroll;

    for (const toggle of this.spec.toggles) {
      const property = toggle.property;
      const set = toggles[property];
      const passing = this.rows.filter((row) => this.passes(row, { except: property }));
      const values = [...new Set(this.rows.map((row) => row[property]))];
      const counts = new Map(values.map((v) => [v, 0]));
      for (const row of passing) counts.set(row[property], counts.get(row[property]) + 1);
      this.querySelector(`[data-chips="${CSS.escape(property)}"]`).innerHTML = values.map((value) => {
        const on = set.has(value);
        return `<button type="button" class="p4-chip${on ? ' p4-on' : ''}" data-p4-toggle="${esc(property)}" data-value="${esc(value)}" aria-pressed="${on}"
          title="${esc(toggle.label)} = ${esc(value)} across every dataset ticked (${counts.get(value)})">${esc(String(value).replace(/_/g, ' '))}<span class="p4-chip-n">${counts.get(value)}</span></button>`;
      }).join('');
    }
  }
}

if (!customElements.get('p4-runs')) customElements.define('p4-runs', RunList);
