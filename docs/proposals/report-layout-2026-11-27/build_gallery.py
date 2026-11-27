#!/usr/bin/env python3
"""The prune surface for the run-report layout round (babble, 2026-11-27): one deck-shell gallery of five layouts.

    python3 /home/bam/traj_compare/docs/proposals/report-layout-2026-11-27/build_gallery.py

Reads criteria.json (frozen before any variant was built), gallery-content.json (written after all five existed and were
checked), shots/<v>/check.json + stills + hero.mp4 (check.py). Proof lines and gate results are generated from
check.json, never typed. Writes gallery-spec.json and gallery.html beside this file, then runs the skill's check --strict.
Stdlib + ffmpeg.
"""

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GALLERY = HERE / "gallery.html"
SPEC = HERE / "gallery-spec.json"
BABBLE = Path("/home/bam/.claude-bam/skills/babble/scripts/gallery.py")
SHOTS = HERE / "shots"
ORDER = ["v1", "v2", "v3", "v4", "v5"]
TABS6 = ["track", "where", "joints", "timing", "signals", "channels"]


def jpeg(src: Path, dst: Path, width: int = 1600) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-q:v", "4", str(dst)], check=True)


def stepped_preview(vid: str, labels: list[str]) -> str:
    css = ["<style>.wt{position:relative;line-height:0}.wt img.f{width:100%;height:auto;display:none}",
           ".wt .chips{position:absolute;left:8px;bottom:8px;display:flex;flex-wrap:wrap;gap:6px;line-height:1.2}",
           ".wt .chips button{font:12px system-ui;padding:3px 9px;border-radius:12px;border:1px solid #888;background:rgba(255,255,255,.94);color:#111;cursor:pointer}"]
    body = []
    for k, label in enumerate(labels, start=1):
        css.append(f'[data-story-state="s{k}"] .wt img.f[data-s="s{k}"]{{display:block}}')
        css.append(f'[data-story-state="s{k}"] .wt .chips button[data-story-to="s{k}"]{{background:#222;color:#fff;border-color:#222}}')
        body.append(f'<img class="f" data-s="s{k}" src="shots/{vid}/step-{k}.jpg" alt="{html.escape(label)}">')
    css.append('.wt img.f[data-s="s1"]{display:block}[data-story-state] .wt img.f[data-s="s1"]{display:none}[data-story-state="s1"] .wt img.f[data-s="s1"]{display:block}')
    chips = "".join(f'<button data-story-to="s{k}">{k} · {html.escape(lb)}</button>' for k, lb in enumerate(labels, 1))
    return "".join(css) + "</style>" + '<div class="wt">' + "".join(body) + f'<div class="chips">{chips}</div></div>'


def ms(x):
    return "—" if x is None else f"{x * 1000:.3f} ms"


def proof(vid: str, c: dict) -> list[str]:
    pt = c["perTab"]
    worst_sync = max((pt[t]["maxChartDiff"] or 0) for t in TABS6)
    r = c["runOff"]
    counts = ", ".join(f"{t} {pt[t]['charts']}" for t in TABS6)
    lines = [
        f"Play 0.9 s: time {c['play']['from']:.2f} → {c['play']['to']:.2f} s; 3D marker on its sample (error {c['syncAfterPlay']['marker3dErrMm']:.3f} mm).",
        f"Drag on a chart: mid-drag t = {c['dragMid']['t']:.2f} s on {c['dragMid']['charts']} chart(s) within {ms(c['dragMid']['maxChartDiff'])}; after release t = {c['syncAfterDrag']['t']:.2f} s, 3D marker error {c['syncAfterDrag']['marker3dErrMm']:.3f} mm.",
        f"All six tabs: time control in view on {sum(pt[t]['timeControlInView'] for t in TABS6)}/6; charts' playheads within {ms(worst_sync)} of the time ({counts} charts).",
        f"Worst moment: {c['worst']['t']:.2f} s (computed {c['worst']['want']:.2f} s). Measured off: {r['stillShown']} of {r['linesOfMeasured']} of its lines still drawn, 3D marker visible = {str(r['marker3dVisible']).lower()}" + (f"; strip values left {r['stripValues']}, of Measured {r['stripValuesOfMeasured']}." if r.get('stripValues') else "."),
        f"rad: units {sorted(set(u for u in c['rad'] if u))} → deg: {sorted(set(u for u in c['deg'] if u))}. Channels reachable: {c['channelsReachable']}/27. Open in Rerun (simulated) shows its command.",
        f"Splitter: {c['splitter']['before']:.0f} → {c['splitter']['after']:.0f} px, {c['splitter']['afterReload']:.0f} px after reload; fold control works = {str(c['fold']).lower()}. Phone 390 px: page {c['phone']['scrollWidth']} px wide. Console errors {len(c['consoleErrors'])}.",
    ]
    return lines


