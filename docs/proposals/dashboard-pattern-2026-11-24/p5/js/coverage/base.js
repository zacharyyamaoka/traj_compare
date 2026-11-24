/* base.js — P5's scope document: one `.base` (as data-ui's parseBase returns it) that the <data-scope> holds and every
 * part inside it reads: `facets:` (the one filter's rail), `properties:`, `views:`, and the two keys P5 proposes,
 * `dashboards:` (named layouts over those views, one per tab) and `settings:` (the gear's controls, set once per scope).
 *
 * WHY generated: the occupancy panels carry their grid's geometry (shape, axis limits, the unreachable cells) inline, so
 * the registered `occupancy` view knows nothing about robots. Those numbers come from the payload. The panel builders
 * are round 2's V2 (coverage-ui-2026-11-24/v2/js/base.js), copied; the document below is P5's.
 *
 * Pure (no DOM).
 */

import { cellsKey, short } from './rows.js';

const DEG = 180 / Math.PI;
const WORD = { q: 'position', qd: 'speed', qdd: 'acceleration' };
const UNIT = { q: '°', qd: '°/s', qdd: '°/s²' };
const QUESTION = {
  q_qd: 'Which positions and speeds?',
  qd_qdd: 'Which speeds and accelerations?',
  q_qdd: 'Which positions and accelerations?',
};
const round = (value, digits = 4) => Math.round(value * 10 ** digits) / 10 ** digits;

/** Runs [start, length] of the cells where `flags` is 0: the unreachable pixels, small enough to sit in a view entry. */
export function zeroRuns(flags) {
  const runs = [];
  let start = -1;
  for (let i = 0; i <= flags.length; i += 1) {
    const off = i < flags.length && !flags[i];
    if (off && start < 0) start = i;
    if (!off && start >= 0) { runs.push([start, i - start]); start = -1; }
  }
  return runs;
}

function jointAxis(joint, signal, edges) {
  const scale = joint.kind === 'revolute' ? DEG : 1;
  return { label: `${signal} · ${WORD[signal]}`, unit: UNIT[signal], lo: round(edges[0] * scale, 2), hi: round(edges[1] * scale, 2) };
}

function jointPanel(coverage, joint, plane) {
  const block = coverage.planes[joint.name][plane];
  return {
    group: short(joint.name),
    title: QUESTION[plane] || plane,
    code: `${short(joint.name)} ${block.x}×${block.y}`,
    cells: cellsKey(plane, joint.name),
    shape: block.shape,
    order: 'x-major',
    xAxis: jointAxis(joint, block.x, block.x_edges),
    yAxis: jointAxis(joint, block.y, block.y_edges),
    frame: 'limit',
    zero: block.x === 'q' ? 'y' : 'both',
    payload: `planes.${joint.name}.${plane}`,
  };
}

const VIEWS = [['xy', 'From above', 'x', 'y'], ['xz', 'From the front', 'x', 'z'], ['yz', 'From the side', 'y', 'z']];

function toolPanel(coverage, key, title, u, v) {
  const tool = coverage.tool;
  const block = tool.projections[key];
  const [nu, nv] = block.shape;
  const mm = (value) => round(value * 1000, 1);
  return {
    title: `${title} (${u}, ${v})`,
    code: `tool ${key}`,
    cells: cellsKey(key),
    shape: block.shape,
    order: 'x-major',
    xAxis: { label: u, unit: 'mm', lo: mm(block.origin[0]), hi: mm(block.origin[0] + nu * tool.pixel_m) },
    yAxis: { label: v, unit: 'mm', lo: mm(block.origin[1]), hi: mm(block.origin[1] + nv * tool.pixel_m) },
    unreachable: block.reachable ? zeroRuns(block.reachable) : [],
    origin: true,
    payload: `tool.projections.${key}`,
  };
}

