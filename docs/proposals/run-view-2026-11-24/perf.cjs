// run-view round: JS cost of one scrub (transport.setScrub, synchronous: charts' cursors + playheads + 3D posing) vs one drawn
// frame (two rAFs, includes the WebGL draw in the headless software renderer), bam_fb fixture, 9 lines kept.
const { chromium } = require('/home/bam/aruco-studio/web/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const out = {};  // node perf.cjs r1,r2,r3,r4,r5 (server on 8853) → paste into shots/perf.json for build_gallery.py
  for (const v of (process.argv[2] || 'r1').split(',')) {
    const p = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    await p.goto(`http://127.0.0.1:8853/${v}/index.html?fixture=bam_fb&keep=3460,3461,3463,3465,3466,3467,3471,3474,3476&dry=1`);
    await p.waitForFunction(() => window.__runView && window.__runView.ready);
    await p.waitForTimeout(800);
    out[v] = await p.evaluate(async () => {
      const t = TrajCompare.state.pages[0].transport;
      const n = 60; let s = performance.now();
      for (let i = 0; i < n; i++) t.setScrub(0.5 + i * 0.05);
      const js = (performance.now() - s) / n;
      const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      s = performance.now();
      for (let i = 0; i < 10; i++) { t.setScrub(1 + i * 0.1); await frame(); }
      return { jsPerScrubMs: +js.toFixed(2), scrubPlusDrawnFrameMs: +((performance.now() - s) / 10).toFixed(1) };
    });
    await p.context().close();
  }
  console.log(JSON.stringify(out));
  await b.close();
})();
