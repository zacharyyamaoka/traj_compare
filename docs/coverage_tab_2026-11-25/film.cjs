#!/usr/bin/env node
// Coverage inside the runs workbench on the REAL bench (feedback fb-5defddb0; docs/RUNS_WORKBENCH.md "Coverage, one tab
// away"), headless Chrome at 1440 x 900: the Coverage tab (each deployment's own coverage page embedded, its cards) ->
// pick another deployment's card -> tick a deployment in the rail (the cards recount, the tab follows) -> Targets -> open a
// target view -> its "Coverage ↗" -> the coverage page with that target's trajectory highlighted. Stills, a session
// video and film.json (every number the stills show, read from the pages) into --out.
//
//   node film.cjs --base http://127.0.0.1:8861 --out /home/bam/traj_compare/reports/media/coverage-tab-2026-11-25 \
//        --deployment "UR5e + Conveyor PnP cell"
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const base = opt('--base', 'http://127.0.0.1:8861');
const out = opt('--out', path.resolve('film'));
const deployment = opt('--deployment', 'UR5e + Conveyor PnP cell');
fs.mkdirSync(out, { recursive: true });
const R = { base, deployment, errors: [], steps: {}, timings: {} };

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true,
    args: ['--no-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 },
    recordVideo: { dir: path.join(out, 'video-raw'), size: { width: 1440, height: 900 } } });
  const page = await context.newPage();
  page.on('pageerror', (e) => R.errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) R.errors.push(m.text()); });
  page.on('response', (r) => { if (r.status() >= 400 && !/favicon/.test(r.url())) R.errors.push(r.status() + ' ' + r.url()); });
  const t0 = Date.now();
  const mark = (name) => { R.timings[name] = (Date.now() - t0) / 1000; };
  const ready = async (timeout = 180000) => { await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout }); await page.waitForTimeout(600); };
  const shot = (name) => page.screenshot({ path: path.join(out, name + '.png') });
  const tick = async (prop, value) => { await page.click(`#tc data-facets input[type=checkbox][data-p="${prop}"][data-value="${value}"]`); await page.waitForTimeout(1800); };
  const view = () => page.evaluate(() => { const el = document.querySelector("#tc [data-tc-view='tc-coverage']"); return el ? { ...el.tcOverview, answer: (el.querySelector('[data-tc-answer]') || {}).textContent } : null; });
  const framed = async () => {
    const handle = await page.$("#tc [data-tc-view='tc-coverage'] iframe[data-tc-coverage-frame]");
    const frame = await handle.contentFrame();
    await frame.waitForSelector('[data-cov-page]', { timeout: 60000 });
    await frame.waitForTimeout(1500);
    return frame.evaluate(() => ({ url: location.pathname, title: (document.querySelector('[data-cov-title]') || {}).textContent }));
  };

  await page.goto(base + '/all/index.html'); await ready(); mark('outer ready');
  await page.click("#tc data-tabs [role=tab]:text-is('Coverage')"); await page.waitForTimeout(1500);
  R.steps.tab = { view: await view(), frame: await framed() }; mark('coverage tab');
  await shot('01-coverage-tab');
  // scroll the dashboard so the embedded page fills the screen, then back
  await page.mouse.move(800, 300); await page.mouse.wheel(0, 380); await page.waitForTimeout(1600);
  await shot('02-embedded-page');
  await page.mouse.wheel(0, -380); await page.waitForTimeout(800);
  // another deployment's card
  const cards = await page.$$("#tc [data-tc-view='tc-coverage'] [data-tc-coverage-pick]");
  if (cards.length > 1) {
    await cards[cards.length - 1].click(); await page.waitForTimeout(1000);
    R.steps.picked = { view: await view(), frame: await framed() }; mark('card picked');
    await shot('03-other-card');
  }
  // tick a deployment in the rail: the cards recount and the tab follows the rail
  await tick('deployment', deployment);
  R.steps.ticked = { view: await view(), frame: await framed() }; mark('rail ticked');
  await shot('04-rail-ticked');
  // one target -> its target view -> Coverage ↗
  await page.click("#tc data-tabs [role=tab]:text-is('Targets')"); await page.waitForTimeout(2000);
  await page.click("#tc data-dashboard[tab='Targets'] tbody tr"); await page.waitForTimeout(1200);
  await Promise.all([page.waitForNavigation(), page.click("#tc button[data-drill-action]:has-text('Open target view')")]);
  await ready(); mark('target view');
  R.steps.target = await page.evaluate(() => { const a = document.querySelector('a[data-tc-coverage-link]'); return { title: document.getElementById('title').textContent, href: a && !a.hidden ? a.getAttribute('href') : null }; });
  await page.hover('a[data-tc-coverage-link]'); await page.waitForTimeout(700);
  await shot('05-target-view');
  await Promise.all([page.waitForNavigation(), page.click('a[data-tc-coverage-link]')]);
  await page.waitForSelector('[data-cov-page]', { timeout: 60000 }); await page.waitForTimeout(1800); mark('coverage page');
  R.steps.page = await page.evaluate(() => ({
    url: location.pathname,
    tab: [...document.querySelectorAll('[data-cov-view]')].filter((s) => !s.hidden).map((s) => s.dataset.covView),
    selected: [...document.querySelectorAll('[data-cov-view="trajectories"] tr.selected')].map((tr) => tr.textContent.replace(/\s+/g, ' ').trim()),
    chip: (document.querySelector('.cov-highlight') || {}).textContent,
  }));
  const row = await page.$('[data-cov-view="trajectories"] tr.selected');
  if (row) { await row.scrollIntoViewIfNeeded(); await page.waitForTimeout(1000); }
  await shot('06-highlighted');
  // the same trajectory in black on the One joint paths
  await page.click('[data-cov-tab="joint"]'); await page.waitForTimeout(2500);
  const spaghetti = await page.$('[data-cov-figure="spaghetti"]');
  if (spaghetti) { await spaghetti.scrollIntoViewIfNeeded(); await page.waitForTimeout(1500); }
  await shot('07-one-joint-path'); mark('end');
  await context.close();
  await browser.close();
  const raw = fs.readdirSync(path.join(out, 'video-raw')).filter((f) => f.endsWith('.webm')).map((f) => path.join(out, 'video-raw', f));
  R.video = raw[raw.length - 1] || null;
  fs.writeFileSync(path.join(out, 'film.json'), JSON.stringify(R, null, 1));
  console.log(JSON.stringify({ errors: R.errors, timings: R.timings, video: R.video }));
})().catch((error) => { console.log(JSON.stringify({ fatal: String(error && error.stack || error), R })); process.exit(1); });
