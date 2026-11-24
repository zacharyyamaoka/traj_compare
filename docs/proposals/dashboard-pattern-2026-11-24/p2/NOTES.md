# P2 · The rail holds the tabs

**Thesis.** One left column does both jobs, as VS Code's activity bar + side bar or Linear's sidebar do. At its top is
the list of dashboards: vertical tabs, one click each, the open one marked. Under it are the filters: Dataset first,
then Split, Kind, Tags, a trajectory search and the ranges. The main pane is only the open dashboard, under one quiet
line that names it, says "28 of 212 trajectories" and lists the picks. There is no horizontal tab strip anywhere, so
the component is a sidebar plus a canvas and drops into any app. When the component is narrower than 1100 px, the
column folds to a 48 px icon strip: the dashboard icons, a Filters icon with a badge counting the active picks (it opens
the same filters as a panel **inside** the component), and the gear.

Run it (the round's server; Open in Rerun needs it):

```bash
/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24 --port 8842
```

Then open `http://127.0.0.1:8842/p2/index.html` (full page) and `http://127.0.0.1:8842/p2/embed.html` (the host's
1000 × 680 slot).

## Decisions that matter

1. **The dashboards are a stock `<data-rail>`, not a new tab element.** `<data-rail>` (data-ui §27, the app rail) already
   has destinations with icons and labels, the open one (`current`, `aria-current`), ↑/↓/Home/End, a cancelable
   `data-rail-navigate`, a collapsed (icons, 3rem) and a wide (rows, 15rem) style, and a tooltip per icon when
   collapsed. P2 lists the `<data-views>`' views in it (`name` + `icon:`). A rail pick calls `selectView(name)`.
   `data-views-change` moves the rail's mark back. The dashboards are `<data-views toolbar="none">`, so the all-views
   filter that `<data-facets>` edits is the same object on every dashboard. Switching keeps the filter for free: P3's
   counts were 28 on all six dashboards.
2. **The facets sit under the dashboards in the same column, and the component's width decides the layout.** At 1100 px
   or wider the column is the rail's wide list with the facets inline. It is 264 px and its right edge drags
   (`makeResizable`, §11): 264 → 340 px measured. Below 1100 px the column is the rail's collapsed strip, and the facets
   become an absolute panel at `left: 48px` inside the component root. That root is `position: relative` and clips.
   - **Measured in `embed.html`:** strip 48 × 678 px, dashboard 950 × 678 px, filters panel 300 × 678 px inside the
     slot. Ticking Cell · Conveyor Collision there gave 40 of 212 and badge 1.
   - **Why the rail's own mode flips the layout:** a container query cannot set an attribute, so a ResizeObserver flips
     `rail.mode` when the width crosses 1100 px. The layout then follows `rail.mode`. A reader who presses the rail's
     ⇥ (or ⇤ at full width) keeps that choice until the next crossing, which is data-rail's rule that a person's
     choice wins. Inside the dashboard, real container queries re-fit the KPI cards (`@container p2main`).
3. **The filter stays legible from every dashboard without the rail open.** The line over the dashboard carries the
   count (it turns blue when filtered) and the picks as chips ("Dataset Cell · Conveyor PnP, UR5e alone · Workspace ·
   Split holdout"). The chips are read back from the filter by data-ui's own `toRail()`, so they say what the rail
   says. In the strip, the Filters icon's badge counts the picks. Each map still labels its subset ("subset of 28:
   re-aggregated …"), and each KPI card carries data-ui's `~ derived` mark.
4. **One colour key per dataset, everywhere.** The `.base` gives `dataset` the colour slots 1–4 and `split` the slots
   0 (dev) and 7 (holdout), so a dataset badge never reads as a split badge. The same slots colour:
   - the rail's dataset checkboxes (a swatch beside each)
   - the table's badges
   - the Overview's composition chips
   - its new "Which dataset covers what" row: one top view per dataset in that dataset's hue, with "N px · M only it",
     then all of them on one map (one colour = that dataset alone, dark = shared)

   That row answers Zach's level 1 (across datasets) at a glance. His level 2 (within a dataset) is one more tick or
   the Trajectory search.

## Best when / loses when

- **Best when** the component lives inside another app's page, as Clank, robotparts or a Vibe Tracks track page would
  host it. It owns no page chrome, and it is just a column and a canvas. At full width every dashboard name and every
  filter shows at once, with nothing folded. The list also scales: 6 dashboards here, and 15 still fit as rows in a
  column, where they would overflow a tab strip into "N more…".
- **Loses when** the filters are long *and* you switch dashboards often in the narrow strip. Then the dashboards and
  the facets compete for one column, and the facets scroll under the dashboards (Kind's 8 values, Tags, the search,
  4 ranges). In the strip, changing a filter costs one extra click, since the panel opens over the dashboard. The
  dashboard names also become icons with tooltips, which is weaker than V5's labelled list for a first-time reader.
  At 1440 px the column is 264 px of filters that a reader who never filters does not need; ⇤ folds it.

## Worth keeping in a splice

1. **`<data-rail>` as the dashboard list**, bound to a `<data-views>`: icons + names, the open one marked, collapsed ↔
   wide (`component.js`, the "dashboards" block, ~10 lines).
2. **The narrow strip with a Filters badge that opens the facets as an in-component panel** (`p2.css` "narrow
   layout"): it is what makes the 1000 × 680 embed comfortable without a second layout.
3. **The dashboard's header line**: name, "N of M" (blue when filtered), the picks as chips from `toRail()`. Any
   proposal can put it over its dashboard.

## Host code vs stock data-ui vs NEW data-ui API

**Stock, untouched** (vendored main 2f08a88):
- `<data-rail>`: destinations, icons, `current`, `data-rail-navigate`, the collapsed/wide modes and their toggle
- `<data-facets>`: `values` with disjunctive counts, `search`, `slider-histogram`, `range`, per-group Clear
- `<data-views toolbar="none" status="off" frame="flush" open="side">`: `selectView`, the all-views `filters`, the
  `table` view (badges, bars, sort), the record peek with ‹ n of N › and `peekExtra`
- `<data-kpi>` cards with the `derived` basis
- `makeResizable`, plus `toRail` / `railConfig` / `facetSpecs` (read the picks back for the chips)
- `registerView`, `stringifyBase`

**Registered views (the figures, round 2's V2 engine, copied):** `occupancy` and `coverage-overview` (views.js,
aggregate.js, drill.js). P2 changed three things in them: the hover tip lives inside the component root and is clamped
to it (no `document.body` popover); the subset line leaves the count to the header; and the Overview gained the
per-dataset row.

**Host code that each app would otherwise copy** (`js/component.js`, 260 lines, generic: it knows a `.base` and rows,
nothing about robots):
- lists the views in the rail
- syncs the open view and the rail
- the width → `rail.mode` flip
- the facets-as-panel in the strip
- the gear's popover anchored inside the root
- the header line and its chips
- the colour swatches beside a coloured facet's values

`js/app.js` (108 lines) is the coverage app: rows, base, colour settings, drill, header-click sort.

**The data-ui API that would make it stock** (five lines):

```html
<data-rail for="cov" mode="auto" collapse-below="1100"></data-rail>   <!-- its pages = cov's views; <data-facets for="cov"> drawn under them; strip + Filters badge + in-rail panel below 1100 px of its container -->
<data-views id="cov" src="coverage.base" toolbar="none" header="line"></data-views>   <!-- the open dashboard only, under "Name · N of M · picks" -->
```
```yaml
views: [{type: occupancy, name: Tool position, icon: map-pin, group: Tool, rail: true}]   # `icon`, `group`, `rail` per view = per page
settings: {colormap: {options: [viridis, magma, plasma, inferno, cividis], default: viridis}, reverse: false, scale: linear}   # one gear at the rail's foot -> input.settings for every view
```

In data-ui's own terms:
- **`<data-rail for="<views id>">`:** destinations are that element's views (`name`, `icon:`, `group:`, `rail: false`
  to leave one out). `current` follows `data-views-change`, and a pick calls `selectView`.
- **`facets="below"` on the same rail:** the rail draws `<data-facets for>` under its destinations in the wide style,
  and in the collapsed style a Filters destination whose badge is the active pick count. That destination opens the
  facets as a panel inside the rail's container.
- **`mode="auto"` with `collapse-below="<px>"`:** collapsed below that width of its container, wide above, a person's
  toggle winning until the next crossing.
- **`settings:`:** a top-level `.base` key, rendered as a gear at the rail's foot, read by every view as
  `input.settings`. Round 2's V2 gap 3; P2 still keeps its own store, `settings.js`.
- **Smaller gaps:**
  - a `values` facet could draw its property's `colors:` swatch (P2 does it with one generated `:has()` rule per value)
  - `<data-rail>` could set a badge on one destination without a redraw
  - the table's `header-click="sort"` (V2's gap 4, still caught in the capture phase)
  - `<data-facets>`' own "Filter N match" summary hidden, as P2's column header says it

## How a second app uses it unchanged

robotparts' datasheets: a `.base` over the parts rows with `facets: [vendor, family, peak_torque …]` and views
`[Overview (kpi), Torque × speed (chart), Compare (compare), Parts (table)]`, each with an `icon:`. Its page calls:

```js
mountRailDashboards(slot, { id: 'parts', base, data, title: 'Actuators', noun: ['part', 'parts'] })
```

It gets the same column, the same strip below 1100 px, the same header line and the same in-component filters. Vibe
Tracks does the same with a track's runs: facets `[track, status, owner]`, views `[Pace, Runs, Timeline]`. Nothing in
`component.js` names a robot, a joint or a trajectory. Its only inputs are a `.base`, rows, a title, a noun and an
optional settings panel. Once the API above lands, the call becomes the two tags.

## Simulated or missing

- The figures are round 2's V2 maps (trajectories per cell). Samples-per-cell, 3-D views and time series are not here;
  the motion opens in Rerun.
- The colour settings live in P2's own store (localStorage, `dashboard-pattern-p2.settings`), not in data-ui.
- The rail's Ctrl+Alt+R hotkey is off (`hotkey="off"`): an embedded component should not take a page-wide key.
- In the strip, the rail's own ⇥ toggle sits under the dashboard icons; it expands the column inside the component.
- The full-page URL carries the dashboard (`#view=`) and the picks (`?dataset=…&split=holdout`). `embed.html` sets
  `no-url`, so the host owns its URL.
