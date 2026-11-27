# Run-report layout round, 2026-11-27 (frozen before any variant was built)

Zach, 2026-11-27: *"I also don't really like our custom viewer right now. I like the general lay out of 3d view on the
left, then tabs on the right. But generally there is a lot to be desired. Please make 5 different prospaosl for complete
redesign within that general structure. I think the content is good, but like think about layout."*

## Outcome every variant serves

Open one scenario's run report and, without hunting, see whether the run tracked, where and when it went worst, which
joint and which diagnostic channel explain it, while the 3D tool paths and every chart share one time.

## Invariants (every variant)

- 3D view on the left, the question tabs on the right, all six tabs: *Did it track the target?* · *Where is the
  error?* · *Which joint has the error?* · *Is it late or off the path?* · *Raw signals per joint* · *Diagnostics*.
- Same content as today: 3D tool paths per run (trail decay, look-ahead, error arrows), the error-statistics table,
  per-joint charts, tool error / pose, lag and cross-track, raw q / qd / qdd / torque, all 27 Diagnostics channels,
  one shared time (transport, play, scrub on any chart, per-run tracks), situation eye toggles, deg (default) / rad,
  Worst moment, Open in Rerun.
- Every panel boundary draggable and its size remembered; the inspector / 3D settings foldable.
- Plain-word labels; angles in degrees by default; SI stays in the data.

## Shared fixture

The real payload embedded in `/home/bam/jtc_diagnostics_agent/site/playback/report.html` (traj_compare build of the
JTC diagnostics playback), page **X1.ElbowStop@-60**: 4 situations (Target, Command, Measured, MuJoCo truth), 2 joints
(shoulder, elbow), 420 plot samples over 0–4.19 s, 27 channels (24 controller + 3 plant truth). `extract.py` copies it
to `data/fixture.js` unchanged except for rounding to 6 significant digits and resampling the truth run's 3D path
(4 200 samples) onto the 420-sample plot clock. No number is typed by hand.

## Prototype stop line

Real: the layout, every panel and splitter, time play / scrub / step across 3D and charts, run toggles, deg/rad,
Worst moment, channel choosing, uPlot charts and a three.js 3D of the real tool paths, all from the fixture.
Simulated: Open in Rerun shows the command the report would run and does not start Rerun; no robot mesh (the payload
has none — today's report also draws tool paths only); the other four scenario pages and Summary are not wired.

## Stack

traj_compare's own: vanilla JS, uPlot 1.6.30 and three.js r160 copied from `src/traj_compare/assets` (vendored, no CDN),
its colour tokens. One shared kit (`common/`) holds data, time, charts and the 3D; each `vN/` owns only its layout.

## Load-bearing axes

1. Where the time lane lives (page footer · editor dock · under the 3D · sticky ruler over the charts · on the 3D).
2. How 24+ channels are chosen (changed-first accordion · event swimlanes · searchable inspector list · sparkline
   matrix · command palette with pins).
3. Where runs are toggled and what is always visible vs on demand (answer bar · track headers · inspector · global
   header · keys + HUD).
4. How the 3D panel's many sliders fold (popover · edge toolbar · inspector section · presets + fine-tune · hover HUD).
