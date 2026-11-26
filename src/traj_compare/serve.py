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
shows, started for you. A report can also post ``?report=<relative HTML>&comparison=<index>``.
The server reads that report's embedded data, builds a missing recording and opens it. Standard
library only until a recording needs to be built.

Two more for the runs workbench's target view (``traj_compare.runs_workbench``, docs/RUNS_WORKBENCH.md), each posted to
``<page dir>/<endpoint>`` with ``{"runs": [{"folder", "series", "label"?, "color"?}]}`` (folders relative to that page
directory, refused outside the root) or ``?runs=<folder>:<series>,...``:

- ``POST <dir>/__playback`` (``crumbs``, ``title`` too): traj_compare's comparison viewer over exactly those runs and their
  target (``selection.build_playback``), cached under ``<dir>/playback/<key>/``; answers ``{ok, n, href}``.
- ``POST <dir>/__rerun/selection[?dry=1]``: one ``.rrd`` of them (``selection.build_selection_rrd``, one plot per joint,
  one line per run) under ``<dir>/selections/``, then the pinned viewer; ``dry=1`` builds without starting it.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shlex
import subprocess
import threading
from collections.abc import Callable
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import report
from .rerun_export import LAYOUTS, blueprint_path, viewer_argv, viewer_command

DEFAULT_PORT = 8767
OPEN_PATH = "/__rerun/open"
# POST <page dir>/__rerun/selection and <page dir>/__playback (the runs workbench's target view): the run folders a body
# names are relative to <page dir>, the directory of the page that posted (a relative URL keeps it), never a guess.
SELECTION_ENDPOINT = "__rerun/selection"
PLAYBACK_ENDPOINT = "__playback"
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_MAX_BODY = 2_000_000


def _endpoint_dir(path: str, endpoint: str) -> str | None:
    """``"all/"``-style directory (relative to the root, ``""`` for the root itself) a POST to ``/<dir>/<endpoint>``
    came from, or None when the path names another endpoint."""
    clean = unquote(path)
    if clean == f"/{endpoint}":
        return ""
    if clean.endswith(f"/{endpoint}"):
        return clean[1 : -len(endpoint)]
    return None


