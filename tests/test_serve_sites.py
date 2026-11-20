"""One server for many sites (docs/NAVIGATION.md Part C, C3; acceptance written before the code, 2026-11-20).

A *site* is a directory holding ``index.html`` and ``runs/``. ``python -m traj_compare.serve <dir>`` builds a run's
``report.html`` / ``rerun/<pair>.rrd`` on first request for a site at any depth below the served root (root included),
from that run folder's manifest alone (``traj_compare.dataset.build_run_folder``), under the one build lock; ``GET /``
with no ``index.html`` at the root answers a landing page of every site up to 3 levels deep; a dataset page's
"Open in Rerun" posts the .rrd's path resolved against the page URL.

Readings of the contract this file pins (the places it is not literal):

- "levels deep" counts path components of the site directory: ``ur5e`` is 1, ``lab/bam_fb`` is 2, ``a/b/c`` is 3 (listed),
  ``a/b/c/d`` is 4 (not listed). The root itself is never listed (with an own ``index.html`` it is served as is).
- "path order" is the sort order of the site paths as posix strings.
- "does NOT read every manifest" is measured as: while one lazy GET is served, every ``manifest.json`` read is of the
  requested run's own folder (so a root with three runs reads one folder, not three), and ``_find_run_folder`` is never called.
- "under the one build lock" is measured as: concurrent first requests for one report build it exactly once, and builds
  never overlap; the build is observed through ``traj_compare.dataset.write_comparison_report``, the call the run report
  is written with today.
- The .rrd parts need the Rerun SDK and are skipped without it; the browser test needs Node Playwright + Chrome
  (``TRAJ_COMPARE_PLAYWRIGHT``) and is skipped without them.

Run:

    cd /home/bam/traj_compare
    env -u VIRTUAL_ENV .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_serve_sites.py
"""

import inspect
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from test_dataset import make_run

from traj_compare import dataset, rerun_export
from traj_compare.dataset import write_dataset_report
from traj_compare.serve import make_handler

PLAYWRIGHT = Path(os.environ.get("TRAJ_COMPARE_PLAYWRIGHT", "/home/bam/aruco-studio/web/node_modules/playwright"))
CHROME = Path("/usr/bin/google-chrome")

needs_browser = pytest.mark.skipif(
    not (PLAYWRIGHT.is_dir() and CHROME.is_file() and shutil.which("node")),
    reason="needs Node Playwright and Chrome",
)
needs_rerun = pytest.mark.skipif(rerun_export.rr is None, reason="needs the Rerun SDK")

# site path -> (title, run count)
SITES = {
    "ur5e": ("UR five-e wrist", 3),
    "pendulum": ("Pendulum swing", 2),
    "lab/bam_fb": ("BAM fb rig", 1),
}


# ── helpers ──────────────────────────────────────────────────────────────────


def write_site(directory: Path, title: str, runs: int) -> None:
    write_dataset_report([make_run(index) for index in range(runs)], directory, title=title)


def write_sites(root: Path, sites: dict[str, tuple[str, int]]) -> None:
    for path, (title, runs) in sites.items():
        write_site(root / path, title, runs)


def run_folders(site: Path) -> list[Path]:
    return sorted(path.parent for path in (site / "runs").glob("*/manifest.json"))


def first_run(site: Path) -> Path:
    return run_folders(site)[0]


def site_rrds(site: Path) -> list[str]:
    """Every .rrd a site's pages link, relative to the site: runs/<slug>/rerun/<pair>.rrd (the name dataset.py documents as stable)."""
    names = []
    for folder in run_folders(site):
        manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
        names += [f"runs/{folder.name}/rerun/{dataset._pair_name(*pair)}.rrd" for pair in manifest["pairs"]]
    return names


def first_rrd(site: Path) -> str:
    return site_rrds(site)[0]


@contextmanager
def serving(root: Path, spawn=lambda argv: None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, spawn=spawn))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def fetch(url: str, method: str = "GET", timeout: float = 120) -> tuple[int, str]:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


