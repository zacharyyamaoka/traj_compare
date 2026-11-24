# Coverage UI, round 2 (2026-11-24): six proposals

Zach's Nov 24 coverage feedback (Daily Note Nov 23, "# Coverage feedback") as a babble round: three proposals built
on data-ui (V1 Stock dashboard, V2 Rows first, V3 Coverage views in data-ui) and three hand-rolled (V4 Tidy, V5 Focus
rail, V6 Who goes there), all on the same UR5e Entire Workspace data, plus V7, the AI-default splice of V3 with V5/V6's landing and V6's click-a-cell, built after the round on the same criteria and checks. `CONTRACT.md` is what every lane built against,
`criteria.json` the weighted criteria fixed before any variant existed, `check.cjs` the acceptance (his feedback as
pass/fail gates), `vN/NOTES.md` each proposal's own account.

The comparison gallery: `/home/bam/traj_compare/reports/media/coverage-ui-proposals-2026-11-24.html`
(`build_gallery.py` makes it from `gallery-content.json` + the check's captures).

## Open the live prototypes

```bash
/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24 --port 8830
```

then `http://127.0.0.1:8830/v1/index.html` … `v7/index.html`. Open in Rerun needs this server (it starts the native
viewer through `POST /__rerun/open`).

## Regenerate what git leaves out (real bench data and builds)

```bash
env -u VIRTUAL_ENV /home/bam/arm_motion_bench/.venv/bin/python /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/extract.py
```

```bash
node /home/bam/data-ui/bin/data-ui.mjs vendor main --into /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/vendor/data-ui
```

```bash
python3 /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/v1/rows.py
```

```bash
python3 /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/v3/rows.py
```

```bash
python3 /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/v7/rows.py
```

Then the checks and the gallery (the server above running on 8830):

```bash
node /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/check.cjs v3 --port 8830 --shots /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/shots
```

```bash
python3 /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/build_gallery.py
```

`check.cjs` writes its JSON to stdout; `build_gallery.py` reads `shots/vN.check.json`, so redirect each check there.
