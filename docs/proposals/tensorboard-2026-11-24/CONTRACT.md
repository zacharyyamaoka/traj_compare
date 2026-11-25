# traj_compare on the stock workbench: Dataset → Target → Run, 5 proposals (re-frozen 2026-11-24 evening)

> **Redirected before any scoring.** The first framing (below the line, "the TensorBoard shell") was superseded the same
> evening: the rail + tabs shell already had its own round (`../dashboard-pattern-2026-11-24/`, Zach "V3 I really like
> this") and is stock data-ui (`<data-scope>` / `<data-workbench>`, data-ui CONTRACT §53). Zach then refined the spec
> (Daily Note Nov 24 ~l.2045–2116). This part is what the five variants build against; `criteria.json` is re-frozen to
> match (the old one is `criteria-shell-v1.json`).

## The spec, in his words

- Runs are atomic: "a trajectory is a trajectory" across datasets and models; each run tries to meet one target; each
  target belongs to a dataset. The rail filters RUNS; Targets shows the targets left; only runs passing every filter show.
- All deployments at the top level; deployment is a filter, not a split; the same config across deployments compares;
  "some grouping by model type across deployments". (The earlier "only same-deployment datasets compare" is kept as a
  WARNING shown when the filter spans deployments, never a block.)
- The rail is TensorBoard-like and big: deployment, dataset, split, model type, config, sim/real, speed, kind, target,
  name search (date range: no bench run carries a date yet — a named gap).
- Tabs: Overview (the League), Targets, Runs. Speed sweeps: an Overview panel (his sentence on it was unfinished).
- Two stages: the outer view across targets, and the target view of one target (today's look: Lines panel with a
  checkbox per run, repeats as lines or bands, joint error and FB share charts) with **Open in Rerun** sending every
  selected run to Rerun as lines.

## Shared parts (every variant)

- Rows: one row per measured line of every deployment (`data/rows-*`), built by `build_rows.py` from `data/<site>.js`
  (extract.py) — `site`, `line` (index into that site's lines), deployment (arm_motion_bench `DEPLOYMENT_TITLES`),
  dataset, split, speed, kind, model type (a PROPOSED mapping in `build_rows.py`, labelled in the UI), config, sim/real,
  target, repeat, the KPIs.
- `serve_round.py`: serves this folder at `/` and the bench's sites at `/bench/<site>/` (run reports built lazily as
  `traj_compare.serve` does), plus `POST /__rerun/selection` `{"runs": [{"site", "line"}]}` → one `.rrd` holding the
  target and every selected run (stock `robot_msgs.viz.rerun.save`: one plot per joint, one line per name) → the pinned
  viewer. One recording, not several: lines share one timeline and overlay in one plot per joint.
- `common/target.html?site=&target=[&keep=1,2,…][&embed=1]` or `?basket=site:line,…`: the target view, traj_compare's
  look, vanilla JS + uPlot over the site's own `targets/<slug>.js`; its Open in Rerun posts the checked lines.

## Directions (allocated before building; they differ on the link, the selection, the tabs, the grouping)

- **V1 The rail is the selection.** Target is a rail facet; when the filter leaves exactly one target the Runs tab
  becomes its target view (iframe, checkboxes = the filtered runs). "Selected" = passes the rail.
- **V2 Two viewers, the filter carried.** Targets and Runs rows drill to `target.html` as its own page; the rail's kept
  runs start checked, the rest listed unchecked; a breadcrumb returns to the workbench with the same URL filter.
  "Selected" = the checkboxes.
- **V3 The target is a workbench page.** Picking a target adds a 4th tab, "Target · <task>", inside the same component
  (droppable as one piece). Selection = its checkboxes; the rail still narrows them.
- **V4 Model × deployment first, target in a side pane.** Overview leads with a model type × deployment matrix and the
  cross-deployment warning, then the League; a Targets row opens the target view in a resizable pane beside the tabs.
- **V5 A selection basket across targets.** Runs rows are added to a basket carried across tabs (a pill: "Selection ·
  N runs"); the target view groups the basket by target and Open in Rerun sends the basket — comparisons across
  targets and deployments (same config on two robots).

## Stop line and proof

Every variant: the rail filters runs on the real rows, the three tabs recount, the link to the target view works with
its carry-over, Open in Rerun posts the selection. Proved once end to end: the `.rrd` for N selected runs holds N
lines per joint (read back), screenshot of Rerun. Not built: production wiring into `dataset.py`, date tags, data-ui
changes (gaps are named, never patched).

---

# (Superseded) first framing: the TensorBoard shell

# traj_compare, the TensorBoard pattern: 5 proposals (babble round, frozen 2026-11-24 before any variant was built)

Zach, Nov 24 (verbatim): "Please make 5 prospoals for how you can make the trajecotyr comparison viewer more like
tensorboard pattern. Message the trajecory coverage viewer to better understand that. but basically its like a filter
side panel on the left, tabs on the top, and then various dashboards like views on each page".

## What he has said that shapes it

- Nov 19: the Target trajectory is the primary organising object; levels dataset → targets (table or cards) → runs,
  sortable by date / config / sim-real; "traj compare could also take a bit of the Tensor board layout with the runs on
  the left"; he liked the Scalars-board sidebar most and "the control over how the lines are showing".
- Nov 20 / 23: compare pipeline configs across all targets first; the League table is the Overview (Part E).
- Nov 24 (coverage viewer): "it lets us filter specifically and then see the analysis on all of the views. Its kinda
  like tensor flow"; "I don't like the tabs here at the top top as then its harder to put it in another app"; "we
  don't need to reinvent the wheel" (data-ui `<data-scope>` / `<data-workbench>`, CONTRACT §53, landed that day);
  "for the single target trajectory now your atomic unit is actually runs ... we are repeating the exact same
  pattern again and again".

## User outcome

Open a bench site, filter on the left what goes in, flip tabs to read dashboards over exactly that subset: which
config wins across targets, how it holds up with speed, where (joint, time) the error sits; then the runs of one
target, without leaving the frame.

## Invariants (every variant)

- Real data: the bench's traj_compare sites `arm_motion_bench/reports/media/dashboard/{ur5e,bam_fb,pendulum}/`.
  `extract.py` copies each payload's per-line numbers to `data/<site>.js` (gitignored, regenerate with it); the drawn
  series are the site's own `targets/<slug>.js`, loaded on demand from the bench folder. Every variant opens UR5e and
  the other two by `?site=`.
- Stack: static pages, vanilla JS + uPlot (vendored copy of traj_compare's), open from `file://`, no CDN, no build.
  V5 alone uses data-ui's vendored build (traj_compare already vendors data-ui, `assets/data_ui`).
- Shared parts in `common/` (`tc.js`, `tc.css`): data loading, the aggregation rules, the league, charts, the
  draggable/foldable panel. Variants differ in how they compose them, never in the numbers.
- Aggregation (named on every figure): a target's value for a config = median over its repeats (lines); a config's
  value = median over targets; the League ranks configs by tool tracking RMS at the fastest speed (1.0 ×), as Part E2.
- Every boundary drags, its width is remembered (localStorage, try/catch), the panel folds.
- League table is the Overview of any variant with one; Coverage stays reachable (↗ link or a tab).
- 1440 × 900 hero, same site (UR5e) and same scenario in every hero.

## Load-bearing axes

1. What the left panel holds: configs (TensorBoard's runs) · a Dataset → Target tree · the current level's atomic
   unit (targets, then runs) · a grouped runs table (W&B) · stock data-ui facets.
2. Tabs by data type (Scalars / Distributions / Time series / Tables, TensorBoard) vs by question (traj_compare's).
3. Where the hierarchy lives: the panel (tree), breadcrumbs, or the tabs.
4. Selection model: global colour + visibility + pins vs per-level.

## Directions (allocated before building)

- **V1 TensorBoard, literally.** Panel = the configs as runs (colour, checkbox, regex), tag filters under it. Tabs by
  data type: Scalars (KPI vs speed, one card per KPI × dataset, collapsible tag groups, pin, fullscreen) ·
  Distributions (per-target RMS histograms per config) · Time series (one target's joint error, median/IQR per config)
  · Tables (the League + targets). A settings pane on the right (smoothing, log y, ignore outliers, x axis).
- **V2 Target tree.** Panel = a Dataset → dataset tag → target tree with checkboxes and search: the hierarchy lives in
  the panel; ticking a branch scopes every tab. Tabs by question: Overview (League) · Speed sweeps · Which joint? ·
  Feedforward or feedback? · Coverage (embedded). Selecting one target leaf adds its run comparison.
- **V3 One frame, every level.** The panel always lists the current level's atomic unit: on the Dataset level the
  targets (facets + sort by worst), on a Target level its runs grouped by config (checkbox, colour, ↗) — the Nov 19
  sidebar. Breadcrumb `Dataset › target` over the tabs; the tabs change with the level (Overview / Sweeps / Targets ·
  How repeatable? / Which joint? / Feedforward or feedback?).
- **V4 Group-by workspace (W&B / Aim).** Panel = a runs table with a Group by control (config, dataset, speed, kind,
  sim/real) — each group a colour, eye and pin; that grouping and colour drive every tab. Tabs are workspace views by
  question; each tab is collapsible panel sections.
- **V5 Stock data-ui workbench.** `<data-workbench src=…base>` over the lines: data-ui's facets as the panel, its
  tabs on the component's own top, pivot/chart/kpi/table views as dashboards, drill to the run report. Zero new shell
  code; whatever data-ui can't draw yet (time series per target) is named, not faked.

## Prototype stop line

Every tab of every variant draws from the real payload and recounts from the panel; the primary interaction and the
drill (into the bench's real `#/target/<slug>` and run reports) work. Not built: production wiring into
`dataset.py`/`dataset.js`, the Rerun side, editing tags.

## Proof (check.cjs)

Headless Chrome 1440 × 900, file://: a still of every tab; a filter measured before/after (count text and a figure's
data); the panel's edge dragged by 120 px and its width measured, then reloaded and measured again; fold; no console
errors; no sideways scroll; a short video of the primary flow.
