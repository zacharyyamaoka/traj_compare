# R5 · Moments first

**Thesis.** The page's first question is "when was it worst?", so the viewer is organised around moments. It opens at
the worst moment and lists the moments worth seeing beside the 3D. At the playhead it shows every shown run at once, in
the 3D (one arm per run) and as numbers (a readout under every chart), so the reader never has to hover to read a value.

Built on R1 (the plain drag on any chart commits the time, live, everywhere). Open it:
`http://127.0.0.1:8853/r5/index.html?fixture=bam_fb&keep=3460,3461,3463,3465,3466,3467,3471,3474,3476`
(or `fixture=tta&keep=p5s-pass3,p6s`).

## Consequential decisions

1. **Moments are data the page computes, and every time control uses them.** For each shown run the page takes its
   worst |joint error| (time, joint, signed value in °) and the first sample where its largest joint error reaches half
   its own peak ("error rises"). It adds its limit violations when the run carries a verdict; neither fixture has one,
   so the list says "Limits: none were checked". It also adds the motion's end: the target's last moving sample. The
   moments sit in a list in the stage under the 3D (click a row to jump there, `[` and `]` step, the current one is
   highlighted, a "▸ playhead" line falls between rows) and as coloured ticks on every chart's top edge. The drag snaps
   to a moment within 6 px: the playhead turns blue and names the moment. Alt drags freely, and a "Snap to moments"
   switch turns snapping off (remembered). With no `?t=`, the page opens at the shown runs' worst moment (tta: 3.51 s,
   p6s on wrist_1; bam_fb: 1.71 s, record · r0 · sim on j1).
2. **Readouts replace hovering, and they are also how you pick runs.** Under every chart is a table at the playhead:
   one row per shown run with its colour, name, value and Δ = target − run (in the chart's unit, degrees for angles),
   sorted by |Δ|. Error-only charts sort by |value|. A narrow small-multiple card shows a single number per row with the
   name cut in the middle (its full name in `title`). Torque cards list their components instead. A row's box hides or
   shows the run on every chart, in the 3D and in `keep=`. A run hidden from a row keeps its unticked row there, so the
   same box brings it back. The 17-chip situation block is gone: it is replaced by one "Runs · 9 of 17 shown ▾" picker
   (grouped by config, with all/none per group) and one "Δ curves on the plots" switch. WHY: at 17 runs the chips took
   the first screen. Now the first chart starts at y ≈ 355 px on bam_fb.
3. **One instant on the page, the committed one.** A hover no longer moves the 3D. uPlot's dashed cursor still shows
   where a press would land, but the 3D, the readouts, the moments row and every playhead always show the same time.
   Every shown run's arm stands at that time: the focus run is opaque, the others are ghosts in their run colours
   (their opacity falls with how many there are, and they are pushed back in depth so they show only where they leave
   the focus arm), and the target is a grey ghost. The focus run is the worst shown run until you click another one in
   a readout or the moments list. It is also drawn thicker on every chart and set in bold in the readouts. A one-line key
   under the canvas names each arm (it sat in a corner at first and covered the arm's upper links). On tta the focus run (p6s) has no arm in its data, and the key says so rather than
   borrowing p5s-pass3's.
4. **The track tab puts "when" first.** The order is: the answer (now about the shown runs only), the two over-time
   charts with their readouts, then the statistics table. The 3D's per-run drawing rows and sliders fold into one
   remembered disclosure, which gives the stage's room to the moments list.

## Best when

- You are reviewing what went wrong: you want the peaks, in order, one keypress apart, with every run's number at
  each one.
- You have 5 to 20 runs that need comparing at the same instant, such as the bench's 9 lines at record · r0's
  4.38° spike.
- You want to read values, not trace lines: the readouts give exact numbers with their units and sign convention.

## Loses when

- The charts are dense small multiples (timing tab: 6 cards a row × 3 rows). Nine readout rows under each one makes a
  wall of numbers, and the names shrink to "reco…im" (full name on hover). A shared readout per row of cards would
  read better.
- You want to skim the shape over time. Readouts and ticks add vertical weight; the per-joint tabs grow by about
  60-190 px per chart.
- At 40 runs, 40-row readouts under every chart are too long; this would need a top-N with "+N more".
- The arms agree. At bench errors of 1-4°, the ghosts mostly coincide and read as one shadow, so the 3D tells you
  "focus is off the crowd" but not which ghost is which (the readouts do).

## Keep-parts for a splice

1. **The readout under a chart** (`attachReadout` / `readoutModel` / `fitMiddle`, ~200 lines): it works on any
   `makeChart` card and needs no contract change.
2. **Moments + snap** (`computeMoments`, `SNAP_PX` in `attachTimeGestures`, the ticks, `[` / `]`): a small,
   self-contained addition to R1's gesture.
3. **Ghost arms with a focus** (viewer3d.js `paintArms` + the key + `setFocus`): about 125 lines on today's robot
   meshes.

## Simulated / not built

- Limit-violation moments are coded from `sit.verdict` (the same violations the verdict table lists) but are untested,
  because neither fixture carries a verdict. The panel says so.
- No click-to-focus on an arm in the 3D (no raycasting): you pick the focus from a readout or a moment.
- The moments list's width is the stage's width (the stage edge drags and is remembered). Its height drags and is
  remembered separately.
- Dark mode: R5's own surfaces have a minimal dark block (not polished, per the round's stop line). No mobile work
  beyond not breaking.

## Gestures (gestures.json)

The scrub is R1's plain drag, with `"snaps": true`. Zoom is the wheel (4 ticks at the chart's centre). Reset is the
"Reset zoom" button (`[data-rv5-reset-zoom]`); double-click still works too. The toggle is the first
`[data-rv-run="{name}"]`, the checkbox of that run's row in the first chart's readout. The tab is `[data-tc-tab="{id}"]`.

## Change size (lines `+`/`-` in `diff -u`)

| file | vs production @ 38b5967 | vs R1 |
|---|---|---|
| plots.js | 921 | 810 |
| viewer3d.js | 143 | 125 |
| style.css | 156 | 144 |

The plots.js number is large but mostly one contained block: moments, readouts and the moments panel (~520 lines),
the run picker (~120) and the snap/ticks in R1's gesture (~70). Only about 50 lines of R1/production are removed: the
situation-chip and Δ-chip loops, which are replaced. Every change is marked `RV:` / `RV (R5)` with its WHY.

## Files

`index.html`, `plots.js`, `viewer3d.js`, `style.css` (copies, changes marked), `gestures.json`, `extra.cjs` (the three
extra stills, captured headless from the real page by the reader's own gestures), `media.json`, this file.
