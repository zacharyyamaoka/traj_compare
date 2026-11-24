/* drill.js — one trajectory, opened in data-ui's own record peek (a table row's click, CONTRACT §13 `open: side`).
 *
 * data-ui draws the record's fields; `el.peekExtra(row)` (§37) adds, at their foot, Open in Rerun and "what it adds":
 * its tool path from above and its position × speed cells per joint, against every other trajectory's, with the
 * cells no other trajectory visits picked out. Those are from membership.json (the cells it visits on the payload's
 * own grids), compared across all 54 trajectories: what this one adds to the whole dataset, whatever is filtered.
 */

import { cellXY } from './aggregate.js';

const ROUND_ROOT = '/home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/';
const RERUN = ['uvx', '--from', 'rerun-sdk==0.40.0', 'rerun'];
const OTHER = [196, 198, 206];
const MINE = [42, 120, 214];
const ONLY = [24, 24, 27];
const EMPTY = [255, 255, 255];
const OUTSIDE = [241, 240, 236];

const esc = (text) => String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** The HTML data-ui puts at the foot of the record's fields. */
export function drillHtml(row) {
  return `<div class="v2-drill" data-v2-drill="${esc(row.name)}">
    <div class="v2-drill-actions">
      <button type="button" class="v2-rerun" data-v2-rerun="${esc(row.rrd)}" title="Opens ${esc(row.rrd)} in the native Rerun viewer (Rerun 0.40): q, qd, qdd per joint in degrees and the tool path">
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3l9 5-9 5z"/></svg>Open in Rerun</button>
      <span class="v2-rerun-status" role="status"></span>
    </div>
    <div class="v2-rerun-fallback" hidden><code></code><button type="button" class="v2-copy">Copy</button></div>
    <h3 class="v2-drill-h">What it adds to the dataset</h3>
    <p class="v2-drill-sub">Its cells against the other trajectories' (all ${'{N}'}), from membership.json on the payload's own grids.</p>
    <div class="v2-drill-figs" data-v2-drill-figs></div>
  </div>`;
}

function canvasOf(width, height) {
  const ratio = globalThis.devicePixelRatio || 1;
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const g = canvas.getContext('2d');
  g.scale(ratio, ratio);
  return { canvas, g };
}

/** One grid: other trajectories grey, this one blue, cells only it visits near-black. */
function mineVsRest(panel, rows, name, size, blocked, crop) {
  const [nx, ny] = panel.shape;
  const win = crop || { x0: 0, x1: nx, y0: 0, y1: ny };
  const total = nx * ny;
  const counts = new Int32Array(total);
  for (const row of rows) for (const cell of row[panel.cells] || []) counts[cell] += 1;
  const mine = new Uint8Array(total);
  const me = rows.find((row) => row.name === name);
  for (const cell of me[panel.cells] || []) mine[cell] = 1;
  const off = document.createElement('canvas');
  const wx = win.x1 - win.x0;
  const wy = win.y1 - win.y0;
  off.width = wx; off.height = wy;
  const g = off.getContext('2d');
  const image = g.createImageData(wx, wy);
  let only = 0; let own = 0;
  for (let cell = 0; cell < total; cell += 1) {
    const [x, y] = cellXY(cell, panel.shape, panel.order);
    if (mine[cell]) { own += 1; if (counts[cell] === 1) only += 1; }
    if (x < win.x0 || x >= win.x1 || y < win.y0 || y >= win.y1) continue;
    const k = ((win.y1 - 1 - y) * wx + (x - win.x0)) * 4;
    let rgb = EMPTY;
    if (mine[cell]) rgb = counts[cell] === 1 ? ONLY : MINE; else if (counts[cell] > 0) rgb = OTHER; else if (blocked && blocked[cell]) rgb = OUTSIDE;
    image.data[k] = rgb[0]; image.data[k + 1] = rgb[1]; image.data[k + 2] = rgb[2]; image.data[k + 3] = 255;
  }
  g.putImageData(image, 0, 0);
  const { canvas, g: out } = canvasOf(size.w + 2, size.h + 2);
  out.imageSmoothingEnabled = false;
  out.drawImage(off, 1, 1, size.w, size.h);
  out.strokeStyle = panel.frame === 'limit' ? '#b4442f' : '#c4c4cc';
  out.lineWidth = 1;
  out.strokeRect(0.5, 0.5, size.w + 1, size.h + 1);
  return { canvas, own, only };
}

