"""Zigbee2MQTT turn_on_for: optional light.turn_on, a publish with on_time, then state read-backs; or, for a Tuya
countdown plug, its family's own call, one publish with `countdown` (families/tuya/countdown.py)."""

import asyncio
import logging
from typing import ClassVar

from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
)
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_ON, Platform
from homeassistant.core import HomeAssistant

from .adapter import Z2MAdapter
from .addressing import not_addressable, topic
from .bridge import logged_options, publish, publish_set, state_reply
from .classes import class_scope
from .families.hue import NEED
from .native_control import COLOR_FIELDS, native_control, settled
from .set_check import checked, note
from ...actions.turn_on_for import TurnOnForRequest
from ...core.errors import describe
from ...core.fields import BRIGHTNESS_FIELD
from ...core.models import EntityResult, Status, Target
from ...core.runtime import get_runtime
from ...core.scope import AdapterScope, DurationLimits, verified
from ...core.zcl import MAX_TENTHS_S

_LOGGER = logging.getLogger(__name__)

# OnWithTimedOff.on_time (core/zcl.py). The 50 ms floor from core/duration.py handles the effective minimum.
_TIMER_LIMITS = DurationLimits(min_s=0, max_s=MAX_TENTHS_S)

# Read-back delays in seconds. The second end read allows for a bulb clock that runs slow on a long timer.
_ON_READ_S = 1.0
_END_READ_S = 1.0
_LATE_END_READ_MIN_S = 5.0
_LATE_END_READ_FRACTION = 0.02
# Z2M publishes a light's state once the command has reached it: under a second, or seconds on a busy mesh.
_STATE_TIMEOUT_S = 5.0


class Z2MTurnOnFor(Z2MAdapter[TurnOnForRequest]):
    """Turn a Z2M light on for a duration using Zigbee2MQTT's on_time attribute.

    With fields: calls light.turn_on first so HA's MQTT light entity applies brightness, color and
    transition through its own protocol, waits for Z2M to publish the light's state, then publishes
    {"state":"ON","on_time":<seconds, 1dp>} to the device's command topic. Without fields: publishes only.
    With a color or color temperature, a Hue light (or a group with a Hue member) gets Z2M's hue_native_control on
    for that light.turn_on (native_control.py), so it lights in that color rather than its last one.

    Z2M publishes no state for a timed command, and Hue bulbs on Z2M don't report, so HA's state would go
    stale. The adapter then asks Z2M to read the state back ({"state":""} on the get topic): 1 s after the
    publish when no fields ran light.turn_on, and twice after the timer should end. A new call on the same
    target replaces its pending reads.

    Returns SENT (fire-and-forget via MQTT), or REJECTED when Zigbee2MQTT logs a set as failed (set_check.py). The
    reads never change the result.
    """

    action: ClassVar[str] = "turn_on_for"
    integration: ClassVar[str] = "zigbee2mqtt"
    scope: ClassVar[AdapterScope] = AdapterScope(
        # Both Verified: the class decides a switch's level, as each class holds its own per domain (its family's
        # turn_on_for scope). Zigbee plugs and switches rarely honor OnWithTimedOff, so only a class with a switch
        # record serves one; a Hue plug and an `other` one are not built (refusals.py).
        domains=verified(Platform.LIGHT, Platform.SWITCH),
        # The not_built entries (refusals.py) each harm their class (a Tuya plug left on), so the dispatcher refuses a
        # device not yet placed, and a group of unknown membership, as class_unknown, even with Labs
        # on (classes.py). The families' own calls (Tuya's countdown) run through execute_own (adapter.py).
        **class_scope("turn_on_for"),
        duration=_TIMER_LIMITS,
        fields=verified(
            BRIGHTNESS_FIELD, ATTR_COLOR_TEMP_KELVIN, ATTR_HS_COLOR, ATTR_RGB_COLOR, ATTR_XY_COLOR, ATTR_TRANSITION
        ),
        confirmable=False,
        native_groups=True,  # Z2M group entities receive commands on <base>/<group ID>/set.
    )

    def supports(self, hass: HomeAssistant, request: TurnOnForRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or not_addressable(hass, target)

    async def execute(
        self, hass: HomeAssistant, request: TurnOnForRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def send(target: Target) -> EntityResult:
            if request.light.present():
                need = NEED[self.action] if request.light.present() & COLOR_FIELDS else None
                async with native_control(hass, target, need):
                    await self._turn_on(hass, target, request.light.as_turn_on_data())

            # The timer goes out as the user's option has it, after this call's restore or an earlier action's.
            await settled(hass, target)

            on_time = round(request.duration_s, 1)
            # supports() refused the targets it can't address.
            await publish_set(hass, target, {"state": "ON", "on_time": on_time})
            self._schedule_reads(hass, target, on_time, read_on=not request.light.present())
            return self.result(target, Status.SENT)

        return await checked(self, hass, targets, send)

    async def _turn_on(self, hass: HomeAssistant, target: Target, data: dict) -> None:
        """light.turn_on, returning once Z2M publishes the light's state, so the timer follows the fields.

        HA returns once it has published the command, and Z2M handles two messages for one light at once. The
        timer's message would then publish the state from before the fields landed, which HA keeps, and contend
        with them on the mesh, starting the timer late. With no state by the timeout, the timer goes anyway.
        """
        service_data = {ATTR_ENTITY_ID: target.entity_id, **data}
        published, unsubscribe = await state_reply(hass, target)
        try:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "%s: sending ha light.turn_on %s with %s", target.reported_id, data, logged_options(hass, target)
                )
            # HA publishes it as a set, whose failure Z2M logs as any other's.
            await note(hass, target)
            await hass.services.async_call(Platform.LIGHT, SERVICE_TURN_ON, service_data, blocking=True)
            if published is None:
                return
            try:
                async with asyncio.timeout(_STATE_TIMEOUT_S):
                    await published
            except TimeoutError:
                _LOGGER.warning(
                    "No state from Zigbee2MQTT for %s in %s s, "
                    "so its timer starts late and it stays on that much longer",
                    target.entity_id,
                    _STATE_TIMEOUT_S,
                )
        finally:
            unsubscribe()

    def _schedule_reads(self, hass: HomeAssistant, target: Target, on_time: float, read_on: bool) -> None:
        get_topic = topic(target, "get")

        async def read() -> None:
            try:
                # A failure lands here rather than in HA's error log; the read runs in its own task.
                await publish(hass, get_topic, {"state": ""})
            except Exception as err:  # noqa: BLE001 - a failed read leaves HA's state stale, nothing more
                _LOGGER.debug("State read for %s failed: %s", target.entity_id, describe(err))

        delays = [on_time + _END_READ_S, on_time + max(_LATE_END_READ_MIN_S, _LATE_END_READ_FRACTION * on_time)]
        if read_on:
            delays.insert(0, _ON_READ_S)
        get_runtime(hass).schedule(
            hass, f"{self.integration}:{self.action}:{target.entity_id}", ((delay, read) for delay in delays)
        )
