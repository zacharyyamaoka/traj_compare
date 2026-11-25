#!/usr/bin/env node
// Frames of one recording in the REAL Rerun 0.40 web viewer, headless, loaded ONCE (the dispatcher's tool; lanes run it,
// never edit it). Like ../rerun-joint-trajectory-2026-11-24/shoot.cjs, but the page loads once and the playhead is set
// through the viewer's own handle (window._handle.set_time_for_timeline, ns) for every frame, so a 33-frame hero takes
// about a minute instead of seven. Prints the time each frame landed on and any ERROR / panic.
//
//   node film.cjs <file.rrd> <out-dir> [--times 0,0.1,...|--every 0.1] [--clicks "x,y;x,y"] [--prefix f] [--width 1600 --height 1000]
//
// --clicks: pixel clicks done once after the load, before the frames (pick a tab). --times "end" = the last sample.
// Frames are <out-dir>/<prefix>-<k>-t<time>.png. Starts its own `rerun --serve-web` + file server on free ports and kills
// both at the end. Open the recording PAUSED (rrb.TimePanel(play_state="paused")) or frames drift. LOOK at the frames.
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const RERUN = process.env.RERUN_BIN || '/home/bam/traj_compare/.venv/bin/rerun';
const argv = process.argv.slice(2);
const rrd = path.resolve(argv[0]);
const outDir = path.resolve(argv[1]);
const opt = (name, fallback) => { const i = argv.indexOf(`--${name}`); return i >= 0 ? argv[i + 1] : fallback; };
const every = opt('every', null);
const width = Number(opt('width', 1600));
const height = Number(opt('height', 1000));
const prefix = opt('prefix', 'f');
const clicks = (opt('clicks', '') || '').split(';').filter(Boolean).map((c) => c.split(',').map(Number));
const waitMs = Number(opt('wait', 12000));
const settleMs = Number(opt('settle', 900));

const freePorts = async (n) => {
  const held = [];
  for (let i = 0; i < n; i += 1) held.push(await new Promise((resolve) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => resolve(s)); }));
  const ports = held.map((s) => s.address().port);
  await Promise.all(held.map((s) => new Promise((resolve) => s.close(resolve))));
  return ports;
};

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const [web, grpc, files] = await freePorts(3);
  const server = http.createServer((req, res) => {
    const file = path.join(path.dirname(rrd), decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, ''));
    if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  }).listen(files, '127.0.0.1');
  const viewer = spawn(RERUN, ['--serve-web', '--web-viewer-port', String(web), '--port', String(grpc)], { stdio: 'ignore', detached: true });
  let browser;
  try {
    for (let i = 0; i < 60; i += 1) {
      const up = await new Promise((resolve) => http.get(`http://127.0.0.1:${web}/`, (r) => { r.resume(); resolve(r.statusCode === 200); }).on('error', () => resolve(false)));
      if (up) break;
      await new Promise((r) => setTimeout(r, 500));
    }
    browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true,
      args: ['--enable-webgl', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
    const page = await browser.newPage({ viewport: { width, height } });
    const log = [];
    page.on('console', (m) => { if (m.type() === 'error' || /^\s*ERROR|panic/.test(m.text())) log.push(m.text().slice(0, 300)); });
    page.on('pageerror', (e) => log.push('pageerror ' + String(e).slice(0, 300)));
    const url = `http://127.0.0.1:${web}/?renderer=webgl&url=${encodeURIComponent(`http://127.0.0.1:${files}/${path.basename(rrd)}`)}`;
    await page.goto(url, { timeout: 120000 });
    await page.waitForTimeout(waitMs);
    const range = await page.evaluate(() => { const h = window._handle; const r = h.get_active_recording_id(); const t = h.get_timeline_time_range(r, 't'); return { r, min: t.min, max: t.max }; });
    let times = (opt('times', null) || '').split(',').filter(Boolean);
    if (every) { times = []; for (let ns = range.min; ns <= range.max + 1; ns += Number(every) * 1e9) times.push(String(Math.round(ns) / 1e9)); }
    for (const [x, y] of clicks) { await page.mouse.click(x, y); await page.waitForTimeout(1200); }
    for (let k = 0; k < times.length; k += 1) {
      const at = times[k];
      const ns = at === 'end' ? range.max : Math.round(Number(at) * 1e9);
      await page.evaluate(([r, value]) => window._handle.set_time_for_timeline(r, 't', value), [range.r, ns]);
      await page.waitForTimeout(settleMs);
      await page.mouse.move(width / 2, 5);
      const state = await page.evaluate((r) => ({ ns: window._handle.get_time_for_timeline(r, 't'), panicked: window._handle.has_panicked() }), range.r);
      const out = path.join(outDir, `${prefix}-${k}-t${at}.png`);
      await page.screenshot({ path: out });
      console.log(out, `playhead ${(state.ns / 1e9).toFixed(3)} s`, state.panicked ? 'PANICKED' : '', JSON.stringify(log.splice(0)));
    }
  } finally {
    if (browser) await browser.close();
    server.close();
    try { process.kill(-viewer.pid, 'SIGTERM'); } catch (e) { /* already gone */ }
  }
})().catch((e) => { console.error(e); process.exit(1); });
