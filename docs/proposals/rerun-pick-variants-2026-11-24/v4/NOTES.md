# V4 · By joint + events

**Thesis.** The run is indexed by its events (start, each via point, peak tool speed, the moment closest to a limit, the worst tracking error, end). Each event is a numbered dot on the tool path, and while the playhead passes it the arm itself lights up in that event's colour. The Events tab leads the right half, and every other tab is organised by joint, not by derivative.

Zach's frame is kept: the URDF arm on the left half, always, and tabs on the right half.

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v4/make.py
```

`save(path, traj, *, robot, tool=None, target=None, target_tool=None, extras=None)` writes `plan-dev-029.rrd` (`fixture.plan()`) and `run-dev-029.rrd` (`fixture.run("p6s")`: the solution drawn, the target overlaid).

- **Blueprint:** embedded at `stream.save(…, default_blueprint=…)`, opens paused at 0 s.
- **Identity:** `application_id` is `rerun_pick_v4`.
- **Units:** degrees on screen.
- **robot_msgs:** imported, never edited. The build picks up main's strip-range fix (3023fce): wrist_2 qd now reads −200…200, labelled every 100.

## Fixed after the check

The independent check filmed the first build and found six defects; a second look at the next build found the seventh. Each one, and the frame that shows the fix:

1. **Fog and overprinting labels.** Seven ghosts sat on screen at alpha 40, and "2 past limit" / "4 worst error" / "1 start" overprinted (in the plan, "2 near limit" sat on "3 via").
   - **Fix:** no always-on ghosts. Between events, each event is a small coloured dot on the tool path with its number. (This build first drew a lit ghost around each event; 7 replaced it with the lit arm.)
   - **Labels:** the lit event's label reads "n kind". Every label is placed in screen space for the blueprint's camera: its lit form overlaps no other label and no event dot, and covers as little as it can of the tool path and of the arm as it stands at that event. When it has to move away from its dot, a leader line links them.
   - **Via:** green instead of slate, so a lit via visibly tints the steel arm.
   - **Frames:**
     - `shots/v4/hero/f-14-t1.4.png`: the arm lit magenta at 4; "4 worst error" is clear of "1", "2" and "3".
     - `shots/v4/hero/f-4-t0.4.png`: the arm lit red at 2, with "2 past limit" to the left.
     - `shots/v4/hero/f-18-t1.8.png`: via 2 lights the arm green.
     - `shots/v4/plan-0-t1.8.png`: "2" and "3" apart.
2. **The end ghost was not lit at the end.** The last window closed at end + 1 ms, which stretched the timeline to 3.201 s.
   - **Fix:** a window that reaches the last sample never closes (`_lit_steps`). The end event's vertical line is drawn at [t − 1 ns, t] instead of [t, t + 1 ns]. Nothing is logged past 3.200 s.
   - **Frame:** `shots/v4/hero/f-32-t3.2.png`. The readout shows +3.200 s, the arm is lit orange, ▶ is on 7 and the END row is current. film.cjs read back 3.200 s for `end`.
3. **Row 7 clipped; TCP orientation title cut off.**
   - **Fix, Events tab:** the row shares are computed from the content (`_events_shares`): lanes, 20 px per log row, 23 px per table row plus its notes, measured from the panel separators in both scenarios. The lanes lost their 28 px title bar (their rows name themselves), and the two short strips got 10 % headroom so the "2000" tick isn't cut.
   - **Fix, TCP:** the orientation title is rebuilt as "TCP orientation [°] · roll / pitch / yaw = red / green / blue · ROS rpy, unwrapped · near gimbal lock 1.05–1.12 s". The frame is named one strip up, in the position title.
   - **Frames:** `shots/v4/tab-events-0-t1.8.png` (7 log rows, 7 table rows and both notes, all inside the panels), `shots/v4/hero/f-32-t3.2.png` (the same at the end, START row still showing), `shots/v4/tab-tcp-0-t1.8.png` (the full title).
4. **"PAST LIMIT · wrist_2 qdd 144.9 %" read like the plan's number.**
   - **Log row:** "2 · 0.40 s · wrist_2 qdd 144.9 % of limit — +498°/s² of ±344°/s² · MEASURED: differences of encoder q".
   - **Table note:** its own paragraph (notes are separated by blank lines, so the caveat no longer runs on after "… qdd wrist_2 145 % at 0.40 s"). It reads: "**2 past limit** is the solution's MEASURED qdd: second differences of its encoder q, drawn as given (144.9 %). Smoothed first (Savitzky–Golay, 70–110 ms) it is still 133–141 %: a real overshoot of the controller (p6s: best of generation 0), not only noise."
   - **How the note is produced:** "MEASURED" is printed only when the message's qd/qdd equals `np.gradient` of its q (`_differenced`). The 133–141 % is computed: a polyorder-2 Savitzky–Golay filter over 70, 90 and 110 ms gives 140.7, 137.0 and 132.6 % (`_smoothed_percent`). The plotted data is unchanged.
   - **Frame:** `shots/v4/tab-events-0-t1.8.png`.
5. **The stills predated the shipped file.** Every frame in `shots/v4/` was re-filmed from the 00:04 build (and again from the 01:12 build, after 7), one film.cjs at a time: the hero first, then the 11 tab stills, then the plan. wrist_1's first take missed its tab click while the page was still loading, so it was re-filmed with `--wait 16000` (the 01:12 takes all used `--wait 30000`, and every click landed first time).
6. **NOTES said teal was lit 2.2–2.4 s.** The window is [2.16, 2.40), so the frames show teal at 2.2 and 2.3 and grey at 2.4. The list below now matches the frames: `shots/v4/hero/f-22-t2.2.png`, `f-23-t2.3.png`, `f-24-t2.4.png`.
7. **A lit ghost z-fought with the live arm.** Near its event the lit ghost stood where the arm was, and its base link, which never moves, always did. The two meshes fought for depth, so the arm showed the ghost's colour as speckles and stripes over the steel: magenta patches on the lower arm and base at 1.4 s (a walkthrough step of the pick page), orange speckles at 3.1 s, half blue and half grey at 0.1 s.
   - **Fix:** no ghost is drawn. While the playhead is within an event's window, the live arm itself takes that event's colour. Each of its seven link meshes has its albedo on the timeline: steel, or the kind's colour at alpha 150 over the steel, mixed in linear light and opaque (`_lit_colour`). That is the colour the lit ghost gave the arm when the two lined up exactly.
   - **robot_msgs untouched:** robot_msgs logs the arm's steel tint as static, and static data always wins over temporal data. So `_log_robot` runs through a filter, `_WithoutArmTint`, which drops exactly those seven static logs. The build raises an error if robot_msgs ever logs them elsewhere.
   - **Unchanged:** the windows, the labels, the lit dot, the lanes and the right half. No ghost copies are written any more (`_GHOST_ALPHA = 0`), so each file is about 1.9–2.2 MB smaller.
   - **Frames** (all 33 of the hero re-filmed, then every still): `shots/v4/hero/f-1-t0.1.png` (all blue), `f-14-t1.4.png` (all magenta, "4 worst error" in place), `f-31-t3.1.png` (all orange, "7 end" in place). `f-0`, `f-4`, `f-18` and `f-32` sit on events 1, 2, 5 and 7. Each was looked at zoomed 2× (ffmpeg crop, nearest neighbour): no speckle, no stripe, and each event's tint reads.
   - **Measured against the old frames** (3D view, below its title bar):
     - The 16 frames between windows are pixel-identical, so the steel is unchanged.
     - The 4 frames exactly on an event differ in at most 5 px, so the tint is the old lit colour.
     - Only the 13 lit frames off an event changed. On those, the low-saturation steel pixels fell from 5 100–39 000 per frame to 10–980. What is left is the label boxes, the grey tool stick and the anti-aliased edge of the silhouette.
     - The right half is pixel-identical in all 33.

## What is on screen

| Where | What |
|---|---|
| Left half | robot_msgs' arm and tool path (`_log_robot`). Each event has a small dot at its tool point, tinted by kind: start blue, via green, peak speed teal, near limit violet (red if past a limit), worst error magenta, end orange. Unlit, the label is its number. While the playhead is within ±0.12 s of an event (windows cut halfway to the neighbours), the arm itself takes that event's colour as a solid tint, the dot grows and the label reads "n kind". Between windows the arm is steel. There is only ever one arm on screen. robot_msgs' own start/end ghosts and path-end dots are off, because they are events 1 and n here. |
| **Events** tab (opens first) | (1) Two lanes on Rerun's state timeline, on the plots' time axis: each event a numbered pulse, and the moves between via points (`move 1 · 0.00–1.15 s` … `at rest · 2.70–3.20 s`). (2) The event log, a `TextLog` per event: the level column is the kind, the body is `n · t · what — detail`. The current row is highlighted, and **clicking a row's time cell moves the playhead there**. (3) "The arm at each event": every event's q per joint in degrees plus tool speed, ▶ on the latest event, then its notes as separate paragraphs (worst % of limit per quantity; on the run, the measured-qdd caveat). (4) Tool speed, plus tool error on the run, with every event as a vertical line. |
| `shoulder_pan` … `wrist_3` (one tab per joint) | The numbered events lane on top, then that joint's q, qd, qdd and qddd stacked: robot_msgs' own strips, with titles cut to `q [°] · travel 130° · 38° to limit`, and so on. They share one time axis and draw limit lines and event lines. On the run, the target is drawn pale and wide **under** the run's ink line, and a fifth strip shows `q error, run − target [°]`. |
| **All joints** | A nested tab row: `q / qd / qdd` · `q` · `qd` · `qdd` · `qddd`. The first is robot_msgs' cards plus the playhead table. The rest are robot_msgs' per-derivative tabs (one strip per joint), all with event lines. **This is how his per-derivative views stay reachable: All joints › q is the stock q tab** (and the same for qd, qdd, qddd). |
| **TCP** | robot_msgs' four TCP strips (position, orientation, speed, angular speed) with event lines, plus tool error on the run. |

The events found (printed by `make.py`):

- **Plan (6):**
  - 1 start 0.00 s
  - 2 near limit 0.90 s: wrist_2 qd 99.3 % (+179°/s of ±180°/s)
  - 3 via 1.15 s
  - 4 via 1.80 s
  - 5 peak speed 2.28 s: 1507 mm/s
  - 6 end 3.20 s: at rest from 2.68 s
- **Run p6s (7):**
  - 1 start
  - 2 **past limit** 0.40 s: wrist_2 qdd 144.9 % (+498°/s² of ±344°/s²). This is the solution's **measured** acceleration: second differences of encoder q. Smoothed (Savitzky–Golay, 70–110 ms) it is still 133–141 %, so the gen-0 controller really overshoots; it is not only noise.
  - 3 via 1.15 s
  - 4 worst error 1.42 s: 2.11 mm on the agent's ruler, RMS 1.09 mm; wrist_2 +0.57° at that moment
  - 5 via 1.80 s
  - 6 peak speed 2.28 s
  - 7 end 3.20 s

The target never passes 99.3 % of a limit.

## Decisions (each reversible)

1. **The events are computed, not authored.**
   - A via point is a dip in the *target's* tool speed whose prominence is at least 15 % of peak (`scipy.signal.find_peaks`). The run's own noise cannot add via points, and the rest at either end does not count.
   - Peak tool speed and "closest to a limit" come from the trajectory drawn. The limit check uses robot_msgs' own % of limit (the cards' `_percent`, over q, qd and qdd against the message's JointLimits); the event is the worst of the three, and the table's note lists all three.
   - The worst error comes from `extras["tool_error_mm"]` (the agent's ruler). Without it, the tool distance to `target_tool` is used.
   - Events less than 0.06 s apart share one window (one tint on the arm, one label).
   - The measured-acceleration caveat is computed too: it appears only when the message's rate is exactly the difference of its q, and its smoothed % is recomputed from q.
2. **The arm itself is lit, no ghost is drawn, and the dots are the index.**
   - **How:** the live arm's seven link meshes carry their colour on the timeline: steel, or the lit event's kind colour at alpha 150 over the steel (mixed in linear light, opaque). robot_msgs logs the steel as static, and a static tint always wins, so `_log_robot` runs through `_WithoutArmTint`. It drops just those seven static logs, and the build raises if they move.
   - **What you see:** one arm, the numbered dots, and the arm's tint naming the event you are at.
   - **Why no ghost:** a ghost at an event's pose coincides with the arm near that event (its base always does) and z-fights (fixed item 7).
   - **Undo:** `_GHOST_ALPHA = 40` brings back the always-on faint ghosts, each hidden in its own window. Their fog and the base's z-fighting come back with them.
3. **Labels are placed, not just dropped at the point.** `_label_layout` projects the dots through the blueprint's camera into the 1600×1000 review layout (an 800×908 px 3D view at Rerun's 55° vertical field of view; the projection matched the first build's frames to 1 px). It then places each label greedily at the nearest free spot among up to 56 candidates (below, above, right, left, then further out). Collisions with other labels and dots are hard. Covering the tool path or the arm's silhouette at that event (its STL meshes through robot_msgs' FK, rasterised in 6 px cells) is soft, weighed against distance. The offset is lifted back to 3D at the dot's depth, so it scales when the view is resized (the labels' pixel size does not).
4. **Joint tabs reuse robot_msgs' strips.** They keep the stock y range, limit lines and title, with the joint name dropped. The target is drawn under the run: a plot draws its series in entity-path order, and `target` sorted after `p6s_…`, so the pale wide target hid the run. It is logged at `/<field>/<joint>/0_target` (legend still "target").
5. **Event lines use a span ladder.** Each line is a 2-sample series from −S to +S at the event time, where S is the power of ten at least 10× the strip's range. Every strip that carries them has a fixed y range, so the line is clipped to the strip.
   - One ±1e6 line for every strip was tried first: it drew dashed in the ±4 mm strip and **not at all** in the ±0.1° strip (f32 precision).
   - Aggregation is off, or zoomed out it averages to a dot at 0.
   - TCP position and orientation, which robot_msgs autoscales, get a fixed range that reaches a round number (`_decade_range`), so orientation reads 0 and −1000.

## Best when / loses when

- **Best when:**
  - the question is "what happened at the bad moment". Click "4 · 1.42 s" in the log, and the arm (lit magenta) and every strip land on it.
  - a problem lives in one joint: that joint's q, qd, qdd, qddd and error are on one screen, with the target under it.
  - a tour or pick has via points: the moves lane reads the motion's structure at a glance.
- **Loses when:**
  - there are many events. The dots stay light, but the lane pulses crowd and the label layout runs out of free spots near a dense cluster. A long run needs a cap, top-N, or windowing.
  - the motion is joint-space with little tool travel (1-DOF rigs, wrist spins). Tool-speed via points mean little there, and there may be none.
  - you compare joints with each other: that needs All joints, one click deeper than in V1.
  - the 3D view never shows the arm's pose at an event before the playhead gets there. The always-on ghosts did, at the price of fog; the lit ghost did for 0.12 s, at the price of z-fighting. The dots carry *where*, and the arm's tint carries *when*.
- **More clicks:** 9 tabs plus a nested row.
- **Layout-specific:** the label placement and the Events tab's row shares are measured for the 1600×1000 review layout. In a much smaller window labels can touch again and the table can scroll.
- **Size:** close to V1's (plan 2.12 MB vs 2.18, run 2.77 MB vs 2.25: the target series and the events). No ghost copies are written.

## Worth keeping in a splice

1. **The event detector and the clickable event log.** `_events` plus `TextLog` at each event time make the log a working time index. Measured on the final run file: a click on row 4's time cell moved the playhead to 1.420 s, a click on row 6's to 2.280 s, and a click on a row's body does nothing.
2. **Event lines in every strip, with the numbered lane on top.** These are `_Marks` (span ladder) and `StateTimelineView` (moments plus moves), and any variant's plots can take them.
3. **A temporally lit arm.** The live arm's `albedo_factor` on the timeline marks "you are at event k" in 3D with no second arm to fog or z-fight. robot_msgs' static tint is filtered out by `_WithoutArmTint`; any variant's arm can take it.
4. **Screen-space label placement for a fixed camera.** `_camera` + `_project` + `_label_layout` + `_arm_cells` keep any 3D labels off each other, the path and the robot.
5. **Nested `Tabs`.** They keep his full tab set one level down when a variant reorganises the top row.

## Proposed robot_msgs signature (additive)

```python
viz.rerun.save(path, traj, robot=urdf, tool=tcp, target=None, target_tool=None,
               events="auto", layout="by_derivative" | "by_joint", tool_error=None)    # -> path
