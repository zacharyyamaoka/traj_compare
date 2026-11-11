"""Screenshot every tab of every layout variant in the REAL Rerun web viewer (pinned 0.40.0), headless.

    uv run --no-project --with playwright==1.64.1 python shoot.py --dir <variants out> --rerun-bin <rerun>

Serves <dir> with CORS, starts `rerun --serve-web` on free ports (stopped by process group at the end),
and opens `?url=<variant>.rrd&url=<tab>.rbl` so the viewer lands on that tab. Writes shots/<slug>--<i>.png.
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


async def set_time(page, args, seconds: float) -> None:
    await page.mouse.click(args.width - 100, args.height - 14)
    await page.keyboard.press("Control+A")
    await page.keyboard.type(f"{seconds:g}s")
    await page.keyboard.press("Enter")
    await page.mouse.move(args.width / 2, 5)


async def film(browser, args, manifest, root: Path, base: str, web: int) -> None:
    """Stop-motion of the real viewer: set the playhead, wait for a fresh frame, screenshot; then ffmpeg.

    WHY stop-motion (as record_hero.py): a screen recording on a loaded machine drops frames, a
    screenshot after each step cannot."""
    import shutil

    slug, tab = args.film.split(":")
    entry = manifest[slug]
    frames = root / "film" / slug
    frames.mkdir(parents=True, exist_ok=True)
    page = await browser.new_page(viewport={"width": args.width, "height": args.height})
    rbl = entry["tabs"][int(tab)]["rbl"]
    await page.goto(f"http://127.0.0.1:{web}/?renderer=webgl&url={base}/{entry['rrd']}&url={base}/{rbl}", timeout=120_000)
    await page.wait_for_timeout(args.wait_ms)
    start, stop, step = (float(x) for x in args.film_times.split(":"))
    times = [round(start + i * step, 3) for i in range(int(round((stop - start) / step)) + 1)]
    for index, seconds in enumerate(times):
        await set_time(page, args, seconds)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(frames / f"{index:04d}.png"))
        print(f"film {index + 1}/{len(times)} t={seconds}", flush=True)
    await page.close()
    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    mp4 = root / "media" / f"{slug}-hero.mp4"
    mp4.parent.mkdir(exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", "5", "-i", str(frames / "%04d.png"),
                    "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", str(mp4)], check=True)
    gif = mp4.with_suffix(".gif")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    "fps=5,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse",
                    str(gif)], check=True)
    poster = mp4.with_name(f"{slug}-hero-poster.png")
    shutil.copy(frames / f"{len(times) // 2:04d}.png", poster)
    print(mp4, gif, poster)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--rerun-bin", nargs="+", required=True)
    parser.add_argument("--only", default="")
    parser.add_argument("--fragment", default="")
    parser.add_argument("--at", default="2s", help="playhead time (s) typed into the time field before the shot")
    parser.add_argument("--suffix", default="", help="appended to each shot's file name (e.g. a playhead time)")
    parser.add_argument("--film", default="", help="slug:tab — step the playhead through the run and film it (hero video)")
    parser.add_argument("--film-times", default="0.1:4.5:0.2", help="start:stop:step seconds for --film")
    parser.add_argument("--wait-ms", type=int, default=20000)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args()
    root = args.dir.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Cors, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    web, grpc = free_port(), free_port()
    process = subprocess.Popen([*args.rerun_bin, "--serve-web", "--web-viewer-port", str(web), "--port", str(grpc)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    (root / "shots").mkdir(exist_ok=True)
    try:
        await asyncio.sleep(4)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True, args=["--use-angle=vulkan", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-features=Vulkan"])
            if args.film:
                await film(browser, args, manifest, root, base, web)
                await browser.close()
                return
            for slug, entry in manifest.items():
                if args.only and args.only not in slug:
                    continue
                for index, tab in enumerate(entry["tabs"]):
                    page = await browser.new_page(viewport={"width": args.width, "height": args.height})
                    url = f"http://127.0.0.1:{web}/?renderer=webgl&url={base}/{entry['rrd']}&url={base}/{tab['rbl']}{args.fragment}"
                    await page.goto(url, timeout=120_000)
                    await page.wait_for_timeout(args.wait_ms)
                    if args.at:
                        # the time readout at the bottom right is an egui text field: type the playhead time into it
                        await page.mouse.click(args.width - 100, args.height - 14)
                        await page.keyboard.press("Control+A")
                        await page.keyboard.type(args.at)
                        await page.keyboard.press("Enter")
                        await page.mouse.move(args.width / 2, 5)
                        await page.wait_for_timeout(4000)
                    shot = root / "shots" / f"{slug}--{index}{args.suffix}.png"
                    await page.screenshot(path=str(shot), timeout=90_000)
                    print(f"{shot.name}  ({tab['tab']})", flush=True)
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
