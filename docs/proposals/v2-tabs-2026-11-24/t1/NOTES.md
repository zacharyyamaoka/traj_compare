# T1 — "Does sim match real?"

**Thesis:** a fourth tab that pairs every real run with its prediction of the same commanded motion (the sim twin, or
the pendulum's dress rehearsal) and answers in one sentence how far off the prediction is, per config, against speed,
and where it is most wrong.

Serve: `/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-tabs-2026-11-24/serve.py --port 8852`,
then `http://127.0.0.1:8852/t1/index.html` and the fourth tab. Rows: `python ../build_tabs.py` (`data/pairs.json`).

## What is on the page (a stock `.base` page, `t1/views.base`, generated)

- **Its own control, Real against:** sim twin (default) · rehearsal · Any (the stock page-level `select` facet, §53).
- **The answer** (a Vega-Lite text mark over the kept pairs): "On the real robot the tool error is 1.21× what the sim twin
  predicted: median real ÷ predicted over 1,752 paired runs; real was worse in 1,381 (79 %)", one line per deployment
  under it.
- **Per config:** median real ÷ predicted, n pairs, the line at 1. **Each pair:** predicted against real tool RMS, log-log,
  y = x (data-ui's `indexLine` guide). **Against speed:** the median per speed per deployment.
- **Where they disagree most:** the pairs sorted by how far apart (× either way); a row → the stock drill pane → Open
  target view: `keep=` the pair's two lines, `back=` this tab with the filter; Open in Rerun in the same pane sends the two.

## Decisions

1. A pair is one run folder holding a `real` line and its `sim` (or `rehearsal`) line: the same commanded motion, the
   prediction and the measurement (`build_tabs.py`, `build_pairs`). No pairing across folders, so nothing is matched by
   guess.
2. The metric is tool tracking RMS (mm), the League's; the worst-joint RMS (°) rides along in the table.
3. The pairs are a dataset linked one-way from the runs by run folder: the rail decides which pairs show (a pair stays
   while either of its runs passes), so the Sim / real facet does not empty the tab.

## Best when / loses when

- **Best when** you are deciding whether to trust the twin (or which config the twin predicts worst) before a real run.
- **Loses when** the deployment has no real runs (the UR5e cell has none): the tab is empty there, and says so only by
  its count.

## Splice parts

- the pairs dataset (run folder → real + prediction), reusable by any page;
- the one-sentence answer over a derived dataset.

## Proof (check.cjs, `shots/t1/check.json`, headless Chrome 1440 × 900)

- Recount = oracle: every run 1,752 pairs, median 1.212, real worse 1,381; Deployment = BAM FB 26 pairs, median 1.9955,
  real worse 24.
- Drill: the pair that disagrees most → `keep=0,1` → target view with 2 of 2 lines checked; Open in Rerun → 2 lines
  (dry); ‹ All targets returns to this tab at 4,972 of 18,507 runs.
- V2's checks unchanged: one dataset tick 18,507 → 4,576; rail 248 → 368 px, 368 after reload; folds; 0 console errors,
  0 px sideways on all four tabs.

## Gaps (named, not patched; each with its ask)

1. **A sentence answer is a Vega-Lite text mark with fixed pixel rows.** The panel's plot box is shorter than the
   chart's canvas, so a text at the canvas middle was cut off. Ask: an `intro:` (§16) or headline (§55) whose text is a
   template over a summary of the page's rows (`"{median ratio}× over {count} pairs"`).
2. **A derived dataset is fixed at build time.** The rail recounts which pairs show, but cannot re-aggregate inside a
   pair (none needed here; T3's per-target medians are the case). Ask: a dataset derived in the page from the default
   dataset (`derive: {groupby, pivot}`), so pairs are made from the runs the rail keeps.
3. **A line's `point: true` overlay is drawn from every row, not the aggregate** (each pair's ratio appeared as a dot
   under the median line). Drawn instead as layers that each carry the aggregate (`build_tabs.py` `line_with_points`).
   Ask: the point overlay of a line reads the line's own transformed data, as Vega-Lite's does.
4. V2's own gaps (its NOTES.md) all hold: the drill is a host action on a stock button (`host.js`), `post:` sends no body,
   drill actions are per file (a pair row offers Open run report: the REAL run's report).
