# O4 — Speed is the x axis

**Thesis:** The Overview is tool RMS against speed, one line per config (not per dataset), a small multiple per model type or per deployment, labelled at each line's end, with the sweep table under it.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/serve.py --port 8851`, then
`http://127.0.0.1:8851/o4/index.html`. Made by `../build_bases.py` from V2 (only the Overview page and its views differ).

## Decisions

1. Colour = config and a direct label at each line's end: no legend at all (V2's 36-entry dataset legend is gone).
2. A config that ran at one speed only is an unlabelled dot in a crowded panel (hover names it); the panel's caption counts them.
3. One log y shared by every panel; panels per model type (proposed) or per deployment.
4. The sweep table marks the best config at each speed; a value opens that config's worst targets at that speed.

## Best when / loses when

- **Best when** the question is whether a config holds up when you go faster: which one wins at 0.1× and which at 1×.
- **Loses when** unfiltered the computed-torque panel holds 20 configs; there is no view by dataset, and energy or jerk are not on it.

## Splice parts

- per-config lines with direct labels
- the model type / deployment panel switch
- the sweep table with best chips

## Proof

`node ../check.cjs o4 --port 8851 --video` → `../shots/o4/check.json`: the numbers before and after the UR5e-cell tick
against `../oracle.json` (Python), the story's stills and video, V2's tabs, rail drag, fold and target link.

## Gaps

The round's data-ui gaps are in `../kit/GAPS.md`; V2's own (`../../tensorboard-2026-11-24/v2/NOTES.md`) still hold. Real:
every number (the 18,507 runs). Proposed: the model-type mapping (`MODEL_TYPE` in V2's `build_rows.py`).
