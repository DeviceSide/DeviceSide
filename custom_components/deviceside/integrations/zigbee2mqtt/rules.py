"""Zigbee2MQTT's rule fields: what a family's rule (core/rules.py) may test on Zigbee2MQTT, and how each is read off a
device (docs/evidence.md, Device classes). Which strings name which class is each family's (families/<family>/); the
order between their rule groups is the integration's (families/__init__.py). A lab probe changes a family's rules,
never this structure.

A rule reads two sources, both sync and with no I/O:

- The registry device, which Z2M fills from its definition at discovery: the vendor as manufacturer, the definition's
  model as `model_id` (research/2026-11-14-lab-probe.md, §1). Enough for Hue, Sengled and Gledopto.
- The device's Zigbee strings, its own manufacturer and model, and its definition's model and exposes, from the
  bridge cache's bridge/devices (bridge_cache.py, the one members.py lists groups from). Only they show a Tuya device
  under another vendor's definition (`_TZ3000_…`, `_TZE…`), which the registry doesn't (plan Decision 18): one that
  fell into `other` would take turn_on_for's call with Labs on, and Zigbee2MQTT would leave it on.
  Only the definition shows which TS011F plugs take Tuya's countdown (internals.md, `turn_on_for`).
"""

from collections.abc import Mapping

from homeassistant.helpers import device_registry as dr

# The fields a rule may test: the registry device's; the Zigbee manufacturer and model bridge/devices holds; and from
# its definition there, Z2M's model and the properties of its device-wide top-level exposes (DEFINITION).
REGISTRY = frozenset({"manufacturer", "model", "model_id"})
ZIGBEE = {"zigbee_manufacturer": "manufacturer", "zigbee_model": "model_id"}  # rule field: bridge/devices key
DEFINITION = frozenset({"definition_model", "exposes"})
FIELDS = REGISTRY | ZIGBEE.keys() | DEFINITION


def zigbee_strings(entry: Mapping | None) -> dict[str, str]:
    """The Zigbee manufacturer and model in a device's bridge/devices entry, as rule fields, each only when it is a
    non-empty string (Z2M holds null until the interview reads it); empty with no entry."""
    if entry is None:
        return {}
    return {name: value for name, key in ZIGBEE.items() if isinstance(value := entry.get(key), str) and value}


def definition_fields(entry: Mapping | None) -> dict[str, str | frozenset[str]]:
    """The rule fields from the definition in a device's bridge/devices entry: Z2M's model (`definition_model`), and
    the properties of its top-level exposes for the whole device, none for an endpoint (`exposes`), each only when the
    entry holds it (Z2M holds a null definition for a device it doesn't support); empty with no entry."""
    definition = entry.get("definition") if entry is not None else None
    if not isinstance(definition, Mapping):
        return {}
    fields: dict[str, str | frozenset[str]] = {}
    if isinstance(model := definition.get("model"), str) and model:
        fields["definition_model"] = model
    if isinstance(exposes := definition.get("exposes"), list):
        # By property, and the device's own alone: a per-endpoint copy keeps the name and suffixes the property
        # (`countdown_l1`, with `endpoint` set: ZHC's `withEndpoint`).
        fields["exposes"] = frozenset(
            prop
            for expose in exposes
            if isinstance(expose, Mapping)
            and expose.get("endpoint") is None
            and isinstance(prop := expose.get("property"), str)
        )
    return fields


def read(
    device: dr.DeviceEntry, bridge: Mapping[str, str | frozenset[str] | None] | None = None
) -> dict[str, str | frozenset[str] | None]:
    """A device's rule fields: the registry device's, and those read off its bridge/devices entry (`bridge`: its
    zigbee_strings and definition_fields)."""
    return {name: getattr(device, name) for name in REGISTRY} | dict(bridge or {})
