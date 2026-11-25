# Five variants of Zach's Rerun pick (2026-11-24)

Zach, Daily Note Nov 24 (l.2940), on the first round's pick page: "I don't see this? I wanted 5 new variants of my pick
not the 5 old looks? please launch the report with the new things if you have built it". His pick, from the chat the
same evening: "for the joint trajectory viewer I like R3 … But Please add tabs Similar to R1 so that you can switch
between what information you are showing on the right hand side. One can be like q, qd, qdd, qddd, q/qd/qdd, TCP (has all
the cartesian info here) etc. the idea is almost to like split the page in half. we are always showing the 3d robot but
the on the right side of the page we get the option to basically like show what ever particualy information we want
there."

So every variant keeps HIS FRAME: the URDF arm in 3D on the left half, tabs on the right half. They differ inside it.
V1 is what is built (robot_msgs main 248f9f1, `viz.rerun.save(path, traj, robot=urdf, tool=tcp)`), and stays the
default until he picks. The dispatcher owns this file, `fixture.py`, `extract.py`, `film.cjs`, `criteria.json`, `data/`
and `v1/`; a lane writes only in its own `v<N>/` folder and `shots/v<N>/`.

## The two scenarios (fixture.py; build both, same names in every variant)

- `plan()` → the dataset tour `workspace-dev-029` alone (3.2 s, six UR5e joints, q/qd/qdd + JointLimits, the tool
  PoseTrajectory). What Open in Rerun shows for a dataset row. → `v<N>/plan-dev-029.rrd`
- `run("p6s")` → the Trajectory Tracking Agent's saved run of the same task: target JointTrajectory, solution
  JointTrajectory (joint encoders; qd/qdd by differences), target tool, solution tool, extras (`tool_error_mm` = the
  agent's own ruler per sample, `rms_mm` = 1.09 mm on this task, `tau_pct`, `qd_pct`, `label`). Errors are small: joints
  ≤ 0.62° (wrist 2), tool ≤ 2.1 mm (ruler; 3.6 mm at the dataset's 145 mm tool point). → `v<N>/run-dev-029.rrd`.
  The hero clip is this scenario. `run("p5s-pass3")` (the best, 0.039 mm) is there if a variant wants a second run.
- `URDF` = the UR5e collision URDF (official meshes). Rerun 0.40 can't load the .dae visuals.

## What each variant is (assigned: build THIS thesis, not another)

| | Name | Left half (3D) | Right half (tabs) | Plot style | Time | The agent's run |
|---|---|---|---|---|---|---|
| V1 | As built | arm, start/end ghosts, tool path solid to the playhead | q · qd · qdd · qddd · q/qd/qdd · TCP | full-span strips, limit lines, title = travel / to limit | opens paused at 0 | the solution alone |
| V2 | Target vs run | two arms: target as a translucent ghost moving with the playhead + the solution solid; both tool paths; an error magnifier (the solution's deviation drawn ×N, labelled) | Error first (tool error mm from the agent's ruler + joint error °), then q · qd · qdd · qddd · q/qd/qdd · TCP, each overlaying target (dashed/faint) and solution | target faint, solution bold, error shaded | opens paused at 0 | both, everywhere |
| V3 | Limit-lit | each link tinted live by its joint's worst % of limit (q/qd/qdd) at the playhead (green → amber ≥ 80 % → red ≥ 95 %), no ghosts | "% of limit" first (every joint, q/qd/qdd normalised, ±100 % band), then q · qd · qdd · qddd · q/qd/qdd · TCP with shaded limit bands | % axes and bands | opens AT the moment closest to a limit | solution lit; target as a faint line in the plots |
| V4 | By joint + events | keyframe ghosts at the run's events (start, peak speed, closest to limit, worst error, end), each labelled | an Events tab (a text log of those moments with their times) + one tab per JOINT (its q, qd, qdd, qddd stacked) + All joints + TCP | small multiples per joint, shared time axis | events marked; the log is the index | worst-error moment is an event; target per joint tab |
| V5 | Tool first | TCP triad at the playhead, tool path coloured by speed, a bright 0.5 s trail; framed on the tool | TCP first (x/y/z mm, roll/pitch/yaw °, speed), Tool error, then q · qd · qdd · qddd · q/qd/qdd | a following window (±1 s around the playhead) instead of the full span | the window follows the playhead | target and solution tool paths, error vectors ×N |

Each variant keeps his six tabs reachable (fr1). If Rerun 0.40 can't do a cell above, do the closest thing it can and
say so in NOTES.md (never fake it).

## Every variant must

- Be one function, in `v<N>/make.py`: `save(path, traj, *, robot, tool=None, target=None, target_tool=None, extras=None)`
  (a JointTrajectory + the URDF, optional target and tool), run for both scenarios. It may import robot_msgs.viz.rerun's
  helpers (`_RobotPlan`, `_urdf_copy`, `_log_robot`, `_robot_dashboard`, `_Strip`, …) but NEVER edit robot_msgs
  (gate g4); a variant's own code lives in its folder.
- Show the URDF arm moving on the left half and tabs on the right half (gate g1), angles in degrees (g3).
- Embed its blueprint, open PAUSED (`rrb.TimePanel(play_state="paused")`), one `application_id` per variant
  (`rerun_pick_v<N>`).
- Open with no ERROR / panic in the real Rerun 0.40 web viewer (g2): film it with
  `node /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/film.cjs v<N>/run-dev-029.rrd shots/v<N>/hero --every 0.1`
  (the hero, 33 frames, default tab), then stills of each tab at t = 1.8 s with `--times 1.8 --clicks "x,y" --prefix tab-<name>`
  (find a tab's pixel from a frame), and the plan scenario at 1.8 s (`--prefix plan`). LOOK at every frame you keep.
  The viewer's own "403" on load is not your recording's error.
- Use only the traj_compare venv: `/home/bam/traj_compare/.venv/bin/python` (rerun-sdk 0.40.0, robot_msgs, numpy, scipy).

## Proof (v<N>/NOTES.md)

Name, one-sentence thesis, 2–4 decisions, best when / loses when, two or three parts worth keeping in a splice, the
signature it would add to robot_msgs (additive), what Rerun 0.40 could not do, file sizes of both .rrd, and the list of
stills to show (file → what it shows). No commits (the dispatcher commits). No servers left running (film.cjs stops its
own). Never the desktop browser pane, never a native Rerun window.
