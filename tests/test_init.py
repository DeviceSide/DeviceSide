"""Setup: an adapter with a caveat stays live, and setup warns once for it, worded per caveat."""

import logging
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
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


# Lifecycle hooks (IntegrationInfo.setup and remove)


class Hooks:
    """One integration's hooks, recording each run in `log`."""

    def __init__(self, log: list[str], key: str, *, fail: str | None = None) -> None:
        self.log, self.key, self.fail = log, key, fail

    async def setup(self, hass, entry) -> None:
        self.log.append(f"{self.key} setup")
        entry.async_on_unload(lambda: self.log.append(f"{self.key} teardown"))
        if self.fail == "setup":
            raise RuntimeError(f"{self.key} broke")

    async def remove(self, hass, entry) -> None:
        self.log.append(f"{self.key} remove")
        if self.fail == "remove":
            raise RuntimeError(f"{self.key} broke")


def hooked(log: list[str], *keys: str, fail: dict[str, str] | None = None, unavailable: str | None = None):
    """An entry and a patch of discovery to fake integrations named `keys`, each with hooks."""
    modules = []
    for key in keys:
        hooks = Hooks(log, key, fail=(fail or {}).get(key))
        info = replace(INTEGRATION, key=key, ha_domain=key, setup=hooks.setup, remove=hooks.remove)
        if key == unavailable:
            info = replace(info, available=False, unavailable_reason="missing")
        modules.append(SimpleNamespace(INTEGRATION=info, ADAPTERS=[]))
    entry = MockConfigEntry(domain=DOMAIN)
    return entry, patch.object(AdapterRegistry, "discover", lambda: AdapterRegistry(actions.discover(), modules))


async def load(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_hooks_run_per_load_and_teardown_on_unload(hass: HomeAssistant):
    log: list[str] = []
    entry, discovery = hooked(log, "one", "two")
    with discovery:
        await load(hass, entry)
        assert sorted(log) == ["one setup", "two setup"]

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert sorted(log) == ["one setup", "one setup", "one teardown", "two setup", "two setup", "two teardown"]


async def test_a_raising_setup_hook_is_logged_and_isolated(hass: HomeAssistant, caplog):
    log: list[str] = []
    entry, discovery = hooked(log, "one", "two", fail={"one": "setup"})
    with discovery, caplog.at_level(logging.WARNING, logger="custom_components.deviceside"):
        await load(hass, entry)

    assert sorted(log) == ["one setup", "two setup"]
    assert entry.state is ConfigEntryState.LOADED
    assert "Integration one setup hook failed" in caplog.text


async def test_remove_hooks_run_and_a_raising_one_stops_no_other(hass: HomeAssistant, caplog):
    log: list[str] = []
    entry, discovery = hooked(log, "one", "two", fail={"one": "remove"})
    with discovery, caplog.at_level(logging.WARNING, logger="custom_components.deviceside"):
        await load(hass, entry)
        log.clear()
        assert await hass.config_entries.async_remove(entry.entry_id)

    assert sorted(log) == ["one remove", "one teardown", "two remove", "two teardown"]
    assert "Integration one remove hook failed" in caplog.text


async def test_unavailable_integrations_have_no_hooks(hass: HomeAssistant):
    log: list[str] = []
    entry, discovery = hooked(log, "one", "two", unavailable="two")
    with discovery:
        await load(hass, entry)
        assert await hass.config_entries.async_remove(entry.entry_id)

    assert [line for line in log if line.startswith("two ")] == []
    assert "one setup" in log
    assert "one remove" in log
