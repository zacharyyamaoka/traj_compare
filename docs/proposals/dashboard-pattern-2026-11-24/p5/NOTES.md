# P5 · A filter scope; the host composes

**Thesis.** No monolith. data-ui adds one context element, `<data-scope>`, that holds the rows and the one filter. Every
data-ui element inside it shares both: a `<data-facets>` rail, a `<data-tabs>` strip, any number of stock
`<data-dashboard>`s, a stock `<data-views>` table. The host lays those pieces out however its app needs. The same parts
make a full-page TensorBoard layout (`index.html`), a component in another app's 1000 × 680 slot (`embed.html`) and two
small cards on a robotparts datasheet (`card.html`).

Run it: `/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24 --port 8845`,
then open `http://127.0.0.1:8845/p5/index.html`, `/p5/embed.html` or `/p5/card.html`.

Proof: `check.cjs p5` passes 7 of 7 (`shots/p5.check.json`). Stills are in `shots/p5/` (steps 1–5, `embed.png`), with
`session.webm`.

## Decisions that matter

1. **The scope is a data source, not a layout.** `<data-scope>` exposes the surface that `<data-facets>` already reads
   from a `<data-views>`: `data`, `base`, `view`, `filters`, `model`, `dataRevision` and `data-views-change`. The stock
   rail therefore binds to it unchanged; the prototype only gives it `for=<scope id>`. The scope draws nothing. Where
   things sit is host CSS: 29 lines in `css/layout.css` for the TensorBoard layout, and about 15 in `card.html`.
2. **Existing elements opt in by being inside the scope, through surfaces they already have.**
   - A `<data-dashboard tab="Overview">` with no `src` is loaded with `load(doc, {rows})`. `doc` is the scope's
     `dashboards.Overview` layout over the scope's `views:` and `properties:`. Its default dataset's rail is the scope's
     filter, set through `setRail` (§17).
   - A `<data-views tab="Trajectories">` gets `data`, `base` and `filters` (§6).

   No dashboard has a rail of its own. A page loads the first time it is shown and catches up with the filter when it is
   shown again, so a tick only repaints what is on screen.
3. **Size is decided by container queries on the scope, never the viewport.** Below 1100 px of *scope* width,
   `<data-fold>` turns the rail into a "Filters · N" chip, and its panel opens inside the scope, over the pages. The tabs,
   the count and the gear stay. The same markup runs in `index.html` (1440 px, rail open) and in `embed.html` (the
   1000 px slot, folded). Two more things follow from the scope:
   - Every layer a part draws is placed relative to the scope: the fold's panel, the gear's popover, the hover tip, and
     a dashboard drill (whose stock CSS uses `position: fixed`). Nothing lands on `document.body`.
   - Settings are per scope (`settings:` + `<data-settings>`). The two cards in `card.html` keep two filters and two
     colour maps.
4. **Dataset is the colour channel; split is a word.** Each dataset gets one colour, from data-ui's series slots 1, 2, 3
   and 7. The colour is used in:
   - the rail's swatch facet (Dataset first),
   - the table's badges,
   - the stock Vega-Lite tick charts,
   - the "Datasets in this subset" key, which shows per dataset the trajectories kept, the position × speed cells and
     the reachable voxels, greyed when the filter drops that dataset.

   Split has no colour: amber or red would read as a problem.

## Best when / loses when

