"""Sengled on Zigbee2MQTT: its bulbs ignore `on_time` (index.md, Device classes), so they are a class of their own."""

from homeassistant.const import Platform

from .....core.rules import Rule
from .....core.scope import Family

SENGLED = "sengled"

RULES = (Rule(SENGLED, {"manufacturer": "Sengled"}),)

FAMILY = Family(
    key="sengled",
    maintainers=(),
    classes={SENGLED: frozenset({Platform.LIGHT})},
    # In no scope: not built on every action. ZHA's probe of its E11-G13 found it departs (it drops a level while off,
    # refuses the timer), and no pass or research predicts it takes the rest (docs/evidence.md, On trial). On
    # turn_on_for it needs a host-side off, which nobody has built.
)
