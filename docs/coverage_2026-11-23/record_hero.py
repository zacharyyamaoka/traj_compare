"""Record the coverage-viewer review's hero clip from the real UR5e coverage pages (2026-11-23).

The pages are static and open from disk (``write_coverage_page``: one self-contained ``.html``, no server), so one
headless Chrome (Node Playwright, ``recordVideo`` at 1440×900, a fresh context so the page's remembered controls start
at their defaults: viridis, linear) walks them as a reader would:

landing page → "UR5e · Entire Workspace · Dev + holdout at full speed" → Overview (the numbers and the ridgeline) →
Limits → One joint (the q × qd heatmap: Colours viridis → magma → viridis, Reverse on and off, Scale linear → equalized
→ linear) → All joints (parallel coordinates) → Tool position (projections, then the 3-D voxels, dragged to orbit) →
Tool orientation (the direction sphere, dragged) → 3-D proposals (the bottom-right drop-down: height map → joint
skyline → workspace terrain) → Trajectories (one row clicked) → back to One joint, where that trajectory is the black
path in the spaghetti.

A small grey dot drawn over the page follows the real mouse (Playwright records no cursor). Writes
``<out>/hero-timeline.json`` (ms of each step from the first recorded frame, and seconds into ``hero.mp4``),
``<out>/hero.mp4`` (H.264, 1200 px wide, muted, faststart), ``<out>/hero.gif`` (480 px fallback) and
``<out>/hero-poster.jpg`` (the clip's first frame, the painted landing page); the raw ``hero-raw.webm`` stays in
``BUILD`` (gitignored ``.cache/``). WHY pinned and niced: a busy shared box, and the robot arm on this host may be
powered.

    taskset -c 2-5,16,17 nice -n 10 python3 /home/bam/traj_compare/docs/coverage_2026-11-23/record_hero.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
# The bench's UR5e coverage build (arm_motion_bench docs/build_ur_coverage_1123.py), one page per dataset × subset.
PAGES = Path("/home/bam/arm_motion_bench/reports/media/coverage-viewer")
FIRST = "ur5e_alone-workspace/full-speed/index.html"  # the landing page's "Start with" link
MEDIA = PACKAGE / "reports" / "media" / "coverage-viewer-2026-11-23"
# WHY outside MEDIA: the raw webm, the driver and the palette are scratch; MEDIA holds only what the report embeds.
BUILD = PACKAGE / ".cache" / "coverage_report_2026-11-23"
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")
FFMPEG = "/usr/bin/ffmpeg"
PIN = ["taskset", "-c", "2-5,16,17", "nice", "-n", "10"]

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

# Helpers both drivers share: glide the mouse, find a selector's centre, press, smooth wheel scroll, a tab's bar height.
HELPERS = r"""
let mouse = { x: 720, y: 450 };
const ease = (f) => f < .5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2;
// WHY paced by the clock, not by a fixed wait per step: under recordVideo each input round trip costs 20-50 ms, so
// fixed waits doubled every glide and the clip ran 36 s. A step that is late does not wait at all.
async function paced(page, ms, steps, step) {
  const start = Date.now();
  for (let i = 1; i <= steps; i++) {
    await step(ease(i / steps));
    const left = start + (ms * i) / steps - Date.now();
    if (left > 0) await page.waitForTimeout(left);
  }
}
async function glide(page, x, y, ms = 320) {
  const from = { ...mouse };
  await paced(page, ms, Math.max(6, Math.round(ms / 22)),
              (e) => page.mouse.move(from.x + (x - from.x) * e, from.y + (y - from.y) * e));
  mouse = { x, y };
}
async function centre(page, selector) {
  const box = await page.locator(selector).first().boundingBox();
  if (!box) throw new Error('not visible: ' + selector);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2, box };
}
async function press(page) { await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up(); }
async function drag(page, dx, dy, ms = 900, steps = 0) {   // a real left-drag from the mouse's place (three.js OrbitControls)
  const from = { ...mouse };
  await page.mouse.down();
  await paced(page, ms, steps || Math.max(10, Math.round(ms / 25)), (e) => page.mouse.move(from.x + dx * e, from.y + dy * e));
  await page.mouse.up();
  mouse = { x: from.x + dx, y: from.y + dy };
}
async function scrollTo(page, y, ms = 500) {   // a wheel scroll in small steps, so the recording shows the motion
  const start = await page.evaluate(() => scrollY);
  let done = 0;
  await paced(page, ms, Math.max(6, Math.round(ms / 30)), async (e) => {
    const want = Math.round((y - start) * e);
    await page.mouse.wheel(0, want - done); done = want;
  });
  await page.waitForTimeout(60);
}
const barHeight = (page) => page.evaluate(() => document.querySelector('.cov-bar').getBoundingClientRect().height);
// The page y that puts a figure's top just under the sticky tab bar.
const underBar = (page, selector, gap = 12) => page.evaluate(([s, g]) => {
  const bar = document.querySelector('.cov-bar').getBoundingClientRect().height;
  return Math.max(0, document.querySelector(s).getBoundingClientRect().top + scrollY - bar - g);
}, [selector, gap]);
"""

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const [chrome, landing, first, dir, cursor] = process.argv.slice(3);
const marks = [];
let t0 = Date.now();
const mark = (name, extra) => marks.push(Object.assign({ name, ms: Date.now() - t0 }, extra || {}));
""" + HELPERS + r"""
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const errors = [];
  try {
    // WHY a fresh context: the page remembers its controls in localStorage; a new context starts at viridis, linear.
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 },
                                               recordVideo: { dir, size: { width: 1200, height: 750 } } });
    // WHY recorded at 1200×750 (the 1440×900 viewport scaled): the clip ships 1200 px wide, and encoding fewer pixels
    // leaves the pinned cores to the page, whose three.js views draw on swiftshader.
    await context.addInitScript(cursor);
    const page = await context.newPage();
    t0 = Date.now();
    page.on('pageerror', (error) => errors.push(String(error)));
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
    async function tab(id, hold) {
      const at = await centre(page, `[data-cov-tab="${id}"]`);
      await glide(page, at.x, at.y, 230); await press(page);
      await page.waitForFunction((t) => { const v = document.querySelector(`[data-cov-view="${t}"]`);
                                          return v && getComputedStyle(v).display !== 'none' && v.querySelector('[data-cov-figure]'); }, id);
      const scrollY = await page.evaluate(() => scrollY);
      mark(id, { scroll_y: scrollY });
      // WHY: a tab's first open can drop the page to the top (it builds after the old view hides, so the page is short
      // for a frame and the browser clamps the scroll), and a tab opened from far down the previous one lands past its
      // first figure. Scroll so the first figure sits under the sticky tab bar; the mouse waits in the right margin,
      // where no figure draws a hover tooltip.
      const want = await underBar(page, `[data-cov-view="${id}"] [data-cov-figure]`);
      if (scrollY < want - 120 || scrollY > want + 200) {
        await glide(page, 1432, 450, 150);
        await scrollTo(page, want, 340);
        mark(id + ' (scrolled back under the bar)', { from: scrollY, to: await page.evaluate(() => scrollY) });
      }
      await page.waitForTimeout(hold);
    }
    async function pick(selector, value, hold) {   // glide to a drop-down, then change it (headless draws no native popup)
      const at = await centre(page, selector);
      await glide(page, at.x, at.y, 260);
      await page.selectOption(selector, value);
      mark(`${selector} = ${value}`);
      await page.waitForTimeout(hold);
    }

    // 1. the landing page: one table per dataset; the lead links the first page to open
    await page.goto(landing);
    await page.waitForSelector(`a[href="${first}"]`);
    await page.mouse.move(mouse.x, mouse.y);
    mark('landing');
    await page.waitForTimeout(500);
    // WHY the first client rect: the link wraps onto two lines, so its bounding box's centre is between them.
    let at = await page.evaluate((f) => { const r = document.querySelector(`.lead a[href="${f}"]`).getClientRects()[0];
                                          return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }, first);
    await glide(page, at.x, at.y + 2, 400);
    await page.waitForTimeout(120);
    await Promise.all([page.waitForNavigation({ waitUntil: 'load' }), press(page)]);
    await page.waitForSelector('[data-cov-figure="ridgeline"] canvas');
    await page.mouse.move(mouse.x + 1, mouse.y);
    // 2. Overview at the top: the one-line answer, the numbers and the ridgeline's first joints in one view
    mark('overview', { title: await page.title() });
    await page.waitForTimeout(1500);

    // 3. Limits (the tab() helper scrolls its figures up under the sticky tab bar)
    await tab('limits', 700);

    // 4. One joint: the q × qd heatmap under each control
    await tab('joint', 350);
    await pick('select[data-cov-cmap]', 'magma', 550);
    await pick('select[data-cov-cmap]', 'viridis', 250);
    at = await centre(page, 'input[data-cov-reverse]');
    await glide(page, at.x, at.y, 220); await press(page); mark('reverse on'); await page.waitForTimeout(550);
    await press(page); mark('reverse off'); await page.waitForTimeout(250);
    await pick('select[data-cov-scale]', 'equalized', 750);
    await pick('select[data-cov-scale]', 'linear', 250);

    // 5. All joints: parallel coordinates
    await tab('joints', 700);

    // 6. Tool position: the projections, then the 3-D voxels, dragged to orbit
    await tab('cartesian', 550);
    await glide(page, 700, 560, 120);
    await scrollTo(page, await underBar(page, '[data-cov-figure="voxels-3d"]'), 380);
    mark('voxels-3d');
    const vox = await centre(page, '[data-cov-figure="voxels-3d"] canvas');
    await glide(page, vox.x - 90, vox.y, 150);
    // WHY 8 steps: each step is one three.js frame of ~1 300 voxels and the reachable specks on swiftshader (~0.2 s);
    // 40 steps took 9 s and played as slow motion.
    await drag(page, 200, 25, 400, 5);
    mark('voxels-orbited');
    await page.waitForTimeout(150);

    // 7. Tool orientation: the direction sphere, dragged
    await tab('orientation', 300);
    const sphere = await centre(page, '[data-cov-figure="sphere-3d"] canvas');
    await glide(page, sphere.x - 80, sphere.y + 20, 200);
    await drag(page, 170, -45, 650);
    mark('sphere-orbited');
    await page.waitForTimeout(250);

    // 8. 3-D proposals: the bottom-right drop-down
    await tab('space3d', 600);
    await pick('select[data-cov-proposal]', 'joint-skyline', 800);
    await pick('select[data-cov-proposal]', 'workspace-terrain', 800);

    // 9. Trajectories: click the visible row whose shoulder_pan path spans most, then see it in One joint's spaghetti
    await tab('trajectories', 250);
    const row = await page.evaluate(() => {
      const head = [...document.querySelectorAll('[data-cov-figure="table"] th')].map((th) => th.textContent);
      const col = head.findIndex((h) => /shoulder_pan/.test(h));
      const rows = [...document.querySelectorAll('[data-cov-figure="table"] tr[data-index]')]
        .filter((r) => { const b = r.getBoundingClientRect(); return b.top > 160 && b.bottom < innerHeight - 20; });
      let best = rows[0];
      for (const r of rows) if (parseFloat(r.cells[col].textContent) > parseFloat(best.cells[col].textContent)) best = r;
      return { index: best.getAttribute('data-index'), trajectory: best.cells[1].textContent.trim(), span: best.cells[col].textContent.trim() };
    });
    at = await centre(page, `[data-cov-figure="table"] tr[data-index="${row.index}"] td:nth-child(2)`);
    await glide(page, at.x, at.y, 320);
    await press(page);
    mark('row-clicked', row);
    await page.waitForTimeout(450);
    await tab('joint', 150);
    await glide(page, 1432, 600, 200);   // the right margin: no figure under the mouse, so no hover tooltip
    await scrollTo(page, await underBar(page, '[data-cov-figure="spaghetti"]'), 450);
    mark('spaghetti-highlighted', { chip: await page.evaluate(() => (document.querySelector('.cov-bar').textContent.match(/Highlighted:\s*\S+/) || [''])[0]) });
    await page.waitForTimeout(1150);
    mark('end');
    const video = page.video();
    await context.close();
    console.log(JSON.stringify({ video: await video.path(), marks, errors }));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });
"""


