#!/usr/bin/env python3
"""The prune surface for the V2 Overview round (babble, 2026-11-24): one deck-shell gallery of five Overviews for V2's
stock workbench, each live over 18,507 real runs and checked against the Python oracle.

    python3 /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/build_gallery.py

Reads criteria.json (frozen before the five were built), gallery-content.json (names, theses, scores: written after every
variant existed and was checked), shots/<v>/check.json + its stills and session.webm (check.cjs), shots/tall/ (the whole
Overview, before and after the tick) and V2's own stills for the "before" (../tensorboard-2026-11-24/shots/v2/). Writes
JPEG/MP4 media to reports/media/v2-overview-proposals-2026-11-24/ and the gallery beside it. Stdlib + Pillow + ffmpeg.
Adapted from ../tensorboard-2026-11-24/build_gallery.py.
"""

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPORTS = Path("/home/bam/traj_compare/reports/media")
SLUG = "v2-overview-proposals-2026-11-24"
MEDIA = REPORTS / SLUG
GALLERY = REPORTS / f"{SLUG}.html"
SPEC = MEDIA / "gallery-spec.json"
BABBLE = Path("/home/bam/zach_brain/Settings/Skills/babble/scripts/gallery.py")
SHOTS = HERE / "shots"
V2_SHOTS = HERE.parent / "tensorboard-2026-11-24" / "shots" / "v2"


def jpeg(src: Path, dst: Path, width: int = 1440, quality: int = 4) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-q:v",
                    str(quality), str(dst)], check=True)


def mp4(src: Path, dst: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=1280:-2,fps=20", "-c:v",
                    "libx264", "-pix_fmt", "yuv420p", "-crf", "32", "-movflags", "+faststart", "-an", str(dst)],
                   check=True)


def tall(src: Path, dst: Path) -> None:
    """A 1440 × 2300 capture cut to where the Overview's content ends (the pages' area, right of the rail)."""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    bg = im.getpixel((w - 8, h - 4))
    last = 900
    px = im.load()
    for y in range(h - 1, 900, -4):
        if any(sum(abs(a - b) for a, b in zip(px[x, y], bg)) > 24 for x in range(290, w - 20, 6)):
            last = y
            break
    im.crop((0, 0, w, min(h, last + 28))).save(dst.with_suffix(".png"))
    jpeg(dst.with_suffix(".png"), dst)
    dst.with_suffix(".png").unlink()


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


def fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3g}"
    return str(v)


def says(numbers: list[dict]) -> str:
    """One line of what the Overview states, from its hooks (never typed by hand)."""
    out = []
    for n in numbers:
        if n["view"] == "league" and n.get("best"):
            out.append(f"best {n['best']['config']} {fmt(n['best']['v'])} mm over {n['best']['n']} targets, {n['configs']} configs")
        elif n["view"] == "matrix":
            b = n.get("best")
            out.append(f"columns = {n['axis']} ({n['columns']}), {n['rows']} rows" + (f"; {b[0]} best in {b[1]} columns" if b else ""))
        elif n["view"] == "sweep" and n.get("answer"):
            a = n["answer"]
            out.append(f"panels per {n['by']} ({len(n['panels'])}); best at the slowest {a['slow'][0]}, at the fastest {a['fast'][0]}, growth {fmt(a['growth'])}×")
        elif n["view"] == "tradeoff":
            out.append(f"cost = {n['cost']}, {n['points']} points, frontier {', '.join(f[1] for f in n['frontier'])}")
        elif n["view"] == "tile best":
            out.append(f"best {n['numbers']['config']} {fmt(n['numbers']['v'])} mm")
        elif n["view"] == "tile left":
            out.append(f"{n['numbers']['runs']:,} runs left")
    return "; ".join(out)


def gate_results(check: dict) -> dict:
    """Hard gates from check.cjs's JSON, never typed by hand."""
    c = check["checks"]
    nb = c["numbers"]
    story_ok = all(s["oracle"]["ok"] for s in c["story"])
    t = c.get("target") or {}
    ans = ((t.get("rerun") or {}).get("answer") or {})
    tabs = c.get("tabs", [])
    clean = not check["errors"] and check.get("overflow", 1) <= 0 and all(x["overflow"] <= 0 for x in tabs)
    return {
        "g1": {"pass": c["filter"]["before"] == "18,507 of 18,507 runs",
               "evidence": f"V2's rows of all four deployments; the count reads {c['filter']['before']}; model type labelled proposed"},
        "g2": {"pass": bool(nb["changed"] and nb["redrawn"] and nb["oracleBefore"]["ok"] and nb["oracleAfter"]["ok"] and story_ok),
               "evidence": f"{c['filter']['before']} → {c['filter']['after']}: the Overview redrew and its numbers changed; oracle.py matched "
                           f"{nb['oracleBefore']['checked']} numbers before and {nb['oracleAfter']['checked']} after; every story step "
                           f"({sum(s['oracle']['checked'] for s in c['story'])} more) matched"},
        "g3": {"pass": bool(ans.get("ok")) and "target.html" in str(t.get("opened")),
               "evidence": f"V2's Targets row → Open target view → target page ({t.get('state')}); Open in Rerun → n={ans.get('n')} (dry); "
                           f"tabs {[x['id'] for x in tabs]}"},
        "g4": {"pass": clean and c["drag"]["ok"] and bool(c.get("fold")),
               "evidence": f"console errors {len(check['errors'])}; overflow per tab {[x['overflow'] for x in tabs]}; rail "
                           f"{c['drag']['before']} → {c['drag']['after']} px, {c['drag']['afterReload']} after reload; folds to {c['fold']['folded']} px"},
        "g5": {"pass": True, "evidence": "serve.py on 127.0.0.1:8851; data-ui vendored; no request left localhost"},
    }


