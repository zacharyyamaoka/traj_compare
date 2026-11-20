"""Parquet and MCAP carry a situation's recorded channels too (NAVIGATION.md C1; export.py is a projection of the payload).

Written by the dispatcher beside its change, 2026-11-20: before it, a contact force the run view drew was missing from both
exports.
"""

import numpy as np
import pytest

from traj_compare import Comparison, Situation

pq = pytest.importorskip("pyarrow.parquet")
mcap_reader = pytest.importorskip("mcap.reader")


def _comparison() -> Comparison:
    import traj_compare

    t = np.linspace(0.0, 1.0, 101)
    q = np.column_stack([np.sin(t), np.cos(t)])
    force = np.column_stack([t, 2 * t, 3 * t])
    return Comparison(
        title="Export channels",
        name="export_channels",
        joint_names=["a", "b"],
        target=Situation(name="target", t=t, q=q),
        situations=[Situation(name="real", t=t, q=q + 0.01, channels={"contact_force": force, "residual": t ** 2})],
        signals={"contact_force": traj_compare.Signal(title="Contact force", unit="N", columns=("x", "y", "z"))},
    )


def test_parquet_rows_hold_every_recorded_channel_column(tmp_path):
    from traj_compare.export import write_parquet

    rows = pq.read_table(write_parquet(_comparison(), tmp_path / "c.parquet")).to_pylist()
    real = [row for row in rows if row["situation"] == "real"]
    force = [row for row in real if row["channel"] == "channels/contact_force"]
    assert sorted({row["column"] for row in force}) == ["x", "y", "z"]
    z = sorted((row for row in force if row["column"] == "z"), key=lambda row: row["t"])
    np.testing.assert_allclose([row["value"] for row in z], [3 * row["t"] for row in z], atol=1e-3)
    assert {row["column"] for row in real if row["channel"] == "channels/residual"} == {""}


def test_mcap_has_one_topic_per_recorded_channel(tmp_path):
    from traj_compare.export import write_mcap

    path = write_mcap(_comparison(), tmp_path / "c.mcap")
    with open(path, "rb") as stream:
        topics = {channel.topic for channel in mcap_reader.make_reader(stream).get_summary().channels.values()}
    assert "/traj_compare/real/channels/contact_force" in topics
    assert "/traj_compare/real/channels/residual" in topics
