# Grasp coverage — contract (v1, 2026-11-24)

**What it answers:** of everything the gripper *can* do (its jaw range, every approach direction, every roll about the
approach, the area it is offered), how much does this set of grasps actually use, and where did the grasps that
failed sit? One grasp list in; the same numbers out to four viewers.

Zach, Daily Note 2026-11-23 "Coverage Feedback" (`~/zach_brain/Sources/Daily Notes/Daily Note - Nov 23 2026.md`
~l.1300): *"showing where the failures where and not thats super helpful"*, *"I really like this how it shows the size
of the grasps"*, roll *"just like a straight line actually works as well"*, and *"there is the trajectory specific ones
and the grasp specific ones ... Robot_msgs in. Then do the analysis. and then like the viwers out"*. He added *"For the
grasping though I am not entirely sure what you want to do there"*, so the input below is the proposal, proven on real
grasps (our repicks, GraspNet-1Billion).

Prior art this promotes (ideas, reimplemented): the Nov 19 gallery's grasp section
(`/home/bam/robot_metrics/docs/proposals/coverage-2026-11-19/figures_grasp.py`: `repick_positions`, `width_limits`,
`roll_rose`, `sphere_comparison`, `object_imbalance`); DROID's scene-coverage figures (grasp positions in 3-D, coloured);
the trajectory coverage viewer's tool section (docs/COVERAGE.md), whose binning this shares (`coverage/bins.py`).

## Where it lives, and why

`traj_compare.grasp_coverage`, beside `traj_compare.coverage`. A grasp set is the trajectory viewer's tool section
without time: the same position grids anchored at the origin, the same equal-area direction sphere, the same tilt disk,
the same colour rule and the same data-ui workbench writer. One repo means one copy of each (`coverage/bins.py`,
`coverage/matplotlib_view.py`'s colour rule, `coverage/workbench.py`'s `.base` writer); a grasp package of its own
would import all of traj_compare anyway.

## The pipeline

```
robot_msgs in                analysis (numpy only)                          viewers out (each reads ONLY the payload)
Sequence[GraspPose]    ──►   traj_compare.grasp_coverage.analyze_grasps() ──► payload "traj_compare.grasp_coverage/1"
+ an outcome per grasp                                                       ├─ our page   write_grasp_workbench()  (data-ui)
+ the jaw range                                                              ├─ Matplotlib plot_grasp_coverage()    (PNGs)
                                                                             ├─ Viser      serve_grasp_coverage()   (3-D)
                                                                             └─ W&B        log_grasp_coverage()     (scalars)
```

**Every viewer reads the payload, never the grasps** — except the workbench, which also re-bins each grasp on the
payload's own grids so its rail can recount (the parts add back up to the payload exactly; its test is that oracle).

## Python API (`traj_compare.grasp_coverage`)

```python
from robot_msgs.manipulation import GraspPose
from traj_compare.grasp_coverage import analyze_grasps

coverage = analyze_grasps(
    grasps,                   # Sequence[GraspPose] | Mapping[str, GraspPose]; ONE frame (header.frame_id) for all
    *,
    outcomes=None,            # Sequence (same order) | Mapping[name, outcome] | None: "picked" | "failed" |
                              #   "hovered" | "refused" | any other word | None (no outcome: a label, a proposal)
    width_range=None,         # (low_m, high_m): the jaw gap from shut to the open stop; None -> the data's span
    planner_width_range=None, # (low_m, high_m) drawn dashed (what the planner plans into), or None
    symmetric_jaws=True,      # a two-finger grasp at roll r is the one at r + 180°: roll is shown folded to 0..180°
    tags=None,                # Mapping[name, Mapping[str, str | float]] per grasp (run, day, dataset, split ...)
    group_by="outcome",       # what the 1-D histograms stack by: "outcome", "object" or a tag name
    area=None,                # the offered pick area: one box ((x0, y0, z0), (x1, y1, z1)) or a list of boxes
    reference=(0.0, 0.0, -1.0),  # tilt is measured from this approach (default straight down in the frame)
    pixel_m=0.01,             # position pixel edge (a pick area is ~10 cm; the trajectory tool uses 2 cm)
    enough=10, title="", subtitle="",
)
coverage.payload, coverage.numbers
coverage.write_workbench(out_dir)   coverage.plot(out_dir)   coverage.serve_viser()   coverage.log_wandb(run)
```

