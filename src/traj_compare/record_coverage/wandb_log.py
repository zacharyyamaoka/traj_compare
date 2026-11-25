"""Weights & Biases view of a record-coverage payload: the headline numbers as run-summary scalars, nothing else.

    import wandb
    from traj_compare.record_coverage import log_records
    run = wandb.init(project="record-coverage")
    log_records(run, payload)        # run.summary["records/coverage_visited_pct"] = 41.2, ...

WHY scalars only (Zach 2026-11-21): W&B gets summary statistics (scalars, small config); the figures live in the
workbench page and the PNGs. So this writes exactly payload["numbers"] into `run.summary` and the title into
`run.config`. The project is registered in bam_ws tools/wandb_trackers/trackers/record_coverage.py.

wandb is never imported here: the caller passes its run (anything with dict-like `.summary` and `.config`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .analysis import SCHEMA


def log_records(run: Any, payload: Mapping[str, Any], *, prefix: str = "records/") -> dict[str, Any]:
    """`run.summary[prefix + key] = value` for every payload["numbers"] entry, `run.config[prefix + "title"]`.

    Returns every key written with its value (the summary scalars, then the config title)."""
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"not a record_coverage payload: schema {payload.get('schema')!r}")
    logged: dict[str, Any] = {}
    for number in payload["numbers"]:
        value = float(number["value"])
        if not math.isfinite(value):  # the contract says all finite; refuse rather than log a NaN W&B would chart
            raise ValueError(f"numbers[{number['key']!r}] = {value!r} is not finite")
        key = prefix + str(number["key"])
        run.summary[key] = value
        logged[key] = value
    title_key = prefix + "title"
    run.config[title_key] = str(payload.get("title", ""))
    logged[title_key] = str(payload.get("title", ""))
    return logged
