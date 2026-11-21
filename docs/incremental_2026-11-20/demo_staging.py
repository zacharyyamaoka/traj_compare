"""The bench's rebuild, on the Part D test fixture: build live, `cp -al live staging`, rebuild staging incrementally with
one run changed and one added, then check that live did not move. Prints a terminal capture for the review report.

    env -u VIRTUAL_ENV /home/bam/traj_compare/.venv/bin/python docs/incremental_2026-11-20/demo_staging.py <scratch dir>
"""

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1] / "src"), str(HERE.parents[1] / "tests")]

import incremental_fixture as fixture  # noqa: E402
from traj_compare import build_drill_down, write_dataset_report  # noqa: E402


def snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        str(path.relative_to(root)): (path.stat().st_ino, path.stat().st_mtime_ns, hashlib.sha1(path.read_bytes()).hexdigest())
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def main() -> None:
    scratch = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
    scratch.mkdir(parents=True, exist_ok=True)
    live, staging = scratch / "live", scratch / "staging"
    clip = fixture.make_clip(scratch / "media")
    runs = fixture.build_runs(clip)
    print(f"$ write_dataset_report({len(runs)} runs, live/)")
    write_dataset_report(runs, live, **fixture.write_options())
    build_drill_down(live, fixture.PROBE)
    before = snapshot(live)
    print(f"  live: {len(before)} files, {fixture.PROBE!r} drill-down built (report.html + rerun/)")
    print("$ cp -al live staging")
    subprocess.run(["cp", "-al", str(live), str(staging)], check=True)

    changed = fixture.build_runs(clip, (*fixture.BASE, fixture.EXTRA))
    probe = next(run for run in changed if run.name == fixture.PROBE)
    real = probe.measured["real"]
    probe.measured = {**probe.measured, "real": dataclasses.replace(real, positions=real.positions + 1e-4)}
    print(f"$ write_dataset_report(..., staging/, progress=print)   # {fixture.PROBE!r} changed, {fixture.EXTRA!r} added")
    seen: dict[str, tuple[int, int]] = {}

    def progress(phase: str, done: int, total: int) -> None:
        seen[phase] = (done, total)
        if phase in ("reused", "index") or done in (0, total):
            print(f"  progress({phase!r}, {done}, {total})")

    write_dataset_report(changed, staging, **fixture.write_options(), progress=progress)
    build_drill_down(staging, fixture.PROBE)
    after = snapshot(live)
    moved = [name for name in before if after.get(name) != before[name]]
    shared = sum(1 for name in snapshot(staging) if (live / name).is_file() and (live / name).stat().st_ino == (staging / name).stat().st_ino)
    leftovers = [str(path) for root in (live, staging) for path in root.rglob("*.tmp")]
    print(f"  reused {seen['reused'][0]} of {seen['reused'][1]} runs")
    print(f"$ check live/")
    print(f"  live files whose inode, mtime_ns or bytes changed: {len(moved)} of {len(before)}")
    print(f"  staging files still sharing their inode with live: {shared}")
    print(f"  *.tmp left in either tree: {len(leftovers)}")
    sys.exit(0 if not moved and not leftovers else 1)


if __name__ == "__main__":
    main()