- **Axes (robot_msgs' gripper convention, `robot_msgs/viz/viser.py` `_gripper`):** the tool frame's **+z is the
  approach** (the direction the gripper moves into the object) and its **x is the jaw axis** (the jaws open along x).
  `pose.position` is where the jaws close.
- Names: the Mapping's keys, else `header.meta["name"]`, else `grasp_<i>`. Order is kept. An empty `object_id` is
  `"(no object)"`.
- `width` is the gap the jaws close to; `pre_grasp_width` the gap they open to before the approach (optional).
- All grasps must share `header.frame_id` (else `ValueError` naming the first mismatch); positions in two frames do not
  add up.

## The angles

- **tilt** = angle between the approach (tool +z) and `reference`; 0 = straight down by default.
- **azimuth** = `atan2(a.y, a.x)` of the approach `a`: which way in the frame's XY the approach leans.
- **roll** = the jaw axis's angle about the approach, counter-clockwise as seen from behind the gripper (from where it
  comes), from the reference grasp's jaw axis carried along the shortest swing that takes `reference` onto the approach.
  The reference grasp's jaw axis is the frame's +x (made perpendicular to `reference`; +y if `reference` is along x).
  For a straight-down grasp, roll is the jaw's heading in the frame's XY (the trajectory viewer's yaw). Range
  (−180°, 180°]; **folded** = roll mod 180° in [0°, 180°) — the same two-finger grasp, jaws swapped.

## The payload `traj_compare.grasp_coverage/1`

Values SI (m, rad); degrees and mm only in viewers. Edges `[low, high, bins]`, linear. 2-D counts flat, C order
(`counts[i * ny + j]` for `shape [nx, ny]`). Every `groups` is `{group: [int] * bins}` in `source.groups` order and
adds up to `counts`.

```text
schema            "traj_compare.grasp_coverage/1"
title, subtitle, back, siblings, enough
source            {"grasps", "frame", "objects": [..], "group_by", "groups": [..], "with_pre_grasp": int,
                   "with_score": int, "jaws": "symmetric" | "asymmetric"}
outcomes          {"order": [..], "counts": {outcome: n}, "closed": ["picked", "failed"], "words": {outcome: str}}
                  # order: picked, failed, hovered, refused, then other words as first seen, then "unknown" (None)
gripper           {"low", "high", "source": "limit" | "data", "planner_low", "planner_high"}  (planner_* null if none)
grasps            [{"name", "object_id", "outcome", "group", "tags", "position": [x, y, z], "approach": [x, y, z],
                    "jaw": [x, y, z], "width", "pre_grasp_width", "score", "tilt", "azimuth", "roll"}]
                  # every grasp up to 20 000 (evenly picked past that: "grasps_subsampled": the count kept, else null)
position          {"pixel_m", "bounds": [[xmin, ymin, zmin], [xmax, ymax, zmax]],
                   "area": [[[x0, y0, z0], [x1, y1, z1]], ...] | null,
                   "projections": {"xy" | "xz" | "yz": {"origin": [u0, v0], "shape": [nu, nv], "samples": flat,
                                   "groups": {group: flat}, "area": flat [0|1] | null}}}
                  # a pixel is in the area when its centre is inside a box's face (u, v) rectangle
width             {"edges": [lo, hi, 72], "counts", "groups", "p001", "p999", "min", "max",
                   "span_pct",       # (p999 - p001) / (high - low) * 100: the share of the jaw range used
                   "peak_pct",       # p999 / high * 100: the widest grasp as a share of the open stop
                   "outside",        # grasps past the stated range (source "limit" only)
                   "beyond_edges"}   # past the histogram's edges (low/high ± 8 % of the range)
pre_grasp_width   same shape over the grasps that have one, or null
width_tilt        {"x_edges": width edges with 36 bins, "y_edges": [0, pi, 18], "shape": [36, 18], "counts"}
orientation       {"reference": [x, y, z],
                   "sphere": {"rings": 12, "sectors": 24, "counts": flat * 288, "groups"},   # the approach, equal area
                   "tilt_azimuth": {"tilt_edges": [0, pi, 18], "azimuth_edges": [-pi, pi, 36], "shape": [18, 36],
                                    "counts"},
                   "tilt": {"edges": [0, pi, 36], "counts", "groups"},
                   "roll": {"edges": [-pi, pi, 72], "counts", "groups"},
                   "roll_folded": {"edges": [0, pi, 36], "counts", "groups"},
                   "roll_shown": "roll_folded" | "roll",                       # folded when symmetric_jaws
                   "tilt_roll": {"tilt_edges": [0, pi, 18], "roll_edges": the shown roll's edges, "shape", "counts"}}
score             {"edges": [min, max, 40], "counts", "groups"} | null    # the detector's own score, when any has one
objects           [{"object_id", "grasps", "outcomes": {outcome: n}, "picked_pct": float | null,
                    "width_span_pct", "directions_visited_pct", "roll_visited_pct", "pixels_xy"}]  # most grasps first
numbers           [{"key", "label", "value": float, "unit"}]    # all finite; W&B logs exactly these
```

Headline `numbers` keys: always `grasps`, `objects`, `width_span_pct`, `width_peak_pct`, `directions_visited_pct`,
`tilt_median_deg`, `tilt_max_deg`, `roll_visited_pct`, `position_pixels_xy`, `object_evenness_pct`,
`largest_object_pct`; with a stated range `width_outside`; with outcomes: `closed`, and `picked_pct` when any grasp
closed; with pre-grasp widths `pre_grasp_width_peak_pct`; with `area`: `area_visited_pct` and, when any closed,
`area_closed_pct`.

## Our page: the workbench (`write_grasp_workbench(coverage, grasps, out_dir, ...)`)

data-ui's stock `<data-workbench>` (data-ui `docs/CONTRACT.md` §52 coverage views, §53 scope + workbench, §32 scene3d
layers): WHY not a hand-rolled page — Zach 2026-11-24, "the nice thing with data-ui is it's the common visual language",
and the trajectory workbench already proved the pattern. **The atomic unit is a grasp**: the rail filters grasps
(Object, Outcome, then the tags, then width / tilt / score ranges), and every coverage figure adds up the kept grasps'
part rows (`coverage.sum: grid`), so a tick ("failed") recounts every tab.

