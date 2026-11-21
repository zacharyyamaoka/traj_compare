"""Incremental writes (acceptance, written before the code, 2026-11-20).

The contract is docs/NAVIGATION.md **Part D: incremental writes** (frozen @ bfbcba2). Source: arm_motion_bench lane V,
where adding 818 runs to a 5,750-run site rewrote all 5,750 (about 6 min, then Ctrl-C). D1 reuses a run whose digest
matches, D1b a target whose key matches, D2 writes every file under a temporary name and renames it into place (so the
bench's hard-linked staging copy, ``cp -al live staging``, never touches live), D3 reports progress. The data is
tests/incremental_fixture.py. These tests are the implementing lane's ruler: it must not edit this file or the fixture.

Readings of the contract this file pins (the places it is not literal):

- **Rewritten / untouched** is file identity. A rewritten file has another ``(st_ino, st_mtime_ns)``; an untouched one
  keeps its bytes, inode and ``mtime_ns``. A reused run's folder keeps every file as it was, none added or removed. A
  rewritten run's lazily built drill-down (``report.html`` and ``rerun/``) is deleted, as before Part D ("its files are
  written as before"); where only file identity is under test, the tests stand a placeholder in for that drill-down.
- **Equivalent** (D1's "reuse changes nothing in the output") is read as: the index payload minus ``generated``,
  ``write_id``, ``serve_command`` and ``command_template``, key by key; ``rows.json`` parsed; ``rows.parquet``'s column
  names and ``to_pylist()``; the set of ``targets/*.js`` and each byte for byte; and for every run of this write, its
  ``manifest.json`` parsed (its ``digest`` included), every ``*.npz`` in its folder member by member (key, dtype, shape,
  bytes), every media file its manifest names byte for byte, and the reference its manifest names. Run folders of runs
  not in the write, and the references only they name, are left out: D1 keeps them.
- **Counting.** ``traj_compare.dataset.compare`` and ``traj_compare.dataset.estimate_time_offset`` are counted by
  wrapping those module attributes (dataset.py imports them by name); every counting test first proves its wrapper sees
  a fresh write's calls, so code that bypasses the wrapper fails loudly instead of passing at zero. The poses function
  counts its own calls (``incremental_fixture.POSES_CALLS``). A call is told to be for a target by the sample count of
  the trajectories it is handed: every target of the fixture has its own.
- **``reuse`` defaults to true** (the contract's signature reads ``reuse=True``): the same-runs-again and hard-linked-copy
  tests pass no ``reuse``.
- **D3's phases** come in the order the contract lists them (runs, reused, targets, index, then drill for eager), and
  each phase's ``(done, total)`` sequence is exactly the contract's, so ``done`` never decreases.
- **D2's "whole-old or whole-new"**: after a stopped write every ``*.json`` parses, every ``*.npz`` loads, and no
  ``*.tmp`` is left anywhere.
- **A reuse=False write in between** must leave no target cache a later ``reuse=True`` write could match against a
  ``.js`` it did not write (pinned black-box: that later write equals a fresh one).

Not covered here: ``robot=`` (no ``RobotDisplay`` in the fixture), ``data_ui``, the ``export`` files, and edits to the
installed traj_compare / robot_msgs sources (a test must not edit the package it tests).

Run (the arm may be powered: CPUs and load are limited, one pytest at a time):

    flock /tmp/claude-1000/traj-tc-heavy.lock taskset -c 2-5,16,17 nice -n 19 env -u VIRTUAL_ENV \\
        /home/bam/traj_compare/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_incremental_writes.py
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from incremental_fixture import (
    BASE,
    CLIP_MTIME_NS,
    EXTRA,
    LATE,
    POSES_CALLS,
    POSES_LONG,
    PROBE,
    SOLO,
    build_runs,
    make_clip,
    samples_of,
    signals,
    target_of,
    tolerances,
    write_options,
)

import traj_compare.dataset as dataset
from traj_compare import Run, build_drill_down, write_dataset_report

pytestmark = [
    pytest.mark.filterwarnings(f"ignore:{LATE}:UserWarning"),  # the fixture's no-overlap pairs, on purpose
    pytest.mark.filterwarnings("ignore:.*Rerun cannot read the video:UserWarning"),  # the clip is stand-in bytes
]

VOLATILE = ("generated", "write_id", "serve_command", "command_template")  # D1: per write, never compared
TARGET_SLUGS = ("reach", "wave", "swing")
WAVE_RUNS = tuple(name for name in BASE if target_of(name) == "wave")
SERIES_FILE = "sim.npz"  # every run's sim series: the file whose identity says a run was rewritten
STAND_IN = "<!-- a drill-down an earlier build left (stand-in) -->\n"
HAS_RERUN = importlib.util.find_spec("rerun") is not None
HEX40 = re.compile(r"[0-9a-f]{40}")


# ── writing ──────────────────────────────────────────────────────────────────


def write(runs: Sequence[Run], out: Path, **overrides: Any) -> Path:
    return write_dataset_report(runs, out, **write_options(**overrides))


def fresh_write(runs: Sequence[Run], out: Path, **overrides: Any) -> Path:
    """D1's yardstick: a ``reuse=False`` write of ``runs`` into an empty folder."""
    assert not out.exists() or not any(out.iterdir()), f"{out} is not empty"
    return write(runs, out, **{**overrides, "reuse": False})


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def folder_of(out: Path, name: str) -> Path:
    return out / "runs" / slug(name)


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> Path:
    return make_clip(tmp_path_factory.mktemp("media"))


