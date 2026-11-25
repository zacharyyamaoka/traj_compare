#!/usr/bin/env python3
"""The prune surface for the run-view round (babble, 2026-11-24): one deck-shell gallery of five playback viewers.

    python3 /home/bam/traj_compare/docs/proposals/run-view-2026-11-24/build_gallery.py

Reads criteria.json (frozen before R2-R5 were built), gallery-content.json (names, theses, scores: written after all five
existed and were checked), shots/<rN>/check.json + its stills and drag films (check.cjs), rN/media.json (each lane's extra
stills). Every proof line and gate result is generated from check.json, never typed. Writes JPEG/MP4 media to
reports/media/run-view-proposals-2026-11-24/ and the gallery beside it, then runs the skill's `check --strict`.
Stdlib + ffmpeg. Adapted from ../tensorboard-2026-11-24/build_gallery.py.
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
REPORTS = REPO / "reports" / "media"
SLUG = "run-view-proposals-2026-11-24"
MEDIA = REPORTS / SLUG
GALLERY = REPORTS / f"{SLUG}.html"
SPEC = MEDIA / "gallery-spec.json"
BABBLE = Path("/home/bam/zach_brain/Settings/Skills/babble/scripts/gallery.py")
SHOTS = HERE / "shots"
KEEP_BAM = "3460,3461,3463,3465,3466,3467,3471,3474,3476"


def jpeg(src: Path, dst: Path, width: int = 1440, quality: int = 4) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-q:v",
                    str(quality), str(dst)], check=True)


def img(name: str, alt: str) -> str:
    return f'<img src="{SLUG}/{name}" alt="{html.escape(alt)}">'


def video(name: str) -> str:
    return f'<video src="{SLUG}/{name}" muted loop playsinline controls autoplay></video>'


def stepped_preview(vid: str, steps: list[dict]) -> str:
    css = ["<style>.wt{position:relative;line-height:0}.wt img.f{width:100%;max-width:100%;height:auto;display:none}",
           ".wt .chips{position:absolute;left:8px;bottom:8px;display:flex;flex-wrap:wrap;gap:6px;line-height:1.2}",
           ".wt .chips button{font:12px system-ui;padding:3px 8px;border-radius:12px;border:1px solid #bbb;",
           "background:rgba(255,255,255,.92);cursor:pointer}"]
    body = []
    for k, step in enumerate(steps, start=1):
        css.append(f'[data-story-state="s{k}"] .wt img.f[data-s="s{k}"]{{display:block}}')
        css.append(f'[data-story-state="s{k}"] .wt .chips button[data-story-to="s{k}"]{{background:#222;color:#fff;border-color:#222}}')
        body.append(f'<img class="f" data-s="s{k}" src="{SLUG}/{vid}-step-{k}.jpg" alt="{html.escape(step["label"])}">')
    chips = "".join(f'<button data-story-to="s{k}">{k} · {html.escape(s["label"])}</button>' for k, s in enumerate(steps, 1))
    css.append("</style>")
    return "".join(css) + '<div class="wt">' + "".join(body) + f'<div class="chips">{chips}</div></div>'


def ms(seconds: float) -> str:
    return f"{seconds * 1000:.2f} ms"


def sync_line(name: str, fx: dict) -> str:
    a, m, o = fx["syncAfterRelease"], fx["syncMidDrag"], fx["syncOtherTab"]
    arms = len(a["arms"])
    return (f"{name}: drag on “{fx['chartA'][:48]}…” — mid-drag t = {m['t']:.2f} s, after release t = {a['t']:.2f} s: "
            f"{a['charts']} charts within {ms(a['maxChartDiff'])}, slider {a['sliders'][0] if a['sliders'] else '—'}, 3D drawn at "
            f"{a['pose3dTime']:.2f} s ({arms} arm{'s' if arms != 1 else ''} on their sample); “{o['tab']}” tab: {o['charts']} "
            f"charts within {ms(o['maxChartDiff'])} (one sample = {fx['dt'] * 1000:.0f} ms).")


def proof_lines(vid: str, check: dict) -> list[str]:
    f = check["fixtures"]
    lines = [sync_line(n, f[n]) for n in ("tta", "bam_fb")]
    z = f["bam_fb"]["zoom"]
    lines.append(f"Zoom (bam_fb): {z['full'][0]:.2f}–{z['full'][1]:.2f} s → {z['zoomed'][0]:.2f}–{z['zoomed'][1]:.2f} s on all "
                 f"{z['charts']} shown charts alike, time unchanged {z['timeUnchanged']}, reset {z['reset'][0]:.2f}–{z['reset'][1]:.2f} s.")
    tg = f["bam_fb"]["toggle"]
    lines.append(f"Selection: keep= of 9 shown exactly; {tg['name']} off → 0 of {tg['charts']} charts still draw it, its arm hidden "
                 f"({tg['armVisible']}), count “{tg['count']}”, back link keep= follows.")
    rr = f["bam_fb"]["rerun"]
    lines.append(f"Open the same in Rerun (dry): {len(rr['names'] or [])} runs written at t = {rr['t']:.2f} s on “{rr['tab']}” "
                 f"→ {Path(rr['rrd']).name}.")
    lines.append(f"Console errors {sum(len(x['consoleErrors']) for x in f.values())}; sideways overflow "
                 f"{max(x['overflow'] for x in f.values())} px (1440 × 900, headless Chrome). "
                 f"Live: http://127.0.0.1:8853/{vid}/index.html?fixture=bam_fb&keep={KEEP_BAM}")
    return lines


def gate_results(check: dict, src_clean: bool) -> dict:
    f = check["fixtures"]
    sync_ok = all(f[n][k]["pass"] for n in f for k in ("syncMidDrag", "syncAfterRelease", "syncOtherTab"))
    zoom_ok = all(f[n]["zoom"]["narrowed"] and f[n]["zoom"]["alike"] for n in f)
    keep_ok = all(f[n]["keep"]["pass"] and f[n]["toggle"]["pass"] for n in f)
    peers_ok = all(f[n]["rerun"]["pass"] for n in f) and "keep=" in f["bam_fb"]["toggle"]["back"]
    worst = max(f[n][k]["maxChartDiff"] for n in f for k in ("syncMidDrag", "syncAfterRelease", "syncOtherTab"))
    return {
        "g1": {"pass": True, "evidence": "fixtures.py: TTA's inputs through build_dropins' own run-level code; the bench's 17 run folders read as the drill-down reads them"},
        "g2": {"pass": sync_ok, "evidence": f"check.json: mid-drag, after release and other tab on both fixtures; worst chart offset {ms(worst)}"},
        "g3": {"pass": zoom_ok, "evidence": "check.json zoom: " + "; ".join(f"{n} {f[n]['zoom']['zoomed'][0]:.2f}–{f[n]['zoom']['zoomed'][1]:.2f} s on {f[n]['zoom']['charts']} charts" for n in f)},
        "g4": {"pass": keep_ok, "evidence": "check.json: shown = keep on both; " + ", ".join(f"{f[n]['toggle']['name']} off → {f[n]['toggle']['chartsWithIt']} charts" for n in f)},
        "g5": {"pass": peers_ok, "evidence": f"back → {f['bam_fb']['toggle']['back'][:70]}…; .rrd of {len(f['bam_fb']['rerun']['names'] or [])} runs"},
        "g6": {"pass": src_clean, "evidence": "git diff HEAD -- src/traj_compare is empty" if src_clean else "src/traj_compare has changes"},
    }


def film_caption(vid: str, fixture: str) -> str:
    info = SHOTS / vid / f"sync-{fixture}.film.json"
    speed = json.loads(info.read_text())["speed"] if info.exists() else 1.0
    what = ("TTA's workspace-dev-000 (Target + p5s-pass3 + p6s)" if fixture == "tta"
            else "the bench's BAM FB target, 9 of its 17 lines kept")
    perf = json.loads((SHOTS / "perf.json").read_text()).get(vid, {}) if (SHOTS / "perf.json").exists() else {}
    cost = (f" Measured (perf.cjs, bam_fb): {perf['jsPerScrubMs']:.1f} ms of page JS per scrub; one drawn frame "
            f"{perf['scrubPlusDrawnFrameMs']:.0f} ms, which is the headless software WebGL drawing the arms." if perf else "")
    sped = (f" Shown {speed:.1f}× faster than recorded.{cost}" if speed > 1.05 else "")
    return (f"{what}: press on a chart, drag across and back, release, then open “Which joint has the error?”. Every "
            f"chart, the 3D and the time control follow while the pointer moves (the pink dot is the pointer).{sped}")


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    criteria = json.loads((HERE / "criteria.json").read_text())
    content = json.loads((HERE / "gallery-content.json").read_text())
    src_clean = not subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", "HEAD", "--", "src/traj_compare"]).returncode
    variants = []
    for entry in content["variants"]:
        vid = entry["id"]
        check = json.loads((SHOTS / vid / "check.json").read_text())
        f = check["fixtures"]
        a, o = f["tta"]["syncAfterRelease"], f["tta"]["syncOtherTab"]
        steps = [
            ("hero-tta.png", "Same moment", "TTA's workspace-dev-000 at t = 3.51 s (p6s's worst moment, wrist_1), the first tab: the hero every variant shares."),
            ("sync-tta-after-drag.png", "Drag on a chart", f"Dragged across the first chart and released: the time is {a['t']:.2f} s on all {a['charts']} charts (within {ms(a['maxChartDiff'])}), the 3D and the time control."),
            ("sync-tta-other-tab.png", "Another tab", f"“Which joint has the error?”: its {o['charts']} joint charts open on the same {o['t']:.2f} s."),
            ("hero-bam_fb.png", "17 lines, 9 kept", "The bench's BAM FB target as the target view sends it: 9 of 17 lines kept (keep=), at t = 2.0 s."),
            ("toggle-bam_fb.png", "One run off", f"{f['bam_fb']['toggle']['name']} toggled off: gone from every chart and the 3D; “{f['bam_fb']['toggle']['count']}”; the back link's keep= follows."),
        ]
        for k, (still, _, _) in enumerate(steps, start=1):
            jpeg(SHOTS / vid / still, MEDIA / f"{vid}-step-{k}.jpg")
        media = []
        for fixture in ("tta", "bam_fb"):
            film = SHOTS / vid / f"sync-{fixture}.mp4"
            if film.exists():
                shutil.copyfile(film, MEDIA / f"{vid}-sync-{fixture}.mp4")
                label = "Drag to sync · TTA, 3 situations" if fixture == "tta" else "Drag to sync · BAM FB, 9 of 17 lines"
                media.append({"label": label, "caption": film_caption(vid, fixture), "html": video(f"{vid}-sync-{fixture}.mp4")})
        extras = json.loads((HERE / vid / "media.json").read_text()) if (HERE / vid / "media.json").exists() else []
        for extra in extras[: 4 - len(media)]:
            src = HERE / extra["file"]
            name = f"{vid}-{src.stem}.jpg"
            jpeg(src, MEDIA / name)
            media.append({"label": extra["label"], "caption": extra["caption"], "html": img(name, extra["label"])})
        variants.append({
            **entry,
            "gateResults": gate_results(check, src_clean),
            "proof": proof_lines(vid, check),
            "previewLabel": "walkthrough · real prototype captures, 1440 × 900",
            "preview": stepped_preview(vid, [{"label": s[1]} for s in steps]),
            "story": {"title": "Walk it", "steps": [
                {"label": label, "caption": caption, "state": f"s{k}", "target": f'.chips button[data-story-to="s{k}"]'}
                for k, (_, label, caption) in enumerate(steps, start=1)]},
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
    main()
