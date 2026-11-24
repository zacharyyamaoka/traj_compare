# Trajectory coverage — contract (v1, 2026-11-23)

**What it answers:** of everything the robot *can* do (its limits), how much does this set of trajectories actually
visit — per joint, across joints, in the workspace and in tool orientation? One trajectory or a whole dataset in;
the same numbers out to four viewers.

Zach, Daily Note 2026-11-23 "Coverage Feedback" (`~/zach_brain/Sources/Daily Notes/Daily Note - Nov 23 2026.md` ~l.1150):
*"we should have like trajectory Coverage Viewer where you can put in like datasets or single trajectories ... a page
you can see standalone or just quickly get there from the traj compare stuff"*, and *"Robot_msgs in. Then do the
analysis. and then like the viewers out ... Matplotlib, Viser, weights and biases, our own custom viewer"*.

Prior art this promotes (ideas and palette, reimplemented here, not imported): the Nov 19 coverage gallery
(`/home/bam/robot_metrics/docs/proposals/coverage-2026-11-19/`: `coverage.py` Grid / limit_use / sphere_cell,
`figures_*.py`), `arm_motion_bench/src/arm_motion_bench/coverage.py` (the UR5e PNG figures), BAM Reach's colormap
control (`/home/bam/robot_reach/src/robot_reach/codes.py` `COLORMAPS`, "Reverse (high = dark)").

## The pipeline

```
robot_msgs in            analysis (numpy only)                  viewers out (each reads ONLY the payload)
JointTrajectory(s)  ──►  traj_compare.coverage.analyze()  ──►  payload dict "traj_compare.coverage/1"
PoseTrajectory(s)                                               ├─ custom page   write_coverage_page()   (HTML, no server)
JointLimits                                                     ├─ Matplotlib    plot_coverage()         (PNGs)
                                                                ├─ Viser         serve_coverage()        (3D, viser_3d_viewer)
                                                                └─ W&B           log_coverage()          (summary scalars only)
```

**Rule: every viewer reads the payload dict, never the trajectories.** The payload is the contract; a viewer that needs
something the payload lacks gets it added to the payload (and to this file), never recomputed on the side. So the four
viewers can never disagree.

## Python API (`traj_compare.coverage`)

```python
from traj_compare.coverage import analyze, write_coverage_page, plot_coverage, serve_coverage, log_coverage

coverage = analyze(
    trajectories,            # JointTrajectory | Sequence[JointTrajectory] | Mapping[str, JointTrajectory]
    *,
    tool=None,               # same shape as `trajectories` (PoseTrajectory each, base frame) or None
    limits=None,             # JointLimits; default: the first trajectory's .limits; a joint with no bound -> data span
    planner_limits=None,     # JointLimits drawn dashed (the planner's / software bound), or None
    tags=None,               # Mapping[name, Mapping[str, str | float]] per trajectory (split, kind, rung ...)
    group_by=None,           # a tag name: 1-D histograms are also split by its values (legend says so)
    title="", subtitle="",
    prismatic=(),            # joint names shown in mm (default: every joint revolute, shown in deg)
    reachable=None,          # (M, 3) TCP points the robot can reach (base frame) -> the Cartesian denominator
    tool_reference=(0.0, 0.0, -1.0),  # tilt is measured from this base-frame axis (default: straight down)
    enough=10,               # a cell is "sufficient" with >= this many samples
)
coverage.payload             # the dict (JSON-safe: json.dumps(allow_nan=False) works)
coverage.numbers             # {key: float} headline scalars (== payload["numbers"] as a dict)
coverage.write_page(path, back=[("Dataset", "../index.html")], siblings=[...])  # -> Path (calls write_coverage_page)
coverage.plot(out_dir)       # -> list[Path] PNGs (calls plot_coverage)
coverage.serve_viser(port=0) # -> the viser_3d_viewer Viewer (calls serve_coverage)
coverage.log_wandb(run)      # -> dict of what was logged (calls log_coverage)
```

- A single `JointTrajectory` is a dataset of one. Names: the Mapping's keys, else `header.meta["name"]`, else
  `traj_<i>`. Trajectory order is kept (it is the "growth" order).
- Missing `velocities` / `accelerations` and the jerk (`qddd`, always derived) are slopes on the trajectory's own clock:
  central differences inside, a plain one-sided difference at each end (numpy's second-order edge stencil invents
  overshoot at sample 0 — tests/test_coverage_edges.py). The tool speed uses the same rule. SI everywhere inside; degrees and mm only in viewers (payload carries `display.scale/unit`).
