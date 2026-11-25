"""Weights & Biases view of a grasp-coverage payload: the headline numbers as run-summary scalars, nothing else.

    import wandb
    from traj_compare.grasp_coverage.wandb_log import log_grasp_coverage
    run = wandb.init(project="grasp-coverage")
    log_grasp_coverage(run, payload)     # run.summary["grasp_coverage/picked_pct"] = 96.1, ...

WHY scalars only (Zach 2026-11-21): W&B gets summary statistics (scalars, small config); media, tables and video live
in the workbench page, Rerun and the local ledger. wandb is never imported here: the caller passes its run (anything
with dict-like `.summary` and `.config`), so this works, and is testable, without wandb installed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .analysis import SCHEMA


def log_grasp_coverage(run: Any, payload: Mapping[str, Any], *, prefix: str = "grasp_coverage/") -> dict[str, Any]:
    """`run.summary[prefix + key] = value` for every payload["numbers"] entry, `run.config[prefix + "title"]`.

    Returns every key written with its value (the summary scalars, then the config title)."""
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"not a grasp_coverage payload ({SCHEMA}): schema {payload.get('schema')!r}")
    logged: dict[str, Any] = {}
    for number in payload["numbers"]:
        value = float(number["value"])
        if not math.isfinite(value):  # the contract says all finite; refuse rather than log a NaN W&B would chart
            raise ValueError(f"numbers[{number['key']!r}] = {value!r} is not finite")
        run.summary[prefix + str(number["key"])] = value
        logged[prefix + str(number["key"])] = value
    run.config[prefix + "title"] = str(payload.get("title", ""))
    logged[prefix + "title"] = str(payload.get("title", ""))
    return logged
