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

Both viewers pin a **stage** beside the tabs: the 3D view (robot + paths, the transport/scrubber under it) over the
camera overlay / videos when present. Rerun: as today's `questions` layout. HTML: the `viewer3d`, `camera` and `videos`
sections move into a left stage pane `[data-tc-stage]` that drags (`[data-tc-stage-resize]`, width remembered), folds
(`[data-tc-stage-fold]`), and stacks above the tabs below 900 px. The shared time cursor and x zoom still span every tab.

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
  Section chips still show/hide sections inside a tab.
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
  3. Inside a part: an arm draws one row per joint; a hand draws one row per finger, that finger's joints as columns.
- What it looks like (the acceptance fixtures):
  - **1 DOF**: tabs track, (where, timing with a tool), (torque with a breakdown), signals; no `joints` tab, no ranking,
    no part selector.
  - **3 DOF / 6 DOF, one arm**: no part selector; a ranking of 3 / 6 bars; 3 / 6 rows.
  - **Bimanual, 46 motors**: parts Left arm (7), Right arm (7), Left hand (16: thumb 4, index 3, middle 3, ring 3,
    little 3), Right hand (16); a part selector of 4; a ranking of 46 bars; a hand part draws 5 finger rows.
- Out of scope here: one tool frame per arm (the model has one `tcp_frame`); the `where` / `timing` tabs follow it.
