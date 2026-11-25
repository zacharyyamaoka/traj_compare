/* T2 "Where in the workspace is it worst?" on V2 "Two viewers, the filter carried".

   V2's link is unchanged (Open target view: common/target.html with keep= the rail's runs of that target and back= this
   URL). This file adds ONE page to the same <data-workbench>: a host element with `tab` (data-ui's scope treats it as a
   page, CONTRACT §53; V3 of the tensorboard round did the same). On it:

   - every joint's position × speed plane, on the bench's OWN coverage cells (coverage.json q_qd, 36 × 24: the cells the
     Coverage page draws), coloured by the tracking error made IN each cell: the median over the targets through the
     cell of (the median over its kept runs of the run's RMS joint error within that cell). Drawn by data-ui's stock
     coverage-plane (§52) inside its own <data-scope>, fed grid rows by this file;
   - one answer line: the worst cell (>= 3 targets through it), where it is, and which dataset its targets come from;
   - a click on a cell lists the targets through it, worst first (a stock table in its own <data-scope>); a row's
     Open target view is V2's drill (host-common.js), keep= the rail's runs of that target.

   WHY the host and not a .base page (named in NOTES.md): data-ui's `coverage.sum` adds part rows and takes the MOST of
   `max_other`; a median over the runs the rail keeps needs this aggregation, and 67k part rows (one per run and joint)
   would be ~50 MB. WHY per-sample error, not each run's RMS spread over its path: a run's error is not uniform along
   its motion; the cell it was made in is the question. Data: ../data/t2-cells.json (build_tabs.py --cells). */
import { host } from './host-common.js';
import { makeResizable } from '../vendor/data-ui/resize.js';

const api = host({ variant: 't2' });
// V2's link, unchanged (../../tensorboard-2026-11-24/v2/host.js): Open target view (a Targets or Runs row, or a row of
// this tab's list) opens the target view in this tab, the rail's runs of that target checked, back= this URL
api.onDrill('Open target view', (row) => {
  if (!row) return;
  const keep = api.keptLines(row.target_key);
  location.href = api.targetUrl(row, { keep: keep.join(','), back: location.href });
});
const TAB = 'Where in the workspace is it worst?';
const MIN_TARGETS = 3; // a cell is a candidate for "worst" only with this many targets through it (one target is noise)
const DEG = 180 / Math.PI;
const ORDER = ['UR5e + Conveyor PnP cell', 'UR5e', 'BAM FB', '1-DOF pendulum'];

const style = document.createElement('style');
style.textContent = `
  #tc .t2 { display: flex; flex-direction: column; height: 100%; min-height: 0; box-sizing: border-box; padding: 10px 12px 0; gap: 8px; }
  #tc .t2[hidden] { display: none; }
  #tc .t2-answer { border: 1px solid var(--data-border, #d0d7de); border-radius: 10px; padding: 10px 14px; background: var(--data-bg, #fff); }
  #tc .t2-answer b { font-size: 15px; display: block; }
  #tc .t2-sub { font-size: 12.5px; color: var(--data-muted, #57606a); margin-top: 4px; }
  #tc .t2-split { flex: 1; min-height: 0; display: flex; }
  #tc .t2-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
  #tc .t2-side { position: relative; flex: 0 0 var(--data-panel-width, 440px); width: var(--data-panel-width, 440px); min-width: 0;
    display: flex; flex-direction: column; border-left: 1px solid var(--data-border, #d0d7de); padding-left: 10px; }
  #tc .t2-side.folded { flex-basis: 34px; width: 34px; }
  #tc .t2-side.folded > :not(.t2-side-head) { display: none; }
  #tc .t2-side.folded .t2-side-head > :not(.t2-fold) { display: none; }
  #tc .t2-title { font-size: 12.5px; font-weight: 600; margin: 2px 0 6px; }
  #tc .t2-side-head { display: flex; gap: 6px; align-items: flex-start; }
  #tc .t2-side-head .t2-title { flex: 1; }
  #tc .t2-fold { border: 0; background: none; cursor: pointer; font-size: 14px; color: var(--data-muted, #57606a); padding: 0 4px; }
  #tc .t2-scope { display: block; flex: 1; min-height: 0; }
  #tc .t2-scope > data-views { display: block; height: 100%; --data-height: 100%; }
  #tc .t2-mark { position: absolute; pointer-events: none; box-sizing: border-box; border: 2px solid var(--data-accent, #1f6feb);
    box-shadow: 0 0 0 1px #fff; z-index: 3; }
`;
document.head.appendChild(style);