@pytest.fixture(scope="module")
def fresh(tmp_path_factory, clip) -> Path:
    """The base runs written ``reuse=False`` into an empty folder: what every incremental write of them must equal."""
    out = tmp_path_factory.mktemp("fresh") / "site"
    fresh_write(build_runs(clip), out)
    return out


# ── changing one ingredient ──────────────────────────────────────────────────


def nudged(values: Any, index: Any, by: float) -> np.ndarray:
    copy = np.array(values, dtype=float, copy=True)
    copy[index] += by
    return copy


def with_run(runs: Sequence[Run], name: str, change: Callable[[Run], Run]) -> list[Run]:
    assert any(run.name == name for run in runs), name
    return [change(run) if run.name == name else run for run in runs]


def with_series(run: Run, series: str, **fields: Any) -> Run:
    return dataclasses.replace(run, measured={**run.measured, series: run.measured[series].replace(**fields)})


def sample_value(run: Run) -> Run:
    return with_series(run, "sim", positions=nudged(run.measured["sim"].positions, (20, 0), 1e-3))


def channel_value(run: Run) -> Run:
    real = run.measured["real"]
    return with_series(run, "real", channels={**real.channels, "grip_force": nudged(real.channels["grip_force"], 10, 0.5)})


def tag_value(run: Run) -> Run:
    return dataclasses.replace(run, tags={**run.tags, "speed": 0.75})


def title(run: Run) -> Run:
    return dataclasses.replace(run, title=f"{run.title} (retaken)")


def time_offset(run: Run) -> Run:
    return dataclasses.replace(run, time_offset_s={"real": 0.003})


def torques(run: Run) -> Run:
    given = run.torques["real"]
    return dataclasses.replace(run, torques={"real": {**given, "tau_fb": given["tau_fb"] * 1.1}})


def pairs(run: Run) -> Run:
    return dataclasses.replace(run, pairs=[("reference", "sim"), ("reference", "real")])


def media_start(run: Run) -> Run:
    return dataclasses.replace(run, media_start_s={"real": 0.2})


def wave_reference(runs: list[Run]) -> list[Run]:
    """One target's reference changed (one sample, one joint): every run that follows it, and only those."""
    old = next(run.reference for run in runs if target_of(run.name) == "wave")
    new = old.replace(positions=nudged(old.positions, (30, 1), 1e-3))
    return [dataclasses.replace(run, reference=new) if target_of(run.name) == "wave" else run for run in runs]


def touch_clip(clip: Path) -> None:
    """The media file's mtime moves (same bytes): a digest covers (key, size, mtime_ns), not the bytes."""
    later = CLIP_MTIME_NS + 1_000_000_000
    os.utime(clip, ns=(later, later))


# ── reading what was written ─────────────────────────────────────────────────

Stamp = tuple[str, int, int]  # (SHA-1 of the bytes, st_ino, st_mtime_ns)


def stamp(path: Path) -> Stamp:
    status = path.stat()
    return hashlib.sha1(path.read_bytes()).hexdigest(), status.st_ino, status.st_mtime_ns


def stamps(root: Path, under: str = "") -> dict[str, Stamp]:
    """Every file below ``root / under`` by its posix path relative to ``root``."""
    base = root / under if under else root
    if not base.exists():
        return {}
    return {path.relative_to(root).as_posix(): stamp(path) for path in sorted(base.rglob("*")) if path.is_file()}


def identity(value: Stamp | None) -> tuple[int, int] | None:
    return None if value is None else (value[1], value[2])


def changed_files(before: dict[str, Stamp], after: dict[str, Stamp]) -> list[str]:
    """Every path added, removed, or whose bytes, inode or mtime_ns moved."""
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def run_stamps(out: Path, names: Iterable[str]) -> dict[str, dict[str, Stamp]]:
    return {name: stamps(out, f"runs/{slug(name)}") for name in names}


def assert_reused(out: Path, before: dict[str, dict[str, Stamp]], names: Iterable[str]) -> None:
    for name in names:
        changes = changed_files(before[name], stamps(out, f"runs/{slug(name)}"))
        assert not changes, f"run {name!r} did not change, so its folder must be left as it was; changed: {changes}"


