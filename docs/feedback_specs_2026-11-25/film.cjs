// Film the coverage workbench's filter driving every tab (feedback fb-a5db22b5), on a served write_workbench site.
//   node film.cjs <playwright dir> <chrome> <index url> <out dir>
// Writes hero.webm (the session) and overview-{all,holdout,one}.png. One context, closed at the end.
const { chromium } = require(process.argv[2]);
const fs = require('fs');
(async () => {
  const [, , , chrome, url, out] = process.argv;
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ executablePath: chrome, headless: true });
  const size = { width: 1280, height: 760 };
  const context = await browser.newContext({ viewport: size, recordVideo: { dir: out, size } });
  const page = await context.newPage();
  const started = Date.now();
  await page.goto(url);
  await page.waitForSelector('data-workbench[data-ready]', { timeout: 30000 });
  await page.waitForTimeout(1500);
  const ready = (Date.now() - started) / 1000;
  const tab = async (name, wait = 1100) => { await page.click(`data-workbench data-tabs [role=tab][data-tab="${name}"]`); await page.waitForTimeout(wait); };
  const tick = async (prop, value) => { await page.click(`data-workbench data-facets section.df-group[data-p="${prop}"] input[data-value="${value}"]`); await page.waitForTimeout(1500); };
  const wb = page.locator('data-workbench');
  await wb.screenshot({ path: `${out}/overview-all.png` });
  await tick('split', 'holdout');
  await wb.screenshot({ path: `${out}/overview-holdout.png` });
  await tick('dataset', 'Cell pick');
  await wb.screenshot({ path: `${out}/overview-one.png` });
  for (const name of ['Limits', 'Tool position', 'Tool orientation', 'Trajectories', 'Overview']) await tab(name);
  const total = (Date.now() - started) / 1000;
  const video = page.video();
  await context.close();
  fs.renameSync(await video.path(), `${out}/hero.webm`);
  fs.writeFileSync(`${out}/film.json`, JSON.stringify({ ready, total }));
  await browser.close();
  console.log(JSON.stringify({ ready, total }));
})().catch((e) => { console.error(e); process.exit(1); });
