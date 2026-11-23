"""python -m traj_compare.coverage <file.npz|dir ...> --out DIR [--tool <file.npz|dir ...>] [--title T]

Reads robot_msgs .npz messages (JointTrajectory; the tool's PoseTrajectory with --tool, paired in the same order) and
writes DIR/coverage.json, plus DIR/index.html when the page viewer is installed. A directory means every *.npz in it,
sorted by name.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path

from robot_msgs._core import load_npz
from robot_msgs.trajectory import JointTrajectory, PoseTrajectory

from .analysis import analyze


def npz_files(inputs: Sequence[str]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            files.extend(sorted(path.glob("*.npz")))
        elif path.is_file():
            files.append(path)
        else:
            raise SystemExit(f"no such file or directory: {path}")
    if not files:
        raise SystemExit(f"no .npz files in {list(inputs)}")
    return files


def load_messages(files: Sequence[Path], message_type: type) -> dict[str, object]:
    """name -> message, in file order. Name: header.meta["name"], else the file name without .npz."""
    messages: dict[str, object] = {}
    for path in files:
        message = load_npz(path)
        if not isinstance(message, message_type):
            hint = " (pass a tool's PoseTrajectory with --tool)" if isinstance(message, PoseTrajectory) else ""
            raise SystemExit(f"{path} holds a {type(message).__name__}, not a {message_type.__name__}{hint}")
        name = message.header.meta.get("name") or path.stem
        if name in messages:
            name = str(path)
        messages[name] = message
    return messages


def page_installed() -> bool:
    """Whether the page viewer module exists. WHY not a bare `except ImportError`: a page that is there but misses
    one of ITS imports must fail loudly, not pass for "not installed"."""
    try:
        import_module(f"{__package__}.page")
    except ModuleNotFoundError as error:
        if error.name != f"{__package__}.page":
            raise
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m traj_compare.coverage", description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="JointTrajectory .npz files or directories of them")
    parser.add_argument("--out", required=True, type=Path, help="directory for coverage.json and index.html")
    parser.add_argument("--tool", nargs="+", default=None, help="the tool's PoseTrajectory .npz files, same order")
    parser.add_argument("--title", default="", help="page title")
    args = parser.parse_args(argv)

    trajectories = load_messages(npz_files(args.inputs), JointTrajectory)
    tool = None
    if args.tool:
        poses = list(load_messages(npz_files(args.tool), PoseTrajectory).values())
        if len(poses) != len(trajectories):
            raise SystemExit(f"--tool gave {len(poses)} pose trajectories for {len(trajectories)} joint trajectories")
        tool = dict(zip(trajectories, poses, strict=True))
    coverage = analyze(trajectories, tool=tool, title=args.title)

    args.out.mkdir(parents=True, exist_ok=True)
    data_path = args.out / "coverage.json"
    data_path.write_text(json.dumps(coverage.payload, allow_nan=False, separators=(",", ":")), "utf-8")
    print(f"wrote {data_path}")
    if page_installed():
        print(f"wrote {coverage.write_page(args.out / 'index.html')}")
    else:
        print("the page viewer (traj_compare.coverage.page) is not installed yet: wrote coverage.json only")
    for row in coverage.payload["numbers"]:
        print(f"  {row['label']}: {row['value']:.4g} {row['unit']}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
