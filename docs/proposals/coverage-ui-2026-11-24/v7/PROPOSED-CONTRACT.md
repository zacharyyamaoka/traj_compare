# Proposed data-ui amendment: coverage views, dashboard settings, dashboard pages (additive)

> **V7 (Splice) copy.** This is V3's amendment, unchanged in §52.1–52.7, plus two sections V7's prototype runs:
> §52.8 (a cell query: "click a cell → who made it") and §52.9 (the KPI sheet layout). V7's host code is `v7/app.js`;
> its views are `v7/views/` (V3's four types, extended, plus `coverage-sheet`).

**Numbering.** The brief asked for "§51". On 2026-11-24 data-ui's `lane/trail-rest` (commit `3e341b7c`) already holds §51
(`rest`, the faint path under the trail). So this text is written as **§52**. Whichever lands second takes the next free
number, as data-ui's amendments have always done.

The text below is meant to land as-is in `/home/bam/data-ui/docs/CONTRACT.md`. V3 of the coverage-UI round
(`/home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/v3/`) is the running prototype. Its view modules in
`v3/views/` are the bundle's first draft. Its host code (`v3/app.js`, `v3/settings.js`) prototypes what the core would
own. Each item below names the prototype file that runs it today.

---

## 52. Amendment 2026-11-24 (coverage views, dashboard settings, dashboard pages; additive)

WHY. Zach, 2026-11-24, on traj_compare's coverage page:

- "migrating some of these visualizations to be stock visualizations you support with data-ui"
- "In some sense this is really just a dashboard on data right…?"
- "the joint selector should just apply on the single joint view and the colors … perhaps those are in a settings
  gear in the top right corner, things that apply to the entire thing that you set once"
- "it should be one of our like generic tables from data-ui"

The figures that answer "how much of a space do these rows fill" are binned grids, histograms against limits, pixel
footprints and direction disks. Today they are hand-drawn in one app. Here they become four view types any dataset page
can use. Dashboards also gain the two shell features that page needed: reader settings set once, and pages as tabs.

Nothing in this amendment removes or renames a key, host call, input field, token or event. A page that uses none of it
draws as before.

### 52.1 The coverage bundle: four view types, one block

There is one view folder, `packages/views/coverage/`, with one lazy bundle `dist/views/coverage.js` (manifest `status:
built`, `npm: []`). It registers four types, the way scene3d's bundle registers three:

| `type` | Draws | Reads (one row =) |
|---|---|---|
| `coverage-plane` | A binned 2-D grid as a heat image: the limit box framed, a colorbar with the scale's real numbers, a lead line (visited %, cells with enough, evenness), a legend, a hover readout of the cell. Several rows draw as small multiples on **one** colour scale. | a **grid row** (§52.2) |
| `coverage-hist` | Binned 1-D histograms against their limits. `layout: multiples` gives one card per `card` value with one strip per row: grey beyond-limit bands, solid limit, dashed planner limit, p0.1/p99.9 ticks, bars stacked by group with an interactive legend (§31). `layout: ridgeline` gives one line per card value and one column per signal, each axis put on its own limit (−100 % … +100 %). | a **hist row** |
| `coverage-projection` | A path's footprint seen from the faces (xy, xz, yz), side by side at **one** metric scale. Colour is samples, distinct paths (Strava's rule) or max speed. Reachable-but-unvisited pixels are the surface colour; unreachable pixels are grey. Axes in mm. | a **projection row** |
| `coverage-polar` | A direction grid on a disk: centre = along the reference, radius = angle away (tilt), angle = azimuth. Each cell is its annular sector. The 90° ring is dashed. | one grid row whose x is an azimuth and whose y is a polar angle |

Each view module follows §1 exactly:

- It exports `options()`, `default class { constructor(host, el); update(input); selected(); destroy() }` and `css`.
- Classes are `dv-coverage-*`. A view writes only inside `el`, including its hover readout.
- Drawing is canvas 2D with one `ImageData` per grid. There is no chart engine.

The shared helpers (axes, colorbar, legend, readout, `room()`) are the bundle's own `src/kit.js`.

