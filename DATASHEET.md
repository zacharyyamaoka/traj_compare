# DATASHEET — traj_compare

The outside view: what goes in, what comes out, what proves it works.

**One sentence:** target + N recorded situations in → one self-contained
static `report.html` out (joint/TCP/path-progress plot grids + interactive
3D path viewer, everything show/hide-able, A/B turn-key).

## Inputs

| Input | Type | Unit | Meaning | Failure mode |
| --- | --- | --- | --- | --- |
| `Situation.t` | `(N,)` float | s | strictly increasing sample times; `None` → declared-but-empty slot | `ValueError` if non-monotonic or arrays without a time base |
| `Situation.q` | `(N, DOF)` float | rad | joint positions (required with `t`) | `ValueError` on shape mismatch |
| `Situation.qd/qdd` | `(N, DOF)` or `None` | rad/s, rad/s² | omitted → `np.gradient` fallback, flagged "derived" in the report | — |
| `Situation.tau` | `(N, DOF)` or `None` | Nm | omitted → τ plots simply absent for that situation | — |
| `Situation.current` | `(N, DOF)` or `None` | A | motor current; offered wherever τ is (a "Motor current i" section, unit A, null-padded like every channel); the target may lack it and no Δ-to-target is drawn then | — |
| `Situation.poses` | `(N, 4, 4)` or `None` | m | precomputed TCP poses (alternative to `fk`) | `ValueError` on shape |
| `Situation.video` | path str | — | video file relative to the report dir; drives the synced Videos section | absent → no card |
| `Situation.group/group_title` | str | — | semantic group for crowded situation controls | omitted → shared Situations group |
| `Comparison.robot` | `RobotDisplay` or `None` | m | link meshes (float32 triangle soups) + `link_fk (N,DOF)→(N,L,4,4)`; every data-bearing situation gets a matching-color model, visible by default with a per-situation `Robot / URDF` toggle | `ValueError` on mismatched links |
| `Comparison.fk` | callable or `None` | — | `(N, DOF) → (N, 4, 4)`; `None` and no poses → cartesian sections omitted | `ValueError` if it returns a wrong shape |
| `Comparison.vec_dirs` | `[(label, (3,))]` | — | directions for signed Vec progress (default world X/Y/Z; pass the conveyor) | `ValueError` on zero vector |
| `Comparison.target` | `Situation` or `None` | — | the reference all error/percent channels use | no target → no error channels, pct uses own totals |
| `Comparison.overlays` | `[CameraOverlay]` | — | real camera video + selectable sim renders (paths relative to the report dir) stacked in a "Camera" section card with an opacity slider, Mix/Difference blend, and a 2 Hz Flicker; `t0_s` is the trajectory time at video time 0 (video position = t − t0) | `ValueError` on empty/duplicate sims or duplicate names; a missing/unloadable file greys the layer and prints its path |
| `Comparison.group/group_title/tab_title` | str | — | primary scenario group + compact secondary permutation label | omitted → one primary tab for this comparison |
| `Comparison.statistics` | `ReportTable` or `None` | — | display-ready domain statistics at the top of the page | omitted → automatic joint/TCP error table |
| `Comparison.tolerances` / `tcp_tolerances` | `robot_msgs.compare.Tolerances` or `None` | — | ROS 2 path/goal tolerances for the joints / the TCP frame | omitted → no verdict |
| `Comparison.estimate_latency` | bool | — | estimate each run's clock offset from the reference | `False` |
| `Comparison.goal_band` / `tcp_goal_band` | float or `None` | rad / m | settling band for goal / settling-time / overshoot | omitted → no goal statistics |
| `Comparison.error_axes` | `[(label, vector)]` or `None` | — | named unit axes the TCP position error is projected on | omitted → none |
| `Comparison.repeat_groups` | `{group: [situation names]}` | — | runs that repeat one motion: ISO 9283 AT / RT against the reference | empty → none |
| `summary/insights` | `ReportPage` or `None` | — | report-level metric cards, bars, tables, evidence, and recommendations | omitted → no corresponding report-level tab |

## Output

| Output | Type | Meaning |
| --- | --- | --- |
| `write_comparison_report(...)` | `Path` to `report.html` | one file, ~2 MB for two 6-DOF trajectories; JSON data + uPlot + three.js + viewer code all inlined; opens from disk with no network |

Report structure: one primary tab per semantic comparison group, with a
secondary permutation selector when a group contains multiple comparisons.
Every detailed page begins with an error-statistics table, followed by
grouped situation chips (empty situations greyed with their note), section
chips (Joint q/qd/qdd/τ/i,
Joint error, TCP pose, TCP error, Path progress, Camera, Videos, 3D paths), deg↔rad
toggle (deg default), synchronized x zoom with a Reset-zoom button, and a
shared **transport**: plot hover previews that instant in 3D; the scrubber
under the 3D canvas (step/play buttons) drives the cursor line on every
plot, time-truncated 3D drawing over a faint full-path ghost, the robot
model pose, and all videos in lockstep. 3D controls per situation: a
visibility eye + a full-word multi-select (Path line / Points / Pose frames
/ Z vectors / Arrows→target / Z rotation arcs / Robot / URDF when a model is
supplied). The model option is checked by default, inherits the situation
color, and can be disabled independently; a clickable view cube snaps axis
views. Optional Summary and Insights tabs use the same self-contained payload
and renderer.

## Open in Rerun (optional)

`write_comparison_report(..., rerun=True)` also writes `rerun/<comparison.name>.rrd` beside the report (one
recording per comparison, application id `traj_compare`, timeline `t` in seconds from the target's start, blueprint
embedded) and adds `comparisons[i].rerun = {rrd, sdk, command}` to the payload, which the viewer turns into the header
control. `write_rrd(comparison, path)` is the same writer on its own. Entities: `/world/<situation>/{robot/<link>,tcp}`,
`/position|velocity|torque/<joint>/<situation>`, `/error/joint/<joint>/<situation>` (target − run, SI rad, from the
analyze payload), `/error/tool/{position_mm,rotation_mrad,x_mm,y_mm,z_mm,lag_mm,cross_track_mm}/<situation>`,
`/vec/<label>/<situation>`, `/video/<situation>` (MP4), `/notes`.

**Pin:** `RERUN_SDK_VERSION = "0.40.0"`; the `rerun` extra is `rerun-sdk==0.40.0`. An `.rrd` needs a viewer at least as new
as its SDK, so every command is `uvx --from rerun-sdk==0.40.0 rerun <abs path>`.

**Button:** `python -m traj_compare.serve <dir> [--port 8767] [--host 127.0.0.1]` serves the directory (CORS +
`Access-Control-Allow-Private-Network` for app.rerun.io) and answers `POST /__rerun/open?rrd=<relative path>` by starting
that command on a `.rrd` inside the root (anything outside is refused, nothing spawned; cross-origin POSTs are refused).
From `file://` or a plain static server the same button copies the command. The payload also carries `reference_title`
(the `target` situation's title), which the viewer writes wherever it says "<reference> − run".

## Dependencies

Runtime: `numpy` and `robot-msgs` (numpy-only; every error signal and statistic comes from
`robot_msgs.compare`, error = target − run, since 2026-11-10). Vendored into the wheel: uPlot 1.6.30, three.js r160
(`src/traj_compare/assets/VENDORED.md`). Test extra: `pytest`, `scipy`
(rotation oracle). Optional `rerun` extra: `rerun-sdk==0.40.0` (only `rerun_export.py` imports it).

## Tests — `uv run --extra test python -m pytest -q tests` → **77 passed** (with `--extra rerun`; `test_rerun_export.py` skips without the SDK)

(`python -m`: the venv's `pytest` script can carry a stale shebang from before the package moved
under `mdp/agent/`. `test_playback.py` checks video frame gaps < 0.6 s and can trip when the machine
is saturated; base and current builds measured the same 0.24–0.42 s spread on 2026-11-10.)

| Test | Proves |
| --- | --- |
| `test_rotations.py` (7) | mat→quat/rpy match scipy (incl. near-π), geodesic angles, accumulation, unwrap/align |
| `test_analysis.py` (15) | arc-length/percent/vec identities on a constant-speed line; pure rotation accumulates RPY path; pct normalized by **target** total; exact error magnitudes for a known offset; null padding beyond a short run's span (no fabricated plateau); derived-channel flagging; empty situation + JSON round trip; joint-only comparisons; NaN → null; robot mesh base64 round-trip + per-link pose tracks; bounded display-only model-track sampling with endpoint preservation; RobotDisplay validation; video passthrough |
| `test_overlay.py` (8) | camera overlay carried into the payload; no overlays/current leaves the payload as before; overlay validation; current resampled onto the target grid with null padding; missing current is fine and never invented for the target; current shape validation; the report ships the Camera section / current channel / pref keys; `camera` accepted as a default section |
| `test_rerun_export.py` (8) | the .rrd verifies and prints through Rerun's own CLI with the standard entity layout and an embedded blueprint; its error values equal the HTML payload; `rerun=True` writes one .rrd per comparison with `{rrd, sdk, command}` and `rerun=False` writes none; `reference_title` names the minuend; `serve` sends CORS + private-network headers and launches the pinned viewer only on a file inside its root |
| `test_wave2_viewer.py` (8) | verdicts, latency, goal / settling, contour + lag time, errors along named axes and ISO 9283 aggregates equal what `robot_msgs.compare` returns for the same inputs; all off by default; the report shows the Verdict / Est. latency / Settling columns and the ISO 9283 card |
| `test_time_offset.py` (4) | `Situation.time_offset_s` reaches compare / check / goal / aggregate for that run: errors equal `robot_msgs.compare` at that offset, a 20 ms late run passes once told, the status cell says "shifted", NaN is refused |
| `test_wave2_rerun.py` (1) | the .rrd verifies and holds `/error/tool/contour_mm`, `lag_time_ms`, `/error/axes/<label>_mm`; the notes carry verdicts, latency, goal and aggregates |
| `test_report.py` (9) | report is self-contained, embeds both libs + data, groups comparison/situation navigation, derives error statistics, serializes Summary/Insights primitives, surfaces torque by default when requested, embeds each distinct robot link mesh once per report (`mesh_library`) however many pages pose it, preserves `</script>` safely, and rejects an empty list |

## Examples

| What you see | How to run |
| --- | --- |
| Camera overlay + motor current on a toy 1-DOF rack (synthetic mp4s via ffmpeg) | `cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare && uv run python examples/overlay_demo.py --out /tmp/overlay_demo` → `/tmp/overlay_demo/report.html` |
| Full-featured UR5e A/B report (conveyor track + joint reach, empty Real slot) | `cd ../traj_integration_tests && PYTHONPATH=src python -m traj_integration_tests ur-compare` → `out/ur_compare_<date>/report.html` |

## Boundaries

- A **viewer**, not a recorder: it does not execute trajectories, talk to
  hardware, or own any robot model — the caller brings arrays, kinematics, and
  a `RobotDisplay`. Standard robot-trajectory adapters are expected to supply
  that display whenever a robot description exists.
- Orientation display convention is extrinsic-xyz RPY (unwrapped, aligned to
  the target's branch); path rotation is accumulated axis-angle, so it is
  convention-free.
- Display channels are resampled onto the target's time grid for plotting
  (max 5000 points); error channels are computed on native grids first.
- The viewer may automate responsive layout inside caller-supplied semantic,
  unit, evidence, and conclusion bounds; it may not merge scenarios or
  invent conclusions.
