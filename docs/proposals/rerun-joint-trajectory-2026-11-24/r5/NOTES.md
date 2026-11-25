# R5: robot_msgs' show(), grown into the arm over joint cards

**Thesis.** Make the smallest change to the stock viewer that fixes Zach's complaint, and make it work for any arm. Start
from what `robot_msgs.viz.rerun` already draws for a JointTrajectory and add three things:

- the URDF arm, framed, in a 3D strip across the top, with the tool path;
- one card per joint below it, each showing q / qd / qdd as % of that joint's own limits on a shared ±100 % axis;
- a readout of the raw degrees at the playhead.

The stock's per-field plots stay in tabs one click away, now in degrees.

**Grows from** `robot_msgs.viz.rerun`. It runs the stock logger with `degrees=`, uses the stock's `band()` for the
limit band and keeps the stock's `/<field>/<column>/<name>` entity layout. It also borrows from traj_compare's Rerun
export:

- `_stage_eye`: frame every link over the whole motion, not just the tool path;
- `_ts`: link the time zoom across plots with `TimeAxis(link="LinkToGlobal")`.

Before it, today's stock on the same input: `../shots/r5/stock-today-dev-029.png`. That still shows a grey arc in an
empty 3D view, nine radian panels, and the tool's x/y/z mixed into the "positions" tab.

## What you see

- **Top left: `ur5e · <name>`.** The URDF arm moves in it, loaded by Rerun 0.40's own `rerun.urdf` with joint
  transforms on `t`. It also shows:
  - the whole tool path (grey) and the path so far (orange);
  - the tool point now;
  - a dark stick from the flange to the tool point.
- **Top right: `at the playhead · degrees`.** A table with one row per joint: q, qd, qdd in degrees (mm for a
  prismatic joint), plus the worst "% of limit" and which quantity it is (`99 qdd`).
- **Below: one card per joint**, named `<joint> · q / qd / qdd, % of limit`.
  - q is blue and thick, qd is orange, qdd is thin grey.
  - A light green band marks ±100 %; its edges are the limits.
  - The y axis is ±125 % on every card.
  - The legend gives each quantity's 100 % in degrees: `q · ±360°`, `qd · ±180°/s`, `qdd · ±344°/s²`.
  - The grid is 3 × 2 for six joints. The column count comes from the joint count (1→1, 2→2, 3→3, 4→2×2, 6→3, 7→4,
    12→4, 46→8).
- **Tabs `positions °` / `velocities °/s` / `accelerations °/s²`.** The stock's per-joint plots, now in degrees, with
  the raw value in the hover.
- **Panels.** The blueprint and selection panels start collapsed, and the time panel is the slim scrub bar. The
  recording opens **playing and looping**.

## Decisions (each reversible)

1. **% of each joint's own limits, `[low, high] → [−100, +100]`.**
   - Asymmetric ranges work too: the limit lines are always ±100 %.
   - Velocity and acceleration are signed over their magnitude limit.
   - Limits come from `traj.limits` first, then the URDF's `<limit>`, then nowhere. A quantity with no limit leaves the
     card, and the card's name says so: `(qdd: no limit)`.
   - The axis widens the same on every card when a limit is broken, so a violation is never clipped. The fallback
     test shows shoulder_pan at 159 % of the collision URDF's ±180°, on a ±195 % axis.
2. **One series entity per card, with q / qd / qdd as its three instances** (`/limit_pct/<joint>/<name>`).
   - The legend reads q, qd, qdd in that order. Three separate entities sorted by path as qdd, q, qd.
   - It stays inside the stock layout: the field is `limit_pct`, the column is the joint. This mirrors how a
     Comparison sits under `error/`.
3. **Raw degrees go in a readout beside the arm, not in the hover.** Measured in the real viewer: a 0.40 plot hover
   shows only the plotted number, `+2.590s · q · ±360° 53.398…` (`../shots/r5/dev-029-hover-card.png`).
   - A number component on the same entity, such as `AnyValues`, gets drawn as a second line rather than shown in the
     hover.
   - So the degrees live in three places: the legend's 100 % scale, the readout at the playhead, and the degree tabs.
   - The readout sits in space the 3D strip leaves empty beside the arm anyway.
