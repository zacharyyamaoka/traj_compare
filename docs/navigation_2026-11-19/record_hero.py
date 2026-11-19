"""Record the review report's hero clip: the real dataset site, served, walked Dataset → Target → Run (2026-11-19).

Serves ``reports/media/traj-compare-tabs-2026-11-19/dataset/site`` with ``python -m traj_compare.serve`` on a free
port (its own process group, stopped by that PID at the end, never by port), then one headless Chrome (Node
Playwright, ``recordVideo`` at 1440×900) walks: Dataset cards (a pause on the summary band) → Table → Cards → Open
target "Full-circle probe · slow" → "Lines up to N" 5 → 8 (fans become lines) → back to 5 → the history tab → one
line's ↗, whose run report the server builds on that request → the run report's question tabs. Each step
holds ~1.2–1.4 s, so the clip is ~16 s. A small grey dot
drawn over the page follows the real mouse so the clicks read in the clip (Playwright records no cursor).

Writes ``<out>/hero-raw.webm`` and ``<out>/hero-timeline.json`` (ms from the first frame of each step). WHY one
browser behind one lock, pinned and niced: the robot arm on this host may be powered and a browser stalls its CAN bus.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/navigation_2026-11-19
    flock /tmp/claude-1000/traj-tc-heavy.lock taskset -c 2-5,16,17 nice -n 19 env -u VIRTUAL_ENV ../../.venv/bin/python record_hero.py
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
MEDIA = Path("/home/bam/bam_ws/reports/media/traj-compare-tabs-2026-11-19")
SITE = MEDIA / "dataset" / "site"
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
TARGET = "full-circle-slow"
LINE = "full-circle-slow/real-01 · real"  # a v1 nominal line; its run report is built by the server on the click

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const [chrome, base, dir, target, line] = process.argv.slice(3);
const marks = [];
let t0 = Date.now();
const mark = (name) => marks.push({ name, ms: Date.now() - t0 });

// A dot that follows the real mouse events, so the clicks read in the recording.
const CURSOR = `
  addEventListener('DOMContentLoaded', () => {
    const dot = document.createElement('div');
    dot.style.cssText = 'position:fixed;left:-40px;top:-40px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;' +
      'background:rgba(40,40,40,.35);border:2px solid rgba(255,255,255,.9);box-shadow:0 0 0 1px rgba(0,0,0,.45);' +
      'pointer-events:none;z-index:2147483647;transition:transform .12s';
    document.documentElement.appendChild(dot);
    addEventListener('mousemove', (e) => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => { dot.style.transform = 'scale(.6)'; }, true);
    addEventListener('mouseup', () => { dot.style.transform = ''; }, true);
  });`;

(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const errors = [];
  let mouse = { x: 720, y: 450 };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 },
                                               recordVideo: { dir, size: { width: 1440, height: 900 } } });
    await context.addInitScript(CURSOR);
    const page = await context.newPage();
    t0 = Date.now();
    page.on('pageerror', (error) => errors.push(String(error)));
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });

    async function glide(x, y, ms = 300) {
      const steps = Math.max(6, Math.round(ms / 22));
      for (let i = 1; i <= steps; i++) {
        const f = i / steps, e = f < .5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2;
        await page.mouse.move(mouse.x + (x - mouse.x) * e, mouse.y + (y - mouse.y) * e);
        await page.waitForTimeout(ms / steps);
      }
      mouse = { x, y };
    }
    async function centre(selector) {
      const box = await page.locator(selector).first().boundingBox();
      if (!box) throw new Error('not visible: ' + selector);
      return { x: box.x + box.width / 2, y: box.y + box.height / 2, box };
    }
    async function click(selector, name, hold) {
      const at = await centre(selector);
      await glide(at.x, at.y);
      await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up();
      mark(name);
      await page.waitForTimeout(hold);
    }
    async function settleReport() {
      try {
        await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages.length && TrajCompare.state.pages[0].builtPage,
                                   null, { timeout: 20000 });
      } catch (error) { errors.push('report did not settle'); }
    }

    await page.goto(base + '/');
    await page.waitForSelector(`[data-tc-target-card="${target}"]`);
    await page.waitForTimeout(700);
    mark('cards');
    await glide(560, 300, 420);           // over the summary band
    await page.waitForTimeout(1250);
    await click('[data-tc-targets-view] [data-view="table"]', 'table', 1300);
    await click('[data-tc-targets-view] [data-view="cards"]', 'cards-again', 700);
    await click(`[data-tc-target-card="${target}"] >> text=Open target`, 'target', 0);
    await page.waitForSelector('[data-tc-run-list] [data-tc-run]');
    await page.waitForTimeout(1100);

    // "Lines up to N": drag the real slider thumb 5 → 8 (fans become lines), then back to 5.
    const slider = await page.locator('[data-tc-lines-n] input').boundingBox();
    const thumbX = (n) => slider.x + 8 + (n - 1) / 19 * (slider.width - 16);
    const midY = slider.y + slider.height / 2;
    await glide(thumbX(5), midY);
    await page.mouse.down();
    for (const n of [6, 7, 8]) { await glide(thumbX(n), midY, 160); }
    await page.mouse.up();
    mark('lines-8:' + await page.locator('[data-tc-lines-n] output').textContent());
    await page.waitForTimeout(1250);
    await page.mouse.down();
    for (const n of [7, 6, 5]) { await glide(thumbX(n), midY, 160); }
    await page.mouse.up();
    mark('lines-5:' + await page.locator('[data-tc-lines-n] output').textContent());
    await page.waitForTimeout(900);

    await click('[data-tc-target-tab][data-tab="history"]', 'history', 1350);
    const open = `[data-tc-run][data-line="${line}"] a.ds-rl-open`;
    const at = await centre(open);
    await glide(at.x, at.y);
    await Promise.all([page.waitForNavigation({ waitUntil: 'load' }),
                       (async () => { await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up(); })()]);
    mark('run-click');
    await settleReport();
    mark('run');
    await page.waitForTimeout(1250);
    const tabs = await page.$$eval('[data-tc-tabs] [data-tc-tab]', (buttons) => buttons.map((b) => b.getAttribute('data-tc-tab')));
    for (const tab of tabs.slice(1, 4)) await click(`[data-tc-tabs] [data-tc-tab="${tab}"]`, 'tab:' + tab, 1400);
    mark('end');
    const video = page.video();
    await context.close();
    console.log(JSON.stringify({ video: await video.path(), marks, tabs, url: page.url(), errors }));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });
"""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=MEDIA / "hero")
    parser.add_argument("--port", type=int, default=0, help="0: a free port")
    args = parser.parse_args()
    out = args.out.resolve()
    (out / "_build").mkdir(parents=True, exist_ok=True)
    port = args.port or free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "traj_compare.serve", str(SITE), "--port", str(port)],
        cwd=PACKAGE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True,
    )  # fmt: skip
    try:
        banner = server.stdout.readline().strip()  # "serving <root> on http://127.0.0.1:<port>/"
        print(banner, flush=True)
        time.sleep(0.3)
        driver = out / "_build" / "driver.js"
        driver.write_text(DRIVER, encoding="utf-8")
        result = subprocess.run(
            ["node", str(driver), str(PLAYWRIGHT), str(CHROME), f"http://127.0.0.1:{port}", str(out / "_build"), TARGET, LINE],
            capture_output=True, text=True, timeout=300, check=False,
        )  # fmt: skip
        if result.returncode:
            sys.exit(result.stderr[-3000:])
        report = json.loads(result.stdout.strip().splitlines()[-1])
        raw = out / "hero-raw.webm"
        Path(report.pop("video")).replace(raw)
        report["serve_banner"] = banner
        (out / "hero-timeline.json").write_text(json.dumps(report, indent=1) + "\n")
        print(raw)
        print(json.dumps(report, indent=1))
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(server.pid, signal.SIGKILL)


if __name__ == "__main__":
    main()
