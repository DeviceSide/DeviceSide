"""Zigbee2MQTT turn_on_for: optional light.turn_on, a publish with on_time, then state read-backs; or, for a Tuya
countdown plug, one publish with `countdown`.

Tuya's countdown plugs (classes.COUNTDOWNS) get `{"state": "ON", "countdown": N}`, whole seconds, 1 to 43200: Z2M's
converter A sends a plain On, then 0x42 `{0, N, N}`, which the plug runs as a toggle at expiry, so from on it ends off
(internals.md, Tuya's countdown). One publish, not a state check first: 0x42 alone on an off plug turns it on at N for
good (probe P1b), and converter A sends 0x42 only once the On's send has resolved, so a lost On sends nothing more and
Z2M logs the set as failed (set_check.py makes it `rejected`). Neither the reads nor `on_time` are sent to it: it
reports its state at expiry, and the time left can't be read (probe P6), so the result is `sent`.
"""

import asyncio
import logging
from typing import ClassVar

from homeassistant.core import HomeAssistant

from .addressing import not_addressable, topic
from .bridge import logged_options, publish, publish_set, state_reply
from .classes import COUNTDOWNS, TURN_ON_FOR, TURN_ON_FOR_NOT_SUPPORTED
from .native_control import COLOR_FIELDS, NEED, native_control, settled
from .set_check import checked, note
from ...actions.turn_on_for import TurnOnForRequest
from ...core.adapter import Adapter
from ...core.errors import describe
from ...core.models import EntityResult, Status, Target
from ...core.runtime import get_runtime
from ...core.scope import AdapterScope, DurationLimits, verified

_LOGGER = logging.getLogger(__name__)

# Zigbee OnWithTimedOff: on_time in tenths of a second (uint16), range 1-65534 tenths.
# 65534 tenths = 6553.4 s. The 50 ms floor from core/duration.py handles the effective minimum.
_TIMER_LIMITS = DurationLimits(min_s=0, max_s=6553.4)
# Tuya's countdown: whole seconds, 1 to 43200, both reaching the plug; Z2M refuses anything else before sending
# (probe P7, internals.md).
COUNTDOWN_LIMITS = DurationLimits(min_s=1, max_s=43200, step_s=1)

# Read-back delays in seconds. The second end read allows for a bulb clock that runs slow on a long timer.
_ON_READ_S = 1.0
_END_READ_S = 1.0
_LATE_END_READ_MIN_S = 5.0
_LATE_END_READ_FRACTION = 0.02
# Z2M publishes a light's state once the command has reached it: under a second, or seconds on a busy mesh.
_STATE_TIMEOUT_S = 5.0


class Z2MTurnOnFor(Adapter[TurnOnForRequest]):
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
        # Both Verified: the class decides a switch's level, as each class holds its own per domain (classes.py,
        # TURN_ON_FOR). Zigbee plugs and switches rarely honor OnWithTimedOff, so only a class with a switch record is
        # Verified there; a Hue plug, an `other` one and the rest stay untested.
        domains=verified("light", "switch"),
        capabilities=TURN_ON_FOR,
        # Each harms its class (a Tuya plug left on), so the dispatcher refuses a device not yet placed, and a group of
        # unknown membership, as class_unknown, even with Experimental features on (classes.py).
        not_supported=TURN_ON_FOR_NOT_SUPPORTED,
        # Each takes the countdown, which a Z2M group's call isn't, so a group with one falls back to its members.
        own_calls=dict.fromkeys(COUNTDOWNS, COUNTDOWN_LIMITS),
        duration=_TIMER_LIMITS,
        fields=verified("brightness", "color_temp_kelvin", "hs_color", "rgb_color", "xy_color", "transition"),
        confirmable=False,
        native_groups=True,  # Z2M group entities receive commands on <base>/<group ID>/set.
    )

    def supports(self, hass: HomeAssistant, request: TurnOnForRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or not_addressable(hass, target)

    async def execute(
        self, hass: HomeAssistant, request: TurnOnForRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def send(target: Target) -> EntityResult:
            if request.limits == COUNTDOWN_LIMITS:
                # The dispatcher planned the run on a countdown class and fitted the duration to its limits; branching
                # on them, not a fresh capability(), keeps the two together if bridge/devices moves the plug between.
                # By equality, as the dispatcher groups runs by it: an equal copy is the same limits.
                # A plug has no light fields to apply.
                await publish_set(hass, target, {"state": "ON", "countdown": int(request.duration_s)})
                return self.result(target, Status.SENT)
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
        service_data = {"entity_id": target.entity_id, **data}
        published, unsubscribe = await state_reply(hass, target)
        try:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "%s: sending ha light.turn_on %s with %s", target.reported_id, data, logged_options(hass, target)
                )
            # HA publishes it as a set, whose failure Z2M logs as any other's.
            await note(hass, target)
            await hass.services.async_call("light", "turn_on", service_data, blocking=True)
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
