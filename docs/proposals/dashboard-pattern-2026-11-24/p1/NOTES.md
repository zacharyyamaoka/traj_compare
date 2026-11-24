# P1 · Workbench element

**Thesis.** The pattern is one new data-ui element, `<data-workbench src="coverage.base">`. It owns the whole pattern
inside its own box: a filter rail on the left, a strip of dashboard tabs along the top of the element (not the top of
the page), and the dashboards. The `.base` declares the rows, the rail (`facets:`, Dataset first) and `pages:`, where
each page is a dashboard of panels. A host drops it in as one tag. It is TensorBoard's layout without the app bar.

Run it:
`/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24 --port 8841`,
then open `http://127.0.0.1:8841/p1/index.html` (full page) or `/p1/embed.html` (inside a host app's 1000 × 680 slot).

The whole host page:

```html
<link rel="stylesheet" href="../vendor/data-ui/data-ui.css">
<script type="module" src="coverage/register.js"></script>        <!-- the app's own views (figures) -->
<script type="module" src="workbench/data-workbench.js"></script> <!-- the element (in core: dist/workbench.js) -->
<data-workbench id="coverage" src="coverage.base"></data-workbench>
```

## Decisions

1. **Every part inside the element is stock data-ui, and the element adds only the frame around them.**
   - Each page is a stock `<data-dashboard no-url>` (§17), made the first time its tab opens. It is loaded with the
     page's `layout:` over the file's `views:`.
   - The rail is a stock `<data-facets>`. It is bound to `<data-workbench-source>`, a 10-line element that implements
     the target interface data-facets already reads (`data, base, view, filters, model`), the same one
     `<data-dashboard-source>` implements.
   - The rail's filter is fed into every page as its default dataset's filter (`setRail`). The open page updates at
     once; the others update when they are opened.
   - The table, the record pane, the badges and the column colours are stock.
2. **The element's own box is the edge of the world.**
   - The tab strip, the count, the pill line and the gear all sit inside the element.
   - The dashboards column is `contain: layout`. The stock dashboard's drill sheet is `position: fixed; inset: 0`, and
     the containment makes it open inside the element instead of across the page.
   - Popovers ("N more", the gear) and figure tooltips are children of the element. Nothing is appended to `<body>`
     and nothing writes to the host's URL (`no-url`).
   - This is what makes "drops into anything" true rather than approximately true.
3. **The element's own width decides the layout, not the viewport.** A ResizeObserver on the element sets three
   modes. I measured them in headless Chrome (check P4 separately proves nothing draws outside the slot):

   | Element width | Rail | Tabs | Overview |
   |---|---|---|---|
   | ≥ 1180 px (full page) | open, 248 px | all 6 shown | rowHeight 158 px, fills 900 px |
   | 860–1180 px (the 1000 × 680 slot) | narrow, 196 px; labels wrap so "Cell · Conveyor PnP / Collision" stay distinct | all 6 fit in 756 px | rowHeight 114 px, 0 px scroll |
   | < 860 px (a 720 px slot, tried by hand) | folded to a button with a filter-count badge; opens as an overlay inside the element | 3 fold into "3 more ▾"; the open tab always stays visible | — |

   `rowHeight: fit` splits the page box among a layout's rows of panels, so one `.base` fills a 900 px window and a
   680 px slot without scrolling. Short cards switch layout: the headline numbers become a dense label · value list.
4. **The filter is visible from every tab.** It shows in three places:
   - the corner reads "28 of 212 trajectories";
   - one pill line under the tabs shows every rail pick, with its dataset colour dots and ✕;
   - every figure has its own subset line ("SUBSET 28 of 212 · re-aggregated", or "ALL 212 · = analyze").

   The pill line is always present ("No filter: all 212 …"), so ticking a box never shifts the page. When the rail is
   folded, the pills are the filter.

## Best when / loses when

- **Best when** the same rows are looked at through several fixed dashboards, and the app wants the whole thing as one
  part it can drop in. Examples: a Clank panel, a robotparts page, a Vibe Tracks track page. One `.base` covers it,
  and a second app writes only its `.base` and, if it needs figures stock data-ui lacks, a `registerView`.
- **Loses when** a host wants its own tabs (its navigation already owns the top row), or wants a filter that only some
  dashboards follow. The element always applies one rail to all pages. Per-page rails would be a second, separate
  feature (`pages[i].facets`).
- **Loses when** layouts must be edited live. It is read-only today; §41's dashboard editor would have to learn pages.
- The dashboards are separate `<data-dashboard>`s. A selection made inside one page (a §17 `select:`) does not carry
  to the next page. Only the rail is shared.

## Worth keeping in a splice

1. **The element frame.** `workbench/data-workbench.js` + `.css` (630 + 103 lines): corner count, tab strip with
   measured overflow into "N more", rail open / narrow / folded / overlay, pill line, gear generated from `settings:`,
   drill actions from `drill:`. It knows nothing about robots, and any other proposal's content could sit inside it.
2. **`contain: layout` on the dashboards column.** This one CSS line keeps stock data-ui's fixed-position drill inside
   a host slot. Any proposal that embeds `<data-dashboard>` needs it.
3. **`splitBy:` on a figure view** (`coverage/views.js` `OccupancyView.split`). It draws one row of the same panels
   per dataset, in the dataset's colour, with one colour scale for all rows. It gives "which dataset covers what" at a
   glance, without flipping filters (the "Datasets side by side" tab).

## What is host code, what is stock data-ui, what would be new

**Stock data-ui (vendored 2f08a88, untouched):**
- `<data-dashboard>`: its 12-column grid, panel titles and ⋯ menu, its drill sheet, and the record pane with ‹ n of N ›;
- `<data-facets>`: values with disjunctive counts, search, slider-histogram, Clear;
- the table (badges coloured from `properties.dataset.colors`, bars, sum row);
- `parseBase`, `loadDataset`, `rowModel`, `toRail` / `fromRail`, `registerView`.

**The app's code (what a second app would replace):**
- `coverage/register.js`: registers three views;
- `coverage/views.js`: the `occupancy` figure engine copied from round 2's V2 (plus `compact` and `splitBy`), and
  `coverage-numbers` and `dataset-mix`;
- `tools/build.mjs`: writes `rows.json` and `coverage.base` from `../data/`, and checks that the figures rebuilt from
  the rows match the producer's counts (33 grids and numbers equal the payload).

**New data-ui API this proposes** (the prototype is in `workbench/`):

```yaml
# <data-workbench src="x.base" [no-url] [rail="auto|open|narrow|folded"] [theme]>
title: UR5e trajectory coverage          # the corner's caption (optional)
noun: [trajectory, trajectories]         # "28 of 212 trajectories" (default: row / rows)
data: rows.json                          # §3, as today
facets: [dataset, split, kind, …]        # §7, as today: the ONE rail every page follows
settings:                                # NEW: behind the one gear; Obsidian option types (§1); views read input.settings
  - { key: cmap, type: dropdown, options: {…}, default: viridis }
drill:                                   # NEW: buttons under a row's fields in the record pane, {p} filled from the row
  actions: [{ label: Open in Rerun, post: '/__rerun/open?rrd={rrd}' }]
pages:                                   # NEW: one tab per page, in order; each is a §17 layout over views:
  - { name: Overview, layout: { columns: 12, rowHeight: fit, panels: [{ view: Headline numbers, w: 8, h: 2 }, …] } }
views: [...]                             # §5, as today
```

- **Element:** `<data-workbench>`. Properties: `filters` (get / set), `page` (get / set), `model` / `rows`, `settings`;
  method `setSetting(key, value)`. Events: `data-workbench-change {page, filters, matched, total}` and
  `data-workbench-settings {settings}`. URL: `#page=<slug>` unless `no-url`.
- **What it would do in core:**
  - ship as `dist/workbench.js`, importing `./dashboard.js` the way the dashboard imports `./data-ui.js`; its CSS goes
    into data-ui.css;
  - make `<data-workbench-source>` public as the general "rail without a view" target;
  - make `rowHeight: fit` a §17 value that the dashboard computes itself;
  - have `<data-dashboard>` pass a `drill:` block (or a `peekExtra`) to its drill sheet;
  - add `input.settings` to the view input (§2);
  - have `<data-facets>` show a value's colour when its column has `colors:` (here the element writes those CSS rules
    itself);
  - add the rail's readable params to the URL (§6), which this prototype skips.
