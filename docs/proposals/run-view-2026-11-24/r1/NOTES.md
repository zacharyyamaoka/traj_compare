# R1 · Every figure is a scrubber

**Thesis.** Keep today's run report exactly as it is and change one gesture: a plain press-and-drag on ANY chart commits
the time, live, so every other chart, the 3D pose and the stage slider follow while the pointer moves.

## What it is

- Every chart gets a **playhead**: the committed time (the end when none), a 2 px line in the page's ink with a grip on
  top (`[data-rv-playhead]`). uPlot's own dashed cursor stays what it was: the hover preview.
- **Press + drag on a chart = commit the time at every move**, snapped to the shared plot grid; the transport does the
  rest (it already drove the 3D, the videos and the slider).
- **x zoom moves off the plain drag**: Shift-drag draws uPlot's own zoom box (untouched), the wheel zooms around the
  pointer, double-click / Reset zoom = full range.
- `?keep=` seeds the situation chips (a bench line index matches `L<index>`); a chip click writes `keep=` back, so the
  back link and Open the same in Rerun carry the selection. `?t=` opens at a time.
- A fix found on the way (production has it too): a chart built when its tab first shows joined uPlot's cursor sync at
  the last sample, and that "hover" parked the 3D at the end after every tab switch. A hover now needs a pointer on a chart.

## Decisions

1. **The drag commits, the hover previews** — two different marks (solid line vs dashed cursor) so the reader always
   knows which instant the 3D shows.
2. **Zoom keeps three ways in** (Shift-drag, wheel, double-click/Reset) instead of a mode switch.
3. **Nothing else moves**: the stage, the chips, the tabs, the grid are today's.

## Best when / loses when

- **Best when** the comparison is 2–5 runs (TTA's three situations): it is today's page, so there is nothing to relearn,
  and the splice is ~130 lines.
- **Loses when** the selection is large: at 17 runs (9 shown) the situation and Δ chips take ~400 px, the first chart
  starts below the fold (the check scrolled 745 px to reach it), the 3D overlays 10 arms, and nothing summarises repeats.
  The drag gesture itself is invisible until you try it (the cursor turns ew-resize; the tooltip says so).

## Keep-parts for a splice

1. `attachTimeGestures` + `paintPlayheads` (the gesture, the playhead, the wheel zoom): every other variant started from it.
2. `keep=` / `t=` in the URL (`keepList`, `writeKeep`): the selection the target view hands over.
3. The hover fix (`page.hoverChart`): worth landing on its own.

## Simulated / not built

Nothing simulated: both fixtures are real; Open the same in Rerun writes a real recording (the checks run it dry). Not
built: a visible hint for the drag beyond the cursor and tooltip.

## Change size (vs `src/traj_compare/assets` @ 38b5967, `diff -u | grep -c '^[-+][^-+]'`)

plots.js 126 · viewer3d.js 18 (the `debug()` readback only) · style.css 11.
