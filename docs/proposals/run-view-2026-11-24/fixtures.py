#!/usr/bin/env python3
"""The round's two real fixtures, as the payload ``traj_compare.write_comparison_report`` embeds (same code path:
``analyze_comparison`` → ``_colorize`` → ``_share_robot_meshes``), written to ``data/<name>.js`` (gitignored, > 1 MB).

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/run-view-2026-11-24/fixtures.py

- ``tta``    — the Trajectory Tracking Agent's workspace-dev-000 · ISO 9283 path (Zach's screenshot): Target + p5s-pass3 +
  p6s, built exactly as ``trajectory_tracking_agent/tools/build_dropins.py`` ``comparison_stage`` builds its run level,
  from its ``outputs/dropins/inputs/`` (the same npz, the same capsule arm on p5s-pass3, the same statistics table).
- ``bam_fb`` — arm_motion_bench BAM FB, workspace-dev-000 · workspace-v2 · 1 × reference motion speed (115 deg/s): every
  line the target view lists for it (17: 16 sim + 1 real, 8 configs, repeats r0-r2), each run folder's manifest + npz
  read as ``traj_compare.dataset._build_run_report`` reads them, put in ONE comparison (one situation per line, the
  bench's config colour, grouped by config). Situation names are ``L<line>``: the target view's ``keep=`` indices.

``comparison(name, keep=None)`` gives the ``Comparison`` itself (``serve.py`` writes the Rerun recording from it).
"""

from __future__ import annotations

import functools
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TTA = Path("/home/bam/trajectory_tracking_agent")
BENCH = Path("/home/bam/arm_motion_bench/reports/media/dashboard")
V2 = HERE.parent / "tensorboard-2026-11-24"  # the target view this viewer is opened from (V2's common/target.html)
BAM_FB_TARGET = "workspace-dev-000-workspace-v2-1-reference-motion-speed-115-deg-s"
# WHY 600 (prototype only): 18 posed arms x 2000 poses (traj_compare's MAX_ROBOT_TRACK_POINTS) was 30+ MB of JSON;
# 600 poses over a 4-6 s motion is still every 10 ms or finer. Production keeps its own constant.
BAM_FB_ROBOT_POSES = 600

FIXTURES = ("tta", "bam_fb")


