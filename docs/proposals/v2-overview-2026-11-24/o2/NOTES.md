# O2 — Model × dataset matrix first

**Thesis:** The Overview is one grid: model type (proposed) › config down, deployment › dataset across, median tool RMS in each cell, the best of each column ringed and read off a roll-up row; the columns switch to split, speed or deployment, model types fold.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/serve.py --port 8851`, then
`http://127.0.0.1:8851/o2/index.html`. Made by `../build_bases.py` from V2 (only the Overview page and its views differ).

## Decisions

1. Rows nest in one column at one pitch (§56's look): a model type's row pools every run of its configs per target, then the median over targets.
2. Columns: deployment › dataset by default; Split / Speed / Deployment one click away. Every axis but speed is at the fastest speed left.
3. Roll-up row = each column's best config (its colour and value); roll-up column = the row over every column.
4. A cell opens that config's worst targets in that column (a card under the matrix, each target linking V2's target view).

## Best when / loses when

- **Best when** the question is where each model and config wins, and where it has never run (Zach's model × dataset example).
- **Loses when** you want energy, jerk, stop error or the shape over speed in one look: the cells are tool RMS only; unfiltered the grid is 34 columns wide and scrolls.

## Splice parts

- nested model-type rows that fold
- the column-axis switch
- the roll-up row of column bests
- hatched no-run cells

## Proof

`node ../check.cjs o2 --port 8851 --video` → `../shots/o2/check.json`: the numbers before and after the UR5e-cell tick
against `../oracle.json` (Python), the story's stills and video, V2's tabs, rail drag, fold and target link.

## Gaps

The round's data-ui gaps are in `../kit/GAPS.md`; V2's own (`../../tensorboard-2026-11-24/v2/NOTES.md`) still hold. Real:
every number (the 18,507 runs). Proposed: the model-type mapping (`MODEL_TYPE` in V2's `build_rows.py`).
