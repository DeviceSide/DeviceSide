"""Which RPC component instance a Shelly entity drives, and the device that serves it.

Read from the registry and the Shelly config entry only, never from aioshelly: importing it (or
homeassistant.components.shelly, which does) would make this adapter module unavailable wherever Shelly isn't installed.
"""

import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from ...core.models import Target
from ...core.scope import documented, verified

# Relays and lights carry unique_id "{mac}-{key}" (shelly/switch.py RpcRelaySwitch, shelly/light.py
# RpcShellyLightBase). Every other Shelly switch (virtual booleans, scripts, circuit breakers) has another suffix
# or key, and has no flip-back timer.
_UNIQUE_ID = re.compile(r"^[^-]+-(?P<key>switch|light|cct|rgb|rgbcct|rgbw):(?P<id>\d+)$")

COMPONENTS = {"switch": "Switch", "light": "Light", "cct": "CCT", "rgb": "RGB", "rgbcct": "RGBCCT", "rgbw": "RGBW"}

_DIMMABLE = frozenset({"brightness", "transition"})
_COLOR = frozenset({"hs_color", "rgb_color", "xy_color"})

# light.turn_on fields each component takes, as shelly/light.py translates them. A Switch shown as a light is on/off.
# RGB and RGBW take color too, but core converts it differently for them (rgb to rgbw with a white split, kelvin to
# color), so their color is dropped until those conversions are ported.
COMPONENT_FIELDS = {
    "Switch": frozenset(),
    "Light": _DIMMABLE,
    "CCT": _DIMMABLE | {"color_temp_kelvin"},
    "RGB": _DIMMABLE,
    "RGBW": _DIMMABLE,
    "RGBCCT": _DIMMABLE | _COLOR | {"color_temp_kelvin"},
}

# The components every Shelly adapter addresses. Light, CCT, RGB and RGBW take the same <Component>.Set, SetConfig
# and GetStatus calls as the Verified Switch and RGBCCT, documented identically by Shelly: Documented until a test
# record covers them (CLAUDE.md, "Release flag").
CAPABILITIES = verified("Switch", "RGBCCT") | documented("Light", "CCT", "RGB", "RGBW")

# The components raise_brightness, lower_brightness and stop address. DimStop halting a Set's fade is the rig's
# finding on RGBCCT (fw 2.0.3), documented by Shelly for none of them, and one user reports a Gen3 Dimmer jumping on
# DimStop: the others stay out of scope until a record covers them.
DIMMING_CAPABILITIES = verified("RGBCCT")


@dataclass(frozen=True, slots=True)
class RpcAddress:
    component: str
    id: int


def rpc_device(target: Target) -> Any | None:
    """The aioshelly RpcDevice behind the entity, or None on a Gen1 (block) device."""
    coordinator = getattr(getattr(target.config_entry, "runtime_data", None), "rpc", None)
    return coordinator.device if coordinator is not None else None


def address(target: Target) -> RpcAddress | None:
    if not (match := _UNIQUE_ID.match(target.entry.unique_id)):
        return None
    return RpcAddress(COMPONENTS[match["key"]], int(match["id"]))


def unsupported_reason(target: Target, capabilities: Collection[str] | None = None) -> str | None:
    """Why this entity can't take a timed Set within the capabilities in scope, or None."""
    if rpc_device(target) is None:
        return "gen1_unsupported"
    if (rpc := address(target)) is None:
        return "not_addressable"
    if capabilities is not None and rpc.component not in capabilities:
        return "capability_not_tested"
    return None
