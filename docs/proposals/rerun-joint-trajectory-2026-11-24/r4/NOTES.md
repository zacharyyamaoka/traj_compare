# R4 — Robot first, numbers at the cursor

**Thesis.** The 3D view *is* the viewer. The URDF arm fills about three quarters of the screen, framed by a camera worked out from the arm's own forward kinematics. The tool path is drawn twice:

- the whole path, faint and coloured by tool speed;
- a bright trail of only the last 0.5 s, data-ui trajectory3d's "decay" from Zach's Oct 28 ask, done natively in Rerun.

Five pale ghost arms sit at evenly spaced instants, and each ghost's tool point is labelled with its time, so one still shows the whole motion. The numbers live at the playhead:

- a readout of every joint (angle in degrees, a gauge of where it sits between its limits, speed in °/s);
- a % of range bar chart pinned at 0 to 100;
- a narrow strip at the bottom with three tabs: q [°] for all six joints on one plot, qd [°/s], and tool speed [mm/s].

Open it (it plays and loops on open):

```bash
/home/bam/traj_compare/.venv/bin/rerun /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/r4/workspace-dev-029.rrd
```

## Grows from

- **robot_msgs.viz.rerun.** The joint series come from `viz.log(traj, name, degrees=True)` itself, in the `/positions|velocities|accelerations/<joint>/<name>` layout, and are only restyled with one colour and readable name per joint. The tool follows the PoseTrajectory logger's `world/<name>/path` + frame pattern, as `world/tool/{path,trail,now,axes,stick,keyframes}`.
- **traj_compare rerun_export.** Framing grows from `_stage_eye` (the swept cloud of link origins plus the tool path). The visible-time-range trail is evo's `growing` range, cut to a 0.5 s window. Joint names are shortened as `_short` does (`shoulder_pan_joint` → `shoulder_pan`).
- **Nov 19 "Solo Run Dashboard".** One big spatial pane, a numbers document beside it, and plots that share the playhead. Here the 3D pane is the hero instead of the plots.
- **Rerun 0.40's own `rerun.urdf.UrdfTree`** loads the robot: no hand-written mesh loader.

## Decisions

1. **The decay trail is Rerun-native.** It is a per-entity `VisibleTimeRanges(cursor−0.5 s … cursor)` override on `/world/tool/trail`, which holds one 2-point segment per sample. The faint full path is a separate static entity.
   - Rerun cannot fade by age, so the trail is a hard 0.5 s window, not a gradient.
2. **Ghosts are extra `UrdfTree`s.** Each has its own `frame_prefix` (`ghost<k>/`). Its chunks are re-pathed under `/world/<robot>/ghosts/<k>/` with `Chunk.with_entity_path`, and its joints are posed by one static set of joint transforms. An identity transform hangs each ghost's root frame on the live arm's root, and every geometry gets one RGBA.
   - Measured: also sending the URDF's own static joint set makes the viewer log `ERROR re_tf … Two entities define the same child frame` (30 lines per load), so ghosts use `include_joint_transforms=False`.
3. **Numbers at the cursor are latest-at data, not a moving frame.**
   - The readout is one markdown `TextDocument` per sample.
   - The tool point, its triad and its speed label are temporal `Points3D` / `Arrows3D` in the URDF root frame.
   - The bar chart has a static 100 % bar behind each joint. That pins the axis (an autoscaled one jumped while scrubbing) and makes each bar a gauge.
   - Every tool entity declares `CoordinateFrame(<URDF root link>)`. Left in its implicit `tf#/world/tool` frame it was **not drawn at all** next to the URDF, which lives in named frames.
4. **It plays and loops on open** (robot first: the arm moves and its trail follows), so it does **not** open paused. In the real 0.40 web viewer a paused blueprint opened every `#when=` link at +0.000 s, and a playing one drifts after a seek. `save(..., playing=False)` builds the paused copy in `r4/paused/`, and the round's stills come from that copy.
   - Also measured: the blueprint must go in at `rec.save(path, default_blueprint=…)`. Sent after the data, the playhead pinned at the first chunk's time.

## Proof

- **Stills.** Shot from `r4/paused/` with `shoot.cjs` and `SHOOT_DEBUG=1`, one shooter at a time. **No `ERROR` lines.** The only console noise is the viewer's own `HTTP 403 api.github.com/repos/rerun-io/rerun/releases/latest`, a version check that is not this recording. The playhead landed exactly where asked:
  - `shots/r4/dev-029-1-t0.4.png` (0.400 s), `dev-029-2-t1.8.png` (1.800 s), `dev-029-3-tend.png` (3.200 s);
  - `dev-003-1-t0.9.png` (0.900 s), `dev-003-2-tend.png` (1.760 s);
  - `dev-029-tab-qd-1-t1.8.png`: the qd tab;
  - `playing-dev-029-1-tend.png`: the delivered, playing file, which lands wherever playback is.
