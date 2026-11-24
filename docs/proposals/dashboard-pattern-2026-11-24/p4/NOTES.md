# P4 · Run selector, TensorBoard / W&B style

**Thesis.** The rail *is* the rows. Datasets are the run list's groups. Each group has a checkbox, its colour swatch
and a count, and unfolds to show its trajectories, each with a checkbox. A regex box filters the names, and Split and
Kind are toggles that apply across every dataset ticked. The main pane is data-ui's own tab row of dashboards. Every
figure is coloured by **dataset**, the way TensorBoard colours runs: one row of maps per dataset, one bar per dataset,
one row of the headline-numbers table per dataset. So you compare datasets at a glance and narrow to particular
trajectories in the same rail.

Run it: `/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24 --port 8844`,
then open `http://127.0.0.1:8844/p4/index.html` (full page) or `/p4/embed.html` (in a host's 1000 × 680 slot).

## Decisions that matter

1. **One filter, written by the run list and owned by data-ui.** `<p4-runs for="p4-cov">` reads the linked
   `<data-views>`' rows and the `.base`'s `runs:` keys. It writes one all-views filter (`el.filters`) in Bases clauses:
   `dataset == …`, `split == …`, and an id list (data-ui's own `inClause('id', …)` idiom) for the regex and for
   trajectory picks. Every dashboard is a view of that one `<data-views>`, so each one recounts from `input.rows`. The
   rail's own count is checked against `views.model` on every render, and the page logs a console error if they ever
   differ.
2. **Semantics follow facets, not TensorBoard.** Nothing ticked means everything is shown, and a tick narrows (data-ui
   facets and gate P1 both work this way). A dataset checkbox has three states, like a file tree:
   - ☐: not picked.
   - ✓: the whole dataset.
   - −: only the trajectories you ticked inside it. Ticking a trajectory also ticks its dataset, so "look at this one"
     shows only that one.

   **Deviation from the brief:** TensorBoard's *Toggle all* means nothing when an empty selection already shows
   everything. Its job ("back to everything") is **Clear**, and **Unfold all** opens every group.
3. **Dataset first, toggles pinned under it.** The brief put Split / Kind at the top. Zach's spec ("dataset … above
   split, it can be the first one") and P1 win. So the dataset tree is the first group. Split / Kind sit in a footer
   that never scrolls away, labelled "Applies to every dataset ticked". The regex box sits above the tree as the list's
   own search, as in TensorBoard.
4. **The dashboards are data-ui's tabs; the sections are mine.** The tab row is `<data-views views="tabs">`, with each
   dashboard as one view entry. Its settings are:
   - `filters=""`: no pill row. The rail already shows the filter beside every tab, and data-ui's pills would print it
     as raw clauses plus a 200-id list.
   - `status: false` on the figure views (§18). Each dashboard prints its own subset line instead: "28 of 212 ·
     re-aggregated · ■ UR5e alone 12 ■ Conveyor PnP 16 · and holdout".

   Each figure dashboard is a `sections` view. Its `figures:` are collapsible sections, like TensorBoard tag groups.
   The maps' sections have a local **Per dataset / Together** switch. The joint picker exists only on One joint. The one
   gear holds the colour map, Reverse and scale for every figure.

## Measured: full page vs the host's slot

| | index.html (1440 × 900) | embed.html (#host-slot 1000 × 680) |
|---|---|---|
| component | 1440 × 863 | 1000 × 680, nothing outside it (check P4, also with the gear open) |
| run list | 276 px | **222 px** (container rule `< 1200 px` → `data-size="compact"`) |
| main pane | 1164 px | 778 px; no sideways scroll on any tab (scrollWidth = clientWidth = 776) |
| tabs | 5 of 5 on the row | 5 of 5 on the row, gear beside them |
| one dense map (Overview) | 148 × 94 | 88 × 57 |
| runs table | 10 numbers | 6 numbers + "+ 4 more numbers" |
| Overview sections open | 3 of 3 | **2 of 3**: the third starts folded, so its header sits 35 px under the slot's fold |
| drill (record pane) | docks beside the table | data-ui's overlay, inside the slot (measured) |

## Best when / loses when

- **Best when** the question compares datasets ("which dataset covers what?"). For example: the conveyor cells' wrist_2
  is a single dot, and the workspace sets fill the plane. Each dataset keeps one colour on every surface: the rail
  swatch, the map row band, the bar, the table badge. You can also go from all 212 to two named trajectories inside one
  dataset in one step, without leaving the dashboard.
- **Loses when** you have many datasets. One row per dataset grows the page linearly. Past 5–6 datasets you want
  *Together* or a pinned comparison set, and data-ui has only eight series colours. It also loses inside one big
  dataset: a flat 64-row checkbox list is a poor way to find "the trajectories that reach far left". V5's click-a-cell /
  sort-by-new-cells is better there, and the regex only partly covers it.

## Worth keeping in a splice

1. **The run list** (`js/runs.js`). It works with any rows: dataset groups with tri-state boxes, swatches from data-ui's
   series tokens, a regex, disjunctive counts on the toggles, and an always-visible count. It is the dataset-first rail
   that Zach's spec describes.
2. **`colorBy:` honoured by every figure** (`groupsOf()` in `js/sections.js`). Its parts:
   - per-dataset rows of small-multiple maps under one colour scale
   - the **runs table** of headline numbers (a row per dataset, plus "All shown", in-cell bars in the dataset colour)
   - grouped bars

   With all 212 shown, the "All" row equals analyze's own numbers (an oracle over 22 grids, the voxels and 10 numbers,
   checked at load and in `tools/emit.mjs`).
3. **Sections that fold by slot size.** A dashboard is a list of collapsible figures. In a small slot only the first
   two open. The rest show as one-line headers you unfold (in the 680 px slot, the Overview's third header is one short
   scroll down).

## Host code vs stock data-ui vs NEW data-ui API

**Stock data-ui, untouched:**
- `<data-views>`: the tab row (`toolbar="bar" views="tabs" promote=""`), the table with dataset / split badges and
  sorting, the record pane with ‹ n of N ›, `peekExtra` (Open in Rerun + what it adds, copied from V2), the "records
  behind this cell" pane, `no-url` (an embedded component never writes the host's URL), `status: false`
  (§18), `tokens()`, `registerView`, `stringifyBase`.
- Data-ui's checker passes `coverage.base` (emitted by `tools/emit.mjs`) with **0 errors**. Its 14 warnings are exactly
  the keys proposed below.

**Host code (≈ 1 700 lines of JS and 230 of CSS; ≈ 750 of the JS copied or adapted from V2):**
- Copied from V2: `rows.js`, `aggregate.js`, `coverage_color.js`, `settings.js`, `drill.js`, the occupancy drawing in
  `sections.js`, and the panel geometry in `base.js`.
- New: `runs.js` (276 lines), the sections / `colorBy` frame in `sections.js` (≈ 300), and `app.js` (mount + gear,
  156).
- Glue V2 also needed: a header click sorts instead of opening the column menu, and the gear is placed on the bar's
  right with `.dv-bar { padding-right }`.

**NEW data-ui API this pattern needs (so a second app writes only a `.base`):**

```yaml
runs:                                  # <data-runs for="views-id">: the rail IS the rows
  group: dataset                       # first filter group: one tri-state checkbox + swatch per value
  title: task                          # the row label under a group
  toggles: [{property: split}, {property: kind}]   # quick toggles that apply across every group
  regex: [dataset, task]               # the regex box matches these, joined by "/"
properties:
  dataset: {colors: {"UR5e alone · Workspace": 1, …}}   # stock today; the run list, badges and figures share it
views:
  - type: sections                     # a dashboard of collapsible figures (TensorBoard tag groups)
    colorBy: dataset                   # EVERY view honours it: maps rows, bars, KPI rows, chart colour
    pick: {label: Joint, options: […]} # a view-local picker (not a view key the bar marks dirty)
    figures: [{key, title, note, kind: maps | bars | numbers, …}]
```

1. **`<data-runs>`**, a sibling of `<data-facets>` that reads and writes the same all-views filter, with `runs:` as
   above. It reads the filter back (`fromRail`) so the bar's Filter menu and the pills stay two-way. This prototype is
   one-way: it hides data-ui's pills (`filters=""`), and with `promote=""` the bar has no Filter button. It needs a
   label for each clause, so the pills could say "Datasets: Conveyor PnP (2 picked)" instead of an id list.
2. **Grammar:** Bases' regex `/…/.matches(name)`. Today a regex has to travel as `inClause('id', …)`.
3. **`colorBy:` as a view key that every registered view honours** through `input.colorBy → groups` with the slot
   colours. The stock `chart` view would read it as its colour encoding.
4. **The `sections` view, with `figures:`.** The key cannot be `sections:`: data-ui's cards already own that key as a
   boolean (§20), and the checker caught the clash.
5. **Component-wide settings** (`configure({settings})` → `input.settings`, and a gear slot on the bar:
   `bar-end` for host buttons). Without these the gear is laid over the bar.
6. **`header-click="sort|menu"`** on the table (also V2's gap). Tab icons should also follow a registered view's `icon`:
   all five tabs show the table icon today.

## A second app, unchanged

- **robotparts' datasheets:** `runs: {group: brand, title: model, toggles: [{property: kind}, {property: in_stock}]}`,
  `colorBy: brand`. The runs table becomes "brand × peak torque, mass, price", and the bars become "share of models
  under 1 kg per brand". It needs no host code beyond its rows.
- **Vibe Tracks:** `group: track`, `title: run`, toggles `status` / `agent`, and `colorBy: track`, over its runs table.
  This is the TensorBoard case itself: runs grouped by experiment, coloured by experiment.

Only figure kinds that know a domain (the occupancy `maps`) stay with the app, as registered views. The rail, the tabs,
the folding sections and the colouring are the pattern.

## Simulated or missing

- The rail is one-way (see API 1). Editing the filter from data-ui's Display › Filter does not move the checkboxes.
- The tool maps overlay two deployments' own cell frames as numbers, not as one room (extract.py's caveat). Grey
  means "neither deployment can reach it".
- Maps count trajectories per cell, not samples (V2's measure). The direction map's oracle checks only the visited set.
