"""Build the traj_compare landing page + documentation into a static folder.

    python3 build_site.py                       # pages only (reuses whatever examples/media exist)
    python3 build_site.py --examples --record   # also (re)generate the example reports and the hero media
    python3 -m traj_compare.serve <out> --port 8767   # serve it: the Open in Rerun buttons then launch Rerun

Standard library only. Writes ``index.html`` and ``docs.html`` (style inlined, so each opens from disk)
plus ``style.css`` into ``--out`` (default: bam_ws/reports/media/traj-compare-site-2026-11-10, gitignored).

WHY the build reads the source instead of restating it: the Rerun pin, the ROS result codes, the
ErrorStats fields and every API name the docs mention are read from (or checked against) the code at
build time, so the docs fail to build rather than drift. The code snippets live in ``snippets/`` and
are executed by the build (``--no-run`` skips), so every snippet shown is a snippet that ran, with its
real output under it.
"""

from __future__ import annotations

import argparse
import ast
import html
import io
import json
import keyword
import os
import re
import shutil
import subprocess
import sys
import tokenize
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import diagrams
import site_content as content

SITE = Path(__file__).resolve().parent
TRAJ_COMPARE = SITE.parents[1]
TRAJ_COMPARE_SRC = TRAJ_COMPARE / "src" / "traj_compare"


def _robot_msgs_checkout() -> Path:
    """The robot_msgs source checkout whose code the docs are checked against.

    WHY a search, not one path: the site is built from bam_ws (robot_msgs six levels up), from this repo's own
    checkout beside ~/robot_msgs, and in CI from a clone at a pinned commit named by ``ROBOT_MSGS_DIR``."""
    candidates = [os.environ.get("ROBOT_MSGS_DIR"), TRAJ_COMPARE / "../../../../../../external/robot_msgs",
                  TRAJ_COMPARE.parent / "robot_msgs", Path.home() / "robot_msgs"]
    for candidate in candidates:
        if candidate and (Path(candidate) / "src" / "robot_msgs" / "compare").is_dir():
            return Path(candidate).resolve()
    raise SystemExit("no robot_msgs checkout found: set ROBOT_MSGS_DIR to one")


ROBOT_MSGS = _robot_msgs_checkout()
COMPARE_SRC = ROBOT_MSGS / "src" / "robot_msgs" / "compare"
INTEGRATION = TRAJ_COMPARE.parent / "traj_integration_tests"
UR_EXAMPLE = INTEGRATION / "src" / "traj_integration_tests" / "ur_compare" / "sim_to_real.py"


