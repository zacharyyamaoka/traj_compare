#!/usr/bin/env node
// R4's ground truth: the REAL Rerun 0.40 web viewer showing the recording "Open the same in Rerun" writes (serve.py,
// the `questions` blueprint), headless at 1440 x 900, so the HTML frame can be laid beside it. Read only: starts its own
// `rerun --serve-web` + a CORS file server on free ports and stops both at the end (pattern from the peer round's
// docs/proposals/rerun-joint-trajectory-2026-11-24/shoot.cjs; the playhead is set through window._handle).
//
//   node r4/rerun-real.cjs <file.rrd> <out.png> [--t 3.51] [--steps '<json list of {click|rclick|dblclick|hover:[x,y] | drag:[x0,y0,x1,y1], shot, wait}>']
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
const t = Number(opt('t', '3.51'));
const steps = JSON.parse(opt('steps', '[]'));
const width = Number(opt('width', 1440));
const height = Number(opt('height', 900));

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
    const file = path.join(path.dirname(rrd), path.basename(decodeURIComponent(req.url.split('?')[0])));
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
    const url = `http://127.0.0.1:${web}/?renderer=webgl&url=${encodeURIComponent(`http://127.0.0.1:${files}/${path.basename(rrd)}`)}`;
    await page.goto(url, { timeout: 120000 });
    await page.waitForTimeout(10000);
    await page.evaluate((at) => {
      const handle = window._handle;
      const recording = handle.get_active_recording_id();
      handle.set_time_for_timeline(recording, 't', Math.round(at * 1e9));
    }, t);
    await page.waitForTimeout(2500);
    await page.mouse.move(width / 2, 5);
    await page.screenshot({ path: out });
    console.log(out);
    for (const step of steps) {
      if (step.click) await page.mouse.click(step.click[0], step.click[1]);
      if (step.rclick) await page.mouse.click(step.rclick[0], step.rclick[1], { button: 'right' });
      if (step.dblclick) await page.mouse.dblclick(step.dblclick[0], step.dblclick[1]);
      if (step.hover) await page.mouse.move(step.hover[0], step.hover[1], { steps: 4 });
      if (step.drag) { await page.mouse.move(step.drag[0], step.drag[1]); await page.mouse.down(); await page.mouse.move(step.drag[2], step.drag[3], { steps: 12 }); await page.mouse.up(); }
      await page.waitForTimeout(step.wait || 1500);
      if (step.shot) {
        const name = out.replace(/\.png$/, `-${step.shot}.png`);
        await page.screenshot({ path: name });
        const now = await page.evaluate(() => { const h = window._handle; return h.get_time_for_timeline(h.get_active_recording_id(), 't') / 1e9; });
        console.log(name, 'time', now.toFixed(3));
      }
    }
  } finally {
    if (browser) await browser.close();
    server.close();
    try { process.kill(-viewer.pid, 'SIGTERM'); } catch (e) { /* already gone */ }
  }
})().catch((e) => { console.error(e); process.exit(1); });
