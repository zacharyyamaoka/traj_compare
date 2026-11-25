"""rows.json / rows.parquet without every tidy row held as a dict (arm_motion_bench, 2026-11-21).

WHY: the bench's pendulum site holds 7,782 traces in 4,804 runs, and its rebuild peaked 10.24 GiB under its 11 GiB cap. A
rebuild reuses almost every run, and write_dataset_report read each reused run's tidy rows back from its analysis.json and
held all of them (2.24 M rows, 2.9 KB each once parsed) until rows.parquet was written: about 60 % of the peak, then about
34 % for building every column of that file at once.

What this file pins:

- ``_RowSink`` holds a run's rows as codes, and ``_write_rows`` writes rows.json and rows.parquet from it with the bytes the
  dict writer wrote (``_dict_writer`` below is that writer as it was at 44f5123, the oracle), over every kind of value a
  row can hold: None, int, float, bool, -0.0, NaN, the list ``pair``, a tag only some runs have, a tag whose type differs
  between runs (written as text), 1 / 1.0 / True kept apart, a tag named like a row field, a key missing from some rows,
  a column that varies inside a run, and more than one 1 Mi-row row group.
- A reuse write's Python heap peak does not grow by a run's rows per run.

Run:

    cd /home/bam/traj_compare
    env -u VIRTUAL_ENV .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_rows_stream.py
"""

from __future__ import annotations

import json
import math
import tracemalloc
from pathlib import Path

import pytest

from traj_compare import dataset

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")


def _dict_writer(output_dir: Path, rows: list[dict], files: frozenset[str]) -> None:
    """traj_compare.dataset._write_rows as it was at 44f5123 (every row a dict, every column built at once): the oracle."""
    if "json" in files:
        (output_dir / "rows.json").write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    if "parquet" in files:
        columns = list(dict.fromkeys(key for row in rows for key in row))
        arrays = {}
        for column in columns:
            values = [row.get(column) for row in rows]
            try:
                arrays[column] = pa.array(values)
            except (pa.ArrowInvalid, pa.ArrowTypeError):
                arrays[column] = pa.array([None if value is None else str(value) for value in values])
        with open(output_dir / "rows.parquet", "xb") as handle:
            pq.write_table(pa.table(arrays), handle)


def _rows(run: str, tags: dict, values: list, *, pairs=(("reference", "real"),), units=("rad",)) -> list[dict]:
    """One run's tidy rows in _analyze_run's layout: {run, pair, metric, stat, value, unit, **tags}."""
    rows = []
    for pair in pairs:
        base = {"run": run, "pair": list(pair)}
        for index, value in enumerate(values):
            unit = units[index % len(units)]
            rows.append({**base, "metric": f"m{index % 3}", "stat": ("rms", "max", "mean")[index % 3], "value": value, "unit": unit,
                         **tags})
    return rows


CASES = {
    "plain": [
        _rows("a", {"rig": "ur", "can": 13, "speed": 0.5, "held_out": False}, [0.1, 0.2, 0.3], pairs=[("reference", "sim"), ("sim", "real")]),
        _rows("b", {"rig": "fb", "can": 11, "speed": 1.0, "held_out": True}, [1.5, None, 2.5]),
    ],
    "value kinds: None, int, float, bool, -0.0, nan": [
        _rows("a", {"t": "x"}, [None, 1, 2.5, -0.0, 0.0, float("nan"), True, False]),
    ],
    "value: ints only, with None": [_rows("a", {"t": "x"}, [1, 2, None, -7]), _rows("b", {"t": "y"}, [2**40, 0])],
    "value: ints beyond a double's exact range beside floats": [_rows("a", {"t": "x"}, [1.5, 2**53 + 1])],
    "a tag whose type differs between runs (text)": [_rows("a", {"t": "x", "n": 1}, [0.1]), _rows("b", {"t": 2, "n": 2.5}, [0.2])],
    "1, 1.0 and True kept apart": [_rows("a", {"k": 1}, [0.1]), _rows("b", {"k": 1.0}, [0.2]), _rows("c", {"k": True}, [0.3])],
    "0.0 and -0.0 kept apart in a tag": [_rows("a", {"k": 0.0}, [0.1]), _rows("b", {"k": -0.0}, [0.2])],
    "per-row units of every kind": [_rows("a", {"t": "x"}, [0.1, 0.2, 0.3, 0.4, 0.5], units=("rad", "", 0.0, -0.0, 1))],
    "units 1 / 1.0 / True": [_rows("a", {"t": "x"}, [0.1, 0.2, 0.3], units=(1, 1.0, True))],
    "a tag only some runs have": [_rows("a", {"t": "x"}, [0.1]), _rows("b", {"t": "y", "extra": "only b"}, [0.2]),
                                  _rows("c", {"extra": 3.0, "t": "z"}, [0.3])],
    "a tag named like a row field": [_rows("a", {"unit": "tagged", "t": "x"}, [0.1, 0.2])],
    "a run with no rows, then one with": [[], _rows("b", {"t": "y"}, [0.2])],
    "a key missing from some rows": [[{"run": "a", "pair": ["reference", "real"], "metric": "m", "stat": "rms", "value": 0.1, "t": "x"},
                                      {"run": "a", "pair": ["reference", "real"], "metric": "m", "stat": "max", "value": 0.2, "unit": "rad",
                                       "t": "x"}]],
    "a column that varies inside a run": [[{**row, "joint": f"j{index}"} for index, row in enumerate(_rows("a", {"t": "x"}, [0.1, 0.2, 0.3]))]],
    "key order differs between runs": [_rows("a", {"x": 1, "y": "p"}, [0.1]), _rows("b", {"y": "q", "x": 2}, [0.2])],
    "a tag whose value is a long string": [_rows(f"r{i}", {"target": "workspace-dev-000 · workspace-v2 · 0.5 × reference motion speed "
                                                           f"({i} deg/s)" * 3}, [0.1 * i, 0.2]) for i in range(5)],
    "no runs": [],
}


