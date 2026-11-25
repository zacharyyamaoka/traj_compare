#!/usr/bin/env node
// The round's acceptance + capture for one variant (adapted from ../tensorboard-2026-11-24/check.cjs, which stays as it is).
//   node check.cjs o2 --port 8851 [--video]
// Served by serve.py. Headless Chrome 1440 × 900. Writes shots/<v>/*.png, shots/<v>/session.webm and shots/<v>/check.json:
// - the story (gates.json) as stills + the session video; after each step the Overview's numbers (its views' hooks);
// - the numbers against oracle.json (oracle.py, Python): the landing against the unfiltered state, every later step
//   against the UR5e-cell state, including the step that switches a view (columns = speed, panels = deployment, cost = jerk);
// - V2's own checks: every tab (still, count, sideways overflow), the rail dragged 120 px and kept after a reload, fold,
//   the target link (Targets row → Open target view → target page, Open in Rerun ?dry=1), console errors.
const fs = require('fs');
const path = require('path');
const { chromium } = require('/home/bam/aruco-studio/web/node_modules/playwright');

const args = process.argv.slice(2);
const v = args[0];
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const port = Number(opt('--port', 8851));
const here = __dirname;
const gates = JSON.parse(fs.readFileSync(path.join(here, v, 'gates.json'), 'utf8'));
const oracle = JSON.parse(fs.readFileSync(path.join(here, 'oracle.json'), 'utf8'));
const out = path.join(here, 'shots', v);
fs.mkdirSync(out, { recursive: true });
const url = `http://127.0.0.1:${port}/${v}/index.html${gates.url_query || ''}`;
const R = { variant: v, url, errors: [], checks: {} };

