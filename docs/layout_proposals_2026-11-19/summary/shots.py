"""Drive the five summary layouts in one headless Chrome: console check, interaction states, drag/fold/persist tests.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    flock /tmp/claude-1000/traj-layout-browser.lock taskset -c 2-5,16,17 nice -n 19 \
      uv run --no-project --with playwright==1.64.1 python summary/shots.py <OUT> [check|states]

`check` loads every page and prints console errors. `states` also writes the state screenshots (OUT/shots/vN-<state>.png),
measures the control each walkthrough step demonstrates (for the gallery's highlight boxes) and records what it exercised
in OUT/shots/states.json. Hero shots are taken separately with TCD/shoot.sh. One browser, closed at the end.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1]).resolve()
MODE = sys.argv[2] if len(sys.argv) > 2 else "check"
SHOTS = OUT / "shots"
VARIANTS = ("v1", "v2", "v3", "v4", "v5")


def rect(page, selector: str) -> dict | None:
    return page.evaluate(
        """(sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();
                     return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; }""",
        selector,
    )


def open_page(browser, variant: str, errors: list):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page = context.new_page()
    page.on("console", lambda m: errors.append(f"{variant}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"{variant}: {e}"))
    page.goto((OUT / variant / "index.html").as_uri())
    page.wait_for_timeout(900)
    return context, page


def drag_test(page, gutter: str, panel: str, dx: int, dy: int, prop: str) -> dict:
    """Drag a boundary, reload (size must persist), double-click it (panel must fold), double-click again (unfold)."""
    g = rect(page, gutter)
    before = rect(page, panel)[prop]
    cx, cy = g["x"] + g["w"] / 2, g["y"] + g["h"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + dx / 2, cy + dy / 2, steps=4)
    page.mouse.move(cx + dx, cy + dy, steps=4)
    page.mouse.up()
    page.wait_for_timeout(250)
    after = rect(page, panel)[prop]
    page.reload()
    page.wait_for_timeout(900)
    persisted = rect(page, panel)[prop]
    page.dblclick(gutter)
    page.wait_for_timeout(250)
    folded = rect(page, panel)[prop]
    page.dblclick(gutter)
    page.wait_for_timeout(300)
    unfolded = rect(page, panel)[prop]
    return {"before": before, "after_drag": after, "after_reload": persisted, "folded": folded, "unfolded": unfolded,
            "ok": abs(after - before) > 20 and abs(persisted - after) <= 2 and folded <= 40 and abs(unfolded - after) <= 2}


def drill_test(page, selector: str) -> dict:
    page.click(selector)
    page.wait_for_timeout(250)
    toast = page.evaluate("() => { const t = document.querySelector('.drill-toast.show'); return t ? t.textContent : null; }")
    hash_ = page.evaluate("() => decodeURIComponent(location.hash)")
    page.evaluate("() => { const t = document.querySelector('.drill-toast'); if (t) t.classList.remove('show'); history.replaceState(null, '', location.pathname); }")
    return {"hash": hash_, "toast": toast, "ok": bool(hash_.startswith("#run/") and toast)}


def shot(page, name: str) -> str:
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path))
    return f"shots/{name}.png"


def states(browser, errors: list) -> dict:
    meta: dict = {}

    # ---------------- V1 Scalars board ----------------
    ctx, page = open_page(browser, "v1", errors)
    m = meta["v1"] = {"steps": {}, "tests": {}}
    m["steps"]["base"] = {"shot": "shots/v1-hero.png", "hl": rect(page, ".answer")}
    page.click("#enc-ctl button[data-v='bands']")
    page.wait_for_timeout(500)
    m["steps"]["bands"] = {"shot": shot(page, "v1-bands"), "hl": rect(page, "#enc-ctl")}
    page.click("#enc-ctl button[data-v='auto']")
    page.fill("input.filter", "v1|sim")
    page.wait_for_timeout(300)
    page.locator(".runrow", has_text="real-03").first.click()
    page.wait_for_timeout(500)
    page.mouse.move(900, 600)
    page.wait_for_timeout(300)
    m["steps"]["pinned"] = {"shot": shot(page, "v1-pinned"), "hl": rect(page, ".runrow.pinned")}
    m["tests"]["regex_filter_rows"] = page.evaluate("() => document.querySelectorAll('.runrow').length")
    m["tests"]["drill"] = drill_test(page, ".runrow.pinned a.drill")
    page.fill("input.filter", "")
    m["tests"]["drag_fold_persist"] = drag_test(page, ".gutter", ".runs-side", 80, 0, "w")
    ctx.close()

    # ---------------- V2 League table ----------------
    ctx, page = open_page(browser, "v2", errors)
    m = meta["v2"] = {"steps": {}, "tests": {}}
    m["steps"]["base"] = {"shot": "shots/v2-hero.png", "hl": rect(page, ".bhead")}
    page.click("button[data-v='flat']")
    page.wait_for_timeout(500)
    m["steps"]["league"] = {"shot": shot(page, "v2-league"), "hl": rect(page, "button[data-v='flat']")}
    page.click("button[data-v='grouped']")
    page.click("button[data-v='fbShare']")
    page.wait_for_timeout(300)
    page.click("tr.grow[data-row='full-circle-fast|v1']")
    page.wait_for_timeout(600)
    m["steps"]["fbshare"] = {"shot": shot(page, "v2-fbshare"), "hl": rect(page, "tr.grow[data-row='full-circle-fast|v1']")}
    m["tests"]["detail_title"] = page.evaluate("() => document.querySelector('.detail .side-title').textContent")
    m["tests"]["sort_click"] = page.evaluate("() => { const th = [...document.querySelectorAll('th.sortable')].find(t => t.textContent.startsWith('FB share')); th.click(); return [...document.querySelectorAll('section.block')][0].querySelectorAll('tr.grow')[0].dataset.row; }")
    m["tests"]["drill"] = drill_test(page, "tr.grow a.drill")
    m["tests"]["drag_fold_persist"] = drag_test(page, ".gutter", ".detail", -90, 0, "w")
    ctx.close()

    # ---------------- V3 Target cards ----------------
    ctx, page = open_page(browser, "v3", errors)
    m = meta["v3"] = {"steps": {}, "tests": {}}
    m["steps"]["base"] = {"shot": "shots/v3-hero.png", "hl": rect(page, "article.card .verdict")}
    page.click("article.card[data-target='full-circle-slow'] .focusbtn")
    page.wait_for_timeout(700)
    m["steps"]["focus"] = {"shot": shot(page, "v3-focus"), "hl": rect(page, ".focus-split .side")}
    m["tests"]["drag_fold_persist"] = drag_test(page, ".focus-split .gutter", ".focus-split .side", -80, 0, "w")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.click("button[data-v='fbabs']")
    page.wait_for_timeout(700)
    m["steps"]["fbtorque"] = {"shot": shot(page, "v3-fbtorque"), "hl": rect(page, "button[data-v='fbabs']")}
    m["tests"]["drill"] = drill_test(page, "article.card .cfoot a.btn")
    ctx.close()

    # ---------------- V4 Torque budget board ----------------
    ctx, page = open_page(browser, "v4", errors)
    m = meta["v4"] = {"steps": {}, "tests": {}}
    m["steps"]["base"] = {"shot": "shots/v4-hero.png", "hl": rect(page, ".cols .col")}
    page.click(".brow[data-run='full-circle-fast/real-04']")
    page.mouse.move(1430, 640)
    page.wait_for_timeout(700)
    m["steps"]["fastrun"] = {"shot": shot(page, "v4-fastrun"), "hl": rect(page, ".brow[data-run='full-circle-fast/real-04']")}
    page.click("#rows-ctl button[data-v='groups']")
    page.wait_for_timeout(600)
    m["steps"]["groups"] = {"shot": shot(page, "v4-groups"), "hl": rect(page, "#rows-ctl")}
    m["tests"]["drill"] = drill_test(page, ".chead a.drill")
    m["tests"]["drag_fold_persist"] = drag_test(page, ".gutter.row", ".drawer", 0, -80, "h")
    ctx.close()

    # ---------------- V5 Run ledger ----------------
    ctx, page = open_page(browser, "v5", errors)
    m = meta["v5"] = {"steps": {}, "tests": {}}
    m["steps"]["base"] = {"shot": "shots/v5-hero.png", "hl": rect(page, ".banner")}
    page.click("#limits-ctl button[data-v='lane']")
    page.wait_for_timeout(600)
    m["steps"]["lane"] = {"shot": shot(page, "v5-lane"), "hl": rect(page, "#limits-ctl")}
    page.click("#limits-ctl button[data-v='phase']")
    page.click("button[data-v='fbShare']")
    page.wait_for_timeout(400)
    page.click(".lrow[data-run='full-circle-fast/real-01']")
    page.mouse.move(1430, 640)
    page.wait_for_timeout(700)
    m["steps"]["fbshare"] = {"shot": shot(page, "v5-fbshare"), "hl": rect(page, ".lrow[data-run='full-circle-fast/real-01']")}
    m["tests"]["drill"] = drill_test(page, ".lane a.drill")
    m["tests"]["drag_fold_persist"] = drag_test(page, ".split-h > .gutter", ".ledger", 70, 0, "w")
    m["tests"]["drawer_drag_fold_persist"] = drag_test(page, ".gutter.row", ".drawer", 0, -60, "h")
    ctx.close()
    return meta


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", args=["--disable-gpu", "--no-sandbox"])
        try:
            if MODE == "check":
                for v in VARIANTS:
                    ctx, page = open_page(browser, v, errors)
                    info = page.evaluate("() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight, charts: document.querySelectorAll('.uplot').length })")
                    print(v, info)
                    ctx.close()
            else:
                meta = states(browser, errors)
                meta["console_errors"] = errors
                (SHOTS / "states.json").write_text(json.dumps(meta, indent=2))
                for v in VARIANTS:
                    print(v, json.dumps(meta[v]["tests"]))
        finally:
            browser.close()
    print("console errors:", errors or "none")


if __name__ == "__main__":
    main()
