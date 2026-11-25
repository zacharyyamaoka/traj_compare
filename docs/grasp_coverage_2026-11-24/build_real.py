"""Build the grasp coverage viewer on REAL grasps (2026-11-24): our full-arm repicks and a GraspNet-1Billion subset,
each through all four viewers (docs/GRASP_COVERAGE.md).

- **Our repicks**: every planned grasp of the real full-arm repick runs (rack 2026-11-10 campaign,
  /archive/datasets/bam_rig/rack_2026-11-10/fivebar_real/pick_loop_full_arm_repick_real_*), read-only, joined to its
  attempt's outcome (attempts.jsonl). The same runs the Nov 19 gallery read (robot_metrics
  docs/proposals/coverage-2026-11-19/grasp_data.py `repicks`), re-read here so the runs since Nov 19 are in.
- **GraspNet-1Billion**: the four YCB objects the gallery used (cracker box, soup can, banana, mug), valid analytic
  labels (friction <= 0.4, collision-free), an even seeded pick per object; read through the gallery's own loader and
  its cache (~/.cache/robot_metrics_coverage, built from /archive/datasets/graspnet).

Writes ``<out>/<set>/grasp_coverage.json`` (the payload), ``<out>/<set>/png/`` (Matplotlib) and ``<out>/<set>/site/``
(the data-ui workbench), one data-ui kit at ``<out>/vendor/data-ui``, and with ``--wandb`` one W&B run per set
(project grasp-coverage, registered in bam_ws tools/wandb_trackers/trackers/grasp_coverage.py).

    taskset -c 2-5,16,17 nice -n 10 /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/grasp_coverage_2026-11-24/build_real.py --wandb
    /home/bam/traj_compare/.venv/bin/python -m traj_compare.serve /home/bam/traj_compare/reports/media/grasp-coverage-2026-11-24
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics
import sys
from pathlib import Path

import numpy as np
from robot_msgs.geometry import Point, Pose, Quaternion
from robot_msgs.manipulation import GraspPose
from robot_msgs.std import Header

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent.parent
sys.path.insert(0, str(PACKAGE / "src"))

from traj_compare.coverage.workbench import DATA_UI, _vendor  # noqa: E402
from traj_compare.grasp_coverage import analyze_grasps  # noqa: E402
from traj_compare.grasp_coverage.workbench import write_grasp_workbench  # noqa: E402

OUT = PACKAGE / "reports" / "media" / "grasp-coverage-2026-11-24"
REPICKS = Path("/archive/datasets/bam_rig/rack_2026-11-10/fivebar_real")
CACHE = Path(os.environ.get("GRASP_COVERAGE_CACHE") or Path.home() / ".cache" / "traj_compare_grasp_coverage")
GALLERY = Path("/home/bam/robot_metrics/docs/proposals/coverage-2026-11-19")
WANDB_PROJECT = "grasp-coverage"  # registered in bam_ws tools/wandb_trackers/trackers/grasp_coverage.py
CLAW_OPEN_STOP_MM = 124.79  # the gallery's fallback: claw_linkage.json's open stop, when no attempt states max_open_mm
OUTCOMES = {"success": "picked", "missed": "failed", "suspect": "failed", "hover": "hovered", "refused": "refused",
            "stopped": "stopped"}
GRASPNET_PER_OBJECT = 600


# ── our repicks ─────────────────────────────────────────────────────────────────────────────────────────────────────


def _attempts(run: Path) -> dict[str, dict]:
    """cycle plan file name -> that attempt's record (as grasp_data._attempts reads it)."""
    found = {}
    path = run / "attempts.jsonl"
    if not path.is_file():
        return found
    for line in path.read_text().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "cycle" not in record:
            continue
        plan = (record.get("plan_file") or {}).get("path")
        found[Path(plan).name if plan else f"c{int(record['cycle']):03d}.json"] = record
    return found


