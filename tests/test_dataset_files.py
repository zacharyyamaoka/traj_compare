"""Row files and files on disk (docs/NAVIGATION.md Part C, C2 and C6; acceptance written before the code, 2026-11-20).

The arm_motion_bench UR5e site (4932 runs) wrote a 460 MB ``rows.json`` it never read, and 0.81 GB of
``runs/<slug>/reference.npz`` for only 974 distinct references, every ``.npz`` stored uncompressed. C2 lets the author
pick the row files (``write_dataset_report(..., rows=...)``); C6 writes each distinct reference once as
``references/<digest>.npz`` and compresses every ``.npz`` the dataset writes. These tests are the implementing lane's
ruler: it must not edit this file.

Readings of the contract this file pins (the places it is not literal):

- C2, ``rows=None`` without pyarrow: ``rows.parquet`` is not chosen this time, so one an earlier write left is deleted
  ("no stale rows outlive their data").
- C2, ``rows`` is a set of names: ``("parquet", "json")`` is the same choice as ``("json", "parquet")``, and a list works
  as a tuple does.
- C2, "raised before any file is written": the output directory's files are exactly as they were (none added, none
  changed, none deleted, so no stale row file is removed either).
- C6, the digest: the file stem is lowercase hex, 12 to 40 characters (a full SHA-1, or a prefix of at least the 12
  today's target hash uses). The digest's exact byte layout is not pinned; what is pinned: equal content in new objects,
  in another run order or in another output directory gives the same name, and a difference anywhere (only the
  velocities, one sample by one ulp, only ``header.frame_id``, one added channel) gives another file.
- C6, the orphan rule is literal: after a write, a ``references/*.npz`` that no ``runs/*/manifest.json`` on disk names
  is deleted, a stray file dropped there included; and every manifest on disk still names a file that exists. Whether
  a run folder an earlier write left (a run no longer in the dataset) is pruned or kept is not pinned, only that it is
  never left naming a deleted reference.
- C6, an old-style folder is one written before 2026-11-20: ``files.reference == "reference.npz"`` beside the series,
  every ``.npz`` uncompressed (``robot_msgs._core.save_npz`` / ``np.savez``), in a site that is otherwise new-style.
  Whether a rewrite deletes a ``runs/<slug>/reference.npz`` left by a pre-2026-11-20 write is not pinned ("nothing
  writes" it is).
- C6, "bit-identical": a saved message's JSON tree equals ``robot_msgs._core.to_dict`` of the input, and every array has
  the input's dtype, shape and bytes (a float32 channel stays float32), read both through ``load_npz`` and raw through
  ``np.load``. Torques compare with the float (N, J) arrays ``Run`` holds after its own checks.
- C6, the size check: "reference storage" is every file a manifest's ``files.reference`` resolves to, plus
  ``references/*.npz``, plus any ``runs/*/reference.npz``; "one reference's compressed size" is
  ``np.savez_compressed`` of that reference in robot_msgs's npz layout (its ``__msg__`` JSON and its arrays), the
  largest of the five.

Run:

    cd /home/bam/traj_compare
    env -u VIRTUAL_ENV .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dataset_files.py
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from dataset_levels_fixture import TARGETS, build_runs
from robot_msgs._core import load_npz, save_npz, to_dict
from robot_msgs.std import Header
from robot_msgs.trajectory import JointTrajectory

from traj_compare import Run, build_drill_down, write_dataset_report

JOINTS = ("shoulder", "elbow", "wrist")
SAMPLE_S = 0.01
FRAME = "base_link"
TAGS = {"rig": "ur_wrist", "can": 13, "speed": 0.5, "held_out": False}
ROW_COLUMNS = ["run", "pair", "metric", "stat", "value", "unit", *TAGS]
JSON_ROWS = "rows.json"
PARQUET_ROWS = "rows.parquet"
BOTH_ROWS = {JSON_ROWS, PARQUET_ROWS}
# What a run's manifest names its reference by (C6); group 1 is the digest.
REFERENCE_PATH = re.compile(r"\.\./\.\./references/([0-9a-f]{12,40})\.npz")


# ── the data ─────────────────────────────────────────────────────────────────


def make_reference(
    variant: int = 0, *, samples: int = 201, velocities: bool = False, frame_id: str = FRAME
) -> JointTrajectory:
    """A minimum-jerk move of the shoulder and elbow with the wrist parked; ``variant`` scales the move."""
    t = np.round(np.arange(samples) * SAMPLE_S, 6)
    phase = np.clip(t / t[-1], 0.0, 1.0)
    progress = phase**3 * (10.0 - 15.0 * phase + 6.0 * phase**2)
    amplitude = 0.3 + 0.1 * variant
    positions = np.column_stack([amplitude * progress, -0.5 * amplitude * progress, np.full_like(t, 0.2)])
    return JointTrajectory(
        t=t,
        joint_names=JOINTS,
        positions=positions,
        velocities=np.gradient(positions, t, axis=0) if velocities else None,
        header=Header(frame_id=frame_id),
    )


def follow(reference: JointTrajectory, seed: int, *, channels: dict[str, np.ndarray] | None = None) -> JointTrajectory:
    """The reference run 10 ms late plus a little seeded noise, on the reference's own samples and frame."""
    rng = np.random.default_rng(seed)
    late = np.column_stack([np.interp(reference.t - 0.01, reference.t, column) for column in reference.positions.T])
    return JointTrajectory(
        t=np.array(reference.t),
        joint_names=JOINTS,
        positions=late + rng.normal(0.0, 2e-4, size=late.shape),
        channels=channels or {},
        header=reference.header,
    )


