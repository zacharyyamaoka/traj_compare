# R4 · Rerun parity

**Thesis.** The HTML playback viewer is laid out AS the Rerun blueprint traj_compare already writes for the same runs
(`rerun_export._layout_questions`). It takes Rerun's own panels and gestures, so switching between the two needs no
re-orientation, and **Open the same in Rerun** is the page's primary action. The one deliberate difference from Rerun:
a plain drag on any chart moves the time everywhere.

Zach, 2026-11-19: "designing a different run viewer for standalone and rerun is a bit silly ... they should be the
exact same thing". 2026-11-24: the playback viewer is "either our custom one or the rerun one".

## Ground truth it mirrors (read, not guessed)

`r4/rerun-real.cjs` drives the real Rerun 0.40 web viewer headless (its own `rerun --serve-web`, stopped at the end). It
shows the recording serve.py writes for the same runs, tab and time, at 1440 × 900. The captures are in
`shots/r4/rerun-real-tta*.png`.

- **Layout.** The stage column (the 3D view, titled "3D: every run's robot and tool point path") sits beside the
  questions Tabs at column shares 2 : 5. The tab bar shows each tab's container icon and its exact title, the open tab
  in ink and the rest muted. Every view has a title bar with an icon, the title, and **? · eye · maximize**. Views are
  separated by hairlines. The time panel is docked at the bottom.
- **Time series help, quoted from its "?" popup** (`rerun-real-tta-help-timeseries.png`):
  Pan: left-drag · Horizontal pan: Shift + scroll · Zoom: Ctrl + scroll · Zoom X-axis: Ctrl + Shift + scroll ·
  Zoom Y-axis: Ctrl + Alt + scroll · Zoom to selection: right-drag · Move time cursor: right-click ·
  Reset view: double-click · Hide/show series: click the legend · Hide/show other series: Alt + click the legend.
- **Timeline help, quoted** (`rerun-real-tta-help-timepanel.png`): Select time segment: drag the time scale · Snap to
  grid: Shift · Pan: middle-click drag · Pan vertically: Scroll · Pan horizontally: Shift + Scroll · Zoom: Ctrl + Scroll ·
  Zoom: right-click drag · Reset view: double-click · Play/Pause: Space.
- **3D view help, quoted** (`rerun-real-tta-help-3d.png`): Pan: drag · Zoom: scroll · Rotate: drag · Roll: Alt + click ·
  Navigate: WASD / QE · Slow down / speed up: Alt / Shift · Focus: double-click an object · Track: Alt + double-click
  an object · Reset view: double-click the background. The popup shows which mouse button each drag uses as an icon;
  only the word "drag" is in its text.
- **Measured in the real viewer** (time read back through `window._handle`):
  - a right-click in a plot moved the time 3.510 → 1.094 s;
  - a drag that starts on the time cursor moved it 1.094 → 2.300 s;
  - a plain left-drag elsewhere panned and left the time at 3.510 s;
  - a drag on the time scale selected a segment (blue band, Start / Stop / Length) and turned the loop button on;
  - a click in the streams area moved the time to 0.905 s.
- **What "Open the same in Rerun" opens** (serve.py): the shown runs, the open tab, paused, with the time panel
  expanded and a 0.2 s time selection around t. Rerun 0.40's blueprint has no cursor position, so the time travels as
  that selection; the real capture shows the blue band at 3.41–3.61 s.

## What it is

