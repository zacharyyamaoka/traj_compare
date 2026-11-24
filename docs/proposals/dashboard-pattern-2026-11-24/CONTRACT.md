# Filter rail + tabbed dashboards in data-ui — five proposals (2026-11-24)

Zach, Daily Note Nov 24 "# UR in robot Parts.." (~l.245–417): "this general pattern that should be supported in data-ui
is like multi tab dashboards, where you filter the data that is included in the dashboards with a left hand bar...
this will happen again and again! so please show like 5 different ways of doing this pattern in data-ui with this as
the case study." This file is the frozen contract every lane builds against. The dispatcher owns it, `check.cjs`,
`extract.py`, `criteria.json`, `data/`, `vendor/` and `host/`; a lane writes only inside its own `p<N>/` folder.

## What he said (the spec)

- **The atomic unit is the trajectory.** The first view is round 2's V2 "Rows first": a left filter rail, and the
  coverage dashboards re-aggregate what the rail leaves.
- **Datasets combine.** "You can just have a thing here for like dataset, above split, it can be the first one" — a
  Dataset filter, FIRST in the rail. "the dev/holdout will apply then to all of the datasets you include. I don't want
  the option to like include dev of one particular dataset and not of the other."
- **Two levels:** (1) across datasets, (2) within a dataset, filtering particular trajectories. Not the same as
  comparing runs of one trajectory (that is traj_compare's run view; out of scope here).
- **Tabs that feel like switching dashboards**: "we are filtering data and then switching between dashboards almost".
  He likes V3's / V5's tab row, the TensorBoard layout (left = what data shows, tabs = which dashboard) — "but I don't
  like the tabs here at the top top as then its harder to put it in another app".
- **Compact, drops into anything**: "ultimately I want the viewer to be a bit more compact … so it can drop into
  anything". He likes V5's left list and V2's facet rail; V3's look ("V3 I really like this").
- **Further filtering within the page**, e.g. the joint picker on the one-joint dashboard (a within-tab control).
- "we don't need to reinvent the wheel here" — W&B and TensorBoard are the prior art; data-ui is where this pattern
  lives so it repeats across his apps.

## The shared scenario

All four UR5e trajectory datasets, dev + holdout at full speed: 212 trajectories (UR5e alone · Workspace 54, Cell ·
Workspace 54, Cell · Conveyor PnP 64, Cell · Conveyor Collision 40). `extract.py` (header has the command) wrote
`data/` (read-only for lanes):

| File | What |
|---|---|
| `coverage.json` / `.js` | one `traj_compare.coverage/1` payload over all 212 (group_by = dataset); its grids are shared by every dataset |
| `trajectories.json` / `.js` | one row per trajectory: `name` ("<dataset slug>/<task>"), `task`, `dataset_slug`, `tags` {dataset, split, kind, rung, tags, belt_speed?}, the payload's per-trajectory numbers, tool numbers, `only_it_q_qd_cells` (over all 212), `rrd` |
| `membership.json` / `.js` | per trajectory, the cells it visits on the payload's grids; rebuilding counts from it equals the payload (asserted) |
| `datasets.json` / `.js` | one row per dataset: label, slug, deployment, full title, trajectories, dev, holdout |
| `rrd/<slug>/<task>.rrd` | Rerun 0.40 per trajectory |

data-ui is vendored at `vendor/data-ui/` (main 2f08a88). Round 2's prototypes are next door
(`../coverage-ui-2026-11-24/`): copy what you reuse — V2's `occupancy` view (recounts trajectories per cell over
whatever rows it gets; `v2/js/`), V3/V7's coverage views and legends (`v3/views/`, `v7/views/`), V7's sheet — into
your folder; never edit them. The figures are NOT what this round judges: reuse them, keep them honest (a subset count
says so), spend your effort on the container pattern.

Serve the round on your own port:

    /home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24 --port <port>

`POST /__rerun/open?rrd=data/rrd/<slug>/<task>.rrd` starts native Rerun (check.cjs intercepts it; never call it for real).

## Two pages per proposal

- `p<N>/index.html` — the component full page (1440 × 900).
- `p<N>/embed.html` — the SAME component dropped into a fake host app: copy `host/embed-template.html` (a host header,
  a host sidebar, and `<div id="host-slot">` of 1000 × 680) and mount your component inside `#host-slot`. Nothing of the
  component may draw outside the slot: no page-top tabs, no `position: fixed` escaping, no body-level popovers outside it.

## Hard gates (`check.cjs` measures every one)

- **P1** Dataset is the first filter group in the rail, listing the four datasets; ticking one dataset makes the
  trajectory count equal its size, and a figure repaints.
- **P2** Split applies across the datasets ticked: two datasets + holdout → the count equals the sum of their holdouts.
- **P3** At least four dashboards switch like tabs, and switching keeps the filter (the count doesn't change).
- **P4** Drops into anything: in `embed.html` every visible part of the component lies inside `#host-slot`, and the
  host header stays visible.
- **P5** The joint picker shows on its dashboard only; colours (colormap at least) sit behind one gear inside the
  component and repaint.
- **P6** A trajectories table drills into one trajectory, with Open in Rerun posting its `rrd`.
- **P7** No console or page errors; no sideways scroll at 1440 × 900.

## `gates.json`

```json
{
  "ready": "<sel present once drawn>",
  "count": "<element whose text starts with the number of trajectories the filter leaves, e.g. '28 of 212'>",
  "dataset_group": "<the dataset filter group>", "first_group": "<the first filter group in the rail>",
  "dataset_option": "<selector template with {label}, the clickable option for that dataset>",
  "split_option": "<selector template with {split}>",
  "figure": "<a figure on the overview that a filter repaints>",
  "tabs": {"overview": "<sel>", "joint": "<sel>", "trajectories": "<sel>", "tool": "<sel>"},
  "joint_picker": "<sel>",
  "settings": "<gear>", "cmap": "<select or group>", "cmap_value": "magma", "cmap_option": "<when not a select>",
  "joint_figure": "<a figure on the joint dashboard the colormap repaints>",
  "drill_trigger": "<first row of the trajectories table>", "drill_action": "click | dblclick",
  "drill": "<the drill>", "open_rerun": "<Open in Rerun in the drill>",
  "embed_root": "<the component's root element in embed.html>"
}
```

## `story.json` — 4–5 steps from a fresh load of index.html

Same format as round 2 (`label`, `caption`, `actions`, `highlight`). Step 1 is the landing (no actions), the hero.
The check adds one more still itself: `embed.html` as loaded.

## Proof

`node /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/check.cjs p<N> --port <port> --shots /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/shots > /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/shots/p<N>.check.json`
exits 0, and you looked at every still. Then `p<N>/NOTES.md`: name, thesis, 2–4 decisions, best when / loses when,
2–3 splice parts, what's host code vs stock data-ui vs NEW data-ui API it would need (name the element / `.base` keys),
and how a second app (e.g. robotparts' datasheets, Vibe Tracks) would reuse it unchanged.
