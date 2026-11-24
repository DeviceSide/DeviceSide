"""light.turn_on for a timer's light fields, returning once Zigbee2MQTT publishes the light's state, so the timer that
follows goes out after the fields have landed: turn_on_for's on_time (turn_on_for.py) and Tuya's datapoint countdown
(families/tuya/datapoint.py) both send it first."""

import asyncio
import logging

from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_ON, Platform
from homeassistant.core import HomeAssistant

from .bridge import logged_options, state_reply
from .set_check import note
from ...core.models import Target

_LOGGER = logging.getLogger(__name__)

# Z2M publishes a light's state once the command has reached it: under a second, or seconds on a busy mesh.
_STATE_TIMEOUT_S = 5.0


async def turn_on(hass: HomeAssistant, target: Target, data: dict) -> None:
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
                "No state from Zigbee2MQTT for %s in %s s, so its timer starts late and it stays on that much longer",
                target.entity_id,
                _STATE_TIMEOUT_S,
            )
    finally:
        unsubscribe()
