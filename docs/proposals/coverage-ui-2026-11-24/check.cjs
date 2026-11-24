#!/usr/bin/env node
// Acceptance for one coverage-UI proposal (babble round 2026-11-24). Written by the dispatcher BEFORE the lanes were
// dispatched; the lanes may read and run it, never edit it. It checks Zach's Nov 24 feedback as hard gates and plays
// the variant's walkthrough, saving one still per step (and a video of the whole walk) for the gallery.
//
//   node check.cjs v4 --port 8804                  gates only
//   node check.cjs v4 --port 8804 --shots shots    gates + story stills + story.webm under shots/v4/
//
// The page is http://127.0.0.1:<port>/<variant>/index.html, served by
//   /home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port <port>
// The variant's gates.json names its selectors (see CONTRACT.md "Gates"); story.json its walkthrough steps.
// POST /__rerun/open is intercepted here and answered {ok: true}, so a check never opens a Rerun window.

const fs = require('fs');
const path = require('path');
const PLAYWRIGHT = process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright';
const CHROME = '/usr/bin/google-chrome';
const { chromium } = require(PLAYWRIGHT);

const args = process.argv.slice(2);
const variant = args[0];
const port = Number(args[args.indexOf('--port') + 1] || 8800);
const shotsRoot = args.includes('--shots') ? path.resolve(args[args.indexOf('--shots') + 1]) : null;
const here = __dirname;
const gates = JSON.parse(fs.readFileSync(path.join(here, variant, 'gates.json'), 'utf8'));
const storyFile = path.join(here, variant, 'story.json');
const story = fs.existsSync(storyFile) ? JSON.parse(fs.readFileSync(storyFile, 'utf8')) : [];
const url = `http://127.0.0.1:${port}/${variant}/index.html`;
const results = [];
const pass = (gate, ok, detail) => results.push({ gate, ok: !!ok, detail });

