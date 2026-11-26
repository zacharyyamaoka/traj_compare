# Navigation contract: Dataset → Target → Run, and the run view's question tabs (frozen 2026-11-19)

Zach's feedback on the 2026-11-19 layout rounds (daily note 2026-11-19, "Traj compare view feedback"):

- *"the Target trajectory is kinda the primary thing we want to organize things around"*
- *"at the top level ... the entire dataset, summary statistics across all the target trajectories. Then at the next
  level the target trajectories ... and for each of those target trajectories you have runs, in sim or real, with
  different robot configs"*; targets *"as table or cards"*; on a target, runs sortable *"by date, configuration type,
  sim/real"*.
- Run view: *"designing a different run viewer for standalone and rerun is a bit silly ... they should be the exact
  same thing"*; *"100% we need to do the tabbed model"*; keep the 3D always showing; *"split the arm and the hand into
  separate concerns, and each arm separately ... Arm can have between 1 - 7 motors, Hand can have 1 - N motors (perhaps
  you group by finger)"*; tab titles *"super descriptive"*: *"Where?" → "Where is the error?" is better.*

Every lane builds against this file. Changing it is a barrier the dispatcher lands first, alone. It extends
`docs/layout_proposals_2026-11-19/CONTRACT.md` (the five torques), which stays in force.

---

## Part A: three levels

| Level | Address | What it answers first |
| --- | --- | --- |
| **Dataset** | `index.html` (hash `#/` or empty) | How is tracking across every target, per config? |
| **Target** | `index.html#/target/<target slug>` | On this one target, how repeatable is each config, and is it improving? |
| **Run** | `runs/<run slug>/report.html` (the existing drill-down) | What happened in this run? (Part B) |

`index.html` stays one self-contained file that opens from `file://` (hash routes, no server). Back/forward work
(`hashchange`). Each level has a breadcrumb: `Dataset › <target title> › <run>`; the run report's breadcrumb links
back to `../../index.html#/target/<target slug>`.

### What a target, a line, a config is (production `Run` model)

- **Target**: runs whose `reference` is the same trajectory. Key: `write_dataset_report(..., target_by=<tag>)`;
  default the tag `"target"` when any run has it, else the first `group_by` tag, else a content hash of the
  reference (`t`, `q` bytes), titled by the first such run's `title` or name. Never mix two different references
  under one key: if a `target_by` value holds two different references, raise `ValueError` naming both runs.
- **Line** (what Zach calls "a run" on the target page): one measured series of one `Run`,
  id `"<run name> · <series>"`. A `Run` with `measured={"sim": …, "real": …}` gives two lines.
- **Kind**: `real` when the series name starts with `real`, else `sim` (the data-ui family rule in `data_ui.py`).
- **Config**: `config_by=<tag>`; default the second `group_by` tag when given, else the series name. Configs get
  fixed colours across every level (sim grey `#5f5e5a`; then violet, green, … — never the torque blue/orange).
- **Date**: the tag `"date"` when present (sort key and control-chart axis), else run order.

### Dataset level (`#/`)

1. The domain `summary` page if given (as today), then the **dataset summary band** `[data-tc-dataset-summary]`:
   N targets · lines (sim / real) · configs · date range; per config, across all targets: median RMS joint error (°),
   median feedback share when any line has a torque breakdown, pass rate when `tolerances` are given, and
   "better on X of Y targets" against the baseline config (the first config in order). Every number is
   `robot_msgs.compare`'s (as in today's `dataset.py`).
2. **Targets**, with a view switch `[data-tc-targets-view]` whose buttons carry `data-view="cards" | "table" | "runs"`
   (remembered in localStorage inside try/catch; default `cards`):
   - `cards` (2026-11-19 summary V3, "Target cards"): one card `[data-tc-target-card="<slug>"]` per target: title, run
     count, the verdict (which config tracks better, by how much, confidence; "nothing to compare" with one config),
     a chart of the chosen metric over trajectory time per config (lines ≤ N, fan past N, as on the Target level),
     a dot strip of every line's RMS error, and **Open target**.
   - `table` (2026-11-19 summary V2, "League table"): one row `[data-tc-target-row="<slug>"]` per target × config:
     n, median RMS error, Δ vs baseline, FB share, drive gap, saturation, ISO 9283 RT, error-over-time sparkline;
     a header click sorts; a row expands to its lines; the target title opens the target.
   - `runs`: today's index content unchanged (answer line, runs × pairs table, heatmap, peak-time strip, ISO 9283
     cards, Open run / Open in Rerun). Nothing that exists today is removed.

### Target level (`#/target/<slug>`)

- **Run list** `[data-tc-run-list]` on the left (2026-11-19 summary V1, "Scalars board" sidebar): regex filter,
  tag chips (config / date / kind and every other tag), one row per line `[data-tc-run]` with `data-line`,
  `data-config`, `data-kind`, `data-date`, a checkbox, its colour, RMS error, and ↗ opening its run report.
  **Group/sort** `[data-tc-sort]` (a `<select>` or buttons with `data-sort`) by `date`, `config`, `kind`; select-all
  per group. The edge drags (width remembered), the list folds. Only this target's lines are listed.
