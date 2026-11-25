"""Record the grasp coverage review's hero clip and stills from the REAL workbench pages (2026-11-24).

build_real.py writes the two sites (our repicks, GraspNet-1Billion) under reports/media/grasp-coverage-2026-11-24/; this
serves that folder with traj_compare.serve on a free port (its pid recorded and stopped), and one headless Chrome (Node
Playwright, recordVideo, a fresh context) walks the repicks page as a reader would:

Overview (all 1 233 grasps: dots, a density heatmap, thin grippers) → tick Outcome "failed" (every figure keeps only the
43 failures) → Grippers (their thin grippers in 3-D, dragged to orbit) → untick (all 1 233) → Over time → the GraspNet
page's Orientation (the same views on a 6-DOF label set). Round 2, 2026-11-24.

Then a second context (no video) shoots the stills the report shows. The cursor dot and the glide / drag helpers are
the trajectory report's (docs/coverage_2026-11-23/record_hero.py), imported. Writes ``<media>/hero.mp4`` (H.264, 1200
px, muted, faststart), ``hero.gif`` (480 px fallback), ``hero-poster.jpg``, ``hero-timeline.json`` and ``stills/*.png``.

    taskset -c 2-5,16,17 nice -n 10 /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/grasp_coverage_2026-11-24/record_hero.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "coverage_2026-11-23"))
from record_hero import CHROME, CURSOR, FFMPEG, HELPERS, PIN, PLAYWRIGHT  # noqa: E402  (the trajectory report's)

SITES = PACKAGE / "reports" / "media" / "grasp-coverage-2026-11-24"
MEDIA = SITES / "report"
BUILD = PACKAGE / ".cache" / "grasp_coverage_report_2026-11-24"

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const [chrome, base, dir, cursor] = process.argv.slice(3);
const marks = [];
let t0 = Date.now();
const mark = (name, extra) => marks.push(Object.assign({ name, ms: Date.now() - t0 }, extra || {}));
""" + HELPERS + r"""
const WB = 'data-workbench';
const ready = (page) => page.waitForSelector(WB + '[data-ready]', { timeout: 30000 });
async function tab(page, name, hold) {
  const at = await centre(page, `${WB} data-tabs [role=tab][data-tab="${name}"]`);
  await glide(page, at.x, at.y, 260); await press(page);
  await page.waitForTimeout(hold);
}
async function tick(page, value, hold) {
  const at = await centre(page, `${WB} data-facets section.df-group[data-p="outcome"] input[data-value="${value}"]`);
  await glide(page, at.x, at.y, 420); await press(page);
  await page.waitForTimeout(hold);
}
const count = (page) => page.evaluate(() => document.querySelector('data-workbench data-count').textContent.trim());
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const errors = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 },
                                               recordVideo: { dir, size: { width: 1200, height: 750 } } });
    await context.addInitScript(cursor);
    const page = await context.newPage();
    t0 = Date.now();
    page.on('pageerror', (error) => errors.push(String(error)));
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
    await page.goto(base + '/repicks/site/index.html'); await ready(page); await page.waitForTimeout(900);
    mark('landing', { count: await count(page) });
    await page.waitForTimeout(1300);
    // WHY the failures first: orbiting all 1 233 thin grippers costs ~15 s a step under software WebGL; the 43 failures
    // orbit smoothly and are the story ("showing where the failures where and not")
    await tick(page, 'failed', 1500);
    mark('failed', { count: await count(page) });
    await tab(page, 'Grippers', 300);
    await page.waitForSelector(`${WB} .dd-panel[aria-label="Thin grippers in 3-D"] canvas`, { timeout: 15000 });
    await page.waitForTimeout(800);
    const scene = await centre(page, `${WB} .dd-panel[aria-label="Thin grippers in 3-D"] canvas`);
    await glide(page, scene.x - 80, scene.y + 40, 300);
    await drag(page, 220, -30, 1300);
    await page.waitForTimeout(500);
    mark('grippers');
    await tick(page, 'failed', 1600);
    mark('all', { count: await count(page) });
    await tab(page, 'Over time', 1900);
    mark('over_time');
    await page.goto(base + '/graspnet/site/index.html#tab=orientation'); await ready(page); await page.waitForTimeout(2300);
    mark('graspnet', { count: await count(page) });
    mark('end');
    const video = page.video();
    await context.close();
    const stills = {};
    // WHY tall: the workbench scrolls inside its own frame, so a still shows a whole tab only when the window fits it
    const shoot = await browser.newContext({ viewport: { width: 1440, height: 1900 } });
    const still = await shoot.newPage();
    still.on('pageerror', (error) => errors.push(String(error)));
    const take = async (name) => { const path = `${dir}/still-${name}.png`; await still.screenshot({ path }); stills[name] = path; };
    for (const [site, tabs] of [['repicks', ['Overview', 'Grippers', 'Position', 'Gripper', 'Orientation', 'Objects', 'Over time', 'Grasps']],
                                ['graspnet', ['Overview', 'Grippers', 'Gripper', 'Orientation']]]) {
      await still.goto(`${base}/${site}/site/index.html`); await ready(still); await still.waitForTimeout(900);
      for (const name of tabs) {
        await still.click(`${WB} data-tabs [role=tab][data-tab="${name}"]`); await still.waitForTimeout(1500);
        await take(`${site}-${name.toLowerCase().replace(' ', '-')}`);
      }
    }
    await still.goto(`${base}/repicks/site/index.html`); await ready(still); await still.waitForTimeout(900);
    await still.click(`${WB} data-facets section.df-group[data-p="outcome"] input[data-value="failed"]`); await still.waitForTimeout(1200);
    await take('repicks-overview-failed');
    await still.click(`${WB} data-tabs [role=tab][data-tab="Gripper"]`); await still.waitForTimeout(1500);
    await take('repicks-gripper-failed');
    await still.goto(`${base}/repicks/site/embed.html`); await ready(still); await still.waitForTimeout(1500);
    await take('repicks-embed');
    console.log(JSON.stringify({ video: await video.path(), marks, stills, errors }));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });
"""


