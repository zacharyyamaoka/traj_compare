#!/usr/bin/env node
// R1's copy of the round's shoot.cjs that lands the playhead by CLICKING the time bar (x = 247 + 1145 · t / --duration at
// 1600 px), and can click a tab (--tab x,y) before the shot. WHY: the 0.40 web viewer ignores the data URL's #when=t@<s>
// under every TimePanel state and with no blueprint at all (tested 2026-11-24: paused -> 0, playing -> from 0, following
// or none -> the end), so shoot.cjs's stills all land at one time. Each still's time field shows where it landed.
//   node r1/shoot_at_time.cjs r1/workspace-dev-029.rrd shots/r1/at-time/dev-029 --times 0.4,1.8,3.2 --duration 3.2
//   node r1/shoot_at_time.cjs r1/workspace-dev-029.rrd shots/r1/tabs/dev-029-how-fast --times 1.8 --duration 3.2 --tab 1167,50
// Screenshots of a recording in the REAL Rerun 0.40 web viewer, headless (the dispatcher's tool for this round; lanes run
// it, never edit it). Starts its own `rerun --serve-web` on free ports and a CORS file server, kills both at the end.
//
//   node shoot.cjs <file.rrd> <out-prefix> [--blueprint file.rbl] [--times 0.5,2.1,end] [--width 1600 --height 1000]
//
// Writes <out-prefix>-<k>-t<time>.png for each time (default: the last frame). Same flags as docs/rerun_layouts/shoot.py
// (renderer=webgl). The playhead comes from Rerun's link fragment #when=<timeline>@<t>s (--timeline, default t); LOOK at
// each still: the time field shows where it landed.

const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const { chromium } = require(process.env.TRAJ_COMPARE_PLAYWRIGHT || '/home/bam/aruco-studio/web/node_modules/playwright');

const RERUN = process.env.RERUN_BIN || '/home/bam/traj_compare/.venv/bin/rerun';
const argv = process.argv.slice(2);
const rrd = path.resolve(argv[0]);
const prefix = path.resolve(argv[1]);
const opt = (name, fallback) => { const i = argv.indexOf(`--${name}`); return i >= 0 ? argv[i + 1] : fallback; };
const blueprint = opt('blueprint', null);
const times = (opt('times', 'end')).split(',');
const width = Number(opt('width', 1600));
const height = Number(opt('height', 1000));
const waitMs = Number(opt('wait', 9000));
const timeline = opt('timeline', 't');
const duration = Number(opt('duration', '0'));
const tab = opt('tab', null);

// WHY all three held open until each has a number: closing one before asking for the next can hand the same port back
const freePorts = async (n) => {
  const held = [];
  for (let i = 0; i < n; i += 1) held.push(await new Promise((resolve) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => resolve(s)); }));
  const ports = held.map((s) => s.address().port);
  await Promise.all(held.map((s) => new Promise((resolve) => s.close(resolve))));
  return ports;
};

(async () => {
  const [web, grpc, files] = await freePorts(3);
  const roots = [path.dirname(rrd), ...(blueprint ? [path.dirname(path.resolve(blueprint))] : [])];
  const server = http.createServer((req, res) => {
    const name = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '');
    const [rootIndex, ...rest] = name.split('/');
    const file = path.join(roots[Number(rootIndex)] || roots[0], rest.join('/'));
    if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  }).listen(files, '127.0.0.1');
  const viewer = spawn(RERUN, ['--serve-web', '--web-viewer-port', String(web), '--port', String(grpc)], { stdio: 'ignore', detached: true });
  let browser;
  try {
    // WHY poll: the viewer's web server takes 2-10 s to come up; a page loaded before it is a blank 404
    for (let i = 0; i < 60; i += 1) {
      const up = await new Promise((resolve) => http.get(`http://127.0.0.1:${web}/`, (r) => { r.resume(); resolve(r.statusCode === 200); }).on('error', () => resolve(false)));
      if (up) break;
      await new Promise((r) => setTimeout(r, 500));
    }
    browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true,
      // WHY no Vulkan/ANGLE flags (the Nov 19 shooter had them): here they failed Rerun's mesh shaders at random (blank
      // page); the robot-description viewer's flags reach the NVIDIA driver (bam_ws memory robot-description-viewer)
      args: ['--enable-webgl', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
    const page = await browser.newPage({ viewport: { width, height } });
    const log = [];
    page.on('console', (m) => { if (m.type() === 'error' || /panic|error/i.test(m.text())) log.push(m.text().slice(0, 300)); });
    page.on('pageerror', (e) => log.push('pageerror ' + String(e).slice(0, 300)));
    for (let k = 0; k < times.length; k += 1) {
      const t = times[k];
      // WHY a link fragment, not typing into the time field: the field is egui on a canvas, and typing into it headless
      // blanked the page; Rerun's own share links carry the playhead as #when=<timeline>@<time> on the data URL
      const data = `http://127.0.0.1:${files}/0/${path.basename(rrd)}` + (t === 'end' ? '' : `#when=${timeline}@${t}s`);
      let url = `http://127.0.0.1:${web}/?renderer=webgl&url=${encodeURIComponent(data)}`;
      if (blueprint) url += `&url=${encodeURIComponent(`http://127.0.0.1:${files}/1/${path.basename(blueprint)}`)}`;
      await page.goto(url, { timeout: 120000 });
      await page.waitForTimeout(waitMs);
      // scratch-only: the #when fragment is not honoured (paused -> t=0), so click the time bar at t / duration
      if (t !== 'end' && duration > 0) {
        const x0 = 247, x1 = 1392;  // the scrub bar's ends at 1600 px, measured on the stills
        await page.mouse.click(x0 + (x1 - x0) * Number(t) / duration, 986);
        await page.waitForTimeout(1500);
      }
      if (tab) { const [x, y] = tab.split(',').map(Number); await page.mouse.click(x, y); await page.waitForTimeout(1500); }
      await page.mouse.move(width / 2, 5);
      const out = `${prefix}-${k + 1}-t${t}.png`;
      await page.screenshot({ path: out });
      console.log(out);
      if (process.env.SHOOT_DEBUG) console.log(JSON.stringify(log.splice(0)));
    }
  } finally {
    if (browser) await browser.close();
    server.close();
    try { process.kill(-viewer.pid, 'SIGTERM'); } catch (e) { /* already gone */ }
  }
})().catch((e) => { console.error(e); process.exit(1); });

