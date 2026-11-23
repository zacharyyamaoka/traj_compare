"""The coverage page: one self-contained ``.html`` per payload (docs/COVERAGE.md, "The custom page").

The page reads only the payload (``traj_compare.coverage/1``), embedded as JSON, and draws every view in the browser:
``assets/coverage.js`` the 2-D figures, tabs and controls, ``assets/coverage3d.js`` (when present) the three.js views,
both colouring through ``assets/coverage_color.js``. No CDN, no server: it opens from disk.

WHY a page of our own beside Matplotlib / Viser / W&B: Zach, 2026-11-23, "a page you can see standalone or just quickly
get there from the traj compare stuff".
"""

from __future__ import annotations

import html
import importlib.resources
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _files
from ..report import _breadcrumb_html

SCHEMA = "traj_compare.coverage/1"


def _asset(name: str) -> str | None:
    """An asset's text, or None when the file is not there (coverage3d.js lands with its own lane)."""

    resource = importlib.resources.files("traj_compare").joinpath("assets", name)
    if not resource.is_file():
        return None
    return resource.read_text("utf-8")


def _script(text: str) -> str:
    # WHY: a literal "</script" inside an inlined script would end the block early
    return "<script>" + text.replace("</script", "<\\/script") + "</script>"


def _back(back: Iterable[Sequence[str]]) -> list[list[str]]:
    pairs = []
    for item in back:
        if isinstance(item, (str, bytes)) or len(item) != 2:
            raise ValueError(f"a back link is a (label, href) pair, got {item!r}")
        pairs.append([str(item[0]), str(item[1])])
    return pairs


def _siblings(siblings: Iterable[Mapping[str, Any] | Sequence[Any]]) -> list[dict[str, Any]]:
    """``[{"label", "href", "group", "current"}]``; a tuple ``(label, href[, group[, current]])`` is accepted too."""

    out = []
    for item in siblings:
        if isinstance(item, Mapping):
            entry = dict(item)
        elif isinstance(item, (str, bytes)) or not 2 <= len(item) <= 4:
            raise ValueError(f"a sibling is a mapping or (label, href[, group[, current]]), got {item!r}")
        else:
            entry = dict(zip(("label", "href", "group", "current"), item, strict=False))
        if "label" not in entry or "href" not in entry:
            raise ValueError(f"a sibling needs a label and an href, got {item!r}")
        out.append({"label": str(entry["label"]), "href": str(entry["href"]),
                    "group": str(entry.get("group") or ""), "current": bool(entry.get("current", False))})
    return out


def write_coverage_page(
    payload: Mapping[str, Any],
    path: Path | str,
    *,
    back: Sequence[Sequence[str]] = (),
    siblings: Sequence[Mapping[str, Any] | Sequence[Any]] = (),
) -> Path:
    """Write one self-contained coverage page for ``payload`` to ``path`` (parent folders created); returns the path.

    ``back`` (``[(label, href), ...]``) is the breadcrumb at the top; ``siblings`` (``[{"label", "href", "group",
    "current"}]``) are links to the other pages of the same dataset, drawn as chips grouped by ``group``. Either one,
    when given, replaces the payload's own ``back`` / ``siblings``; the payload passed in is not changed.
    """

    if payload.get("schema") != SCHEMA:
        raise ValueError(f"expected a {SCHEMA!r} payload, got schema {payload.get('schema')!r}")
    page_payload = dict(payload)
    if back:
        page_payload["back"] = _back(back)
    else:
        page_payload["back"] = _back(page_payload.get("back") or ())
    if siblings:
        page_payload["siblings"] = _siblings(siblings)
    else:
        page_payload["siblings"] = _siblings(page_payload.get("siblings") or ())

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    title = str(page_payload.get("title") or "Trajectory coverage")
    subtitle = str(page_payload.get("subtitle") or "")
    breadcrumb = _breadcrumb_html([tuple(pair) for pair in page_payload["back"]])
    # WHY allow_nan=False: the payload is JSON-safe by contract; a NaN would make JSON.parse throw in the browser
    data = json.dumps(page_payload, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")

    # WHY viewhelper.js: three.js' clickable orientation gizmo, the one the run report's 3-D view already uses (Zach's
    # viewer taste: a ViewCube to snap views); coverage3d.js falls back to a plain triad without it.
    scripts = [_script(_asset("three.min.js") or ""), _script(_asset("viewhelper.js") or ""),
               _script(_asset("coverage_color.js") or "")]
    three_d = _asset("coverage3d.js")
    if three_d is not None:
        scripts.append(_script(three_d))
    scripts.append(_script(_asset("coverage.js") or ""))
    scripts.append("<script>TrajCoverage.boot();</script>")

    document = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>{html.escape(title)} · coverage</title>
<style>{_asset("style.css")}</style>
<style>{_asset("coverage.css")}</style>
</head>
<body>
<div class='cov' data-cov-page>
<header class='tc cov-head'>
  {breadcrumb}<h1 data-cov-title>{html.escape(title)}</h1>
  <p class='cov-subtitle'>{html.escape(subtitle)}</p>
  <div class='cov-siblings' id='cov-siblings'></div>
</header>
<div id='cov-root'></div>
<footer class='tc'>traj_compare coverage page · payload {html.escape(SCHEMA)} · opens from disk, no server</footer>
</div>
<script type="application/json" id="cov-payload">{data}</script>
{chr(10).join(scripts)}
</body>
</html>
"""
    _files.write_text(path, document)
    return path