def ffmpeg(*args: str) -> None:
    subprocess.run([*PIN, FFMPEG, "-v", "error", "-y", *args], check=True)


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    (MEDIA / "stills").mkdir(exist_ok=True)
    scratch = BUILD / "hero"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "driver.cjs").write_text(DRIVER, encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "traj_compare.serve", str(SITES), "--port", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        url = server.stdout.readline().split(" on ", 1)[1].split()[0].rstrip("/")
        result = subprocess.run([*PIN, "node", str(scratch / "driver.cjs"), str(PLAYWRIGHT), str(CHROME), url,
                                 str(scratch), CURSOR], capture_output=True, text=True, timeout=900, check=False)
    finally:
        server.terminate()
        server.wait(timeout=10)
    if result.returncode:
        raise SystemExit(result.stderr[-3000:])
    report = json.loads(result.stdout.strip().splitlines()[-1])
    raw = BUILD / "hero-raw.webm"
    Path(report.pop("video")).replace(raw)
    for name, path in report.pop("stills").items():
        Path(path).replace(MEDIA / "stills" / f"{name}.png")
    marks = {mark["name"]: mark["ms"] / 1000 for mark in report["marks"]}
    start, end = max(0.0, marks["landing"] - 0.2), marks["end"]
    span = ["-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", str(raw)]
    mp4, gif, poster = MEDIA / "hero.mp4", MEDIA / "hero.gif", MEDIA / "hero-poster.jpg"
    ffmpeg(*span, "-an", "-vf", "fps=25,scale=1200:-2:flags=lanczos", "-c:v", "libx264", "-preset", "veryslow",
           "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4))
    palette = BUILD / "palette.png"
    ffmpeg(*span, "-vf", "fps=3,scale=480:-2:flags=lanczos,palettegen=max_colors=32:stats_mode=diff", str(palette))
    ffmpeg(*span, "-i", str(palette), "-lavfi",
           "fps=3,scale=480:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=none:diff_mode=rectangle", str(gif))
    ffmpeg("-ss", "0.10", "-i", str(mp4), "-frames:v", "1", "-q:v", "4", str(poster))
    for mark in report["marks"]:
        mark["video_s"] = round(max(0.0, mark["ms"] / 1000 - start), 2)
    report.update(duration_s=round(end - start, 2), mp4_bytes=mp4.stat().st_size, gif_bytes=gif.stat().st_size)
    (MEDIA / "hero-timeline.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