def _main_checkout() -> Path:
    """The repo's main checkout, even when this runs from a worktree (reports never live in one)."""
    try:
        common = subprocess.run(["git", "-C", str(SITE), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return SITE.parents[8]


DEFAULT_OUT = _main_checkout() / "reports" / "media" / "traj-compare-site-2026-11-10"
VENV_PYTHON = TRAJ_COMPARE / ".venv" / "bin" / "python"

# The examples the gallery shows: slug -> how to (re)build it with --examples.
INTEGRATION_PYTHON = INTEGRATION / ".venv" / "bin" / "python"
EXAMPLES = {
    "ur5e-conveyor": {
        "title": "UR5e on a conveyor (6-DOF)",
        "blurb": (
            "A UR5e (Pinocchio dynamics) tracks a straight segment along the belt at belt speed: target, sim "
            "and repeated “real” runs, one page per pairing. There is no UR on the bench: real is a "
            "stand-in, a perturbed plant, and the report says so."
        ),
        "tags": ["6-DOF", "conveyor frame", "sim → real", "verdicts", "latency", "ISO 9283", "robot model",
                 "videos", "real = stand-in"],
        # WHY a command, not a script: the example is the integration package's `ur-sim-real` command
        "command": ["-m", "traj_integration_tests", "ur-sim-real", "--out"],
        "python": INTEGRATION_PYTHON,
        "source": UR_EXAMPLE,
        "cwd": INTEGRATION,
        "pythonpath": [INTEGRATION / "src"],
    },
    "planar-2r": {
        "title": "Planar 2R swing (a five-bar's L1/L2 chain)",
        "blurb": (
            "The smallest complete example. Sim follows the same joint path 40 ms late; real is on time "
            "but J2 reads 1.5° high. Lag and offset look different in every field, the verdicts split "
            "them (the late sim breaks the path limit, the offset real misses the goal) and the latency "
            "estimate reads the 40 ms back."
        ),
        "tags": ["2-DOF", "lag vs offset", "L2 tip frame", "verdicts", "latency", "Rerun"],
        "command": [str(TRAJ_COMPARE / "examples" / "tracking_errors_demo.py"), "--rerun", "--exports", "--out"],
        "python": VENV_PYTHON,
        "source": TRAJ_COMPARE / "examples" / "tracking_errors_demo.py",
        "cwd": TRAJ_COMPARE,
        "pythonpath": [],
    },
    # WHY these three (2026-11-27, Zach: "there should be examples trajectories that I can load and see in the viewer
    # online"): every one is generated from the repo's own synthetic examples, so the public site carries no private
    # data and CI rebuilds it from the pushed commit.
    "torque-breakdown": {
        "title": "Torque breakdown on a vertical 2R arm",
        "blurb": (
            "Simulated moteus-style control at 1 kHz: commanded = feedforward + feedback, applied through a lagging "
            "current loop. “ff v1” underestimates gravity by 20 %, so its feedback slopes with the arm’s angle; "
            "“ff v2” has the true model and its feedback stays small. Each run records a different pair, the report "
            "derives the third."
        ),
        "tags": ["2-DOF", "torque", "feedforward vs feedback", "derived channels", "simulated"],
        "command": [str(TRAJ_COMPARE / "examples" / "torque_breakdown_demo.py"), "--out"],
        "python": VENV_PYTHON,
        "source": TRAJ_COMPARE / "examples" / "torque_breakdown_demo.py",
        "cwd": TRAJ_COMPARE / "examples",
        "pythonpath": [],
    },
    "camera-overlay": {
        "title": "Camera overlay + motor current on a 1-DOF rack",
        "blurb": (
            "Target, real and a twin on a one-joint rack, each carrying motor current. The Camera section stacks a "
            "stand-in real camera stream under the selected sim render, synced to the plots’ cursor; the camera "
            "started half a second into the trajectory and the report lines it up."
        ),
        "tags": ["1-DOF", "synced video", "camera overlay", "motor current", "synthetic video"],
        "command": [str(TRAJ_COMPARE / "examples" / "overlay_demo.py"), "--out"],
        "python": VENV_PYTHON,
        "source": TRAJ_COMPARE / "examples" / "overlay_demo.py",
        "cwd": TRAJ_COMPARE / "examples",
        "pythonpath": [],
    },
    "dataset": {
        "title": "A dataset of runs: twin iterations on two tapes",
        "blurb": (
            "Many runs at a glance: each run is one pass over a tape, recorded sim vs the sim after five twin "
            "iterations vs the real arm. Filter by tape, speed and gain set, read the ISO 9283 cards per tape and "
            "the sim-to-real summary, then drill into any run’s full report."
        ),
        "tags": ["dataset", "runs table", "drill-down", "ISO 9283 per tape", "sim → real summary"],
        "command": [str(TRAJ_COMPARE / "examples" / "dataset_demo.py"), "--static", "--runs", "4", "--out"],
        "python": VENV_PYTHON,
        "source": TRAJ_COMPARE / "examples" / "dataset_demo.py",
        "cwd": TRAJ_COMPARE / "examples",
        "pythonpath": [],
        "entry": "index.html",
    },
}


# ── facts read from the code ────────────────────────────────────────────────


def _read(path: Path) -> str:
    return path.read_text("utf-8")


def _dataclass_fields(path: Path, class_name: str) -> list[str]:
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            ]
    raise SystemExit(f"{path}: no class {class_name}")


def read_facts() -> dict:
    rerun_src = _read(TRAJ_COMPARE_SRC / "rerun_export.py")
    sdk = re.search(r'^RERUN_SDK_VERSION = "([^"]+)"', rerun_src, re.M)
    tolerances_src = _read(COMPARE_SRC / "tolerances.py")
    codes = {
        name: int(value)
        for name, value in re.findall(r"^(SUCCESSFUL|PATH_TOLERANCE_VIOLATED|GOAL_TOLERANCE_VIOLATED) = (-?\d+)",
                                      tolerances_src, re.M)
    }
    init = ast.parse(_read(COMPARE_SRC / "__init__.py"))
    exported: list[str] = []
    for node in init.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in node.targets):
            exported = [element.value for element in node.value.elts]
    if not sdk or len(codes) != 3 or not exported:
        raise SystemExit("could not read the Rerun pin, the result codes or robot_msgs.compare.__all__")
    return {
        "sdk": sdk.group(1),
        "codes": codes,
        "exported": exported,
        "error_stats": _dataclass_fields(COMPARE_SRC / "error_stats.py", "ErrorStats"),
        "comparison": _dataclass_fields(COMPARE_SRC / "comparison.py", "Comparison"),
        "tolerances": _dataclass_fields(COMPARE_SRC / "tolerances.py", "Tolerances"),
        "joint_tolerance": _dataclass_fields(COMPARE_SRC / "tolerances.py", "JointTolerance"),
        "outcome": _dataclass_fields(COMPARE_SRC / "tolerances.py", "Outcome"),
        "goal_stats": _dataclass_fields(COMPARE_SRC / "goal.py", "GoalStats"),
        "viewer_comparison": _dataclass_fields(TRAJ_COMPARE_SRC / "model.py", "Comparison"),
    }


