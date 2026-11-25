#!/usr/bin/env python3
"""Serve the V2-tabs round: this folder at ``/``, and what V2 already has at the same paths it uses.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-tabs-2026-11-24/serve.py --port 8852

then ``http://127.0.0.1:8852/t1/index.html`` (… ``/t3/``). Reuses V2's server (``../tensorboard-2026-11-24/serve_round.py``,
READ-ONLY, imported, not copied): the bench at ``/bench/`` (run reports built lazily) and ``POST /__rerun/selection``
(one ``.rrd`` for the selected runs, written under THIS folder's ``data/rerun/``). Paths:

- ``/common/`` and ``/vendor/`` are V2's (the shared target view, the vendored data-ui ``e8c73dc``);
- ``/data/<file>`` is this folder's ``data/`` when it has the file (pairs, h2h, t2-cells, oracle), else V2's (the runs,
  the targets, the site extracts).
"""

from __future__ import annotations

import argparse
import importlib.util
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROUND = Path(__file__).resolve().parent
V2_ROUND = ROUND.parent / "tensorboard-2026-11-24"

_spec = importlib.util.spec_from_file_location("serve_round", V2_ROUND / "serve_round.py")
serve_round = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serve_round)
serve_round.OUT = ROUND / "data" / "rerun"  # WHY: never write into V2's folder, even its gitignored data/


def _inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


class Handler(serve_round.Handler):
    def __init__(self, *args, **kwargs):
        SimpleHTTPRequestHandler.__init__(self, *args, directory=str(ROUND), **kwargs)

    def translate_path(self, path: str) -> str:
        clean = unquote(urlsplit(path).path)
        if clean.startswith("/bench/"):
            return super().translate_path(path)
        relative = clean.lstrip("/")
        if clean.startswith(("/common/", "/vendor/")):
            target = V2_ROUND / relative
            return str(target) if _inside(target, V2_ROUND) else str(ROUND / "__nope__")
        if clean.startswith("/data/"):
            mine = ROUND / relative
            target = mine if mine.exists() else V2_ROUND / relative
            ok = _inside(target, ROUND) or _inside(target, V2_ROUND)
            return str(target) if ok else str(ROUND / "__nope__")
        return SimpleHTTPRequestHandler.translate_path(self, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8852)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"http://{args.host}:{args.port}/t1/index.html  /t2/  /t3/  (round: {ROUND})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
