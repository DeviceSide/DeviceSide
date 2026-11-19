"""IKEA on Zigbee2MQTT: its TRÅDFRI lights, in Labs on turn_on_for, and the two bulbs reported to stay on there.

Research names IKEA as running the Zigbee timer: about 25 of its bulbs and drivers advertise OnWithTimedOff, and three
reports say it works, against two bulbs that turn on by a unicast and never off, and two old models that don't advertise
it (research/2026-11-14-timed-on-call-patterns.md, §3). So `ikea` is in Labs on turn_on_for, on lights alone, and
those two bulbs are a class of their own, refused there (refusals.py). On every other action both take `other`'s level
(classes.py): in Labs on the brightness fades and stop, not built elsewhere.

The rules read the device's own Zigbee strings from bridge/devices, by the catalog both Zigbee stacks share
(zigbee/ikea.py), escaped: the registry shows Z2M's vendor `IKEA` and its definition's model, which names the two
bulbs as one definition. Until bridge/devices lists a device, it is `other`, Unplaced (classes.py).
"""

import re

from homeassistant.const import Platform

from .....core.rules import Rule
from .....core.scope import Family, FamilyScope, labs
from .....zigbee import ikea as strings

# IKEA's lights, and its outlets, which Zigbee2MQTT shows as a switch.
IKEA = "ikea"
# The TRÅDFRI GU10 white spectrum bulbs (LED2005R5, LED2106R3), reported to turn on by a unicast timer and never off.
IKEA_TIMER_HARMED = "ikea_timer_harmed"

_MANUFACTURER = re.escape(strings.MANUFACTURER)

# The reported bulbs first, as IKEA's rule matches their manufacturer too.
RULES = (
    Rule(
        IKEA_TIMER_HARMED,
        {"zigbee_manufacturer": _MANUFACTURER, "zigbee_model": "|".join(map(re.escape, strings.TIMER_HARMED_MODELS))},
    ),
    Rule(IKEA, {"zigbee_manufacturer": _MANUFACTURER}),
)

# Level Control's moves, which a Zigbee 3.0 dimmable light must take (docs/internals.md, Shared), as `other`'s are.
_CERTIFIED = FamilyScope(capabilities=labs(IKEA, IKEA_TIMER_HARMED))

FAMILY = Family(
    key="ikea",
    maintainers=(),
    classes={IKEA: frozenset({Platform.LIGHT, Platform.SWITCH}), IKEA_TIMER_HARMED: frozenset({Platform.LIGHT})},
    scopes={
        "raise_brightness": _CERTIFIED,
        "lower_brightness": _CERTIFIED,
        "stop": _CERTIFIED,
        # On lights alone: an outlet has no pass, and the integration refuses it on switches, as it does the two
        # bulbs reported to stay on (refusals.py).
        "turn_on_for": FamilyScope(capabilities=labs(IKEA, domains=(Platform.LIGHT,))),
    },
)
