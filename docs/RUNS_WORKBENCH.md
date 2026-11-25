# The runs workbench: every run of every deployment, then one target, then playback (2026-11-24)

Zach picked V2, "Two viewers, the filter carried", of the round in `docs/proposals/tensorboard-2026-11-24/`. His words
(Daily Note 2026-11-24):

- *"yes v2 is really great please do that one … Ok I really like kinda the layout structure now"*
- Runs are atomic; the rail filters runs across ALL deployments; deployment is a filter, not a split; tabs Overview ·
  Targets · Runs.
- l.3227: *"there are almost like 3 actually. We have like the dataset view, then the target view (at this point its
  still just summary data though), Then we can actually open up the playback viewer. either our custom one or the
  rerun one."*

Acceptance: `tests/test_runs_workbench.py` (Python) and `tests/test_runs_workbench_browser.py` (headless Chrome), both
written red first. The two defaults added on 2026-11-25 (below): `tests/test_runs_workbench_picks.py` and
`tests/test_runs_workbench_picks_browser.py`, against `tests/runs_picks_oracle.py`, also red first.

## The defaults since 2026-11-25: the Overview's tiles and "Does sim match real?"

The AI picks of the two rounds that followed V2, made the defaults of `write_runs_workbench` (every caller gets them;
Zach can still swap, below). Code: `traj_compare/runs_overview.py` (the pages, the pairs) and
`assets/runs_views.js` + `.css` (the host views, registered through data-ui's own `registerView`; promoted from the
round's `kit/` and made generic: every name comes from the writer's config, `<script id="tc-views">` in `index.html`).

**The Overview = O3 "Headline tiles → drill"** (`docs/proposals/v2-overview-2026-11-24/`, `o3/NOTES.md`; gallery
`reports/media/v2-overview-proposals-2026-11-24.html`). Six tiles, each a small view whose Open chip (data-ui §55's
`open:`) goes to its own full page:

| Tile | Says | Opens |
| --- | --- | --- |
| Best config | the config with the lowest League value at the fastest speed left, the gap to the next, the top five | League (the round's League table: answer sentence, KPIs with sparklines, best-in counts, a row's worst targets) |
| Speed growth | how much the best config's error grows from the slowest speed to the fastest | Speed (one line per config, small multiples per model type or deployment, the sweep table) |
| Trade-off frontier | the configs no other beats on both accuracy and the first cost KPI, in the best config's deployment | Trade-off (accuracy against a cost per deployment, the Pareto frontier; the cost switches) |
| Model × dataset coverage | the share of model type × dataset cells with runs (config × dataset without a mapping) | Model × dataset (model type › config × deployment › dataset, columns switchable) |
| Worst target | the best config's worst target, linked to its target view | Worst targets (any config's 25 worst, each → target view) |
| Runs left | runs, targets, configs, datasets, deployments the rail leaves | Targets |

Every number is the round's rule, named on each figure: a target's value for a config = the median over its runs; the
config's = the median over its targets; at the fastest speed the filter leaves; n = targets. A tile whose data is absent
is absent with its page: one speed → no Speed growth and no Speed page; no cost KPI (a KPI other than the League's,
`better="lower"`) → no Trade-off.

**A fourth tab, "Does sim match real?"** = T1 (`docs/proposals/v2-tabs-2026-11-24/`, `t1/NOTES.md`; gallery
`reports/media/v2-tab-proposals-2026-11-24.html`), after Runs. `pairs.json` holds one row per real line and each
prediction of it in the same run folder (every other line of the folder: a simulation, a rehearsal), built in Python from
the runs (`build_pairs`), never by the round's scraping. Linked one-way from the runs by the folder (`run_report`), so a
pair stays while either of its lines passes the rail. The page: the answer ("On the real robot the tool tracking RMS is
×1.21 what its sim run predicted …", a line per deployment), per config, each pair (log-log, the y = x line), the gap
against speed, and the pairs that disagree most; a row's Open target view ticks exactly its two lines (`why=pair`, so the
target view says "not in this pair" of the others) and ‹ returns to the tab with the filter. "Real against" (the stock
page-level select) picks the prediction, default the one with the most pairs.

