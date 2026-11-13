from unittest.mock import call as director_call

import pytest

from custom_components.deviceside.integrations.control4 import director

from ...conftest import allow_experimental, unload_mock_entries
from ...fixtures.control4 import ITEM, FakeDirector, add_control4_light, control4_entry

# pyControl4 stays out of the test environment on purpose: the integration must load without it.
unload_mock_control4_entries = unload_mock_entries("control4")


@pytest.fixture(autouse=True)
async def experimental_on(hass, setup_production):
    """Every Control4 adapter is flagged, so the tests run with the Experimental features option on."""
    allow_experimental(hass)


@pytest.fixture(autouse=True)
def no_settle_delay(monkeypatch):
    """A read-back waits before each read; the tests don't. Four reads at most, as in production."""
    monkeypatch.setattr(director, "SETTLE_DELAYS_S", (0, 0, 0, 0))
    monkeypatch.setattr(director, "MOVE_SETTLE_DELAYS_S", (0, 0))


LAMP = {"entity_id": "light.lamp"}
SENT = {"status": "sent", "integration": "control4"}
CONFIRMED = {"status": "confirmed", "integration": "control4"}

READ = director_call(
    f"/api/v1/items/{ITEM}/variables?varnames=Brightness%20Percent,LIGHT_LEVEL,Brightness%20Target%20Percent"
)
HALT = director_call(f"/api/v1/items/{ITEM}/commands", "SET_BRIGHTNESS_STOP", {})


def ramp(level: int, time_ms: int):
    return director_call(f"/api/v1/items/{ITEM}/commands", "RAMP_TO_LEVEL", {"LEVEL": level, "TIME": time_ms})


def dimmable_lamp(hass, brightness: float = 40, on: bool = True, **kwargs) -> FakeDirector:
    """light.lamp, a dimmer at `brightness` percent, on or off; its Director.

    HA's state is left on with no level: the adapters read the Director's own level, never HA's."""
    director = FakeDirector(brightness=brightness, on=on, **kwargs)
    add_control4_light(hass, control4_entry(hass, director), "light.lamp", state="on" if on else "off")
    return director
