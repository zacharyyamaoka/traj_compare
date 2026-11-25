#!/usr/bin/env node
// R5's extra stills (run-view round 2026-11-24): headless Chrome at 1440 × 900, the real page on the round server, each
// state reached by the reader's own gestures (no state poked in). Writes shots/r5/extra-*.png; media.json captions them.
//
//   node r5/extra.cjs [--port 8853]
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const port = Number(args.includes('--port') ? args[args.indexOf('--port') + 1] : 8853);
const out = path.join(__dirname, '..', 'shots', 'r5');
const KEEP = { tta: 'p5s-pass3,p6s', bam_fb: '3460,3461,3463,3465,3466,3467,3471,3474,3476' };

async function open(browser, fixture) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const problems = [];
  page.on('pageerror', (error) => problems.push(String(error)));
  page.on('console', (message) => { if (message.type() === 'error') problems.push(message.text()); });
  // no ?t=: the page opens at the worst moment by itself (R5's first decision)
  await page.goto(`http://127.0.0.1:${port}/r5/index.html?fixture=${fixture}&keep=${KEEP[fixture]}&dry=1`);
  await page.waitForFunction(() => window.__runView && window.__runView.ready, null, { timeout: 90000 });
  await page.waitForTimeout(900);
  return { context, page, problems };
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const report = {};
  try {
    // 1. tta: opened at p6s's worst moment; "Zoom to this moment" gives the close-up; the readouts read both runs there
    {
      const { context, page, problems } = await open(browser, 'tta');
      report.ttaOpenedAt = await page.evaluate(() => window.__runView.t());
      await page.click('[data-rv5-zoom-moment]');
      await page.waitForTimeout(500);
      report.ttaZoom = await page.evaluate(() => window.__runView.charts().filter((c) => c.shown).map((c) => c.zoom)[0]);
      await page.screenshot({ path: path.join(out, 'extra-moments-readouts-tta.png') });
      report.ttaProblems = problems;
      await context.close();
    }
    // 2. bam_fb: nine arms at the worst moment, the focus (record · r0 · sim) solid; the stage dragged wider and the 3D
    //    zoomed in with the wheel, both by the reader's gestures
    {
      const { context, page, problems } = await open(browser, 'bam_fb');
      const handle = await page.evaluate(() => document.querySelector('[data-tc-stage-resize]').getBoundingClientRect().toJSON());
      await page.mouse.move(handle.left + handle.width / 2, handle.top + 300);
      await page.mouse.down();
      await page.mouse.move(handle.left + handle.width / 2 + 300, handle.top + 300, { steps: 12 });
      await page.mouse.up();
      await page.waitForTimeout(500);
      const canvas = await page.evaluate(() => document.querySelector('.tc-3dcanvasbox canvas').getBoundingClientRect().toJSON());
      await page.mouse.move(canvas.left + canvas.width * 0.5, canvas.top + canvas.height * 0.5);
      for (let tick = 0; tick < 2; tick++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(60); }
      await page.waitForTimeout(600);
      report.bamArms = await page.evaluate(() => window.__runView.pose3d().robots.filter((r) => r.visible).map((r) => r.name + ':' + r.role));
      report.bamOpenedAt = await page.evaluate(() => window.__runView.t());
      await page.screenshot({ path: path.join(out, 'extra-ghosts-bam_fb.png') });
      report.bamProblems = problems;
      await context.close();
    }
    // 3. bam_fb: a drag on the first chart, held just short of 2.83 s: the playhead snaps onto the moment and names it
    {
      const { context, page, problems } = await open(browser, 'bam_fb');
      await page.evaluate(() => TrajCompare.state.pages[0].charts[0].card.scrollIntoView({ block: 'center' }));
      await page.waitForTimeout(300);
      const box = await page.evaluate(() => TrajCompare.state.pages[0].charts[0].u.over.getBoundingClientRect().toJSON());
      const xs = await page.evaluate((times) => times.map((t) => TrajCompare.state.pages[0].charts[0].u.valToPos(t, 'x')), [2.3, 2.805]);
      await page.mouse.move(box.left + xs[0], box.top + box.height * 0.55);
      await page.mouse.down();
      await page.mouse.move(box.left + xs[1], box.top + box.height * 0.55, { steps: 10 });
      await page.waitForTimeout(300);
      report.snap = await page.evaluate(() => { const p = TrajCompare.state.pages[0]; return { t: p.transport.t, snapped: p.rvSnapped && p.rvSnapped.t }; });
      await page.screenshot({ path: path.join(out, 'extra-snap-bam_fb.png') });
      await page.mouse.up();
      report.snapProblems = problems;
      await context.close();
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(report, null, 1));
})();
