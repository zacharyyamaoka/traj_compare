#!/usr/bin/env node
// V3's check of where a recording OPENS: film.cjs's loader (same viewer, same headless Chrome) but it never sets the
// playhead; it reads where the viewer put it after the load, screenshots that, and prints any ERROR / panic.
//
//   node v3/opens_at.cjs <file.rrd> <out.png> [--wait 12000] [--clicks "x,y;x,y"]
//
// Starts its own `rerun --serve-web` + file server on free ports and kills both at the end.
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const RERUN = process.env.RERUN_BIN || '/home/bam/traj_compare/.venv/bin/rerun';
const argv = process.argv.slice(2);
const rrd = path.resolve(argv[0]);
const out = path.resolve(argv[1]);
const opt = (name, fallback) => { const i = argv.indexOf(`--${name}`); return i >= 0 ? argv[i + 1] : fallback; };
const waitMs = Number(opt('wait', 12000));
const clicks = (opt('clicks', '') || '').split(';').filter(Boolean).map((c) => c.split(',').map(Number));

const freePorts = async (n) => {
  const held = [];
  for (let i = 0; i < n; i += 1) held.push(await new Promise((resolve) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => resolve(s)); }));
  const ports = held.map((s) => s.address().port);
  await Promise.all(held.map((s) => new Promise((resolve) => s.close(resolve))));
  return ports;
};

(async () => {
  fs.mkdirSync(path.dirname(out), { recursive: true });
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
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    const log = [];
    page.on('console', (m) => { if (m.type() === 'error' || /^\s*ERROR|panic/.test(m.text())) log.push(m.text().slice(0, 300)); });
    page.on('pageerror', (e) => log.push('pageerror ' + String(e).slice(0, 300)));
    const url = `http://127.0.0.1:${web}/?renderer=webgl&url=${encodeURIComponent(`http://127.0.0.1:${files}/${path.basename(rrd)}`)}`;
    await page.goto(url, { timeout: 120000 });
    await page.waitForTimeout(waitMs);
    for (const [x, y] of clicks) { await page.mouse.click(x, y); await page.waitForTimeout(1200); }
    await page.mouse.move(800, 5);
    const state = await page.evaluate(() => { const h = window._handle; const r = h.get_active_recording_id(); const t = h.get_timeline_time_range(r, 't');
      return { ns: h.get_time_for_timeline(r, 't'), min: t.min, max: t.max, panicked: h.has_panicked() }; });
    await page.screenshot({ path: out });
    console.log(out, `opened at ${(state.ns / 1e9).toFixed(3)} s of ${(state.min / 1e9).toFixed(3)}..${(state.max / 1e9).toFixed(3)} s`,
      state.panicked ? 'PANICKED' : '', JSON.stringify(log));
  } finally {
    if (browser) await browser.close();
    server.close();
    try { process.kill(-viewer.pid, 'SIGTERM'); } catch (e) { /* already gone */ }
  }
})().catch((e) => { console.error(e); process.exit(1); });
