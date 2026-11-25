# traj_compare on the stock workbench: five ways to link Dataset → Target → Run (2026-11-24)

Zach's ask: the TensorBoard pattern for the trajectory comparison viewer. The ask was refined the same evening
(Daily Note Nov 24 ~l.2045–2116): runs are atomic; the rail filters runs across ALL deployments; there are three tabs,
Overview (the League), Targets and Runs; and a second stage, the target view, has **Open in Rerun** for the selected runs.

- `CONTRACT.md` was frozen before the variants were built. Its first framing, the TensorBoard shell, was redirected
  before any scoring; that history is kept below the line in the file.
- `criteria.json` holds the re-frozen weighted criteria and gates. `criteria-shell-v1.json` is the superseded set.
- `gallery-content.json` holds the names, theses and scores, written after every variant was built and checked.
- The gallery is `/home/bam/traj_compare/reports/media/tensorboard-proposals-2026-11-24.html`, built by `build_gallery.py`.

| | Variant | How the target view is reached | "Selected" = |
|---|---|---|---|
| V1 | The rail is the selection | the rail filtered to one target → the Runs tab shows its view | passes the rail |
| V2 | Two viewers, the filter carried | its own page, `keep=` + `back=` | the checkboxes, seeded by the rail |
| V3 | The target is a workbench page | a 4th tab in the same component | its checkboxes |
| V4 | Model × deployment first, side pane | a resizable pane beside the tabs | the pane's checkboxes |
| V5 | A selection basket across targets | `target.html?basket=…` | the basket |

## Run it

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/serve_round.py --port 8841
```

Then open `http://127.0.0.1:8841/v1/index.html` through `/v5/index.html`. The server is needed because data-ui ships ES
modules, and Chrome refuses those over file://. A real Open in Rerun starts the pinned Rerun viewer. Add `?dry=1` to
build the `.rrd` without launching the viewer.

## Regenerate the gitignored data

```bash
python3 /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/extract.py /home/bam/arm_motion_bench/reports/media/dashboard/ur5e /home/bam/arm_motion_bench/reports/media/dashboard/ur5e_alone /home/bam/arm_motion_bench/reports/media/dashboard/bam_fb /home/bam/arm_motion_bench/reports/media/dashboard/pendulum
```

```bash
python3 /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/build_rows.py
```

```bash
node /home/bam/data-ui/bin/data-ui.mjs vendor main --into /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/vendor/data-ui
```

The prototypes were built against data-ui `e8c73dc`.

## Checks and the gallery

With the server on 8841, `node check.cjs vN --port 8841 --video` writes `shots/vN/check.json`, the stills and the
session video. Then run `python3 build_gallery.py`.

## Shared parts

- **`common/target.html`** is the target view: traj_compare's Target-level look over the site's own
  `targets/<slug>.js`, with checkboxes and Open in Rerun.
- **`serve_round.py`** serves this folder and `/bench/`. It builds run reports lazily and provides
  `POST /__rerun/selection`, which writes one `.rrd` per selection through stock `robot_msgs.viz.rerun`: one plot
  per joint, one line per run, plus the target.
