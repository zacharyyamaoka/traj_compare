#!/usr/bin/env node
// Writes P1's two data files from the round's shared data/ (dashboard-pattern babble, 2026-11-24):
//   p1/rows.json      one row per trajectory (212), with the cells it visits as list properties (coverage/rows.js)
//   p1/coverage.base  the workbench's document: rows, rail, settings, pages, properties, then the views (whose figure
//                     geometry is read from the payload, coverage/grids.js)
// then checks the re-aggregation oracle: with nothing filtered, every grid's trajectories-per-cell rebuilt from the
// rows' cell lists must equal the payload's own counts, and every headline number must equal analyze's.
//
//   node /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/p1/tools/build.mjs
//
// WHY generated: the occupancy panels carry their grid's geometry inline (shape, axis limits, unreachable cells), so the
// views stay generic. The top of the file (data, facets, settings, pages, properties) is the part a person writes; it is
// spelled out literally below so it reads as the proposed API.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { stringifyBase, parseBase } from '/home/bam/data-ui/packages/core/src/base.js';
import { trajectoryDataset, cellsKey, short } from '../coverage/rows.js';
import { jointPanel, toolPanel, directionPanel, TOOL_VIEWS } from '../coverage/grids.js';
import { oracle } from '../coverage/aggregate.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const p1 = path.resolve(here, '..');
const round = path.resolve(p1, '..');
const read = (name) => JSON.parse(fs.readFileSync(path.join(round, 'data', name), 'utf8'));
const coverage = read('coverage.json');
const trajectories = read('trajectories.json');
const membership = read('membership.json');
const datasets = read('datasets.json');

const dataset = trajectoryDataset(coverage, trajectories, membership, datasets);
const joints = coverage.joints;
const planes = Object.keys(coverage.planes[joints[0].name]);
const qqdCells = coverage.planes[joints[0].name].q_qd.shape.reduce((a, b) => a * b, 1);
const qdqddCells = coverage.planes[joints[0].name].qd_qdd.shape.reduce((a, b) => a * b, 1);
const [rings, sectors] = membership.sphere;
const reachableVoxels = (coverage.tool.voxels.reachable || []).length;

// ── the part a person writes ─────────────────────────────────────────────────────────────────────────────────────

// WHY these four slots (data-ui's validated series palette): blue, orange, green, purple read apart in light and dark
// and stay off the heat maps' own colours (the maps are viridis/magma; red is the limit frame).
const DATASET_SLOTS = [1, 2, 3, 7];
const datasetColors = Object.fromEntries(datasets.map((d, i) => [d.dataset, DATASET_SLOTS[i]]));

const top = {
  title: 'UR5e trajectory coverage',
  noun: ['trajectory', 'trajectories'],
  data: 'rows.json',
  // the rail: Dataset FIRST (Zach, Nov 24: "a thing here for like dataset, above split, it can be the first one");
  // split under it applies to every dataset ticked (one facet, one clause: split == "holdout")
  facets: [
    { property: 'dataset', label: 'Dataset', order: datasets.map((d) => d.dataset),
      info: 'Tick one to see only it; tick several to combine them. Split, kind and the rest apply to every dataset ticked.' },
    { property: 'split', label: 'Split', order: ['dev', 'holdout'] },
    { property: 'kind', label: 'Kind' },
    { property: 'tags', label: 'Waypoints' },
    { as: 'search', properties: ['task', 'kind'], label: 'Find a trajectory', placeholder: 'e.g. conveyor-holdout-003' },
    { property: 'duration_s', as: 'slider-histogram', label: 'Duration', unit: 's', collapsed: true },
    { property: 'new_cells', as: 'slider-histogram', label: 'New cells', collapsed: true },
  ],
  // behind the one gear, read by every view on every page (Zach, Nov 23: "things that apply to the entire thing that
  // you set once"); option types are a view's own (CONTRACT §1: dropdown, toggle, slider)
  settings: [
    { key: 'cmap', type: 'dropdown', displayName: 'Colour map', default: 'viridis',
      options: { viridis: 'viridis', magma: 'magma', plasma: 'plasma', inferno: 'inferno', cividis: 'cividis' } },
    { key: 'reverse', type: 'toggle', displayName: 'Reverse (high = dark)', default: false },
    { key: 'scale', type: 'dropdown', displayName: 'Scale', default: 'linear',
      options: { linear: 'linear (clipped at p98)', log: 'log', equalized: 'histogram-equalized', visited: 'visited / not', enough: '≥ enough / not' } },
  ],
  // what a row's drill (its record pane) offers beyond its fields: one button per action, its URL filled from the row
  drill: {
    actions: [
      { label: 'Open in Rerun', post: '/__rerun/open?rrd={rrd}', title: 'Opens {rrd} in the native Rerun viewer (Rerun 0.40): q, qd, qdd per joint and the tool path' },
    ],
  },
  // the dashboards: each page is a CONTRACT §17 layout over the views below; the tab strip lists them in this order
  pages: [
    { name: 'Overview', layout: { columns: 12, rowHeight: 'fit', panels: [
      { view: 'Headline numbers', w: 8, h: 2 },
      { view: 'Datasets in this subset', w: 4, h: 2 },
      { view: 'Every joint', w: 5, h: 3, title: 'Every joint · position × speed' },
      { view: 'Tool from three sides', w: 4, h: 3, title: 'The tool from three sides' },
      { view: 'Pointing', w: 3, h: 3, title: 'Which way the tool points' },
    ] } },
    { name: 'Datasets side by side', layout: { columns: 12, rowHeight: 'fit', panels: [
      { view: 'Datasets side by side', w: 12, h: 5, title: 'Each dataset ticked, one row each · the same colour scale' },
    ] } },
    { name: 'One joint', layout: { columns: 12, rowHeight: 'fit', panels: [
      { view: 'One joint', w: 12, h: 5, style: { title: 'none' } },
    ] } },
    { name: 'Tool position', layout: { columns: 12, rowHeight: 'fit', panels: [
      { view: 'Tool position', w: 12, h: 5, style: { title: 'none' } },
    ] } },
    { name: 'Tool orientation', layout: { columns: 12, rowHeight: 'fit', panels: [
      { view: 'Tool orientation', w: 12, h: 5, style: { title: 'none' } },
    ] } },
    { name: 'Trajectories', layout: { columns: 12, rowHeight: 'fit', panels: [
      { view: 'Trajectories', w: 12, h: 5, style: { title: 'none' } },
    ] } },
  ],
};

