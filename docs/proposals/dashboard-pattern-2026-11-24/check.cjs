#!/usr/bin/env node
// Acceptance for one dashboard-pattern proposal (babble round 2026-11-24, "filter rail + tabbed dashboards in data-ui").
// Written by the dispatcher BEFORE the lanes were dispatched; lanes may read and run it, never edit it.
//
//   node check.cjs p3 --port 8833                gates only
//   node check.cjs p3 --port 8833 --shots shots  gates + story stills (+ the embed still) + session.webm under shots/p3/
//
// Pages: http://127.0.0.1:<port>/<p>/index.html and /<p>/embed.html, served by traj_compare.serve over this folder.
// POST /__rerun/open is intercepted (answered {ok: true}), so a check never opens a Rerun window.

const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const variant = args[0];
const port = Number(args[args.indexOf('--port') + 1] || 8830);
const shotsRoot = args.includes('--shots') ? path.resolve(args[args.indexOf('--shots') + 1]) : null;
const here = __dirname;
const gates = JSON.parse(fs.readFileSync(path.join(here, variant, 'gates.json'), 'utf8'));
const storyFile = path.join(here, variant, 'story.json');
const story = fs.existsSync(storyFile) ? JSON.parse(fs.readFileSync(storyFile, 'utf8')) : [];
const datasets = JSON.parse(fs.readFileSync(path.join(here, 'data', 'datasets.json'), 'utf8'));
const base = `http://127.0.0.1:${port}/${variant}`;
const results = [];
const pass = (gate, ok, detail) => results.push({ gate, ok: !!ok, detail });
const fill = (template, key, value) => template.split(`{${key}}`).join(value);

