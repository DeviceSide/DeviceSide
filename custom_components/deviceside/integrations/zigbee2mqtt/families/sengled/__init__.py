"""Sengled on Zigbee2MQTT: its bulbs ignore `on_time` (index.md, Device classes), so they are a class of their own."""

from ...rules import Rule
from .....core.scope import Family, FamilyScope, experimental

SENGLED = "sengled"

RULES = (Rule(SENGLED, {"manufacturer": "Sengled"}),)

_UNTESTED = FamilyScope(capabilities=experimental(SENGLED))
FAMILY = Family(
    key="sengled",
    maintainers=(),
    classes=frozenset({SENGLED}),
    # No turn_on_for: the Sengled needs a host-side off, which nobody has built, so it is not built yet.
    scopes={
        "raise_brightness": _UNTESTED,
        "lower_brightness": _UNTESTED,
        "raise_hue": _UNTESTED,
        "lower_hue": _UNTESTED,
        "raise_saturation": _UNTESTED,
        "lower_saturation": _UNTESTED,
        "stop": _UNTESTED,
        "get_attributes": _UNTESTED,
        "set_attributes": _UNTESTED,
    },
)
