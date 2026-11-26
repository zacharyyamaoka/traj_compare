"""write_trajectory_rrd(robot=…): the workbench's Open in Rerun shows the trajectory as its URDF arm (2026-11-24).

Zach, Daily Note 2026-11-24: "this should basically be the stock trajectory rerun viewer... 100% there should be a urdf
showing". The viewer is robot_msgs.viz.rerun's (``robot=``: the arm on the left, tabs of joint and TCP plots on the
right); this file only checks that the workbench's recordings use it when given a URDF, and stay what they were (the
Trajectory Tracking Agent ships them) when not. Read back with Rerun's own reader.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from robot_msgs.trajectory import JointLimits, JointTrajectory, PoseTrajectory

pytest.importorskip("rerun")

from traj_compare.coverage.workbench import write_trajectory_rrd  # noqa: E402

JOINTS = ("base", "shoulder", "elbow")
URDF = """<?xml version="1.0"?>
<robot name="made_up_arm">
  <link name="root"><visual><geometry><cylinder radius="0.05" length="0.1"/></geometry></visual></link>
  <link name="l1"><visual><origin xyz="0 0 0.15"/><geometry><box size="0.04 0.04 0.3"/></geometry></visual></link>
  <link name="l2"><visual><origin xyz="0 0 0.12"/><geometry><box size="0.03 0.03 0.25"/></geometry></visual></link>
  <link name="l3"><visual><origin xyz="0 0 0.1"/><geometry><box size="0.02 0.02 0.2"/></geometry></visual></link>
  <joint name="base" type="revolute"><parent link="root"/><child link="l1"/><origin xyz="0 0 0.1"/><axis xyz="0 0 1"/>
    <limit lower="-3.2" upper="3.2" effort="5" velocity="3"/></joint>
  <joint name="shoulder" type="revolute"><parent link="l1"/><child link="l2"/><origin xyz="0 0 0.3"/>
    <axis xyz="0 1 0"/><limit lower="-2" upper="2" effort="5" velocity="3"/></joint>
  <joint name="elbow" type="revolute"><parent link="l2"/><child link="l3"/><origin xyz="0 0 0.25"/>
    <axis xyz="0 1 0"/><limit lower="-3.2" upper="3.2" effort="5" velocity="4"/></joint>
</robot>
"""


def move() -> tuple[JointTrajectory, PoseTrajectory]:
    t = np.arange(0.0, 2.0, 0.01)
    q = np.stack([0.8 * np.sin(t), 0.5 * np.sin(1.3 * t), 1.0 * np.cos(t)], 1)
    limits = JointLimits(joint_names=JOINTS, min_position=[-math.pi] * 3, max_position=[math.pi] * 3,
                         max_velocity=[3.0, 3.0, 4.0], max_acceleration=[15.0, 15.0, 20.0])
    joint = JointTrajectory(t=t, joint_names=JOINTS, positions=q, limits=limits)
    tool = PoseTrajectory(t=t, positions=np.stack([0.3 + 0.1 * np.cos(t), 0.1 * np.sin(t), 0.4 + 0 * t], 1),
                          orientations=np.tile([0.0, 0.0, 0.0, 1.0], (len(t), 1)))
    return joint, tool


def read(path: Path) -> tuple[set[str], list, list]:
    from rerun.chunk import RrdReader

    reader = RrdReader(path)
    return {chunk.entity_path for chunk in reader.stream()}, reader.recordings(), reader.blueprints()


def scalars(path: Path, entity: str) -> np.ndarray:
    from rerun.chunk import RrdReader

    values = []
    for chunk in RrdReader(path).stream():
        batch = chunk.to_record_batch()
        if chunk.entity_path == entity and "Scalars:scalars" in batch.schema.names:
            values += [row[0] for row in batch.column("Scalars:scalars").to_pylist() if row]
    return np.asarray(values)


def test_with_robot_the_recording_is_robot_msgs_urdf_viewer(tmp_path):
    urdf = tmp_path / "arm.urdf"
    urdf.write_text(URDF)
    joint, tool = move()
    path = write_trajectory_rrd(tmp_path / "rrd" / "bench" / "move-1.rrd", "bench/move-1", joint, tool=tool, robot=urdf)
    found, recordings, blueprints = read(path)
    part = "bench_move-1"  # robot_msgs' path_part of the name
    assert {f"/world/{part}/robot/joint_transforms/{name}" for name in JOINTS} <= found
    assert f"/world/{part}/ghost_start/joint_transforms/base" in found
    assert f"/tcp/position_mm/{part}" in found and f"/notes/{part}" in found
    np.testing.assert_allclose(scalars(path, f"/positions/shoulder/{part}"), np.degrees(joint.positions[:, 1]))
    # still the workbench's recording: its application id, and the trajectory's name as the recording id (re-opening a
    # trajectory in the viewer replaces it rather than adding a copy)
    assert [(entry.application_id, entry.recording_id) for entry in recordings] == [("traj_compare_coverage",
                                                                                      "bench/move-1")]
    assert blueprints  # the dashboard is in the file, written first


def test_ghosts_false_passes_through_for_web_bundles(tmp_path):
    urdf = tmp_path / "arm.urdf"
    urdf.write_text(URDF)
    joint, tool = move()
    path = write_trajectory_rrd(tmp_path / "a.rrd", "a", joint, tool=tool, robot=urdf, ghosts=False)
    found, _, _ = read(path)
    assert "/world/a/robot/joint_transforms/base" in found
    assert not any("/ghost_" in entity for entity in found)


def test_without_robot_the_recording_is_the_one_the_tracking_agent_ships(tmp_path):
    joint, tool = move()
    path = write_trajectory_rrd(tmp_path / "b.rrd", "b", joint, tool=tool)
    found, recordings, _ = read(path)
    # qddd since 2026-11-26 (Zach: jerk "if it doesn't [have it] ... calculate and display"); added, nothing removed
    expected = ({f"/joints/{signal}/{name}" for signal in ("q", "qd", "qdd", "qddd") for name in JOINTS}
                | {"/tool/path", "/tool/now"})
    assert {entity for entity in found if not entity.startswith("/__")} == expected
    np.testing.assert_allclose(scalars(path, "/joints/q/elbow"), np.degrees(joint.positions[:, 2]))
    assert recordings[0].recording_id == "b"


def test_prismatic_is_for_the_robotless_file_only(tmp_path):
    urdf = tmp_path / "arm.urdf"
    urdf.write_text(URDF)
    joint, _ = move()
    with pytest.raises(ValueError, match="URDF"):
        write_trajectory_rrd(tmp_path / "c.rrd", "c", joint, robot=urdf, prismatic=("elbow",))
