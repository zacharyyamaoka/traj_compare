"""The Rerun projection carries the second wave: contour, lag time, errors along named axes, notes.

Read back through Rerun's own CLI (`rrd verify` / `rrd print`), as test_rerun_export.py does.
"""

import subprocess
import sys

import numpy as np
import pytest

from traj_compare.analysis import analyze_comparison
from traj_compare.rerun_export import _notes_markdown, write_rrd

pytest.importorskip("rerun")

from test_wave2_viewer import BELT, comparison, tcp_tolerances, tolerances  # noqa: E402


def rrd_print(path) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "rerun", "rrd", "print", "-v", str(path)],
        capture_output=True, text=True, check=True, timeout=120,
    )  # fmt: skip
    return result.stdout + result.stderr


def test_wave2_channels_and_notes_are_in_the_recording(tmp_path):
    full = comparison(
        tolerances=tolerances(),
        tcp_tolerances=tcp_tolerances(),
        estimate_latency=True,
        goal_band=0.002,
        tcp_goal_band=0.002,
        error_axes=[("along belt", BELT), ("up", np.array([0.0, 0.0, 1.0]))],
        repeat_groups={"Real ×3": ["real_1", "real_2", "real_3"]},
    )
    path = write_rrd(full, tmp_path / "belt.rrd")
    verify = subprocess.run(
        [sys.executable, "-m", "rerun", "rrd", "verify", str(path)],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert verify.returncode == 0, verify.stdout + verify.stderr

    printed = rrd_print(path)
    for entity in (
        "/error/tool/contour_mm/real_1",
        "/error/tool/lag_time_ms/real_1",
        "/error/axes/along_belt_mm/real_1",  # one spelling with robot_msgs.viz.rerun.path_part: a space becomes _
        "/error/axes/up_mm/real_1",
    ):
        assert entity in printed, f"{entity} missing"
    assert "/notes" in printed
    # WHY the markdown function, not the printout: `rrd print` lists columns, not document text.
    notes = _notes_markdown(analyze_comparison(full))
    for text in ("## Verdicts", "PATH_TOLERANCE_VIOLATED", "## Estimated latency", "## Goal", "ISO 9283"):
        assert text in notes, f"{text!r} missing from /notes"
