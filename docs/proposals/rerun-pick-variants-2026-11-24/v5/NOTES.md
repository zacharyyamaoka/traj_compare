# V5: Tool first

**Thesis.** The arm stays on the left and the tabs on the right, but both halves follow the tool point:

- **Left (3D):** the camera is framed on the tool's workspace. It shows a TCP triad at the playhead, the tool path coloured by speed, and a bold trail of the last 0.5 s.
- **Right (tabs):** opens on TCP, then Tool error, then V1's q · qd · qdd · qddd · q/qd/qdd. Every plot shows a following window of ±1 s around the playhead.

Build, then open:

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v5/make.py
```

```bash
/home/bam/traj_compare/.venv/bin/rerun /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v5/run-dev-029.rrd
```

## Fixed after the second check

The checker filmed the fixed build and found one new defect, plus two smaller ones. All three are fixed and confirmed on the re-filmed frames (all under `shots/v5/`):

1. **The playhead label could land far from the TCP, over the arm.** At 1.8 s it hung ~160 px below the TCP, at the flange end of the stick and over the wrist link, so it read as the wrist's label.
   - **Cause:** the first fix only tried straight above or straight below, just past the farthest mark. "Below" meant past the flange end of the 145 mm stick.
   - **Fix:** the label sits right beside the TCP, in any of 24 directions (every 15°). It takes the shortest offset that clears the triad, the stick, the bold arrow and the TCP point, and it is **never on the arm**: the box is checked against the arm's silhouette on the opening camera's pixels (`_ArmOnScreen`: each URDF collision mesh's projected convex hull, at every sample, with a 10 px gap).
   - **Choosing the side:** it prefers the side away from the flange, keeps off the bold trail and the path just ahead, and keeps off "start" / "end". A Viterbi pass over the samples stops it from flickering between sides.
   - **Measured on the model:** no sample in either scenario puts the box on the arm. The box's near edge is a median 50 px from the TCP on the run (max 98) and 33 px on the plan (max 93). The longest offsets are where the triad's 80 mm arrows fill the space around the TCP.
   - **Also:** the label lost its "(×20)", since the 3D title carries the gain and a shorter box fits closer. At an end it now reads `start · 1 mm/s · error 0.01 mm` / `end · 0 mm/s · error 0.26 mm`, and that end's own label steps aside. This replaces the old stacking.
   - **Frames:** `fix2-label-t1.8.png` (before / after at 1.8 s: the label goes from over the wrist to above the TCP, away from the arm); `hero/f-12-t1.2.png`, `hero/f-13-t1.3.png`, `hero/f-15-t1.5.png`, `hero/f-24-t2.4.png`, `hero/f-26-t2.6.png`.
2. **Faint 0.1 s error arrows drew over the bold arrow and the triad.** The faint arrow at the playhead's own 0.1 s sat on the bold one, and Rerun drew its light magenta over it.
   - **Fix:** the faint arrows are now logged over time. One is hidden while the playhead is within 0.15 s of its time, or while it passes within 6 px of the bold arrow, the triad, the TCP point or the label (on the opening camera's pixels). 3–11 of the 33 are hidden at a time, and a batch is logged only when that set changes.
   - **Frames:** `fix2-label-t1.8.png` (before: a light arrow on the bold one; after: the bold one alone), `hero/f-12-t1.2.png` (the 3.62 mm worst point, the bold arrow alone).
3. **The yaw strip carried only two labels** (0 and −1000).
   - **Cause:** Rerun labels a y axis at powers of ten only, and fades a label out under ~25 px apart. 100° steps over yaw's ~660° need ~180 px of plot, so no fixed range on the old 75 px could carry more. A range fitted to the ±1 s window doesn't help either: the window holds up to 633° of yaw.
   - **Fix:** yaw now spans −857…−143 (snapped to 50, thin margins) on a taller strip. It is labelled every 100°, −800 … −200: seven labels, ~25 px apart.
   - **Making room:** the other strips' ranges are snapped finer. Position is −464…1264, roll/pitch ±130 (labelled −100 / 0 / 100), speed 0…1664 (0 / 1000; its "2000" used to sit cut on the top edge) and angular speed 0…468 (0 … 400). The panes were then re-shared so each keeps its labels ≥ ~25 px apart: run `[197, 121, 115, 221, 92, 159]`, plan `[152, 140, 117, 221, 96, 179]` px of 905.
   - **Frames:** `fix2-yaw-axis.png` (before / after, y-label columns), `tab-tcp-0-t1.8.png`, `plan-0-t1.8.png`.

Found and fixed while re-filming:

- **"end" floated over the wrist** at 2.2–2.4 s, where the wrist passes over the end point; at 2.5 s it sat inside the triad. An end's label is now hidden while the arm's silhouette or a mark at the TCP covers it: "start" until 0.14 s, and "end" from 2.12 s (from 2.57 s the playhead label carries it). Frames: `hero/f-22-t2.2.png`, `f-25-t2.5.png`.
- **The readout's error line was clipped** on the first re-share. The readout pane is 197 px on the run and 152 on the plan.
- **The position strip was squashed** to ~45 px on the first re-share. It got the height that was left (~80 px of plot).

## Fixed after the check

An independent checker filmed the first build and found six defects. All six are fixed. Each was confirmed on the re-filmed frames (all under `shots/v5/`). Items 2 and 3 were reworked in the second check (above).

1. **The grey target path drew over the speed-coloured path.** On the fastest stretch (1.9–2.5 s) the lime was greyed and a grey stripe ran through the bold trail.
   - **Cause:** Rerun 0.40 draws a line as a camera-facing ribbon. A thin target line inside the solution's thicker one ends up in front of it.
   - **Fix:** the target path is drawn only where it parts from the solution's by more than the bold trail's half-width plus its own: 8.5 + 1.6 = 10.1 mm. Nothing is offset.
   - **On this run:** the paths never part by more than 3.62 mm, so the target path is not drawn at all. The 3D title says so ("target path not drawn"), and the magenta ×20 arrows show the deviation.
   - **Frames:** `hero/f-22-t2.2.png` and `hero/f-24-t2.4.png` (clean lime trail at 1414 and 1143 mm/s).
2. **The orientation strip was unreadable.** The unwrapped yaw turns −173 → −828°, which flattened roll and pitch on one shared range.
   - **Fix:** roll/pitch and yaw are two strips, each with its own range. At this round they spanned −216…216 and −1040…40; the second check narrowed both.
   - The strips are V5's own entities, `/tcp/roll_pitch_deg/<name>` and `/tcp/yaw_deg/<name>`. V1's 3-angle entity is filtered out.
   - **Frame:** `tab-tcp-0-t1.8.png`.
3. **The playhead label overprinted the triad and hid start/end, in a low-contrast speed colour.**
   - **Fix (still current):** the label now rides on a point of its own, drawn at radius 0 in a dark neutral (Rerun draws label text in its point's colour). That point is placed in screen pixels with a pinhole model of the fitted camera.
   - **Fix (this round, since replaced):** it went straight above or below the TCP. It sits just past the triad, the flange stick, the error arrow and the TCP point, on the nearer side that keeps the box inside the view and leaves start/end uncovered. It slides sideways only to stay in view.
   - **Start/end:** each label stays on its point except while the TCP sits on that end (within 20 mm: until 0.13 s and from 2.57 s). Then it stacks just beyond the playhead label.
   - **Superseded:** the above/below placement and the stacking were replaced in the second check (item 1 above). Below the stick at 1.8 s was the new defect.
4. **The rose error arrow was too close in hue to the triad's red x.**
   - **Fix:** the error arrows and series are now magenta (200, 30, 200), the faint arrows light magenta (230, 160, 230). The title says "magenta error ×20".
   - **Frames:** `hero/f-12-t1.2.png` (the 3.62 mm worst point: the magenta arrow beside the red x arrow), `tab-error-0-t1.8.png`.
5. **V1's "TCP angular speed" strip was missing.** It is back as the TCP tab's last strip (peak 415 °/s at 1.45 s), with the target pale under it.
   - **Frame:** `tab-tcp-0-t1.8.png`.
6. **The 3D title was cut at half width**, losing the run name, robot and duration.
   - **Fix:** it now leads with them and keeps only the key the view can't draw. On the run: `p6s on workspace-dev-029 · ur5e · 3.20 s · purple→lime 0–1507 mm/s · magenta error ×20 · target path not drawn`. On the plan: `… · bold = last 0.5 s · triad = TCP`. Both fit at 1600 × 1000.
   - **Frames:** any; `tab-tcp-0-t1.8.png`, `plan-0-t1.8.png`.

Found and fixed while re-filming:

- **The readout's error line was pushed out.** With six panes in the TCP tab, it fell below the readout. Now t sits in the table's corner and one line follows the table.
- **The angular-speed strip showed a lone "0".** Rerun labels a y axis at powers of ten only, and fades a label out when ticks are under ~25 px apart. Its range was snapped finer (0…520; 0…468 since the second check), so it is labelled every 100.
- **The middle Tool error title was cut.** It is shorter now.

## What is on screen

- **Left half (3D).**
  - The URDF arm (the solution).
  - The whole tool path, coloured purple (0) → lime (1507 mm/s, the peak, at 2.28 s).
  - The same path drawn thick for only the last 0.5 s (the trail).
  - At the playhead: the TCP triad (x red, y green, z blue), a point in its speed colour, and a flange → TCP stick. The label sits in dark text right beside the TCP, on the side away from the arm and never on it, e.g. `560 mm/s · error 1.94 mm`.
  - Start and end points with grey labels. A label steps aside while the arm or the TCP's marks cover it, and while the TCP sits on that end (the playhead label then leads with "start" / "end").
  - On the agent's run only: magenta error vectors, drawn ×20 from the target's tool point. The bold one is at the playhead; faint ones every 0.1 s are shown away from it, never over the bold arrow, the triad or the label. The target path is not drawn (see fix 1).
- **TCP tab** (opens first).
  - **A readout at the playhead:** a table of x/y/z mm, roll/pitch/yaw ° and mm/s for the solution, the target and the error, with t in its corner.
  - **One line under it:** the error at the tool point, the agent's ruler (RMS 1.09 mm) and the ±1 s window.
  - **Then five strips:**
    - position (x/y/z mm, −464…1264);
    - roll/pitch (°, ±130);
    - yaw (°, its own range, −857…−143, the tallest strip, labelled every 100°);
    - speed in mm/s, drawn on the 3D path's own per-sample colours (0…1664);
    - angular speed (°/s, 0…468).

    On the run, the target sits pale under each strip.
- **Tool error tab** (run only). Three strips:
  - the agent's own ruler `tool_error_mm` (peak 2.11 mm at 1.42 s), with its RMS 1.09 mm as a grey line;
  - the tool point's error vector, solution − target at the dataset's tool point from URDF FK: |error| in magenta plus x/y/z. Peak 3.62 mm at 1.20 s; it is the vector the 3D arrows draw ×20.
  - the tool orientation error, the angle between the two tool frames (peak 0.71° at 0.84 s).
- **q · qd · qdd · qddd · q / qd / qdd.** V1's strips, titles, limit lines, cards and playhead table, unchanged, except that the time axis is the following window. Their y ranges come from robot_msgs main, which includes 3023fce's strip-range fix: wrist_2 qd is now −224…224.
- **Plan scenario.** Same layout, with no target, no arrows and no Tool error tab: TCP, q, qd, qdd, qddd, q/qd/qdd.

## Decisions

1. **V1 is reused by filtering, not copying.** `viz._log_robot` writes into a thin `_Without` wrapper that drops three things:
   - V1's tool path (`/world/<name>/tool/...`);
   - V1's one-colour speed series (static, it would shadow the per-sample colours);
   - V1's 3-angle orientation entity (split here into roll/pitch and yaw).

   Everything else is robot_msgs' own: the stock series in degrees, the jerk, the limits, the cards, the playhead table, the angular speed series and the URDF arm.
2. **The following window is native Rerun.** Every plot uses `rrb.TimeAxis(link="Independent", view_range=TimeRange(cursor_relative(-1 s), cursor_relative(+1 s)))`. Each y range is fixed over the whole motion, snapped to round steps, so the axis doesn't jump as the window scrolls.
3. **The camera is fitted to the tool, and the labels are placed on its screen.**
   - **Direction:** along the tool path's best-fit plane normal, turned 35°, 25–50° above the horizon.
   - **Distance:** a projection fit moves it in as close as every link origin at every sample, plus the path, allows.
   - **Labels:** the same camera, as a pinhole (`_Screen`: 55° vertical FOV, an 800 × 908 px view), places them. Checked: it puts the TCP within 3 px of where the viewer draws it at t = 0, 1.8 and 3.2 s.
   - **The arm on those pixels:** `_ArmOnScreen` projects each URDF collision mesh (the STLs the viewer draws) at every sample and fills its convex hull on a 4 px grid. Overlaid on the real 1.8 s frame, it covers the drawn arm. The playhead label is placed off it, and an end's label is hidden while it is covered. Placement costs ~9 s per scenario; the build takes ~22 s for both.
4. **The error is drawn ×N in magenta, and the target path only where it parts.**
   - N is a round 1/2/5 × 10^k, chosen so the largest vector is about 1/7 of the workspace. Here that is ×20.
   - A coincident target line is left out rather than drawn over the signal (see fix 1).

## Best when / loses when

- **Best when** the question is about the tool: where it went, how fast, and how well it tracked. That covers pick-and-place, tours, and the tracking agent's runs. The cursor sits mid-plot, so you see what is coming as well as what just happened. One still answers "where on the path is it slow" (the path colour plus the speed strip) and "where did it miss" (the ×N arrows).
- **Loses when** you want the whole run's curves at a glance. The plots show 2 s of the 3.2 s, and half the window is empty at the ends.
- **Also loses on** joint-space moves with little tool travel: the path is a stub and the camera fit has nothing to frame.
- **The plots are no longer linked.** `Independent` drops V1's "zoom one plot, all follow".
- **N scales itself, so every run's arrows look the same size.** Only the ×N says how big the error is.
- **Fixed label placement.** The labels are placed for the default camera at 1600 × 1000. Orbit the view and they keep their offsets from the TCP in metres, which may then cover something.

## Worth keeping in a splice

- **`_following()`**: a ±N s following time axis for any tab of any variant. Pair it with fixed y ranges.
- **The speed key**: the path's per-sample speed colours, reused on the speed strip (`SeriesLines` colours sent per sample work in 0.40). The strip is the path's colour legend.
- **`_tool_eye` + `_Screen` + `_ArmOnScreen` + `_place_labels`**: the projection-fit camera, the arm's silhouette on its pixels, and a label kept beside its point, off the arm and the point's own marks, inside the view, without flicker. Any 3D annotation could use it.

## The signature it would add to robot_msgs (additive)

```python
viz.rerun.save(path, traj, robot=urdf, tool=tcp,                      # today's V1 call, unchanged
               target=None, target_tool=None, extras=None,            # a run: Tool error tab, ×N arrows, target path where it parts
               follow_s=None, trail_s=None, color_tool_by=None,       # e.g. follow_s=1.0, trail_s=0.5, color_tool_by="speed"
               first_tab="q")                                         # "TCP" opens tool first
