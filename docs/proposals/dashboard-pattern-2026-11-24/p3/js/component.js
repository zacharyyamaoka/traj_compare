/* component.js — P3 "Every tab is a saved view": the whole coverage component, mounted into any box.
 *
 *   mountCoverage(slot, {id})   one <data-facets> rail + one <data-views>, both stock, inside `.p3-root`; nothing else
 *
 * The component is data-ui's own container: its view tabs are the dashboards (presets of the proposed `type: panels`
 * view, panels.js), + and Save view make a reader's own tab, the rail is the one all-views filter every tab shares
 * (filters="rail pills": the bar's Filter button folds the rail, the pill row says what is set). The host page owns
 * nothing of it: index.html gives it the window under a title, embed.html a host app's 1000 × 680 slot. The page code
 * here is only what an app always writes: its rows, its .base, its registered views, the drill's Open in Rerun.
 */

import * as DataUI from '../../vendor/data-ui/data-ui.js';
import '../../vendor/data-ui/views/kpi.js';
import PanelsView, { setSubsetNote } from './panels.js';
import { OccupancyView, context, el } from './occupancy.js';
import { NumbersView, KeyView } from './numbers.js';
import { trajectoryDataset } from './rows.js';
import { buildBase, occupancyEntries } from './base.js';
import { oracle } from './aggregate.js';
import { drillHtml, mountDrill, openInRerun, copyCommand } from './drill.js';
import { tabIcons, headerClickSort, facetDots, saveWithFilter, settingsGear, installShims } from './shims.js';
import { SCALE_NOTES } from './settings.js';

const Color = globalThis.CoverageColor;
const data = globalThis.COVERAGE_UI;

// the views P3 registers (CONTRACT §1): `panels` is the proposal; the other three are this app's figures
DataUI.registerView('panels', { name: 'Dashboard', icon: 'dashboard', load: async () => ({ default: PanelsView }), canDraw: () => null });
DataUI.registerView('occupancy', { name: 'Occupancy', icon: 'chart', load: async () => ({ default: OccupancyView }) });
DataUI.registerView('numbers', { name: 'Numbers', icon: 'kpi', load: async () => ({ default: NumbersView }) });
DataUI.registerView('coverage-key', { name: 'Colour key', icon: 'kpi', load: async () => ({ default: KeyView }) });

const dataset = trajectoryDataset(data.coverage, data.trajectories, data.membership);
const base = buildBase(data.coverage, data.membership, dataset);
// the oracle: every grid and number, rebuilt from ALL the rows, must equal the payload (else the page says so, loudly)
const overview = base.views.find((view) => view.name === 'Overview');
const headline = overview.panels.find((panel) => panel.key === 'numbers').view.numbers;
const report = oracle(data.coverage, dataset.rows, occupancyEntries(base), headline, data.membership.voxel_shape);
if (report.failures.length) console.error('P3 re-aggregation does not match the payload:', report.failures);
Object.assign(context, { oracle: report, base, total: dataset.rows.length, enough: data.coverage.enough });
globalThis.P3 = { report, base, dataset };

setSubsetNote((n, total) => (n === total
  ? el('span', { class: report.failures.length ? 'p3-oracle p3-bad' : 'p3-oracle', title: report.lines.join('\n'),
    text: report.failures.length ? 'does NOT match the payload: see the console' : 'matches analyze' })
  : el('span', { class: 'p3-rebuilt', title: "every count and number below is rebuilt from these trajectories' cells (membership.json)", text: 're-aggregated' })));

// the drill's grids: the tool from above and each joint's position × speed, the ones the dashboards draw
const entries = occupancyEntries(base);
const grids = {
  top: entries.flatMap((entry) => entry.occupancy.panels).find((grid) => grid.code === 'tool xy'),
  joints: overview.panels.find((panel) => panel.key === 'joints').view.occupancy.panels,
};

/** The component in `slot`: returns its <data-views>. `id` names the instance (its rail, its URL, its kept settings). */
export function mountCoverage(slot, { id = 'cov' } = {}) {
  const root = el('div', { class: 'p3-root data-ui', 'data-p3-root': '' });
  const rail = document.createElement('data-facets');
  rail.setAttribute('for', id);
  rail.setAttribute('theme', 'light');
  const views = document.createElement('data-views');
  views.id = id;
  for (const [key, value] of Object.entries({
    theme: 'light', toolbar: 'bar',
    // WHY tabs, forced: the dashboards are the tabs (Zach: "switching between dashboards almost"); in a narrow host
    // the bar folds the ones that don't fit into data-ui's own "N more…" (CONTRACT §15, §47), never a second row
    views: 'tabs',
    // WHY rail + pills + promote filter: the bar's one Filter button (an icon beside the tabs) shows and hides the
    // rail, and the pill row under the bar says what is filtered on every tab, so the subset stays legible with the
    // rail folded away (a host's narrow slot)
    filters: 'rail pills', promote: 'filter', display: 'panel', open: 'side', 'view-types': 'panels table chart',
  })) views.setAttribute(key, value);
  root.append(rail, views);
  slot.replaceChildren(root);

  views.base = base;
  views.baseText = DataUI.stringifyBase(base);
  views.peekExtra = (row) => (row && row.rrd ? drillHtml(row) : '');
  views.data = dataset;

  facetDots(root, base);
  headerClickSort(views);
  installShims(views, [
    tabIcons(views),
    saveWithFilter(views, root),
    settingsGear(views, root, base.settings, (box, values) => {
      const ramp = Color.ramp(values.cmap, values.reverse);
      const stops = [];
      for (let k = 0; k <= 8; k += 1) { const c = ramp(k / 8); stops.push(`rgb(${c[0]},${c[1]},${c[2]})`); }
      box.innerHTML = `<div class="p3-ramp" title="the colour map now in use: low → high" style="background:linear-gradient(90deg, ${stops.join(', ')})"></div><p class="p3-settings-note">${SCALE_NOTES[values.scale] || ''}</p>`;
    }),
  ]);

  // the drill's figures, once data-ui has drawn the peek
  views.addEventListener('data-views-open', (event) => {
    const row = event.detail.row;
    if (!row || !row.rrd || event.detail.records) return;
    requestAnimationFrame(() => mountDrill(views.querySelector('.dv-peek'), row, dataset.rows, grids));
  });
  root.addEventListener('click', (event) => {
    const rerun = event.target.closest('[data-p3-rerun]');
    if (rerun) { event.preventDefault(); openInRerun(rerun); return; }
    const copy = event.target.closest('.p3-rerun-fallback .p3-copy');
    if (copy) copyCommand(copy);
  });
  views.addEventListener('data-views-render', () => { root.dataset.p3Ready = report.failures.length ? 'mismatch' : 'ok'; }, { once: true });
  return views;
}
