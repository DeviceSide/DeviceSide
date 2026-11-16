"""Zigbee2MQTT's rule: how a family says which devices are its classes' (docs/evidence.md, Device classes).

A rule is a class and conditions; a family exports its rules in named groups, and families/__init__.py puts the
groups in order, the first match winning. A lab probe changes a family's rules, never this structure.

A rule reads two sources, both sync and with no I/O:

- The registry device, which Z2M fills from its definition at discovery: the vendor as manufacturer, the definition's
  model as `model_id` (research/2026-11-14-lab-probe.md, §1). Enough for Hue, Sengled and Gledopto.
- The device's Zigbee strings, its own manufacturer and model, and its definition's model and exposes, from the
  bridge cache's bridge/devices (bridge_cache.py, the one members.py lists groups from). Only they show a Tuya device
  under another vendor's definition (`_TZ3000_…`, `_TZE…`), which the registry doesn't (plan Decision 18): one that
  fell into `other` would take turn_on_for's call with Experimental features on, and Zigbee2MQTT would leave it on.
  Only the definition shows which TS011F plugs take Tuya's countdown (internals.md, `turn_on_for`).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

# The fields a rule may test: the registry device's; the Zigbee manufacturer and model bridge/devices holds; and from
# its definition there, Z2M's model and the properties of its device-wide top-level exposes (DEFINITION).
REGISTRY = frozenset({"manufacturer", "model", "model_id"})
ZIGBEE = {"zigbee_manufacturer": "manufacturer", "zigbee_model": "model_id"}  # rule field: bridge/devices key
DEFINITION = frozenset({"definition_model", "exposes"})


@dataclass(frozen=True, slots=True)
class Rule:
    """A class and the fields that place a device in it, each a regex the field must fully match; every condition
    must hold, and there is at least one. Whether the class is its family's is checked where the groups are composed
    (families/__init__.py)."""

    capability: str
    conditions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.conditions:
            raise ValueError(f"a rule for {self.capability!r} tests nothing")
        if unknown := self.conditions.keys() - REGISTRY - ZIGBEE.keys() - DEFINITION:
            raise ValueError(f"a rule tests {sorted(unknown)}, which neither the registry nor bridge/devices holds")

    def matches(self, strings: Mapping[str, str | frozenset[str] | None]) -> bool:
        """Whether every condition holds: a string field fully matches its pattern, a set (`exposes`) has a member
        that does."""
        return all(
            any(re.fullmatch(pattern, value) for value in values)
            if isinstance(values := strings.get(name), frozenset)
            else isinstance(values, str) and re.fullmatch(pattern, values)
            for name, pattern in self.conditions.items()
        )
