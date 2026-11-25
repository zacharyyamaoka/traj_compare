# O5 — Trade-off map

**Thesis:** Each config is one point, accuracy (tool RMS, log) against a cost (energy per task, or jerk, or stop error), one panel per deployment, the Pareto frontier drawn and named: which config is best and what it costs.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/serve.py --port 8851`, then
`http://127.0.0.1:8851/o5/index.html`. Made by `../build_bases.py` from V2 (only the Overview page and its views differ).

## Decisions

1. One panel per deployment: a config on two robots is a point in each, never one frontier across robots.
2. The cost switches between energy per task, tool jerk RMS and stop error; point size = n targets.
3. On the frontier = no other config of that deployment is both more accurate and cheaper; the answer names its two ends, the table marks every member.
4. A row's “worst targets →” opens its worst targets in that deployment, each linking V2's target view.

## Best when / loses when

- **Best when** two configs are close on accuracy and you need the tiebreaker (UR5e cell: ctc_tuned_v2 0.0366 mm at 42.9 J against id_pd 0.043 mm at 22.8 J).
- **Loses when** you need to know where or at what speed a config wins; a config without the cost tag leaves its panel (UR5e alone, most of BAM FB's).

## Splice parts

- the per-deployment frontier
- the cost switch
- the frontier named in the answer

## Proof

`node ../check.cjs o5 --port 8851 --video` → `../shots/o5/check.json`: the numbers before and after the UR5e-cell tick
against `../oracle.json` (Python), the story's stills and video, V2's tabs, rail drag, fold and target link.

## Gaps

The round's data-ui gaps are in `../kit/GAPS.md`; V2's own (`../../tensorboard-2026-11-24/v2/NOTES.md`) still hold. Real:
every number (the 18,507 runs). Proposed: the model-type mapping (`MODEL_TYPE` in V2's `build_rows.py`).
