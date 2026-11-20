"""Record the scale-and-signals review's hero clip from the real bench sites, one server for three robots (2026-11-20).

Serves the folder holding the arm_motion_bench's three rebuilt sites (``ur5e/``, ``pendulum/``, ``bam_fb/``) with
``python -m traj_compare.serve`` on a free port, in its own process group, stopped by that PID at the end (never by
port). The root has no index.html, so ``/`` is the landing page (NAVIGATION.md C3). One headless Chrome (Node
Playwright, ``recordVideo`` at 1440×900) then walks:

landing page → UR5e → its summary and the bench's scorecard → fast scroll into the 1006 target cards (each chart is a
placeholder until its ``targets/<slug>.js`` arrives, C5) → a jump to card 496, "workspace-dev-005 · workspace-v1 ·
speed 1", as Ctrl-F would → Open target (four controllers in four colours, C4; "drawn at 50 Hz", C5) → one line's ↗,
whose run report the server builds on that click (C3: a site one level below the served root).

The line opened is the first candidate whose ``report.html`` does not exist yet, so the build on the click is real.
A small grey dot drawn over the page follows the real mouse (Playwright records no cursor).

Writes ``<out>/hero-raw.webm``, ``<out>/hero-timeline.json`` (ms from the first frame of each step), then
``<out>/hero.mp4`` (H.264, 1200 px wide, muted, faststart) and ``<out>/hero.gif`` (480 px fallback). WHY one browser
behind one lock, pinned and niced: the robot arm on this host may be powered and a browser stalls its CAN bus.

    flock /tmp/claude-1000/traj-tc-heavy.lock taskset -c 2-5,16,17 nice -n 19 env -u VIRTUAL_ENV /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/scale_signals_2026-11-20/record_hero.py --sites <folder holding ur5e/ pendulum/ bam_fb/>
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
# The bench's three sites rebuilt with the new code (its own dashboard.py build --no-hero --display-hz 50), 2026-11-20.
SITES = Path(
    "/tmp/claude-1000/-home-bam--claude-jidoka-spares-spare-rrpsDw/b331c896-01c1-4684-837b-e19d9e0e6e2f/scratchpad/bench-after"
)
MEDIA = PACKAGE / "reports" / "media" / "traj-compare-scale-signals-2026-11-20"
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
FFMPEG = "/usr/bin/ffmpeg"
PIN = ["taskset", "-c", "2-5,16,17", "nice", "-n", "19"]
# WHY the bench's interpreter serves: each run's manifest names the bench's robot hook
# (``arm_motion_bench.dashboard:ur5e_robot``), which needs mujoco; traj_compare's own .venv has none and answers that
# build with a 500. The bench's .venv imports traj_compare from this checkout (editable), so the code served is main's.
SERVE_PYTHON = Path("/home/bam/arm_motion_bench/.venv/bin/python")

SITE = "ur5e"
TARGET = "workspace-dev-005-workspace-v1-speed-1"  # the target of the bench's own "before" shot (ur5e-2-target.png)
# (data-line in the target's line list, run folder): the first whose report.html is missing is opened.
LINES = [
    (f"workspace-dev-005 · workspace-v1 · speed 1 · {config} · r{repeat} · sim",
     f"workspace-dev-005-workspace-v1-speed-1-{config.replace('_', '-')}-r{repeat}")
    for config in ("ctc_tuned", "id_pd", "ctc_model_err") for repeat in (0, 1, 2)
]  # fmt: skip

CURSOR = r"""
  addEventListener('DOMContentLoaded', () => {
    const dot = document.createElement('div');
    dot.style.cssText = 'position:fixed;left:-40px;top:-40px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;' +
      'background:rgba(40,40,40,.35);border:2px solid rgba(255,255,255,.9);box-shadow:0 0 0 1px rgba(0,0,0,.45);' +
      'pointer-events:none;z-index:2147483647;transition:transform .12s';
    document.documentElement.appendChild(dot);
    addEventListener('mousemove', (e) => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => { dot.style.transform = 'scale(.6)'; }, true);
    addEventListener('mouseup', () => { dot.style.transform = ''; }, true);
  });"""

# Helpers every driver shares: glide the mouse, click a selector, count chart placeholders in view.
HELPERS = r"""
let mouse = { x: 720, y: 450 };
async function glide(page, x, y, ms = 320) {
  const steps = Math.max(6, Math.round(ms / 22));
  for (let i = 1; i <= steps; i++) {
    const f = i / steps, e = f < .5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2;
    await page.mouse.move(mouse.x + (x - mouse.x) * e, mouse.y + (y - mouse.y) * e);
    await page.waitForTimeout(ms / steps);
  }
  mouse = { x, y };
}
async function centre(page, selector) {
  const box = await page.locator(selector).first().boundingBox();
  if (!box) throw new Error('not visible: ' + selector);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}
async function press(page) { await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up(); }
const waitsInView = (page) => page.evaluate(() => [...document.querySelectorAll('.ds-wait')]
  .filter((e) => { const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight; }).length);