let page = null, planes = null, list = null, side = null, cells = null, loading = null, dirty = true, state = null, pick = null;

function median(values) {
  const v = values.slice().sort((a, b) => a - b);
  const n = v.length;
  if (!n) return null;
  return n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2;
}
const fmt = (x, d = 3) => (x == null || !isFinite(x) ? '—' : Math.abs(x) >= 100 ? x.toFixed(0) : Number(x.toPrecision(d)).toString());
const range = (lo, step, i, scale) => `${fmt((lo + i * step) * scale, 3)} … ${fmt((lo + (i + 1) * step) * scale, 3)}`;

function makePage() {
  if (page) return;
  page = document.createElement('section');
  page.className = 't2';
  page.setAttribute('tab', TAB);
  page.innerHTML = `
    <div class="t2-answer" role="status"><b id="t2-head">Reading the error at every position × speed cell…</b><div class="t2-sub" id="t2-sub"></div></div>
    <div class="t2-split">
      <div class="t2-main">
        <div class="t2-title">Each joint · position × speed on the bench's coverage cells · colour = tracking error made in the cell (median over the targets through it of the median over its runs, RMS within the cell) · one colour scale · click a cell</div>
        <data-scope no-url class="t2-scope" id="t2-planes"><data-views view="Error" toolbar="none"></data-views></data-scope>
      </div>
      <aside class="t2-side" id="t2-side" aria-label="Targets through the cell">
        <div class="t2-side-head"><div class="t2-title" id="t2-side-title">Targets through the cell</div>
          <button type="button" class="t2-fold" id="t2-fold" title="Fold the targets list">»</button></div>
        <data-scope no-url class="t2-scope" id="t2-list"><data-views view="Targets"></data-views></data-scope>
      </aside>
    </div>`;
  api.wb.querySelector('.dw-pages').appendChild(page);
  planes = page.querySelector('#t2-planes');
  list = page.querySelector('#t2-list');
  // WHY: a scope's events bubble (CONTRACT §53); this page's own two scopes must not reach the workbench's listeners,
  // or every redraw here would read as a rail change and redraw again
  for (const inner of [planes, list]) {
    for (const type of ['data-scope-change', 'data-scope-load', 'data-scope-tab', 'data-scope-settings']) {
      inner.addEventListener(type, (e) => e.stopPropagation());
    }
  }
  side = page.querySelector('#t2-side');
  makeResizable(side, { edge: 'left', min: 300, max: 760, keep: 420, key: 'tc-round/t2/targets', label: 'the targets list' });
  const FOLD = 'tc-round/t2/targets-folded';
  const fold = page.querySelector('#t2-fold');
  const applyFold = (f) => { side.classList.toggle('folded', f); fold.textContent = f ? '«' : '»'; fold.title = f ? 'Show the targets list' : 'Fold the targets list'; };
  try { applyFold(localStorage.getItem(FOLD) === '1'); } catch { applyFold(false); }
  fold.addEventListener('click', () => { const f = !side.classList.contains('folded'); applyFold(f); try { localStorage.setItem(FOLD, f ? '1' : '0'); } catch { /* private */ } });
  planes.base = {
    properties: { title: { displayName: 'Plane' } },
    views: [{ type: 'coverage-plane', name: 'Error',
      // WHY equalized (colour = the cell's rank among every visited cell, the colour bar keeping the real degrees):
      // the error spans five decades here (0.001° on a tuned UR5e to 50° in a collision), so a linear or even a log map
      // paints every cell but the collisions one colour. The view's own Layout options switch it to linear or log.
      coverage: { value: 'max_other', switch: true, title: 'title', columns: 3, share: true, scale: 'equalized' } }],
  };
  list.base = {
    properties: { target: { displayName: 'Target' }, error: { displayName: 'Error in the cell' } },
    drill: { actions: [{ label: 'Open target view ↗', href: '/common/target.html?site={site}&target={target_slug}', title: 'The target view of {target}' }] },
    views: [{ type: 'table', name: 'Targets', order: ['target', 'error', 'runs', 'dataset', 'speed', 'configs', 'deployment'],
      sort: [{ property: 'error', direction: 'DESC' }], display: { dataset: 'badge', error: 'bar' } }],
  };
  planes.addEventListener('click', onPlaneClick, true);
}

