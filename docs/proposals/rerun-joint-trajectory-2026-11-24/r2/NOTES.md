# R2 — evo: one full-screen tab per analysis

**Thesis.** The stock JointTrajectory view is traj_compare's "evo" layout grown up: Rerun Tabs, each one full screen.
**Robot** opens first and is the hero: the URDF arm moving, framed, the tool's path. Each analysis is one click away:
**Joints** (all six q on one plot), **Speed** (qd), **Acceleration** (qdd), **Data** (the samples as a table).

**Grows from** `traj_compare.rerun_export._layout_evo`, Zach's Nov 11 pick (copied from `evo_ape --rerun`). It keeps
evo's full-screen tab per analysis, the trail drawn up to the playhead, linked plot x-axes (`_ts`), collapsed side
panels and a raw-data DataframeView. The series are robot_msgs' own `viz.rerun.log(traj, name, degrees=…)`, so the
entity layout is `/<field>/<joint>/<name>`. The camera's viewing side is `_stage_eye`'s.

## Run it

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r2/make.py

It writes `r2/workspace-dev-029.rrd` and `r2/workspace-dev-003.rrd`, both opening on the Robot tab, plus one
`r2/blueprints/<task>.<tab>.rbl` per tab. Each `.rbl` opens the same recording on that tab (load it after the `.rrd`).

## What it shows

| Tab | Content | Entities |
|---|---|---|
| Robot | The URDF arm on the clock, plus the tool's path: drawn so far (orange), still ahead (grey), now (yellow, with an RGB triad), and the start and end points. A thin grey stick runs from the end link to the TCP when the tool trajectory is offset from it (here 145 mm). | `/world/ur5e/**` (Rerun's URDF loader), `/world/ur5e/joint_transforms/<joint>`, `/world/target/tool/{trail,ahead,point,axes,ends,stick}` |
| Joints | All six q in degrees on one plot. Each line carries its joint's name and colour, and each joint's min/max limits are drawn as thin lines in the same colour. | `/positions/<joint>/target`, `/positions/<joint>/limits` |
| Speed | qd in °/s, against ±max_velocity | `/velocities/<joint>/{target,limits}` |
| Acceleration | qdd in °/s², against ±max_acceleration | `/accelerations/<joint>/{target,limits}` |
| Data | The time `t` and each joint's q in degrees, in chain order, auto-scrolled to the playhead | DataframeView of `/positions/<joint>/target` |

A colour means the same joint on every plot. The plots' x zoom is linked. The time panel starts collapsed and paused
at t = 0, so the recording opens on the start pose with the whole path ahead.

## Decisions (each one reversible)

1. **Each analysis gets the whole screen (evo), with the robot first.** The arm is never squeezed beside plots. The
   cost is that the arm and a plot are never on screen together (see "loses when").
2. **robot_msgs' series, restyled.** robot_msgs labels every line with the trajectory's name (`target`), which works
   for one plot per joint (target vs real) but makes six lines on one plot unreadable. `_style_series` overwrites
   the static `SeriesLines` with each joint's name and colour. The **limits sit beside the series as a sibling name,
   `/<field>/<joint>/limits`** (one entity with two instances, min and max, so each joint gets one legend entry).
   Any view rooted at `/positions` or at `/positions/<joint>` picks the limits up with no extra contents.
3. **The tool path is split per time row into trail and ahead**, capped at 400 rows. Earlier, one static full path
   under the trail z-fought with it and speckled the orange grey in the real viewer. The TCP stick makes the 145 mm
   TCP offset readable, where the URDF has no tool geometry.
4. **The camera is fitted from FK over the whole motion.** It uses every link origin at 60 samples plus every tool
   sample, takes their bounding sphere and fits it to Rerun's 55° field of view. `_stage_eye`'s middle-90 % box
   framed the 3.2 s tour small and cut the top off the arm on the 1.8 s A-to-B (first stills). The FK uses Rerun's own
   `UrdfJoint.compute_transform`, so there is no kinematics dependency, and the arm drawn and the frame are one model.
5. **Paused at t = 0, with the blueprint sent first** (`rec.save(path, default_blueprint=…)`). When the blueprint
   was sent after the data, playback ran one frame first and the recording opened at +0.1 s.

## Shoot results (the gate, `shoot.cjs`) and the stills

- **Every `shoot.cjs` run printed 0 `ERROR` lines and exited 0.** That is 2 Robot runs plus 8 tab runs, run one at a
  time. The debug log holds only `DEBUG wgpu_hal … Naga generated shader` lines. On some loads the viewer's update
  check fails with `HTTP 403 api.github.com/repos/rerun-io/rerun/releases/latest`, which is the viewer's own request.
- **Every still landed at the asked time** (time field checked on each still, and read back by the handle). The
  commands:
  - `--times 0.4,1.8,3.2` for dev-029 (0.400 / 1.800 / 3.200 s)
  - `--times 0.9,1.76` for dev-003 (0.900 / 1.760 s)
  - each other tab: one time (1.8 s / 0.9 s) plus `--tab <x>,50` (x = 106 Joints, 178 Speed, 268 Acceleration, 350
    Data)
- **`shoot.cjs` changed during my run** (20:27). The first four stills used its `--duration` scrub-bar click, and
  dev-003's read 0.901 s. The rest used the `window._handle.set_time_for_timeline` seek it took over from
  `r2/shoot_at.cjs`. I reshot the two 0.901 s stills with the handle version, so all are now exact.