class SiteLinks(HTMLParser):
    """Every ``<a data-tc-site>``: (site, href, text)."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str]] = []
        self._open: list | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and "data-tc-site" in attributes:
            self._open = [attributes["data-tc-site"], attributes.get("href"), ""]

    def handle_data(self, data):
        if self._open is not None:
            self._open[2] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._open is not None:
            site, href, text = self._open
            self.links.append((site, href, " ".join(text.split())))
            self._open = None


def site_links(page: str) -> list[tuple[str, str, str]]:
    parser = SiteLinks()
    parser.feed(page)
    return parser.links


# ── lazy builds in nested sites ──────────────────────────────────────────────


def test_a_nested_sites_report_is_built_on_first_request_in_its_own_run_folder(tmp_path):
    write_sites(tmp_path, SITES)
    folder = first_run(tmp_path / "ur5e")
    relative = f"ur5e/runs/{folder.name}/report.html"
    assert not (tmp_path / relative).exists()
    with serving(tmp_path) as base:
        status, body = fetch(f"{base}/{relative}")
    assert status == 200, body[:300]
    assert (tmp_path / relative).is_file()
    built = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("report.html"))
    assert built == [relative]  # only that run's folder; no other run and no other site grew a report


def test_a_site_two_levels_down_builds_its_report_too(tmp_path):
    write_sites(tmp_path, SITES)
    folder = first_run(tmp_path / "lab" / "bam_fb")
    relative = f"lab/bam_fb/runs/{folder.name}/report.html"
    with serving(tmp_path) as base:
        status, body = fetch(f"{base}/{relative}")
    assert status == 200, body[:300]
    assert (tmp_path / relative).is_file()


@needs_rerun
def test_a_nested_sites_recording_is_built_on_first_request(tmp_path):
    write_sites(tmp_path, SITES)
    site = tmp_path / "ur5e"
    relative = f"ur5e/{first_rrd(site)}"
    assert not (tmp_path / relative).exists()
    with serving(tmp_path) as base:
        status, body = fetch(f"{base}/{relative}")
    assert status == 200, body[:300]
    assert (tmp_path / relative).is_file()
    assert not list((tmp_path / "pendulum").rglob("*.rrd"))  # the other site is untouched


def test_the_root_site_still_builds_lazily(tmp_path):
    """Pins today's behaviour (passes before the change): a site at the served root itself."""
    write_site(tmp_path, "Root site", 2)
    folder = first_run(tmp_path)
    relative = f"runs/{folder.name}/report.html"
    assert not (tmp_path / relative).exists()
    with serving(tmp_path) as base:
        status, body = fetch(f"{base}/{relative}")
    assert status == 200, body[:300]
    assert (tmp_path / relative).is_file()


def test_a_missing_run_in_a_nested_site_is_a_404_not_a_build_failure(tmp_path):
    write_sites(tmp_path, {"ur5e": SITES["ur5e"]})
    with serving(tmp_path) as base:
        status, _ = fetch(f"{base}/ur5e/runs/nope/report.html")
    assert status == 404


# ── build_run_folder ─────────────────────────────────────────────────────────


def test_build_run_folder_is_public_and_takes_just_the_folder():
    build_run_folder = getattr(dataset, "build_run_folder", None)
    assert callable(build_run_folder), "traj_compare.dataset.build_run_folder does not exist"
    assert not build_run_folder.__name__.startswith("_")
    assert list(inspect.signature(build_run_folder).parameters) == ["folder"]


def test_build_run_folder_builds_the_report_from_the_folder_alone(tmp_path):
    write_site(tmp_path / "site", "Folder only", 2)
    folder = first_run(tmp_path / "site")
    # No site around it: no index.html, no sibling runs. Since NAVIGATION.md C6 (2026-11-20) a run folder names its
    # reference as ../../references/<digest>.npz, so "the folder alone" is the folder plus the reference it names.
    moved = tmp_path / "elsewhere" / "runs" / folder.name
    shutil.copytree(folder, moved)
    if (tmp_path / "site" / "references").is_dir():
        shutil.copytree(tmp_path / "site" / "references", tmp_path / "elsewhere" / "references")
    path = dataset.build_run_folder(moved)
    assert path == moved / "report.html" and path.is_file()
    assert not (folder / "report.html").exists()  # the original folder is not the one built
    assert not (tmp_path / "elsewhere" / "index.html").exists()