async function ready(page) {
  await page.waitForFunction((sel) => !!document.querySelector(sel), gates.ready, { timeout: 90000 }).catch(() => R.errors.push('never ready'));
  await page.waitForFunction(() => [...document.querySelectorAll('[data-tc-view]')].some((e) => e.offsetParent), null, { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(800);
}
async function countText(page) {
  return page.evaluate((sel) => { const e = document.querySelector(sel); return e ? e.textContent.trim().replace(/\s+/g, ' ') : null; }, gates.count);
}
async function act(page, a) {
  if (a.click) await page.click(a.click);
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
// every visible host view's numbers, and what the page shows around them (the open tab, a records peek)
async function hooks(page) {
  return page.evaluate(() => {
    const wb = document.getElementById('tc');
    const peek = [...document.querySelectorAll('#tc data-views.dd-drill')].find((e) => e.offsetParent);
    return {
      tab: wb && wb.tab, count: (document.querySelector('#tc data-count') || {}).textContent,
      peek: peek ? { text: (peek.textContent || '').replace(/\s+/g, ' ').slice(0, 220), rows: peek.querySelectorAll('tbody tr').length, records: peek.querySelectorAll('[data-id], .dv-peek-records tr, .dv-records tr').length } : null,
      views: [...document.querySelectorAll('[data-tc-view]')].filter((e) => e.offsetParent).map((e) => ({ type: e.dataset.tcView, draws: Number(e.dataset.tcDraws), hook: e.tcOverview })),
    };
  });
}

// ── the oracle comparison ──
const close = (a, b) => (a === b) || (typeof a === 'number' && typeof b === 'number' && Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b)));
function compare(h, o) {
  const res = { checked: 0, bad: [] };
  const eq = (what, a, b) => { res.checked += 1; if (!close(a, b)) res.bad.push(`${what}: page ${JSON.stringify(a)} vs oracle ${JSON.stringify(b)}`); };
  const byKey = (rows, n) => new Map(rows.map((r) => [JSON.stringify(r.slice(0, n)), r.slice(n)]));
  const rows = (what, page, orc, n) => {
    const om = byKey(orc, n);
    for (const r of page) {
      const k = JSON.stringify(r.slice(0, n));
      if (!om.has(k)) { res.checked += 1; res.bad.push(`${what}: ${k} not in the oracle`); continue; }
      r.slice(n).forEach((x, i) => eq(`${what} ${k}[${i}]`, x, om.get(k)[i]));
    }
    return om.size;
  };
  for (const view of h.views) {
    const x = view.hook || {};
    if (x.kind === 'league') {
      const ol = x.facet && x.facet !== 'all' ? o.leagueByFacet[x.facet] : o.league;
      const ok = x.facet && x.facet !== 'all' ? o.kpisByFacet[x.facet] : o.kpis;
      if (!ol) { res.bad.push(`no oracle League for ${x.facet}`); continue; }
      eq('league length', x.league.length, ol.length);
      x.league.forEach((r, i) => { eq(`league #${i + 1} config`, r[0], (ol[i] || [])[0]); eq(`league #${i + 1} v`, r[1], (ol[i] || [])[1]); eq(`league #${i + 1} n`, r[2], (ol[i] || [])[2]); });
      for (const [c, ks] of Object.entries(x.kpis || {})) for (const [k, val] of Object.entries(ks)) eq(`${k} ${c}`, val, (ok[k][c] === undefined ? null : ok[k][c]));
      if (x.wins) {
        eq('wins cells', x.wins.cells, o.wins.cells);
        for (const [c, w, of] of x.wins.byConfig) { eq(`wins ${c}`, w, (o.wins.byConfig[c] || [])[0]); eq(`of ${c}`, of, (o.wins.byConfig[c] || [])[1]); }
      }
      if (x.heat) { const n = rows('heat', x.heat.cells, o.heat, 2); eq('heat cells', x.heat.cells.length, n); }
    } else if (x.kind === 'matrix' && !x.empty) {
      const om = o.matrix[x.axis];
      if (!om) { res.bad.push(`no oracle for axis ${x.axis}`); continue; }
      const leaf = x.cells.filter((c) => c[0] === 'config').map((c) => c.slice(1));
      const group = x.cells.filter((c) => c[0] === 'group').map((c) => c.slice(1));
      const nLeaf = rows(`matrix ${x.axis} leaf`, leaf, om.leaf.map((r) => [r[0], String(r[1]), r[2], r[3]]), 2);
      rows(`matrix ${x.axis} group`, group, om.group.map((r) => [r[0], String(r[1]), r[2], r[3]]), 2);
      if (!x.rows || leaf.length) eq(`matrix ${x.axis} leaf cells drawn (unfolded)`, leaf.length === nLeaf || leaf.length < nLeaf, true);
      for (const [col, c, val] of x.best) { const b = om.best[col]; eq(`best ${col}`, c, b && b[0]); eq(`best ${col} v`, val, b && b[1]); }
    } else if (x.kind === 'sweep') {
      if (x.by === 'deployment') rows('sweep by deployment', x.cells, o.sweepByDeployment.map((r) => [r[0], r[1], r[2], r[3], r[4]]), 3);
      else rows('sweep', x.cells.map((r) => r.slice(1)), o.sweep, 2);
      rows('sweep table', x.table, o.sweep, 2);
      eq('slowest best', x.answer.slow[0], o.sweepAnswer.slow[0]); eq('slowest best v', x.answer.slow[1], o.sweepAnswer.slow[1]);
      eq('fastest best', x.answer.fast[0], o.sweepAnswer.fast[0]); eq('growth', x.answer.growth, o.sweepAnswer.growth);
    } else if (x.kind === 'tradeoff') {
      const ot = o.tradeoff[x.cost];
      if (!ot) { res.bad.push(`no oracle for cost ${x.cost}`); continue; }
      const n = rows(`tradeoff ${x.cost}`, x.points, ot.points, 2);
      eq(`tradeoff ${x.cost} points`, x.points.length, n);
      eq(`frontier ${x.cost}`, JSON.stringify(x.frontier.map((f) => f.join('|')).sort()), JSON.stringify(ot.frontier.map((f) => f.join('|')).sort()));
    } else if (x.kind === 'worst') {
      // O3's Worst targets page opens on the best config: its 25 worst targets, worst first
      eq('worst config', x.config, o.tiles.best.config);
      eq('worst rows', x.rows.length, o.tiles.worstList.length);
      x.rows.forEach((r, i) => { eq(`worst #${i + 1} target`, r[0], (o.tiles.worstList[i] || [])[0]); eq(`worst #${i + 1} v`, r[1], (o.tiles.worstList[i] || [])[1]); });
    } else if (x.kind === 'tile' && x.numbers) {
      const t = o.tiles[x.tile];
      const nb = x.numbers;
      if (x.tile === 'best') { eq('tile best', nb.config, t.config); eq('tile best v', nb.v, t.v); eq('tile best n', nb.n, t.n); eq('tile next', JSON.stringify(nb.next && nb.next[0]), JSON.stringify(t.next && t.next[0])); eq('tile next ratio', nb.next && nb.next[1], t.next && t.next[1]); }
      if (x.tile === 'speed') { eq('tile speed from', nb.from, t.from); eq('tile speed v0', nb.v0, t.v0); eq('tile speed ratio', nb.ratio, t.ratio); }
      if (x.tile === 'worst') { eq('tile worst target', nb.target, t.target); eq('tile worst v', nb.v, t.v); eq('tile worst ratio', nb.ratio, t.ratio); eq('tile worst of', nb.targets, t.targets); }
      if (x.tile === 'coverage') { eq('tile coverage filled', nb.filled, t.filled); eq('tile coverage cells', nb.cells, t.cells); eq('tile coverage pct', nb.pct, t.pct); }
      if (x.tile === 'left') for (const k of ['runs', 'targets', 'configs', 'deployments', 'datasets']) eq(`tile left ${k}`, nb[k], t[k]);
      if (x.tile === 'cost') { eq('tile cost deployment', nb.deployment, t.deployment); eq('tile cost frontier', JSON.stringify(nb.frontier.slice().sort()), JSON.stringify(t.frontier)); eq('tile cost accurate', nb.accurate[0], t.accurate[0]); eq('tile cost cheapest', nb.cheapest[0], t.cheapest[0]); eq('tile cost cheapest x', nb.cheapest[1], t.cheapest[1]); }
    }
  }
  res.ok = res.checked > 0 && res.bad.length === 0;
  res.bad = res.bad.slice(0, 12);
  return res;
}
// the few numbers a reader sees first, per view (the check.json's before / after)
function headline(h) {
  return h.views.map((view) => {
    const x = view.hook || {};
    if (x.kind === 'league') return { view: 'league', best: x.best, configs: x.configs, cells: x.wins && x.wins.cells };
    if (x.kind === 'matrix') return { view: 'matrix', axis: x.axis, columns: (x.columns || []).length, rows: x.rows, best: x.answer && x.answer.cfgWins && x.answer.cfgWins[0] };
    if (x.kind === 'sweep') return { view: 'sweep', by: x.by, panels: x.panels, answer: x.answer };
    if (x.kind === 'tradeoff') return { view: 'tradeoff', cost: x.cost, points: x.points.length, frontier: x.frontier };
    if (x.kind === 'tile') return { view: `tile ${x.tile}`, numbers: x.numbers };
    return { view: x.kind };
  });
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 },
      recordVideo: args.includes('--video') ? { dir: path.join(out, 'video'), size: { width: 1440, height: 900 } } : undefined });
    // the check never launches a viewer: every selection post is rewritten to ?dry=1
    await ctx.route('**/__rerun/**', (route) => { const u = route.request().url(); route.continue({ url: u + (u.includes('?') ? '&' : '?') + 'dry=1' }); });
    const page = await ctx.newPage();
    page.on('console', (m) => { if (m.type() === 'error') R.errors.push(m.text()); });
    page.on('pageerror', (e) => R.errors.push(String(e)));
    // the story first (it is the video)
    await page.goto(url, { waitUntil: 'load' });
    await page.evaluate(() => { try { localStorage.clear(); } catch { /* */ } });
    await page.reload({ waitUntil: 'load' }); await ready(page);
    const story = [];
    for (const [i, step] of (gates.story || []).entries()) {
      for (const a of step.actions || []) await act(page, a);
      await page.screenshot({ path: path.join(out, `story-${i + 1}.png`) });
      const h = await hooks(page);
      const against = i === 0 ? 'all' : 'ur5e_cell';
      story.push({ label: step.label, count: await countText(page), tab: h.tab, peek: h.peek, numbers: headline(h), oracle: { against, ...compare(h, oracle[against]) } });
    }
    R.checks.story = story;
    // fresh state for the measurements (no URL filter, no remembered switch)
    await page.evaluate(() => { try { localStorage.clear(); } catch { /* */ } });
    await page.goto(url, { waitUntil: 'load' }); await ready(page);
    const before = await countText(page);
    const hb = await hooks(page);
    for (const a of gates.filter || []) await act(page, a);
    const after = await countText(page);
    const ha = await hooks(page);
    R.checks.filter = { before, after, changed: before !== after };
    R.checks.numbers = {
      before: headline(hb), after: headline(ha),
      redrawn: ha.views.every((x, i) => !hb.views[i] || x.draws > hb.views[i].draws),
      oracleBefore: compare(hb, oracle.all), oracleAfter: compare(ha, oracle.ur5e_cell),
    };
    R.checks.numbers.changed = JSON.stringify(R.checks.numbers.before) !== JSON.stringify(R.checks.numbers.after);
    await page.screenshot({ path: path.join(out, 'overview-filtered.png') });
    const tabs = [];
    for (const t of gates.tabs || []) {
      await act(page, { click: t.sel, wait: 1800 });
      const ov = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      await page.screenshot({ path: path.join(out, `tab-${t.id}.png`) });
      tabs.push({ id: t.id, count: await countText(page), overflow: ov });
    }
    R.checks.tabs = tabs;
    await act(page, { click: gates.tabs[0].sel, wait: 1200 });
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
      await act(page, { click: gates.fold });
      R.checks.fold = { folded: wf, unfolded: await width(page) };
    }
    // V2's target link, unchanged
    if (gates.target_link) {
      await page.goto(url, { waitUntil: 'load' }); await ready(page);
      for (const a of gates.target_link) await act(page, a);
      await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 60000 }).catch(() => R.errors.push('target view never ready'));
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(out, 'target-view.png') });
      const state = await page.evaluate(() => window.TV_STATE || null);
      let rerun = null;
      const h = await page.$(gates.rerun_button);
      if (h) {
        const label = (await h.textContent()).trim();
        await h.click();
        await page.waitForTimeout(8000);
        rerun = { label, answer: await page.evaluate(() => window.TV_LAST_RERUN || null) };
      }
      R.checks.target = { opened: page.url(), state, rerun };
    }
    R.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const video = page.video();
    await ctx.close();
    if (video) { const p = path.join(out, 'session.webm'); fs.renameSync(await video.path(), p); R.video = p; }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(out, 'check.json'), JSON.stringify(R, null, 1));
  const n = R.checks.numbers || {};
  console.log(JSON.stringify({ v, errors: R.errors, filter: R.checks.filter, oracleBefore: n.oracleBefore && { ok: n.oracleBefore.ok, checked: n.oracleBefore.checked, bad: n.oracleBefore.bad },
    oracleAfter: n.oracleAfter && { ok: n.oracleAfter.ok, checked: n.oracleAfter.checked, bad: n.oracleAfter.bad }, changed: n.changed, redrawn: n.redrawn,
    story: (R.checks.story || []).map((s) => [s.label, s.tab, s.peek && s.peek.rows, s.oracle.ok, s.oracle.checked, s.oracle.bad.slice(0, 2)]),
    drag: R.checks.drag, fold: R.checks.fold, target: R.checks.target && { opened: R.checks.target.opened.slice(-80), rerun: R.checks.target.rerun && R.checks.target.rerun.answer && R.checks.target.rerun.answer.n },
    tabs: (R.checks.tabs || []).map((t) => [t.id, t.overflow]), overflow: R.overflow }));
})();
