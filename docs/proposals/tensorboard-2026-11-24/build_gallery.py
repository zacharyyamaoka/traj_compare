#!/usr/bin/env python3
"""The prune surface for the workbench-levels round (babble, 2026-11-24): one deck-shell gallery of five ways to put
traj_compare's Dataset → Target → Run on data-ui's stock <data-workbench>, with Open in Rerun for a selection.

    python3 /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/build_gallery.py

Reads criteria.json (re-frozen before the five were built), gallery-content.json (names, theses, scores: written after
every variant existed and was checked), shots/<v>/check.json + its stills and session.webm (check.cjs), and the shared
Rerun proof (shots/common/). Writes JPEG/MP4 media to reports/media/tensorboard-proposals-2026-11-24/ and the gallery
beside it. Stdlib + ffmpeg. Adapted from ../dashboard-pattern-2026-11-24/build_gallery.py.
"""

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = Path("/home/bam/traj_compare/reports/media")
SLUG = "tensorboard-proposals-2026-11-24"
MEDIA = REPORTS / SLUG
GALLERY = REPORTS / f"{SLUG}.html"
SPEC = MEDIA / "gallery-spec.json"
BABBLE = Path("/home/bam/zach_brain/Settings/Skills/babble/scripts/gallery.py")
SHOTS = HERE / "shots"


def jpeg(src: Path, dst: Path, width: int = 1440, quality: int = 4) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-q:v",
                    str(quality), str(dst)], check=True)


def mp4(src: Path, dst: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=1280:-2,fps=20", "-c:v",
                    "libx264", "-pix_fmt", "yuv420p", "-crf", "32", "-movflags", "+faststart", "-an", str(dst)],
                   check=True)


def img(name: str, alt: str) -> str:
    return f'<img src="{SLUG}/{name}" alt="{html.escape(alt)}">'


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


def gate_results(vid: str, check: dict) -> dict:
    """Hard gates from check.cjs's JSON, never typed by hand (G1 and G2 are by construction: say how)."""
    c = check["checks"]
    tabs = c.get("tabs", [])
    target = c.get("target") or {}
    answer = ((target.get("rerun") or {}).get("answer") or {})
    clean = not check["errors"] and check.get("overflow", 1) <= 0 and all(t["overflow"] <= 0 for t in tabs)
    return {
        "g1": {"pass": True, "evidence": "rows from build_rows.py over the four bench payloads (extract.py); the count reads "
               + str(c["filter"]["before"])},
        "g2": {"pass": True, "evidence": "served by serve_round.py on 127.0.0.1; no request left localhost (check.cjs ran offline)"},
        "g3": {"pass": bool(tabs) and c["drag"]["ok"] and bool(c.get("fold")),
               "evidence": f"tabs {[t['id'] for t in tabs]}; rail {c['drag']['before']} → {c['drag']['after']} px, "
                           f"{c['drag']['afterReload']} after reload; fold {c.get('fold')}"},
        "g4": {"pass": bool(answer.get("ok")),
               "evidence": f"target view opened at {str(target.get('opened'))[-90:]}; button '{(target.get('rerun') or {}).get('label')}'"
                           f" → {answer.get('n')} runs in {str(answer.get('rrd', ''))[-40:]}"},
        "g5": {"pass": clean, "evidence": f"console errors {len(check['errors'])}: {check['errors'][:2]}; overflow per tab "
                                          f"{[t['overflow'] for t in tabs]}"},
    }