def gates(c: dict) -> dict:
    pt = c["perTab"]
    tabs_ok = len(c["tabs"]) >= 6 and c["leftOfTabs"]["stageRight"] <= c["leftOfTabs"]["tabsLeft"]
    content_ok = (c["channelsReachable"] == 27 and c["worst"]["t"] == c["worst"]["want"] and c["rerunToast"] is not None
                  and any("rad" in (u or "") for u in c["rad"]) and not any("rad" in (u or "") for u in c["deg"]) and c["runOff"]["stillShown"] == 0)
    split_ok = abs(c["splitter"]["after"] - c["splitter"]["before"]) > 30 and abs(c["splitter"]["afterReload"] - c["splitter"]["after"]) < 2 and c["fold"]
    offline_ok = not c["consoleErrors"] and c["phone"]["scrollWidth"] <= c["phone"]["clientWidth"]
    return {
        "g1": {"pass": tabs_ok, "evidence": f"3D ends at x = {c['leftOfTabs']['stageRight']} px, tabs start at {c['leftOfTabs']['tabsLeft']} px; {len(c['tabs'])} question tabs."},
        "g2": {"pass": content_ok, "evidence": f"27/27 channels reachable = {c['channelsReachable']}; worst, deg/rad, eye toggle, Rerun all exercised (check.json)."},
        "g3": {"pass": split_ok, "evidence": f"splitter {c['splitter']['before']:.0f} → {c['splitter']['after']:.0f} px, kept after reload ({c['splitter']['afterReload']:.0f}); fold = {c['fold']}."},
        "g4": {"pass": offline_ok, "evidence": f"file://, vendored uPlot + three.js, extract.py fixture; {len(c['consoleErrors'])} console errors; phone {c['phone']['scrollWidth']} px."},
    }


def main() -> None:
    criteria = json.loads((HERE / "criteria.json").read_text())
    content = json.loads((HERE / "gallery-content.json").read_text())
    import walk as chk  # the walkthrough labels/captions live with the actions that made the stills
    variants = []
    for entry in content["variants"]:
        vid = entry["id"]
        c = json.loads((SHOTS / vid / "check.json").read_text())
        steps = chk.steps(vid)
        for k in range(1, len(steps) + 1):
            jpeg(SHOTS / vid / f"step-{k}.png", SHOTS / vid / f"step-{k}.jpg")
        jpeg(SHOTS / vid / "phone.png", SHOTS / vid / "phone.jpg", width=780)
        hero = c.get("hero", {})
        media = [
            {"label": "Hero clip · play, drag a chart, worst moment, walkthrough", "caption": f"Recorded from the running prototype (headless Chrome, CDP screencast, {hero.get('seconds', '?')} s, {hero.get('frames', '?')} frames): play, drag back across a chart, ◆ worst moment, then walkthrough steps 2–4. Watch the 3D, every chart and the time control move together.",
             "html": f'<video src="shots/{vid}/hero.mp4" muted loop playsinline controls autoplay></video>'},
            {"label": "Live prototype · try it", "caption": f"The real page, running here at 1600 × 1000 scaled down. Drag a chart, press space, open Diagnostics, drag a panel edge. Full size: {vid}/index.html.",
             "html": f'<div style="width:100%;overflow:hidden;line-height:0"><iframe src="{vid}/index.html" title="{html.escape(entry["name"])} live" style="width:1600px;height:1000px;border:0;zoom:.62"></iframe></div>'},
            {"label": "Phone width · 390 px", "caption": f"Below 900 px the panels stack; the page is {c['phone']['scrollWidth']} px wide at 390 (no sideways scroll).",
             "html": f'<img src="shots/{vid}/phone.jpg" alt="{html.escape(entry["name"])} at phone width" style="max-width:390px">'},
        ]
        variants.append({
            **entry,
            "scores": content["scores"][vid],
            "gateResults": gates(c),
            "proof": proof(vid, c),
            "previewLabel": "walkthrough · real prototype captures, 1600 × 1000",
            "preview": stepped_preview(vid, [s[0] for s in steps]),
            "story": {"title": "Walk it", "steps": [
                {"label": label, "caption": caption, "state": f"s{k}", "target": f'.chips button[data-story-to="s{k}"]'}
                for k, (label, caption, _) in enumerate(steps, start=1)]},
            "media": media,
        })
    spec = {"schemaVersion": 3, "title": content["title"], "kicker": content["kicker"], "brief": content["brief"],
            "count": len(variants), "defaultId": content["defaultId"], "defaultWhy": content["defaultWhy"],
            "decisionHinge": content["decisionHinge"], "invariants": content["invariants"], "boundary": content["boundary"],
            "axes": content["axes"], "requirements": criteria["requirements"], "hardGates": criteria["hardGates"],
            "variants": variants}
    SPEC.write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    fresh = GALLERY.with_suffix(".next.html")
    fresh.unlink(missing_ok=True)
    subprocess.run(["python3", str(BABBLE), "build", "--spec", str(SPEC), "--output", str(fresh)], check=True)
    fresh.replace(GALLERY)
    subprocess.run(["python3", str(BABBLE), "check", "--input", str(GALLERY), "--strict"], check=True)
    print(GALLERY, f"{GALLERY.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(HERE))
    main()