def assert_rewritten(out: Path, before: dict[str, dict[str, Stamp]], names: Iterable[str]) -> None:
    for name in names:
        folder = f"runs/{slug(name)}"
        after = stamps(out, folder)
        for file in (SERIES_FILE, "manifest.json"):
            path = f"{folder}/{file}"
            assert path in after, f"run {name!r} was to be rewritten, but {path} is missing"
            assert identity(after[path]) != identity(before[name].get(path)), f"run {name!r} changed, but {path} was not rewritten"


def stand_in_drill_downs(out: Path, names: Iterable[str]) -> None:
    """A placeholder for a lazily built drill-down in each run folder: a ``report.html`` and one ``rerun/`` file."""
    for name in names:
        folder = folder_of(out, name)
        (folder / "report.html").write_text(STAND_IN, encoding="utf-8")
        (folder / "rerun").mkdir(exist_ok=True)
        (folder / "rerun" / "reference--sim.rrd").write_bytes(b"stand-in")


def target_stamps(out: Path) -> dict[str, Stamp]:
    return stamps(out, "targets")


def temp_files(*roots: Path) -> list[str]:
    return sorted(str(path) for root in roots for path in root.rglob("*.tmp"))


def assert_whole_files(root: Path) -> None:
    """D2: every file is whole, old or new: each ``*.json`` parses and each ``*.npz`` loads, member by member."""
    for path in sorted(root.rglob("*.json")):
        try:
            json.loads(path.read_text("utf-8"))
        except ValueError as error:
            pytest.fail(f"{path.relative_to(root)} is not whole JSON after a stopped write: {error}")
    for path in sorted(root.rglob("*.npz")):
        try:
            with np.load(path, allow_pickle=False) as archive:
                for key in archive.files:
                    archive[key]
        except Exception as error:  # noqa: BLE001 - any failure to read it back is a torn file
            pytest.fail(f"{path.relative_to(root)} does not load after a stopped write: {error!r}")


def dataset_payload(out: Path) -> dict[str, Any]:
    text = (out / "index.html").read_text("utf-8")
    match = re.search(r'<script type="application/json" id="traj-compare-dataset">(.*?)</script>', text, re.S)
    assert match, "index.html has no dataset payload"
    return json.loads(match.group(1).replace("<\\/", "</"))


