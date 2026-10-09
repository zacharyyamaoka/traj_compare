# traj_compare

Turn-key A/B trajectory comparison viewer. Feed it a **target** and any
number of **situations** — sim A vs sim B, sim vs real, yesterday vs today —
and it writes **one self-contained static `report.html`**: no server, no CDN,
no install at view time. Open it from disk, keep it forever next to the run
data it describes.

Built 2026-07-28 as the second generation of the trajectory comparison
viewer (the first lives in `traj_integration_tests/report.py`), from the
directive in [`traj_integration_tests/Logs.md`](../traj_integration_tests/Logs.md).

## What the report shows

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
| Joint q / qd / qdd / τ | per joint, target + every situation overlaid | q on, rest off |
| Joint error | per joint, `q − target(t)` | off |
| TCP pose | x, y, z [m], rx, ry, rz [deg] (extrinsic xyz, unwrapped) | off |
| TCP error | \|Δp\| [mm], rotation error [deg] vs target at the same instant | on |
| Path progress | rows path/path_d/path_dd × columns **%** (of target path length), **XYZ** arc length, **RPY** accumulated rotation, **Vec[label]** signed progress along each configured direction | on |
| Videos | one card per situation with a `video`, always played/seeked together by the transport | on |
| 3D paths | interactive three.js viewer — see below | on |

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
- Situations may live on different time grids; display channels are
  resampled onto the target's grid (nulls outside a run's own span, so a
  short run ends in a visible gap, not a fabricated plateau). Error channels
  are computed exactly on each situation's native grid first.
- No `fk` and no `poses` → the cartesian sections are simply omitted;
  joint-space comparison still works.
- `poses` may be passed directly per situation (e.g. mocap) instead of `fk`.
- `Comparison.statistics` accepts a display-ready `ReportTable`; otherwise a
  standard error table is generated automatically.
- `summary=` and `insights=` accept `ReportPage` objects. A page may contain
  `MetricCard`, `BarChart`, `ReportTable`, and `Insight` blocks.

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
uv run --extra test pytest -q          # 31 tests
```

`tests/test_rotations.py` pins the rotation helpers against scipy;
`tests/test_analysis.py` pins channel identities (arc length of a line,
percent normalization by target total, vec projection, null padding, empty
situations); `tests/test_report.py` checks the report is self-contained and
survives `</script>` in user text.

## Design notes

- Runtime dependency: **numpy only**. scipy appears only in the test extra
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
