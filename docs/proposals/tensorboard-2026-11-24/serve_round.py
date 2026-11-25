#!/usr/bin/env python3
"""Serve the round (prototype server): this folder at ``/``, the bench's sites at ``/bench/``, and Open in Rerun for a
SELECTION of runs.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/tensorboard-2026-11-24/serve_round.py --port 8841

- ``/bench/<site>/...`` is ``arm_motion_bench/reports/media/dashboard/<site>/...``; a run's ``report.html`` that was never
  built is built on the spot (``traj_compare.dataset.build_run_folder``), as ``traj_compare.serve`` does.
- ``POST /__rerun/selection`` with ``{"runs": [{"site": "ur5e", "line": 12}, ...]}`` (``line`` = the index into that
  site's lines in ``data/<site>.js``) writes ONE ``.rrd`` holding every distinct target and every selected run, then
  starts the pinned viewer on it (``traj_compare.rerun_export.viewer_argv``). ``?dry=1`` builds without launching.
  Answer: ``{ok, n, rrd, command, entities}``.

WHY one recording for the whole selection (not one per run in one viewer): Rerun overlays series in one plot when they
share a recording and a timeline; separate recordings show side by side, never as lines in one plot. Zach: "any of the
selected runs now appear as lines in the rerun viewer. That allows us to basically like do any number of possible
comparisons". WHY stock robot_msgs.viz.rerun: it IS the stock JointTrajectory look (one plot per joint, one line per
name, /<field>/<joint>/<name>), shared with traj_compare's own Rerun projection, so nothing is forked.

Prototype only: production is one more endpoint in ``traj_compare.serve`` beside ``/__rerun/open``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
BENCH = Path("/home/bam/arm_motion_bench/reports/media/dashboard")
OUT = HERE / "data" / "rerun"
_LAZY = re.compile(r"^([^/]+)/runs/([A-Za-z0-9][A-Za-z0-9._-]*)/report\.html$")
_SITES: dict[str, dict] = {}


def site_model(site: str) -> dict:
    if site not in _SITES:
        text = (HERE / "data" / f"{site}.js").read_text(encoding="utf-8")
        _SITES[site] = json.loads(text[text.index("{"): text.rindex("}") + 1])
    return _SITES[site]


def rgb(hex_colour: str) -> list[int]:
    hex_colour = hex_colour.lstrip("#")
    return [int(hex_colour[i:i + 2], 16) for i in (0, 2, 4)]


def build_selection(runs: list[dict]) -> tuple[Path, list[str]]:
    """One .rrd: each distinct target (grey) and each selected line (its config's colour), q and joint error."""
    import rerun as rr
    from robot_msgs._core import load_npz
    from robot_msgs.compare import compare
    from robot_msgs.viz import rerun as viz

    picked = []
    for item in runs:
        model = site_model(str(item["site"]))
        line = int(item["line"])
        lines = model["lines"]
        if not 0 <= line < len(lines["id"]):
            raise ValueError(f"no line {line} in {item['site']}")
        picked.append((str(item["site"]), line, model))
    key = hashlib.sha1(json.dumps(sorted((s, l) for s, l, _ in picked)).encode()).hexdigest()[:12]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"selection-{len(picked)}-{key}.rrd"
    names: list[str] = []
    stream = rr.RecordingStream(viz.APPLICATION_ID, recording_id=f"selection-{key}")
    stream.save(str(path))
    many_targets = len({(s, m["lines"]["target"][l]) for s, l, m in picked}) > 1
    references: dict[tuple[str, int], object] = {}
    for site, line, model in picked:
        lines, targets = model["lines"], model["targets"]
        target = lines["target"][line]
        folder = BENCH / site / "runs" / lines["report"][line]
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        series = model["series"][lines["series"][line]]
        task = targets["task"][target]
        if (site, target) not in references:
            reference = load_npz(folder / manifest["files"]["reference"])
            references[(site, target)] = reference
            ref_name = f"target {site} {task}" if many_targets else "target"
            viz.log(reference, viz.path_part(ref_name), recording=stream, degrees=True, color=[150, 150, 150],
                    label=ref_name)
            names.append(ref_name)
        measured = load_npz(folder / manifest["files"][series])
        config = model["configs"][lines["config"][line]]
        label = f"{config['name']} · r{lines['repeat'][line]} · {series}"
        if many_targets:
            label = f"{site} {task} · {label}"
        short = viz.path_part(f"{site}-{line}")
        viz.log(measured, short, recording=stream, degrees=True, color=rgb(config["color"]), label=label)
        comparison = compare(references[(site, target)], measured)
        viz.log(comparison.error, short, recording=stream, degrees=True, color=rgb(config["color"]), label=label,
                prefix="error/")
        names.append(label)
    viz._finish(stream)  # the stock default dashboard: one plot per <field>/<joint>, every name in it
    stream.flush()
    stream.disconnect()
    return path, names


def viewer(path: Path) -> list[str]:
    from traj_compare.rerun_export import viewer_argv

    return viewer_argv(path)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def translate_path(self, path: str) -> str:
        clean = unquote(urlsplit(path).path)
        if clean.startswith("/bench/"):
            relative = clean[len("/bench/"):]
            target = (BENCH / relative).resolve()
            if not target.is_relative_to(BENCH):
                return str(HERE / "__nope__")
            match = _LAZY.match(relative)
            if match and not target.is_file() and (BENCH / match.group(1) / "runs" / match.group(2) / "manifest.json").is_file():
                from traj_compare.dataset import build_run_folder

                build_run_folder(BENCH / match.group(1) / "runs" / match.group(2))
            return str(target)
        return super().translate_path(path)

    def send_head(self):
        # favicon and other misses: a plain 204 rather than a logged 404
        if urlsplit(self.path).path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return None
        return super().send_head()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        # a local Rerun web viewer (another port) reads a selection .rrd from here
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quiet static traffic
        if "POST" in str(args[0] if args else ""):
            super().log_message(fmt, *args)

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            self._json(403, {"ok": False, "error": "cross-origin request refused"})
            return
        if parts.path != "/__rerun/selection":
            self._json(404, {"ok": False, "error": f"no such endpoint: {parts.path}"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            runs = body.get("runs") or []
            # WHY a query form too: data-ui's stock drill `post:` action sends no body, only a URL with {column}s
            # filled: ?runs=ur5e:12,ur5e:13 (site:line, comma-separated)
            for token in ",".join(parse_qs(parts.query).get("runs") or []).split(","):
                if ":" in token:
                    site, _, line = token.rpartition(":")
                    runs.append({"site": site, "line": int(line)})
            if not runs:
                self._json(400, {"ok": False, "error": "no runs selected"})
                return
            path, names = build_selection(runs)
        except Exception as error:  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(error)})
            return
        argv = viewer(path)
        command = " ".join(argv)
        if (parse_qs(parts.query).get("dry") or ["0"])[0] != "1":
            try:
                subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError as error:
                self._json(500, {"ok": False, "error": f"could not start the viewer: {error}", "command": command})
                return
        self._json(200, {"ok": True, "n": len(runs), "rrd": str(path), "command": command, "entities": names})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8841)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"http://{args.host}:{args.port}/  (round: {HERE}, bench: {BENCH})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