// ── data ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

function ensureCells() {
  if (cells) return Promise.resolve(cells);
  if (!loading) loading = fetch('../data/t2-cells.json').then((r) => r.json()).then((c) => { cells = c; return c; });
  return loading;
}

function compute() {
  const kept = api.kept();
  const byTarget = new Map();
  for (const r of kept) { let a = byTarget.get(r.target_key); if (!a) byTarget.set(r.target_key, (a = [])); a.push(r); }
  const values = new Map(); // `${site}|${j}` -> Map(cell -> [[value, target_key], ...])
  const samples = new Map(), paths = new Map();
  for (const [tk, runs] of byTarget) {
    const site = runs[0].site;
    const pl = cells.planes[site], lines = cells.lines[site], geo = cells.targets[tk];
    if (!pl) continue;
    for (let j = 0; j < pl.length; j++) {
      const key = `${site}|${j}`;
      const size = pl[j].nx * pl[j].ny;
      if (geo && geo[j] && geo[j].length) {
        let s = samples.get(key), p = paths.get(key);
        if (!s) { samples.set(key, (s = new Array(size).fill(0))); paths.set(key, (p = new Array(size).fill(0))); }
        const g = geo[j];
        for (let k = 0; k < g.length; k += 2) { s[g[k]] += g[k + 1]; p[g[k]] += 1; }
      }
      const per = new Map();
      for (const r of runs) {
        const e = lines[r.line];
        if (!e || !e[j]) continue;
        const f = e[j];
        for (let k = 0; k < f.length; k += 2) { let a = per.get(f[k]); if (!a) per.set(f[k], (a = [])); a.push(f[k + 1] / 1e4); }
      }
      if (!per.size) continue;
      let vm = values.get(key);
      if (!vm) values.set(key, (vm = new Map()));
      for (const [cell, errs] of per) { let a = vm.get(cell); if (!a) vm.set(cell, (a = [])); a.push([median(errs), tk]); }
    }
  }
  // the grid rows, the worst cell, the median cell
  const rows = [];
  const every = [];
  let worst = null;
  const keys = [...values.keys()].sort((a, b) => {
    const [sa, ja] = a.split('|'), [sb, jb] = b.split('|');
    const da = ORDER.indexOf(deploymentOf(sa)), db = ORDER.indexOf(deploymentOf(sb));
    return da - db || Number(ja) - Number(jb);
  });
  const top = [];
  for (const key of keys) {
    const [site, jStr] = key.split('|');
    const j = Number(jStr);
    const pl = cells.planes[site][j];
    const vm = values.get(key);
    const size = pl.nx * pl.ny;
    const err = new Array(size).fill(null);
    for (const [cell, list] of vm) {
      const m = median(list.map((x) => x[0]));
      err[cell] = Math.round(m * 1e4) / 1e4;
      every.push(m);
      if (list.length >= MIN_TARGETS && (!worst || m > worst.median)) worst = { key, site, j, joint: pl.joint, cell, median: m, targets: list.length };
      if (list.length >= MIN_TARGETS) top.push({ panel: key, cell, median: m, targets: list.length });
    }
    rows.push({
      // WHY the joint first: a narrow panel cuts the end of its title, and the joint is what tells two panels apart
      id: key, title: `${pl.joint} · ${deploymentOf(site)}`, deployment: deploymentOf(site), joint: pl.joint,
      x: 'q', y: 'qd', x_label: 'position', y_label: 'speed',
      x_lo: pl.x_lo, x_hi: pl.x_hi, nx: pl.nx, y_lo: pl.y_lo, y_hi: pl.y_hi, ny: pl.ny,
      x_scale: DEG, y_scale: DEG, x_unit: '°', y_unit: '°/s', box: 'none', zero: 'y', enough: 1,
      samples: samples.get(key) || new Array(size).fill(0), paths: paths.get(key) || new Array(size).fill(0), max_other: err,
      other_label: 'tracking error (RMS in the cell)', other_scale: 1, other_unit: '°',
    });
  }
  top.sort((a, b) => b.median - a.median);
  return { rows, values, byTarget, worst, top: top.slice(0, 12), medianCell: every.length ? median(every) : null, cells: every.length };
}

function deploymentOf(site) {
  return { ur5e: 'UR5e + Conveyor PnP cell', ur5e_alone: 'UR5e', bam_fb: 'BAM FB', pendulum: '1-DOF pendulum' }[site] || site;
}

