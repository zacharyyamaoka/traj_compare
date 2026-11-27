# traj_compare site — landing page + documentation

A static two-page site for `robot_msgs.compare` (the maths) and `traj_compare` (the viewers):
`index.html` (what it is, the three pairings, quickstart, the example gallery, Open in Rerun) and
`docs.html` (how it works, the rules, every metric, verdicts online and offline, ISO 9283, latency,
goal / drift / Fréchet / integrals, the HTML report, Rerun, install, prior art with sources).

Output goes to a gitignored folder (default `bam_ws/reports/media/traj-compare-site-2026-11-10/`,
resolved to the main checkout even from a worktree). Only this folder's source is committed.

## Build

```bash
python3 ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/site/build_site.py
```

| Flag | Does |
| --- | --- |
| `--out DIR` | output folder |
| `--examples [SLUG ...]` | (re)build the example reports into `DIR/examples/<slug>/` first: `ur5e-conveyor` runs `python -m traj_integration_tests ur-sim-real` (traj_integration_tests' venv), `planar-2r` runs `traj_compare/examples/tracking_errors_demo.py --rerun` |
| `--record` | run `record_hero.py`: hero video + stills from the real UR5e / planar reports, and a Rerun web-viewer still |
| `--no-run` | do not execute `snippets/` (pages then show code without output) |
| `--python PATH` | interpreter with traj_compare + robot_msgs for the snippets (default: `traj_compare/.venv`) |
| `--extra-path P` | prepend to PYTHONPATH for snippets and examples (repeatable) |
| `--example-stills` | screenshot every built example into `media/<slug>.png` for the gallery (`record_hero.py --example-stills`, headless) |
| `--browser-channel chrome` | with `--example-stills`: drive an installed Google Chrome, so nothing downloads |
| `--public URL` | build for a public host served at URL: unbuilt examples and pending stills are left out, and the build folder's path in pages and Rerun commands becomes URL (`rerun <url>.rrd` opens from the site) |

The examples are `planar-2r`, `torque-breakdown`, `camera-overlay` and `dataset` (all from this repo's synthetic
`examples/`), plus `ur5e-conveyor` when bam_ws' `traj_integration_tests` is beside it. `robot_msgs` (whose source the
docs are checked against) is found at `$ROBOT_MSGS_DIR`, bam_ws' `src/external/robot_msgs`, or `~/robot_msgs`.

## The public site

https://zacharyyamaoka.github.io/trajectory_comparison_viewer/ is built and deployed by `.github/workflows/site.yml`
on every push to main (Pages source: GitHub Actions), the same as robot_msg_viz:

```bash
cd ~/traj_compare && MPLBACKEND=Agg .venv/bin/python docs/site/build_site.py --out _site --examples planar-2r torque-breakdown camera-overlay dataset --example-stills --browser-channel chrome --public https://zacharyyamaoka.github.io/trajectory_comparison_viewer/
```

Then the workflow greps the folder for local paths and e-mail addresses and fails on any.

Then serve it, so every Open in Rerun button launches the pinned viewer:

```bash
uv run --directory ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare python -m traj_compare.serve ~/bam_ws/reports/media/traj-compare-site-2026-11-10 --port 8767
```

Opened from disk instead, the pages still work; the Rerun buttons copy the `uvx` command.

## How it stays true

- **Facts are read, not restated.** The Rerun pin, the ROS result codes and the dataclass fields are
  parsed from the code (`read_facts`), and every API name and default the pages state is checked
  against the source (`check_claims`, lists in `site_content.py`). A drift fails the build.
- **Snippets run.** Each `snippets/*.py` is executed against synthetic runs from `snippets/_fixture.py`;
  the region between `# --- show` and `# --- end` is shown, its stdout printed under it. A failing
  snippet fails the build.
- **The UR5e code shown is the example's own.** `build_site.py` copies the page-building statements out
  of `traj_integration_tests/.../ur_compare/sim_to_real.py` each build.
- **The Rerun button is the report's.** `el`, `copyText`, `copyTextFallback` and `buildRerunBar` are
  extracted verbatim from `traj_compare/assets/plots.js`.
- **Diagrams are computed** (`diagrams.py`) from the same geometry as the library: lag / cross-track vs
  contour on a curve, the conveyor frame, ISO 9283 from drawn points with ddof = 1.
- **Links are checked**: every internal `href` / `src` / `.rrd` and every `#anchor` must resolve.
- **Citations** are `[[n:key]]` tokens in `templates/docs.html` and `site_content.py`, numbered by first
  use into the Sources list. External sources are public URLs only.

## record_hero.py

```bash
uv run --no-project --with playwright==1.64.1 python record_hero.py --site <out> [--rerun-bin <cmd ...>]
```

Headless Chromium only, on a local server it starts and stops. The hero is stop-motion: a real
screenshot of the UR5e report after every step (scrub positions along the belt track, orbit
increments, the TCP error, verdicts + ISO 9283, the Sim → Real tab), each held for a set time, joined
by ffmpeg into `media/hero.mp4` (H.264) + `media/hero.gif` + `media/hero-poster.png`. Why stop-motion:
on a loaded machine both Playwright's video recorder and a raw CDP screencast delivered frames seconds
late, so cuts landed on the wrong step; a screenshot waits for a fresh paint. `playwright==1.64.1`
matches the Chromium build already in `~/.cache/ms-playwright`, so nothing downloads.

## Files

| File | What |
| --- | --- |
| `build_site.py` | the build: facts, checks, snippets, examples, media, templating, link check |
| `site_content.py` | sources, prior art, metric / ErrorStats tables, the checked claim lists, page fragments |
| `diagrams.py` | the inline SVGs, computed |
| `templates/index.html`, `templates/docs.html` | the prose |
| `style.css` | inlined into both pages; light + dark via `prefers-color-scheme` |
| `snippets/` | runnable code shown on the pages |
| `record_hero.py` | hero video + stills from the real reports |
