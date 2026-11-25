# V1 · As built

**Thesis:** your pick exactly as it is on robot_msgs main (248f9f1): the URDF arm on the left half with start/end ghosts
and the tool path solid up to the playhead, your six tabs on the right (q · qd · qdd · qddd · q / qd / qdd · TCP).

- Grows from: R3 "Solo run dashboard" + R1's tabs (round 1, rerun-joint-trajectory-2026-11-24); the stock module itself.
- Decisions: one JointTrajectory per recording; strips titled "travel 130° · 38° to limit"; opens paused at t = 0 on q;
  a flange-to-tool stick so the tool point sits on the arm.
- Best when: a single trajectory (a plan, a dataset row) is being read, joint by joint.
- Loses when: the recording is a tracking run: the target is not on screen, so where the solution is off can't be seen.
- Keep in a splice: the strip titles (travel / to limit); start/end ghosts; the q / qd / qdd table + cards tab.
- Signature (already on main): `viz.rerun.save(path, traj, robot=urdf, tool=tcp, ghosts=True)` / `traj.show(robot=urdf)`.
- Rerun 0.40 limits: collision meshes only (no .dae visuals).
- Sizes: plan-dev-029.rrd 2129 KB, run-dev-029.rrd 2201 KB (robot_msgs 3023fce: the strip-range fix).

Stills:
- shots/v1/hero/f-*.png — the agent's run (p6s), 0 → 3.2 s, q tab.
- shots/v1/tab-qd-0-t1.8.png — qd tab at 1.8 s.
- shots/v1/tab-qdd-0-t1.8.png — qdd tab at 1.8 s.
- shots/v1/tab-qddd-0-t1.8.png — qddd tab at 1.8 s.
- shots/v1/tab-cards-0-t1.8.png — q / qd / qdd table + cards at 1.8 s.
- shots/v1/tab-tcp-0-t1.8.png — TCP tab at 1.8 s.
- shots/v1/plan-0-t1.8.png — the dataset plan scenario at 1.8 s.