function cellWords(key, cell) {
  const [site, jStr] = key.split('|');
  const pl = cells.planes[site][Number(jStr)];
  const i = Math.floor(cell / pl.ny), jj = cell % pl.ny;
  const dx = (pl.x_hi - pl.x_lo) / pl.nx, dy = (pl.y_hi - pl.y_lo) / pl.ny;
  return { title: `${deploymentOf(site)} · ${pl.joint}`, where: `position ${range(pl.x_lo, dx, i, DEG)}°, speed ${range(pl.y_lo, dy, jj, DEG)} °/s` };
}

function targetsThrough(key, cell) {
  const list = (state.values.get(key) || new Map()).get(cell) || [];
  return list.map(([value, tk]) => {
    const runs = state.byTarget.get(tk) || [];
    const r = runs[0] || {};
    return { id: tk, site: r.site, target_slug: r.target_slug, target_key: tk, target: r.target, dataset: r.dataset,
      deployment: r.deployment, speed: r.speed, error: Math.round(value * 1e4) / 1e4, runs: runs.length,
      configs: [...new Set(runs.map((x) => x.config))].join(', ') };
  });
}

// ── drawing ──────────────────────────────────────────────────────────────────────────────────────────────────────────

const PROPS = {
  title: { type: 'text', label: 'Plane' }, deployment: { type: 'text', label: 'Deployment' }, joint: { type: 'text', label: 'Joint' },
};
const LIST_PROPS = {
  target: { type: 'text', label: 'Target' }, error: { type: 'number', label: 'Error in the cell', unitText: '°', digits: 3 },
  runs: { type: 'number', label: 'Runs (kept)' }, dataset: { type: 'text', label: 'Dataset' }, speed: { type: 'number', label: 'Speed', unitText: '×' },
  configs: { type: 'text', label: 'Configs' }, deployment: { type: 'text', label: 'Deployment' },
  site: { type: 'text', label: 'Site' }, target_slug: { type: 'text', label: 'Target slug' }, target_key: { type: 'text', label: 'Target key' },
};

function draw() {
  if (!cells || !page) return;
  state = compute();
  dirty = false;
  const head = page.querySelector('#t2-head'), sub = page.querySelector('#t2-sub');
  if (!state.rows.length) {
    head.textContent = 'No run the rail keeps has a joint error series: nothing to place.';
    sub.textContent = '';
  } else if (!state.worst) {
    head.textContent = `No cell has ${MIN_TARGETS} or more targets through it: widen the filter.`;
    sub.textContent = '';
  } else {
    const w = state.worst, words = cellWords(w.key, w.cell);
    const through = targetsThrough(w.key, w.cell);
    const tally = new Map();
    for (const t of through) tally.set(t.dataset, (tally.get(t.dataset) || 0) + 1);
    const [topSet, topN] = [...tally].sort((a, b) => b[1] - a[1])[0];
    head.textContent = `Worst: ${words.title} at ${words.where}: ${fmt(w.median)}° (median over the ${w.targets} targets through that cell; the median cell is ${fmt(state.medianCell)}°).`;
    sub.textContent = `${topN} of those ${w.targets} targets are ${topSet}. ${state.rows.length} joint plane${state.rows.length === 1 ? '' : 's'}, ${state.cells.toLocaleString('en-US')} cells with error. Click any cell to list the targets through it.`;
  }
  planes.data = { id: 't2-grids', title: 'Error over position × speed', titleProperty: 'title', properties: PROPS, rows: state.rows };
  const keep = pick && state.values.has(pick.key) && state.values.get(pick.key).has(pick.cell) ? pick : state.worst ? { key: state.worst.key, cell: state.worst.cell, auto: true } : null;
  showCell(keep);
  window.T2_STATE = state.worst ? {
    planes: state.rows.length, cells: state.cells, median_cell: Math.round(state.medianCell * 1e4) / 1e4,
    worst: { site: state.worst.site, joint: state.worst.joint, cell: state.worst.cell, median: Math.round(state.worst.median * 1e4) / 1e4, targets: state.worst.targets },
    // the next worst cells, one per plane (the check clicks one; a reader would click it on the plane)
    others: state.top.filter((t, i, all) => all.findIndex((x) => x.panel === t.panel) === i).slice(1, 6),
  } : { planes: state.rows.length, cells: state.cells, median_cell: null, worst: null };
  // WHY html[data-ready] here too: host-common.js marks it only for a <data-dashboard> page, and a link back to this
  // tab (the target view's ‹ All targets) opens on this host page
  whenDrawn().then(() => { placeMark(); page.dataset.ready = '1'; document.documentElement.dataset.ready = '1'; });
}

