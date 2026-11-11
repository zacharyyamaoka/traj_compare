"""Serve a report directory and launch the pinned Rerun viewer on one of its .rrd files.

    python -m traj_compare.serve <dir> [--port 8767] [--host 127.0.0.1]

A plain static server plus two behaviours. A request for a dataset run's ``runs/<slug>/report.html``
(or its ``rerun/*.rrd``) that was never built is built on the spot from that run's manifest
(``traj_compare.dataset.build_drill_down``) and cached on disk; and one endpoint, ``POST /__rerun/open?rrd=<path relative to the root>``,
which is what the report's "Open in Rerun" button calls. WHY an endpoint and not a custom URL
scheme: a browser page cannot start a process, and a registered ``rerun://`` handler would be one
more thing to install per machine; this is the same ``uvx`` command the "Copy command" button
shows, started for you. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
from collections.abc import Callable
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit

from .rerun_export import viewer_argv, viewer_command

DEFAULT_PORT = 8767
OPEN_PATH = "/__rerun/open"
# runs/<slug>/report.html or runs/<slug>/rerun/<pair>.rrd, relative to the served root
_LAZY_BUILD = re.compile(r"^runs/([A-Za-z0-9][A-Za-z0-9._-]*)/(?:report\.html|rerun/[A-Za-z0-9._-]+\.rrd)$")


def _spawn_detached(argv: list[str]) -> None:
    """Start the viewer as its own session so closing this server does not close the viewer."""

    subprocess.Popen(  # noqa: S603 - argv is built from the pin plus a resolved path inside the root
        argv,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_handler(
    root: Path | str, *, spawn: Callable[[list[str]], object] = _spawn_detached
) -> type[SimpleHTTPRequestHandler]:
    """A request-handler class serving ``root``; ``spawn`` launches the viewer (injected for tests)."""

    root = Path(root).resolve()
    # WHY one lock: two clicks on the same run must build it once, and a build writes the .rrd files
    # and the page; building different runs at once would also pile up Rerun SDK processes.
    build_lock = threading.Lock()

    def build_missing(relative: str) -> None:
        """Build a dataset run's drill-down when ``relative`` names one of its unbuilt files."""
        match = _LAZY_BUILD.match(relative)
        if match is None or (root / relative).is_file():
            return
        manifest = root / "runs" / match.group(1) / "manifest.json"
        if not manifest.is_file():
            return
        with build_lock:
            if (root / relative).is_file():  # another request built it while this one waited
                return
            from .dataset import build_drill_down

            build_drill_down(root, json.loads(manifest.read_text("utf-8"))["name"])

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        # WHY CORS + Private-Network headers: app.rerun.io (the "Rerun in browser" link) fetches the
        # .rrd from this localhost server, which a browser allows only when the server says so.
        def end_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            super().end_headers()

        def do_OPTIONS(self) -> None:  # noqa: N802 - http.server's naming
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                self.headers.get("Access-Control-Request-Headers") or "*",
            )
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _serve_built(self, serve: Callable[[], None]) -> None:
            relative = unquote(urlsplit(self.path).path).lstrip("/")
            try:
                build_missing(relative)
            except Exception as error:  # noqa: BLE001 - the browser gets the reason, the server keeps running
                reason = (str(error).splitlines() or [type(error).__name__])[0]  # one header line
                self.send_error(500, f"could not build {relative}: {reason}")
                return
            serve()

        def do_GET(self) -> None:  # noqa: N802
            self._serve_built(super().do_GET)

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve_built(super().do_HEAD)

        def _json(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            if parts.path != OPEN_PATH:
                self._json(404, {"ok": False, "error": f"no such endpoint: {parts.path}"})
                return
            # WHY same-origin only: this endpoint starts a process, and the CORS header above lets
            # any page read this server; a POST from another origin must not be able to start one.
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                self._json(403, {"ok": False, "error": "cross-origin request refused"})
                return
            requested = (parse_qs(parts.query).get("rrd") or [""])[0]
            if not requested:
                self._json(400, {"ok": False, "error": "missing ?rrd=<path relative to the served root>"})
                return
            if requested.startswith(("/", "\\")) or PurePosixPath(requested).is_absolute():
                self._json(400, {"ok": False, "error": "rrd must be relative to the served root"})
                return
            resolved = (root / requested).resolve()
            if not resolved.is_relative_to(root):
                self._json(403, {"ok": False, "error": "rrd is outside the served root"})
                return
            if resolved.suffix.lower() != ".rrd":
                self._json(400, {"ok": False, "error": "only .rrd files can be opened"})
                return
            if not resolved.is_file():
                # A dataset page links the .rrd of a run nobody opened yet: build it, then open it.
                try:
                    build_missing(PurePosixPath(requested).as_posix())
                except Exception as error:  # noqa: BLE001
                    self._json(500, {"ok": False, "error": f"could not build {requested}: {error}"})
                    return
            if not resolved.is_file():
                self._json(404, {"ok": False, "error": f"no such file: {requested}"})
                return
            try:
                spawn(viewer_argv(resolved))
            except OSError as error:
                self._json(
                    500,
                    {
                        "ok": False,
                        "error": f"could not start the viewer ({error}); is uv installed?",
                        "command": viewer_command(resolved),
                    },
                )
                return
            self._json(200, {"ok": True, "command": viewer_command(resolved)})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path, help="the report directory to serve")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    root = args.directory.resolve()
    if not root.is_dir():
        raise SystemExit(f"{root} is not a directory")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(root))
    page = "report.html" if (root / "report.html").is_file() else ""
    print(f"serving {root} on http://{args.host}:{server.server_address[1]}/{page}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
