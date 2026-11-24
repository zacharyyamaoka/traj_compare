# V2 · Rows first (data-ui)

**Thesis.** The dataset is a table of trajectories. Coverage is what the rows you have filtered add up to. Every focus area
is a data-ui view of the same 54 rows. The rail, the Find box and a view's own filter narrow those rows, and each map
redraws from what is left. Each map labels its subset ("subset 12 of 54 · re-aggregated").

Run it: `/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port 8812`,
then open `http://127.0.0.1:8812/v2/index.html`.

## Decisions that matter

1. **The focus areas are data-ui view tabs, not a host tab row.** Overview, One joint, All joints, Tool position, Tool
   orientation and Trajectories are presets of one `<data-views>`. A saved view is the same kind of thing as a focus
   area. "New ground" is the table sorted by the cells only that trajectory visits. "Holdout reach" is Tool position
   with `filters: split == "holdout"`, so a saved view can be a saved subset of the coverage. Save view and + come from
   data-ui (the user's views live in localStorage).
2. **Every map counts trajectories per cell**, the same measure as the payload's `paths`. The count is re-aggregated from
   `membership.json` over the rows data-ui hands the view. The page checks this at load: with nothing filtered, all
   22 grids, the 1 283 voxels and the 10 headline numbers must equal analyze's. The map then shows "✓ = analyze's own
   counts". On a mismatch it prints a console error, so G5 fails. `tools/emit.mjs` runs the same check in Node. The
   numbers that need every sample do not re-aggregate: peak speed or acceleration as a % of the limit, joint range at
   p0.1–p99.9, and tool speed p99. The Overview shows them as "whole set only".
3. **Controls sit where they apply.** The headline numbers are stock `<data-kpi>` cards and appear only on Overview. A
   subset value carries data-ui's "~ derived" mark. The joint picker lives inside the One joint view, and the pick is a
   view key, so Save view keeps it. The colour map, Reverse and scale sit behind one gear at the top right. They live
   in a host store that every registered view subscribes to, and the setting persists.
4. **Text filter and sorting.** Under data-ui §47 the tabs form always folds the query bar behind its Search icon. The
   always-visible text filter is therefore the rail's stock `search` facet ("Find", over name, split, kind and tags). It
   writes the same all-views filter as the query bar, so the maps narrow too. A header click sorts: high to low first
   for numbers, A to Z for text. Data-ui's own click opens Notion's column menu, so the host catches that click; the
   gaps list explains how.

## Best when / loses when

- **Best when** the question is about a slice: "what does holdout cover that dev doesn't", "what would I lose if I
  dropped this kind", "which trajectory is the only one in this corner". You can click a map cell to see the trajectories
  through it in data-ui's record pane. One vocabulary covers everything (rail, pills, tabs, status line, peek), the same
  as robotparts and Vibe Tracks.
- **Loses when** you want density by time: a map counts trajectories per cell, so a long dwell counts once. It also
  loses when you want the motion itself. The live page's spaghetti, envelope, slabs, ridgeline, parallel coordinates,
  growth curve, tool speed and 3-D views are not here, because none of them re-aggregates from cell membership. Eight
  tabs fill the bar, so more saved views fold into "N more…".

## Worth keeping in a splice

1. **The `occupancy` view** (`js/views.js`). It is generic: each row lists the cells it visits, and the view draws rows
   per cell. It supports a shared colour scale, a limit frame, an unreachable mask, a picker over panel groups, marginal
   bars and the hero layout. Hovering a cell gives its count; clicking it calls `host.open(..., {records})`. The `.base`
   spec carries all the geometry, so the view knows nothing about robots. Its partner is `js/aggregate.js` `oracle()`.
2. **The subset line and derived KPI cards.** The line reads "subset 12 of 54 · re-aggregated from these trajectories'
   cells", or "✓ = analyze's own counts" when nothing is filtered. The header chip says "Subset: 12 of 54
   trajectories".
3. **The drill: what this trajectory adds** (`js/drill.js`, through `el.peekExtra`). Open in Rerun sits in data-ui's
   own record pane, with ‹ n of N › stepping. Beside it are the trajectory's tool pixels from above, cropped to the
   dataset's extent, and its position × speed cells per joint. Blue marks this trajectory, black marks cells no other
   trajectory visits, and grey marks the rest. The black counts equal the table's "Only it".

## Simulated or missing

- There are no samples-per-cell maps for a subset: membership holds which cells a trajectory visits, not how often.
  The sphere's payload counts are samples, so for directions the oracle checks only the visited set.
- No 3-D views. Voxels appear only as a count.
- The drill shows cells, not time series. The motion opens in Rerun.
- If `/__rerun/open` fails, the Copy fallback builds its command from the round's absolute path (pinned to rerun-sdk
  0.40.0, as traj_compare's `viewer_command` is). The server's own `command` is used when it sends one.
- check.cjs runs its story in the same browser context as its gates. The landing still shows magma, which the G4b gate
  set and the setting kept. Story step 3 switches to cividis.

## data-ui: stock, new, and what would make it stock

**Stock, untouched:**
- `<data-views>`:
  - the bar: tabs, `+`, Search, Display panel, Reset / Save view
  - the pill row and the status line ("12 of 54 rows · 2 groups · Unfold all · Fold all")
  - the table: group by split with fold and sums, `bar` and `badge` displays (split colours are badge slots 1 and 7,
    with a legend in the header), sorting
  - the record peek: `record.sections`, "N more properties", ‹ n of N ›
  - the "records behind this cell" peek
- `<data-facets>`: `search`, `values` with disjunctive counts, `slider-histogram`, `range`, Clear all.
- `<data-kpi>` cards and the `derived` basis.
- `registerView`, `stringifyBase` and `data-ui check`. `coverage.base` is generated by `tools/emit.mjs` and reports 0
  errors. Its only 12 warnings are the two view types V2 registers.

**New views V2 registers:**
- `occupancy`: generic, five panels' worth of options.
- `coverage-overview`: KPI cards, small copies of the other views' panels, and the whole-set-only line.

**How a host learns the filtered rows.** There is no gap here: a registered view gets them as `input.rows`
(`input.total` = 54). The host reads `el.model.rows` on `data-views-change` / `data-views-render`; the header's subset
chip does this.

**What data-ui would need to make this stock:**
1. **`occupancy` as a stock view type**, with its keys (`cells`, `shape`, `order`, `xAxis` / `yAxis`, `frame`,
   `unreachable`, `marginals`, `pick`, `layout`) in `schemas/view.schema.json`.
2. **A "distinct items" summary over list cells:** the size of the union, or its share of a total. With it, the
   Overview's cell, pixel, voxel and direction numbers become stock `kpi` / `intro.kpi` summaries, and
   `coverage-overview` is no longer needed.
3. **Page-level settings that every view reads**, such as `configure({colormap, reverse, scale})` → `input.settings`,
   with a gear in the bar. V2 uses its own store beside data-ui.
4. **`header-click="sort|menu"` on the table.** Today a click opens the column menu and a shift-click sorts. V2 catches
   the click in the capture phase and calls `setView({sort})`.
5. **Tabs that use a registered view's `icon`.** `layoutIcon` falls back to the table icon, so every tab shows a table.
6. **"Save view" that can keep the rail's filter.** Today it saves the view entry only. "Holdout reach" uses a
   view-level `filters:` written in the `.base`; a reader cannot yet make one from the rail in one step.
7. **`peekExtra` that can return a node or a mount callback.** Today it returns HTML, and V2 draws its canvases on
   `data-views-open`.
