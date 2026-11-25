#!/usr/bin/env node
// The round's proof for one variant (headless Chrome, 1440 x 900, never a visible window). Served by serve.py.
//
//   node check.cjs r1 [--port 8853] [--video] [--only tta|bam_fb]
//
// Per fixture (tta: Zach's screenshot, Target + p5s-pass3 + p6s; bam_fb: 17 lines, 8 configs), with rN/gestures.json
// naming the variant's own gestures:
//   1. hero still at the same moment (t = HERO_T[fixture]) on the first tab;
//   2. SYNC: drag the time on chart A (the variant's scrub gesture), sampling mid-drag (live) and after release; read
//      back, from what is DRAWN, every shown chart's playhead, the stage slider(s), the 3D's drawn time and every posed
//      arm (its sample's time and its last link against the payload's pose); then switch to another tab and read that
//      tab's charts too. Pass = every reading within one sample of the committed t;
//   3. ZOOM: the variant's zoom gesture narrows x on every shown chart alike; its reset restores the full range;
//   4. SELECTION: ?keep= is honoured (the shown runs = keep), then toggling one run off hides it on every chart and in
//      the 3D, and the back link's keep= follows;
//   5. Open the same in Rerun (dry: written, not launched): the .rrd exists and names exactly the shown runs;
//   6. console errors and sideways overflow.
// Writes shots/<v>/*.png, shots/<v>/check.json (and with --video shots/<v>/sync-<fixture>.webm → .mp4).
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const v = args[0];
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const port = Number(opt('--port', 8853));
const wantVideo = args.includes('--video');
const only = opt('--only', null);
const here = __dirname;
const gestures = JSON.parse(fs.readFileSync(path.join(here, v, 'gestures.json'), 'utf8'));
const out = path.join(here, 'shots', v);
fs.mkdirSync(out, { recursive: true });

// The same moment in every variant's hero: tta's worst moment (p6s on wrist_1 at 3.51 s, the screenshot's "Go to");
// bam_fb's mid-motion 2.0 s.
const HERO_T = { tta: 3.51, bam_fb: 2.0 };
const FIXTURES = [
  { name: 'tta', keep: 'p5s-pass3,p6s', back: '/tta/index.html', toggle: 'p6s', otherTab: 'joints' },
  { name: 'bam_fb', keep: '3460,3461,3463,3465,3466,3467,3471,3474,3476', back: null, toggle: 'L3471', otherTab: 'joints' },
];

const R = { variant: v, port, fixtures: {}, errors: [], ok: true };
function fail(where, why) { R.ok = false; R.errors.push(where + ': ' + why); }

async function ready(page) {
  await page.waitForFunction(() => window.__runView && window.__runView.ready, null, { timeout: 90000 });
  await page.waitForTimeout(700);
}
async function shownCharts(page) {
  return page.evaluate(() => window.__runView.charts().filter((c) => c.shown && c.box && c.box.width > 40));
}
// Bring a chart fully into the viewport (a long run list can push it below the fold) and return its fresh box.
async function focusChart(page, index) {
  await page.evaluate((i) => { const c = TrajCompare.state.pages[0].charts[i]; c.card.scrollIntoView({ block: 'center' }); }, index);
  await page.waitForTimeout(250);
  return (await shownCharts(page)).filter((c) => c.index === index)[0];
}
async function readback(page) {
  return page.evaluate(() => ({
    t: window.__runView.t(), grid: window.__runView.grid().length, sliders: window.__runView.sliders(),
    charts: window.__runView.charts().filter((c) => c.shown).map((c) => ({ i: c.index, title: c.title, tab: c.tab, playhead: c.playhead, zoom: c.zoom })),
    pose: window.__runView.pose3d(), tab: window.__runView.activeTab(), selection: window.__runView.selection(),
  }));
}
function dtOf(grid) { let d = Infinity; for (let i = 1; i < grid.length; i++) d = Math.min(d, grid[i] - grid[i - 1]); return d; }
function judge(rb, dt, label, rec) {
  const t = rb.t;
  const tol = dt * 1.01 + 1e-6;
  const bad = [];
  rb.charts.forEach((c) => { if (c.playhead === null || Math.abs(c.playhead - t) > tol) bad.push(`chart ${c.i} "${c.title.slice(0, 40)}" playhead ${c.playhead}`); });
  if (!rb.charts.length) bad.push('no chart shown');
  (rec.sliderSkip ? [] : rb.sliders).forEach((s, i) => { if (!(Math.abs(s - t) <= Math.max(tol, 0.003))) bad.push(`slider ${i} ${s}`); });
  if (rb.pose) {
    if (Math.abs(rb.pose.time - t) > tol) bad.push(`3D time ${rb.pose.time}`);
    rb.pose.robots.filter((r) => r.visible).forEach((r) => {
      if (Math.abs(r.t - t) > tol * 2) bad.push(`arm ${r.name} t ${r.t}`);
      const d = r.tip && r.expected ? Math.hypot(r.tip[0] - r.expected[0], r.tip[1] - r.expected[1], r.tip[2] - r.expected[2]) : 1;
      if (d > 1e-6) bad.push(`arm ${r.name} tip off its sample by ${d}`);
    });
  }
  rec[label] = { t, charts: rb.charts.length, maxChartDiff: Math.max(0, ...rb.charts.map((c) => Math.abs((c.playhead ?? 1e9) - t))),
    sliders: rb.sliders, pose3dTime: rb.pose ? rb.pose.time : null, arms: rb.pose ? rb.pose.robots.filter((r) => r.visible).map((r) => ({ name: r.name, t: r.t })) : [],
    tab: rb.tab, pass: !bad.length, bad };
  if (bad.length) fail(label, bad.slice(0, 4).join('; '));
}
async function mods(page, list, down) { for (const k of list || []) await (down ? page.keyboard.down(k) : page.keyboard.up(k)); }

