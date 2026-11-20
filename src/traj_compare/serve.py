"""Serve a report directory and launch the pinned Rerun viewer on one of its .rrd files.

    python -m traj_compare.serve <dir> [--port 8767] [--host 127.0.0.1]

A plain static server plus three behaviours. A request for a dataset run's ``<site>/runs/<slug>/report.html``
(or its ``rerun/*.rrd``) that was never built is built on the spot from that run folder's manifest
(``traj_compare.dataset.build_run_folder``) and cached on disk; a *site* (a directory holding ``index.html`` and
``runs/``) may sit at the root or at any depth below it, so one server serves several robots' sites. WHY: the
arm_motion_bench agent writes one site per robot and should not need one server each. When the root has no
``index.html`` of its own, ``GET /`` answers a landing page linking every site up to 3 levels deep. And one endpoint, ``POST /__rerun/open?rrd=<path relative to the root>[&layout=questions|evo]``,
which is what the report's "Open in Rerun" button calls. WHY an endpoint and not a custom URL
scheme: a browser page cannot start a process, and a registered ``rerun://`` handler would be one
more thing to install per machine; this is the same ``uvx`` command the "Copy command" button
shows, started for you. Standard library only.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import threading
from collections.abc import Callable
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .rerun_export import LAYOUTS, blueprint_path, viewer_argv, viewer_command

DEFAULT_PORT = 8767
OPEN_PATH = "/__rerun/open"
# [<site>/]runs/<slug>/report.html or [<site>/]runs/<slug>/rerun/<pair>.rrd, relative to the served root
_LAZY_BUILD = re.compile(r"^((?:[^/]+/)*)runs/([A-Za-z0-9][A-Za-z0-9._-]*)/(?:report\.html|rerun/[A-Za-z0-9._-]+\.rrd)$")


def _spawn_detached(argv: list[str]) -> None:
    """Start the viewer as its own session so closing this server does not close the viewer."""

    subprocess.Popen(  # noqa: S603 - argv is built from the pin plus a resolved path inside the root
        argv,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


_SITE_DEPTH = 3
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def find_sites(root: Path) -> list[Path]:
    """Every site (a dir holding index.html and runs/) 1 to 3 levels below ``root``, in posix path order."""
    found: list[str] = []

    def walk(directory: Path, depth: int) -> None:
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or child.is_symlink() or child.name == "runs":
                continue
            if (child / "index.html").is_file() and (child / "runs").is_dir():
                found.append(child.relative_to(root).as_posix())
            if depth < _SITE_DEPTH:
                walk(child, depth + 1)

    walk(root, 1)
    return [root / path for path in sorted(found)]


def landing_page(root: Path) -> str:
    """The page ``GET /`` answers when the root has no index.html: one link per site, with its title and run count."""
    items = []
    for site in find_sites(root):
        path = site.relative_to(root).as_posix()
        # WHY only the head: a site's index.html embeds its whole dataset (tens of MB for the UR5e); the <title> is near the top.
        with (site / "index.html").open("r", encoding="utf-8", errors="replace") as page:
            match = _TITLE.search(page.read(65536))
        title = html.unescape(match.group(1)).strip() if match else path
        runs = len(list((site / "runs").glob("*/manifest.json")))
        text = html.escape(f"{title} \u2014 {runs} {'run' if runs == 1 else 'runs'}")
        items.append(
            f'<li><a data-tc-site="{html.escape(path)}" href="{html.escape(quote(path))}/index.html">{text}</a></li>'
        )
    body = "<ul>" + "".join(items) + "</ul>" if items else "<p>No sites found.</p>"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Sites</title></head>'
        f"<body><h1>Sites</h1>{body}</body></html>"
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
        site = match.group(1)
        if ".." in PurePosixPath(site).parts:
            return
        folder = (root / site / "runs" / match.group(2)).resolve()
        if not folder.is_relative_to(root) or not (folder / "manifest.json").is_file():
            return
        with build_lock:
            if (root / relative).is_file():  # another request built it while this one waited
                return
            from .dataset import build_run_folder

            build_run_folder(folder)

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

        def _landing(self, head: bool) -> bool:
            """Answer the landing page when the root has no index.html of its own."""
            if unquote(urlsplit(self.path).path) not in ("/", "/index.html") or (root / "index.html").is_file():
                return False
            data = landing_page(root).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not head:
                self.wfile.write(data)
            return True

        def do_GET(self) -> None:  # noqa: N802
            if not self._landing(head=False):
                self._serve_built(super().do_GET)

        def do_HEAD(self) -> None:  # noqa: N802
            if not self._landing(head=True):
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
            # ?layout=<name> opens that named layout's .rbl beside the .rrd (rerun_export.LAYOUTS)
            layout = (parse_qs(parts.query).get("layout") or [None])[0]
            if layout is not None and layout not in LAYOUTS:
                self._json(400, {"ok": False, "error": f"unknown layout {layout!r}; choose one of: {', '.join(LAYOUTS)}"})
                return
            if layout is not None and not blueprint_path(resolved, layout).is_file():
                self._json(404, {"ok": False, "error": f"no {layout} layout file beside {requested}"})
                return
            try:
                spawn(viewer_argv(resolved, layout))
            except OSError as error:
                self._json(
                    500,
                    {
                        "ok": False,
                        "error": f"could not start the viewer ({error}); is uv installed?",
                        "command": viewer_command(resolved, layout),
                    },
                )
                return
            self._json(200, {"ok": True, "command": viewer_command(resolved, layout)})

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
