"""Record the site's hero video and stills from the REAL example reports, headlessly.

    uv run --no-project --with playwright==1.64.1 python record_hero.py --site <site out dir>

Opens ``examples/ur5e-conveyor/report.html`` (and the planar 2R one) from a local http server this
script starts on a free port and stops, in headless Chromium (never a visible window), and:

- drives the primary flow: the statistics with their verdict columns, scrub the synced transport under
  the 3D view and orbit it, the TCP error along the belt, the verdict details and the ISO 9283 card,
  then the "Sim → Real" tab;
- films it stop-motion: a real screenshot after every step (scrub positions, orbit increments), each
  held for a set time, joined by ffmpeg into ``media/hero.mp4`` (H.264, yuv420p, faststart),
  ``media/hero.gif`` (small fallback) and ``media/hero-poster.png``;
- takes the stills the site embeds: ``media/ur5e-conveyor.png``, ``media/planar-2r.png``,
  ``media/report-{overview,3d,tcp-error,iso,sim-to-real,videos}.png``;
- with ``--rerun-bin``, opens the example's .rrd in the real Rerun web viewer: ``media/rerun-viewer.png``.

WHY playwright==1.64.1: it drives the Chromium build already in ~/.cache/ms-playwright (1248), so
nothing is downloaded; any other installed build is the fallback. WHY SwiftShader flags: the 3D view
is WebGL and a headless shell has no GPU.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import os
import signal
import socket
import shutil
import subprocess
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import Page, async_playwright

FFMPEG = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
CHROMIUM_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
UR_REPORT = "examples/ur5e-conveyor/report.html"
PLANAR_REPORT = "examples/planar-2r/report.html"
VIDEO_SIZE = {"width": 1280, "height": 800}
HERO_MAX_S = 15.0


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    # WHY CORS: the Rerun web viewer (another local port) fetches the .rrd from this server
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def _serve(root: Path) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


async def _launch(playwright):
    try:
        return await playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS)
    except Exception as error:  # the bundled build for this playwright version is not installed
        cache = Path.home() / ".cache" / "ms-playwright"
        pattern = "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
        for candidate in sorted(cache.glob(pattern), reverse=True):
            print(f"  falling back to {candidate}")
            return await playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS, executable_path=str(candidate))
        raise SystemExit(f"no Chromium for playwright: {error}")


# ── driving the real report ─────────────────────────────────────────────────


def _section_js(title: str) -> str:
    """JS expression: the active page's section whose heading starts with ``title``."""
    return (f"[...document.querySelectorAll('.tc-page.active .tc-section')].find(s => "
            f"((s.querySelector('h2,h3,summary') || {{}}).textContent || '').trim().startsWith({title!r}))")


# WHY: the report's control bar is sticky; anything after it in the page sits under it once scrolled.
_TOP_OFFSET_JS = """(node) => {
  const bar = document.querySelector('.tc-page.active .tc-controls');
  const after = bar && (bar.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING);
  return (after ? bar.offsetHeight : 0) + 8;
}"""


async def _open_report(page: Page, url: str) -> None:
    # WHY generous: a 8 MB report with ~40 WebGL / uPlot canvases on a software renderer, often on a
    # machine other agents are loading too; a screenshot after a tab rebuild took over 30 s once.
    page.set_default_timeout(180_000)
    await page.goto(url, wait_until="load", timeout=180_000)
    await page.wait_for_function("document.querySelectorAll('.tc-page.active canvas').length > 0", timeout=120_000)
    await page.wait_for_timeout(1500)  # first WebGL frames and uPlot layout


async def _element(page: Page, selector_js: str):
    element = (await page.evaluate_handle(f"() => {selector_js}")).as_element()
    if element is None:
        raise SystemExit(f"not on the page: {selector_js}")
    return element


async def _scroll_top(page: Page, element) -> None:
    """Scroll ``element``'s top just below whatever sticky bar would cover it (instant: smooth tears)."""
    offset = await page.evaluate(_TOP_OFFSET_JS, element)
    await page.evaluate("([node, offset]) => window.scrollTo({top: node.getBoundingClientRect().top + "
                        "window.scrollY - offset, behavior: 'instant'})", [element, offset])