async function scrubDrag(page, chart, f0, f1, steps, sampleAt) {
  const g = gestures.scrub || {};
  const box = chart.box;
  const y = box.top + box.height * (g.yFrac ?? 0.55);
  const x0 = box.left + box.width * f0, x1 = box.left + box.width * f1;
  let mid = null;
  if (g.selector) { // the variant scrubs on its own element (a timeline lane), at the chart's x pixels
    const lane = await page.evaluate((sel) => { const e = document.querySelector(sel); return e ? e.getBoundingClientRect().toJSON() : null; }, g.selector);
    if (!lane) throw new Error('no scrub element ' + g.selector);
    return scrubOn(page, lane.top + lane.height * (g.yFrac ?? 0.5), x0, x1, steps, sampleAt, g);
  }
  return scrubOn(page, y, x0, x1, steps, sampleAt, g);
}
async function scrubOn(page, y, x0, x1, steps, sampleAt, g) {
  let mid = null;
  await page.mouse.move(x0, y);
  await mods(page, g.modifiers, true);
  await page.mouse.down();
  for (let k = 1; k <= steps; k++) {
    await page.mouse.move(x0 + (x1 - x0) * k / steps, y);
    await page.waitForTimeout(g.stepMs ?? 30);
    if (k === sampleAt) mid = await readback(page);
  }
  await page.mouse.up();
  await mods(page, g.modifiers, false);
  await page.waitForTimeout(250);
  return mid;
}

async function zoomGesture(page, chart) {
  const z = gestures.zoom;
  const box = chart.box;
  const y = box.top + box.height * 0.5;
  if (z.kind === 'wheel') {
    await page.mouse.move(box.left + box.width * (z.at ?? 0.5), y);
    for (let k = 0; k < (z.ticks ?? 4); k++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(60); }
  } else if (z.kind === 'drag') {
    let yy = y, b = box;
    if (z.selector) b = await page.evaluate((sel) => document.querySelector(sel).getBoundingClientRect().toJSON(), z.selector), yy = b.top + b.height * (z.yFrac ?? 0.5);
    await page.mouse.move(b.left + b.width * (z.from ?? 0.3), yy);
    await mods(page, z.modifiers, true);
    await page.mouse.down();
    for (let k = 1; k <= 8; k++) { await page.mouse.move(b.left + b.width * ((z.from ?? 0.3) + ((z.to ?? 0.6) - (z.from ?? 0.3)) * k / 8), yy); await page.waitForTimeout(25); }
    await page.mouse.up();
    await mods(page, z.modifiers, false);
  } else if (z.kind === 'click') {
    await page.click(z.selector);
  }
  await page.waitForTimeout(400);
}
async function resetZoom(page, chart) {
  const r = gestures.reset || { dblclick: 'chart' };
  if (r.click) await page.click(r.click);
  else { const b = chart.box; await page.mouse.dblclick(b.left + b.width * 0.5, b.top + b.height * 0.5); }
  await page.waitForTimeout(400);
}
async function openTab(page, id) {
  const sel = (gestures.tab || '[data-tc-tab="{id}"]').replace('{id}', id);
  await page.click(sel);
  await page.waitForTimeout(700);
}

