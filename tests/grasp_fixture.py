"""A made-up grasp set for the grasp coverage tests (docs/GRASP_COVERAGE.md): three objects, every outcome, one grasp
past the jaw range, top-down, tilted and side grasps, in one frame "base" (z up), with an offered pick area.

Each grasp is built from (position, approach tilt + azimuth, roll, width) so a test knows the angles it must get back:
rotation = swing(reference -> approach) @ R0 @ Rz(-roll), where R0 is the reference grasp (jaws along +x, approach
straight down) and Rz(-roll) about the tool +z turns the jaws counter-clockwise as seen from behind the gripper.
"""

from __future__ import annotations

import math

import numpy as np
from robot_msgs.geometry import Point, Pose, Quaternion
from robot_msgs.manipulation import GraspPose
from robot_msgs.std import Header
from scipy.spatial.transform import Rotation

REFERENCE = np.array([0.0, 0.0, -1.0])
R0 = Rotation.from_rotvec([math.pi, 0.0, 0.0])  # tool x = +x, tool z = -z (straight down), tool y = -y
WIDTH_RANGE = (0.0, 0.12)
PLANNER_RANGE = (0.0, 0.07)
AREA = ((-0.45, -0.05, -0.70), (-0.35, 0.05, -0.60))  # a 10 x 10 cm look area on a belt below the base
OUTCOMES = ("picked", "picked", "failed", "hovered", "refused", None)


def approach_vector(tilt: float, azimuth: float) -> np.ndarray:
    """The approach tilted `tilt` from straight down, leaning toward `azimuth` in base XY."""
    return np.array([math.sin(tilt) * math.cos(azimuth), math.sin(tilt) * math.sin(azimuth), -math.cos(tilt)])


def swing(approach: np.ndarray) -> Rotation:
    axis = np.cross(REFERENCE, approach)
    s, c = np.linalg.norm(axis), float(REFERENCE @ approach)
    if s < 1e-12:
        return Rotation.identity() if c > 0 else Rotation.from_rotvec([math.pi, 0.0, 0.0])
    return Rotation.from_rotvec(axis / s * math.atan2(s, c))


def grasp_rotation(tilt: float, azimuth: float, roll: float) -> np.ndarray:
    return (swing(approach_vector(tilt, azimuth)) * R0 * Rotation.from_rotvec([0.0, 0.0, -roll])).as_matrix()


def grasp(position, tilt, azimuth, roll, width, *, pre=None, score=None, object_id="", frame="base", name=None):
    quat = Rotation.from_matrix(grasp_rotation(tilt, azimuth, roll)).as_quat()  # x, y, z, w
    header = Header(frame_id=frame, meta={"name": name} if name else {})
    return GraspPose(pose=Pose(position=Point(*position), orientation=Quaternion(*quat)), width=width,
                     pre_grasp_width=pre, score=score, object_id=object_id, header=header)


def made_up() -> tuple[dict, list, dict, dict]:
    """(grasps by name, outcomes in order, tags by name, truth by name: tilt, azimuth, roll, width, position)."""
    rng = np.random.default_rng(3)
    grasps, outcomes, tags, truth = {}, [], {}, {}
    plan = [("vial", 18, 0.0), ("cap", 9, math.radians(32)), ("box", 5, math.radians(87))]
    k = 0
    for object_id, count, tilt in plan:
        for i in range(count):
            position = (rng.uniform(-0.44, -0.36), rng.uniform(-0.04, 0.04), rng.uniform(-0.69, -0.61))
            azimuth = rng.uniform(-math.pi, math.pi)
            roll = rng.uniform(-math.pi, math.pi)
            width = rng.uniform(0.01, 0.06)
            name = f"{object_id}-{i + 1:02d}"
            pre = width + 0.02 if i % 2 == 0 else None
            grasps[name] = grasp(position, tilt, azimuth, roll, width, pre=pre,
                                 score=float(rng.uniform(0.2, 0.9)) if object_id != "box" else None, object_id=object_id)
            outcomes.append(OUTCOMES[k % len(OUTCOMES)])
            tags[name] = {"run": f"run-{k // 4:02d}", "day": "2026-11-12" if k < 16 else "2026-11-14"}
            truth[name] = {"tilt": tilt, "azimuth": azimuth, "roll": roll, "width": width, "position": position}
            k += 1
    # one grasp outside the range and outside the area, straight down, jaws along +y (0.01 rad off: not on a bin edge)
    # WHY 32 and 87 degrees above, not 30 and 90: those sit exactly on a 5 degree bin edge
    grasps["wide-01"] = grasp((-0.30, 0.10, -0.65), 0.0, 0.0, math.pi / 2 + 0.01, 0.135, object_id="vial")
    outcomes.append("failed")
    tags["wide-01"] = {"run": "run-09", "day": "2026-11-14"}
    truth["wide-01"] = {"tilt": 0.0, "azimuth": 0.0, "roll": math.pi / 2 + 0.01, "width": 0.135,
                        "position": (-0.30, 0.10, -0.65)}
    return grasps, outcomes, tags, truth
