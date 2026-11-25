# Record coverage — contract (v1, 2026-11-24)

**What it answers:** given any list of records (frozen dataclasses, robot_msgs messages included, or plain mappings
read from a JSON log), how well does the set cover the space its fields declare? Per field: the values against the
declared range, the class balance of every categorical field, the missing values; across fields: how much of chosen
2-D planes is visited; across the set: is more data still adding coverage? One list in, one payload out, the same four
viewers as the trajectory family (data-ui page, Matplotlib, Viser, W&B).

Zach, Daily Note 2026-11-23 "Coverage Feedback": *"there are like the generic ML dataclass visualization I think thats
one viewer we can have. Then there is the trajectory specific ones and the grasp specific ones"*, and *"Robot_msgs in.
Then do the analysis. and then like the viewers out"*. Nov 19: *"I think the key prior art is from the ML community …
Robotics dataset analyzer is basically like the stable sub assembly here."*

The three families: **records** (this file, any dataclass), **trajectories** (`docs/COVERAGE.md`, `traj_compare.coverage`),
**grasps** (`traj_compare.grasp_coverage`). They share the colour rule (`coverage/matplotlib_view.py`, a mirror of
`assets/coverage_color.js`), the legend rules and data-ui's stock coverage views (data-ui `docs/CONTRACT.md` §52, §53).

Prior art (ideas, reimplemented, not imported): TFDV / Facets Overview (a statistics row per feature, the schema's
domain as the range, missing and class counts), the Nov 19 gallery's generic-ML cards
(`robot_metrics/docs/proposals/coverage-2026-11-19/figures_dataset.py`: imbalance, novelty, held-out support,
rarefaction), ecology's species-accumulation curve and Chao1 for "will more of the same help?", Hill numbers for
evenness. Not taken: TFDV itself (needs TensorFlow and protobuf schemas; the schema here is the dataclass).

## The pipeline

```
records in                analysis (numpy only)                        viewers out (each reads ONLY the payload)
Sequence[dataclass]  ──►  traj_compare.record_coverage.analyze()  ──►  payload "traj_compare.record_coverage/1"
Sequence[Mapping]                                                     ├─ data-ui workbench  write_workbench()  (HTML)
                                                                      ├─ Matplotlib         plot_records()     (PNGs)
                                                                      ├─ Viser              serve_records()    (3-D, when xyz)
                                                                      └─ W&B                log_records()      (summary scalars)
```

**Rule: every viewer reads the payload, never the records** (the trajectory family's rule). The one exception is the
workbench's part rows, which are counted from the records with this module's own bin functions on the payload's own
edges, and must add back up to the payload exactly (a test is that oracle).

## Python API (`traj_compare.record_coverage`)

```python
from traj_compare.record_coverage import analyze

coverage = analyze(
    records,               # Sequence of dataclass instances (any depth), robot_msgs messages, or Mappings
    *,
    ranges=None,           # {field: (low, high)}: a declared range that wins over the class's
    choices=None,          # {field: [level, ...]}: declared classes, in order (unseen ones count as missing classes)
    space=None,            # a robot_msgs Space: its array bounds declare the components of array fields
    fields=None,           # only these fields (flattened names), in this order; default: every field
    pairs=None,            # [(x, y), ...] number fields for 2-D coverage; default: every pair of the first 4 ranged ones
    group_by=None,         # a category field: histograms stack by it, class bars split by it (a legend names it)
    split=None,            # a category field (dev / holdout) for held-out support ...
    reference=None,        # ... and its reference level (default: the first level)
    xyz=None,              # three number fields for the 3-D view (Viser); default: the first 3-vector field
    id_field=None,         # the field that names a record; default: the first text field whose values are all unique
    title="", subtitle="",
    enough=10,             # a cell is "sufficient" with >= this many records
    bins=40,               # cells inside a declared range, per number field (a whole-number field: one per integer, to 60)
    grid=24,               # cells per axis of a pair plane
)
coverage.payload           # the dict (JSON-safe: json.dumps(allow_nan=False) works)
coverage.numbers           # {key: float} headline scalars
coverage.write_page(out_dir)       # data-ui workbench (calls workbench.write_workbench)
coverage.plot(out_dir)             # PNGs (calls matplotlib_view.plot_records)
coverage.serve_viser(port=0)       # the house viser_3d_viewer (calls viser_view.serve_records)
coverage.log_wandb(run)            # summary scalars (calls wandb_log.log_records)
```

`python -m traj_compare.record_coverage <file.jsonl|file.json ...> --out <dir> [--group-by F] [--split F] [--pair X Y]`
reads JSON-lines / JSON-list records as Mappings and writes `<dir>/index.html` (the workbench) + `<dir>/coverage.json`.

### Fields: how a record becomes columns

- A dataclass's fields in declaration order, then its public `@property` values (computed: `n_points`), skipping a
  property that raises. A nested dataclass or Mapping is flattened with dots (`pose.position.x`, `meta.bin`). A tuple,
  list or numpy array of at most 4 numbers becomes one column per component (`tcp_base_m[0]`, … `[2]`); anything longer
  or ragged becomes its length (`len(keyposes)`), kind `number`, source `length`. Deeper than 4 levels is cut and said.
- **Kinds:** `number` (int or float, never bool), `category` (bool, str, enum, or a number with declared choices),
  `text` (a str field with more than 24 distinct values and more than half its values distinct: an identifier; its
  distinct count and duplicates are reported, no figure). None, NaN and a missing key are **missing**, never a value.
- **The declared range, first wins:** `ranges=` (source `given`); the record's own `Value(low=, high=)` (source
  `declared`; records that disagree take the union, and the field says so); the dataclass field default's `Value`
  (source `declared`: the class declares the space, instances hold measurements); `space=` array bounds for a
  component (source `declared`); else the data's p0.1 … p99.9 widened ×1.15, source `data` ("no range stated" in every
  viewer; never drawn as a limit). Declared choices: `choices=`, then `Value(choices=)`, then an `Enum`'s members, then
  `(False, True)` for a bool; else the levels seen, commonest first (source `data`).