@needs_rerun
def test_build_run_folder_writes_the_recordings_beside_the_report(tmp_path):
    write_site(tmp_path, "Recordings", 1)
    folder = first_run(tmp_path)
    dataset.build_run_folder(folder)
    assert sorted(path.name for path in (folder / "rerun").glob("*.rrd"))


def test_build_drill_down_keeps_its_signature():
    """Pins today's behaviour (passes before the change)."""
    assert list(inspect.signature(dataset.build_drill_down).parameters) == ["output_dir", "run_name"]


# ── the serve path builds one run, never scans ───────────────────────────────


def counted_manifest_reads(monkeypatch) -> list[Path]:
    reads: list[Path] = []
    original = Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name == "manifest.json":
            reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    return reads


def test_a_lazy_build_reads_only_that_runs_manifest(tmp_path, monkeypatch):
    write_sites(tmp_path, {"ur5e": SITES["ur5e"], "pendulum": SITES["pendulum"]})
    write_site(tmp_path, "Root site", 3)  # the root site too: three runs, only one may be read
    cases = [first_run(tmp_path / "ur5e"), first_run(tmp_path)]
    reads = counted_manifest_reads(monkeypatch)
    with serving(tmp_path) as base:
        for folder in cases:
            reads.clear()
            status, body = fetch(f"{base}/{folder.relative_to(tmp_path).as_posix()}/report.html")
            assert status == 200, body[:300]
            others = [path for path in reads if path.parent != folder]
            assert reads and not others, f"read other runs' manifests while building {folder.name}: {others}"


def test_a_lazy_build_never_scans_for_the_run(tmp_path, monkeypatch):
    write_sites(tmp_path, {"ur5e": SITES["ur5e"]})
    write_site(tmp_path, "Root site", 2)

    def scan(*args, **kwargs):
        raise AssertionError("scanned every manifest through _find_run_folder")

    monkeypatch.setattr(dataset, "_find_run_folder", scan)
    with serving(tmp_path) as base:
        for site in (tmp_path / "ur5e", tmp_path):
            folder = first_run(site)
            status, body = fetch(f"{base}/{folder.relative_to(tmp_path).as_posix()}/report.html")
            assert status == 200, body[:300]
            assert (folder / "report.html").is_file()


def test_concurrent_first_requests_build_a_report_once_under_the_lock(tmp_path, monkeypatch):
    write_sites(tmp_path, {"ur5e": SITES["ur5e"], "pendulum": SITES["pendulum"]})
    original = dataset.write_comparison_report
    state = {"calls": 0, "inflight": 0, "peak": 0}
    guard = threading.Lock()

    def observed(*args, **kwargs):
        with guard:
            state["calls"] += 1
            state["inflight"] += 1
            state["peak"] = max(state["peak"], state["inflight"])
        try:
            time.sleep(0.3)  # long enough that an unlocked second build overlaps this one
            return original(*args, **kwargs)
        finally:
            with guard:
                state["inflight"] -= 1

    monkeypatch.setattr(dataset, "write_comparison_report", observed)
    targets = [first_run(tmp_path / "ur5e")] * 3 + [first_run(tmp_path / "pendulum")]
    results: list[int] = []
    with serving(tmp_path) as base:
        threads = [
            threading.Thread(
                target=lambda folder=folder: results.append(
                    fetch(f"{base}/{folder.relative_to(tmp_path).as_posix()}/report.html")[0]
                )
            )
            for folder in targets
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=300)
    assert results == [200] * 4
    assert state["calls"] == 2, state  # one build per distinct report
    assert state["peak"] == 1, state  # and never two at once


# ── the landing page ─────────────────────────────────────────────────────────


@pytest.fixture
def landed(tmp_path):
    write_sites(tmp_path, SITES)
    write_site(tmp_path / "a" / "b" / "c", "Three deep", 1)
    write_site(tmp_path / "a" / "b" / "c" / "d", "Four deep", 1)
    return tmp_path


def test_the_root_without_an_index_answers_a_landing_page_of_its_sites(landed):
    with serving(landed) as base:
        status, body = fetch(f"{base}/")
    assert status == 200
    links = site_links(body)
    assert links, "no <a data-tc-site> on the landing page"
    assert {site for site, _, _ in links} >= set(SITES)
    for site, href, _ in links:
        assert href == f"{site}/index.html"


