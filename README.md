# traj_compare

Turn-key A/B trajectory comparison viewer. Feed it a **target** and any
number of **situations** — sim A vs sim B, sim vs real, yesterday vs today —
and it writes **one self-contained static `report.html`**: no server, no CDN,
no install at view time. Open it from disk, keep it forever next to the run
data it describes.

Built 2026-07-28 in bam_ws as the second generation of the trajectory comparison viewer (the first lives in
bam_ws `traj_integration_tests/report.py`). **Its own repo since 2026-11-20** (`/home/bam/traj_compare`, history from
2026-08-24 kept; older history stays in bam_ws): a leaf on [robot_msgs](https://github.com/zacharyyamaoka/robot_msgs),
which keeps the data types and the comparison math (`robot_msgs.compare`) while this package is the viewer. bam_ws
links it at `src/external/traj_compare`, and its old path `src/core/mdp/agent/actor/trajectory_generation/traj_compare`
is a symlink to that, so every existing path dependency and command keeps working.

## What the report shows

A run report puts a **stage** on the left: the 3D view (robot + tool paths, the scrubber
under it) over the camera overlay / videos. Drag its edge, fold it with ‹ (both remembered);
below 900 px it stacks above the tabs. Beside it, the **question tabs** shared with Rerun
(`traj_compare.tabs`, contract `docs/NAVIGATION.md` Part B):
*Did it track the target?* · *Where is the error?* · *Which joint has the error?* ·
*Is it late or off the path?* · *Feedforward or feedback?* · *Raw signals per joint*.
A tab with nothing to show is dropped; the last tab is remembered and `#tab=<id>` opens one.
With `Comparison.parts` (`{"Left arm": [joints], "Left hand": {"Thumb": [joints], ...}}`), the per-joint tabs
rank every joint worst first (`<part> · <joint>`, click to jump), offer a part selector (`Left hand · 16 joints`),
and draw an arm one row per joint, a hand one row per finger. Every title names signal, joint, sign and unit
(`shoulder: joint error, Target − run [°]`). Situation chips, Δ-vs-target, rad/**deg**, the
zoom and the time cursor span every tab. `breadcrumb=[(label, href), …]` adds the links back
to the dataset and target.

Everything is show/hide-able per section (chips), per situation (legend
chips), with a rad/**deg (default)** angle toggle. All time plots share one
synchronized x zoom (drag to zoom any plot, all follow; the **Reset zoom**
button or a double-click restores the full range).

Factorial studies use two navigation levels: a short primary tab per
trajectory/scenario group and a secondary selector for that group's
controller, environment, or variant permutations. Situation chips can be
grouped independently (for example Target / Topology / Single changes /
Combined stack), so neither navigation nor legends collapse into one
unexplained list.

Every comparison begins with a compact **error-statistics table**. The viewer
derives a standard joint/TCP table automatically, or an adapter can replace
it with a richer domain table. Report authors can also provide first-class
**Summary** and **Insights** pages with metric cards, grouped bar charts,
tables, evidence, and recommendations.

A per-page **transport** carries one shared time state: hovering any plot
previews that instant in the 3D view; the **scrubber** under the 3D canvas
(step/play/pause buttons + slider) commits a time that drives the vertical
cursor line on every plot, the 3D truncation and robot pose, and the video
players.

| Section | Channels | Default |
| --- | --- | --- |
| Joint q / qd / qdd / τ / i | per joint, target + every situation overlaid; i is motor current in A (`Situation.current`, offered only when a run has it) | q on, rest off |
| Torque breakdown | the **Torque budget** table (per measured run × joint: FB share, commanded / FF / FB RMS, target − commanded RMS, commanded − applied RMS, peak \|commanded\|), then one card per joint × run with five torques: target (grey, dashed), **commanded** (run colour, thickest), **feedforward** (blue), **feedback** (orange, filled to zero), **applied** (run colour, thin). One component legend toggles a torque on every card; situation chips hide a run's cards; a derived component says so in the card title. Offered when a run has `tau_cmd`, `tau_ff` or `tau_fb` | on |
| Joint error | per joint, `target(t) − q` | off |
| TCP pose | x, y, z [m], rx, ry, rz [deg] (extrinsic xyz, unwrapped) of the `tcp_frame` | off |
| TCP error | vs target (error = target − run) at the run's own samples: \|Δp\| [mm] and rotation angle [deg]; **cross-track** (off the path) and signed **lag** along it (+ when the run is behind the target) [mm]; per-axis x/y/z [mm] and rx/ry/rz [deg] as a world-axis rotation vector | on |
| TCP error, second wave | the exact **contour** error (distance to the nearest point of the reference path) and **lag time** (+ when the run is behind) from `robot_msgs.compare`; with `Comparison.error_axes` one row per named axis (**error · along belt**, across belt, up): the same position error as x/y/z projected on those directions | with TCP error |
| Path progress | rows path/path_d/path_dd × columns **%** (of target path length), **XYZ** arc length, **RPY** accumulated rotation, **Vec[label]** signed progress along each configured direction | on |
| Camera | one card per `CameraOverlay` in `Comparison.overlays`: the real video with a selected sim render stacked on top — **Real ◀ ▶ Sim** opacity slider (0 = only real, 1 = only sim), sim-source dropdown, Mix / Difference blend, 2 Hz Flicker; video position = t − `t0_s`; opacity/sim/blend/flicker are report-level prefs; a missing file shows a greyed "no video" card with its path | on |
| Videos | one card per situation with a `video`, always played/seeked together by the transport | on |
| 3D paths | interactive three.js viewer — see below | on |
| Recorded channels (tab **What else was measured?**) | every other signal a situation recorded (`Situation.channels`: contact force, a detector residual, a temperature), described by `Comparison.signals` = `{name: traj_compare.Signal(title, unit, columns, per_joint)}`: one section per channel, one plot per column titled `<title>, <column> [<unit>]`, every situation in its run colour. A channel nobody described is drawn under its own name, never dropped (`docs/NAVIGATION.md` C1). Rerun: `/channels/<name>/<column>/<situation>`, the same tab title | on |

**Vec** is the belt-matching view: pass your conveyor direction in
`vec_dirs` and `Vec[Conveyor]_d` reads back directly whether the TCP holds
belt speed.

The 3D viewer draws, per situation: the path (target dashed), sampled
points, full pose frames (RGB), z-vectors, **difference arrows** (from a
run's pose to the target's pose *at the same instant* — points to where you
should have been; ahead/behind reads along the path), and **z-arcs** (the
rotation gap fan between a run's tool z and the target's, grey ghost =
target z). Each situation is one control row: a **visibility eye** (bulk
show/hide in the scene) plus a **full-word multi-select dropdown** choosing
which elements draw; rows disappear when the situation is hidden globally.
The transport truncates all of it to the scrub/hover time over a faint
full-path ghost. A log **density** slider controls how many samples get
markers (default 20) and a **size** slider scales them. Orbit / wheel zoom /
right-drag pan / double-click fit, plus a clickable **view cube** in the
canvas corner (TOP/FRONT/RIGHT… snap views); z-up.

Pass a `RobotDisplay(link_names, link_meshes, link_fk)` as
`Comparison.robot` and the viewer also poses the robot at the transport time
for every data-bearing situation. Mesh triangle soups are embedded in the
report once: identical link meshes posed on many pages (a joint x speed
study) share one entry of the report-level `mesh_library`. Each situation's dropdown includes a checked-by-default **Robot /
URDF** option so the matching model is visible by default and can be turned
off independently; the model inherits that situation's color. A shared
opacity slider controls all displayed models. Standard robot-trajectory
adapters should always provide this display when a robot description exists.

A situation declared without data (e.g. a skipped hardware run) keeps its
legend slot and renders as "no data — *note*": a sim-vs-real report still
builds when real was not run.

## API

```python
import numpy as np
from traj_compare import (
    Comparison, Insight, ReportPage, Situation, write_comparison_report,
)

target = Situation(name="target", title="Target", t=t, q=q, qd=qd, qdd=qdd, tau=tau)
sim_a  = Situation(name="sim_a", title="Sim A", t=t_a, q=q_a, qd=qd_a, tau=tau_a)
real   = Situation(name="real", title="Real", note="hardware run skipped")

comparison = Comparison(
    title="Conveyor track",
    group="part-a",
    group_title="Part A",
    tab_title="Controller A",
    joint_names=["j1", "j2", "j3", "j4", "j5", "j6"],
    target=target,
    situations=[sim_a, real],
    fk=my_fk,                                  # (N, DOF) -> (N, 4, 4) TCP poses
    tcp_frame="TCP",                           # which frame fk describes: "L2 tip", "coupler point", ...
    vec_dirs=[("Conveyor", np.array([0, 1, 0]))],
)
insights = ReportPage(
    name="insights",
    title="Insights",
    insights=[
        Insight(
            title="Controller A is the next candidate",
            finding="It lowers TCP RMS without raising motor torque.",
            recommendation="Repeat it on the endurance tape.",
            tone="positive",
        )
    ],
)
write_comparison_report([comparison], out_dir, insights=insights)
```

- Arrays are SI (s, rad, m, Nm); the deg default is a viewer toggle only.
- `qd`/`qdd` fall back to `np.gradient` when omitted (flagged in the report);
  `tau` stays absent if absent.
- **The five torques** (N·m, (N, DOF) on the situation's own grid; Zach 2026-11-19, contract in
  `docs/layout_proposals_2026-11-19/CONTRACT.md`):

  | Name | `Situation` field | What it is | moteus |
  | --- | --- | --- | --- |
  | target | `target.tau` | the torque the reference needs (inverse dynamics of the target) | planner |
  | commanded | `tau_cmd` | what the controller asks the FOC current loop for | reply `control_torque` |
  | feedforward | `tau_ff` | the model-based part of the command | cmd `feedforward_torque` |
  | feedback | `tau_fb` | the error-correcting part (kp·e + kd·ė + ki∫e) | `control_torque − feedforward_torque` |
  | applied | `tau` | the torque actually delivered at that instant | reply `torque` |

  `tau` keeps its meaning (applied on a run, target on the target), so older reports are unchanged. **Two of
  three derive the third** (`tau_cmd = tau_ff + tau_fb`), listed in `entry["derived"]` and labelled "derived" on
  the page; all three given are kept as given (a drive clamp can break the sum, and the page shows it); one alone
  derives nothing. Payload: `plot["tau_cmd" | "tau_ff" | "tau_fb"]`, `payload["has_torque_breakdown"]`, and per
  measured run with a breakdown `entry["torque_budget"][joint]` = `cmd_rms`, `ff_rms`, `fb_rms`, `applied_rms`,
  `cmd_peak` (`error_stats` rms / max_abs on the run's own samples), `fb_share` = Σ\|fb\| / (Σ\|ff\| + Σ\|fb\|)
  (how much of the command the feedback supplied), `target_minus_cmd_rms` (`compare` with effort = commanded:
  time offset honoured, never extrapolated) and `cmd_minus_applied_rms` (the drive gap); `None` where a series is
  missing. `examples/torque_breakdown_demo.py` writes one (a feedforward that underestimates gravity vs a calibrated one).
- Situations may live on different time grids; display channels are
  resampled onto the target's grid (nulls outside a run's own span, so a
  short run ends in a visible gap, not a fabricated plateau). Error channels
  are computed exactly on each situation's native grid first.
  Error channels never extrapolate the target either: a sample past the
  target's first or last time has a null error and no arrow, and stays out of
  the RMS (data-ui `difference(a, b)`, fixture in `tests/fixtures/data_ui_difference`).
- No `fk` and no `poses` → the cartesian sections are simply omitted;
  joint-space comparison still works.
- `poses` may be passed directly per situation (e.g. mocap) instead of `fk`.
- `Comparison.statistics` accepts a display-ready `ReportTable`; otherwise a
  standard error table is generated automatically: mean/worst joint RMS,
  TCP position and rotation RMS, max · final, and cross-track · lag RMS.
- Every error signal and statistic is computed by `robot_msgs.compare`
  (`compare(target, run)`), never by this package: one source of truth.
  The convention is its ROS 2 one, **error = target − run**, taken on the
  run's own samples inside the target's span (the target is interpolated,
  never extrapolated).
- Every measured situation's payload entry carries `error_metrics` (SI): one
  entry per `robot_msgs.compare` metric name (`positions/<joint>`,
  `velocities/<joint>`, `position`, `rotation`, `x` `y` `z` `rx` `ry` `rz`,
  `lag`, `cross_track`), each the `ErrorStats` fields `n`, `rms`, `mean`,
  `median`, `std`, `min`, `max`, `max_abs`, `p95_abs`, `final`, plus
  `coverage`, `dropped` and `time_offset_s` of how the run was lined up, so
  adapters and agents read the numbers instead of re-deriving them.
- Lag / cross-track split the position error on the target's direction of
  travel (the lag / contouring split of model predictive contouring
  control); lag is + when the run is behind. Where the target rests there is
  no direction, so both are null.
- **Verdicts, latency, settling, repeatability** (all optional, all `robot_msgs.compare`; a report without
  them is unchanged):

  | `Comparison` field | Adds |
  | --- | --- |
  | `tolerances` / `tcp_tolerances` (`Tolerances`: `JointTolerance` groups / `PoseTolerance`) | per run `entry["verdict"] = {"joint": …, "tcp": …}` (`check`: `code_name`, `violations`, `margins`, `goal_time`, `unchecked`); a green/red **verdict badge** on the run's legend chip whose hover is the first violation ("positions/j2: 0.504° > 0.229° at t = 0.71 s"; joints and rotations in °, the tool in mm); **Verdict** column; a "Verdicts" details block |
  | `estimate_latency=True` | `entry["latency"] = {offset_s, rms_before, rms_after}` (`estimate_time_offset` on the joints); **Est. latency** column |
  | `goal_band` (rad) / `tcp_goal_band` (m) | `entry["goal"]` (`goal`: final error, settling time, overshoot); **Settling · overshoot** column (TCP, else the slowest joint) |
  | `error_axes=[(label, vector), …]` | `payload["error_axes"]`, `plot["err_axes"]` and the TCP-error rows above |
  | `reference_kind="run"` | the reference in `target` is a recorded run (sim → real), not a trajectory to follow: the torque legend reads `<title> τ (applied)`, the toolbar `Error vs <title>`, the 3D arrows `Arrows → <title>`, Rerun's torque views `<title> (applied)`; the dataset drill-down sets it for every run-to-run pair. Default `"target"` keeps "target" |
  | `repeat_groups={"Real ×5": [names]}` | `payload["aggregates"][group]` (`aggregate`) and an **Accuracy vs repeatability (ISO 9283)** card: AT = max \|reference − barycentre\| (bias), RT = max of mean + 3σ of the runs' distance to the barycentre (scatter), per joint and TCP position |

  `Situation.time_offset_s` (how late the run's clock runs, `robot_msgs.compare`'s `time_offset_s`; 0 = agree) is
  passed to every `compare` / `check` / `goal` / `aggregate` call for that run: set it to a latency estimate to
  see the error that is left. The legend chip shows it ("clock −8 ms") and the table's status cell says
  "shifted"; the plotted channels stay on the run's own clock.
  The default `stopped_velocity_tolerance` (0.01 rad/s) applies to the goal phase whenever a run records `qd`;
  a reference that ends moving (a conveyor track) needs it raised, or `check` can never reach the goal.
- `examples/tracking_errors_demo.py` shows every standard field on a planar
  2R arm with a lagging and an offset run.
- `summary=` and `insights=` accept `ReportPage` objects. A page may contain
  `MetricCard`, `BarChart`, `ReportTable`, and `Insight` blocks.

## Open in Rerun

Every comparison can also be written as a [Rerun](https://rerun.io) recording: the same data, a second
projection (decision note "Tracking-Run Data — data-ui vs Rerun", 2026-10-26). Install the extra and ask for it:

```python
write_comparison_report(comparisons, out_dir, rerun=True)   # needs: uv run --extra rerun ...
```

`rerun=True` writes `rerun/<comparison.name>.rrd` beside `report.html` (one recording per comparison, blueprint
embedded) and gives each page an **Open in Rerun** control. Without the SDK it raises an `ImportError` naming the
`rerun` extra; the default `rerun=False` never imports it. `write_rrd(comparison, path)` writes one file directly.
The numbers come from the same payload as the HTML (so from `robot_msgs.compare`), shown in the units a person reads:
joints in degrees (`/positions`, `/velocities` in °/s, `/error/positions/<joint>/<situation>` = target − run in °), the tool
in mm (`/error/tool/...`, rotation in °), `/vec/<label>/<situation>` the signed speed along each `vec_dirs` direction,
`/effort`, `/world/<situation>/{robot,tcp}`, `/video/<situation>` (MP4) and a `/notes` statistics table. The joint series,
errors, bands, robot links and videos are written by `robot_msgs.viz.rerun` (`degrees=True`, `band`, `links`, `video`), so a
traj_compare recording and a `msg.show()` recording share one entity layout; the rest is traj_compare's own. The stored data (payload,
Parquet, MCAP) stays SI; the `.rrd` is a viewer. On top of that every recording carries what the layouts read:
shaded tolerance bands (`.../tolerance`, Rerun `Measurements`), `/worst/joint_deg/<run>`, `/tcp/{x,y,z}_mm`, the
reference path coloured by the worst run's tool error (`/heat_worst`, and `/trail_worst` on the clock), a worst-first
`/scorecard`, tolerance `/events` and per-run RMS bars (`/stats/...`). With a torque breakdown it also carries
`/torque/<joint>/target` and `/torque/<joint>/<run>/{commanded,feedforward,feedback,applied}` (N·m; feedforward
`#3b82f6`, feedback `#f97316`, commanded and applied in the run's colour, applied thin, target grey), the
`/stats/fb_share/<joint>` bars (feedback share of the command per run, %) and a Torque budget table in `/notes`.

**Two named layouts** (`rerun_export.LAYOUTS`, Zach's pick from five, 2026-11-11):

| Name | What it is | Tabs |
| --- | --- | --- |
| `questions` (default) | the 3D robot over the camera overlay pinned on the left; the HTML run view's own question tabs (`traj_compare.tabs`: same titles, same drop rule) | Did it track the target? · Where is the error? · Which joint has the error? · Is it late or off the path? · Feedforward or feedback? · Raw signals per joint |
| `evo` | evo's own Rerun layout (`evo_ape --rerun`) plus one full-screen tab per analysis | Visualization · Trajectories · Joint error · Along / across · Torque · Video · Stats · Raw data |

With `Comparison.parts`, the `questions` layout's per-joint tabs (joints, torque, signals) nest one tab per part,
`<part> · <n> joints`: an arm is a two-column grid, a hand one row per finger. The joints tab ranks first: each part's bars
(`/stats/joint_rms/<part>`, every joint's worst-run RMS error in °; the title names the worst joint, then the bar
order) and, with two or more parts, one line listing every joint worst first (`/stats/joint_ranking`).
`layout_blueprint(..., tab=)` takes a tab id, its title, a pre-2026-11-19 title ("Which joint?") or a check tab's name.

The torque tab (**Feedforward or feedback?** / **Torque**) shows, per joint, the worst scorecard run's full breakdown, every
run's feedback and the FB-share bars. Tabs with nothing to show are dropped (no video → no Video tab; no tool frame → no
*Where is the error?* / *Is it late or off the path?*; one joint → no *Which joint has the error?*; no torque breakdown → no torque tab). Pick one per
call (`write_comparison_report(..., rerun=True, rerun_layout="evo")`, `write_rrd(..., layout="evo")`) or set your
preference once, for every call that does not name one:

```bash
export TRAJ_COMPARE_RERUN_LAYOUT=evo
```

or `rerun_layout = "evo"` in `~/.config/traj_compare/config.toml` (the env var wins). The chosen layout is embedded in
the `.rrd`; every layout is also written beside it as `<name>.<layout>.rbl`, so the report's **Layout** menu (and
`viewer_command(rrd, layout="evo")`) opens either. `layout_blueprint(name, payload, videos, tab="joints")` opens on
a named tab.

**Check tabs in Rerun.** A measurement that checks the others (a camera's ArUco angle checking the encoder) is not a run to
grade. Name its situation `group` and give it a tab: `write_comparison_report(..., rerun=True, rerun_checks={"camera": "Camera Check"})`
(also `write_rrd(..., checks=...)`, `layout_blueprint(..., checks=...)`). That group's runs leave every other Rerun view (a
`- $origin/<run>/**` contents rule, so they are in no legend or auto-scaled axis there), the scorecard, the events, the RMS
bars and the worst-run heat path, and get a last tab in either layout: their notes and every run's scores
(`/checks/<group>/scorecard`), the angle and joint error of every run, the tool error, and every run in 3D. A comparison whose
check run has only a note (no data) still gets the tab, saying why; one without the group gets none. The HTML page is unchanged.

**Camera overlay in Rerun.** A `CameraOverlay` (the real camera + sim renders) is baked with ffmpeg into one MP4,
`rerun/<name>.overlay-<overlay>.mp4`, and logged as `/video/overlay/<overlay>`: Rerun's stock video view plays it. Each
render is mixed at 50 %; `CameraOverlay(key_color="#fcfcfb")` keys a render's flat background out first so only the
robot lies over the camera.

**Version pin.** `RERUN_SDK_VERSION = "0.40.0"` (`traj_compare.rerun_export`, and the `rerun` extra): an `.rrd` must be
opened by a viewer at least as new as the SDK that wrote it, so the button and the printed command always use
`uvx --from rerun-sdk==0.40.0 rerun <file>`.

**What the button does**, by how the report is opened:

| Opened from | "Open in Rerun" | Also |
| --- | --- | --- |
| `python -m traj_compare.serve <dir>` (default `http://127.0.0.1:8767/report.html`) | `POST /__rerun/open?rrd=...&layout=...`; the server starts the pinned viewer on the file in the chosen layout (only files inside `<dir>`) | "Rerun in browser" opens app.rerun.io on the served `.rrd`; one server holds every dataset site below `<dir>` (see Dataset view) |
| `file://` or any plain static server | copies the `uvx` command (no launcher to call) | "Copy command", "Download .rrd" |

## Dataset view

Many runs at a glance, then drill down into one (`traj_compare.dataset`, 2026-11-11). `robot_msgs.compare` is the math,
`write_comparison_report` the run view, this the dataset view; the domain package supplies the runs, tags, tolerances and a
`summary` page. Every number is `robot_msgs.compare`'s; angles are SI in the files and degrees on the page.

```python
from traj_compare import Run, write_dataset_report

runs = [Run(name="can13 rep 0", reference=target, measured={"sim": sim, "real": real},
            tags={"tape": "A", "speed": 0.5, "held_out": False})]
write_dataset_report(runs, "out/", title="Wrist coverage", group_by=("tape",), tolerances=tolerances,
                     poses="my_rig:tool_pose", robot="my_rig:robot_display", summary=summary_page,
                     primary={"sim": "sim_it5"}, drill_down="lazy")
```

- **Tabs and the config league** (`docs/NAVIGATION.md` Part E, 2026-11-23). The Dataset level is tabs: **Overview**
  (`#/`: one row per config, ranked on the sweep's `y` at the fastest x, its ratio to the best, n targets, every KPI with
  a sparkline over x, chips per facet, a facet × config matrix; then the band below), **Speed sweeps** (`#/sweeps`),
  **Targets** (`#/targets`: cards ⇄ table a page at a time, or `?cfg=` a config's worst targets) and **Runs** (`#/runs`).
  A row click drills to that config's worst targets, then a target, then a run. KPIs are run tags:
  `Sweep(x="speed_fraction", y="{series}_tcp_rms_mm", facet_by=("dataset", "split"), metrics=(Metric("{series}_energy_j",
  label="energy per task", unit="J"),))`; `{series}` reads each measured series' own tag, so sim and real rank apart.
  Without a sweep the Overview ranks configs by their median RMS joint error. The `summary` page is folded at the foot of
  Speed sweeps (Overview without a sweep).
- **Three levels** (`docs/NAVIGATION.md` Part A). `index.html` opens on the **Dataset**: your `summary`, a band across every
  target (targets, lines sim/real, configs, dates; per config the median RMS error and "better than <baseline> on X of Y
  targets"), then the targets as **Cards** ⇄ **Table** (one row per target × config: lines, RMS error per line, median,
  Δ vs baseline, ISO 9283 RT, error over time) ⇄ **Runs** (the table, heatmap, peak strip and ISO cards below).
  `#/target/<slug>` is one **Target**: a draggable, foldable line list (regex filter, tag chips, group by config / date /
  sim-real), a verdict, and two tabs: *How repeatable is each config on this target?* (joint error per joint; lines up to
  N, then a median · IQR · p5–p95 · min–max fan of the real lines, sims dashed, never pooled) and *Has tracking improved
  across configs over time?* (an I-MR control chart per config phase, in date order). A line's ↗ opens its run report,
  whose breadcrumb links back.
- `target_by` (default: the `"target"` tag, else the first `group_by` tag, else a hash of the reference), `config_by`
  (default: the first `group_by` tag that isn't the target, else the series name); a `"date"` tag orders the history;
  configs keep one colour on every level, all distinct (grey only for the single sim-only config of a twin-vs-hardware
  dataset; sim lines are dashed either way).
- **Size** (`docs/NAVIGATION.md` C5). `index.html` holds each line's scalars only; every line's drawn series (joint error,
  feedback torque, FB share) lives in `targets/<slug>.js`, a classic script the page adds when a target opens or its card
  or league row scrolls into view, so it works from `file://` too. `display_hz` (default 50) is the rate picked from the
  reference; `target_budget` (default 2 000 000 drawn values per target file) grows the stride for a huge target, and every
  chart says the rate it draws.
- **Signals beyond the joints** (`docs/NAVIGATION.md` C1). A series' `JointTrajectory.channels` travel with it:
  `channels["current"]` (N, J) in A (or (N,) on one joint) is the run report's motor current; every other channel is drawn
  in its *What else was measured?* tab. `write_dataset_report(..., signals={"contact_force_n": Signal("Contact force", "N")})`
  names and units them; it is stored in every manifest, so a drill-down built later still has it. A wrong-shape current
  raises when the dataset is written, never at drill-down.
- `Run(name, reference, measured, tags, pairs, time_offset_s, title, media, media_start_s)`: `measured` holds any number
  of series (`"reference"` is the target's reserved name). `pairs=None` is `default_pairs(series)`: the target to each series,
  then every series to every later one. A pair (a, b) is taken with `time_offset_s[b] - time_offset_s[a]`.
- `poses` / `robot` are `"module:function"` import specs (`JointTrajectory -> PoseTrajectory`, `() -> RobotDisplay`), stored in
  each manifest so a later process can rebuild the drill-down; `poses` adds the TCP rows and the run view's cartesian sections.
- `data_ui=True` also writes `out/data-ui/` for data-ui's dashboards (the **data-ui** section below).
- `primary={"sim": "sim_it5"}`: the default view shows the reference, the primary series, and every series that is neither an
  alias nor named `<alias>_...` (3 pairs, not 6); the page's **show all pairs** switch and `rows.json` keep the rest.
- **Files**: `index.html` (self-contained: answer line, your `summary` page, runs x pairs table with sort, a filter per tag,
  verdict and shaded cells, joint x run heatmap, peak-time strip, ISO 9283 cards per group x series, per-row **Open run** and
  **Open in Rerun**); `targets/<slug>.js` (the drawn series, above); `rows.json` and `rows.parquet` (with the `export`
  extra): one row per run x pair x metric x stat `{run, pair, metric, stat, value, unit, <each tag>}` in SI, choose with
  `rows=("parquet",)` (or `()`, `("json",)`; default both when pyarrow imports; one not chosen is deleted);
  `references/<digest>.npz`, each distinct reference once (a run's manifest names it as `../../references/<digest>.npz`);
  `runs/<slug>/manifest.json` (written last, with the run's `digest`), `analysis.json` (the run's index entries and rows),
  `<series>.npz` (`robot_msgs.load_npz`), `<series>.torques.npz`, `media/<key>.<ext>`; `targets/<slug>.cache.json` (a
  target's index entry and lines). Every `.npz` is deflated, values bit-identical (`docs/NAVIGATION.md` C2, C6).
- **Incremental writes** (`docs/NAVIGATION.md` Part D). Writing into a folder an earlier write left reuses every run whose
  digest is unchanged: its data, title, tags, pairs, offsets, torques, media (key, size, mtime), its slug and target, the
  per-run options (`poses`, `robot`, `tolerances`, `signals`, `primary`) and the source of traj_compare, robot_msgs and
  your poses / robot module. A reused run's folder is not touched (its built report and `.rrd` stay), its rows come from
  `analysis.json`, and nothing is compared or posed again; a target whose runs and drawing options are unchanged keeps its
  `targets/<slug>.js`. The result equals a fresh write. `reuse=False` rewrites everything; pass it after changing data your
  poses or robot function loads (a URDF), which the digest cannot see. Every file is written under a `.tmp` name and
  renamed into place, so a stopped write leaves each file whole (old or new) and a hard-linked copy (`cp -al live staging`)
  can be rewritten without touching the original. `progress=lambda phase, done, total: ...` reports `runs`, `reused`,
  `targets`, `index` and, when eager, `drill`; an exception from it stops the write.
- **Drill-down** (`build_drill_down(out, run_name)`, or `python -m traj_compare.dataset drill <out> "<run name>"`): one
  `Comparison` per pair (first element is the reference), one tab per pair, `runs/<slug>/report.html` plus a `.rrd` per pair.
  A media key equal to a series name is that situation's synced video (`Situation.video_start_s`: trajectory time at video time
  0); any other key is an extra clip on the page.
- **Lazy vs eager**: `"lazy"` (default) writes nothing heavy; `python -m traj_compare.serve <out>` builds a run's report, or its
  `.rrd` when you press **Open in Rerun**, on the first request and caches it. `"eager"` builds all now. WHY lazy: 387 runs x 3
  pairs of `.rrd` is about 2 GB up front. From `file://` the buttons copy the command instead. One server serves every site
  below its root (a site is a folder with `index.html` and `runs/`, at any depth): `python -m traj_compare.serve dashboard/`
  holds `dashboard/ur5e/`, `dashboard/pendulum/`, ... and answers `/` with a page linking each site (title, run count) when
  the root has no `index.html`. It builds a run straight from its folder (`traj_compare.build_run_folder(folder)`).
- `examples/dataset_demo.py --out DIR [--eager]` writes twelve synthetic runs of the planar 2R arm.

- **Torque breakdown.** `Run(..., torques={"real": {"tau_ff": ff, "tau_fb": fb}})` takes any of `tau_cmd` / `tau_ff` /
  `tau_fb`, (N, DOF) N·m on that series' samples. Two of the three give the third; applied stays the series' `effort`. It is
  saved as `runs/<slug>/<series>.torques.npz`, so the run report gets its "Feedforward or feedback?" tab. The Dataset band
  shows each config's median FB share (Σ|fb| / (Σ|ff| + Σ|fb|)); the League table shows FB share and drive gap (RMS
  commanded − applied) per target × config; a Target's "How repeatable…" tab adds a feedback-torque and an FB-share chart
  per joint (±150 ms window), as lines or fans per config like the joint error. No breakdown: "—" or nothing.

## data-ui

The dataset also feeds data-ui's robotics dashboards (`traj_compare.data_ui`, 2026-11-11), through data-ui's **trajectory
contract, version 1** (`/home/bam/data-ui/gallery/robotics/CONTRACT.md`). Seams: `robot_msgs.compare` is the math, this is the
classic run view + dataset view + the data-ui producer, data-ui only draws, sim2real is the domain.

```python
write_dataset_report(runs, "out/", title="Wrist coverage", poses="my_rig:tool_pose", robot="my_rig:robot_display", data_ui=True)
# or on its own: from traj_compare.data_ui import write_tables; write_tables(runs, "out/data-ui", poses=..., links=...)
```

- **Files**, in `out/data-ui/`: `runs.json` (`url` is the classic drill-down, `../runs/<slug>/report.html`; every tag a column),
  `samples.json` (`q_deg`, `qd_deg_s`, `qdd_deg_s2`, `tau_nm` per joint), `devices.json` (one servo per joint), `diff_samples.json`,
  and with `poses` the TCP in `poses.json` + `diff_poses.json` (mm, wxyz), with `links` (or a `robot` spec) `links.json`,
  and `media.json` only when a run has media. Each file carries its contract schema inline, with the declared units.
  `views.base` is the dashboard over them (runs table, playback, 3D path + top view, tool error, joint error, joint angle, coverage).
- **Situations**: `target` (family `target`), a series named `real…` (family `real`), every other series (family `sim`). Pairs
  written: each situation against `target`, each `sim` against each `real`. A series' clock is shifted by its `time_offset_s`
  onto the target's.
- **`difference(a, b)`** (CONTRACT section 5, b − a) is `traj_compare.data_ui.difference`: the numbers are `robot_msgs.compare`'s
  error (reference = b) converted at the edge, and it reproduces the contract's fixture (`tests/test_data_ui.py`). Rows are picked
  at `display_hz` (default 100 Hz), never averaged, and the differences are computed on the rows written.
- **Open it**: `write_dataset_report(data_ui=True)` also stages `out/data-ui.html` and a `out/kit` link to a built data-ui
  (`traj_compare.data_ui.stage_viewer`, when `/home/bam/data-ui/dist/site/kit` exists); then
  `python -m traj_compare.serve out/` and open `/data-ui.html` (a run's link goes to its drill-down, built on first open). Any host
  page works the same: `<data-dashboard src="data-ui/views.base">` beside data-ui's `kit/`. Check the file with
  `node /home/bam/data-ui/bin/data-ui.mjs check out/data-ui/views.base`.
- **Degrees rule**: stored data is a display projection (data-ui converts nothing, and a `.base` formula is a coalesce, never
  arithmetic), so the joint error is stored in degrees as `e_q_deg` beside the contract's `e_q_mrad` (and `err_rot_deg` beside
  `err_rot_mrad`): CONTRACT section 5 lets a library add `e_<channel>`. Every panel reads `e_q_deg` (°) and `err_mm` (mm); no view shows rad or mrad.
- **Contract gap found**: `robot_msgs.trajectory`'s `quat_slerp` falls back to a normalised lerp under 1.8° (`dot > 0.9995`), which is
  up to 8e-4 mrad off the contract's slerp, so `difference` takes b's orientation at t from its own exact slerp (the rest is robot_msgs').

## Coverage viewers

Three families, one shape (Zach 2026-11-23: "Robot_msgs in. Then do the analysis. and then like the viewers out"):
`analyze()` writes one JSON payload, and a data-ui workbench page, Matplotlib PNGs, Viser and W&B summary scalars all
read only that payload.

- **Trajectories** (`traj_compare.coverage`, `docs/COVERAGE.md`): joint limits, phase planes, the tool's workspace.
- **Grasps** (`traj_compare.grasp_coverage`, `docs/GRASP_COVERAGE.md`): GraspPose + outcome + the jaw range.
- **Any records** lives in its own public package, [dataclass_coverage](https://github.com/zacharyyamaoka/dataclass_coverage)
  (`/home/bam/dataclass_coverage`): a list of frozen dataclasses (robot_msgs messages, JSON rows), each field against its
  declared `Value(low=, high=)`, class balance, missing values, pair planes, growth with a Chao1 ceiling, held-out
  support. It was `traj_compare.record_coverage` for a day (2026-11-24); its proof on BAM data stays here,
  `docs/record_coverage_2026-11-24/`.

## Parquet and MCAP exports

`write_comparison_report(comparisons, out_dir, exports=True)` also writes `exports/<comparison.name>.parquet` and
`.mcap` beside `report.html`, adds `comparisons[i].exports = {parquet, mcap}` to the payload and shows **Download
Parquet** / **Download MCAP** links next to "Download .rrd" (or alone when `rerun` is off). Both are projections of the
same payload as the HTML and the .rrd, so no metric is recomputed; install the extra (`uv run --extra export ...`:
`pyarrow>=15`, `mcap>=1.2`), otherwise `ImportError` names it. `write_parquet(comparison, path)` and
`write_mcap(comparison, path)` (`traj_compare.export`) write one file directly.

- **Parquet** — tidy long rows `comparison, situation, reference, channel, column, t, value`. `channel` is the payload's
  plot key (`q`, `qd`, `qdd`, `tau`, `tau_cmd`, `tau_ff`, `tau_fb`, `err_q`, `err_x`.., `lag`, `cross_track`, `contour`, `lag_time`, `vec0_d`,
  `err_axes`, ..., and `channels/<name>` for each recorded channel), `column` the joint name / `error_axes` label / the
  channel's column label or `""` for a scalar channel, `t` seconds from the
  reference's first sample on the plot grid, `value` NaN where the payload has null. The target's rows carry its own name
  as `reference`.
- **MCAP** — JSON messages with a jsonschema schema per topic `/traj_compare/<situation>/<channel>`; one message per
  plot-grid sample `{"t": seconds, "<column>": value, ...}` (a scalar channel's field is `value`; null samples are
  left out), log time = publish time = `t` in integer ns. `/traj_compare/metrics` holds one message with every
  situation's error statistics.

## Publishing on a static host

What a public site (GitHub Pages) needs, all off by default so a local report is unchanged (TTA asks, 2026-11-24):

- `write_comparison_report(..., assets="site/assets")` writes the shared viewer files (uPlot, three.js, the viewer's JS
  and CSS) into that folder once and references them relatively, instead of inlining ~0.95 MB in every report; a URL
  (`assets="https://…/assets"`) is referenced as given. 42 task reports: 56.8 MB inline, 17.6 MB shared.
- `write_dataset_report(..., command_root="site/comparison", rerun_server=False, public_url="https://…/comparison/")`:
  the page's commands name `command_root` instead of the absolute build folder; each run row links "Open in the Rerun web
  viewer" (app.rerun.io at the pinned SDK) and the `.rrd` instead of POSTing to `traj_compare.serve`; `rows=()` leaves
  the row files out of the footer.
- `Comparison(stats_mask=<bool per target sample>, stats_mask_label="moving samples")` takes every error statistic over
  those samples only (the plots keep every sample), so a ruler's "RMS over the moving samples" is the report's RMS.
- `report.html#run=<name or title>` opens one run beside its reference (with `#tab=<id>&run=…` too); not remembered.
- Both pages follow `prefers-color-scheme`; `<html data-theme="light">` (or `"dark"`) pins one. The dark rules are
  generated from the light ones (`python -m traj_compare._theme`; `--check` in CI), so the light page is unchanged.

## Formatting contract

Adapters define the semantic bounds: group names and order, table values and
units, evidence, and recommendations. Within those bounds, the shared viewer
is explicitly free to automate presentation — responsive reflow, compact
secondary navigation, grouped controls, table scrolling, and card/chart
layout — whenever that makes the report clearer. Presentation automation must
not merge scenarios, change units, reorder evidence into a different meaning,
or invent conclusions.

## Run the tests

```bash
cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
uv run --extra test --extra rerun --extra export python -m pytest -q
```

`tests/test_rotations.py` pins the rotation helpers against scipy;
`tests/test_analysis.py` pins channel identities (arc length of a line,
percent normalization by target total, vec projection, null padding, empty
situations); `tests/test_report.py` checks the report is self-contained and
survives `</script>` in user text.

## Design notes

- Runtime dependencies: **numpy + robot-msgs** (`src/external/robot_msgs`,
  itself numpy-only; Python >= 3.11). scipy appears only in the test extra
  as the rotation oracle.
- The browser stack is vendored into the wheel (`assets/`): uPlot 1.6.30
  (plots) + three.js r160 (last classic-script build; 3D). See
  [`assets/VENDORED.md`](src/traj_compare/assets/VENDORED.md).
  `plots.js` / `viewer3d.js` / `style.css` are authored here.
- Report data is embedded as one JSON block, floats rounded, non-finite →
  `null`; a full two-trajectory 6-DOF report is ~2 MB.
- The percent channel normalizes by the **target's** total path length so
  A/B percent curves are comparable (falls back to each run's own total when
  there is no target, and says so in the section hint).

The end-to-end exercise of this package is
`traj_integration_tests ur-compare` (UR5e, Pinocchio dynamics, A/B
controllers + an intentionally empty Real): see
[`traj_integration_tests/README.md`](../traj_integration_tests/README.md).