```

Every new keyword defaults to today's behaviour. `make.py`'s own entry point is `save(path, traj, *, robot, tool=None, target=None, target_tool=None, extras=None, name=None)`. `name` (the entity and title name; default: the extras label) is an addition to the contract's signature.

## What Rerun 0.40 could not do (and what V5 does instead)

- **No fade by age.** The trail is a hard 0.5 s window (a `VisibleTimeRanges` override, cursor −0.5 s … cursor) at one thickness.
- **No draw order for 3D lines.** Lines are camera-facing ribbons, so a thin line inside a thick one shows in front of it. V5 leaves the coincident target path out (fix 1).
- **No colour-bar legend for a 3D colour scale.** The scale goes in the title, after the name, robot and duration. The speed strip, drawn on the same colours, is the visual key.
- **Labels can't be placed.**
  - A label sits on its point, its text takes the point's colour, and it can't be offset.
  - Geometry (the triad) draws over it.
  - Rerun draws a label on top of the geometry in front of its point, so a static label (like "end") floats over the arm when the arm passes in front of it.
  - V5's workaround is labels on their own radius-0 points, placed beside the TCP off the arm's silhouette from the default camera, with an end's label hidden while covered (second check, item 1). They don't follow an orbit.
- **No dashed or alpha-faint series lines.** A line alpha draws darker in 0.40. The target is a pale, opaque, wide line drawn under the solution, by entity-path order (`/tcp/.../_target`).
- **The 3D field of view is not in `EyeControls3D`.** The camera fit and the label placement assume Rerun's default 55° and the 800 × 908 px view of a 1600 × 1000 page. They were checked on the hero frames, not on other window sizes.
- **Y labels are powers of ten only.** They also fade out when closer than ~25 px, and there is no tick-step setting. So yaw (span ~660°) needs a ~180 px plot to be labelled every 100°: it gets the tallest strip, and the others' ranges are snapped tight to make room. Position and speed are labelled in 1000s.
- **Linked zoom and a following window don't combine.** Per the SDK doc, `LinkToGlobal` uses the shared global range instead of a view's own `view_range`.
- **Not tried:** `EyeControls3D(tracking_entity=…)`, a camera that rides the TCP.

## Files

- **`v5/make.py`**: `save()` + `main()`. Run with the traj_compare venv.
  - `application_id` is `rerun_pick_v5`.
  - The blueprint is embedded at save, and the file opens paused at t = 0 on the TCP tab.
  - It imports robot_msgs main (3023fce), which is not edited.
- **`v5/plan-dev-029.rrd`**: **1,739,586 B (1.74 MB)**.
- **`v5/run-dev-029.rrd`**: **2,013,964 B (2.01 MB)**. V1's, with ghosts, are 2.18 / 2.25 MB.
- **Filming:** with `film.cjs`, one invocation at a time, against this build.
  - The only console line is the viewer's own `403` on load. There is no ERROR, no panic, and no `PANICKED`.
  - Every playhead landed where asked.
  - The qd still's first take died with a headless-Chrome "Target crashed" (host memory: 7 GB free under the other lanes' filming), not a viewer panic. Re-filmed cleanly.

## Stills to show

- **`shots/v5/hero/f-0-t0.png` … `f-32-t3.2.png`**: the hero, 33 frames, 0.1 s apart, on the TCP tab.
  - The arm moves along the speed-coloured path with its bold 0.5 s trail and the TCP triad.
  - The magenta ×20 arrows sit along the path.
  - The dark label stays right beside the TCP, off the triad and never on the arm.
  - The faint arrows step aside near the playhead.
  - The plots scroll under a cursor that stays mid-plot.
  - Good single frames:
    - `f-0-t0.png`: start, the label reads `start · 1 mm/s · error 0.01 mm` above the triad;
    - `f-12-t1.2.png`: the bold magenta arrow alone at the 3.62 mm worst point, the label right of the forearm (not on it);
    - `f-18-t1.8.png`: the label above the TCP, away from the arm (where the defect was);
    - `f-22-t2.2.png` / `f-24-t2.4.png`: the lime fastest stretch, clean; "end" hidden while the wrist covers it;
    - `f-32-t3.2.png`: the end, `end · 0 mm/s · error 0.26 mm` left of the TCP; the window's right half is empty.
- **`shots/v5/fix2-label-t1.8.png`**: before / after at 1.8 s, 2× zoom on the TCP. Before: the label over the wrist and a light arrow on the bold one. After: the label above the TCP and the bold arrow alone.
- **`shots/v5/fix2-yaw-axis.png`**: before / after, the TCP tab's y labels. Yaw goes from 0 / −1000 to −200 … −800.
- **`shots/v5/tab-tcp-0-t1.8.png`**: TCP at 1.8 s.
  - The readout: solution / target / error rows, 1.94 mm at the tool point, ruler 0.93 mm.
  - The five strips: position, roll/pitch (−100 / 0 / 100), yaw on its own tall range (−200 … −800), speed on the path's colours, angular speed (0 … 400). The target is pale under each.
- **`shots/v5/tab-error-0-t1.8.png`**: Tool error at 1.8 s. The agent's ruler (magenta) with its RMS line, the tool point error vector (|error| magenta + x/y/z), and the orientation error in degrees.
- **`shots/v5/tab-q-0-t1.8.png`**: q at 1.8 s. V1's six joint strips (travel, to limit, limit lines) in a ±1 s window.
- **`shots/v5/tab-qd-0-t1.8.png`**: qd at 1.8 s. Peak and % of limit per joint; wrist 2 and wrist 3 reach 100 %, on robot_msgs' new snapped ranges.
- **`shots/v5/tab-qdd-0-t1.8.png`**: qdd at 1.8 s. The solution's differenced qdd is noisy and up to 145 % of limit.
- **`shots/v5/tab-qddd-0-t1.8.png`**: qddd at 1.8 s, the slope of qdd (noise-dominated on encoder data).
- **`shots/v5/tab-cards-0-t1.8.png`**: q / qd / qdd at 1.8 s. V1's playhead table and % of limit cards, each a ±1 s window.
- **`shots/v5/plan-0-t1.8.png`**: the plan scenario at 1.8 s. Same framing and trail, with no target or arrows; the label reads `557 mm/s`, just right of the TCP.
  - The title is `workspace-dev-029 · ur5e · 3.20 s · purple→lime 0–1507 mm/s · bold = last 0.5 s · triad = TCP`.
  - The TCP readout has one "plan" row.