const properties = {
  task: { displayName: 'Trajectory' },
  dataset: { displayName: 'Dataset', colors: datasetColors },
  station: { displayName: 'Station', description: 'tool positions are in each station\'s own cell frame: the two stations overlay as numbers, not as one room' },
  split: { displayName: 'Split', colors: { dev: 0, holdout: 0 } },
  kind: { displayName: 'Kind' },
  tags: { displayName: 'Waypoints' },
  order: { displayName: '#' },
  duration_s: { displayName: 'Duration' },
  samples: { displayName: 'Samples' },
  new_cells: { displayName: 'New cells', description: 'position × speed cells (all joints) it was the first to visit, in extract.py\'s order over all 212' },
  only_it_cells: { displayName: 'Only it', description: 'position × speed cells (all joints) no other of the 212 visits: drop it and they are gone' },
  tool_path_m: { displayName: 'Tool path' },
  tool_speed_max_m_s: { displayName: 'Tool speed max' },
  tool_z_min_mm: { displayName: 'Tool z low' },
  tool_z_max_mm: { displayName: 'Tool z high' },
  tool_tilt_max_deg: { displayName: 'Tilt max', description: 'largest tilt of the tool axis from straight down' },
  rrd: { displayName: 'Rerun file' },
};
for (const key of Object.keys(dataset.properties)) if (key.startsWith('cells_')) properties[key] = { hidden: true };

// ── the views (generated geometry) ───────────────────────────────────────────────────────────────────────────────

const FRAME_NOTE = 'Tool positions are in each station\'s own cell frame: UR5e alone and the Conveyor PnP cell overlay as numbers, not as one room.';
const number = (label, summary, extra) => ({ label, summary, ...extra });
const jointQqd = joints.map((joint) => ({ ...jointPanel(coverage, joint, 'q_qd'), title: short(joint.name) }));
const tool = TOOL_VIEWS.map(([key, title, u, v]) => toolPanel(coverage, key, title, u, v));
const pointing = directionPanel(coverage, membership);