/** The window (in cells) around every cell any row visits, padded and made square: the dataset's own extent. */
function extent(panel, rows, pad) {
  let x0 = Infinity; let x1 = -Infinity; let y0 = Infinity; let y1 = -Infinity;
  for (const row of rows) {
    for (const cell of row[panel.cells] || []) {
      const [x, y] = cellXY(cell, panel.shape, panel.order);
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
  }
  const side = Math.max(x1 - x0, y1 - y0) + 1 + 2 * pad;
  const cx = (x0 + x1 + 1) / 2;
  const cy = (y0 + y1 + 1) / 2;
  const [nx, ny] = panel.shape;
  const lo = (c, n) => Math.max(0, Math.min(n - side, Math.round(c - side / 2)));
  return { x0: lo(cx, nx), x1: lo(cx, nx) + side, y0: lo(cy, ny), y1: lo(cy, ny) + side };
}

function blockedOf(panel) {
  if (!panel.unreachable || !panel.unreachable.length) return null;
  const flags = new Uint8Array(panel.shape[0] * panel.shape[1]);
  for (const [start, length] of panel.unreachable) flags.fill(1, start, start + length);
  return flags;
}

/** Draw the figures into the peek, once data-ui has put the HTML there. */
export function mountDrill(peek, row, rows, base) {
  const host = peek && peek.querySelector(`[data-v2-drill="${CSS.escape(row.name)}"] [data-v2-drill-figs]`);
  if (!host || host.dataset.drawn === row.name) return;
  host.dataset.drawn = row.name;
  const sub = peek.querySelector('.v2-drill-sub');
  if (sub) sub.textContent = sub.textContent.replace('{N}', String(rows.length));
  const width = Math.max(300, Math.min(560, host.clientWidth || 480));
  const views = base.views;
  const top = views.find((view) => view.name === 'Tool position').occupancy.panels[0];
  const joints = views.find((view) => view.name === 'All joints').occupancy.panels;
  const parts = [];
  // WHY cropped to the dataset's extent: the whole reachable disk would leave one trajectory's path a few pixels wide
  const crop = extent(top, rows, 3);
  const toolSize = Math.min(230, Math.floor(width * 0.44));
  const drawn = mineVsRest(top, rows, row.name, { w: toolSize, h: toolSize }, blockedOf(top), crop);
  const mm = (cells, axis) => Math.round((axis.lo + ((axis.hi - axis.lo) * cells) / top.shape[0]));
  const tool = document.createElement('figure');
  tool.className = 'v2-drill-fig v2-drill-tool';
  tool.style.width = `${toolSize + 2}px`;
  tool.innerHTML = `<figcaption><b>Tool path, from above</b><br>${drawn.own} pixels of 2 cm, <b>${drawn.only}</b> no other trajectory visits</figcaption>`;
  tool.append(drawn.canvas);
  const span = document.createElement('div');
  span.className = 'v2-drill-span';
  span.textContent = `x ${mm(crop.x0, top.xAxis)} … ${mm(crop.x1, top.xAxis)} mm, y ${mm(crop.y0, top.yAxis)} … ${mm(crop.y1, top.yAxis)} mm (the dataset's extent)`;
  tool.append(span);
  const grid = document.createElement('div');
  grid.className = 'v2-drill-joints';
  const w = Math.floor((width - toolSize - 2 - 14 - 6) / 2) - 2;
  let ownTotal = 0; let onlyTotal = 0;
  for (const panel of joints) {
    const result = mineVsRest(panel, rows, row.name, { w, h: Math.round(w * 0.5) }, null);
    ownTotal += result.own; onlyTotal += result.only;
    const fig = document.createElement('figure');
    fig.className = 'v2-drill-mini';
    fig.innerHTML = `<figcaption>${esc(panel.title)} <span title="cells it visits · cells only it visits">${result.own} · <b>${result.only}</b></span></figcaption>`;
    fig.append(result.canvas);
    grid.append(fig);
  }
  const jointsFig = document.createElement('figure');
  jointsFig.className = 'v2-drill-fig';
  jointsFig.innerHTML = `<figcaption><b>Position × speed, each joint</b><br>${ownTotal} cells, <b>${onlyTotal}</b> only it visits (= the table's Only it, ${row.only_it_cells})</figcaption>`;
  jointsFig.append(grid);
  const row2 = document.createElement('div');
  row2.className = 'v2-drill-row';
  row2.append(tool, jointsFig);
  parts.push(row2);
  const key = document.createElement('div');
  key.className = 'v2-legend v2-drill-key';
  key.innerHTML = `<span class="v2-key"><span class="v2-key-box" style="background:rgb(${MINE})"></span>this trajectory</span>
    <span class="v2-key"><span class="v2-key-box" style="background:rgb(${ONLY})"></span>only this trajectory</span>
    <span class="v2-key"><span class="v2-key-box" style="background:rgb(${OTHER})"></span>the other trajectories</span>
    <span class="v2-key"><span class="v2-key-box v2-key-empty"></span>no trajectory</span>
    <span class="v2-key"><span class="v2-key-box" style="background:rgb(${OUTSIDE})"></span>cannot reach</span>
    <span class="v2-key"><span class="v2-key-box v2-key-frame"></span>joint limit box</span>`;
  parts.push(key);
  host.replaceChildren(...parts);
}

/** Open in Rerun: POST the round server's /__rerun/open; on failure show the command with Copy. */
export async function openInRerun(button) {
  const rrd = button.dataset.v2Rerun;
  const drill = button.closest('.v2-drill');
  const status = drill.querySelector('.v2-rerun-status');
  const fallback = drill.querySelector('.v2-rerun-fallback');
  const command = [...RERUN, ROUND_ROOT + rrd].join(' ');
  status.textContent = 'Starting Rerun…';
  fallback.hidden = true;
  try {
    const response = await fetch(`/__rerun/open?rrd=${encodeURIComponent(rrd)}`, { method: 'POST' });
    const answer = await response.json().catch(() => ({}));
    if (!response.ok || !answer.ok) throw Object.assign(new Error(answer.error || `HTTP ${response.status}`), { command: answer.command });
    status.textContent = 'Opened in Rerun ✓';
  } catch (error) {
    status.textContent = `Could not start Rerun here (${error.message}); run this yourself:`;
    fallback.querySelector('code').textContent = error.command || command;
    fallback.hidden = false;
  }
}

export function copyCommand(button) {
  const code = button.parentElement.querySelector('code');
  try { navigator.clipboard.writeText(code.textContent); button.textContent = 'Copied'; } catch (error) { button.textContent = 'Select it'; }
}
