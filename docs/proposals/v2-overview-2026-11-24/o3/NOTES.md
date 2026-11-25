# O3 — Headline tiles → drill

**Thesis:** Six calm headline tiles, each a small view whose title row and Open chip go to its full page (§55's Overview grid): best config, speed growth, energy frontier, model × dataset coverage, worst target, runs left.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/serve.py --port 8851`, then
`http://127.0.0.1:8851/o3/index.html`. Made by `../build_bases.py` from V2 (only the Overview page and its views differ).

## Decisions

1. Stock §55: each tile panel names the page it opens (`open:`); a tile is its own view, not a shrunken page.
2. The detail pages reuse the round's views (League, Model × dataset, Speed, Trade-off) plus a Worst targets page whose rows open V2's target view; Runs left opens Targets.
3. Every tile states one number and the rule behind it; the worst-target tile links its target view directly.

## Best when / loses when

- **Best when** you check in often and want the state at a glance, then go deep on one question.
- **Loses when** you want to compare across questions on one screen: the detail is a click away on its own tab, and the tabs grow to eight.

## Splice parts

- §55 tiles with Open
- the worst-target tile → target view
- the runs-left tile

## Proof

`node ../check.cjs o3 --port 8851 --video` → `../shots/o3/check.json`: the numbers before and after the UR5e-cell tick
against `../oracle.json` (Python), the story's stills and video, V2's tabs, rail drag, fold and target link.

## Gaps

The round's data-ui gaps are in `../kit/GAPS.md`; V2's own (`../../tensorboard-2026-11-24/v2/NOTES.md`) still hold. Real:
every number (the 18,507 runs). Proposed: the model-type mapping (`MODEL_TYPE` in V2's `build_rows.py`).
