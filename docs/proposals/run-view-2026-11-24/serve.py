#!/usr/bin/env python3
"""Serve the run-view round (prototype server, port 8853):

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/run-view-2026-11-24/serve.py --port 8853

- ``/``              this folder: ``r1/`` … ``r5/`` (each variant's playback viewer), ``common/``, ``data/``.
- ``/assets/``       traj_compare's own viewer files (``src/traj_compare/assets``): what a variant did not change.
- ``/target-view/``  the target view the playback viewer is opened from (``../tensorboard-2026-11-24``, V2's
                     ``common/target.html``), read only, with its ``bench/`` and its ``POST __rerun/selection``.
- ``/tta/``          the Trajectory Tracking Agent's comparison site (fixture ``tta``'s target page).
- ``/bench/``        the arm_motion_bench dashboard sites (a run's report.html is built on first open).
- ``POST /__rerun/open`` ``{fixture, keep: [situation names], t, tab}`` → ONE ``.rrd`` of exactly those runs through
  traj_compare's own ``rerun_export.write_rrd`` (the ``questions`` layout: the same tab titles as the HTML), opening on
  the same tab, paused, with a 0.2 s time selection around ``t`` (Rerun 0.40's blueprint has no cursor position, so the
  time travels as that selection), then starts the pinned viewer. ``?dry=1`` writes without launching.
  Answer: ``{ok, rrd, command, runs, t, launched}``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ASSETS = REPO / "src" / "traj_compare" / "assets"
V2 = HERE.parent / "tensorboard-2026-11-24"
TTA_SITE = Path("/home/bam/trajectory_tracking_agent/site/comparison")
BENCH = Path("/home/bam/arm_motion_bench/reports/media/dashboard")
OUT = HERE / "data" / "rerun"
sys.path.insert(0, str(HERE))


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def open_in_rerun(body: dict, dry: bool) -> dict:
    import rerun.blueprint as rrb
    from rerun.datatypes import AbsoluteTimeRange
    from traj_compare import tabs as tc_tabs
    from traj_compare.analysis import analyze_comparison
    from traj_compare.report import _colorize
    from traj_compare.rerun_export import layout_blueprint, viewer_argv, viewer_command, write_rrd

    import fixtures

    name = str(body.get("fixture") or "tta")
    if name not in fixtures.FIXTURES:
        raise ValueError(f"no fixture {name!r}")
    keep = [str(k) for k in (body.get("keep") or [])]
    comparison = fixtures.comparison(name, keep)
    if not comparison.situations:
        raise ValueError("no run selected")
    payload = analyze_comparison(comparison)
    _colorize(payload)
    colours = fixtures.payload_colours(name)
    for situation in payload["situations"]:
        if situation["name"] in colours:
            situation["color"] = colours[situation["name"]]
    t = body.get("t")
    tab_id = body.get("tab")
    titles = {getattr(tab, "id", None): getattr(tab, "title", None) for tab in getattr(tc_tabs, "TABS", ())}
    tab_title = titles.get(tab_id) if tab_id else None

    def blueprint(page: dict, videos: dict) -> object:
        bp = layout_blueprint("questions", page, videos, tab=tab_title)
        if t is not None:
            ns = int(round(float(t) * 1e9))
            bp.time_panel = rrb.TimePanel(state="expanded", timeline="t", play_state="paused",
                                          time_selection=AbsoluteTimeRange(min=ns - 100_000_000, max=ns + 100_000_000))
        return bp

    key = hashlib.sha1(json.dumps([name, sorted(keep), t, tab_id]).encode()).hexdigest()[:10]
    path = OUT / f"{name}-{len(comparison.situations)}-{key}.rrd"
    write_rrd(comparison, path, layout="questions", payload=payload, blueprint=blueprint)
    launched = False
    if not dry:
        subprocess.Popen(viewer_argv(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        launched = True
    return {"ok": True, "rrd": str(path), "command": viewer_command(path), "runs": len(comparison.situations),
            "names": [s.name for s in comparison.situations], "t": t, "tab": tab_title, "launched": launched}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def translate_path(self, path: str) -> str:
        clean = unquote(urlsplit(path).path)
        for prefix, root in (("/assets/", ASSETS), ("/target-view/bench/", BENCH), ("/bench/", BENCH),
                             ("/target-view/", V2), ("/tta/", TTA_SITE)):
            if clean.startswith(prefix):
                relative = clean[len(prefix):]
                target = (root / relative).resolve()
                if not target.is_relative_to(root.resolve()):
                    return str(HERE / "__nope__")
                if root is BENCH and target.name == "report.html" and not target.is_file():
                    run = target.parent
                    if (run / "manifest.json").is_file():
                        from traj_compare.dataset import build_run_folder

                        build_run_folder(run)
                return str(target)
        return super().translate_path(path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        if "POST" in str(args[0] if args else ""):
            super().log_message(fmt, *args)

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            dry = "dry=1" in (url.query or "")
            if url.path == "/__rerun/open":
                self._json(200, open_in_rerun(body, dry))
            elif url.path == "/target-view/__rerun/selection":
                round_server = _module("tensorboard_serve_round", V2 / "serve_round.py")
                path, names = round_server.build_selection(body.get("runs") or [])
                if not dry:
                    subprocess.Popen(round_server.viewer(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
                self._json(200, {"ok": True, "n": len(names), "rrd": str(path), "entities": names,
                                 "command": " ".join(round_server.viewer(path))})
            else:
                self._json(404, {"ok": False, "error": "no such endpoint"})
        except Exception as error:  # noqa: BLE001 - the page shows it
            self._json(500, {"ok": False, "error": f"{type(error).__name__}: {error}"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8853)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"http://127.0.0.1:{args.port}/r1/index.html?fixture=tta", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
