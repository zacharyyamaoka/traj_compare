"""Screenshot each layout state in the REAL Rerun web viewer (pinned 0.40.0), headless — adapted from
traj_compare/docs/rerun_layouts/shoot.py (2026-11-11).

    cd ~/bam_ws/src/core/mdp/agent/actor/trajectory_generation/traj_compare/docs/layout_proposals_2026-11-19/rerun
    flock /tmp/claude-1000/traj-layout-browser.lock taskset -c 2-5,16,17 nice -n 19 \
      uv run --no-project --with playwright==1.64.1 python shoot_rerun.py --dir <OUT> --rerun-bin <venv>/bin/rerun [--only hero]

Reads <OUT>/manifest.json ("shots": slug, shot, rbl, at), serves <OUT> with CORS, starts `rerun --serve-web` on free
ports in its own process group (stopped by that group's PID at the end, never by port), opens
`?url=<slug>.rrd&url=<shot>.rbl`, types the playhead into the time field and writes shots/<slug>--<shot>.png.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import os
import signal
import socket
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright


class _Cors(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--rerun-bin", required=True)
    parser.add_argument("--only", default="", help="substring of '<slug>--<shot>' to keep")
    parser.add_argument("--embedded", default="", help="instead: open <slug>.rrd alone (no .rbl) to prove the embedded blueprint")
    parser.add_argument("--wait-ms", type=int, default=22000)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    root = args.dir.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Cors, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    web, grpc = free_port(), free_port()
    process = subprocess.Popen([args.rerun_bin, "--serve-web", "--web-viewer-port", str(web), "--port", str(grpc)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    (root / "shots").mkdir(exist_ok=True)
    try:
        await asyncio.sleep(4)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True, args=["--use-angle=vulkan", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-features=Vulkan"])
            shots = manifest["shots"]
            if args.embedded:  # G1: the .rrd alone, its embedded default blueprint, no sidecar
                shots = [{"slug": args.embedded, "shot": "embedded-check", "rbl": None, "at": manifest["t_worst"]}]
            for spec in shots:
                name = f"{spec['slug']}--{spec['shot']}"
                if args.only and args.only not in name:
                    continue
                rrd = manifest["variants"][spec["slug"]]["rrd"]
                page = await browser.new_page(viewport={"width": args.width, "height": args.height})
                blueprint = f"&url={base}/{spec['rbl']}" if spec["rbl"] else ""
                await page.goto(f"http://127.0.0.1:{web}/?renderer=webgl&url={base}/{rrd}{blueprint}", timeout=120_000)
                await page.wait_for_timeout(args.wait_ms)
                # the time readout at the bottom right is an egui text field: type the playhead time into it
                await page.mouse.click(args.width - 100, args.height - 14)
                await page.keyboard.press("Control+A")
                await page.keyboard.type(f"{spec['at']:g}s")
                await page.keyboard.press("Enter")
                await page.mouse.move(args.width / 2, 5)
                await page.wait_for_timeout(4000)
                shot = root / "shots" / f"{name}.png"
                await page.screenshot(path=str(shot), timeout=90_000)
                print(shot, flush=True)
                await page.close()
            await browser.close()
    finally:
        server.shutdown()
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


if __name__ == "__main__":
    asyncio.run(main())
