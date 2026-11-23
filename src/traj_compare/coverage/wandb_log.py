"""Weights & Biases view of a trajectory-coverage payload: the headline numbers as run-summary scalars, nothing else.

    import wandb
    from traj_compare.coverage.wandb_log import log_coverage
    run = wandb.init(project="...")
    log_coverage(run, payload)        # run.summary["coverage/q_span_median_pct"] = 74.2, ...

WHY scalars only (Zach 2026-11-21): W&B gets summary statistics (scalars, small config); media, tables and video live
in the coverage page, Rerun and the local ledger. So this writes exactly payload["numbers"] into `run.summary` and
the payload's title into `run.config` — no tables, images or histograms.

wandb is never imported here: the caller passes its run (anything with dict-like `.summary` and `.config`), so this
module works, and is testable, without wandb installed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def log_coverage(run: Any, payload: Mapping[str, Any], *, prefix: str = "coverage/") -> dict[str, Any]:
    """`run.summary[prefix + key] = value` for every payload["numbers"] entry, `run.config[prefix + "title"]`.

    Returns every key written with its value (the summary scalars, then the config title)."""
    if payload.get("schema") != "traj_compare.coverage/1":
        raise ValueError(f"not a coverage payload: schema {payload.get('schema')!r}")
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