def _read_run(run: Path) -> dict:
    attempts = _attempts(run)
    plans = []
    for plan_path in sorted((run / "plans").glob("c*.json")):
        try:
            plan = json.loads(plan_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        grasp = plan.get("grasp") or {}
        if "tcp_base_m" not in grasp or "approach_base" not in grasp or "opening_dir_base" not in grasp:
            continue
        record = attempts.get(plan_path.name, {})
        look_item = (record.get("look") or {}).get("item") or {}
        opening = (record.get("first_grasp") or {}).get("opening") or {}
        plan_item = plan.get("item") or {}
        plans.append({
            "run": run.name.rsplit("_", 1)[-1], "cycle": plan_path.stem, "item": plan.get("item_id") or "",
            "stamp_utc": plan.get("stamp_utc") or "", "tcp_base_m": grasp["tcp_base_m"],
            "approach_base": grasp["approach_base"], "opening_dir_base": grasp["opening_dir_base"],
            "outcome": record.get("outcome"), "stage_failed": record.get("stage_failed"),
            "item_width_mm": opening.get("item_width_mm") or look_item.get("width_mm") or plan_item.get("width_mm"),
            "open_gap_mm": opening.get("gap_mm"), "look_opening_mm": look_item.get("opening_mm")
            or plan_item.get("opening_mm"), "max_open_mm": opening.get("max_open_mm"),
            "claw_span_mm": look_item.get("claw_span_mm") or plan_item.get("claw_span_mm"),
            "stall_gap_mm": (record.get("close") or {}).get("stall_gap_mm"), "plane_frame": plan.get("plane_frame"),
        })
    area = None
    try:
        loop = json.loads((run / "pick_loop.json").read_text())
        if isinstance(loop.get("area"), dict) and "x_m" in loop["area"]:
            area = {key: loop["area"].get(key) for key in ("x_m", "z_m", "surface_y_m", "name")}
    except (OSError, json.JSONDecodeError):
        pass
    return {"run": run.name, "plans": plans, "area": area}


def repick_runs(refresh: bool = False) -> list[dict]:
    """Every repick run's plans + outcomes + look area; cached as JSON (the archive is a slow HDD, read once)."""
    cache = CACHE / "repicks.json"
    if cache.is_file() and not refresh:
        return json.loads(cache.read_text())
    runs = [_read_run(Path(path)) for path in sorted(glob.glob(str(REPICKS / "pick_loop_full_arm_repick_real_*")))
            if Path(path).is_dir()]
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(runs))
    return runs


def _rotation(approach, opening) -> np.ndarray:
    """robot_msgs' gripper frame: +z the approach, x the jaw (opening) axis made perpendicular to it."""
    z = np.asarray(approach, float)
    z /= np.linalg.norm(z)
    x = np.asarray(opening, float) - (np.asarray(opening, float) @ z) * z
    x /= np.linalg.norm(x)
    return np.column_stack([x, np.cross(z, x), z])


def _pose(position, rotation: np.ndarray) -> Pose:
    from scipy.spatial.transform import Rotation

    x, y, z, w = Rotation.from_matrix(rotation).as_quat()
    return Pose(position=Point(*(float(v) for v in position)), orientation=Quaternion(x, y, z, w))