async def _jump(page: Page, selector_js: str) -> None:
    await _scroll_top(page, await _element(page, selector_js))


async def _scrub_to(page: Page, fraction: float) -> None:
    """Set the 3D section's transport slider to ``fraction`` of the track: the same transport the play
    button drives (plot cursors, 3D pose, videos). WHY the slider: playback advances per animation
    frame, which a loaded headless machine has few of; a set position is exact."""
    await page.evaluate(f"""(fraction) => {{ const s = ({_section_js('3D paths')}).querySelector('input[type=range]');
        s.value = String(Number(s.min) + (Number(s.max) - Number(s.min)) * fraction);
        s.dispatchEvent(new Event('input', {{bubbles: true}})); s.dispatchEvent(new Event('change', {{bubbles: true}})); }}""",
                        fraction)


async def _click_tab(page: Page, prefix: str) -> None:
    found = await page.evaluate(
        """(prefix) => { const tab = [...document.querySelectorAll('#tc-tabs button')]
             .find(b => b.textContent.trim().startsWith(prefix)); if (tab) tab.click(); return !!tab; }""",
        prefix,
    )
    if not found:
        raise SystemExit(f"no report tab starting {prefix!r}")


async def _open_verdicts(page: Page) -> None:
    await page.evaluate("document.querySelectorAll('.tc-page.active details.tc-verdicts').forEach(d => d.open = true)")


# ── the hero video ──────────────────────────────────────────────────────────


class _StopMotion:
    """The hero as a sequence of real screenshots of the report, each held for a set time.

    WHY not a screen recording: on a loaded machine (load average ~47 on 24 cores while this was
    built) both Playwright's recorder and a raw CDP screencast delivered frames seconds late and with
    stale timestamps, so every cut landed on the wrong step. ``page.screenshot`` waits for a fresh
    paint, so each frame is guaranteed to show the state the script just set, and the clip's length
    is the same however slow the machine is."""

    def __init__(self, page: Page, folder: Path) -> None:
        self.page = page
        self.folder = folder
        self.frames: list[tuple[Path, float]] = []

    async def shot(self, hold_s: float) -> None:
        path = self.folder / f"frame-{len(self.frames):04d}.png"
        await self.page.screenshot(path=str(path))
        self.frames.append((path, hold_s))

    def seconds(self) -> float:
        return sum(hold for _, hold in self.frames)

    def write(self, mp4: Path) -> None:
        lines = []
        for path, hold in self.frames:
            lines += [f"file '{path}'", f"duration {hold:.3f}"]
        lines.append(f"file '{self.frames[-1][0]}'")  # the concat demuxer needs the last file twice
        listing = self.folder / "frames.txt"
        listing.write_text("\n".join(lines) + "\n")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-vf", "fps=25,scale=1280:-2,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
                        "-crf", "26", "-movflags", "+faststart", "-an", str(mp4)], check=True)