- **Two prototype shortcuts would become core changes.**
  - The element wraps each dashboard's `drill()` to attach the actions and to hand the sheet the rail's filter. Stock
    drill clears the filter, so ‹ n of N › stepped through all 212 rows, not the 28 shown.
  - Views find their settings through `closest('data-workbench')`.

**How a second app uses it unchanged.** It writes its own `.base` and drops in the same tag. No new code is needed
unless its figures are missing from stock data-ui.
- **robotparts' datasheet table:** `data: actuators.json`, `facets: [brand, peak_torque, …]` (its current rail),
  `pages:` Catalogue (a `table` panel), Torque vs mass (a `chart` panel), Compare (a `compare` panel over the rail's
  rows), `drill.actions: [{label: Open datasheet, href: '{datasheet_url}'}]`. Every view is stock, so there is no
  register script.
- **Vibe Tracks:** `data: tracks.json`, `facets: [status, owner, area]`, `pages:` Board (kanban), Timeline,
  KPIs (`kpi` / `tracker` cards), Table; `settings:` for its density or theme; `noun: [track, tracks]`. It reuses its
  existing §17 dashboards' `layout:` blocks verbatim as pages.

## Honest gaps

- The tab strip folds into "N more"; it does not scroll. At the 1000 px slot all six tabs fit (756 px needed, 756 px
  available, measured), so overflow shows only below ~860 px. I checked that by resizing the slot to 720 px; no check
  still shows it.
- The colour settings are kept in localStorage per element id. index.html and embed.html share the id `coverage`, so
  embed.png shows magma, the colour map P5 picked earlier in the same browser context. That is the setting persisting
  as designed, not a bug.
- Selections inside a page (a §17 `select:`) stay on that page. A click on a figure cell opens the stock records pane
  listing the trajectories through that cell; it does not filter the rail.
- No dark theme: the element pins `theme="light"` because the maps' "white = empty" needs a white ground.
- `rows.json` is 1.1 MB, because the cell lists from membership.json are inlined so the views stay generic. The grids
  are checked in Node (`tools/build.mjs`); in the page, only the headline numbers are checked against analyze.
- The tool maps overlay two stations' cell frames as numbers, not as one room. The Tool position page says so.
