# R2 · One timeline for the page

**Thesis.** A video-editor page: ONE time control (a lane docked under the question tabs) and ONE playhead line that
runs through every chart, because every chart and the lane's ruler share the same x pixels.

## What it is

- **The time lane** (`timeline.js`, docked under the tabs column, always in view): transport (to start, step back,
  play / pause, step forward, to end), the readout `t / tMax s`, `‹ ◆ Worst moment ›` (jump to the worst moment of the
  shown runs, or to the previous / next marked moment), Full range, the Angles deg / rad chips, fold.
  Under it: a **ruler** whose x pixels are exactly the charts' plotting area (measured from a shown chart's `.u-over`).
  The ruler is the page's slider (`[data-rv-slider]`, `data-rv-time`, role slider, ← → Home End Space). Press and drag
  on it, on its grip or on any run's track and the time follows, live.
- **One track per run** (17 for bam_fb, grouped by config). Each has an eye (`[data-rv-run]`, the run's on / off
  everywhere), its colour, its full name (ellipsized, whole name in `title`), a Δ overlay toggle, and its error at the
  playhead. Its band is its largest joint error over time (max over joints of |Target − run|, one scale for every run).
  It marks its moments: ◆ worst moment, ▲ "error rises" (the first sample above half its own peak), and × limit broken
  (from `Situation.verdict`). Click a marker to go there. A config row folds its runs like a DAW folder track and its
  eye toggles all of them.
- **A zoom bar** over the whole motion, with an overview of the shown runs' error. Drag a range to zoom every chart,
  drag the window to pan, drag its edges to resize; the wheel over the ruler or the zoom bar zooms; Full range or a
  double-click resets. When the time is outside the zoomed range, its grip waits at that edge; click it to bring the
  time back into view.
- **Stacked charts.** Charts sit one per row at full width in every tab. Each card is a title column (the whole title,
  wrapped, never ellipsized) beside the plot, with a fixed y-axis width (56 px) and fixed uPlot padding. So every
  chart's plotting area starts and ends at the same x as the ruler: measured equal to the pixel on all six tabs of both
  fixtures, including the 54 torque cards.
- **One playhead line** (`[data-rv-playhead]`, 2 px, page ink). It runs from the first chart down to the lane at the
  committed time, scrolls with the charts and continues through the lane's tracks. It passes behind non-time content
  (cards, tables, headings) instead of over their text. Hovering a chart or a track draws a dashed preview line and
  previews that instant in the 3D (R1's hover fix kept).

## Decisions (each reversible)

1. **The stage's own slider is gone; the lane is the only time control.** `buildTransportBar` returns nothing when the
   lane is loaded, so the 3D gets its room back and there is no second slider to keep in step. Readback: the ruler is
   `[data-rv-slider]`.
2. **The ruler scrubs and the zoom bar zooms.** The brief puts both "drag on the ruler = scrub" and "drag a range on
   the ruler = zoom" on one strip. Video editors and Foxglove scrub on the ruler, so that stays. Zoom moved to a separate
   bar over the full range, under the tracks. `gestures.json` zooms with
   `{"kind":"drag","selector":"[data-rv-range]",from 0.3,to 0.6}` and resets with a click on `[data-rv-zoom-reset]`.
3. **The wheel over a chart scrolls the column (R1 zoomed with it).** Full-width stacked charts leave no room to scroll
   otherwise. Zoom: the wheel over the ruler or zoom bar, Ctrl / Alt + wheel over the tracks, Shift-drag on a chart,
   double-click.
4. **App layout at ≥ 901 px**: header · stage beside the tabs column. The tabs' panels scroll in their own column above
   the lane. Below 900 px the page flows and the lane sticks to the bottom. The page's own h2 is hidden because the
   header already names the target. On the track tab the two "when was it worst" charts now come before the statistics
   table: at 17 runs the table pushed both charts below the first screen.
5. **Run selection lives in the tracks.** R1's chips stay in the DOM, hidden, as the state machinery (`keep=`, applyShared).
   The eye, the Δ and the group eye call the chips' own `apply`.
6. Names column width, lane height, lane fold and each config's fold are remembered (localStorage in try/catch, keys
   `traj-compare:rv2:*`). Double-click a handle to go back to the default.

## Best when / loses when

- **Best when** the question is *when*, across many runs and charts. The bands line up across runs: all three `record`
  repeats peak at 1.70–1.71 s on j1, while jtc_baseline peaks at 0.31 s and the model-FF configs near 2.83 s
  (`extra-lane-17.png`). Zoomed around a moment, one line reads every joint at once.
  Playback, stepping and moment jumps work from one place.
- **Loses when** vertical room matters. The lane takes about 180 px (3 runs) to 300 px (17 runs), so 2–3 charts fit on
  a 1440 × 900 screen until it is folded or dragged smaller. A tab with no chart has nothing to measure, so the ruler
  falls back to an estimate. It is also the biggest splice so far: a new ~1000-line module.

## Keep-parts for a splice

1. **Shared x geometry**: fixed `axes[1].size` + explicit `padding` + the title column (about 10 lines of plots.js and
   15 of CSS). Any one-line overlay or aligned ruler needs only this.
2. **Run tracks with error bands and moments** (worst / rises / limits, error at t). They work as a run list in any
   variant, e.g. R3's run list could carry the bands.
3. **The one line + the zoom bar** (`timeline.js` paint / setView): a measured-geometry playhead that never drifts from
   uPlot's own `valToPos`.

## Simulated / not built

Nothing is simulated: both fixtures are real data. Not built or not exercised:
- **Limit-violation markers.** The code path is there, but neither fixture has a verdict.
- **Dark theme.** Only a minimal pass.
- **The stage's own per-run 3D rows** are unchanged. They are a second list of the runs, but 3D-only.
- **Narrow layout.** Checked once at 820 px, not polished.
- **No "solo a run on hover".**

## Change size

| file | vs production (`diff -u … \| grep -c '^[-+]'`) | vs R1 |
|---|---|---|
| plots.js | 151 | 100 |
| style.css | 224 | 228 |
| viewer3d.js | 20 (R1's `debug()`, unchanged) | 0 |
| timeline.js | new, 1086 lines | new |
| index.html | +timeline.js, a 6-line footer move | |

Proof: `node check.cjs r2 --video` → `"ok": true`. Extra stills: `node r2/extra.cjs` (listed in `media.json`).
