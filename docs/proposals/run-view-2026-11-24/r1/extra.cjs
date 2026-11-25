// R1's extra still (headless, 1440 x 900): Shift-drag draws uPlot's own zoom box (the zoom gesture that moved off the
// plain drag), mid-gesture, on the tta fixture's first chart.
const path = require('path');
const { chromium } = require('/home/bam/aruco-studio/web/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await page.goto('http://127.0.0.1:8853/r1/index.html?fixture=tta&keep=p5s-pass3,p6s&dry=1');
  await page.waitForFunction(() => window.__runView && window.__runView.ready);
  await page.evaluate(() => { const p = TrajCompare.state.pages[0]; p.transport.setScrub(3.51); p.charts[0].card.scrollIntoView({ block: 'center' }); });
  await page.waitForTimeout(600);
  const b = await page.evaluate(() => TrajCompare.state.pages[0].charts[0].u.over.getBoundingClientRect().toJSON());
  await page.mouse.move(b.left + b.width * 0.55, b.top + b.height * 0.5);
  await page.keyboard.down('Shift');
  await page.mouse.down();
  for (let k = 1; k <= 10; k++) await page.mouse.move(b.left + b.width * (0.55 + 0.3 * k / 10), b.top + b.height * 0.5);
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(__dirname, '..', 'shots', 'r1', 'extra-shift-zoom.png') });
  await page.mouse.up();
  await page.keyboard.up('Shift');
  await browser.close();
})();
