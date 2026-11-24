/* app.js — P4 "Run selector, TensorBoard / W&B style": mounts the component into any box (a full page or a host app's
 * slot). Three parts, all inside one root:
 *
 *   <p4-runs for>   the rail: the rows themselves (datasets as groups, trajectories under them, a regex, Split / Kind
 *                   toggles). It writes ONE all-views filter on the <data-views> below (runs.js).
 *   <data-views>    stock data-ui: its bar's tabs ARE the dashboards (one view per dashboard); its table is
 *                   Trajectories; its record peek is the drill (Open in Rerun). The figure dashboards are `sections`
 *                   views P4 registers (sections.js), colouring by `colorBy: dataset`.
 *   the gear        colour map, Reverse, scale: set once for every figure (settings.js); a popover inside the root.
 *
 * Nothing is fixed-position or appended to <body>: the component draws only inside the box it is given.
 * WHY filters="" (no pill row): the run list IS the filter's face, beside every tab; data-ui's pills would repeat it
 * as raw clauses (and an id list for the regex). A stock <data-runs> would hand data-ui a label per clause instead.
 */

import * as DataUI from '../../vendor/data-ui/data-ui.js';
import { trajectoryDataset } from './rows.js';
import { buildBase, allPanels } from './base.js';
import { oracle } from './aggregate.js';
import { SectionsView, context, rampCss } from './sections.js';
import { drillHtml, mountDrill, openInRerun, copyCommand } from './drill.js';
import { settings, setSettings, SCALE_NOTES } from './settings.js';
import './runs.js';

const Color = globalThis.CoverageColor;
const data = globalThis.COVERAGE_UI;
// WHY under 1200 px the component is "compact": a host's 1000 px slot leaves ~780 px beside the rail; the rail narrows,
// the dense figures shrink and a dashboard opens with its first two sections unfolded (measured in NOTES.md)
const COMPACT_BELOW = 1200;

DataUI.registerView('sections', { name: 'Sections', icon: 'chart', load: async () => ({ default: SectionsView }) });

const GEAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>';

