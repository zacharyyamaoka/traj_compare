"""The 3-joint row of the review report's scaling strip: the HTML run view's tabs on the ``3dof`` scaling fixture.

``shoot_html.py`` shoots the 1-, 6- and 46-joint fixtures; this reuses its driver, Playwright, Chrome and
``write_scaling_report`` unchanged and only adds a 3-joint plan: the ``joints`` tab (ranking of 3 bars, 3 rows,
no part selector) and the ``track`` tab. Writes ``<out>/3dof-joints.png`` and ``<out>/3dof-track.png``.
WHY one browser behind one lock, pinned and niced: the robot arm on this host may be powered.

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/navigation_2026-11-19
    flock /tmp/claude-1000/traj-tc-heavy.lock taskset -c 2-5,16,17 nice -n 19 env -u VIRTUAL_ENV ../../.venv/bin/python shoot_3dof.py /home/bam/bam_ws/reports/media/traj-compare-tabs-2026-11-19/html
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shoot_html import CHROME, DRIVER, PLAYWRIGHT, write_scaling_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help="where the PNGs go")
    args = parser.parse_args()
    out = args.out.resolve()
    build = out / "_reports"
    build.mkdir(parents=True, exist_ok=True)
    report = write_scaling_report("3dof", build / "3dof")
    shots = [{"report": str(report), "out": str(out / f"3dof-{tab}.png"), "actions": [{"tab": tab}]} for tab in ("joints", "track")]
    plan = {"width": 1440, "height": 900, "shots": shots}
    (build / "plan-3dof.json").write_text(json.dumps(plan))
    (build / "driver.js").write_text(DRIVER)
    result = subprocess.run(["node", str(build / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(build / "plan-3dof.json")],
                            capture_output=True, text=True, timeout=300)  # fmt: skip
    if result.returncode:
        sys.exit(result.stderr[-3000:])
    for item in json.loads(result.stdout.strip().splitlines()[-1]):
        print(item["out"], "errors:" if item["errors"] else "", *item["errors"])


if __name__ == "__main__":
    main()
