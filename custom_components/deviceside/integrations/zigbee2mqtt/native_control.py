"""Set Z2M's hue_native_control the way an action needs it, for that action's own publish only.

With the option on, Z2M sends on, brightness, color and color temperature to a Hue light as one Philips-cluster
command (zigbee-herdsman-converters src/lib/philips.ts); with it off, as ZCL commands. Some actions need one of the two:

- A timer with a color needs it on: a Hue bulb drops a color sent while it is off, so as ZCL it lights at its last
  color first.
- A brightness fade needs it off: sent native, a long raise runs about 2.3x faster than its transition, and a soft off
  reports `onOff: 0` at once while the bulb still fades.
- A saturation fade needs it on: native, the bulb fades in xy and holds its hue.

The option belongs to the user. An action that needs it the other way sets it, publishes, and puts the user's value
back once Z2M has published the target's state in reply (1 s cap), so nothing outlasts the publish. Z2M reads an
entity's options as it takes a command (lib/extension/publish.ts), so a fade already sent runs on unchanged. A command
to a group reads the group's options, never its members', so a group with a Hue member is set itself.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .addressing import group_id, state_topic, z2m_address
from .bridge import ensure_options, group_members
from ...core.models import Target
from ...core.runtime import get_runtime

_LOGGER = logging.getLogger(__name__)

OPTION = "hue_native_control"
# The fields Z2M sends as a separate command after on; brightness rides moveToLevelWithOnOff with it.
COLOR_FIELDS = frozenset({"color_temp_kelvin", "hs_color", "rgb_color", "xy_color"})
# Each action's need: True on, False off. An action left out works either way and leaves the option alone.
NEED: dict[str, bool] = {
    "turn_on_for": True,  # with a color; without one it works either way
    "raise_brightness": False,
    "lower_brightness": False,
    "raise_saturation": True,
    "lower_saturation": True,
}
_HUE_MANUFACTURER = "Philips"  # Z2M's vendor string for Hue, which HA's device registry shows
_REPLY_CAP_S = 1.0

type Address = tuple[str, str]  # Z2M's options section ("device" or "group") and the ID in it


def _locks(hass: HomeAssistant) -> dict[Address, asyncio.Lock]:
    return get_runtime(hass).integration_state.setdefault("zigbee2mqtt_native_control_locks", {})


@asynccontextmanager
async def native_control(hass: HomeAssistant, target: Target, need: bool | None) -> AsyncIterator[None]:
    """Hold the option at `need` around the body's publish to a Hue device, or a group with a Hue member.

    Reads Z2M's settings on each call rather than caching them, so a user who changes the option is seen. A need of
    None, a non-Hue target or the option already right costs no writes, and a non-Hue device reads nothing. One lock
    per device or group, held from the set to the restore, keeps actions with opposite needs apart.

    Never raises of its own: a failed check, set or restore logs a warning, and the body runs (or has run) anyway.
    """
    if need is None:
        yield
        return
    try:
        address = await _hue_address(hass, target)
    except Exception as err:  # noqa: BLE001 - the command still goes out, encoded as the user's option has it
        _warn_set(target, need, err)
        address = None
    if address is None:
        yield
        return
    async with _locks(hass).setdefault(address, asyncio.Lock()):
        if not await _set(hass, target, address, need):
            yield
            return
        replied, unsubscribe = await _state_reply(hass, target)
        try:
            yield
            try:
                async with asyncio.timeout(_REPLY_CAP_S):
                    await replied
            except TimeoutError:
                _LOGGER.debug("No state from Zigbee2MQTT for %s in %s s", target.entity_id, _REPLY_CAP_S)
        finally:
            unsubscribe()
            # Only a value other than need was changed, and an absent option is Z2M's default, off.
            await _set(hass, target, address, not need, restoring=True)


async def _hue_address(hass: HomeAssistant, target: Target) -> Address | None:
    """Where the target's options live, for a Hue device or a group with a Hue member; None for anything else."""
    if (group := group_id(target)) is not None:
        return ("group", group) if await _has_hue_member(hass, group) else None
    if target.device is not None and target.device.manufacturer == _HUE_MANUFACTURER:
        return "device", z2m_address(target.device)
    return None


async def _has_hue_member(hass: HomeAssistant, group: str) -> bool:
    registry = dr.async_get(hass)
    for ieee in await group_members(hass, group):
        device = registry.async_get_device(identifiers={("mqtt", f"zigbee2mqtt_{ieee}")})
        if device is not None and device.manufacturer == _HUE_MANUFACTURER:
            return True
    return False


async def _set(hass: HomeAssistant, target: Target, address: Address, value: bool, restoring: bool = False) -> bool:
    """Set the option to value where it differs, or regardless for a restore; whether Z2M confirmed a write.

    A restore doesn't compare: Z2M may not have republished bridge/info since the set.
    """
    written = False

    def confirmed(_z2m_id: str) -> None:
        nonlocal written
        written = True
        _LOGGER.debug("Set Zigbee2MQTT's %s to %s for %s", OPTION, value, target.entity_id)

    def wanted(current: dict) -> dict:
        return {OPTION: value} if restoring or bool(current.get(OPTION)) != value else {}

    kind, z2m_id = address
    try:
        await ensure_options(hass, kind, [z2m_id], wanted, confirmed)
    except Exception as err:  # noqa: BLE001 - the command goes out (or went out) as the option stood
        if not restoring:
            _warn_set(target, value, err)
        else:
            _LOGGER.warning(
                "Couldn't put Zigbee2MQTT's %s back to %s for %s, so it stays %s: %s",
                OPTION,
                value,
                target.entity_id,
                not value,
                err,
            )
    return written


def _warn_set(target: Target, value: bool, err: Exception) -> None:
    _LOGGER.warning(
        "Couldn't set Zigbee2MQTT's %s to %s for %s, so the command goes out as the option stands: %s",
        OPTION,
        value,
        target.entity_id,
        err,
    )


async def _state_reply(hass: HomeAssistant, target: Target) -> tuple[asyncio.Future[None], Callable[[], None]]:
    """A future for Z2M's next state publish for the target, subscribed before the body publishes, and its
    unsubscribe. With no state topic it never resolves, so the restore waits the cap."""
    published: asyncio.Future[None] = hass.loop.create_future()
    if (light_topic := state_topic(target)) is None:
        return published, lambda: None

    @callback
    def received(msg: mqtt.ReceiveMessage) -> None:
        # A retained message is old state the broker resends on subscribe, not Z2M's answer.
        if not msg.retain and not published.done():
            published.set_result(None)

    # HA's own light entity subscribes to this topic, so the subscription is live at once.
    return published, await mqtt.async_subscribe(hass, light_topic, received)
