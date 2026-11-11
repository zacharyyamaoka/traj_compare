"""Beside the frozen test_dataset.py: what the dataset view does at its edges (serve, rewrite, bad input)."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from test_dataset import make_run

from traj_compare.dataset import Run, write_dataset_report
from traj_compare.serve import make_handler


def test_open_in_rerun_builds_an_unbuilt_runs_recording_first(tmp_path):
    run = make_run(0)
    write_dataset_report([run], tmp_path, title="Rerun")
    folder = next(path for path in (tmp_path / "runs").iterdir() if path.is_dir())
    opened = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, spawn=opened.append))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        entry = json.loads((tmp_path / "rows.json").read_text("utf-8"))[0]
        rrd = f"runs/{folder.name}/rerun/reference--real.rrd"
        assert not (tmp_path / rrd).exists()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/__rerun/open?rrd={rrd}", method="POST"
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            assert response.status == 200
        assert (tmp_path / rrd).is_file() and len(opened) == 1
        assert entry["run"] == run.name
    finally:
        server.shutdown()


def test_serve_leaves_unknown_paths_alone(tmp_path):
    write_dataset_report([make_run(0)], tmp_path, title="Unknown")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, spawn=lambda argv: None))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/runs/nope/report.html")
        assert error.value.code == 404
    finally:
        server.shutdown()


def test_rewriting_a_dataset_drops_the_stale_drill_down(tmp_path):
    write_dataset_report([make_run(0)], tmp_path, title="First", drill_down="eager")
    folder = next(path for path in (tmp_path / "runs").iterdir() if path.is_dir())
    assert (folder / "report.html").is_file()
    write_dataset_report([make_run(0)], tmp_path, title="Second", drill_down="lazy")
    assert not (folder / "report.html").exists() and not (folder / "rerun").exists()


def test_bad_input_is_named(tmp_path):
    run = make_run(0)
    with pytest.raises(ValueError, match="unique"):
        write_dataset_report([run, make_run(0)], tmp_path, title="Dup")
    with pytest.raises(ValueError, match="primary names series"):
        write_dataset_report([run], tmp_path, title="Primary", primary={"sim": "nope"})
    with pytest.raises(ValueError, match="collides"):
        run.tags = {"metric": "x"}
        write_dataset_report([run], tmp_path, title="Tag")
    clash = Run(name="x", reference=run.reference, measured={"reference": run.reference})
    with pytest.raises(ValueError, match="target's name"):
        write_dataset_report([clash], tmp_path, title="Reserved")