def check_claims(facts: dict) -> list[str]:
    """Every name the docs state, checked against the code. Returns the problems found."""
    problems = []
    for name in content.CLAIMED_EXPORTS:
        if name not in facts["exported"]:
            problems.append(f"robot_msgs.compare does not export {name}")
    for key, names in content.CLAIMED_FIELDS.items():
        missing = [name for name in names if name not in facts[key]]
        if missing:
            problems.append(f"{key} lacks {missing}")
    if facts["error_stats"] != [row[0] for row in content.ERROR_STATS]:
        problems.append(f"ErrorStats fields changed: {facts['error_stats']}")
    for relative, probes in content.CLAIMED_SOURCE_STRINGS.items():
        text = _read(ROBOT_MSGS / relative) if not relative.startswith("traj_compare/") else _read(
            TRAJ_COMPARE / relative.removeprefix("traj_compare/"))
        for probe in probes:
            if probe not in text:
                problems.append(f"{relative} no longer contains {probe!r}")
    return problems


# ── code: highlighting, snippets ────────────────────────────────────────────

_BUILTINS = {"print", "len", "range", "min", "max", "dict", "tuple", "list", "zip", "enumerate", "lambda"}


def highlight(code: str) -> str:
    """Python syntax colouring with the tokenize module; falls back to plain text."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return html.escape(code)
    lines = code.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    out, cursor, previous = [], 0, None
    for token in tokens:
        if token.type in (tokenize.ENDMARKER,):
            break
        start = offsets[token.start[0] - 1] + token.start[1]
        end = offsets[token.end[0] - 1] + token.end[1]
        out.append(html.escape(code[cursor:start]))
        text = html.escape(code[start:end])
        cls = None
        if token.type == tokenize.COMMENT:
            cls = "com"
        elif token.type == tokenize.STRING or (hasattr(tokenize, "FSTRING_START") and token.type in (
                tokenize.FSTRING_START, tokenize.FSTRING_MIDDLE, tokenize.FSTRING_END)):
            cls = "str"
        elif token.type == tokenize.NUMBER:
            cls = "num"
        elif token.type == tokenize.NAME:
            if keyword.iskeyword(token.string):
                cls = "kw"
            elif previous is not None and previous.string in ("def", "class"):
                cls = "fn"
        out.append(f'<span class="tok-{cls}">{text}</span>' if cls else text)
        cursor = end
        if token.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            previous = token
    out.append(html.escape(code[cursor:]))
    return "".join(out)


def code_block(code: str, label: str = "", source: str = "", language: str = "python") -> str:
    body = highlight(code) if language == "python" else html.escape(code)
    head = ""
    if label or source:
        head = f'<div class="label">{html.escape(label)}<span class="src">{html.escape(source)}</span></div>'
    cls = "codeblock labelled" if head else "codeblock"
    return (f'<div class="{cls}">{head}<button class="copy" type="button">Copy</button>'
            f'<pre><code>{body.rstrip()}</code></pre></div>')


def snippet_source(name: str) -> str:
    text = _read(SITE / "snippets" / f"{name}.py")
    match = re.search(r"^# --- show\n(.*?)^# --- end", text, re.S | re.M)
    if not match:
        raise SystemExit(f"snippets/{name}.py has no '# --- show' / '# --- end' region")
    return match.group(1).rstrip()


def run_snippets(python: Path, extra_paths: list[str]) -> dict[str, str]:
    """Run every snippet; return name -> stdout. A failing snippet stops the build."""
    outputs = {}
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(SITE / "snippets"), *extra_paths, env.get("PYTHONPATH", "")]).strip(os.pathsep)
    env.setdefault("MPLBACKEND", "Agg")
    for path in sorted((SITE / "snippets").glob("[a-z]*.py")):
        result = subprocess.run([str(python), str(path)], cwd=path.parent, env=env, capture_output=True,
                                text=True, timeout=600)
        if result.returncode != 0:
            raise SystemExit(f"snippet {path.name} failed:\n{result.stderr[-3000:]}")
        outputs[path.stem] = result.stdout.rstrip()
        print(f"  ran snippets/{path.name}")
    return outputs


def snippet_block(name: str, outputs: dict[str, str], label: str = "") -> str:
    block = code_block(snippet_source(name), label, f"snippets/{name}.py")
    output = outputs.get(name)
    if output:
        block += ('<div class="codeblock labelled"><div class="label">Output<span class="src">captured when this '
                  f'page was built</span></div><pre><code>{html.escape(output)}</code></pre></div>')
    return block


def ur_example_code() -> tuple[str, str, str]:
    """The UR example's own code: (focused excerpt, its source path, the whole file); "" when absent.

    The excerpt is the module's tolerance / axis helpers and, verbatim, the statements of its main
    function that build the pages (``shared = dict(...)``, every ``Comparison(...)`` / ``Situation(...)``
    assignment and the ``write_comparison_report(...)`` call), joined in file order."""
    if not UR_EXAMPLE.is_file():
        return "", "", ""
    text = _read(UR_EXAMPLE)
    tree = ast.parse(text)
    pieces = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ("_tolerances", "_error_axes"):
            pieces.append(ast.get_source_segment(text, node) or "")
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or "write_comparison_report" not in (ast.get_source_segment(text, node) or ""):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
                continue
            called = statement.value.func
            name = getattr(called, "id", getattr(called, "attr", ""))
            if name in ("Comparison", "Situation", "write_comparison_report", "dict"):
                segment = ast.get_source_segment(text, statement) or ""
                indent = " " * statement.col_offset
                pieces.append("\n".join(line[len(indent):] if line.startswith(indent) else line
                                         for line in (indent + segment).splitlines()))
    excerpt = "\n\n".join(piece for piece in pieces if piece)
    return excerpt, str(UR_EXAMPLE.relative_to(INTEGRATION.parent)), text


# ── examples, media ─────────────────────────────────────────────────────────


def build_examples(out: Path, extra_paths: list[str], only: list[str]) -> None:
    for slug, example in EXAMPLES.items():
        if only and slug not in only:
            continue
        if not example["source"].is_file():
            print(f"  example {slug}: {example['source']} does not exist yet; skipped")
            continue
        target = out / "examples" / slug
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [*map(str, example["pythonpath"]), *extra_paths, env.get("PYTHONPATH", "")]).strip(os.pathsep)
        python = example["python"] if example["python"].exists() else Path(sys.executable)
        command = [str(python), *example["command"], str(target)]
        print(f"  building example {slug}: {' '.join(command)}")
        result = subprocess.run(command, cwd=example["cwd"], env=env, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise SystemExit(f"example {slug} failed:\n{result.stdout[-2000:]}\n{result.stderr[-4000:]}")


def publicize(out: Path, base_url: str) -> list[str]:
    """Rewrite the build folder's absolute path in the example pages to the URL they are served from.

    WHY: a report names its .rrd files by absolute path in its copy-able Rerun commands (``rerun /abs/x.rrd``); on a
    public host that path would name the build machine's folder and open nothing. ``rerun <url>`` opens the same file
    from the site, so the command still works when pasted. Returns the files changed."""
    changed = []
    roots = sorted({str(out), str(out.resolve())}, key=len, reverse=True)
    for path in sorted((out / "examples").rglob("*")):
        if path.suffix not in (".html", ".json", ".js", ".md", ".txt", ".csv") or not path.is_file():
            continue
        text = path.read_text("utf-8")
        new = text
        for root in roots:
            new = new.replace(root + "/", base_url)
            new = new.replace(root, base_url.rstrip("/"))
        # a dataset's manifest names the examples' import root: say it relative to the repo
        new = new.replace(str(TRAJ_COMPARE) + "/", "")
        if new != text:
            path.write_text(new, "utf-8")
            changed.append(str(path.relative_to(out)))
    return changed


def report_payload(report: Path) -> dict | None:
    match = re.search(r'<script type="application/json" id="traj-compare-data">(.*?)</script>',
                      report.read_text("utf-8"), re.S)
    if not match:
        return None
    return json.loads(match.group(1).replace("<\\/", "</"))


def discover_examples(out: Path) -> list[dict]:
    found = []
    for slug, example in EXAMPLES.items():
        folder = out / "examples" / slug
        report = folder / example.get("entry", "report.html")
        entry = {"slug": slug, **{k: v for k, v in example.items() if k in ("title", "blurb", "tags")},
                 "report": None, "pages": [], "rrds": [], "shot": None, "subtitle": ""}
        if report.is_file():
            entry["report"] = f"examples/{slug}/{report.name}"
            payload = report_payload(report) or {}
            header = re.search(r"<header class='tc'>\s*<h1>(.*?)</h1>\s*<p>(.*?)</p>", report.read_text("utf-8"), re.S)
            entry["subtitle"] = html.unescape(header.group(2)) if header else ""
            for page in payload.get("comparisons", []):
                entry["pages"].append({
                    "title": page.get("tab_title") or page.get("title"),
                    "group": page.get("group_title") or "",
                    "reference": page.get("reference_title", ""),
                    "runs": [s["title"] for s in page.get("situations", []) if s.get("role") != "target"],
                    "rrd": (page.get("rerun") or {}).get("rrd"),
                })
            # the report's own page order, so the first .rrd is the first (main) page's
            listed = [f"examples/{slug}/{page['rrd']}" for page in entry["pages"] if page["rrd"]]
            entry["rrds"] = [rrd for rrd in listed if (out / rrd).is_file()]
        shot = out / "media" / f"{slug}.png"
        if shot.is_file():
            entry["shot"] = f"media/{slug}.png"
        found.append(entry)
    return found


def media_state(out: Path) -> dict:
    media = out / "media"

    def have(name: str) -> str | None:
        return f"media/{name}" if (media / name).is_file() else None

    return {name: have(name) for name in content.MEDIA_FILES}


def record_media(out: Path, sdk: str) -> None:
    report = out / "examples" / "ur5e-conveyor" / "report.html"
    if not report.is_file():
        print("  --record: examples/ur5e-conveyor/report.html is missing; media stay pending")
        return
    venv_rerun = TRAJ_COMPARE / ".venv" / "bin" / "rerun"
    # the pinned viewer: the traj_compare venv's own (it is the rerun extra), else the same uvx pin
    rerun_bin = [str(venv_rerun)] if venv_rerun.exists() else ["uvx", "--from", f"rerun-sdk=={sdk}", "rerun"]
    # WHY playwright==1.64.1: it drives the Chromium build already installed, so nothing downloads
    command = ["uv", "run", "--no-project", "--with", "playwright==1.64.1", "python", str(SITE / "record_hero.py"),
               "--site", str(out), "--rerun-bin", *rerun_bin]
    print(f"  recording media: {' '.join(command)}")
    result = subprocess.run(command, cwd=SITE, capture_output=True, text=True, timeout=3600)
    print(result.stdout[-3000:])
    if result.returncode != 0:
        raise SystemExit(f"record_hero.py failed:\n{result.stderr[-4000:]}")


def record_example_stills(out: Path, channel: str | None) -> None:
    """``media/<slug>.png`` for every built example, with ``record_hero.py --example-stills`` (headless)."""
    command = ["uv", "run", "--no-project", "--with", "playwright==1.64.1", "python", str(SITE / "record_hero.py"),
               "--site", str(out), "--example-stills", *(["--channel", channel] if channel else [])]
    print(f"  example stills: {' '.join(command)}")
    result = subprocess.run(command, cwd=SITE, capture_output=True, text=True, timeout=1800)
    print(result.stdout[-3000:])
    if result.returncode != 0:
        raise SystemExit(f"record_hero.py --example-stills failed:\n{result.stderr[-4000:]}")


# ── the Open in Rerun control: the report's own code, extracted ────────────


def extract_js_function(source: str, name: str) -> str:
    match = re.search(rf"\n(\s*)function {re.escape(name)}\(", source)
    if not match:
        raise SystemExit(f"plots.js has no function {name}; the report's Rerun bar moved")
    start = match.start() + 1
    depth, index, opened = 0, source.index("{", start), False
    while index < len(source):
        char = source[index]
        if char == "{":
            depth += 1
            opened = True
        elif char == "}":
            depth -= 1
            if opened and depth == 0:
                return source[start:index + 1]
        index += 1
    raise SystemExit(f"plots.js: unbalanced braces in {name}")


def rerun_script() -> str:
    """``el``, ``copyText``, ``copyTextFallback`` and ``buildRerunBar`` exactly as the report ships them.

    WHY extracted, not rewritten: the site's button must behave exactly like the report's (POST to
    serve.py, else copy the pinned command; Download; Rerun in browser when served)."""
    plots = _read(TRAJ_COMPARE_SRC / "assets" / "plots.js")
    functions = "\n".join(extract_js_function(plots, name) for name in (
        "el", "copyText", "copyTextFallback", "buildRerunBar"))
    return ("(function () {\n'use strict';\n" + functions + """
  document.querySelectorAll('[data-rerun]').forEach(function (host) {
    buildRerunBar(host, JSON.parse(host.getAttribute('data-rerun')));
  });
})();""")


def rerun_command(sdk: str, rrd: Path, out: Path | None = None, base_url: str = "") -> str:
    # the same spelling as traj_compare.rerun_export.viewer_command (shlex.join of the argv); on a public site the
    # file's URL (Rerun opens http(s) URLs), never the build machine's path
    import shlex
    target = base_url + rrd.resolve().relative_to(out.resolve()).as_posix() if base_url and out else str(rrd.resolve())
    return shlex.join(["uvx", "--from", f"rerun-sdk=={sdk}", "rerun", target])


# ── sources and citations ───────────────────────────────────────────────────


class Citations:
    """``[[n:key,key]]`` → numbered superscript links; the Source Index lists them in first-use order."""

    def __init__(self, sources: dict[str, dict]) -> None:
        self.sources = sources
        self.order: list[str] = []

    def number(self, key: str) -> int:
        if key not in self.sources:
            raise SystemExit(f"unknown citation key {key!r}")
        if key not in self.order:
            self.order.append(key)
        return self.order.index(key) + 1

    def replace(self, text: str) -> str:
        def one(match: re.Match) -> str:
            keys = [key.strip() for key in match.group(1).split(",")]
            links = ",".join(f'<a href="#src-{self.number(k)}">{self.number(k)}</a>' for k in keys)
            return f'<sup class="cite">{links}</sup>'

        return re.sub(r"\[\[n:([^\]]+)\]\]", one, text)

    def index_html(self) -> str:
        items = []
        for number, key in enumerate(self.order, start=1):
            source = self.sources[key]
            title = html.escape(source["title"])
            label = f'<a href="{html.escape(source["url"])}">{title}</a>' if source.get("url") else title
            where = f' <span class="where">{source["where"]}</span>' if source.get("where") else ""
            items.append(f'<li id="src-{number}">{label}{where}</li>')
        unused = sorted(set(self.sources) - set(self.order))
        if unused:
            print(f"  note: sources never cited: {unused}")
        return '<ol class="sources">' + "".join(items) + "</ol>"


# ── templating ──────────────────────────────────────────────────────────────


def render(template: str, values: dict[str, str]) -> str:
    def one(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise SystemExit(f"template placeholder {{{{{key}}}}} has no value")
        return values[key]

    return re.sub(r"\{\{([a-z0-9_:.-]+)\}\}", one, template)


# ── link check ──────────────────────────────────────────────────────────────


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        for name in ("href", "src", "poster"):
            if attributes.get(name):
                self.links.append(attributes[name])
        if attributes.get("data-rerun"):
            self.links.append(json.loads(attributes["data-rerun"])["rrd"])


def check_links(out: Path, pages: list[str]) -> list[str]:
    parsed = {}
    for page in pages:
        parser = _Links()
        parser.feed((out / page).read_text("utf-8"))
        parsed[page] = parser
    problems = []
    for page, parser in parsed.items():
        for link in parser.links:
            parts = urlsplit(link)
            if parts.scheme in ("http", "https", "mailto", "data", "javascript"):
                continue
            path = unquote(parts.path)
            target = page if not path else os.path.normpath(os.path.join(os.path.dirname(page), path))
            if not (out / target).exists():
                problems.append(f"{page}: {link} → missing {target}")
                continue
            if parts.fragment and target in parsed and parts.fragment not in parsed[target].ids:
                problems.append(f"{page}: {link} → no #{parts.fragment} in {target}")
    return problems


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output folder (default {DEFAULT_OUT})")
    parser.add_argument("--examples", nargs="*", metavar="SLUG",
                        help="(re)build the example reports first (all, or the slugs named)")
    parser.add_argument("--record", action="store_true",
                        help="record the hero video + stills with record_hero.py (needs the UR5e example)")
    parser.add_argument("--no-run", action="store_true", help="do not execute the snippets (no outputs shown)")
    parser.add_argument("--python", type=Path, default=VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable),
                        help="interpreter with traj_compare + robot_msgs (default: traj_compare/.venv)")
    parser.add_argument("--extra-path", action="append", default=[],
                        help="prepend to PYTHONPATH for snippets and examples (repeatable)")
    parser.add_argument("--example-stills", action="store_true",
                        help="screenshot every built example (media/<slug>.png) for the gallery, headless")
    parser.add_argument("--browser-channel", default=None,
                        help="with --example-stills: a browser channel, e.g. chrome (an installed Chrome)")
    parser.add_argument("--public", metavar="URL", default="",
                        help="build for a public host served at URL (e.g. the GitHub Pages site): unbuilt examples are "
                             "left out, and paths of the build folder in pages and commands become URLs")
    args = parser.parse_args()
    if args.public and not args.public.endswith("/"):
        args.public += "/"
    out = args.out.resolve()
    args.python = Path(os.path.abspath(args.python))  # absolute, not resolved: a venv python is a symlink
    out.mkdir(parents=True, exist_ok=True)

    facts = read_facts()
    problems = check_claims(facts)
    if problems:
        raise SystemExit("the docs claim things the code no longer says:\n  " + "\n  ".join(problems))
    print(f"facts: Rerun {facts['sdk']}, codes {facts['codes']}, {len(facts['exported'])} exports checked")

    if args.examples is not None:
        build_examples(out, args.extra_path, args.examples)
    if args.public:  # before any still is shot, so the stills show the public commands too
        changed = publicize(out, args.public)
        print(f"  public: rewrote the build folder's path to {args.public} in {len(changed)} example files")
    if args.record:
        record_media(out, facts["sdk"])
    if args.example_stills:
        record_example_stills(out, args.browser_channel)
    outputs = {} if args.no_run else run_snippets(args.python, args.extra_path)

    examples = discover_examples(out)
    if args.public:  # WHY: a public page shows only what it can open
        examples = [example for example in examples if example["report"]]
    media = media_state(out)
    ur_code, ur_source, ur_file = ur_example_code()
    citations = Citations(content.SOURCES)
    css = _read(SITE / "style.css")
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    shared = {
        "css": css,
        "sdk": facts["sdk"],
        "stamp": stamp,
        "rerun_js": rerun_script(),
        "site_js": content.SITE_JS,
        "run_note": ("The output under each snippet is what it printed when this page was built."
                     if outputs else "(Snippets were not executed for this build.)"),
        "serve_command": (f"uv run --directory {content.display_path(TRAJ_COMPARE)} python -m traj_compare.serve "
                          f"{content.display_path(out)} --port 8767") if not args.public else
                         "python -m traj_compare.serve <folder holding this site> --port 8767",
    }
    context = {
        "facts": facts, "examples": examples, "media": media, "outputs": outputs, "out": out,
        "ur_code": ur_code, "ur_source": ur_source, "ur_file": ur_file,
        "ur_subtitle": next((e["subtitle"] for e in examples if e["slug"] == "ur5e-conveyor"), ""), "code_block": code_block, "snippet_block": snippet_block,
        "rerun_command": lambda sdk, rrd: rerun_command(sdk, rrd, out, args.public), "diagrams": diagrams,
        "shared": shared, "public": args.public,
    }
    pages = {
        "index.html": content.index_values(context),
        "docs.html": content.docs_values(context),
    }
    for name, values in pages.items():
        template = _read(SITE / "templates" / name)
        page = render(template, {**shared, **values})
        page = citations.replace(page) if name == "docs.html" else page
        if name == "docs.html":
            page = page.replace("<!--SOURCE_INDEX-->", citations.index_html())
        (out / name).write_text(page, "utf-8")
        print(f"wrote {out / name} ({len(page) / 1024:.0f} KB)")
    shutil.copy2(SITE / "style.css", out / "style.css")

    problems = check_links(out, list(pages))
    if problems:
        raise SystemExit("broken internal links:\n  " + "\n  ".join(problems))
    pending = [name for name, path in media.items() if path is None]
    print(f"links ok · examples: {[e['slug'] for e in examples if e['report']] or 'none'} · "
          f"media pending: {pending or 'none'}")


if __name__ == "__main__":
    main()
