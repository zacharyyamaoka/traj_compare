"""What the site says, as data: sources, prior art, metric and field tables, and page fragments.

The prose lives in templates/; this module holds everything tabular or generated, and the lists of
names `build_site.check_claims` verifies against the code before a page is written.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

# ── names the docs state; the build fails if the code stops saying them ────

CLAIMED_EXPORTS = [
    "compare", "Comparison", "ErrorStats", "error_stats", "align", "check", "ToleranceMonitor", "Tolerances",
    "JointTolerance", "PoseTolerance", "Outcome", "Violation", "aggregate", "Aggregate", "estimate_time_offset",
    "TimeOffsetEstimate", "goal", "GoalStats", "relative_error", "frechet", "contour_errors", "track_errors",
    "TIME_BASE_CHANNELS", "SUCCESSFUL", "PATH_TOLERANCE_VIOLATED", "GOAL_TOLERANCE_VIOLATED",
]
CLAIMED_FIELDS = {
    "comparison": ["error", "metrics", "time_offset_s", "dropped", "coverage"],
    "tolerances": ["path", "goal", "goal_time_tolerance", "stopped_velocity_tolerance"],
    "joint_tolerance": ["name", "position", "velocity", "acceleration"],
    "outcome": ["error_code", "error_string", "violations", "margins", "goal_time", "unchecked"],
    "goal_stats": ["final_error", "settling_time", "overshoot", "overshoot_percent", "band", "samples_after_end"],
    "viewer_comparison": [
        "target", "situations", "fk", "robot", "vec_dirs", "tcp_frame", "overlays", "statistics",
        "tolerances", "tcp_tolerances", "estimate_latency", "goal_band", "tcp_goal_band", "error_axes",
        "repeat_groups",
    ],
}
CLAIMED_SOURCE_STRINGS = {
    "src/robot_msgs/compare/metrics.py": [
        '_JOINT_FIELDS = ("positions", "velocities", "accelerations", "effort")',
        'for name in ("lag", "cross_track", "contour", "lag_time")',
        'metrics["linear_velocity"]',
        'metrics["angular_velocity"]',
        '(("rx", 0), ("ry", 1), ("rz", 2))',
        'f"channels/{name}"',
    ],
    "src/robot_msgs/compare/difference.py": [
        'TIME_BASE_CHANNELS = ("speed_scaling", "segment_index")',
        'TIME_BASE_PREFIX = "time_base/"',
        "quat_multiply(reference_at.orientations, quat_conjugate(measured.orientations))",
    ],
    "src/robot_msgs/compare/_dispatch.py": ["contour_window_s: float = 0.25"],
    "src/robot_msgs/compare/tolerances.py": ["stopped_velocity_tolerance: float = 0.01", "goal_time_tolerance: float = 0.0"],
    "src/robot_msgs/compare/timing.py": ["max_offset_s: float = 0.25", "1e-6"],
    "src/robot_msgs/compare/aggregate.py": ["ddof=1", "distances.mean(axis=0) + 3.0 * distances.std(axis=0, ddof=1)"],
    "src/robot_msgs/compare/error_stats.py": ["np.percentile(magnitude, 95.0)", "np.std(finite)"],
    "traj_compare/src/traj_compare/serve.py": ["DEFAULT_PORT = 8767", 'OPEN_PATH = "/__rerun/open"'],
    "traj_compare/src/traj_compare/rerun_export.py": ['APPLICATION_ID = "traj_compare"', 'TIMELINE = "t"',
                                                     "default_blueprint="],
}

# Media record_hero.py writes into <out>/media; anything missing renders as "media pending".
MEDIA_FILES = [
    "hero.mp4", "hero.gif", "hero-poster.png", "ur5e-conveyor.png", "planar-2r.png",
    "report-overview.png", "report-3d.png", "report-tcp-error.png", "report-iso.png",
    "report-sim-to-real.png", "report-videos.png", "rerun-viewer.png",
]


def display_path(path: Path | str) -> str:
    text = str(path)
    home = str(Path.home())
    return "~" + text[len(home):] if text.startswith(home + "/") else text


# ── sources (public links only; the site may become public) ─────────────────

SOURCES = {
    # SLAM / odometry evaluation
    "evo": {"title": "evo — Python package for the evaluation of odometry and SLAM (MichaelGrupp/evo)",
            "url": "https://github.com/MichaelGrupp/evo", "where": "metrics.py, sync.py, result.py; GPL-3.0"},
    "rpg": {"title": "rpg_trajectory_evaluation (uzh-rpg)", "url": "https://github.com/uzh-rpg/rpg_trajectory_evaluation"},
    "zhang18": {"title": "Zhang & Scaramuzza, “A Tutorial on Quantitative Trajectory Evaluation for Visual(-Inertial) "
                         "Odometry”, IROS 2018", "url": "https://rpg.ifi.uzh.ch/docs/IROS18_Zhang.pdf"},
    "tum": {"title": "TUM RGB-D benchmark tools (Sturm et al.)", "url": "https://cvg.cit.tum.de/data/datasets/rgbd-dataset/tools"},
    "kitti": {"title": "KITTI odometry evaluation", "url": "https://www.cvlibs.net/datasets/kitti/eval_odometry.php"},
    "trajectopy": {"title": "trajectopy (gereon-t)", "url": "https://github.com/gereon-t/trajectopy", "where": "GPL-3.0"},
    "trajectopy_ate": {"title": "trajectopy ATE result documentation",
                       "url": "https://gereon-t.github.io/trajectopy/api/results/ate_result/"},
    "evalio": {"title": "evalio stats reference", "url": "https://contagon.github.io/evalio/stable/ref/stats/"},
    # robot controllers
    "jtc_state": {"title": "control_msgs JointTrajectoryControllerState.msg",
                  "url": "https://raw.githubusercontent.com/ros-controls/control_msgs/master/control_msgs/msg/JointTrajectoryControllerState.msg"},
    "fjt_action": {"title": "control_msgs FollowJointTrajectory.action",
                   "url": "https://raw.githubusercontent.com/ros-controls/control_msgs/master/control_msgs/action/FollowJointTrajectory.action"},
    "joint_tolerance": {"title": "control_msgs JointTolerance.msg",
                        "url": "https://raw.githubusercontent.com/ros-controls/control_msgs/master/control_msgs/msg/JointTolerance.msg"},
    "jtc_docs": {"title": "ros2_controllers joint_trajectory_controller — user documentation",
                 "url": "https://control.ros.org/rolling/doc/ros2_controllers/joint_trajectory_controller/doc/userdoc.html"},
    "jtc_params": {"title": "ros2_controllers joint_trajectory_controller — parameters",
                   "url": "https://control.ros.org/rolling/doc/ros2_controllers/joint_trajectory_controller/doc/parameters.html",
                   "where": "constraints.goal_time default 10.0; 0 = no grace period, negative = wait indefinitely (re-read 2026-11-10)"},
    "jtc_cpp": {"title": "joint_trajectory_controller.cpp (error = desired − current)",
                "url": "https://raw.githubusercontent.com/ros-controls/ros2_controllers/master/joint_trajectory_controller/src/joint_trajectory_controller.cpp"},
    "moveit": {"title": "MoveIt — controller configuration (trajectory execution manager)",
               "url": "https://moveit.picknik.ai/main/doc/examples/controller_configuration/controller_configuration_tutorial.html"},
    "control_msgs_changelog": {"title": "control_msgs CHANGELOG",
                               "url": "https://raw.githubusercontent.com/ros-controls/control_msgs/master/control_msgs/CHANGELOG.rst"},
    # industrial arms and machine tools
    "iso_hexagon": {"title": "Hexagon, ISO 9283 basics (secondary summary)",
                    "url": "https://documentation-be.hexagon.com/bundle/04_ISO9283_Basics/raw/resource/enus/04_ISO9283_Basics.pdf"},
    "iso_sample": {"title": "ISO 9283:1998 sample pages",
                   "url": "https://cdn.standards.iteh.ai/samples/16937/a90ecd3949ee4de7b15f9624bc09cc42/ISO-9283-1990.pdf"},
    "robodk": {"title": "RoboDK — ISO 9283 path accuracy", "url": "https://robodk.com/doc/en/Robot-Validation-ISO9283-Path-Accuracy.html"},
    "cnc_fiveaxis": {"title": "Modeling and control of contouring errors for five-axis machine tools",
                     "url": "https://typeset.io/pdf/modeling-and-control-of-contouring-errors-for-five-axis-37fnq206ec.pdf"},
    "cnc_thesis": {"title": "Contour error vs tracking error (NYCU thesis)",
                   "url": "https://ir.lib.nycu.edu.tw/bitstream/11536/28949/1/000174454200005.pdf"},
    # shape, driving, controls, signals
    "eiter": {"title": "Eiter & Mannila, “Computing discrete Fréchet distance”, TU Wien technical report, 1994"},
    "shapely": {"title": "shapely.frechet_distance", "url": "https://shapely.readthedocs.io/en/stable/reference/shapely.frechet_distance.html"},
    "similaritymeasures": {"title": "similaritymeasures (cjekel)", "url": "https://github.com/cjekel/similarity_measures"},
    "dtaidistance": {"title": "dtaidistance — dynamic time warping", "url": "https://dtaidistance.readthedocs.io/en/latest/usage/dtw.html"},
    "argoverse": {"title": "Argoverse 2 motion-forecasting metrics",
                  "url": "https://raw.githubusercontent.com/argoverse/av2-api/main/src/av2/datasets/motion_forecasting/eval/metrics.py"},
    "waymo": {"title": "Waymo Open Dataset motion metrics proto",
              "url": "https://raw.githubusercontent.com/waymo-research/waymo-open-dataset/master/src/waymo_open_dataset/protos/motion_metrics.proto"},
    "nuplan": {"title": "nuPlan metrics description", "url": "https://nuplan-devkit.readthedocs.io/en/latest/metrics_description.html"},
    "stepinfo": {"title": "MATLAB stepinfo", "url": "https://www.mathworks.com/help/control/ref/dynamicsystem.stepinfo.html"},
    "python_control": {"title": "python-control step_info", "url": "https://python-control.readthedocs.io/en/latest/generated/control.step_info.html"},
    "sproclib": {"title": "sproclib control utilities (IAE / ISE / ITAE)",
                 "url": "https://sproclib.readthedocs.io/en/latest/_modules/sproclib/utilities/control_utils.html"},
    "scipy_lags": {"title": "scipy.signal.correlation_lags", "url": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlation_lags.html"},
    "matlab_sdi": {"title": "MATLAB Simulation Data Inspector — how it compares time series",
                   "url": "https://www.mathworks.com/help/simulink/ug/how-the-simulation-data-inspector-tool-compares-time-series-data.html"},
    # viewers and data
    "rerun_dataframes": {"title": "Rerun — dataframe reference", "url": "https://rerun.io/docs/reference/dataframes"},
    "rerun_tsv": {"title": "Rerun — TimeSeriesView", "url": "https://rerun.io/docs/reference/types/views/time_series_view"},
    "rerun_rrd": {"title": "Rerun — the .rrd format and version compatibility",
                  "url": "https://github.com/rerun-io/rerun/blob/main/docs/content/concepts/logging-and-ingestion/rrd-format.md"},
    "rerun_embed": {"title": "Rerun — embed the web viewer (viewer and SDK versions must match)",
                    "url": "https://rerun.io/docs/howto/integrations/embed-web"},
    "rerun_release": {"title": "Rerun 0.40.0 release", "url": "https://github.com/rerun-io/rerun/releases/tag/0.40.0"},
    "rerun_video": {"title": "Rerun — video (MP4: H.264 / AV1 through WebCodecs)",
                    "url": "https://github.com/rerun-io/rerun/blob/main/docs/content/concepts/logging-and-ingestion/video.md"},
    "rerun_sinks": {"title": "Rerun SDK sinks.py (save with default_blueprint)",
                    "url": "https://github.com/rerun-io/rerun/blob/main/rerun_py/rerun_sdk/rerun/sinks.py"},
    "plotjuggler": {"title": "PlotJuggler", "url": "https://github.com/facontidavide/PlotJuggler"},
    "foxglove": {"title": "Foxglove — plot panel", "url": "https://docs.foxglove.dev/docs/visualization/panels/plot"},
    "lerobot": {"title": "LeRobot dataset v3", "url": "https://huggingface.co/docs/lerobot/lerobot-dataset-v3"},
    # the code itself
    "code_design": {"title": "robot_msgs docs/DESIGN.md — “Comparing trajectories”", "where": "robot_msgs repository"},
    "code_align": {"title": "robot_msgs/compare/align.py", "where": "the clock rules: one clock, no extrapolation"},
    "code_difference": {"title": "robot_msgs/compare/difference.py", "where": "error = reference − measured; lag, cross-track, contour"},
    "code_metrics": {"title": "robot_msgs/compare/metrics.py and error_stats.py", "where": "metric names and ErrorStats"},
    "code_tolerances": {"title": "robot_msgs/compare/tolerances.py and _phases.py", "where": "check, ToleranceMonitor, one shared per-sample rule"},
    "code_aggregate": {"title": "robot_msgs/compare/aggregate.py", "where": "ISO 9283 barycentre, RP = l̄ + 3·S_l"},
    "code_timing": {"title": "robot_msgs/compare/timing.py", "where": "estimate_time_offset"},
    "code_goal": {"title": "robot_msgs/compare/goal.py, relative.py, frechet.py", "where": "goal, drift, Fréchet"},
    "code_oracles": {"title": "robot_msgs commit 3e14b8b (2026-11-10)",
                     "where": "records relative_error == evo RPE (all_pairs) to 1e-15 and frechet == shapely (2D) / "
                              "similaritymeasures (3D); run once, not part of the committed test suite"},
    "code_viewer": {"title": "traj_compare README, DATASHEET, report.py, rerun_export.py, serve.py",
                    "where": "the HTML report, the .rrd projection and the Open in Rerun launcher"},
    "code_wave2_test": {"title": "traj_compare tests/test_wave2_viewer.py",
                        "where": "the viewer's verdict / latency / goal / ISO numbers equal robot_msgs.compare's"},
}

# ── prior art: what we copied, what we deliberately do not ──────────────────

PRIOR_ART = [
    ("SLAM and odometry evaluation", "best at bookkeeping", [
        ("evo", ["evo"],
         "The statistic set (rmse → <code>rms</code>, mean, median, std, min, max); a result object that keeps the "
         "raw error arrays; relative pose error over windows (<code>relative_error</code>).",
         "No spatial alignment by default (Umeyama SE(3)/Sim(3)): when tracking a command the command <em>is</em> the "
         "frame, and aligning would hide real error. No <code>merge_results</code>-style averaging of per-sample "
         "arrays across runs. No clamping at the ends: we drop samples outside the reference instead.",
         "GPL-3.0: ideas only, no code. Checked once as an oracle: <code>relative_error</code> equals evo's RPE "
         "(all_pairs) to 1e-15 [[n:code_oracles]]."),
        ("rpg_trajectory_evaluation · Zhang &amp; Scaramuzza", ["rpg", "zhang18"],
         "Repeated trials as a first-class input (its <code>--mul_trials</code> is our <code>aggregate</code>); "
         "relative error over sub-trajectory lengths.",
         "posyaw / SE(3) alignment: it exists because visual-inertial odometry has four unobservable degrees of "
         "freedom. A commanded arm has none.", ""),
        ("TUM RGB-D · KITTI", ["tum", "kitti"],
         "The RPE definition E<sub>ij</sub> = (Q<sub>i</sub>⁻¹Q<sub>j</sub>)⁻¹(P<sub>i</sub>⁻¹P<sub>j</sub>); KITTI's "
         "drift per distance travelled is <code>unit=\"m\"</code>.",
         "Drift as a percent of distance: an arm's paths are short and a percent hides millimetres.", ""),
        ("trajectopy", ["trajectopy", "trajectopy_ate"],
         "Time-shift estimation (a coarse lag, then a fit that minimises the error): "
         "<code>estimate_time_offset</code>. Along / cross-track error.",
         "Fitting the shift inside the comparison: we estimate it, then you pass it explicitly as "
         "<code>time_offset_s</code>.", "GPL-3.0: ideas only, no code."),
        ("evalio", ["evalio"],
         "Window types in metres or seconds (<code>WindowMeters</code> / <code>WindowSeconds</code>) → "
         "<code>unit=\"m\" | \"s\"</code>; an error object that keeps its arrays.", "", ""),
    ]),
    ("Robot controllers", "best at verdicts", [
        ("control_msgs JointTrajectoryControllerState", ["jtc_state", "jtc_cpp"],
         "The sign: <code>error = reference − feedback</code>, and the controller computes it the same way "
         "(<code>desired − current</code>). A positive error is the correction still to apply.",
         "", "traj_compare used run − target before 2026-11-10; it now follows ROS."),
        ("FollowJointTrajectory · JointTolerance", ["fjt_action", "joint_tolerance"],
         "Verbatim: <code>JointTolerance{name, position, velocity, acceleration}</code>, path vs goal tolerance, "
         "<code>goal_time_tolerance</code>, result codes <code>SUCCESSFUL</code> 0, "
         "<code>PATH_TOLERANCE_VIOLATED</code> −4, <code>GOAL_TOLERANCE_VIOLATED</code> −5.",
         "Codes −1…−3 (<code>INVALID_GOAL</code>, <code>INVALID_JOINTS</code>, <code>OLD_HEADER_TIMESTAMP</code>) "
         "validate a goal, not a run. Component tolerances (multi-DOF joints) are not in. ROS reads 0 as “use the "
         "server default” and −1 as “no limit”; here both mean “not checked”, because a <code>Tolerances</code> "
         "already is the default set and merging a per-goal override onto it is the caller's job.", ""),
        ("joint_trajectory_controller", ["jtc_docs", "jtc_params"],
         "The goal is judged after the trajectory ends, against its final point held; "
         "<code>stopped_velocity_tolerance</code> (default 0.01) applies to every joint in the goal phase.",
         "<code>goal_time_tolerance = 0</code> here means “as long as the data lasts”. JTC's "
         "<code>constraints.goal_time</code> now defaults to 10 s, with 0 meaning no grace period and a negative "
         "value meaning wait indefinitely: pass the controller's number explicitly.", ""),
        ("MoveIt trajectory execution", ["moveit"],
         "Nothing yet. It checks the first point against the current state (<code>allowed_start_tolerance</code>) "
         "and cancels runs that overrun a scaled duration (<code>allowed_execution_duration_scaling</code>, "
         "<code>allowed_goal_duration_margin</code>); path and goal tolerances stay with the controller.",
         "Start-state and duration checks are not in.", ""),
    ]),
    ("Industrial arms and machine tools", "best at separating path from timing", [
        ("ISO 9283", ["iso_hexagon", "iso_sample", "robodk"],
         "Accuracy vs repeatability: the barycentre of N runs against the command (bias), and RP = l̄ + 3·S<sub>l</sub> "
         "around the barycentre (spread).",
         "The test procedure itself (poses in a cube, cycle counts, path planes). We apply the split per instant on "
         "the reference's own grid.",
         "The standard is paywalled; the path details here come from secondary summaries."),
        ("CNC contouring", ["cnc_fiveaxis", "cnc_thesis"],
         "Contour error (distance to the nearest point of the path) separate from lag (tracking) error: "
         "<code>contour</code> / <code>lag_time</code>. Our <code>cross_track</code> is the first-order version.",
         "Path-planning-side compensation: we measure, we do not correct.", ""),
    ]),
    ("Shape metrics and driving benchmarks", "best at time-free comparison", [
        ("Discrete Fréchet", ["eiter", "shapely", "similaritymeasures"],
         "Eiter–Mannila's recurrence, our own numpy implementation along anti-diagonals.",
         "", "shapely (2-D) and similaritymeasures (3-D) used once as oracles [[n:code_oracles]]."),
        ("Dynamic time warping", ["dtaidistance"], "",
         "Not added: Fréchet already gives the one time-free number, and DTW's warped alignment would re-introduce "
         "a hidden time decision.", ""),
        ("Argoverse 2 · Waymo · nuPlan", ["argoverse", "waymo", "nuplan"],
         "Continuous errors next to pass/fail flags: <code>Outcome</code> beside <code>ErrorStats</code>.",
         "ADE / FDE minimum-over-K: that scores multi-modal predictions, not tracking.", ""),
    ]),
    ("Controls and signals", "the classic numbers", [
        ("MATLAB stepinfo · python-control", ["stepinfo", "python_control"],
         "Settling time to a band; overshoot as a percent of the move.",
         "Settling time is NaN when the run never stays inside the band, never “the end of the data”. The band is "
         "absolute (in the signal's unit), not a fraction of the step.", ""),
        ("IAE / ISE / ITAE", ["sproclib"], "The integral criteria, on every <code>ErrorStats</code>.",
         "", "Trapezoids over intervals observed at both ends."),
        ("scipy.signal.correlation_lags", ["scipy_lags"], "The lag-axis sign convention of the cross-correlation.",
         "scipy as a dependency: robot_msgs stays numpy-only; scipy is a test oracle.", ""),
        ("MATLAB Simulation Data Inspector", ["matlab_sdi"], "Compare only where both signals exist.", "", ""),
    ]),
    ("Viewers and data", "where the numbers are looked at", [
        ("Rerun", ["rerun_dataframes", "rerun_tsv", "rerun_rrd", "rerun_embed"],
         "A second projection of the same comparison: one <code>.rrd</code> per comparison, blueprint embedded, "
         "the SDK version pinned.",
         "A log axis (Rerun has none) and custom UI (Rust-only): verdicts go in as data, in <code>/notes</code>.", ""),
        ("PlotJuggler · Foxglove · LeRobot v3", ["plotjuggler", "foxglove", "lerobot"],
         "", "Not targeted yet: an MCAP / Parquet export of a <code>Comparison</code> is the open item that would "
         "let them overlay runs without recomputing.", ""),
    ]),
]

# ── metric reference ─────────────────────────────────────────────────────────

METRICS = [
    ("JointTrajectory", None),
    ("positions/<joint>", "rad (m prismatic)", "signed", "Joint position error, reference − measured, at each measured sample."),
    ("velocities/<joint>", "rad/s", "signed", "When both runs carry velocities."),
    ("accelerations/<joint>", "rad/s²", "signed", "When both runs carry accelerations."),
    ("effort/<joint>", "N·m (N)", "signed", "Torque / force error, when both runs carry effort."),
    ("PoseTrajectory (one per point you care about)", None),
    ("position", "m", "magnitude", "‖p<sub>ref</sub> − p<sub>meas</sub>‖."),
    ("rotation", "rad", "magnitude", "Angle of q<sub>ref</sub>·q<sub>meas</sub>⁻¹, the world-frame rotation taking the measured orientation to the reference."),
    ("x · y · z", "m", "signed", "Components of p<sub>ref</sub> − p<sub>meas</sub> on the reference frame's axes (<code>header.frame_id</code>)."),
    ("rx · ry · rz", "rad", "signed", "Components of that rotation as a world-frame rotation vector (axis × angle). Not a difference of Euler angles, which couple and jump at gimbal lock."),
    ("lag", "m", "signed, + = behind", "Position error projected on the reference's direction of travel (first-order). NaN where the reference rests."),
    ("cross_track", "m", "magnitude", "The rest of the position error, off that direction. Exact on straight segments; leaks lag on curves. NaN at rest."),
    ("contour", "m", "magnitude", "Exact distance to the nearest point of the reference polyline, searched within ±<code>contour_window_s</code> (0.25 s) of the sample's reference time."),
    ("lag_time", "s", "signed, + = behind", "The sample's reference time minus the reference time at that nearest point. NaN where the nearest segment has zero length."),
    ("linear_velocity", "m/s", "magnitude", "‖v<sub>ref</sub> − v<sub>meas</sub>‖, when the measured run carries linear velocities (the reference's are derived if missing)."),
    ("angular_velocity", "rad/s", "magnitude", "Same, for angular velocities."),
    ("Any trajectory", None),
    ("channels/<name>", "the channel's", "signed", "Reference − measured for every numeric channel both runs carry with the same shape; one column per joint or index (<code>channels/&lt;name&gt;/&lt;joint&gt;</code>)."),
    ("time_base/<name>", "—", "not an error", "<code>speed_scaling</code> and <code>segment_index</code> copied verbatim from the measured run; no statistics are made of them. A speed-scaled run's timing error is expected and has to be read against the scaling."),
]

ERROR_STATS = [
    ("n", "count", "—", "Finite samples used. NaN samples (no reference there) are skipped; missing data is NaN with n = 0, never 0."),
    ("rms", "unit", "magnitude", "√mean(e²)."),
    ("mean", "unit", "signed", "The bias."),
    ("median", "unit", "signed", "The bias, robust to a few bad samples."),
    ("std", "unit", "—", "Standard deviation about the mean (population, ddof = 0)."),
    ("min", "unit", "signed", "Most negative sample."),
    ("max", "unit", "signed", "Most positive sample."),
    ("max_abs", "unit", "magnitude", "Worst sample."),
    ("p95_abs", "unit", "magnitude", "95th percentile of |e|: the worst case with one glitch sample ignored."),
    ("final", "unit", "signed", "The last finite sample: the error left when the comparison ends (inside the reference's span; use goal() for after the end)."),
    ("iae", "unit·s", "—", "∫|e| dt (trapezoids over intervals observed at both ends)."),
    ("ise", "unit²·s", "—", "∫e² dt."),
    ("itae", "unit·s²", "—", "∫(t − t₀)|e| dt: late errors weigh more."),
]


def _table(columns: list[str], rows: list[list[str]], group_rows: dict[int, str] | None = None) -> str:
    head = "".join(f"<th>{column}</th>" for column in columns)
    body = []
    for index, row in enumerate(rows):
        if group_rows and index in group_rows:
            body.append(f'<tr class="group"><td colspan="{len(columns)}">{group_rows[index]}</td></tr>')
        if row:
            body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def metrics_table() -> str:
    rows, groups = [], {}
    for entry in METRICS:
        if entry[1] is None:
            groups[len(rows)] = entry[0]
            continue
        name, unit, sign, definition = entry
        names = " ".join(f"<code>{html.escape(part.strip())}</code>" for part in name.split("·"))
        rows.append([names, unit, sign, definition])
    # group headers sit before the row index they name
    out_rows, out_groups = [], {}
    for index, row in enumerate(rows):
        if index in groups:
            out_groups[len(out_rows)] = groups[index]
        out_rows.append(row)
    return _table(["Metric", "Unit", "Sign", "Definition"], out_rows, out_groups)


def error_stats_table() -> str:
    return _table(["Field", "Unit", "Sign", "Meaning"],
                  [[f"<code>{name}</code>", unit, sign, meaning] for name, unit, sign, meaning in ERROR_STATS])


def prior_art_html() -> str:
    blocks = []
    for group, strength, rows in PRIOR_ART:
        body = []
        for name, keys, copied, not_copied, note in rows:
            cite = f"[[n:{','.join(keys)}]]"
            body.append(
                "<tr>"
                f"<td><strong>{name}</strong>{cite}</td>"
                f"<td>{copied or '<span class=why-none>—</span>'}</td>"
                f"<td>{not_copied or '—'}</td>"
                f"<td>{note or '—'}</td>"
                "</tr>")
        blocks.append(
            f'<h3>{group} <span style="font-weight:400;color:var(--faint);font-size:15px">· {strength}</span></h3>'
            '<div class="table-wrap"><table><thead><tr><th>Source</th><th>What we copied</th>'
            "<th>What we deliberately don't do</th><th>Notes</th></tr></thead><tbody>" + "".join(body) +
            "</tbody></table></div>")
    return "".join(blocks)


# ── page fragments ───────────────────────────────────────────────────────────


def media_block(media: dict, name: str, caption: str, alt: str, pending_hint: str = "") -> str:
    path = media.get(name)
    if path:
        return (f'<figure class="media-frame"><a class="zoom" href="{path}" title="open full size">'
                f'<img src="{path}" alt="{html.escape(alt)}" loading="lazy"/></a>'
                f'<figcaption class="media-caption">{caption}</figcaption></figure>')
    hint = pending_hint or "run <code>build_site.py --record</code> once the UR5e example report exists"
    return (f'<figure class="media-frame"><div class="pending"><strong>Media pending</strong>'
            f'<span>{html.escape(alt)}</span><span>{hint}</span></div>'
            f'<figcaption class="media-caption">{caption}</figcaption></figure>')


def hero_media(media: dict) -> str:
    if media.get("hero.mp4"):
        poster = f' poster="{media["hero-poster.png"]}"' if media.get("hero-poster.png") else ""
        fallback = (f'<img src="{media["hero.gif"]}" alt="The UR5e example report: playing the synced transport, '
                    f'turning the 3D view, the TCP error along the belt, the verdicts and the sim → real page"/>'
                    if media.get("hero.gif") else "")
        return (f'<figure class="media-frame"><video src="{media["hero.mp4"]}" autoplay muted loop playsinline controls'
                f'{poster}>{fallback}</video><figcaption class="media-caption">The real UR5e example report, recorded '
                'headlessly: synced playback, the 3D view, TCP error along the belt, verdicts and ISO 9283, then the '
                'sim → real page.</figcaption></figure>')
    return media_block(media, "hero.gif", "The UR5e example report.", "Hero video of the UR5e example report")


def rerun_bar(info: dict) -> str:
    return f"<div class=\"rerun-host\" data-rerun='{html.escape(json.dumps(info), quote=True)}'></div>"


def gallery(context: dict) -> str:
    cards = []
    out = context["out"]
    sdk = context["facts"]["sdk"]
    for example in context["examples"]:
        shot = (f'<img src="{example["shot"]}" alt="{html.escape(example["title"])} report" loading="lazy"/>'
                if example["shot"] else
                '<div class="pending"><strong>Screenshot pending</strong><span>recorded by record_hero.py</span></div>')
        tags = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in example["tags"])
        if example["report"]:
            pages = ""
            if example["pages"]:
                def runs(names: list[str]) -> str:
                    if len(names) <= 2:
                        return ", ".join(names)
                    return f"{names[0]} + {len(names) - 1} more"

                items = "".join(
                    f"<li><strong>{html.escape(page['title'])}</strong>"
                    + (f" — {html.escape(page['reference'])} vs {html.escape(runs(page['runs']))}"
                       if page["reference"] else "") + "</li>"
                    for page in example["pages"][:6])
                pages = f'<ul style="margin:0;font-size:13.5px;color:var(--muted)">{items}</ul>'
            actions = f'<a class="btn" href="{example["report"]}">Open report</a>'
            bars = "".join(
                rerun_bar({"rrd": rrd, "sdk": sdk, "command": context["rerun_command"](sdk, out / rrd)})
                for rrd in example["rrds"][:1])
            link_open, link_close = f'<a class="shot" href="{example["report"]}">', "</a>"
        else:
            pages = ('<p style="font-size:13.5px;color:var(--faint)">Report not built yet: '
                     f'<code>build_site.py --examples {example["slug"]}</code></p>')
            actions, bars = "", ""
            link_open, link_close = '<div class="shot">', "</div>"
        cards.append(
            f'<article class="example">{link_open}{shot}{link_close}<div class="body">'
            f'<h3>{html.escape(example["title"])}</h3><p>{html.escape(example["blurb"])}</p>'
            f'<div class="tags">{tags}</div>{pages}<div class="actions">{actions}</div>{bars}</div></article>')
    return '<div class="gallery">' + "".join(cards) + "</div>"


def landing_rerun(context: dict) -> str:
    out = context["out"]
    sdk = context["facts"]["sdk"]
    for example in context["examples"]:
        if example["rrds"]:
            rrd = example["rrds"][0]
            return (f'<p style="margin:14px 0 4px;color:var(--muted);font-size:14.5px">Try it on '
                    f'<code>{html.escape(rrd)}</code>:</p>'
                    + rerun_bar({"rrd": rrd, "sdk": sdk, "command": context["rerun_command"](sdk, out / rrd)}))
    return ('<div class="note">No example <code>.rrd</code> built yet: run <code>build_site.py --examples</code> '
            '(needs the <code>rerun</code> extra).</div>')


SITE_JS = r"""
(function () {
  'use strict';
  // copy buttons on code blocks
  document.querySelectorAll('.codeblock .copy').forEach(function (button) {
    button.addEventListener('click', function () {
      var code = button.parentNode.querySelector('pre').innerText;
      var done = function (ok) { button.textContent = ok ? 'Copied' : 'Select + copy'; setTimeout(function () { button.textContent = 'Copy'; }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code).then(function () { done(true); }, function () { done(false); });
      } else { done(false); }
    });
  });
  // docs: active section in the table of contents
  var links = Array.prototype.slice.call(document.querySelectorAll('.sidebar .toc a'));
  if (links.length && 'IntersectionObserver' in window) {
    var byId = {};
    links.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var visible = {};
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) { visible[entry.target.id] = entry.isIntersecting; });
      var first = Object.keys(byId).filter(function (id) { return visible[id]; })[0];
      if (first) { links.forEach(function (a) { a.classList.toggle('active', a === byId[first]); }); }
    }, { rootMargin: '-64px 0px -70% 0px' });
    Object.keys(byId).forEach(function (id) { var node = document.getElementById(id); if (node) observer.observe(node); });
  }
  // docs: draggable, remembered, foldable sidebar
  var docs = document.querySelector('.docs');
  var gutter = document.querySelector('.gutter');
  var fold = document.querySelector('.fold');
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* storage blocked */ } }
  function load(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  if (docs && gutter) {
    var saved = parseInt(load('tc-site-sidebar') || '', 10);
    if (saved >= 160 && saved <= 480) docs.style.setProperty('--sidebar-w', saved + 'px');
    if (load('tc-site-folded') === '1') { docs.classList.add('folded'); }
    gutter.addEventListener('pointerdown', function (down) {
      down.preventDefault();
      gutter.classList.add('dragging');
      gutter.setPointerCapture(down.pointerId);
      var left = docs.getBoundingClientRect().left;
      function move(event) {
        var width = Math.max(160, Math.min(480, event.clientX - left));
        docs.classList.remove('folded');
        docs.style.setProperty('--sidebar-w', width + 'px');
      }
      function up() {
        gutter.classList.remove('dragging');
        gutter.removeEventListener('pointermove', move);
        gutter.removeEventListener('pointerup', up);
        store('tc-site-sidebar', parseInt(getComputedStyle(docs).getPropertyValue('--sidebar-w'), 10));
      }
      gutter.addEventListener('pointermove', move);
      gutter.addEventListener('pointerup', up);
    });
    gutter.addEventListener('dblclick', function () { docs.style.removeProperty('--sidebar-w'); store('tc-site-sidebar', ''); });
  }
  if (docs && fold) {
    var label = function () { fold.textContent = docs.classList.contains('folded') ? 'Show contents' : 'Hide contents'; };
    label();
    fold.addEventListener('click', function () {
      docs.classList.toggle('folded');
      store('tc-site-folded', docs.classList.contains('folded') ? '1' : '0');
      label();
    });
  }
})();
"""


def index_values(context: dict) -> dict[str, str]:
    diagrams = context["diagrams"]
    return {
        "hero_media": hero_media(context["media"]),
        "pairings_svg": diagrams.pairings(),
        "quickstart": context["snippet_block"]("quickstart", context["outputs"]),
        "gallery": gallery(context),
        "landing_rerun": landing_rerun(context),
    }


def ur_code_block(context: dict) -> str:
    code, source, whole = context["ur_code"], context["ur_source"], context["ur_file"]
    if not code:
        return ('<div class="note warn">The UR5e example (<code>traj_integration_tests/…/ur_compare/sim_to_real.py</code>) '
                "is not in the tree yet. The snippets above are written against the API and run; "
                "<code>build_site.py</code> shows the example's own code here once the file exists.</div>")
    subtitle = context.get("ur_subtitle", "")
    quoted = f" Its report's own header: <em>{html.escape(subtitle)}</em>" if subtitle else ""
    intro = ("<p>The real example, <code>python -m traj_integration_tests ur-sim-real</code>: one page per pairing, "
             "each written with <code>rerun=True</code>." + quoted + "</p><p>The page-building statements below are "
             "copied out of the file by <code>build_site.py</code> on every build.</p>")
    full = (f'<details style="margin:0 0 1.2em"><summary style="cursor:pointer;color:var(--muted);font-size:14.5px">'
            f'The whole file ({len(whole.splitlines())} lines)</summary>'
            + context["code_block"](whole, "", source) + "</details>")
    return intro + context["code_block"](code, "From the UR5e example", source) + full


def docs_values(context: dict) -> dict[str, str]:
    diagrams = context["diagrams"]
    media = context["media"]
    outputs = context["outputs"]
    block = context["snippet_block"]
    facts = context["facts"]
    codes = facts["codes"]
    return {
        "svg_flow": diagrams.flow(facts["sdk"]),
        "svg_pairings": diagrams.pairings(),
        "svg_tracking": diagrams.tracking(),
        "svg_conveyor": diagrams.conveyor(),
        "svg_iso": diagrams.iso9283(),
        "snippet_quickstart": block("quickstart", outputs),
        "snippet_pairings": block("pairings", outputs),
        "snippet_cartesian": block("cartesian", outputs),
        "snippet_conveyor": block("conveyor", outputs),
        "snippet_verdict_offline": block("verdict_offline", outputs),
        "snippet_verdict_online": block("verdict_online", outputs),
        "snippet_aggregate": block("aggregate", outputs),
        "snippet_latency": block("latency", outputs),
        "snippet_goal": block("goal", outputs),
        "snippet_drift": block("drift", outputs),
        "snippet_frechet": block("frechet", outputs),
        "snippet_report_full": block("report_full", outputs),
        "snippet_pages": block("pages", outputs),
        "ur_code": ur_code_block(context),
        "metrics_table": metrics_table(),
        "error_stats_table": error_stats_table(),
        "prior_art": prior_art_html(),
        "code_successful": str(codes["SUCCESSFUL"]),
        "code_path": str(codes["PATH_TOLERANCE_VIOLATED"]).replace("-", "−"),
        "code_goal": str(codes["GOAL_TOLERANCE_VIOLATED"]).replace("-", "−"),
        "shot_overview": media_block(media, "report-overview.png", "Statistics table with the verdict, latency and settling columns, then the verdict details.", "Report statistics and verdicts"),
        "shot_3d": media_block(media, "report-3d.png", "3D: target, sim and real paths with the posed UR5e models, difference arrows and the view cube.", "Report 3D view"),
        "shot_tcp": media_block(media, "report-tcp-error.png", "TCP error: |Δp|, lag vs cross-track, contour and lag time, and the error along / across the belt.", "Report TCP error plots"),
        "shot_iso": media_block(media, "report-iso.png", "The ISO 9283 card over the repeated real runs: accuracy (bias) vs repeatability (spread).", "Report ISO 9283 card"),
        "shot_sim_real": media_block(media, "report-sim-to-real.png", "The sim → real page: sim is the reference, so every error reads “sim − real”.", "Report sim to real page"),
        "shot_videos": media_block(media, "report-videos.png", "Synced videos: one transport drives every video, the plot cursors and the 3D pose.", "Report synced videos"),
        "docs_rerun": landing_rerun(context),
        "shot_rerun": media_block(media, "rerun-viewer.png", f"The same comparison in Rerun {facts['sdk']} (its embedded blueprint).", "The .rrd in the Rerun viewer",
                                  "recorded by <code>record_hero.py --rerun-shot</code> when the Rerun web viewer can render headlessly"),
    }
