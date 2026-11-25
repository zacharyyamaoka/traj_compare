#!/usr/bin/env node
// R4's extra stills (media.json), headless at 1440 x 900 from the real page on the round server (port 8853):
//   extra-beside-rerun.png  this page over the REAL Rerun 0.40 viewer showing the recording "Open the same in Rerun"
//                           writes for the same runs and time (shots/r4/rerun-real-tta-blueprint.png, by rerun-real.cjs);
//   extra-help.png          a chart's "?" help: the gestures here beside Rerun 0.40's own, the one difference marked;
//   extra-time-panel.png    the time panel: a time segment selected on the time scale (loop on) and a right-drag zoom
//                           band mid-gesture, under the real Rerun time panel doing the same.
//
//   node r4/extra.cjs [--port 8853]
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const here = path.resolve(__dirname, '..');
const out = path.join(here, 'shots', 'r4');
const port = Number(process.argv.includes('--port') ? process.argv[process.argv.indexOf('--port') + 1] : 8853);
const url = `http://127.0.0.1:${port}/r4/index.html?fixture=tta&keep=p5s-pass3,p6s&dry=1`;
const realBlueprint = path.join(out, 'rerun-real-tta-blueprint.png');
const realSelection = path.join(out, 'rerun-real-tta-after-ruler-drag.png');

async function ready(page) {
  await page.waitForFunction(() => window.__runView && window.__runView.ready, null, { timeout: 90000 });
  await page.waitForTimeout(700);
}
async function at(page, t) {
  await page.evaluate((time) => { const p = TrajCompare.state.pages[0]; p.transport.pause(); p.transport.setScrub(time); }, t);
  await page.waitForTimeout(600);
}
// two stills one over the other, each with a caption bar, shot as one page (the composite is made of real captures)
async function stack(browser, items, file, crop) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const cells = items.map((item) => {
    const data = fs.readFileSync(item.png).toString('base64');
    const style = crop ? `height:${crop.height}px;object-fit:none;object-position:0 -${crop.top}px` : '';
    return `<figure><figcaption>${item.label}</figcaption><img src="data:image/png;base64,${data}" style="width:1440px;display:block;${style}"></figure>`;
  }).join('');
  await page.setContent(`<!doctype html><html><head><style>
    body{margin:0;background:#f4f4f2;font:13px/1.4 -apple-system,'Segoe UI',Roboto,sans-serif;color:#22211f}
    figure{margin:0;border-bottom:3px solid #22211f} figcaption{padding:7px 14px;background:#22211f;color:#f1f1f1;font-weight:600}
  </style></head><body>${cells}</body></html>`);
  await page.waitForTimeout(300);
  await page.screenshot({ path: file, fullPage: true });
  await context.close();
}

(async () => {
  if (!fs.existsSync(realBlueprint) || !fs.existsSync(realSelection)) {
    // the real Rerun captures: write the recording (dry) the same way the button does, then shoot it in Rerun 0.40
    const answer = JSON.parse(execFileSync('curl', ['-s', '-X', 'POST', '-H', 'Content-Type: application/json', '-d',
      JSON.stringify({ fixture: 'tta', keep: ['p5s-pass3', 'p6s'], t: 3.51, tab: 'track' }), `http://127.0.0.1:${port}/__rerun/open?dry=1`]).toString());
    execFileSync('node', [path.join(__dirname, 'rerun-real.cjs'), answer.rrd, path.join(out, 'rerun-real-tta.png'), '--t', '3.51', '--steps',
      JSON.stringify([{ click: [1360, 18], shot: 'blueprint', wait: 2500 }, { click: [1360, 18], wait: 1500 },
        { drag: [600, 722, 900, 722], shot: 'after-ruler-drag' }])], { stdio: 'inherit' });
  }
  const browser = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    await page.goto(url);
    await ready(page);
    await at(page, 3.51);
    const mine = path.join(out, 'extra-page-tta.png');
    await page.screenshot({ path: mine });

    // the help popup of the first chart of the open tab
    const q = await page.evaluate(() => {
      const button = Array.prototype.filter.call(document.querySelectorAll('.tc-plotcard .r4-q'), (b) => b.offsetParent)[0];
      const r = button.getBoundingClientRect();
      return [r.left + r.width / 2, r.top + r.height / 2];
    });
    await page.mouse.move(q[0], q[1], { steps: 4 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(out, 'extra-help.png') });
    await page.mouse.move(700, 880);
    await page.waitForTimeout(400);

    // the time panel: select 2.0 to 3.0 s on the time scale, then a right-drag zoom band held mid-gesture on a chart
    const ruler = await page.evaluate(() => document.querySelector('.r4-ruler').getBoundingClientRect().toJSON());
    const tr = await page.evaluate(() => { const p = TrajCompare.state.pages[0]; return [p.transport.tMin, p.transport.tMax]; });
    const xOf = (t) => ruler.left + (t - tr[0]) / (tr[1] - tr[0]) * ruler.width;
    await page.mouse.move(xOf(2.0), ruler.top + ruler.height / 2);
    await page.mouse.down();
    await page.mouse.move(xOf(3.0), ruler.top + ruler.height / 2, { steps: 10 });
    await page.mouse.up();
    await page.mouse.move(xOf(2.5), ruler.top + 60);  // hover the selection: its start / stop / length, as Rerun shows it
    await page.waitForTimeout(300);
    const chart = await page.evaluate(() => {
      const c = window.__runView.charts().filter((x) => x.shown && x.box)[0];
      return c.box;
    });
    const tipShown = await page.evaluate(() => getComputedStyle(document.querySelector('.r4-tsel-tip')).display);
    if (tipShown !== 'block') console.warn('selection tip not shown');
    await page.mouse.move(chart.left + chart.width * 0.35, chart.top + chart.height * 0.5);
    await page.mouse.down({ button: 'right' });
    await page.mouse.move(chart.left + chart.width * 0.62, chart.top + chart.height * 0.5, { steps: 10 });
    await page.waitForTimeout(300);
    const selection = path.join(out, 'extra-page-selection.png');
    await page.screenshot({ path: selection });
    await page.mouse.up({ button: 'right' });
    await context.close();

    await stack(browser, [
      { png: mine, label: 'This page (R4): tta, p5s-pass3 + p6s, t = 3.51 s, “Did it track the target?”' },
      { png: realBlueprint, label: 'The real Rerun 0.40 viewer: the recording “Open the same in Rerun” writes for the same runs, tab and time (blueprint panel opened)' },
    ], path.join(out, 'extra-beside-rerun.png'));
    await stack(browser, [
      { png: selection, label: 'This page: a time segment dragged on the time scale (2.0–3.0 s; the loop button turns on) · a right-drag zoom band held on a chart' },
      { png: realSelection, label: 'Real Rerun 0.40: a time segment dragged on its time scale (the loop button turns on)' },
    ], path.join(out, 'extra-time-panel.png'), { top: 430, height: 470 });
    for (const f of ['extra-page-tta.png', 'extra-page-selection.png']) fs.rmSync(path.join(out, f), { force: true });
    console.log(['extra-beside-rerun.png', 'extra-help.png', 'extra-time-panel.png'].map((f) => path.join(out, f)).join('\n'));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });
