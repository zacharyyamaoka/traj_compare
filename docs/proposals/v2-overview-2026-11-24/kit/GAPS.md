# data-ui gaps this round met (named, not patched; data-ui main 1f7c004)

Each variant's NOTES.md points here. "Ask" is the exact change that would retire the host code.

1. **A registered view cannot say it is content-sized.** A `.dd-panel` without `h` sizes a kpi / gauge / tracker to its
   content, but a `registerView` type gets the 440 px default. Worked around: one rule in `kit/views-css.js`
   (`.dd-panel:not([data-sized])[data-type^="tc-"] data-views { height: auto }`).
   *Ask:* `registerView(type, {fit: 'content'})`, or §53's planned `rowHeight: fit`.
2. **A records peek's rows open nothing.** `host.open(id, {records, row})` lists the records as a plain table under a
   synthetic row; a record there is not clickable, so the file's `drill:` actions (Open target view ↗) are out of reach.
   It also needs a `row` (`openPeek` returns early on `null`) and shows every column unless `dataset.records.columns`
   is set. Worked around: the "worst targets" drill is the host view's own list, each row a V2 target-view link.
   *Ask:* a records peek row opens that record in the same peek (the trail, `open.js`), drill actions included.
3. **A two-stage median is not a summary.** The rule on every figure ("median over targets of each target's median
   over its runs") has no stock form: a pivot's `value.summary` is one stage over rows, a table's `rollup` cannot feed a
   pivot, and Vega-Lite can do it (V2 did) only as text labels on dots. *Ask:* `value: {summary: Median, per:
   target_key}` = the summary over per-group summaries, on pivot, kpi, tracker and chart.
4. **§56's nested matrix holds states, not numbers** (O2). Its rows nest exactly as O2 needs (one pitch, indents,
   Unfold all), and its `axes` are O2's column switch, but a cell is a pass / fail word and a group the worst of its
   children. *Ask:* `tracker.value: {property, summary, per}` drawing a number on §52's colour map, `best: min` ringing
   each column's best leaf, a group row = the summary over its leaves' runs, and `rollup: best` (the column's best row).
5. **§49 `best:` marks a row's best cell, not a column's** (O1, O2 rings). *Ask:* `best: {among, by, along: column}`.
6. **A chart's colour has eight slots, then "Other (N)"**, and with `colors:` its legend lists every value, also the
   filtered-out ones (V2's gap 7: a 36-entry legend). O4 and O5 need one colour per config (up to 30) and only what is
   drawn. Worked around: host SVG with direct labels. *Ask:* `chart.labels: end` (a direct label per series at its last
   point, collision-avoided) and a legend over the drawn domain only.
7. **§55's tile number is a kpi summary over rows** (O3): "the best config by the two-stage median" is no summary, so
   a tile is a host view. *Ask:* a view plugin's `headline(input)`, read by §55's tiles and thumbnails.
8. **A host view's switch is not in the URL.** The views keep their switch (O1's dataset · split, O2's columns and
   folds, O4's panels, O5's cost) in localStorage per variant; `host.setView` from a dashboard panel inside a scope was
   not exercised here. *Ask:* confirm (and test) that `host.setView` in a workbench page's panel lands in the URL.

V2's own gaps (its NOTES.md: no date column, a drill action cannot run host code, `post:` sends no body, …) still hold.