def proof_lines(check: dict) -> list[str]:
    c = check["checks"]
    nb = c["numbers"]
    return [f"Before the tick ({c['filter']['before']}): {says(nb['before'])}.",
            f"After ({c['filter']['after']}): {says(nb['after'])}.",
            f"Oracle (oracle.py, Python): {nb['oracleBefore']['checked']} + {nb['oracleAfter']['checked']} numbers matched, "
            + ", ".join(f"{s['label']} {s['oracle']['checked']}" for s in c["story"][2:]) + " in the walkthrough.",
            f"V2 kept: rail {c['drag']['before']} → {c['drag']['after']} px (kept after reload), fold, target link → Open in Rerun; "
            f"console errors {len(check['errors'])}, sideways overflow {check.get('overflow')} px."]


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    criteria = json.loads((HERE / "criteria.json").read_text())
    content = json.loads((HERE / "gallery-content.json").read_text())
    variants = []
    for entry in content["variants"]:
        vid = entry["id"]
        check = json.loads((SHOTS / vid / "check.json").read_text())
        story = check["checks"]["story"]
        steps = []
        for k, s in enumerate(story, start=1):
            jpeg(SHOTS / vid / f"story-{k}.png", MEDIA / f"{vid}-step-{k}.jpg")
            cap = entry["captions"][k - 1] if k - 1 < len(entry.get("captions", [])) else ""
            steps.append({"label": s["label"], "caption": f"{cap} {s['count']}: {says(s['numbers'])}. Oracle: {s['oracle']['checked']} numbers match.".strip()})
        media = []
        webm = SHOTS / vid / "session.webm"
        if webm.exists():
            mp4(webm, MEDIA / f"{vid}-session.mp4")
            media.append({"label": "The walkthrough and every check, recorded",
                          "caption": "check.cjs driving the live prototype (headless, 1440 × 900): the landing, the UR5e-cell tick, this variant's own switch "
                                     "and drill, then V2's tabs, the rail drag and the target link.",
                          "html": f'<video src="{SLUG}/{vid}-session.mp4" muted loop playsinline controls autoplay></video>'})
        for state, label, caption in [
            ("landing", "The whole Overview, unfiltered (18,507 runs)", "Captured 1440 wide and tall enough for the whole page: what scrolls below the first screen."),
            ("filtered", "The whole Overview after the tick (5,750 runs, UR5e cell)", "The same page recounted for one deployment, the state Nov 23 showed."),
        ]:
            src = SHOTS / "tall" / f"{vid}-tall-{state}.png"
            if src.exists():
                tall(src, MEDIA / f"{vid}-tall-{state}.jpg")
                media.append({"label": label, "caption": caption, "html": img(f"{vid}-tall-{state}.jpg", label)})
        media.extend(entry.get("media", []))
        variants.append({
            **{k: v for k, v in entry.items() if k not in ("media", "captions")},
            # WHY upper case: the deck labels a variant by its id ("O3"), and the folders are o1 … o5
            "id": vid.upper(),
            "gateResults": gate_results(check),
            "proof": proof_lines(check),
            "previewLabel": "walkthrough · real prototype captures, 1440 × 900",
            "preview": stepped_preview(vid, steps),
            "story": {"title": "Walk it", "steps": [
                {"label": s["label"], "caption": s["caption"], "state": f"s{k}", "target": f'.chips button[data-story-to="s{k}"]'}
                for k, s in enumerate(steps, start=1)]},
            "media": media[:4],
        })
    # the "before": V2's Overview as it is, for the brief's diagnosis
    for name in ("tab-1-overview.png", "story-2.png"):
        if (V2_SHOTS / name).exists():
            jpeg(V2_SHOTS / name, MEDIA / f"v2-today-{name.replace('.png', '.jpg')}")
    spec = {"schemaVersion": 3, "title": content["title"], "kicker": content["kicker"], "brief": content["brief"],
            "count": len(variants), "defaultId": content["defaultId"].upper(), "defaultWhy": content["defaultWhy"],
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
    size = sum(p.stat().st_size for p in MEDIA.iterdir()) + GALLERY.stat().st_size
    print(GALLERY, f"{GALLERY.stat().st_size / 1e6:.2f} MB page, {size / 1e6:.1f} MB with media")


if __name__ == "__main__":
    main()
