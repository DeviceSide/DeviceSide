"""Zigbee2MQTT's families, and the order their rule groups run in: the one home for the rule order (internals.md
points here).

A family is a vendor's firmware (docs/design.md, Family): its classes, its rules in named groups, its
levels and the code only its classes need, under one path. The order inside a group is the family's, kept beside the
group; the order between groups is the integration's, below, as one family's rule can take another's device. It
matters where a comment says so; elsewhere no device can match two groups.
"""

from . import gledopto, hue, sengled, tuya
from ..rules import REGISTRY, Rule
from ....core.scope import Family

FAMILIES: tuple[Family, ...] = (hue.FAMILY, tuya.FAMILY, sengled.FAMILY, gledopto.FAMILY)


def _group(family: Family, rules: tuple[Rule, ...]) -> tuple[Rule, ...]:
    """A family's rule group, which names only that family's classes: no family places a device in another's class,
    or in the default one."""
    if foreign := sorted({rule.capability for rule in rules} - family.classes):
        raise ValueError(f"family {family.key!r}: its rules name classes that aren't its own: {foreign}")
    return rules


RULES: tuple[Rule, ...] = (
    # First, before any rule on the Zigbee strings, so the registry alone places a Hue device (REGISTRY_PLACED). Its
    # vendor is Z2M's own Philips string, which no Tuya rule matches.
    *_group(hue.FAMILY, hue.RULES),
    # Before the vendor rules (`sengled`, `gledopto`), so a Tuya device sold under another vendor's definition
    # (Gledopto's GL-SPI-206P runs Tuya datapoints) takes its Tuya class.
    *_group(tuya.FAMILY, tuya.ZIGBEE_RULES),
    *_group(sengled.FAMILY, sengled.RULES),
    *_group(gledopto.FAMILY, gledopto.RULES),
    # Last, as they only stand in for Tuya's rules on the Zigbee strings.
    *_group(tuya.FAMILY, tuya.REGISTRY_RULES),
)

# The classes placed by the registry alone (classes.placed), as their families declare them. A class is one only
# while its rules, and every rule before them, read the registry alone: then no later report from bridge/devices can
# move a device into or out of it.
REGISTRY_PLACED: frozenset[str] = hue.REGISTRY_PLACED


def _check_registry_placed() -> None:
    for name in sorted(REGISTRY_PLACED):
        last = max((index for index, rule in enumerate(RULES) if rule.capability == name), default=-1)
        if last < 0 or any(not rule.conditions.keys() <= REGISTRY for rule in RULES[: last + 1]):
            raise ValueError(f"class {name!r} can't be placed by the registry alone: a rule up to its own reads more")


_check_registry_placed()
