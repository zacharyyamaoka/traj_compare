/* grids.js — the geometry of every coverage figure (a grid's shape, its axes in display units, the cells the robot
 * cannot reach), read from the payload so the registered `occupancy` view knows nothing about robots: it counts, over
 * the rows it is handed, how many rows list each cell. Copied from round 2's V2 js/base.js (its panel builders).
 *
 * Pure (no DOM): tools/build.mjs writes these into ../coverage.base's views.
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

export function jointPanel(coverage, joint, plane) {
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

export const TOOL_VIEWS = [['xy', 'From above', 'x', 'y'], ['xz', 'From the front', 'x', 'z'], ['yz', 'From the side', 'y', 'z']];

export function toolPanel(coverage, key, title, u, v) {
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

export function directionPanel(coverage, membership) {
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
    payload: 'tool.orientation.sphere',
  };
}