def _sink_of(runs: list[list[dict]]):
    sink = dataset._RowSink()
    for rows in runs:
        sink.add_run(rows)
    return sink


@pytest.mark.parametrize("name", list(CASES))
def test_the_streamed_row_files_are_the_dict_writers_bytes(tmp_path, name):
    runs = CASES[name]
    rows = [row for run in runs for row in run]
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    files = frozenset({"json", "parquet"})
    _dict_writer(tmp_path / "old", rows, files)
    sink = _sink_of(runs)
    assert len(sink) == len(rows)
    dataset._write_rows(tmp_path / "new", sink, files)
    for file in ("rows.json", "rows.parquet"):
        assert (tmp_path / "new" / file).read_bytes() == (tmp_path / "old" / file).read_bytes(), file


def test_more_than_one_row_group_is_the_dict_writers_bytes(tmp_path):
    """1 Mi rows is pyarrow's default row group (pq.write_table's own split): 1,100,000 rows make two, as before."""
    run = _rows("a", {"target": "workspace-dev-000 · workspace-v2 · 0.5 × speed", "repeat": 3, "speed": 0.5},
                [0.001 * k for k in range(550)] + [None] * 550)
    runs = [run] * 1000  # the same dicts again: cheap to hold for the oracle
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    _dict_writer(tmp_path / "old", [row for rows in runs for row in rows], frozenset({"parquet"}))
    dataset._write_rows(tmp_path / "new", _sink_of(runs), frozenset({"parquet"}))
    assert pq.read_metadata(tmp_path / "old" / "rows.parquet").num_row_groups == 2
    assert (tmp_path / "new" / "rows.parquet").read_bytes() == (tmp_path / "old" / "rows.parquet").read_bytes()


def test_a_row_file_not_chosen_is_deleted(tmp_path):
    for file in ("rows.json", "rows.parquet"):
        (tmp_path / file).write_text("stale")
    dataset._write_rows(tmp_path, _sink_of(CASES["plain"]), frozenset({"json"}))
    assert not (tmp_path / "rows.parquet").exists() and json.loads((tmp_path / "rows.json").read_text())
    dataset._write_rows(tmp_path, _sink_of(CASES["plain"]), frozenset())
    assert not (tmp_path / "rows.json").exists()


def test_a_reuse_write_does_not_hold_every_runs_rows(tmp_path):
    """A write that reuses every run must not grow its Python heap peak by a run's rows per run.

    Measured on these runs (3 pairs, 13 tags, 123 rows a run): at 44f5123 the peak grew 417 KiB per added run; the bound,
    100 KiB per run, is under a quarter of that. The runs themselves are made before tracing starts, so what is measured is
    write_dataset_report's own retention."""
    from test_dataset_files import follow, make_reference

    from traj_compare import Run, write_dataset_report

    tags = {f"tag_{k:02d}": f"a long-ish tag value number {k} · repeated on every row" for k in range(12)}
    references = [make_reference(variant) for variant in range(4)]

    def runs(count: int) -> list[Run]:
        return [Run(name=f"run-{i:03d}", reference=references[i % 4], tags={**tags, "seed": i},
                    measured={"sim": follow(references[i % 4], i), "real": follow(references[i % 4], i + 1000)},
                    pairs=[("reference", "sim"), ("reference", "real"), ("sim", "real")]) for i in range(count)]

    # WHY the lower peak of two reuse writes (2026-11-25, CI 3.11 at 5e13af2): one 3755 KiB allocation at pathlib.py:71,
    # sys.intern, landed in the 40-run window: the interpreter's interned-string table resizing, once, after every test
    # before this one had filled it, and read as 177 KiB a run. The second write cannot meet that resize again (the table
    # just doubled), and a write that holds every run's rows peaks as high on both, so the bound below still catches it.
    peaks = {}
    for count in (10, 40):
        written = runs(count)
        write_dataset_report(written, tmp_path / f"n{count}", title="t", rows=("parquet",))  # fresh
        started_here = not tracemalloc.is_tracing()
        if started_here:
            tracemalloc.start(1)
        try:
            for _ in range(2):
                tracemalloc.reset_peak()
                write_dataset_report(written, tmp_path / f"n{count}", title="t", rows=("parquet",))  # every run reused
                peak = tracemalloc.get_traced_memory()[1]
                peaks[count] = min(peaks.get(count, peak), peak)
        finally:
            if started_here:
                tracemalloc.stop()
    per_run_kib = (peaks[40] - peaks[10]) / 30 / 1024
    assert math.isfinite(per_run_kib) and per_run_kib < 100, f"the reuse write's peak grows {per_run_kib:.0f} KiB per run ({peaks})"