def sha1_of(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def npz_members(path: Path) -> dict[str, tuple[str, tuple[int, ...], str]]:
    with np.load(path, allow_pickle=False) as archive:
        return {
            key: (archive[key].dtype.str, archive[key].shape, hashlib.sha1(archive[key].tobytes()).hexdigest())
            for key in archive.files
        }


def site_view(out: Path, runs: Sequence[Run]) -> dict[str, Any]:
    """What D1 says must not depend on reuse (see the module docstring)."""
    payload = dataset_payload(out)
    for key in VOLATILE:
        payload.pop(key, None)
    view: dict[str, Any] = {"payload": payload, "rows.json": json.loads((out / "rows.json").read_text("utf-8"))}
    view["rows.parquet"] = None
    if (out / "rows.parquet").exists():
        import pyarrow.parquet as parquet

        table = parquet.read_table(out / "rows.parquet")
        view["rows.parquet"] = (table.column_names, table.to_pylist())
    view["targets"] = {path.name: sha1_of(path) for path in sorted((out / "targets").glob("*.js"))}
    view["runs"], view["references"] = {}, {}
    for run in runs:
        folder = folder_of(out, run.name)
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        files: dict[str, Any] = {path.name: npz_members(path) for path in sorted(folder.glob("*.npz"))}
        for relative in manifest["media"].values():
            files[relative] = sha1_of(folder / relative)
        reference = manifest["files"]["reference"]
        view["references"][reference] = npz_members(folder / reference)
        view["runs"][run.name] = {"manifest": manifest, "files": files}
    return view


def assert_equivalent(expected_out: Path, out: Path, runs: Sequence[Run]) -> None:
    """``out`` holds what a fresh ``reuse=False`` write of ``runs`` (``expected_out``) holds (D1)."""
    expected, actual = site_view(expected_out, runs), site_view(out, runs)
    for key in sorted(set(expected["payload"]) | set(actual["payload"])):
        assert actual["payload"].get(key) == expected["payload"].get(key), (
            f"index payload {key!r} differs from a fresh reuse=False write of the same runs"
        )
    for part in ("rows.json", "rows.parquet", "targets", "references"):
        assert actual[part] == expected[part], f"{part} differs from a fresh reuse=False write of the same runs"
    for name, wanted in expected["runs"].items():
        got = actual["runs"][name]
        assert got["manifest"] == wanted["manifest"], f"runs/{slug(name)}/manifest.json differs from a fresh write"
        assert got["files"] == wanted["files"], f"runs/{slug(name)}/'s npz or media differ from a fresh write"


# ── counting calls ───────────────────────────────────────────────────────────


@dataclass
class Calls:
    """Every call of ``traj_compare.dataset.compare`` / ``estimate_time_offset``: the sample counts of its trajectories."""

    compare: list[tuple[int, ...]] = field(default_factory=list)
    estimate_time_offset: list[tuple[int, ...]] = field(default_factory=list)

    def clear(self) -> None:
        self.compare.clear()
        self.estimate_time_offset.clear()
        POSES_CALLS.clear()

    @staticmethod
    def lengths(calls: Sequence[tuple[int, ...]]) -> set[int]:
        return {length for call in calls for length in call}


@pytest.fixture
def counted(monkeypatch) -> Calls:
    calls = Calls()
    for name in ("compare", "estimate_time_offset"):
        log, original = getattr(calls, name), getattr(dataset, name)

        def counting(*args: Any, _original: Callable = original, _log: list = log, **kwargs: Any) -> Any:
            _log.append(tuple(len(value.t) for value in (*args, *kwargs.values()) if hasattr(value, "t")))
            return _original(*args, **kwargs)

        monkeypatch.setattr(dataset, name, counting)
    calls.clear()
    return calls


def assert_counters_see_a_write(calls: Calls) -> None:
    assert calls.compare and calls.estimate_time_offset, (
        "a fresh write made no call through traj_compare.dataset.compare / estimate_time_offset: the counters this test "
        "relies on no longer see the write's analysis"
    )
    assert POSES_CALLS, "a fresh write never called the poses function"


# ── progress ─────────────────────────────────────────────────────────────────


class StopWrite(Exception):
    """Raised by a progress function: what a Ctrl-C mid-write is to the writer."""


class Progress:
    def __init__(self, stop_at: tuple[str, int, int] | None = None) -> None:
        self.calls: list[tuple[str, int, int]] = []
        self.stop_at = stop_at

    def __call__(self, phase: str, done: int, total: int) -> None:
        self.calls.append((phase, done, total))
        if (phase, done, total) == self.stop_at:
            raise StopWrite(f"stopped at {self.stop_at}")


def expected_progress(runs: int, reused: int, targets: int, drill: bool = False) -> list[tuple[str, int, int]]:
    calls = [("runs", done, runs) for done in range(runs + 1)]
    calls.append(("reused", reused, runs))
    calls += [("targets", done, targets) for done in range(targets + 1)]
    calls += [("index", 0, 1), ("index", 1, 1)]
    if drill:
        calls += [("drill", done, runs) for done in range(runs + 1)]
    return calls


# ── D1: the digest and analysis.json ─────────────────────────────────────────


def test_every_run_folder_holds_its_digest_in_its_manifest_and_its_analysis(tmp_path, clip):
    runs = build_runs(clip)
    out = tmp_path / "site"
    write(runs, out)
    payload = dataset_payload(out)
    tidy_rows = json.loads((out / "rows.json").read_text("utf-8"))
    digests = set()
    for run in runs:
        folder = folder_of(out, run.name)
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        assert HEX40.fullmatch(str(manifest.get("digest"))), f"{run.name}: manifest digest {manifest.get('digest')!r}"
        analysis = json.loads((folder / "analysis.json").read_text("utf-8"))
        assert set(analysis) >= {"digest", "entries", "rows"}
        assert analysis["digest"] == manifest["digest"]
        # entries: the run's entries in the payload's rows, one per pair, error entries included (LATE has two)
        own = [row for row in payload["rows"] if row["run"] == run.name]
        assert len(analysis["entries"]) == len(run.resolved_pairs()) == len(own)
        for entry, row in zip(analysis["entries"], own, strict=True):
            assert {key: entry.get(key) for key in row} == row, f"{run.name}: analysis.json entry differs from the index row"
        assert analysis["rows"] == [row for row in tidy_rows if row["run"] == run.name]
        digests.add(manifest["digest"])
    assert len(digests) == len(runs), "two runs share a digest"
    assert any("error" in entry for entry in json.loads((folder_of(out, LATE) / "analysis.json").read_text())["entries"])


def without(entry: dict[str, Any], key: str) -> dict[str, Any]:
    return {name: value for name, value in entry.items() if name != key}


def test_every_target_holds_its_cache_beside_its_file(tmp_path, clip):
    out = tmp_path / "site"
    write(build_runs(clip), out)
    levels = dataset_payload(out)["levels"]
    assert sorted(target["slug"] for target in levels["targets"]) == sorted(TARGET_SLUGS)
    for target in levels["targets"]:
        path = out / "targets" / f"{target['slug']}.cache.json"
        assert path.is_file(), f"target {target['slug']!r} has no {path.name} beside its .js"
        cache = json.loads(path.read_text("utf-8"))
        assert set(cache) >= {"key", "target", "lines"}
        assert HEX40.fullmatch(str(cache["key"])), cache["key"]
        # D1b: the cached entry is taken before the site-wide has_torque_breakdown pass; a line's order is per write
        assert without(cache["target"], "has_torque_breakdown") == without(target, "has_torque_breakdown")
        own = [without(line, "order") for line in levels["lines"] if line["target"] == target["slug"]]
        assert [without(line, "order") for line in cache["lines"]] == own


def test_the_return_value_is_still_the_path_of_index_html(tmp_path, clip):
    out = tmp_path / "site"
    assert write(build_runs(clip), out, progress=Progress()) == out / "index.html"
    assert write(build_runs(clip), out, reuse=True) == out / "index.html"
    assert write(build_runs(clip), out, reuse=False) == out / "index.html"


# ── D1: reuse changes nothing in the output ──────────────────────────────────


def test_an_incremental_write_equals_a_fresh_reuse_false_write(tmp_path, clip, fresh):
    out = tmp_path / "site"
    # The earlier write: EXTRA first (every later run's order moves by one), two runs missing, two others changed.
    # swing's runs are all there, unchanged and in order, so the final write reuses them and that target.
    earlier = build_runs(clip, [EXTRA, *(name for name in BASE if name not in ("reach pd 2", "wave mpc 2"))])
    earlier = with_run(with_run(earlier, "reach mpc 1", sample_value), PROBE, tag_value)
    write(earlier, out)
    swing = [name for name in BASE if target_of(name) == "swing"]
    before = run_stamps(out, swing)
    swing_file = stamp(out / "targets" / "swing.js")

    final = build_runs(clip)
    write(final, out)
    assert_reused(out, before, swing)
    assert stamp(out / "targets" / "swing.js") == swing_file, "target swing did not change, so its file must not be rewritten"
    assert_equivalent(fresh, out, final)
    assert (folder_of(out, EXTRA) / "manifest.json").is_file(), "a run folder not in this write must stay in place"
    for run in final:
        folder = folder_of(out, run.name)
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        assert json.loads((folder / "analysis.json").read_text("utf-8"))["digest"] == manifest["digest"]


def test_a_reuse_false_write_in_between_leaves_nothing_a_later_write_wrongly_reuses(tmp_path, clip, fresh):
    out = tmp_path / "site"
    write(build_runs(clip), out)
    write(with_run(build_runs(clip), PROBE, sample_value), out, reuse=False, display_hz=25.0)
    write(build_runs(clip), out)
    assert_equivalent(fresh, out, build_runs(clip))


# ── D1: a run that did not change is reused ──────────────────────────────────


def test_writing_the_same_runs_again_rewrites_no_run_or_target_file_and_analyses_nothing(tmp_path, clip, counted):
    out = tmp_path / "site"
    write(build_runs(clip), out)
    assert_counters_see_a_write(counted)
    build_drill_down(out, PROBE)  # a lazily built drill-down, as traj_compare.serve leaves one
    assert (folder_of(out, PROBE) / "report.html").is_file()
    if HAS_RERUN:
        assert list((folder_of(out, PROBE) / "rerun").glob("*.rrd")), "the drill-down wrote no .rrd"
    before = {**stamps(out, "runs"), **target_stamps(out)}
    index_before = stamp(out / "index.html")
    counted.clear()

    write(build_runs(clip), out)  # new Run objects with equal content; reuse is the default

    changes = changed_files(before, {**stamps(out, "runs"), **target_stamps(out)})
    assert not changes, f"the same runs written again changed run or target files: {changes}"
    assert identity(stamp(out / "index.html")) != identity(index_before), "index.html is rewritten by every write"
    assert counted.compare == [], "a reused run or target was compared again"
    assert counted.estimate_time_offset == [], "a reused run's latency was estimated again"
    assert POSES_CALLS == [], "a reused run's poses were computed again"


@dataclass(frozen=True)
class Change:
    runs: Callable[[list[Run]], list[Run]] = lambda runs: runs
    options: dict[str, Any] = field(default_factory=dict)
    on_disk: Callable[[Path], None] | None = None  # handed the clip
    rewrites: tuple[str, ...] = (PROBE,)  # the runs it must rewrite; every other run is reused
    targets: tuple[str, ...] = ("wave",)  # the targets it must rewrite; every other target is reused


def on_probe(change: Callable[[Run], Run]) -> Callable[[list[Run]], list[Run]]:
    return lambda runs: with_run(runs, PROBE, change)


EVERY_RUN = {"rewrites": BASE, "targets": TARGET_SLUGS}
CHANGES = {
    # one ingredient of ONE run (PROBE): that run and its target only
    "sample-value": Change(runs=on_probe(sample_value)),
    "channel-value": Change(runs=on_probe(channel_value)),
    "tag": Change(runs=on_probe(tag_value)),
    "title": Change(runs=on_probe(title)),
    "time-offset": Change(runs=on_probe(time_offset)),
    "torques": Change(runs=on_probe(torques)),
    "pairs": Change(runs=on_probe(pairs)),
    "media-mtime": Change(on_disk=touch_clip),
    "media-start": Change(runs=on_probe(media_start)),
    # one target's reference: every run that follows it
    "reference": Change(runs=wave_reference, rewrites=WAVE_RUNS),
    # a per-run option of the write: every run
    "tolerances": Change(options={"tolerances": tolerances(0.06)}, **EVERY_RUN),
    "signals": Change(options={"signals": signals("Gripper force")}, **EVERY_RUN),
    "primary": Change(options={"primary": {"model": "sim"}}, **EVERY_RUN),
    "poses-spec": Change(options={"poses": POSES_LONG}, **EVERY_RUN),
    "reuse-false": Change(options={"reuse": False}, **EVERY_RUN),
    # site-level only: no run, every target
    "display-hz": Change(options={"display_hz": 25.0}, rewrites=(), targets=TARGET_SLUGS),
    "target-budget": Change(options={"target_budget": 1_999_999}, rewrites=(), targets=TARGET_SLUGS),
}


@pytest.mark.parametrize("case", list(CHANGES), ids=list(CHANGES))
def test_a_change_rewrites_exactly_the_runs_and_targets_its_digest_covers(tmp_path, case):
    change = CHANGES[case]
    clip = make_clip(tmp_path / "media")  # its own: media-mtime moves it
    out = tmp_path / "site"
    write(build_runs(clip), out)
    stand_in_drill_downs(out, BASE)
    before = run_stamps(out, BASE)
    targets_before = target_stamps(out)

    if change.on_disk is not None:
        change.on_disk(clip)
    runs = change.runs(build_runs(clip))
    write(runs, out, **change.options)

    assert_rewritten(out, before, change.rewrites)
    for name in change.rewrites:  # a drill-down cached for the old data is gone
        assert not (folder_of(out, name) / "report.html").exists(), f"run {name!r} changed but kept its old report.html"
        assert not (folder_of(out, name) / "rerun").exists(), f"run {name!r} changed but kept its old rerun/"
    assert_reused(out, before, [name for name in BASE if name not in change.rewrites])
    targets_after = target_stamps(out)
    for target in TARGET_SLUGS:
        files = [f"targets/{target}.js", f"targets/{target}.cache.json"]
        if target in change.targets:
            checked = files if change.options.get("reuse", True) else files[:1]  # reuse=False need not keep a cache
            for path in checked:
                assert path in targets_after, f"{path} is missing"
                assert identity(targets_after[path]) != identity(targets_before.get(path)), f"{path} was not rewritten"
        else:
            for path in files:
                assert targets_after.get(path) == targets_before.get(path), f"{path} did not change, yet was rewritten"
    fresh_write(runs, tmp_path / "fresh", **change.options)
    assert_equivalent(tmp_path / "fresh", out, runs)


EDITABLE_FK = "incremental_editable_fk"
EDITABLE_SOURCE = '''"""A poses module a test edits on disk (tests/test_incremental_writes.py)."""

import numpy as np
from robot_msgs.trajectory import PoseTrajectory


def tool_xy(trajectory):
    q = trajectory.positions
    yaw = q[:, 0] + q[:, 1]
    positions = np.column_stack([0.3 * np.cos(q[:, 0]) + 0.25 * np.cos(yaw), 0.3 * np.sin(q[:, 0]) + 0.25 * np.sin(yaw), 0 * yaw])
    quats = np.column_stack([0 * yaw, 0 * yaw, np.sin(yaw / 2), np.cos(yaw / 2)])
    return PoseTrajectory(t=trajectory.t, positions=positions, orientations=quats, child_frame_id="tool", header=trajectory.header)
'''


def test_editing_the_poses_module_on_disk_rewrites_every_run(tmp_path, clip, monkeypatch):
    module = tmp_path / "fk" / f"{EDITABLE_FK}.py"
    module.parent.mkdir()
    module.write_text(EDITABLE_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(module.parent))
    monkeypatch.delitem(sys.modules, EDITABLE_FK, raising=False)  # and removed again after the test
    out = tmp_path / "site"
    options = {"poses": f"{EDITABLE_FK}:tool_xy"}
    write(build_runs(clip), out, **options)
    before = run_stamps(out, BASE)
    write(build_runs(clip), out, **options)
    assert_reused(out, before, BASE)  # the control: the same module, the same runs, nothing rewritten

    # WHY a comment is enough: the digest covers the module's file, not what the edit means
    module.write_text(EDITABLE_SOURCE + "\n# edited: a cache that outlives a code change serves stale numbers\n", "utf-8")
    write(build_runs(clip), out, **options)
    assert_rewritten(out, before, BASE)


# ── D1b: a target that did not change is reused ──────────────────────────────


def test_a_changed_run_recomputes_its_own_target_and_no_other(tmp_path, clip, counted):
    out = tmp_path / "site"
    write(build_runs(clip), out)
    assert_counters_see_a_write(counted)
    targets_before = target_stamps(out)
    counted.clear()

    write(with_run(build_runs(clip), PROBE, sample_value), out)

    wave = samples_of("wave")
    assert POSES_CALLS, "PROBE changed, so its poses (and its target's) are computed"
    assert set(POSES_CALLS) == {wave}, f"poses computed for trajectories of {sorted(set(POSES_CALLS))} samples; only wave's ({wave})"
    assert counted.compare and Calls.lengths(counted.compare) == {wave}, (
        f"compare called on {sorted(Calls.lengths(counted.compare))}-sample trajectories; only wave's ({wave}) changed"
    )
    assert counted.estimate_time_offset and Calls.lengths(counted.estimate_time_offset) == {wave}
    targets_after = target_stamps(out)
    for target in ("reach", "swing"):
        for path in (f"targets/{target}.js", f"targets/{target}.cache.json"):
            assert path in targets_before and targets_after.get(path) == targets_before[path], f"{path} was rewritten"


# ── D1: when a run is reused (its three conditions) ──────────────────────────


def _delete_series(out: Path) -> None:
    (folder_of(out, PROBE) / "real.npz").unlink()


def _delete_media_copy(out: Path) -> None:
    (folder_of(out, PROBE) / "media" / "real.mp4").unlink()


def _corrupt_analysis(out: Path) -> None:
    path = folder_of(out, PROBE) / "analysis.json"
    path.write_text(path.read_text("utf-8")[:20], encoding="utf-8")


def _other_digest_in_analysis(out: Path) -> None:
    path = folder_of(out, PROBE) / "analysis.json"
    analysis = json.loads(path.read_text("utf-8"))
    analysis["digest"] = "0" * 40
    path.write_text(json.dumps(analysis), encoding="utf-8")


PRECONDITIONS = {
    "series-npz-deleted": _delete_series,
    "media-copy-deleted": _delete_media_copy,
    "analysis-corrupt": _corrupt_analysis,
    "analysis-digest-differs": _other_digest_in_analysis,
}


@pytest.mark.parametrize("case", list(PRECONDITIONS), ids=list(PRECONDITIONS))
def test_a_run_whose_folder_fails_a_reuse_condition_is_rewritten(tmp_path, clip, fresh, case):
    out = tmp_path / "site"
    write(build_runs(clip), out)
    before = run_stamps(out, BASE)
    PRECONDITIONS[case](out)

    write(build_runs(clip), out)

    folder = f"runs/{slug(PROBE)}"
    after = stamps(out, folder)
    assert f"{folder}/manifest.json" in after and identity(after[f"{folder}/manifest.json"]) != identity(
        before[PROBE][f"{folder}/manifest.json"]
    ), f"{case}: PROBE's folder cannot be reused, yet its manifest was not rewritten"
    assert_reused(out, before, [name for name in BASE if name != PROBE])
    assert_equivalent(fresh, out, build_runs(clip))


def test_a_deleted_shared_reference_is_written_again(tmp_path, clip, fresh):
    """Every wave run's manifest names this reference; which of them are rewritten is not pinned, only the output."""
    out = tmp_path / "site"
    write(build_runs(clip), out)
    manifest = json.loads((folder_of(out, PROBE) / "manifest.json").read_text("utf-8"))
    reference = (folder_of(out, PROBE) / manifest["files"]["reference"]).resolve()
    reference.unlink()
    write(build_runs(clip), out)
    assert reference.is_file()
    assert_equivalent(fresh, out, build_runs(clip))


def test_a_reused_run_whose_pair_errors_warns_again(tmp_path, clip):
    out = tmp_path / "site"
    with pytest.warns(UserWarning, match=f"^{LATE}: ") as first:
        write(build_runs(clip), out)
    before = run_stamps(out, [LATE])
    with pytest.warns(UserWarning, match=f"^{LATE}: ") as again:
        write(build_runs(clip), out)
    assert_reused(out, before, [LATE])

    def messages(record) -> list[str]:
        return sorted(str(warning.message) for warning in record if str(warning.message).startswith(f"{LATE}: "))

    assert len(messages(first)) == 2  # (reference, real) and (sim, real) never overlap
    assert messages(again) == messages(first)


# ── D2: a hard-linked copy (the bench's cp -al live staging) ─────────────────


def hard_linked_copy(source: Path, destination: Path) -> None:
    """``cp -al``: every directory made anew, every file a second name for the same inode."""
    destination.mkdir()
    for path in sorted(source.rglob("*")):
        target = destination / path.relative_to(source)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(path, target)


def test_writing_into_a_hard_linked_copy_leaves_the_original_untouched(tmp_path, clip):
    live, staging = tmp_path / "live", tmp_path / "staging"
    write(build_runs(clip, (*BASE, SOLO)), live)  # SOLO is target solo's only run
    reused = "reach pd 1"  # reused by the staging write, with its drill-down
    for name in (reused, PROBE):
        build_drill_down(live, name)
    if HAS_RERUN:
        assert list((folder_of(live, PROBE) / "rerun").glob("*.rrd")), "the live drill-down wrote no .rrd"
    live_before = stamps(live)
    hard_linked_copy(live, staging)

    # one run changed, one new, one dropped (and with it target solo)
    runs = with_run(build_runs(clip, (*BASE, EXTRA)), PROBE, sample_value)
    write(runs, staging)
    changes = changed_files(live_before, stamps(live))
    assert not changes, f"an incremental write into the hard-linked copy changed live files: {changes}"
    for path in (SERIES_FILE, "report.html"):
        shared = folder_of(staging, reused) / path
        assert shared.is_file(), f"{reused} was reused, yet staging lost its {path}"
        assert shared.stat().st_ino == (folder_of(live, reused) / path).stat().st_ino, (
            f"{reused}'s {path} was reused, so staging and live must still share its inode"
        )
    for path in ("targets/solo.js", "targets/solo.cache.json"):
        assert not (staging / path).exists(), f"staging's {path} outlived its target"
    build_drill_down(staging, PROBE)  # the changed run's drill-down, built lazily in the copy
    build_drill_down(staging, reused)  # and one rebuilt over files the copy shares with live
    if HAS_RERUN:
        assert list((folder_of(staging, PROBE) / "rerun").glob("*.rrd")), "the staging drill-down wrote no .rrd"

    changes = changed_files(live_before, stamps(live))
    assert not changes, f"a drill-down built in the hard-linked copy changed live files: {changes}"
    assert not temp_files(live, staging), "a temporary file outlived its write"
    fresh_write(runs, tmp_path / "fresh")
    assert_equivalent(tmp_path / "fresh", staging, runs)


# ── D2 / D3: a stopped write ─────────────────────────────────────────────────


def test_a_write_stopped_by_its_progress_function_leaves_the_old_index_and_the_next_write_is_correct(tmp_path, clip):
    out = tmp_path / "site"
    write(build_runs(clip), out)
    index_before = (out / "index.html").read_bytes()
    runs = with_run(with_run(build_runs(clip), "reach pd 1", sample_value), PROBE, channel_value)
    stop = Progress(stop_at=("runs", 3, len(runs)))
    with pytest.raises(StopWrite):
        write(runs, out, progress=stop)
    assert stop.calls[-1] == ("runs", 3, len(runs))
    assert (out / "index.html").read_bytes() == index_before, "a stopped write replaced index.html"
    assert not temp_files(out), "a stopped write left a temporary file"
    assert_whole_files(out)

    write(runs, out)
    fresh_write(runs, tmp_path / "fresh")
    assert_equivalent(tmp_path / "fresh", out, runs)


def test_a_write_that_fails_inside_a_run_leaves_nothing_half_written_to_reuse(tmp_path):
    """PROBE changes and its media "file" is now a directory, so its write fails partway; the next write is of the
    ORIGINAL runs.

    WHY a directory, not a missing file: a directory still has a size and an mtime, so a digest can be taken and the
    run's folder is rewritten until the media copy refuses it (today: after its series .npz are written). A folder left
    with its old manifest and analysis.json beside new data would then be reused, wrongly: D1 deletes the manifest
    first and writes it last."""
    clip = make_clip(tmp_path / "media")
    out = tmp_path / "site"
    write(build_runs(clip), out)
    index_before = (out / "index.html").read_bytes()
    changed = with_run(build_runs(clip), PROBE, sample_value)
    clip.unlink()
    clip.mkdir()
    with pytest.raises(OSError):  # today FileNotFoundError ("media ... is not a file"); IsADirectoryError would do
        write(changed, out)
    assert (out / "index.html").read_bytes() == index_before
    assert not temp_files(out)
    assert_whole_files(out)

    clip.rmdir()
    clip = make_clip(tmp_path / "media")  # the same clip again: same bytes, same mtime_ns
    write(build_runs(clip), out)
    fresh_write(build_runs(clip), tmp_path / "fresh")
    assert_equivalent(tmp_path / "fresh", out, build_runs(clip))


# ── D3: progress ─────────────────────────────────────────────────────────────


def test_progress_reports_every_phase_in_order_with_the_number_reused(tmp_path, clip):
    out = tmp_path / "site"
    write(build_runs(clip), out)
    runs = with_run(build_runs(clip, (*BASE, EXTRA)), PROBE, sample_value)  # 11 runs: one changed, one new
    progress = Progress()
    write(runs, out, progress=progress)
    assert progress.calls == expected_progress(len(runs), reused=len(runs) - 2, targets=len(TARGET_SLUGS))


def test_eager_progress_drills_every_run_and_rebuilds_only_the_rewritten_ones(tmp_path, clip):
    names = ("reach pd 1", "reach pd 2", "reach mpc 1")
    out = tmp_path / "site"
    write(build_runs(clip, names), out, drill_down="eager")
    before = run_stamps(out, names)
    report = f"runs/{slug('reach pd 2')}/report.html"
    assert report in before[names[1]]

    progress = Progress()
    write(with_run(build_runs(clip, names), "reach pd 2", sample_value), out, drill_down="eager", progress=progress)

    assert progress.calls == expected_progress(3, reused=2, targets=1, drill=True)
    assert_reused(out, before, ["reach pd 1", "reach mpc 1"])  # their report.html (and .rrd) are not rebuilt
    rebuilt = out / report
    assert rebuilt.is_file(), "the rewritten run's drill-down was not rebuilt"
    assert identity(stamp(rebuilt)) != identity(before[names[1]][report]), "the rewritten run kept its old report.html"
