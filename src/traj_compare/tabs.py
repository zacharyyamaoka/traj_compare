"""The run view's question tabs and the arm / hand parts, shared by the HTML report and Rerun.

One set of tabs for both viewers (docs/NAVIGATION.md, Part B, frozen 2026-11-19). WHY one module (Zach
2026-11-19, traj compare view feedback: "designing a different run viewer for standalone and rerun is a
bit silly ... they should be the exact same thing"): the titles, the headings and the rule that drops a
tab with nothing to show live here once, so the two viewers cannot drift apart.

- ``TABS``: every fixed question tab in the contract's order, with its exact title and heading.
- ``CHANNELS_TAB``: "What else was measured?", one section per recorded channel (NAVIGATION.md C1), after ``signals``.
- ``tabs_for(payload)``: the tabs an ``analyze_comparison`` payload can fill (``payload["tabs"]``).
- ``normalize_parts(joint_names, parts)``: ``Comparison.parts`` as the payload's ``payload["parts"]``.
- ``resolve_tab(name)``: a tab by id, by title, or by a pre-2026-11-19 title.
- ``SubTab``: inside a tab, one fixed graph (or fixed group of graphs) the HTML view shows at a time.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# The part every joint falls into when ``Comparison.parts`` is None (no part selector is drawn).
IMPLICIT_PART = "All joints"
# The trailing part holding the joints ``Comparison.parts`` does not name.
OTHER_PART = "Other joints"


@dataclass(frozen=True)
class SubTab:
    """One sub-tab inside a question tab: the fixed graph, or fixed stack of graphs, it shows.

    ``title`` is the short text on the sub-tab ("q / qd / qdd"); ``words`` says it in plain words ("angle, speed and
    acceleration"); ``sections`` are the report's section ids it draws, top to bottom. Several per-joint sections
    stack per joint (each joint's q, qd and qdd one under the other, on the same time axis).

    WHY sub-tabs (Zach 2026-11-25, traj compare 3D viewer feedback): the graphs are fixed; you pick which one you look
    at (the sub-tab) and which series it draws (the legend), instead of toggling graphs on and off with chips.
    """

    id: str
    title: str
    sections: tuple[str, ...]
    words: str = ""


@dataclass(frozen=True)
class Tab:
    """One question tab: its id, the exact title on the tab, the exact heading inside it, and its HTML sections.

    ``html_sections`` are the report's section ids (``model._SECTION_IDS``) the tab holds. ``track`` holds
    none: it carries the page-level blocks (statistics table, verdicts, aggregate cards, Summary / Insights
    pages, worst moment) instead. ``legacy_titles`` are the pre-2026-11-19 Rerun tab names that still open it.
    ``subtabs`` are the HTML view's sub-tabs, in order; a tab with two or more sections and no ``subtabs`` gets one
    sub-tab per section (``tabs_for``).
    """

    id: str
    title: str
    heading: str
    html_sections: tuple[str, ...] = ()
    legacy_titles: tuple[str, ...] = ()
    subtabs: tuple[SubTab, ...] = ()


# WHY these titles (Zach 2026-11-19, traj compare view feedback): tab titles "super descriptive" —
# "Where?" → "Where is the error?" is better. The order is the order a reviewer asks the questions in.
TABS: tuple[Tab, ...] = (
    Tab(
        id="track",
        title="Did it track the target?",
        heading="How well did each run follow the target, and when was it worst?",
        legacy_titles=("Is it good?",),
    ),
    Tab(
        id="where",
        title="Where is the error?",
        heading="Where along the path is the tool off the target, and in which direction?",
        html_sections=("tcp-err", "tcp-pose"),
        legacy_titles=("Where?",),
        subtabs=(
            SubTab("error", "Tool error", ("tcp-err",), "position, rotation, off-path and lag error"),
            SubTab("pose", "Tool pose", ("tcp-pose",), "position and orientation in the world frame"),
        ),
    ),
    Tab(
        id="joints",
        title="Which joint has the error?",
        heading="Which joint contributes the most tracking error?",
        html_sections=("joint-err",),
        legacy_titles=("Which joint?",),
    ),
    Tab(
        id="timing",
        title="Is it late or off the path?",
        heading="Is the tool behind schedule (timing) or off the path (shape)?",
        html_sections=("path",),
        legacy_titles=("Timing or shape?",),
    ),
    Tab(
        id="torque",
        title="Feedforward or feedback?",
        heading="How much of the commanded torque comes from the feedforward model, and how much from feedback?",
        html_sections=("joint-torque",),
        legacy_titles=("Feedforward or feedback?",),
    ),
    Tab(
        id="signals",
        title="Raw signals per joint",
        heading="Every measured joint signal: angle, speed, acceleration, torque, current",
        html_sections=("joint-q", "joint-qd", "joint-qdd", "joint-tau", "joint-current"),
        legacy_titles=("Signals",),
        # WHY exactly these six, in this order (Zach 2026-11-25, traj compare 3D viewer feedback): one signal at a time,
        # then the two stacks he reads together; current, when recorded, after them
        subtabs=(
            SubTab("q", "q", ("joint-q",), "joint angle"),
            SubTab("qd", "qd", ("joint-qd",), "joint speed"),
            SubTab("qdd", "qdd", ("joint-qdd",), "joint acceleration"),
            SubTab("qddd", "qddd", ("joint-qddd",), "joint jerk"),
            SubTab("tau", "T", ("joint-tau",), "joint torque"),
            SubTab("q-qd-qdd", "q / qd / qdd", ("joint-q", "joint-qd", "joint-qdd"), "angle, speed and acceleration"),
            SubTab("q-qd-qdd-qddd", "q / qd / qdd / qddd", ("joint-q", "joint-qd", "joint-qdd", "joint-qddd"),
                   "angle, speed, acceleration and jerk"),
            SubTab("q-qd-tau", "q / qd / T", ("joint-q", "joint-qd", "joint-tau"), "angle, speed and torque"),
            SubTab("current", "Current", ("joint-current",), "motor current"),
        ),
    ),
)

# Every recorded signal beyond the joints (``Situation.channels``), one section per channel: docs/NAVIGATION.md C1.
# WHY not in ``TABS``: ``TABS`` are the six fixed question tabs of Part B, each with sections known in advance; this
# one is data-driven like the check tabs — its sections are whatever channels the runs recorded — so ``tabs_for``
# appends it right after ``signals`` only when a situation (the target included) has a channel.
CHANNELS_TAB = Tab(
    id="channels",
    title="What else was measured?",
    heading="How did every other recorded signal change over the run?",
)

_BY_ID = {tab.id: tab for tab in (*TABS, CHANNELS_TAB)}


def _runs_with(payload: Mapping[str, Any], key: str) -> bool:
    return any(
        entry.get("role") != "target" and entry.get("plot") and entry["plot"].get(key) is not None
        for entry in payload["situations"]
    )


def _available_sections(payload: Mapping[str, Any]) -> set[str]:
    """The section ids this payload can draw — the same conditions as ``sectionDefs`` in ``assets/plots.js``."""

    sections = {"joint-q", "joint-qd", "joint-qdd"}
    if payload.get("has_qddd"):
        sections.add("joint-qddd")
    if payload.get("has_tau"):
        sections.add("joint-tau")
    if payload.get("has_current"):
        sections.add("joint-current")
    if payload.get("has_torque_breakdown"):
        sections.add("joint-torque")
    if _runs_with(payload, "err_q"):
        sections.add("joint-err")
    if payload.get("has_cartesian"):
        sections.update({"tcp-pose", "path"})
        if _runs_with(payload, "xyz_mag"):
            sections.add("tcp-err")
    return sections


def _shown(tab: Tab, payload: Mapping[str, Any], sections: list[str]) -> bool:
    """The contract's "Shown when" column, plus: a tab whose sections are all absent has nothing to show."""

    if tab.id in ("where", "timing"):
        shown = bool(payload.get("has_cartesian"))  # a tool frame exists (fk or poses)
    elif tab.id == "joints":
        shown = len(payload["joint_names"]) >= 2  # one joint has nothing to rank
    elif tab.id == "torque":
        shown = bool(payload.get("has_torque_breakdown"))
    else:  # track, signals: always
        shown = True
    return shown and (not tab.html_sections or bool(sections))


def _subtabs(tab: Tab, sections: list[str], titles: Mapping[str, str]) -> list[dict[str, Any]]:
    """``tab``'s sub-tabs this payload can draw: a sub-tab needs every one of its sections. A tab with two or more
    sections and no fixed ``subtabs`` gets one per section, titled ``titles[section]`` (a channel's title)."""

    if tab.subtabs:
        return [{"id": sub.id, "title": sub.title, "words": sub.words, "sections": list(sub.sections)}
                for sub in tab.subtabs if all(section in sections for section in sub.sections)]
    if len(sections) < 2:
        return []
    return [{"id": section, "title": titles.get(section, section), "words": "", "sections": [section]}
            for section in sections]


def tabs_for(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The tabs an ``analyze_comparison`` payload fills, in order: ``[{"id", "title", "heading", "sections", "subtabs"}]``.

    A tab with nothing to show is dropped, in both viewers, by this one rule (NAVIGATION.md Part B):
    ``where`` and ``timing`` need a tool frame, ``joints`` at least two joints (and a joint error to rank),
    ``torque`` a torque breakdown; ``track`` and ``signals`` are always there. ``sections`` lists only the
    tab's sections this payload can draw (``joint-tau`` only with ``tau``, and so on). ``channels``
    (``CHANNELS_TAB``) follows ``signals`` when any situation, the target included, has a channel
    (``payload["channels"]``), one ``channel-<slug>`` section each (NAVIGATION.md C1).
    ``subtabs`` (``[{"id", "title", "words", "sections"}]``, ``_subtabs``) are the HTML view's sub-tabs; empty for a
    tab of fewer than two sections. The tabs of ``payload["panels"]`` (``traj_compare.panels``) come first, each
    ``{"id": "panel-<id>", "title", "heading", "sections": [], "subtabs": [], "panel": <index>}``.
    """

    available = _available_sections(payload)
    shown: list[dict[str, Any]] = []
    for tab in TABS:
        sections = [section for section in tab.html_sections if section in available]
        heading = tab.heading
        if tab.id == "signals" and "joint-qddd" in available:
            sections.insert(sections.index("joint-qdd") + 1, "joint-qddd")
            heading = heading.replace("acceleration,", "acceleration, jerk,")
        if _shown(tab, payload, sections):
            shown.append({"id": tab.id, "title": tab.title, "heading": heading, "sections": sections,
                          "subtabs": _subtabs(tab, sections, {})})
    # the channels tab: one section per recorded channel (payload["channels"], analysis.py), right after signals
    channels = list(payload.get("channels") or ())
    channel_sections = [channel["section"] for channel in channels]
    if channel_sections:
        after = next((index + 1 for index, tab in enumerate(shown) if tab["id"] == "signals"), len(shown))
        tab = CHANNELS_TAB
        titles = {channel["section"]: str(channel.get("title") or channel.get("name") or channel["section"])
                  for channel in channels}
        shown.insert(after, {"id": tab.id, "title": payload.get("channels_title") or tab.title,
                             "heading": tab.heading, "sections": channel_sections,
                             "subtabs": _subtabs(tab, channel_sections, titles)})
    # the caller's panel tabs (``Comparison.panels``: a table at the playhead, a log) lead, in the caller's order.
    # WHY first: a comparison that has them is a recorded procedure, and "what is each joint told now" is its first
    # question (Zach 2026-11-27, the JointCommandSequence viewer). ``panel`` indexes ``payload["panels"]["tabs"]``.
    panel_tabs = (payload.get("panels") or {}).get("tabs") or ()
    taken = {entry["id"] for entry in shown}
    lead = []
    for index, panel in enumerate(panel_tabs):
        tab_id = panel_tab_id(panel["id"])
        if tab_id in taken:
            raise ValueError(f"two tabs share the id {tab_id!r}")
        taken.add(tab_id)
        lead.append({"id": tab_id, "title": panel["title"], "heading": panel["heading"], "sections": [], "subtabs": [],
                     "panel": index})
    return lead + shown


def panel_tab_id(panel_id: str) -> str:
    """The tab id of a ``Comparison.panels`` tab (``#tab=panel-now``): ``panel-`` + the panel's id, so it can never
    collide with a question tab."""

    return f"panel-{panel_id}"


def channel_slug(name: str) -> str:
    """A channel's section slug: lowercased, every run outside ``[a-z0-9]`` -> ``-``, ends stripped (NAVIGATION.md C1).

    ``contact_force_n`` -> ``contact-force-n``. A name with no letter or digit at all slugs to ``channel``.
    """

    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-") or "channel"


def resolve_tab(name_or_id: str) -> Tab:
    """The tab named ``name_or_id``: its id (``"joints"``), its title, or a pre-2026-11-19 title (``"Which joint?"``).

    An unknown name raises ``ValueError`` listing the ids and titles that exist.
    """

    name = str(name_or_id)
    if name in _BY_ID:
        return _BY_ID[name]
    for tab in (*TABS, CHANNELS_TAB):
        if name == tab.title or name in tab.legacy_titles:
            return tab
    known = ", ".join(f"{tab.id} ({tab.title!r})" for tab in (*TABS, CHANNELS_TAB))
    raise ValueError(f"no question tab {name!r}; tabs: {known}")


def _joint_list(part: str, finger: str | None, joints: Any) -> list[str]:
    where = f"part {part!r}" + (f", finger {finger!r}" if finger is not None else "")
    # WHY a bare string is refused: "shoulder" is a Sequence of letters, never a list of one joint
    if isinstance(joints, (str, bytes)) or not isinstance(joints, Sequence):
        raise ValueError(f"{where}: expected a list of joint names, got {joints!r}")
    names = [str(joint) for joint in joints]
    if not names:
        raise ValueError(f"{where} names no joints")
    return names


def normalize_parts(
    joint_names: Sequence[str],
    parts: Mapping[str, Sequence[str] | Mapping[str, Sequence[str]]] | None,
) -> list[dict[str, Any]]:
    """``Comparison.parts`` as ``[{"name", "groups": [{"name", "joints"}]}]``, in the caller's order.

    A part's value is a list of joint names (an **arm**, one group named ``""``) or ``{finger: [joints]}``
    (a **hand**, one group per finger). Every named joint must exist and appear once (else ``ValueError``);
    joints not named fall into a trailing part ``"Other joints"``, in ``joint_names`` order. ``None`` (or an
    empty mapping) is one implicit part ``"All joints"`` holding every joint: the viewers draw no part selector.

    WHY explicit (Zach 2026-11-19, traj compare view feedback: "split the arm and the hand into separate
    concerns, and each arm separately"): the viewer never guesses arm / hand membership from joint names.
    """

    joint_names = [str(joint) for joint in joint_names]
    if not parts:
        return [{"name": IMPLICIT_PART, "groups": [{"name": "", "joints": list(joint_names)}]}]
    if not isinstance(parts, Mapping):
        raise ValueError(f"parts must map a part name to its joints, got {type(parts).__name__}")
    known = set(joint_names)
    owner: dict[str, str] = {}
    normalized: list[dict[str, Any]] = []
    for part_name, value in parts.items():
        part = str(part_name)
        if not part.strip():
            raise ValueError("a part needs a non-empty name")
        if isinstance(value, Mapping):
            if not value:
                raise ValueError(f"part {part!r} names no fingers")
            groups = []
            for finger_name, joints in value.items():
                finger = str(finger_name)
                if not finger.strip():
                    raise ValueError(f"part {part!r}: a finger needs a non-empty name")
                groups.append({"name": finger, "joints": _joint_list(part, finger, joints)})
        else:
            groups = [{"name": "", "joints": _joint_list(part, None, value)}]
        for group in groups:
            for joint in group["joints"]:
                if joint not in known:
                    raise ValueError(f"part {part!r} names unknown joint {joint!r}; joints: {joint_names}")
                if joint in owner:
                    raise ValueError(
                        f"joint {joint!r} appears twice (in part {owner[joint]!r} and part {part!r}); "
                        "each joint belongs to one part"
                    )
                owner[joint] = part
        normalized.append({"name": part, "groups": groups})
    unnamed = [joint for joint in joint_names if joint not in owner]
    if unnamed:
        if any(part["name"] == OTHER_PART for part in normalized):
            raise ValueError(
                f"joints {unnamed} are in no part, and {OTHER_PART!r} is already a part name; name them explicitly"
            )
        normalized.append({"name": OTHER_PART, "groups": [{"name": "", "joints": unnamed}]})
    return normalized