- Files: `grasps.json` (one row per grasp: name, object, outcome, tags, mm / degree columns, the approach arrow's tail
  50 mm back, and `t: 0` — data-ui's scene3d drops a row without a numeric t), `parts.json` (one row per grasp ×
  coverage figure: a one-hot histogram or one sparse cell, `at` + `samples`), `grasp_coverage.base`, `index.html`,
  `embed.html` (1000 × 680 host slot), `vendor/data-ui/` (unless `kit=`).
- Tabs: **Overview** (where the gripper closed, top view by outcome; jaw width against the claw; grasps per object;
  which way it approaches; roll), **Position** (3-D: a point per grasp and an arrow along its approach, coloured by
  outcome, the offered areas' outer box as the workspace; top and side scatter; the three faces as counts),
  **Gripper** (jaw width and pre-grasp opening against the range; every histogram as data-ui's stock strips; width ×
  tilt), **Orientation** (pointing disk, equal-area sphere, roll as a straight line, tilt, tilt × roll), **Objects**
  (grasps and outcome share per object), **Grasps** (the table).
- The big 1-D histograms (width, pre-grasp, roll, tilt) are Vega-Lite charts over `grasps.json` on the payload's own
  bins, stacked by outcome, the range in red (solid the open stop, dashed the planner's span), grey past it. WHY not
  data-ui's `coverage-hist` there: its strips are 58 px tall (made for stacks of limit bars) and the width figure is
  the one Zach singled out; the stock strips stay as one panel ("Every histogram against its range"), re-summed from
  the parts like every coverage figure. The bars square their ends (`cornerRadiusEnd: 0`): Vega-Lite 6.5 drops a
  binned bar's x under data-ui's theme radius.
- Not in the workbench (yet): the area mask on the projections (a per-grasp part cannot carry the whole set's area;
  the same gap as the trajectory workbench's reachable mask) — the area shows as the 3-D workspace box and in the PNGs.
- Outcome colours (`grasp_coverage/colours.py`, one table for all four viewers): picked = data-ui slot 1 (blue
  `#2a78d6`), failed = slot 2 (orange), hovered = muted grey, refused = slot 4 (amber), unknown = slot 7 (violet);
  another word takes pink, then teal — never green or red first. Blue / orange / grey are the Nov 19 gallery's.
- `grasp_workbench_rows(coverage, grasps)` returns (grasp rows, part rows) without writing.

## The other viewers

- **Matplotlib** `plot_grasp_coverage(payload, out_dir, *, cmap="viridis", reverse=False, scale="linear") ->
  list[Path]`: `positions.png` (top + side, a dot per grasp by outcome, the area), `position-density.png` (xy / xz / yz
  counts, outside the area grey), `width.png` (jaw width and pre-grasp width stacked by group against the range: grey
  beyond, solid red the range, dashed red the planner's), `roll.png` (a straight-line histogram, the shown roll),
  `pointing.png` (tilt disk), `sphere.png` (equal-area approach map), `width-tilt.png`, `objects.png`. The colour rule
  is `coverage.matplotlib_view`'s (= `assets/coverage_color.js`).
- **Viser** `serve_grasp_coverage(payload, *, port=0) -> viser_3d_viewer.Viewer`: a two-finger gripper glyph per grasp
  (robot_msgs' glyph: jaws along x, approach +z) coloured by outcome with a checkbox per outcome, the area boxes, and the
  approach sphere coloured by count (colormap dropdown + Reverse). Prints `READY <url>`.
- **W&B** `log_grasp_coverage(run, payload, *, prefix="grasp_coverage/") -> dict`: `run.summary[prefix + key]` for every
  `numbers` entry and `run.config[prefix + "title"]`. Scalars only (Zach 2026-11-21).
