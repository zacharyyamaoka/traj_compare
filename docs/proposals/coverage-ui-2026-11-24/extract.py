#!/usr/bin/env python3
"""Shared data for the coverage-UI proposals (babble round 2026-11-24): the UR5e Entire Workspace, dev + holdout at
full speed, the same 54 trajectories the live coverage page draws.

    env -u VIRTUAL_ENV /home/bam/arm_motion_bench/.venv/bin/python /home/bam/traj_compare/docs/proposals/coverage-ui-2026-11-24/extract.py

Writes data/ (gitignored, regenerated here):

    coverage.json / coverage.js     the traj_compare.coverage/1 payload, exactly as analyze() returns it
    trajectories.json / .js         one row per trajectory: its tags, the payload's per-trajectory numbers, a few
                                    tool numbers, and `rrd`, its Rerun recording (path relative to the round's folder)
    membership.json / .js           which cells each trajectory visits, on the payload's own grids:
                                      planes[joint][plane]  flat cell (x_bin * ny + y_bin), the payload's planes
                                      xy / xz / yz          flat pixel (row-major over the payload's projection shape)
                                      voxels                flat voxel (row-major over voxel_shape)
                                      directions            flat sphere cell (ring * sectors + sector)
    samples.json                    every sample as one row (degrees, mm, m/s), for data-ui's Vega-Lite charts
    rrd/<name>.rrd                  per trajectory: q / qd / qdd per joint (deg) on its own clock, and the tool path

A `.js` twin sets `window.COVERAGE_UI.<name>` so a page opened from file:// can load it with <script src>.

Nothing is invented: membership uses analysis.py's own bin functions on the same inputs as build_ur_coverage_1123.py,
and the script asserts that every grid's per-cell trajectory count rebuilt from membership equals the payload's
`paths` (planes, projections, voxels) and its sample counts (sphere).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/bam/arm_motion_bench/docs")
import build_ur_coverage_1123 as ur  # noqa: E402
from arm_motion_bench.datasets import load_dataset  # noqa: E402
from traj_compare.coverage import analyze  # noqa: E402
from traj_compare.coverage import analysis as cov  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "data"
DEPLOYMENT, DATASET, TITLE = "ur5e_alone", "workspace", "UR5e · Entire Workspace"
SUBSET_LABEL, SPLITS, RUNGS, GROUP_BY = "Dev + holdout at full speed", ("dev", "holdout"), (1.0,), "split"
DEG = 180.0 / math.pi


def write(name: str, value, js: bool = True) -> None:
    text = json.dumps(value, separators=(",", ":"), allow_nan=False)
    (OUT / f"{name}.json").write_text(text, encoding="utf-8")
    if js:
        (OUT / f"{name}.js").write_text(f"window.COVERAGE_UI=window.COVERAGE_UI||{{}};window.COVERAGE_UI.{name}={text};\n",
                                        encoding="utf-8")
    print(f"  data/{name}.json  {len(text) / 1e6:.2f} MB")


def unique(values: np.ndarray) -> list[int]:
    return [int(v) for v in np.unique(values[values >= 0])]


def plane_cells(signals: dict, j: int, plane: dict) -> np.ndarray:
    x_low, x_high, nx = plane["x_edges"]
    y_low, y_high, ny = plane["y_edges"]
    xi = cov._bin_index(signals[plane["x"]][:, j], x_low, x_high, nx)
    yi = cov._bin_index(signals[plane["y"]][:, j], y_low, y_high, ny)
    inside = (xi >= 0) & (yi >= 0)
    return np.where(inside, xi * ny + yi, -1)


def sphere_cells(z_axis: np.ndarray) -> np.ndarray:
    rings, sectors = cov.SPHERE_RINGS, cov.SPHERE_SECTORS
    ring = np.clip(np.floor((z_axis[:, 2] + 1.0) / 2.0 * rings), 0, rings - 1).astype(np.int64)
    azimuth = np.arctan2(z_axis[:, 1], z_axis[:, 0])
    sector = np.clip(np.floor((azimuth + math.pi) / (2 * math.pi) * sectors), 0, sectors - 1).astype(np.int64)
    return ring * sectors + sector


def write_rrd(path: Path, name: str, trajectory, signals: dict, tool, joints: list[str]) -> None:
    import rerun as rr

    rec = rr.RecordingStream("coverage_ui_2026_11_24", recording_id=name)
    rec.save(str(path))
    t = np.asarray(trajectory.t, float) - float(trajectory.t[0])
    times = [rr.TimeColumn("t", duration=t)]
    for signal, unit in (("q", "deg"), ("qd", "deg/s"), ("qdd", "deg/s²")):
        for j, joint in enumerate(joints):
            rec.send_columns(f"joints/{signal}/{joint}", indexes=times,
                             columns=rr.Scalars.columns(scalars=signals[signal][:, j] * DEG))
    positions = np.asarray(tool.positions, float)
    rec.log("tool/path", rr.LineStrips3D([positions], colors=[[120, 120, 120]], radii=[0.002]), static=True)
    rec.send_columns("tool/now", indexes=times,
                     columns=rr.Points3D.columns(positions=positions).partition([1] * len(positions)))
    rec.flush()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "rrd").mkdir(exist_ok=True)
    ds = load_dataset(ur.REPO / f"datasets/{DEPLOYMENT}/{DATASET}/v2")
    reachable, _ = ur.reachable_cell(DEPLOYMENT, ds, refresh=False)
    picked = ur.selection(ds, SPLITS, RUNGS)
    trajectories, tools, tags = ur.inputs(ds, picked, "cell")
    coverage = analyze(trajectories, tool=tools, tags=tags, group_by=GROUP_BY, reachable=reachable,
                       tool_reference=(0.0, 0.0, -1.0), title=TITLE, subtitle=ur.subtitle(SUBSET_LABEL, picked))
    payload = coverage.payload
    joints = [joint["name"] for joint in payload["joints"]]
    names = list(trajectories)
    assert [row["name"] for row in payload["trajectories"]] == names

    # the tool grids exactly as analysis.py builds them (same low/high, same densified polylines)
    poses = [tools[name] for name in names]
    samples = cov._tool_samples(poses)
    reach = np.asarray(reachable, float).reshape(-1, 3)
    low, high = cov._tool_bounds(samples, reach[np.isfinite(reach).all(axis=1)])
    pixels = {view: cov._grid_cells(samples.path_points, cov.PIXEL_M, low, high, axes)[0]
              for view, axes in cov.PROJECTIONS.items()}
    voxel_cell, voxel_shape = cov._grid_cells(samples.path_points, cov.VOXEL_M, low, high, (0, 1, 2))
    directions = sphere_cells(samples.rotations[:, :, 2])

    membership, rows, sample_rows = {}, [], []
    for k, name in enumerate(names):
        trajectory = trajectories[name]
        q, qd, qdd, _ = cov._signals(trajectory)
        signals = {"q": q, "qd": qd, "qdd": qdd}
        dense = samples.path_owner == k
        raw = slice(int(samples.starts[k]), int(samples.starts[k + 1]))
        membership[name] = {
            "planes": {joint: {plane: unique(plane_cells(signals, j, payload["planes"][joint][plane]))
                               for plane in payload["planes"][joint]} for j, joint in enumerate(joints)},
            **{view: unique(pixels[view][dense]) for view in pixels},
            "voxels": unique(voxel_cell[dense]),
            "directions": unique(directions[raw]),
        }
        rrd = OUT / "rrd" / f"{name}.rrd"
        write_rrd(rrd, name, trajectory, signals, tools[name], joints)

        position = np.asarray(tools[name].positions, float)
        speed = cov._tool_speed(tools[name])
        z_axis = samples.rotations[raw][:, :, 2]
        x_axis = samples.rotations[raw][:, :, 0]
        tilt = np.degrees(np.arccos(np.clip(z_axis @ np.array([0.0, 0.0, -1.0]), -1.0, 1.0)))
        azimuth = np.degrees(np.arctan2(z_axis[:, 1], z_axis[:, 0]))
        yaw = np.degrees(np.arctan2(x_axis[:, 1], x_axis[:, 0]))
        base = payload["trajectories"][k]
        rows.append({
            **base,
            "tool_path_m": round(float(np.linalg.norm(np.diff(position, axis=0), axis=1).sum()), 4),
            "tool_speed_max_m_s": round(float(np.nanmax(speed)), 4),
            "tool_z_min_m": round(float(position[:, 2].min()), 4),
            "tool_z_max_m": round(float(position[:, 2].max()), 4),
            "tool_tilt_max_deg": round(float(tilt.max()), 2),
            "rrd": f"data/rrd/{name}.rrd",
        })
        t = np.asarray(trajectory.t, float) - float(trajectory.t[0])
        for i in range(len(t)):
            row = {"trajectory": name, **{key: str(value) for key, value in base["tags"].items()},
                   "t_s": round(float(t[i]), 4)}
            for j, joint in enumerate(joints):
                short = joint.removesuffix("_joint")
                row[f"{short}_q_deg"] = round(float(q[i, j] * DEG), 3)
                row[f"{short}_qd_deg_s"] = round(float(qd[i, j] * DEG), 3)
                row[f"{short}_qdd_deg_s2"] = round(float(qdd[i, j] * DEG), 2)
            row.update({"x_mm": round(float(position[i, 0] * 1000), 2), "y_mm": round(float(position[i, 1] * 1000), 2),
                        "z_mm": round(float(position[i, 2] * 1000), 2), "tool_speed_m_s": round(float(speed[i]), 4),
                        "tilt_deg": round(float(tilt[i]), 2), "azimuth_deg": round(float(azimuth[i]), 2),
                        "yaw_deg": round(float(yaw[i]), 2)})
            sample_rows.append(row)

    # cells only one trajectory visits (q x qd, all joints): a trajectory you could not drop without losing coverage
    owners: dict[tuple, list[str]] = {}
    for name in names:
        for joint in joints:
            for cell in membership[name]["planes"][joint]["q_qd"]:
                owners.setdefault((joint, cell), []).append(name)
    for row in rows:
        row["only_it_q_qd_cells"] = sum(1 for who in owners.values() if who == [row["name"]])

    check(payload, membership, names, voxel_shape)
    write("coverage", payload)
    write("trajectories", rows)
    write("membership", {"voxel_shape": voxel_shape, "sphere": [cov.SPHERE_RINGS, cov.SPHERE_SECTORS],
                         "trajectories": membership})
    write("samples", sample_rows, js=False)
    print(f"  data/rrd/: {len(names)} recordings")


def check(payload: dict, membership: dict, names: list[str], voxel_shape: list[int]) -> None:
    """Rebuild each grid's trajectories-per-cell from membership and compare with the payload: the oracle."""
    for joint, planes in payload["planes"].items():
        for plane, block in planes.items():
            rebuilt = np.zeros(len(block["paths"]), int)
            for name in names:
                rebuilt[membership[name]["planes"][joint][plane]] += 1
            assert rebuilt.tolist() == block["paths"], f"{joint} {plane}: membership != payload paths"
    for view, block in payload["tool"]["projections"].items():
        rebuilt = np.zeros(len(block["paths"]), int)
        for name in names:
            rebuilt[membership[name][view]] += 1
        assert rebuilt.tolist() == block["paths"], f"{view}: membership != payload paths"
    voxels = {}
    for name in names:
        for cell in membership[name]["voxels"]:
            voxels[cell] = voxels.get(cell, 0) + 1
    payload_voxels = {int(np.ravel_multi_index((c[0], c[1], c[2]), voxel_shape)): c[4]
                      for c in payload["tool"]["voxels"]["cells"]}
    assert voxels == payload_voxels, "voxels: membership != payload paths"
    visited = {cell for name in names for cell in membership[name]["directions"]}
    payload_visited = {i for i, n in enumerate(payload["tool"]["orientation"]["sphere"]["counts"]) if n > 0}
    assert visited == payload_visited, "directions: membership != payload sphere"
    print("  oracle: every grid's per-cell trajectory count rebuilt from membership equals the payload")


if __name__ == "__main__":
    main()
