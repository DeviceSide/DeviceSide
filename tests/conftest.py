import logging
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.deviceside import actions
from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.runtime import get_runtime

from .fakes.scripted import SCRIPT

FAKE_INTEGRATIONS = ["tests.fakes.broken_integration", "tests.fakes.fake_integration", "tests.fakes.fake_special"]


class Clock:
    """A transition cache clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def result(integration: str, status: str, **extra) -> dict:
    """One target's expected response entry: result("zha", "unchanged", detail="off")."""
    return {"status": status, "integration": integration, **extra}


def unload_mock_entries(domain: str):
    """An autouse fixture, for an integration's conftest: mark its mocked config entries not loaded before teardown,
    so HA doesn't import the real integration (or run its unload) on them."""

    @pytest.fixture(autouse=True, name=f"unload_mock_{domain}_entries")
    async def unload(hass: HomeAssistant):
        yield
        for entry in hass.config_entries.async_entries(domain):
            entry.mock_state(hass, ConfigEntryState.NOT_LOADED)

    return unload


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def reset_script():
    SCRIPT.reset()
    yield SCRIPT


@pytest.fixture
def wire(caplog):
    """DeviceSide's log at DEBUG, as a user's debug log has it, for sent() to read the calls an action sent."""
    caplog.set_level(logging.DEBUG, logger="custom_components.deviceside")
    return caplog


def sent(caplog) -> list[str]:
    """The debug line of each call sent, in order: "<entity_id>: sending <transport> <command> <params>"."""
    return [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG and ": sending " in r.msg]


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
