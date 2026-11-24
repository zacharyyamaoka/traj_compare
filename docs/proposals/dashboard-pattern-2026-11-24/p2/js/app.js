/* app.js — P2's coverage app: what is specific to trajectory coverage. The container (rail of dashboards + filters,
 * the open dashboard, the gear) is component.js and knows nothing about robots; this file hands it the rows, the
 * `.base` document, the colour settings and the drill.
 *
 * The figures are round 2's V2 engine (views.js, aggregate.js): every map counts trajectories per cell over the rows
 * the rail leaves, and with nothing filtered equals analyze's payload (the oracle runs at load; a mismatch is a console
 * error, so the check's P7 fails).
 *
 *   index.html   mountCoverage(document.getElementById('p2-app'))
 *   embed.html   mountCoverage(document.getElementById('host-slot'), {noUrl: true})
 */

import * as DataUI from '../../vendor/data-ui/data-ui.js';
import '../../vendor/data-ui/views/kpi.js';
import { trajectoryDataset } from './rows.js';
import { buildBase } from './base.js';
import { oracle } from './aggregate.js';
import { OccupancyView, OverviewView, context } from './views.js';
import { drillHtml, mountDrill, openInRerun, copyCommand } from './drill.js';
import { settings, setSettings, SCALE_NOTES } from './settings.js';
import { mountRailDashboards } from './component.js';

const Color = globalThis.CoverageColor;
const data = globalThis.COVERAGE_UI;

DataUI.registerView('occupancy', { name: 'Occupancy', icon: 'chart', load: async () => ({ default: OccupancyView }) });
DataUI.registerView('coverage-overview', { name: 'Coverage overview', icon: 'kpi', load: async () => ({ default: OverviewView }) });

/** The colour settings behind the gear: colour map, Reverse, scale. Every map on every dashboard reads them. */
function buildSettings(body) {
  body.innerHTML = `
    <label class="p2-field"><span>Colour map</span><select data-p2-cmap aria-label="Colour map"></select></label>
    <div class="p2-ramp" data-p2-ramp title="the colour map now in use: low → high"></div>
    <label class="p2-check"><input type="checkbox" data-p2-reverse> Reverse (high = dark)</label>
    <label class="p2-field"><span>Scale</span><select data-p2-scale aria-label="Colour scale"></select></label>
    <p class="p2-settings-note" data-p2-scale-note></p>`;
  const cmap = body.querySelector('[data-p2-cmap]');
  const reverse = body.querySelector('[data-p2-reverse]');
  const scale = body.querySelector('[data-p2-scale]');
  cmap.replaceChildren(...Color.NAMES.map((name) => new Option(name, name)));
  scale.replaceChildren(...Color.SCALES.map((mode) => new Option(Color.SCALE_TITLES[mode], mode)));
  const paint = () => {
    cmap.value = settings.cmap;
    reverse.checked = settings.reverse;
    scale.value = settings.scale;
    const ramp = Color.ramp(settings.cmap, settings.reverse);
    const stops = [];
    for (let k = 0; k <= 8; k += 1) { const c = ramp(k / 8); stops.push(`rgb(${c[0]},${c[1]},${c[2]})`); }
    body.querySelector('[data-p2-ramp]').style.background = `linear-gradient(90deg, ${stops.join(', ')})`;
    body.querySelector('[data-p2-scale-note]').textContent = SCALE_NOTES[settings.scale];
  };
  paint();
  cmap.addEventListener('change', () => { setSettings({ cmap: cmap.value }); paint(); });
  reverse.addEventListener('change', () => { setSettings({ reverse: reverse.checked }); paint(); });
  scale.addEventListener('change', () => { setSettings({ scale: scale.value }); paint(); });
}

export function mountCoverage(slot, { noUrl = false, id = 'p2-cov' } = {}) {
  const dataset = trajectoryDataset(data.coverage, data.trajectories, data.membership);
  const base = buildBase(data.coverage, data.membership, dataset, data.datasets);
  // the oracle: every grid and number, rebuilt from ALL the rows, must equal the payload (else the page says so)
  const report = oracle(data.coverage, dataset, base, data.membership.voxel_shape);
  if (report.failures.length) console.error('P2 re-aggregation does not match the payload:', report.failures);
  Object.assign(context, { oracle: report, base, total: dataset.rows.length, enough: data.coverage.enough, root: slot, datasets: data.datasets });

  const dash = mountRailDashboards(slot, {
    id, base, baseText: DataUI.stringifyBase(base), data: dataset, noUrl,
    title: 'Dashboards', noun: ['trajectory', 'trajectories'],
    settings: { label: 'Colours', build: buildSettings },
  });
  const views = dash.views;

  // the drill: data-ui's own record peek + Open in Rerun and what this trajectory adds (drill.js)
  views.peekExtra = (row) => (row && row.rrd ? drillHtml(row) : '');
  views.addEventListener('data-views-open', (event) => {
    const row = event.detail.row;
    if (!row || !row.rrd || event.detail.records) return;
    requestAnimationFrame(() => mountDrill(views.querySelector('.dv-peek'), row, dataset.rows, base));
  });
  slot.addEventListener('click', (event) => {
    const rerun = event.target.closest('[data-p2-rerun]');
    if (rerun) { event.preventDefault(); openInRerun(rerun); return; }
    const copy = event.target.closest('.p2-rerun-fallback .p2-copy');
    if (copy) copyCommand(copy);
  });

  // WHY a click on a column header sorts (and does not open data-ui's column menu): Zach likes "sorting the table" on
  // the live page, where a header click sorts; data-ui's table opens Notion's column menu on a click and sorts on a
  // shift-click. Numbers sort high-first on the first click, text A-Z; a second click flips it. (Round 2 V2's fix;
  // data-ui gap: `header-click="sort|menu"`.)
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

  globalThis.P2 = { report, base, dataset, dash };
  slot.dataset.p2Ready = report.failures.length ? 'mismatch' : 'ok';
  return dash;
}