function directionPanel(coverage, membership) {
  const [rings, sectors] = membership.sphere;
  // WHY these edges: the sphere's rings are equal bands of the tool axis' z (equal area, Archimedes), so a ring's
  // tilt from straight down (the reference -z) is arccos(-z) at its two edges; drawn as equal rows they ARE the
  // Lambert cylindrical equal-area map: equal rectangles, equal solid angle.
  const tiltEdges = [];
  for (let k = 0; k <= rings; k += 1) tiltEdges.push(round(Math.acos(Math.max(-1, Math.min(1, 1 - (2 * k) / rings))) * DEG, 1));
  const reference = coverage.tool.orientation.reference;
  const down = reference[0] === 0 && reference[1] === 0 && reference[2] < 0;
  return {
    title: 'Which way does the tool point?',
    code: 'tool directions',
    cells: cellsKey('directions'),
    shape: [sectors, rings],
    order: 'y-major',
    xAxis: { label: 'azimuth · which way it leans, in the x-y plane', unit: '°', lo: -180, hi: 180 },
    yAxis: { label: down ? 'tilt from straight down' : 'tilt from the reference', unit: '°', lo: 0, hi: 180, flip: true, edges: tiltEdges },
    marginals: { x: 'per azimuth band', y: 'per tilt band' },
    payload: 'tool.orientation.sphere',
  };
}


// WHY one colour per dataset, and split as a word: comparing datasets is the colour channel (Zach: "1 is across datasets");
// the hexes are data-ui's own series slots 1, 2, 3 and 7 (light), so the rail's swatches, the table's badges and the
// stock chart all draw the same four colours.
export const DATASET_SLOTS = [1, 2, 3, 7];
export const DATASET_HEX = ['#2a78d6', '#eb6834', '#1baf7a', '#6250d6'];

const TABLE_ORDER = ['task', 'dataset', 'split', 'kind', 'duration_s', 'new_cells', 'only_it_cells', 'tool_path_m', 'tool_tilt_max_deg'];

