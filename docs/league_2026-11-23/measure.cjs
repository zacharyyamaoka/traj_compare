// Measure the outer view on a real site at 1440 x 900 (NAVIGATION.md Part E): every tab's document height, where the league
// sits, and the drill path by clicking. Prints one JSON line; screenshots each tab into <out>.
//   node measure.cjs <playwright dir> <chrome> <index url> <out dir> <name>
const { chromium } = require(process.argv[2]);
const [chrome, index, outDir, name] = process.argv.slice(3);
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true });
  const out = { name, errors: [], tabs: {} };
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('pageerror', (e) => out.errors.push(String(e)));
  const height = () => page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  async function go(hash, shot) {
    await page.goto(index + hash); await page.waitForTimeout(3500);
    const h = await height();
    if (shot) await page.screenshot({ path: `${outDir}/${name}-${shot}.png` });
    return h;
  }
  const t0 = Date.now();
  out.tabs.overview = await go('#/', 'overview');
  out.open_ms = Date.now() - t0;
  out.tablist = await page.evaluate(() => Array.from(document.querySelectorAll('[data-tc-dataset-tab]')).map((a) => a.getAttribute('data-tc-dataset-tab')));
  out.league = await page.evaluate(() => {
    const t = document.querySelector('[data-tc-league]'); const b = t && t.getBoundingClientRect();
    return { top: b && Math.round(b.top), bottom: b && Math.round(b.bottom), rows: document.querySelectorAll('[data-tc-league-row]').length,
      keys: Array.from(document.querySelectorAll('[data-tc-league-row]')).map((r) => r.getAttribute('data-key')),
      verdict: (document.querySelector('[data-tc-league-verdict]') || {}).textContent || '' };
  });
  if (out.tablist.includes('sweeps')) out.tabs.sweeps = await go('#/sweeps', 'sweeps');
  out.tabs.targets_cards = await go('#/targets', 'targets');
  await page.click('[data-tc-targets-view] [data-view="table"]'); await page.waitForTimeout(2500);
  out.tabs.targets_table = await height();
  await page.screenshot({ path: `${outDir}/${name}-table.png` });
  await page.click('[data-tc-targets-view] [data-view="cards"]'); await page.waitForTimeout(500);
  out.tabs.runs = await go('#/runs', 'runs');
  // drill: Overview -> the rank-1 row -> its worst target -> that target's level
  await go('#/', null);
  await page.click('[data-tc-league-row][data-rank="1"]'); await page.waitForTimeout(2500);
  out.drill = await page.evaluate(() => ({ hash: location.hash, rows: document.querySelectorAll('[data-tc-drill-row]').length,
    first: (document.querySelector('[data-tc-drill-row]') || { getAttribute: () => null }).getAttribute('data-target'),
    run: ((document.querySelector('[data-tc-drill-row] a[href*="report.html"]') || {}).getAttribute || (() => null)).call(document.querySelector('[data-tc-drill-row] a[href*="report.html"]'), 'href') }));
  out.tabs.drill = await height();
  await page.screenshot({ path: `${outDir}/${name}-drill.png` });
  await page.click('[data-tc-drill-row] a[href^="#/target/"]'); await page.waitForTimeout(3500);
  out.target = { hash: await page.evaluate(() => location.hash), height: await height(),
    run_list: await page.evaluate(() => !!document.querySelector('[data-tc-run-list] [data-tc-run]')) };
  await page.screenshot({ path: `${outDir}/${name}-target.png` });
  // the Coverage link at the end of the tab bar (traj_compare a5de694, written with coverage=True) opens its page
  await go('#/', null);
  const link = await page.$('a[data-tc-coverage-link]');
  out.coverage = { link: !!link };
  if (link) {
    out.coverage.href = await link.getAttribute('href');
    await Promise.all([page.waitForLoadState('load'), link.click()]);
    await page.waitForTimeout(4000);
    out.coverage.url = page.url().replace(/^.*\/(?=coverage\/)/, '');
    out.coverage.title = await page.title();
    out.coverage.height = await height();
    await page.screenshot({ path: `${outDir}/${name}-coverage.png` });
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
