#!/usr/bin/env python3
"""The prune surface for the V2-tabs round (babble, 2026-11-24): one deck-shell gallery of three proposals for a fourth
tab on V2's workbench (traj_compare on the stock data-ui workbench).

    python3 /home/bam/traj_compare/docs/proposals/v2-tabs-2026-11-24/build_gallery.py

Reads criteria.json (frozen before the three were built), gallery-content.json (names, theses, scores: written after
every tab existed and was checked), shots/<t>/check.json + its stills and session.webm (check.cjs). Writes JPEG/MP4
media to reports/media/v2-tab-proposals-2026-11-24/ and the gallery beside it, then runs the skill's strict check.
Stdlib + ffmpeg. Adapted from ../tensorboard-2026-11-24/build_gallery.py.
"""

from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = Path("/home/bam/traj_compare/reports/media")
SLUG = "v2-tab-proposals-2026-11-24"
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


def fmt(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.4g}"
    return f"{x:,}" if isinstance(x, int) else str(x)


def recount_table(vid: str, check: dict) -> str:
    """The new tab's numbers as the page drew them and as build_tabs.py's Python oracle counts them, both states."""
    rc = check["checks"]["recount"]
    keys = {"t1": [("n", "n", "pairs"), ("med", "median", "median real ÷ predicted"), ("worse", "worse", "real worse")],
            "t3": [("n", "n", "targets both ran"), ("bw", "b_better", "B better"), ("aw", "a_better", "A better"),
                   ("t", "tie", "ties"), ("med", "median", "median B ÷ A")],
            "t2": [("planes", "planes", "joint planes"), ("cells", "cells", "cells with error"),
                   ("median_cell", "median_cell", "median cell, °")]}[vid]
    rows = []
    for g, w, label in keys:
        cells = []
        for state in ("unfiltered", "scenario"):
            page = (rc.get(state) or {}).get("page") or {}
            want = (rc.get(state) or {}).get("oracle") or {}
            cells.append(f"<td>{fmt(page.get(g))}</td><td>{fmt(want.get(w))}</td>")
        rows.append(f"<tr><th>{html.escape(label)}</th>{''.join(cells)}</tr>")
    if vid == "t2":
        cells = []
        for state in ("unfiltered", "scenario"):
            pw = ((rc.get(state) or {}).get("page") or {}).get("worst") or {}
            ow = ((rc.get(state) or {}).get("oracle") or {}).get("worst") or {}
            cells.append(f"<td>{html.escape(str(pw.get('joint')))} · cell {pw.get('cell')} · {fmt(pw.get('median'))}°</td>"
                         f"<td>{html.escape(str(ow.get('joint')))} · cell {ow.get('cell')} · {fmt(ow.get('median'))}°</td>")
        rows.append(f"<tr><th>worst cell</th>{''.join(cells)}</tr>")
    ok = all((rc.get(s) or {}).get("ok") for s in ("unfiltered", "scenario"))
    return ("<style>.rc{font:13px/1.45 system-ui;padding:14px 16px}.rc table{border-collapse:collapse;width:100%}"
            ".rc th,.rc td{border-bottom:1px solid #d0d7de;padding:5px 8px;text-align:right}.rc th{text-align:left;font-weight:600}"
            ".rc thead th{text-align:right;color:#57606a;font-weight:600}.rc p{margin:8px 0 0;color:#57606a}</style>"
            "<div class='rc'><table><thead><tr><th></th><th>every run · page</th><th>oracle</th><th>one pick · page</th>"
            f"<th>oracle</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
            f"<p>{'Equal' if ok else 'NOT equal'} in both states (check.cjs reads the page; build_tabs.py counts the same rule "
            "in Python over the same rows, data/oracle.json).</p></div>")


