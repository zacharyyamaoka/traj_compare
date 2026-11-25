# How a JointTrajectory looks in Rerun — five proposals (2026-11-24)

Zach, Daily Note Nov 24 (~l.1990): "I love how I can view these trajectories in rerun. One thing I don't like right
now is how this trajectory looks in rerun [today: a grey tool-path arc in an empty 3D view + nine separate per-joint
q/qd/qdd plot panels] … this should basically be the stock trajectory rerun viewer... 100% there should be a urdf
showing. Please show 5 different proposals for how the rerun Joint trajectory can look like. Please find the previous
examples we have done and base yours off of that." Later the same day: "For all of the robotmsgs I would like to have a
bunch of Rerun viewers. For like common use cases and messages." The pick becomes the stock "Open in Rerun" for every
trajectory: a robot_msgs `JointTrajectory` in, the URDF from the deployment's robot description.

The dispatcher owns this file, `extract.py`, `shoot.cjs`, `criteria.json` and `data/`; a lane writes only in its own
`r<N>/` folder.

## Inputs (data/, read-only)

- `workspace-dev-029.npz` (a 3.5 s multi-waypoint tour, the trajectory that adds the most coverage) and
  `workspace-dev-003.npz` (a 1.8 s A-to-B): `t`, `names` (the six UR5e joints), `q` rad, `qd`, `qdd`, `tool_xyz` (m,
  base frame), `tool_rot` (3×3), `lo`/`hi`/`vmax`/`amax` (the UR5e's JointLimits). `trajectory.json` says what they are.
  Build a robot_msgs `JointTrajectory` from them (`JointTrajectory(t=…, joint_names=…, positions=…, velocities=…,
  accelerations=…, limits=JointLimits(…))`): the proposal's entry point takes a JointTrajectory, nothing else.
- `robot/ur5e_collision.urdf` + `robot/meshes/*.stl`: the UR5e (official ur_description collision meshes, LICENSE
  beside them; Rerun 0.40 cannot load the .dae visuals). Joint names match the trajectory's.

## The previous examples to build on (read them)

- traj_compare's Rerun export: `/home/bam/traj_compare/src/traj_compare/rerun_export.py` — the "questions" layout (a
  pinned 3D stage on the left, question tabs beside it; the default) and "evo" (one full-screen tab per analysis; Zach's
  Nov 11 pick), `LAYOUTS`, `RobotDisplay` / `_robot_links`, robot_msgs' logger for joint series.
- The Nov 19 Rerun run-view round: `/home/bam/bam_ws/reports/media/traj-compare-layouts-2026-11-19/rerun/` (q1–q5
  .rrd + blueprints + shots; "Solo Run Dashboard" was the pick) and its builder `/home/bam/traj_compare/docs/rerun_layouts/`.
- The stock: `/home/bam/robot_msgs/src/robot_msgs/viz/rerun.py` — `.show()` / `save()` / `log()` for every type,
  `_series` (JointTrajectory → /<field>/<column>/<name>), `_blueprint`, `links()`. The pick is grown INTO this module
  (robot_msgs is the API, "one stock viewer per data type, grown, never a new one"), so stay in its entity layout.
- Rerun 0.40's URDF support: `rerun.urdf.UrdfTree.from_file_path(path)`, `.log_urdf_to_recording(recording=)`, then per
  joint `rec.send_columns(f"/joint_transforms/{name}", indexes=[rr.TimeColumn("t", duration=t)],
  columns=tree.get_joint_by_name(name).compute_transform_columns(q[:, j].tolist(), clamp=False))` — proven in the
  dispatcher's probe (the arm moves along the trajectory in the web viewer).

## Every proposal must

- Show the URDF robot moving with the trajectory, in a 3D view framed on the arm (set the camera: `EyeControls3D`).
- Show joint values in degrees (Zach's rule: angles shown to him in degrees; data stays SI).
- Embed its blueprint (`rec.send_blueprint(...)` or the `default_blueprint=` of `rr.save`), one `application_id` per proposal.
- Be one function from a robot_msgs JointTrajectory (+ the URDF path, + an optional tool PoseTrajectory) to a `.rrd`,
  in `r<N>/make.py`, run for both trajectories → `r<N>/workspace-dev-029.rrd`, `r<N>/workspace-dev-003.rrd`.
- Open with no errors in the real Rerun 0.40 web viewer: shoot with
  `SHOOT_DEBUG=1 node /home/bam/traj_compare/docs/proposals/rerun-joint-trajectory-2026-11-24/shoot.cjs r<N>/workspace-dev-029.rrd shots/r<N>/dev-029 --times 0.4,1.8,end`
  (and `--times 0.9,end` for dev-003), and no `ERROR` line in the printed log. A blueprint that starts playing moves the
  playhead during the load: set `rrb.TimePanel(play_state="paused")` if you want the stills at the asked times, or say why
  not. LOOK at every still.
- Use only the traj_compare venv (`/home/bam/traj_compare/.venv/bin/python`: rerun-sdk 0.40.0, robot_msgs, numpy).

## Proof

`r<N>/NOTES.md`: name, thesis, which previous example it grows from, 2–4 decisions, best when / loses when, parts worth
keeping in a splice, the function signature it proposes for robot_msgs (e.g. `JointTrajectory.show(robot=…)` /
`viz.rerun.save(path, traj, robot=urdf)`), what's missing. Stills in `shots/r<N>/`. No commits (the dispatcher commits).
No servers left running (shoot.cjs stops its own). Never the desktop browser pane, never a native Rerun window.
