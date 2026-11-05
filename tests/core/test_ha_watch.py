"""The core watch of light and scene calls from HA: one target resolution, handed to each busy resolver."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core import ha_watch
from custom_components.deviceside.core.ha_watch import ALL, Call
from custom_components.deviceside.core.registry import AdapterRegistry


class Resolver:
    """Records each forget; later makes it async, until the event is set. raising fails it in busy, forget or later."""

    def __init__(self, busy: bool = True, later: asyncio.Event | None = None, raising: str | None = None) -> None:
        self.is_busy = busy
        self.later = later
        self.raising = raising
        self.calls: list[tuple[Call, list[str] | object]] = []
        self.done: list[Call] = []

    def busy(self, hass) -> bool:
        if self.raising == "busy":
            raise RuntimeError("resolver broke")
        return self.is_busy

    def forget(self, hass, call, entries):
        if self.raising == "forget":
            raise RuntimeError("resolver broke")
        self.calls.append((call, entries if entries is ALL else [entry.entity_id for entry in entries]))
        if self.later is None:
            return None

        async def finish() -> None:
            await self.later.wait()
            if self.raising == "later":
                raise RuntimeError("resolver broke")
            self.done.append(call)

        return finish()


@pytest.fixture
def resolvers() -> dict[str, Resolver]:
    return {"alpha": Resolver(), "beta": Resolver()}


@pytest.fixture
async def watched(hass, fake_registry, resolvers) -> MockConfigEntry:
    with patch.object(AdapterRegistry, "call_resolvers", lambda self: resolvers):
        entry = MockConfigEntry(domain=DOMAIN)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    async_mock_service(hass, "light", "turn_on")
    async_mock_service(hass, "scene", "turn_on")
    async_mock_service(hass, "switch", "turn_on")
    return entry


def entity(hass, platform: str, entity_id: str, **updates) -> er.RegistryEntry:
    domain, object_id = entity_id.split(".")
    entities = er.async_get(hass)
    entities.async_get_or_create(domain, platform, object_id, suggested_object_id=object_id)
    return entities.async_update_entity(entity_id, **updates) if updates else entities.async_get(entity_id)


async def light_call(hass, data: dict | None, domain: str = "light") -> None:
    await hass.services.async_call(domain, "turn_on", data, blocking=True)


async def test_an_idle_watch_resolves_nothing(hass, watched, resolvers):
    entity(hass, "alpha", "light.a")
    for resolver in resolvers.values():
        resolver.is_busy = False

    with patch.object(ha_watch, "async_extract_referenced_entity_ids") as extract:
        await light_call(hass, {"entity_id": "light.a"})

    extract.assert_not_called()
    assert resolvers["alpha"].calls == []


async def test_each_resolver_gets_its_own_integrations_entries(hass, watched, resolvers):
    entity(hass, "alpha", "light.a")
    entity(hass, "beta", "light.b")
    entity(hass, "demo", "light.other")

    await light_call(hass, {"entity_id": ["light.a", "light.b", "light.other"], "brightness_pct": 40})

    call = Call("light", "turn_on", {"entity_id": ["light.a", "light.b", "light.other"], "brightness_pct": 40})
    assert resolvers["alpha"].calls == [(call, ["light.a"])]
    assert resolvers["beta"].calls == [(call, ["light.b"])]


async def test_a_call_naming_no_entity_of_an_integration_skips_its_resolver(hass, watched, resolvers):
    entity(hass, "alpha", "light.a")

    await light_call(hass, {"entity_id": "light.a"})
    await light_call(hass, None)

    assert [entries for _call, entries in resolvers["alpha"].calls] == [["light.a"]]
    assert resolvers["beta"].calls == []


async def test_only_busy_resolvers_are_handed_the_call(hass, watched, resolvers):
    entity(hass, "alpha", "light.a")
    entity(hass, "beta", "light.b")
    resolvers["beta"].is_busy = False

    await light_call(hass, {"entity_id": ["light.a", "light.b"]})

    assert len(resolvers["alpha"].calls) == 1
    assert resolvers["beta"].calls == []


async def test_all_hands_every_busy_resolver_all(hass, watched, resolvers):
    await light_call(hass, {"entity_id": "all"})

    assert [entries for _call, entries in resolvers["alpha"].calls] == [ALL]
    assert [entries for _call, entries in resolvers["beta"].calls] == [ALL]


async def test_an_area_target_reaches_the_entities_in_it(hass, watched, resolvers):
    area = ar.async_get(hass).async_create("office")
    entity(hass, "alpha", "light.a", area_id=area.id)
    entity(hass, "alpha", "light.elsewhere")

    await light_call(hass, {"area_id": area.id})

    assert [entries for _call, entries in resolvers["alpha"].calls] == [["light.a"]]


async def test_a_device_target_reaches_its_entities(hass, watched, resolvers):
    config_entry = MockConfigEntry(domain="alpha")
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=config_entry.entry_id, identifiers={("alpha", "1")})
    entity(hass, "alpha", "light.a", device_id=device.id)

    await light_call(hass, {"device_id": device.id})

    assert [entries for _call, entries in resolvers["alpha"].calls] == [["light.a"]]


async def test_scene_calls_are_watched_and_other_domains_are_not(hass, watched, resolvers):
    entity(hass, "alpha", "scene.relax")
    entity(hass, "alpha", "switch.plug")

    await light_call(hass, {"entity_id": "switch.plug"}, domain="switch")
    await light_call(hass, {"entity_id": "scene.relax"}, domain="scene")

    assert [(call.domain, entries) for call, entries in resolvers["alpha"].calls] == [("scene", ["scene.relax"])]


async def test_an_async_resolver_is_awaited_by_settled(hass, watched, resolvers):
    entity(hass, "alpha", "light.a")
    released = asyncio.Event()
    resolvers["alpha"].later = released

    await light_call(hass, {"entity_id": "light.a"})
    settling = hass.async_create_task(ha_watch.settled(hass))
    await asyncio.sleep(0)
    assert not settling.done()
    released.set()
    await settling

    assert len(resolvers["alpha"].done) == 1
    await ha_watch.settled(hass)  # nothing pending now


@pytest.mark.parametrize("where", ["busy", "forget", "later"])
async def test_a_resolver_that_raises_is_logged_and_the_others_still_run(hass, watched, resolvers, caplog, where):
    entity(hass, "alpha", "light.a")
    entity(hass, "beta", "light.b")
    resolvers["alpha"].raising = where
    resolvers["alpha"].later = asyncio.Event()
    resolvers["alpha"].later.set()

    await light_call(hass, {"entity_id": ["light.a", "light.b"]})
    await ha_watch.settled(hass)

    assert "The alpha call resolver failed" in caplog.text
    assert [entries for _call, entries in resolvers["beta"].calls] == [["light.b"]]


async def test_the_watch_detaches_with_the_entry_and_attaches_again_on_reload(hass, watched, resolvers):
    entity(hass, "alpha", "light.a")

    assert await hass.config_entries.async_unload(watched.entry_id)
    await light_call(hass, {"entity_id": "light.a"})
    assert resolvers["alpha"].calls == []

    with patch.object(AdapterRegistry, "call_resolvers", lambda self: resolvers):
        assert await hass.config_entries.async_setup(watched.entry_id)
    await light_call(hass, {"entity_id": "light.a"})
    assert len(resolvers["alpha"].calls) == 1


@pytest.mark.parametrize(
    ("domain", "service", "data", "ends"),
    [
        ("light", "turn_on", {"brightness_pct": 40, "transition": 2}, False),
        ("light", "turn_on", {"hs_color": [30, 80]}, True),
        ("light", "turn_on", {"color_temp_kelvin": 3000}, True),
        ("light", "turn_on", {"effect": "colorloop"}, True),
        ("light", "turn_off", {}, True),
        ("light", "toggle", {}, True),
        ("scene", "turn_on", {}, False),
    ],
)
def test_a_call_that_sets_a_color_or_turns_off_ends_a_hue_cycle(domain, service, data, ends):
    assert Call(domain, service, data).ends_hue_cycle is ends
