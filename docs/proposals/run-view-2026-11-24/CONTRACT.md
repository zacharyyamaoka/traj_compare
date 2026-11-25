# The playback viewer: five proposals (run-view round, 2026-11-24)

Frozen before the variants were built (R1 was built first because it is also the check harness's baseline: the
minimal change to today's viewer). Criteria and gates: `criteria.json`. Lanes write only their own `rN/` (and
`shots/rN/`); this file, `common/`, `fixtures.py`, `serve.py`, `check.cjs` and `criteria.json` are the round's.

## What it is (Zach, Daily Note 2026-11-24)

> "This page is basically just our classic trajectory compare viewer where you can like select a bunch of different
> trajectories and then compare them." · "I think we decide to have this structure with like the 3d viewer and then the
> tabs with the questions and we were doing the same thing in rerun." · "And we of course have rerun as the back door but
> I think we should make sure our built in viewer here is also good." · "a important thing is that as you drag the time
> on any of the figures it syncs across all of the other ones." · "This is actually its own stable sub assembly ... the
> dataset viewer should import [it]. That one basically just compares single target trajectories."

Clarified the same night (l.3227): three levels — **dataset view → target view (summary data) → playback viewer**
("either our custom one or the rerun one"). So this round designs the **playback viewer** (level 3): it is opened FROM
the target view with the runs ticked there, as the peer of opening them in Rerun. Also tonight, on the Rerun version:
"Please show the joints one per row here not with 2 columns" → joints are one per row wherever they are small multiples.

## The user outcome every variant serves

One target trajectory, a selection of its runs (2 to ~40, arriving from the target view), compared through time: drag
the time on any figure and every figure, the 3D pose and the slider follow; read where, which joint, late or off-path,
feedforward or feedback, and the raw signals; go back to the target view, or open the same runs at the same time in
Rerun.

## Invariants (every variant)

- **The frozen structure** (`docs/NAVIGATION.md` Part B): a stage (3D + its time control) pinned beside the question
  tabs `traj_compare.tabs.TABS`, exact titles and headings; every chart title names signal, joint, sign convention and
  unit; angles in degrees; joints one per row; every boundary drags and is remembered; panels fold; plain-word labels;
  no silent truncation (ellipsized names carry the whole name in `title`).
- **Drag-to-sync is the core**: dragging the time on any chart commits it, live, to every chart (other tabs too when
  shown), the 3D pose and the slider. x zoom survives by some other gesture.
- **Selection in the URL**: `?keep=<names or bench line indices>`; toggling a run updates every figure and writes `keep=`
  back. `?t=<s>` opens at a time.
- **Peers**: a visible `‹ Target view` (its href carries the current selection) and **Open the same in Rerun** (the same
  runs, the playhead time, the open tab; `serve.py` writes it with traj_compare's own `rerun_export.write_rrd`).
- **Production untouched**: each variant carries its own copy of every asset it changes (`rN/plots.js`, `style.css`,
  `viewer3d.js`, …, copied from `src/traj_compare/assets` @ 38b5967, changes marked `RV:`); unchanged files load from
  `/assets/`. Real data only.

## The shared scenario (`fixtures.py`, `data/` gitignored)

1. `tta` — the Trajectory Tracking Agent's workspace-dev-000 · ISO 9283 path (Zach's screenshot): Target + p5s-pass3 +
   p6s, built with build_dropins.py's own run-level code from its inputs. Hero moment t = 3.51 s (p6s's worst, wrist_1).
2. `bam_fb` — arm_motion_bench BAM FB, workspace-dev-000 · workspace-v2 · 1 × reference motion speed (115 deg/s): all 17
   lines of that target (16 sim + 1 real, 8 configs, repeats r0–r2), each read as the drill-down reads a run folder,
   coloured by the bench's config colours; arrives with `keep=` of 9 lines (what a target view would send). Hero t = 2.0 s.

Viewport 1440 × 900, light theme, headless Chrome.

## The prototype stop line

Real: both fixtures, the variant's gestures, sync, zoom, selection, the back link, the Rerun recording (written; the
check runs it with `?dry=1`, so no viewer window opens). Not built: production splicing, the dataset viewer importing
the viewer, mobile layouts beyond not breaking, dark-theme polish.

## Load-bearing axes (each variant takes a different position)

| | Variant | Time control | Run selection | Figure layout |
|---|---|---|---|---|
| R1 | Every figure is a scrubber | drag on any chart; Shift-drag / wheel zoom | today's chips | today's: stage + tabs, chart grid |
| R2 | One timeline for the page | one playhead line through every chart + a docked time lane (event markers, zoom brush) | one track per run in the lane | charts stacked full width on the same x pixels |
| R3 | Summary and playback, one page | drag on any chart; zoom by brushing the summary strip | the target view's run list (groups, checkboxes) | run list · stage · tabs; repeats as lines or bands |
| R4 | Rerun parity | Rerun's own gestures and time panel | Rerun's blueprint tree (entity paths, eyes) | the `questions` blueprint, view title bars |
| R5 | Moments first | events: opens at the worst moment, jump / step / snap | rows of each chart's readout table | readout table under every chart; every run's arm a ghost |

## The proof (`check.cjs`, per variant, per fixture → `shots/rN/check.json`)

Hero at the same moment; drag on chart A (the variant's gesture) with a mid-drag sample and after release; read back
from what is DRAWN (`[data-rv-playhead]` boxes, `input.tc-scrub` / `[data-rv-slider]`, the 3D's drawn time and every arm's
posed sample against the payload) on every shown chart, then on another tab; the variant's zoom narrows every chart
alike and resets; `keep=` honoured; one run toggled off disappears from every chart and the 3D and the back link's
`keep=`; Open the same in Rerun writes a recording of exactly the shown runs at the playhead time; no console error, no
sideways overflow. With `--video`, a 1440 × 900 film of the drag-to-sync interaction.

A variant tells the check its gestures in `rN/gestures.json` (`scrub` modifiers or element, `zoom` kind, `reset`, the
run `toggle` selector, the `tab` selector, `snaps` when the drag snaps to events).

## Readback hooks a variant keeps

`common/runview.js` provides `window.__runView` and the header (`#rv-head`: `[data-rv-back]`, `[data-rv-count]`,
`[data-rv-rerun]`, `[data-rv-status]`); a variant may restyle or move them, never drop them. A variant marks each drawn
playhead `[data-rv-playhead]` (one per chart, or one line spanning the charts), keeps the stage slider
`input.tc-scrub` or marks its own `[data-rv-slider]` with `data-rv-time`, keeps `viewer3d.debug()` and exposes
`TrajCompare.state` as today.
