# V2 · Target vs run

**Thesis.** The agent's run as one solid steel arm. Its deviation from the target is drawn ×N as a thin magenta skeleton
(FEA style: elbow → wrists → flange → tool point of the arm at target + N × (run − target)), labelled with N and the
true TCP offset, with both tool paths (the target's dashed blue). The right half opens on an **Error** tab: the agent's
own ruler in mm with its RMS 1.09 mm, the TCP offset the 3D label reads, and each joint's error in degrees. Then come
V1's six tabs, each with the target as a pale line under the run's bold one. With no target (the plan) it degrades to
one arm and the six tabs.

```bash
/home/bam/traj_compare/.venv/bin/rerun /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/v2/run-dev-029.rrd
```

Built by `v2/make.py` (`save(path, traj, *, robot, tool=None, target=None, target_tool=None, extras=None)`, `main()` writes
both scenarios). Application id `rerun_pick_v2`, blueprint embedded at `rec.save(..., default_blueprint=...)`, opens paused
at 0 s on the Error tab. The pieces come from robot_msgs.viz.rerun by import: `_RobotPlan` (one per trajectory),
`_urdf_copy` (the steel arm), `_strip`/`_cards`/`_tcp_strips`/`_tables`, `_forward_kinematics`, `_tip_link` and `_eye`.
robot_msgs is not edited; the rebuild picks up main's strip-range fix (3023fce).

## What is on screen (run-dev-029, p6s)

- **Left, the 3D view.** Title (the whole key, 114 characters, ends before the view's icons at 1600 px):
  `steel = run · magenta skeleton = run ×50 about the target · dashed blue = target path (arm ≤ 0.62° off, not drawn)`.
  - steel arm = the run (joint encoders). No target arm is drawn: it is within 0.62° of the run, the same pose at this
    scale.
  - magenta skeleton = the run magnified ×50 about the target (target + 50 × (run − target)), at the playhead. It is
    one 3.5 mm line through the ×50 arm's elbow, a corner where the forearm meets the wrist_1 housing, wrist_1, wrist_2,
    the flange (wrist_3) and the ×50 tool point, with a 9 mm sphere at each of the four joints. Inside the steel the
    depth test hides it, so it only shows where the deformation takes it out of the casting (decision 1).
  - orange = the run's tool path, solid to the playhead and faint after it (V1's);
  - dashed blue = the target's tool path;
  - pink line = the ×50 run's tool path;
  - at the playhead, a thick magenta arrow from the target's tool point to the ×50 tool point, which is where the
    skeleton ends. Its label, `run ×50 · TCP off 3.3 mm`, sits on a thin leader off the arrow (decision 6).
- **Right, the tabs:**
  - **Error** (open on load):
    - Tool error [mm]: the agent's ruler (`extras["tool_error_mm"]`) bold magenta over a shaded area, and a pale line
      `TCP off (FK, 145 mm point) = 3D label`. Title:
      `ruler (bold) RMS 1.09 (the agent's score), max 2.11 at 1.42 s · TCP off (pale) max 3.62 at 1.20 s`. Legend in
      the top right, where both lines stay under 1.6 mm.
    - Joint error, run − target [°]: all six joints on one axis, no legend. The title names the two worst by their line
      colour: `purple wrist_2 +0.62° at 1.19 s · green wrist_1 -0.52° at 1.94 s · the rest within ±0.13°`.
    - A table at the playhead: `ruler 2.05 mm · TCP off 3.30 mm (the 3D label; arrow ×50) · p6s`, then each joint's
      target, run, run − target and qd difference.
  - **q · qd · qdd · qddd:** V1's strip per joint. The target is a 6 px pale line under the run's 2 px ink line, and each
    title adds `run − target ≤ …`. No legend. The first strip's title carries the key:
    `bold = run, pale = target, grey = limit` on q, qd and qdd. On qddd it is `bold = run, pale = target`, because no
    jerk limit exists and no grey line is drawn there.
  - **q / qd / qdd:** V1's cards and table. Each card adds the target's three lines, pale and wide, underneath; the
    table's key line says so.
  - **TCP:** position, orientation, speed and angular speed, with the target pale under the run. No legends; the
    titles carry the key. Position, speed and angular speed each say `bold = run, pale = target` (speed and angular
    speed are a bold line over a pale one of a single colour, with nothing else to tell them apart). Orientation reads
    `roll red, pitch green, yaw blue (ROS rpy, unwrapped) · near gimbal lock 1.05–1.12 s` and drops the source, which
    position names just above it.

## Decisions

1. **The deviation is an FEA deformation, done in joint space, and drawn as a skeleton, not as a second arm.** Every
   joint is at target + N × (run − target). The ×N arm is a magenta line through its joint origins plus small joint
   spheres, ending at its tool point, where the arrow points.
   - Joint space keeps the arrow's tip exactly on the magnified arm's tool point. The Cartesian alternative (target tool
     + N × the tool's deviation) drifted up to 7.4 mm off it at ×20 on this run.
   - N is the 1-2-5 number nearest 35 % of the tool path's bounding radius over the peak deviation. That gives ×50 here
     (176 mm drawn for 3.62 mm true). The first build's 15 % gave ×20 and a ~10 px arrow.
   - **Why a skeleton.** Two mesh overlays failed. The first was a magenta glass arm. The second was pale pink glass,
     faded in by each link's distance from the steel. Even faded, from the opening camera it lay on the steel run arm
     for about half the clip. Measured on the same 33 frames against a build with no overlay, it covered up to 27 % of
     the steel arm's pixels (1.5 s) and more than 5 % in 15 frames; the check measured up to 34 % tinted mauve at
     1.3–1.6 s. The skeleton covers at most 2.2 % (1.4–1.5 s), in no frame more than 5 %, 0.7 % on average.
   - **Where it starts.** The skeleton starts at the first link that moves at least half as far as the farthest one.
     At ×50 the base and shoulder move 0 mm, the upper arm 32 mm, the forearm 70 mm and the wrists 99 mm, so it starts
     at the elbow, as asked. Drawn from the shoulder, it would run inside the steel and say nothing.
   - **Routed through the casting.** A URDF's joint origins sit on the joint axes. The UR5e's wrist_1 is 133 mm along
     its axis from the forearm's line, so a straight elbow → wrist_1 segment cut diagonally out of the forearm even at
     zero error. Each offset is routed along the link first, then along the child joint's axis (the corner point). At
     zero error the whole skeleton then lies inside the steel, apart from the flange → tool segment, which is in the
     air. Only the deformation brings it out (`_Run._skeleton`).
   - **Sizes.** The opening camera shows about 0.5 px per mm. A 3.5 mm radius is a ~3.5 px line on a ~38 px forearm,
     and a 9 mm sphere is ~9 px. The 7 mm arrow stays the boldest magenta mark.
2. **No target arm.** The target is within 0.62° of the run. Drawn as glass, it lay on the steel and z-fought (mottled
   stripes on the base and upper arm). The title says why it is missing; the dashed blue path and the arrow's origin
   still show where the target is.
3. **One name per measurement, so the two halves never disagree.** The ruler (the agent's own number, 2.05 mm at
   1.4 s) and the TCP offset (FK at the dataset's 145 mm tool point, 3.30 mm at 1.4 s) are different quantities. The 3D
   label says `TCP off`. The Error tab's pale line, its legend, its title and the table say `TCP off` too. The ruler's
   numbers sit in the title and the table.
4. **The target is a pale, wide line under a bold one, not dashed**, because Rerun 0.40 has no dash style. To get the
   draw order right, the target's entity part is `reference`, which sorts before `solution`; the hover still reads
   "target".
5. **No legend over a curve.** Rerun's legend has a fixed size and sits inside the plot. In a ~130 px strip it covered
   the last half second, so keys live in titles: run / target / limit on the joint tabs, run / target on TCP position,
   speed and angular speed. The one legend kept (tool error) sits in that plot's empty top right.
6. **The magnifier's label is placed, not pinned.** Rerun draws a point's label just under the point and has no
   placement control. So `_label_places` tries a few spots per instant, in order: one step (0.22 × path radius, 97 mm)
   above the arrow's upper end, two steps above, beside left or right, below its lower end. It keeps the first whose
   label box clears the `start` / `end` labels and points, the arrow and the view's edge, and holds the previous pick
   while that still clears (no flicker). The boxes are computed at the opening camera at 1600 x 1000: Rerun's 55°
   field of view, fitted to the first build's frames to 1 px on four known points. Over the 33 hero instants the label
   clears `start` by ≥ 21 px and `end` by ≥ 103 px. A fixed lift off the ×N tip sat on the arrow's shaft at 1.2 s; a
   fixed lift off the arrow's top landed on `start` there.

## Best when / loses when

- **Best when** reviewing a tracking run with sub-millimetre, sub-degree errors. One still answers how far off the run
  is (ruler, RMS, max), where along the path (the pink ×50 path and the arrow), and which joint (wrist_2, then wrist_1;
  the ×50 skeleton bends out of the forearm and wrists). The playhead ties all three together.
- **Loses when:**
  - There is no target. The plan is V1 minus its start/end ghosts: one arm, the six tabs.
  - Errors are large. N falls to ×1-2 and the overlay adds little. The missing target arm would then matter; it would
    need its own glass arm again, and that only works once the two arms visibly separate.
  - Someone opens it cold mid-run. A magenta wire that comes out of the arm and goes back in needs the title's key.
    It reads as a deformed arm only where enough of it is out of the steel (0.8–1.6 s, 2.0–2.1 s).
  - You want several runs against one target. A recording holds one target and one run.

## Worth keeping in a splice

- **The deformation skeleton** (`_Run._magnifier` + `_Run._skeleton` + `_log_tool`'s skeleton, joints and arrow): a
  joint-space ×N arm drawn as a wire through its joint origins, routed through the castings so that it hides in the
  steel at zero error. It ends at the ×N tool point, with a thick arrow labelled with N and the true TCP offset. It needs
  no URDF loader change, and any target-vs-run view can take it, including V5's error vectors.
- **Label placement at the opening camera** (`_screen` + `_label_places`): a moving label kept off fixed ones, which
  Rerun does not do. Every variant with start / end labels and a playhead label has the same collision.
- **The overlay rule for two trajectories in one plot:** pale and wide under bold, with the target's entity path
  sorting first. This is the only lever on draw order that Rerun 0.40 has.
- **The Error tab:** the ruler with the shaded area under it (a `Measurements` band from 0 to the error, centre line at
  width 0), the TCP offset named as the 3D label names it, all joints' errors keyed in the title, and the target-vs-run
  table at the playhead.

## Signature it would add to robot_msgs (additive)

```python
viz.rerun.save(path, solution, robot="ur5e.urdf", tool=tcp,
               target=planned, target_tool=planned_tcp,          # new: the overlay robot= refuses today
               tool_error_mm=ruler, tool_error_rms_mm=1.09,      # new: the Error tab's ruler and its score
               magnify="auto")                                   # new: ×N (int) or "auto" (1-2-5, 35 % of the path)
traj.show(robot="ur5e.urdf", tool=tcp, target=planned, target_tool=planned_tcp)
```

All keyword-only, defaulting to today's behaviour. `_robot_inputs` refuses a second JointTrajectory today ("overlays of
several trajectories on one arm are not designed yet"), and `target=` is that design. The recording's layout adds
`/world/<name>/magnifier/{path,now,skeleton,joints,tip,leader,label}`, `/world/<name>/target_tool/...`,
`/error/tool|joint/...`, `/notes/error` and the `reference` series beside the run's. The skeleton needs only
`_forward_kinematics` and the URDF tree, both already in robot_msgs. It no longer needs a per-link tint on the
timeline, which the mesh overlay did.

## What Rerun 0.40 could not do (and what V2 does instead)

- **No dashed line style** for `SeriesLines` (colours, widths, names, visibility only) or `LineStrips3D`. In the plots the
  target is faint (pale and wide), not dashed. In 3D the target path is cut into alternating 12 mm pieces, so it reads as
  dashed.
- **No control of series draw order.** The plots draw (and the legends list) series in entity-path order. Log order and
  `contents` order do not count, hence the `reference` entity name (and `fk_tcp_off` < `ruler` on the Error tab).
- **No fill-between.** The shaded error is the stock `band` trick (a `Measurements` ±σ band from 0 to the error), drawn
  at about a quarter of its colour whatever the alpha (hence alpha 255). Its centre line drew a false second curve at
  half the error until it was given width 0.
- **No legend outside the plot, no smaller legend.** `PlotLegend` has only `visible` and `corner`, so keys moved into
  titles.
- **Coincident translucent meshes z-fight** (mottled stripes), and a translucent mesh over an opaque one tints it. The
  target arm is not drawn, and the ×N arm is a line and points, which the steel's depth hides.
- **Coincident lines have no draw priority.** Near zero error the skeleton's flange → tool segment lies on the run's
  grey tool stick (radius 4 mm), and the thinner magenta (3.5 mm) is drawn over it. The steel arm is unaffected.
- **No label placement control or collision avoidance.** A point's label is drawn just under the point, so the
  magnifier's label is placed from the recording's side (decision 6). That holds at the opening camera only; after an
  orbit the labels can meet again. The .dae visuals cannot be drawn, so the arm is its collision meshes.

## Fixed after the check (2026-11-24)

1. **The arm never read as "steel = run"** (the target glass z-fought the steel, and the ×20 magenta sat on the forearm
   and wrists). The target arm is gone (the title says it is within 0.62°, not drawn). The ×N overlay became pale pink
   glass faded in by distance. *That was superseded by the second check's skeleton (below).*
2. **The magnifier label covered start / end** at 0 s, 3.2 s and 1.4 s. It now sits on a thin leader off the arrow, at
   the first of a few spots whose screen box clears `start` / `end` and the arrow (decision 6; ≥ 21 px from `start`
   at every hero instant). Frames: `hero/f-0-t0.png` (above, `start` clear), `hero/f-12-t1.2.png` (beside the arrow,
   where "above" would have hit `start`), `hero/f-14-t1.4.png` (above `start`), `hero/f-32-t3.2.png` (above `end`).
3. **Two "true" errors for one moment** (3D `true 3.3 mm`, Error tab ruler 2.05 mm). The 3D label now reads
   `run ×50 · TCP off 3.3 mm`. The Error tab's pale line is `TCP off (FK, 145 mm point) = 3D label`, the title carries
   both (`ruler (bold) RMS 1.09 … max 2.11 · TCP off (pale) max 3.62`), and the table says `ruler 2.05 mm · TCP off
   3.30 mm (the 3D label; arrow ×50)`. Frame: `hero/f-14-t1.4.png`.
4. **The 3D title was cut off at "dashed ▸"**. It was shortened then, and is 114 characters now; it still ends before
   the view's icons at 1600 px. The run's label moved to the Error table. Frame: any hero frame, e.g.
   `hero/f-0-t0.png`.
5. **Legends covered the ends of curves.** The joint-error legend is gone; its key is the title (the two worst joints
   by colour, the rest bounded). TCP position and orientation lost their six-entry legends to title keys. The joint
   tabs' first-strip legend (limit, target, solution), which covered shoulder_pan's last half second, became a title
   key. The tool-error legend moved to its plot's empty top right. Frames: `tab-error-0-t1.8.png`,
   `tab-tcp-0-t1.8.png`, `tab-q-0-t1.8.png`.
6. **The arrow was ~10 px and the shading barely visible.** N went from ×20 to ×50 (35 % of the path radius, 176 mm
   drawn at the 3.62 mm peak), the arrow's radius from 3.5 to 7 mm, and the shade's alpha from 55 to 255. Rerun draws a
   `Measurements` band at about a quarter of its colour, so that is (243, 212, 230) on white; 120 was still only
   (249, 235, 243). Frames: `hero/f-12-t1.2.png` (a ~65 px thick arrow), `tab-error-0-t1.8.png` (the shaded area
   under the ruler).

## Fixed after the second check (2026-11-24)

1. **The ×50 pink glass lay on the steel run arm for about half the clip.** The check counted 16 of 33 frames, with up
   to 34 % of the arm mauve at 1.3–1.6 s, including `f-14-t1.4`. The ×N arm is now a skeleton (decision 1): one 3.5 mm
   magenta line through the ×50 elbow, wrists, flange and tool point, with 9 mm joint spheres. The ×50 mesh copy, its
   per-link fade (`_faded_copy`) and the 3D view's link exclusions are gone.
   - **How it was measured.** A temporary build with no overlay was filmed at the same 33 instants. Its grey pixels in
     the 3D half are the steel (and the grey tool stick). A frame's overlay is every pixel that differs from that
     build by more than 12 levels.
   - **Before:** up to 27.2 % of the steel covered (1.5 s), more than 5 % in 15 frames, 26.8 % at 1.4 s.
   - **After:** at most 2.2 % (1.4 and 1.5 s), no frame over 5 %, mean 0.73 %. After 2.4 s the 0.4–0.7 % left is the
     flange sphere on the wrist_3 face and the ×50 tool segment over the grey stick.
   - **Frames:** `zoom/f-14-t1.4-before-after.png`, `zoom/f-15-t1.5-before-after.png` and
     `zoom/f-12-t1.2-before-after.png` show 2× crops of the arm, the old build on the left and this one on the right.
     `hero/f-0-t0.png` and `hero/f-32-t3.2.png` show all steel at the ends.
2. **The q · qd · qdd · qddd keys had lost the grey limit line** when the legend became a title key. The first strip
   now reads `bold = run, pale = target, grey = limit` on q, qd and qdd, where the grey lines are drawn. On qddd it
   stays `bold = run, pale = target`: there is no jerk limit and no grey line, and saying "grey = limit" there would be
   false. All four titles end before the plot's icons at 1600 px. Frames: `tab-q-0-t1.8.png`, `tab-qd-0-t1.8.png`,
   `tab-qdd-0-t1.8.png`, `tab-qddd-0-t1.8.png`.
3. **The TCP orientation title was cut off at 1600 px** (148 characters). It is 105 now:
   `TCP orientation [°] · roll red, pitch green, yaw blue (ROS rpy, unwrapped) · near gimbal lock 1.05–1.12 s`. The
   source it dropped (`tool PoseTrajectory tool in base_link_ur`) is in the position title above it. Frame:
   `tab-tcp-0-t1.8.png`.
4. **TCP speed and angular speed had no run / target key.** Both titles now say `bold = run, pale = target`, before the
   source, so that a narrower window cuts the source first. Frame: `tab-tcp-0-t1.8.png`.
5. **The previous `tab-tcp-0-t1.8.png` showed the Error tab** (its click missed the TCP tab). It was re-filmed with the
   click at (1215, 50) and now shows TCP. The tab clicks used are Error (843, 50), q (890, 50), qd (935, 50),
   qdd (990, 50), qddd (1050, 50), q / qd / qdd (1135, 50) and TCP (1215, 50).

## Files

- `v2/make.py`: the variant (run with `/home/bam/traj_compare/.venv/bin/python v2/make.py`).
- `v2/plan-dev-029.rrd`: **1,573,548 bytes (1.57 MB)**. One arm, no ghosts, so it is 0.61 MB smaller than V1's.
- `v2/run-dev-029.rrd`: **2,332,030 bytes (2.33 MB)**. One URDF copy (the run), plus the target's series, the skeleton
  and the magnifier: 0.08 MB more than V1's. The second check's build was 2.69 MB, carrying a second (×50) URDF copy
  and its per-link tint; the first build was 3.00 MB, with a third copy for the target.

## Proof

Filmed in the real Rerun 0.40 web viewer with `film.cjs`, one invocation at a time. Every frame landed on the asked time.
**No ERROR or panic line in any run.**

Stills (in `shots/v2/`, all re-filmed from this build):

- `hero/f-0-t0.png` … `hero/f-32-t3.2.png`: the hero, 33 frames every 0.1 s on the default Error tab. The steel arm
  moves through the whole tour and stays steel. The ×50 skeleton bends out of the forearm and wrists as the deviation
  grows (0.5–1.6 s, 2.0–2.1 s) and goes back inside them. The arrow and its lifted label follow the ×50 tool point
  (TCP off 0.0 mm at 0 s, 3.6 mm at 1.2 s, 0.3 mm at 3.2 s). The playhead sweeps the ruler and joint-error plots, and
  the table updates each frame.
  - `hero/f-0-t0.png`: start. All steel, with the skeleton inside it; the label above `start`.
  - `hero/f-12-t1.2.png`: the peak TCP offset (3.62 mm). The ×50 wrist and tool point lie well below the steel ones,
    with the thick arrow from the target's tool point.
  - `hero/f-14-t1.4.png`: next to the ruler's peak (2.11 mm at 1.42 s). The skeleton steps out of the forearm and runs
    through the wrists to the arrow's tip, and the steel stays steel. The label reads `TCP off 3.3 mm`, the table
    `ruler 2.05 mm · TCP off 3.30 mm`. The best single image of the thesis.
  - `hero/f-32-t3.2.png`: the end. All steel apart from the flange sphere and the ×50 tool segment on the grey stick;
    the label above `end`.
- `zoom/f-12-t1.2-before-after.png`, `zoom/f-14-t1.4-before-after.png`, `zoom/f-15-t1.5-before-after.png`: 2× crops
  of the arm. On the left, the second check's pink glass tints the forearm and wrists mauve. On the right, this build's
  skeleton, with the casting steel grey.
- `tab-error-0-t1.8.png`: the Error tab at 1.8 s (ruler 0.93 mm, TCP off 1.94 mm, wrist_1 −0.50°).
- `tab-q-0-t1.8.png`: q. Bold run on the pale target in all six strips, each title with `run − target ≤ …°` (wrist_2
  0.62°), the grey limit lines on shoulder_pan and wrist_3, and `bold = run, pale = target, grey = limit` in the first
  title.
- `tab-qd-0-t1.8.png`: qd, with gaps of 1.0–6.0°/s; wrist_2 spans ±224°/s (robot_msgs 3023fce). Same key.
- `tab-qdd-0-t1.8.png`: qdd. The run's wiggles about the target's trapezoids, gaps up to 159°/s², the grey limits at
  each strip's edge. Same key.
- `tab-qddd-0-t1.8.png`: qddd. The target's bang-bang jerk pulses (pale) under the run's encoder-difference noise. No
  limit line, so the key is `bold = run, pale = target`.
- `tab-cards-0-t1.8.png`: q / qd / qdd. V1's cards, each with the target's three lines pale and wide underneath; the key
  line names them.
- `tab-tcp-0-t1.8.png`: TCP. Position, orientation, speed and angular speed, the target pale under the run. All four
  titles are uncut, and position, speed and angular speed carry `bold = run, pale = target`.
- `plan-0-t1.8.png`: the plan scenario at 1.8 s. One steel arm, the tool path solid to the playhead, six tabs opening
  on q.
