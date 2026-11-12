"""Which RPC component instance a Shelly entity drives, and the device that serves it.

Read from the registry and the Shelly config entry only, never from aioshelly: importing it (or
homeassistant.components.shelly, which does) would make this adapter module unavailable wherever Shelly isn't installed.
"""

import re
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant

from ...core.errors import Reason
from ...core.models import Target
from ...core.scope import documented, experimental, verified

# Relays and lights carry unique_id "{mac}-{key}" (shelly/switch.py RpcRelaySwitch, shelly/light.py
# RpcShellyLightBase). Every other Shelly switch (virtual booleans, scripts, circuit breakers) has another suffix
# or key, and has no flip-back timer.
_UNIQUE_ID = re.compile(r"^[^-]+-(?P<key>switch|light|cct|rgb|rgbcct|rgbw):(?P<id>\d+)$")

COMPONENTS = {"switch": "Switch", "light": "Light", "cct": "CCT", "rgb": "RGB", "rgbcct": "RGBCCT", "rgbw": "RGBW"}

_DIMMABLE = frozenset({"brightness", "transition"})
_COLOR = frozenset({"hs_color", "rgb_color", "xy_color"})

# light.turn_on fields each component takes, as shelly/light.py translates them. A Switch shown as a light is on/off.
# RGB and RGBW take color too, but core converts it differently for them (rgb to rgbw with a white split, kelvin to
# color), so their color is dropped until those conversions are ported. CCT takes ct, but as CCT.Set {ct} without the
# bulb's mode switch: a call no record covers, and fields are never Documented, so it is dropped until one does.
COMPONENT_FIELDS = {
    "Switch": frozenset(),
    "Light": _DIMMABLE,
    "CCT": _DIMMABLE,
    "RGB": _DIMMABLE,
    "RGBW": _DIMMABLE,
    "RGBCCT": _DIMMABLE | _COLOR | {"color_temp_kelvin"},
}

# The components every Shelly adapter addresses. Light, CCT, RGB and RGBW take the same <Component>.Set, SetConfig
# and GetStatus calls as the Verified RGBCCT (whose Set carries brightness as theirs do, Switch.Set doesn't),
# documented identically by Shelly: Documented (docs/evidence.md, Levels).
CAPABILITIES = verified("Switch", "RGBCCT") | documented("Light", "CCT", "RGB", "RGBW")

# The components the persistent auto-off / auto-on adapters address. Their GetConfig and SetConfig are the same on
# every component, documented identically by Shelly, and the adapter confirms the setting it stored by reading it
# back: the Switch's record proves the call and the rest ride it, RGBCCT included (docs/evidence.md, Levels).
AUTO_CAPABILITIES = verified("Switch") | documented("Light", "CCT", "RGB", "RGBW", "RGBCCT")

# The components raise_brightness, lower_brightness and stop address. DimStop halting a Set's fade is the rig's
# finding on RGBCCT (fw 2.0.3), documented by Shelly for none of them, and one user reports a Gen3 Dimmer jumping on
# DimStop: the others take the same calls, so they stay flagged experimental, untested, until a maintainer verifies
# them, and the PR landing that verification makes them verified(...). That one unconfirmed report keeps Light from
# Documented, not from the flag: the option is opt-in, and a jump is what testers report (docs/evidence.md, The
# experimental flag).
DIMMING_CAPABILITIES = verified("RGBCCT") | experimental("Light", "CCT", "RGB", "RGBW")


@dataclass(frozen=True, slots=True)
class RpcAddress:
    component: str
    id: int


class RpcComponent:
    """Mixed into every Shelly adapter, ahead of Adapter: the capability a call reaches is the entity's RPC
    component, which the dispatcher weighs against the scope's capabilities."""

    def capability(self, hass: HomeAssistant, target: Target) -> str | None:
        return rpc.component if (rpc := address(target)) is not None else None


def rpc_device(target: Target) -> Any | None:
    """The aioshelly RpcDevice behind the entity, or None on a Gen1 (block) device."""
    coordinator = getattr(getattr(target.config_entry, "runtime_data", None), "rpc", None)
    return coordinator.device if coordinator is not None else None


def address(target: Target) -> RpcAddress | None:
    if not (match := _UNIQUE_ID.match(target.entry.unique_id)):
        return None
    return RpcAddress(COMPONENTS[match["key"]], int(match["id"]))


def unsupported_reason(target: Target) -> str | None:
    """Why this entity can't take an RPC call at all, or None. Adapter.supports checks the capability in scope."""
    if rpc_device(target) is None:
        return "gen1_unsupported"
    if address(target) is None:
        return Reason.NOT_ADDRESSABLE
    return None
