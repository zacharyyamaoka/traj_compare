# R1 — Stage + questions

**Thesis.** The stock JointTrajectory view is traj_compare's default "questions" layout grown up: the URDF arm on a
pinned stage on the left (the hero, 3/5 of the width), and four question tabs beside it — **Where are the joints?**
(angle, °), **How fast?** (°/s), **How hard?** (°/s²), **Where does the tool go?** (x/y/z and speed, mm). Every joint
plot shows that joint's limits; every joint keeps one colour on the stage, in the plots and in the table.

**Grows from.** `traj_compare.rerun_export._layout_questions` (Zach's Nov 11 pick: pinned stage + question tabs), its
`_stage_eye` framing and `_ts` linked-x plots; robot_msgs.viz.rerun's entity layout and `band`.

## What it looks like

| still | what it shows |
|---|---|
| `shots/r1/at-time/dev-029-1-t0.4.png`, `-2-t1.8.png`, `-3-t3.2.png` | dev-029 at 0.4 s / 1.8 s / the end: the arm, the tool's path so far (orange) over the whole path (grey), the playhead in every joint plot |
| `shots/r1/at-time/dev-003-1-t0.9.png`, `-2-t1.76.png` | dev-003 at 0.9 s / the end: the stick from the flange to the TCP (the URDF has no gripper) |
| `shots/r1/tabs/dev-029-how-fast-1-t1.8.png`, `dev-029-how-hard-…`, `dev-029-tool-…`, `dev-003-how-fast-1-t0.9.png` | the other three tabs (wrists at 99–100 % of 180 °/s; every joint at 99 % of 344 °/s²) |
| `shots/r1/dev-029-*.png`, `shots/r1/dev-003-*.png` | the contract's `shoot.cjs` stills: all land at +0.000 s (see Shoot below) |

## Decisions

1. **The stage is the hero (3 : 2, was 2 : 5 in "questions").** A lone trajectory has no runs to rank, so the arm,
   framed from the front-right by traj_compare's `_stage_eye` rule (link origins + tool path, base kept on screen), takes
   the room; an "At a glance" table under it gives each joint's range, limits, and peak speed / acceleration as % of limit.
2. **One plot per joint per question, each opening on its limits.** A 2-column grid; the joint's limits are dark lines
   with a faint red strip beyond them (robot_msgs' `band`), and the y-axis opens on limits + 12 % (zoom stays free). The
   plot title carries the one number: `elbow [°] · limits ±180`, `wrist 1 [°/s] · peak 99 % of 180`. Legends off: the
   title and the colour say which joint.
3. **The arm is colour-keyed to the plots.** Each link is tinted pale with the colour of the trajectory joint that drives
   it (Tableau 10, joint i = colour i), so "the pink link is the elbow plot" needs no legend. Joint labels in 3D were
   tried and dropped: the three wrist labels and the tool's sat on top of each other.
4. **The tool.** A given tool PoseTrajectory wins (it knows the TCP offset; its `header.frame_id` may be any URDF link);
   without one, the URDF's last link by numpy forward kinematics. Drawn as the whole path (grey), the path so far
   (orange, ≤ 600 rows so long trajectories stay small), the point with its axes, and a stick from the flange to the TCP
   (dev-003 without it read as a wrong frame: the TCP floated 145 mm off the wrist). Opens paused on the start pose.

## Best when / loses when

- **Best when** reviewing one planned trajectory: where the arm goes, which joint is near which limit, and at what instant
  — one scrub moves the arm, the trail and all six cursors together.
- **Loses when** comparing trajectories (one robot drawn; see Missing), on many-joint robots (a 46-motor bimanual is 46
  plots per tab), when a joint barely moves inside wide limits (dev-003 wrist 2: 3° inside ±360° is a flat line until you
  zoom), and when you want angle and speed side by side (they are on different tabs).

## Worth keeping in a splice

- `_log_limits` + `_bounds`: limit lines + red strip + the y-axis opening on the limits, any plot of any proposal.
- `Kinematics.driver` + the tint in `_log_robot`: links coloured by the joint that drives them.
- `_log_tool`: path / trail / point / axes / flange-to-TCP stick, all in the URDF root frame (`rr.CoordinateFrame`).
- `Kinematics`: forward kinematics from `rerun.urdf` joints alone (no Pinocchio), for framing and the FK tool fallback.
- `shoot_at_time.cjs`: stills at the asked times (below).

## Proposed robot_msgs signature

```python
# robot_msgs.viz.rerun — robot= and tool= join show / save / log for a JointTrajectory
traj.show(robot="ur5e.urdf", tool=tcp)                         # Msg.show(name=None, *, robot=None, tool=None)
viz.rerun.save("pick.rrd", target=traj, robot="ur5e.urdf", tool=tcp)
viz.rerun.log(traj, "target", recording=rec, robot="ur5e.urdf", tool=tcp, degrees=True)
# robot: a URDF path (later: a RobotDescription); tool: a PoseTrajectory in the URDF root frame or any link's frame
```

Here it is `save_joint_trajectory(traj, urdf, out, *, tool=None, name=None, application_id=...) -> Path` in `make.py`.
`_blueprint` would pick this stage + questions layout whenever a robot was logged.

Entity layout (robot_msgs', so `show(target=traj)` logged into the same recording lands in the same plots):
`/world/<name>/robot/<urdf>/…` (Rerun's own URDF loader, `rr.log_file_from_path`),
`/world/<name>/robot/joint_transforms/<joint>`, `/world/<name>/tcp/{path,trail,now,axes,mount}`,
`/{positions,velocities,accelerations}/<joint>/<name>` (°, °/s, °/s²; mm for a prismatic joint) with `…/limits` and
`…/{above,below}_limit` beside them, `/tcp/{x,y,z}_mm/<name>`, `/tcp/speed_mm_s/<name>`, `/notes/<name>`.

## Shoot

- The contract command, both files: exit 0, **0 ERROR lines** (the printed log is only `DEBUG wgpu_hal … Naga generated
  shader` lines: 66 for dev-029, 44 for dev-003). Its stills all show **+0.000 s**.
- **Round-wide: the 0.40 web viewer ignores the data URL's `#when=t@<s>`.** Tested on dev-003 at 0.9 s: paused → 0.000;
  no play state → playing (caught at 1.760, and at 1.200 in a rerun); `following` → 1.760; `playback_speed=0.001` → 0.0013 (so it starts from 0, not 0.9);
  a bare recording with no blueprint at all → 1.760; the fragment on the page URL instead → no effect. The peers' stills
  (r2, r4, r5) show the same: their t1.8 and end files are byte-identical in size.
- `r1/shoot_at_time.cjs` (shoot.cjs + one click on the time bar at t / duration, + an optional tab click) lands every
  still exactly: 0.400, 1.800, 3.200, 0.901, 1.760 s, **0 ERROR lines**. Those are the stills in `shots/r1/at-time/` and
  `shots/r1/tabs/`.

## Missing

- **Two robots in one recording** (target + real): `rr.log_file_from_path` has no `frame_prefix`, so a second URDF would
  share frame names; `UrdfTree(frame_prefix=…)` has one, but its `entity_path_prefix` is a single escaped segment in 0.40
  (`"world/target/robot"` became one part), so the robot would land at `/<name>/<urdf>/…`, outside `/world/`.
- **Many joints**: the grid has no grouping by part (traj_compare's `_per_part` would be the fix).
- **Visual meshes**: this URDF has collision meshes only; when visuals exist, the view hides the collision meshes by a
  contents rule — written, not exercised here. Primitives (box, cylinder) are not tinted.
- **Dark theme** not checked (the headless viewer renders light); the limit lines are dark grey.
- Mimic joints are ignored by the forward kinematics; on a branched tree the FK tool fallback picks one tip.
- The at-a-glance table has no colour swatches (Rerun's markdown renders no HTML).
