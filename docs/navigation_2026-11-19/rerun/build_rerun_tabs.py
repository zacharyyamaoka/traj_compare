"""The Rerun ``questions`` layout on the shared question tabs (NAVIGATION.md Part B) — recordings + shot list, 2026-11-19.

Writes the 1-, 6- and 46-joint acceptance fixtures (``tests/scaling_fixtures.py``, tool + torque on) as .rrd with
every layout's .rbl beside it, plus one .rbl per screenshot: the ``questions`` layout opened on one tab (and, for the
46-joint recording, on one part of a per-joint tab). ``manifest.json`` lists the shots in the format
``docs/layout_proposals_2026-11-19/rerun/shoot_rerun.py`` reads; shot names carry their viewport (``w1440`` /
``w1920``) so each width is one ``--only`` run of the shooter.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare
    env -u VIRTUAL_ENV .venv/bin/python docs/navigation_2026-11-19/rerun/build_rerun_tabs.py --out ~/bam_ws/reports/media/traj-compare-tabs-2026-11-19/rerun
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PACKAGE / "tests"))  # the acceptance fixtures live with the tests

from scaling_fixtures import scaling_comparison  # noqa: E402
from traj_compare.analysis import analyze_comparison  # noqa: E402
from traj_compare.report import _colorize  # noqa: E402
from traj_compare.rerun_export import APPLICATION_ID, layout_blueprint, write_rrd  # noqa: E402

PLAYHEAD_S = 1.2  # mid-motion in every fixture: the arms are out and the fingers are curling
# (fixture, tab id, part index or None, viewport): every tab of the 6-joint arm, the 1-joint pivot's tabs,
# and the 46-motor robot's per-joint tabs on a hand part (plus one arm part for the joints tab).
SHOTS = [
    *[("1dof", tab, None, "w1440") for tab in ("track", "where", "timing", "torque", "signals")],
    *[("6dof", tab, None, "w1440") for tab in ("track", "where", "joints", "timing", "torque", "signals")],
    ("bimanual", "joints", 2, "w1440"),
    ("bimanual", "joints", 0, "w1440"),
    ("bimanual", "torque", 2, "w1440"),
    ("bimanual", "signals", 3, "w1440"),
    ("6dof", "track", None, "w1920"),
    ("bimanual", "joints", 2, "w1920"),
]


def _tab_container(blueprint, title: str):
    questions = blueprint.root_container.contents[1]  # beside the stage
    return next(child for child in questions.contents if child.name == title)


def _open_part(container, index: int) -> None:
    """Open part ``index`` in the per-joint tab: the nested Tabs whose children are the ``<part> · <n> joints`` tabs."""

    stack = [container]
    while stack:
        node = stack.pop(0)
        if type(node).__name__ == "Tabs" and all(" · " in (child.name or "") for child in node.contents):
            node.active_tab = index
            return
        stack += [child for child in getattr(node, "contents", None) or [] if hasattr(child, "contents")]
    raise ValueError("no part tabs here")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    (out / "rbl").mkdir(parents=True, exist_ok=True)
    manifest = {"t_worst": PLAYHEAD_S, "variants": {}, "shots": []}
    payloads = {}
    for shape in sorted({shape for shape, *_ in SHOTS}):
        comparison = scaling_comparison(shape, tool=True, torque=True)
        payload = analyze_comparison(comparison)
        _colorize(payload)
        payloads[shape] = payload
        rrd = write_rrd(comparison, out / f"{shape}.rrd", layout="questions", payload=payload)
        manifest["variants"][shape] = {"rrd": rrd.name, "tabs": [tab["title"] for tab in payload["tabs"]]}
    for shape, tab_id, part, width in SHOTS:
        payload = payloads[shape]
        blueprint = layout_blueprint("questions", payload, {}, tab=tab_id)
        shot = f"{width}-{tab_id}" + (f"-part{part}" if part is not None else "")
        if part is not None:
            title = next(tab["title"] for tab in payload["tabs"] if tab["id"] == tab_id)
            _open_part(_tab_container(blueprint, title), part)
        rbl = out / "rbl" / f"{shape}--{shot}.rbl"
        blueprint.save(APPLICATION_ID, rbl)
        manifest["shots"].append({"slug": shape, "shot": shot, "rbl": f"rbl/{rbl.name}", "at": PLAYHEAD_S})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(out / "manifest.json")


if __name__ == "__main__":
    main()
