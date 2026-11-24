/* type: coverage-sheet — the headline numbers as one compact sheet of label · value (V7; PROPOSED-CONTRACT.md §52.9).
 *
 * Reads number rows (rows.py "numbers": label, key, section, order, value = a rich cell {value, unit, note}) and draws
 * one column per section (Dataset · Joints · Tool), each a list of "label ……… value". The payload's own label, as
 * stored: when the column is too narrow it ends in an ellipsis and the full label, the code id (`key`, the name in the
 * payload and in traj_compare's code) and where the number comes from are one hover away. Nothing is recomputed: the
 * value is the payload's, written to 3 significant figures (the stored value is in the hover).
 *
 * WHY not the stock `kpi` cards: Zach, Nov 24: the headline numbers "doesn't make sense to be showing them the entire
 * time"; V3's 15 cards took 300 px of the landing. Fifteen numbers read as a sheet in ~110 px, so every joint's plane,
 * the tool and its pointing fit the same screen (V5's key/value sheet). In data-ui this is `kpi` with a
 * `layout: sheet` key (§52.9), not a new type.
 *
 *   coverage:
 *     group: section          the column property (default `section`)
 *
 * STOCK PARTS: none (DOM).
 */
import { esc, fmt, rows as rowsOf, block } from './kit.js';
import css from './coverage-css.js';

export { css };

function valueOf(cell) { return cell && typeof cell === 'object' ? cell.value : cell; }
function unitOf(cell) { return cell && typeof cell === 'object' ? cell.unit || '' : ''; }

function text(v, unit) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const n = fmt(v);
  if (!unit) return n;
  return unit === '°' ? `${n}°` : `${n} ${unit}`;
}

export default class CoverageSheetView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.classList.add('dv-coverage', 'dv-coverage-sheetview');
  }

  update(input) {
    const list = [...rowsOf(input)].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    const by = block(input).group || 'section';
    const groups = new Map();
    for (const r of list) {
      const g = r[by] || '';
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(r);
    }
    const cols = [...groups.entries()].map(([name, rows]) => `<div class="dv-coverage-sheet-col" role="group" aria-label="${esc(name)}">
      <div class="dv-coverage-sheet-h">${esc(name)}</div>
      ${rows.map((r) => {
        const v = valueOf(r.value); const unit = unitOf(r.value);
        const note = r.value && r.value.note ? r.value.note : '';
        const tip = `${r.label} = ${v} ${unit}\ncode id: ${r.key || r.id}${note ? `\n${note}` : ''}`;
        return `<div class="dv-coverage-sheet-row" title="${esc(tip)}" data-key="${esc(r.key || r.id)}"><span class="dv-coverage-sheet-l">${esc(r.label)}</span><span class="dv-coverage-sheet-v">${esc(text(v, unit))}</span></div>`;
      }).join('')}
    </div>`).join('');
    this.el.innerHTML = `<div class="dv-coverage-sheet" data-cov-sheet style="grid-template-columns:${[...groups.values()].map((rows) => (rows.length < 4 ? '0.75fr' : '1.2fr')).join(' ')}">${cols}</div>`;
  }

  destroy() {}
}
