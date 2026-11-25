// Drive pages of the round in headless Chrome (one browser), take stills, print measurements.
//   node shoot.cjs jobs.json OUT_DIR
// jobs: [{name, url, w?, h?, full?, actions: [{click}|{dblclick}|{fill:[sel,text]}|{select:[sel,val]}|{wait}|{eval}|{drag:[sel,dx]}|{shot:name}|{frame:sel}]}]
// Each job prints one JSON line: console errors, failed requests, eval results, horizontal overflow.
const fs = require('fs');
const path = require('path');
const { chromium } = require('/home/bam/aruco-studio/web/node_modules/playwright');

(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const out = process.argv[3];
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  try {
    for (const job of jobs) {
      const ctx = await browser.newContext({ viewport: { width: job.w || 1440, height: job.h || 900 },
        recordVideo: job.video ? { dir: path.join(out, 'video'), size: { width: job.w || 1440, height: job.h || 900 } } : undefined });
      const page = await ctx.newPage();
      const errors = [], failed = [], results = [];
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('pageerror', (e) => errors.push(String(e)));
      page.on('requestfailed', (r) => failed.push(r.url()));
      await page.goto(job.url, { waitUntil: 'load' });
      if (!job.noready) await page.waitForFunction(() => document.documentElement.dataset.ready === "1", null, { timeout: 60000 }).catch(() => errors.push("never ready"));
      await page.waitForTimeout(job.settle || 600);
      for (const a of job.actions || []) {
        if (a.click) await page.click(a.click);
        if (a.dblclick) await page.dblclick(a.dblclick);
        if (a.fill) await page.fill(a.fill[0], a.fill[1]);
        if (a.select) await page.selectOption(a.select[0], a.select[1]);
        if (a.drag) {
          const box = await (await page.$(a.drag[0])).boundingBox();
          const x = box.x + box.width / 2, y = box.y + Math.min(box.height / 2, 200);
          await page.mouse.move(x, y); await page.mouse.down();
          await page.mouse.move(x + a.drag[1] / 2, y, { steps: 5 }); await page.mouse.move(x + a.drag[1], y, { steps: 5 });
          await page.mouse.up();
        }
        if (a.reload) { await page.reload({ waitUntil: 'load' }); await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 60000 }).catch(() => {}); }
        if (a.wait) await page.waitForTimeout(a.wait);
        if (a.eval) results.push(await page.evaluate(a.eval));
        if (a.shot) await page.screenshot({ path: path.join(out, a.shot + '.png'), fullPage: !!a.full });
        await page.waitForTimeout(a.after || 300);
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      await page.screenshot({ path: path.join(out, job.name + '.png'), fullPage: !!job.full });
      const video = page.video();
      await ctx.close();
      let videoPath = null;
      if (video) { videoPath = path.join(out, job.name + '.webm'); fs.renameSync(await video.path(), videoPath); }
      console.log(JSON.stringify({ name: job.name, errors, failed, overflow, results, video: videoPath }));
    }
  } finally {
    await browser.close();
  }
})();
