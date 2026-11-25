# V2 — Two viewers, the filter carried

**Thesis:** The outer workbench and the target view are two pages; Open target view goes to the target page with the rail's runs checked (`keep=`), and its ‹ All targets returns to the workbench URL with the same filter.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/serve_round.py --port 8873`, then `http://127.0.0.1:8873/v2/index.html`. Rows and `.base`: `python3 ../build_rows.py`.

## Decisions

1. Same-tab navigation, so the browser back button works too; `back=` is `location.href`, which already holds the rail (`?deployment=…`) and the tab (`#tab=targets`).
2. "Selected" = the target view's checkboxes, starting as the rail's runs for that target (the others listed unchecked).
3. The target page is full width: the most room for the joint-error charts.

## Best when / loses when

- **Best when** the target view is where you spend time (repeats, bands, joint by joint) and want all of the screen for it.
- **Loses when** you flip often between targets: each round trip reloads the 19 MB runs file (3.5–4.7 s to ready here).

## Splice parts

- `keep=` + `back=` carry-over (works with any page that reads the URL).

## This variant's own gaps and proofs

- Back: proved the link is `/v2/index.html?dry=1#tab=targets` (it keeps the query and the tab).

## Shared by all five (stock, from `../build_rows.py`)

- **Outer view = one stock `<data-workbench src="views.base">`** (data-ui `e8c73dc`, CONTRACT §53) over
  `data/rows-runs.json`: 18,507 runs of all four deployments (UR5e cell 5,750 · UR5e alone 3 · BAM FB 4,972 · pendulum
  7,782), noun "runs". Rail: Deployment, Dataset (36, "Conveyor PnP v1 · UR5e + Conveyor PnP cell": a dataset value
  always carries its deployment), Split, Model type (proposed), Config, Sim / real, Speed, Motion kind, Target, Name
  search. Tabs Overview · Targets · Runs, on the component's own top; the pills show the filter on every tab.
- **Overview:** the League (configs) and the League by model type, both a two-stage median done in stock Vega-Lite over
  the runs (a target's value = median over its runs, a config's = median over targets, at 1.0 ×; rank, value, × best and
  n targets in the label), and Speed sweeps (tool RMS vs speed, one small multiple per model type, one line per dataset).
  Headline numbers only here.
- **Targets:** `data/rows-targets.json` (2,558) linked one-way from the runs, so it lists only targets with a run left
  ("260 of 2,558 rows" after one dataset tick). **Runs:** the runs table; each row drills (stock record pane): Open target
  view ↗, Open run report ↗ (`/bench/<site>/runs/<report>/report.html`), Open in Rerun (stock `post:` to
  `/__rerun/selection?runs=<site>:<line>`).
- **Colour = dataset** (`properties.dataset.colors`, 36 golden-angle hues; badges and the Speed sweeps legend explain
  it). League dots are one grey; Sim / real has no colour.
- **Model type** is a PROPOSED mapping (`MODEL_TYPE` in `build_rows.py`), labelled "proposed" in the rail and on the
  League. Unmapped → "other (one-off rig run)": `fullarm_jtc refit`, the W2 release reversal, the wrist self-check.
- **Host (`host-common.js`, one copy per variant, v1's is the source):** `html[data-ready]`, the cross-deployment
  warning line, the Fold button, and `onDrill` (a host action on a stock drill button).

## Gaps every variant shares (named, not patched)

1. **No date column** in any bench run: no date-range facet.
2. **A drill action cannot run host code**: data-ui runs `href` / `post` / `copy` only. The host intercepts the stock
   button's click (capture phase, matched by its label). Needs: `drill.actions[].event` (a `data-scope-drill` event).
3. **`post:` sends no body**: Open in Rerun puts the runs in the query string (the round's endpoint accepts both).
4. **Drill actions are per file, not per dataset**: a Targets row shows Open run report, which has no `{report}` (404).
5. **No conditional note**: the cross-deployment warning is a host line above the component. Needs: a `notes:` entry
   with a condition (e.g. `distinct(deployment) > 1`).
6. **No fold at full width**: the stock rail only folds below 1,100 px; the Fold button sets the stock `fold="always"`.
7. **A colour legend lists every dataset**, also the ones the filter removed: with `colors:` set, data-ui takes the
   domain from all rows (stable colours), so the Speed sweeps legend is 36 entries long.
8. **data-ui chart quirks worked around** (from the first V5): no bars on a log axis (dots), an encoding aggregate over
   a transform's field draws nothing (medians written back as `tcp`), only columns named in a channel or `hover` reach
   Vega (target_key in `hover`), a sort after transforms is ignored (zero-padded rank), two facets on one property share
   their typed text (Name search is on `task`).
9. **Run reports are built lazily by `serve_round.py`**: none exists on disk in the bench (0 of 5,750 for UR5e).

## Real vs placeholder

Real: every number (the bench payloads via `extract.py` → `build_rows.py`), the target view (`common/target.html`, the
other lane's), the Rerun endpoint (proved with `dry=1`: "Built (not launched): N lines + target"). Placeholder: the
model-type mapping (proposed), the dataset colours (generated hues, not the bench's).
