"""Classification rules for an integration with families (docs/design.md, Family): which devices are a class's.

One rule type and one composer for every integration, so the checks that keep one family's rules out of another's
classes run wherever rules are composed, with no integration able to skip them. What the fields are, and how they are
read off a device, is each integration's (its `rules.py`); the order between the families' rule groups is too (its
`families/__init__.py`).
"""

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from .scope import Family


@dataclass(frozen=True, slots=True)
class Rule:
    """A class and the fields that place a device in it: each condition names a field and a regex its value must
    fully match, and every condition must hold. `compose` checks the class and the fields."""

    capability: str
    conditions: Mapping[str, str]

    def matches(self, device: Mapping[str, str | frozenset[str] | None]) -> bool:
        """Whether every condition holds for a device's fields: a string fully matches its pattern, a set has a member
        that does, and a field the device lacks matches nothing."""
        return all(
            any(re.fullmatch(pattern, value) for value in values)
            if isinstance(values := device.get(name), frozenset)
            else isinstance(values, str) and re.fullmatch(pattern, values) is not None
            for name, pattern in self.conditions.items()
        )


def compose(fields: Collection[str], *groups: tuple[Family, Iterable[Rule]]) -> tuple[Rule, ...]:
    """An integration's ordered rules: the families' rule groups joined in the order given, the first match winning
    (`match`). Each group comes with the family it is from, and `fields` are the names a rule may test. Raises for a
    rule that names a class its family doesn't hold, as a family places devices in its own classes only, never in
    another's or the default one; for one that tests a field outside `fields`, which would never match; and for one
    that tests nothing, which would match every device."""
    composed: list[Rule] = []
    for family, group in groups:
        for rule in group:
            if rule.capability not in family.classes:
                raise ValueError(f"family {family.key!r}: a rule names {rule.capability!r}, which isn't its class")
            if not rule.conditions:
                raise ValueError(f"family {family.key!r}: a rule for {rule.capability!r} tests nothing")
            if unknown := sorted(rule.conditions.keys() - set(fields)):
                raise ValueError(
                    f"family {family.key!r}: a rule for {rule.capability!r} tests {unknown}, not among {sorted(fields)}"
                )
            composed.append(rule)
    return tuple(composed)


def match(rules: Iterable[Rule], device: Mapping[str, str | frozenset[str] | None]) -> str | None:
    """The class of the first rule a device's fields match, or None."""
    return next((rule.capability for rule in rules if rule.matches(device)), None)
