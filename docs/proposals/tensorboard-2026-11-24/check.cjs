#!/usr/bin/env node
// The round's acceptance + capture for one variant, from its vN/gates.json (dispatcher's harness, 2026-11-24).
//   node check.cjs v2 --port 8841 [--site ur5e] [--video]
// Served by serve_round.py. Measures: count before / after the gates' one-dataset filter; every tab clicked (still +
// count kept); the rail dragged 120 px, width after, after a reload; fold; the target link (still of the target view,
// its selection count and Open in Rerun ?dry=1 answer); story stills (+ session video with --video); console errors;
// sideways overflow. Writes shots/<v>/*.png and prints one JSON object (also shots/<v>/check.json).
const fs = require('fs');
const path = require('path');
const { chromium } = require('/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const v = args[0];
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const port = Number(opt('--port', 8841));
const site = opt('--site', 'ur5e');
const here = __dirname;
const gates = JSON.parse(fs.readFileSync(path.join(here, v, 'gates.json'), 'utf8'));
const out = path.join(here, 'shots', v);
fs.mkdirSync(out, { recursive: true });
const url = `http://127.0.0.1:${port}/${v}/index.html${gates.query || gates.url_query || ''}`;
const R = { variant: v, url, errors: [], checks: {} };

async function ready(page) {
  await page.waitForFunction((sel) => !!document.querySelector(sel), gates.ready, { timeout: 60000 }).catch(() => R.errors.push('never ready'));
  await page.waitForTimeout(1200);
}
async function countText(page) {
  return page.evaluate((sel) => { const e = document.querySelector(sel); return e ? e.textContent.trim().replace(/\s+/g, ' ') : null; }, gates.count);
}
async function act(page, a) {
  if (a.click) await page.click(a.click);
  if (a.dblclick) await page.dblclick(a.dblclick);
  if (a.fill) await page.fill(a.fill[0], a.fill[1]);
  if (a.select) await page.selectOption(a.select[0], a.select[1]);
  if (a.press) await page.keyboard.press(a.press);
  await page.waitForTimeout(a.wait || 900);
}
async function width(page) { return page.evaluate((s) => { const e = document.querySelector(s); return e ? Math.round(e.getBoundingClientRect().width) : null; }, gates.panel); }
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
    // the story first (it is the video)
    await page.goto(url, { waitUntil: 'load' }); await ready(page);
    const story = [];
    for (const [i, step] of (gates.story || []).entries()) {
      for (const a of step.actions || []) await act(page, a);
      await page.screenshot({ path: path.join(out, `story-${i + 1}.png`) });
      story.push({ label: step.label, caption: step.caption, count: await countText(page) });
    }
    R.checks.story = story;
    // fresh state for the measurements (no URL filter)
    await page.goto(url, { waitUntil: 'load' }); await ready(page);
    const before = await countText(page);
    for (const a of gates.filter || []) await act(page, a);
    const after = await countText(page);
    R.checks.filter = { before, after, changed: before !== after };
    const tabs = [];
    for (const t of gates.tabs || []) {
      await act(page, { click: t.sel, wait: 1500 });
      const ov = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      await page.screenshot({ path: path.join(out, `tab-${t.id}.png`) });
      tabs.push({ id: t.id, count: await countText(page), overflow: ov });
    }
    R.checks.tabs = tabs;
    const w0 = await width(page);
    await drag(page, gates.resizer, 120);
    const w1 = await width(page);
    await page.reload({ waitUntil: 'load' }); await ready(page);
    const w2 = await width(page);
    R.checks.drag = { before: w0, after: w1, afterReload: w2, ok: w1 - w0 >= 100 && Math.abs(w2 - w1) <= 2 };
    if (gates.fold) {
      await act(page, { click: gates.fold });
      const wf = await width(page);
      await page.screenshot({ path: path.join(out, 'folded.png') });
      await act(page, { click: gates.unfold || gates.fold });
      R.checks.fold = { folded: wf, unfolded: await width(page) };
    }
    // the target link
    if (gates.target_link) {
      await page.goto(url, { waitUntil: 'load' }); await ready(page);
      const popup = ctx.waitForEvent('page', { timeout: 4000 }).catch(() => null);
      for (const a of gates.target_link) await act(page, a);
      const other = await popup;
      const tp = other || page;
      let frame = null;
      const fsel = gates.target_frame || gates.rerun_frame;
      if (!other && fsel) { const h = await page.$(fsel); frame = h ? await h.contentFrame() : null; }
      const scope = frame || tp;
      await scope.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 60000 }).catch(() => R.errors.push('target view never ready'));
      await tp.waitForTimeout(1500);
      await tp.screenshot({ path: path.join(out, 'target-view.png') });
      const state = await scope.evaluate(() => window.TV_STATE || null);
      let rerun = null;
      if (gates.rerun_button) {
        const h = await scope.$(gates.rerun_button);
        if (!h) rerun = { error: 'no button ' + gates.rerun_button };
        else {
          const label = (await h.textContent()).trim();
          await h.click();
          await tp.waitForTimeout(8000);
          rerun = { label, answer: await scope.evaluate(() => window.TV_LAST_RERUN || window.TC_LAST_RERUN || null) };
        }
      }
      R.checks.target = { opened: other ? other.url() : (frame ? frame.url() : page.url()), state, rerun };
      if (other) await other.close();
    }
    R.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const video = page.video();
    await ctx.close();
    if (video) { const p = path.join(out, 'session.webm'); fs.renameSync(await video.path(), p); R.video = p; }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(out, 'check.json'), JSON.stringify(R, null, 1));
  console.log(JSON.stringify(R));
})();
