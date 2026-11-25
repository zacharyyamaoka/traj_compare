# R3 · Summary and playback, one page

**Thesis:** the target view's summary (a run list with checkboxes, repeats as lines or bands, the "which config tracks
better" verdict) and the playback viewer (stage + question tabs) can be one page for 2 to 40 runs, so a reader picks
runs, reads the repeat summary and plays any instant without leaving the page.

Built from a copy of R1. R1's gesture (drag on any chart commits the time, live) is unchanged. Every R3 change in
`plots.js` / `style.css` is marked `RV: R3`.

## What is on the page (1440 × 900)

- **Run list, far left** (`[data-rv3-runs]`). It replaces the situation chips. Runs are grouped by config
  (`Situation.group`; tta has none, so it shows one group, "Runs"). Each group has a checkbox (indeterminate when only
  some runs are ticked) and `n shown / n`. Each run row has: a checkbox in the run's colour (`[data-rv-run=<name>]`), its
  line style (dashed for a sim run whose config also has a real run, a small band when its config is drawn as a band),
  its whole name (the config's words ellipsize first so "r0 · sim" stays readable; the full name is the hover), its
  **mean** joint RMS error, and **at t**: its largest |joint error| at the playhead. "At t" updates live while you drag;
  the largest shown value is bold. "Group by" switches between config and sim · real (hidden on tta, which has no
  sim/real tags). The list's edge drags (width remembered) and it folds (remembered). Its foot holds the display options
  (Error lines, Angles) and the payload's description.
- **Summary strip, above the tabs** (`[data-rv-strip]`, sticky with the tab strip). For each config, it draws the largest
  joint error over time. With Repeats = Auto (the default), a config with N or fewer shown runs is drawn as lines; past
  N it becomes a median line, a middle-half band (25–75 %) and a min–max band. N is set by "Lines up to", default 5. The
  strip is also the **time navigator**: its x range is always the whole run. Dragging across it zooms every chart to
  that span (the window shows on the strip with the rest shaded). Dragging inside the window pans it, a click goes to
  that time, its black playhead drags, and the wheel zooms. **Reset zoom** sits beside it. The verdict sits to its right:
  "Which config tracks this target better?" Configs are ranked by the median of their shown runs' mean joint RMS error,
  with ×-the-best for each. With no groups (tta) the runs themselves are ranked.
- **Repeats in the charts.** The same Auto / Lines / Bands rule applies, per config, to "Which joint has the error?" (all
  six joint-error charts) and to the track tab's "Largest joint error at each instant". **The other tabs keep one line
  per run:** where, timing, torque and raw signals. Their charts carry a target trace and Δ overlays, and a band of
  signals is a different question.
- **Unchanged:** the shared header (‹ Target view with `keep=`, Open the same in Rerun), the stage (3D + slider), the
  question tabs with their exact titles and headings, and R1's drag-to-scrub, wheel and Shift-drag zoom on the charts.

## Consequential decisions

1. **The strip is the zoom's first way in; the charts keep the drag for time.** The strip's x is fixed at the whole run,
   so it works as overview + detail (a minimap). Zoom never takes the drag away from time on any chart. Wheel and
   Shift-drag on the charts (from R1) still work.
2. **Bands are always per config, whatever the list is grouped by.** Repeats are runs of one config, so a band never
   mixes configs. A band of one run is that run's line. The run lines stay in each chart (hidden while banded), so
   `keep=`, the toggle and the readback are untouched; the band series are extra uPlot series after them, one slot per
   config.
3. **The track tab draws its charts before the statistics table.** At 17 runs the table alone filled a screen, and the
   run list already shows each run's mean error. Now the first chart is on the first screen on both fixtures.
4. **The answer card ("Worst run … best …") and the verdict follow the run list.** Production ranks every run in the
   payload, so with 9 of 17 ticked it named a run that was not shown.
5. **The stage's default width gives way to the run list.** The default stage is narrowed (to no less than its 280 px
   minimum) so the six question titles stay on one line. A width the reader drags is kept. R3 remembers that width under
   its own key (`rv3:stage-width`).
