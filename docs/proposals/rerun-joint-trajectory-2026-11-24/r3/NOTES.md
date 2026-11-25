# R3 · Solo Run Dashboard, one screen

**Thesis.** "What does this whole motion look like, at a glance": everything on one screen, no tabs. The URDF arm
fills ~60 % of the screen, framed on the whole motion. Faint ghosts mark the start pose (blue) and the end pose
(orange). The tool path is drawn as two parts: solid up to the playhead, faint for the rest. Beside the arm is a
column of small plots, one per joint: q in degrees, the joint's limits as grey lines, and the joint's name, travel
and distance to its nearest limit in the plot's title. A last plot shows tool speed. Every plot has the time cursor.

**Grows from** the Nov 19 Rerun run-view pick, *Q2 Solo run dashboard*
(`/home/bam/traj_compare/docs/layout_proposals_2026-11-19/rerun/build_rerun_variants.py` `q2`). It keeps the no-tabs
container, the 3D view at the left with plots right (2:3 there, 3:2 here so the arm is the hero), one small plot per
joint with its x zoom linked to the others (`TimeAxis(link="LinkToGlobal")`), Solo Run's orange accent, collapsed side
panels and a paused time bar. The series come from robot_msgs' own logger (`robot_msgs.viz.rerun.log(traj, …,
degrees=…)`), so the plots read robot_msgs' entity layout unchanged.

## Run it

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r3/make.py
```

```bash
/home/bam/traj_compare/.venv/bin/rerun /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r3/workspace-dev-029.rrd
```

The build takes about 1 s and writes `workspace-dev-029.rrd` (1.4 MB) and `workspace-dev-003.rrd` (1.3 MB).

## Decisions

1. **One screen, and the arm is the hero.** The split is 3:2, the arm on the left. The camera is computed from the
   motion itself: every link origin at every sample plus the tool path, seen in profile (across their main horizontal
   direction, ~29° above the horizon, from the side nearer traj_compare's front-right default) at 2.35 radii.
   I tried and dropped a fixed front-right camera and one looking from the tool's side: both showed a UR5e end-on, so
   it looked foreshortened and filled the view.
2. **The start and end are always visible.** The ghosts are the same URDF loaded twice more, each joint posed
   statically, with a faint `albedo_factor`. The tool path is two polylines logged at every instant (latest-at): from
   the start to now in solid orange, and from now to the end in a faint opaque orange. The whole path is always on
   screen, and the travelled part grows as you scrub.
3. **The plots are small, so each title does the reading.** A title looks like
   `wrist_3_joint [°] · travel 309° · 14° to limit`; a joint beyond its limit says `PAST limit`. The y range is the
   motion, stretched to take in a limit only when that limit is within one motion span. Otherwise the UR5e's ±360°
   would flatten a 60° move to a line. The range is then snapped outward to round numbers so a ~90 px plot always gets
   tick labels. All joint lines are one ink colour, the limits are grey, and orange appears only on the tool: nothing
   reads as an alarm.
4. **It opens paused at the start, and play loops the motion.** The blueprint is written into the file before the data,
   with `TimePanel(play_state="paused", loop_mode="all")`. A blueprint sent last let the viewer play ~0.1 s first.

## Best when / loses when

- **Best when** you want to see a whole motion at once: where the tool goes, the pose it starts and ends in, which
  joints do the work, how close each one gets to its limit, and when the tool is fastest. Scrubbing moves the arm, the
  solid path and all seven cursors together.
- **Loses when** you need q̇/q̈ against their limits. They are logged (the stock series), but they are not on screen.
  It also loses when comparing trajectories: one `name` per recording, with no overlay design. On a robot with many
  joints, seven plots fit in 1000 px, but twelve would be cramped; nothing scrolls. On a 1-DOF rig the tool point can
  sit on the axis, so the speed plot is flat 0 (scratch test below).

## Parts worth keeping in a splice

- **The URDF under `/world/<name>/`, with its frames prefixed `<name>/`.** Rerun's own loader is moved there with
  `UrdfTree.stream().map(Chunk.with_entity_path)`, and one mount `Transform3D(parent_frame="tf#/world/<name>",
  child_frame=<name>/<root link>)` connects it to the scene. Any number of trajectories or ghosts can then share one
  recording without frame collisions.
- **Ghost arms:** `include_joint_transforms=False`, every joint logged as a static `compute_transform`, and a faint
  `Asset3D.from_fields(albedo_factor=…)`.
- **The travelled and remaining path** as two latest-at polylines per instant. It is capped at 400 instants × 256
  vertices, so long trajectories stay small, and it needs nothing from the blueprint.
- **Limit lines** at `/positions/<joint>/lower_limit|upper_limit`. They sit in the stock `<field>/<column>`, so even
  robot_msgs' stock blueprint puts them on the joint's plot. The message's `JointLimits` win; the URDF's limits are the
  fallback.
- **The titles** (travel and distance to the nearest limit) and the **snapped y ranges**.
- **Degrees decided by the URDF:** the joint type picks degrees for revolute and continuous joints and leaves
  prismatic joints in metres, through robot_msgs' existing `degrees=<names>`.

## Proposed robot_msgs signature

```python
# robot_msgs.viz.rerun — grown, not new: the JointTrajectory logger gains robot= / tool=
log(traj, name=None, *, recording, robot: str | Path | None = None, tool: PoseTrajectory | None = None)
save(path, traj, robot="ur5e.urdf", tool=tcp)    # -> .rrd with this dashboard embedded when robot= is given
traj.show(robot="ur5e.urdf", tool=tcp)
```

`tool` is the TCP's PoseTrajectory. Its `header.frame_id` must be a URDF link (default: the root link). Without it, the
path is the flange's, from forward kinematics on the URDF. `make.py` already has this split: `plan()` (pure: limits,
titles, ranges, FK, camera), `log()` and `blueprint()`.

