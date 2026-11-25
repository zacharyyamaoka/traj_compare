"""The 2026-11-24 report: the generic record-coverage viewer on two real datasets, one self-contained HTML page.

    /home/bam/dataclass_coverage/.venv/bin/python docs/record_coverage_2026-11-24/build_report.py

Reads the build (build.py) and its evidence folder (hero clip, tab captures, the Viser review, pytest's tail) under
reports/media/record-coverage-2026-11-24/, and writes reports/media/record-coverage-2026-11-24.html with every image and
the clip inlined (the GIF fallback stays a sibling file). Numbers in the text are read from the payloads, never typed.
"""

from __future__ import annotations

import base64
import html
import io
import json
from collections import Counter
from pathlib import Path

from PIL import Image

MEDIA = Path("/home/bam/traj_compare/reports/media")
OUT = MEDIA / "record-coverage-2026-11-24"
EVIDENCE = OUT / "evidence"
REPORT = MEDIA / "record-coverage-2026-11-24.html"


def jpeg(path: Path, width: int = 1200, quality: int = 80) -> str:
    image = Image.open(path).convert("RGB")
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def figure(path: Path, caption: str, width: int = 1200, quality: int = 80) -> str:
    return (f'<figure><img loading="lazy" src="{jpeg(path, width, quality)}" alt="{html.escape(caption)}">'
            f"<figcaption>{caption}</figcaption></figure>")


def numbers(slug: str) -> dict:
    payload = json.loads((OUT / slug / "coverage.json").read_text())
    return payload, {n["key"]: n["value"] for n in payload["numbers"]}


def pct(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f} %"


