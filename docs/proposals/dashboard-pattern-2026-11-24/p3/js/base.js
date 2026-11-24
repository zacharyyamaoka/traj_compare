/* base.js — P3's whole component as ONE Obsidian Bases / data-ui `.base` document, generated from the coverage payload.
 *
 * P3's thesis, in this file's shape: every dashboard is a `views:` entry (a preset, so a data-ui view tab), and a
 * dashboard is the proposed view type `panels`, whose `panels:` are view entries drawn over the rows the
 * all-views filter (the rail) leaves. The Trajectories table is a stock `table` preset beside them; a reader's own tab
 * is a user view of either type (+ in the bar, or Save view with the filter kept). Nothing here is page code.
 *
 * WHY generated: the occupancy grids carry their geometry (shape, axis limits, the unreachable cells) inline, so the
 * `occupancy` view knows nothing about robots. tools/emit.mjs writes the same document to ../coverage.base so
 * `data-ui check` reads every key, and a reader sees the dashboards as text. Pure (no DOM): imported by page and Node.
 *
 * Keys that are NOT data-ui today (the proposal, docs in ../NOTES.md):
 *   settings:                top level: component-wide settings behind one gear in the bar, handed to every view
 *   type: panels             a dashboard as a view: panels: [{key, title, w (of 12), view | use, open, repeat}]
 *   vars:                    on a panels view: its own controls (Grafana's dashboard variables), ${key} in its panels
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

// WHY these slots (data-ui's series tokens, CONTRACT §4): four hues far apart for the four datasets, so a dot in the
// rail, a badge in the table and a stripe on a dashboard all say "which dataset" at a glance; split stays muted (dev)
// and purple (holdout), a hue no dataset uses.
export const DATASET_SLOTS = {
  'UR5e alone · Workspace': 1,
  'Cell · Workspace': 2,
  'Cell · Conveyor PnP': 3,
  'Cell · Conveyor Collision': 5,
};

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

function jointGrid(coverage, joint, plane) {
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

const SIDES = [['xy', 'From above', 'x', 'y'], ['xz', 'From the front', 'x', 'z'], ['yz', 'From the side', 'y', 'z']];

function toolGrid(coverage, key, title, u, v) {
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

function directionGrid(coverage, membership) {
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

// the line every dashboard draws under the bar: which rows (by dataset, by split) every panel is drawing
const SUBSET = { noun: 'trajectory', by: ['dataset', 'split'] };

const TABLE_ORDER = ['task', 'dataset', 'split', 'kind', 'duration_s', 'new_cells', 'only_it_cells', 'tool_path_m',
  'tool_speed_max_m_s', 'tool_tilt_max_deg', 'samples', 'tags'];

/** The whole `.base` document for P3, as data-ui's parseBase would return it. */
export function buildBase(coverage, membership, dataset) {
  const joints = coverage.joints;
  const planes = Object.keys(coverage.planes[joints[0].name]);
  const qqdCells = coverage.planes[joints[0].name].q_qd.shape.reduce((a, b) => a * b, 1);
  const qdqddCells = coverage.planes[joints[0].name].qd_qdd.shape.reduce((a, b) => a * b, 1);
  const qqddCells = coverage.planes[joints[0].name].q_qdd.shape.reduce((a, b) => a * b, 1);
  const [rings, sectors] = membership.sphere;
  const reachableVoxels = (coverage.tool.voxels.reachable || []).length;
  const jointNames = joints.map((j) => short(j.name));

  const properties = {
    task: { displayName: 'Trajectory' },
    name: { displayName: 'Dataset / task' },
    order: { displayName: '#' },
    dataset: { displayName: 'Dataset', colors: DATASET_SLOTS, description: 'Which of the four UR5e datasets the trajectory is from' },
    split: { displayName: 'Split', colors: { dev: 0, holdout: 7 } },
    kind: { displayName: 'Kind' },
    tags: { displayName: 'Tags' },
    belt_speed: { displayName: 'Belt speed' },
    duration_s: { displayName: 'Duration' },
    samples: { displayName: 'Samples' },
    new_cells: { displayName: 'New cells', description: "position × speed cells (all joints) it was the first to visit, in the set's order" },
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
  const headline = [
    number('Trajectories', 'count', { payload: 'trajectories' }),
    number('Samples', 'sum', { property: 'samples', payload: 'samples' }),
    number('Motion', 'sum', { property: 'duration_s', unit: 's', decimals: 1, payload: 'duration_s' }),
    number('Position × speed cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('q_qd', j.name)), total: qqdCells, unit: '%', note: 'mean over joints', payload: 'q_qd_visited_mean_pct' }),
    number('Speed × accel. cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('qd_qdd', j.name)), total: qdqddCells, unit: '%', note: 'mean over joints', payload: 'qd_qdd_visited_mean_pct' }),
    number('Tool pixels, from above', 'distinct', { property: cellsKey('xy'), note: '2 cm', payload: 'tool_pixels_xy' }),
    number('Tool voxels', 'distinct', { property: cellsKey('voxels'), note: '5 cm', payload: 'tool_voxels_visited' }),
    number('Reachable voxels reached', 'distinct', { property: cellsKey('voxels'), total: reachableVoxels, unit: '%', decimals: 1, payload: 'tool_voxels_reachable_pct' }),
    number('Tool directions', 'distinct', { property: cellsKey('directions'), total: rings * sectors, unit: '%', note: 'equal-area cells', payload: 'tool_directions_visited_pct' }),
    number('Largest tilt', 'max', { property: 'tool_tilt_max_deg', unit: '°', decimals: 0, payload: 'tool_tilt_max_deg', tolerance: 0.01 }),
  ];

  // ── the figures, each defined once, in the dashboard that owns it; other dashboards reuse them with `use:` ──────
  const everyJoint = {
    type: 'occupancy',
    occupancy: {
      of: 'trajectory',
      columns: 3,
      // WHY the bars under each map: which of the joint's position bands the rows reach (its "span"), re-aggregated
      panels: joints.map((joint) => ({ ...jointGrid(coverage, joint, 'q_qd'), title: short(joint.name), marginals: { x: 'position' } })),
    },
  };
  const toolThreeSides = {
    type: 'occupancy',
    occupancy: { of: 'trajectory', columns: 2, layout: 'hero', equal: true, frame: coverage.tool.frame,
      panels: SIDES.map(([key, title, u, v]) => toolGrid(coverage, key, title, u, v)) },
  };
  const pointing = {
    type: 'occupancy',
    occupancy: { of: 'trajectory', columns: 1, panels: [directionGrid(coverage, membership)] },
  };
  const key = (extra) => ({ type: 'coverage-key', ...extra });

  // ── the dashboards: each a `type: panels` preset, so each is one of data-ui's view tabs ──────────────────────────
  const overview = {
    type: 'panels',
    name: 'Overview',
    panels: [
        { key: 'numbers', title: 'Headline numbers', w: 12, view: { type: 'numbers', numbers: headline,
          whole: ['q_span_median_pct', 'qd_peak_max_pct', 'qdd_peak_max_pct', 'tool_speed_p99_m_s'] } },
        { key: 'joints', title: 'Every joint · positions × speeds', open: 'One joint', w: 4, view: { ...everyJoint, compact: true } },
        { key: 'tool', title: 'The tool from three sides', open: 'Tool position', w: 5, use: 'Tool position/tool', compact: true },
        { key: 'pointing', title: 'Pointing', open: 'Tool orientation', w: 3, use: 'Tool orientation/pointing', compact: true },
        { key: 'key', w: 12, view: key({ items: ['ramp', 'empty', 'outside', 'frame'] }) },
    ],
  };

  const oneJoint = {
    type: 'panels',
    name: 'One joint',
    // the dashboard's own control: only this tab draws it; ${joint} in its panels reads it (Grafana's variables)
    vars: [{ key: 'joint', label: 'Joint', values: jointNames, value: jointNames[0] }],
    panels: [
        { key: 'planes', title: '${joint}: positions, speeds, accelerations', w: 8,
          view: { type: 'occupancy', height: 640, occupancy: { of: 'trajectory', group: '${joint}', columns: 2,
            panels: joints.flatMap((joint) => planes.map((plane) => jointGrid(coverage, joint, plane))) } } },
        { key: 'numbers', title: '${joint} in numbers', w: 4, view: { type: 'numbers', columns: 1, numbers: [
          number('Trajectories', 'count', {}),
          number('Positions × speeds visited', 'distinct', { property: 'cells_${joint}_q_qd', total: qqdCells, unit: '%', note: 'of the limit box' }),
          number('Speeds × accelerations visited', 'distinct', { property: 'cells_${joint}_qd_qdd', total: qdqddCells, unit: '%', note: 'of the limit box' }),
          number('Positions × accelerations visited', 'distinct', { property: 'cells_${joint}_q_qdd', total: qqddCells, unit: '%', note: 'of the limit box' }),
        ] } },
    ],
  };

  const toolPosition = {
    type: 'panels',
    name: 'Tool position',
    panels: [
        { key: 'tool', title: 'The tool from three sides', w: 9, view: { ...toolThreeSides, height: 600 } },
        { key: 'numbers', title: 'The tool in numbers', w: 3, view: { type: 'numbers', columns: 1, numbers: [
          number('Tool pixels, from above', 'distinct', { property: cellsKey('xy'), note: '2 cm' }),
          number('Tool pixels, from the front', 'distinct', { property: cellsKey('xz'), note: '2 cm' }),
          number('Tool voxels', 'distinct', { property: cellsKey('voxels'), note: '5 cm' }),
          number('Reachable voxels reached', 'distinct', { property: cellsKey('voxels'), total: reachableVoxels, unit: '%', decimals: 1 }),
          number('Tool path, all trajectories', 'sum', { property: 'tool_path_m', unit: 'm', decimals: 0 }),
          number('Highest tool point', 'max', { property: 'tool_z_max_mm', unit: 'mm', decimals: 0 }),
        ], caveat: "Each deployment's tool is in its own cell frame: the alone UR5e and the cell UR5e overlay as numbers, not as one room." } },
    ],
  };

  const toolOrientation = {
    type: 'panels',
    name: 'Tool orientation',
    panels: [
        { key: 'pointing', title: 'Every direction the tool points, equal-area', w: 8, view: { ...pointing, height: 460 } },
        { key: 'numbers', title: 'Pointing in numbers', w: 4, view: { type: 'numbers', columns: 1, numbers: [
          number('Tool directions', 'distinct', { property: cellsKey('directions'), total: rings * sectors, unit: '%', note: 'equal-area cells' }),
          number('Directions visited', 'distinct', { property: cellsKey('directions'), note: `of ${rings * sectors} cells` }),
          number('Largest tilt', 'max', { property: 'tool_tilt_max_deg', unit: '°', decimals: 0 }),
          number('Median trajectory’s largest tilt', 'median', { property: 'tool_tilt_max_deg', unit: '°', decimals: 0 }),
        ] } },
    ],
  };

  const trajectories = {
    type: 'table',
    name: 'Trajectories',
    order: TABLE_ORDER,
    display: { dataset: 'badge', split: 'badge', new_cells: 'bar', only_it_cells: 'bar' },
    columnSize: { task: 170, dataset: 178 },
    // the record peek (the drill): the few fields that say what it is and what it adds; the rest fold under "more"
    record: { sections: [{ name: 'Trajectory', properties: ['dataset', 'split', 'kind', 'duration_s', 'new_cells', 'only_it_cells'] }] },
  };

  // Datasets side by side: ONE panel, repeated per dataset value of the rows (Grafana's repeat-by-variable); the panel
  // is itself a small dashboard, so each dataset gets the same row of figures, its colour on the stripe
  const byDataset = {
    type: 'panels',
    name: 'By dataset',
    panels: [
        { key: 'each', repeat: 'dataset', w: 12, view: { type: 'panels', panels: [
          { key: 'numbers', w: 3, view: { type: 'numbers', columns: 1, compact: true, numbers: [
            number('Trajectories', 'count', {}),
            number('Position × speed cells', 'distinct-mean', { properties: joints.map((j) => cellsKey('q_qd', j.name)), total: qqdCells, unit: '%', note: 'mean over joints' }),
            number('Tool directions', 'distinct', { property: cellsKey('directions'), total: rings * sectors, unit: '%' }),
          ] } },
          { key: 'joints', title: 'Every joint · positions × speeds', w: 5, use: 'Overview/joints', compact: true },
          { key: 'tool', title: 'From above', w: 2, view: { type: 'occupancy', compact: true, occupancy: { of: 'trajectory', columns: 1, equal: true, frame: coverage.tool.frame, panels: [toolThreeSides.occupancy.panels[0]] } } },
          { key: 'pointing', title: 'Pointing', w: 2, use: 'Tool orientation/pointing', compact: true },
        ] } },
        { key: 'key', w: 12, view: key({ items: ['ramp', 'empty', 'outside', 'frame'], note: 'One colour scale per figure. Comparing datasets of different sizes? The gear’s “visited / not” scale shows who reaches where.' }) },
    ],
  };

  return {
    // PROPOSED (P3): what every dashboard's strip counts the rows as and by (a reader's own dashboard included)
    subset: SUBSET,
    // which layouts + offers (CONTRACT §47): a dashboard, the table, a chart
    viewTypes: ['panels', 'table', 'chart'],
    // PROPOSED (P3): set once behind the gear in the bar; every view gets input.settings (Obsidian's option types)
    settings: {
      cmap: { type: 'dropdown', displayName: 'Colour map', options: { viridis: 'viridis', magma: 'magma', plasma: 'plasma', inferno: 'inferno', cividis: 'cividis' }, default: 'viridis' },
      reverse: { type: 'toggle', displayName: 'Reverse (high = dark)', default: false },
      scale: { type: 'dropdown', displayName: 'Scale', options: { linear: 'linear (clipped at p98)', log: 'log', equalized: 'histogram-equalized', visited: 'visited / not', enough: '≥ enough / not' }, default: 'linear' },
    },
    facets: [
      // WHY dataset first (Zach, Nov 24): "a thing here for like dataset, above split, it can be the first one"; split
      // below it applies to every dataset ticked (a values facet ANDs across properties, ORs within one)
      { property: 'dataset', label: 'Dataset', order: Object.keys(DATASET_SLOTS) },
      { property: 'split', label: 'Split', order: ['dev', 'holdout'] },
      { property: 'kind', label: 'Kind' },
      { as: 'search', properties: ['task', 'kind', 'tags'], label: 'Find', placeholder: 'Trajectory name (try holdout-00)' },
      { property: 'tags', label: 'Tags', collapsed: true },
      { property: 'duration_s', as: 'slider-histogram', label: 'Duration', unit: 's', collapsed: true },
      { property: 'new_cells', as: 'slider-histogram', label: 'New cells', collapsed: true },
      { property: 'tool_tilt_max_deg', as: 'slider-histogram', label: 'Tilt max', unit: '°', collapsed: true },
    ],
    properties,
    views: [overview, oneJoint, toolPosition, toolOrientation, trajectories, byDataset],
  };
}

/** Every occupancy entry in the document (walking dashboards and their nested panels): what the oracle rebuilds. */
export function occupancyEntries(base) {
  const out = [];
  const walk = (view) => {
    if (!view || typeof view !== 'object') return;
    if (view.occupancy) out.push(view);
    for (const panel of Array.isArray(view.panels) ? view.panels : []) walk(panel.view);
  };
  for (const view of base.views) walk(view);
  return out;
}