viz.rerun.events(traj, robot=urdf, tool=tcp, target=None, target_tool=None,
                 tool_error=None) -> list[TrajectoryEvent]                            # pure: (t, index, kind, what, detail)
```

- **Defaults** (`events=None`, `layout="by_derivative"`) keep today's V1 view exactly.
- **`events=`** also takes a list of `TrajectoryEvent`, for authored events such as grasp or release.
- **`events()`** is pure and testable on its own (via points, peak speed, limit, worst error, the measured-rate check).
- **The arm's colour on the timeline** (an optional `arm_colour=(seconds, rgba)` on `_log_robot`) would let V4 drop its `_WithoutArmTint` filter. Today robot_msgs logs the steel as static.

## What Rerun 0.40 could not do (and what V4 does instead)

- **No vertical marker or annotation in a time-series plot.** Event lines are the ±S series above, so they need a fixed y range. robot_msgs' TCP position/orientation strips scale themselves, so V4 gives them a range and turns their legend off (the legend would list the event lines). The titles name the axis colours instead.
- **No labels on points in a plot.** The numbers come from the lane above the strips. The lane's plot area does not line up pixel-exactly with the strips, which have a y-axis gutter: same time scale, offset about 25–35 px.
- **No fixed y-axis gutter, so small multiples do not line up to the pixel.** The strips share one linked time axis, but each strip's left edge moves with its widest tick label ("0" vs "−10 000"). In a joint tab, one instant can sit up to about 40 px apart from strip to strip. Each strip's own playhead and event lines are the reference.
- **Tick labels only a power of ten apart on a short strip.** A ±400°/s² qdd strip reads only "0" (V1's stock strips behave the same), and the ~100 px Events-tab tool-error strip reads only "0". The grey limit lines and the titles carry the scale there.
- **No label offset, priority or collision handling in 3D.** A label hangs centred under its point, wherever that is. V4 therefore computes the placement itself for one camera and one layout (decision 3) and draws a leader line when a label moved. Orbit the camera and the placement no longer holds.
- **No depth bias or draw priority between coincident meshes.** Two arms at (nearly) the same pose z-fight, whatever their alpha, and a base link that never moves always coincides. So an event lights the live arm instead of drawing a second one (fixed item 7).
- **A static component always wins over a temporal one, and robot_msgs logs the arm's tint as static.** V4 filters those seven logs out of `_log_robot` (`_WithoutArmTint`) instead of copying `_log_robot`.
- **Text-log rows are one line, and the time column sized itself to "…" in the web viewer.** The body starts with the time so it is always readable, and the "…" cell is still the button that jumps. Long bodies run off the right edge, so the measured-qdd caveat's full text lives in the table note.
- **A Vertical container splits by shares, not by content height.** The Events tab's shares are therefore computed from the content and measured on the panel separators (decision in `_events_shares`).
- **No dashed lines.** The target is pale, wider and drawn first.
- **No asset de-duplication.** A ghost would copy the UR5e meshes (about 0.3 MB each). That is why none is written while `_GHOST_ALPHA = 0`; the first builds' 6–7 ghosts took the files to 4–5 MB.
- **A view object shows in one place only.** The same tool-error view placed in Events and TCP rendered blank in TCP, so each tab gets its own instance.

## Proof

- **Viewer:** filmed in the real Rerun 0.40 web viewer with `film.cjs`, one invocation at a time, all against the final build (both .rrd written 01:12), each with `--wait 30000` (the machine was loaded).
- **Errors:** no ERROR or panic lines in any run (only the viewer's own 403 on load).
- **Playhead:** every frame landed on the time asked (playhead read back: 0.000 … 3.200 s, and 1.800 s for every still). The recording ends at 3.200 s.
- **Hero:** `node film.cjs v4/run-dev-029.rrd shots/v4/hero --every 0.1 --wait 30000`, 33 frames, Events tab.
- **Stills:** `--times 1.8 --clicks "<x>,50" --prefix tab-<name>`, with tab x positions Events 840, shoulder_pan 935, shoulder_lift 1045, elbow 1130, wrist_1 1210, wrist_2 1278, wrist_3 1353, All joints 1432, TCP 1505. The nested tabs used `--clicks "1432,50;<x>,78"`: q 930, qddd 1088. Every click landed on the first take: the right half of all 12 stills is pixel-identical to the 00:04 takes, and the 3D view differs in at most 5 px (at 1.8 s the arm sits exactly on via 2). The collapsed time bar's data ticks differ slightly, because there are no ghost tints any more.
- **Click-to-jump:** re-checked on the 01:12 run file with a scratch Playwright script outside the repo (`/tmp/v4film/click.cjs`; stops its own servers). From t = 0, after one neutral click so the log draws: row 4's time cell → 1.420 s, row 6's → 2.280 s, and a click on row 2's body leaves it at 2.280 s. Headless Chrome crashed once mid-run (the machine had ~4 GB free), so rows 6 and 2 come from a second load. The 2.280 s screenshot shows the arm a clean teal, exactly on peak speed.

File sizes:

- `v4/plan-dev-029.rrd`: 2 118 252 B (2.12 MB; 3.98 MB with the ghost copies)
- `v4/run-dev-029.rrd`: 2 765 581 B (2.77 MB; 4.94 MB with the ghost copies)

### Stills to show

| File | Shows |
|---|---|
| `shots/v4/hero/f-0-t0.png` … `f-32-t3.2.png` | Hero, run p6s, Events tab, 0 → 3.2 s every 0.1 s. One arm moves past seven numbered dots and takes each event's colour as it passes: blue start 0.0–0.1 s, red past limit 0.3–0.5, green via 1.1–1.2, magenta worst error 1.3–1.5, green via 1.7–1.9, teal peak speed 2.2–2.3 (steel again at 2.4), orange end 3.1–3.2, still lit on the last frame. In between (0.2, 0.6–1.0, 1.6, 2.0–2.1, 2.4–3.0) it is steel. The log row, the table's ▶ and the lanes follow the playhead. |
| `shots/v4/hero/f-14-t1.4.png` | Best single hero frame (the poster): the arm lit magenta 0.02 s before the worst error, "4 worst error" beside its dot, "next 4 worst error in 0.02 s", the event lines on tool speed and tool error. |
| `shots/v4/hero/f-32-t3.2.png` | The end: +3.200 s, the arm lit orange, "7 end" placed off the arm with a leader, ▶ 7, END the current log row. |
| `shots/v4/tab-events-0-t1.8.png` | Events tab at via 2 (1.80 s), arm lit green: lanes (moments 1–7, moves 1–3 + at rest), the event log with row 5 highlighted and row 2 saying MEASURED, the arm-at-each-event table with ▶ 5, the per-quantity note and the measured-qdd note, then tool speed and tool error with 7 event lines. All inside the panels at 1600×1000. |
| `shots/v4/tab-shoulder_pan-0-t1.8.png` | shoulder_pan tab: lane, q/qd/qdd/qddd strips with the target pale under the run, limit and event lines, and the q error strip (worst +0.08° at 2.60 s; qdd 111 % of limit). |
| `shots/v4/tab-shoulder_lift-0-t1.8.png` | shoulder_lift tab: the same layout (q error worst +0.09° at 1.62 s; qdd 111 %). |
| `shots/v4/tab-elbow-0-t1.8.png` | elbow tab: qdd peak 105 % of limit, with the run's noise visible over the pale target (q error +0.13° at 0.84 s). |
| `shots/v4/tab-wrist_1-0-t1.8.png` | wrist_1 tab: qd at 99 % of its limit through the middle, qdd 116 %, q error −0.52° at 1.94 s. |
| `shots/v4/tab-wrist_2-0-t1.8.png` | wrist_2 tab: the joint behind the past-limit event (qdd 145 %) and the worst error (+0.62° at 1.19 s); qd now spans −200…200, labelled every 100 (robot_msgs 3023fce). |
| `shots/v4/tab-wrist_3-0-t1.8.png` | wrist_3 tab: q 14° from its limit, qd 100 %, qdd 111 %. |
| `shots/v4/tab-all-joints-0-t1.8.png` | All joints › q / qd / qdd: robot_msgs' playhead table and six cards, with event lines. |
| `shots/v4/tab-all-joints-q-0-t1.8.png` | All joints › q: the stock q tab (six strips, limit lines), still reachable, with event lines. |
| `shots/v4/tab-all-joints-qddd-0-t1.8.png` | All joints › qddd: the stock qddd tab. |
| `shots/v4/tab-tcp-0-t1.8.png` | TCP tab: position, orientation (full title, labelled 0 and −1000), speed, angular speed and tool error, all with event lines. |
| `shots/v4/plan-0-t1.8.png` | The plan scenario at 1.8 s, arm lit green at via 2: 6 events (near limit violet, no worst error), "2" and "3" apart. The Events tab shows "the tool slowest between moves" and the per-quantity note under the table. |