def repick_grasps(runs: list[dict]):
    """(grasps by name, outcomes, tags, look-area boxes in the base frame, claw open stop m, planner span m, skipped)."""
    grasps, outcomes, tags, skipped = {}, {}, {}, 0
    opens, spans = [], []
    for run in runs:
        for plan in run["plans"]:
            width = plan["item_width_mm"]
            if width is None or not width > 0:
                skipped += 1
                continue
            name = f"{plan['run']}/{plan['cycle']}"
            pre = next((value for value in (plan["open_gap_mm"], plan["look_opening_mm"]) if value and value >= width),
                       None)
            grasps[name] = GraspPose(
                pose=_pose(plan["tcp_base_m"], _rotation(plan["approach_base"], plan["opening_dir_base"])),
                width=width / 1000.0, pre_grasp_width=None if pre is None else pre / 1000.0, object_id=plan["item"],
                header=Header(frame_id="arm base"))
            outcomes[name] = OUTCOMES.get(plan["outcome"]) if plan["outcome"] else None
            tags[name] = {"run": plan["run"], "day": plan["stamp_utc"][:10] or "unknown"}
            if plan["stage_failed"]:
                tags[name]["failed at"] = plan["stage_failed"]
            if plan["max_open_mm"]:
                opens.append(plan["max_open_mm"])
            if plan["claw_span_mm"]:
                spans.append(plan["claw_span_mm"])
    boxes = _areas(runs, grasps)
    open_stop = (statistics.median(opens) if opens else CLAW_OPEN_STOP_MM) / 1000.0
    span = (statistics.median(spans) if spans else 70.0) / 1000.0
    return grasps, outcomes, tags, boxes, open_stop, span, skipped


def _areas(runs: list[dict], grasps: dict) -> list:
    """Each run's look area (pick_loop.json: x and z in the plan's plane frame, ±60 mm around the item) as a box in the
    arm base frame, the same box kept once (5 mm). Its height spans the grasps' own heights ±10 mm: the area is a patch
    of belt, and a box needs a z to draw from the front and the side."""
    frame = next((plan["plane_frame"] for run in runs for plan in run["plans"] if plan.get("plane_frame")), None)
    if frame is None:
        return []
    rows = np.array(frame["B2P_rows"], float)
    origin = np.array(frame["origin_in_base_m"], float)
    heights = np.array([g.pose.position.z for g in grasps.values()])
    z_low, z_high = float(heights.min()) - 0.01, float(heights.max()) + 0.01
    seen = {}
    for run in runs:
        area = run.get("area")
        if not area or not area.get("x_m") or not area.get("z_m"):
            continue
        y = float(area.get("surface_y_m") or 0.0)
        corners = np.array([rows.T @ np.array([x, y, z]) + origin for x in area["x_m"] for z in area["z_m"]])
        low = (float(corners[:, 0].min()), float(corners[:, 1].min()), z_low)
        high = (float(corners[:, 0].max()), float(corners[:, 1].max()), z_high)
        seen.setdefault(tuple(round(v / 0.005) for v in low + high), (low, high))
    return list(seen.values())


# ── GraspNet-1Billion ───────────────────────────────────────────────────────────────────────────────────────────────


def graspnet_grasps(per_object: int = GRASPNET_PER_OBJECT):
    """An even seeded pick of each object's valid labels, as GraspPose in that object's own frame."""
    sys.path.insert(0, str(GALLERY))
    import grasp_data as gd  # the Nov 19 gallery's loader: its cache, else a read-only pass over /archive

    views = gd.generate_views()
    rng = np.random.default_rng(0)
    grasps = {}
    for object_id, label in gd.GRASPNET_OBJECTS.items():
        data = gd.graspnet_object(object_id)
        count = len(data["point"])
        picked = np.sort(rng.choice(count, size=min(per_object, count), replace=False))
        angles = data["angle"][picked].astype(float) * math.pi / gd.NUM_ANGLES
        rotations = gd.grasp_rotation(views[data["view"][picked]], angles)  # columns: approach, jaw, finger height
        for k, index in enumerate(picked):
            g = rotations[k]
            tool = np.column_stack([g[:, 1], g[:, 2], g[:, 0]])  # robot_msgs: x jaw, z approach
            grasps[f"{object_id:03d}/{index}"] = GraspPose(
                pose=_pose(data["points"][data["point"][index]], tool), width=float(data["width_mm"][index]) / 1000.0,
                object_id=label, header=Header(frame_id="object"))
    return grasps, gd


