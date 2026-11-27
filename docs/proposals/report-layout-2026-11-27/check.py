#!/usr/bin/env python3
"""Drive all five prototypes headlessly: functional checks, walkthrough stills, phone still, hero video.

    uv run --no-project --with playwright==1.64.1 python /home/bam/traj_compare/docs/proposals/report-layout-2026-11-27/check.py

Headless Chrome only (never a window), 1600 × 1000, dark scheme (what Zach's report shows). Writes shots/<v>/check.json,
step-<k>.png, phone.png, hero.mp4. Every number the gallery prints comes from check.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
VIEW = {"width": 1600, "height": 1000}
ARGS = ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"]

SYNC_JS = """() => {
  const t = Kit.state.time, i = Kit.idxAt(t);
  const vis = [...Kit.charts].filter(r => document.body.contains(r.el) && r.el.offsetParent && r.ph.style.display !== 'none');
  const offs = vis.map(r => Math.abs(r.u.posToVal(parseFloat(r.ph.style.left), 'x') - t));
  const pr = Kit.viewers[0]();
  const want = Kit.F.runs.find(r => r.name === 'measured').path[i];
  const got = pr.measured.p;
  return { t, charts: vis.length, maxChartDiff: offs.length ? Math.max(...offs) : null,
           marker3dErrMm: Math.hypot(got[0]-want[0], got[1]-want[1], got[2]-want[2]) * 1000 };
}"""

from walk import steps  # noqa: E402


FOLD = {  # (action, js that returns true when folded/opened)
    "v1": ("pg.click('[data-fold3d]')", "document.querySelector('.app').classList.contains('folded')"),
    "v2": ("pg.click('[data-tool=ahead]')", "getComputedStyle(document.querySelector('.fly')).display === 'block'"),
    "v3": ("pg.click('[data-insp-toggle]')", "document.querySelector('.app').classList.contains('noinsp')"),
    "v4": ("pg.click('[data-drawer] summary')", "document.querySelector('[data-drawer]').open"),
    "v5": ("pg.click('[data-viewsettings]')", "document.querySelector('[data-hud]').classList.contains('open')"),
}


def url(v):
    return (HERE / v / "index.html").as_uri()


def run_steps(pg, v, out):
    for k, (_, _, acts) in enumerate(steps(v), start=1):
        for a in acts:
            exec(a, {"pg": pg})
            pg.wait_for_timeout(350)
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(out / f"step-{k}.png"))


def reachable(pg, v):
    pg.click("[data-tab=channels]"); pg.wait_for_timeout(300)
    if v == "v5":  # palette: does typing the first 12 letters of each title put it first?
        names = pg.evaluate("Kit.channels.map(c => [c.name, c.title.slice(0, 12)])")
        ok = 0
        for name, q in names:
            pg.fill("[data-palette]", q); pg.wait_for_timeout(30)
            if pg.evaluate("(document.querySelector('[data-hit]') || {dataset: {}}).dataset.hit") == name:
                ok += 1
        pg.fill("[data-palette]", ""); pg.keyboard.press("Escape")
        return ok
    if v == "v4":
        pg.click("[data-flat] summary"); pg.wait_for_timeout(300)
    return pg.evaluate("""() => new Set([...document.querySelectorAll('[data-channel],[data-pick],[data-strip^=ch-]')].map(e => e.dataset.channel || e.dataset.pick || e.dataset.strip.replace(/^ch-/, '').replace(/-\\d+$/, ''))).size""")


def visible_chart_box(pg):
    return pg.evaluate("""() => { const r = [...Kit.charts].find(r => document.body.contains(r.el) && r.el.offsetParent);
      const el = r ? r.u.over : document.querySelector('.spark'); if (!el) return null; const b = el.getBoundingClientRect(); return [b.x, b.y, b.width, b.height]; }""")


def check(b, v):
    out = SHOTS / v
    out.mkdir(parents=True, exist_ok=True)
    ctx = b.new_context(viewport=VIEW, color_scheme="dark")
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(url(v))
    pg.wait_for_timeout(1200)
    res = {"variant": v}
    if v == "v4":  # strips start folded: open the first one so a full chart takes part in the sync checks
        pg.click(".strip .lab >> nth=0"); pg.wait_for_timeout(300)
    res["tabs"] = pg.evaluate("[...document.querySelectorAll('[data-tab]')].map(b => b.textContent.trim())")
    res["leftOfTabs"] = pg.evaluate("""() => { const s = document.querySelector('.kit-3d').getBoundingClientRect(); const t = document.querySelector('[data-tab]').getBoundingClientRect();
      return { stageRight: Math.round(s.right), tabsLeft: Math.round(t.left), stageArea: Math.round(s.width * s.height / 16000) / 100 }; }""")
    # play
    t0 = pg.evaluate("Kit.state.time")
    pg.click("[data-play]"); pg.wait_for_timeout(900); pg.click("[data-play]")
    res["play"] = {"from": t0, "to": pg.evaluate("Kit.state.time")}
    res["syncAfterPlay"] = pg.evaluate(SYNC_JS)
    # drag on the first visible chart
    box = visible_chart_box(pg)
    x0, x1, y = box[0] + box[2] * 0.25, box[0] + box[2] * 0.6, box[1] + box[3] * 0.5
    pg.mouse.move(x0, y); pg.mouse.down()
    for k in range(1, 11):
        pg.mouse.move(x0 + (x1 - x0) * k / 10, y)
    mid = pg.evaluate(SYNC_JS)
    pg.mouse.up()
    res["dragMid"] = mid
    res["syncAfterDrag"] = pg.evaluate(SYNC_JS)
    # worst
    pg.evaluate("Kit.setTime(3.0)")
    pg.click("[data-worst]")
    res["worst"] = {"t": pg.evaluate("Kit.state.time"), "want": pg.evaluate("Kit.WORST_T")}
    # every tab: sync holds
    res["perTab"] = {}
    for tid in ["track", "where", "joints", "timing", "signals", "channels"]:
        pg.click(f"[data-tab={tid}]"); pg.wait_for_timeout(250)
        s = pg.evaluate(SYNC_JS)
        res["perTab"][tid] = {"charts": s["charts"], "maxChartDiff": s["maxChartDiff"],
                              "timeControlInView": pg.evaluate("""() => { const e = document.querySelector('[data-lane]'); const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.height > 20; }""")}
    # run toggle
    pg.click("[data-tab=joints]"); pg.wait_for_timeout(200)
    pg.click("[data-eye=measured] >> nth=0")
    res["runOff"] = pg.evaluate("""() => { const vis = [...Kit.charts].filter(r => document.body.contains(r.el));
      let withIt = 0, shown = 0; vis.forEach(r => r.spec.lines.forEach((l, i) => { if (l.run === 'measured') { withIt++; if (r.u.series[i + 1].show) shown++; } }));
      const mc = Kit.byName.measured.color; const sv = [...document.querySelectorAll('.strip .vals span')];
      const probe = document.createElement('span'); probe.style.color = mc; document.body.appendChild(probe); const want = getComputedStyle(probe).color; probe.remove();
      return { charts: vis.length, linesOfMeasured: withIt, stillShown: shown, marker3dVisible: Kit.viewers[0]().measured.visible,
        stripValues: sv.length, stripValuesOfMeasured: sv.filter(e => getComputedStyle(e).color === want).length }; }""")
    pg.click("[data-eye=measured] >> nth=0")
    # units
    pg.click("[data-units=rad] >> nth=0"); pg.wait_for_timeout(300)
    res["rad"] = pg.evaluate("""() => [...Kit.charts].filter(r => document.body.contains(r.el)).map(r => r.spec.unit).concat([...document.querySelectorAll('[data-strip] .u')].map(e => e.textContent.replace(/[\\[\\]]/g, '')))""")
    pg.click("[data-units=deg] >> nth=0"); pg.wait_for_timeout(300)
    res["deg"] = pg.evaluate("""() => [...Kit.charts].filter(r => document.body.contains(r.el)).map(r => r.spec.unit).concat([...document.querySelectorAll('[data-strip] .u')].map(e => e.textContent.replace(/[\\[\\]]/g, '')))""")
    # rerun (simulated)
    pg.click("[data-rerun] >> nth=0"); pg.wait_for_timeout(200)
    res["rerunToast"] = pg.evaluate("(() => { const t = document.querySelector('.kit-toast'); return t && t.style.display !== 'none' ? t.innerText.slice(0, 160) : null; })()")
    # channels reachable: count distinct channel names the page can show/pick
    res["channelsReachable"] = reachable(pg, v)
    # splitter drag + remembered after reload
    sp = pg.evaluate("""() => { const s = document.querySelector('.split.v'); const b = s.getBoundingClientRect(); const L = s.previousElementSibling.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2, L.width]; }""")
    pg.mouse.move(sp[0], sp[1]); pg.mouse.down(); pg.mouse.move(sp[0] - 90, sp[1], steps=6); pg.mouse.up()
    after = pg.evaluate("document.querySelector('.split.v').previousElementSibling.getBoundingClientRect().width")
    pg.reload(); pg.wait_for_timeout(900)
    reloaded = pg.evaluate("document.querySelector('.split.v').previousElementSibling.getBoundingClientRect().width")
    res["splitter"] = {"before": sp[2], "after": after, "afterReload": reloaded}
    # fold
    act, probe = FOLD[v]
    exec(act, {"pg": pg}); pg.wait_for_timeout(300)
    res["fold"] = pg.evaluate(probe)
    ctx.close()
    # walkthrough stills (fresh context = default state)
    ctx = b.new_context(viewport=VIEW, color_scheme="dark")
    pg = ctx.new_page(); pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None); pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(url(v)); pg.wait_for_timeout(1200)
    run_steps(pg, v, out)
    ctx.close()
    # phone
    ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", device_scale_factor=2)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(url(v)); pg.wait_for_timeout(1200)
    res["phone"] = pg.evaluate("({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth })")
    pg.screenshot(path=str(out / "phone.png"))
    ctx.close()
    res["consoleErrors"] = errors
    (out / "check.json").write_text(json.dumps(res, indent=1))
    return res


def hero(b, v):
    """A real recording of the prototype via CDP screencast (Playwright's own video needs a binary it does not ship here)."""
    import base64
    out = SHOTS / v
    frames = out / "frames"
    frames.mkdir(exist_ok=True)
    for f in frames.glob("*.jpg"):
        f.unlink()
    ctx = b.new_context(viewport=VIEW, color_scheme="dark")
    pg = ctx.new_page()
    pg.goto(url(v)); pg.wait_for_timeout(900)
    cdp = ctx.new_cdp_session(pg)
    got = []

    def on_frame(ev):
        k = len(got)
        (frames / f"{k:05d}.jpg").write_bytes(base64.b64decode(ev["data"]))
        got.append(ev["metadata"]["timestamp"])
        try:
            cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            pass
    cdp.on("Page.screencastFrame", on_frame)
    cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 80, "maxWidth": 1280, "maxHeight": 800, "everyNthFrame": 1})
    pg.evaluate("Kit.setTime(0.3)"); pg.wait_for_timeout(500)
    pg.click("[data-play]"); pg.wait_for_timeout(2200); pg.click("[data-play]")
    box = visible_chart_box(pg)
    x0, x1, y = box[0] + box[2] * 0.6, box[0] + box[2] * 0.15, box[1] + box[3] * 0.55
    pg.mouse.move(x0, y); pg.mouse.down()
    for k in range(1, 31):
        pg.mouse.move(x0 + (x1 - x0) * k / 30, y); pg.wait_for_timeout(40)
    pg.mouse.up(); pg.wait_for_timeout(400)
    pg.click("[data-worst]"); pg.wait_for_timeout(700)
    for acts in [s[2] for s in steps(v)[1:4]]:
        for a in acts:
            exec(a, {"pg": pg}); pg.wait_for_timeout(450)
        pg.wait_for_timeout(1000)
    cdp.send("Page.stopScreencast")
    pg.wait_for_timeout(200)
    ctx.close()
    lst = out / "frames.txt"
    lines = []
    for k in range(len(got)):
        dur = (got[k + 1] - got[k]) if k + 1 < len(got) else 0.5
        lines.append(f"file '{frames / f'{k:05d}.jpg'}'\nduration {max(dur, 0.01):.3f}")
    lines.append(f"file '{frames / f'{len(got) - 1:05d}.jpg'}'")
    lst.write_text("\n".join(lines) + "\n")
    mp4 = out / "hero.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", "scale=1280:-2,fps=25", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "28", "-preset", "veryfast", "-an", str(mp4)], check=True)
    for f in frames.glob("*.jpg"):
        f.unlink()
    frames.rmdir(); lst.unlink()
    return {"frames": len(got), "seconds": round(got[-1] - got[0], 1) if got else 0}


def main():
    only = sys.argv[1:] or ["v1", "v2", "v3", "v4", "v5"]
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, channel="chrome", args=ARGS)
        for v in only:
            for attempt in range(3):  # swiftshader's GPU process occasionally crashes a tab under load; the retry is logged
                try:
                    r = check(b, v)
                    r['hero'] = hero(b, v)
                    r['attempts'] = attempt + 1
                    break
                except Exception as e:
                    print(v, "attempt", attempt + 1, "failed:", str(e).splitlines()[0])
                    if not b.is_connected():
                        b = p.chromium.launch(headless=True, channel="chrome", args=ARGS)
            else:
                raise SystemExit(f"{v}: failed 3 times")
            (SHOTS / v / 'check.json').write_text(json.dumps(r, indent=1))
            print(v, json.dumps({k: r[k] for k in ("play", "syncAfterDrag", "worst", "runOff", "splitter", "fold", "phone", "channelsReachable", "consoleErrors")}))
        b.close()


if __name__ == "__main__":
    main()
