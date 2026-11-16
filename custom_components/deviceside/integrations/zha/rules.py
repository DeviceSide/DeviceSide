"""ZHA's classification rules: what a rule reads off a device, and how a family's rule groups compose into the
integration's ordered list. Which strings name which class is each family's (families/<family>/); the order between
their groups is the integration's (families/__init__.py)."""

import re
from typing import NamedTuple

from ...core.scope import Family


class Rule(NamedTuple):
    """A class, a field of the device, and a regex the field must fully match. `manufacturer` and `model` are zigpy's
    raw Zigbee strings; `quirk` is the module that defines the On/Off cluster's `command`; `identity` is
    `manufacturer/model`, for a ban that names both (docs/evidence.md, Contrary evidence)."""

    cls: str
    field: str
    pattern: str


type Group = tuple[Rule, ...]


def match(rules: Group, manufacturer: str, model: str, quirk: str | None = None) -> str | None:
    """The class of the first rule a device with these Zigbee strings and On/Off `quirk` module matches, or None."""
    fields = {"manufacturer": manufacturer, "model": model, "quirk": quirk or "", "identity": f"{manufacturer}/{model}"}
    return next((rule.cls for rule in rules if re.fullmatch(rule.pattern, fields[rule.field])), None)


def compose(*groups: tuple[Family, Group]) -> Group:
    """The rule groups joined in the order given, each with the family it is from. A rule that names a class its
    family doesn't hold raises: a family places devices in its own classes only, never in another's."""
    for family, group in groups:
        if foreign := sorted({rule.cls for rule in group} - family.classes):
            raise ValueError(f"family {family.key!r}: its rules name classes that aren't its own: {foreign}")
    return tuple(rule for _family, group in groups for rule in group)
