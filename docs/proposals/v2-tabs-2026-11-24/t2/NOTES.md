# T2 — "Where in the workspace is it worst?"

**Thesis:** a fourth tab that places the tracking error where it was made: every joint's position × speed plane, on the
bench's own coverage cells, coloured by the error in each cell over the runs the rail keeps; the answer names the worst
cell, and a click on any cell lists the targets through it.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-tabs-2026-11-24/serve.py --port 8852`,
then `http://127.0.0.1:8852/t2/index.html` and the fourth tab. Data: `python ../build_tabs.py --cells` (35 s; reads the
bench's 650 MB of drawn series once and writes `data/t2-cells.json`, 18.6 MB).

## What is on the page (a host page in the same component, `t2/host.js`)

- **The answer:** "Worst: UR5e + Conveyor PnP cell · wrist_3_joint at position 101 … 116°, speed −102 … −85 °/s: 49.5°
  (median over the 16 targets through that cell; the median cell is 0.0011°)", and which dataset those targets come
  from (here the collision datasets).
- **Every joint's position × speed plane**: data-ui's stock `coverage-plane` (§52) in its own `<data-scope>`, one row per
  joint plane, its `max_other` = the error. One colour scale over every plane (`share`), histogram-equalized (the colour
  bar keeps the real degrees), the stock "colour =" switch to the samples or the targets per cell.
- **Targets through the cell:** a stock table in its own `<data-scope>`, worst first; the worst cell to start, any cell
  on a click (outlined). A row → the stock pane → Open target view: `keep=` the rail's runs of that target, `back=` this
  tab with the filter (V2's own drill, `host-common.js`).

## The rule (on the page and in `build_tabs.py`'s oracle)

A line's error in a cell = the RMS of its joint error (`e_deg`, the bench's own drawn series, 50 Hz) over the instants
the target's reference (q, qd, interpolated at those instants) is in that cell. A cell's value = the median over the
targets through it of (the median over its kept runs). The worst cell = the highest value among cells with 3 or more
targets (one target is noise). The cells are the bench's `coverage.json` q × qd grid (36 × 24 per joint), the Coverage
page's own.

## Decisions

1. Joint space, per joint, position × speed: the error at velocity reversals (qd ≈ 0) and at the range ends shows as a
   band, which a per-run RMS can never show. No tool-space (xyz) version: no tool position is stored per sample.
2. One colour scale across joints, so "which joint" is answered too; equalized, because the error spans five decades.
3. A host page, not a `.base` page: see gap 1.

## Best when / loses when

- **Best when** you are retuning or deciding where to collect more trajectories: it says where in each joint's range and
  speed the controller fails, and which targets to open.
- **Loses when** you need a scalar verdict (that is T3 or the League), or the filter spans robots (one colour scale over
  different robots compares numbers, not motions); it also loads 18.6 MB the first time the tab opens (~1 s).

## Splice parts

- the per-cell error parts (any page that draws coverage could colour by error);
- cell → targets → target view.

## Proof (check.cjs, `shots/t2/check.json`, headless Chrome 1440 × 900)

- Recount = oracle: every run 19 joint planes, 9,423 cells, worst BAM FB c1 cell 807 at 50.10° over 174 targets, median
  cell 0.0729°; Config = ctc_tuned 6 planes, 4,073 cells, worst UR5e wrist_3_joint cell 750 at 49.51° over 16 targets,
  median cell 0.0011°.
- A click on another joint's worst cell lists its targets; a row → `keep=` that target's 3 kept runs → target view with
  3 of 12 lines checked; Open in Rerun → 3 (dry); ‹ All targets returns to this tab at 1,642 of 18,507 runs, redrawn.
- V2's checks unchanged; 0 console errors, 0 px sideways.

## Gaps (named, not patched; each with its ask)

1. **`coverage.sum` cannot take a median over the runs the rail keeps.** It adds part rows and takes the MOST of
   `max_other` (§53). A max over many targets grows with traffic (more targets through a cell, a higher max), so the
   honest colour is a median, computed here by the host; as part rows it would be one row per run and joint, ~67k rows
   and ~50 MB. Ask: `coverage.sum: {by, other: median | mean}` over part rows, or a coverage view that aggregates a value
   column of the default dataset per cell.
2. **A coverage click opens the grid row, not the cell** (`host.open(id, {records})`). The host reads the view's
   read-only hook (`panels[].box`, `nx`, `ny`) to find the cell. Ask: `host.open(id, {records, cell: {i, j}})` and a
   `select:` per cell, so a table beside it can follow the click with no host code.
3. **A scope's events bubble out of a nested scope** (§53): this page's own two scopes would reach the workbench's host
   listeners and redraw in a loop; the host stops them at the nested scope. Ask: `data-scope-*` events stay inside a scope
   that sits in another (or carry the scope they are about).
4. **No per-sample error in any row.** Built offline from `targets/<slug>.js` (the bench's drawn series); production:
   `traj_compare.dataset` writes the per-cell error parts beside the coverage parts.
5. **Only a `<data-dashboard>` page marks the workbench ready** (V2's `host-common.js` tick); the host marks it for this
   page.
6. Seen in V2, not this tab: ticking a Config value also shows a Name search pill with the same text (the Name search
   facet searches `config` too; data-ui's facets on one property share their text, V2 gap 8).
