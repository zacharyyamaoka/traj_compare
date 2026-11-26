"""Build or open the Rerun recording for a saved traj_compare report.

    traj-compare-rerun /path/to/report.html --comparison 0 --open
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from robot_msgs.compare import JointTolerance, PoseTolerance, Tolerances

from .model import CameraOverlay, Comparison, RobotDisplay, Situation
from .rerun_export import LAYOUTS, RERUN_SDK_VERSION, blueprint_path, default_layout, viewer_argv, write_rrd

_DATA = re.compile(r'<script type="application/json" id="traj-compare-data">(.*?)</script>', re.DOTALL)
_FILENAME = re.compile(r"[^A-Za-z0-9_.-]+")
_SAFE_OVERLAY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _within(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise PermissionError(f"{path.name} is outside the report directory")
    return resolved


def _recording_file(path: Path) -> bool:
    if not path.is_file():
        return False
    # A static host can answer a missing .rrd with HTML and HTTP 200.
    # RRF2 is the container signature read by the pinned Rerun version.
    with path.open("rb") as recording:
        header = recording.read(12)
        return len(header) == 12 and header.startswith(b"RRF2")


def _robot_display(spec: dict[str, Any], mesh_library: list[str]) -> RobotDisplay:
    links = spec["links"]

    def mesh(link: dict[str, Any]) -> np.ndarray:
        tris = link["tris"]
        if isinstance(tris, int):
            tris = mesh_library[tris]
        return np.frombuffer(base64.b64decode(tris, validate=True), dtype="<f4").reshape(-1, 3, 3)

    def link_fk(_positions: np.ndarray) -> np.ndarray:
        raise ValueError("a saved report already contains its robot link poses")

    return RobotDisplay(
        name=spec["name"],
        link_names=[link["name"] for link in links],
        link_meshes=[mesh(link) for link in links],
        link_colors=[link.get("color") for link in links],
        link_opacities=[link.get("opacity", 0.55) for link in links],
        link_fk=link_fk,
    )


def _media(root: Path, directory: Path, location: str | None) -> str | None:
    if location:
        try:
            path = _within(root, directory / location)
        except (PermissionError, ValueError):
            return None
        if path.suffix.lower() == ".mp4" and path.is_file():
            return str(path)
    return None


def _limits(source: dict[str, Any], key: str) -> Tolerances | None:
    values = source.get(key)
    if values is None:
        return None
    if key == "position_bands":
        phases = {
            phase: tuple(JointTolerance(name=name, position=limit) for name, limit in bands.items())
            for phase, bands in values.items()
        }
    else:
        phases = {phase: PoseTolerance(position=limit) for phase, limit in values.items()}
    return Tolerances(**phases)


def _comparison(
    payload: dict[str, Any], mesh_library: list[str], source: dict[str, Any], root: Path, directory: Path
) -> Comparison:
    robots = [_robot_display(spec, mesh_library) for spec in payload.get("robots", [])]
    ranges = source.get("time_ranges") or {}
    plot_t = np.asarray(payload["plot_t"], dtype=float)
    joint_names = payload["joint_names"]
    runs = []
    target = None
    for entry in payload["situations"]:
        entry["video"] = _media(root, directory, entry["video"])
        t, q = None, None
        if entry["has_data"]:
            # Only the run's start/end come from Situation. The stock exporter reads
            # every plotted channel and pose from the original aligned payload.
            if entry["name"] in ranges:
                t = np.asarray(ranges[entry["name"]], dtype=float)
            else:
                has_position = np.any(np.isfinite(np.asarray(entry["plot"]["q"], dtype=float)), axis=0)
                active = plot_t[has_position]
                t = active[[0, -1]] if active.size > 1 else plot_t[[0, -1]]
            q = np.zeros((2, len(joint_names)))
        track = entry.get("robot_track")
        robot = robots[track["robot"]] if track is not None else None
        situation = Situation(entry["name"], entry["title"], t=t, q=q, robot=robot)
        if entry["role"] == "target":
            target = situation
        else:
            runs.append(situation)
    payload["has_video"] = any(entry["video"] for entry in payload["situations"])

    overlays = []
    for spec in payload.get("overlays", []):
        if not _SAFE_OVERLAY.fullmatch(spec["name"]):
            continue
        video = _media(root, directory, spec.get("real_video"))
        simulations = [(sim["label"], _media(root, directory, sim["video"])) for sim in spec["sims"]]
        if video and (present := [(label, path) for label, path in simulations if path]):
            overlays.append(CameraOverlay(spec["name"], video, present, t0_s=spec["t0_s"]))
    return Comparison(
        title=payload["title"], joint_names=joint_names, situations=runs, target=target, overlays=overlays,
        name=payload["name"], group_title=payload.get("group_title", ""), tab_title=payload.get("tab_title", ""),
        tolerances=_limits(source, "position_bands"), tcp_tolerances=_limits(source, "tcp_position_bands"),
        reference_kind=payload.get("reference_kind", "target"),
    )


def report_recording(
    path: Path | str, index: int = 0, *, root: Path | None = None, layout: str | None = None
) -> Path:
    """Resolve an existing recording or rebuild it from the selected report payload on disk."""

    path = Path(path).resolve()
    root = path.parent if root is None else root.resolve()
    _within(root, path)
    if path.suffix.lower() not in (".html", ".htm"):
        raise ValueError("expected a traj_compare HTML report")
    if index < 0:
        raise ValueError("comparison index must be at least zero")
    if layout is not None and layout not in LAYOUTS:
        raise ValueError(f"unknown layout {layout!r}; choose one of: {', '.join(LAYOUTS)}")
    match = _DATA.search(path.read_text("utf-8"))
    if match is None:
        raise ValueError("this HTML file has no traj_compare comparison payload")
    raw = match[1]
    document = json.loads(raw)
    comparisons = document["comparisons"]
    if index >= len(comparisons):
        raise ValueError(f"comparison index {index} is outside this report")
    payload = comparisons[index]
    info = payload.get("rerun") or {}

    def reusable(output: Path) -> bool:
        if output.suffix.lower() != ".rrd":
            raise ValueError("the comparison recording must be a .rrd file")
        if not _recording_file(output):
            return False
        return layout is None or _recording_file(_within(root, blueprint_path(output, layout)))

    declared = _within(root, path.parent / info["rrd"]) if info.get("rrd") else None
    if declared is not None and reusable(declared):
        return declared

    # A generation publishes one whole recording and all its sidecars at
    # once. A CLI and server building concurrently may race to publish it,
    # but neither reads the other caller's unfinished files.
    chosen = info["layout"] if info.get("layout") in LAYOUTS else default_layout()
    stem = _FILENAME.sub("-", path.stem).strip("-.") or "report"
    build = hashlib.sha256((raw + "\0" + chosen + RERUN_SDK_VERSION).encode("utf-8")).hexdigest()[:12]
    key = f"{stem}-{build}-{index + 1}"
    cache = _within(root, path.parent / "rerun")
    completed = cache / key
    filename = f"{key}.rrd"

    def ready(directory: Path) -> Path | None:
        if directory.is_symlink():
            raise PermissionError("the generated Rerun directory must not be a symlink")
        output = _within(root, directory / filename)
        if reusable(output) and all(_recording_file(_within(root, blueprint_path(output, name))) for name in LAYOUTS):
            return output
        return None

    if (output := ready(completed)) is not None:
        return output
    if completed.exists():
        if (output := ready(completed)) is not None:
            return output
        raise ValueError(f"incomplete Rerun output at {completed}")

    source = payload.get("rerun_source") or {}
    comparison = _comparison(payload, document.get("mesh_library", []), source, root, path.parent)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".rerun-build-", dir=cache) as staging:
        stage = Path(staging)
        write_rrd(
            comparison, stage / filename, layout=chosen, payload=payload, video_root=path.parent,
            checks=source.get("checks"), view="layouts",
        )
        if ready(stage) is None:
            raise ValueError(f"did not build a complete Rerun recording for {path.name}")
        if (output := ready(completed)) is not None:
            return output
        try:
            stage.rename(completed)
        except OSError:
            if (output := ready(completed)) is not None:
                return output
            raise
    if (output := ready(completed)) is None:
        raise ValueError(f"did not build a complete Rerun recording for {path.name}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="the saved HTML comparison")
    parser.add_argument("--comparison", type=int, default=0, help="zero-based comparison index in the report")
    parser.add_argument("--layout", choices=LAYOUTS, help="use this named Rerun layout")
    parser.add_argument("--open", action="store_true", help="open the result in Rerun")
    args = parser.parse_args()
    try:
        recording = report_recording(args.report, args.comparison, layout=args.layout)
        print(recording, flush=True)
        if args.open:
            subprocess.run(viewer_argv(recording, args.layout), check=True)
    except (ImportError, KeyError, OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
