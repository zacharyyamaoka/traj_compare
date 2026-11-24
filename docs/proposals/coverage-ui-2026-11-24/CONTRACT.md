# Coverage UI, round 2 — six proposals (2026-11-24)

Zach's feedback on the coverage page (Daily Note Nov 23, "# Coverage feedback", ~l.1540, and "# Feedback on coverage
viewer and traj view", ~l.1499) asks for 3 proposals built on **data-ui** (moving the coverage visuals into stock data-ui
views where that's needed) and 3 that keep **hand-rolling**, each fixing what he didn't like. This file is the frozen
contract every lane builds against. The dispatcher owns it, `check.cjs`, `extract.py`, `data/` and `vendor/`; a lane
writes only inside its own `v<N>/` folder.

## What Zach said (verbatim where it matters)

- Likes: "at a glance being able to see like the entire trajectory dataset, and then also like the tool position and
  orientations"; "the different tabs that allow me to focus in on particular aspects"; sorting the table.
- 1 · the headline numbers: "it doesn't make sense to be showing them the entire time".
- 2 · "There is no drill in option in the trajectories page … I want the option to open in Rerun".
- 3 · "The trajectories have these random colors next to them but its not clear what those mean to me." (Every row has
  a blue square: it is the trajectory's *group* colour, group_by = split, and nothing says so.)
- 4 · "I should also be able to like filter etc this table, and possibly like create saved views … it should be one of
  our like generic tables from data-ui" (his reference: the robotparts Datasheet table — view tabs across the top
  ("Datasheet / Datasheet only / Measured vs datasheet / Sources / +"), search + settings icons at the right, groups
  that fold, "38 of 38 rows · 7 groups · Unfold all · Fold all").
- 5 · the control strip (COLOURS · Reverse · SCALE · JOINT) shows on every tab "though they don't apply to what is
  being looked at"; "the joint selector should just apply on the single joint view and the colors … perhaps those are
  in a settings gear in the top right corner, things that apply to the entire thing that you set once". (l.1499: "a
  settings kinda page on our custom viewer where we put the color choice configuration and anything else … a gear
  icon in the top right hand corner".)
- 6 · "In some sense this is really just a dashboard on data right…?" — data-ui is "the common visual language".

## The shared scenario (every variant, same data, same viewport)

The UR5e · Entire Workspace, dev + holdout at full speed: 54 trajectories, 12,870 samples, 6 joints, tool in the cell
frame. Regenerate with `extract.py` (the header has the command). Files, all under `data/` (read-only for lanes):

| File | What |
|---|---|
| `coverage.json` / `.js` | the `traj_compare.coverage/1` payload (schema: `/home/bam/traj_compare/docs/COVERAGE.md`) |
| `trajectories.json` / `.js` | one row per trajectory: `name`, `tags` {split, kind, rung, tags}, `duration_s`, `samples`, `span_pct[joint][q/qd/qdd/qddd]`, `new_cells`, `only_it_q_qd_cells`, `tool_path_m`, `tool_speed_max_m_s`, `tool_z_min_m`, `tool_z_max_m`, `tool_tilt_max_deg`, `rrd` |
| `membership.json` / `.js` | per trajectory, the cells it visits on the payload's own grids (planes per joint, xy/xz/yz pixels, voxels, sphere directions); `voxel_shape`, `sphere` [rings, sectors]. Rebuilding counts from it equals the payload exactly (extract.py asserts it) |
| `samples.json` | every sample as a row: trajectory, split, kind, rung, t_s, `<joint>_q_deg / _qd_deg_s / _qdd_deg_s2` (joint without `_joint`), x/y/z_mm, tool_speed_m_s, tilt_deg, azimuth_deg, yaw_deg (9.3 MB: a variant may subsample it, and must say so where it does) |
| `rrd/<name>.rrd` | per trajectory, Rerun 0.40: q/qd/qdd per joint in degrees on its own clock + the tool path |

