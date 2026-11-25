# T3 — "Which config wins head to head?"

**Thesis:** a fourth tab for the decision before shipping a config: pick A (what you run now) and B (the candidate);
on every target both ran, per sim/real, B against A, counted as wins, ties (within 5 %) and losses, with where B regressed.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-tabs-2026-11-24/serve.py --port 8852`,
then `http://127.0.0.1:8852/t3/index.html` and the fourth tab. Rows: `python ../build_tabs.py` (`data/h2h.json`).

## What is on the page (a stock `.base` page, `t3/views.base`, generated)

- **Its own control, A · current and B · candidate:** two stock `select` facets (dropdowns, §53 page control) over the
  match-ups; each lists only the configs that ran with the other pick. Default A = ctc_tuned, B = ctc_tuned_v2.
- **The answer:** "B ctc_tuned_v2 beats A ctc_tuned on 376 of 502 targets they both ran, loses on 8, ties 118; median
  B ÷ A = 0.57 (B 43 % better)", and under it the biggest regression and the biggest gain by name.
- **Per dataset** (wins / ties / losses, stacked), **each target** (A against B, log-log, B = A line, colour = verdict),
  **against speed** (median B ÷ A per speed), and **where B regressed most** (a row → the stock drill pane → Open target
  view: `keep=` A's and B's runs of that target, `back=` this tab with the filter).

## Decisions

1. A match-up row = one target × sim/real × A × B where both configs ran it; each side's value is the median tool RMS
   over that config's runs of the target (`build_tabs.py`, `build_h2h`), the League's first stage.
2. A tie is within ±5 % (stated on the page). Verdict colours are blue / grey / purple: none of them is amber or red,
   because a regression is the candidate's problem only once you decide to ship it.
3. Four one-way links from the runs (target, sim/real, config → A, config → B; ANDed, §17 P1a): a match-up shows only
   when its target, its sim/real and BOTH configs are among the runs the rail keeps. Ticking only one config in the rail
   empties the tab: tick both, or leave Config open.

## Best when / loses when

- **Best when** you are about to replace a config and need to know where the new one is worse, not only its median.
- **Loses when** the two configs share few targets (BAM FB's real configs ran 1–14 targets each); and on load: the
  match-ups are 26,442 rows (15.9 MB), read with the runs before the tab is opened (about 1 s more to ready).

## Splice parts

- the A/B page control over a match-up dataset;
- "biggest regression / biggest gain" by name under the answer.

## Gaps (named, not patched; each with its ask)

1. **The first click on a match-up row throws.** The dashboard's `drill()` hands its sheet the 26,442-row h2h dataset
   and calls `openPeek` before the sheet has a model: `TypeError … reading 'pivot'` (stack: `openPeek` ← dashboard
   `drill` ← `_clicked`); a second click works. Likely the row-model worker (`WORKER_ROWS` = 5,000) answering after
   `openPeek`; but V2's Runs table (18,507 rows, no view filter) opens on the first click, so size alone is not the
   whole trigger (this table also has a view-level filter). Worked around in `host.js`: the stock `drill()` (a public
   method, §17) is retried once the sheet draws. Ask: `drill()` waits for the sheet's first model.
2. **An `argmax` row carries only the columns a channel or a transform names**, so the regression's name needed a
   `calculate` that reads `datum.target`. Ask: the columns in `hover.fields` reach every aggregate's rows.
3. **Every plain `datasets:` file is read at load** (§53), so the 15.9 MB match-ups load before the tab is opened. Ask: a
   page's own dataset read when the page is first shown.
4. **The match-ups are derived at build time:** each side's median is over all of its runs of that target; the rail
   decides which match-ups show, not which repeats count (no repeat facet exists today, so nothing is lost yet). Ask: a
   dataset derived in the page from the runs the rail keeps (T1's gap 2).
5. **A stale median after a filter, when one aggregate holds a median and an argmax of the same field.** Vega-Lite
   merged the answer's two lines (same groupby) into one aggregate; after Speed = 1.0 × the median stayed at the
   unfiltered 0.570 while the counts moved (once in three runs; vega's TupleStore memo, which data-ui's chart already
   documents and tries to avoid by rebuilding the cells). Worked around in the spec: the argmax reads `change`, not
   `ratio`; the recount then held in four repeated runs (n 158, median 0.982). Ask: data-ui's fresh-cells rule covers a
   merged aggregate (or splits a layer's aggregates).
6. The sentence answer: T1's gap 1; the speed line's points: T1's gap 3. V2's gaps hold.

## Proof (check.cjs, `shots/t3/check.json`, headless Chrome 1440 × 900)

- Recount = oracle: every run 502 targets (376 B better, 8 A better, 118 ties, median 0.570); Speed = 1.0 × 158 (35, 5,
  118, median 0.982); stable over four more repeated runs.
- Drill: the worst regression → `keep=` A's and B's 6 runs → target view with 6 of 9 lines checked; Open in Rerun → 6
  (dry); ‹ All targets returns to this tab at 8,520 of 18,507 runs.
- V2's checks unchanged; 0 console errors (with the drill guard), 0 px sideways.