async function runFixture(browser, fx) {
  const rec = { url: null };
  R.fixtures[fx.name] = rec;
  const query = new URLSearchParams({ fixture: fx.name, keep: fx.keep, dry: '1' });
  if (fx.back) query.set('back', fx.back);
  const url = `http://127.0.0.1:${port}/${v}/index.html?${query.toString().replace(/%2C/g, ',')}`;
  rec.url = url;
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  await page.goto(url);
  await ready(page);
  rec.dt = await page.evaluate(() => { const g = window.__runView.grid(); let d = Infinity; for (let i = 1; i < g.length; i++) d = Math.min(d, g[i] - g[i - 1]); return d; });
  rec.firstTab = await page.evaluate(() => window.__runView.activeTab());

  // 4a. keep= honoured
  const want = fx.keep.split(',').map((k) => (/^\d+$/.test(k) ? 'L' + k : k)).sort();
  const sel = (await page.evaluate(() => window.__runView.selection())).slice().sort();
  rec.keep = { want, shown: sel, pass: JSON.stringify(want) === JSON.stringify(sel) };
  if (!rec.keep.pass) fail(fx.name + ' keep', `shown ${sel} != keep ${want}`);

  // 1. hero at the same moment (set through the variant's own transport; the drag is tested below)
  await page.evaluate((t) => { const p = TrajCompare.state.pages[0]; p.transport.pause(); p.transport.setScrub(t); }, HERO_T[fx.name]);
  if (gestures.heroSetup) await page.evaluate(gestures.heroSetup);
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(out, `hero-${fx.name}.png`) });

  // 2. SYNC by dragging on chart A
  let charts = await shownCharts(page);
  if (!charts.length) { fail(fx.name, 'no chart shown on the first tab'); }
  else {
    const a = await focusChart(page, charts[0].index);
    rec.chartA = a.title;
    rec.chartAScrolledBy = await page.evaluate(() => window.scrollY);
    const mid = await scrubDrag(page, a, 0.18, 0.72, 16, 8);
    if (mid) judge(mid, rec.dt, 'syncMidDrag', rec);
    const after = await readback(page);
    judge(after, rec.dt, 'syncAfterRelease', rec);
    const expectT = await page.evaluate(([i, b, f]) => { const c = TrajCompare.state.pages[0].charts[i]; return c.u.posToVal(b.width * f, 'x'); }, [a.index, a.box, 0.72]);
    rec.dragTarget = expectT;
    if (!gestures.snaps && Math.abs(after.t - expectT) > rec.dt * 1.01 + 1e-6) fail(fx.name + ' drag', `committed ${after.t}, pointer at ${expectT}`);
    rec.dragLanded = Math.abs(after.t - expectT);
    await page.screenshot({ path: path.join(out, `sync-${fx.name}-after-drag.png`) });
    // the other tab
    await openTab(page, fx.otherTab);
    const other = await readback(page);
    judge(other, rec.dt, 'syncOtherTab', rec);
    await page.screenshot({ path: path.join(out, `sync-${fx.name}-other-tab.png`) });
    await openTab(page, rec.firstTab);

    // 3. ZOOM by the variant's gesture
    charts = await shownCharts(page);
    const za = await focusChart(page, charts[0].index);
    const full = za.zoom;
    await zoomGesture(page, za);
    const zoomed = await shownCharts(page);
    const spans = zoomed.map((c) => c.zoom[1] - c.zoom[0]);
    const tNow = await page.evaluate(() => window.__runView.t());
    const narrowed = spans.every((s) => s < (full[1] - full[0]) * 0.9);
    const alike = zoomed.every((c) => Math.abs(c.zoom[0] - zoomed[0].zoom[0]) < 1e-6 && Math.abs(c.zoom[1] - zoomed[0].zoom[1]) < 1e-6);
    rec.zoom = { full, zoomed: zoomed[0].zoom, charts: zoomed.length, narrowed, alike, timeUnchanged: Math.abs(tNow - after.t) < 1e-9 };
    if (!narrowed || !alike) fail(fx.name + ' zoom', JSON.stringify(rec.zoom));
    if (!rec.zoom.timeUnchanged && !gestures.zoomMovesTime) fail(fx.name + ' zoom', 'the zoom gesture moved the time');
    await page.screenshot({ path: path.join(out, `zoom-${fx.name}.png`) });
    await resetZoom(page, zoomed[0]);
    const reset = await shownCharts(page);
    rec.zoom.reset = reset[0].zoom;
    if (Math.abs(reset[0].zoom[0] - full[0]) > 1e-6 || Math.abs(reset[0].zoom[1] - full[1]) > 1e-6) fail(fx.name + ' zoom reset', JSON.stringify(reset[0].zoom));
  }

  // 4b. toggle one run off: every chart and the 3D drop it; the back link's keep follows
  const toggleSel = (gestures.toggle || '[data-rv-run="{name}"]').replace('{name}', fx.toggle);
  const backBefore = await page.evaluate(() => window.__runView.backHref());
  await page.click(toggleSel);
  await page.waitForTimeout(500);
  const after = await page.evaluate((name) => {
    const rv = window.__runView;
    const charts = rv.charts().filter((c) => c.shown);
    const still = charts.filter((c) => c.series.some((s) => s.sit === name && s.show));
    const pose = rv.pose3d();
    const arm = pose ? pose.robots.filter((r) => r.name === name)[0] : null;
    return { selection: rv.selection(), chartsWithIt: still.length, charts: charts.length, armVisible: arm ? arm.visible : null, back: rv.backHref(),
      count: (document.querySelector('[data-rv-count]') || {}).textContent };
  }, fx.toggle);
  rec.toggle = { name: fx.toggle, backBefore, ...after, pass: !after.selection.includes(fx.toggle) && after.chartsWithIt === 0 && after.armVisible !== true };
  if (!rec.toggle.pass) fail(fx.name + ' toggle', JSON.stringify(rec.toggle));
  await page.screenshot({ path: path.join(out, `toggle-${fx.name}.png`) });
  await page.click(toggleSel);  // back on
  await page.waitForTimeout(300);

  // 5. Open the same in Rerun (dry)
  await page.click('[data-rv-rerun]');
  await page.waitForFunction(() => { const s = document.querySelector('[data-rv-status]'); return s && /ok|bad/.test(s.className); }, null, { timeout: 180000 }).catch(() => {});
  const rr = await page.evaluate(() => ({ status: document.querySelector('[data-rv-status]').textContent, answer: window.__runViewLastRerun || null, shown: window.__runView.selection(), t: window.__runView.t() }));
  rec.rerun = { status: rr.status, rrd: rr.answer && rr.answer.rrd, names: rr.answer && rr.answer.names, t: rr.answer && rr.answer.t, tab: rr.answer && rr.answer.tab };
  rec.rerun.pass = !!(rr.answer && fs.existsSync(rr.answer.rrd) && JSON.stringify(rr.answer.names.slice().sort()) === JSON.stringify(rr.shown.slice().sort()) && Math.abs(rr.answer.t - rr.t) < 1e-9);
  if (!rec.rerun.pass) fail(fx.name + ' rerun', JSON.stringify(rec.rerun));

  // 6. layout sanity
  rec.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (rec.overflow > 0) fail(fx.name + ' overflow', rec.overflow + ' px sideways');
  rec.consoleErrors = consoleErrors;
  if (consoleErrors.length) fail(fx.name + ' console', consoleErrors.slice(0, 3).join(' | '));
  await context.close();
}

