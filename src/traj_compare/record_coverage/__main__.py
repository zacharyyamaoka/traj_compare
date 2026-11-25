"""python -m traj_compare.record_coverage <file.jsonl|file.json ...> --out <dir> [options]

Reads JSON-lines files (one record per line) and JSON files holding a list of records, as Mappings, in the order given,
and writes the workbench (<dir>/index.html, served with `python -m traj_compare.serve <dir>`) and <dir>/coverage.json.
Records that are dataclasses (with their declared Value ranges) go through the Python API instead (docs/RECORD_COVERAGE.md).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import analyze


def read_records(paths: list[Path]) -> list:
    records: list = []
    for path in paths:
        text = path.read_text("utf-8")
        if path.suffix == ".json":
            loaded = json.loads(text)
            records.extend(loaded if isinstance(loaded, list) else [loaded])
        else:
            records.extend(json.loads(line) for line in text.splitlines() if line.strip())
    return records


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m traj_compare.record_coverage",
                                     description=__doc__.strip().splitlines()[0])
    parser.add_argument("files", type=Path, nargs="+", help=".jsonl (one record per line) or .json (a list)")
    parser.add_argument("--out", type=Path, required=True, help="the folder the workbench is written into")
    parser.add_argument("--title", default="")
    parser.add_argument("--group-by", default=None, help="a category field: histograms stack by it")
    parser.add_argument("--split", default=None, help="a category field (dev / holdout) for held-out support")
    parser.add_argument("--reference", default=None, help="the split's reference level (default: its first)")
    parser.add_argument("--pair", nargs=2, action="append", metavar=("X", "Y"), help="a pair plane (repeatable)")
    parser.add_argument("--range", nargs=3, action="append", metavar=("FIELD", "LOW", "HIGH"),
                        help="a declared range for a number field (repeatable)")
    parser.add_argument("--kit", default=None, help="href (relative to --out) of a data-ui kit already vendored")
    args = parser.parse_args(argv)
    records = read_records(args.files)
    ranges = {name: (float(low), float(high)) for name, low, high in (args.range or [])}
    coverage = analyze(records, title=args.title or ", ".join(p.name for p in args.files), group_by=args.group_by,
                       split=args.split, reference=args.reference, ranges=ranges or None,
                       pairs=[tuple(pair) for pair in args.pair] if args.pair else None)
    index = coverage.write_page(args.out, kit=args.kit)
    print(f"{len(records)} records -> {index}  (serve: python -m traj_compare.serve {args.out})")


if __name__ == "__main__":
    main()
