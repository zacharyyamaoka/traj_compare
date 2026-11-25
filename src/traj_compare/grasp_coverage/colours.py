"""One colour per outcome, for all four grasp viewers (the workbench's data-ui slots, the PNGs, Viser).

WHY these slots (data-ui packages/core tokens.css, light theme): 1 is #2a78d6 and 2 #eb6834, the Nov 19 gallery's blue
(succeeded) and orange (closed, then missed) that Zach called "super helpful" for "showing where the failures where and
not"; hovered is muted grey (it never closed: the gallery's grey); refused is amber (a gate said no); unknown (no outcome:
a label) is violet, a hue with no status meaning. Any other word takes pink, then teal, never green or red first: those
read as a verdict the word may not mean.
"""

from __future__ import annotations

from collections.abc import Sequence

OUTCOME_SLOTS = {"picked": 1, "failed": 2, "hovered": 0, "refused": 4, "unknown": 7}
SPARE_SLOTS = (5, 3, 6, 8)
# data-ui's series slots in the light theme (0 = muted)
SLOT_HEX = {0: "#8a8983", 1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a", 4: "#eda100", 5: "#e87ba4", 6: "#008300",
            7: "#6250d6", 8: "#e34948"}
GROUP_SLOTS = (1, 2, 3, 7, 5, 4, 6)


def outcome_slots(order: Sequence[str]) -> dict[str, int]:
    """Each outcome in `order` -> its data-ui slot (known words fixed, other words the spare slots in turn)."""
    spare = iter(SPARE_SLOTS)
    return {name: OUTCOME_SLOTS[name] if name in OUTCOME_SLOTS else next(spare, 0) for name in order}


def outcome_hex(order: Sequence[str]) -> dict[str, str]:
    return {name: SLOT_HEX[slot] for name, slot in outcome_slots(order).items()}


def group_hex(groups: Sequence[str], group_by: str) -> dict[str, str]:
    """The colour of each of a payload's `source.groups`: outcome colours when they are outcomes, else the slots."""
    if group_by == "outcome":
        return outcome_hex(groups)
    return {name: SLOT_HEX[GROUP_SLOTS[i % len(GROUP_SLOTS)]] for i, name in enumerate(groups)}
