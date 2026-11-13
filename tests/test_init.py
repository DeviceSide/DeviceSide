"""Setup: an adapter with a caveat stays live, and setup warns once for it, worded per caveat."""

import logging
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside import actions
from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.scope import Caveat, CaveatKind

from .fakes.fake_integration import ADAPTERS, INTEGRATION, FakeTurnOffFor

REASON = "https://github.com/DeviceSide/DeviceSide/issues/1"
WARNINGS = {
    CaveatKind.UNMAINTAINED: f"fake turn_off_for is unmaintained ({REASON}): no one is fixing it; use at your own risk",
    CaveatKind.UNTESTED_FIX: f"fake turn_off_for ships an untested fix ({REASON}): it changed and no one could test it"
    " before this release; please report whether it works",
}


def marked(caplog) -> list[str]:
    """The caveat warnings, in the order setup gives them."""
    messages = [record.getMessage() for record in caplog.records]
    return [message for message in messages if " is unmaintained " in message or " ships an untested fix " in message]


@pytest.mark.parametrize("kind", list(CaveatKind))
async def test_setup_warns_once_per_caveat(hass: HomeAssistant, caplog, kind):
    scope = replace(FakeTurnOffFor.scope, caveat=Caveat(kind, REASON))
    adapter = type("MarkedTurnOffFor", (FakeTurnOffFor,), {"scope": scope})
    module = SimpleNamespace(
        INTEGRATION=INTEGRATION, ADAPTERS=[adapter if cls is FakeTurnOffFor else cls for cls in ADAPTERS]
    )
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    with (
        patch.object(AdapterRegistry, "discover", lambda: AdapterRegistry(actions.discover(), [module])),
        caplog.at_level(logging.WARNING, logger="custom_components.deviceside"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert marked(caplog) == [WARNINGS[kind]]
    # It stays live.
    assert hass.data[DOMAIN].registry.adapter("turn_off_for", "fake").scope is scope


async def test_setup_is_quiet_with_no_caveat(hass: HomeAssistant, caplog, setup_integration):
    assert marked(caplog) == []