- **Forward kinematics checked against the dataset.** The flange (`wrist_3_link`) from the numpy FK over the URDF, set against the dataset's own tool poses, gives a constant 144.6 mm tool offset along flange z (spread 0.5 mm) and identical orientation (|q·q'| − 1 ≤ 2e-16). The FK is therefore right, and so is the tool-is-in-the-URDF-root-frame assumption, for this data.
- **Also built:** `tool=None` (the flange from FK) and `ghosts=0`.

## Best when / loses when

- **Best when** the tool travels: tours, pick-and-place, anything where *where the tool went, how fast, and in what order* is the question (dev-029). One still shows the path, its speed and its order: the ghosts plus the time labels.
- **Loses when** the motion is mostly joint-space with little tool travel (dev-003: pan and wrist_3 turn about 60° and 100° with the arm near upright). The ghosts stack into one fog, the path is a short stub, and the per-joint story sits in the small bottom strip.
- **Also loses when** you want each joint's curve against its limits over time. There is no per-joint limit band in the strip (UR5e limits are ±360°, so drawn bands would flatten all six curves). Limits appear only as the gauges.
- The time-series legend covers the first ~0.3 s of the strip, and Rerun sorts it alphabetically, not in joint order.

## Worth keeping in a splice

- `_joint_values` + `_log_robot`: every movable URDF joint gets a transform, including mimic joints and joints the trajectory doesn't name (held at 0). Otherwise the frame chain breaks and the links below vanish.
- `_forward` (numpy FK from `UrdfTree`'s public joint properties) and `_eye` (framing from it). Nothing in either is specific to one arm.
- The decay trail (one `VisibleTimeRanges` override) and the speed-coloured faint path.
- The `CoordinateFrame(root)` rule for anything drawn next to a Rerun URDF.
- The fixed-axis gauge bar chart (the static 100 % bar).
- The ghosts via `frame_prefix` + `with_entity_path`, if a splice wants the whole motion in one still.
- `default_blueprint=` at save.

## Proposed robot_msgs signature

```python
viz.rerun.save(path, traj, robot="ur5e.urdf", tool=None, ghosts=5, decay_s=0.5)     # -> path
viz.rerun.log(traj, name, recording=rec, robot="ur5e.urdf", tool=None)              # composes into any recording
JointTrajectory.show(robot="ur5e.urdf", tool=pose_traj)                             # opens the viewer
```

`robot=` is the URDF path, today `r4/make.py`'s `save(path, traj, robot, tool=None, *, name, ghosts, playing)`. Without `robot=`, today's series-only view stays. With it, `log` adds the arm, the tool and the readout layers, and `_blueprint` adds the 3D stage and readout column.

## What's missing / found on the way

- **robot_msgs `_series` gives every column the same legend name** (`label or name`), so six joints on one plot all read "target". R4 restyles the static `SeriesLines` afterwards. robot_msgs should take a per-column legend, e.g. `legend="column"`.
- **A tool PoseTrajectory logged with `viz.log` collides with the joints.** Its series land at `/positions/{x,y,z}/<name>`, inside the JointTrajectory's `/positions` plot. R4 logs the tool's spatial parts itself and keeps its series out.
- **Entity layout.** Rerun's URDF loader writes `/world/<robot>/collision_geometries/mesh/<link>/<geom>` (prefix `world`). robot_msgs' `links()` writes `/world/<name>/robot/<link>`. These need reconciling before the pick lands in robot_msgs. Note that `entity_path_prefix` must be one segment: a `/` in it is escaped.
- **`viz._PATHS.pop(...)` touches a private.** It is needed because R4 sends its own blueprint, so robot_msgs needs a public "log without registering a dashboard" path.
- **Ghosts copy the mesh blobs once each.** They add about 1.5 MB to a 0.7 MB recording. `ghosts=0` drops them; asset de-duplication would be the real fix.
- **The tool PoseTrajectory is assumed to be in the URDF root frame.** Its `header.frame_id` is not resolved against the URDF.
- **Colours are tuned for the light theme the headless shooter renders.** The live arm (mid steel) and the pale ghosts were checked only there, not on Rerun's dark theme.
- **No tool/gripper geometry.** This collision URDF ends at the flange, so a thin "stick" from flange to tool point shows where the 144.6 mm TCP sits.
