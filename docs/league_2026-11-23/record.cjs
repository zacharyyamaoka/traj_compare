// The hero clip: Overview -> a config's row -> its worst target -> that target's level -> a run report, on a served site.
//   node record.cjs <playwright dir> <chrome> <index url> <video dir>
// Each click is marked with a short ring where it lands (Playwright records no cursor).
const { chromium } = require(process.argv[2]);
const [chrome, index, videoDir] = process.argv.slice(3);
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: videoDir, size: { width: 1440, height: 900 } } });
  const page = await context.newPage();
  async function mark(selector) {
    const box = await page.locator(selector).first().boundingBox();
    if (!box) throw new Error('nothing at ' + selector);
    await page.evaluate(([x, y]) => {
      const ring = document.createElement('div');
      ring.style.cssText = `position:fixed;left:${x - 18}px;top:${y - 18}px;width:36px;height:36px;border-radius:50%;` +
        'border:3px solid #e8590c;background:rgba(232,89,12,.18);z-index:99999;pointer-events:none;transition:opacity .5s';
      document.body.appendChild(ring);
      setTimeout(() => { ring.style.opacity = '0'; }, 700);
      setTimeout(() => ring.remove(), 1300);
    }, [box.x + Math.min(box.width / 2, 60), box.y + box.height / 2]);
    await page.waitForTimeout(650);
    return box;
  }
  async function click(selector, pause) {
    await mark(selector);
    await page.locator(selector).first().click();
    await page.waitForTimeout(pause);
  }
  await page.goto(index + '#/'); await page.waitForTimeout(3000);
  await click('[data-tc-league-facet="workspace-v2 · dev"]', 1600);
  await click('[data-tc-league-facet="all"]', 1200);
  await click('[data-tc-league-row][data-rank="1"] [data-tc-league-value]', 2600);
  await page.mouse.wheel(0, 200); await page.waitForTimeout(700); await page.mouse.wheel(0, -200); await page.waitForTimeout(500);
  const cfg = await page.evaluate(() => new URLSearchParams(location.hash.split('?')[1] || '').get('cfg'));
  await click('[data-tc-drill-row] a[href^="#/target/"]', 3200);
  const run = `[data-tc-run-list] [data-tc-run][data-config="${cfg}"] a.ds-rl-open`;
  await click(run, 6500);
  await context.close();
  await browser.close();
  console.log('ok');
})().catch((e) => { console.error(e); process.exit(1); });
