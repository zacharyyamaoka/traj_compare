/* app.js — the host glue every P5 page shares (index.html, embed.html, card.html). It is short on purpose: the pattern
 * lives in the parts (scope.js); what an app writes is its rows, its document and its own figures.
 *
 *   1. register the coverage views (data-ui's registerView, CONTRACT §1): occupancy maps, the headline numbers, the
 *      per-dataset key; all three recount over the rows they are handed
 *   2. build the rows (212 trajectories) and the scope document (facets, views, dashboards, settings)
 *   3. hand both to every <data-scope> on the page; a page may first adjust its own copy of the document
 *      (card.html keeps two facets and its own one-panel dashboards)
 *   4. the drill: the Trajectories table's record peek gets Open in Rerun and "what it adds" (data-ui's peekExtra, §37)
 */

import { registerView } from '../../vendor/data-ui/data-ui.js';
import '../../vendor/data-ui/views/kpi.js';
import './scope.js';
import { trajectoryDataset } from './coverage/rows.js';
import { buildBase } from './coverage/base.js';
import { oracle } from './coverage/aggregate.js';
import { OccupancyView, NumbersView, DatasetsView, context, SCALE_NOTES } from './coverage/views.js';
import { drillHtml, mountDrill, openInRerun, copyCommand } from './coverage/drill.js';

const Color = globalThis.CoverageColor;
const data = globalThis.COVERAGE_UI;

registerView('occupancy', { name: 'Occupancy', icon: 'chart', load: async () => ({ default: OccupancyView }) });
registerView('coverage-numbers', { name: 'Coverage numbers', icon: 'kpi', load: async () => ({ default: NumbersView }) });
registerView('coverage-datasets', { name: 'Datasets key', icon: 'list', load: async () => ({ default: DatasetsView }) });

const dataset = trajectoryDataset(data.coverage, data.trajectories, data.membership);
const base = buildBase(data.coverage, data.membership, dataset, data.datasets);
// the oracle: with nothing filtered, every grid and number rebuilt from the 212 rows must equal the payload
const report = oracle(data.coverage, dataset, base, data.membership.voxel_shape);
if (report.failures.length) console.error('P5 re-aggregation does not match the payload:', report.failures);
Object.assign(context, { oracle: report, base, total: dataset.rows.length, enough: data.coverage.enough });

// the gear's own note under its controls: the colour map as a ramp, and what the scale means
function describe(now) {
  const ramp = Color.ramp(now.cmap, now.reverse);
  const stops = [];
  for (let k = 0; k <= 8; k += 1) { const c = ramp(k / 8); stops.push(`rgb(${c[0]},${c[1]},${c[2]})`); }
  return `<div class="ds-ramp" title="the colour map now in use: low → high" style="background:linear-gradient(90deg, ${stops.join(', ')})"></div>
    <p class="ds-note">${SCALE_NOTES[now.scale] || ''}</p>`;
}

/** Hand every scope its rows and document; `adjust(base, scope)` lets a page (card.html) shape its own copy. */
export function start(adjust = (b) => b) {
  for (const settings of document.querySelectorAll('data-settings')) settings.describe = describe;
  for (const table of document.querySelectorAll('data-views[tab]')) {
    table.peekExtra = (row) => (row && row.rrd ? drillHtml(row) : '');
    table.addEventListener('data-views-open', (event) => {
      const row = event.detail.row;
      if (!row || !row.rrd || event.detail.records) return;
      requestAnimationFrame(() => mountDrill(table.querySelector('.dv-peek'), row, dataset.rows, base));
    });
  }
  for (const scope of document.querySelectorAll('data-scope')) {
    scope.base = adjust(structuredClone(base), scope);
    scope.data = dataset;
  }
  document.documentElement.dataset.p5Ready = report.failures.length ? 'mismatch' : 'ok';
}

document.addEventListener('click', (event) => {
  const rerun = event.target.closest('[data-v2-rerun]');
  if (rerun) { event.preventDefault(); openInRerun(rerun); return; }
  const copy = event.target.closest('.v2-rerun-fallback .v2-copy');
  if (copy) copyCommand(copy);
});
