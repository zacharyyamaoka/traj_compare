// Screenshot + measure the outer-view prototypes in headless Chrome (one browser, one page at a time).
//   node shoot.cjs jobs.json OUT_DIR
// jobs.json: [{ "name": "v1-s1", "url": "file:///…/v1.html#/overview", "actions": [ {"click": "css"} | {"hover": "css"} |
//   {"hoverAt": [x, y]} | {"wait": ms} | {"eval": "js"} ], "full": false }]
// Prints one JSON line per job: console errors, page height, and any {"eval"} results — the measurements the scoring cites.
const path = require('path');
const fs = require('fs');
const { chromium } = require('/home/bam/aruco-studio/web/node_modules/playwright');

(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const outDir = process.argv[3];
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--allow-file-access-from-files'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  let errors = [];
  let network = [];
  // G2 evidence: anything the page fetches that is not file:// or data: (the drill links are navigation, not fetches).
  page.on('request', (r) => { const u = r.url(); if (!/^(file|data|about|blob):/.test(u)) network.push(u); });
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  for (const job of jobs) {
    errors = [];
    network = [];
    const results = [];
    await page.goto('about:blank');
    await page.goto(job.url, { waitUntil: 'load' });
    await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 30000 }).catch(() => errors.push('never ready'));
    await page.waitForTimeout(job.settle || 400);
    for (const a of job.actions || []) {
      if (a.click) await page.click(a.click);
      if (a.hover) await page.hover(a.hover);
      if (a.hoverAt) await page.mouse.move(a.hoverAt[0], a.hoverAt[1]);
      if (a.wait) await page.waitForTimeout(a.wait);
      if (a.eval) results.push(await page.evaluate(a.eval));
      await page.waitForTimeout(a.after || 250);
    }
    const height = await page.evaluate(() => {
      const main = document.getElementById('ov-main');
      return { scroll: document.scrollingElement.scrollHeight, mainBottom: main ? Math.round(main.getBoundingClientRect().bottom + window.scrollY) : null, hash: location.hash };
    });
    const file = path.join(outDir, job.name + '.png');
    await page.screenshot({ path: file, fullPage: !!job.full });
    console.log(JSON.stringify({ name: job.name, errors, network, height, results }));
  }
  await browser.close();
})();