- **Units:** `Value`'s unit, else the name's suffix (`_rad`, `_deg`, `_mm`, `_m`, `_m_s`, `_s`, `_kg`, `_n`, `_pct`).
  SI in the payload; viewers show `value × display.scale` in `display.unit`. Radians are shown in degrees
  (Zach 2026-11-11: angles in degrees), every other unit as it is.

## The payload `traj_compare.record_coverage/1`

Edges are linear and written `[low, high, bins]`; 2-D counts are flat, C order (`counts[i * ny + j]`), as the
trajectory payload.

```text
schema            "traj_compare.record_coverage/1"
title, subtitle   str
enough            int
source            {"records": int, "fields": int, "group_by": str|null, "groups": [str], "split": str|null,
                   "reference": str|null, "id_field": str|null, "notes": [str]}        # notes: cut depth, unions ...
fields            [{"name", "label", "kind": "number"|"category"|"text", "unit": str|null,
                    "display": {"scale": float, "unit": str|null}, "origin": "field"|"property"|"component"|"length",
                    "present": int, "missing": int, "missing_pct": float}]
hist              {field: {                             # number fields
                     "edges": [lo, hi, n],              # the range +- 10 % margin (n = bins + 2 x margin bins), so the
                                                        #   limits fall exactly on bin edges and overshoot shows
                     "low", "high", "source": "given"|"declared"|"data", "integer": bool,
                     "counts": [int] * n, "groups": {group: [int] * n} | null,
                     "p001", "p999", "min", "max", "mean", "std",
                     "span_pct",                        # (p999 - p001) / (high - low) x 100
                     "visited_pct",                     # bins inside the range with >= 1 record / bins inside the range
                     "outside": int,                    # records beyond the range (source given / declared only)
                     "distinct": int}}
classes           {field: {                             # category fields
                     "levels": [str],                   # declared first (in order), then any seen but undeclared
                     "declared": [bool],                # per level
                     "source": "given"|"declared"|"enum"|"bool"|"data",
                     "counts": [int], "groups": {group: [int]} | null,
                     "unseen": [str],                   # declared levels no record has: a missing class
                     "undeclared": [str],               # seen levels the declaration does not list
                     "majority_pct", "minority_pct",    # the largest and smallest SEEN level's share of present records
                     "imbalance_ratio",                 # largest / smallest seen count (1 = balanced)
                     "effective_classes",               # exp(Shannon H) over seen levels (Hill number of order 1)
                     "evenness_pct"}}                   # effective_classes / every level (declared + seen) x 100
texts             {field: {"distinct": int, "duplicates": int, "examples": [str] * <= 3}}
pairs             [{"x", "y", "x_edges": [lo, hi, nx], "y_edges": [lo, hi, ny],   # EXACTLY the declared ranges
                    "shape": [nx, ny], "samples": flat [int], "visited_pct", "sufficient_pct", "evenness_pct",
                    "outside": int, "missing": int}]   # outside: beyond either range; missing: either value missing
coverage          {"cells": int,                        # every cell of the space: each number field's bins inside its
                                                        #   range, each category's levels, each pair's cells
                   "visited": int, "visited_pct": float,
                   "growth": {"records": [int], "visited_pct": [float],          # <= 200 points, given order
                              "shuffled": {"median": [...], "p10": [...], "p90": [...]}},  # 32 shuffles, seed 0
                   "last_tenth_new_pct": float,         # cells first visited by the last 10 % of records / visited
                   "chao1_cells": float, "ceiling_pct": float}   # Chao1 estimate: more of the same reaches this
records           [{"id", "index", "group": str|null, "split": str|null, "missing": int,
                    "new_cells": int,                   # cells it was first to visit, in the given order
                    "unique_cells": int}]               # cells no other record visits (novelty; 0 = droppable)
support           null | {"split", "reference", "levels": {level: {
                     "records": int, "unsupported": int, "unsupported_pct": float,   # a record is unsupported when
                     "fields": {field: float}}}}        #   any of its bins/cells has no reference record; per field %
points3d          null | {"fields": [x, y, z], "labels": [3], "low": [3], "high": [3], "source": [3],
                          "display": {"scale", "unit"}, "points": [[x, y, z]] (<= 20 000, evenly picked),
                          "color_by": str|null, "levels": [str], "codes": [int]}   # codes index levels, -1 = missing
numbers           [{"key", "label", "value": float, "unit": str}]   # all finite; W&B logs exactly these
```