def _tta_module() -> Any:
    sys.path.insert(0, str(TTA / "tools"))
    spec = importlib.util.spec_from_file_location("tta_build_dropins", TTA / "tools" / "build_dropins.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _site_model(site: str) -> dict[str, Any]:
    text = (V2 / "data" / f"{site}.js").read_text(encoding="utf-8")
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


@functools.lru_cache(maxsize=None)
def _tta() -> tuple[Any, dict[str, Any]]:
    """build_dropins.comparison_stage's run level, for workspace-dev-000 only (its code, its inputs)."""
    from robot_msgs import load_npz
    from traj_compare import Comparison, RobotDisplay, Situation

    tta = _tta_module()
    inputs = tta.INPUTS
    manifest = json.loads((inputs / "manifest.json").read_text())
    joints = tuple(manifest["joint_names"])
    titles = {s["id"]: f"{s['id']} ({s['role']})" if s["role"] else s["id"] for s in manifest["solutions"]}
    task = next(task for task in manifest["tasks"] if task["id"] == "workspace-dev-000")
    with np.load(inputs / manifest["robot"]["meshes"]) as stored:
        meshes = [stored[f"m{i}"] for i in range(len(stored.files))]
    data = dict(np.load(inputs / f"{task['id']}.npz"))
    tape = load_npz(TTA / task["tape"])
    if "moving" not in data:  # inputs prepared before build_dropins saved it: the ruler's own mask, as prepare() makes it
        sys.path.insert(0, str(TTA / "src"))
        from trajectory_tracking_agent.ruler.metrics import moving_mask

        data["moving"] = moving_mask(tape.t, data["target_pose"][:, :3, 3], tape.velocities)
    target = Situation(name="target", title="Target (the frozen tape)", t=tape.t, q=tape.positions,
                       qd=tape.velocities, qdd=tape.accelerations, poses=data["target_pose"])
    situations = []
    for situation in task["situations"]:
        sid = situation["id"]
        robot = None
        if sid == manifest["robot"]["situation"]:
            q = data[f"{sid}__q"]
            links = data[f"{sid}__links"]
            by_row = {np.ascontiguousarray(row, dtype=np.float64).tobytes(): i for i, row in enumerate(q)}

            def link_fk(rows, links=links, by_row=by_row):
                rows = np.ascontiguousarray(np.asarray(rows, dtype=np.float64))
                return links[[by_row[row.tobytes()] for row in rows]]

            robot = RobotDisplay(link_names=list(manifest["robot"]["links"]), link_meshes=meshes,
                                 link_fk=link_fk, name="UR5e (the deployment's capsules)")
        situations.append(Situation(name=sid, title=titles[sid], t=data["t"], q=data[f"{sid}__q"],
                                    tau=data[f"{sid}__tau"], poses=data[f"{sid}__pose"], robot=robot,
                                    note=situation["record"]))
    comparison = Comparison(
        title=task["title"], name=task["id"], joint_names=list(joints), target=target, situations=situations,
        tcp_frame=manifest["tcp_frame"], vec_dirs=[],
        stats_mask=data["moving"], stats_mask_label="moving samples", statistics=tta._stats_table(task, titles),
        description=(f"Target: {task['tape']} (the frozen dataset). Runs: the saved records tta evaluate wrote. "
                     "Errors are Target − run."),
    )
    meta = {
        "name": "tta",
        "fixture": "Trajectory Tracking Agent · workspace-dev-000 · ISO 9283 path",
        "deployment": "UR5e (ur5e_alone) · workspace/v2 · dev",
        "target": task["title"],
        "target_view": "/tta/index.html#/target/" + _tta_target_slug(task["id"]),
        "target_view_label": "Comparison: all 42 tasks › " + task["title"],
        "lines": {sid: sid for sid in titles},
        "rerun_note": "",
    }
    return comparison, meta


def _tta_target_slug(task_id: str) -> str:
    page = (TTA / "site" / "comparison" / "index.html").read_text()
    for match in __import__("re").finditer(r'"slug":"([^"]+)"', page):
        if match.group(1).startswith(task_id):
            return match.group(1)
    return task_id


@functools.lru_cache(maxsize=None)
def _bam_fb() -> tuple[Any, dict[str, Any]]:
    """Every line of one BAM FB target, read as the drill-down reads a run folder, in one comparison."""
    from robot_msgs import load_npz
    from traj_compare import Comparison, Signal, Situation
    from traj_compare.dataset import _import_spec, _torque_file

    site = "bam_fb"
    model = _site_model(site)
    lines = model["lines"]
    target_index = model["targets"]["slug"].index(BAM_FB_TARGET)
    picked = [i for i, t in enumerate(lines["target"]) if t == target_index]
    reference = None
    situations: list[Situation] = []
    robot = poses = None
    signals: dict[str, Signal] = {}
    line_names: dict[str, int] = {}
    for line in picked:
        folder = BENCH / site / "runs" / lines["report"][line]
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        series = model["series"][lines["series"][line]]
        if robot is None:
            robot = _import_spec(manifest["robot"], manifest["import_roots"])()
            poses = _import_spec(manifest["poses"], manifest["import_roots"])
            signals = {str(n): Signal(title=e.get("title", ""), unit=e.get("unit", ""), columns=tuple(e.get("columns", ())),
                                      per_joint=bool(e.get("per_joint", False))) for n, e in (manifest.get("signals") or {}).items()}
        if reference is None:
            reference = load_npz(folder / manifest["files"]["reference"])
        trajectory = load_npz(folder / manifest["files"][series])
        columns = [list(trajectory.joint_names).index(j) for j in reference.joint_names]
        breakdown: dict[str, np.ndarray] = {}
        keys = manifest.get("torques", {}).get(series, [])
        if keys:
            with np.load(folder / _torque_file(series), allow_pickle=False) as stored:
                breakdown = {k: stored[k][:, columns] for k in keys}
        origin = float(reference.header.stamp)
        trajectory = trajectory.select(reference.joint_names)
        config = model["configs"][lines["config"][line]]
        name = f"L{line}"
        line_names[name] = line
        situations.append(Situation(
            name=name,
            title=f"{config['name']} · r{lines['repeat'][line]} · {series}",
            t=trajectory.absolute_times - origin,
            q=trajectory.positions, qd=trajectory.velocities, qdd=trajectory.accelerations, tau=trajectory.effort,
            **breakdown,
            poses=poses(trajectory).matrices(),
            group=config["name"], group_title=config["name"],
            meta={"config": config["name"], "color": config["color"], "repeat": lines["repeat"][line], "series": series,
                  "line": line, "report": lines["report"][line]},
        ))
    ref = reference.select(reference.joint_names)
    target = Situation(name="target", title="Target", t=ref.absolute_times - float(ref.header.stamp), q=ref.positions,
                       qd=ref.velocities, qdd=ref.accelerations, poses=poses(ref).matrices())
    title = model["targets"]["title"][target_index]
    comparison = Comparison(
        title=title, name="bam-fb-workspace-dev-000", joint_names=list(reference.joint_names), target=target,
        situations=situations, robot=robot, tcp_frame=poses(ref).child_frame_id or "TCP", estimate_latency=True,
        description="Errors are Target − run, the ROS 2 convention. One situation per line of the target view "
                    "(config · repeat · sim/real).",
    )
    meta = {
        "name": "bam_fb",
        "fixture": "arm_motion_bench · BAM FB · " + title,
        "deployment": "BAM FB (bam_arm_fb_sim) · workspace-v2 · dev",
        "target": title,
        "target_view": f"/target-view/common/target.html?site={site}&target={BAM_FB_TARGET}",
        "target_view_label": "Target view › " + title,
        "lines": {name: line for name, line in line_names.items()},
        "colors": {s.name: s.meta["color"] for s in situations},
        "robot_poses": BAM_FB_ROBOT_POSES,
    }
    return comparison, meta


def comparison(name: str, keep: list[str] | None = None) -> Any:
    """The fixture's Comparison, only the kept situations (names) when ``keep`` is given."""
    import dataclasses

    base, _ = (_tta if name == "tta" else _bam_fb)()
    if not keep:
        return base
    wanted = set(keep)
    return dataclasses.replace(base, situations=[s for s in base.situations if s.name in wanted])


def payload_colours(name: str) -> dict[str, str]:
    """``{situation name: colour}`` the fixture overrides (the bench's config colours); empty for ``tta``."""
    _, meta = (_tta if name == "tta" else _bam_fb)()
    return dict(meta.get("colors", {}))


def payload(name: str) -> dict[str, Any]:
    from traj_compare import analysis
    from traj_compare.analysis import analyze_comparison
    from traj_compare.report import _colorize, _share_robot_meshes

    built, meta = (_tta if name == "tta" else _bam_fb)()
    keep_cap = analysis.MAX_ROBOT_TRACK_POINTS
    if name == "bam_fb":
        analysis.MAX_ROBOT_TRACK_POINTS = BAM_FB_ROBOT_POSES
    try:
        page = analyze_comparison(built)
    finally:
        analysis.MAX_ROBOT_TRACK_POINTS = keep_cap
    _colorize(page)
    for situation in page["situations"]:  # the bench's config colours (what the target view shows), not the palette
        colour = meta.get("colors", {}).get(situation["name"])
        if colour:
            situation["color"] = colour
    pages = [page]
    library = _share_robot_meshes(pages)
    return {"title": page["title"], "comparisons": pages, "mesh_library": library, "report_pages": [], "meta": meta}


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or FIXTURES:
        body = payload(name)
        text = json.dumps(body, separators=(",", ":")).replace("</", "<\\/")
        out = DATA / f"{name}.js"
        out.write_text(f"window.__runViewFixture({text});\n", encoding="utf-8")
        page = body["comparisons"][0]
        print(f"{out}: {out.stat().st_size / 1e6:.1f} MB, {len(page['situations'])} situations, "
              f"{len(page['plot_t'])} samples, tabs {[t['id'] for t in page.get('tabs', [])]}")


if __name__ == "__main__":
    main()
