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
written red first.

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
- Splice points for the sibling rounds: `overview=` replaces the Overview page (a `.base` page); `pages=` and `views=`
  add tabs after Runs. The target view's playback is the existing `write_comparison_report`, called as a sub-assembly
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
| 8 | data-ui chart quirks | data-ui's | workarounds kept in the `.base`: dots, not bars, on a log axis; each median written back under the KPI's own name; `target_key` named in `hover`; a zero-padded rank in the label; the Name search on `target_slug`. **Asks:** bars on a log axis; an encoding aggregate over a transform's field; every transform's input field reaching Vega; a sort after transforms; two facets on one property each with its own typed text. |
| 9 | Run reports built lazily only by the round's server | traj_compare's | fixed: rows link each run's report in its own site; `traj_compare.serve` builds it (C3), and serves `__playback` and `__rerun/selection`. |

Also fixed on traj_compare's side: the model-type mapping is the caller's (`model_type=`), never a regex in the package;
dataset names are the caller's (`dataset_titles=`); a target is named by its key, not its first run's title (which, for a
one-run target, names that run's config).

Asked of robot_msgs: a public `finish(stream)` (today `robot_msgs.viz.rerun._finish`) to send the stock default dashboard
for a stream logged with options (`degrees`, `color`, `label`); `selection.build_selection_rrd` calls the private one.

## Not done here

- The Overview stays V2's (League, League by model type, About, Speed sweeps). The sibling round's pick splices in
  through `overview=`.
- Playback colours are the comparison viewer's own palette, not the configs' colours: the viewer is called as it is.
- A playback is one target's runs; picks of two targets are refused (400). A basket across targets (V5) is not built.
