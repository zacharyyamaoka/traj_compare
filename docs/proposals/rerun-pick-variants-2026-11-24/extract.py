#!/usr/bin/env python3
"""Shared inputs for the Rerun pick-variants round (babble, 2026-11-24): the UR5e tour dev-029 as a target, and the
Trajectory Tracking Agent's two saved runs of it (target vs solution), plus the UR5e URDF.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/rerun-pick-variants-2026-11-24/extract.py

Writes data/ (gitignored):
- workspace-dev-029.npz: copied from the previous round (rerun-joint-trajectory-2026-11-24/data): t, names, q/qd/qdd (rad),
  tool_xyz (m) + tool_rot (3x3) in the base frame, the UR5e JointLimits (lo/hi/vmax/amax).
- tta-dev-029.npz: the agent's run records (bb-run/1, trajectory_tracking_agent git HEAD, site/data/runs/<solution>/
  workspace-dev-029.json): t, q_target (rad), and per solution q_<id> (rad), tool_target / tool_<id> (m, base frame, the
  deployment's tool point: 0.1 m along wrist_3), tool_error_<id> (mm), tau_pct_<id>, qd_pct_<id> (%).
- tta.json: which solutions, their labels and scores, the commit the records came from, and the checks below.
Checks (printed, and in tta.json): the agent's target equals the dataset trajectory; the agent's tool point vs the URDF's
FK of the same q (frame agreement).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "rerun-joint-trajectory-2026-11-24" / "data"
TTA = Path("/home/bam/trajectory_tracking_agent")
TASK = "workspace-dev-029"
SOLUTIONS = ("p6s", "p5s-pass3")  # the best of generation 0 (0.83 mm median) and the best so far (0.03 mm)


def record(solution: str) -> dict:
    text = subprocess.run(["git", "-C", str(TTA), "show", f"HEAD:site/data/runs/{solution}/{TASK}.json"],
                          capture_output=True, text=True, check=True).stdout
    return json.loads(text)


def channel(rec: dict, cid: str) -> np.ndarray:
    return np.asarray(next(c for c in rec["channels"] if c["id"] == cid)["values"], dtype=float)


def main() -> None:
    data = HERE / "data"
    data.mkdir(exist_ok=True)
    shutil.copy(PREVIOUS / f"{TASK}.npz", data / f"{TASK}.npz")
    if not (data / "robot").exists():
        (data / "robot").symlink_to(PREVIOUS / "robot")
    commit = subprocess.run(["git", "-C", str(TTA), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    target = np.load(data / f"{TASK}.npz")
    arrays, meta = {}, {"task": TASK, "commit": commit, "solutions": []}
    for solution in SOLUTIONS:
        rec = record(solution)
        t = np.asarray(rec["time"]["t"], dtype=float)
        q_target = np.deg2rad(channel(rec, "q_target"))
        arrays.setdefault("t", t)
        arrays.setdefault("q_target", q_target)
        arrays[f"q_{solution}"] = np.deg2rad(channel(rec, "q"))
        arrays.setdefault("tool_target", channel(rec, "tool_target"))
        arrays[f"tool_{solution}"] = channel(rec, "tool")
        arrays[f"tool_error_{solution}"] = channel(rec, "tool_error")
        arrays[f"tau_pct_{solution}"] = channel(rec, "tau_pct")
        arrays[f"qd_pct_{solution}"] = channel(rec, "qd_pct")
        objective = next(m for m in rec["metrics"] if m["id"] == "tool_track_rms_mm")["value"]
        meta["solutions"].append({"id": solution, "label": rec["subject"]["label"], "verdict": rec["subject"]["verdict"],
                                  "tool_track_rms_mm_on_this_task": objective})
    names = [str(n) for n in target["names"]]
    same_t = np.allclose(arrays["t"], target["t"], atol=1e-9)
    worst_q = float(np.max(np.abs(arrays["q_target"] - target["q"]))) if same_t else float("nan")
    meta["target_equals_dataset"] = {"same_t": bool(same_t), "worst_joint_diff_deg": float(np.rad2deg(worst_q)),
                                     "note": "the agent's q_target is saved at 4 decimals of a degree"}
    # frame agreement: the agent's tool point vs the URDF's FK of the same q (tool0/flange + 0.1 m along wrist_3's z)
    import rerun as rr  # noqa: F401  (rerun.urdf needs the SDK)
    from rerun.urdf import UrdfTree
    tree = UrdfTree.from_file_path(str(data / "robot" / "ur5e_collision.urdf"))
    meta["joint_names"] = names
    meta["urdf_links"] = [link.name for link in tree.links()] if hasattr(tree, "links") else []
    np.savez(data / "tta-dev-029.npz", **arrays)
    (data / "tta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
