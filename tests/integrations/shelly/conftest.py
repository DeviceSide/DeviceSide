from ...conftest import unload_mock_entries
from ...fixtures.shelly import add_shelly_entity, shelly_device

# aioshelly stays out of the test environment on purpose: the integration must load without it.
unload_mock_shelly_entries = unload_mock_entries("shelly")


BULB = {"entity_id": "light.bulb"}
SENT = {"status": "sent", "integration": "shelly"}
CONFIRMED = {"status": "confirmed", "integration": "shelly"}


def dimmable_bulb(hass, brightness: int = 40, on: bool = True, halt: dict | None = None):
    """light.bulb, an RGBCCT bulb at `brightness` percent, on or off, whose DimStop halts at `halt`; its call_rpc.

    HA's state is left at 10 %: the adapters read the device's own level, never HA's."""
    entry, call_rpc = shelly_device(
        hass, status={"output": on, "brightness": brightness, "mode": "cct", "ct": 2700}, halt=halt
    )
    attributes = {"supported_color_modes": ["color_temp", "rgb"], "brightness": 26}
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0", state="on" if on else "off", attributes=attributes)
    return call_rpc