function showCell(p) {
  const title = page.querySelector('#t2-side-title');
  if (!p) { title.textContent = 'Targets through the cell'; list.data = { id: 't2-list', properties: LIST_PROPS, rows: [] }; return; }
  const words = cellWords(p.key, p.cell);
  const rows = targetsThrough(p.key, p.cell);
  title.textContent = `${p.auto ? 'Worst cell' : 'Picked cell'}: ${words.title} at ${words.where} · ${rows.length} target${rows.length === 1 ? '' : 's'}, worst first · click one: its target view`;
  list.data = { id: 't2-list', title: 'Targets through the cell', titleProperty: 'target', properties: LIST_PROPS, rows };
  page.dataset.cell = `${p.key}|${p.cell}`;
  placeMark(p);
}

// the coverage view's read-only hook (CONTRACT §52): {panels: [{id, canvas, box, nx, ny}]}
function hook() {
  const views = planes && planes.querySelector('data-views');
  if (!views) return null;
  for (const el of views.querySelectorAll('*')) if (el.coverage && Array.isArray(el.coverage.panels)) return el.coverage;
  return null;
}
function whenDrawn() {
  return new Promise((ok) => {
    let n = 0;
    (function tick() {
      const h = hook();
      if ((h && h.panels.length >= (state ? state.rows.length : 1)) || n++ > 60) { ok(); return; }
      setTimeout(tick, 100);
    }());
  });
}

let mark = null;
function placeMark(p) {
  const at = p || (page.dataset.cell ? { key: page.dataset.cell.split('|').slice(0, 2).join('|'), cell: Number(page.dataset.cell.split('|')[2]) } : null);
  const h = hook();
  if (mark) mark.hidden = true;
  if (!at || !h) return;
  const panel = h.panels.find((x) => x.id === at.key);
  if (!panel || !panel.canvas || !panel.box) return;
  const c = panel.canvas;
  const parent = c.parentElement;
  if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';
  if (!mark) { mark = document.createElement('div'); mark.className = 't2-mark'; }
  if (mark.parentElement !== parent) parent.appendChild(mark);
  const i = Math.floor(at.cell / panel.ny), jj = at.cell % panel.ny;
  const cw = panel.box.w / panel.nx, ch = panel.box.h / panel.ny;
  mark.style.left = `${c.offsetLeft + panel.box.x + i * cw - 1}px`;
  mark.style.top = `${c.offsetTop + panel.box.y + (panel.ny - 1 - jj) * ch - 1}px`;
  mark.style.width = `${cw + 2}px`;
  mark.style.height = `${ch + 2}px`;
  mark.hidden = false;
}

// a click on a cell: the targets through it (WHY the host reads the hook: the stock click opens the grid row, not a cell)
function onPlaneClick(e) {
  const h = hook();
  if (!h || !state) return;
  const panel = h.panels.find((x) => x.canvas === e.target);
  if (!panel || !panel.box) return;
  const r = panel.canvas.getBoundingClientRect();
  const x = e.clientX - r.left - panel.box.x, y = e.clientY - r.top - panel.box.y;
  if (x < 0 || y < 0 || x >= panel.box.w || y >= panel.box.h) return;
  const i = Math.floor((x / panel.box.w) * panel.nx), jj = panel.ny - 1 - Math.floor((y / panel.box.h) * panel.ny);
  const cell = i * panel.ny + jj;
  e.preventDefault(); e.stopPropagation();
  if (!(state.values.get(panel.id) || new Map()).has(cell)) return;
  pick = { key: panel.id, cell };
  showCell(pick);
}

// ── wiring: the page is made when the file is read; it draws when shown, and again when the rail changes ─────────────

api.wb.addEventListener('data-scope-load', makePage);
function shown() { return page && !page.hidden; }
function refresh() {
  if (!shown()) return;
  ensureCells().then(() => { if (dirty) draw(); });
}
api.wb.addEventListener('data-scope-tab', () => setTimeout(refresh, 0));
api.onChange.push(() => { dirty = true; if (page) delete page.dataset.ready; refresh(); });
window.addEventListener('resize', () => setTimeout(() => placeMark(), 300));
window.TC_HOST = api;
