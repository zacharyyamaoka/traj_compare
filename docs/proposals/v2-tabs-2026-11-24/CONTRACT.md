# V2's workbench: three proposals for a fourth tab (babble round, frozen 2026-11-24 night before any tab was built)

Zach, Daily Note 2026-11-24 (verbatim): "yes v2 is really great please do that one: traj_compare on the stock workbench:
five ways to link Dataset → Target → Run" / "Are there any more tabs we want to add to that outer view? we have overview,
targets and runs. Make 3 prospaols for 3 different tabs we could add".

Earlier the same day: runs are atomic ("a trajectory is a trajectory" across datasets and models); the rail filters runs;
all deployments at the top, deployment a filter; "some grouping by model type across deployments". Tabs are titled as
questions ("Where?" → "Where is the error?" is better).

## User outcome

A fourth tab on V2's workbench that answers a decision the Overview (League, Speed sweeps), Targets and Runs leave open,
over exactly the runs the rail keeps, and drills to the V2 target view with the runs it is about.

## Invariants (all three)

- **Base = V2 "Two viewers, the filter carried"** (`../tensorboard-2026-11-24/v2/`, READ-ONLY): each `tN/` is a copy of
  V2's `index.html`, `host-common.js`, `host.js` and `views.base` plus ONE new tab; Overview · Targets · Runs unchanged.
- **Real rows:** V2's `data/rows-runs.json` (18,507 runs of all four deployments) and `data/<site>.js`; derived rows built
  by `build_tabs.py` from those and from the bench's own `targets/<slug>.js` (drawn joint error, 50 Hz) and
  `references/*.npz`. Nothing invented; a derived file names its rule.
- **Stock data-ui** (`<data-workbench>`, `.base` pages, Vega-Lite charts, tables, §52 coverage views) at V2's vendored
  build `e8c73dc`; host JS only where data-ui cannot, each place a named gap in `NOTES.md`. No edit to `/home/bam/data-ui`
  or `traj_compare/src`.
- **Drill:** a row (or point, or cell) opens `common/target.html` (V2's target view) with `keep=` the runs it is about and
  `back=` the workbench URL (its filter and tab), as V2's Targets / Runs rows do.
- **Served** by `serve.py` on 127.0.0.1:8852 (this folder at `/`, V2's `common/`, `vendor/` and data at the same paths,
  the bench at `/bench/`, Open in Rerun's endpoint with its `.rrd` written under this folder's `data/rerun/`).
- **Zach's UI rules:** boundaries drag and are remembered, panels fold (V2's rail); one calm answer first, detail on
  demand; plain-word labels; angles in degrees; never truncate a name silently; amber/red only for problems.
- **1440 × 900**, headless Chrome, same scenario shape for all three.

## What the data can carry (checked before choosing)

| Candidate | Data check (V2's rows) | Verdict |
|---|---|---|
| **T1 Does sim match real?** | real lines exist only on the pendulum (3,616) and BAM FB (41); a run folder holding a real line AND its sim twin's line is the same commanded motion predicted and measured: **1,752 pairs** (pendulum 1,726, BAM FB 26); the pendulum also has **1,204** real ↔ rehearsal pairs (the twin's dress rehearsal of the real plan, `pendulum_real.py`) | carried; UR5e has no real run, so the tab says so by having no pairs there |
| **T2 Where in the workspace is it worst?** | the bench's own coverage grids (`coverage.json`, q × qd per joint, 36 × 24, the Coverage page's cells) and every line's joint error at 50 Hz in `targets/<slug>.js` (`e_deg`), with the reference's q, qd at the same instants: the error at each cell it was made in, ~20 cells per target and joint | carried, in joint space (no tool position is stored per sample; the tool view is a named next step) |
| **T3 Which config wins head to head?** | configs share targets: UR5e cell 5 configs over 1,006 targets, BAM FB 4 main ones over ~1,000, the pendulum 6 over 522 | carried |
| Which joint has the error? | `worst_joint` and per-joint RMS exist | folded into T2 (one colour scale over every joint's plane) |
| Feedforward or feedback? | `fb` share on 15,988 of 18,507 runs | weaker: a share, not a decision; left out |
| Speed sweeps | already an Overview panel; a sibling lane redesigns Overview | left out (would duplicate) |

## Scenario (each tab)

Unfiltered (all 18,507 runs) → ONE rail pick that matters for the tab → the tab recounts; check.cjs reads the tab's
numbers in both states and `data/oracle.json` (Python, same rows, same rule) must equal them:

- T1: Deployment = **BAM FB** (the arm: 1,752 → 26 sim ↔ real pairs).
- T2: Config = **ctc_tuned** (where is the UR5e's tuned controller worst?).
- T3: A = ctc_tuned, B = ctc_tuned_v2 (the shipped tune and its successor) → Speed = **1.0 ×** (the League's speed).

## Load-bearing axes (why these three differ)

1. **The question's object:** a run's prediction (T1: one run, predicted vs measured) · a place in the robot's space (T2) ·
   a decision between two configs (T3).
2. **The grain:** a pair of lines · a cell of a joint's q × qd plane · a target × config match-up.
3. **How stock:** T1 and T3 are `.base` pages of stock views over a derived dataset linked one-way from the runs; T2 is a
   host page (the aggregate a median over runs per cell, which `coverage.sum` cannot do) drawn by the stock coverage-plane.

## Directions (allocated before building)

- **T1 "Does sim match real?"** A page over `pairs` (linked one-way from the runs by run folder) with its own control,
  Real against: sim twin | rehearsal. The answer line (median real ÷ predicted tool RMS, n, how often real is worse),
  per config (median, middle half), every pair (predicted against real, log-log, the y = x line), the gap against speed,
  and the pairs that disagree most; a pair drills with `keep=` its two lines.
- **T2 "Where in the workspace is it worst?"** A host page in the same component: each joint's q × qd plane (the bench's
  own coverage grid) coloured by the tracking error made in each cell, the median over the targets through it of the
  median over its kept runs of their RMS error within the cell; one colour scale over every joint. The answer line names
  the worst cell (≥ 3 targets). A click on a cell lists the targets through it, worst first; a row drills with `keep=`
  that target's kept runs.
- **T3 "Which config wins head to head?"** A page over `h2h` (one row per target × sim/real × A × B, the median tool RMS
  of each config's runs of that target) linked one-way from the runs on target, sim/real and both configs; its own
  control, A and B (default ctc_tuned → ctc_tuned_v2). The answer line (wins, losses, ties within 5 %, median B ÷ A),
  per dataset, each target A against B, B ÷ A against speed, and where B regressed most; a row drills with `keep=` A's and
  B's runs of that target.

## Stop line and proof

Every tab: real rows, the scenario's recount equal to the oracle (check.json), the drill to the target view with `keep=`
and `back=`, a still of every state and a session video (headless, 1440 × 900). Not built: production wiring into
`dataset.py`, the tool-space (xyz) version of T2, edits to data-ui (gaps named in each `tN/NOTES.md`).