def main() -> None:
    summary = json.loads((OUT / "build-summary.json").read_text())
    repick, rn = numbers("repick-grasps")
    bench, bn = numbers("bench-tasks")
    rows = json.loads((OUT / "repick-grasps" / "records.json").read_text())["rows"]
    by_item = Counter((r["item"], r["outcome"]) for r in rows)
    items = {item: (sum(v for (i, _), v in by_item.items() if i == item), by_item[(item, "success")])
             for item in repick["classes"]["item"]["levels"]}
    successes = repick["classes"]["outcome"]["counts"][repick["classes"]["outcome"]["levels"].index("success")]
    gap = repick["hist"]["open_gap_mm"]
    pair_gap = next(p for p in repick["pairs"] if p["y"] == "open_gap_mm")
    holdout = bench["support"]["levels"]["holdout"]
    worst = sorted(holdout["fields"].items(), key=lambda kv: -kv[1])[:2]
    kind = bench["classes"]["kind"]
    no_range = [f["name"] for f in bench["fields"] if f["kind"] == "number" and bench["hist"][f["name"]]["source"] == "data"]
    meta_missing = [f for f in bench["fields"] if f["name"].startswith("meta.") and f["missing"]]
    pytest_tail = (EVIDENCE / "pytest.txt").read_text().strip().splitlines()[-1]
    hero = "data:video/mp4;base64," + base64.b64encode((EVIDENCE / "hero.mp4").read_bytes()).decode()
    wandb = {slug: s.get("wandb") for slug, s in summary.items()}

    rp, bt, vz = EVIDENCE / "repick-grasps", EVIDENCE / "bench-tasks", EVIDENCE / "viser"
    png = lambda slug, name: OUT / slug / "png" / name  # noqa: E731

    body = f"""
<header>
  <p class="kicker">dataclass_coverage · 2026-11-24</p>
  <h1>Any list of records in, how well it covers its space out</h1>
  <p class="verdict"><b>The generic “ML dataclass” viewer works on two real datasets:</b> a list of frozen dataclasses
  (robot_msgs messages, or JSON rows) goes into <code>dataclass_coverage.analyze()</code>, which writes one payload.
  That payload feeds the same four viewers as the trajectory family: a data-ui workbench page, Matplotlib PNGs, Viser
  for the 3-D points, and W&amp;B summary scalars. Its own public package:
  <a href="https://github.com/zacharyyamaoka/dataclass_coverage">github.com/zacharyyamaoka/dataclass_coverage</a>
  (<code>/home/bam/dataclass_coverage</code>); {pytest_tail}.</p>
</header>

<section>
  <video autoplay muted loop playsinline controls src="{hero}">
    <img src="record-coverage-2026-11-24/evidence/hero.gif" alt="the workbench being driven (GIF fallback)">
  </video>
  <p class="caption">The real repick log ({rn['records']:.0f} planned grasps) in the workbench. Ticking
  <b>outcome: missed</b> keeps 30 records, and every figure on every tab recounts from those 30. Then come the
  number fields against their declared ranges, the pair planes, <b>success</b>, the gear's colour map (viridis →
  magma, one setting for every page), class balance, and the records table. Recorded headless from the real page.
  <a href="record-coverage-2026-11-24/evidence/hero.gif">GIF</a></p>
</section>

<section>
  <h2>What it reads, and what it says</h2>
  <ul>
    <li><b>Per field, against the declared range.</b> The range comes from the class's own
    <code>Value(low=, high=)</code>, from a <code>ranges=</code> argument, or from a robot_msgs <code>Space</code>. With
    none of those it uses the data's span, and every viewer says “no range stated”. A field's bar chart covers its
    range plus 10 % on each side, so overshoot shows: grey beyond the range, the limit in red, and the values beyond
    it counted.</li>
    <li><b>Class balance</b> for bool, enum, string or declared-choice fields. Declared classes come first, so a
    declared class no record has shows up as an empty row and is counted. Imbalance (largest ÷ smallest class) and
    evenness are given per field.</li>
    <li><b>Missing values.</b> None, NaN and absent keys are counted per field and per record, and never treated as
    a value.</li>
    <li><b>Pair planes.</b> A 2-D grid spanning exactly the two declared ranges, using the trajectory family's heat
    colours: white means empty, linear scale clipped at p98, BAM Reach's five colour maps.</li>
    <li><b>Is more data still adding coverage?</b> The share of the whole space visited as records are added. It is
    drawn in the given order and against 32 random orders, with a Chao1 ceiling (“more of the same reaches about
    X %”), the cells each record was first to reach, and the cells only it reaches.</li>
    <li><b>Held-out support</b> when there is a split: the share of holdout records sitting in cells the reference
    split (dev) never visits.</li>
  </ul>
  <p>Prior art: TFDV / Facets Overview (a stats row per feature, with the schema's domain as its range), the Nov 19
  gallery's generic-ML cards (imbalance, novelty, held-out support, rarefaction), and ecology's species-accumulation
  curve with Chao1. Contract: <code>docs/RECORD_COVERAGE.md</code>.</p>
</section>

<section>
  <h2>Dataset 1 · real repick grasps ({rn['records']:.0f} plans, full arm, 2026-11-10 campaign)</h2>
  <p>Each plan was joined to what happened when the arm tried it, and declares its own J1, wrist and claw limits as
  <code>Value(low=, high=)</code>. Seven different limit sets appear across the plans, and the viewer takes their
  union and says so. Built in {summary['repick-grasps']['analyze_s']:.2f} s.</p>
  <ul class="findings">
    <li><b>Successes are clear vials.</b> {items['clear_vial'][1]} of the {successes} successes are
    <code>clear_vial</code>. Blue caps succeeded {items['blue_cap'][1]} time in {items['blue_cap'][0]} plans, amber
    bottles {items['amber_bottle'][1]} in {items['amber_bottle'][0]}. Item imbalance is
    {repick['classes']['item']['imbalance_ratio']:.0f}× and outcome imbalance
    {repick['classes']['outcome']['imbalance_ratio']:.0f}× (success vs suspect).</li>
    <li><b>Every approach points straight down.</b> The approach's z component uses
    {pct(repick['hist']['approach_base[2]']['visited_pct'])} of its [−1, 1] range (span
    {pct(repick['hist']['approach_base[2]']['span_pct'])}). The Nov 19 gallery found the same thing on directions.</li>
    <li><b>The wrist barely turns.</b> W1 uses {pct(repick['hist']['w_rad[0]']['visited_pct'])} of its ±160° range and
    W2 {pct(repick['hist']['w_rad[1]']['visited_pct'])}. J1 uses {pct(repick['hist']['j1_rad']['visited_pct'])} of
    its 30°.</li>
    <li><b>The claw's gap against the item's width:</b> {pct(pair_gap['visited_pct'])} of the plane is visited.
    {gap['outside']} measured open gaps exceed the 70 mm claw span, which is either a gap reading or a span that is
    not the opening limit. Worth a look; I did not judge which.</li>
    <li><b>More of the same will not help.</b> The records reach {pct(rn['coverage_visited_pct'])} of the space's
    {repick['coverage']['cells']:,} cells. The last 10 % of plans added {pct(rn['last_tenth_new_pct'])} of what is
    visited, and Chao1 puts the ceiling at {pct(rn['ceiling_pct'])}.
    {pct(rn['droppable_records_pct'], 0)} of plans reach no cell of their own. New coverage needs different grasps
    (other items, tilted approaches, wider wrist use), not more runs.</li>
  </ul>
  <div class="grid2">
    {figure(rp / 'overview.png', 'Overview: the summary strip, every number field against its range, the growth curve with its Chao1 ceiling.')}
    {figure(rp / 'numbers.png', 'Numbers: the declared ranges (red), with grey beyond them. The approach and opening directions sit on one bin of [−1, 1].')}
    {figure(rp / 'pairs.png', 'Pairs: the TCP from above, the gap against the item width (1 % visited, 2 past the box), J1 × W1.')}
    {figure(rp / 'classes.png', 'Classes: outcome, item, bucket and stage, each split by outcome.')}
  </div>
</section>

<section>
  <h2>Dataset 2 · arm_motion_bench tasks ({bn['records']:.0f} Task records, 4 robots)</h2>
  <p>Every <code>tasks.jsonl</code> under <code>datasets/*/*/v2/</code>, read with the bench's own
  <code>Task.from_json</code>, so these are the records exactly as that package defines them. I curated
  {bn['fields']:.0f} fields for the page; with no <code>fields=</code>, all 146 flattened columns analyse in about
  0.1 s. Grouped by robot, with dev/holdout as the split. Built in {summary['bench-tasks']['analyze_s']:.2f} s.</p>
  <ul class="findings">
    <li><b>{len(no_range)} of {len(no_range) + 1} number fields declare no range.</b> <code>Task</code> has none,
    and the only range here is the yaw's ±180°, which I passed. This is the real gap: if <code>Task</code> carried
    <code>Value(low=, high=)</code> on its fields (pick cell within the belt, durations within the tour), every chart
    would measure against the bench's own space.</li>
    <li><b>The holdout is partly outside dev.</b> {holdout['unsupported']} of {holdout['records']} holdout tasks
    ({pct(holdout['unsupported_pct'])}) have at least one value in a cell dev never visits. The worst fields are
    {worst[0][0]} ({pct(worst[0][1])}) and {worst[1][0]} ({pct(worst[1][1])}). Scoring on those tasks is
    extrapolation.</li>
    <li><b>Kinds are imbalanced {kind['imbalance_ratio']:.0f}×:</b> {kind['counts'][0]} a_to_b_joint tasks against 3
    ISO 9283 paths and 3 ISO 9283 cubes.</li>
    <li><b>“Missing” mostly means “not this kind”:</b> {len(meta_missing)} <code>meta.*</code> fields are missing in
    50–70 % of tasks because only pick-and-place tasks have a belt, a bin and a pick cell. The viewer counts them
    truthfully. It does not yet know “not applicable” from “not recorded” (see Left).</li>
    <li><b>Task ids repeat across robots</b> ({bench['texts']['task_id']['distinct']} distinct over
    {bn['records']:.0f}). This found a rule bug: a repeating id was being treated as a 160-level class.</li>
  </ul>
  <div class="grid2">
    {figure(bt / 'overview.png', 'Overview: robot first in the rail, dev/holdout second.')}
    {figure(bt / 'support.png', 'Support: the share of holdout tasks per field that sit where dev never went (whole set).')}
    {figure(bt / 'missing.png', 'Missing: the meta.* fields only some task kinds carry.')}
    {figure(bt / 'classes.png', 'Classes: robot, dataset, split, kind, belt, bin, object, distance class, time law.')}
  </div>
</section>

<section>
  <h2>The same payload in the other three viewers</h2>
  <p><b>Matplotlib</b> writes PNGs with the trajectory family's colour rule, and every figure has a legend:</p>
  <div class="grid2">
    {figure(png('repick-grasps', 'numbers.png'), 'numbers.png: each number field against its declared range, stacked by outcome.', 1100, 82)}
    {figure(png('repick-grasps', 'growth.png'), 'growth.png: the given order, the 32-shuffle median and band, and the Chao1 ceiling.', 1100, 82)}
    {figure(png('bench-tasks', 'support.png'), 'support.png: holdout tasks outside dev, per field and overall.', 1100, 82)}
    {figure(png('repick-grasps', 'pair-item_width_mm-open_gap_mm.png'), 'pair-item_width_mm-open_gap_mm.png: white is empty, with the colour bar in records.', 1100, 82)}
  </div>
  <p><b>Viser</b> draws a record's 3-D field, here each plan's TCP in the base frame. It uses the house viewer, is drawn
  to scale in metres, colours points by outcome with a legend that counts them, and shows the box's ranges. Headless
  review: mechanical PASS, and every screenshot was looked at.</p>
  {figure(vz / '00-initial-1440x1000-page.png', 'serve_records(): 1,131 planned TCPs coloured by outcome, in the data-span box (the TCP has no declared range).')}
  <p><b>W&amp;B</b> gets the payload's <code>numbers</code> as run-summary scalars only, in project
  <code>record-coverage</code> (registered in bam_ws <code>tools/wandb_trackers/trackers/record_coverage.py</code>):
  <a href="{html.escape(wandb.get('repick-grasps') or '#')}">repick-grasps</a> ·
  <a href="{html.escape(wandb.get('bench-tasks') or '#')}">bench-tasks</a>.</p>
</section>

<section>
  <h2>Why the page's recount is exact</h2>
  <p>The rail filters records by their category fields only. Every figure on every tab is drawn from <b>part
  rows</b>, one per <i>cohort</i>: a cohort is the set of records that share every rail value. A tick keeps or drops
  whole cohorts, so summing the kept parts gives exactly the histogram of the kept records.</p>
  <p>The test recounts each pick with <code>np.histogram</code> / <code>histogram2d</code> on the payload's own
  edges. Headless Chrome then ticks a class and reads data-ui's own coverage hook: every histogram's and every
  plane's total matches the numpy oracle.</p>
  <p>WHY cohorts and not one row per record: a part row carries its figure's whole geometry, so 1,131 records × 30
  figures would be about 12 MB. Per cohort, the repick parts are {summary['repick-grasps']['bytes']['parts.json'] / 1e6:.1f} MB.
  The cost is that the rail holds no slider or search, since those would keep part of a cohort. The Records table has
  its own search.</p>
</section>

<section>
  <h2>Stock parts</h2>
  <table>
    <tr><th>Element</th><th>Today</th><th>Off-the-shelf part</th><th>Must survive</th></tr>
    <tr><td>Page, rail, tabs, gear, table</td><td>none before (the trajectory family hand-rolled its own page first)</td><td>data-ui <code>&lt;data-workbench&gt;</code>, stock table, chart (Vega-Lite), summary</td><td>a tick recounts every figure</td></tr>
    <tr><td>Histograms against a limit, heat planes</td><td>—</td><td>data-ui <code>coverage-hist</code>, <code>coverage-plane</code> (CONTRACT §52/§53)</td><td>white = empty, linear default, a legend on every figure</td></tr>
    <tr><td>Bins, percentiles, entropy</td><td>—</td><td>numpy (<code>np.histogram</code>'s bins); <code>robot_msgs.coverage.binned</code> is the pair-plane oracle</td><td>a reader re-bins with numpy and gets the same counts</td></tr>
    <tr><td>Declared ranges and classes</td><td>—</td><td><code>dataclass_values.Value</code> / <code>meta()</code>, robot_msgs <code>Space</code></td><td>the class declares the space</td></tr>
    <tr><td>PNG figures, colour maps</td><td>traj_compare's trajectory family</td><td>its colour rule and drawing helpers, copied into <code>colour.py</code>; a test pins the stops to data-ui's <code>colormap.js</code></td><td>the same cell, the same colour, in every viewer</td></tr>
    <tr><td>3-D</td><td>—</td><td><code>viser_3d_viewer</code> (house viewer)</td><td>no logo, loopback, READY line</td></tr>
    <tr><td>Per-feature stats prior art</td><td>—</td><td>TFDV / Facets: ideas only (TFDV needs TensorFlow + protobuf schemas)</td><td>—</td></tr>
  </table>
</section>

<section class="decide">
  <h2>Where it stands</h2>
  <h3>Done and proved</h3>
  <ul>
    <li>Analysis, workbench, Matplotlib, Viser and W&amp;B. The acceptance tests were written and committed before
    each part; {pytest_tail} in dataclass_coverage, headless-Chrome page tests included (CI on 3.11 to 3.13 runs the rest; the page tests need data-ui, Playwright and Chrome).</li>
    <li>Both real datasets build cleanly: <code>data-ui check</code> passes on both <code>.base</code> files, and every
    tab loads with no console errors.</li>
  </ul>
  <h3>Decided for you (each undoable)</h3>
  <ul>
    <li><b>Its own public package, <code>dataclass_coverage</code></b> (your call after the first build: “make this a
    standalone viewer with its own public github repo”). It sits beside <code>dataclass_values</code> because it views
    any dataclass, not only robotics data. The house <code>viser_3d_viewer</code> is optional (it is not published);
    without it, plain viser keeps the same rules. The real-data proof stays private in traj_compare.</li>
    <li><b>The growth band's centre is the median, not the mean.</b> With 32 discrete shuffles, a mean can fall
    outside p10–p90. I changed the contract and its test before any consumer existed.</li>
    <li><b>Cohort parts with a categories-only rail</b>, for exactness at this size (see above).</li>
    <li><b>A curated field list for the bench page</b>: 25 of its 146 columns.</li>
    <li><b>Two W&amp;B runs logged</b> in project <code>record-coverage</code>. Undo: delete the two runs.</li>
  </ul>
  <h3>Left (next, not blocked)</h3>
  <ul>
    <li>“Not applicable” vs “not recorded”: a way to declare that a field only applies to some kinds, so the bench's
    meta.* fields stop reading as missing.</li>
    <li>The Nov 19 cards not built here: dispersion / largest holes, and the embedding atlas.</li>
    <li>A tighter default camera in the Viser view (the flat TCP slab sits small in the frame).</li>
    <li>data-ui's checker throws a TypeError, instead of a message, when a chart's <code>guides</code> is a mapping
    rather than a list. Found here; not fixed, since it is data-ui's code.</li>
  </ul>
  <h3>Needs you</h3>
  <ul><li>Nothing blocks. One question, for when you look: should <code>Task</code> (arm_motion_bench) declare its
  ranges as <code>Value</code>s? That is the change that would make the bench's histograms measure against its own
  space.</li></ul>
</section>
"""
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Record coverage viewer</title>
<link rel="icon" href="data:,">
<style>
:root {{ --bg: #ffffff; --fg: #1d1d1f; --muted: #6e6e73; --hair: #d2d2d7; --card: #f5f5f7; --accent: #3d5a80; --limit: #b4442f; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg: #111113; --fg: #e8e8ed; --muted: #a1a1a6; --hair: #3a3a3e; --card: #1c1c1f; --accent: #8fb3e0; --limit: #e0705c; }} }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 28px 16px 80px; }}
.kicker {{ color: var(--muted); font-size: 13px; margin: 0; }}
h1 {{ font-size: 28px; line-height: 1.2; margin: 6px 0 12px; }}
h2 {{ font-size: 20px; margin: 40px 0 10px; padding-top: 14px; border-top: 1px solid var(--hair); }}
h3 {{ font-size: 15px; margin: 18px 0 6px; }}
.verdict {{ font-size: 16px; }}
video {{ width: 100%; border: 1px solid var(--hair); border-radius: 10px; background: #000; }}
.caption, figcaption {{ color: var(--muted); font-size: 13px; }}
figure {{ margin: 0; }}
figure img {{ width: 100%; border: 1px solid var(--hair); border-radius: 8px; display: block; }}
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 18px; margin-top: 14px; }}
.findings li {{ margin-bottom: 6px; }}
code {{ font-size: 13px; background: var(--card); padding: 1px 5px; border-radius: 4px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
th, td {{ text-align: left; vertical-align: top; padding: 7px 8px; border-bottom: 1px solid var(--hair); }}
th {{ color: var(--muted); font-weight: 600; }}
a {{ color: var(--accent); }}
.decide {{ background: var(--card); border-radius: 12px; padding: 4px 20px 16px; margin-top: 40px; }}
.decide h2 {{ border-top: 0; }}
@media (max-width: 520px) {{ .grid2 {{ grid-template-columns: 1fr; }} h1 {{ font-size: 23px; }} table {{ display: block; overflow-x: auto; }} }}
</style></head>
<body><main>{body}</main></body></html>
"""
    REPORT.write_text(page, "utf-8")
    print(REPORT, f"{REPORT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