def proof_lines(check: dict) -> list[str]:
    """What check.cjs measured on this variant, as the gallery's proof list (generated, never typed)."""
    c = check["checks"]
    t = c.get("target") or {}
    a = ((t.get("rerun") or {}).get("answer") or {})
    return [f"Filter: {c['filter']['before']} → {c['filter']['after']} after one dataset tick; every tab kept it "
            f"({', '.join(x['id'] + ' ' + str(x['count']) for x in c['tabs'])}).",
            f"Rail: {c['drag']['before']} → {c['drag']['after']} px after a 120 px drag, {c['drag']['afterReload']} after reload; "
            f"folds to {(c.get('fold') or {}).get('folded')} px.",
            f"Target view: {t.get('state')}; Open in Rerun '{(t.get('rerun') or {}).get('label')}' → server n={a.get('n')} "
            f"({len(a.get('entities') or [])} names in the .rrd, dry run).",
            f"Console errors {len(check['errors'])}; sideways overflow {check.get('overflow')} px (1440 × 900, headless Chrome)."]


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    criteria = json.loads((HERE / "criteria.json").read_text())
    content = json.loads((HERE / "gallery-content.json").read_text())
    shared = []
    for name, label, caption in [
        ("rerun-selection-12.png", "Open in Rerun: 12 selected runs, one recording",
         "The shared target view's Open in Rerun on UR5e conveyor-dev-000 at 1 ×: 12 checked lines → one .rrd (stock "
         "robot_msgs.viz.rerun: one plot per joint, one line per run, the target in grey). Read back: 13 position lines per "
         "joint (12 + target), 12 error lines per joint. Shown in Rerun 0.40's own web viewer, headless."),
        ("rerun-selection-12-error.png", "Rerun: the joint error tab of the same selection",
         "error/positions: target − run per joint, the same numbers the target view draws."),
    ]:
        jpeg(SHOTS / "common" / name, MEDIA / name.replace(".png", ".jpg"))
        shared.append({"label": label, "caption": caption, "html": img(name.replace(".png", ".jpg"), label)})
    variants = []
    for entry in content["variants"]:
        vid = entry["id"]
        check = json.loads((SHOTS / vid / "check.json").read_text())
        story = check["checks"]["story"]
        # WHY a first step that is the last state: four of five landings are the same Overview, so the hero opens on
        # where the variant differs (its target view); the walkthrough then replays from the landing.
        last = len(story)
        steps = [{"label": "Where it lands", "caption": story[-1]["caption"]}] + story
        sources = [last] + list(range(1, last + 1))
        while len(steps) > 5:  # the shell's walkthrough takes 2-5 steps: drop the plainest middle one
            del steps[3], sources[3]
        for k, n in enumerate(sources, start=1):
            jpeg(SHOTS / vid / f"story-{n}.png", MEDIA / f"{vid}-step-{k}.jpg")
        media = []
        webm = SHOTS / vid / "session.webm"
        if webm.exists():
            mp4(webm, MEDIA / f"{vid}-session.mp4")
            media.append({"label": "The walkthrough and every check, recorded",
                          "caption": "check.cjs driving the live prototype (headless, 1440 × 900): the story, then the filter, each tab, the rail drag and the target link.",
                          "html": f'<video src="{SLUG}/{vid}-session.mp4" muted loop playsinline controls autoplay></video>'})
        for t in check["checks"].get("tabs", []):
            jpeg(SHOTS / vid / f"tab-{t['id']}.png", MEDIA / f"{vid}-tab-{t['id']}.jpg")
            media.append({"label": f"Tab · {t['id']}", "caption": f"After ticking one dataset in the rail: the count reads “{t['count']}”.",
                          "html": img(f"{vid}-tab-{t['id']}.jpg", t["id"])})
        if (SHOTS / vid / "target-view.png").exists():
            jpeg(SHOTS / vid / "target-view.png", MEDIA / f"{vid}-target.jpg")
            tv = check["checks"].get("target") or {}
            media.append({"label": "The target view, as this variant reaches it",
                          "caption": entry.get("targetCaption", "") + f" Selection on arrival: {tv.get('state')}.",
                          "html": img(f"{vid}-target.jpg", "target view")})
        if (SHOTS / vid / "folded.png").exists():
            jpeg(SHOTS / vid / "folded.png", MEDIA / f"{vid}-folded.jpg")
            media.append({"label": "Rail folded", "caption": "The rail folds; the tabs keep the filter.",
                          "html": img(f"{vid}-folded.jpg", "folded")})
        # WHY four: the deck's strict check (more than four exhibits slows the scan). Kept: the recorded session, the
        # filtered Overview, the target view as this variant reaches it, and Rerun with a selection (shared proof).
        media = [m for m in media if not m["label"].startswith(("Tab · targets", "Tab · runs", "Rail folded"))]
        media.extend(shared[:1])
        media.extend(entry.get("media", []))
        variants.append({
            **{k: v for k, v in entry.items() if k not in ("media", "targetCaption")},
            "gateResults": gate_results(vid, check),
            "proof": proof_lines(check),
            "previewLabel": "walkthrough · real prototype captures",
            "preview": stepped_preview(vid, steps),
            "story": {"title": "Walk it", "steps": [
                {"label": s["label"], "caption": s["caption"], "state": f"s{k}", "target": f'.chips button[data-story-to="s{k}"]'}
                for k, s in enumerate(steps, start=1)]},
            "media": media,
        })
    spec = {"schemaVersion": 3, "title": content["title"], "kicker": content["kicker"], "brief": content["brief"],
            "count": len(variants), "defaultId": content["defaultId"], "defaultWhy": content["defaultWhy"],
            "decisionHinge": content["decisionHinge"], "invariants": content["invariants"], "boundary": content["boundary"],
            "axes": content["axes"], "requirements": criteria["requirements"],
            "hardGates": [{"id": g["id"].lower(), "name": g["name"], "why": g["condition"]} for g in criteria["gates"]],
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
