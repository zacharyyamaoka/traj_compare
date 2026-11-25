"""Open the grasp coverage viewer on the real grasps: the workbench (our repicks, the GraspNet page beside it) and the
Viser 3-D view, until Ctrl-C (2026-11-24).

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/grasp_coverage_2026-11-24/demo.py

Starts traj_compare.serve over reports/media/grasp-coverage-2026-11-24 (built by build_real.py) and the Viser view of
the repicks payload, each on a free loopback port, opens the workbench in the browser (/home/bam/.local/bin/open, which
detaches), prints both URLs and stops both on Ctrl-C. WHY one script: two servers behind one Run button.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent.parent
SITES = PACKAGE / "reports" / "media" / "grasp-coverage-2026-11-24"
OPEN = "/home/bam/.local/bin/open"


def main() -> None:
    sys.path.insert(0, str(PACKAGE / "src"))
    from traj_compare.grasp_coverage.viser_view import serve_grasp_coverage

    if not (SITES / "repicks" / "site" / "index.html").is_file():
        raise SystemExit(f"no workbench at {SITES}; build it first: {sys.executable} "
                         f"{PACKAGE / 'docs/grasp_coverage_2026-11-24/build_real.py'}")
    server = subprocess.Popen([sys.executable, "-m", "traj_compare.serve", str(SITES), "--port", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    viewer = None
    try:
        base = server.stdout.readline().split(" on ", 1)[1].split()[0].rstrip("/")
        viewer = serve_grasp_coverage(json.loads((SITES / "repicks" / "grasp_coverage.json").read_text("utf-8")))
        page = f"{base}/repicks/site/index.html"
        print(f"workbench  {page}\n           {base}/graspnet/site/index.html  (the GraspNet-1Billion labels)\n"
              f"viser      {viewer.url}\nCtrl-C stops both.", flush=True)
        subprocess.run([OPEN, page], check=False)
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if viewer is not None:
            viewer.stop()
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
