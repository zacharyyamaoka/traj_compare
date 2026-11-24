/* rows.js — the one dataset P3 hands data-ui: one row per trajectory (data/trajectories.json), all four datasets, plus
 * the cells each trajectory visits (data/membership.json) as list properties, so every dashboard can re-aggregate
 * whatever rows the rail leaves. Copied from round 2's V2 (v2/js/rows.js) and widened by the dataset columns.
 *
 * Pure (no DOM): the page imports it, and tools/emit.mjs imports it in Node to write coverage.base and check it with
 * `data-ui check`. Nothing here computes a number: it reshapes the producer's (analyze's / extract.py's) values.
 */

export const DATASET_ID = 'ur5e-coverage-p3';

/** "shoulder_pan_joint" -> "shoulder_pan" (the samples' and the labels' short form). */
export function short(joint) { return String(joint).replace(/_joint$/, ''); }

/** The cell-list property for a joint plane, a tool projection, the voxels or the sphere. */
export function cellsKey(kind, joint) {
  return joint ? `cells_${short(joint)}_${kind}` : `cells_${kind}`;
}

const round = (value, digits) => (value === null || value === undefined || !Number.isFinite(value) ? null
  : Math.round(value * 10 ** digits) / 10 ** digits);

/** data-ui's runtime dataset {id, title, titleProperty, properties, rows} from the round's shared data. */
export function trajectoryDataset(coverage, trajectories, membership) {
  const joints = coverage.joints.map((joint) => joint.name);
  const planes = Object.keys(coverage.planes[joints[0]]);
  const rows = trajectories.map((t, index) => {
    const m = membership.trajectories[t.name];
    if (!m) throw new Error(`membership.json has no ${t.name}`);
    const row = {
      id: t.name,
      name: t.name,
      task: t.task,
      order: index + 1,
      dataset: t.tags.dataset,
      split: t.tags.split,
      kind: t.tags.kind,
      tags: t.tags.tags,
      belt_speed: t.tags.belt_speed || null,
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
    name: { type: 'text', label: 'Dataset / task' },
    order: { type: 'number', label: '#', decimals: 0 },
    dataset: { type: 'text', label: 'Dataset' },
    split: { type: 'text', label: 'Split' },
    kind: { type: 'text', label: 'Kind' },
    tags: { type: 'text', label: 'Tags' },
    belt_speed: { type: 'text', label: 'Belt speed' },
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
  return { id: DATASET_ID, title: 'Trajectories', titleProperty: 'task', properties, rows };
}