`.js` twins set `window.COVERAGE_UI.<name>` for `<script src>`. data-ui is vendored at `vendor/data-ui/` (data-ui `main`,
`VENDOR.json` says which commit): link `../vendor/data-ui/data-ui.css` and `../vendor/data-ui/data-ui.js`. Never copy or
edit data-ui's files; a view data-ui lacks is registered from your own folder with `registerView` (data-ui
`docs/CONTRACT.md` §1). The live page you are improving: `/home/bam/traj_compare/src/traj_compare/coverage/page.py` and
`src/traj_compare/assets/coverage*.{js,css}` (+ `coverage_color.js`, `three.min.js`, `viewhelper.js`); copy what you
reuse into your folder, never edit those.

Serve the whole round (data, vendor, every variant) with one command, on your own port:

    /home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port <your port>

and open `http://127.0.0.1:<port>/v<N>/index.html`. Its `POST /__rerun/open?rrd=<path relative to the round>` starts the
native Rerun viewer on that file and answers `{ok, command}`; **Open in Rerun** calls it with `rrd=data/rrd/<name>.rrd`,
and shows the returned `command` (with a Copy button) when the call fails (e.g. the page opened from file://).

## Hard gates (pass/fail, `check.cjs` measures every one)

- **G1** the headline numbers show on the overview and nowhere else.
- **G2** the trajectories table filters (typing narrows the rows), sorts (a header click reorders) and has saved views
  (≥ 2, and you can save the current one); **G2b** a row drills into that trajectory, and the drill has **Open in
  Rerun** posting `rrd=data/rrd/<its name>.rrd`.
- **G3** every colour beside a trajectory is explained on screen (a legend), or there is no such colour.
- **G4a** the joint picker shows only where it applies; **G4b** colormap, Reverse and scale live behind one gear (top
  right), are hidden until it opens, and changing the colormap repaints the figures.
- **G5** no console or page errors. **G6** no sideways page scroll at 1440 × 900.
- Every number shown comes from `data/` (computed by `analyze`), not recomputed in the page — except where a variant's
  thesis is to re-aggregate a filtered subset from `membership.json`; then the page says it is a subset count.
- Keep the tabs, or named focus areas that do the same job: at least Overview, One joint and Trajectories exist.

## `gates.json` (in your folder; `check.cjs` reads it)

```json
{
  "ready": "<selector present once the page has drawn>",
  "tabs": {"overview": "<sel>", "joint": "<sel>", "trajectories": "<sel>"},
  "stats": "<the headline numbers' container>",
  "joint_picker": "<sel>",
  "settings": "<the gear button>", "settings_panel": "<sel>", "settings_close": "<sel, optional: else Escape>",
  "cmap": "<select or button group>", "cmap_value": "magma", "cmap_option": "<sel, when cmap is not a <select>>",
  "reverse": "<sel>", "scale": "<sel>",
  "figure": "<a figure on the One joint tab that the colormap repaints>",
  "table_rows": "<one visible data row of the trajectories table>",
  "filter": "<the table's text filter input>", "filter_query": "holdout",
  "sort_header": "<a column header whose click reorders the rows>",
  "saved_view_items": "<each saved view (≥ 2)>",
  "drill_trigger": "<what you click to drill into the first row>", "drill_action": "click | dblclick",
  "drill": "<the drill panel or page; its text names the trajectory>",
  "open_rerun": "<the Open in Rerun button inside the drill>",
  "row_colours": "none" | {"legend": "<sel visible on the trajectories tab>"}
}
```

## `story.json` — the walkthrough (3–5 steps, the gallery's stepper)

`[{"label": "short state name", "caption": "what to notice (one sentence)", "actions": [{"click": sel} | {"fill":
[sel, text]} | {"select": [sel, value]} | {"dblclick": sel} | {"hover": sel} | {"scroll": sel} | {"press": key} |
{"wait": ms}], "highlight": "<the control this step demonstrates>"}]` — steps run in order from a fresh page load.
Step 1 is the landing (no actions): it is the variant's hero.

## Proof a lane hands back

`node /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/check.cjs v<N> --port <port> --shots /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/shots`
green (exit 0), and you *looked at* every `shots/v<N>/step-*.png`. Stop your server by its PID when done. Then a
`v<N>/NOTES.md`: name, one-sentence thesis, 2–4 consequential decisions, best when / loses when, 2–3 parts worth
keeping in a splice, what is simulated or missing, and (data-ui variants) which data-ui parts are stock, which are new
views you registered, and what data-ui would need to make it stock.