def gate_results(vid: str, check: dict) -> dict:
    """Hard gates from check.cjs's JSON, never typed by hand (G1 and G2 are by construction: say how)."""
    c = check["checks"]
    tabs = c.get("tabs", [])
    d = c.get("drill") or {}
    clean = not check["errors"] and check.get("overflow", 1) <= 0 and all(t["overflow"] <= 0 for t in tabs)
    return {
        "g1": {"pass": True, "evidence": "V2's rows (18,507 runs) and the derived file build_tabs.py writes from them and the bench's own series; nothing typed"},
        "g2": {"pass": len(tabs) == 4, "evidence": f"tabs {[t['id'] for t in tabs]} on V2's unchanged .base + one page; served by serve.py on 127.0.0.1:8852"},
        "g3": {"pass": bool(c.get("recountOk")), "evidence": "page = oracle, unfiltered and after the one pick: "
               + "; ".join(f"{k}: {'ok' if v.get('ok') else v.get('diffs')}" for k, v in (c.get("recount") or {}).items())},
        "g4": {"pass": bool(d.get("keep")) and bool(d.get("backKeepsTab")) and bool((d.get("state") or {}).get("selected")),
               "evidence": f"keep={d.get('keep')}; back keeps the tab {d.get('backKeepsTab')}, the filter {d.get('backKeepsFilter')}; "
                           f"target view {d.get('state')}; Open in Rerun n={((d.get('rerun') or {}).get('answer') or {}).get('n')}"},
        "g5": {"pass": clean and c["drag"]["ok"] and bool(c.get("fold")),
               "evidence": f"console errors {len(check['errors'])}; overflow per tab {[t['overflow'] for t in tabs]}; rail "
                           f"{c['drag']['before']} → {c['drag']['after']} px, {c['drag']['afterReload']} after reload; folds to {c['fold']['folded']} px"},
    }


def proof_lines(vid: str, check: dict) -> list[str]:
    c = check["checks"]
    d = c.get("drill") or {}
    rc = c.get("recount") or {}
    a = ((d.get("rerun") or {}).get("answer") or {})
    return [f"The tab's numbers equal the Python oracle unfiltered and after the one rail pick ({'yes' if c.get('recountOk') else 'NO'}).",
            f"Drill: keep={d.get('keep')} → target view {d.get('state')}; Open in Rerun → n={a.get('n')} (dry run); back link returns to "
            f"'{(d.get('returned') or {}).get('tab')}' at {(d.get('returned') or {}).get('count')}.",
            f"V2's own checks: one dataset tick {c['filter']['before']} → {c['filter']['after']}; rail {c['drag']['before']} → "
            f"{c['drag']['after']} px, {c['drag']['afterReload']} after reload; folds to {c['fold']['folded']} px.",
            f"Console errors {len(check['errors'])}; sideways overflow {check.get('overflow')} px (1440 × 900, headless Chrome)."]


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    criteria = json.loads((HERE / "criteria.json").read_text())
    content = json.loads((HERE / "gallery-content.json").read_text())
    variants = []
    for entry in content["variants"]:
        vid = entry["id"]
        check = json.loads((SHOTS / vid / "check.json").read_text())
        story = check["checks"]["story"]
        for k in range(1, len(story) + 1):
            jpeg(SHOTS / vid / f"story-{k}.png", MEDIA / f"{vid}-step-{k}.jpg")
        media = []
        webm = SHOTS / vid / "session.webm"
        if webm.exists():
            mp4(webm, MEDIA / f"{vid}-session.mp4")
            media.append({"label": "The walkthrough and every check, recorded",
                          "caption": "check.cjs driving the live prototype (headless, 1440 × 900): the new tab, the one rail pick, the tab's own control, the drill to the target view and back, then V2's own checks.",
                          "html": f'<video src="{SLUG}/{vid}-session.mp4" muted loop playsinline controls autoplay></video>'})
        media.append({"label": "The recount, against the oracle",
                      "caption": "The numbers the page drew (read from Vega's own aggregate, or the host's state) beside build_tabs.py's Python count of the same rule over the same rows.",
                      "html": recount_table(vid, check)})
        back = SHOTS / vid / f"story-{len(story)}-back.png"
        if back.exists():
            jpeg(back, MEDIA / f"{vid}-back.jpg")
            media.append({"label": "‹ All targets: back to the tab, the filter kept",
                          "caption": f"The target view's breadcrumb (back=) returns to this tab with the one pick still on: {(check['checks'].get('drill') or {}).get('returned')}.",
                          "html": img(f"{vid}-back.jpg", "back to the tab")})
        variants.append({
            **{k: v for k, v in entry.items() if k not in ("media",)},
            "gateResults": gate_results(vid, check),
            "proof": proof_lines(vid, check),
            "previewLabel": "walkthrough · real prototype captures",
            "preview": stepped_preview(vid, story),
            "story": {"title": "Walk it", "steps": [
                {"label": s["label"], "caption": s["caption"], "state": f"s{k}", "target": f'.chips button[data-story-to="s{k}"]'}
                for k, s in enumerate(story, start=1)]},
            "media": media + entry.get("media", []),
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