**One block for all four**, `coverage:`. It is shared the way §32's stage keys are shared by scene3d, trajectory3d and
voxels. A key a type does not use is ignored, never an error.

| Key | Types | Values (default first) | Means |
|---|---|---|---|
| `value` | plane, projection | `samples` \| `paths` \| `max_other` (plane) \| `max_speed` (projection) | The list column the colour reads. The figure's own "colour =" switch writes it with `host.setView`, so it rides in Save view. |
| `switch` | plane, projection | `true` \| `false` | Draw that switch. |
| `title` | plane | a property | What names each small multiple. Default: the slab band, else the joint, else `x × y`. |
| `columns` | plane | 1–8 | Small multiples per line. Default: as many as fit at 150 px. |
| `share` | plane | `true` \| `false` | One colour scale over every panel. |
| `layout` | hist | `multiples` \| `ridgeline` | See the table above. |
| `card` | hist | a property, default `joint` | What makes a card, or a ridgeline row. |
| `columns` | hist (ridgeline) | a list of signals, default `[q, qd, qdd]` | The ridgeline's columns, left to right. |
| `columnsPerLine` | hist (multiples) | number | Cards per line. Default: as many as fit at 380 px. |
| `pick` | hist (ridgeline) | a property | A row click asks the dashboard to open that value (§52.5's `openPage`). |
| `reach` | polar | degrees, default the grid's top (180) | The outer ring. |
| `overlay` | plane, projection | `this.<property>` (bound to a peeked row, §52.6) or a literal | One path drawn over the grid in the accent colour, with a dot at its start. A plane takes `{<joint>: [[x…], [y…]]}` (SI); a projection takes `[[x, y, z], …]` (m). |
| `muted` | plane, projection | `false` \| `true` | Draw the grid in greys, so an overlay reads first. Used by the drill. |

**Sizing.** Inside a sized dashboard panel a view fills the panel, from its own top to the panel's padded bottom
(`room(el)` in kit.js). A reader who drags a panel taller under Arrange gets a bigger figure. Outside a panel the view
uses its own height, else a fixed fallback.

### 52.2 The rows they read: one row per grid, never one per cell

WHY one row per grid. The row model is for things a reader filters, sorts, groups and opens: a joint, a plane, a
signal, a face. Nobody filters one bin of a 36 × 24 grid. Pushing 13,824 plane cells through `rowModel` on every pick
buys nothing and costs a sort per change.

So a grid is one row. Its scalars (joint, plane, visited %, the limit box) are ordinary columns that a table, a facet
or a KPI can read. Its counts ride along as **list cells**, which §2 already allows. The one exception is `voxels`
(§32), which already reads pre-gridded rows one per cell, so voxel rows stay cells.

Values are SI. Display is `value × <axis>_scale` in `<axis>_unit`, so degrees exist only at the display edge (Zach's
rule). Flat arrays are row-major: cell `(i, j)` is at `i * ny + j`, with i along x and j = 0 at the bottom.

**The grid row** (coverage-plane, coverage-polar):

| Column | Type | Required | Means |
|---|---|---|---|
| `x`, `y` | text | yes | Axis names (`q`, `qd`, `azimuth`, `tilt`). |
| `x_label`, `y_label` | text | | Axis titles. |
| `x_lo`, `x_hi`, `nx`, `y_lo`, `y_hi`, `ny` | number | yes | Linear edges. The grid spans exactly `[lo, hi]` in `n` equal cells. |
| `x_scale`, `y_scale`, `x_unit`, `y_unit` | number, text | | Display conversion (default 1, no unit). |
| `samples` | list of nx·ny integers | yes | Samples per cell. |
| `paths` | list of nx·ny integers | | Distinct paths per cell. |
| `max_other` | list of nx·ny numbers or null | | A third quantity per cell (null = unvisited), named by `other_label`, `other_scale` and `other_unit`. |
| `visited_pct`, `sufficient_pct`, `evenness_pct`, `outside`, `cells`, `enough` | number | | The producer's numbers for the lead line. Drawn as given, never recomputed (§2: a headline number is the producer's). |
| `box` | `limit` \| `none` | | `limit`: the grid IS the limit span, so its frame is drawn in the limit colour. |
| `slab`, `slab_lo`, `slab_hi`, `by`, `by_scale`, `by_unit` | | | A slab of a 3-D grid: names the band. |
| `reference` | list of 3 numbers | | coverage-polar: what the centre means. |