4. **The recording plays and loops on open, and the blueprint is written first** (`save(..., default_blueprint=)`).
   - On open, the moving arm is the first thing you see.
   - I tried a paused blueprint (see "Stills" below). It did not hold `shoot.cjs`'s `#when=` playhead, so pausing
     bought nothing.

Also decided:

- **Flange-to-tool stick.** The dataset's tool point sits 144.7 mm (±0.9 mm) out along wrist_3's z axis (its rotation
  matches FK exactly), and the URDF has no tool0 link. Without the stick, the orange point floats beside the wrist and
  looks like a frame bug. I proved it was not one: numpy FK points drawn over the meshes coincide.
- **Camera framing.** The camera is fitted to every link origin over the whole motion plus the tool path, with a
  7 %-of-extent radius per point standing in for link thickness. It looks from the front right, about 18° up.

## Best when / loses when

- **Best when:** any serial arm with limits in its JointLimits or URDF, and the question is "how hard does this push
  each joint". In dev-029 every joint runs bang-bang acceleration at 98.7 % and the wrists run at 99 % velocity; that
  reads in one glance, card after card.
- **Loses when:**
  - You want absolute angles on the plot itself: the cards are %, and degrees are in the readout and tabs.
  - A continuous joint has no position limit: its q leaves the card.
  - The arm has 20+ joints: the cards get small (a bimanual wants traj_compare's per-part grids).
  - You overlay target / sim / real: one robot, one trajectory.
  - You read the start of the motion: each card's legend covers roughly the first fifth of its time axis.

## Parts worth keeping in a splice

- `_percent` + `_legend`: the % normaliser with the 100 % scale in degrees in the legend.
- `_limits`: limits from the message, then the URDF, honestly marked "no limit".
- The three-instance series entity per card, for legend order and a single hover.
- `_readouts`: the playhead table in degrees.
- `_link_poses` + `_tool_link` + `_eye`: FK framing that works for any URDF, and the tool path when no tool
  PoseTrajectory is given.
- The flange-to-tool stick.
- The degree tabs, from the stock's `degrees=` driven by the URDF's revolute joints.
- `save(..., default_blueprint=)`: blueprint first.

## The function signature it proposes for robot_msgs (a diff to `robot_msgs.viz.rerun`)

```diff
-def recording(*messages: Msg, application_id: str = APPLICATION_ID, **named: Msg) -> rr.RecordingStream
+def recording(*messages: Msg, application_id: str = APPLICATION_ID,
+              robot: str | Path | None = None, tool: PoseTrajectory | None = None, **named: Msg) -> rr.RecordingStream
-def show(*messages: Msg, **named: Msg) -> rr.RecordingStream
+def show(*messages: Msg, robot: str | Path | None = None, tool: PoseTrajectory | None = None, **named: Msg) -> rr.RecordingStream
-def save(path: str, *messages: Msg, **named: Msg) -> str
+def save(path: str, *messages: Msg, robot: str | Path | None = None, tool: PoseTrajectory | None = None, **named: Msg) -> str
+
+def robot(traj: JointTrajectory, urdf: str | Path, name: str | None = None, *,
+          recording: rr.RecordingStream, tool: PoseTrajectory | None = None) -> None:
+    """The URDF arm driven by `traj` at /world/<robot>, the tool path at /world/<name>, the joint cards' series at
+    /limit_pct/<joint>/<name>, the playhead readout at /notes/<name>; `log(traj, degrees=<the URDF's revolute joints>)`."""
-def _blueprint(paths: list[str]) -> Any
+def _blueprint(paths: list[str], robot: Scene | None = None) -> Any   # with a robot: Tabs("arm + joints", *the field tabs)

 # robot_msgs/_core.py, robot_msgs/viewers.py: forward the robot to the Rerun viewer
-    def show(self, name: str | None = None, *, viewer: str = "rerun") -> Any
+    def show(self, name: str | None = None, *, viewer: str = "rerun", **options: Any) -> Any   # traj.show(robot=urdf)
-        _show=lambda module, msg, name: module.show(**{name: msg}),
+        _show=lambda module, msg, name, **options: module.show(**{name: msg}, **options),
```

The call sites:

- `traj.show(robot="ur5e.urdf")`
- `viz.rerun.save("pick.rrd", JointTrajectory=traj, robot=urdf, tool=tcp)`

`robot=` is a URDF path, so robot_msgs stays dependency-free: the `[rerun]` extra already brings `rerun.urdf`, which
parses it. Today's `links()` exists only because robot_msgs could not read a robot model. A deployment's robot
description can hand its URDF path in here.

## Shoot results

- **`shoot.cjs` with `SHOOT_DEBUG=1`, as the contract says, run on the final build:**
  - `workspace-dev-029.rrd --times 0.4,1.8,end`: **0 ERROR lines**. The console holds 66 `DEBUG wgpu_hal … Naga
    generated shader` lines and nothing else. Log: `../shots/r5/shoot-dev-029.log`.
  - `workspace-dev-003.rrd --times 0.9,end`: **0 ERROR lines** and 44 of the same DEBUG lines. Log:
    `../shots/r5/shoot-dev-003.log`.
  - Its stills (`dev-029-{1,2,3}-t*.png`, `dev-003-{1,2}-t*.png`) landed at +0.900, +0.800, +2.100, +0.800 and
    +0.900 s: wherever playback was when the page settled.
- **Why those stills miss the asked times.** In this viewer, `#when=t@<t>s` on the data URL did not set the playhead.
  I tested it four ways:
  - A paused blueprint opened at **+0.000 s every time**. That held for stock-only data with only a paused
    `TimePanel`, whether the blueprint went at the head or the tail of the file.
  - Four fragment forms all failed on a paused recording: `t@1.8s`, `t@+1.8s`, `t@1800ms`, `t@1800000000`.
  - Without pausing, the playhead depends on load time.

  So the stills at the asked times come from `r5/shoot_at.cjs`, a companion that leaves `shoot.cjs` untouched. It
  loads the recording, clicks pause, then clicks the scrubber. Every one landed: dev-029 at +0.400 / +1.805 / +3.200 s,
  dev-003 at +0.901 / +1.760 s. Its console had 0 ERROR lines. Run it one browser at a time: four runs in parallel on
  the software rasterizer missed the pause click.
- **Stills, all looked at, in `../shots/r5/`:**
  - `dev-029-at-0.4.png`, `dev-029-at-1.8.png`, `dev-029-at-end.png`, `dev-003-at-0.9.png`, `dev-003-at-end.png`: the
    proposal at the asked times.
  - `dev-029-hover-card.png`: the card hover, showing % and not degrees.
  - `dev-029-tab-positions-at-1.8.png`: the stock tab in degrees.
  - `fallback-3-joints-urdf-limits-at-1.8.png`: three joints, no JointLimits and no tool. The limits come from the URDF
    and the tool path from FK; the card names say `qdd: no limit`; shoulder_pan reaches 159 % of the URDF's ±180°.
  - `stock-today-dev-029.png`: before.
  - `dev-0xx-N-t*.png`: `shoot.cjs`'s own stills.
- **No servers left running.** Both scripts kill their own viewer.

## What's missing

- **Raw degrees in the card hover.** Rerun 0.40's plot tooltip prints only the plotted value. The readout and the
  legend scale stand in for it.
- **The `#when=` playhead with a paused blueprint.** A fix belongs in the round's `shoot.cjs` or in Rerun, not in this
  lane.
- **The legend box covers about the first 20 % of each card's time axis.** A 0.40 legend cannot be hidden per series or
  pushed outside the plot. One option: start each card's x range at −0.25 × duration so the legend sits over empty
  space. Not tried.
- **Limits disagree in the data.** The trajectory's JointLimits give shoulder_pan ±360°, while the collision URDF says
  ±180°, and dev-029 drives it to +321.9°. The cards follow the message, which is the default; the fallback still
  shows the URDF's view. Worth a look upstream.
- **Overlays.** No target / sim / real overlay and no ghost robot. `UrdfTree.from_file_path(frame_prefix=<name>/)`
  would allow one robot per name.
- **No tool-orientation triad.** The stock's `TransformAxes3D` at the tool would need a named frame per sample.
- **Trail orange equals qd orange.** That could suggest a link between the two that does not exist.
- **Grey collision meshes**, because Rerun 0.40 cannot load the .dae visuals.
- **Implementation shortcuts.**
  - `_link_poses` is my own numpy FK, used only for framing and the fallback tool path; Rerun draws the arm from its
    own joint transforms.
  - `make.py` reaches into the stock's private `_PATHS` register only to drop the paths its default blueprint would
    have used.
