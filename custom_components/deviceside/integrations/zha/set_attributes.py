"""ZHA set_attributes: MoveTo commands with the ExecuteIfOff override through zha.issue_zigbee_cluster_command, so a
light that is off stores the values and stays off; then an update_entity so HA shows them."""

import asyncio
import logging
from typing import Any, ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er

from . import zcl
from .addressing import address, unsupported_reason
from ...actions.set_attributes import SetAttributesRequest
from ...core.adapter import Adapter
from ...core.ha_entity import ha_entity, replace_if_set
from ...core.models import EntityResult, Status, Target
from ...core.runtime import get_runtime
from ...core.scope import AdapterScope, verified
from ...core.zcl_write import (
    Command,
    MoveToColor,
    MoveToColorTemp,
    MoveToHueAndSaturation,
    MoveToLevel,
    commands,
    wants_level,
)

# 0.4 s, the Hue bridge's default write fade, so a call looks alike on both; a light that is off doesn't fade.
_EXECUTE_IF_OFF = zcl.execute_if_off(4)

Wire = tuple[int, int, dict[str, Any]]

# zha skips update_entity while a light's transition flag is up: for an HA turn_off, its fade plus 0.5 s (1.5 s for a
# plain off). The refresh waits it out this long, polling, then goes ahead and refreshes again once it clears.
TRANSITION_WAIT_S = 3.0
TRANSITION_POLL_S = 0.1
LATE_REFRESH_POLL_S = 0.5
FADE_WAIT_S = 0.6  # the commands' 0.4 s fade plus margin: a read sooner sees a mid-fade color temperature
SETTLE_REFRESH_S = 1.0  # a second read after the first, for a fade that ran slow
LATE_REFRESH_LIMIT_S = 60.0  # past the longest off fade anyone sets; a flag stuck longer is zha's fault


def _wire(command: Command) -> Wire:
    """The command as zha's (cluster, command, params), with the fade and the override."""
    match command:
        case MoveToLevel(level):
            return zcl.LEVEL_CLUSTER, zcl.MOVE_TO_LEVEL, {"level": level, **_EXECUTE_IF_OFF}
        case MoveToColorTemp(mireds):
            return zcl.COLOR_CLUSTER, zcl.MOVE_TO_COLOR_TEMP, {"color_temp_mireds": mireds, **_EXECUTE_IF_OFF}
        case MoveToColor(x, y):
            params = {"color_x": round(x * 65535), "color_y": round(y * 65535)}
            return zcl.COLOR_CLUSTER, zcl.MOVE_TO_COLOR, {**params, **_EXECUTE_IF_OFF}
        case MoveToHueAndSaturation(hue, saturation):
            params = {"hue": hue, "saturation": saturation}
            return zcl.COLOR_CLUSTER, zcl.MOVE_TO_HUE_AND_SATURATION, {**params, **_EXECUTE_IF_OFF}


_LOGGER = logging.getLogger(__name__)


def _zha_light(hass: HomeAssistant, entity_id: str) -> Any:
    """The zha library's light behind HA's ZHA entity, or None."""
    return getattr(getattr(ha_entity(hass, entity_id), "entity_data", None), "entity", None)


