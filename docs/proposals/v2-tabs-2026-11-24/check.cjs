#!/usr/bin/env node
// The round's acceptance + capture for one tab proposal, from its tN/gates.json (adapted from
// ../tensorboard-2026-11-24/check.cjs, V2's harness).
//   node check.cjs t1 --port 8852 [--video]
// Served by serve.py. Measures, headless Chrome 1440 × 900:
//   - the NEW tab's numbers unfiltered and after the scenario's one rail pick, each compared with data/oracle.json
//     (build_tabs.py, Python over the same rows: the independent oracle);
//   - the drill: a row of the new tab → the target view (keep=, back=, its selection, Open in Rerun ?dry=1);
//   - V2's own checks unchanged: count before / after one dataset tick, every tab (still + count + overflow), the rail
//     dragged 120 px and after a reload, the fold;
//   - a still of every story step (+ the session video with --video); console errors; sideways overflow.
// Writes shots/<t>/*.png and shots/<t>/check.json.
const fs = require('fs');
const path = require('path');
const { chromium } = require('/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const v = args[0];
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const port = Number(opt('--port', 8852));
const here = __dirname;
const gates = JSON.parse(fs.readFileSync(path.join(here, v, 'gates.json'), 'utf8'));
const oracle = JSON.parse(fs.readFileSync(path.join(here, 'data', 'oracle.json'), 'utf8'))[v];
const out = path.join(here, 'shots', v);
fs.mkdirSync(out, { recursive: true });
const url = `http://127.0.0.1:${port}/${v}/index.html?dry=1`;
const R = { variant: v, url, errors: [], checks: {} };

async function ready(page) {
  await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 60000 }).catch(() => R.errors.push('never ready'));
  await page.waitForTimeout(1200);
}
async function countText(page) {
  return page.evaluate(() => { const e = document.querySelector('#tc data-count'); return e ? e.textContent.trim().replace(/\s+/g, ' ') : null; });
}
async function act(page, a) {
  if (a.click) await page.click(a.click);
  if (a.dblclick) await page.dblclick(a.dblclick);
  if (a.select) await page.selectOption(a.select[0], a.select[1]);
  if (a.eval) await page.evaluate(a.eval);
  if (a.cell) await clickCell(page, a.cell);
  if (a.cellEval) await clickCell(page, await page.evaluate(a.cellEval));
  if (a.waitFor) await page.waitForFunction(a.waitFor, null, { timeout: 60000 }).catch(() => R.errors.push('timed out: ' + a.waitFor));
  await page.waitForTimeout(a.wait || 900);
}
// T2: click a cell of a coverage plane by its panel id and cell index (through the view's read-only hook)
async function clickCell(page, { panel, cell }) {
  const at = await page.evaluate(({ panel, cell }) => {
    const views = document.querySelector('#t2-planes data-views');
    const el = views && [...views.querySelectorAll('*')].find((e) => e.coverage && e.coverage.panels);
    const p = el && el.coverage.panels.find((x) => x.id === panel);
    if (!p) return null;
    p.canvas.scrollIntoView({ block: 'center' });
    const r = p.canvas.getBoundingClientRect();
    const i = Math.floor(cell / p.ny), j = cell % p.ny;
    return { x: r.left + p.box.x + (i + 0.5) * p.box.w / p.nx, y: r.top + p.box.y + (p.ny - 1 - j + 0.5) * p.box.h / p.ny };
  }, { panel, cell });
  if (!at) { R.errors.push(`no panel ${panel}`); return; }
  await page.mouse.click(at.x, at.y);
}
// the new tab's numbers: a .base page's answer chart (Vega's own aggregate), or T2's host state
async function numbers(page) {
  return page.evaluate((tab) => {
    if (window.T2_STATE && document.querySelector('.t2:not([hidden])')) return { kind: 't2', ...window.T2_STATE };
    const dash = document.querySelector(`#tc data-dashboard[tab="${tab}"]`);
    if (!dash) return null;
    for (const el of dash.querySelectorAll('*')) {
      if (!el.vegaView) continue;
      const view = el.vegaView;
      for (const name of Object.keys(view._runtime.data)) {
        let rows = null;
        try { rows = view.data(name); } catch { continue; }
        if (rows && rows.length && rows[0].answer !== undefined && rows[0].n !== undefined) {
          return { kind: 'answer', text: rows.map((r) => r.answer), ...rows[0] };
        }
      }
    }
    return null;
  }, gates.tab);
}
function compare(got, want) {
  if (!got || !want) return { ok: false, why: 'missing' };
  const near = (a, b) => (a == null && b == null) || (a != null && b != null && Math.abs(a - b) <= 1.5e-4 * Math.max(1, Math.abs(b)));
  const pairs = v === 't1' ? [['n', 'n'], ['med', 'median'], ['worse', 'worse']]
    : v === 't3' ? [['n', 'n'], ['bw', 'b_better'], ['aw', 'a_better'], ['t', 'tie'], ['med', 'median']]
      : [['planes', 'planes'], ['cells', 'cells'], ['median_cell', 'median_cell']];
  const diffs = [];
  for (const [g, w] of pairs) if (!near(got[g], want[w])) diffs.push(`${g}: page ${got[g]} vs oracle ${want[w]}`);
  if (v === 't2') {
    const a = got.worst || {}, b = want.worst || {};
    for (const k of ['site', 'joint', 'cell', 'targets']) if (a[k] !== b[k]) diffs.push(`worst.${k}: ${a[k]} vs ${b[k]}`);
    if (!near(a.median, b.median)) diffs.push(`worst.median: ${a.median} vs ${b.median}`);
  }
  return { ok: !diffs.length, diffs };
}
async function width(page) { return page.evaluate(() => { const e = document.querySelector('#tc data-fold.dw-rail'); return e ? Math.round(e.getBoundingClientRect().width) : null; }); }
async function drag(page, sel, dx) {
  const h = await page.$(sel); if (!h) return false;
  const b = await h.boundingBox(); if (!b) return false;
  const x = b.x + b.width / 2, y = b.y + Math.min(b.height / 2, 150);
  await page.mouse.move(x, y); await page.mouse.down();
  await page.mouse.move(x + dx / 2, y, { steps: 6 }); await page.mouse.move(x + dx, y, { steps: 6 }); await page.mouse.up();
  await page.waitForTimeout(600); return true;
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 },
      recordVideo: args.includes('--video') ? { dir: path.join(out, 'video'), size: { width: 1440, height: 900 } } : undefined });
    // the check never launches a viewer: every selection post is rewritten to ?dry=1 (build the .rrd, report, no spawn)
    await ctx.route('**/__rerun/**', (route) => { const u = route.request().url(); route.continue({ url: u + (u.includes('?') ? '&' : '?') + 'dry=1' }); });
    const page = await ctx.newPage();
    page.on('console', (m) => { if (m.type() === 'error') R.errors.push(m.text()); });
    page.on('pageerror', (e) => R.errors.push(String(e)));

    // 1. the story (it is the video): landing, the new tab, the scenario's pick, the tab's own move, the drill
    await page.goto(url, { waitUntil: 'load' }); await ready(page);
    const story = [];
    const recount = {};
    for (const [i, step] of (gates.story || []).entries()) {
      for (const a of step.actions || []) await act(page, a);
      if (step.read) {
        const got = await numbers(page);
        recount[step.read] = { page: got, oracle: oracle[step.read], ...compare(got, oracle[step.read]) };
      }
      if (step.drill) {
        // the drill leaves this page: the target view, its selection, Open in Rerun, the way back
        await page.waitForFunction(() => /\/common\/target\.html/.test(location.pathname), null, { timeout: 15000 }).catch(() => R.errors.push('drill did not open the target view'));
        await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 60000 }).catch(() => R.errors.push('target view never ready'));
        await page.waitForTimeout(1500);
        const u = new URL(page.url());
        const back = u.searchParams.get('back') || '';
        const state = await page.evaluate(() => window.TV_STATE || null);
        const crumb = await page.evaluate(() => { const a = document.querySelector('#crumb a'); return a ? { text: a.textContent, href: a.getAttribute('href') } : null; });
        R.checks.drill = { url: page.url(), keep: u.searchParams.get('keep'), back, backKeepsTab: back.includes(`#tab=${gates.tabSlug}`),
          backKeepsFilter: gates.scenarioParam ? back.includes(gates.scenarioParam) : null, state, crumb };
      }
      await page.screenshot({ path: path.join(out, `story-${i + 1}.png`) });
      if (step.drill && gates.rerun_button) {
        const h = await page.$(gates.rerun_button);
        if (h) {
          const label = (await h.textContent()).trim();
          await h.click();
          await page.waitForTimeout(9000);
          R.checks.drill.rerun = { label, answer: await page.evaluate(() => window.TV_LAST_RERUN || window.TC_LAST_RERUN || null) };
        }
        // back to the workbench by its own link: the tab and the filter come back
        const href = await page.evaluate(() => { const a = document.querySelector('#crumb a'); return a ? a.href : null; });
        if (href) {
          await page.goto(href, { waitUntil: 'load' }); await ready(page);
          await page.waitForTimeout(2500);
          R.checks.drill.returned = { tab: await page.evaluate(() => { const t = document.querySelector('#tc data-tabs [role=tab][aria-selected=true]'); return t ? t.textContent : null; }), count: await countText(page) };
          await page.screenshot({ path: path.join(out, `story-${i + 1}-back.png`) });
        }
      }
      story.push({ label: step.label, caption: step.caption, count: await countText(page).catch(() => null) });
    }
    R.checks.story = story;
    R.checks.recount = recount;
    R.checks.recountOk = Object.keys(recount).length === 2 && Object.values(recount).every((x) => x.ok)
      && JSON.stringify(recount.unfiltered && recount.unfiltered.page) !== JSON.stringify(recount.scenario && recount.scenario.page);

    // 2. V2's own checks, unchanged: one dataset tick, every tab, the rail drag + reload, the fold
    await page.goto(url, { waitUntil: 'load' }); await ready(page);
    const before = await countText(page);
    await act(page, { click: '#tc data-facets section[data-key=dataset] input[type=checkbox]', wait: 2500 });
    const after = await countText(page);
    R.checks.filter = { before, after, changed: before !== after };
    const tabs = [];
    for (const [k, t] of ['overview', 'targets', 'runs', 'new'].entries()) {
      await act(page, { click: `#tc data-tabs [role=tab]:nth-of-type(${k + 1})`, wait: t === 'new' ? 6000 : 1800 });
      const ov = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      await page.screenshot({ path: path.join(out, `tab-${t}.png`) });
      tabs.push({ id: t, count: await countText(page), overflow: ov });
    }
    R.checks.tabs = tabs;
    const w0 = await width(page);
    await drag(page, '#tc .dw-rail-handle', 120);
    const w1 = await width(page);
    await page.reload({ waitUntil: 'load' }); await ready(page);
    const w2 = await width(page);
    R.checks.drag = { before: w0, after: w1, afterReload: w2, ok: w1 - w0 >= 100 && Math.abs(w2 - w1) <= 2 };
    await act(page, { click: '#fold' });
    const wf = await width(page);
    await page.screenshot({ path: path.join(out, 'folded.png') });
    await act(page, { click: '#fold' });
    R.checks.fold = { folded: wf, unfolded: await width(page) };
    // put the rail back where it was, so the next run starts the same
    await drag(page, '#tc .dw-rail-handle', -120);
    R.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const video = page.video();
    await ctx.close();
    if (video) { const p = path.join(out, 'session.webm'); fs.renameSync(await video.path(), p); R.video = p; }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(out, 'check.json'), JSON.stringify(R, null, 1));
  console.log(JSON.stringify({ variant: v, errors: R.errors, recountOk: R.checks.recountOk, recount: R.checks.recount,
    drill: R.checks.drill && { keep: R.checks.drill.keep, backKeepsTab: R.checks.drill.backKeepsTab, backKeepsFilter: R.checks.drill.backKeepsFilter,
      state: R.checks.drill.state, rerun: R.checks.drill.rerun && R.checks.drill.rerun.answer && R.checks.drill.rerun.answer.n, returned: R.checks.drill.returned },
    filter: R.checks.filter, drag: R.checks.drag, fold: R.checks.fold, tabs: R.checks.tabs, overflow: R.overflow }, null, 1));
})();