- **Best when** the same data has to appear in several apps at several sizes. robotparts wants one card, Vibe Tracks a
  pane, traj_compare a full page. Each app composes the parts in a few lines and gets the one-filter behaviour for free.
  It also stays honest: one row model (data-ui's `rowModel`) feeds the count, the rail's counts and every dashboard, so
  the counts cannot disagree.
- **Loses when** an app wants the opinionated whole without writing any layout. A host writes its grid (about 30 lines
  of CSS), and a bad grid is the host's bug, not data-ui's. A monolith `<data-explorer>` (another proposal) ships that
  layout for you. A scope is also one filter only: per-dashboard rails or cross-filter selections between dashboards
  stay inside each `<data-dashboard>` (§17). The scope does not merge them.

## Worth keeping in a splice

1. **`<data-scope>` as the target `<data-facets>` already understands** (`js/scope.js`, `DataScope`). It is the smallest
   addition that turns "one rail, many dashboards" into a reusable part, and the other four proposals' containers could
   sit on top of it.
2. **`<data-fold>` plus container queries.** The rail becomes a chip, and its panel opens inside the component's box.
   This is the piece that makes anything "drop into anything", whoever owns the layout.
3. **The "Datasets in this subset" key** (`coverage-datasets` view), which compares across datasets at a glance:
   coloured rows with kept / size and what each covers.

## What is host code, stock data-ui, and new data-ui API

**Host code (this app):**
- `js/app.js` (67 lines): registers three views, builds the rows and the document, hands both to every scope.
- `css/layout.css` (29 lines): the grid.
- The figures: `js/coverage/*`, copied from round 2's V2 (the `occupancy` view, the oracle and the drill) plus two small
  views, `coverage-numbers` and `coverage-datasets`.

**Stock data-ui, untouched** (vendored main 2f08a88):
- `<data-facets>`: swatch, values, search, slider-histogram, range, Clear; its own `matched` count.
- `<data-dashboard>` and its panels: `load()`, `setRail()`, panel titles, the ⋯ menu.
- `<data-views>` table: badges, bars, sort, the record peek with ‹ n of N › and `peekExtra` (§37).
- `rowModel`, `<data-kpi>`, the Vega-Lite `chart` view, `makeResizable` on the rail (§11; drags 200–440 px, remembered).

**New data-ui API (prototyped in `js/scope.js` and `css/parts.css`):**

| Part | Attributes · properties | Events | Notes |
|---|---|---|---|
| `<data-scope>` | `data`, `base`, `filters` (the one filter), `settings` / `setSettings()`, `show(tab)`, `tab`, `pages`, `rows`, `picks()`, `active`; read-only `model {rows, matched, total}` | `data-scope-change {filters, matched, total}`, `data-scope-tab {tab}`, `data-scope-settings {settings}`; also `data-views-change` / `data-views-render` for the rail | `container: data-scope / inline-size`; `position: relative` is the containing block for every layer its parts draw |
| `<data-tabs>` | (none; lists the scope's pages) | (uses the scope's) | ARIA tablist, roving tabindex, ← → Home End |
| `<data-count>` | `noun`, `plural` | (none) | "28 of 212 trajectories"; its title lists the picks |
| `<data-fold>` | `label`, `fold="auto \| always \| never"`, `open` | (none) | auto folds under 1100 px of scope width; chip shows "· N" active groups |
| `<data-settings>` | (none; draws `settings:`) | (uses the scope's) | one gear; the popover stays inside the scope |
| `<data-facets layout="row">` | new attribute on a stock element | (none) | the same rail as one line of chips (card 1) |

New `.base` keys:
- `dashboards: {<tab name>: {layout: …}}`: named §17 layouts over the file's own `views:`.
- `settings: [{key, as: select | toggle, label, options, labels, default}]`: the gear's controls; a view reads them as
  its scope's `settings`. In core this would arrive as `input.settings`.

What core would change, small and additive:
- `<data-facets>` attaches to `this.closest('data-scope, data-views')` when it has no `for=`. Today the prototype sets
  `for`.
- A `<data-dashboard>` or `<data-views>` inside a scope with no `src` / `data` of its own takes the scope's (today the
  scope pushes them).
- `dashboard.css`:
  - `data-views.dd-drill` becomes `position: absolute` inside a scope, instead of `fixed` over the viewport;
  - the 900 px one-column fold becomes a container query;
  - an empty `.dd-bar` takes no room;
  - `arrange: false` is already a layout key.
- The swatch facet gets a one-line list style for narrow rails.
- `input.settings` is added to §2's row model.

## How a second app reuses it unchanged

robotparts' datasheet page (`card.html` is that case) or Vibe Tracks' track pane:
- puts a `<data-scope>` where it wants the component,
- inside it places the parts it wants (a chip row, a fold, tabs, one or more `<data-dashboard tab>`),
- sets `scope.base` to its own `.base` (its `facets:`, `views:`, `dashboards:`) and `scope.data` to its rows.

No P5 file changes. For example, a robotparts datasheet scope over its actuators would have:
- `facets: [brand, peak_torque]`;
- a "Torque" dashboard (a stock chart);
- a "Thermal" dashboard (a stock chart);
- a table.

`card.html` shows two such compositions on one page:
- card 1: a chip row and one dashboard, no tabs;
- card 2: a folded chip, tabs over two dashboards, and the count.

The two cards have independent filters and colour maps.

## Gaps

- The scope writes no URL yet. `<data-views>` keeps `?dataset=…&split=…` (§6, `railParams`); the scope should do the
  same, with `no-url` to opt out. The tab is kept in sessionStorage only.
- The prototype reaches one stock seam from outside: it sets `for=` on the rail. Its CSS overrides three stock rules
  (drill position, grid fold, empty bar) under `data-scope`. In core these are the four small changes above.
- The headline numbers that need every sample (joint range p0.1–p99.9, peak speed and acceleration as % of the limit,
  tool speed p99) stay whole-set only. The page says "All 212 only" (round 2's limit; membership holds cells, not
  samples).
- A cell click on a dashboard map opens the dashboard's own drill: "115 trajectories through q −20 … 0°", with the
  records behind it. Checked by hand in the 1000 × 680 slot: the drill and the hover tip stay inside it. That records
  table shows every column (stock §17 drill); a `record:` layout for it is not written.
- The table sorts through data-ui's column menu (click a header, then Sort) or shift-click. Round 2 V2's header-click
  sort hack was left out.