async function visible(page, selector) {
  if (!selector) return false;
  const handles = await page.$$(selector);
  for (const h of handles) if (await h.isVisible()) return true;
  return false;
}
async function count(page, selector) {
  let n = 0;
  for (const h of await page.$$(selector)) if (await h.isVisible()) n += 1;
  return n;
}
async function tab(page, id) {
  const selector = gates.tabs && gates.tabs[id];
  if (!selector) throw new Error(`gates.json has no tabs.${id}`);
  await page.click(selector);
  await page.waitForTimeout(700);
}
async function shot(page, selector) {
  const el = await page.$(selector);
  if (!el) return null;
  await el.scrollIntoViewIfNeeded();
  return (await el.screenshot()).toString('base64');
}
async function act(page, a) {
  if (a.click) await page.click(a.click);
  if (a.dblclick) await page.dblclick(a.dblclick);
  if (a.hover) await page.hover(a.hover);
  if (a.fill) await page.fill(a.fill[0], a.fill[1]);
  if (a.select) await page.selectOption(a.select[0], a.select[1]);
  if (a.press) await page.keyboard.press(a.press);
  if (a.scroll) await page.evaluate((s) => { const el = document.querySelector(s); if (el) el.scrollIntoView({ block: 'start' }); }, a.scroll);
  if (a.wait) await page.waitForTimeout(a.wait);
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const contextOptions = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 };
  const videoDir = shotsRoot ? path.join(shotsRoot, variant, 'video') : null;
  if (videoDir) { fs.mkdirSync(videoDir, { recursive: true }); contextOptions.recordVideo = { dir: videoDir, size: { width: 1440, height: 900 } }; }
  const context = await browser.newContext(contextOptions);
  const rerunCalls = [];
  await context.route('**/__rerun/open**', (route) => {
    rerunCalls.push(route.request().url());
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, command: 'intercepted by check.cjs' }) });
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon/.test(m.text())) errors.push('console: ' + m.text()); });
  page.on('response', (r) => { if (r.status() >= 400 && !/favicon/.test(r.url())) errors.push(`${r.status()} ${r.url()}`); });
  await page.goto(url, { waitUntil: 'load' });
  if (gates.ready) await page.waitForSelector(gates.ready, { timeout: 20000 });
  await page.waitForTimeout(1200);

  // G1 headline numbers: on the overview, nowhere else
  try {
    await tab(page, 'overview');
    const onOverview = await visible(page, gates.stats);
    await tab(page, 'trajectories');
    const onTable = await visible(page, gates.stats);
    await tab(page, 'joint');
    const onJoint = await visible(page, gates.stats);
    pass('G1 headline numbers only on the overview', onOverview && !onTable && !onJoint, { onOverview, onTable, onJoint });
  } catch (e) { pass('G1 headline numbers only on the overview', false, String(e)); }

  // G4a the joint picker shows where it applies, not elsewhere
  try {
    await tab(page, 'joint');
    const onJoint = await visible(page, gates.joint_picker);
    await tab(page, 'overview');
    const onOverview = await visible(page, gates.joint_picker);
    await tab(page, 'trajectories');
    const onTable = await visible(page, gates.joint_picker);
    pass('G4a joint picker only where it applies', onJoint && !onOverview && !onTable, { onJoint, onOverview, onTable });
  } catch (e) { pass('G4a joint picker only where it applies', false, String(e)); }

  // G4b global settings live behind one gear, and changing the colormap repaints a figure
  try {
    await tab(page, 'joint');
    const before = await shot(page, gates.figure);
    const hiddenAtFirst = !(await visible(page, gates.cmap));
    await page.click(gates.settings);
    await page.waitForTimeout(400);
    const panel = await visible(page, gates.settings_panel);
    const controls = (await visible(page, gates.cmap)) && (await visible(page, gates.reverse)) && (await visible(page, gates.scale));
    const tag = await page.$eval(gates.cmap, (el) => el.tagName);
    if (tag === 'SELECT') await page.selectOption(gates.cmap, gates.cmap_value || 'magma');
    else await page.click(gates.cmap_option);
    await page.waitForTimeout(900);
    if (gates.settings_close) { await page.click(gates.settings_close); await page.waitForTimeout(300); }
    else { await page.keyboard.press('Escape'); await page.waitForTimeout(300); }
    const after = await shot(page, gates.figure);
    pass('G4b colours set once behind a gear, and they repaint', hiddenAtFirst && panel && controls && before && after && before !== after,
      { hiddenAtFirst, panel, controls, repainted: !!(before && after && before !== after) });
  } catch (e) { pass('G4b colours set once behind a gear, and they repaint', false, String(e)); }

  // G2 the trajectories table filters, sorts and keeps saved views
  try {
    await tab(page, 'trajectories');
    const all = await count(page, gates.table_rows);
    await page.fill(gates.filter, gates.filter_query || 'holdout');
    await page.waitForTimeout(700);
    const filtered = await count(page, gates.table_rows);
    await page.fill(gates.filter, '');
    await page.waitForTimeout(500);
    const firstBefore = await page.$eval(gates.table_rows, (el) => el.textContent.trim().slice(0, 80));
    await page.click(gates.sort_header);
    await page.waitForTimeout(500);
    const firstAfter = await page.$eval(gates.table_rows, (el) => el.textContent.trim().slice(0, 80));
    const views = await count(page, gates.saved_view_items);
    pass('G2 table filters, sorts, has saved views', all > 0 && filtered > 0 && filtered < all && firstBefore !== firstAfter && views >= 2,
      { all, filtered, sorted: firstBefore !== firstAfter, savedViews: views });
  } catch (e) { pass('G2 table filters, sorts, has saved views', false, String(e)); }

  // G3 every colour beside a trajectory is explained (or there is none)
  try {
    if (gates.row_colours === 'none') {
      pass('G3 row colours explained', true, 'the variant draws no colour beside a trajectory');
    } else {
      await tab(page, 'trajectories');
      const legend = await visible(page, gates.row_colours.legend);
      pass('G3 row colours explained', legend, { legend });
    }
  } catch (e) { pass('G3 row colours explained', false, String(e)); }

  // G2b drill into one trajectory, and open it in Rerun
  try {
    await tab(page, 'trajectories');
    await page.fill(gates.filter, '');
    await page.waitForTimeout(300);
    if (gates.drill_action === 'dblclick') await page.dblclick(gates.drill_trigger); else await page.click(gates.drill_trigger);
    await page.waitForTimeout(900);
    const drill = await visible(page, gates.drill);
    const drillText = drill ? await page.$eval(gates.drill, (el) => el.textContent) : '';
    const named = /workspace-(dev|holdout)-\d{3}/.exec(drillText);
    await page.click(gates.open_rerun);
    await page.waitForTimeout(600);
    const call = rerunCalls[rerunCalls.length - 1] || '';
    const rrd = decodeURIComponent((/rrd=([^&]+)/.exec(call) || [])[1] || '');
    const exists = rrd && fs.existsSync(path.join(here, rrd));
    pass('G2b drill in + Open in Rerun', drill && named && exists && rrd.includes(named[0]),
      { drill, trajectory: named && named[0], rrd, rrdExists: !!exists });
  } catch (e) { pass('G2b drill in + Open in Rerun', false, String(e)); }

  // G6 fits 1440 wide (no sideways page scroll), and nothing threw
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  pass('G6 no sideways scroll at 1440', wide <= 1, { overflowPx: wide });

  // the walkthrough: fresh page, one still per step
  if (shotsRoot && story.length) {
    const out = path.join(shotsRoot, variant);
    fs.mkdirSync(out, { recursive: true });
    await page.goto(url, { waitUntil: 'load' });
    if (gates.ready) await page.waitForSelector(gates.ready, { timeout: 20000 });
    await page.waitForTimeout(1200);
    for (let k = 0; k < story.length; k += 1) {
      const step = story[k];
      for (const a of step.actions || []) await act(page, a);
      await page.waitForTimeout(step.settle || 900);
      let box = null;
      if (step.highlight) {
        const h = await page.$(step.highlight);
        if (h && await h.isVisible()) box = await h.boundingBox();
      }
      await page.screenshot({ path: path.join(out, `step-${k + 1}.png`) });
      step.box = box;
    }
    fs.writeFileSync(path.join(out, 'story.shot.json'), JSON.stringify(story, null, 2));
  }
  pass('G5 no console or page errors', errors.length === 0, errors.slice(0, 8));

  await context.close();
  await browser.close();
  if (videoDir) {
    const webm = fs.readdirSync(videoDir).filter((f) => f.endsWith('.webm')).map((f) => path.join(videoDir, f));
    if (webm.length) fs.renameSync(webm[webm.length - 1], path.join(shotsRoot, variant, 'session.webm'));
  }
  const failed = results.filter((r) => !r.ok);
  console.log(JSON.stringify({ variant, url, passed: results.length - failed.length, of: results.length, results }, null, 2));
  process.exit(failed.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
