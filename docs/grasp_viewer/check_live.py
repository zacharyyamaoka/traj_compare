"""Check the deployed Grasp dataset viewer in headless Chrome (Node Playwright; never a visible window).

    python3 /home/bam/traj_compare/docs/grasp_viewer/check_live.py [URL]

Passes when: the landing page shows one card per dataset of the built site, every card's "Open the viewer" page draws
its data-ui workbench (``data-workbench[data-ready]``) with the count "<n> of <n> grasps" its payload says, the repicks
count reads "1,233 of 1,233 grasps", and no page logs a console error or fails a request. Screenshots (landing + each
workbench) go to reports/media/grasp-viewer-site-checks/. Exit 1 and the reasons on any failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
SITE = PACKAGE / "reports" / "media" / "grasp-viewer-site"
SHOTS = PACKAGE / "reports" / "media" / "grasp-viewer-site-checks"
LIVE = "https://grasp-viewer.zach-yamaoka.workers.dev"
PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = "/usr/bin/google-chrome"

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const [chrome, base, shots] = process.argv.slice(3);
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true });
  const out = { errors: [], failed: [], cards: [], pages: {} };
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const watch = (page) => {
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
    page.on('response', (r) => { if (r.status() >= 400) out.failed.push(r.status() + ' ' + r.url()); });
  };
  let page = await context.newPage(); watch(page);
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  out.title = await page.title();
  out.cards = await page.evaluate(() => [...document.querySelectorAll('.card')].map((c) => ({
    title: c.querySelector('h2').textContent, href: c.querySelector('a.open').getAttribute('href') })));
  await page.screenshot({ path: shots + '/landing.png', fullPage: true });
  for (const card of out.cards) {
    page = await context.newPage(); watch(page);
    await page.goto(base + '/' + card.href);
    await page.waitForSelector('data-workbench[data-ready]', { timeout: 45000 });
    await page.waitForTimeout(1500);
    const count = await page.evaluate(() => document.querySelector('data-workbench data-count').textContent.trim());
    const slug = card.href.split('/')[0];
    await page.screenshot({ path: shots + '/' + slug + '.png' });
    out.pages[slug] = { count };
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def main() -> None:
    base = (sys.argv[1] if len(sys.argv) > 1 else LIVE).rstrip("/")
    SHOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        driver = Path(scratch) / "driver.cjs"
        driver.write_text(DRIVER, "utf-8")
        result = subprocess.run(["node", str(driver), str(PLAYWRIGHT), CHROME, base, str(SHOTS)], capture_output=True,
                                text=True, timeout=300)
    if result.returncode or not result.stdout.strip():
        raise SystemExit(f"the browser driver failed: {result.stderr[-2000:]}")
    out = json.loads(result.stdout.strip().splitlines()[-1])
    problems = []
    expected = {}
    for folder in sorted(p for p in SITE.iterdir() if (p / "grasp_coverage.json").is_file()):
        grasps = int(json.loads((folder / "grasp_coverage.json").read_text("utf-8"))["source"]["grasps"])
        expected[folder.name] = f"{grasps:,} of {grasps:,} grasps"
    got = {slug: page["count"] for slug, page in out["pages"].items()}
    if got != expected:
        problems.append(f"workbench counts {got} != the payloads' {expected}")
    if expected.get("repicks") != "1,233 of 1,233 grasps":
        problems.append(f"repicks count {expected.get('repicks')!r}, expected '1,233 of 1,233 grasps'")
    if len(out["cards"]) != len(expected):
        problems.append(f"{len(out['cards'])} cards for {len(expected)} datasets")
    problems += [f"console: {e}" for e in out["errors"]] + [f"request: {f}" for f in out["failed"]]
    print(json.dumps({"base": base, "title": out["title"], "cards": [c["title"] for c in out["cards"]], "counts": got,
                      "screenshots": str(SHOTS)}, indent=1))
    if problems:
        print("LIVE CHECK FAILED:", *problems, sep="\n  ", file=sys.stderr)
        raise SystemExit(1)
    print("live check passed")


if __name__ == "__main__":
    main()