def run_driver(source: str, scratch: Path, *args: str, timeout: int = 600) -> dict:
    """Run a Node Playwright driver (its source written to ``scratch``); returns the JSON its last stdout line holds."""

    scratch.mkdir(parents=True, exist_ok=True)
    driver = scratch / "driver.cjs"
    driver.write_text(source, encoding="utf-8")
    result = subprocess.run([*PIN, "node", str(driver), str(PLAYWRIGHT), str(CHROME), *args],
                            capture_output=True, text=True, timeout=timeout, check=False)  # fmt: skip
    if result.returncode:
        raise SystemExit(result.stderr[-3000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def ffmpeg(*args: str) -> None:
    subprocess.run([*PIN, FFMPEG, "-v", "error", "-y", *args], check=True)


def convert(raw: Path, out: Path, start_s: float, end_s: float) -> tuple[Path, Path, Path]:
    """The raw recording, trimmed to [start_s, end_s]: a muted H.264 mp4 (1200 px), a 480 px GIF and a poster JPEG."""

    mp4, gif, poster = out / "hero.mp4", out / "hero.gif", out / "hero-poster.jpg"
    span = ["-ss", f"{start_s:.2f}", "-to", f"{end_s:.2f}", "-i", str(raw)]
    # WHY CRF 30 at 1200 px and 25 fps: UI text stays readable and the clip leaves room for ~40 stills under 12 MB.
    # WHY the GIF is 480 px, 3 fps, 32 colours: it is only the fallback for a viewer that cannot play H.264.
    ffmpeg(*span, "-an", "-vf", "fps=25,scale=1200:-2:flags=lanczos", "-c:v", "libx264", "-preset", "veryslow",
           "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4))  # fmt: skip
    palette = BUILD / "palette.png"
    ffmpeg(*span, "-vf", "fps=3,scale=480:-2:flags=lanczos,palettegen=max_colors=32:stats_mode=diff", str(palette))
    ffmpeg(*span, "-i", str(palette), "-lavfi",
           "fps=3,scale=480:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=none:diff_mode=rectangle", str(gif))  # fmt: skip
    # WHY the first frame: the poster is what shows before playback, so it must be the frame playback starts on.
    ffmpeg("-ss", "0.10", "-i", str(mp4), "-frames:v", "1", "-q:v", "4", str(poster))
    return mp4, gif, poster


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pages", type=Path, default=PAGES, help="the folder holding the coverage landing page")
    parser.add_argument("--out", type=Path, default=MEDIA)
    args = parser.parse_args()
    pages, out = args.pages.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    report = run_driver(DRIVER, BUILD / "hero", (pages / "index.html").as_uri(), FIRST, str(BUILD / "hero"), CURSOR)
    raw = BUILD / "hero-raw.webm"
    Path(report.pop("video")).replace(raw)
    marks = {mark["name"]: mark["ms"] / 1000 for mark in report["marks"]}
    # Trim the white frames before the landing page painted; keep everything after.
    start = max(0.0, marks["landing"] + 0.05)
    mp4, gif, poster = convert(raw, out, start, marks["end"])
    for mark in report["marks"]:
        mark["video_s"] = round(max(0.0, mark["ms"] / 1000 - start), 2)
    report.update(trim_s=[round(start, 2), marks["end"]], duration_s=round(marks["end"] - start, 2),
                  mp4_bytes=mp4.stat().st_size, gif_bytes=gif.stat().st_size, poster_bytes=poster.stat().st_size)  # fmt: skip
    (out / "hero-timeline.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