def _transitioning(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether zha's transition flag is up on the light, so its update_entity would read nothing; False when the
    library's light, or its flag, can't be reached."""
    return bool(getattr(_zha_light(hass, entity_id), "is_transitioning", False))


async def _transition_over(hass: HomeAssistant, entity_id: str, wait: float) -> bool:
    """Wait up to `wait` seconds for zha's transition flag to clear; whether it did."""
    deadline = hass.loop.time() + wait
    while _transitioning(hass, entity_id):
        if hass.loop.time() >= deadline:
            return False
        await asyncio.sleep(TRANSITION_POLL_S)
    return True


def _keep_level(hass: HomeAssistant, target: Target, level: int, absolute: float | None) -> None:
    """Make the level the zha library keeps for the light's next plain on the one just written.

    After an off, the library keeps the light's level (`_off_brightness`, 0-255) and sends it on the next turn_on
    without a brightness, which would undo this write; a ZHA group's light keeps its own. Each is replaced only when
    set. The group reached as the target's takes only an explicit brightness: a clamp leaves its lights at different
    levels, so its kept one stays.
    """
    replace_if_set(_zha_light(hass, target.entity_id), "_off_brightness", level)
    if absolute is None or target.via_group is None:
        return
    if (entry := er.async_get(hass).async_get(target.via_group)) is not None and entry.platform == "zha":
        replace_if_set(_zha_light(hass, target.via_group), "_off_brightness", level)


class ZHASetAttributes(Adapter[SetAttributesRequest]):
    """Send each light its MoveTo commands one after another, never the WithOnOff variants, then update_entity it.

    The ExecuteIfOff override makes a light that is off store the values and stay off (probe 13a). The zha library
    raises on a delivery failure or a non-success ZCL status, so a light whose commands return is SENT; nothing reads
    back, so a bulb that ignores the override also reports SENT. ZHA never applies a color temperature report, hence
    the update_entity. The dispatcher expands a ZHA group into its members, written one at a time: a groupcast has no
    delivery feedback. A field the light can't take is dropped and the result says so, as on Hue. A level write
    replaces the one the zha library keeps for the next plain on (_keep_level).

    zha's update_entity does nothing while its transition flag is up, as it is for 1.5 s after an HA turn_off, and ZHA
    applies no color reports: a refresh then would leave HA showing the old color after the next plain on. So the
    refresh waits for the flag (TRANSITION_WAIT_S), and after a longer off fade refreshes once more when it clears.
    The read is also held until FADE_WAIT_S after the last command, as the commands fade the light over 0.4 s and a
    read inside the fade would keep a mid-fade color temperature; a second read follows SETTLE_REFRESH_S later, for a
    fade that ran slow.
    """

    action: ClassVar[str] = "set_attributes"
    integration: ClassVar[str] = "zha"
    scope: ClassVar[AdapterScope] = AdapterScope(
        experimental=True,
        domains=verified("light"),
        fields=verified(
            "brightness", "color_temp_kelvin", "hs_color", "rgb_color", "xy_color", "min_brightness", "max_brightness"
        ),
        max_concurrency=2,
    )

    def supports(self, hass: HomeAssistant, request: SetAttributesRequest, target: Target) -> str | None:
        if reason := super().supports(hass, request, target) or unsupported_reason(target):
            return reason
        if target.device is not None and target.device.model in zcl.DROPS_WHILE_OFF:
            return "execute_if_off_unsupported"
        return None

    async def execute(
        self, hass: HomeAssistant, request: SetAttributesRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def send(target: Target) -> EntityResult:
            addr = address(target.entry.unique_id)  # supports() refused the targets it can't address
            # supported_color_modes stays in the state while the light is off.
            attrs = dict(target.state.attributes) if target.state else {}
            modes = set(attrs.get("supported_color_modes") or ())
            current_level = None
            if wants_level(request, modes):
                read = await zcl.read_attributes(hass, addr, zcl.LEVEL_CLUSTER, (zcl.CURRENT_LEVEL,))
                current_level = read[zcl.CURRENT_LEVEL]
            sent, dropped = commands(request, modes, attrs, current_level)
            detail = "fields_dropped" if dropped else None
            if not sent:
                return self.result(target, Status.UNCHANGED, detail=detail or "within_limits")
            try:
                for cluster_id, command_id, params in map(_wire, sent):
                    await zcl.command(
                        hass, addr, cluster_id, command_id, params, request.context, entity_id=target.reported_id
                    )
                # Before the refresh, which can wait seconds: a plain on meanwhile must not send the old level.
                if (level := next((c.level for c in sent if isinstance(c, MoveToLevel)), None)) is not None:
                    _keep_level(hass, target, level, request.brightness)
            except Unauthorized:
                return self.result(target, Status.REJECTED, detail="admin_required")
            finally:  # a later command failing still leaves the earlier ones landed
                await self._refresh(hass, request, target.entity_id)
            return self.result(target, Status.SENT, detail=detail)

        return await self.gather(hass, targets, send)

    async def _refresh(self, hass: HomeAssistant, request: SetAttributesRequest, entity_id: str) -> None:
        sent_at = hass.loop.time()
        over = await _transition_over(hass, entity_id, TRANSITION_WAIT_S)
        # The flag wait counts toward the fade wait.
        if (fade_left := FADE_WAIT_S - (hass.loop.time() - sent_at)) > 0:
            await asyncio.sleep(fade_left)
        await self._update(hass, request, entity_id)
        if over:

            async def settle() -> None:
                await self._update(hass, request, entity_id)

            get_runtime(hass).schedule(hass, f"zha:{self.action}:{entity_id}", [(SETTLE_REFRESH_S, settle)])
        else:
            self._refresh_when_over(hass, request, entity_id, hass.loop.time() + LATE_REFRESH_LIMIT_S)

    def _refresh_when_over(
        self, hass: HomeAssistant, request: SetAttributesRequest, entity_id: str, deadline: float
    ) -> None:
        """Refresh once zha's transition flag clears, checking every LATE_REFRESH_POLL_S until `deadline`. A later
        call on the light replaces it."""

        async def job() -> None:
            if _transitioning(hass, entity_id) and hass.loop.time() < deadline:
                self._refresh_when_over(hass, request, entity_id, deadline)
            else:
                await self._update(hass, request, entity_id)

        get_runtime(hass).schedule(hass, f"zha:{self.action}:{entity_id}", [(LATE_REFRESH_POLL_S, job)])

    async def _update(self, hass: HomeAssistant, request: SetAttributesRequest, entity_id: str) -> None:
        try:
            await hass.services.async_call(
                "homeassistant", "update_entity", {"entity_id": entity_id}, blocking=True, context=request.context
            )
        except Exception as err:  # noqa: BLE001 - the write landed; a stale HA state is no reason to fail it
            _LOGGER.warning("update_entity after %s failed for %s: %s", self.action, entity_id, err)
