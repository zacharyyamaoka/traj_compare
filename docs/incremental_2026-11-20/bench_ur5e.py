"""Time write_dataset_report on arm_motion_bench's real UR5e runs: full, +N new runs, no change (NAVIGATION.md Part D).

Run on the bench's Python with the traj_compare under test first on the path, e.g.:
    PYTHONPATH=/home/bam/traj_compare/.claude/worktrees/incremental/src \
      /home/bam/arm_motion_bench/.venv/bin/python docs/incremental_2026-11-20/bench_ur5e.py --out /tmp/x --added 818

Scenarios, in one process (the runs load once):
  1. base:      a reuse=False write of every run but the last --added, into <out>/incremental
  2. added:     the full run list written into the same folder (the bench's "818 new runs" rebuild)
  3. unchanged: the same full list again (a rebuild where nothing changed)
  4. fresh:     a reuse=False write of the full list into <out>/fresh, the reference for scenario 2's output
Prints one JSON line per scenario: seconds, per-phase seconds (from progress), reused count; then whether 2 == 4.
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
import time
from pathlib import Path


def payload(index: Path) -> dict:
    text = index.read_text("utf-8")
    data = json.loads(re.search(r'id="traj-compare-dataset">(.*?)</script>', text, re.S).group(1).replace("<\\/", "</"))
    for key in ("generated", "write_id", "serve_command", "command_template"):
        data.pop(key, None)
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--added", type=int, default=818)
    parser.add_argument("--robot", default="ur5e")
    parser.add_argument("--limit", type=int, default=0, help="use only the first N runs (0 = all)")
    args = parser.parse_args()

    import traj_compare
    from arm_motion_bench import dashboard as bench
    from traj_compare import write_dataset_report

    print(json.dumps({"traj_compare": traj_compare.__file__}), flush=True)
    started = time.perf_counter()
    files = bench.discover(args.robot, None)
    datasets = bench._Datasets(bench.REPO / "datasets")
    ledger = bench.load_ledgers(bench.default_ledgers(args.robot))
    runs = list(bench.assemble_runs(args.robot, files, datasets, ledger).runs)
    if args.limit:
        runs = runs[: args.limit]
    print(json.dumps({"scenario": "load", "runs": len(runs), "seconds": round(time.perf_counter() - started, 1)}), flush=True)

    incremental = "reuse" in inspect.signature(write_dataset_report).parameters
    options = dict(title=f"{args.robot} bench", target_by="target", config_by="controller", poses=bench.SPECS[args.robot]["poses"],
                   robot=bench.SPECS[args.robot]["robot"], drill_down="lazy", display_hz=bench.DISPLAY_HZ,
                   signals=bench.signals(), rows=("parquet",))

    def write(name: str, chosen, out: Path, reuse: bool) -> None:
        phases: dict[str, float] = {}
        marks = {"last": time.perf_counter(), "phase": None, "reused": None}

        def progress(phase: str, done: int, total: int) -> None:
            now = time.perf_counter()
            if marks["phase"] is not None:
                phases[marks["phase"]] = phases.get(marks["phase"], 0.0) + now - marks["last"]
            marks["phase"], marks["last"] = phase, now
            if phase == "reused":
                marks["reused"] = done

        extra = dict(reuse=reuse, progress=progress) if incremental else {}
        begun = time.perf_counter()
        write_dataset_report(chosen, out, **options, **extra)
        total = time.perf_counter() - begun
        if marks["phase"] is not None:
            phases[marks["phase"]] = phases.get(marks["phase"], 0.0) + time.perf_counter() - marks["last"]
        print(json.dumps({"scenario": name, "runs": len(chosen), "seconds": round(total, 1), "reused": marks["reused"],
                          "phases": {key: round(value, 1) for key, value in phases.items()}}), flush=True)

    base = runs[: max(1, len(runs) - args.added)]
    write("base", base, args.out / "incremental", reuse=False)
    write("added", runs, args.out / "incremental", reuse=True)
    write("unchanged", runs, args.out / "incremental", reuse=True)
    write("fresh", runs, args.out / "fresh", reuse=False)
    same = payload(args.out / "incremental" / "index.html") == payload(args.out / "fresh" / "index.html")
    print(json.dumps({"scenario": "compare", "index_payload_equal": same}), flush=True)
    sys.exit(0 if same else 1)


if __name__ == "__main__":
    main()