**The hist row** (coverage-hist):

| Column | Type | Required | Means |
|---|---|---|---|
| `lo`, `hi`, `bins` | number | yes | Linear edges. |
| `counts` | list of `bins` integers | yes | Samples per bin. |
| `groups` + `group_counts` | list of text + list of lists | | Per-group counts (each the same length as `counts`). Stacked bars and a legend. |
| `low`, `high`, `limit_source`, `limit_kind` | | | The limit. It is drawn only when `limit_source` is `limit`; otherwise the card says "no limit stated". |
| `planner_low`, `planner_high` | number | | The planner's limit, dashed. |
| `p001`, `p999`, `span_pct`, `peak_pct`, `outside`, `beyond_edges` | number | | The producer's numbers. |
| `signal`, `signal_word`, `label`, `family`, `scale`, `unit` | | | Labels and display. |

**The projection row** (coverage-projection): `view` (xy | xz | yz), `title`, `u`, `v` (axis names), `frame`,
`pixel_m`, `origin_u`, `origin_v`, `nu`, `nv`, and the list cells `samples`, `paths`, `max_speed` (null = unvisited)
and `reachable` (0 \| 1, or null = no mask), plus `pixels` (the producer's count).

A producer writes these rows with a few lines of reshaping and no analysis; `v3/rows.py` is the worked example. Both
checkers check them (§52.7).

### 52.3 Colour: the five maps and the scales move into the core

`packages/core/src/colormap.js` is exported from `@data-ui/core` as `ramp(name, reverse)`, `scale(counts, mode, {enough,
clip, max})`, `MAPS`, `NAMES` and `SCALES`. It holds BAM Reach's and traj_compare's five perceptually uniform maps
(viridis, magma, plasma, inferno, cividis, 17 stops each) and five scales:

- `linear`: clipped at p98 of the visited cells, the default. Zach: "Linear to me is BY far the most informative".
- `log`
- `equalized`: colour is the rank among visited cells.
- `visited`
- `enough`

Every coverage view, and any future heatmap, reads these; none carries its own copy. The source of truth is
`traj_compare/src/traj_compare/assets/coverage_color.js`, copied, with a golden test (§52.7).

The rules every coverage view keeps:

- **Empty** (count 0) is the surface colour, `--data-bg` (white in light). It is never a colormap colour. Zach: "so its
  clear that white means empty".
- **Beyond the limit / not reachable** is a new host token, **`--data-outside`** (default `rgb(221 220 214)` light,
  `rgb(58 58 62)` dark).
- **A limit** is a new host token, **`--data-limit`** (default traj_compare's `#b4442f`, dark `#e0705c`). It is red
  because a limit is a boundary, never because of a status.
- **Group colours** come from `style.families` slots (§32), so "dev" is one blue in a bar, a badge and a legend.
- `input.tokens` gains `outside` and `limit`.

### 52.4 Reader settings: `settings:`, `<data-settings>`, `input.settings`

**The key.** `settings:` at the top level of a `.base` lists the style keys a reader may change, each with an option
type. The types are §1's Obsidian ones plus `colormap`:

```yaml
style: { colormap: viridis, reverse: false, scale: linear }     # the file's defaults
settings:
  colormap: { type: colormap, displayName: Colour map, options: [viridis, magma, plasma, inferno, cividis] }
  reverse:  { type: toggle, displayName: Reverse (high = dark) }
  scale:    { type: dropdown, displayName: Scale, options: { linear: linear (clipped at p98), log: log, equalized: histogram-equalized, visited: visited / not, enough: ≥ enough samples / not } }
```

**Resolution, per key, first wins:**

1. the reader's pick, kept in localStorage under `data-ui/settings/<dashboard key>` (every read and write in try/catch);
2. the file's `style.<key>`;
3. the option's `default`;
4. its first option.

**Delivery.** Every view's `update(input)` receives **`input.settings`**, a new frozen field in §2 holding the resolved
`{key: value}`. The same values are also merged into `input.view.style`, so a view that reads style keeps working (the
prototype runs on that path today; `resolveStyle` already keeps keys it does not know). A change calls `update(input)` on
every mounted view with the new settings, in place, with no remount. Views on hidden pages update when they are next
shown.

**The element.** `<data-settings for="<id …>" key="<storage key>">` is a gear button, `aria-haspopup="dialog"`,
`[data-settings-gear]`. Its popover, `[data-settings-panel]`, `role=dialog`, holds:

- a row per setting: a `colormap` is a radio group of named gradients (drawn with the current Reverse); a toggle is a
  checkbox; a dropdown is a select;
- the chosen scale's one-sentence note;
- "Reset to the file's", which appears only when the reader has picks.

Escape, ✕ or a click outside closes it. Event: `data-settings-change {settings, key}`. Property: `el.value`. Method:
`reset()`.

`<data-dashboard>` draws one, right-most in its bar (where Display sits in a view's bar), whenever its file has
`settings:`. A plain `<data-views>` page places one itself. Zach's words fix the place: "a settings gear in the top
right corner, things that apply to the entire thing that you set once".

**Not in the URL.** Settings are the reader's own reading glasses, so a shared link shows the data in the receiver's
colours. A view's own switches (`coverage.value`) are view state and do ride in the URL and in Save view.

**Stock views that read settings:**

- `coverage-*`: all keys.
- `voxels` (§32), when `voxels.ramp: settings`, takes its ramp from `settings.colormap` and `reverse`. The default stays
  §32's family hue, so no page changes.

### 52.5 Pages: `pages:` on a dashboard

A dashboard file may hold **pages**, which the dashboard draws as tabs. The prior art is Metabase's dashboard tabs,
Grafana's tabs layout and Power BI's report pages.

```yaml
datasets: { planes: rows/planes.json, trajectories: rows/trajectories.json }
layout: { columns: 12, rowHeight: 40 }            # shared by every page
pages:
  - name: One joint
    datasets:                                      # this page's own rail and default filter, over the shared dataset
      planes: { facets: [{ property: joint, as: select, label: Joint }], filters: 'joint == "shoulder_pan_joint"' }
    panels:
      - { view: "Which positions and speeds does the joint visit?", w: 6, h: 10 }
  - name: Trajectories
    views: [By split, What each one adds, Speed span]   # a full-page <data-views>: its presets are its tabs (§47)
```

- **A page** is either `panels:` (a dashboard page laid out like `layout.panels`) or `views:` (one full-page
  `<data-views>` over those view names, with `toolbar: bar` and `views: tabs`).
- `page.datasets.<name>` merges `facets` and `filters` over the top-level dataset for that page only. **Each page has its
  own rail state.** This is what puts the joint picker on One joint and nowhere else.
- **The tabs.** They are drawn in the dashboard's bar, one row (§47: the pages spread as tabs, the bar's own controls as
  icons): Arrange, the settings gear, Open in Rerun. Each tab is `[data-dd-page=<slug>]`, `role=tab`.
- **Lazy.** A page's panels mount the first time it is shown. A hidden page draws nothing and loads no view bundle.
- **State.** The URL holds `#page=<slug>`, scoped as §25 scopes the clock (`#page.<key>=` with several dashboards on a
  page). Each page's rails, selections and panel tabs keep the existing `#s.` / `#p.` / rail params, prefixed with the
  page slug. Back and Forward step pages.
- **`openPage: {page, property}`** on a view: a click on a row that carries `property` shows that page with its rail's
  one-choice facet moved to the clicked value (a §33 picker across pages). It is one history entry. The prototype is
  coverage-hist's `pick: joint` on the Overview ridgeline, dispatched as `data-coverage-pick`.
- **Readers.** `readDashboard(base)` returns `pages: [{name, slug, panels | views, datasets}]`; a file without `pages:`
  is one unnamed page, exactly today's dashboard. A page panel naming no view is a `problems` entry, with its line.

### 52.6 The table and the drill (keys the coverage page's Trajectories tab needed)

- **`columnClick: sort | menu`** on a `table` view, default `menu` (today's Notion header).
  - `sort` makes a plain header click cycle ASC → DESC → off through `host.setView`. This is the same rule the table
    already runs for a shift-click.
  - The header's ⋯ (`[data-col-menu]`) and Enter still open Notion's column menu.
  - WHY: on a page whose act is sorting ("sorting the table" was one of Zach's likes), the default puts the act one menu
    away. Prototype: a capture-phase click listener in `v3/app.js`.
- **`rerun: {rrd: <property>, sdk, endpoint}`** on a view. This extends §25's dashboard-level `rerun:` to one file per
  row.
  - The record's peek shows **Open in Rerun** in its actions row (beside ‹ n of N ›, where §46's `openElsewhere` link
    sits).
  - A click POSTs `<endpoint>?rrd=<the row's value>`. The default endpoint is `/__rerun/open`, traj_compare's
    `serve.py`, which answers `{ok, command}`.
  - The result is said under the actions row. On failure (no server, file://) the peek shows the command
    `uvx --from rerun-sdk==<sdk> rerun <absolute path>` with a Copy button.
  - Prototype: `el.openElsewhere` returning the `.rrd`'s URL, its click taken over and turned into the POST.
- **A record section's view may bind any key, not only `filters`, to the peeked row** with `this.<column>`, the
  analyses' `bindThis` (§19, §35). It may also read a second dataset as `layers` (§32) in a plain `<data-views>`.
  - With both, the drill's "its tool path over every trajectory" is a stock record section:
    `{name: Its motion, view: {type: coverage-projection, from: projections, coverage: {muted: true, overlay:
    this.tool_path}}}`. That needs no host code.
  - Prototype: `el.peekExtra` (§37) plus `mountDrill()` in `v3/app.js`, which mounts the same view classes into the
    slot.
- **The table's badge reads `style.families`** when the badged column is the families' property, so one declaration
  colours the badge, the bars and the legends. Prototype: the same slots are written twice, once in
  `properties.split.colors` and once in `style.families.colors`.

### 52.7 Tests and the gallery case a lane needs

**Unit** (`node --test`):

- `tests/unit/colormap.test.mjs`
  - every map's 17 stops equal traj_compare's `coverage_color.js` (golden copy);
  - `scale()` on fixed counts for each of the five modes: t values, ticks, the clip note, empty = −1;
  - Reverse reverses.
- `tests/unit/coverage-rows.test.mjs`
  - a grid row's lists are nx·ny long and a hist row's are `bins` long; a wrong length is a named error;
  - `C`-order indexing round-trips;
  - the producer's `visited_pct` is drawn, never recomputed (mutation: a view that recounts fails on a fixture whose
    stated % differs from its cells).
- `tests/unit/settings.test.mjs`
  - resolution order;
  - a throwing localStorage falls back to the file;
  - Reset;
  - `input.settings` is frozen and equal to the merged style keys.
- `tests/unit/pages.test.mjs`
  - `readDashboard` with `pages:`: page dataset overrides, an unknown view name is a problem, a file without pages is
    one page;
  - `#page=` read and write, scoped.

**Checkers** (`check.js`, `tools/check_views.py`, both from `schemas/view.schema.json`) accept the keys above and
refuse, each with a did-you-mean:

- a `coverage.value` naming a column that is not a list;
- an unknown `layout`;
- a `settings:` entry whose type is unknown, or whose key no view reads (a warning);
- a page with both `panels` and `views`;
- a `columnClick` other than sort or menu;
- a `rerun.rrd` naming no column.

**Gallery case** `gallery/examples/trajectory-coverage/`:

- `views.base` is V3's `coverage.base`, and the data is `rows.py`'s output.
- **Needs Zach's word before it ships:** §8 says gallery data is public-safe only and data-ui.dev is public. The rows are
  simulated UR5e motions, with no customer data and no private figures, but the call is his.

**The case's `checks.py`**, at 1440 × 900 and 390 px, light and dark:

1. No sideways scroll on any page.
2. The headline KPIs are on Overview only.
3. The joint rail shows on One joint only. Picking elbow_joint changes the lead to the payload's elbow numbers.
4. Settings are hidden until the gear opens. Picking magma changes the pixels of every coverage canvas on the open page.
   - Mutation: a view that ignores `input.settings` fails.
5. An empty cell's pixel equals `--data-bg`. The limit frame's pixel equals `--data-limit`.
6. Every drawn mark kind has a legend entry (fill, empty, frame, line, dash, tick, outside, path).
7. The hover readout of a known cell shows its count.
8. A hidden page holds no canvas.
9. `#page=` survives a reload.
10. A ridgeline row click opens One joint with the rail moved.
11. A header click sorts.
12. Open in Rerun POSTs `rrd=` with the row's value (route intercepted), and shows the copyable command when the route
    fails.

Positions are measured with `getBoundingClientRect`, never asserted from DOM presence.

**The views page** lists the four types as built.

**Not in this amendment:**

- a 3-D direction sphere: `voxels` and `scene3d` cover 3-D; a sphere view is its own proposal;
- the parallel-coordinates density;
- per-trajectory spaghetti on the dataset planes.

traj_compare keeps those until a second app asks for them.

### 52.8 A cell query: "click a cell → who made it" (V7)

Prototype: `v7/views/query.js` (the store), `v7/views/kit.js` (`gridKey`, `cellWords`, `askCell`, `hitLayer`, the
fade), `v7/app.js` (the bar, the chips, the answer as a filter).

- **A membership dataset.** A coverage bundle may name `membership:` (a file of `{<record id>: {<grid key>: [cell, …]}}`,
  traj_compare's `data/membership.json`): which cells of which grid each record visits, on the payload's own lattice.
  Grid keys: `plane/<joint>/<q_qd | qd_qdd | q_qdd>`, `xy | xz | yz`, `directions`. A checker rebuilds every grid's
  per-cell record count from it and requires it to equal the payload's `paths` (extract.py does this today).
- **A view asks; the dashboard owns the question.** A coverage view never writes outside its element: a click on a
  cell dispatches `coverage-cell` `{key, cell, label, empty}` (bubbling). The dashboard keeps the chips (its state, in
  the URL as `#q=<key>:<cell>,…`), ANDs them, and hands every view `input.query = {chips, answer, visited(key)}`; today
  the host keeps them in one store every coverage view subscribes to.
- **The answer filters records, never recounts cells.** The answer (the records whose membership holds every chip's
  cell) reaches every table on the record dataset as an all-views clause; the figures keep the payload's counts and
  fade the cells no answer record visits (a stated wash toward the surface, keyed "faded" in each legend while a
  query is set). The only derived numbers are the answer's size ("n of 54", a subset count) and the fade.
- **A host-labelled pill.** An all-views clause the host set carries a label (`filtersLabel`), so the pill reads "Who
  made it: the 8 that visit every asked cell", not the `name == …` or-group; its ✕ clears the question. V7 rewrites
  the pill's text after each render.
- **The click target.** A plot's click layer is one cell wider (right) and taller (top) than the plot, so its centre
  is the middle of one cell (V6's rule): a keyboard Enter and a scripted click at the centre ask about one cell.

### 52.9 `kpi` with `layout: sheet` (V7)

Prototype: `v7/views/coverage-sheet.js` (registered as its own type until this lands).

- `kpi: {layout: sheet, group: <property>}` draws the cards as one sheet of `label ……… value`, one column per group,
  the label as stored (an ellipsis when narrow) and, one hover away, the full label, the record's `key` (its code id)
  and the value's `note`. WHY: 15 headline numbers read as a sheet in ~150 px; as cards they took ~300 px of the
  landing (Zach, Nov 24: the numbers "doesn't make sense to be showing them the entire time").

