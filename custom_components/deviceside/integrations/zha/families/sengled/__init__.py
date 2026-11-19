"""Sengled bulbs on ZHA: their class (internals.md, Tested behavior)."""

from homeassistant.const import Platform

from .....core.rules import Rule
from .....core.scope import Family

SENGLED = "sengled"

RULES = (
    # The lab's E11-G13 reads `sengled`.
    Rule(SENGLED, {"manufacturer": "(?i:sengled)"}),
)

FAMILY = Family(
    key="sengled",
    maintainers=(),
    classes={SENGLED: frozenset({Platform.LIGHT})},
    # In no scope: not built on every action. Its probe found it departs (it drops a level while off, refuses the
    # timer), and no pass or research predicts it takes the rest (docs/evidence.md, In Labs); turn_on_for's call harms
    # it, so the integration refuses it there with a reason (refusals.py).
)
