/* base.js — P4's whole component as ONE `.base` document: the run list (`runs:`), the dataset colours
 * (`properties.dataset.colors`), and the dashboards as views (`views:`), each a `sections` view (TensorBoard's tag
 * groups) whose `figures:` are its collapsible sections, or the stock table. (Not `sections:`: data-ui's cards own that key.) Generated from the coverage payload because the occupancy panels carry their
 * grid's geometry inline (shape, axis limits, unreachable cells), so the figures know nothing about robots.
 *
 * Panel geometry is round 2's V2 (js/base.js), copied. Pure (no DOM); tools/emit.mjs writes it to ../coverage.base.
 */

import { cellsKey, short } from './rows.js';

const DEG = 180 / Math.PI;
const WORD = { q: 'position', qd: 'speed', qdd: 'acceleration' };
const UNIT = { q: '°', qd: '°/s', qdd: '°/s²' };
const QUESTION = { q_qd: 'Position × speed', qd_qdd: 'Speed × acceleration', q_qdd: 'Position × acceleration' };
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
    code: `${block.x}×${block.y}`,
    cells: cellsKey(plane, joint.name),
    shape: block.shape,
    order: 'x-major',
    aspect: 0.62,
    xAxis: jointAxis(joint, block.x, block.x_edges),
    yAxis: jointAxis(joint, block.y, block.y_edges),
    frame: 'limit',
    zero: block.x === 'q' ? 'y' : 'both',
    payload: `planes.${joint.name}.${plane}`,
  };
}

const SIDES = [['xy', 'From above', 'x', 'y'], ['xz', 'From the front', 'x', 'z'], ['yz', 'From the side', 'y', 'z']];

function toolPanel(coverage, key, title, u, v) {
  const tool = coverage.tool;
  const block = tool.projections[key];
  const [nu, nv] = block.shape;
  const mm = (value) => round(value * 1000, 1);
  return {
    title,
    code: `${u}, ${v}`,
    cells: cellsKey(key),
    shape: block.shape,
    order: 'x-major',
    equal: true,
    xAxis: { label: u, unit: 'mm', lo: mm(block.origin[0]), hi: mm(block.origin[0] + nu * tool.pixel_m) },
    yAxis: { label: v, unit: 'mm', lo: mm(block.origin[1]), hi: mm(block.origin[1] + nv * tool.pixel_m) },
    unreachable: block.reachable ? zeroRuns(block.reachable) : [],
    origin: true,
    payload: `tool.projections.${key}`,
  };
}

function directionPanel(coverage, membership) {
  const [rings, sectors] = membership.sphere;
  // WHY these edges (V2's): the sphere's rings are equal bands of the tool axis' z (equal area), so drawn as equal rows
  // the map IS Lambert's cylindrical equal-area projection: equal rectangles, equal solid angle.
  const tiltEdges = [];
  for (let k = 0; k <= rings; k += 1) tiltEdges.push(round(Math.acos(Math.max(-1, Math.min(1, 1 - (2 * k) / rings))) * DEG, 1));
  return {
    title: 'Where it points',
    code: 'azimuth, tilt',
    cells: cellsKey('directions'),
    shape: [sectors, rings],
    order: 'y-major',
    aspect: 0.5,
    xAxis: { label: 'azimuth', unit: '°', lo: -180, hi: 180 },
    yAxis: { label: 'tilt from down', unit: '°', lo: 0, hi: 180, flip: true, edges: tiltEdges },
    payload: 'tool.orientation.sphere',
  };
}

// WHY slots 1-4 for the datasets and 0 / 7 for the split: the dataset is what every figure colours by (the run list's
// swatches, the maps' row bands, the bars, the table's badges are one palette, data-ui's series tokens); the split's
// badge stays out of those four hues so "orange" always means one dataset.
export function datasetColors(datasets) {
  return Object.fromEntries(datasets.map((d, i) => [d.dataset, i + 1]));
}

