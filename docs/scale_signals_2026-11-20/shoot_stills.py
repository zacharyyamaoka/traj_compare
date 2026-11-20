"""Shoot the scale-and-signals review's stills from the real bench sites, the same way the bench shot its "before" (2026-11-20).

Serves the bench's rebuilt sites like ``record_hero.py`` (one server for the folder, its own process group, stopped by
PID) and drives one headless Chrome at 1440×900:

1. ``ur5e-1b-dataset-table.png`` and ``ur5e-2-target.png`` repeat the bench's own driver step for step
   (``/home/bam/arm_motion_bench/reports/media/dashboard/shots/_driver.cjs``: the dataset page, a glide to (600, 420),
   Table, Cards, Open target on "workspace-dev-005 · workspace-v1 · speed 1", 1.6 s, shoot), so each "after" has the
   viewport, scroll position and mouse position of the bench's "before". The one addition: the target's charts must
   have drawn (its ``targets/<slug>.js`` arrived) before the shot.
2. ``landing.png``: ``/``, the landing page the server answers for a root without index.html (C3).
3. ``lazy-held.png`` / ``lazy-drawn.png``: the UR5e cards scrolled one row past what is loaded. The requests for the
   next rows' ``targets/<slug>.js`` are held in flight for the first shot (on localhost they arrive in ~0.2 s, too
   fast to photograph), then released for the second. Nothing else is changed: the placeholders are the page's own.

Writes into ``<out>`` plus ``stills.json`` (what was held, the drawn rate, console errors).

    flock /tmp/claude-1000/traj-tc-heavy.lock taskset -c 2-5,16,17 nice -n 19 env -u VIRTUAL_ENV /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/scale_signals_2026-11-20/shoot_stills.py --sites <folder holding ur5e/ pendulum/ bam_fb/>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_hero import (  # noqa: E402
    CURSOR,
    HELPERS,
    MEDIA,
    SERVE_PYTHON,
    SITE,
    SITES,
    TARGET,
    run_driver,
    serving,
)

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const [chrome, base, shots, site, target, cursor] = process.argv.slice(3);
""" + HELPERS + r"""
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true,
                                          args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = { errors: [], held: [] };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await context.addInitScript(cursor);
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon/.test(JSON.stringify(m.location()))) out.errors.push(m.text()); });
    page.on('response', (r) => { if (r.status() >= 400 && !/favicon/.test(r.url())) out.errors.push(r.status() + ' ' + r.url()); });
    async function click(selector, hold) {   // the bench's click: scroll into view if needed, glide, press, hold
      const loc = page.locator(selector).first(); await loc.scrollIntoViewIfNeeded();
      const at = await centre(page, selector);
      await glide(page, at.x, at.y); await press(page); await page.waitForTimeout(hold);
    }

    // 1. the bench's own steps (its _driver.cjs), so each "after" matches its "before"
    await page.goto(`${base}/${site}/index.html`, { timeout: 120000 });
    await page.waitForSelector(`[data-tc-target-card="${target}"]`, { timeout: 120000 });
    await page.waitForTimeout(1200);
    await glide(page, 600, 420, 500); await page.waitForTimeout(900);
    await click('[data-tc-targets-view] [data-view="table"]', 1400);
    await page.screenshot({ path: `${shots}/${site}-1b-dataset-table.png` });
    await click('[data-tc-targets-view] [data-view="cards"]', 500);
    await click(`[data-tc-target-card="${target}"] >> text=Open target`, 0);
    await page.waitForSelector('[data-tc-run-list] [data-tc-run]', { timeout: 60000 });
    out.target_drawn_ms = await settled(page);
    await page.waitForTimeout(1600);
    out.target_scroll_y = await page.evaluate(() => scrollY);
    out.mouse = mouse;
    await page.screenshot({ path: `${shots}/${site}-2-target.png` });
    out.rates = [...new Set(await page.$$eval('[data-tc-drawn-rate]', (r) => r.map((x) => x.textContent + ' | ' + x.title)))];

    // 2. the landing page
    await page.goto(base + '/');
    await page.waitForSelector('[data-tc-site]');
    out.sites = await page.$$eval('[data-tc-site]', (a) => a.map((x) => x.getAttribute('data-tc-site') + ' | ' + x.textContent));
    await page.mouse.move(-40, -40);
    await page.screenshot({ path: `${shots}/landing.png`, clip: { x: 0, y: 0, width: 760, height: 150 } });

    // 3. lazy cards: one row past what is loaded, its files held in flight, then released
    await page.goto(`${base}/${site}/index.html`);
    await page.waitForSelector(`[data-tc-target-card="${target}"]`);
    await page.evaluate((t) => document.querySelector(`[data-tc-target-card="${t}"]`).scrollIntoView({ block: 'start' }), target);
    await settled(page);
    await page.waitForTimeout(400);
    const held = [];
    await page.route('**/targets/**', (route) => { held.push(route); out.held.push(route.request().url().split('/').pop()); });
    // WHY +300: the page loads a card's file once the card is within 300 px of the viewport (dataset.js whenVisible).
    const rowTop = await page.evaluate(() => {
      const edge = scrollY + innerHeight + 300;
      const tops = [...document.querySelectorAll('[data-tc-target-card]')].map((c) => c.getBoundingClientRect().top + scrollY);
      return tops.filter((top) => top > edge).sort((a, b) => a - b)[0];
    });
    await page.evaluate((y) => window.scrollTo(0, y), rowTop - 470);
    await page.waitForTimeout(500);
    out.waits_held = await waitsInView(page);
    await page.screenshot({ path: `${shots}/lazy-held.png` });
    for (const route of held) await route.continue();   // release first: unroute would hand them on itself
    await page.unroute('**/targets/**');
    out.drawn_after_release_ms = await settled(page);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${shots}/lazy-drawn.png` });
  } finally { await browser.close(); }
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sites", type=Path, default=SITES, help="the folder holding the bench's site folders")
    parser.add_argument("--out", type=Path, default=MEDIA / "stills")
    parser.add_argument("--python", type=Path, default=SERVE_PYTHON if SERVE_PYTHON.is_file() else Path(sys.executable),
                        help="the interpreter that serves (it must import the sites' robot hooks)")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with serving(args.sites.resolve(), args.python) as (base, banner):
        print(banner, flush=True)
        report = run_driver(DRIVER, out / "_build", base, str(out), SITE, TARGET, CURSOR)
    report["serve_banner"] = banner
    (out / "stills.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
