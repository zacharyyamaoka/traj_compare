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