/** The whole `.base` document, as data-ui's parseBase would return it. */
export function buildBase(coverage, membership, dataset, datasets) {
  const joints = coverage.joints;
  const planes = Object.keys(coverage.planes[joints[0].name]);
  const qqdCells = coverage.planes[joints[0].name].q_qd.shape.reduce((a, b) => a * b, 1);
  const qdqddCells = coverage.planes[joints[0].name].qd_qdd.shape.reduce((a, b) => a * b, 1);
  const [rings, sectors] = membership.sphere;
  const reachableVoxels = (coverage.tool.voxels.reachable || []).length;

  const properties = {
    task: { displayName: 'Trajectory' },
    dataset: { displayName: 'Dataset', colors: datasetColors(datasets) },
    dataset_order: { displayName: 'Dataset #', hidden: true },
    order: { displayName: '#', hidden: true },
    split: { displayName: 'Split', colors: { dev: 0, holdout: 7 } },
    kind: { displayName: 'Kind' },
    tags: { displayName: 'Tags' },
    duration_s: { displayName: 'Duration' },
    samples: { displayName: 'Samples' },
    new_cells: { displayName: 'New cells', description: 'position × speed cells (all joints) it was the first to visit, in the 212\'s order' },
    only_it_cells: { displayName: 'Only it', description: 'position × speed cells (all joints) no other of the 212 visits' },
    tool_path_m: { displayName: 'Tool path' },
    tool_speed_max_m_s: { displayName: 'Tool speed max' },
    tool_z_min_mm: { displayName: 'Tool z low' },
    tool_z_max_mm: { displayName: 'Tool z high' },
    tool_tilt_max_deg: { displayName: 'Tilt max', description: 'largest tilt of the tool axis from straight down' },
    rrd: { displayName: 'Rerun file' },
  };
  for (const key of Object.keys(dataset.properties)) if (key.startsWith('cells_')) properties[key] = { hidden: true };

  const number = (label, summary, extra) => ({ label, summary, ...extra });
  const numbers = [
    number('Trajectories', 'count', { payload: 'trajectories', decimals: 0 }),
    number('Samples', 'sum', { property: 'samples', payload: 'samples', decimals: 0, wide: true }),
    number('Motion', 'sum', { property: 'duration_s', unit: 's', decimals: 0, payload: 'duration_s' }),
    number('Position × speed cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('q_qd', j.name)), total: qqdCells, unit: '%', decimals: 1, note: 'mean over joints', payload: 'q_qd_visited_mean_pct' }),
    number('Speed × accel. cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('qd_qdd', j.name)), total: qdqddCells, unit: '%', decimals: 1, note: 'mean over joints', payload: 'qd_qdd_visited_mean_pct', wide: true }),
    number('Tool pixels, top view', 'distinct', { property: cellsKey('xy'), note: '2 cm', decimals: 0, payload: 'tool_pixels_xy' }),
    number('Tool voxels', 'distinct', { property: cellsKey('voxels'), note: '5 cm', decimals: 0, payload: 'tool_voxels_visited', wide: true }),
    number('Reachable voxels reached', 'distinct', { property: cellsKey('voxels'), total: reachableVoxels, unit: '%', decimals: 1, payload: 'tool_voxels_reachable_pct', wide: true }),
    number('Tool directions', 'distinct', { property: cellsKey('directions'), total: rings * sectors, unit: '%', decimals: 1, note: 'equal-area cells', payload: 'tool_directions_visited_pct' }),
    number('Largest tilt', 'max', { property: 'tool_tilt_max_deg', unit: '°', decimals: 0, payload: 'tool_tilt_max_deg', tolerance: 0.01 }),
  ];
  const jointMaps = joints.map((joint) => ({ ...jointPanel(coverage, joint, 'q_qd'), title: short(joint.name) }));
  const allPlanes = joints.flatMap((joint) => planes.map((plane) => jointPanel(coverage, joint, plane)));
  const sides = SIDES.map(([key, title, u, v]) => toolPanel(coverage, key, title, u, v));
  const pointing = directionPanel(coverage, membership);
  const share = (panel, total, label) => ({ label: label || panel.title, cells: panel.cells, total, group: panel.group });

  const overview = {
    type: 'sections',
    name: 'Overview',
    status: false,  // §18: the dashboard says its own subset line; data-ui's "N of M rows" would repeat it
    colorBy: 'dataset',
    figures: [
      { key: 'numbers', title: 'Headline numbers', note: 'a row per dataset shown (a runs table), and all of them together', kind: 'numbers', numbers },
      { key: 'joints', title: 'Every joint · which positions and speeds', note: 'position × speed, trajectories per cell', kind: 'maps', compact: true, panels: jointMaps },
      { key: 'tool', title: 'The tool · from three sides, and where it points', note: "tool pixels (2 cm, each deployment's own cell frame) and directions", kind: 'maps', compact: true, panels: [...sides, pointing] },
    ],
  };
  const oneJoint = {
    type: 'sections',
    name: 'One joint',
    status: false,  // §18: the dashboard says its own subset line; data-ui's "N of M rows" would repeat it
    colorBy: 'dataset',
    pick: { label: 'Joint', options: joints.map((joint) => short(joint.name)) },
    figures: [
      { key: 'planes', title: '{pick} · position, speed and acceleration', note: 'trajectories per cell; red frame = the joint\'s limits', kind: 'maps', panels: allPlanes, pickBy: 'group' },
      { key: 'share', title: '{pick} · cells visited, per dataset', note: 'share of each plane\'s cells any trajectory of the dataset visits', kind: 'bars', unit: '%', pickBy: 'group',
          items: allPlanes.map((panel) => share(panel, panel.shape[0] * panel.shape[1])) },
    ],
  };
  const toolPosition = {
    type: 'sections',
    name: 'Tool position',
    status: false,  // §18: the dashboard says its own subset line; data-ui's "N of M rows" would repeat it
    colorBy: 'dataset',
    figures: [
      { key: 'sides', title: 'From above, the front and the side', note: "2 cm pixels, one mm-per-px scale; each deployment's own cell frame", kind: 'maps', panels: sides },
      { key: 'share', title: 'Tool pixels and voxels, per dataset', note: 'distinct cells the tool passed through', kind: 'bars', items: [
          ...sides.map((panel) => share(panel, null, `${panel.title} (pixels)`)),
          { label: 'Voxels (5 cm)', cells: cellsKey('voxels'), total: null },
        ] },
    ],
  };
  const toolOrientation = {
    type: 'sections',
    name: 'Tool orientation',
    status: false,  // §18: the dashboard says its own subset line; data-ui's "N of M rows" would repeat it
    colorBy: 'dataset',
    figures: [
      { key: 'pointing', title: 'Which way does the tool point?', note: 'equal-area map of the tool axis: azimuth × tilt from straight down', kind: 'maps', panels: [pointing] },
      { key: 'share', title: 'Directions visited, per dataset', note: 'share of the 288 equal-area direction cells', kind: 'bars', unit: '%', items: [share(pointing, rings * sectors, 'Directions visited')] },
    ],
  };
  const table = {
    type: 'table',
    name: 'Trajectories',
    order: ['task', 'dataset', 'split', 'kind', 'tags', 'duration_s', 'samples', 'new_cells', 'only_it_cells', 'tool_path_m',
      'tool_speed_max_m_s', 'tool_tilt_max_deg'],
    sort: [{ property: 'dataset_order', direction: 'ASC' }, { property: 'order', direction: 'ASC' }],
    display: { dataset: 'badge', split: 'badge', only_it_cells: 'bar' },
    summaries: { duration_s: 'Sum', samples: 'Sum' },
    columnSize: { task: 180, dataset: 190 },
    record: { sections: [{ name: 'Trajectory', properties: ['dataset', 'split', 'kind', 'duration_s', 'only_it_cells'] }] },
  };

  return {
    // NEW (P4's proposal): the run list's keys. data-ui would read them as `<data-runs for>` reads `facets:` today.
    runs: {
      group: 'dataset',
      label: 'Datasets',
      title: 'task',
      toggles: [{ property: 'split', label: 'Split' }, { property: 'kind', label: 'Kind' }],
      regex: ['dataset', 'task'],
    },
    properties,
    views: [overview, oneJoint, toolPosition, toolOrientation, table],
  };
}

/** Every grid the sections draw, once each (the oracle's list). */
export function allPanels(base) {
  const out = new Map();
  for (const view of base.views) for (const figure of view.figures || []) {
    if (figure.kind === 'maps') for (const panel of figure.panels) if (!out.has(panel.cells)) out.set(panel.cells, panel);
  }
  return [...out.values()];
}