async function settled(page, timeout = 30000) {   // every chart in view drawn (no placeholder left)
  const start = Date.now();
  while (Date.now() - start < timeout) { if (await waitsInView(page) === 0) return Date.now() - start; await page.waitForTimeout(40); }
  throw new Error('charts in view never drew');
}
"""

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const [chrome, base, dir, site, target, line, cursor] = process.argv.slice(3);
const marks = [];
let t0 = Date.now();
const mark = (name, extra) => marks.push(Object.assign({ name, ms: Date.now() - t0 }, extra || {}));
""" + HELPERS + r"""
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const errors = [], placeholders = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 },
                                               recordVideo: { dir, size: { width: 1440, height: 900 } } });
    await context.addInitScript(cursor);
    const page = await context.newPage();
    t0 = Date.now();
    page.on('pageerror', (error) => errors.push(String(error)));
    page.on('console', (message) => { if (message.type() === 'error' && !/favicon/.test(JSON.stringify(message.location()))) errors.push(message.text()); });
    page.on('response', (r) => { if (r.status() >= 400 && !/favicon/.test(r.url())) errors.push(r.status() + ' ' + r.url()); });

    // 1. the landing page: one link per site under the served root
    await page.goto(base + '/');
    await page.waitForSelector(`[data-tc-site="${site}"]`);
    mark('landing', { sites: await page.$$eval('[data-tc-site]', (a) => a.map((x) => x.textContent)) });
    await page.waitForTimeout(300);
    let at = await centre(page, `[data-tc-site="${site}"]`);
    await glide(page, at.x - 100, at.y, 450);
    await page.waitForTimeout(200);
    const loadStart = Date.now();
    await Promise.all([page.waitForNavigation({ waitUntil: 'load' }), press(page)]);
    await page.waitForSelector('[data-tc-target-card]');
    mark('site', { load_ms: Date.now() - loadStart, cards: await page.$$eval('[data-tc-target-card]', (c) => c.length) });
    await page.waitForTimeout(600);

    // 2. a fast scroll through the scorecard into the cards; then slower through the cards
    await glide(page, 720, 520, 260);
    const firstCard = await page.evaluate(() => document.querySelector('[data-tc-target-card]').getBoundingClientRect().top + scrollY);
    while (await page.evaluate(() => scrollY) < firstCard - 1500) { await page.mouse.wheel(0, 1600); await page.waitForTimeout(70); }
    await page.mouse.wheel(0, firstCard - 140 - await page.evaluate(() => scrollY));
    await page.waitForTimeout(60);
    mark('cards');
    for (let i = 0; i < 4; i++) {
      await page.mouse.wheel(0, 700); await page.waitForTimeout(40);
      placeholders.push({ ms: Date.now() - t0, step: 'scroll', in_view: await waitsInView(page) });
      await page.waitForTimeout(240);
    }
    await page.waitForTimeout(250);

    // 3. a jump to the target's card (card 496 of 1006), as Ctrl-F would: its charts load as they arrive
    await page.evaluate((t) => document.querySelector(`[data-tc-target-card="${t}"]`).scrollIntoView({ block: 'center' }), target);
    mark('jump', { index: await page.evaluate((t) => [...document.querySelectorAll('[data-tc-target-card]')].findIndex((c) => c.getAttribute('data-tc-target-card') === t), target) });
    placeholders.push({ ms: Date.now() - t0, step: 'jump', in_view: await waitsInView(page) });
    const drewIn = await settled(page);
    mark('jump-drawn', { after_ms: drewIn });
    await page.waitForTimeout(900);

    // 4. Open target: four configs in four colours, every chart "drawn at 50 Hz"
    at = await centre(page, `[data-tc-target-card="${target}"] >> text=Open target`);
    await glide(page, at.x, at.y, 380);
    await press(page);
    await page.waitForSelector('[data-tc-run-list] [data-tc-run]');
    await settled(page);
    mark('target', { rate: await page.$eval('[data-tc-drawn-rate]', (r) => r.textContent) });
    await page.waitForTimeout(500);
    const chart = await page.locator('.ds-plot canvas, .ds-plot svg').first().boundingBox();
    if (chart) { await glide(page, chart.x + chart.width * 0.55, chart.y + chart.height * 0.45, 450); }
    await page.waitForTimeout(1100);

    // 5. one line's ↗: the server builds that run's report on this request
    const open = `[data-tc-run][data-line="${line}"] a.ds-rl-open`;
    await page.locator(open).first().scrollIntoViewIfNeeded();
    at = await centre(page, open);
    await glide(page, at.x, at.y, 420);
    await page.waitForTimeout(150);
    const clicked = Date.now();
    await Promise.all([page.waitForNavigation({ waitUntil: 'load', timeout: 120000 }), press(page)]);
    mark('run-click');
    await page.waitForFunction(() => window.TrajCompare && TrajCompare.state.pages.length && TrajCompare.state.pages[0].builtPage,
                               null, { timeout: 60000 });
    mark('run', { build_and_load_ms: Date.now() - clicked, url: page.url() });
    await glide(page, 900, 420, 450);
    await page.waitForTimeout(1500);
    mark('end');
    const video = page.video();
    await context.close();
    console.log(JSON.stringify({ video: await video.path(), marks, placeholders, errors }));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });
"""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextlib.contextmanager
def serving(root: Path, python: Path = SERVE_PYTHON) -> Iterator[tuple[str, str]]:
    """``python -m traj_compare.serve root`` on a free port, in its own process group; yields (base URL, banner).

    Stopped by that process group's PID on exit, never by port (another session's server may hold any port here).
    """

    port = free_port()
    server = subprocess.Popen(
        [*PIN, str(python), "-m", "traj_compare.serve", str(root), "--port", str(port)],
        cwd=PACKAGE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True,
    )  # fmt: skip
    try:
        banner = server.stdout.readline().strip()  # "serving <root> on http://127.0.0.1:<port>/"
        if "serving" not in banner:
            raise SystemExit(f"server did not start: {banner}")
        time.sleep(0.3)
        yield f"http://127.0.0.1:{port}", banner
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(server.pid, signal.SIGKILL)
            server.wait(5)