def test_the_landing_page_lists_sites_in_path_order_up_to_three_levels_deep(landed):
    with serving(landed) as base:
        _, body = fetch(f"{base}/")
    listed = [site for site, _, _ in site_links(body)]
    assert listed == ["a/b/c", "lab/bam_fb", "pendulum", "ur5e"], listed  # a/b/c/d is 4 deep: not listed


def test_each_landing_link_says_the_sites_title_and_run_count(landed):
    with serving(landed) as base:
        _, body = fetch(f"{base}/")
    text = {site: text for site, _, text in site_links(body)}
    expected = {**SITES, "a/b/c": ("Three deep", 1)}
    assert set(expected) <= set(text), text
    for site, (title, runs) in expected.items():
        assert title in text[site], (site, text[site])
        assert re.search(rf"(?<!\d){runs}(?!\d)", text[site].replace(title, "")), (site, text[site])
        assert not re.search(r"(?<!\d)(?!%d)\d+(?!\d)" % runs, text[site].replace(title, "")), (
            f"{site}: more than the run count in {text[site]!r}"
        )


def test_index_html_at_a_root_without_its_own_answers_the_landing_page_too(landed):
    with serving(landed) as base:
        status, body = fetch(f"{base}/index.html")
    assert status == 200
    assert {site for site, _, _ in site_links(body)} >= set(SITES)


def test_a_landing_link_opens_the_site(landed):
    with serving(landed) as base:
        _, body = fetch(f"{base}/")
        links = {link[0]: link for link in site_links(body)}
        assert "ur5e" in links, links
        site, href, _ = links["ur5e"]
        status, page = fetch(f"{base}/{href}")
    assert status == 200 and "UR five-e wrist" in page


def test_a_root_with_its_own_index_serves_that_instead(tmp_path):
    """Pins today's behaviour (passes before the change)."""
    write_site(tmp_path, "Root site", 1)
    write_sites(tmp_path, {"ur5e": SITES["ur5e"]})
    with serving(tmp_path) as base:
        for path in ("/", "/index.html"):
            status, body = fetch(f"{base}{path}")
            assert status == 200 and "Root site" in body
            assert not site_links(body)


# ── safety still holds for nested sites ──────────────────────────────────────


@needs_rerun
def test_open_posts_for_a_nested_recording_spawn_the_viewer_on_the_resolved_path(tmp_path):
    write_sites(tmp_path, SITES)
    rrd = f"ur5e/{first_rrd(tmp_path / 'ur5e')}"
    opened = []
    with serving(tmp_path, spawn=opened.append) as base:
        status, body = fetch(f"{base}/__rerun/open?rrd={urllib.parse.quote(rrd)}", method="POST")
    assert status == 200, body
    assert (tmp_path / rrd).is_file()
    assert len(opened) == 1 and str((tmp_path / rrd).resolve()) in opened[0]


def test_open_posts_outside_the_root_are_refused_from_a_nested_site(tmp_path):
    """Pins today's behaviour (passes before the change)."""
    root = tmp_path / "served"
    write_sites(root, {"ur5e": SITES["ur5e"]})
    (tmp_path / "outside.rrd").write_bytes(b"x")
    opened = []
    with serving(root, spawn=opened.append) as base:
        for rrd in ("ur5e/../../outside.rrd", "../outside.rrd", "ur5e/runs/../../../outside.rrd"):
            status, _ = fetch(f"{base}/__rerun/open?rrd={urllib.parse.quote(rrd)}", method="POST")
            assert status in (400, 403), (rrd, status)
    assert opened == []


