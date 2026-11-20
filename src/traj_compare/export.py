"""The Parquet and MCAP projections: one comparison -> one columnar file and one message log.

WHY (prior-art item 10, 2026-11-10): Rerun, PlotJuggler, Foxglove and LeRobot all read columnar or MCAP
logs, so exporting the comparison lets them overlay runs without recomputing anything. Like the HTML
and the .rrd, both files are projections of the ``analyze_comparison`` payload (never recomputed, never
scraped from HTML), so the numbers match the report, which in turn are ``robot_msgs.compare``'s.

Both files share one clock: ``t`` is seconds from the comparison start (the reference's first sample,
as in the .rrd), on the payload's plot grid. A channel is a payload plot key; a column is a joint name
(q, qd, qdd, tau, current, tau_cmd, tau_ff, tau_fb, err_q), an ``error_axes`` label (err_axes) or ""
for a scalar channel.

Parquet: tidy long rows ``comparison, situation, reference, channel, column, t, value`` (NaN where the
payload has null); the target's rows carry its own name as ``reference``.

MCAP: JSON messages, a jsonschema schema per topic ``/traj_compare/<situation>/<channel>``, one message
per plot-grid sample ``{"t": seconds, "<column>": value, ...}`` with log time = publish time = t in
integer nanoseconds. A scalar channel's one field is called ``value``. Null samples are left out of the
message; a sample with no value at all writes no message. ``/traj_compare/metrics`` holds one message
with every situation's error statistics, so the numbers travel with the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .analysis import analyze_comparison
from .model import Comparison
from .rerun_export import _reference_start

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ModuleNotFoundError as error:  # the core report works without the extra; only this module needs it
    if error.name != "pyarrow":
        raise
    pa = pq = None
try:
    from mcap.writer import Writer as McapWriter
except ModuleNotFoundError as error:
    if error.name != "mcap":
        raise
    McapWriter = None

METRICS_TOPIC = "/traj_compare/metrics"
SCALAR_COLUMN = "value"  # the field of a one-column channel in an MCAP message
_NS = 1_000_000_000


def _require(module: Any, name: str) -> None:
    if module is None:
        raise ImportError(
            f"this export needs {name}; install the 'export' extra "
            f"(pip install 'traj-compare[export]', or uv run --extra export)"
        )


def _array(values: list | None) -> np.ndarray:
    """Payload columns carry null outside a run's own span; the files want NaN for the gap."""

    return np.array([np.nan if value is None else value for value in values], dtype=float)


def _reference_name(payload: dict[str, Any]) -> str:
    for entry in payload["situations"]:
        if entry["role"] == "target":
            return entry["name"]
    return ""


def _channels(payload: dict[str, Any], entry: dict[str, Any]) -> list[tuple[str, list[tuple[str, np.ndarray]]]]:
    """A situation's plot as ``(channel, [(column, values)])`` in the payload's own order, then its recorded channels.

    WHY the recorded channels too (NAVIGATION.md C1, 2026-11-20): Parquet and MCAP are projections of the same payload,
    so a contact force the run view draws must not vanish from the export. They are named ``channels/<name>``, so a
    recorded channel can never collide with a joint signal such as ``q``; columns are ``Comparison.signals``' labels.
    """
    plot = entry["plot"]

    columns_of = {
        "err_axes": payload["error_axes"],
        **{key: payload["joint_names"]
           for key in ("q", "qd", "qdd", "tau", "current", "tau_cmd", "tau_ff", "tau_fb", "err_q")},
    }
    channels = []
    for channel, series in plot.items():
        if series is None:
            continue
        if series and isinstance(series[0], list):
            names = columns_of[channel]
            channels.append((channel, [(str(name), _array(values)) for name, values in zip(names, series, strict=True)]))
        else:
            channels.append((channel, [("", _array(series))]))
    described = {descriptor["name"]: descriptor for descriptor in payload.get("channels") or []}
    for name, columns in (entry.get("channels") or {}).items():
        labels = (described.get(name) or {}).get("columns") or []
        if len(labels) != len(columns):  # a 1-D channel is one unnamed column, as the run view's scalar series
            labels = [""] if len(columns) == 1 else [str(index) for index in range(len(columns))]
        channels.append((f"channels/{name}", [(str(label), _array(values)) for label, values in zip(labels, columns, strict=True)]))
    return channels


def _prepared(comparison: Comparison, payload: dict[str, Any] | None) -> tuple[dict[str, Any], np.ndarray]:
    if payload is None:
        payload = analyze_comparison(comparison)
    if payload["plot_t"] is None:
        return payload, np.zeros(0)
    return payload, _array(payload["plot_t"]) - _reference_start(comparison)