export function mount(slot) {
  const dataset = trajectoryDataset(data.coverage, data.trajectories, data.membership, data.datasets);
  const base = buildBase(data.coverage, data.membership, dataset, data.datasets);
  const numbers = base.views[0].figures.find((figure) => figure.kind === 'numbers').numbers;
  const report = oracle(data.coverage, dataset.rows, allPanels(base), numbers, data.membership.voxel_shape);
  if (report.failures.length) console.error('P4 re-aggregation does not match the payload:', report.failures);
  Object.assign(context, { oracle: report, base, total: dataset.rows.length, enough: data.coverage.enough });

  const root = document.createElement('div');
  root.className = 'p4';
  root.dataset.p4Root = '';
  root.innerHTML = `
    <aside class="p4-rail" aria-label="Which trajectories every dashboard shows"><p4-runs for="p4-cov"></p4-runs></aside>
    <div class="p4-main">
      <data-views id="p4-cov" no-url toolbar="bar" views="tabs" promote="" filters="" open="side" theme="light" search="icon"></data-views>
      <button type="button" class="p4-gear" data-p4-gear aria-label="Colour settings" aria-haspopup="dialog" aria-expanded="false"
        title="Colour settings: set once, every figure on every dashboard uses them">${GEAR}</button>
      <div class="p4-settings" data-p4-settings role="dialog" aria-label="Colour settings" hidden>
        <div class="p4-settings-head"><div><b>Colour settings</b><span>Set once: every figure on every dashboard.</span></div>
          <button type="button" class="p4-x" data-p4-settings-close aria-label="Close colour settings">✕</button></div>
        <label class="p4-field"><span>Colour map</span><select data-p4-cmap aria-label="Colour map"></select></label>
        <div class="p4-ramp" data-p4-ramp title="the colour map now in use: low → high"></div>
        <label class="p4-check"><input type="checkbox" data-p4-reverse> Reverse (high = dark)</label>
        <label class="p4-field"><span>Scale</span><select data-p4-scale aria-label="Colour scale"></select></label>
        <p class="p4-settings-note" data-p4-scale-note></p>
        <div class="p4-settings-ds"><span>Datasets</span><div data-p4-ds-key></div></div>
      </div>
    </div>`;
  slot.append(root);
  const sizeIt = () => { root.dataset.size = root.clientWidth < COMPACT_BELOW ? 'compact' : 'full'; };
  sizeIt();
  new ResizeObserver(sizeIt).observe(root);

  // ── data-ui ────────────────────────────────────────────────────────────────────────────────────────────────────
  const views = root.querySelector('data-views');
  views.base = base;
  views.baseText = DataUI.stringifyBase(base);
  views.peekExtra = (row) => (row && row.rrd ? drillHtml(row) : '');
  views.data = dataset;
  const runs = root.querySelector('p4-runs');
  context.runs = runs;
  runs.bind(views, dataset, base);

  // the run list's count is its own arithmetic; data-ui filtered the rows itself: they must agree (else say so)
  views.addEventListener('data-views-render', () => {
    const model = views.model;
    if (model && model.rows && model.rows.length !== runs.shown() && model.matched && model.matched.length !== runs.shown()) {
      console.error(`P4: the run list says ${runs.shown()} trajectories, data-ui's filter left ${model.rows.length}`);
    }
    if (!document.documentElement.dataset.p4Ready) document.documentElement.dataset.p4Ready = report.failures.length ? 'mismatch' : 'ok';
  });

  // a double-click on a trajectory in the rail opens it in Trajectories' record pane
  root.addEventListener('p4-open-row', (event) => {
    views.selectView('Trajectories');
    setTimeout(() => views.openPeek(event.detail.id), 80);
  });

  // the drill: Open in Rerun and what this trajectory adds, at the foot of data-ui's record peek
  const top = allPanels(base).find((panel) => panel.cells === 'cells_xy');
  const joints = base.views[0].figures.find((figure) => figure.key === 'joints').panels;
  views.addEventListener('data-views-open', (event) => {
    const row = event.detail.row;
    if (!row || !row.rrd || event.detail.records) return;
    requestAnimationFrame(() => mountDrill(views.querySelector('.dv-peek'), row, dataset.rows, top, joints));
  });
  root.addEventListener('click', (event) => {
    const rerun = event.target.closest('[data-p4-rerun]');
    if (rerun) { event.preventDefault(); openInRerun(rerun); return; }
    const copy = event.target.closest('.p4-rerun-fallback .p4-copy');
    if (copy) copyCommand(copy);
  });

  // WHY a header click sorts (V2's glue): data-ui's table opens Notion's column menu on a click and sorts on a
  // shift-click; here the first click sorts numbers high-first and text A-Z. data-ui gap: `header-click="sort|menu"`.
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
    const direction = current && (views.view.sort || [])[0] === current ? (current.direction === 'ASC' ? 'DESC' : 'ASC') : first;
    views.setView({ sort: [{ property, direction }] });
  }, true);

  // ── the gear ───────────────────────────────────────────────────────────────────────────────────────────────────
  const gear = root.querySelector('[data-p4-gear]');
  const panel = root.querySelector('[data-p4-settings]');
  const cmap = root.querySelector('[data-p4-cmap]');
  const reverse = root.querySelector('[data-p4-reverse]');
  const scale = root.querySelector('[data-p4-scale]');
  cmap.replaceChildren(...Color.NAMES.map((name) => new Option(name, name)));
  scale.replaceChildren(...Color.SCALES.map((mode) => new Option(Color.SCALE_TITLES[mode], mode)));
  const paintSettings = () => {
    cmap.value = settings.cmap;
    reverse.checked = settings.reverse;
    scale.value = settings.scale;
    root.querySelector('[data-p4-ramp]').style.background = rampCss(Color.ramp(settings.cmap, settings.reverse));
    root.querySelector('[data-p4-scale-note]').textContent = SCALE_NOTES[settings.scale];
    root.querySelector('[data-p4-ds-key]').innerHTML = runs.groups.map((key) =>
      `<span class="p4-key"><span class="p4-sw" style="--ds:${runs.colour(key)}"></span>${key.replace(/[<>&]/g, '')}</span>`).join('');
  };
  paintSettings();
  const openSettings = (open) => {
    panel.hidden = !open;
    gear.setAttribute('aria-expanded', String(open));
    if (open) cmap.focus();
  };
  gear.addEventListener('click', () => openSettings(panel.hidden));
  root.querySelector('[data-p4-settings-close]').addEventListener('click', () => openSettings(false));
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !panel.hidden) { openSettings(false); gear.focus(); } });
  document.addEventListener('pointerdown', (event) => { if (!panel.hidden && !panel.contains(event.target) && !gear.contains(event.target)) openSettings(false); });
  cmap.addEventListener('change', () => { setSettings({ cmap: cmap.value }); paintSettings(); });
  reverse.addEventListener('change', () => { setSettings({ reverse: reverse.checked }); paintSettings(); });
  scale.addEventListener('change', () => { setSettings({ scale: scale.value }); paintSettings(); });
  globalThis.P4 = { root, views, runs, base, dataset, report };
  return root;
}
