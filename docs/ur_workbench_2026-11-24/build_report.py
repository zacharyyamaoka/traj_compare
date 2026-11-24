#!/usr/bin/env python3
"""Review report: Zach's four UR5e trajectory datasets in data-ui's stock <data-workbench> (2026-11-24).

    python3 /home/bam/traj_compare/docs/ur_workbench_2026-11-24/build_report.py

Reads the evidence in /home/bam/traj_compare/reports/media/ur-workbench-2026-11-24/ (the saved browser check's
checks.json and stills from arm_motion_bench/docs/check_ur_workbench_1124.cjs, the hero clip recorded from the served
page) and writes /home/bam/traj_compare/reports/media/ur-workbench-2026-11-24.html beside it (media by relative path,
so the page stays small and opens from file://).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

MEDIA = Path("/home/bam/traj_compare/reports/media/ur-workbench-2026-11-24")
OUT = MEDIA.parent / "ur-workbench-2026-11-24.html"
REL = MEDIA.name

STILLS = [
    ("full-1-overview.png", "Two datasets + holdout ticked: 28 of 212",
     "Dataset is the first filter; dev / holdout applies across both datasets ticked. Every figure is the 28 kept "
     "trajectories' cells summed (the check compares each panel with an independent sum)."),
    ("full-0-overview-all.png", "No filter: all four datasets, 212 trajectories",
     "The landing. 'Trajectories per dataset' stacks dev (pink) and holdout (amber); the rail lists each dataset's size."),
    ("embed-1-filters-open.png", "Dropped into a host app (1000 × 680 slot)",
     "The same one tag inside another app: the rail folds into a 'Filters · 2' chip whose panel opens inside the "
     "slot; tabs, count and gear stay. Nothing draws outside the slot (checked at load, with the panel, gear and a record open)."),
    ("full-7-record-open.png", "Drill into one trajectory",
     "A Trajectories row opens data-ui's record pane with its numbers, ‹ › through the 28, and Open in Rerun."),
    ("full-4-tool-position.png", "Tool position, same filter",
     "Switching tabs keeps the filter: the tool from above, front and side for the 28."),
]


def main() -> None:
    checks = json.loads((MEDIA / "checks.json").read_text())
    rows = checks.get("results") or checks.get("checks") or []
    if isinstance(checks, list):
        rows = checks
    passed = sum(1 for r in rows if r.get("ok", r.get("pass")))
    table = "".join(
        f'<tr><td>{"✓" if r.get("ok", r.get("pass")) else "✗"}</td><td>{html.escape(str(r.get("name") or r.get("check") or r.get("gate")))}</td>'
        f'<td><code>{html.escape(json.dumps(r.get("detail", r.get("value", "")), ensure_ascii=False)[:140])}</code></td></tr>'
        for r in rows)
    stills = "".join(
        f'<figure><img src="{REL}/{name}" alt="{html.escape(title)}"><figcaption><b>{html.escape(title)}.</b> '
        f'{html.escape(caption)}</figcaption></figure>' for name, title, caption in STILLS if (MEDIA / name).exists())
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UR5e coverage workbench</title><style>
:root{{--bg:#fbfaf7;--fg:#1f2328;--muted:#57606a;--rule:#d8dee4;--accent:#2563eb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e6e6e6;--muted:#9aa4ae;--rule:#30363d;--accent:#6ea8fe}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:24px;margin:0 0 6px}} h2{{font-size:18px;margin:32px 0 10px;border-top:1px solid var(--rule);padding-top:20px}}
.lead{{font-size:16px}} .muted{{color:var(--muted)}} code{{font-size:12.5px}}
video,img{{width:100%;height:auto;border:1px solid var(--rule);border-radius:8px;background:#fff}}
figure{{margin:0 0 22px}} figcaption{{color:var(--muted);font-size:14px;margin-top:6px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}} td{{border-top:1px solid var(--rule);padding:4px 6px;vertical-align:top}}
ul{{padding-left:20px}} li{{margin:3px 0}}
</style></head><body><main>
<h1>Your four UR datasets in data-ui's stock workbench</h1>
<p class="lead"><b>All 212 UR5e trajectories (four datasets) now open in one data-ui <code>&lt;data-workbench&gt;</code>: Dataset as the first filter,
dev/holdout across every dataset ticked, tabs that keep the filter, a drill with Open in Rerun, and the same tag drops into another app.</b>
It sits beside the hand-rolled coverage page, which is unchanged.</p>
<p class="muted">data-ui main <code>a2b1f7ab</code> (coverage views, CONTRACT §52) + <code>2587b04e</code> (scope + workbench, §53) ·
traj_compare main <code>39e7914</code> + <code>9d3ead8</code> (pushed) · arm_motion_bench main <code>d83fba6</code> · {passed} of {len(rows)} browser checks pass.</p>
<video src="{REL}/hero.mp4" poster="{REL}/full-0-overview-all.png" autoplay muted loop playsinline controls></video>
<p class="muted">Hero (18 s, recorded from the served page): tick Cell · Conveyor PnP and UR5e alone · Workspace, then holdout → 28 of 212;
step through every tab (the count holds); open a row; Open in Rerun. <a href="{REL}/hero.gif">GIF</a>.</p>
<h2>What it looks like</h2>{stills}
<h2>Checks (re-run against the served page)</h2>
<table>{table}</table>
<h2>Decided for you</h2><ul>
<li>Took the round's AI pick without waiting: P5's filter scope as data-ui's core, P1's one-tag workbench as its default layout. Undo: <code>git -C /home/bam/data-ui revert -m 1 2587b04e</code>.</li>
<li>Landed the four coverage figures as stock data-ui views first. Undo: <code>git -C /home/bam/data-ui revert -m 1 a2b1f7ab</code>.</li>
<li>Added the workbench beside the hand-rolled page instead of replacing it. Undo: <code>git -C /home/bam/traj_compare revert 9d3ead8 39e7914</code>.</li>
<li>data-ui's gallery examples use made-up data, so no UR data reaches the public data-ui.dev.</li>
<li>Split colours: dev pink, holdout amber (slots no dataset uses, never red). The first build had both grey under a two-entry legend; fixed with a failing test first.</li>
</ul>
<h2>Left</h2><ul>
<li>The tool maps of the two stations overlay as numbers in each station's own cell frame, not one room; joint maps compare directly.</li>
<li>Unreachable areas aren't greyed on the workbench's tool maps (a filtered part can't carry the whole set's reachable cloud).</li>
<li>Not on the workbench yet: the 3-D views, growth curve, parallel coordinates and slabs (still on the hand-rolled page); numbers that need every sample are left out of summed figures, not guessed.</li>
<li>parts.json is 9.8 MB (histograms stored whole, plus per-dataset copies for stacking); the page draws in about 0.55 s.</li>
<li>data-ui planned, not built: colour-by-dataset in every figure, panels sharing the page height, tabs folding into "N more", a selection carried across pages.</li>
</ul>
<h2>Open it</h2>
<p><code>/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/arm_motion_bench/reports/media/coverage-workbench --port 8861</code>
then <code>http://127.0.0.1:8861/index.html</code> (or <code>/embed.html</code>). Rebuild:
<code>env -u VIRTUAL_ENV /home/bam/arm_motion_bench/.venv/bin/python /home/bam/arm_motion_bench/docs/build_ur_workbench_1124.py</code>.</p>
</main></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(OUT, f"{OUT.stat().st_size / 1e3:.0f} kB", f"{passed}/{len(rows)} checks")


if __name__ == "__main__":
    main()