async def record_hero(browser, base: str, media: Path, work: Path) -> None:
    context = await browser.new_context(viewport=VIDEO_SIZE, color_scheme="light")
    page = await context.new_page()
    await _open_report(page, f"{base}/{UR_REPORT}")
    film = _StopMotion(page, work)
    # 1 · the verdict first: the statistics table with its verdict columns
    await film.shot(1.8)
    # 2 · the 3D view: scrub the synced transport along the belt track, orbit, scrub on
    await _jump(page, _section_js("3D paths"))
    for step in range(9):
        await _scrub_to(page, 0.05 + 0.45 * step / 8)
        await film.shot(0.2)
    canvas = await _element(page, f"({_section_js('3D paths')}).querySelector('canvas')")
    box = await canvas.bounding_box()
    x0, y0 = box["x"] + box["width"] * 0.42, box["y"] + box["height"] * 0.45
    await page.mouse.move(x0, y0)
    await page.mouse.down()
    for step in range(1, 9):
        await page.mouse.move(x0 + 300 * step / 8, y0 - 40 * step / 8, steps=4)
        await film.shot(0.15)
    await page.mouse.up()
    for step in range(1, 9):
        await _scrub_to(page, 0.5 + 0.45 * step / 8)
        await film.shot(0.2)
    # 3 · the TCP error along / across the belt; the cursor line sits at the transport time
    await _jump(page, _section_js("TCP error"))
    await page.wait_for_timeout(400)
    await film.shot(2.1)
    # 4 · the verdict details and the ISO 9283 card
    await _open_verdicts(page)
    await _jump(page, "document.querySelector('.tc-page.active details.tc-verdicts')")
    await page.wait_for_timeout(400)
    await film.shot(2.2)
    # 5 · sim → real: sim is the reference, no target involved
    await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    await _click_tab(page, "Sim →")
    await page.wait_for_function("""() => { const page = document.querySelector('.tc-page.active');
        const title = page && page.querySelector('.tc-page-title');
        return title && title.textContent.trim().startsWith('Sim') && page.querySelectorAll('canvas').length > 0; }""",
                                 timeout=120_000)
    await page.wait_for_timeout(600)
    await film.shot(2.6)
    await context.close()
    if film.seconds() > HERO_MAX_S:
        raise SystemExit(f"hero would run {film.seconds():.1f} s; shorten the holds")
    mp4 = media / "hero.mp4"
    film.write(mp4)
    print(f"  hero: {film.seconds():.1f} s from {len(film.frames)} screenshots of the real report")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "0.3", "-i", str(mp4), "-frames:v", "1",
                    str(media / "hero-poster.png")], check=True)
    palette = work / "palette.png"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    "fps=8,scale=640:-1:flags=lanczos,palettegen=max_colors=80", str(palette)], check=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(mp4), "-i", str(palette), "-lavfi",
                    "fps=8,scale=640:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
                    str(media / "hero.gif")], check=True)
    for name in ("hero.mp4", "hero.gif", "hero-poster.png"):
        print(f"  wrote media/{name} ({(media / name).stat().st_size / 1024:.0f} KB)")


# ── stills ──────────────────────────────────────────────────────────────────


async def _shot(page: Page, element, path: Path, max_height: int = 980) -> None:
    """The top of ``element`` (at most ``max_height`` px), scrolled clear of the sticky bar first."""
    await _scroll_top(page, element)
    await page.wait_for_timeout(700)
    box = await element.bounding_box()
    height = min(box["height"], max_height, page.viewport_size["height"] - box["y"])
    await page.screenshot(path=str(path), clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": height})
    print(f"  wrote media/{path.name}")


async def stills(browser, base: str, media: Path) -> None:
    context = await browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="light")
    page = await context.new_page()
    await _open_report(page, f"{base}/{UR_REPORT}")
    # overview: the statistics table down to the verdict details
    await _open_verdicts(page)
    table = await _element(page, "document.querySelector('.tc-page.active .tc-tableblock') || "
                                 "document.querySelector('.tc-page.active table')")
    verdicts = await page.query_selector(".tc-page.active details.tc-verdicts") or table
    await _scroll_top(page, table)
    await page.wait_for_timeout(500)
    top, bottom = await table.bounding_box(), await verdicts.bounding_box()
    height = min(bottom["y"] + bottom["height"] - top["y"], page.viewport_size["height"] - top["y"])
    await page.screenshot(path=str(media / "report-overview.png"),
                          clip={"x": top["x"], "y": top["y"], "width": top["width"], "height": height})
    print("  wrote media/report-overview.png")
    iso = await page.query_selector(".tc-page.active .tc-aggregate")
    if iso:
        await _shot(page, iso, media / "report-iso.png")
    # the 3D view mid-motion: scrub the transport to just past the middle of the track
    three = await _element(page, _section_js("3D paths"))
    await _scroll_top(page, three)
    await page.evaluate(f"""() => {{ const s = ({_section_js('3D paths')}).querySelector('input[type=range]');
        if (s) {{ s.value = String((Number(s.min) + Number(s.max)) * 0.55);
                  s.dispatchEvent(new Event('input', {{bubbles: true}}));
                  s.dispatchEvent(new Event('change', {{bubbles: true}})); }} }}""")
    await page.wait_for_timeout(1200)
    await _shot(page, three, media / "report-3d.png", max_height=900)
    await _shot(page, await _element(page, f"({_section_js('3D paths')}).querySelector('canvas')"),
                media / "ur5e-conveyor.png")
    await _shot(page, await _element(page, _section_js("TCP error")), media / "report-tcp-error.png", max_height=1000)
    await _shot(page, await _element(page, _section_js("Videos")), media / "report-videos.png", max_height=700)
    await _click_tab(page, "Sim →")
    await page.wait_for_timeout(1200)
    await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    await page.wait_for_timeout(800)
    await page.screenshot(path=str(media / "report-sim-to-real.png"))
    print("  wrote media/report-sim-to-real.png")
    await context.close()

    if (media.parent / PLANAR_REPORT).is_file():
        context = await browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page = await context.new_page()
        await _open_report(page, f"{base}/{PLANAR_REPORT}")
        await page.screenshot(path=str(media / "planar-2r.png"))  # the top: verdict table and the first plots
        print("  wrote media/planar-2r.png")
        await context.close()