# ── build ───────────────────────────────────────────────────────────────────────────────────────────────────────────


def write_set(coverage, grasps, out: Path, *, kit: str, dataset_label: str, facets) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "grasp_coverage.json").write_text(json.dumps(coverage.payload, allow_nan=False, separators=(",", ":")))
    coverage.plot(out / "png")
    write_grasp_workbench(coverage, grasps, out / "site", kit=kit, dataset_label=dataset_label, facets=facets)


def log_to_wandb(coverage, name: str, config: dict) -> None:
    import wandb

    run = wandb.init(project=WANDB_PROJECT, dir=str(CACHE / "wandb"), name=name, job_type="grasp-coverage",
                     reinit="finish_previous", config=config)
    try:
        coverage.log_wandb(run)
        print(f"W&B {name}: {run.url}")
    finally:
        run.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--refresh", action="store_true", help="re-read /archive (else the cache)")
    parser.add_argument("--wandb", action="store_true", help="log each set's headline numbers to W&B (grasp-coverage)")
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (CACHE / "wandb").mkdir(parents=True, exist_ok=True)
    if not (out / "vendor" / "data-ui" / "data-ui.js").is_file():
        _vendor(out, "main", DATA_UI)
    kit = "../../vendor/data-ui"

    runs = repick_runs(args.refresh)
    grasps, outcomes, tags, boxes, open_stop, span, skipped = repick_grasps(runs)
    days = sorted({t["day"] for t in tags.values()})
    repicks = analyze_grasps(
        grasps, outcomes=outcomes, width_range=(0.0, open_stop), planner_width_range=(0.0, span),
        # WHY the full circle: the Nov 19 gallery read our claw as asymmetric (roll_rose: "asymmetric claw: full
        # circle"), so a grasp at roll r is not the one at r + 180°
        symmetric_jaws=False, tags=tags, area=boxes, title="Our real repicks",
        subtitle=f"{len(runs)} runs of the rack 2026-11-10 campaign, {days[0]} to {days[-1]}; "
                 f"claw open stop {open_stop * 1000:.1f} mm, planner span {span * 1000:.0f} mm")
    write_set(repicks, grasps, out / "repicks", kit=kit, dataset_label="pick_loop_full_arm_repick_real_*",
              facets=("day", "failed at"))
    print(f"repicks: {len(grasps)} grasps ({skipped} plans without a width skipped), {len(boxes)} look areas, "
          f"{repicks.numbers}")

    graspnet, gd = graspnet_grasps()
    labels = analyze_grasps(
        graspnet, width_range=(0.0, open_stop), planner_width_range=(0.0, span), symmetric_jaws=True,
        title="GraspNet-1Billion, 4 YCB objects",
        subtitle=f"valid analytic labels (friction ≤ {gd.FRICTION_MAX}, collision-free), {GRASPNET_PER_OBJECT} per object "
                 "picked evenly (seed 0); each object in its own frame; against our claw's range")
    write_set(labels, graspnet, out / "graspnet", kit=kit, dataset_label="GraspNet-1Billion grasp_label", facets=())
    print(f"graspnet: {len(graspnet)} grasps, {labels.numbers}")

    index = {"repicks": {"grasps": len(grasps), "runs": len(runs), "skipped": skipped, "areas": len(boxes),
                         "open_stop_m": open_stop, "planner_span_m": span, "days": days},
             "graspnet": {"grasps": len(graspnet), "per_object": GRASPNET_PER_OBJECT}}
    (out / "build.json").write_text(json.dumps(index, indent=1))
    if args.wandb:
        log_to_wandb(repicks, "repicks", {"set": "repicks", "runs": len(runs), "days": f"{days[0]}..{days[-1]}"})
        log_to_wandb(labels, "graspnet-4-ycb", {"set": "graspnet", "per_object": GRASPNET_PER_OBJECT})


if __name__ == "__main__":
    main()