def write_parquet(comparison: Comparison, path: Path | str, *, payload: dict[str, Any] | None = None) -> Path:
    """Write ``comparison`` as tidy long rows in one Parquet file and return its path.

    ``payload`` is an already-computed ``analyze_comparison`` result so a report that writes
    several files does not analyze twice; omitted, it is computed here.
    """

    _require(pa, "pyarrow")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload, time_s = _prepared(comparison, payload)
    reference = _reference_name(payload)

    pieces: dict[str, list] = {key: [] for key in ("situation", "reference", "channel", "column", "t", "value")}
    for entry in payload["situations"]:
        if not entry["has_data"] or entry["plot"] is None:
            continue
        own_reference = entry["name"] if entry["role"] == "target" else reference
        for channel, columns in _channels(payload, entry):
            for column, values in columns:
                count = len(time_s)
                pieces["situation"].append(np.full(count, entry["name"], dtype=object))
                pieces["reference"].append(np.full(count, own_reference, dtype=object))
                pieces["channel"].append(np.full(count, channel, dtype=object))
                pieces["column"].append(np.full(count, column, dtype=object))
                pieces["t"].append(time_s)
                pieces["value"].append(values)

    def joined(key: str, dtype: Any) -> np.ndarray:
        return np.concatenate(pieces[key]) if pieces[key] else np.zeros(0, dtype=dtype)

    rows = len(joined("t", float))
    table = pa.table(
        {
            "comparison": pa.array([comparison.name] * rows, type=pa.string()),
            "situation": pa.array(joined("situation", object), type=pa.string()),
            "reference": pa.array(joined("reference", object), type=pa.string()),
            "channel": pa.array(joined("channel", object), type=pa.string()),
            "column": pa.array(joined("column", object), type=pa.string()),
            "t": pa.array(joined("t", float), type=pa.float64()),
            "value": pa.array(joined("value", float), type=pa.float64()),
        }
    )
    pq.write_table(table, path, compression="zstd")
    return path


def _schema(columns: list[str]) -> bytes:
    fields = [SCALAR_COLUMN if column == "" else column for column in columns]
    schema = {
        "type": "object",
        "properties": {
            "t": {"type": "number", "description": "seconds from the comparison start"},
            **{field: {"type": "number"} for field in fields},
        },
        "required": ["t"],
    }
    return json.dumps(schema).encode()


def _metrics_message(payload: dict[str, Any], comparison: Comparison) -> dict[str, Any]:
    return {
        "comparison": comparison.name,
        "title": comparison.title,
        "reference": _reference_name(payload),
        "joint_names": list(payload["joint_names"]),
        "tcp_frame": payload["tcp_frame"],
        "situations": {
            entry["name"]: entry["error_metrics"]
            for entry in payload["situations"]
            if entry["error_metrics"] is not None
        },
    }


def write_mcap(comparison: Comparison, path: Path | str, *, payload: dict[str, Any] | None = None) -> Path:
    """Write ``comparison`` as one MCAP file of JSON messages and return its path.

    ``payload`` is an already-computed ``analyze_comparison`` result; omitted, it is computed here.
    """

    _require(McapWriter, "mcap")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload, time_s = _prepared(comparison, payload)
    log_time = np.rint(time_s * _NS).astype(np.int64)

    with open(path, "wb") as stream:
        writer = McapWriter(stream)
        writer.start(profile="", library="traj_compare")
        topics = []  # (channel id, field names, (samples, fields) values)
        for entry in payload["situations"]:
            if not entry["has_data"] or entry["plot"] is None:
                continue
            for channel, columns in _channels(payload, entry):
                names = [column for column, _ in columns]
                topic = f"/traj_compare/{entry['name']}/{channel}"
                schema_id = writer.register_schema(
                    name=f"traj_compare/{channel}", encoding="jsonschema", data=_schema(names)
                )
                channel_id = writer.register_channel(
                    topic=topic, message_encoding="json", schema_id=schema_id
                )
                fields = [SCALAR_COLUMN if name == "" else name for name in names]
                topics.append((channel_id, fields, np.column_stack([values for _, values in columns])))

        metrics_schema = writer.register_schema(
            name="traj_compare/metrics", encoding="jsonschema",
            data=json.dumps({"type": "object"}).encode(),
        )  # fmt: skip
        metrics_channel = writer.register_channel(
            topic=METRICS_TOPIC, message_encoding="json", schema_id=metrics_schema
        )
        writer.add_message(
            channel_id=metrics_channel, log_time=0, publish_time=0, sequence=0,
            data=json.dumps(_metrics_message(payload, comparison)).encode(),
        )  # fmt: skip

        # Sample-major so the file is in log-time order for streaming readers.
        for sample, nanos in enumerate(log_time):
            for channel_id, fields, values in topics:
                row = values[sample]
                present = np.isfinite(row)
                if not present.any():
                    continue
                message = {"t": float(time_s[sample])}
                message.update({f: float(v) for f, v, ok in zip(fields, row, present, strict=True) if ok})
                writer.add_message(
                    channel_id=channel_id, log_time=int(nanos), publish_time=int(nanos),
                    sequence=sample, data=json.dumps(message).encode(),
                )  # fmt: skip
        writer.finish()
    return path