- **The design opens paused on purpose** (decision 5); it is not a variant made for the stills. Both seek methods
  rely on it.
- **The end time is a number, not `end`.** On a paused blueprint, `end` with no seek stays at t = 0. dev-029's
  timeline ends at 3.20 s (321 samples, 0.00–3.20 s), so the end is 3.2, not 3.21.
- **Before either fix**, I measured `#when=` with a paused blueprint: `t@1.8s`, `t@+1.8s`, `t@1.800s`, `t@1800ms` and
  `time_selection=t@1.0s..2.0s` all stayed at +0.000 s. With a playing blueprint, headless playback drifts about 5×
  slow.
- **`r2/shoot_at.cjs`** is the lane helper the handle seek came from. Its stills are the `at-*` files, a cross-check
  of the same set. Each tab also has a blueprint, `r2/blueprints/<task>.<tab>.rbl`, which opens on that tab without a
  click.

Stills (all in `shots/r2/`):

- Robot tab: `dev-029-1-t0.4.png`, `dev-029-2-t1.8.png`, `dev-029-3-t3.2.png`, `dev-003-1-t0.9.png`, `dev-003-2-t1.76.png`
- Other tabs: `dev-029-{joints,speed,acceleration,data}-1-t1.8.png` and `dev-003-{joints,speed,acceleration,data}-1-t0.9.png`
- Cross-check from `shoot_at.cjs`: the same set with an `at-` prefix (the end stills are named `-tend`)

## Best when / loses when

- **Best when** the motion matters most and you dig into one quantity at a time: a full-width plot of six lines can
  be zoomed and hovered for exact values, and long or many-joint trajectories still have room. It is also the most
  direct "Open in Rerun" for a single planned trajectory.
- **Loses when** you need to read a joint's value *while* watching the arm. They are on different tabs, so scrubbing
  moves the arm and each plot's cursor, but only one is visible at a time (fr5 is partial). Six lines plus twelve
  limit lines on one plot tangle when joints move in the same band, and the ±360° limits squeeze the y-axis. It does
  not overlay target vs real: that wants per-joint plots, which traj_compare's evo "Joint error" tab already has.

## Parts worth keeping in a splice

- `_style_series`: per-joint names and colours on top of robot_msgs' series, without touching robot_msgs' paths.
- Limits as the sibling name `/<field>/<joint>/limits` (one two-instance entity per joint, so one legend entry each).
- The tool's trail/ahead split per time row, the TCP stick, and the labelled start/end points.
- The Data tab: a DataframeView with `ComponentColumnSelector(entity_path=…, component="Scalars:scalars")` (the
  `"/path:Component"` string form splits on one `:`, and 0.40's id has two), `entity_order` set to the chain order,
  and `auto_scroll=True`.
- `_eye`: the bounding sphere from FK, fitted to the field of view.
- `_end_link`, the FK tool fallback, and URDF-typed degrees (revolute/continuous → °; prismatic stays in m and the
  titles say so).
- `shoot_at.cjs`'s `window._handle` seek.

## Proposed robot_msgs signature

`robot=` takes a URDF path or a `rerun.urdf.UrdfTree`. `rerun.urdf` ships in `rerun-sdk` (already the
`robot-msgs[rerun]` extra), so robot_msgs gains no dependency:

```python
from robot_msgs.viz import rerun as viz

traj.show(robot="ur5e.urdf", tool=tcp)                         # opens the viewer on this layout
viz.save("move.rrd", traj, robot="ur5e.urdf", tool=tcp)        # the .rrd ("Open in Rerun")
viz.log(traj, "target", recording=rec, robot=tree, tool=tcp)   # composable into a bigger recording
viz.joint_trajectory_blueprint(traj, robot=tree, tab="Joints") # the tabs, for traj_compare to reuse
```

Without `robot=`, today's `_blueprint` is unchanged. With it, the JointTrajectory blueprint becomes these five tabs
(Speed and Acceleration only when the message has qd and qdd, as here). In this lane the function is
`make.save(path, traj, robot, *, tool=None, name="target", tab=None, application_id=…, blueprints=None)`. I checked
three cases: with a tool PoseTrajectory, without one (FK to `wrist_3_link`), and a bare JointTrajectory with no
qd, qdd or limits (tabs: Robot, Joints, Data).

## What's missing

- **Overlays (target + real arms)**: Rerun's URDF loader writes `/world/<urdf robot name>/…` and takes only a single
  path segment as prefix (`"world/target"` is escaped to one segment). A second arm therefore needs `frame_prefix`
  plus a renamed URDF, or chunk re-pathing through `UrdfTree.stream()`. It is not built.
- **The legend is sorted by entity path** (elbow, shoulder lift, shoulder pan, …), not chain order, and each joint
  shows twice (line + limit). Rerun 0.40 cannot order or filter legend entries.
- **The Data table prints 15–17 significant digits**; 0.40 has no number format control. Only q is in the table (no
  qd or qdd columns).
- **The arm is drawn from collision STLs in one grey**: 0.40 cannot load the `.dae` visuals. The 3D view switches to
  visuals by itself when a URDF has loadable ones (it excludes `collision_geometries`).
- No effort tab even when `traj.effort` exists, no derived qd/qdd when the message lacks them, and no highlight when
  a joint nears its limit.
- No numeric q readout on the Robot tab; it is one click away on Joints or Data.
- The arm's joint values follow the trajectory past the URDF's own limits (`clamp=False`: the data is the truth, and
  this UR5e trajectory goes beyond the fixture URDF's ±180°).