// A short film of the drag-to-sync interaction, slow enough to watch: hover, press, drag across, release, other tab.
async function film(browser, fx) {
  const dir = path.join(out, 'film-' + fx.name);
  fs.rmSync(dir, { recursive: true, force: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir, size: { width: 1440, height: 900 } } });
  const page = await context.newPage();
  const filmStart = Date.now();  // the recording starts with the page: the drag's offset into it trims the load away
  const query = new URLSearchParams({ fixture: fx.name, keep: fx.keep, dry: '1' });
  await page.goto(`http://127.0.0.1:${port}/${v}/index.html?${query.toString().replace(/%2C/g, ',')}`);
  await ready(page);
  await page.evaluate(() => { const p = TrajCompare.state.pages[0]; p.transport.pause(); p.transport.setScrub(p.transport.tMin + (p.transport.tMax - p.transport.tMin) * 0.1); });
  if (gestures.filmSetup) await page.evaluate(gestures.filmSetup);
  await page.waitForTimeout(800);
  await page.evaluate(() => { // a visible pointer: headless video has no cursor
    const dot = document.createElement('div');
    dot.id = 'rv-film-pointer';
    dot.style.cssText = 'position:fixed;z-index:99999;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(214,51,108,.35);border:2px solid #d6336c;pointer-events:none;left:-50px;top:-50px';
    document.body.appendChild(dot);
    document.addEventListener('mousemove', (e) => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', () => { dot.style.background = 'rgba(214,51,108,.8)'; }, true);
    document.addEventListener('mouseup', () => { dot.style.background = 'rgba(214,51,108,.35)'; }, true);
  });
  const listed = await shownCharts(page);
  const pick = await focusChart(page, listed[Math.min(listed.length - 1, gestures.filmChart ?? 1)].index);
  const g = gestures.scrub || {};
  let y = pick.box.top + pick.box.height * 0.55;
  if (g.selector) { const lane = await page.evaluate((s) => document.querySelector(s).getBoundingClientRect().toJSON(), g.selector); y = lane.top + lane.height * (g.yFrac ?? 0.5); }
  const x0 = pick.box.left + pick.box.width * 0.12, x1 = pick.box.left + pick.box.width * 0.85;
  const dragStart = Date.now();
  await page.mouse.move(x0 - 60, y + 30, { steps: 8 });
  await page.waitForTimeout(400);
  await page.mouse.move(x0, y, { steps: 6 });
  await mods(page, g.modifiers, true);
  await page.mouse.down();
  for (let k = 1; k <= 60; k++) { await page.mouse.move(x0 + (x1 - x0) * k / 60, y); await page.waitForTimeout(45); }
  for (let k = 59; k >= 25; k--) { await page.mouse.move(x0 + (x1 - x0) * k / 60, y); await page.waitForTimeout(40); }
  await page.mouse.up();
  await mods(page, g.modifiers, false);
  await page.waitForTimeout(700);
  await openTab(page, fx.otherTab);
  await page.waitForTimeout(1400);
  const filmEnd = Date.now();
  await context.close();
  const webm = fs.readdirSync(dir).filter((f) => f.endsWith('.webm')).map((f) => path.join(dir, f))[0];
  const mp4 = path.join(out, `sync-${fx.name}.mp4`);
  // WHY trimmed and maybe sped up: the recording starts at page creation, so it holds the fixture's load (13.6 MB for
  // bam_fb), and the headless software renderer draws ten arms slowly; the film keeps the interaction only, at most
  // ~18 s. The speed-up is recorded (film.json) and said in the gallery caption.
  const from = Math.max(0, (dragStart - filmStart) / 1000 - 0.6);
  const length = (filmEnd - dragStart) / 1000 + 0.6;
  const speed = Math.max(1, length / 18);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', from.toFixed(2), '-i', webm, '-vf', `setpts=PTS/${speed.toFixed(3)},scale=1440:-2`, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '28', '-movflags', '+faststart', '-an', mp4]);
  fs.writeFileSync(path.join(out, `sync-${fx.name}.film.json`), JSON.stringify({ trimmedFrom: from, interactionSeconds: length, speed }));
  fs.rmSync(dir, { recursive: true, force: true });
  return mp4;
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  try {
    for (const fx of FIXTURES) {
      if (only && fx.name !== only) continue;
      try { await runFixture(browser, fx); } catch (error) { fail(fx.name, 'threw ' + (error && error.stack || error)); }
      if (wantVideo) { try { R.fixtures[fx.name].video = await film(browser, fx); } catch (error) { fail(fx.name + ' film', String(error)); } }
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(out, 'check.json'), JSON.stringify(R, null, 1));
  console.log(JSON.stringify({ variant: v, ok: R.ok, errors: R.errors }, null, 1));
})();
