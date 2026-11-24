#!/usr/bin/env python3
"""Shared data for the dashboard-pattern round (babble, 2026-11-24): all four UR5e trajectory datasets as one set, so
"dataset" can be the first filter and split (dev / holdout) applies across every dataset ticked.

    env -u VIRTUAL_ENV /home/bam/arm_motion_bench/.venv/bin/python /home/bam/traj_compare/docs/proposals/dashboard-pattern-2026-11-24/extract.py

The four datasets are build_ur_coverage_1123.py's, each at full speed (dev + holdout, rung 1.0): 212 trajectories.
One analyze() over all of them gives one set of grids every dataset shares (the joint grids come from the UR5e's
limits, identical for all four; the tool grids span every dataset's tool and both deployments' reachable clouds), so
any filter of datasets, splits or kinds re-aggregates exactly from membership.json.

Writes data/ (gitignored), the same files as round 2's extract.py (coverage, trajectories, membership as .json + .js,
rrd/<dataset>/<task>.rrd) plus datasets.json, one row per dataset. No samples.json: the per-sample rows of 212
trajectories are ~37 MB, and no proposal in this round needs them (Rerun carries the motion).

Caveat: tool positions are in each deployment's own cell frame. The two cells are different stations, so the tool maps
of the alone-UR5e and the cell UR5e overlay as numbers, not as one physical room. The joint-space maps are directly
comparable (same robot, same limits).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/bam/arm_motion_bench/docs")
import build_ur_coverage_1123 as ur  # noqa: E402
from arm_motion_bench.datasets import load_dataset  # noqa: E402
from robot_msgs.std import Header  # noqa: E402
from robot_msgs.trajectory import PoseTrajectory  # noqa: E402
from traj_compare.coverage import analyze  # noqa: E402
from traj_compare.coverage import analysis as cov  # noqa: E402

HERE = Path(__file__).resolve().parent
ROUND2 = HERE.parent / "coverage-ui-2026-11-24" / "extract.py"
spec = importlib.util.spec_from_file_location("round2_extract", ROUND2)
r2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r2)  # reuse its plane_cells / sphere_cells / write_rrd / check, so both rounds bin alike
r2.OUT = HERE / "data"

# (deployment, dataset, short label for a filter row): short labels because a rail is ~240 px wide
DATASETS = (
    ("ur5e_alone", "workspace", "UR5e alone · Workspace"),
    ("ur5e", "workspace", "Cell · Workspace"),
    ("ur5e", "conveyor", "Cell · Conveyor PnP"),
    ("ur5e", "impact", "Cell · Conveyor Collision"),
)
SPLITS, RUNGS = ("dev", "holdout"), (1.0,)


def main() -> None:
    out = r2.OUT
    out.mkdir(exist_ok=True)
    trajectories, tools, tags, origin, datasets, clouds = {}, {}, {}, {}, [], {}
    for deployment, dataset, label in DATASETS:
        ds = load_dataset(ur.REPO / f"datasets/{deployment}/{dataset}/v2")
        if deployment not in clouds:
            clouds[deployment], _ = ur.reachable_cell(deployment, ds, refresh=False)
        slug = ur.slug(deployment, dataset)
        picked = ur.selection(ds, SPLITS, RUNGS)
        joint, tool, tag = ur.inputs(ds, picked, "cell")
        for name in joint:
            key = f"{slug}/{name}"
            trajectories[key] = joint[name]
            pose = tool[name]
            tools[key] = PoseTrajectory(t=pose.t, positions=pose.positions, orientations=pose.orientations,
                                        header=Header(frame_id="cell"))
            tags[key] = {"dataset": label, **tag[name]}
            origin[key] = (slug, name)
        splits = [tag[name]["split"] for name in joint]
        datasets.append({"dataset": label, "slug": slug, "deployment": deployment, "title": dict(
            (f"{d}-{n}", t) for d, n, t in ur.DATASETS)[slug], "trajectories": len(joint),
            "dev": splits.count("dev"), "holdout": splits.count("holdout")})
        print(f"  {label}: {len(joint)} trajectories")
    reachable = np.vstack(list(clouds.values()))
    coverage = analyze(trajectories, tool=tools, tags=tags, group_by="dataset", reachable=reachable,
                       tool_reference=(0.0, 0.0, -1.0), title="UR5e trajectory datasets",
                       subtitle=f"{len(DATASETS)} datasets · dev + holdout at full speed · {len(trajectories)} trajectories")
    payload = coverage.payload
    joints = [joint["name"] for joint in payload["joints"]]
    names = list(trajectories)

    poses = [tools[name] for name in names]
    samples = cov._tool_samples(poses)
    low, high = cov._tool_bounds(samples, reachable[np.isfinite(reachable).all(axis=1)])
    pixels = {view: cov._grid_cells(samples.path_points, cov.PIXEL_M, low, high, axes)[0]
              for view, axes in cov.PROJECTIONS.items()}
    voxel_cell, voxel_shape = cov._grid_cells(samples.path_points, cov.VOXEL_M, low, high, (0, 1, 2))
    directions = r2.sphere_cells(samples.rotations[:, :, 2])

    membership, rows = {}, []
    for k, name in enumerate(names):
        q, qd, qdd, _ = cov._signals(trajectories[name])
        signals = {"q": q, "qd": qd, "qdd": qdd}
        dense = samples.path_owner == k
        raw = slice(int(samples.starts[k]), int(samples.starts[k + 1]))
        membership[name] = {
            "planes": {joint: {plane: r2.unique(r2.plane_cells(signals, j, payload["planes"][joint][plane]))
                               for plane in payload["planes"][joint]} for j, joint in enumerate(joints)},
            **{view: r2.unique(pixels[view][dense]) for view in pixels},
            "voxels": r2.unique(voxel_cell[dense]),
            "directions": r2.unique(directions[raw]),
        }
        slug, task = origin[name]
        rrd = out / "rrd" / slug / f"{task}.rrd"
        rrd.parent.mkdir(parents=True, exist_ok=True)
        r2.write_rrd(rrd, name, trajectories[name], signals, tools[name], joints)
        position = np.asarray(tools[name].positions, float)
        speed = cov._tool_speed(tools[name])
        z_axis = samples.rotations[raw][:, :, 2]
        tilt = np.degrees(np.arccos(np.clip(z_axis @ np.array([0.0, 0.0, -1.0]), -1.0, 1.0)))
        rows.append({
            **payload["trajectories"][k], "task": task, "dataset_slug": slug,
            "tool_path_m": round(float(np.linalg.norm(np.diff(position, axis=0), axis=1).sum()), 4),
            "tool_speed_max_m_s": round(float(np.nanmax(speed)), 4),
            "tool_z_min_m": round(float(position[:, 2].min()), 4), "tool_z_max_m": round(float(position[:, 2].max()), 4),
            "tool_tilt_max_deg": round(float(tilt.max()), 2), "rrd": f"data/rrd/{slug}/{task}.rrd",
        })
    owners: dict[tuple, list[str]] = {}
    for name in names:
        for joint in joints:
            for cell in membership[name]["planes"][joint]["q_qd"]:
                owners.setdefault((joint, cell), []).append(name)
    for row in rows:
        row["only_it_q_qd_cells"] = sum(1 for who in owners.values() if who == [row["name"]])

    r2.check(payload, membership, names, voxel_shape)
    r2.write("coverage", payload)
    r2.write("trajectories", rows)
    r2.write("membership", {"voxel_shape": voxel_shape, "sphere": [cov.SPHERE_RINGS, cov.SPHERE_SECTORS],
                            "trajectories": membership})
    r2.write("datasets", datasets)
    print(f"  data/rrd/: {len(names)} recordings")


if __name__ == "__main__":
    main()
