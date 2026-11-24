"""Shoot the coverage-viewer review's stills from the real UR5e coverage pages, plus the Dataset level's new link (2026-11-23).

The coverage pages open from disk. One headless Chrome (Node Playwright, deviceScaleFactor 1, viewport 1440×1300) opens
a fresh context for every control setting, so each shot starts from the page's own defaults (viridis, linear,
shoulder_pan_joint) rather than whatever the last shot left in localStorage. Each figure is scrolled to sit just under
the sticky tab bar and shot as an element (JPEG q80), with the mouse parked in the page's left margin so no hover
tooltip draws:

- s01 the Overview's top (viewport), s02 the limit bars, s03 the q × qd heatmap under the linear / log / equalized /
  visited scales, s04 it in magma, cividis and reversed viridis, s05 the tool projections in "trajectories" mode
  (paths per pixel, Strava style) under linear and equalized, s06-s16 the remaining figures, s17 the landing page
  (full page), s18 the UR5e + conveyor cell's projections (samples).
- s19 / s19b: a scratch traj_compare site over six UR5e targets (``write_dataset_report(..., coverage=True)``, written
  to ``.cache/report_site``): the Dataset level's header and tab bar ending in "Coverage ↗", then the page that link
  opens.
- Copies of earlier lanes' real screenshots as JPEG q80, at most 1100 px wide: ``p-<id>.jpg`` (the eight 3-D proposals,
  ``.cache/lane_c``), ``mpl-*.jpg`` (Matplotlib, ``.cache/lane_d/png-r1``) and ``viser-voxels.jpg`` /
  ``viser-sphere.jpg`` (``.cache/lane_d/viser/run-04``, cropped below the headless browser's "Software WebGL
  rendering detected" notice and Viser's view cube).

Writes ``<out>/stills.json`` (each still's size, the control settings, console errors). Run with the bench's
interpreter: it imports ``arm_motion_bench`` (the dataset) and ``traj_compare`` (editable, this checkout).

    taskset -c 2-5,16,17 nice -n 10 env -u VIRTUAL_ENV /home/bam/arm_motion_bench/.venv/bin/python /home/bam/traj_compare/docs/coverage_2026-11-23/shoot_stills.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_hero import BUILD, FIRST, HELPERS, MEDIA, PACKAGE, PAGES, run_driver  # noqa: E402

DATASET = Path("/home/bam/arm_motion_bench/datasets/ur5e_alone/workspace/v2")
SITE = PACKAGE / ".cache" / "report_site"
CONVEYOR = "ur5e-conveyor/full-speed/index.html"
LANE_C = PACKAGE / ".cache" / "lane_c"
LANE_D = PACKAGE / ".cache" / "lane_d"
# (source, still): Matplotlib renders of the same UR payload; shoulder_pan, the joint the page's stills show.
MPL = [("png-r1/heat-q-qd-shoulder_pan_joint.png", "mpl-heat-q-qd.jpg"), ("png-r1/projections.png", "mpl-projections.jpg"),
       ("png-r1/limit-bars.png", "mpl-limit-bars.jpg"), ("png-r1/ridgeline.png", "mpl-ridgeline.jpg")]  # fmt: skip
# Picked by looking (2026-11-23): every voxel (the >= 300 samples one is sparse), the sphere at linear (the default).
# WHY the crop (x0, y0, x1, y1): it drops the headless browser's "Software WebGL rendering detected" notice and the
# view cube above the scene; the scene itself is untouched.
VISER = [("viser/run-04/01-voxels-scene.png", "viser-voxels.jpg", (0, 200, 1116, 1000)),
         ("viser/run-04/07-sphere-scene.png", "viser-sphere.jpg", (0, 200, 1116, 1000))]  # fmt: skip

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const [chrome, pages, first, conveyor, site, shots] = process.argv.slice(3);
""" + HELPERS + r"""
const PAGE = `file://${pages}/${first}`;
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = { errors: [], stills: [] };
  async function fresh(url, height = 1300) {   // a new context: localStorage empty, so the controls are the defaults
    const context = await browser.newContext({ viewport: { width: 1440, height }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
    await page.goto(url);
    return { context, page };
  }
  async function park(page) { await page.mouse.move(3, 3); }   // the left margin: no figure, no hover tooltip
  async function openTab(page, id) {
    await page.click(`[data-cov-tab="${id}"]`);
    await page.waitForSelector(`[data-cov-view="${id}"] [data-cov-figure]`);
    await park(page);
  }
  async function set(page, settings) {   // { cmap, scale, reverse, switch: [figure, value] }
    if (settings.cmap) await page.selectOption('select[data-cov-cmap]', settings.cmap);
    if (settings.scale) await page.selectOption('select[data-cov-scale]', settings.scale);
    if (settings.reverse) await page.check('input[data-cov-reverse]');
    if (settings.switch) await page.click(`[data-cov-figure="${settings.switch[0]}"] button[data-value="${settings.switch[1]}"]`);
    await park(page);
  }
  async function shoot(page, figure, file, settings = {}, wait = 500) {
    const selector = `[data-cov-figure="${figure}"]`;
    await page.evaluate((s) => { window.scrollTo(0, 0);   // then under the sticky bar, measured from the page top
      const bar = document.querySelector('.cov-bar').getBoundingClientRect().height;
      window.scrollTo(0, document.querySelector(s).getBoundingClientRect().top + scrollY - bar - 12); }, selector);
    await page.waitForTimeout(wait);
    const box = await page.locator(selector).boundingBox();
    await page.locator(selector).screenshot({ path: `${shots}/${file}`, type: 'jpeg', quality: 80 });
    out.stills.push({ file, figure, settings, width: Math.round(box.width), height: Math.round(box.height),
                      top_in_view: Math.round(box.y) });
  }
  async function figureShot(tab, figure, file, settings = {}, wait = 500) {   // one figure under one setting, fresh
    const { context, page } = await fresh(PAGE);
    await page.waitForSelector('[data-cov-page]');
    await openTab(page, tab);
    await set(page, settings);
    await shoot(page, figure, file, settings, wait);
    await context.close();
  }
  try {
    // s01: the Overview's top, as a reader lands on it
    let { context, page } = await fresh(PAGE);
    await page.waitForSelector('[data-cov-figure="ridgeline"] canvas');
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${shots}/s01-overview.jpg`, type: 'jpeg', quality: 80 });
    out.stills.push({ file: 's01-overview.jpg', viewport: '1440x1300' });
    // the defaults, one context: none of these shots changes a control
    await shoot(page, 'ridgeline', 's08-ridgeline.jpg');
    await openTab(page, 'limits'); await shoot(page, 'limit-bars', 's02-limit-bars.jpg');
    await openTab(page, 'joint');
    await shoot(page, 'heat-q-qd', 's03-heat-linear.jpg', { scale: 'linear' });
    await shoot(page, 'slabs', 's06-slabs.jpg');
    await shoot(page, 'envelope', 's09-envelope.jpg');
    await openTab(page, 'joints');
    await shoot(page, 'parallel', 's07-parallel.jpg');
    await shoot(page, 'growth', 's10-growth.jpg');
    await openTab(page, 'cartesian');
    await shoot(page, 'voxels-3d', 's11-voxels-3d.jpg', {}, 1500);
    await shoot(page, 'spaghetti-3d', 's12-spaghetti-3d.jpg', {}, 1500);
    await openTab(page, 'orientation');
    await shoot(page, 'sphere-3d', 's13-sphere-3d.jpg', {}, 1500);
    await shoot(page, 'tilt-map', 's14-tilt-map.jpg');
    await shoot(page, 'tilt-yaw', 's15-tilt-yaw.jpg');
    await shoot(page, 'yaw-line', 's16-yaw-line.jpg');
    await context.close();

    // s03 / s04 / s05: one fresh context per control setting
    for (const scale of ['log', 'equalized', 'visited']) await figureShot('joint', 'heat-q-qd', `s03-heat-${scale}.jpg`, { scale });
    await figureShot('joint', 'heat-q-qd', 's04-cmap-magma.jpg', { cmap: 'magma' });
    await figureShot('joint', 'heat-q-qd', 's04-cmap-cividis.jpg', { cmap: 'cividis' });
    await figureShot('joint', 'heat-q-qd', 's04-viridis-reversed.jpg', { reverse: true });
    for (const scale of ['linear', 'equalized'])
      await figureShot('cartesian', 'projections', `s05-projections-${scale}.jpg`, { scale, switch: ['projections', 'paths'] });

    // s17: the landing page, whole
    ({ context, page } = await fresh(`file://${pages}/index.html`, 900));
    await page.waitForSelector(`a[href="${first}"]`);
    await page.screenshot({ path: `${shots}/s17-landing.jpg`, type: 'jpeg', quality: 80, fullPage: true });
    out.stills.push({ file: 's17-landing.jpg', full_page: true });
    await context.close();

    // s18: the UR5e + conveyor cell's tool projections (samples, the default)
    ({ context, page } = await fresh(`file://${pages}/${conveyor}`));
    await page.waitForSelector('[data-cov-page]');
    await openTab(page, 'cartesian');
    await shoot(page, 'projections', 's18-conveyor-projections.jpg', { page: conveyor });
    await context.close();

    // s19: the traj_compare Dataset level, its tab bar ending in "Coverage ↗"; s19b: the page that link opens
    ({ context, page } = await fresh(`file://${site}/index.html`, 900));
    await page.waitForSelector('[data-tc-coverage-link]');
    await page.waitForTimeout(800);
    await page.hover('[data-tc-coverage-link]');   // its hover style marks it; a title tooltip is never drawn headless
    await page.screenshot({ path: `${shots}/s19-dataset-link.jpg`, type: 'jpeg', quality: 80, clip: { x: 0, y: 0, width: 1440, height: 420 } });
    out.stills.push({ file: 's19-dataset-link.jpg', link: await page.$eval('[data-tc-coverage-link]', (a) => [a.textContent, a.getAttribute('href'), a.title]) });
    await Promise.all([page.waitForNavigation({ waitUntil: 'load' }), page.click('[data-tc-coverage-link]')]);
    await page.waitForSelector('[data-cov-page]');
    await page.waitForTimeout(800);
    await park(page);
    await page.screenshot({ path: `${shots}/s19b-dataset-coverage.jpg`, type: 'jpeg', quality: 80 });
    out.stills.push({ file: 's19b-dataset-coverage.jpg', url: page.url().replace(/^file:\/\//, ''), title: await page.title() });
    await context.close();
  } finally { await browser.close(); }
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def build_site(out: Path, tasks: int = 6) -> dict:
    """A small traj_compare site over the first ``tasks`` UR5e workspace targets, with its coverage page."""

    from arm_motion_bench.datasets import load_dataset

    from traj_compare import Run, write_dataset_report

    dataset = load_dataset(DATASET)
    ids = [task.task_id for task in dataset.tasks][:tasks]
    runs = []
    for task_id in ids:
        target = dataset.target(task_id, 1.0)
        runs.append(Run(name=task_id, reference=target, measured={"sim": target}, tags={"target": task_id}))
    index = write_dataset_report(runs, out, title="UR5e · Entire Workspace (demo site)", coverage=True)
    return {"site": str(index), "tasks": ids}


def to_jpeg(source: Path, still: Path, crop: tuple[int, int, int, int] | None = None, width: int = 1100) -> dict:
    """``source`` as a JPEG q80 at most ``width`` px wide (optionally cropped first); returns its sizes."""

    from PIL import Image

    with Image.open(source) as image:
        image = image.convert("RGB")
        if crop:
            image = image.crop(crop)
        if image.width > width:
            image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
        image.save(still, "JPEG", quality=80, optimize=True)
        return {"file": still.name, "source": str(source), "crop": crop, "width": image.width, "height": image.height}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pages", type=Path, default=PAGES, help="the folder holding the coverage landing page")
    parser.add_argument("--out", type=Path, default=MEDIA)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {"site": build_site(SITE)}
    report.update(run_driver(DRIVER, BUILD / "stills", str(args.pages.resolve()), FIRST, CONVEYOR, str(SITE), str(out)))
    copies = [to_jpeg(png, out / ("p-" + png.stem.removeprefix("proposal-") + ".jpg")) for png in sorted(LANE_C.glob("proposal-*.png"))]
    copies += [to_jpeg(LANE_D / source, out / still) for source, still in MPL]
    copies += [to_jpeg(LANE_D / source, out / still, crop) for source, still, crop in VISER]
    report["copies"] = copies
    sizes = {path.name: path.stat().st_size for path in sorted(out.iterdir()) if path.is_file()}
    report.update(files=sizes, folder_bytes=sum(sizes.values()))
    (out / "stills.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
