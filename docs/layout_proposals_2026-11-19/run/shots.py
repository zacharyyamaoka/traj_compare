"""Interaction-state screenshots + a drag test for the run-view layouts (run by build.py --shots, under the shared lock).

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    flock /tmp/claude-1000/traj-layout-browser.lock taskset -c 2-5,16,17 nice -n 19 \
      uv run --no-project --with playwright==1.64.1 python run/shots.py OUT [--only v1] [--console]

Uses the system Chrome (channel="chrome"), one browser for the whole run, closed at the end. Each state is reached by
driving the real page (clicks, key presses, drags) — never by editing the DOM — and the console is checked for errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

W, H = 1440, 900


def _drag_split(page, selector: str, dx: int) -> dict:
    """Drag a split handle by dx px; return the side panel width before/after (measured, getBoundingClientRect)."""

    handle = page.locator(selector).first
    box = handle.bounding_box()
    before = page.evaluate("(s) => document.querySelector(s).previousElementSibling.getBoundingClientRect().width", selector)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 300)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + dx, box["y"] + 300, steps=8)
    page.mouse.up()
    after = page.evaluate("(s) => document.querySelector(s).previousElementSibling.getBoundingClientRect().width", selector)
    return {"before": round(before), "after": round(after)}


def v1(page, shots: Path, log: dict) -> None:
    page.click("#worst")
    page.wait_for_timeout(500)
    page.screenshot(path=str(shots / "v1-worst.png"))
    page.click(".rv-seg button[data-v='lines']")
    page.locator(".rv-run", has_text="Real #12").click()
    page.wait_for_timeout(400)
    page.screenshot(path=str(shots / "v1-lines.png"))
    page.click(".rv-seg button[data-v='auto']")
    page.evaluate("document.querySelector('#sec-three').scrollIntoView()")
    page.wait_for_timeout(500)
    page.screenshot(path=str(shots / "v1-3d.png"))


def v2(page, shots: Path, log: dict) -> None:
    page.locator(".rv-run", has_text="Real #12").click()
    page.wait_for_timeout(400)
    page.screenshot(path=str(shots / "v2-v2run.png"))
    page.click("#worst")
    page.wait_for_timeout(500)
    page.screenshot(path=str(shots / "v2-worst.png"))


def v3(page, shots: Path, log: dict) -> None:
    page.click("button[data-tab='torque']")
    page.wait_for_timeout(500)
    page.screenshot(path=str(shots / "v3-torque.png"))
    page.click("button[data-tab='when']")
    page.wait_for_timeout(500)
    page.click("#worst")
    page.wait_for_timeout(500)
    page.screenshot(path=str(shots / "v3-when.png"))


def v4(page, shots: Path, log: dict) -> None:
    page.click(".v4-cell[data-cell='0-fb'] .v4-expand")
    page.wait_for_timeout(500)
    page.screenshot(path=str(shots / "v4-expanded.png"))
    page.keyboard.press("Escape")
    page.click(".rv-seg button[data-v='lines']")
    page.wait_for_timeout(400)
    page.screenshot(path=str(shots / "v4-lines.png"))
    page.click(".rv-seg button[data-v='auto']")


def v5(page, shots: Path, log: dict) -> None:
    page.click(".v5-moment[data-rank='1']")
    page.wait_for_timeout(600)
    page.screenshot(path=str(shots / "v5-worst.png"))
    page.click("button[data-target='full-circle-fast']") if page.locator("button[data-target='full-circle-fast']").count() else None
    page.select_option(".rv-select", "full-circle-fast")
    page.wait_for_timeout(600)
    page.click(".v5-moment[data-rank='0']")
    page.wait_for_timeout(600)
    page.screenshot(path=str(shots / "v5-fast.png"))
    page.select_option(".rv-select", "full-circle-slow")


def gallery(browser, out: Path) -> dict:
    """Open the babble gallery itself: heroes render, one hero opens the deck, the walkthrough steps, no console errors."""

    context = browser.new_context(viewport={"width": W, "height": H})
    page = context.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.goto((out / "index.html").as_uri())
    page.wait_for_timeout(2500)
    page.screenshot(path=str(out / "shots" / "gallery-grid.png"))
    imgs = page.evaluate("""() => { let n = 0; const walk = (root) => { root.querySelectorAll('*').forEach(e => { if (e.tagName === 'IMG' && e.complete && e.naturalWidth > 0) n++; if (e.shadowRoot) walk(e.shadowRoot); }); }; walk(document); return n; }""")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "shots" / "gallery-deck.png"))
    page.get_by_role("button", name="Next →").first.click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / "shots" / "gallery-deck-step2.png"))
    page.get_by_text("Live", exact=True).first.click()
    page.wait_for_timeout(2500)
    page.screenshot(path=str(out / "shots" / "gallery-live.png"))
    context.close()
    return {"loaded_images": imgs, "errors": errors}


def main() -> None:
    out = Path(sys.argv[1])
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    shots = out / "shots"
    shots.mkdir(exist_ok=True)
    flows = {"v1": v1, "v2": v2, "v3": v3, "v4": v4, "v5": v5}
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", args=["--disable-gpu", "--no-sandbox"])
        try:
            if "--gallery" in sys.argv:
                report["gallery"] = gallery(browser, out)
                flows = {}
            for name, flow in flows.items():
                if only and name != only:
                    continue
                if not (out / name / "index.html").exists():
                    continue
                context = browser.new_context(viewport={"width": W, "height": H})
                page = context.new_page()
                errors: list[str] = []
                page.on("console", lambda m, errors=errors: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") and "deprecated with r150" not in m.text else None)
                page.on("pageerror", lambda e, errors=errors: errors.append(f"pageerror: {e} | {(e.stack or '')[:600]}"))
                page.goto((out / name / "index.html").as_uri())
                page.wait_for_timeout(900)
                log: dict = {}
                if "--console" not in sys.argv:
                    flow(page, shots, log)
                    page.reload()
                    page.wait_for_timeout(700)
                    log["drag"] = _drag_split(page, ".rv-split", 80)
                    page.reload()
                    page.wait_for_timeout(700)
                    log["width_after_reload"] = round(page.evaluate("document.querySelector('.rv-split').previousElementSibling.getBoundingClientRect().width"))
                    log["drag_back"] = _drag_split(page, ".rv-split", -80)
                    page.dblclick(".rv-split")
                    page.wait_for_timeout(200)
                    log["folded_rail_visible"] = page.evaluate("getComputedStyle(document.querySelector('.rv-rail')).display !== 'none'")
                    page.click(".rv-rail")
                log["errors"] = errors
                report[name] = log
                context.close()
        finally:
            browser.close()
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