- **Verdict card** `[data-tc-verdict]`: which config tracks this target better, by how much, how confident.
- **Repeats control** (V1): `[data-tc-repeats]` buttons `data-mode="auto" | "lines" | "bands"`, a "lines up to N"
  slider `[data-tc-lines-n]` (default 5), smoothing slider. Auto: a config group draws lines while it has ≤ N
  visible lines, else a median · IQR · p5–p95 · min–max fan. Each chart states what it draws per group:
  `[data-tc-draw]` elements with `data-config` and `data-draw="lines" | "bands"`.
- Two tabs, titled by question, buttons `[data-tc-target-tab]` with `data-tab`:
  - `repeat` — **How repeatable is each config on this target?** Charts over trajectory time: joint error per joint
    (target − line, °), and when present feedback torque and FB share.
  - `history` — **Has tracking improved across configs over time?** (2026-11-19 summary V5's control chart):
    RMS error per line in date order, one phase per config with its mean and control limits, FB share under it.
- Clicking a line or a band opens that run's report (the existing drill-down link).

---

## Part B: the run view's question tabs (HTML and Rerun are the same thing)

### The stage (always visible)

Both viewers pin a **stage** beside the tabs: the 3D view (robot + paths) over the camera overlay / videos when present.
Rerun: as today's `questions` layout. HTML: the `viewer3d`, `camera` and `videos` sections move into a left stage pane
`[data-tc-stage]` that drags (`[data-tc-stage-resize]`, width remembered), folds (`[data-tc-stage-fold]`), and stacks
above the tabs below 900 px. The shared time and x zoom still span every tab. The stage has no time control of its own
since 2026-11-25: the page's one time control is the time lane under the tabs (below). A page without `timeline.js` (an
older shared `assets=` folder) keeps the old transport/scrubber under the 3D and the videos.

