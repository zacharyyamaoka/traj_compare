# V1 · Stock dashboard

**Thesis:** it really is just a dashboard on data: here is the coverage page built from data-ui as it is today, with
zero new data-ui code, and the honest list of where stock falls short.

All eight gates pass (`node check.cjs v1 --port 8811 --shots shots`, exit 0). Open it with the round server:
`/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port 8811`
and then `http://127.0.0.1:8811/v1/index.html`.

## What it is

- **Seven pages, seven `.base` files.** Overview, Limits, One joint, All joints, Tool position and Tool orientation are
  each a `.base` drawn by one stock `<data-dashboard>`. Trajectories is a stock `<data-views>` table with a stock
  `<data-facets>` rail. Every file passes `node /home/bam/data-ui/bin/data-ui.mjs check <file>.base`.
- **Navigation is data-ui's own app rail** (`<data-rail>`, Figma style). A hash router swaps the `.base` file, the same
  pattern as data-ui's `gallery/examples/admin-shopify/app`.
- **The data is rows.** `rows.py` reshapes `data/coverage.json` and `data/trajectories.json` (plus a few columns of
  `samples.json`) into 18 row tables in `rows/`. It computes nothing: it expands the payload's `[low, high, n]` edges
  into each cell's lo/hi, and it applies the payload's own display scale (rad→°, m→mm). Empty cells are not rows, so
  white means never visited. The reachable mask is stored as run-length rows. The q×qd paths and the parallel-coordinate
  cells are stored as list cells, and the chart's stock Vega-Lite `flatten` expands them in the page. Nothing is
  subsampled.
- **The figures are stock data-ui views.**
  - `kpi` cards for the 15 headline numbers, on the Overview only.
  - `table` with bar cells for each joint in numbers.
  - Vega-Lite `rect` heatmaps: q×qd, qd×qdd, the qdd slabs, max |qdd| per cell, the xy/xz/yz projections, the fastest
    speed per pixel, tilt×yaw and the parallel-coordinate density. Each is layered with the limit box or the reachable
    mask.
  - Vega-Lite `bin: binned` bars for the histograms (stacked by split, with limit rules and the grey margin), plus the
    tool speed and the tilt and yaw histograms.
  - A Vega-Lite `arc` polar disk for the tilt map.
  - A Vega-Lite line and area for growth, with its shuffled band.
  - Stock `voxels` for the 5 cm voxels and a stock `scene3d` lines layer for the 3-D tool paths.
  - Dashboard `text` panels as each page's legend line.
- **The trajectories table** is the reference Zach pointed at:
  - saved views as tabs across the top: By split, Most new cells, Holdout only, Speed span and Tool, with `+` to add
    one and Save view;
  - a filter rail (word search over name, split, kind and tags, plus Split, Kind and Tags);
  - groups by split that fold ("54 of 54 rows · 2 groups · Unfold all Fold all");
  - one-click sort.

  A row opens data-ui's side peek ("1 of 54", ↑/↓ steps). The peek shows the trajectory's numbers, its joint angles over
  time (a `timeseries` embedded through `record.sections`, `samples` filtered to `this.name`) and **Open in Rerun**.
- **Group colours.** The table draws no colour beside a trajectory (gate G3: `none`). Where split has a colour (the
  Limits bars, the q×qd paths, the 3-D paths), the chart's own legend names it, and `style.palette` keeps dev blue and
  holdout green on every page.

## Consequential decisions