async function visible(page, selector) {
  if (!selector) return false;
  for (const h of await page.$$(selector)) if (await h.isVisible()) return true;
  return false;
}
async function count(page) {
  const text = await page.$eval(gates.count, (el) => el.textContent);
  const m = /\d[\d,  ]*/.exec(text);
  return m ? Number(m[0].replace(/[,  ]/g, '')) : NaN;
}
async function tab(page, id) {
  if (!gates.tabs[id]) throw new Error(`gates.json has no tabs.${id}`);
  await page.click(gates.tabs[id]);
  await page.waitForTimeout(800);
}
async function pick(page, template, key, value) {
  await page.click(fill(template, key, value));
  await page.waitForTimeout(900);
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
async function fresh(page, url) {
  await page.evaluate(() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) { /* blocked */ } });
  await page.goto(url, { waitUntil: 'load' });
  if (gates.ready) await page.waitForSelector(gates.ready, { timeout: 30000 });
  await page.waitForTimeout(1500);
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true });
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
  await page.goto(`${base}/index.html`, { waitUntil: 'load' });
  if (gates.ready) await page.waitForSelector(gates.ready, { timeout: 30000 });
  await page.waitForTimeout(1500);

  const [alone, cell, conveyor] = [datasets[0], datasets[1], datasets[2]];
  // P1 dataset first, and ticking one dataset leaves exactly its trajectories
  try {
    await tab(page, 'overview');
    const total = await count(page);
    const firstIsDataset = await page.evaluate(([first, group]) => {
      const a = document.querySelector(first), b = document.querySelector(group);
      return !!(a && b && (a === b || a.contains(b) || b.contains(a)));
    }, [gates.first_group, gates.dataset_group]);
    const listed = [];
    for (const d of datasets) listed.push(await visible(page, fill(gates.dataset_option, 'label', d.dataset)));
    const before = await shot(page, gates.figure);
    await pick(page, gates.dataset_option, 'label', conveyor.dataset);
    const one = await count(page);
    const after = await shot(page, gates.figure);
    pass('P1 dataset first; one dataset leaves its trajectories; a figure repaints',
      firstIsDataset && listed.every(Boolean) && total === 212 && one === conveyor.trajectories && before && after && before !== after,
      { firstIsDataset, listed, total, one, expected: conveyor.trajectories, repainted: !!(before && after && before !== after) });
  } catch (e) { pass('P1 dataset first; one dataset leaves its trajectories; a figure repaints', false, String(e)); }

  // P2 split applies across the datasets ticked
  let filtered = NaN;
  try {
    await pick(page, gates.dataset_option, 'label', alone.dataset);
    const two = await count(page);
    await pick(page, gates.split_option, 'split', 'holdout');
    filtered = await count(page);
    const expected = conveyor.holdout + alone.holdout;
    pass('P2 split applies across the datasets ticked', two === conveyor.trajectories + alone.trajectories && filtered === expected,
      { two, expectedTwo: conveyor.trajectories + alone.trajectories, holdout: filtered, expected });
  } catch (e) { pass('P2 split applies across the datasets ticked', false, String(e)); }

  // P3 dashboards switch like tabs and keep the filter
  try {
    const seen = {};
    for (const id of Object.keys(gates.tabs)) { await tab(page, id); seen[id] = await count(page); }
    const kept = Object.values(seen).every((n) => n === filtered);
    pass('P3 ≥ 4 dashboards switch like tabs and keep the filter', Object.keys(gates.tabs).length >= 4 && kept, { counts: seen, filtered });
  } catch (e) { pass('P3 ≥ 4 dashboards switch like tabs and keep the filter', false, String(e)); }

  // P5 joint picker scoped; colours behind a gear inside the component
  try {
    await tab(page, 'joint');
    const onJoint = await visible(page, gates.joint_picker);
    await tab(page, 'overview');
    const onOverview = await visible(page, gates.joint_picker);
    await tab(page, 'joint');
    const before = await shot(page, gates.joint_figure);
    const hiddenAtFirst = !(await visible(page, gates.cmap));
    await page.click(gates.settings);
    await page.waitForTimeout(400);
    const tag = await page.$eval(gates.cmap, (el) => el.tagName);
    if (tag === 'SELECT') await page.selectOption(gates.cmap, gates.cmap_value || 'magma'); else await page.click(gates.cmap_option);
    await page.waitForTimeout(900);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const after = await shot(page, gates.joint_figure);
    pass('P5 joint picker on its dashboard only; colours behind a gear, repainting',
      onJoint && !onOverview && hiddenAtFirst && before && after && before !== after,
      { onJoint, onOverview, hiddenAtFirst, repainted: !!(before && after && before !== after) });
  } catch (e) { pass('P5 joint picker on its dashboard only; colours behind a gear, repainting', false, String(e)); }

  // P6 drill + Open in Rerun
  try {
    await tab(page, 'trajectories');
    if (gates.drill_action === 'dblclick') await page.dblclick(gates.drill_trigger); else await page.click(gates.drill_trigger);
    await page.waitForTimeout(900);
    const drill = await visible(page, gates.drill);
    const text = drill ? await page.$eval(gates.drill, (el) => el.textContent) : '';
    const named = /(workspace|conveyor|impact)-(dev|holdout)-\d{3}/.exec(text);
    await page.click(gates.open_rerun);
    await page.waitForTimeout(600);
    const call = rerunCalls[rerunCalls.length - 1] || '';
    const rrd = decodeURIComponent((/rrd=([^&]+)/.exec(call) || [])[1] || '');
    const exists = rrd && fs.existsSync(path.join(here, rrd));
    pass('P6 drill + Open in Rerun', drill && named && exists && rrd.includes(named[0]), { drill, trajectory: named && named[0], rrd, rrdExists: !!exists });
  } catch (e) { pass('P6 drill + Open in Rerun', false, String(e)); }

  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

  // P4 the same component inside a host app's 1000 x 680 slot draws nothing outside it
  try {
    const embedPage = await context.newPage();
    embedPage.on('pageerror', (e) => errors.push('embed pageerror: ' + String(e)));
    embedPage.on('console', (m) => { if (m.type() === 'error' && !/favicon/.test(m.text())) errors.push('embed console: ' + m.text()); });
    await embedPage.goto(`${base}/embed.html`, { waitUntil: 'load' });
    await embedPage.waitForSelector(gates.embed_root, { timeout: 30000 });
    await embedPage.waitForTimeout(1500);
    const probe = async () => embedPage.evaluate((rootSel) => {
      const slot = document.querySelector('#host-slot').getBoundingClientRect();
      const root = document.querySelector(rootSel);
      const header = document.querySelector('#host-header').getBoundingClientRect();
      const outside = [];
      const inSlot = (r) => r.left >= slot.left - 1 && r.top >= slot.top - 1 && r.right <= slot.right + 1 && r.bottom <= slot.bottom + 1;
      const walk = (el) => {
        for (const child of el.children) {
          const cs = getComputedStyle(child);
          if (cs.display === 'none' || cs.visibility === 'hidden') continue;
          const r = child.getBoundingClientRect();
          if (r.width > 0 && r.height > 0 && (cs.position === 'fixed' || cs.position === 'absolute') && !inSlot(r)) outside.push(`${child.tagName.toLowerCase()}.${String(child.className).slice(0, 40)}`);
          walk(child);
          if (child.shadowRoot) walk(child.shadowRoot);
        }
      };
      // escapes the slot would hide: body-level popovers or fixed layers the component appended outside the slot
      const strays = [...document.body.children].filter((el) => !['host-header', 'host-main'].includes(el.id) && el.tagName !== 'SCRIPT' && el.tagName !== 'STYLE')
        .filter((el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !inSlot(r); }).map((el) => el.tagName.toLowerCase() + '#' + el.id);
      if (root) walk(root);
      const r = root ? root.getBoundingClientRect() : null;
      return { rootInSlot: !!(r && inSlot(r)), outside: outside.slice(0, 6), strays, headerVisible: header.height > 0 && header.top >= 0,
        pageScrollX: document.documentElement.scrollWidth - window.innerWidth };
    }, gates.embed_root);
    const atLoad = await probe();
    // open the gear inside the embed too: its popover must stay in the slot
    let gear = null;
    if (await embedPage.$(gates.settings)) { await embedPage.click(gates.settings); await embedPage.waitForTimeout(500); gear = await probe(); await embedPage.keyboard.press('Escape'); }
    if (shotsRoot) { fs.mkdirSync(path.join(shotsRoot, variant), { recursive: true }); await embedPage.screenshot({ path: path.join(shotsRoot, variant, 'embed.png') }); }
    const ok = (p) => p && p.rootInSlot && p.outside.length === 0 && p.strays.length === 0 && p.headerVisible && p.pageScrollX <= 1;
    pass('P4 drops into a host app: nothing outside the 1000 × 680 slot', ok(atLoad) && (gear === null || ok(gear)), { atLoad, gearOpen: gear });
    await embedPage.close();
  } catch (e) { pass('P4 drops into a host app: nothing outside the 1000 × 680 slot', false, String(e)); }

  if (shotsRoot && story.length) {
    const out = path.join(shotsRoot, variant);
    fs.mkdirSync(out, { recursive: true });
    await fresh(page, `${base}/index.html`);
    for (let k = 0; k < story.length; k += 1) {
      const step = story[k];
      for (const a of step.actions || []) await act(page, a);
      await page.waitForTimeout(step.settle || 900);
      let box = null;
      if (step.highlight) { const h = await page.$(step.highlight); if (h && await h.isVisible()) box = await h.boundingBox(); }
      await page.screenshot({ path: path.join(out, `step-${k + 1}.png`) });
      step.box = box;
    }
    fs.writeFileSync(path.join(out, 'story.shot.json'), JSON.stringify(story, null, 2));
  }
  pass('P7 no errors; no sideways scroll at 1440', errors.length === 0 && wide <= 1, { errors: errors.slice(0, 8), overflowPx: wide });

  await context.close();
  await browser.close();
  if (videoDir) {
    const webm = fs.readdirSync(videoDir).filter((f) => f.endsWith('.webm')).map((f) => path.join(videoDir, f));
    // WHY the largest: the embed page records its own short video; the index page's walk is the long one
    webm.sort((a, b) => fs.statSync(b).size - fs.statSync(a).size);
    if (webm.length) fs.renameSync(webm[0], path.join(shotsRoot, variant, 'session.webm'));
  }
  const failed = results.filter((r) => !r.ok);
  console.log(JSON.stringify({ variant, passed: results.length - failed.length, of: results.length, results }, null, 2));
  process.exit(failed.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
