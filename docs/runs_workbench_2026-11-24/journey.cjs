#!/usr/bin/env node
// The runs workbench's three levels on the REAL bench (traj_compare.runs_workbench, docs/RUNS_WORKBENCH.md), headless
// Chrome at 1440 x 900: filter one deployment and one config -> the count recounts -> open a target (summary, the rail's
// runs ticked) -> back keeps the filter and the tab -> open it again, tick exactly 3 runs -> Open playback (traj_compare's
// comparison viewer over those 3 and the target) -> its breadcrumb back -> Open in Rerun (rewritten to ?dry=1: built,
// never launched) -> 3 lines. Stills, a session video and journey.json into --out.
//
//   node journey.cjs --base http://127.0.0.1:8854 --out /home/bam/traj_compare/reports/media/v2-production-2026-11-24 \
//        --deployment "UR5e + Conveyor PnP cell" --config ctc_tuned
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const base = opt('--base', 'http://127.0.0.1:8854');
const out = opt('--out', path.resolve('journey'));
const deployment = opt('--deployment', 'UR5e + Conveyor PnP cell');
const config = opt('--config', 'ctc_tuned');
fs.mkdirSync(out, { recursive: true });
const R = { base, deployment, config, errors: [], steps: {}, timings: {} };

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true,
    args: ['--no-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 },
    recordVideo: { dir: path.join(out, 'video-raw'), size: { width: 1440, height: 900 } } });
  await context.route('**/__rerun/**', (route) => { const u = route.request().url(); route.continue({ url: u + (u.includes('?') ? '&' : '?') + 'dry=1' }); });
  const page = await context.newPage();
  page.on('pageerror', (e) => R.errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon/.test(m.text())) R.errors.push(m.text()); });
  const t0 = Date.now();
  const mark = (name) => { R.timings[name] = (Date.now() - t0) / 1000; };
  const ready = async (timeout = 120000) => { await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout }); await page.waitForTimeout(600); };
  const count = () => page.evaluate(() => { const e = document.querySelector('#tc data-count'); return e ? e.textContent.trim().replace(/\s+/g, ' ') : null; });
  const shot = (name) => page.screenshot({ path: path.join(out, name + '.png') });
  const tick = async (prop, value) => { await page.click(`#tc data-facets input[type=checkbox][data-p="${prop}"][data-value="${value}"]`); await page.waitForTimeout(1500); };
  const targetView = () => page.evaluate(() => ({ url: location.href, title: document.getElementById('title').textContent,
    lines: [...document.querySelectorAll('[data-tc-run]')].map((r) => ({ line: r.dataset.line, config: r.dataset.config, ticked: r.querySelector('input').checked })) }));
  const openFirstTarget = async () => {
    // by its name: since 2026-11-25 the Overview's own pages (League, …) come before Targets
    await page.click("#tc data-tabs [role=tab]:text-is('Targets')"); await page.waitForTimeout(2000);
    await page.click("#tc data-dashboard[tab='Targets'] tbody tr"); await page.waitForTimeout(1200);
    await Promise.all([page.waitForNavigation(), page.click("#tc button[data-drill-action]:has-text('Open target view')")]);
    await ready();
  };

  await page.goto(base + '/all/index.html'); await ready(); mark('outer ready');
  R.steps.count0 = await count();
  await shot('01-outer');
  await tick('deployment', deployment); R.steps.count1 = await count();
  await tick('config', config); R.steps.count2 = await count();
  await shot('02-filtered');
  await openFirstTarget(); mark('target ready');
  R.steps.target = await targetView();
  await shot('03-target');
  await Promise.all([page.waitForNavigation(), page.click('#back')]); await ready(); mark('back ready');
  R.steps.back = { url: page.url(), count: await count(), tab: await page.evaluate(() => (document.querySelector('#tc data-tabs [aria-selected=true]') || {}).textContent) };
  await shot('04-back');
  await openFirstTarget();
  // exactly three ticked: keep the rail's, add others until three
  // (a tick redraws the run list, so each round looks the boxes up again)
  for (let round = 0; round < 10; round += 1) {
    const n = await page.evaluate(() => (window.TV_STATE || { selected: [] }).selected.length);
    if (n >= 3) break;
    const box = await page.$('[data-tc-run] input[type=checkbox]:not(:checked)');
    if (!box) break;
    await box.click(); await page.waitForTimeout(600);
  }
  R.steps.three = await page.evaluate(() => window.TV_STATE);
  R.steps.playbackLabel = (await page.textContent('#playback')).trim();
  await shot('05-three-ticked');
  mark('playback asked');
  await Promise.all([page.waitForNavigation({ timeout: 300000 }), page.click('#playback')]);
  await page.waitForFunction(() => window.TrajCompare && TrajCompare.state && TrajCompare.state.pages[0] && TrajCompare.state.pages[0].builtPage, null, { timeout: 120000 });
  await page.waitForTimeout(2500); mark('playback ready');
  R.steps.playback = await page.evaluate(() => {
    const data = JSON.parse(document.getElementById('traj-compare-data').textContent);
    const s = data.comparisons[0].situations;
    return { url: location.href, title: data.title, targets: s.filter((x) => x.role === 'target').length,
      measured: s.filter((x) => x.role !== 'target').map((x) => x.title), joints: data.comparisons[0].joint_names,
      crumbs: [...document.querySelectorAll('[data-tc-breadcrumb] a')].map((a) => [a.textContent, a.getAttribute('href')]) };
  });
  await shot('06-playback');
  const crumbs = await page.$$('[data-tc-breadcrumb] a');
  await Promise.all([page.waitForNavigation(), crumbs[crumbs.length - 1].click()]); await ready(); mark('returned');
  R.steps.returned = await page.evaluate(() => window.TV_STATE);
  await page.click('#rerun');
  await page.waitForFunction(() => window.TV_LAST_RERUN, null, { timeout: 300000 }); mark('rerun built');
  await page.waitForTimeout(800);
  R.steps.rerun = await page.evaluate(() => ({ answer: window.TV_LAST_RERUN, status: document.getElementById('status').textContent }));
  await shot('07-rerun');
  R.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  const video = page.video();
  await context.close();
  if (video) { const p = path.join(out, 'journey.webm'); fs.renameSync(await video.path(), p); R.video = p; }
  fs.rmSync(path.join(out, 'video-raw'), { recursive: true, force: true });
  await browser.close();
  fs.writeFileSync(path.join(out, 'journey.json'), JSON.stringify(R, null, 1));
  console.log(JSON.stringify(R));
})().catch((e) => { console.log(JSON.stringify({ fatal: String(e && e.stack || e), R })); process.exit(1); });
