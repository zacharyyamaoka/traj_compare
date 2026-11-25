#!/usr/bin/env python3
"""Serve the Overview round: this folder at ``/`` (o1 … o5, kit/, vendor/), and V2's shared parts from the read-only
tensorboard round: ``/data/`` (the 18,507 rows), ``/common/`` (the target view), ``/bench/`` and ``POST /__rerun/selection``.

    /home/bam/traj_compare/.venv/bin/python /home/bam/traj_compare/docs/proposals/v2-overview-2026-11-24/serve.py --port 8851

Then http://127.0.0.1:8851/o1/index.html … /o5/index.html. Everything else is ``serve_round.py``'s (imported, not copied):
lazy run reports and the Rerun selection endpoint (``?dry=1`` builds without launching a viewer).
"""

from __future__ import annotations

import argparse
import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "tensorboard-2026-11-24"
_spec = importlib.util.spec_from_file_location("serve_round", BASE / "serve_round.py")
serve_round = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serve_round)
SHARED = ("/data/", "/common/")  # V2's: the rows and the target view, never copied


class Handler(serve_round.Handler):
    def __init__(self, *args, **kwargs):
        # SimpleHTTPRequestHandler's directory: this round; the parent's __init__ would pin the tensorboard folder
        super(serve_round.Handler, self).__init__(*args, directory=str(HERE), **kwargs)

    def translate_path(self, path: str) -> str:
        clean = unquote(urlsplit(path).path)
        if clean.startswith(SHARED):
            target = (BASE / clean.lstrip("/")).resolve()
            return str(target) if target.is_relative_to(BASE) else str(HERE / "__nope__")
        return super().translate_path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8851)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"http://{args.host}:{args.port}/o1/index.html … /o5/index.html  (round: {HERE})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
