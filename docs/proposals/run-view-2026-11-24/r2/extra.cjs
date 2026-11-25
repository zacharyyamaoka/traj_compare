#!/usr/bin/env node
// R2's extra stills (run-view round 2026-11-24): headless Chrome, 1440 x 900, from the real page on the round server.
//   node r2/extra.cjs [--port 8853]   ->  shots/r2/extra-*.png (listed in r2/media.json)
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const port = Number(args.includes('--port') ? args[args.indexOf('--port') + 1] : 8853);
const out = path.join(__dirname, '..', 'shots', 'r2');
const ALL_17 = '3460,3461,3462,3463,3464,3465,3466,3467,3468,3469,3470,3471,3472,3473,3474,3475,3476';
const KEEP_9 = '3460,3461,3463,3465,3466,3467,3471,3474,3476';

async function open(browser, query, prefs) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  // the lane's remembered height / fold (localStorage, as a reader would have left them)
  await context.addInitScript((entries) => {
    try { Object.keys(entries).forEach((key) => localStorage.setItem(key, JSON.stringify(entries[key]))); } catch (error) {}
  }, prefs || {});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(`http://127.0.0.1:${port}/r2/index.html?${query}&dry=1`);
  await page.waitForFunction(() => window.__runView && window.__runView.ready, null, { timeout: 120000 });
  await page.waitForTimeout(800);
  return { context, page, errors };
}
function at(page, t) {
  return page.evaluate((time) => { const p = TrajCompare.state.pages[0]; p.transport.pause(); p.transport.setScrub(time); }, t);
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  try {
    // 1. all 17 bam_fb lines in the lane, grouped by config, each with its error band and moments, at the worst moment
    {
      const { context, page, errors } = await open(browser, `fixture=bam_fb&keep=${ALL_17}`, { 'traj-compare:rv2:lane-h': 700 });
      await at(page, 1.71);
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(out, 'extra-lane-17.png') });
      console.log('extra-lane-17', await page.evaluate(() => ({
        tracks: document.querySelectorAll('[data-rv-track]').length, shown: window.__runView.selection().length,
        marks: document.querySelectorAll('[data-rv-moment]').length, laneH: document.querySelector('[data-rv-lane]').offsetHeight,
      })), errors);
      await context.close();
    }
    // 2. zoomed around the worst moment: one line through every joint chart (lane folded to transport + ruler)
    {
      const { context, page, errors } = await open(browser, `fixture=bam_fb&keep=${KEEP_9}#tab=joints`, { 'traj-compare:rv2:lane-folded': true });
      await at(page, 1.71);
      await page.evaluate(() => TrajCompare.state.pages[0].timeline.setView(1.15, 2.35));
      await page.evaluate(() => {
        const first = TrajCompare.state.pages[0].charts.filter((c) => c.card.offsetParent)[0];
        document.querySelector('[data-rv-scroll]').scrollTop = first.card.offsetTop - 34;
      });
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(out, 'extra-zoomed-line.png') });
      console.log('extra-zoomed-line', await page.evaluate(() => {
        const rv = window.__runView, t = rv.t();
        const shown = rv.charts().filter((c) => c.shown);
        const visible = shown.filter((c) => c.box.bottom > 0 && c.box.top < window.innerHeight);
        return { t, zoom: shown[0].zoom, charts: shown.length, inView: visible.length,
          maxDiff: Math.max(...shown.map((c) => Math.abs(c.playhead - t))) };
      }), errors);
      await context.close();
    }
    // 3. hover a run's track: the dashed preview line through every chart and the 3D at that instant; the solid line stays
    {
      const { context, page, errors } = await open(browser, 'fixture=tta&keep=p5s-pass3,p6s#tab=where', {});
      await at(page, 3.51);
      const track = await page.evaluate(() => document.querySelector('[data-rv-track="p6s"] .rv-track-time').getBoundingClientRect().toJSON());
      await page.mouse.move(track.left + track.width * 0.45, track.top + track.height / 2, { steps: 4 });
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(out, 'extra-hover-preview.png') });
      console.log('extra-hover-preview', await page.evaluate(() => ({ committed: window.__runView.t(), shown3d: window.__runView.pose3d().time })), errors);
      await context.close();
    }
  } finally {
    await browser.close();
  }
})();