def _crumbs(value: object) -> list[tuple[str, str]]:
    """A playback page's breadcrumb from a request: ``[[label, href], ...]``, each href a same-origin path or a
    relative one (WHY refused otherwise: the page would carry a ``javascript:`` or another site's link)."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError("crumbs is a list of at most 8 [label, href] pairs")
    out = []
    for item in value:
        if not (isinstance(item, list) and len(item) == 2 and all(isinstance(part, str) for part in item)):
            raise ValueError(f"a crumb is [label, href], got {item!r}")
        label, href = item
        if len(label) > 300 or len(href) > 8000 or href.startswith("//") or _SCHEME.match(href):
            raise ValueError(f"a crumb's href is a same-origin or relative path, got {href[:80]!r}")
        out.append((label, href))
    return out
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
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Sites</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>body{font:15px/1.5 system-ui,sans-serif;margin:32px auto;max-width:760px;padding:0 16px;color:#2c2c2a;"
        "background:#fafaf8}h1{font-size:22px;margin:0 0 4px}p{color:#6b6a65;margin:0 0 18px}ul{list-style:none;padding:0}"
        "li{margin:0 0 8px}a{display:block;padding:12px 16px;border:1px solid #deddd8;border-radius:8px;background:#fff;"
        "color:#2c2c2a;text-decoration:none}a:hover{border-color:#7c5cc4}</style></head>"
        "<body><h1>Sites</h1><p>Every dataset site below this folder; a run's report is built when you first open it.</p>"
        f"{body}</body></html>"
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

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY:
                raise ValueError("request body too large")
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw.strip() else {}
            if not isinstance(body, dict):
                raise ValueError("the body is a JSON object")
            return body

        def _picks(self, directory: str, body: dict, query: dict) -> tuple[Path, list]:
            """The page's directory and the runs it names: ``{"runs": [{"folder", "series", "label"?, "color"?}]}`` or,
            for data-ui's bodyless ``post:`` action, ``?runs=<folder>:<series>,...``; each folder relative to it."""
            from .selection import Pick

            base = (root / directory).resolve()
            if not base.is_relative_to(root):
                raise PermissionError("the page's directory is outside the served root")
            items = list(body.get("runs") or [])
            for token in ",".join(query.get("runs") or []).split(","):
                if token.strip():
                    folder, _, series = token.rpartition(":")
                    items.append({"folder": folder, "series": series})
            picks = []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("folder"), str) or not item.get("series"):
                    raise ValueError(f"a run is {{folder, series}}, got {item!r}")
                folder = (base / item["folder"]).resolve()
                if not folder.is_relative_to(root):
                    raise PermissionError(f"{item['folder']} is outside the served root")
                picks.append(Pick(folder, str(item["series"]), label=str(item.get("label") or ""),
                                  color=str(item.get("color") or "")))
            return base, picks

        def _selection(self, directory: str, parts, query: dict) -> None:
            """``POST <dir>/__rerun/selection[?dry=1]``: one .rrd of the picked lines (``selection.build_selection_rrd``),
            then the pinned viewer on it; ``dry=1`` builds and answers without starting the viewer."""
            from .selection import build_selection_rrd, selection_key

            base, picks = self._picks(directory, self._body(), query)
            if not picks:
                raise ValueError("no runs selected")
            path = base / "selections" / f"selection-{len(picks)}-{selection_key(picks)}.rrd"
            with build_lock:
                path, names = build_selection_rrd(picks, path)
            dry = (query.get("dry") or ["0"])[0] == "1"
            answer = {"ok": True, "n": len(picks), "rrd": str(path), "command": viewer_command(path), "entities": names,
                      "dry": dry}
            if not dry:
                try:
                    spawn(viewer_argv(path))
                except OSError as error:
                    self._json(500, {**answer, "ok": False, "error": f"could not start the viewer ({error}); is uv installed?"})
                    return
            self._json(200, answer)

        def _playback(self, directory: str, query: dict) -> None:
            """``POST <dir>/__playback`` with ``{runs, crumbs?, title?}``: traj_compare's comparison viewer over exactly
            those runs and their target (``selection.build_playback``), cached under ``<dir>/playback/<key>/``;
            answers ``{ok, n, href}``, the page's path, for the target view to open in its own tab."""
            from .selection import build_playback, selection_key

            body = self._body()
            base, picks = self._picks(directory, body, query)
            if not picks:
                raise ValueError("no runs selected")
            crumbs = _crumbs(body.get("crumbs"))
            title = body.get("title") or ""
            if not isinstance(title, str) or len(title) > 300:
                raise ValueError("title is a string of at most 300 characters")
            count = f"{len(picks)} run{'s' if len(picks) != 1 else ''}"
            # WHY the viewer in the key and the assets folder's name (2026-11-25): keyed by the selection alone, a
            # selection opened before a viewer upgrade kept yesterday's page forever; one shared assets folder would
            # also hand an old page a newer viewer's files. Each viewer version gets its own pages and its own files.
            viewer = report.viewer_digest()
            folder = base / "playback" / selection_key(picks, title, crumbs, viewer)
            with build_lock:
                if not (folder / "report.html").is_file():
                    build_playback(picks, folder, title=title, breadcrumb=[*crumbs, (f"Playback · {count}", "")],
                                   assets=base / "playback" / f"assets-{viewer}")
            href = "/" + quote((folder / "report.html").relative_to(root).as_posix())
            self._json(200, {"ok": True, "n": len(picks), "href": href})

        def _open_report(self, query: dict[str, list[str]]) -> None:
            from .rerun_report import report_recording

            requested = query["report"][0]
            if requested.startswith(("/", "\\")) or PurePosixPath(requested).is_absolute():
                raise ValueError("report must be relative to the served root")
            path = (root / requested).resolve()
            if not path.is_relative_to(root):
                raise PermissionError("report is outside the served root")
            if path.is_dir():
                # HTTP directory URLs normally serve index.html. A direct
                # comparison folder can instead contain only report.html.
                index_page = path / "index.html"
                path = (index_page if index_page.is_file() else path / "report.html").resolve()
                if not path.is_relative_to(root):
                    raise PermissionError("report is outside the served root")
            index = int((query.get("comparison") or ["0"])[0])
            layout = (query.get("layout") or [None])[0]
            try:
                with build_lock:
                    recording = report_recording(path, index, root=root, layout=layout)
            except (PermissionError, FileNotFoundError, KeyError, TypeError, ValueError):
                raise
            except Exception as error:  # noqa: BLE001 - report the build failure and a local retry command
                argv = ["traj-compare-rerun", str(path), "--comparison", str(index), "--open"]
                if layout is not None:
                    argv.extend(("--layout", layout))
                self._json(500, {"ok": False, "error": str(error), "command": shlex.join(argv)})
                return
            command = viewer_command(recording, layout)
            try:
                spawn(viewer_argv(recording, layout))
            except OSError as error:
                self._json(500, {"ok": False, "error": f"could not start the viewer ({error})", "command": command})
                return
            self._json(200, {"ok": True, "command": command})

        def do_POST(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            selection = _endpoint_dir(parts.path, SELECTION_ENDPOINT)
            playback = _endpoint_dir(parts.path, PLAYBACK_ENDPOINT)
            if parts.path != OPEN_PATH and selection is None and playback is None:
                self._json(404, {"ok": False, "error": f"no such endpoint: {parts.path}"})
                return
            # WHY same-origin only: this endpoint starts a process, and the CORS header above lets
            # any page read this server; a POST from another origin must not be able to start one.
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                self._json(403, {"ok": False, "error": "cross-origin request refused"})
                return
            if selection is not None or playback is not None:
                query = parse_qs(parts.query)
                try:
                    if selection is not None:
                        self._selection(selection, parts, query)
                    else:
                        self._playback(playback, query)
                except PermissionError as error:
                    self._json(403, {"ok": False, "error": str(error)})
                except (ValueError, KeyError) as error:
                    self._json(400, {"ok": False, "error": str(error)})
                except Exception as error:  # noqa: BLE001 - the page says why, the server keeps running
                    self._json(500, {"ok": False, "error": f"{type(error).__name__}: {error}"})
                return
            query = parse_qs(parts.query)
            if "report" in query:
                try:
                    self._open_report(query)
                except PermissionError as error:
                    self._json(403, {"ok": False, "error": str(error)})
                except FileNotFoundError as error:
                    self._json(404, {"ok": False, "error": str(error)})
                except (KeyError, TypeError, ValueError) as error:
                    self._json(400, {"ok": False, "error": str(error)})
                except Exception as error:  # noqa: BLE001 - the report gets the error
                    self._json(500, {"ok": False, "error": str(error)})
                return
            requested = (query.get("rrd") or [""])[0]
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
