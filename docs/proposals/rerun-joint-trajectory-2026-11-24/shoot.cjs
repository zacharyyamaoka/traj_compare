#!/usr/bin/env node
// The round's stills in the REAL Rerun 0.40 web viewer, headless (the dispatcher's tool; lanes run it, never edit it).
// Starts its own `rerun --serve-web` + a CORS file server on free ports, kills both at the end. The playhead is SET through
// the viewer's own handle after the load (R2's seek, adopted round-wide 2026-11-24), and the time it landed on is printed.
//
//   node shoot.cjs <file.rrd> <out-prefix> [--blueprint file.rbl] [--times 0.4,1.8,end] [--timeline t] [--tab x,y]
//
// A recording whose blueprint PLAYS keeps moving after the seek (stills drift; the printed time says where); open PAUSED
// (rrb.TimePanel(play_state="paused")) for exact stills. Run one at a time. Prints has_panicked() and errors per still.
// WHY (measured in the real 0.40 web viewer, 2026-11-24): with a paused blueprint every #when=t@<s> form tried
// (1.8s, +1.8s, 1.800s, 1800ms, time_selection=) left the playhead at +0.000 s; with a playing one it is wherever
// playback drifted (software rendering plays ~5x slower than real time); arrow-key seeks drop presses at random.
// window._handle (the WebHandle the @rerun-io/web-viewer package drives: set_time_for_timeline, in nanoseconds on a
// duration timeline) lands exactly. Prints the time read back and has_panicked() per still. LOOK at each still.

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
const timeline = opt('timeline', 't');
const tab = opt('tab', null);
const width = Number(opt('width', 1600));
const height = Number(opt('height', 1000));
const waitMs = Number(opt('wait', 9000));

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
    page.on('response', (r) => { if (r.status() >= 400) log.push(`HTTP ${r.status()} ${r.url().slice(0, 160)}`); });
    for (let k = 0; k < times.length; k += 1) {
      const t = times[k];
      let url = `http://127.0.0.1:${web}/?renderer=webgl&url=${encodeURIComponent(`http://127.0.0.1:${files}/0/${path.basename(rrd)}`)}`;
      if (blueprint) url += `&url=${encodeURIComponent(`http://127.0.0.1:${files}/1/${path.basename(blueprint)}`)}`;
      await page.goto(url, { timeout: 120000 });
      await page.waitForTimeout(waitMs);
      const landed = await page.evaluate(([name, at]) => {
        const handle = window._handle;
        const recording = handle.get_active_recording_id();
        const range = handle.get_timeline_time_range(recording, name);
        handle.set_time_for_timeline(recording, name, at === 'end' ? range.max : Math.round(Number(at) * 1e9));
        return recording;
      }, [timeline, t]);
      await page.waitForTimeout(2500);
      if (tab) { const [x, y] = tab.split(',').map(Number); await page.mouse.click(x, y); await page.waitForTimeout(1500); }
      await page.mouse.move(width / 2, 5);
      const state = await page.evaluate(([name, recording]) => ({ ns: window._handle.get_time_for_timeline(recording, name),
        panicked: window._handle.has_panicked() }), [timeline, landed]);
      const out = `${prefix}-${k + 1}-t${t}.png`;
      await page.screenshot({ path: out });
      console.log(out, `playhead ${(state.ns / 1e9).toFixed(3)} s`, state.panicked ? 'PANICKED' : '', JSON.stringify(log.splice(0)));
    }
  } finally {
    if (browser) await browser.close();
    server.close();
    try { process.kill(-viewer.pid, 'SIGTERM'); } catch (e) { /* already gone */ }
  }
})().catch((e) => { console.error(e); process.exit(1); });