- **No real run in the data → no tab** (and no `pairs.json`): a page is fixed when the workbench is written, and a tab
  that can never hold a pair is clutter. **A filter that leaves no pair → one calm sentence** ("No real run in this
  filter has a prediction of the same motion beside it …", and where the pairs are): the rail changes in the page,
  the tabs cannot, and a 0 or "—" beside "real ÷ predicted" would read as a result.

**One value both read, `accuracy`** (a column of `runs.json`): the League KPI where the run carries it, else
traj_compare's own tool RMS (`robot_msgs.compare`), flagged `accuracy_from: "traj_compare"` on the row and counted under
every figure that reads it. WHY: the V2 rounds' rule (their `extract.py`: "tcp falls back to rows[].tcp"); on the bench
every real run of one arm carries no tool RMS tag, and without the stand-in it had no pair and no place in the League.
Only into a League KPI in mm (the tool RMS's unit); the League KPI's own column is never touched.

**Proved** on the bench's four deployments (18,507 runs, port 8855, headless Chrome 1440 × 900, 2026-11-25): every tile
number equals the round's `oracle.json` unfiltered and with the UR5e cell ticked; each tile opens its page; the tab
answers 1,752 pairs ×1.21 (real worse in 1,381) unfiltered and 26 pairs ×2.00 (24) with BAM FB ticked, as the tabs
round's oracle; the top pair opens its target view with its two lines ticked and ‹ returns to the tab at 4,972 runs; no
console error, no sideways scroll. Stills: `reports/media/v2-production-picks-2026-11-25/`.

### How to swap

```python
write_runs_workbench(sites, out, overview="league")   # the round's O1 alone (also "matrix" O2, "speed" O4, "tradeoff" O5)
write_runs_workbench(sites, out, overview="v2")       # V2's own Overview: the Vega League, League by model type, Speed sweeps
write_runs_workbench(sites, out, overview={"name": "Overview", "layout": {...}}, views=[...])  # your own .base page
write_runs_workbench(sites, out, sim_vs_real=False)   # no "Does sim match real?" tab
write_runs_workbench(sites, out, accuracy_fallback=False)  # the League KPI only, no traj_compare stand-in
```

`"tiles"` (or `None`) is the default. With `"league"` … `"tradeoff"` the Overview is that one host view, full width,
and no extra pages; with `"v2"` or a page of your own, V2's Vega views stay beside it (a caller's page may name them).

### The rounds' named data-ui gaps that still hold (named, not patched)

From `docs/proposals/v2-overview-2026-11-24/kit/GAPS.md` and `v2-tabs-2026-11-24/t1/NOTES.md`; each with its ask there:

- A registered view cannot say it is content-sized: one CSS rule in `runs_views.css` (`data-views { height: auto }` on
  a `tc-*` panel without `h`). *Ask:* `registerView(type, {fit: 'content'})`.
- A records peek's rows open nothing: the worst-target lists are the host views' own, each row a target-view link.
- A two-stage median (median over targets of each target's median over its runs) is no stock summary, so every tile and
  page above is a host view. *Ask:* `value: {summary: Median, per: target_key}`; and a view plugin's `headline(input)`
  for §55's tiles.
- A chart's colour has eight slots and its legend lists every value: the host views draw direct labels.
- A host view's switch (League facet, matrix columns and folds, sweep panels, trade-off cost) is kept in localStorage,
  not the URL.
- T1: a derived dataset is fixed at write time (the rail recounts which pairs show, never re-pairs); a line's
  `point: true` overlay reads every row (drawn as layers); a sort after transforms is ignored (the per-config chart
  ranks by a zero-padded `#01` label, as V2's League did).

## Coverage, one tab away (2026-11-25)

Feedback fb-5defddb0, Zach, Daily Note 2026-11-23 "Coverage Feedback": *"I need to basically like integrate this into the
viewer ... trajectory Coverage Viewer Where you can put in like datasets or single trajectories ... a page you can see
standalone or just quickly get there from the traj compare stuff"*. The coverage viewer is `traj_compare.coverage`
(docs/COVERAGE.md), and every site written with `write_dataset_report(coverage=True)` (every bench site) has its page at
`<site>/coverage/index.html`. The workbench reaches it from both levels:

- **The Coverage tab** (after Runs and "Does sim match real?", before `pages=`), present when any site has a coverage page:
  one card per such deployment (its page's own headline numbers: joint range used, angle × speed cells visited, tool
  voxels; how many of its targets the rail keeps runs of), the picked deployment's page **embedded below as written**
  (an iframe of the site's own file, so the tab and the standalone page cannot disagree), and **Open on its own ↗**. The
  deployments without a page are named in one line. The pick is remembered; when the rail keeps no run of it, the tab
  shows the first deployment it does keep.
- **The target view's Coverage ↗** (when its site has a page): the page with this target's trajectory highlighted,
  `<site>/coverage/index.html#tab=trajectories&trajectory=<name>` (the Trajectories tab, its row selected, and the
  One joint paths and 3-D views draw it in black). The name is the page's own (`dataset.coverage_names`).
- **What the rail does to it:** it picks the deployment and recounts the cards; it never refilters the page, which counts
  every target of its deployment once (a target repeated by many runs counts once) and is written with the site. The
  answer line says so. Refiltering by the rail would need the coverage *workbench* (`traj_compare.coverage.workbench`,
  per-trajectory parts) written per site and the rail carried into it: not built.
- Framed, the page's own links (its breadcrumb to the dataset page) open in the whole window (`<base target="_top">`).
- Files: nothing new in `out_dir`; `index.html`'s `tc-views` carries `coverage: {deployments: [{deployment, site, href,
  title, trajectories, numbers, names}], missing: [...]}` (or `null`), `target.html`'s `tc-config` carries
  `coverage: {<site key>: {href, names}}`. Python: `runs_workbench._coverage`; the view: `tc-coverage` in
  `assets/runs_views.js`.
- Acceptance: `tests/test_runs_workbench_coverage.py` (Python) and `tests/test_runs_workbench_coverage_browser.py`
  (headless Chrome), both written red first.

## The three levels

| Level | Page | What it is |
| --- | --- | --- |
| Dataset workbench | `index.html` | stock data-ui `<data-workbench src="runs.base">` over `runs.json`: one row per measured line (a run) of every site |
| Target view | `target.html?site=<key>&target=<slug>&keep=<lines>&back=<url>` | one target's runs as summary data: run list with checkboxes, verdict, repeats as lines or bands, joint error per joint, FB share |
| Playback | `playback/<key>/report.html` (ours) or Rerun | the ticked runs and their target: `write_comparison_report` as it is (3D stage + question tabs), or one Rerun recording, one plot per joint, one line per run |

- Workbench → target view: a Targets or Runs row's **Open target view** opens it in the same tab. The runs the rail keeps
  for that target start ticked (`keep=`); every other run of the target is listed unticked ("outside the rail filter").
  `back=` is the workbench's URL, so it holds the rail (`?deployment=…&config=…`) and the tab (`#tab=targets`).
- Target view → playback: **Open playback · N runs** (`POST <dir>/__playback`) builds traj_compare's comparison viewer
  over exactly the ticked runs and opens it in the same tab; its breadcrumb is `‹ All targets` (the workbench, filter
  kept) › `<target>` (this target view with the same runs ticked) › `Playback · N runs`. **Open in Rerun · N runs**
  (`POST <dir>/__rerun/selection`) writes one `.rrd` (stock `robot_msgs.viz.rerun`) and starts the pinned viewer.
- On a static host (no `traj_compare.serve`) or from `file://`, both buttons say what they need: the server command and
  the page to open from it. Written with `rerun_server=False`, the Runs rows offer no Open in Rerun and the target view
  says so up front.

## API

```python
from traj_compare import write_runs_workbench

write_runs_workbench(
    {"UR5e + Conveyor PnP cell": "dashboard/ur5e", "BAM FB": "dashboard/bam_fb"},  # sites write_dataset_report wrote
    "dashboard/all",
    model_type={"some_config": "computed torque"},  # config -> model type; None = no facet; unmapped = "other"
    dataset_titles={"conveyor-v1": "Conveyor PnP v1"},  # the dataset tag's values, renamed
    labels={"kind": "Motion kind"},
)
```

```bash
python -m traj_compare.serve dashboard
```

Then open `/all/index.html`. The server builds each run's report lazily (NAVIGATION.md C3), the playback pages and the
selection `.rrd`s.

- Rows come from each site's own payload (`traj_compare.dataset.read_site_payload`), never from the runs: every number
  is the dataset view's. KPIs are run tags (default: every site's `Sweep` y and metrics, `{series}` = the line's series),
  plus traj_compare's worst-joint RMS (°), tool RMS (mm, `robot_msgs.compare`) and feedback share.
- `rail=` (default V2's order: deployment, dataset, split, model type, config, sim / real, speed, kind, date, target,
  then a Name search) names columns or run tags; one no row has is left out.
- Splice points: `overview=` picks the Overview (default the tiles; "How to swap" above) or replaces it with a `.base`
  page; `pages=` and `views=` add tabs at the end (after "Does sim match real?"). The target view's playback is the existing `write_comparison_report`, called as a sub-assembly
  (`traj_compare.selection.build_playback`): a new look of that viewer lands there with no change here.

## V2's nine named gaps (`docs/proposals/tensorboard-2026-11-24/v2/NOTES.md`)

| # | Gap | Whose | Now |
| --- | --- | --- | --- |
| 1 | No date column, so no date range | the bench's | traj_compare reads a run's `date` tag into the rows and the rail when any run has one (NAVIGATION.md Part A's date tag); no bench run carries one yet. Ask (bench): tag each run with its `date`. |
| 2 | A drill action cannot run host code | data-ui's | host workaround kept (`assets/runs_host.js`: the stock button's click, capture phase, by its label). **Ask:** `drill.actions[].event: "<name>"`, dispatching a cancelable, bubbling `data-scope-drill` `{action, row}`, or `href` with `target: "_self"`. |
| 3 | `post:` sends no body | data-ui's | traj_compare.serve takes the query form (`?runs=<folder>:<series>,…`) beside the JSON body. **Ask:** `post` with `body:` (a JSON template filled from the row). |
| 4 | Drill actions are per file: a Targets row offered Open run report (404) | data-ui's | fixed in data-ui `354ccdde` (a row shows only the actions whose `{column}`s it has); vendored `main` has it. |
| 5 | No conditional note | data-ui's | host warning line kept (more than one deployment in the filter). **Ask:** `notes: [{when: "distinct(deployment) > 1", text}]` on a page. |
| 6 | No fold at full width | data-ui's | host Fold button kept (sets the stock `fold="always"`). **Ask:** a fold toggle on `<data-fold>` at any width (`fold="toggle"`, its own button, remembered). |
| 7 | A colour legend lists every dataset, also the filtered-out ones | data-ui's | kept. **Ask:** with `colors:` keep the colours stable but list only the values left (`legend: present`). |
| 8 | data-ui chart quirks | data-ui's | workarounds kept in the `.base`: dots, not bars, on a log axis; each median written back under the KPI's own name; `target_key` named in `hover`; a zero-padded rank in the label; the Name search only over columns no other facet has (`target_slug`, `run`). **Asks:** bars on a log axis; an encoding aggregate over a transform's field; every transform's input field reaching Vega; a sort after transforms; a search facet's pill holding only its typed text (today `railPills` gives it every value of every property it searches, so a Config tick also showed as "Name search ctc_tuned", and that pill's ✕ dropped the Config pick; measured on the bench). |
| 9 | Run reports built lazily only by the round's server | traj_compare's | fixed: rows link each run's report in its own site; `traj_compare.serve` builds it (C3), and serves `__playback` and `__rerun/selection`. |

Also fixed on traj_compare's side: the model-type mapping is the caller's (`model_type=`), never a regex in the package;
dataset names are the caller's (`dataset_titles=`); a target is named by its key, not its first run's title (which, for a
one-run target, names that run's config).

Asked of robot_msgs: a public `finish(stream)` (today `robot_msgs.viz.rerun._finish`) to send the stock default dashboard
for a stream logged with options (`degrees`, `color`, `label`); `selection.build_selection_rrd` calls the private one.

## Not done here

- V2's own Overview (League, League by model type, About, Speed sweeps) is no longer the default; it stays one word
  away (`overview="v2"`).
- No in-page switch between the Overview options: the swap is the caller's `overview=` (the rounds' galleries are the
  pick surface).
- T2 ("Where in the workspace is it worst?") and T3 ("Which config wins head to head?") of the tabs round are not
  built.
- Playback colours are the comparison viewer's own palette, not the configs' colours: the viewer is called as it is.
- A playback is one target's runs; picks of two targets are refused (400). A basket across targets (V5) is not built.
