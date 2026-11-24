# Filter rail + tabbed dashboards in data-ui (2026-11-24): five proposals

Zach's Nov 24 ask (Daily Note Nov 24, "# UR in robot Parts.."): show five ways data-ui could support "multi tab
dashboards, where you filter the data that is included in the dashboards with a left hand bar", with the four UR5e
trajectory datasets (212 trajectories) as the case. `CONTRACT.md` is what every lane built against, `criteria.json` the
weighted criteria fixed before any proposal existed, `check.cjs` the acceptance (7 gates, including mounting each
proposal in a fake host app's 1000 × 680 slot, `host/embed-template.html`), `pN/NOTES.md` each proposal's own account
and the data-ui API it proposes.

- P1 Workbench element · P2 The rail holds the tabs · P3 Every tab is a saved view · P4 Run selector (TensorBoard /
  W&B) · P5 A filter scope; the host composes.
- The comparison gallery: `/home/bam/traj_compare/reports/media/dashboard-pattern-proposals-2026-11-24.html`
  (`build_gallery.py` makes it from `gallery-content.json` + the check's captures).

## Open the live prototypes

```bash
/home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24 --port 8830
```

then `http://127.0.0.1:8830/p1/index.html` … `p5/index.html`, and each `pN/embed.html` (the same component inside a
host app). P5 also has `p5/card.html`. Open in Rerun needs this server.

## Regenerate what git leaves out

```bash
env -u VIRTUAL_ENV /home/bam/arm_motion_bench/.venv/bin/python /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/extract.py
```

```bash
node /home/bam/data-ui/bin/data-ui.mjs vendor main --into /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/vendor/data-ui
```

```bash
node /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/p1/tools/build.mjs
```

The prototypes were built against data-ui main 2f08a88; a newer vendor may differ. Then each check (server on 8830),
redirected to `shots/pN.check.json`, and the gallery:

```bash
node /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/check.cjs p1 --port 8830 --shots /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/shots
```

```bash
python3 /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/build_gallery.py
```
