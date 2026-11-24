/* aggregate.js — copied from round 2's V2 (v2/js/aggregate.js), unchanged but for where the numbers live. V2's one licensed exception to "never recompute in the page": re-aggregating a FILTERED set of rows.
 *
 * Every count here is trajectories per cell (how many of the given rows list the cell), the same measure as the
 * payload's `paths`; with every row given it must equal the payload exactly, and `oracle()` checks that (the page runs
 * it at start and says so on screen; tools/emit.mjs runs it in Node). Pure (no DOM).
 */

/** Trajectories per cell: how many rows list each cell of a grid of `size` cells. */
export function countCells(rows, key, size) {
  const counts = new Int32Array(size);
  for (const row of rows) {
    const cells = row[key];
    if (!Array.isArray(cells)) continue;
    for (const cell of cells) if (cell >= 0 && cell < size) counts[cell] += 1;
  }
  return counts;
}

/** How many distinct cells the rows list together (a union). */
export function distinct(rows, key) {
  const seen = new Set();
  for (const row of rows) for (const cell of row[key] || []) seen.add(cell);
  return seen.size;
}

/** The (x, y) of a flat cell index under the panel's order. */
export function cellXY(cell, shape, order) {
  const [nx, ny] = shape;
  return order === 'y-major' ? [cell % nx, Math.floor(cell / nx)] : [Math.floor(cell / ny), cell % ny];
}
export function cellIndex(x, y, shape, order) {
  const [nx, ny] = shape;
  return order === 'y-major' ? y * nx + x : x * ny + y;
}

/** Trajectories per column (axis 0) or row (axis 1) band: rows with ANY cell in that band, each counted once. */
export function marginal(rows, panel, axis) {
  const n = panel.shape[axis];
  const out = new Int32Array(n);
  for (const row of rows) {
    const seen = new Uint8Array(n);
    for (const cell of row[panel.cells] || []) seen[cellXY(cell, panel.shape, panel.order)[axis]] = 1;
    for (let i = 0; i < n; i += 1) out[i] += seen[i];
  }
  return out;
}

/** One overview number over the rows: {value, n}. Summaries: count, sum, max, distinct (a union's size, or its share
 *  of `total` in %), distinct-mean (the mean over `properties` of each union's share of `total`, in %). */
export function summarize(spec, rows) {
  if (spec.summary === 'count') return rows.length;
  if (spec.summary === 'sum') return rows.reduce((total, row) => total + (Number(row[spec.property]) || 0), 0);
  if (spec.summary === 'max') return rows.length ? Math.max(...rows.map((row) => Number(row[spec.property]) || 0)) : null;
  if (spec.summary === 'distinct') {
    const size = distinct(rows, spec.property);
    return spec.total ? (100 * size) / spec.total : size;
  }
  if (spec.summary === 'distinct-mean') {
    const shares = spec.properties.map((key) => (100 * distinct(rows, key)) / spec.total);
    return shares.reduce((a, b) => a + b, 0) / shares.length;
  }
  throw new Error(`unknown summary: ${spec.summary}`);
}

function at(payload, dotted) {
  // "planes.shoulder_pan_joint.q_qd": the joint names hold underscores, never dots
  return dotted.split('.').reduce((node, key) => (node ? node[key] : undefined), payload);
}

/** With every row, every grid and number V2 draws must equal the payload. Returns {checked, lines, failures}. */
export function oracle(coverage, dataset, base, voxelShape) {
  const rows = dataset.rows;
  const failures = [];
  const lines = [];
  let checked = 0;
  const panels = [];
  for (const view of base.views) if (view.occupancy) for (const panel of view.occupancy.panels) panels.push(panel);
  const seen = new Set();
  for (const panel of panels) {
    if (seen.has(panel.cells)) continue;
    seen.add(panel.cells);
    const block = at(coverage, panel.payload);
    const size = panel.shape[0] * panel.shape[1];
    const counts = countCells(rows, panel.cells, size);
    if (block.paths) {
      const bad = block.paths.findIndex((value, i) => value !== counts[i]);
      if (block.paths.length !== size || bad >= 0) failures.push(`${panel.cells}: cell ${bad} payload ${block.paths[bad]} rebuilt ${counts[bad]}`);
    } else if (block.counts) {
      // the sphere holds samples, not trajectories: its VISITED set must match
      const bad = block.counts.findIndex((value, i) => (value > 0) !== (counts[i] > 0));
      if (bad >= 0) failures.push(`${panel.cells}: cell ${bad} visited in one and not the other`);
    }
    checked += 1;
  }
  lines.push(`grids: ${checked} rebuilt from the rows' cell lists`);
  if (voxelShape) {
    const [, ny, nz] = voxelShape;
    const want = new Map(coverage.tool.voxels.cells.map((c) => [(c[0] * ny + c[1]) * nz + c[2], c[4]]));
    const got = new Map();
    for (const row of rows) for (const cell of row.cells_voxels || []) got.set(cell, (got.get(cell) || 0) + 1);
    const same = want.size === got.size && [...want].every(([cell, paths]) => got.get(cell) === paths);
    if (!same) failures.push(`voxels: ${got.size} rebuilt vs ${want.size} in the payload`);
    checked += 1;
    lines.push(`voxels: ${got.size} rebuilt, ${want.size} in the payload`);
  }
  const overview = base.views.find((view) => view.type === 'coverage-numbers');
  for (const spec of overview.numbers) {
    const payload = coverage.numbers.find((row) => row.key === spec.payload);
    const value = summarize(spec, rows);
    const tolerance = spec.tolerance ?? 1e-6 * Math.max(1, Math.abs(payload.value));
    if (!payload || Math.abs(value - payload.value) > tolerance) failures.push(`${spec.label}: rebuilt ${value} vs analyze ${payload && payload.value}`);
    lines.push(`${spec.payload}: ${value} (analyze ${payload && payload.value})`);
    checked += 1;
  }
  return { checked, lines, failures };
}