- **Top bar:** ‹ Target view · PLAYBACK VIEWER and the target's name · "9 of 17 runs shown". Under that count is what
  the button will open: "Rerun opens them on “Did it track the target?” at t = 2.00 s". After a press, the button's
  answer replaces that line until what it would send changes. Then the **Open the same in Rerun** primary button
  (blue, the page's one filled control). Then Rerun's panel toggles: blueprint panel and time panel.
- **Blueprint panel (left), Rerun's.**
  - **SOURCES:** `traj_compare` › the recording (selected pill), and the comparison's description.
  - **RUNS:** `world/` with each run as its entity `world/<run>/`, its colour, its own words, and **an eye that IS
    the run selection**: shown or hidden in the 3D and every chart at once, written to `keep=` and the back link
    (`[data-rv-run="<name>"]`). In Rerun the same would be a `- /**/<run>` line in each view's filter. bam_fb's 17
    lines are grouped by config. Each group has an eye for all its runs, a shown/total count, and folds; long config
    names wrap to two lines. Alt+click a run or a group shows it alone, Rerun's "hide/show other series"; Alt+click again
    brings back the runs shown before.
  - **BLUEPRINT:** the questions layout's own tree: Viewport (Horizontal container, 2 : 5) › Vertical container › the
    3D view; Tab container › the tabs. Clicking a tab row opens it.
  - **VIEW OPTIONS** (folded, "this viewer only"): the Δ-to-target curves, deg / rad and Reset zoom. Rerun's blueprint
    has none of these.
  - The panel's width drags and is remembered; double-click restores the default. It hides from the top bar.
- **Stage:** the 3D as Rerun's spatial view. It fills its column, under the title bar "3D: every run's robot and
  <tool frame> path" with ? (help) · eye (fold the stage) · maximize. The per-run visualizers, marker sliders and Fit
  view fold into "Visualizers and view options" under the canvas; Rerun keeps these in its selection panel. The
  stage/tabs boundary drags and is remembered. Its default is the blueprint's 2 : 5 (`plots.js` RV).
- **Question tabs:** the exact titles (`traj_compare.tabs.TABS`) in Rerun's tab bar, with the tab's heading as one
  quiet line under it.
  - **Track tab:** the answer and the statistics table are one text view, "Scorecard: every run against the Target,
    worst run first", as in Rerun. Its bottom edge drags and is remembered (Rerun's row share), and by default it is
    capped at 42 % of the screen so that, at 17 runs, the first chart is still on the first screen.
  - **Joints and torque tabs:** the ranking bars are one view.
  - **Several plot sections in one tab** (Raw signals, Where): they are Rerun's nested tabs, one section at a time; the
    pick is remembered.
  - **Charts:** every chart is a view with its own title bar (signal, joint, sign convention, unit; ellipsized, whole
    in `title`), one per row at full width. The view's eye folds it (remembered); maximize fills the tabs column (Esc
    restores it).
- **Time panel (bottom), Rerun's.**
  - **Controls:** play/pause (Space), step back and forward one sample (← →), loop (off → time selection → whole run),
    the timeline `t`, playback speed 0.25x–4x, and the current time field (`+3.510s`; type a time and press Enter).
  - **Streams:** one row per run entity (`world/<run>/`), with its time span in the run's colour (grey when hidden),
    and a line naming the recording's other entities.
  - **Time scale:** with Rerun's **time cursor**, a line with a triangle on top. Drag the cursor, or click or drag the
    streams, to move the time. Drag the time scale to select a segment; this turns the loop on, as in Rerun. Hover the
    segment to read Start / Stop / Length. Double-click or Esc removes it.
  - **Resizing and folding:** the panel's top edge and the streams column drag and are remembered. Collapsed, the
    panel is Rerun's one-row scrubber.
- **Every chart's time:** shown as Rerun's time cursor (`[data-rv-playhead]`), a 1.5 px dark line with a triangle on
  the plot's top edge. Hovering shows Rerun's tooltip: the time, then each shown run's colour, name and value. While
  dragging, the pointer is the time cursor, so it reads every run at the playhead.
- **Every "?"** opens that view's help: this page's gesture beside Rerun 0.40's, with the rows that differ marked.

## Gestures (time series)

| Action | This page | Rerun 0.40 |
|---|---|---|
| Move time cursor | **drag anywhere** · right-click | right-click · drag the cursor itself |
| Pan | **middle-drag · Shift + scroll** | left-drag |
| Horizontal pan | Shift + scroll | same |
| Zoom | Ctrl + scroll | same |
| Zoom X-axis | Ctrl + Shift + scroll | same |
| Zoom Y-axis | **not built** (y always fits the runs shown) | Ctrl + Alt + scroll |
| Zoom to selection | right-drag · **Ctrl + drag** | right-drag |
| Reset view | double-click (the time stays where it was) | same |
| Hide/show series · other series | **the eye in Runs (every view) · Alt + click a run** | click the legend · Alt + click the legend |

`gestures.json`:

- **scrub:** a plain drag. It moves time, the round's core, and it is the one deliberate deviation from Rerun.
- **zoom:** `drag` with `Control`, the one-button stand-in for Rerun's right-drag "Zoom to selection" (macOS reads
  Ctrl-click as a right click). check.cjs can only press the left button, so it cannot express a right-drag. A real
  right-drag works too, and `extra-time-panel.png` shows it held mid-gesture.
- **reset:** double-click.
- **toggle:** `[data-rv-run]`, the eye.
- **tab:** `[data-tc-tab]`.

## Consequential decisions

1. **Rerun's gestures, except the plain drag.**
   - Kept as Rerun has them: right-click, right-drag, Ctrl + scroll, Shift + scroll and double-click.
   - A plain drag moves the time, because dragging time on any figure is the core of the viewer.
   - Pan moves to the middle button, which Rerun's own time panel uses to pan.
   - Double-click restores the time held before its two presses, so it only resets the view, as in Rerun.
