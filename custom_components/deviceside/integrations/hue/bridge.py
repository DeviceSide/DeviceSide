"""The core hue integration's bridge, through aiohue's v2 API: the bridge behind a target, group members, writes."""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ...core.models import Target
from ...core.resolver import resolve_members
from ...core.runtime import get_runtime
from ...core.transition import BRIGHTNESS
from ...core.wire import wire_enabled, wire_trace

if TYPE_CHECKING:
    from aiohue.v2 import HueBridgeV2
    from aiohue.v2.controllers.groups import GroupedLightController
    from aiohue.v2.controllers.lights import LightsController

# The delta object whose stop halts each attribute's fade.
DELTAS = {BRIGHTNESS: "dimming_delta"}


def bridge_api(target: Target) -> HueBridgeV2 | None:
    """The v2 API of the bridge behind the target, or None on a v1 bridge.

    The core hue integration keeps its HueBridge on the config entry; HueBridge.api is a HueBridgeV2 from API 2 on.
    """
    bridge = getattr(target.config_entry, "runtime_data", None)
    if bridge is None or getattr(bridge, "api_version", 1) < 2:
        return None
    return bridge.api


def resource_id(target: Target) -> str:
    """The bridge's id for the light, grouped_light or scene: core's hue integration uses it as the unique_id."""
    return target.entry.unique_id


def controller(api: HueBridgeV2, target: Target) -> LightsController | GroupedLightController:
    """The controller that reads and writes the target as one resource: the room's grouped_light, or the light."""
    return api.groups.grouped_light if target.is_group else api.lights


def is_hue_group(hass: HomeAssistant, target: Target) -> bool:
    """A room or zone, which core's hue integration exposes as one light on the room's grouped_light.

    A v1 bridge's group is left as a plain target, so supports() refuses it as bridge_v1 rather than expanding it.
    """
    return bool(target.state and target.state.attributes.get("is_hue_group")) and bridge_api(target) is not None


def expand_group(hass: HomeAssistant, target: Target) -> list[Target]:
    """The room's or zone's lights that have a light entity in HA, sorted by entity_id (aiohue's order is a set's).

    Only called for a target is_hue_group accepted, which has a v2 bridge.
    """
    lights = bridge_api(target).groups.grouped_light.get_lights(resource_id(target))
    return resolve_members(hass, get_runtime(hass).registry, target, "hue", (light.id for light in lights))


def trace(hass: HomeAssistant, writer: LightsController | GroupedLightController, rid: str, command: str, params: dict):
    """The wire trace of one write to the light or grouped_light, naming its light entity, not its resource id."""
    if not wire_enabled():
        return
    entity_id = er.async_get(hass).async_get_entity_id("light", "hue", rid)
    wire_trace(hass, entity_id, "clip", f"{writer.item_type.value}.{command}", params)


async def set_state(
    hass: HomeAssistant, writer: LightsController | GroupedLightController, rid: str, **state: Any
) -> None:
    """aiohue's set_state on the light or grouped_light, traced. Raises on failure."""
    trace(hass, writer, rid, "set_state", {key: value for key, value in state.items() if value is not None})
    await writer.set_state(rid, **state)


async def write_light(
    hass: HomeAssistant,
    api: HueBridgeV2,
    light_id: str,
    *,
    on: bool | None = None,
    brightness: float | None = None,
    color_temp_mirek: int | None = None,
    color_xy: tuple[float, float] | None = None,
) -> None:
    """One PUT to one light; the bridge stores what it is sent whether the light is on or off. Raises on failure."""
    await set_state(
        hass, api.lights, light_id, on=on, brightness=brightness, color_temp=color_temp_mirek, color_xy=color_xy
    )


def stops(attributes: Iterable[str]) -> dict:
    """The PUT body fields that halt these attributes' fades where they are."""
    return {DELTAS[attribute]: {"action": "stop"} for attribute in attributes}


def xy_halt(xy: tuple[float, float]) -> dict:
    """The PUT body fields that halt an xy fade at this xy, its predicted one: the bridge has no color delta stop, and
    reports the written xy at once (docs/integration-internals.md, Hue tested behavior). The duration of 0 holds for
    every field in the PUT."""
    return {"color": {"xy": {"x": xy[0], "y": xy[1]}}, "dynamics": {"duration": 0}}


async def put(
    hass: HomeAssistant, api: HueBridgeV2, writer: LightsController | GroupedLightController, rid: str, body: dict
) -> None:
    """One raw CLIP v2 PUT to the light or grouped_light, its body as given. Raises on failure."""
    trace(hass, writer, rid, "put", body)
    await api.request("put", f"clip/v2/resource/{writer.item_type.value}/{rid}", json=body)
