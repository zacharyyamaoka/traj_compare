/* base.js — P2's dashboards as one Obsidian Bases / data-ui `.base` document, generated from the coverage payload.
 *
 * Copied from round 2's V2 (coverage-ui-2026-11-24/v2/js/base.js). P2 changes the document, not the figures: the rail's
 * facets put Dataset FIRST (Zach, Nov 24: "a thing here for like dataset, above split, it can be the first one"), each
 * dataset gets a colour slot (one key shared by the rail, the table badges and the Overview's per-dataset maps), and
 * each view carries `icon:` — the rail lists the views as its pages, by name and icon (a key P2 proposes; data-ui keeps
 * an unknown key and warns). The occupancy panels carry their grid geometry inline, so the registered views know
 * nothing about robots. Pure (no DOM).
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

// WHY these slots: four distinct series hues for the four datasets (blue, orange, green, amber), and the split on the
// two that stay apart from them (dev muted, holdout violet), so a dataset badge never reads as a split badge.
export const DATASET_SLOTS = [1, 2, 3, 4, 5, 6, 8];
export const SPLIT_COLORS = { dev: 0, holdout: 7 };

const SEARCH = ['name', 'dataset', 'split', 'kind', 'tags'];
const recordLayout = () => ({ sections: [{ name: 'Trajectory', properties: ['dataset', 'split', 'kind', 'duration_s', 'new_cells', 'only_it_cells'] }] });
const TABLE_ORDER = ['task', 'dataset', 'split', 'kind', 'tags', 'duration_s', 'samples', 'new_cells', 'only_it_cells', 'tool_path_m',
  'tool_speed_max_m_s', 'tool_z_min_mm', 'tool_z_max_mm', 'tool_tilt_max_deg'];

/** The whole `.base` document for P2, as data-ui's parseBase would return it. `datasets` = data/datasets.json. */
export function buildBase(coverage, membership, dataset, datasets) {
  const joints = coverage.joints;
  const planes = Object.keys(coverage.planes[joints[0].name]);
  const qqdCells = coverage.planes[joints[0].name].q_qd.shape.reduce((a, b) => a * b, 1);
  const qdqddCells = coverage.planes[joints[0].name].qd_qdd.shape.reduce((a, b) => a * b, 1);
  const [rings, sectors] = membership.sphere;
  const reachableVoxels = (coverage.tool.voxels.reachable || []).length;
  const datasetColors = Object.fromEntries(datasets.map((d, i) => [d.dataset, DATASET_SLOTS[i % DATASET_SLOTS.length]]));

  const properties = {
    name: { displayName: 'Trajectory' },
    task: { displayName: 'Trajectory', description: 'the task within its dataset; the full name is <dataset slug>/<task>' },
    dataset: { displayName: 'Dataset', colors: datasetColors, description: 'which of the four UR5e datasets the trajectory comes from' },
    dataset_slug: { hidden: true },
    order: { displayName: '#' },
    split: { displayName: 'Split', colors: SPLIT_COLORS, description: 'dev or holdout; the pick applies to every dataset ticked' },
    kind: { displayName: 'Kind' },
    rung: { displayName: 'Rung' },
    tags: { displayName: 'Tags' },
    belt_speed: { displayName: 'Belt speed' },
    duration_s: { displayName: 'Duration' },
    samples: { displayName: 'Samples' },
    new_cells: { displayName: 'New cells', description: "position × speed cells (all joints) it was the first to visit, in its dataset's order" },
    only_it_cells: { displayName: 'Only it', description: 'position × speed cells (all joints) no other of the 212 trajectories visits: drop it and they are gone' },
    tool_path_m: { displayName: 'Tool path' },
    tool_speed_max_m_s: { displayName: 'Tool speed max' },
    tool_z_min_mm: { displayName: 'Tool z low' },
    tool_z_max_mm: { displayName: 'Tool z high' },
    tool_tilt_max_deg: { displayName: 'Tilt max', description: 'largest tilt of the tool axis from straight down' },
    rrd: { displayName: 'Rerun file' },
  };
  for (const key of Object.keys(dataset.properties)) if (key.startsWith('cells_')) properties[key] = { hidden: true };

  const number = (label, summary, extra) => ({ label, summary, ...extra });
  const overview = {
    type: 'coverage-overview',
    name: 'Overview',
    icon: 'layout-dashboard',
    order: SEARCH,
    overview: {
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
      minis: ['All joints', 'Tool position', 'Tool orientation'],
      // the across-datasets row: one small top view per dataset in the subset, in that dataset's colour
      compare: { by: 'dataset', view: 'Tool position', panel: 0 },
    },
  };

  const oneJoint = {
    type: 'occupancy',
    name: 'One joint',
    icon: 'crosshair',
    order: SEARCH,
    occupancy: {
      of: 'trajectory',
      pick: { label: 'Joint' },
      columns: 2,
      panels: joints.flatMap((joint) => planes.map((plane) => jointPanel(coverage, joint, plane))),
    },
  };
  const allJoints = {
    type: 'occupancy',
    name: 'All joints',
    icon: 'grid',
    order: SEARCH,
    occupancy: {
      of: 'trajectory',
      columns: 3,
      compact: true,
      // WHY the bars under each map: which of the joint's position bands the rows reach (its "span"), re-aggregated
      panels: joints.map((joint) => ({ ...jointPanel(coverage, joint, 'q_qd'), title: short(joint.name), marginals: { x: 'position' } })),
    },
  };
  const toolPosition = {
    type: 'occupancy',
    name: 'Tool position',
    icon: 'map-pin',
    order: SEARCH,
    occupancy: {
      of: 'trajectory',
      columns: 2,
      layout: 'hero',
      equal: true,
      frame: coverage.tool.frame,
      panels: VIEWS.map(([key, title, u, v]) => toolPanel(coverage, key, title, u, v)),
    },
  };
  const toolOrientation = {
    type: 'occupancy',
    name: 'Tool orientation',
    icon: 'compass',
    order: SEARCH,
    occupancy: { of: 'trajectory', columns: 1, panels: [directionPanel(coverage, membership)] },
  };
  const trajectoriesTable = {
    type: 'table',
    name: 'Trajectories',
    icon: 'table',
    order: TABLE_ORDER,
    display: { dataset: 'badge', split: 'badge', new_cells: 'bar', only_it_cells: 'bar' },
    summaries: { duration_s: 'Sum', samples: 'Sum' },
    columnSize: { task: 190, dataset: 170 },
    // the record peek (the drill): the few fields that say what it is and what it adds; the rest fold under "more"
    record: recordLayout(),
  };

  return {
    facets: [
      // WHY Dataset first and Split right under it: the split is one pick that applies to every dataset ticked
      // (Zach, Nov 24: "I don't want the option to like include dev of one particular dataset and not of the other")
      { property: 'dataset', label: 'Dataset', order: datasets.map((d) => d.dataset) },
      { property: 'split', label: 'Split', order: ['dev', 'holdout'] },
      { property: 'kind', label: 'Kind' },
      { property: 'tags', label: 'Tags' },
      { as: 'search', properties: ['name', 'kind', 'tags'], label: 'Trajectory', placeholder: 'Find by name (try conveyor-holdout)' },
      { property: 'duration_s', as: 'slider-histogram', label: 'Duration', unit: 's' },
      { property: 'new_cells', as: 'slider-histogram', label: 'New cells' },
      { property: 'tool_z_min_mm', as: 'range', label: 'Tool z low', unit: 'mm' },
      { property: 'tool_z_max_mm', as: 'range', label: 'Tool z high', unit: 'mm' },
    ],
    properties,
    views: [overview, allJoints, oneJoint, toolPosition, toolOrientation, trajectoriesTable],
  };
}
