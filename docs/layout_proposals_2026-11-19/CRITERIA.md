# Layout rounds 2026-11-19 — frozen criteria (written before any variant)

Zach, daily note 2026-11-19: five layouts for the standalone viewer's **summary view**, five for its **run view**, five for
the **Rerun run view**; runs grouped by target ("the target is the thing that is constant and identical in everything"),
a TensorBoard-like run list on the left, and real-vs-real×N shown as lines for a few repeats and as a distribution
(median, then min/max or percentile bands, like TensorBoard's histogram fans) for many. The torque breakdown
(CONTRACT.md) is first class in every view.

Shared fixture: `fixture.py` → `fixture/fixture.json` (SIMULATED: vertical 2R arm, 3 targets, 27 real repeats + 3 sims,
ff model v1 nominal vs v2 calibrated). Viewport for every hero: 1440 × 900.

Weights are AI-inferred from the note; Zach may move them. Scores are 1–5 with evidence; total = Σ weight × score / 5.

## Round A — standalone summary view (many runs, every target)

| FR | Weight | What must be true | 1 | 3 | 5 |
| --- | ---: | --- | --- | --- | --- |
| A1 Answer first | 25 | Opening the page says which configuration is better on each target, and by how much (error and FB share), without scrolling | numbers exist but must be hunted | per-target winner visible, magnitude needs reading | one glance: winner, margin, and confidence per target |
| A2 Runs grouped by target | 20 | Runs sit under their target; select / hide / filter by tag (ff model, date, kind) | flat run list | grouped, but filtering is clumsy | TensorBoard-grade: grouped, colour-keyed, filterable, select-all per group |
| A3 Repeat distribution | 20 | real vs real × N spread is readable: lines for a few, bands (median, IQR, p5–p95, min–max) for many | only means | spread shown for one metric | spread over time and per metric, encoding adapts to N |
| A4 Torque budget at summary level | 15 | FF vs FB share, drive gap and saturation per run / group | absent | one number per run | compared across groups and targets at a glance |
| A5 Drill-down | 10 | one click from a run or group to its run view | none | link per run | from any mark (row, band, dot) |
| A6 Scales | 10 | 3 → 100+ runs, 1 → 6 joints without breaking | breaks past ~10 runs | degrades but usable | designed for it (aggregation, virtual lists) |

## Round B — standalone run view (one target and its runs)

| FR | Weight | What must be true | 1 | 3 | 5 |
| --- | ---: | --- | --- | --- | --- |
| B1 Torque breakdown readable | 25 | For a joint and run: target, commanded, feedforward, feedback, applied; how much is FB is evident | five lines in a tangle | readable with effort | the split reads at a glance and at any instant |
| B2 Repeat distribution | 20 | N repeats of the target as lines or percentile bands, automatic or switchable | overplotted lines only | bands for one channel | bands everywhere, lines on demand, one run highlightable against the band |
| B3 Where / when | 20 | error, torque and 3D share the time cursor and zoom, so the bad moment is located | separate, unsynced | synced cursor | cursor + zoom + an explicit "worst moment" jump |
| B4 Runs on the left | 15 | TensorBoard-like run list: toggle, solo, group by tag | chips only | list with toggles | list with groups, solo, colour key, tag filter |
| B5 Calm density | 10 | progressive disclosure, not a wall of 40 plots | wall | sections | one calm answer, detail on demand |
| B6 Fits traj_compare | 10 | buildable in the existing stack (vanilla JS, uPlot, three.js, sections, transport) | rewrite | partial reuse | reuses sections + transport as-is |

## Round C — Rerun run view (stock Rerun 0.40.0)

| FR | Weight | What must be true | 1 | 3 | 5 |
| --- | ---: | --- | --- | --- | --- |
| C1 Torque breakdown at a glance | 25 | target / commanded / FF / FB / applied for a joint and run in one view | spread over tabs | one view per run, cluttered | one view, legible, FB share visible |
| C2 Repeats as a distribution | 20 | many repeats as bands (precomputed p5/p25/median/p75/p95 series) with any one run against them | all lines | bands for one channel | bands for error and torque, one run highlighted |
| C3 Where / when | 20 | 3D, time series (and video when present) on one timeline | separate tabs | same timeline, some scrolling | one screen |
| C4 Scales to repeats | 15 | 14 repeats do not explode the tab bar or legends | one tab per run | grouped | constant structure as N grows |
| C5 Consistent with the HTML | 10 | same names, colours, units as the HTML run view | different | mostly | identical |
| C6 Opens in one step | 10 | blueprint embedded, `uvx --from rerun-sdk==0.40.0 rerun file.rrd` shows it | needs manual setup | needs a second file | embedded |

## Hard gates (all rounds)

- **G1 Self-contained:** standalone pages open from `file://` with no server and no CDN (traj_compare's contract); Rerun
  layouts open in stock Rerun 0.40.0 with the blueprint embedded.
- **G2 Units:** angles in degrees, tool in mm, torque in N·m; SI stays in the stored data.
- **G3 Honest data:** everything shown comes from the shared fixture; every page says SIMULATED.
- **G4 Robot model:** a run view with 3D keeps the robot model available (skill contract).

## Allocated directions (orthogonal on the round's load-bearing axes)

Round A axes: primary object (curve · table · target card · torque budget · history) × navigation × distribution encoding.

- **S1 Scalars board** — TensorBoard's Scalars page: left run sidebar grouped by target with regex filter and colour checkboxes; right, one chart per metric over trajectory time, a percentile fan per config group, smoothing slider.
- **S2 League table** — answer-first table: one row per target × config group; error distribution as a box, FB share, saturation, ISO 9283 repeatability, sparkline; sort, click a row to drill.
- **S3 Target cards** — small multiples: one card per target with its error fan, torque-budget bar per group and a verdict line; the grid is the page.
- **S4 Torque budget board** — torque first: per target, stacked FF | FB | drive-gap bars per run, a beeswarm of FB share by config; error is secondary.
- **S5 Run ledger** — history first: runs along the date / run index, a control chart (SPC) per target lane with limits, to see what changed when (ff v1 → v2).

Round B axes: organising principle (signal · torque · question · joint grid · moment) × torque encoding × repeat encoding.

- **R1 Sidebar + sections** — today's viewer, TensorBoard-ified: left run tree (group by tag, solo, hide), right the existing sections plus Torque breakdown; repeats collapse into bands past a threshold.
- **R2 Torque cockpit** — per joint, commanded drawn as a stacked area (FF + FB) with target dashed and applied thin; error beneath; budget bars beside; one run at a time against its group's band.
- **R3 Question tabs** — mirrors Rerun's questions: Is it good? · Where does the torque come from? · When did it go wrong? · Which joint? — each one composed screen.
- **R4 Joint × signal grid** — a spreadsheet of small multiples: rows = joints, columns = signals (error, τ breakdown, FB share over time, current); every cell carries the repeat band; click a cell to expand.
- **R5 The moment** — one scrubbable stage: big 3D robot, and at the cursor a torque waterfall (target → FF → +FB → commanded → drive gap → applied) for each joint; time plots small underneath.

Round C axes: container structure × torque encoding × repeat encoding.

- **Q1 Torque tab grid** — the smallest extension of `questions`: a tab with a joint × component grid, every run in each view.
- **Q2 Solo run dashboard** — one screen: 3D left; one selected run's per-joint breakdown right; its group's band behind it (one `.rbl` per run to switch).
- **Q3 Distribution first** — per joint, band series (min / p25 / median / p75 / max) for error and FB; individual runs hidden by default, the worst run drawn over the band.
- **Q4 Config-group tabs** — one tab per config group (sim · ff v1 · ff v2), each with breakdown and error for its runs, plus a "v1 vs v2" tab of the two bands.
- **Q5 Oscilloscope stack** — one vertical stack on a shared timeline: 3D / video on top, then error, then commanded / FF / FB, then applied and current, joints as columns.