## Proof

- **The stills of record:** shoot.cjs, run one at a time, using the contract's commands. All five landed exactly where
  asked: `playhead 0.400 / 1.800 / 3.200 s` for dev-029 and `0.900 / 1.760 s` for dev-003. **ERROR lines: 0.** The
  only console lines are the viewer's own GitHub update check (HTTP 403).
  - `/home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/shots/r3/dev-029-1-t0.4.png`
  - `/home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/shots/r3/dev-029-2-t1.8.png`
  - `/home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/shots/r3/dev-029-3-tend.png`
  - `/home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/shots/r3/dev-003-1-t0.9.png`
  - `/home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/shots/r3/dev-003-2-tend.png`
- **What each still shows** (I looked at every one): the arm moves off the blue start ghost (0.4 s). The solid path
  ends at the tool and the faint path runs on to `end` (1.8 s). At the last sample the arm sits inside the orange end
  ghost and the whole path is solid. Every plot's cursor sits at the same instant as the 3D view.
- **The data checks out against the URDF.** The dataset's TCP is in this URDF's root frame: the flange orientation from
  forward kinematics matches `tool_rot` to 1e-8, and the TCP sits a constant ~145 mm out along the flange's z.
- **It generalises (scratch test, not delivered).** I ran the same `save()` on a different robot, robotparts'
  `sysid-1dof-sim/robot/rig.urdf`: visual STL meshes with a scale, one continuous joint, no limits, no tool. I also ran
  it on the UR5e with no `tool` and no `JointLimits`: the flange path and the URDF's ±180° limits apply, so the
  shoulder pan reads `27° PAST limit`. Both open with 0 ERROR lines.

## Found on the way (worth knowing for every proposal)

- **`UrdfTree.from_file_path(entity_path_prefix=…)` takes one path segment.** Slashes are escaped, so
  `"world/x/robot"` became the single segment `/world\/x\/robot`. That is why this proposal moves the chunks instead.
- **The URDF's root frame is not connected to a `Spatial3DView(origin="/")` on its own.** The robot did not draw until
  the mount transform was added.
- **Ghosts must leave out the loader's `tf_static`.** It already holds every revolute joint at zero, and a second
  static transform for the same child frame is an `ERROR re_tf … Two entities define the same child frame`.
- **A view-wide `time_ranges` range-queries the static meshes.** That dropped the ghosts' `albedo_factor`: both ghosts
  drew solid white.
- **A line colour with alpha draws darker (brown), not fainter.** The faint path uses an opaque light colour instead.
- **The `#when=` link fragment never moved the playhead,** paused or not. The dispatcher has since fixed shoot.cjs (it
  now seeks through the viewer's `_handle`). The stills above use the fixed shoot.cjs.

## What's missing

- **No overlay of several trajectories** (target vs real), though the frame prefixes already allow several robots in
  one recording.
- **q̇/q̈ and velocity limits are not on screen.**
- **No joint-speed fallback for a tool point on the axis.** A 1-DOF rig needs one.
- **Tick labels fade when dense.** On 300°-span joints the in-between tick labels are faint at seven plots per column
  (egui decides this).
- **The camera is a heuristic.** On the short A-to-B (dev-003) the arm fills the frame and the 0.27 m path is small.
- **Collision meshes only:** Rerun 0.40 cannot load the UR .dae visuals.
- **The URDF's own limits (±180°) disagree with the trajectory's (±360°).** The message wins.
- **Fragile hooks:** `stock._PATHS.pop` reaches into a private name, and `UrdfTree.stream()` is marked experimental in
  0.40.
- **Payload:** three URDF copies (arm plus two ghosts) triple the mesh bytes: ~1.1 MB of the 1.4 MB file here.
