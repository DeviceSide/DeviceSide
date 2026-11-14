from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.shelly.addressing import address

from ...conftest import call as call_service
from ...conftest import unload_mock_entries
from ...fixtures.shelly import add_shelly_entity, shelly_device

# aioshelly stays out of the test environment on purpose: the integration must load without it.
unload_mock_shelly_entries = unload_mock_entries("shelly")


BULB = {"entity_id": "light.bulb"}
SENT = {"status": "sent", "integration": "shelly"}
CONFIRMED = {"status": "confirmed", "integration": "shelly"}


async def call(hass, service: str, data: dict, return_response: bool = True):
    """The response, each entry's class checked and left out, so a test states only what its action decides: every
    Shelly result names the RPC component its entity drives (docs/action-behavior.md)."""
    response = await call_service(hass, service, data, return_response)
    for entity_id, entry in (response or {}).items():
        # A switch_as_x light reports the class of the switch it wraps, which resolve() finds.
        rpc = address(resolve(hass, get_runtime(hass).registry, entity_id))
        assert entry.pop("capability", None) == (rpc.component if rpc else None), entity_id
    return response


def dimmable_bulb(hass, brightness: int = 40, on: bool = True, halt: dict | None = None):
    """light.bulb, an RGBCCT bulb at `brightness` percent, on or off, whose DimStop halts at `halt`; its call_rpc.

    HA's state is left at 10 %: the adapters read the device's own level, never HA's."""
    entry, call_rpc = shelly_device(
        hass, status={"output": on, "brightness": brightness, "mode": "cct", "ct": 2700}, halt=halt
    )
    attributes = {"supported_color_modes": ["color_temp", "rgb"], "brightness": 26}
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0", state="on" if on else "off", attributes=attributes)
    return call_rpc