**Drag the time on any figure (2026-11-25).** Zach, Daily Note 2026-11-24: "as you drag the time on any of the figures
it syncs across all of the other ones". HTML: every plot is a scrubber. A plain press-and-drag on any plot (mouse, pen,
or a finger dragging sideways) commits the time at every move, snapped to the plot grid; every plot's playhead
`[data-tc-playhead]` (a solid line: the committed time, other tabs included), the 3D pose and path, the videos and the
lane's ruler follow while it moves. Hovering a plot without a press only previews that instant in the 3D
(uPlot's dashed cursor), and leaving the plot puts the 3D back on the committed time. x zoom moved off the plain drag:
Shift-drag (uPlot's box) or Ctrl/⌘+wheel (a trackpad pinch) zooms every plot alike without moving the time; a plain
wheel scrolls the page; the lane's **Full range** or a double-click restores the full range. Opening a tab never moves
the 3D. Rerun keeps its own time panel and gestures (`rerun_export` is unchanged). Tests: `tests/test_drag_sync_browser.py`.

**One timeline for the page: the time lane (2026-11-25).** Changed here because Zach's pick round of 2026-11-24
(`docs/proposals/run-view-2026-11-24/`, the playback viewer) applied its AI pick, R2 "One timeline for the page" (80 of
100, co-leader with R3 at 78; reversible, Zach can still swap). Until then the stage carried the transport and slider.
HTML, the default look of `write_comparison_report` (`assets/timeline.js`):

- **The lane** `[data-tc-lane]` is docked at the bottom of the tabs column (sticky: in view while the page scrolls). Its
  bar: to start, step back, play / pause `[data-tc-play]`, step forward, to end, the readout `[data-tc-lane-readout]`
  (`t / tMax s`), `‹ ◆ Worst moment ›` (`[data-tc-jump="prev|worst|next"]`: the worst moment of the shown runs, or the
  previous / next marked one), the zoomed span, **Full range** `[data-tc-zoom-reset]`, the Angles deg / rad chips and
  the fold `[data-tc-lane-fold]`.
- **The ruler** `[data-tc-ruler]` is the page's one slider (`role="slider"`, `aria-valuenow` = the committed time;
  ← → step a sample, Shift ten, Home / End, Space plays). Press and drag on it, or on any run's track: the time follows,
  live, snapped to the plot grid. No other time slider is drawn.
- **One track per run** `[data-tc-lane-track="<situation name>"]` (`data-shown`), grouped as the situation chips are
  (`[data-tc-lane-group="<group>"]`: folds its tracks, remembered; its eye toggles every run in it): an eye
  `[data-tc-lane-eye]` (the run on or off on every chart, the 3D and the answer), its colour, its whole name
  (ellipsized, whole in `title`), Δ `[data-tc-lane-delta]`, its error at the playhead `[data-tc-lane-value]` (the largest
  |reference − run| over the joints), a band of that error over time on one scale for every run, and its moments
  `[data-tc-moment="worst|rise|limit"]`: ◆ its worst moment (the answer's "Its worst moment" for the worst run), ▲ its
  error rises (the first sample above half its own peak), × a broken limit (`Situation.verdict`). Click one to go there.
  The count `[data-tc-lane-count]` reads "N of M shown". The situation, Δ and zoom chips are hidden under the lane; they
  stay the state machinery (prefs, `#run=`) the lane calls.
- **The zoom bar** `[data-tc-zoom-bar]` over the whole motion (an overview of the shown runs' error): drag a range to
  zoom every chart, drag the window `[data-tc-zoom-window]` to pan, its edges to resize, the wheel to zoom; a
  double-click resets. Shift-drag and Ctrl/⌘+wheel on a chart still zoom, and the window follows.
- **One line** `[data-tc-line]` runs through every chart of the open tab at the committed time, from the first chart
  down to the lane, behind what is not on the time axis (cards, tables, headings). WHY it can: every chart stacks one
  per row at full width (a hand's finger row stacks its joints too), its title in a left column as wide as the lane's
  names column, with a fixed y-axis width and padding, so every plotting area starts and ends at the ruler's x pixels.
  Each chart keeps its own `[data-tc-playhead]` under the line. On the track tab the "when was it worst" charts come
  before the statistics table.
- **Sizes**: the lane's top edge drags its height `[data-tc-lane-resize]` (double-click: default, about six tracks), it
  folds to its bar and ruler, and the names column drags `[data-tc-lane-names-resize]` (the charts' title column
  follows). All three are remembered (localStorage, try/catch).

Costs taken with it: the lane uses about 180 px (3 runs) to 300 px (17 runs) until folded or dragged smaller; charts
no longer sit side by side. Tests: `tests/test_time_lane_browser.py`.

### The tabs (`traj_compare.tabs.TABS`, in this order)

| id | Tab title (exact) | Heading inside the tab (exact) | HTML sections | Rerun `questions` layout | Shown when |
| --- | --- | --- | --- | --- | --- |
| `track` | **Did it track the target?** | How well did each run follow the target, and when was it worst? | the statistics table / answer, Summary + Insights pages where present, worst moment | scorecard, worst joint error (any joint), tool position error, events | always |
| `where` | **Where is the error?** | Where along the path is the tool off the target, and in which direction? | `tcp-err`, `tcp-pose` | tool error per axis (or per `error_axes`) | a tool frame exists |
| `joints` | **Which joint has the error?** | Which joint contributes the most tracking error? | `joint-err` | ranking bars + joint error per part | ≥ 2 joints |
| `timing` | **Is it late or off the path?** | Is the tool behind schedule (timing) or off the path (shape)? | `path` | lag time, contour error, speed along each `vec_dirs` | a tool frame exists |
| `torque` | **Feedforward or feedback?** | How much of the commanded torque comes from the feedforward model, and how much from feedback? | `joint-torque` | the torque tab (as today) per part | a torque breakdown exists |
| `signals` | **Raw signals per joint** | Every measured joint signal: angle, speed, acceleration, torque, current | `joint-q`, `joint-qd`, `joint-qdd`, `joint-tau`, `joint-current` | Angle [°] · Speed [°/s] · Applied torque [N·m] sub-tabs | always |
| (check) | the caller's name, e.g. "Camera Check" | as today | — | as today (`rerun_checks`) | `rerun_checks` given |

- A tab with nothing to show is dropped (no empty tabs), in both viewers, by the same rule
  (`traj_compare.tabs.tabs_for(payload)`).
- Every view / plot / card title inside a tab names its signal, joint, sign convention and unit, e.g.
  `shoulder: joint error, target − run [°]`, never a bare `shoulder [°]`.
- HTML: tab strip `[data-tc-tabs]`, buttons `[data-tc-tab="<id>"]` (textContent = the exact title,
  `aria-selected`), panels `[data-tc-panel="<id>"]` whose first heading `[data-tc-tab-heading]` is the exact heading.
  The active tab is remembered (localStorage, try/catch) and addressable: `report.html#tab=<id>` opens it.
  **Sub-tabs and a legend, not section chips (2026-11-25).** Zach, traj compare 3D viewer feedback: graphs are fixed;
  a tab of several sections has sub-tabs (`tabs.SubTab`, `payload.tabs[i].subtabs`; HTML `[data-tc-subtabs]`, buttons
  `[data-tc-subtab="<id>"]`) that pick which graph, or fixed stack of graphs, shows, and a legend `[data-tc-legend]`
  (items `[data-tc-legend-item="run:<name>" | "delta:<name>" | "joint:<joint>"]`) that picks which series they draw:
  runs per tab (on top of the lane's eye), Δ (the lane's own Δ state), joints on a per-joint tab. Both are remembered
  per tab. `signals` sub-tabs: `q`, `qd`, `qdd`, `T`, `q / qd / qdd`, `q / qd / T` (a stack: per joint, its cards one
  under the other), then `Current` when recorded; `where`: Tool error, Tool pose; `channels`: one per channel.
- **Open in Rerun is pinned** top right `[data-tc-rerun-pin]` on every tab (fixed while scrolling); without a launcher
  it shows the one-line command, without a recording it says how to write one.
- **The 3D view's line styles (2026-11-25, a pick between three)**: A Ghost + comet (default), B Error ribbon,
  C Focused instant, switched by `[data-tc-style-pick]` bottom right (remembered). Every style draws the run at the
  target + ×N its error (auto N, the Rerun magnifier's 1-2-5 rule), colours the position error on a stated scale, draws
  no dashed line, and limits the drawing to "Trail decay" seconds behind the playhead (the target also "Look-ahead"
  seconds ahead). Elements: Path, Points, Robot model, Pose frames, Tool Z axis, Position error arrow, Orientation error
  arc; a compact legend `[data-tc-3dlegend]` under the canvas names the marks of the active style.
- Rerun: the `questions` layout's tabs carry the exact titles. `layout_blueprint(..., tab=)` accepts a tab id, the
  new title, or a pre-2026-11-19 title ("Is it good?", "Where?", "Which joint?", "Timing or shape?",
  "Feedforward or feedback?", "Signals"). The `evo` layout is unchanged.

### Scaling with joint count: parts

- `Comparison.parts: Mapping[str, Sequence[str] | Mapping[str, Sequence[str]]] | None = None`, ordered.
  A value is a list of joint names (an **arm**, 1–7 motors) or `{finger: [joint names]}` (a **hand**, grouped by finger).
  Every named joint must exist and appear once (else `ValueError`); joints not named fall into a trailing part
  "Other joints". `None` is one implicit part holding every joint: no part selector is drawn.
  WHY explicit: the viewer never guesses arm/hand membership from joint names.
- Payload: `payload["parts"] = [{"name": str, "groups": [{"name": str, "joints": [str]}]}]` (an arm has one group named
  `""`); `payload["tabs"] = [{"id", "title", "heading", "sections": [section ids]}]`, already dropped by `tabs_for`.
- In the per-joint tabs (`joints`, `torque`, `signals`):
  1. **Ranking first** (≥ 2 joints): one bar per joint across all parts, worst first, labelled `<part> · <joint>`
     (`joints`: RMS joint error of the worst run, °; `torque`: FB share, %). HTML `[data-tc-rank]` with bars
     `[data-tc-rank-bar]` carrying `data-joint`; clicking a bar shows that joint's part and scrolls to its plot.
     Rerun: a bar chart per part under `/stats/joint_rms/<part>` with the joint order in the view title.
  2. **Part selector** when there are ≥ 2 parts: HTML buttons `[data-tc-part="<index>"]` labelled
     `<part> · <n> joints`; Rerun: nested `Tabs`, one per part, same labels.
  3. Inside a part: an arm draws one row per joint; a hand draws one row per finger, that finger's joints as columns
     (under the time lane a finger's joints stack in its row, one chart per row, so they share the lane's x).
- What it looks like (the acceptance fixtures):
  - **1 DOF**: tabs track, (where, timing with a tool), (torque with a breakdown), signals; no `joints` tab, no ranking,
    no part selector.
  - **3 DOF / 6 DOF, one arm**: no part selector; a ranking of 3 / 6 bars; 3 / 6 rows.
  - **Bimanual, 46 motors**: parts Left arm (7), Right arm (7), Left hand (16: thumb 4, index 3, middle 3, ring 3,
    little 3), Right hand (16); a part selector of 4; a ranking of 46 bars; a hand part draws 5 finger rows.
- Out of scope here: one tool frame per arm (the model has one `tcp_frame`); the `where` / `timing` tabs follow it.

### Joint jerk, torque and limits

- `Situation.qddd` accepts a per-joint jerk trace in SI units. Mark undefined jerk at acceleration jumps with a
  non-finite value. The display keeps these gaps when it thins the time grid. Use `derive_jerk=True` only when the
  provided `qdd` is continuous and modeled as linear between samples. The viewer labels the resulting per-interval
  slope as derived. A trajectory with no finite jerk trace keeps the existing acceleration views.
- `Situation.tau_cmd`, `Situation.tau`, and `Situation.tau_gearbox` are the commanded actuator torque, the applied
  torque on a run (required torque on a trajectory target), and the gearbox load. The raw torque view shows each
  recorded signal it has. The existing feedforward/feedback view can still reconstruct a missing command from its
  two components. A gearbox trace requires a modeled or measured load supplied by the caller.
- `Comparison.joint_limits` sets page-wide robot_msgs bounds by joint name. `Situation.joint_limits` can supply a
  run's own bounds. For asymmetric limits and channel-specific torque envelopes, add `signal_limits` at either level.
  Each value is a `(lower, upper)` pair in comparison joint order, with `None` for an open side. Scalars apply to
  every joint. Use `q`, `qd`, `qdd`, `qddd`, `tau`, `tau_cmd`, `tau_gearbox` or `current` for the signal key. A run's
  limit entry replaces the page limit for that signal. `JointLimits.max_effort` sets `tau` only. A gearbox cap such as
  `signal_limits={"tau_gearbox": (-18.0, 18.0)}` belongs to the gearbox trace.
- `Comparison.joint_units={"rail_joint": "m"}` sets linear units for a slide. All other positions default to `rad`.
  Angular display units follow the degree/radian toggle. Rates and effort on a linear axis use metres per power of
  seconds and newtons respectively.
- A dataset run also forwards its saved `JointTrajectory.limits`. Undescribed canonical `qddd`, `tau_cmd`, and
  `tau_gearbox` channels with one numeric column per joint go to these native plots. A channel explicitly described
  with `Signal` keeps its authored units, labels and generic plot.

---

## Part C: scale and signals (frozen 2026-11-20)

Source: the arm_motion_bench Trajectory Tracking Agent, 2026-11-20. It ran the dataset view on three robots (UR5e 1006
targets / 4932 runs, BAM FB 504 / 1648, pendulum 465 / 2301 sim + real) and listed seven gaps it had worked around.
Measured on its UR5e site:
- the index was 38 MB at 3 Hz: line torque series 13.4 MB, line `e_deg` 6.7 MB, the runs table's rows 10.9 MB;
- `rows.json` was 460 MB;
- `runs/` held 2.4 GB, of which 0.81 GB was `reference.npz`, for only 974 distinct references across 4932 runs.

Parts A and B stay in force; this part adds to them.

### C1. Signals beyond the joints (gaps 1, 2)

- **Carrier: each series' `JointTrajectory.channels`.** These are robot_msgs-native and already saved in its `.npz`,
  so `Run` gains nothing.
- **`channels["current"]`, shaped (N, J):** motor current in A, columns in that series' `joint_names` order.
  On a one-joint series (N,) is accepted too, as `Run.torques` promotes 1-D (amended 2026-11-20 for the pendulum).
  - The drill-down hands it over as `Situation.current`, reordered onto the reference's joints exactly as `effort` is.
  - The HTML `signals` tab draws it in its existing `joint-current` section.
  - Rerun's `signals` tab gets a **Motor current [A]** sub-tab when any situation has current.
  - A `"current"` channel of any other shape raises `ValueError` from `write_dataset_report` (naming run, series and
    shape), never at drill-down time.
- **Other channels** become `Situation.channels[name]`: float, (N,) or (N, k), on that situation's own samples.
  The canonical exclusions for joint jerk and torque are listed above.
  - `Situation.__post_init__` raises `ValueError` (naming the situation and the channel) for:
    - another dimensionality;
    - a first dimension that differs from `len(t)`;
    - the key `"current"` (use `Situation.current`).
- **Description: `traj_compare.Signal`.** A frozen dataclass in `model.py`, exported from `traj_compare`:
  `Signal(title: str = "", unit: str = "", columns: Sequence[str] = (), per_joint: bool = False)`.
  - It is given through `Comparison.signals: Mapping[str, Signal]` (default `{}`), or
    `write_dataset_report(..., signals: Mapping[str, Signal] | None = None)`. The dataset form stores them in every
    manifest under `"signals"`, so a drill-down rebuilt later still has them.
  - A channel nobody described is still drawn: title = its name, no unit, columns `[0]`, `[1]`, …
    WHY: truthful rendering. A recorded signal is never dropped or renamed.
  - `per_joint=True`: shape must be (N, J); the columns are the joints, reordered with the series as `effort` is.
  - `columns`, when given, must have length k (else `ValueError`).

**The run view's tab for them**, after `signals` and before the check tabs:

| id | Tab title (exact) | Heading inside the tab (exact) | HTML sections | Rerun `questions` layout | Shown when |
| --- | --- | --- | --- | --- | --- |
| `channels` | **What else was measured?** | How did every other recorded signal change over the run? | one per channel, `[data-tc-section="channel-<slug>"]` | one TimeSeriesView per channel | any situation (target included) has a channel |

- `<slug>` is the channel name lowercased, with every run of characters outside `[a-z0-9]` replaced by `-` and
  leading or trailing `-` stripped (`contact_force_n` → `contact-force-n`).
- **Plot titles name the signal and its unit:** `Contact force [N]` for a 1-D channel; `Contact force, x [N]` for one
  column of a 2-D channel, which gets one plot per column.
  - Every situation that has the channel is drawn in its run colour, the target as the target is drawn elsewhere.
  - A missing unit drops the brackets: `contact_force_n`, never `contact_force_n []`.
- **Rerun:**
  - Entities: `/channels/<name>/<column>/<situation>` (a 1-D channel's column is `value`).
  - The tab title is exact. One view per channel holds all its columns and situations; the view is titled
    `<title> [<unit>]`.
- `traj_compare.tabs.tabs_for(payload)` drops the tab when no situation has a channel, in both viewers.
- Out of scope: drawing channels on the Dataset or Target level. A per-run scalar (peak force) stays a run tag.

### C2. Row files (gap 3)

`write_dataset_report(..., rows: Sequence[str] | None = None)` picks which row files to write, a subset of
`("json", "parquet")`:
- `None` (the default) is today's behaviour: `rows.json` always, `rows.parquet` when pyarrow imports.
- `()` writes neither; `("parquet",)` writes only `rows.parquet`.
- An unknown name raises `ValueError`. Naming `"parquet"` without pyarrow raises `ModuleNotFoundError`. Both are raised
  before any file is written.
- A row file not chosen this time is deleted if an earlier write left one, so no stale rows outlive their data.
- The rows' content and columns are unchanged.

### C3. One server for many sites (gap 4)

- A **site** is a directory holding `index.html` and `runs/`. `python -m traj_compare.serve <dir>` lazily builds
  `<site>/runs/<slug>/report.html` and `<site>/runs/<slug>/rerun/<pair>.rrd`:
  - for every site at any depth below the served root, the root included, as it does for the root site today;
  - from `<site>/runs/<slug>/manifest.json`;
  - under the one existing build lock.
- **The build goes straight to that run's folder** through the new public
  `traj_compare.dataset.build_run_folder(folder) -> Path`, never through a scan of every manifest.
  `build_drill_down(output_dir, run_name)` keeps its signature.
- **`GET /` (or `/index.html`) when the served root has no `index.html` of its own** answers a landing page listing every
  site up to 3 levels deep, in path order:
  - one link per site, `<a data-tc-site="<site path>" href="<site path>/index.html">`;
  - its text holds the site's `<title>` and its run count (the number of `runs/*/manifest.json`).
- **Open in Rerun from a dataset page** posts the `.rrd`'s path resolved against the page's own URL, relative to the
  served root (`ur5e/runs/<slug>/rerun/<pair>.rrd` for a site at `ur5e/`), as the run report already does.

### C4. Config colours (gap 5)

- Grey `#5f5e5a` marks a sim-only config only in the **twin case**: exactly one config has no real line, and at least
  one config has real lines.
- Every other config, sim-only or not, takes the next named hue in config order; past the named hues it takes distinct
  generated ones.
- In one dataset every config colour is distinct, for up to 24 configs. None is the torque blue `#2a78d6` or the
  orange `#eb6834` (CONTRACT.md).
- Sim lines are still dashed, with the hollow sim swatch. Kind is never shown by colour alone.

### C5. Per-level detail and the index's size (gap 6)

- **`index.html` embeds no line's time series.**
  - Each line keeps only its scalars: `rms`, `worst_rms`, `worst_joint`, `coverage`, `ok`, and the torque scalars
    `fb_share` / drive gap / per-joint shares when present.
  - The runs table's per-row repeats are built in the page from one template, never stored per row. The template
    holds the run name and the folder (e.g. `rerun_command`).
- **Every line's drawn series live in one file per target, `targets/<slug>.js`**, holding the joint error `e_deg` and
  the torque display series.
  - It is a classic script calling `window.trajCompareTarget("<slug>", {...})`, so it loads with a `<script>` tag from
    `file://` and from http alike.
  - The Target level loads it when `#/target/<slug>` opens.
  - The Dataset level's cards and league rows load it when they scroll into view: cards and charts render lazily,
    with a placeholder until the file arrives.
  - A file the write did not produce this time is deleted.
- **Rate.** A target's series are picked at `display_hz` (default 50), never averaged.
  - `write_dataset_report(..., target_budget: int = 2_000_000)` caps one target's file at that many drawn values
    (lines × joints × samples × drawn series). Over the cap, the stride grows until the file fits.
  - Every Target-level chart and every card says what it draws in a `[data-tc-drawn-rate]` element whose text contains
    `<rate> Hz`, the rate actually drawn.
  - `display_hz` and `target_budget` must be positive (else `ValueError`).

### C6. Files on disk (gap 7)

- **One reference per distinct reference.** Each is written once as `references/<digest>.npz` beside `runs/`. The digest
  is a SHA-1 over the reference message's saved content (its JSON tree and every array's bytes), so two references
  differing anywhere are two files.
  - A run's `manifest.json` names it relatively: `files.reference = "../../references/<digest>.npz"`, and nothing
    writes `runs/<slug>/reference.npz`.
  - After the write, any `references/*.npz` that no `runs/*/manifest.json` names is deleted.
  - A manifest written before 2026-11-20 (`"reference.npz"`) still builds.
- **Every `.npz` the dataset writes is compressed** (`np.savez_compressed`): references, series and `.torques.npz`.
  - `robot_msgs._core.load_npz` and `np.load` read it unchanged.
  - The saved values are bit-identical to the inputs.

## Part D: incremental writes (frozen 2026-11-20)

Source: arm_motion_bench lane V, 2026-11-20. Zach waited about 6 min on a UR5e rebuild and hit Ctrl-C: adding 818 runs to
a 5,750-run site rewrote all 5,750. Its cProfile of a 600-run UR5e build (traj_compare 8d67234) spent 25.9 s in
`write_dataset_report`:
- `_analyze_pair` 12.3 s (`estimate_time_offset` 6.2 s, the TCP compare 4.7 s);
- `_write_run_files` 7.3 s (`np.savez_compressed`, 1,533 files);
- the `poses` function 1.5 s, `_levels_payload` 2.1 s, `_write_rows` 1.3 s.

About 35 ms of that per run is identical when the run did not change. Parts A to C stay in force; this part adds to them.
The bench rebuilds into a hard-linked copy (`cp -al live staging`), writes incrementally into it, then swaps the two with
`renameat2(RENAME_EXCHANGE)`. D2 is what makes that safe.

### D1. A run that did not change is reused

- **`write_dataset_report(..., reuse=True)`.** `reuse=False` rewrites every run, as before this part.
- **Each run has a digest**, a SHA-1 hex string stored as `runs/<slug>/manifest.json["digest"]`. It covers everything
  that decides that run's files and analysis:
  - **the code**: every file of the installed `traj_compare` package (`.py` and `assets/`), every `.py` of the installed
    `robot_msgs` package, and the source file of the module that defines the `poses` function and the `robot` function.
    WHY files, not `__version__`: the version string does not move on a commit, and a cache that outlives a code change
    serves stale numbers. Data such a function loads (a URDF, a MuJoCo model) is not covered; pass `reuse=False` after
    changing it.
  - **the run**: name, title, tags;
    - the reference's and every measured series' saved content, digested as C6 digests a reference (the JSON tree,
      channels included, and every array's key, dtype, shape and bytes);
    - its torques (series, key, dtype, shape, bytes), resolved pairs, `time_offset_s` and `media_start_s`;
    - each media file as (key, size, `mtime_ns`). WHY not its bytes: hashing every clip on every write costs about what
      copying it does.
  - **its place in this write**: its slug and its target's key, slug and title.
  - **this write's per-run options**: `poses`, `robot`, the import roots, `tolerances`, `signals`, `primary`.
  - **Not covered**: `display_hz`, `target_budget`, `group_by`, `config_by`, `title`, `summary`, `rows`, `drill_down`,
    `data_ui`. They decide only site-level output, which every write recomputes (or D1b reuses by its own key).
- **`runs/<slug>/analysis.json`**: `{"digest", "entries", "rows"}`.
  - `entries` are the run's entries in the index payload's `rows` list, one per pair, exactly as a full write makes them
    (error entries included).
  - `rows` are its tidy rows for `rows.json` / `rows.parquet`.
- **When a run is reused.** Three conditions:
  - `reuse` is true;
  - its folder's `manifest.json` and `analysis.json` both parse and both hold the run's digest;
  - every file the manifest names exists.

  Then nothing in its folder is written or deleted, including a `report.html` and a `rerun/` an earlier drill-down
  built. Its index entries and tidy rows come from `analysis.json`. A pair error in a reused run warns again, as the
  write that made it did. Its pose trajectories are computed only if something this write recomputes needs them: a
  target that is not reused (D1b), or a `group_by` group whose runs share one reference (its ISO 9283 card).
  `group_by` cards are not cached.
- **Every other run is rewritten.** Its `manifest.json` is deleted first, then its files are written as before, then
  `analysis.json`, and `manifest.json` last. So a write stopped midway leaves no manifest naming half-written data.
- **Reuse changes nothing in the output.** A write that reuses runs must produce the same output as a `reuse=False`
  write of the same runs, in the same order, into an empty folder:
  - the same index payload, except `generated`, `write_id`, `serve_command` and `command_template`;
  - the same row files and `targets/*.js` (bar the per-write `?v=` id, which lives in the page, not the file);
  - the same `runs/*/manifest.json` and `.npz` contents, and the same `references/`.
- Run folders that are not in this write are left in place, as before. The caller deletes them if it wants to.

### D1b. A target that did not change is reused

- **`targets/<slug>.cache.json`**: `{"key", "target", "lines"}`.
  - `target` is that target's entry in `levels.targets`, before the site-wide `has_torque_breakdown` pass.
  - `lines` are its lines in `levels.lines`.
- **`key`**: a SHA-1 hex string over:
  - the digests (D1) of the target's runs, in order;
  - the target's key, slug and title;
  - the config tag, the labels, `display_hz` and `target_budget`.
- **A target is reused** when `reuse` is true, its `.cache.json` parses and holds this key, and its `<slug>.js` exists.
  Neither file is then written, and no compare, `poses` call or repeatability aggregate runs for it. Its lines' `order`
  field is recomputed for this write.
- **The site-wide pieces are recomputed from every target's lines on every write**: config counts, colours (C4),
  `fb_share_median` and the `has_torque_breakdown` flags.
- A `*.cache.json` whose target is not in this write is deleted, as its `.js` is.

### D2. Every file is written under a temporary name, then renamed into place

- **Every file traj_compare writes** goes to a temporary name in the same directory, then `os.replace` moves it onto
  its own name. No existing file is opened for writing. This covers:
  - the dataset site: `.npz`, `manifest.json`, `analysis.json`, `targets/*`, `references/*`, `index.html`, the row files
    and copied media;
  - the run view's `report.html`, `.rrd` and `.rbl` files;
  - data-ui tables;
  - the `export` files.
- **What that guarantees:**
  - In a hard-linked copy of a site, every file a write leaves untouched keeps the same bytes, inode and `mtime_ns` in
    the original. That holds for an incremental write and for a lazy drill-down build in the copy. Deleting a stale
    file in the copy removes only the copy's name.
  - A write that is stopped leaves each file either whole and old or whole and new.
- A temporary name ends in `.tmp`, so no glob for `*.npz`, `*.js` or `*.rrd` matches it. A failed write deletes its
  temporary file.

### D3. Progress

- **`write_dataset_report(..., progress=fn)`.** It calls `fn(phase, done, total)`:
  - `"runs"`: `(0, N)` before the first run, then `(i, N)` after each run, whether reused or rewritten;
  - `"reused"`: once, right after the runs phase, as `(number of runs reused, N)`;
  - `"targets"`: `(0, T)`, then `(i, T)` after each target;
  - `"index"`: `(0, 1)` before `index.html` is written, `(1, 1)` after;
  - `"drill"`: with `drill_down="eager"`, `(0, N)`, then `(i, N)` after each run. A reused run whose `report.html`
    exists is not rebuilt.
- Within a phase, `done` never decreases.
- **An exception from `fn` propagates and stops the write.** `index.html` stays the previous write's (D2), and the next
  write is correct (D1).
- The return value is unchanged: the path of `index.html`.

---

## Part E: the outer view, tabs and the config league table (frozen 2026-11-23)

Zach, 2026-11-20: *"the landing page is WAYYY to hard to navigate ... At the highest level we want to be comparing
different pipeline configurations vs how they do on all of the targets ... add tabs so it's not all on the one page"*;
2026-11-23: *"league table seems reasonable please build that out"* (V1 of `docs/proposals/outer-view-2026-11-20/`). The
UR5e landing page was 206,472 px tall at 1440 px wide (229 screens). Acceptance: `tests/test_dataset_league.py`.

### E1. Tabs

- The Dataset level is tabs `[data-tc-dataset-tabs]`, links `[data-tc-dataset-tab="<id>"]` (`aria-selected`), panels
  `[data-tc-dataset-panel="<id>"]`, in this order: `overview` (`#/`, the landing), `sweeps` (`#/sweeps`, only with a
  sweep), `targets` (`#/targets`), `runs` (`#/runs`). A tab takes a query: `#/<tab>?k=v&…`. `#/target/<slug>` is
  unchanged (Part A).
- Overview: the league (E2), then the summary band (Part A). Speed sweeps: the sweep view, one chart per extra metric,
  and the domain `summary` page folded in `details[data-tc-domain-summary]` (without a sweep it folds on the Overview).
  Targets: the `[data-tc-targets-view]` switch, now `cards` | `table`, a page at a time (Show more), or, with
  `?cfg=`, a config's worst targets (E3). Runs: Part A's `runs` view, unchanged.
- No tab is taller than ~3 screens at 1440 x 900; the league lies above the fold.

#### Fixed speed-sweep reports

- A `Sweep` can set `x_domain=(0, 1)` and `x_step=0.1`. The chart axis runs from 0 to 1.
  The bins `(0, 0.1]`, `(0.1, 0.2]` and so on are labeled by their upper edge. Zero is
  an axis tick and has no bin. Missing bins interrupt the curve.
- `SweepObservation(series, target, x, value)` supplies a reporting measurement for an
  existing Dataset target key. A named series can appear solely in the sweep. Pass
  `value=None` to record an unavailable measurement. The table counts target paths with
  values and shows the expected path count. A median and quartiles require the same
  complete target set for every series and bin within the facet.
- Explicit observations change the primary sweep chart and its table. Qualifying detail
  links open the underlying target path. The Overview league, extra metrics, Targets and
  run reports still use the ordinary recorded runs.

### E2. The league (`[data-tc-league]`)

- **KPIs** come from run tags: the sweep's `y`, then `Sweep.metrics` (`Metric(tag, label, unit, log, better)`). A tag may
  hold `{series}` (each measured series reads its own tag); a **key** is a config, or `<config> · <series>` when more
  than one series has values. `Sweep.facet_by` may be a tuple of tags, a facet being their values joined by ` · `.
- A target's value for a key and KPI: the median over its repeats. A cell (facet, key, x): the median over the facet's
  targets, n = those targets. Rows: every key with a primary value at the fastest x, best first (`data-rank`), showing
  the value, its ratio to the best (`best` on rank 1), n, one sparkline per KPI over x (`data-metric`), and how many
  (facet, x) cells it is lowest in. Facet chips `[data-tc-league-facet]` (`all` first). A verdict line
  `[data-tc-league-verdict]` names the best key and the others' ratios.
- Without a sweep the league has one KPI: each config's median over targets of its median RMS joint error (the levels'
  numbers, real lines when it has any).

### E3. Drill

- A league row opens `#/targets?cfg=<key>&facet=<facet>&x=<x>`: `[data-tc-drill]` lists the key's targets in that
  facet at that x worst first, rows `[data-tc-drill-row]` (`data-target`), each linking `#/target/<slug>` and the run
  report of the repeat closest to the target's value. Selects change the config, facet, x and sort (own value, or ratio
  to the best other key).
