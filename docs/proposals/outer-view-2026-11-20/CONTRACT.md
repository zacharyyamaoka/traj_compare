# Outer dataset view: 5 proposals (babble round, frozen 2026-11-20 before any variant was built)

Zach, 2026-11-20 (screenshot of http://127.0.0.1:8779/ur5e/index.html, the bench's scorecard bars): "the landing page is WAYYY
to hard to navigate. Please make 5 proposals for how you can make the outer most dataset view easier to see at a glance and
more compact. At the highest level we want to be comparing different pipeline configurations vs how they do on all of the
targets. Probably using pareto graphs and line charts may be more compact, and you should probably add tabs so it's not all
on the one page."

## Today (what the variants replace)
`index.html` opens on the bench's `summary` (a traj_compare `ReportPage`): 9 metric tiles, then 20 bar-group charts
(4 KPIs: tool tracking RMS, runs passing every gate, energy per task, tool jerk RMS; x 4 datasets x dev/holdout; each bar
group = 5 speeds x 4 controllers), 3 tables and 3 insights. Then traj_compare's Dataset level (1006 target cards / league
table / runs table). About 15 screens of scrolling before the targets.

## User outcome
Open a robot's site and, at a glance, see which pipeline config (controller) does best across all targets, by how much,
where the trade-offs are, and get from there to the targets and runs behind it.

## Invariants (every variant)
- Real data: the bench's UR5e site (`/home/bam/arm_motion_bench/reports/media/dashboard/ur5e/index.html`: 4 configs, 1006
  targets, 4932 lines, sim only; the summary's scorecard charts and tables). No invented numbers.
- traj_compare's stack: one static page, vanilla JS + uPlot (as `src/traj_compare/assets/dataset.js`), opens from file://
  and over `traj_compare.serve`; no CDN, no build step. Config colours from `levels.configs` (C4).
- Tabs: the outer view is split into tabs, so it is no longer one long page. Today's Target level
  (`index.html#/target/<slug>`) and runs table stay reachable.
- Same viewport for every hero: 1440 x 900.

## Weighted criteria (sum 100)
| FR | Weight | Pass condition | 1 | 3 | 5 |
|---|---|---|---|---|---|
| Config verdict at a glance | 30 % | Which config is best overall and by how much is readable above the fold at 1440 x 900 with no scroll or click | Must scroll and read many charts | Visible, but needs reading several numbers | One glance: ranking and magnitude explicit |
| Compact | 20 % | The scorecard's content (4 KPIs x datasets/splits x 5 speeds x configs) fits the Overview tab | > 4 screens | ~2 screens | <= 1 screen |
| Trade-offs visible | 15 % | Shows how configs trade error against cost (energy, jerk, speed) | One metric at a time | Several metrics side by side, no joint view | An explicit joint view / frontier |
| Drill path | 15 % | From a config or a point to the targets where it does worst, then a run | No link | A link to an unfiltered list | Click: filtered worst targets, then the run |
| Generalises | 10 % | Works for 4 configs sim-only (UR5e), 11 configs (BAM FB) and sim + real (pendulum) from traj_compare's generic payload plus the optional summary | Hard-coded to UR5e | Needs per-robot tweaks | Generic |
| Truthful | 10 % | Every number traceable to the payload or the bench scorecard, units shown, n stated, aggregation named (median over what) | Unlabelled aggregates | Mostly labelled | Every number labelled with source and n |

Hard gates (pass/fail): G1 real UR5e data, no fabricated numbers. G2 runs from file:// with no network.

## Directions (allocated before building; each differs on the primary object)
- V1 League table: Overview = one row per config, KPI columns at full speed + inline sparklines of each KPI vs speed,
  rank and delta to the best, n targets; a dataset/split chip filter. Tabs: Overview, Speed sweeps, Targets, Runs.
- V2 Pareto frontier: Overview = scatter, x tool tracking RMS (log), y energy per task; each config a polyline through
  its speeds; the non-dominated frontier marked; dataset/split chips; click a config -> Targets tab filtered to its worst.
- V3 Small multiples: Overview = a grid of small line charts, rows = KPIs, columns = dataset x split, x = speed, one line
  per config, one shared legend; the 20 bar charts become one screen.
- V4 Config x target heatmap: Overview = matrix, rows = configs, columns = all targets sorted by difficulty and grouped by
  dataset / speed, colour = log TCP RMS; hover a column for the target, click -> its Target level.
- V5 Head-to-head: Overview = pick a baseline config (default: lowest median RMS); every other config as the distribution
  of its per-target RMS ratio to the baseline, "better on k of n targets", median ratio, and that ratio vs speed.

Prototype stop line: the Overview tab works on the real data with its primary interaction and its drill path (links into
the real site's `#/target/<slug>` and run reports). Other tabs may be thin, but every visible control works.