/** The whole scope document for P5. `datasets` is data/datasets.json (labels in their order). */
export function buildBase(coverage, membership, dataset, datasets) {
  const joints = coverage.joints;
  const planes = Object.keys(coverage.planes[joints[0].name]);
  const qqdCells = coverage.planes[joints[0].name].q_qd.shape.reduce((a, b) => a * b, 1);
  const qdqddCells = coverage.planes[joints[0].name].qd_qdd.shape.reduce((a, b) => a * b, 1);
  const [rings, sectors] = membership.sphere;
  const reachableVoxels = (coverage.tool.voxels.reachable || []).length;
  const labels = datasets.map((d) => d.dataset);
  const slot = Object.fromEntries(labels.map((label, i) => [label, DATASET_SLOTS[i]]));
  const hex = Object.fromEntries(labels.map((label, i) => [label, DATASET_HEX[i]]));

  const properties = {
    task: { displayName: 'Trajectory' },
    name: { displayName: 'Full name' },
    dataset: { displayName: 'Dataset', colors: slot, description: 'Which of the four UR5e datasets the trajectory belongs to' },
    dataset_slug: { displayName: 'Dataset slug' },
    order: { displayName: '#' },
    split: { displayName: 'Split', colors: { dev: 0, holdout: 0 }, description: 'dev or holdout; a tick applies to every dataset ticked above it' },
    kind: { displayName: 'Kind' },
    rung: { displayName: 'Rung' },
    tags: { displayName: 'Tags' },
    belt_speed: { displayName: 'Belt speed' },
    duration_s: { displayName: 'Duration' },
    samples: { displayName: 'Samples' },
    new_cells: { displayName: 'New cells', description: "position × speed cells (all joints) it was the first to visit, in the dataset's order" },
    only_it_cells: { displayName: 'Only it', description: 'position × speed cells (all joints) no other trajectory of the 212 visits: drop it and they are gone' },
    tool_path_m: { displayName: 'Tool path' },
    tool_speed_max_m_s: { displayName: 'Tool speed max' },
    tool_z_min_mm: { displayName: 'Tool z low' },
    tool_z_max_mm: { displayName: 'Tool z high' },
    tool_tilt_max_deg: { displayName: 'Tilt max', description: 'largest tilt of the tool axis from straight down' },
    rrd: { displayName: 'Rerun file' },
  };
  for (const key of Object.keys(dataset.properties)) if (key.startsWith('cells_')) properties[key] = { hidden: true };

  const number = (label, summary, extra) => ({ label, summary, ...extra });
  const quiet = { status: false };
  const numbers = {
    type: 'coverage-numbers', name: 'Headline numbers', ...quiet,
    numbers: [
      number('Trajectories', 'count', { payload: 'trajectories' }),
      number('Samples', 'sum', { property: 'samples', payload: 'samples' }),
      number('Motion', 'sum', { property: 'duration_s', unit: 's', decimals: 0, payload: 'duration_s' }),
      number('Position × speed cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('q_qd', j.name)), total: qqdCells, unit: '%', note: 'mean over joints', payload: 'q_qd_visited_mean_pct' }),
      number('Speed × accel. cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('qd_qdd', j.name)), total: qdqddCells, unit: '%', note: 'mean over joints', payload: 'qd_qdd_visited_mean_pct' }),
      number('Tool pixels, top view', 'distinct', { property: cellsKey('xy'), note: '2 cm', payload: 'tool_pixels_xy' }),
      number('Tool voxels', 'distinct', { property: cellsKey('voxels'), note: '5 cm', payload: 'tool_voxels_visited' }),
      number('Reachable voxels reached', 'distinct', { property: cellsKey('voxels'), total: reachableVoxels, unit: '%', decimals: 1, payload: 'tool_voxels_reachable_pct' }),
      number('Tool directions', 'distinct', { property: cellsKey('directions'), total: rings * sectors, unit: '%', note: 'equal-area cells', payload: 'tool_directions_visited_pct' }),
      number('Largest tilt', 'max', { property: 'tool_tilt_max_deg', unit: '°', decimals: 0, payload: 'tool_tilt_max_deg', tolerance: 0.01 }),
    ],
    whole: ['q_span_median_pct', 'qd_peak_max_pct', 'qdd_peak_max_pct', 'tool_speed_p99_m_s'],
  };
  const byDataset = {
    type: 'coverage-datasets', name: 'Datasets in this subset', ...quiet,
    datasets: { property: 'dataset', order: labels, colors: hex, sizes: Object.fromEntries(datasets.map((d) => [d.dataset, d.trajectories])),
      cells: joints.map((j) => cellsKey('q_qd', j.name)), cellsTotal: qqdCells, voxels: cellsKey('voxels'), voxelsTotal: reachableVoxels },
  };
  const jointPanels = joints.map((joint) => ({ ...jointPanel(coverage, joint, 'q_qd'), title: short(joint.name) }));
  const toolPanels = VIEWS.map(([key, title, u, v]) => toolPanel(coverage, key, title, u, v));
  const sphere = directionPanel(coverage, membership);
  const occupancy = (name, spec, extra) => ({ type: 'occupancy', name, ...quiet, occupancy: { of: 'trajectory', ...spec }, ...extra });

  const views = [
    numbers,
    byDataset,
    occupancy('Every joint · position × speed', { columns: 3, compact: true, panels: jointPanels, open: 'One joint' }),
    occupancy('The tool from three sides', { columns: 2, compact: true, layout: 'hero', equal: true, frame: coverage.tool.frame, panels: toolPanels, open: 'Tool position' }),
    occupancy('Which way it points', { columns: 1, compact: true, panels: [sphere], open: 'Tool orientation', aspect: 0.5 }),
    // the one-joint dashboard's own control: `pick` draws the joint picker INSIDE this view (a within-tab filter)
    occupancy('One joint', { pick: { label: 'Joint' }, columns: 2, panels: joints.flatMap((joint) => planes.map((plane) => jointPanel(coverage, joint, plane))) }),
    occupancy('Tool position', { columns: 2, layout: 'hero', equal: true, frame: coverage.tool.frame, panels: toolPanels }),
    occupancy('Tool orientation', { columns: 1, panels: [{ ...sphere, marginals: { x: 'per azimuth band', y: 'per tilt band' } }] }),
    {
      type: 'chart', name: 'Largest tilt, per trajectory', ...quiet, controls: false,
      chart: {
        mark: { type: 'tick', thickness: 2 },
        encoding: {
          x: { field: 'tool_tilt_max_deg', type: 'quantitative', title: 'largest tilt from straight down (°)', scale: { type: 'linear', zero: true } },
          y: { field: 'dataset', type: 'nominal', title: null, sort: labels },
          color: { field: 'dataset', type: 'nominal', scale: { domain: labels, range: labels.map((l) => hex[l]) }, legend: null },
        },
      },
    },
    {
      type: 'chart', name: 'Lowest tool height, per trajectory', ...quiet, controls: false,
      chart: {
        mark: { type: 'tick', thickness: 2 },
        encoding: {
          x: { field: 'tool_z_min_mm', type: 'quantitative', title: 'lowest tool z in the cell frame (mm)', scale: { type: 'linear', zero: false } },
          y: { field: 'dataset', type: 'nominal', title: null, sort: labels },
          color: { field: 'dataset', type: 'nominal', scale: { domain: labels, range: labels.map((l) => hex[l]) }, legend: null },
        },
      },
    },
    {
      type: 'table', name: 'Trajectories', order: TABLE_ORDER,
      sort: [{ property: 'only_it_cells', direction: 'DESC' }],
      display: { dataset: 'badge', split: 'badge', new_cells: 'bar', only_it_cells: 'bar' },
      columnSize: { task: 170, dataset: 190 },
      record: { sections: [{ name: 'Trajectory', properties: ['dataset', 'split', 'kind', 'duration_s', 'new_cells', 'only_it_cells'] }] },
    },
  ];

  // P5's proposed key: named dashboards over the views above, one per tab. A <data-dashboard tab="…"> inside the scope
  // draws the entry of its name; the panels are stock data-ui layout panels (docs/CONTRACT.md §17).
  const dashboards = {
    Overview: { layout: { columns: 12, rowHeight: 90, arrange: false, panels: [
      { view: 'Headline numbers', w: 7, h: 3, title: 'Headline numbers · the trajectories the filter leaves' },
      { view: 'Datasets in this subset', w: 5, h: 3 },
      { view: 'Every joint · position × speed', w: 5, h: 5 },
      { view: 'The tool from three sides', w: 4, h: 5 },
      { view: 'Which way it points', w: 3, h: 5 },
    ] } },
    'One joint': { layout: { columns: 12, rowHeight: 100, arrange: false, panels: [{ view: 'One joint', w: 12, h: 7, title: 'One joint: position, speed and acceleration' }] } },
    'Tool position': { layout: { columns: 12, rowHeight: 100, arrange: false, panels: [
      { view: 'Tool position', w: 12, h: 6, title: 'Where the tool goes' },
      { view: 'Lowest tool height, per trajectory', w: 12, h: 2 },
    ] } },
    'Tool orientation': { layout: { columns: 12, rowHeight: 100, arrange: false, panels: [
      { view: 'Tool orientation', w: 12, h: 5, title: 'Which way the tool points' },
      { view: 'Largest tilt, per trajectory', w: 12, h: 2 },
    ] } },
  };

  return {
    // the one filter's rail, top to bottom. Dataset FIRST (Zach, Nov 24: "dataset, above split, it can be the first one"),
    // a swatch per dataset = the dataset colour key; split under it applies to every dataset ticked.
    facets: [
      { property: 'dataset', as: 'swatch', label: 'Dataset', columns: 1, order: labels, colors: hex },
      { property: 'split', label: 'Split', order: ['dev', 'holdout'] },
      { property: 'kind', label: 'Kind' },
      { property: 'tags', label: 'Tags' },
      { property: 'belt_speed', label: 'Belt speed', collapsed: true },
      { as: 'search', properties: ['task', 'name', 'kind', 'tags'], label: 'Find trajectories', placeholder: 'e.g. conveyor-holdout-003' },
      { property: 'duration_s', as: 'slider-histogram', label: 'Duration', unit: 's' },
      { property: 'new_cells', as: 'slider-histogram', label: 'New cells', collapsed: true },
      { property: 'tool_z_min_mm', as: 'range', label: 'Tool z low', unit: 'mm', collapsed: true },
    ],
    properties,
    views,
    dashboards,
    // P5's proposed key: the scope's settings, behind one gear, read by every view inside the scope (input.settings)
    settings: [
      { key: 'cmap', as: 'select', label: 'Colour map', options: globalThis.CoverageColor ? globalThis.CoverageColor.NAMES : ['viridis'], default: 'viridis' },
      { key: 'reverse', as: 'toggle', label: 'Reverse (high = dark)', default: false },
      { key: 'scale', as: 'select', label: 'Scale', options: globalThis.CoverageColor ? globalThis.CoverageColor.SCALES : ['linear'],
        labels: globalThis.CoverageColor ? globalThis.CoverageColor.SCALE_TITLES : {}, default: 'linear' },
    ],
  };
}