Headline `numbers` keys: `records`, `fields`, `number_fields`, `category_fields`, `missing_pct` (missing cells /
records × fields), `complete_records_pct`, `range_visited_mean_pct` (mean of the number fields' `visited_pct`),
`fields_without_range`, `class_imbalance_max` (the largest `imbalance_ratio`), `missing_classes` (sum of `unseen`),
`pair_visited_mean_pct`, `coverage_visited_pct`, `last_tenth_new_pct`, `ceiling_pct`, `droppable_records_pct` (records
with `unique_cells` 0); with `support`: `unsupported_pct.<level>`.

## The workbench (`write_workbench(coverage, records, out_dir)`)

data-ui's stock `<data-workbench>` (CONTRACT §52, §53). The rail filters **records** by their category fields (the
group_by field first, the split second, then every category of 2 to 24 levels, at most 5); tabs: **Overview** (every
number field against its range, class balance, missing values, the growth curve), **Numbers**, **Classes**, **Pairs**,
**Missing**, **Growth**, **Records** (data-ui's table: sort, filter, saved views). One gear for the heatmap colours.

- `records.json`: one row per record (its id, every category field, every number field, its missing count, new and
  unique cells, its `cohort`). `parts.json`: one row per **cohort** × figure, where a cohort is the records that share
  every rail value: a hist row per number field (`coverage.sum: grid`, stacked by group_by), a sparse grid row per pair,
  a `class` row per (category field, level), a `missing` row per field. The link `records.cohort → parts.cohort` keeps
  exactly the cohorts the rail keeps, so a tick recounts every figure **exactly** (the rail holds only cohort fields,
  never a slider or a search: those would keep part of a cohort). `growth.json`: the whole set's curve, not narrowed
  by the rail, and its panel says so.
- `index.html`, `embed.html` (a host's 1000 × 680 slot), `coverage.base`, `vendor/data-ui/` (as the trajectory
  workbench: `kit=` reuses a vendored kit).

## The other viewers

- **Matplotlib** `plot_records(payload, out_dir, *, cmap="viridis", reverse=False, scale="linear") -> list[Path]`:
  `numbers.png` (every number field against its range: grey beyond, the limit solid red, p0.1/p99.9 ticks, bars
  stacked by group with a legend), `classes.png` (each category's bars, declared-but-unseen levels marked, split by
  group), `missing.png`, `pair-<x>-<y>.png` (heat image, white = empty, the colour bar's real numbers), `growth.png`
  (given order, the shuffled band, the Chao1 ceiling), `support.png` (with support). Every figure has a legend.
- **Viser** `serve_records(payload, *, port=0, title=None)`: when `points3d` is set, the points in their declared box
  (limit colour), coloured by `color_by` with a legend in the panel, through `viser_3d_viewer`; prints `READY <url>`.
  Without `points3d` it refuses (`ValueError`: no 3-D fields).
- **W&B** `log_records(run, payload, *, prefix="records/")`: exactly `numbers` into `run.summary`, the title into
  `run.config`; nothing else (Zach 2026-11-21: W&B gets summary statistics only). Project: `record-coverage`,
  registered in bam_ws `tools/wandb_trackers/trackers/record_coverage.py`.
