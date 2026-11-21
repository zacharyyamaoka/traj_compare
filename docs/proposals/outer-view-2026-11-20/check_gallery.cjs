// Drive the built gallery in headless Chrome: grid of heroes, a walkthrough hotspot + the stepper, and every variant's live
// iframe (does the real prototype boot inside the deck, and does a click inside it work?).
//   node check_gallery.cjs GALLERY.html OUT_DIR
const path = require('path');
const { chromium } = require('/home/bam/aruco-studio/web/node_modules/playwright');

(async () => {
  const [gallery, outDir] = process.argv.slice(2);
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [], network = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('request', (r) => { if (!/^(file|data|about|blob):/.test(r.url())) network.push(r.url()); });
  const out = {};
  await page.goto('file://' + gallery);
  await page.waitForFunction(() => document.documentElement.dataset.brReady === '1', null, { timeout: 60000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(outDir, 'gallery-grid.png') });
  out.heroesInView = await page.evaluate(() => [...document.querySelectorAll('#grid .cell')].map((c) => {
    const r = c.getBoundingClientRect(); return r.bottom <= innerHeight && r.right <= innerWidth;
  }));

  // Walkthrough: open V1's hero, click the still's hotspot, then the stepper's next key.
  await page.evaluate(() => window.__deck.openDeck('v1', 'main', 0));
  await page.waitForTimeout(600);
  const state = () => page.evaluate(() => {
    const host = document.querySelector('#stage .bx[data-ex="main"] .bx-html');
    const surface = host && host.shadowRoot && host.shadowRoot.querySelector('.prototype');
    return { step: window.__deck.stepper ? window.__deck.stepper.step : null, state: surface ? surface.dataset.storyState : null,
      target: surface && surface.querySelector('.story-target') ? surface.querySelector('.story-target').getAttribute('data-story-to') || 'mark' : null };
  });
  out.walk = [await state()];
  await page.screenshot({ path: path.join(outDir, 'gallery-deck-v1-s1.png') });
  await page.locator('#stage [data-story-to="s2"]').first().click();
  await page.waitForTimeout(500);
  out.walk.push(await state());
  await page.screenshot({ path: path.join(outDir, 'gallery-deck-v1-s2.png') });
  await page.keyboard.press(']');
  await page.waitForTimeout(500);
  out.walk.push(await state());
  await page.keyboard.press('[');
  await page.waitForTimeout(400);
  out.walk.push(await state());

  // Live exhibits: every variant's iframe boots on the real data and answers a click.
  out.live = {};
  for (const v of ['v1', 'v2', 'v3', 'v4', 'v5']) {
    await page.evaluate((vid) => window.__deck.openDeck(vid, 'media-1', 0), v);
    await page.waitForTimeout(2500);
    const frame = page.frames().find((f) => f.url().endsWith('/' + v + '.html') || f.url().includes('/' + v + '.html#'));
    if (!frame) { out.live[v] = 'no frame'; continue; }
    const ready = await frame.evaluate(() => document.documentElement.dataset.ready === '1').catch((e) => String(e));
    const before = await frame.evaluate(() => location.hash);
    // One real click inside the iframe: the Targets tab.
    await frame.click('nav.ov-tabs button[data-tab="targets"]');
    await page.waitForTimeout(400);
    const after = await frame.evaluate(() => ({ hash: location.hash, rows: document.querySelectorAll('.ov-ttable tbody tr').length }));
    out.live[v] = { ready, before, after };
    if (v === 'v2') await page.screenshot({ path: path.join(outDir, 'gallery-deck-v2-live.png') });
  }
  out.errors = errors;
  out.network = network;
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})();