- All trajectories must share `joint_names` (else `ValueError` naming the first mismatch).
- `python -m traj_compare.coverage <file.npz|dir ...> --out <dir> [--tool <file.npz|dir ...>] [--title T]` reads robot_msgs
  `.npz` messages (`robot_msgs._core.load_npz`) and writes `<dir>/index.html` + `<dir>/coverage.json`.

## The payload `traj_compare.coverage/1`

Edges are always linear and written `[low, high, bins]` (WHY linear: Zach 2026-11-19, "I feel it would be better to just
have a linear scale" — equal cells, so a visited % is a share of the space). 2-D/3-D count arrays are **flat, row-major**
lists of ints with their `shape` (C order: `counts[i * ny + j]` for `shape [nx, ny]`). Values are SI.

```text
schema            "traj_compare.coverage/1"
title, subtitle   str
back              [[label, href], ...]                      breadcrumb links (set by write_page)
siblings          [{"label", "href", "group", "current"}]  other pages of the same dataset (subsets, rungs)
enough            int                                       the `enough` threshold: a cell is "sufficient" with >= this
                                                            many samples (sufficient_pct, the page's "enough" scale)
source            {"trajectories": int, "samples": int, "duration_s": float, "rate_hz": float | null,
                   "group_by": str | null, "groups": [str, ...]}
joints            [{"name", "kind": "revolute"|"prismatic", "display": {"scale": 57.29.. | 1000, "unit": "deg"|"mm"}}]
signals           ["q", "qd", "qdd", "qddd"]
units             {"q": "rad"|"m", ...} per joint kind -> keyed "revolute"/"prismatic": {"q": "rad", "qd": "rad/s", ...}

limits            {joint: {signal: {"low", "high", "source": "limit"|"data", "kind": "physical"|"software"|null}}}
                  q: [min_position, max_position]; qd/qdd/qddd: [-max_*, +max_*]; no bound -> the data's p0.1..p99.9
                  widened x1.15 with source "data" (a viewer says "no limit stated")
planner_limits    same shape (only the signals given) or null

hist              {joint: {signal: {
                     "edges": [lo, hi, 120],         # limit span +- 8 % margin, so overshoot shows
                     "counts": [int] * 120,
                     "groups": {group_value: [int] * 120} | null,   # when group_by is set
                     "p001", "p999", "min", "max",   # data percentiles 0.1 / 99.9 and extremes
                     "span_pct",                     # (p999 - p001) / (high - low) * 100
                     "peak_pct",                     # max(|p001|, |p999|) / max(|low|, |high|) * 100 (qd, qdd, qddd);
                                                     #   for q: share of the range from the centre reached, same rule
                     "outside": int,                 # samples beyond the limit (low/high), source "limit" only
                     "beyond_edges": int             # samples past the histogram's edges: not in any bin, so a viewer
                                                     #   can say "N samples off the chart" instead of hiding them
                  }}}

planes            {joint: {"q_qd" | "qd_qdd" | "q_qdd": {
                     "x": "q", "y": "qd",
                     "x_edges": [lo, hi, nx], "y_edges": [lo, hi, ny],   # EXACTLY the limit span (no margin)
                     "shape": [nx, ny],                                  # q 36, qd 24, qdd 24 bins
                     "samples": flat [int],          # samples per cell
                     "paths": flat [int],            # distinct trajectories through the cell (episode-weighted)
                     "max_other": flat [float|null], # q_qd only: max |qdd| reached in the cell (rad/s^2), null = unvisited;
                                                     #   the whole field is null on qd_qdd and q_qdd
                     "visited_pct", "sufficient_pct", "evenness_pct",  # of all nx*ny cells; evenness = exp(H)/cells
                     "outside": int
                  }}}

slabs             {joint: {"x": "q", "y": "qd", "by": "qdd", "by_edges": [lo, hi, 5],
                           "shape": [5, nx, ny], "samples": flat, "visited_pct": [5 floats]}}
                  # the end slabs also hold samples past the qdd limit, so the slabs add up to the q_qd plane

paths             {joint: [[[q...], [qd...], [qdd...]] per trajectory]}   # <= 400 points each, evenly picked
                  # (fewer for a big dataset: ~20 000 points per joint in all, at least 32 each); values to 3
                  # significant figures of the limit span. tool.spaghetti uses the same budget, in metres to 0.1 mm

parallel          {signal: {"axes": [joint names], "height": 128, "width": 48,
                            "range": "limit",            # every axis runs low limit (0) .. high limit (1)
                            "gaps": [flat [int] * (48*128) per adjacent joint pair],   # line density, row-major [x][y]
                            "subsampled": int | null}}  # q, qd, qdd; subsampled = samples drawn (evenly picked)
                                                         #   when there were more than 50 000, null = every sample

trajectories      [{"name", "tags": {..}, "duration_s", "samples",
                    "span_pct": {joint: {signal: float}},          # this trajectory's own span_pct
                    "new_cells": int}]                             # q_qd cells (all joints) it was first to visit
growth            {"visited_pct": [float per trajectory added, in order],
                   "shuffled": {"mean": [...], "p10": [...], "p90": [...]}}   # 32 shuffles, seed 0

tool              null | {
                    "frame": str, "pixel_m": 0.02, "voxel_m": 0.05,
                    "bounds": [[xmin, ymin, zmin], [xmax, ymax, zmax]],     # data (and reachable) bounds, padded
                    "projections": {"xy" | "xz" | "yz": {
                        "origin": [u0, v0], "shape": [nu, nv],              # pixel (i, j) covers origin + [i, i+1) * pixel_m
                        "samples": flat [int], "paths": flat [int],          # Strava: distinct trajectories per pixel
                        "max_speed": flat [float|null],                      # m/s, null = never visited
                        "reachable": flat [0|1] | null}},                    # from `reachable`
                    "voxels": {"origin": [x0, y0, z0], "size": voxel_m,
                               "cells": [[ix, iy, iz, samples, paths, max_speed], ...],
                               "reachable": [[ix, iy, iz], ...] | null},
                    "spaghetti": [[[x, y, z], ...] per trajectory],          # <= 400 points each
                    "speed": {"edges": [0, vmax, 60], "counts": [...]},      # tool linear speed histogram
                    "orientation": {
                        "reference": [x, y, z],                              # tool_reference
                        "sphere": {"rings": 12, "sectors": 24, "counts": flat [int] * 288},
                                  # tool z axis in the BASE frame; ring k covers base-z in equal bands of [-1, 1]
                                  # (equal area), sector s covers azimuth [-pi + s*2pi/24, ...)
                        "tilt_azimuth": {"tilt_edges": [0, pi, 18], "azimuth_edges": [-pi, pi, 36],
                                         "shape": [18, 36], "counts": flat},
                        "tilt_yaw": {"tilt_edges": [0, pi, 18], "yaw_edges": [-pi, pi, 36], "shape": [18, 36], "counts": flat},
                        "tilt": {"edges": [0, pi, 36], "counts": [...]},
                        "yaw": {"edges": [-pi, pi, 72], "counts": [...]}}}
                    # tilt    = angle between the tool z axis and `reference` (0 = tool along reference)
                    # azimuth = atan2(z_tool.y, z_tool.x): which way (in base XY) the tool z leans
                    # yaw     = atan2(x_tool.y, x_tool.x): heading of the tool x axis in base XY (the jaw yaw)

numbers           [{"key", "label", "value": float, "unit": str}]   # headline scalars, all finite; W&B logs exactly these
```

Headline `numbers` keys (always present; tool ones only with `tool`):
`trajectories`, `samples`, `duration_s`, `q_span_median_pct`, `q_span_min_pct`, `qd_peak_max_pct`,
`qdd_peak_max_pct`, `q_qd_visited_mean_pct`, `qd_qdd_visited_mean_pct`; with tool: `tool_pixels_xy`,
`tool_voxels_visited`, `tool_voxels_reachable_pct` (only with `reachable`), `tool_speed_p99_m_s`,
`tool_directions_visited_pct`, `tool_tilt_max_deg`.

## The custom page (`write_coverage_page(payload, path, *, back=(), siblings=())`)

One self-contained `.html` (inline JS/CSS, three.js inlined from `assets/three.min.js`, no CDN, no server). Opens from
disk. It must look like a traj_compare page (same fonts, `style.css` tokens) and follow Zach's UI rules: one calm answer
first, detail on demand; plain-word titles phrased as the question they answer; every colour and every line explained
in a visible legend (Zach 2026-11-23: *"This is good as long as you show the legend of the meaning of the lines"*).

Stable selectors (the browser acceptance test reads these):

- `[data-cov-page]` root; `[data-cov-title]`; `[data-cov-numbers]` the headline numbers row.
- `[data-cov-nav] [data-cov-tab="overview|limits|joint|joints|cartesian|orientation|space3d|trajectories"]`;
  the visible section `[data-cov-view="<same id>"]`. Tabs with nothing to show (no tool) are omitted. `#tab=<id>` opens one;
  the last tab is remembered (localStorage, try/catch).
- Global controls, in a sticky bar: `select[data-cov-cmap]` with options exactly `viridis, magma, plasma, inferno,
  cividis` (BAM Reach's set, viridis default, the same 17 stops); `input[type=checkbox][data-cov-reverse]` "Reverse
  (high = dark)"; `select[data-cov-scale]` with `linear` (default — *"Linear to me is BY far the most informative"*),
  `log`, `equalized`, `visited`, `enough`; `select[data-cov-joint]` (the joint the per-joint views show). Each remembered.
  Empty cells are always white (or the page background), cells outside the limit grey — never a colormap colour.
- Every figure is a `[data-cov-figure="<id>"]` with a `[data-cov-legend]` that names every mark it draws, and a
  `<details>` "How to read this" with the one-paragraph explanation and the prior art.
- Every heatmap draws to a `<canvas data-cov-heat>`; changing `data-cov-cmap` / `data-cov-reverse` / `data-cov-scale`
  repaints it (its pixels change). A colorbar with the scale's real numbers sits beside it.
- Every three.js renderer is created with `preserveDrawingBuffer: true` (the test reads its pixels) and draws on load
  of its tab; 3-D views get orbit / zoom / pan and a "fit" on double-click, z up.

Views (figure ids):
- **overview**: `ridgeline` (every joint's q, qd, qdd as % of its limit, one row per joint, tidy), `summary-table`.
- **limits**: `limit-bars` (per joint: q, qd, qdd, qddd histograms against grey limit band, solid red physical limit,
  dashed red planner limit, black ticks p0.1/p99.9; groups drawn in named colours with a legend).
- **joint** (per selected joint): `heat-q-qd`, `heat-qd-qdd`, `slabs` (q x qd per qdd slab, side by side),
  `spaghetti` (every trajectory's (q, qd) path at low opacity, hover highlights one), `envelope` (max |qdd| per q
  vs the box limit).
- **joints**: `parallel` (line-density image across all joints, q / qd / qdd switch), `growth` (visited % as trajectories
  are added, with the shuffled band).
- **cartesian** (with tool): `projections` (xy, xz, yz side by side, samples / paths switch), `tool-speed` (max tool
  speed per xy pixel), `voxels-3d` and `spaghetti-3d` (three.js, orbit, a count threshold slider for voxels).
- **orientation** (with tool): `tilt-map` (polar disk: centre = along the reference, radius = tilt, angle = azimuth),
  `tilt-yaw` (tilt x yaw heatmap), `sphere-3d` (three.js sphere, cells coloured by count), `yaw-line` (yaw histogram
  as a straight line, not a rose).
- **space3d**: 3D proposals behind a bottom-right drop-down `select[data-cov-proposal]` that remembers the pick
  (Zach's prototype-switch rule): at least `height-q-qd` (q x qd counts as a height map), `terrain-qdd` (height = max
  |qdd| reached over (q, qd)), `hist-over-trajectories` (per-trajectory histogram surfaces, TensorBoard style),
  `slab-stack` (the qdd slabs stacked in 3D), `joint-skyline` (all joints' histograms as one 3D ridgeline),
  `workspace-terrain` (xy floor, height = paths through the pixel, colour = max speed; tool only), `direction-hedgehog`
  (sphere with spikes = samples per direction; tool only). Each proposal has a one-line "what it shows / when it wins".
- **trajectories**: `table` (one row per trajectory: name, tags, duration, span % per joint, new cells), click a row to
  highlight it in the spaghetti views.

## The workbench (`traj_compare.coverage.workbench`, 2026-11-24)

The same figures as data-ui's stock `<data-workbench>` (data-ui `docs/CONTRACT.md` §52 coverage views, §53 scope and
workbench): a filter rail of **trajectories** (Dataset first, then split, kind, tags, ranges), tabs that switch dashboards
(Overview, One joint, Limits, Tool position, Tool orientation, Trajectories), one gear for the heatmap colours, and a
record's Open in Rerun. Every figure re-sums the part rows of the trajectories the rail keeps (`coverage.sum: grid`), so a
tick recounts every tab. It sits beside the hand-rolled page (which keeps its 3-D views, growth and parallel coordinates);
it does not replace it. Zach, 2026-11-24: "the atomic unit here is trajectories"; dev/holdout "will apply then to all of
the datasets you include"; compact enough to drop into any app.

```python
from traj_compare.coverage.workbench import write_workbench, write_trajectory_rrd
coverage = analyze(trajectories, tool=poses, tags=tags, group_by="dataset")     # tags: {"dataset", "split", "kind", ...}
for name in trajectories:
    write_trajectory_rrd(out / f"rrd/{name}.rrd", name, trajectories[name], tool=poses[name])  # optional
write_workbench(coverage, trajectories, out, tool=poses, title="UR5e", rrd_for=lambda name: f"rrd/{name}.rrd")
# python -m traj_compare.serve out   ->  /index.html, /embed.html  (http needed; Open in Rerun is its endpoint)
```

- Inputs: the `analyze()` result and the **same** `trajectories` / `tool` it was given, in the same order (else
  `ValueError`). Every part is binned with analysis.py's own functions on the payload's own grids, so the parts of every
  trajectory add back up to the payload exactly (planes' samples, paths and max |qdd|; histograms and their groups;
  projections' samples, paths and max speed; the tool speed histogram; the direction sphere, the pointing disk, tilt ×
  yaw). `tests/test_coverage_workbench.py` is that oracle, plus `data-ui check` on the `.base` and a headless-Chrome run.
- Files: `trajectories.json` (one row per trajectory: name, every tag, `rrd`, duration, samples, new cells, each joint's
  range used, the tool's path length, top speed and largest tilt), `parts.json` (one row per trajectory × figure; a big grid
  is sparse, `at` + `samples`), `coverage.base`, `index.html`, `embed.html` (the page in a host app's 1000 × 680 slot),
  `vendor/data-ui/` (data-ui `main`, vendored by `data-ui vendor`; `kit="<href>"` reuses one instead, `vendor=` picks a ref).
- `workbench_rows(coverage, trajectories, tool=, rrd_for=)` returns the two row lists without writing anything.
- The direction grids as §52 rows: the pointing disk is `coverage-polar` (x azimuth, y tilt); the equal-area sphere is a
  plane of azimuth × the tool axis's z (its rings are equal bands of z: Lambert's cylindrical equal-area map); tilt × yaw
  is a plane with yaw along x.
- Not in it (yet): the projections' reachable mask (a per-trajectory part cannot carry the whole set's reach; data-ui would
  need a whole-set layer row the rail does not filter), the 3-D views, the growth curve, parallel coordinates, slabs.
- The UR5e case: `arm_motion_bench/docs/build_ur_workbench_1124.py`, all four datasets in one page.

## The other viewers

- **Matplotlib** `plot_coverage(payload, out_dir, *, cmap="viridis", reverse=False, scale="linear") -> list[Path]`: one
  PNG per figure id above that is 2-D (`limit-bars.png`, `ridgeline.png`, `heat-q-qd-<joint>.png`, `slabs-<joint>.png`,
  `parallel-q.png`, `projections.png`, `tool-speed.png`, `tilt-map.png`, `tilt-yaw.png`, `growth.png`), each with the
  same title, legend and colormap rules. matplotlib is imported only inside this module.
- **Viser** `serve_coverage(payload, *, port=0, title=...) -> viser_3d_viewer.Viewer`: the 3-D views (voxels coloured by
  count with a threshold slider, spaghetti, direction sphere, the q-qd-qdd height map) with the same colormap dropdown +
  Reverse checkbox, via `viser_3d_viewer` (no logo, ViewCube, loopback, asserted port). Prints `READY <url>`.
- **W&B** `log_coverage(run, payload, *, prefix="coverage/") -> dict`: `run.summary[prefix + key] = value` for every
  `numbers` entry, plus `run.config[prefix + "title"]`. Scalars only — no tables, media or histograms (Zach 2026-11-21:
  W&B gets summary statistics; media lives in the page / Rerun / the ledger). wandb imported only inside.

## traj_compare integration

- `write_dataset_report(..., coverage=True)` also writes `output_dir/coverage/index.html` + `coverage.json` over the
  site's distinct targets (each target's reference once; TCP from `poses` when given), with `back` pointing to the
  dataset page; the Dataset level shows a `a[data-tc-coverage-link]` "Coverage" link to it. `coverage=False` (default):
  today's page, no link.
