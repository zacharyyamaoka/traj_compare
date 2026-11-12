"""Per-tab blueprints for the two shipped layouts ("questions", "evo"), for shoot.py to screenshot.

Runs with the integration venv (Pinocchio rebuilds the UR5e comparisons, seeded, so the payload
matches the .rrd that ``ur-sim-real`` wrote):

    traj_integration_tests/.venv/bin/python traj_compare/docs/rerun_layouts/shoot_named.py --root <report dir>

``<root>/ur5e-conveyor`` must hold the ``ur-sim-real`` output. Writes ``<root>/blueprints/*.rbl`` and
``<root>/manifest.json`` in the shape shoot.py reads (one entry per layout, one blueprint per tab).
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import rerun.blueprint as rrb

from traj_compare.analysis import analyze_comparison
from traj_compare.report import _colorize
from traj_compare.rerun_export import APPLICATION_ID, LAYOUTS, _resolvable_videos, layout_blueprint

COMPARISON = "ur5e-target-sim-real"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    example = root / "ur5e-conveyor"

    from traj_integration_tests.ur_compare import sim_to_real

    captured = {}
    sim_to_real.write_comparison_report = lambda comparisons, out, **_: captured.setdefault("all", comparisons) and Path(out)
    with tempfile.TemporaryDirectory() as work:
        sim_to_real.run_ur_sim_to_real(work, fast=False)
    comparison = next(c for c in captured["all"] if c.name == COMPARISON)
    payload = analyze_comparison(comparison)
    _colorize(payload)
    videos = _resolvable_videos(payload, example)
    overlays = [overlay.name for overlay in comparison.overlays
                if (example / "rerun" / f"{COMPARISON}.overlay-{overlay.name}.mp4").is_file()]

    manifest = {}
    (root / "blueprints").mkdir(exist_ok=True)
    for name in LAYOUTS:
        top = layout_blueprint(name, payload, videos, overlays).root_container
        tabs = top if type(top).__name__ == "Tabs" else top.contents[-1]
        shots = []
        for index, tab in enumerate(container.name for container in tabs.contents):
            blueprint = layout_blueprint(name, payload, videos, overlays, tab=tab)
            # paused, so the harness can type the playhead time and get the same frame every time
            paused = rrb.Blueprint(blueprint.root_container, rrb.BlueprintPanel(state="collapsed"),
                                   rrb.SelectionPanel(state="collapsed"),
                                   rrb.TimePanel(state="collapsed", play_state="paused"))
            rbl = root / "blueprints" / f"{name}--{index}.rbl"
            paused.save(APPLICATION_ID, rbl)
            shots.append({"tab": tab, "rbl": str(rbl.relative_to(root))})
        manifest[name] = {"rrd": f"ur5e-conveyor/rerun/{COMPARISON}.rrd", "tabs": shots}
        print(name, [shot["tab"] for shot in shots])
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
