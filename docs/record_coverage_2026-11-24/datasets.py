"""The two real datasets the record-coverage viewer was proven on (2026-11-24), as frozen dataclass records.

- ``bench_tasks()``: every arm_motion_bench task (``datasets/*/*/v2/tasks.jsonl``, 424 records, 4 robots), read with
  arm_motion_bench's own ``Task.from_json``: the records exactly as that package defines them.
- ``repick_plans()``: every planned grasp of the real full-arm repick runs (rack 2026-11-10 campaign, 1,131 plans),
  joined to its attempt's outcome by robot_metrics' coverage-gallery reader (``grasp_data.repicks()``, which caches
  /archive once). Each plan's limits (J1's range, the wrist's ±max, the claw span) are declared on its own record as
  ``Value(low=, high=)``, the way dataclass_values says a record carries its space.

Read-only on every source. Paths are overridable: ``ARM_MOTION_BENCH``, ``ROBOT_METRICS``.
"""

from __future__ import annotations

import glob
import importlib.util
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dataclass_values import Value

ARM_MOTION_BENCH = Path(os.environ.get("ARM_MOTION_BENCH", "/home/bam/arm_motion_bench"))
ROBOT_METRICS = Path(os.environ.get("ROBOT_METRICS", "/home/bam/robot_metrics"))


def bench_tasks() -> list:
    """arm_motion_bench's Task records, every robot and dataset (v2), in path order then file order."""
    sys.path.insert(0, str(ARM_MOTION_BENCH / "src"))
    try:
        # WHY the records module alone: arm_motion_bench/__init__ pulls the bench's heavy deps; records/ is stdlib
        spec = importlib.util.spec_from_file_location("amb_task", ARM_MOTION_BENCH / "src/arm_motion_bench/records/task.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # WHY: @dataclass looks its class's module up in sys.modules
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    tasks = []
    for path in sorted(glob.glob(str(ARM_MOTION_BENCH / "datasets/*/*/v2/tasks.jsonl"))):
        for line in Path(path).read_text().splitlines():
            if line.strip():
                tasks.append(module.Task.from_json(line))
    return tasks


@dataclass(frozen=True)
class RepickPlan:
    """One planned grasp of a real full-arm repick run, joined to what happened when the arm tried it."""

    run: str
    cycle: str
    item: str
    outcome: str | None  # success | hover | refused | missed | stopped | suspect; None = never attempted
    bucket: str | None  # what failed, when something did
    stage_failed: str | None
    grasped: bool | None
    tcp_base_m: tuple  # the planned TCP, base frame
    approach_base: tuple  # unit vector
    opening_dir_base: tuple  # unit vector
    psi_rad: float
    theta_open_rad: float
    theta_item_rad: float
    j1_rad: float
    w_rad: tuple  # the three wrist joints
    fit_margin_mm: float
    item_width_mm: float | None
    open_gap_mm: float | None  # the claw's measured gap when it opened
    wanted_gap_mm: float | None
    stall_gap_mm: float | None
    claw_span_mm: float | None
    stamp_utc: str


def _declared(value, unit: str, low: float, high: float):
    """The value as a Value carrying its record's limit, or the plain number when it is beyond it (a Value outside its
    range is refused at construction; the plain number then counts as 'beyond the range' against the class's union)."""
    if value is None:
        return None
    if low <= float(value) <= high:
        return Value(float(value), unit, low=low, high=high)
    return float(value)


def _unit(vector) -> tuple:
    return tuple(_declared(v, "", -1.0, 1.0) for v in vector)


def repick_plans() -> list[RepickPlan]:
    spec = importlib.util.spec_from_file_location(
        "grasp_data", ROBOT_METRICS / "docs/proposals/coverage-2026-11-19/grasp_data.py")
    grasp_data = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = grasp_data
    spec.loader.exec_module(grasp_data)
    plans = []
    for run in grasp_data.repicks():
        for plan in run["plans"]:
            limits = plan.get("limits") or {}
            j1_low, j1_high = limits.get("j1_range_rad", (-math.pi, math.pi))
            w1, w23 = limits.get("w1_abs_max_rad", math.pi), limits.get("w23_abs_max_rad", math.pi)
            span = plan.get("claw_span_mm")
            w = plan["w_rad"]
            gap = (lambda key: _declared(plan.get(key), "mm", 0.0, span) if span else plan.get(key))
            plans.append(RepickPlan(
                run=plan["run"], cycle=plan["cycle"], item=plan["item"], outcome=plan.get("outcome"),
                bucket=plan.get("bucket"), stage_failed=plan.get("stage_failed"), grasped=plan.get("grasped"),
                tcp_base_m=tuple(plan["tcp_base_m"]), approach_base=_unit(plan["approach_base"]),
                opening_dir_base=_unit(plan["opening_dir_base"]),
                psi_rad=_declared(plan["psi_rad"], "rad", -math.pi, math.pi),
                theta_open_rad=plan["theta_open_rad"], theta_item_rad=plan["theta_item_rad"],
                j1_rad=_declared(plan["j1_rad"], "rad", j1_low, j1_high),
                w_rad=(_declared(w[0], "rad", -w1, w1), _declared(w[1], "rad", -w23, w23),
                       _declared(w[2], "rad", -w23, w23)),
                fit_margin_mm=plan["fit_margin_mm"], item_width_mm=gap("item_width_mm"),
                open_gap_mm=gap("open_gap_mm"), wanted_gap_mm=gap("wanted_gap_mm"), stall_gap_mm=gap("stall_gap_mm"),
                claw_span_mm=span, stamp_utc=plan.get("stamp_utc") or "",
            ))
    return plans
