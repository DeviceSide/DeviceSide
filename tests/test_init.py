"""Setup: an unmaintained adapter stays live and setup warns once for it."""

import logging
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.deviceside import actions
from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.registry import AdapterRegistry

from .fakes.fake_integration import ADAPTERS, INTEGRATION, FakeTurnOffFor

REASON = "https://github.com/jasonmx/DeviceSide/issues/1"


class UnmaintainedTurnOffFor(FakeTurnOffFor):
    scope = replace(FakeTurnOffFor.scope, unmaintained=REASON)


async def test_setup_warns_once_per_unmaintained_adapter(hass: HomeAssistant, caplog):
    module = SimpleNamespace(
        INTEGRATION=INTEGRATION,
        ADAPTERS=[UnmaintainedTurnOffFor if cls is FakeTurnOffFor else cls for cls in ADAPTERS],
    )
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    with (
        patch.object(AdapterRegistry, "discover", lambda: AdapterRegistry(actions.discover(), [module])),
        caplog.at_level(logging.WARNING, logger="custom_components.deviceside"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    warnings = [record.getMessage() for record in caplog.records if "unmaintained" in record.getMessage()]
    assert warnings == [f"fake turn_off_for is unmaintained ({REASON}): no one is fixing it; use at your own risk"]
    # It stays live.
    assert hass.data[DOMAIN].registry.adapter("turn_off_for", "fake").scope.unmaintained == REASON


async def test_setup_is_quiet_with_every_adapter_maintained(hass: HomeAssistant, caplog, setup_integration):
    assert not [record for record in caplog.records if "unmaintained" in record.getMessage()]
