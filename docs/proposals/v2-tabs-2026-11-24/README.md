# V2's workbench: three proposals for a fourth tab (2026-11-24)

Zach's ask (Daily Note Nov 24): "Are there any more tabs we want to add to that outer view? we have overview, targets and
runs. Make 3 prospaols for 3 different tabs we could add". Base: V2 "Two viewers, the filter carried"
(`../tensorboard-2026-11-24/`, read-only). Each `tN/` is V2 plus ONE tab, titled as a question.

- `CONTRACT.md` and `criteria.json` were frozen before any tab was built (the data check that chose the three is in
  CONTRACT.md); `gallery-content.json` (names, theses, scores) was written after all three were built and checked.
- The gallery: `/home/bam/traj_compare/reports/media/v2-tab-proposals-2026-11-24.html` (`build_gallery.py`).

| | Tab | What it reads | How stock |
|---|---|---|---|
| T1 | Does sim match real? | `data/pairs.json`: a real run and its prediction of the same motion (1,752 sim twin, 1,204 rehearsal) | a `.base` page |
| T2 | Where in the workspace is it worst? | `data/t2-cells.json`: each line's error in each q × qd cell of the bench's coverage grid | a host page, stock coverage-plane + table |
| T3 | Which config wins head to head? | `data/h2h.json`: target × sim/real × A × B (26,442 match-ups) | a `.base` page with an A/B page control |

## Run it

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-tabs-2026-11-24/serve.py --port 8852
```

Then `http://127.0.0.1:8852/t1/index.html`, `/t2/index.html`, `/t3/index.html`, and the fourth tab. The server is
needed because data-ui ships ES modules (Chrome refuses those over file://). `?dry=1` makes Open in Rerun build the
`.rrd` without launching the viewer.

## Regenerate the gitignored data

V2's rows and vendored data-ui must exist (`../tensorboard-2026-11-24/README.md`), then:

```bash
/home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-tabs-2026-11-24/build_tabs.py --cells
```

(35 s; without `--cells` it rebuilds the pairs, the match-ups, the `.base` files and the oracle, and keeps T2's cells.)

## Checks and the gallery

With the server on 8852: `node check.cjs tN --port 8852 --video` writes `shots/tN/check.json` (the new tab's numbers
unfiltered and after the scenario's one rail pick, each against `data/oracle.json`; the drill to the target view and
back; V2's own checks), the stills and the session video. Then `python3 build_gallery.py`.

## Scenario (each tab)

All 18,507 runs → one rail pick → the tab recounts: T1 Deployment = BAM FB · T2 Config = ctc_tuned · T3 Speed = 1.0 ×
(A = ctc_tuned, B = ctc_tuned_v2).

Each tab's own decisions and named data-ui gaps (with the ask) are in its `tN/NOTES.md`.