6. **Sub-pixel time (an R1 fix that R3 needed).** Chrome truncates a mouse event's x to whole pixels, while the pointer
   event keeps the fraction. On R3's narrower charts (290 px for 408 samples) a drag landed one sample short. The scrub
   now reads the pointer's sub-pixel x. During a drag, uPlot's whole-pixel hover no longer drives the 3D: the committed
   time does.

## Best when / loses when

- **Best when** the reader arrives with many runs of a few configs and wants to tell repeatability from config effect,
  then play the moment that matters. That is the bench target with 17 runs in 8 configs. The run list answers "which
  run is bad right now" while you drag, and the strip shows where along the motion to look.
- **Loses when** the run count is 2–3 (tta). The run list and verdict take width that R1 gives to the 3D and the charts.
  At 1440 px, the default stage drops to about 290 px with six tabs. Also, sim repeats on this bench are nearly
  identical, so bands are thin. They pay off visually only where repeats really scatter (the real arm, or many runs).

## Keep-parts for a splice

- The **run list** (`buildRunList`), with live "at t" values: it can replace the chip bar in any variant.
- The **summary strip as a navigator** (`buildSummaryStrip`): brush, pan, click to go, a draggable playhead, and the
  shaded window. It also works without the verdict.
- **Band slots in `makeChart`** (`spec.bands`, `repeatSlotOpts` / `repeatSlotData`): an opt-in per chart, with no
  contract change.
- The **sub-pixel scrub** (`preciseX`) and **hover yields to the drag**: small R1 fixes, worth taking whatever wins.

## If this won: what happens to the target level

The target view's per-target page would no longer be needed as its own level. Dataset view → "open target" would land
here with all of that target's runs listed, and the `keep=` the dataset view sends would only pre-tick them. The
target view's other content (the per-joint repeat grid and the feedback-share charts) maps onto this page's "Which
joint has the error?" and "Feedforward or feedback?" tabs. Its basket mode (lines from several targets) does not: one
playback page plays one target. So the cross-target basket would stay with the dataset view. The ‹ Target view link
would become ‹ Dataset view. In this proposal it still points at the target view, because that level exists today.

## Simulated / not built

- Every number is real (both fixtures). Nothing is simulated.
- Not built: dark-theme polish for the new pieces, keyboard access to the strip (the slider and tabs keep theirs),
  dragging the window's edges to resize it (use the wheel), regex filtering of runs (the brief said Group by is
  enough), and bands in the where / timing / torque / signals tabs (deliberately left as lines).
- A banded config whose runs mix sim and real (fullarm_jtc baseline: r0 sim + r0 real) bands them together, as the
  target view does. Group by sim · real only regroups the list, never the bands.

## Change size (vs `src/traj_compare/assets` @ 38b5967)

| file | `diff -u … | grep -c '^[-+]'` | R1 for scale |
| --- | --- | --- |
| plots.js | 1055 | 133 |
| style.css | 162 | 14 |
| viewer3d.js | 20 (R1's `debug()`, unchanged) | 20 |

Most of plots.js is one new contained block: run groups, band slots, the run list and the strip, about 600 lines. The
rest is about 30 marked edits in `makeChart`, the track panel, `buildAnswer`, `setStageWidth` and `buildPage`, where the
run list replaces the chip, Δ and zoom controls. There is no payload or contract change.

## Gestures (`gestures.json`)

scrub = R1's plain drag on a chart · zoom = drag across the strip's plot area (`[data-rv-strip] .u-over`, 0.3 → 0.6) ·
reset = `[data-rv-reset-zoom]` · toggle = the run list checkbox `[data-rv-run="{name}"]` · tab = `[data-tc-tab="{id}"]`.
The extra stills are made by `node r3/extra.cjs` (headless, 1440 × 900).
