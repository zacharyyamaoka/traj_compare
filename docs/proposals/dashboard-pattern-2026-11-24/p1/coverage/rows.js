/* rows.js — the rows P1's coverage.base names (`data: rows.json`): one row per trajectory over all four UR5e datasets,
 * flattened for a table, plus the cells each trajectory visits on the payload's shared grids (membership.json) as list
 * properties, so a coverage view re-aggregates whatever rows the workbench's rail leaves.
 *
 * Pure (no DOM): tools/build.mjs imports it in Node and writes ../rows.json. Nothing here computes a number: it
 * reshapes the producer's (analyze's / extract.py's) values. Adapted from round 2's V2 js/rows.js (+ dataset).
 */

export const DATASET_ID = 'ur5e-coverage-all';

/** "shoulder_pan_joint" -> "shoulder_pan" (the labels' short form). */
export function short(joint) { return String(joint).replace(/_joint$/, ''); }

/** The cell-list property for a joint plane, a tool projection, the voxels or the sphere. */
export function cellsKey(kind, joint) {
  return joint ? `cells_${short(joint)}_${kind}` : `cells_${kind}`;
}

const round = (value, digits) => (value === null || value === undefined || !Number.isFinite(value) ? null
  : Math.round(value * 10 ** digits) / 10 ** digits);

/** data-ui's runtime dataset {id, title, titleProperty, properties, rows} from the round's shared data. */
export function trajectoryDataset(coverage, trajectories, membership, datasets) {
  const joints = coverage.joints.map((joint) => joint.name);
  const planes = Object.keys(coverage.planes[joints[0]]);
  const deployment = Object.fromEntries(datasets.map((d) => [d.dataset, d.deployment]));
  const rows = trajectories.map((t, index) => {
    const m = membership.trajectories[t.name];
    if (!m) throw new Error(`membership.json has no ${t.name}`);
    const row = {
      id: t.name,
      task: t.task,
      dataset: t.tags.dataset,
      station: deployment[t.tags.dataset] === 'ur5e_alone' ? 'UR5e alone' : 'Conveyor PnP cell',
      split: t.tags.split,
      kind: t.tags.kind,
      tags: t.tags.tags,
      order: index + 1,
      duration_s: t.duration_s,
      samples: t.samples,
      new_cells: t.new_cells,
      only_it_cells: t.only_it_q_qd_cells,
      tool_path_m: t.tool_path_m,
      tool_speed_max_m_s: t.tool_speed_max_m_s,
      tool_z_min_mm: round(t.tool_z_min_m * 1000, 1),
      tool_z_max_mm: round(t.tool_z_max_m * 1000, 1),
      tool_tilt_max_deg: t.tool_tilt_max_deg,
      rrd: t.rrd,
    };
    for (const joint of joints) {
      for (const plane of planes) row[cellsKey(plane, joint)] = m.planes[joint][plane];
    }
    for (const view of ['xy', 'xz', 'yz', 'voxels', 'directions']) row[cellsKey(view)] = m[view];
    return row;
  });
  const properties = {
    task: { type: 'text', label: 'Trajectory' },
    dataset: { type: 'text', label: 'Dataset' },
    station: { type: 'text', label: 'Station' },
    split: { type: 'text', label: 'Split' },
    kind: { type: 'text', label: 'Kind' },
    tags: { type: 'text', label: 'Tags' },
    order: { type: 'number', label: '#', decimals: 0 },
    duration_s: { type: 'number', label: 'Duration', unitText: 's', decimals: 2 },
    samples: { type: 'number', label: 'Samples', decimals: 0 },
    new_cells: { type: 'number', label: 'New cells', decimals: 0 },
    only_it_cells: { type: 'number', label: 'Only it', decimals: 0 },
    tool_path_m: { type: 'number', label: 'Tool path', unitText: 'm', decimals: 2 },
    tool_speed_max_m_s: { type: 'number', label: 'Tool speed max', unitText: 'm/s', decimals: 2 },
    tool_z_min_mm: { type: 'number', label: 'Tool z low', unitText: 'mm', decimals: 0 },
    tool_z_max_mm: { type: 'number', label: 'Tool z high', unitText: 'mm', decimals: 0 },
    tool_tilt_max_deg: { type: 'number', label: 'Tilt max', unitText: '°', decimals: 0 },
    rrd: { type: 'text', label: 'Rerun file' },
  };
  for (const key of Object.keys(rows[0])) if (key.startsWith('cells_')) properties[key] = { type: 'list', label: key };
  return { id: DATASET_ID, title: 'UR5e trajectories', titleProperty: 'task', properties, rows };
}
