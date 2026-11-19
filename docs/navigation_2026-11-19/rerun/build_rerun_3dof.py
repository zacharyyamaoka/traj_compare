"""The 3-joint Rerun recording for the review report's scaling strip (``build_rerun_tabs.py`` writes 1, 6 and 46).

Writes the ``3dof`` scaling fixture (tool + torque on) as ``<out>/3dof.rrd`` in the ``questions`` layout, one .rbl
per shot (the layout opened on the ``joints`` and ``track`` tabs) and a ``manifest.json`` in the format
``docs/layout_proposals_2026-11-19/rerun/shoot_rerun.py`` reads. Kept beside ``build_rerun_tabs.py``, not inside it,
so that script's recordings and shot list stay as they were; ``<out>`` is its own folder for the same reason.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/navigation_2026-11-19/rerun
    env -u VIRTUAL_ENV ../../../.venv/bin/python build_rerun_3dof.py --out ~/bam_ws/reports/media/traj-compare-tabs-2026-11-19/rerun/3dof
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_rerun_tabs import (  # noqa: E402 - also puts the acceptance fixtures on the path
    APPLICATION_ID,
    PLAYHEAD_S,
    _colorize,
    analyze_comparison,
    layout_blueprint,
    scaling_comparison,
    write_rrd,
)

SHOTS = [("3dof", "joints", "w1440"), ("3dof", "track", "w1440")]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    (out / "rbl").mkdir(parents=True, exist_ok=True)
    comparison = scaling_comparison("3dof", tool=True, torque=True)
    payload = analyze_comparison(comparison)
    _colorize(payload)
    rrd = write_rrd(comparison, out / "3dof.rrd", layout="questions", payload=payload)
    manifest = {"t_worst": PLAYHEAD_S, "variants": {"3dof": {"rrd": rrd.name, "tabs": [tab["title"] for tab in payload["tabs"]]}},
                "shots": []}  # fmt: skip
    for shape, tab_id, width in SHOTS:
        rbl = out / "rbl" / f"{shape}--{width}-{tab_id}.rbl"
        layout_blueprint("questions", payload, {}, tab=tab_id).save(APPLICATION_ID, rbl)
        manifest["shots"].append({"slug": shape, "shot": f"{width}-{tab_id}", "rbl": f"rbl/{rbl.name}", "at": PLAYHEAD_S})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(out / "manifest.json")


if __name__ == "__main__":
    main()
