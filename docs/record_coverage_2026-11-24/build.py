"""Build the record-coverage viewer on the two real datasets (2026-11-24): a data-ui workbench, the Matplotlib PNGs and
coverage.json for each, data-ui vendored once beside them. Optionally log each payload's numbers to W&B.

    taskset -c 2-5,16,17 /home/bam/dataclass_coverage/.venv/bin/python docs/record_coverage_2026-11-24/build.py [--out DIR] [--wandb]
    python -m http.server 8934 --bind 127.0.0.1 --directory <out>     # then /repick-grasps/index.html, /bench-tasks/index.html

WHY in traj_compare, with dataclass_coverage's interpreter: the viewer moved to its own public package
(github.com/zacharyyamaoka/dataclass_coverage) the same day; this proof on BAM's own data stays private, here.

The datasets are read by datasets.py (read-only). Output defaults to the main checkout's reports/media (gitignored).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from datasets import bench_tasks, repick_plans  # noqa: E402

from dataclass_coverage import analyze  # noqa: E402
from dataclass_coverage._kit import DATA_UI, _vendor  # noqa: E402

OUT = Path("/home/bam/traj_compare/reports/media/record-coverage-2026-11-24")
PI = math.pi

# WHY a curated field list for the bench: Task.meta and .recipe hold 146 columns across 8 task kinds; these are the
# ones a reader asks about (where picks are, how long, which object and bin). analyze(tasks) with no fields= runs too
# (0.13 s, 146 columns), and the report says so.
BENCH_FIELDS = [
    "robot", "dataset", "split", "kind", "task_id", "order", "len(keyposes)", "n_points", "len(stops)",
    "belt_speed_m_s", "meta.belt", "meta.bin", "meta.object", "meta.distance_class", "meta.time_law",
    "meta.duration_s", "meta.line_deviation_max_mm", "meta.tcp_distance_m", "meta.yaw_rad",
    "meta.pick_cell_m[0]", "meta.pick_cell_m[1]", "meta.pick_cell_m[2]",
    "meta.release_cell_m[0]", "meta.release_cell_m[1]", "meta.release_cell_m[2]",
]


def datasets() -> dict:
    tasks = bench_tasks()
    plans = repick_plans()
    return {
        "repick-grasps": dict(
            records=plans,
            title="Real repick grasps (full arm, 2026-11-10 campaign)",
            subtitle=f"{len(plans)} planned grasps of the real full-arm repick runs, each joined to what happened; "
                     "J1, the wrist and the claw declare their limits on each record",
            group_by="outcome",
            pairs=[("tcp_base_m[0]", "tcp_base_m[1]"), ("item_width_mm", "open_gap_mm"), ("j1_rad", "w_rad[0]")],
        ),
        "bench-tasks": dict(
            records=tasks,
            title="arm_motion_bench tasks (v2, every robot)",
            subtitle=f"{len(tasks)} arm_motion_bench Task records (tasks.jsonl, 4 robots, 3 datasets), "
                     "read with the bench's own Task.from_json",
            fields=BENCH_FIELDS, group_by="robot", split="split",
            ranges={"meta.yaw_rad": (-PI, PI)},
            pairs=[("meta.pick_cell_m[0]", "meta.pick_cell_m[1]"), ("meta.tcp_distance_m", "meta.duration_s")],
            xyz=["meta.pick_cell_m[0]", "meta.pick_cell_m[1]", "meta.pick_cell_m[2]"],
        ),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--wandb", action="store_true", help="log each payload's numbers to W&B project record-coverage")
    args = parser.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    kit = out / "vendor" / "data-ui"
    if not (kit / "data-ui.js").is_file():
        _vendor(out, "main", DATA_UI)
    # WHY keep the earlier W&B links: a rebuild without --wandb must not forget the runs already logged
    previous = json.loads((out / "build-summary.json").read_text()) if (out / "build-summary.json").is_file() else {}
    summary = {}
    for slug, spec in datasets().items():
        records = spec.pop("records")
        title, subtitle = spec.pop("title"), spec.pop("subtitle")
        started = time.time()
        coverage = analyze(records, title=title, subtitle=subtitle, **spec)
        seconds = time.time() - started
        site = out / slug
        coverage.write_page(site, kit="../vendor/data-ui")
        pngs = coverage.plot(site / "png")
        summary[slug] = {"records": len(records), "analyze_s": round(seconds, 3), "pngs": [p.name for p in pngs],
                         "numbers": coverage.numbers, "notes": coverage.payload["source"]["notes"],
                         "bytes": {p.name: p.stat().st_size for p in site.glob("*.json")}}
        if (previous.get(slug) or {}).get("wandb"):
            summary[slug]["wandb"] = previous[slug]["wandb"]
        if args.wandb:
            import wandb

            run = wandb.init(project="record-coverage", name=slug, job_type="record-coverage",
                             config={"records": len(records)}, settings=wandb.Settings(console="off", save_code=False))
            try:
                coverage.log_wandb(run)
                summary[slug]["wandb"] = run.url
            finally:
                run.finish()
        print(f"{slug}: {len(records)} records, analyze {seconds:.2f} s, {len(pngs)} PNGs -> {site}")
    (out / "build-summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
