#!/usr/bin/env node
// R5's stills at exact times, in the REAL Rerun 0.40 web viewer, headless. A companion to the round's shoot.cjs (which
// stays the gate: it is run unchanged, with SHOOT_DEBUG): here the playhead is set by pausing and clicking the time
// panel's scrubber, because a link's #when= did not land in this viewer (NOTES.md has the probe).
//
//   node shoot_at.cjs <file.rrd> <out-prefix> --duration 3.2 --times 0.4,1.8,end [--click 150,50] [--hover 300,700]
//
// --click x,y is clicked once after pausing (a tab, say); --hover x,y is hovered after the last time.
//
// Writes <out-prefix>-at-<time>.png (and -hover.png). Geometry is R5's blueprint at 1600 x 1000: the collapsed time
// panel's play button at (27, 986) and its scrubber from x 245 (t = 0) to x 1395 (t = duration) on y 986; LOOK at
// each still, the time field (bottom right) says where it landed. Run one at a time: four in parallel on the
// software rasterizer missed the pause click (the stills came out at the wrong times).

const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const argv = process.argv.slice(2);
const rrd = path.resolve(argv[0]);
const prefix = path.resolve(argv[1]);
const opt = (name, fallback) => { const i = argv.indexOf(`--${name}`); return i >= 0 ? argv[i + 1] : fallback; };
const duration = Number(opt('duration', '1'));
const times = opt('times', 'end').split(',');
const hover = opt('hover', null);
const click = opt('click', null);
const width = Number(opt('width', 1600));
const height = Number(opt('height', 1000));
const [scrubStart, scrubEnd, scrubY] = [245, 1395, 986];

const freePorts = async (n) => {
  const held = [];
  for (let i = 0; i < n; i += 1) held.push(await new Promise((resolve) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => resolve(s)); }));
  const ports = held.map((s) => s.address().port);
  await Promise.all(held.map((s) => new Promise((resolve) => s.close(resolve))));
  return ports;
};

(async () => {
  const [web, grpc, files] = await freePorts(3);
  const server = http.createServer((req, res) => {
    const file = path.join(path.dirname(rrd), decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, ''));
    if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  }).listen(files, '127.0.0.1');
  const viewer = spawn('/home/bam/traj_compare/.venv/bin/rerun', ['--serve-web', '--web-viewer-port', String(web), '--port', String(grpc)],
    { stdio: 'ignore', detached: true });
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
    page.on('console', (m) => { if (m.type() === 'error' || /panic|error/i.test(m.text())) log.push(m.text().slice(0, 300)); });
    page.on('pageerror', (e) => log.push('pageerror ' + String(e).slice(0, 300)));
    const data = `http://127.0.0.1:${files}/${path.basename(rrd)}`;
    await page.goto(`http://127.0.0.1:${web}/?renderer=webgl&url=${encodeURIComponent(data)}`, { timeout: 120000 });
    await page.waitForTimeout(9000);
    await page.mouse.click(27, scrubY);  // pause: R5's blueprint opens playing
    await page.waitForTimeout(500);
    if (click) {
      const [x, y] = click.split(',').map(Number);
      await page.mouse.click(x, y);
      await page.waitForTimeout(1500);
    }
    for (const t of times) {
      const seconds = t === 'end' ? duration : Number(t);
      await page.mouse.click(scrubStart + (seconds / duration) * (scrubEnd - scrubStart), scrubY);
      await page.mouse.move(width / 2, 5);
      await page.waitForTimeout(1500);
      const out = `${prefix}-at-${t}.png`;
      await page.screenshot({ path: out });
      console.log(out);
    }
    if (hover) {
      const [x, y] = hover.split(',').map(Number);
      await page.mouse.move(x - 4, y - 4);
      await page.waitForTimeout(300);
      await page.mouse.move(x, y);
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `${prefix}-hover.png` });
      console.log(`${prefix}-hover.png`);
    }
    const errors = log.filter((line) => /ERROR/.test(line));
    console.log(JSON.stringify({ console_lines: log.length, error_lines: errors }));
  } finally {
    if (browser) await browser.close();
    server.close();
    try { process.kill(-viewer.pid, 'SIGTERM'); } catch (e) { /* already gone */ }
  }
})().catch((e) => { console.error(e); process.exit(1); });