2. **The run selection is the blueprint panel's entity tree.** Rerun's eyes act on one view; these act on every view,
   and the RUNS header says so ("eye = shown in every view"). The chips row is gone (hidden; the eyes click it), so the
   tabs start right under the tab bar.
3. **Rerun's light theme, in traj_compare's palette and type** (style.css: `#fcfcfb` views, `#dddcd6` hairlines,
   `#2a78d6` accent, system sans). This was my call: the real Rerun captures in this repo are the light theme, and the
   check is light. The plot data keeps traj_compare's run colours. Basic dark tokens exist; dark polish is not built.
4. **The frame is one new file over today's page.** `rerun-frame.js` and `.css` decorate what `plots.js` builds,
   through two small hooks (`TrajCompare.onChart`, `onPanel`).
   - `plots.js` changes only by:
     - the gestures;
     - the transport's speed, loop and selection, and a guard so playback never runs time backwards: the first frame's
       timestamp can come before play();
     - Rerun's `+1s` axis labels;
     - the 2 : 5 default width;
     - the 3D height callback;
     - the hooks.
   - The section sizes, the tables and the chart builders are untouched.

## Best when

- The reader uses Rerun as well, or will: same tab names, same 2 : 5 layout, same title bars, same time panel, same
  right-click / right-drag / Ctrl + scroll / double-click. Open the same in Rerun lands on the same picture
  (`extra-beside-rerun.png`).
- Many runs, toggled from one tree: entity names, configs that fold, Alt+click to show one alone.
- Watching one moment repeatedly: select a segment on the time scale and loop it at 0.25x.

## Loses when

- A first-time reader expects a plain drag to pan (Rerun habit) or to zoom (R1 / uPlot habit). The "?" says what it
  does, but there is no on-chart affordance beyond the ew-resize cursor and the hint in the time panel.
- Six tabs do not fit on one line beside the stage with the blueprint panel open: the tab bar wraps to a second line
  rather than hiding tabs behind an arrow. Rerun hides them, which is the reason rerun_export uses 2 : 5.
- Values at the playhead appear only on hover or while dragging (Rerun's tooltip), not permanently (R5's readout
  table does that).
- The frame adds about 1 050 lines of JavaScript and 290 of CSS, more than any other lane's chrome.

## Keep-parts (for a splice)

1. **The blueprint panel's RUNS tree:** entity names, config groups with shown/total counts, one-click eyes,
   Alt+click to show a run alone (`rerun-frame.js` buildBlueprint / runRow / solo). It works over any variant's chips.
2. **Rerun's chart gestures as a second gesture set:** right-click moves the time, right-drag or Ctrl+drag zooms to a
   selection, Ctrl + scroll zooms, Shift + scroll pans, middle-drag pans, and double-click resets without moving the
   time (`plots.js` attachTimeGestures). Each one fits beside R1's plain-drag scrub.
3. **The "?" help that puts this page's gestures beside Rerun's** (`HELP` in rerun-frame.js), and **Open the same in
   Rerun as the primary action, with the line of what it will open**.

## Simulated / not built

- **Not built:** Rerun's in-plot legend (the RUNS eyes and the hover tooltip do its job); Zoom Y-axis; the time panel's
  own pan and zoom (it always shows the whole run); the right-hand selection panel; the Events text-log view of
  Rerun's track tab; Roll, WASD, focus and track in the 3D; dark-theme polish.
- **Simulated:** the BLUEPRINT tree is drawn from the layout's known shape (`_layout_questions`), not read from the
  `.rbl`. The streams list shows `world/<run>/` and one summary line for the recording's other entities. The group rows
  are the bench's configs: the recording's paths are flat `/world/<run>`.
- The answer and statistics table do not follow the selection (production); the HTML's where, timing and joints tabs
  hold more views than Rerun's.

## Change size

`diff -u src/traj_compare/assets/<f> r4/<f> | grep -c '^[-+]'`:

| File | Lines |
|---|---|
| plots.js | 279 (R1's was 133; the gestures and hooks replace R1's block) |
| style.css | 19 |
| viewer3d.js | 20 (R1's readback, unchanged) |

New files:

| File | Lines | What it is |
|---|---|---|
| rerun-frame.js | 1 055 | the frame |
| rerun-frame.css | 294 | the frame's styles |
| rerun-real.cjs | 83 | the real-Rerun capture tool |
| extra.cjs | 117 | the extra stills |

## Proof

`node check.cjs r4 --video` → `ok: true` on both fixtures (numbers in the report and `shots/r4/check.json`). Extra
stills: `node r4/extra.cjs`, which also runs `rerun-real.cjs` when its captures are missing.