const views = [
  {
    type: 'coverage-numbers',
    name: 'Headline numbers',
    numbers: [
      number('Trajectories', 'count', { payload: 'trajectories' }),
      number('Samples', 'sum', { property: 'samples', payload: 'samples' }),
      number('Motion', 'sum', { property: 'duration_s', unit: 's', decimals: 1, payload: 'duration_s' }),
      number('Position × speed cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('q_qd', j.name)), total: qqdCells, unit: '%', note: 'mean over joints', payload: 'q_qd_visited_mean_pct' }),
      number('Speed × accel. cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('qd_qdd', j.name)), total: qdqddCells, unit: '%', note: 'mean over joints', payload: 'qd_qdd_visited_mean_pct' }),
      number('Tool pixels, top view', 'distinct', { property: cellsKey('xy'), note: '2 cm', payload: 'tool_pixels_xy' }),
      number('Tool voxels', 'distinct', { property: cellsKey('voxels'), note: '5 cm', payload: 'tool_voxels_visited' }),
      number('Reachable voxels reached', 'distinct', { property: cellsKey('voxels'), total: reachableVoxels, unit: '%', decimals: 1, payload: 'tool_voxels_reachable_pct' }),
      number('Tool directions', 'distinct', { property: cellsKey('directions'), total: rings * sectors, unit: '%', note: 'equal-area cells', payload: 'tool_directions_visited_pct' }),
      number('Largest tilt', 'max', { property: 'tool_tilt_max_deg', unit: '°', decimals: 0, payload: 'tool_tilt_max_deg', tolerance: 0.01 }),
    ],
    whole: ['q_span_median_pct', 'qd_peak_max_pct', 'qdd_peak_max_pct', 'tool_speed_p99_m_s'],
  },
  {
    type: 'dataset-mix',
    name: 'Datasets in this subset',
    mix: { by: 'dataset', split: 'split', of: 'trajectory' },
  },
  { type: 'occupancy', name: 'Every joint', occupancy: { of: 'trajectory', compact: true, columns: 3, panels: jointQqd } },
  { type: 'occupancy', name: 'Tool from three sides', occupancy: { of: 'trajectory', compact: true, layout: 'hero', equal: true, frame: 'cell', panels: tool } },
  { type: 'occupancy', name: 'Pointing', occupancy: { of: 'trajectory', compact: true, columns: 1, panels: [{ ...pointing, title: 'azimuth × tilt' }] } },
  {
    type: 'occupancy',
    name: 'Datasets side by side',
    occupancy: { of: 'trajectory', compact: true, splitBy: 'dataset', frame: 'cell',
      panels: [...jointQqd.map((p) => ({ ...p, title: `${p.title} q×qd` })), { ...tool[0], title: 'tool from above' }, { ...pointing, title: 'pointing' }] },
  },
  {
    type: 'occupancy',
    name: 'One joint',
    occupancy: { of: 'trajectory', pick: { label: 'Joint' }, columns: 2,
      panels: joints.flatMap((joint) => planes.map((plane) => jointPanel(coverage, joint, plane))) },
  },
  { type: 'occupancy', name: 'Tool position', occupancy: { of: 'trajectory', columns: 2, layout: 'hero', equal: true, frame: 'cell', note: FRAME_NOTE, panels: tool } },
  {
    type: 'occupancy',
    name: 'Tool orientation',
    occupancy: { of: 'trajectory', columns: 1, panels: [{ ...pointing, marginals: { x: 'per azimuth band', y: 'per tilt band' } }] },
  },
  {
    type: 'table',
    name: 'Trajectories',
    order: ['task', 'dataset', 'split', 'kind', 'tags', 'duration_s', 'new_cells', 'only_it_cells', 'tool_path_m', 'tool_speed_max_m_s', 'tool_tilt_max_deg'],
    display: { dataset: 'badge', split: 'badge', new_cells: 'bar', only_it_cells: 'bar' },
    summaries: { duration_s: 'Sum' },
    columnSize: { task: 170, dataset: 190 },
    record: { sections: [{ name: 'Trajectory', properties: ['dataset', 'split', 'kind', 'tags', 'duration_s', 'new_cells', 'only_it_cells'] }] },
  },
];

// analyze's own value beside each re-aggregated number, and the whole-set-only numbers as literals: the page checks
// "nothing filtered = analyze" without loading the 4 MB payload (the grids are checked here, below)
const payloadNumber = (key) => coverage.numbers.find((row) => row.key === key);
for (const spec of views[0].numbers) spec.analyze = payloadNumber(spec.payload).value;
views[0].whole = views[0].whole.map((key) => { const row = payloadNumber(key); return { key, label: row.label, value: row.value, unit: row.unit }; });

const base = { ...top, properties, views };

// ── write and check ──────────────────────────────────────────────────────────────────────────────────────────────

const header = [
  '# P1 "Workbench element" (dashboard-pattern babble, 2026-11-24): the whole document <data-workbench src="coverage.base">',
  '# draws. GENERATED by p1/tools/build.mjs from ../data/ (edit the builder, never this file). The top keys are the',
  '# proposed API: title, noun, data, facets (the rail, Dataset first), settings (behind the one gear), pages (the tabs,',
  '# each a CONTRACT §17 layout). `occupancy`, `coverage-numbers` and `dataset-mix` are views P1 registers',
  '# (coverage/views.js), not stock data-ui; the Trajectories table is stock.',
  '',
].join('\n');
const text = header + stringifyBase(base);
const again = parseBase(text);
if (JSON.stringify(again.pages) !== JSON.stringify(base.pages)) throw new Error('coverage.base does not read back as written (pages)');
fs.writeFileSync(path.join(p1, 'coverage.base'), text);
fs.writeFileSync(path.join(p1, 'rows.json'), JSON.stringify(dataset));
console.log(`wrote coverage.base (${(text.length / 1024).toFixed(0)} KB) and rows.json (${dataset.rows.length} rows)`);

const report = oracle(coverage, dataset, base, membership.voxel_shape);
for (const line of report.lines) console.log(line);
if (report.failures.length) {
  for (const failure of report.failures) console.error('FAIL ' + failure);
  process.exit(1);
}
console.log(`oracle: ${report.checked} grids and numbers rebuilt from the rows equal the payload`);
