"""Files other viewers open: Parquet (tidy rows) and MCAP (PlotJuggler / Foxglove), written before the code.

Prior-art item 10 (2026-11-10): Rerun, PlotJuggler, Foxglove and LeRobot all read columnar or
MCAP logs; exporting the comparison lets them overlay runs without recomputing anything. Both
are projections of the same analysis payload as the HTML and the .rrd. Read-back goes through
the stock readers (pyarrow, mcap), never our writer.
"""

import json

import numpy as np
import pytest

from traj_compare import Comparison, Situation, write_comparison_report
from traj_compare.analysis import analyze_comparison

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")
mcap_reader = pytest.importorskip("mcap.reader")

from traj_compare.export import write_mcap, write_parquet  # noqa: E402

from test_report import extract_payload  # noqa: E402


def translation_fk(q: np.ndarray) -> np.ndarray:
    poses = np.tile(np.eye(4), (len(q), 1, 1))
    poses[:, :2, 3] = q
    return poses


def belt() -> Comparison:
    t = np.linspace(0.0, 2.0, 201)
    q = np.column_stack([0.3 * t, 0.1 * np.sin(np.pi * t)])
    return Comparison(
        title="Belt pick",
        joint_names=["j1", "j2"],
        target=Situation(name="target", title="Target", t=t, q=q),
        situations=[
            Situation(name="sim", title="Sim", t=t, q=q + [0.002, 0.0]),
            Situation(name="real", title="Real", t=t, q=q + [0.0, -0.003]),
        ],
        fk=translation_fk,
    )


def test_parquet_is_tidy_rows_equal_to_the_payload(tmp_path):
    comparison = belt()
    path = write_parquet(comparison, tmp_path / "belt.parquet")
    table = pq.read_table(path)
    for column in ("comparison", "situation", "reference", "channel", "column", "t", "value"):
        assert column in table.column_names
    data = table.to_pydict()
    picks = [
        index
        for index in range(table.num_rows)
        if data["situation"][index] == "real"
        and data["channel"][index] == "err_q"
        and data["column"][index] == "j2"
    ]
    assert picks, "real j2 joint error missing"
    values = np.array([data["value"][index] for index in picks], dtype=float)
    np.testing.assert_allclose(values[np.isfinite(values)], 0.003, atol=1e-12)  # target - run
    assert set(data["reference"]) == {"target"}


def test_mcap_has_one_json_topic_per_situation_channel(tmp_path):
    path = write_mcap(belt(), tmp_path / "belt.mcap")
    with open(path, "rb") as stream:
        reader = mcap_reader.make_reader(stream)
        summary = reader.get_summary()
        topics = {channel.topic for channel in summary.channels.values()}
        assert "/traj_compare/real/err_q" in topics
        assert "/traj_compare/sim/q" in topics
        assert all(channel.message_encoding == "json" for channel in summary.channels.values())
        messages = [
            json.loads(message.data)
            for _schema, channel, message in reader.iter_messages(topics=["/traj_compare/real/err_q"])
        ]
    assert len(messages) > 100
    first = messages[0]
    assert set(first) >= {"t", "j1", "j2"}
    assert first["j2"] == pytest.approx(0.003)
    # log time is the sample time, in ns, so PlotJuggler / Foxglove line runs up on one clock
    assert messages[1]["t"] > first["t"]


def test_report_exports_flag_writes_both_and_links_them(tmp_path):
    report = write_comparison_report([belt()], tmp_path, exports=True)
    page = extract_payload(report.read_text("utf-8"))["comparisons"][0]
    files = page["exports"]
    assert (tmp_path / files["parquet"]).is_file()
    assert (tmp_path / files["mcap"]).is_file()
    assert "Parquet" in report.read_text("utf-8") and "MCAP" in report.read_text("utf-8")


def test_exports_off_by_default(tmp_path):
    report = write_comparison_report([belt()], tmp_path)
    assert extract_payload(report.read_text("utf-8"))["comparisons"][0].get("exports") is None
    assert analyze_comparison(belt()).get("exports") is None