1. **One dashboard element, a file per page.** The joint picker (a stock select facet in the dashboard's rail) only
   exists on the One joint file. G1 and G4a therefore hold by construction, with no show/hide code. The cost is that
   the picker is a left rail (with an "Every joint, overlaid" option and per-joint cell counts, both stock), not a small
   dropdown.
2. **Trajectories is a plain `<data-views>`, not a dashboard panel.** A plain element lets the host hand it
   `sections` (the drill's samples) and `openElsewhere` (Rerun) before it opens anything. A dashboard's drill peek is
   created on the fly, with no hook.
3. **The gear rewrites the Vega-Lite colour scales.** It touches every colour channel whose scale names a `scheme` and
   redraws through the dashboard's public `load(base, datasets, {keepState: true})`, so picks and rails survive.
   - linear → `linear`;
   - log → `symlog` (zero-safe);
   - equalized → `quantile` with nine colours;
   - enough → `threshold` at the payload's `enough` (10), on sample counts only.

   The choice is kept in localStorage, so the story's landing is in magma: the gate run set it, and the walkthrough
   reloads the same browser profile.
4. **Histograms use a √ height** instead of the live page's linear scale clipped at p98, because Vega-Lite has no "clip
   at p98". Heatmaps default to linear (Zach's pick) and the gear offers the rest.

## Best when / loses when

- **Best when** coverage should be one more dashboard in the common visual language. An agent edits YAML, and a new
  figure is a dozen lines of `.base`, checked by `data-ui check`. The table, the filters, the saved views, the peek,
  the rail and the KPI cards come for free. Every future data-ui improvement lands here too.
- **Loses when** a figure needs polish that data-ui does not have:
  - the p98-clipped linear scale and its "dark cap";
  - equal aspect on the xz/yz projections (they stretch);
  - figure titles that name the picked joint;
  - highlighting one trajectory across every figure from a table click;
  - the direction sphere and the 3-D proposals tab (left out);
  - each figure's own legend and "How to read this" (replaced by a text-panel line per page).

  Pages also read about 11 MB of rows in total, loaded per page (samples.json alone is 3 MB, for the drill).

## Parts worth keeping in a splice

- **`rows.py`.** The payload as row tables, with no recompute. Any data-ui variant can reuse it as is.
- **The trajectories page.** Stock table, filter rail, saved views as tabs, folding split groups, and a side peek with
  an embedded per-trajectory time series plus Open in Rerun through `openElsewhere`.
- **The gear as a scale rewrite** (`colourScale()` in `index.html`, about 20 lines). It is the smallest bridge until
  data-ui has a dashboard-wide colour setting. The polar tilt map in plain Vega-Lite `arc` marks is a small bonus.

## Stock, new, and what data-ui would need

- **Stock data-ui parts used:**
  - `<data-rail>`;
  - `<data-dashboard>` (layout panels, datasets, one-way links, select facets in its rail, text panels, `load()`);
  - `kpi`, `table` (bar display), `chart` (Vega-Lite, every figure above), `voxels`, `scene3d` (lines layer);
  - `<data-views>` (presets as tabs, `fill`), `<data-facets>` (search and values facets);
  - the side peek with `record.sections` and an embedded `timeseries`;
  - `openElsewhere`'s "Open in Rerun";
  - `loadDataset`.
- **New views registered:** none. `registerView` is never called, and no data-ui file was copied or edited.
- **Host code** (the one `<script>` in `index.html`, about 140 lines; each item is a gap):

| # | Gap | Host workaround here | What data-ui would need to make it stock |
|---|---|---|---|
| 1 | No dashboard-wide setting (colormap, Reverse, scale) | A gear in the page header rewrites each chart's colour scale and calls `load(…, {keepState})` | `style.colormap: {scheme, reverse, scale}`, resolved like `style.palette` (dashboard → panel → view). A stock ⚙ in the dashboard bar that edits it. `voxels`' ramp honouring it (today: one family hue or grey, so the gear does not reach the voxels). |
| 2 | Open in Rerun is per dashboard (`rerun: {rrd}`, docs/RERUN.md), not per record | `openElsewhere` returns the row's `.rrd`; a click handler POSTs `/__rerun/open?rrd=…` and shows the command with Copy on failure | A view key such as `open: {rerun: <property>}` that draws "Open in Rerun" in the peek with RERUN.md's three forms. An optional host launcher URL for the native viewer. |
| 3 | A header click opens Notion's column menu (CONTRACT §28); shift-click adds a sort level | A capture-phase click sets `sort` (ascending, descending, off) through `el.setView`; Alt-click still opens the menu | A `headerClick: sort \| menu` view key (or attribute). |
| 4 | No pages in a dashboard file | `<data-rail>` + a 10-line hash router swapping `src` | A `pages:` key (or a `<data-app>` element) that lists `.base` files with a stock tab strip or rail. |
| 5 | Data-ui hands a list cell to Vega as `"a, b, c"` text | `calculate: split(datum.q, ', ')` before `flatten` (paths, parallel) | Pass list cells to Vega as arrays (`plain()` in `chart/src/index.js` joins them). |
| 6 | A select facet always offers "Any" and shows counts | `any: "Every joint, overlaid"`, plus an ⓘ note that the counts are cells visited | `any: false` and `counts: false` facet options. A one-pick dropdown in the dashboard bar instead of the side rail. |
| 7 | The tabs form folds the table's query box (CONTRACT §47: presets OR controls) | The text filter is a `search` facet in a stock `<data-facets>` rail beside the table | Nothing, if the rail is the answer. Otherwise an option to keep the query box open beside the tabs. |
| 8 | The empty selection-chip bar takes a row (`arrange: false`, no chips) | One CSS rule hides `.dd-bar` while it is empty (a skin rule) | Do not draw the bar while it holds nothing. |
| 9 | `chart` has no equal-aspect option (only `trajectory` does) | None: the xz/yz projections stretch | `aspect: equal` on `chart`. |
| 10 | No percentile clip on a scale (p98) | √ bar heights; the gear's log/equalized for heatmaps | A `clip: p98` scale option, with the clipped marks flagged. |
| 11 | `trajectory3d` draws a per-series mode strip (54 rows here) and fades to 1/n | A `scene3d` lines layer instead (one draw call, hue by split) | `controls: false` honoured by `trajectory3d`, and an opacity floor. |
| 12 | A panel title cannot name the current pick | Titles say "it"; the rail shows the pick | `{pick:<property>}` templating in panel titles. |

## Simulated or missing

- **Open in Rerun.** `check.cjs` intercepts the POST. The real `traj_compare.serve` endpoint was not exercised,
  because it opens a native window.
- **Left out of the live page:**
  - the envelope (replaced by "How hard does it accelerate at each position and speed?", from the payload's
    `max_other`);
  - the direction sphere;
  - the 3-D proposals tab;
  - row-click highlighting across figures;
  - the per-figure "How to read this".
- **The 3-D tool paths** come from `samples.json`'s own tool points (every sample), not from the payload's
  `tool.spaghetti`. Their dots are each path's marker at the dashboard clock's t (0 s, its start).
