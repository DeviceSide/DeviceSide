"""Zigbee2MQTT's families, and the order their rule groups run in: the one home for the rule order (internals.md
points here).

A family is a vendor's firmware (docs/design.md, Family): its classes, its rules in named groups, its
levels and the data and calls only its classes need, under one path. The order inside a group is the family's, kept
beside the group; the order between groups is the integration's, below, as one family's rule can take another's
device. It matters where a comment says so; elsewhere no device can match two groups.
tests/integrations/zigbee2mqtt/test_classification.py pins the devices each constraint is about.
"""

from collections.abc import Collection, Sequence

from . import aqara, gledopto, hue, ikea, sengled, sonoff, tuya
from ..rules import FIELDS, REGISTRY
from ....core.rules import Rule, compose
from ....core.scope import Family

FAMILIES: tuple[Family, ...] = (
    hue.FAMILY,
    ikea.FAMILY,
    tuya.FAMILY,
    sonoff.FAMILY,
    sengled.FAMILY,
    gledopto.FAMILY,
    aqara.FAMILY,
)

RULES: tuple[Rule, ...] = compose(
    FIELDS,
    # First, before any rule on the Zigbee strings, so the registry alone places a Hue device (REGISTRY_PLACED). Its
    # vendor is Z2M's own Philips string, which no Tuya rule matches.
    (hue.FAMILY, hue.RULES),
    # Before the vendor rules (`sengled`, `gledopto`), so a Tuya device sold under another vendor's definition
    # (Gledopto's GL-SPI-206P runs Tuya datapoints) takes its Tuya class.
    (tuya.FAMILY, tuya.ZIGBEE_RULES),
    # On IKEA's own Zigbee manufacturer string, which no Tuya device carries.
    (ikea.FAMILY, ikea.RULES),
    # Read from the definition alone, and no Tuya device has these definition models, so after Tuya's rules.
    (sonoff.FAMILY, sonoff.RULES),
    (sengled.FAMILY, sengled.RULES),
    (gledopto.FAMILY, gledopto.RULES),
    # On the Zigbee manufacturer string `Aqara`, which no Tuya device carries, so after Tuya's rules like the vendors'.
    (aqara.FAMILY, aqara.RULES),
    # Last, as they only stand in for Tuya's rules on the Zigbee strings.
    (tuya.FAMILY, tuya.REGISTRY_RULES),
)

# The classes the registry alone places for good (classes.placed), so a device in one needn't wait for its Zigbee
# strings. `hue`: its vendor is Z2M's own Philips string, which the definition sets and no later report changes. A
# property of the order above, not of the family: a class is one only while its rules, and every rule before them,
# read the registry alone, so no later report from bridge/devices can move a device into or out of it.
REGISTRY_PLACED: frozenset[str] = frozenset({hue.HUE})


def check_registry_placed(rules: Sequence[Rule], placed: Collection[str]) -> None:
    """Raise unless each class in `placed` has a rule, and that rule and every one before it read the registry alone."""
    for name in sorted(placed):
        last = max((index for index, rule in enumerate(rules) if rule.capability == name), default=-1)
        if last < 0 or any(not rule.conditions.keys() <= REGISTRY for rule in rules[: last + 1]):
            raise ValueError(f"class {name!r} can't be placed by the registry alone: a rule up to its own reads more")


check_registry_placed(RULES, REGISTRY_PLACED)
