"""A selection of measured lines picked across dataset run folders, played back: in traj_compare's own comparison
viewer (``build_playback``) or in Rerun (``build_selection_rrd``).

    picks = [Pick(Path("ur5e/runs/<slug>"), "sim", label="pd · r0 · sim"), ...]
    build_playback(picks, "out/playback/<key>", title="conveyor-dev-000", breadcrumb=[("‹ All targets", "...")])
    build_selection_rrd(picks, "out/selections/selection-3-<key>.rrd")

WHY (Zach, Daily Note 2026-11-24 l.3227): "We have like the dataset view, then the target view (at this point its still
just summary data though), Then we can actually open up the playback viewer. either our custom one or the rerun one."
The runs workbench's target view (``traj_compare.runs_workbench``) ticks runs; ``python -m traj_compare.serve`` answers
its two buttons with these two functions (``POST <page dir>/__playback`` and ``POST <page dir>/__rerun/selection``).

Both read only run folders (``runs/<slug>/manifest.json`` and its ``.npz``), as the lazy run report does, so they work on
any site ``write_dataset_report`` wrote, long after it was written, in another process.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from robot_msgs.compare import PoseTolerance

from . import _files
from .dataset import REFERENCE, _RunFolder, _same_reference
from .model import Comparison
from .report import write_comparison_report

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_PICKS = 400  # WHY a cap: one POST must not make the server load a whole site; a target holds tens of runs


@dataclass(frozen=True)
class Pick:
    """One measured line: the run ``folder`` (it holds ``manifest.json``), one of its measured ``series``, the legend
    ``label`` (default: the run's title and the series) and ``color`` (``#rrggbb``; default: the viewer's own)."""

    folder: Path
    series: str
    label: str = ""
    color: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "folder", Path(self.folder))
        if self.color and not _COLOR.match(self.color):
            raise ValueError(f"a pick's color is #rrggbb, got {self.color!r}")
        if len(self.label) > 300:
            raise ValueError("a pick's label is at most 300 characters")


def _manifest(folder: Path) -> dict:
    path = folder / "manifest.json"
    if not path.is_file():
        raise ValueError(f"{folder} is no dataset run folder (no manifest.json)")
    return json.loads(path.read_text("utf-8"))


def _checked(picks: Sequence[Pick]) -> list[tuple[Pick, dict]]:
    picks = list(picks)
    if not picks:
        raise ValueError("no runs selected")
    if len(picks) > MAX_PICKS:
        raise ValueError(f"at most {MAX_PICKS} runs in one selection, got {len(picks)}")
    out = []
    for pick in picks:
        manifest = _manifest(pick.folder)
        if pick.series not in manifest["series"]:
            raise ValueError(f"run {manifest['name']!r} has no series {pick.series!r} (it has {manifest['series']})")
        out.append((pick, manifest))
    return out


def _label(pick: Pick, manifest: dict) -> str:
    return pick.label or f"{manifest.get('title') or manifest['name']} · {pick.series}"


def selection_key(picks: Sequence[Pick], *extra: object) -> str:
    """A short digest of the picks (each run folder, series, label, color) and ``extra``: the name a cached build of
    this selection goes under, so the same selection is the same file."""
    text = json.dumps([[str(Path(p.folder).resolve()), p.series, p.label, p.color] for p in picks] + [list(map(str, extra))])
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


# ── our playback viewer: traj_compare's comparison report over the picks and their target ───────────────────────────


def build_playback(picks: Sequence[Pick], output_dir: Path | str, *, title: str = "", subtitle: str | None = None,
                   breadcrumb: Sequence[tuple[str, str]] = (), assets: Path | str | None = None) -> Path:
    """``output_dir/report.html``: ``write_comparison_report`` (as it is, no restyle) over ONE target and every pick as
    a situation on it, titled by the pick's label, each on its own run's clock (its run's reference start is time 0).

    Every pick must follow the same target (the same reference trajectory); picks of two targets raise ``ValueError``.
    The viewer, its tool path and robot come from the first pick's run folder (``poses`` / ``robot`` of its manifest).
    ``breadcrumb`` is the page's links back up (``write_comparison_report(breadcrumb=)``); ``assets`` its shared viewer
    files (``write_comparison_report(assets=)``), so many playbacks share one copy.
    """
    checked = _checked(picks)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    folders: dict[Path, _RunFolder] = {}

    def run_of(folder: Path) -> _RunFolder:
        key = folder.resolve()
        if key not in folders:
            folders[key] = _RunFolder(folder)
        return folders[key]

    lead = run_of(checked[0][0].folder)
    reference = lead.trajectories[REFERENCE]
    reference_file = (lead.folder / lead.manifest["files"][REFERENCE]).resolve()
    target = lead.situation(REFERENCE, reference, float(reference.header.stamp), 0.0, title="Target")
    situations = []
    for index, (pick, manifest) in enumerate(checked, start=1):
        run = run_of(pick.folder)
        own = run.trajectories[REFERENCE]
        # WHY the file first: a site writes each distinct reference once (NAVIGATION.md C6), so runs of one target share it
        if (run.folder / manifest["files"][REFERENCE]).resolve() != reference_file and not _same_reference(reference, own):
            raise ValueError(f"run {manifest['name']!r} follows another target than {lead.manifest['name']!r}: a playback "
                             "is one target's runs")
        offset = float(manifest["time_offset_s"].get(pick.series, 0.0))
        situations.append(run.situation(pick.series, own, float(own.header.stamp), offset, title=_label(pick, manifest),
                                        situation_name=f"run{index}", video_root=output_dir))
    poses = lead.poses
    tolerances = lead.tolerances
    pose_tolerances = tolerances is not None and (
        isinstance(tolerances.path, PoseTolerance) or isinstance(tolerances.goal, PoseTolerance)
    )
    skipped = "".join(f" Not drawn: {key} ({why})." for run in folders.values() for key, why in run.not_drawn.items())
    comparison = Comparison(
        title=title or "Playback",
        name="playback",
        tab_title=f"Target → {len(situations)} run{'s' if len(situations) != 1 else ''}",
        joint_names=list(reference.joint_names),
        target=target,
        situations=situations,
        robot=lead.robot(),
        tcp_frame=(poses(reference).child_frame_id if poses is not None else "") or "TCP",
        tolerances=None if pose_tolerances else tolerances,
        tcp_tolerances=tolerances if pose_tolerances else None,
        estimate_latency=True,
        description=f"Errors are Target − run, the ROS 2 convention; each run on its own clock.{skipped}",
        signals=lead.signals,
        reference_kind="target",
    )
    count = f"{len(situations)} run{'s' if len(situations) != 1 else ''}"
    return write_comparison_report(
        comparison, output_dir / "report.html", title=title or "Playback",
        subtitle=subtitle if subtitle is not None else f"{count} of one target, ticked in the target view",
        provenance={"playback": count}, rerun=False, breadcrumb=list(breadcrumb), assets=assets,
    )


# ── Rerun: one recording, one plot per joint, one line per pick ─────────────────────────────────────────────────────


def _zero_at(reference, trajectory) -> float:
    """The ``t0`` that puts ``trajectory`` on its run's clock: the reference's first sample is time 0. WHY absolute
    times: a series stamped apart from its reference keeps its true offset."""
    return float(reference.header.stamp) + float(reference.t[0]) - float(trajectory.header.stamp)


def _rgb(color: str) -> list[int]:
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def build_selection_rrd(picks: Sequence[Pick], path: Path | str) -> tuple[Path, list[str]]:
    """One ``.rrd`` at ``path`` holding every distinct target (grey) and every pick (its color): joint angles and joint
    error, in degrees, through stock ``robot_msgs.viz.rerun`` (``/<field>/<joint>/<name>``, one plot per joint, one line
    per name, its default dashboard). Returns the path and the line names, targets first.

    WHY one recording for the whole selection, not one per run: Rerun overlays series in one plot only when they share a
    recording and a timeline (Zach, 2026-11-24: "any of the selected runs now appear as lines in the rerun viewer").
    Each line is on its own run's clock: its run's reference start is time 0.
    """
    from robot_msgs._core import load_npz
    from robot_msgs.compare import compare

    from .rerun_export import APPLICATION_ID, rr, viz

    if rr is None:
        raise ModuleNotFoundError("Open in Rerun needs the Rerun SDK: install traj_compare's 'rerun' extra", name="rerun")
    checked = _checked(picks)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    references: dict[Path, tuple[object, str]] = {}
    for pick, manifest in checked:
        file = (pick.folder / manifest["files"][REFERENCE]).resolve()
        if file not in references:
            references[file] = (None, (manifest.get("target") or {}).get("title") or manifest["name"])
    many = len(references) > 1
    names: list[str] = []
    recording = rr.RecordingStream(APPLICATION_ID, recording_id=f"selection-{path.stem}")
    with _files.replacing(path) as temporary:  # NAVIGATION.md D2: whole and old, or whole and new
        recording.save(str(temporary))
        for number, (file, (_, title)) in enumerate(list(references.items()), start=1):
            reference = load_npz(file)
            name = f"target {number}" if many else "target"
            viz.log(reference, viz.path_part(name), recording=recording, degrees=True, color=[150, 150, 150],
                    label=f"{name}: {title}" if many else name, t0=float(reference.t[0]))
            references[file] = (reference, title)
            names.append(name)
        for number, (pick, manifest) in enumerate(checked, start=1):
            reference = references[(pick.folder / manifest["files"][REFERENCE]).resolve()][0]
            measured = load_npz(pick.folder / manifest["files"][pick.series])
            label = _label(pick, manifest)
            short = viz.path_part(f"run{number}")
            color = _rgb(pick.color) if pick.color else None
            viz.log(measured, short, recording=recording, degrees=True, color=color, label=label,
                    t0=_zero_at(reference, measured))
            error = compare(reference, measured).error  # target - run, on the run's own samples
            viz.log(error, short, recording=recording, degrees=True, color=color, label=label, prefix="error/",
                    t0=_zero_at(reference, error))
            names.append(label)
        # WHY robot_msgs' private _finish: it sends the stock default dashboard (one plot per <field>/<joint>, every name
        # in it) for what was logged; robot_msgs has no public "finish" for a stream logged with options (degrees,
        # colour, label). Asked for in docs/RUNS_WORKBENCH.md.
        viz._finish(recording)
        recording.flush()
        recording.disconnect()
    return path, names
