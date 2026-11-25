# The Overview tab of V2: five proposals (2026-11-24)

Zach picked V2 "Two viewers, the filter carried" of `../tensorboard-2026-11-24/` and asked: "improve the overview tab on the
dataset view It was better in the past not sure what is going on now, show 5 proposals here … Probably shwoing a model x
dataset or something seems reasonable here as one example". `CONTRACT.md` diagnoses what V2's Overview lost against Nov
23's League and freezes the round; `criteria.json` holds the weighted criteria and gates, frozen before any variant was
built; `gallery-content.json` the names, theses and scores, written after every variant was built and checked.

| | Variant | The Overview's primary object |
|---|---|---|
| O1 | The League, back, over the rail | Nov 23's sentence + League table + config × dataset · split matrix |
| O2 | Model × dataset matrix first | model type › config × deployment › dataset, columns switchable |
| O3 | Headline tiles → drill | six §55 tiles, each opening its full page |
| O4 | Speed is the x axis | tool RMS vs speed, one line per config, small multiples |
| O5 | Trade-off map | accuracy vs cost per config, per deployment, the frontier |

Gallery: `/home/bam/traj_compare/reports/media/v2-overview-proposals-2026-11-24.html` (`build_gallery.py`).

## Run it

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/serve.py --port 8851
```

Then `http://127.0.0.1:8851/o1/index.html` … `/o5/index.html`. `serve.py` serves this folder and borrows V2's rows
(`/data/`), target view (`/common/`), bench (`/bench/`) and Rerun endpoint from `../tensorboard-2026-11-24/` (read-only).

## What is here

- `build_bases.py` → `o1 … o5/` (`views.base`, `index.html`, `host.js`, `host-common.js`, `gates.json`): V2's files with only
  the Overview page and its views replaced. Re-run it after changing it.
- `kit/model.js` (the one aggregation), `kit/views.js` + `kit/views-css.js` (the host views, registered through data-ui's
  `registerView`), `kit/GAPS.md` (what data-ui could not draw, with the exact ask).
- `oracle.py` → `oracle.json`: every stated number recomputed in Python; `check.cjs <oN> --port 8851 --video` compares the
  page to it in both states and writes `shots/<oN>/` (gitignored).
- Gitignored and regenerated: `vendor/data-ui` (`node /home/bam/data-ui/bin/data-ui.mjs vendor main --into
  /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/vendor/data-ui`; built against `1f7c004`), `shots/`, and
  V2's `data/` (its README says how).