async def rerun_still(playwright, base: str, media: Path, rerun_bin: list[str], rrd: str) -> None:
    """The example's .rrd in the real Rerun web viewer, headless: ``media/rerun-viewer.png``.

    Starts ``rerun --serve-web`` on free ports (and stops it), opens its web viewer on the .rrd this
    script serves, WebGL renderer (the WebGPU backend panicked headless), Chromium on Vulkan ANGLE
    (SwiftShader timed out on the viewer's first frame)."""

    def free_port() -> int:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    web, grpc = free_port(), free_port()
    # WHY a session of its own: the venv's `rerun` is a wrapper that starts the real binary as a child,
    # so stopping only the wrapper's pid left the viewer server running; the whole group is stopped.
    process = subprocess.Popen([*rerun_bin, "--serve-web", "--web-viewer-port", str(web), "--port", str(grpc)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    browser = None
    try:
        await asyncio.sleep(4)
        if process.poll() is not None:
            print("  rerun --serve-web exited; media/rerun-viewer.png stays pending")
            return
        browser = await playwright.chromium.launch(
            headless=True, args=["--use-angle=vulkan", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-features=Vulkan"])
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})
        await page.goto(f"http://127.0.0.1:{web}/?renderer=webgl&url={base}/{rrd}", timeout=120_000)
        await page.wait_for_timeout(25_000)  # wasm start-up, the .rrd decode, the first frames
        await page.screenshot(path=str(media / "rerun-viewer.png"), timeout=90_000)
        print("  wrote media/rerun-viewer.png")
    finally:
        if browser is not None:
            await browser.close()
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


async def run(site: Path, video: bool, still: bool, rerun_bin: list[str] | None = None) -> None:
    media = site / "media"
    media.mkdir(exist_ok=True)
    server, base = _serve(site)
    try:
        async with async_playwright() as playwright:
            browser = await _launch(playwright)
            try:
                if still:
                    await stills(browser, base, media)
                if video:
                    with tempfile.TemporaryDirectory() as scratch:
                        await record_hero(browser, base, media, Path(scratch))
            finally:
                await browser.close()
            rrds = sorted((site / "examples" / "ur5e-conveyor" / "rerun").glob("*.rrd"))
            if rerun_bin and rrds:
                main = next((rrd for rrd in rrds if "target-sim-real" in rrd.name), rrds[0])  # the full page
                await rerun_still(playwright, base, media, rerun_bin, str(main.relative_to(site)))
    finally:
        server.shutdown()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, required=True, help="the site output folder (holds examples/)")
    parser.add_argument("--no-video", action="store_true", help="stills only")
    parser.add_argument("--no-stills", action="store_true", help="the hero video only")
    parser.add_argument("--rerun-bin", nargs="+", metavar="ARG",
                        help="command that runs the pinned Rerun (e.g. uvx --from rerun-sdk==0.40.0 rerun); "
                             "with it, also screenshot the .rrd in the Rerun web viewer")
    args = parser.parse_args()
    site = args.site.resolve()
    if not (site / UR_REPORT).is_file():
        raise SystemExit(f"{site / UR_REPORT} is missing: build the examples first (build_site.py --examples)")
    asyncio.run(run(site, video=not args.no_video, still=not args.no_stills, rerun_bin=args.rerun_bin))


if __name__ == "__main__":
    main()
