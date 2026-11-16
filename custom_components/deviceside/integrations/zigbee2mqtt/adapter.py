"""The base of every Zigbee2MQTT adapter: what each sends the same way, whatever its action."""

from homeassistant.core import HomeAssistant

from .set_check import checked
from ...core.adapter import Adapter
from ...core.models import EntityResult, Request, Target
from ...core.scope import OwnCall


class Z2MAdapter[RequestT: Request](Adapter[RequestT]):
    """A Zigbee2MQTT adapter. A class's own call (AdapterScope.own_calls) goes out under the set check, as an
    adapter's own sends do (set_check.py): core's default would report a set Zigbee2MQTT logs as failed as `sent`. It
    settles as turn_on_for's does, the one action with an own call; an own call on get_attributes, which checks no set,
    or set_attributes, which doesn't settle, needs its adapter to override this."""

    async def execute_own(
        self, hass: HomeAssistant, request: RequestT, targets: list[Target], call: OwnCall
    ) -> list[EntityResult]:
        return await checked(self, hass, targets, lambda target: call.send(self, hass, request, target))
