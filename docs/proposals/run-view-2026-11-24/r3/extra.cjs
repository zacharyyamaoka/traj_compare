#!/usr/bin/env node
// R3's extra stills (beyond check.cjs): the same moment of bam_fb with Repeats = Bands and = Lines, and all 17 runs as
// bands in the joint-error tab, zoomed by brushing the summary strip. Headless, 1440 x 900, from the real page.
//   node r3/extra.cjs [--port 8853]
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');
const args = process.argv.slice(2);
const port = Number(args.includes('--port') ? args[args.indexOf('--port') + 1] : 8853);
const out = path.join(__dirname, '..', 'shots', 'r3');
const KEEP9 = '3460,3461,3463,3465,3466,3467,3471,3474,3476';
const ALL17 = Array.from({ length: 17 }, (_, i) => 3460 + i).join(',');

async function open(browser, keep, hash) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:${port}/r3/index.html?fixture=bam_fb&keep=${keep}&dry=1${hash || ''}`);
  await page.waitForFunction(() => window.__runView && window.__runView.ready, null, { timeout: 90000 });
  await page.waitForTimeout(700);
  return { context, page };
}
async function at(page, t) {
  await page.evaluate((time) => { const p = TrajCompare.state.pages[0]; p.transport.pause(); p.transport.setScrub(time); }, t);
}

// brush the summary strip from fraction a to b (the variant's zoom gesture)
async function brush(page, a, b) {
  const box = await page.evaluate(() => document.querySelector('[data-rv-strip] .u-over').getBoundingClientRect().toJSON());
  const y = box.top + box.height * 0.5;
  await page.mouse.move(box.left + box.width * a, y);
  await page.mouse.down();
  for (let k = 1; k <= 10; k++) { await page.mouse.move(box.left + box.width * (a + (b - a) * k / 10), y); await page.waitForTimeout(25); }
  await page.mouse.up();
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const wrote = [];
  try {
    // 1-2. all 17 runs (8 configs, repeats r0-r2), the joint-error tab, the same window and moment: Lines, then Bands
    for (const mode of ['lines', 'bands']) {
      const { context, page } = await open(browser, ALL17, '#tab=joints');
      await page.click(`[data-rv3-repeats="${mode}"]`);
      await at(page, 1.71);
      await brush(page, 0.3, 0.56);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(900);
      const file = path.join(out, `extra-17-${mode}.png`);
      await page.screenshot({ path: file });
      wrote.push(file);
      await context.close();
    }
    // 3. the 9 runs the target view sent, the first tab, Bands: the strip's legend, the bands on the largest-error chart
    const { context, page } = await open(browser, KEEP9);
    await page.click('[data-rv3-repeats="bands"]');
    await at(page, 1.71);
    await page.waitForTimeout(900);
    const file = path.join(out, 'extra-9-bands.png');
    await page.screenshot({ path: file });
    wrote.push(file);
    await context.close();
  } finally {
    await browser.close();
  }
  console.log('wrote', wrote.join(' '));
})();
