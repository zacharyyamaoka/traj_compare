# The playback viewer: five proposals (run-view round, 2026-11-24)

Zach (Daily Note 2026-11-24): the classic trajectory compare viewer, one target and a bunch of its runs, with the 3D
stage and the question tabs; *"as you drag the time on any of the figures it syncs across all of the other ones"*; the
dataset viewer should import it; Rerun is its peer. Clarified the same night: it is level 3 (dataset view → target view →
**playback viewer**), opened from the target view with the runs ticked there.

- `CONTRACT.md` and `criteria.json` were frozen before R2–R5 were built (R1 first: it is also the check's baseline).
- `gallery-content.json` (names, theses, scores) was written after all five existed and passed `check.cjs`.
- Gallery: `/home/bam/traj_compare/reports/media/run-view-proposals-2026-11-24.html` (`build_gallery.py`).

| | Variant | Time | Runs | Layout |
|---|---|---|---|---|
| R1 | Every figure is a scrubber | drag any chart; Shift-drag / wheel zoom | today's chips | today's |
| R2 | One timeline for the page | one line through every chart + a docked time lane | one track per run | charts stacked on one x |
| R3 | Summary and playback, one page | drag charts; brush the summary strip to zoom | the target view's run list | run list · stage · tabs, bands |
| R4 | Rerun parity | Rerun's time panel and gestures (+ plain drag) | Rerun's blueprint tree | the questions blueprint |
| R5 | Moments first | opens at the worst; jump, step, snap | each chart's readout rows | a readout under every chart, ghost arms |

Each `rN/` carries its own copies of the viewer files it changes (from `src/traj_compare/assets` @ 38b5967, changes
marked `RV:`), a `NOTES.md` (decisions, best when / loses when, keep-parts, change size) and `gestures.json`.

## Run it

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/run-view-2026-11-24/serve.py --port 8853
```

Then `http://127.0.0.1:8853/r1/index.html?fixture=tta&keep=p5s-pass3,p6s` … `/r5/…`, or the many-runs fixture
`?fixture=bam_fb&keep=3460,3461,3463,3465,3466,3467,3471,3474,3476`. Add `&dry=1` to have Open the same in Rerun write
the recording without starting the viewer.

## Regenerate the gitignored data (`data/`, ~14 MB)

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/run-view-2026-11-24/fixtures.py
```

It reads the Trajectory Tracking Agent's `outputs/dropins/inputs/` (its build_dropins.py `prepare` writes them), the
bench's `reports/media/dashboard/bam_fb/runs/`, and the target view's line index `../tensorboard-2026-11-24/data/bam_fb.js`.

## Checks and the gallery

With the server on 8853: `node check.cjs rN --video` writes `shots/rN/check.json`, the stills and the drag films; then
`python3 build_gallery.py`.
