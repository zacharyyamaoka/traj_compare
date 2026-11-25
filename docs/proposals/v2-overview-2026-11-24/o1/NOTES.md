# O1 — The League, back, over the rail

**Thesis:** Nov 23's Overview, recomputed over whatever the rail leaves: the answer sentence, the League table (every KPI at the fastest speed with its shape over speed, best-in counts, a worst-targets drill) and the config × dataset · split matrix whose column click ranks the table.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/serve.py --port 8851`, then
`http://127.0.0.1:8851/o1/index.html`. Made by `../build_bases.py` from V2 (only the Overview page and its views differ).

## Decisions

1. One host view (`tc-league`) draws the sentence, the table and the matrix, so the matrix's column click can re-rank the table (two stock panels cannot talk to each other).
2. More than 14 dataset · split values (50 unfiltered, 12 in the UR5e cell) become one select instead of chips; the matrix's columns stay the main switch.
3. Each config carries its deployment; with more than one deployment in the filter the sentence says so (V2's warning line stays above).
4. “worst targets →” opens a list of that config's 10 worst targets under its row, each linking V2's target view (keep= the rail's runs, back= here).

## Best when / loses when

- **Best when** you want Nov 23's page back: after the deployment tick it reproduces Nov 23's numbers exactly (0.0366 mm; 1.01×, 1.2×, 27×, 1,996×; best in 20 of 22, 4 of 44, 16 of 22, 4 of 44, 0 of 22).
- **Loses when** unfiltered: 23 configs and a 50-column matrix that scrolls sideways inside its card; there is no model-type grouping.

## Splice parts

- the answer sentence
- the League table with sparklines and best-in
- the matrix column → League switch

## Proof

`node ../check.cjs o1 --port 8851 --video` → `../shots/o1/check.json`: the numbers before and after the UR5e-cell tick
against `../oracle.json` (Python), the story's stills and video, V2's tabs, rail drag, fold and target link.

## Gaps

The round's data-ui gaps are in `../kit/GAPS.md`; V2's own (`../../tensorboard-2026-11-24/v2/NOTES.md`) still hold. Real:
every number (the 18,507 runs). Proposed: the model-type mapping (`MODEL_TYPE` in V2's `build_rows.py`).
