/* app.js — V2 "Rows first": the dataset is a table of trajectories; coverage is what the rows you filtered add up to.
 *
 * One stock <data-views> (its tabs are the focus areas and the saved views, its query bar and the stock <data-facets>
 * rail the one filter) over one row per trajectory. The coverage focus areas are views V2 registers (views.js), so a
 * filter anywhere redraws them from the rows it leaves. The gear (top right) holds the colour settings every map
 * reads. A table row opens data-ui's record peek, with Open in Rerun and what the trajectory adds (drill.js).
 */

import * as DataUI from '../../vendor/data-ui/data-ui.js';
import '../../vendor/data-ui/views/kpi.js';
import { trajectoryDataset } from './rows.js';
import { buildBase } from './base.js';
import { oracle } from './aggregate.js';
import { OccupancyView, OverviewView, context } from './views.js';
import { drillHtml, mountDrill, openInRerun, copyCommand } from './drill.js';
import { settings, setSettings, SCALE_NOTES } from './settings.js';

const Color = globalThis.CoverageColor;
const data = globalThis.COVERAGE_UI;

DataUI.registerView('occupancy', { name: 'Occupancy', icon: 'chart', load: async () => ({ default: OccupancyView }) });
DataUI.registerView('coverage-overview', { name: 'Coverage overview', icon: 'kpi', load: async () => ({ default: OverviewView }) });

const dataset = trajectoryDataset(data.coverage, data.trajectories, data.membership);
const base = buildBase(data.coverage, data.membership, dataset);
// the oracle: every grid and number, rebuilt from ALL the rows, must equal the payload (else the page says so, loudly)
const report = oracle(data.coverage, dataset, base, data.membership.voxel_shape);
if (report.failures.length) console.error('V2 re-aggregation does not match the payload:', report.failures);
Object.assign(context, { oracle: report, base, total: dataset.rows.length, enough: data.coverage.enough });
globalThis.V2 = { report, base, dataset };

// ── the header ───────────────────────────────────────────────────────────────────────────────────────────────────

document.querySelector('[data-v2-title]').textContent = data.coverage.title;
document.querySelector('[data-v2-subtitle]').textContent = data.coverage.subtitle;
const colours = base.properties.split.colors;
const key = document.querySelector('[data-v2-key]');
key.innerHTML = `<span class="v2-key-label">split</span>${Object.entries(colours).map(([name, slot]) =>
  `<span class="dv-badge dv-h${slot}" title="rows, badges and counts coloured by split: ${name}">${name}</span>`).join('')}`;

// ── the gear: colour map, Reverse and scale, set once for every map ──────────────────────────────────────────────

const gear = document.getElementById('v2-gear');
const panel = document.getElementById('v2-settings');
const cmap = document.getElementById('v2-cmap');
const reverse = document.getElementById('v2-reverse');
const scale = document.getElementById('v2-scale');
cmap.replaceChildren(...Color.NAMES.map((name) => new Option(name, name)));
scale.replaceChildren(...Color.SCALES.map((mode) => new Option(Color.SCALE_TITLES[mode], mode)));
function paintSettings() {
  cmap.value = settings.cmap;
  reverse.checked = settings.reverse;
  scale.value = settings.scale;
  const ramp = Color.ramp(settings.cmap, settings.reverse);
  const stops = [];
  for (let k = 0; k <= 8; k += 1) { const c = ramp(k / 8); stops.push(`rgb(${c[0]},${c[1]},${c[2]})`); }
  document.querySelectorAll('[data-v2-ramp]').forEach((node) => { node.style.background = `linear-gradient(90deg, ${stops.join(', ')})`; });
  document.querySelector('[data-v2-scale-note]').textContent = SCALE_NOTES[settings.scale];
}
paintSettings();
const openSettings = (open) => {
  panel.hidden = !open;
  gear.setAttribute('aria-expanded', String(open));
  if (open) cmap.focus();
};
gear.addEventListener('click', () => openSettings(panel.hidden));
document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !panel.hidden) { openSettings(false); gear.focus(); } });
document.addEventListener('pointerdown', (event) => { if (!panel.hidden && !panel.contains(event.target) && !gear.contains(event.target)) openSettings(false); });
document.getElementById('v2-settings-close').addEventListener('click', () => openSettings(false));
cmap.addEventListener('change', () => { setSettings({ cmap: cmap.value }); paintSettings(); });
reverse.addEventListener('change', () => { setSettings({ reverse: reverse.checked }); paintSettings(); });
scale.addEventListener('change', () => { setSettings({ scale: scale.value }); paintSettings(); });

// ── data-ui ──────────────────────────────────────────────────────────────────────────────────────────────────────

const views = document.getElementById('cov');
views.base = base;
views.baseText = DataUI.stringifyBase(base);
views.peekExtra = (row) => (row && row.rrd ? drillHtml(row) : '');
views.data = dataset;

// the drill's figures, once data-ui has drawn the peek
views.addEventListener('data-views-open', (event) => {
  const row = event.detail.row;
  if (!row || !row.rrd || event.detail.records) return;
  requestAnimationFrame(() => mountDrill(views.querySelector('.dv-peek'), row, dataset.rows, base));
});
document.addEventListener('click', (event) => {
  const rerun = event.target.closest('[data-v2-rerun]');
  if (rerun) { event.preventDefault(); openInRerun(rerun); return; }
  const copy = event.target.closest('.v2-rerun-fallback .v2-copy');
  if (copy) copyCommand(copy);
});

// WHY a click on a column header sorts here (and does not open data-ui's column menu): Zach likes "sorting the table"
// on the live page, where a header click sorts; data-ui's table opens Notion's column menu on a click and sorts on a
// shift-click. A first click sorts numbers high-first (the answer you came for) and text A-Z, a second flips it.
// The column menu stays one keystroke away (Enter on a focused header) and in Display › Sort. data-ui gap: a
// `header-click="sort|menu"` attribute would make this stock.
views.addEventListener('click', (event) => {
  const th = event.target.closest('thead th[data-sort]');
  if (!th || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.closest('.dv-resize, [data-col-menu], .dv-selbox')) return;
  event.stopPropagation();
  event.preventDefault();
  const property = th.dataset.sort;
  const column = views.model && views.model.columns[property];
  const current = (views.view.sort || []).find((item) => item.property === property);
  const first = column && column.type === 'number' ? 'DESC' : 'ASC';
  const direction = current ? (current.direction === 'ASC' ? 'DESC' : 'ASC') : first;
  views.setView({ sort: [{ property, direction }] });
}, true);

// the subset chip in the header: which rows every view is drawing now
const chip = document.querySelector('[data-v2-chip]');
function paintChip() {
  const model = views.model;
  if (!model) return;
  const n = model.rows.length;
  const total = dataset.rows.length;
  chip.classList.toggle('v2-chip-on', n !== total);
  chip.innerHTML = n === total ? `All <b>${total}</b> trajectories` : `Subset: <b>${n}</b> of ${total} trajectories`;
  chip.title = n === total ? 'Nothing is filtered: every view draws the whole dataset' : 'Every coverage view redraws from these rows (filters: the rail, the query bar, the view)';
}
views.addEventListener('data-views-change', () => queueMicrotask(paintChip));
views.addEventListener('data-views-render', paintChip);
document.documentElement.dataset.v2Ready = report.failures.length ? 'mismatch' : 'ok';
