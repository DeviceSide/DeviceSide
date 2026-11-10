import logging
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed

from custom_components.deviceside import actions
from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.wire import WIRE_EVENT, WIRE_LOGGER

from .fakes.scripted import SCRIPT

FAKE_INTEGRATIONS = ["tests.fakes.broken_integration", "tests.fakes.fake_integration", "tests.fakes.fake_special"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def reset_script():
    SCRIPT.reset()
    yield SCRIPT


@pytest.fixture
async def wire(hass: HomeAssistant):
    """The wire trace, on as a rig turns it on (its logger at DEBUG): the deviceside_wire events fired."""
    events = async_capture_events(hass, WIRE_EVENT)
    level = WIRE_LOGGER.level
    WIRE_LOGGER.setLevel(logging.DEBUG)
    yield events
    WIRE_LOGGER.setLevel(level)


def traced(events) -> list[tuple]:
    """Each traced call as (entity_id, transport, command, params)."""
    return [(e.data["entity_id"], e.data["transport"], e.data["command"], e.data["params"]) for e in events]


@pytest.fixture
def fake_registry():
    """Production actions over the fake integrations, in place of discovery."""
    with patch.object(AdapterRegistry, "discover", lambda: AdapterRegistry(actions.discover(), FAKE_INTEGRATIONS)):
        yield


@pytest.fixture
async def setup_integration(hass: HomeAssistant, fake_registry) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def setup_production(hass: HomeAssistant) -> MockConfigEntry:
    """The integration over the real discovered integrations, for adapter tests."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def call(hass: HomeAssistant, service: str, data: dict, return_response: bool = True):
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=return_response)


async def refusal(hass: HomeAssistant, service: str, data: dict) -> str:
    """The reason a call raises with for a named target that can never take the action."""
    with pytest.raises(TargetNotSupported) as raised:
        await call(hass, service, data)
    return raised.value.reason


def allow_experimental(hass: HomeAssistant, on: bool = True) -> None:
    """Turn the Experimental features option on (or off) for a loaded entry, as saving it in the options would."""
    get_runtime(hass).experimental_features = on


def wall_clock_now() -> datetime:
    """Wall-clock now, which async_fire_time_changed measures against (dt_util.utcnow can be frozen)."""
    return datetime.fromtimestamp(time.time(), UTC)


async def advance(hass: HomeAssistant, start: datetime, seconds: float) -> None:
    """Fire the timers due by start + seconds and let what they started finish."""
    async_fire_time_changed(hass, start + timedelta(seconds=seconds))
    await hass.async_block_till_done()