def run_driver(source: str, scratch: Path, *args: str, timeout: int = 600) -> dict:
    """Run a Node Playwright driver (its source written to ``scratch``); returns the JSON its last stdout line holds."""

    scratch.mkdir(parents=True, exist_ok=True)
    driver = scratch / "driver.cjs"
    driver.write_text(source, encoding="utf-8")
    result = subprocess.run(["node", str(driver), str(PLAYWRIGHT), str(CHROME), *args],
                            capture_output=True, text=True, timeout=timeout, check=False)  # fmt: skip
    if result.returncode:
        raise SystemExit(result.stderr[-3000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def ffmpeg(*args: str) -> None:
    subprocess.run([*PIN, FFMPEG, "-v", "error", "-y", *args], check=True)


def convert(raw: Path, out: Path, start_s: float, end_s: float) -> tuple[Path, Path]:
    """The raw recording, trimmed to [start_s, end_s], as a muted H.264 mp4 (1200 px) and a 480 px GIF fallback."""

    mp4, gif = out / "hero.mp4", out / "hero.gif"
    span = ["-ss", f"{start_s:.2f}", "-to", f"{end_s:.2f}", "-i", str(raw)]
    # WHY CRF 30 at 1200 px and 25 fps: UI text stays readable and the clip fits the 1.9 MB page with its stills.
    # WHY the GIF is 480 px, 3 fps, 32 colours: it is only the fallback for a viewer that cannot play H.264.
    ffmpeg(*span, "-an", "-vf", "fps=25,scale=1200:-2:flags=lanczos", "-c:v", "libx264", "-preset", "veryslow",
           "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4))  # fmt: skip
    palette = out / "_build" / "palette.png"
    ffmpeg(*span, "-vf", "fps=3,scale=480:-2:flags=lanczos,palettegen=max_colors=32:stats_mode=diff", str(palette))
    ffmpeg(*span, "-i", str(palette), "-lavfi",
           "fps=3,scale=480:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=none:diff_mode=rectangle", str(gif))  # fmt: skip
    return mp4, gif


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sites", type=Path, default=SITES, help="the folder holding the bench's site folders")
    parser.add_argument("--out", type=Path, default=MEDIA / "hero")
    parser.add_argument("--python", type=Path, default=SERVE_PYTHON if SERVE_PYTHON.is_file() else Path(sys.executable),
                        help="the interpreter that serves (it must import the sites' robot hooks)")
    args = parser.parse_args()
    sites, out = args.sites.resolve(), args.out.resolve()
    (out / "_build").mkdir(parents=True, exist_ok=True)
    unbuilt = [(line, slug) for line, slug in LINES if not (sites / SITE / "runs" / slug / "report.html").is_file()]
    if not unbuilt:
        raise SystemExit(f"every candidate line's report.html already exists under {sites / SITE / 'runs'}")
    line, slug = unbuilt[0]
    with serving(sites, args.python) as (base, banner):
        print(banner, flush=True)
        report = run_driver(DRIVER, out / "_build", base, str(out / "_build"), SITE, TARGET, line, CURSOR)
    raw = out / "hero-raw.webm"
    Path(report.pop("video")).replace(raw)
    built = sites / SITE / "runs" / slug / "report.html"
    report.update(serve_banner=banner, line=line, report_built_on_click=built.is_file(), report=str(built))
    marks = {mark["name"]: mark["ms"] / 1000 for mark in report["marks"]}
    # Trim the white frames before the landing page painted; keep everything after.
    start = max(0.0, marks["landing"] - 0.15)
    mp4, gif = convert(raw, out, start, marks["end"])
    report.update(trim_s=[start, marks["end"]], duration_s=round(marks["end"] - start, 2),
                  mp4_bytes=mp4.stat().st_size, gif_bytes=gif.stat().st_size)  # fmt: skip
    (out / "hero-timeline.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