def torque_breakdown(samples: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    return {
        "tau_ff": rng.normal(1.0, 0.2, size=(samples, len(JOINTS))),
        "tau_fb": rng.normal(0.0, 0.1, size=(samples, len(JOINTS))),
    }


def make_run(name: str, reference: JointTrajectory, seed: int = 0, *, torques: bool = False) -> Run:
    return Run(
        name=name,
        reference=reference,
        measured={"real": follow(reference, seed)},
        tags=dict(TAGS),
        torques={"real": torque_breakdown(len(reference.t), seed)} if torques else {},
    )


def instrumented_run(name: str = "instrumented", seed: int = 7) -> Run:
    """A run that exercises every .npz the dataset writes, with every kind of array in it.

    The reference has velocities, effort and a float32 channel; the series has motor current (float32, which must stay
    float32) and a 1-D float64 force channel; the series carries a torque breakdown (``.torques.npz``).
    """
    rng = np.random.default_rng(seed)
    base = make_reference(3, velocities=True)
    samples = len(base.t)
    reference = base.replace(
        effort=rng.normal(0.0, 1.0, size=(samples, len(JOINTS))),
        channels={"setpoint_index": np.arange(samples, dtype=np.float32)},
    )
    measured = follow(
        reference,
        seed,
        channels={
            "current": rng.normal(0.0, 2.0, size=(samples, len(JOINTS))).astype(np.float32),
            "contact_force_n": rng.normal(5.0, 0.5, size=samples),
        },
    )
    return Run(
        name=name,
        reference=reference,
        measured={"real": measured},
        tags=dict(TAGS),
        torques={"real": torque_breakdown(samples, seed)},
    )


def two_runs() -> list[Run]:
    reference = make_reference(0)
    return [make_run(f"rep {index}", reference, seed=index) for index in range(2)]


def copy_of(trajectory: JointTrajectory) -> JointTrajectory:
    """The same content in new objects: a new message over new arrays."""
    buffer = io.BytesIO()
    save_npz(trajectory, buffer)
    buffer.seek(0)
    return load_npz(buffer)


def write(runs: list[Run], output: Path, **options: Any) -> Path:
    return write_dataset_report(runs, output, title="Files on disk", drill_down="lazy", **options)


# ── reading what was written ─────────────────────────────────────────────────


@pytest.fixture
def no_pyarrow(monkeypatch):
    """pyarrow made unimportable for one test (``import pyarrow`` raises ModuleNotFoundError); never uninstalled."""
    hide_pyarrow(monkeypatch)


def hide_pyarrow(monkeypatch) -> None:
    for name in ("pyarrow", "pyarrow.parquet"):
        monkeypatch.setitem(sys.modules, name, None)


def files_under(directory: Path) -> dict[str, str]:
    """Every file below ``directory`` by its posix path, to the SHA-1 of its bytes."""
    return {
        path.relative_to(directory).as_posix(): hashlib.sha1(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def row_files(output: Path) -> set[str]:
    return {name for name in (JSON_ROWS, PARQUET_ROWS) if (output / name).exists()}


def json_rows(output: Path) -> list[dict[str, Any]]:
    return json.loads((output / JSON_ROWS).read_text("utf-8"))


def run_manifests(output: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    """Every ``runs/*/manifest.json`` on disk, by run name, with its folder."""
    found = {}
    for path in sorted((output / "runs").glob("*/manifest.json")):
        manifest = json.loads(path.read_text("utf-8"))
        found[manifest["name"]] = (path.parent, manifest)
    return found


def reference_files(output: Path) -> list[Path]:
    return sorted((output / "references").glob("*.npz"))


def named_reference(folder: Path, manifest: dict[str, Any]) -> Path:
    """The file a manifest's ``files.reference`` names, resolved against its run folder."""
    return (folder / manifest["files"]["reference"]).resolve()


def reference_storage(output: Path) -> set[Path]:
    named = {named_reference(folder, manifest) for folder, manifest in run_manifests(output).values()}
    return named | {path.resolve() for path in reference_files(output)} | {
        path.resolve() for path in (output / "runs").glob("*/reference.npz")
    }


def assert_references_consistent(output: Path) -> None:
    """C6's two halves: every manifest on disk names a reference that exists, and every references/*.npz is named."""
    named = set()
    for name, (folder, manifest) in run_manifests(output).items():
        path = named_reference(folder, manifest)
        assert path.is_file(), f"run {name!r} names {manifest['files']['reference']!r}, which does not exist"
        named.add(path)
    orphans = [path.name for path in reference_files(output) if path.resolve() not in named]
    assert not orphans, f"references/ holds files no manifest names: {orphans}"


def undeflated_members(path: Path) -> list[tuple[str, int]]:
    """The zip members of an .npz that are NOT ZIP_DEFLATED (np.savez stores them, np.savez_compressed deflates)."""
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
    return [(info.filename, info.compress_type) for info in members if info.compress_type != zipfile.ZIP_DEFLATED]


def _resolved(tree: Any, arrays: dict[str, np.ndarray]) -> Any:
    """A robot_msgs npz tree with every ``{"npz": key}`` replaced by its array."""
    if isinstance(tree, dict):
        if set(tree) == {"npz"}:
            return arrays[tree["npz"]]
        return {key: _resolved(value, arrays) for key, value in tree.items()}
    if isinstance(tree, list):
        return [_resolved(value, arrays) for value in tree]
    return tree


def saved_content(message: Any) -> Any:
    """What robot_msgs saves for a message: its JSON tree with every array in place."""
    arrays: dict[str, np.ndarray] = {}
    tree = json.loads(json.dumps(to_dict(message, arrays=arrays)))
    return _resolved(tree, arrays)


def archive_content(path: Path) -> Any:
    """The same, read back raw with ``np.load`` (no robot_msgs)."""
    with np.load(path, allow_pickle=False) as archive:
        assert "__msg__" in archive.files, f"{path.name} is not in robot_msgs's npz layout (no __msg__)"
        tree = json.loads(str(archive["__msg__"]))
        arrays = {key: archive[key] for key in archive.files if key != "__msg__"}
    return _resolved(tree, arrays)


def assert_bit_identical(actual: Any, expected: Any, where: str) -> None:
    if isinstance(expected, np.ndarray):
        assert isinstance(actual, np.ndarray), f"{where}: a {type(actual).__name__}, expected an array"
        assert (actual.dtype, actual.shape) == (expected.dtype, expected.shape), (
            f"{where}: {actual.dtype} {actual.shape}, expected {expected.dtype} {expected.shape}"
        )
        assert actual.tobytes() == expected.tobytes(), f"{where}: the values are not bit-identical"
    elif isinstance(expected, dict):
        assert isinstance(actual, dict) and set(actual) == set(expected), f"{where}: {actual!r}, expected keys {sorted(expected)}"
        for key, value in expected.items():
            assert_bit_identical(actual[key], value, f"{where}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), f"{where}: {actual!r}, expected {expected!r}"
        for index, (got, want) in enumerate(zip(actual, expected, strict=True)):
            assert_bit_identical(got, want, f"{where}[{index}]")
    else:
        assert type(actual) is type(expected) and actual == expected, f"{where}: {actual!r}, expected {expected!r}"


def compressed_size(message: Any) -> int:
    """The bytes of ``message`` saved as robot_msgs's npz layout through ``np.savez_compressed``."""
    arrays: dict[str, np.ndarray] = {}
    tree = to_dict(message, arrays=arrays)
    buffer = io.BytesIO()
    np.savez_compressed(buffer, __msg__=np.array(json.dumps(tree)), **arrays)
    return buffer.getbuffer().nbytes


def report_payload(report: Path) -> dict[str, Any]:
    match = re.search(r'id="traj-compare-data">(.*?)</script>', report.read_text("utf-8"), re.S)
    assert match, f"{report} has no run-view payload"
    return json.loads(match.group(1).replace("<\\/", "</"))


# ── C2. Row files ────────────────────────────────────────────────────────────


def test_rows_default_writes_json_and_parquet_when_pyarrow_imports(tmp_path):
    """Pins today's behaviour (``rows=None``)."""
    pytest.importorskip("pyarrow")
    write(two_runs(), tmp_path)
    assert row_files(tmp_path) == BOTH_ROWS


def test_rows_default_without_pyarrow_writes_json_only(tmp_path, no_pyarrow):
    """Pins today's behaviour (``rows=None``): no pyarrow is no parquet, and no error."""
    write(two_runs(), tmp_path)
    assert row_files(tmp_path) == {JSON_ROWS}


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ((), set()),
        (("json",), {JSON_ROWS}),
        (("parquet",), {PARQUET_ROWS}),
        (("json", "parquet"), BOTH_ROWS),
        (("parquet", "json"), BOTH_ROWS),
        (["parquet"], {PARQUET_ROWS}),
    ],
    ids=["neither", "json", "parquet", "both", "both-reordered", "a-list"],
)
def test_rows_writes_exactly_the_chosen_row_files(tmp_path, rows, expected):
    pytest.importorskip("pyarrow")
    write(two_runs(), tmp_path, rows=rows)
    assert row_files(tmp_path) == expected
    assert (tmp_path / "index.html").is_file() and run_manifests(tmp_path)  # the rest of the site is written regardless


def test_json_rows_need_no_pyarrow(tmp_path, no_pyarrow):
    write(two_runs(), tmp_path, rows=("json",))
    assert row_files(tmp_path) == {JSON_ROWS}


@pytest.mark.parametrize("rows", [("csv",), ("json", "xlsx")], ids=["unknown", "known-and-unknown"])
def test_an_unknown_row_file_raises_value_error_before_any_file_is_written(tmp_path, rows):
    output = tmp_path / "site"
    output.mkdir()
    with pytest.raises(ValueError):
        write(two_runs(), output, rows=rows)
    assert files_under(output) == {}


@pytest.mark.parametrize("rows", [("parquet",), ("json", "parquet")], ids=["parquet", "both"])
def test_parquet_without_pyarrow_raises_module_not_found_before_any_file_is_written(tmp_path, no_pyarrow, rows):
    output = tmp_path / "site"
    output.mkdir()
    with pytest.raises(ModuleNotFoundError):
        write(two_runs(), output, rows=rows)
    assert files_under(output) == {}


def test_a_refused_row_choice_leaves_an_earlier_site_exactly_as_it_was(tmp_path, monkeypatch):
    pytest.importorskip("pyarrow")
    write(two_runs(), tmp_path, rows=("json", "parquet"))
    before = files_under(tmp_path)
    # WHY other data: a refused write of the same runs could rewrite byte-identical files and go unseen.
    other = [make_run("another run", make_reference(4), seed=9)]
    with pytest.raises(ValueError):
        write(other, tmp_path, rows=("csv",))
    assert files_under(tmp_path) == before, "an unknown row file name changed the site before it was refused"
    hide_pyarrow(monkeypatch)
    with pytest.raises(ModuleNotFoundError):
        write(other, tmp_path, rows=("parquet",))
    assert files_under(tmp_path) == before, "parquet without pyarrow changed the site before it was refused"


def test_a_row_file_not_chosen_this_time_is_deleted(tmp_path):
    pytest.importorskip("pyarrow")
    runs = two_runs()
    for rows, expected in (
        (("json", "parquet"), BOTH_ROWS),
        (("json",), {JSON_ROWS}),
        (("parquet",), {PARQUET_ROWS}),
        ((), set()),
        (None, BOTH_ROWS),
    ):
        write(runs, tmp_path, rows=rows)
        assert row_files(tmp_path) == expected, f"after a write with rows={rows!r}"


def test_the_default_without_pyarrow_deletes_the_parquet_an_earlier_write_left(tmp_path, monkeypatch):
    """``rows=None`` without pyarrow does not choose parquet, so a stale rows.parquet must not outlive its data."""
    pytest.importorskip("pyarrow")
    runs = two_runs()
    write(runs, tmp_path)  # rows.parquet and rows.json (the default with pyarrow, pinned above)
    hide_pyarrow(monkeypatch)
    write(runs[:1], tmp_path)
    assert not (tmp_path / PARQUET_ROWS).exists(), "the earlier write's rows.parquet outlived its data"
    assert {row["run"] for row in json_rows(tmp_path)} == {runs[0].name}


def test_parquet_holds_the_json_rows_row_for_row(tmp_path):
    parquet = pytest.importorskip("pyarrow.parquet")
    write(two_runs(), tmp_path, rows=("json", "parquet"))
    rows = json_rows(tmp_path)
    table = parquet.read_table(tmp_path / PARQUET_ROWS)
    assert rows and all(list(row) == ROW_COLUMNS for row in rows), "rows.json's columns changed"
    assert table.column_names == ROW_COLUMNS, "rows.parquet's columns changed"
    assert table.to_pylist() == rows


def test_a_chosen_row_file_holds_the_same_rows_as_the_default(tmp_path):
    parquet = pytest.importorskip("pyarrow.parquet")
    runs = two_runs()
    write(runs, tmp_path / "default")
    write(runs, tmp_path / "json", rows=("json",))
    write(runs, tmp_path / "parquet", rows=("parquet",))
    assert (tmp_path / "json" / JSON_ROWS).read_bytes() == (tmp_path / "default" / JSON_ROWS).read_bytes()
    chosen = parquet.read_table(tmp_path / "parquet" / PARQUET_ROWS)
    assert chosen.equals(parquet.read_table(tmp_path / "default" / PARQUET_ROWS))


# ── C6. One reference per distinct reference ─────────────────────────────────


def test_one_reference_file_per_distinct_reference(tmp_path):
    runs = build_runs()  # 15 runs over 3 targets; every run of a target shares one reference object
    write(runs, tmp_path / "shared")
    names = {path.name for path in reference_files(tmp_path / "shared")}
    assert len(names) == len(TARGETS), f"{len(runs)} runs over {len(TARGETS)} references wrote {sorted(names)}"
    assert all(re.fullmatch(r"[0-9a-f]{12,40}\.npz", name) for name in names), sorted(names)
    # The same content in new objects (every run its own copy) is still one file per distinct reference.
    copies = [dataclasses.replace(run, reference=copy_of(run.reference)) for run in runs]
    write(copies, tmp_path / "copies")
    assert {path.name for path in reference_files(tmp_path / "copies")} == names


def _same_content(reference: JointTrajectory) -> JointTrajectory:
    return copy_of(reference)


def _other_velocities(reference: JointTrajectory) -> JointTrajectory:
    return reference.replace(velocities=reference.velocities * 1.5)


def _one_sample_one_ulp(reference: JointTrajectory) -> JointTrajectory:
    positions = np.array(reference.positions)
    positions[100, 0] = np.nextafter(positions[100, 0], np.inf)
    return reference.replace(positions=positions)


def _other_frame(reference: JointTrajectory) -> JointTrajectory:
    return reference.replace(header=Header(frame_id="world"))


def _one_more_channel(reference: JointTrajectory) -> JointTrajectory:
    return reference.replace(channels={"setpoint_index": np.arange(len(reference.t), dtype=float)})


@pytest.mark.parametrize(
    ("change", "expected_files"),
    [
        (_same_content, 1),
        (_other_velocities, 2),
        (_one_sample_one_ulp, 2),
        (_other_frame, 2),
        (_one_more_channel, 2),
    ],
    ids=["same-content-new-objects", "only-velocities", "one-sample-one-ulp", "only-header-frame", "one-more-channel"],
)
def test_references_differing_anywhere_are_two_files(tmp_path, change, expected_files):
    first = make_reference(0, velocities=True)
    second = change(first)
    write([make_run("first", first, seed=1), make_run("second", second, seed=2)], tmp_path)
    names = [path.name for path in reference_files(tmp_path)]
    assert len(names) == expected_files, f"expected {expected_files} references/*.npz, found {names}"
    manifests = run_manifests(tmp_path)
    for run, reference in (("first", first), ("second", second)):
        stored = load_npz(named_reference(*manifests[run]))
        assert_bit_identical(saved_content(stored), saved_content(reference), f"{run}'s stored reference")


def test_a_reference_file_is_named_by_its_content_not_by_the_write(tmp_path):
    references = [make_reference(variant) for variant in range(3)]
    runs = [make_run(f"rep {index}", references[index % 3], seed=index) for index in range(6)]
    write(runs, tmp_path / "forward")
    write(list(reversed(runs)), tmp_path / "reversed")
    names = {path.name for path in reference_files(tmp_path / "forward")}
    assert len(names) == 3, f"6 runs over 3 references wrote references/ {sorted(names)}"
    assert {path.name for path in reference_files(tmp_path / "reversed")} == names


def test_a_manifest_names_its_reference_under_references(tmp_path):
    references = [make_reference(variant) for variant in range(3)]
    runs = [make_run(f"rep {index}", references[index % 3], seed=index) for index in range(6)]
    write(runs, tmp_path)
    manifests = run_manifests(tmp_path)
    named: dict[str, Path] = {}
    for run in runs:
        folder, manifest = manifests[run.name]
        relative = manifest["files"]["reference"]
        assert REFERENCE_PATH.fullmatch(relative), f"{run.name}: files.reference is {relative!r}"
        path = named_reference(folder, manifest)
        assert path.parent == (tmp_path / "references").resolve() and path.is_file(), path
        assert not (folder / "reference.npz").exists(), f"{run.name}: runs/{folder.name}/reference.npz was written"
        assert_bit_identical(saved_content(load_npz(path)), saved_content(run.reference), f"{run.name}'s reference")
        named[run.name] = path
    for first in runs:
        for second in runs:
            same_file = named[first.name] == named[second.name]
            assert same_file == (first.reference is second.reference), (first.name, second.name)
    assert not list((tmp_path / "runs").glob("*/reference.npz"))


def test_a_run_whose_reference_is_shared_builds_its_drill_down(tmp_path):
    reference = make_reference(0)
    runs = [make_run(f"rep {index}", reference, seed=index) for index in range(3)]
    write(runs, tmp_path)
    manifests = run_manifests(tmp_path)
    shared = {named_reference(*manifests[run.name]) for run in runs}
    assert len(shared) == 1, f"three runs over one reference name {len(shared)} files: {sorted(map(str, shared))}"
    assert next(iter(shared)).parent == (tmp_path / "references").resolve()
    for run in runs[:2]:
        report = build_drill_down(tmp_path, run.name)
        assert report == manifests[run.name][0] / "report.html" and report.is_file()
        assert len(report_payload(report)["comparisons"]) == len(run.resolved_pairs())


def test_an_orphaned_reference_is_deleted_after_a_write(tmp_path):
    first, second, third = (make_reference(variant) for variant in range(3))
    write([make_run("rep a", first), make_run("rep b", second, 1), make_run("rep c", third, 2)], tmp_path)
    before = {path.name for path in reference_files(tmp_path)}
    assert len(before) == 3, f"3 runs over 3 references wrote references/ {sorted(before)}"
    # The same runs again, now over two of the three references: the third's file is named by no manifest.
    write([make_run("rep a", first), make_run("rep b", first, 1), make_run("rep c", second, 2)], tmp_path)
    after = {path.name for path in reference_files(tmp_path)}
    assert len(after) == 2 and after < before, (sorted(before), sorted(after))
    assert_references_consistent(tmp_path)


def test_a_reference_file_no_manifest_names_is_deleted(tmp_path):
    stray = tmp_path / "references" / "0123456789abcdef0123456789abcdef01234567.npz"
    stray.parent.mkdir(parents=True)
    other = make_reference(5)
    arrays: dict[str, np.ndarray] = {}
    tree = to_dict(other, arrays=arrays)
    np.savez_compressed(stray, __msg__=np.array(json.dumps(tree)), **arrays)  # a valid reference of no run
    write(two_runs(), tmp_path)
    assert not stray.exists(), "a references/*.npz that no manifest names outlived the write"
    assert len(reference_files(tmp_path)) == 1
    assert_references_consistent(tmp_path)


def test_rewriting_with_fewer_runs_leaves_no_manifest_without_its_reference(tmp_path):
    references = [make_reference(variant) for variant in range(3)]
    runs = [make_run(f"rep {index}", references[index], seed=index) for index in range(3)]
    write(runs, tmp_path)
    write(runs[:1], tmp_path)
    folder, manifest = run_manifests(tmp_path)[runs[0].name]
    assert REFERENCE_PATH.fullmatch(manifest["files"]["reference"]), f"files.reference is {manifest['files']['reference']!r}"
    assert_references_consistent(tmp_path)
    for name in run_manifests(tmp_path):  # whatever run folders are left on disk still build
        assert build_drill_down(tmp_path, name).is_file()


def test_an_old_style_run_folder_still_builds(tmp_path):
    reference = make_reference(0)
    runs = [make_run(f"rep {index}", reference, seed=index, torques=True) for index in range(2)]
    write(runs, tmp_path)
    folder, manifest = run_manifests(tmp_path)[runs[0].name]
    assert REFERENCE_PATH.fullmatch(manifest["files"]["reference"]), "the site is not new-style"
    # A folder as written before 2026-11-20, in this otherwise new-style site: reference.npz beside the series and
    # every .npz uncompressed (robot_msgs.save_npz, np.savez), its manifest naming "reference.npz".
    legacy = folder.with_name(f"{folder.name}-legacy")
    shutil.copytree(folder, legacy)
    for name, relative in manifest["files"].items():
        if name != "reference":
            save_npz(load_npz(legacy / relative), legacy / relative)
    for series, keys in manifest["torques"].items():
        path = legacy / f"{series}.torques.npz"
        with np.load(path, allow_pickle=False) as stored:
            parts = {key: stored[key] for key in keys}
        np.savez(path, **parts)
    save_npz(reference, legacy / "reference.npz")
    old = {
        **manifest,
        "name": "rep 0 (written 2026-11-19)",
        "slug": legacy.name,
        "files": {**manifest["files"], "reference": "reference.npz"},
    }
    (legacy / "manifest.json").write_text(json.dumps(old, indent=2) + "\n", encoding="utf-8")
    report = build_drill_down(tmp_path, old["name"])
    assert report == legacy / "report.html" and report.is_file()
    assert len(report_payload(report)["comparisons"]) == len(old["pairs"])


# ── C6. Every .npz compressed, values bit-identical ──────────────────────────


def test_every_npz_the_dataset_writes_is_compressed(tmp_path):
    runs = [instrumented_run(), make_run("plain", make_reference(0))]
    write(runs, tmp_path)
    written = sorted(tmp_path.rglob("*.npz"))
    stored = {path.relative_to(tmp_path).as_posix(): members for path in written if (members := undeflated_members(path))}
    assert not stored, f"stored, not deflated (np.savez, not np.savez_compressed): {stored}"
    # Not vacuous: the files checked include both references, both series and the torque breakdown.
    manifests = run_manifests(tmp_path)
    kinds: set[Path] = set()
    for folder, manifest in manifests.values():
        kinds.add(named_reference(folder, manifest))
        kinds |= {(folder / manifest["files"][series]).resolve() for series in manifest["series"]}
    kinds.add((manifests["instrumented"][0] / "real.torques.npz").resolve())
    assert len(kinds) == 2 + 2 + 1, sorted(map(str, kinds))
    assert kinds <= {path.resolve() for path in written}


def test_saved_values_are_bit_identical_through_load_npz_and_np_load(tmp_path):
    run = instrumented_run()
    write([run], tmp_path)
    folder, manifest = run_manifests(tmp_path)[run.name]
    reference_path = named_reference(folder, manifest)
    assert reference_path.parent == (tmp_path / "references").resolve(), f"files.reference is {manifest['files']['reference']!r}"
    for name, message in {"reference": run.reference, **run.measured}.items():
        path = reference_path if name == "reference" else folder / manifest["files"][name]
        assert_bit_identical(saved_content(load_npz(path)), saved_content(message), f"load_npz({name})")
        assert_bit_identical(archive_content(path), saved_content(message), f"np.load({name})")
    series = load_npz(folder / manifest["files"]["real"])
    assert series.channels["current"].dtype == np.float32
    assert series.channels["contact_force_n"].dtype == np.float64
    with np.load(folder / "real.torques.npz", allow_pickle=False) as stored:
        assert set(stored.files) == set(run.torques["real"])
        for key, values in run.torques["real"].items():
            assert_bit_identical(stored[key], values, f"real.torques.npz[{key}]")


def test_fifty_runs_over_five_references_store_about_five_compressed_references(tmp_path):
    references = [make_reference(variant, samples=1001, velocities=True) for variant in range(5)]
    runs = [make_run(f"rep {index:02d}", references[index % 5], seed=index) for index in range(50)]
    write(runs, tmp_path)
    one_reference = max(compressed_size(reference) for reference in references)
    stored = sum(path.stat().st_size for path in reference_storage(tmp_path))
    limit = 5 * one_reference * 1.05
    assert stored <= limit, f"references take {stored} bytes on disk; 5 compressed references are {5 * one_reference}"