def test_a_path_walking_out_of_a_nested_site_leaks_nothing(tmp_path):
    """Pins today's behaviour (passes before the change)."""
    root = tmp_path / "served"
    write_sites(root, {"ur5e": SITES["ur5e"]})
    (tmp_path / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    with serving(root) as base:
        for path in ("/ur5e/runs/..%2f..%2f..%2fsecret.txt", "/ur5e/runs/%2e%2e/%2e%2e/%2e%2e/secret.txt"):
            _, body = fetch(f"{base}{path}")
            assert "TOP-SECRET" not in body, path


def test_a_cross_origin_post_is_still_refused(tmp_path):
    """Pins today's behaviour (passes before the change)."""
    write_sites(tmp_path, {"ur5e": SITES["ur5e"]})
    opened = []
    with serving(tmp_path, spawn=opened.append) as base:
        request = urllib.request.Request(
            f"{base}/__rerun/open?rrd=ur5e/runs/x/rerun/a.rrd", method="POST", headers={"Origin": "http://evil.example"}
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=30)
    assert error.value.code == 403 and opened == []


# ── Open in Rerun from a nested dataset page (real headless Chrome) ──────────

DRIVER = r"""
const { chromium } = require(process.argv[2]);
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
(async () => {
  const browser = await chromium.launch({
    executablePath: process.argv[3], headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const out = {};
  for (const [name, url] of Object.entries(spec.pages)) {
    const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    const page = await context.newPage();
    const posts = [];
    page.on('request', (request) => { if (request.url().includes('/__rerun/open')) posts.push({ url: request.url(), method: request.method() }); });
    const record = { posts, error: null };
    out[name] = record;
    try {
      await page.goto(url);
      await page.click('[data-tc-targets-view] [data-view="runs"]', { timeout: 8000 });
      const button = page.locator('button[data-rerun]').first();
      await button.waitFor({ state: 'visible', timeout: 8000 });
      const answered = page.waitForResponse((response) => response.url().includes('/__rerun/open'), { timeout: 120000 });
      await button.click();
      const response = await answered;
      record.status = response.status();
    } catch (error) {
      record.error = String(error);
    }
    await context.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((error) => { console.error(error); process.exit(1); });
"""


@pytest.fixture(scope="module")
def opened_from_pages(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("sites_browser")
    write_site(root, "Root site", 2)
    write_site(root / "ur5e", "UR five-e wrist", 2)
    opened: list[list[str]] = []
    with serving(root, spawn=opened.append) as base:
        spec = {"pages": {"nested": f"{base}/ur5e/index.html", "root": f"{base}/index.html"}}
        (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        (root / "driver.js").write_text(DRIVER, encoding="utf-8")
        result = subprocess.run(
            ["node", str(root / "driver.js"), str(PLAYWRIGHT), str(CHROME), str(root / "spec.json")],
            capture_output=True, text=True, timeout=600,
        )  # fmt: skip
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(f"the browser driver crashed: {result.stderr[-3000:]}")
    measured = json.loads(result.stdout.strip().splitlines()[-1])
    measured["root_dir"] = root
    measured["spawned"] = opened
    return measured


def posted_rrd(record: dict) -> str:
    assert record["error"] is None, record["error"]
    assert len(record["posts"]) == 1 and record["posts"][0]["method"] == "POST", record["posts"]
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(record["posts"][0]["url"]).query)
    return query["rrd"][0]


@needs_browser
def test_open_in_rerun_on_a_nested_page_posts_the_path_from_the_served_root(opened_from_pages):
    rrd = posted_rrd(opened_from_pages["nested"])
    assert rrd in {f"ur5e/{own}" for own in site_rrds(opened_from_pages["root_dir"] / "ur5e")}, rrd
    assert re.fullmatch(r"ur5e/runs/[A-Za-z0-9][A-Za-z0-9._-]*/rerun/[A-Za-z0-9._-]+\.rrd", rrd), rrd


@needs_browser
@needs_rerun
def test_that_nested_open_reaches_the_viewer_with_the_recording_it_built(opened_from_pages):
    rrd = posted_rrd(opened_from_pages["nested"])
    assert rrd.startswith("ur5e/runs/"), rrd  # not the root site's recording of the same name
    assert opened_from_pages["nested"]["status"] == 200
    resolved = str((opened_from_pages["root_dir"] / rrd).resolve())
    assert (opened_from_pages["root_dir"] / rrd).is_file()
    assert any(resolved in argv for argv in opened_from_pages["spawned"]), opened_from_pages["spawned"]


@needs_browser
def test_open_in_rerun_on_the_root_page_still_posts_a_runs_path(opened_from_pages):
    """Pins today's behaviour (passes before the change)."""
    rrd = posted_rrd(opened_from_pages["root"])
    assert re.fullmatch(r"runs/[A-Za-z0-9][A-Za-z0-9._-]*/rerun/[A-Za-z0-9._-]+\.rrd", rrd), rrd
