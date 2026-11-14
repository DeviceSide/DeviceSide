"""Hue's classes (classes.py): a light's by its device's manufacturer, a scene's by the lights it writes, a room's by
its members, a light with no entity included; and what each class's level does at the gate."""

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.hue import ADAPTERS, INTEGRATION, classes

from .conftest import SENT, STOP, call, lamp
from ...conftest import allow_experimental, result
from ...conftest import call as call_service
from ...fixtures.hue import add_hue_entity, add_hue_group, hue_entry, light_action

pytestmark = pytest.mark.usefixtures("setup_production")

IKEA = "IKEA of Sweden"


def capability(hass, entity_id: str) -> str | None:
    return INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id))


@pytest.mark.parametrize(
    ("manufacturer", "expected"), [(classes.SIGNIFY, "hue"), (IKEA, "other"), ("Signify", "other")]
)
async def test_a_light_is_classed_by_its_devices_manufacturer(hass, bridge, manufacturer, expected):
    entity_id = await lamp(hass, bridge, manufacturer=manufacturer)

    assert capability(hass, entity_id) == expected


async def test_a_light_with_no_device_cant_be_classed(hass, bridge):
    entity_id = await lamp(hass, bridge)
    er.async_get(hass).async_update_entity(entity_id, device_id=None)

    assert capability(hass, entity_id) is None


async def scene(hass, bridge, manufacturers: dict[str, str], *, smart: bool = False, missing: bool = False) -> str:
    """scene.relax over one light per entry, made by that manufacturer; `missing` adds one the bridge doesn't list."""
    for light_id, manufacturer in manufacturers.items():
        bridge.light(light_id, manufacturer=manufacturer)
    actions = [light_action(light_id, dimming={"brightness": 50.0}) for light_id in manufacturers]
    if missing:
        actions.append(light_action("gone", dimming={"brightness": 50.0}))
    bridge.scene("scene-1", actions, smart=smart)
    entry = await hue_entry(hass, bridge)
    return add_hue_entity(hass, entry, "scene.relax", "scene-1")


@pytest.mark.parametrize(
    ("manufacturers", "expected"),
    [
        pytest.param({"one": classes.SIGNIFY, "two": classes.SIGNIFY}, "hue", id="hue"),
        pytest.param({"one": classes.SIGNIFY, "two": IKEA}, "other", id="one_other"),
        pytest.param({}, "hue", id="writes_none"),
    ],
)
async def test_a_scene_is_classed_by_the_lights_it_writes(hass, bridge, manufacturers, expected):
    assert capability(hass, await scene(hass, bridge, manufacturers)) == expected


async def test_a_smart_scene_is_its_own_class(hass, bridge):
    assert capability(hass, await scene(hass, bridge, {}, smart=True)) == "smart_scene"


async def test_a_scene_missing_from_the_bridge_is_hue(hass, bridge):
    # It writes nothing (set_scene rejects it as scene_not_found), so no light's class is reached.
    entry = await hue_entry(hass, bridge)
    assert capability(hass, add_hue_entity(hass, entry, "scene.gone", "scene-gone")) == "hue"


async def test_a_scene_with_a_light_the_bridge_doesnt_list_cant_be_classed(hass, bridge):
    assert capability(hass, await scene(hass, bridge, {"one": classes.SIGNIFY}, missing=True)) is None


async def test_a_scene_with_a_light_ha_has_no_device_for_cant_be_classed(hass, bridge):
    entity_id = await scene(hass, bridge, {"one": classes.SIGNIFY})
    devices = dr.async_get(hass)
    devices.async_remove_device(devices.async_get_device_by_identifier(("hue", "device-one"), get_entry(hass)).id)

    assert capability(hass, entity_id) is None


def get_entry(hass) -> str:
    return hass.config_entries.async_entries("hue")[0].entry_id


@pytest.mark.parametrize("adapter", ADAPTERS, ids=lambda adapter: adapter.action)
def test_hue_is_verified_and_other_experimental_on_every_adapter(adapter):
    # The step 8 PR argues each: no action passes the Documented test for other (plan Decision 2).
    assert adapter.scope.capabilities == {"hue": Level.VERIFIED, "other": Level.EXPERIMENTAL}


def test_only_set_scene_lists_smart_scenes_and_no_entry_harms():
    listed = {adapter.action: set(adapter.scope.doesnt_work) for adapter in ADAPTERS if adapter.scope.doesnt_work}

    assert listed == {"set_scene": {"smart_scene"}}
    assert not any(adapter.scope.harms for adapter in ADAPTERS)


async def test_another_makers_light_runs_only_with_experimental_features(hass, bridge):
    entity_id = await lamp(hass, bridge, manufacturer=IKEA)

    with pytest.raises(TargetNotSupported) as raised:
        await call_service(hass, "stop", {"entity_id": entity_id})
    assert raised.value.reason == "experimental_off"

    allow_experimental(hass)
    assert await call(hass, "stop", {"entity_id": entity_id}) == {entity_id: SENT}
    assert bridge.puts == [("light/light-1", STOP)]


async def mixed_room(hass, bridge, *, entity_for_two: bool = True) -> str:
    """light.room over a Hue light (one) and an IKEA light (two), both on at 60 %; `entity_for_two` False leaves the
    IKEA light without a light entity in HA, as the bridge still lists it."""
    bridge.light("one", on=True)
    bridge.light("two", on=True, manufacturer=IKEA)
    bridge.room("grouped-1", ["one", "two"], brightness=60.0)
    entry = await hue_entry(hass, bridge)
    members = [add_hue_entity(hass, entry, "light.one", "one", state="on")]
    if entity_for_two:
        members.append(add_hue_entity(hass, entry, "light.two", "two", state="on"))
    add_hue_group(hass, entry, "light.room", "grouped-1", members)
    return "light.room"


async def test_a_room_with_another_makers_light_falls_back_to_its_members(hass, bridge):
    # Experimental features off: the Hue light runs on its own, the IKEA one is skipped, and the room gets no result.
    await mixed_room(hass, bridge)

    response = await call(hass, "stop", {"entity_id": "light.room"})

    assert response == {"light.one": SENT}
    assert bridge.puts == [("light/one", STOP)]


async def test_a_room_runs_whole_with_experimental_features(hass, bridge):
    await mixed_room(hass, bridge)
    allow_experimental(hass)

    response = await call_service(hass, "stop", {"entity_id": "light.room"})

    assert response == {
        "light.room": result(
            "hue",
            "sent",
            capabilities=["hue", "other"],
            member_capabilities={"light.one": "hue", "light.two": "other"},
        )
    }
    assert bridge.puts == [("grouped_light/grouped-1", STOP)]


async def test_a_room_light_with_no_entity_is_left_out_of_the_member_map(hass, bridge):
    # Its class counts in the room's capabilities, as the room's write reaches it, but it has no entity of its own to
    # show the call reached it, so member_capabilities names only the light that has one (docs/action-behavior.md).
    await mixed_room(hass, bridge, entity_for_two=False)
    allow_experimental(hass)

    response = await call_service(hass, "stop", {"entity_id": "light.room"})

    assert response == {
        "light.room": result("hue", "sent", capabilities=["hue", "other"], member_capabilities={"light.one": "hue"})
    }
    assert bridge.puts == [("grouped_light/grouped-1", STOP)]


async def test_a_room_light_with_no_entity_still_classes_the_room(hass, bridge):
    # The room's write would reach the IKEA light, so the room takes its class; the light itself has no target to
    # fall back to, so only the Hue light runs.
    await mixed_room(hass, bridge, entity_for_two=False)

    target = resolve(hass, get_runtime(hass).registry, "light.room")
    members = INTEGRATION.expand_group(hass, target)
    assert [INTEGRATION.capability(hass, member) for member in members] == ["hue", "other"]
    assert members[1].state is None

    response = await call(hass, "stop", {"entity_id": "light.room"})

    assert response == {"light.one": SENT}


async def test_a_room_light_ha_has_no_device_for_classes_the_room_unknown(hass, bridge):
    # Its class can't be named, so the room counts as Experimental: with the option off it falls back to its lights
    # that have entities, and set_attributes still writes them.
    await mixed_room(hass, bridge, entity_for_two=False)
    devices = dr.async_get(hass)
    devices.async_remove_device(devices.async_get_device_by_identifier(("hue", "device-two"), get_entry(hass)).id)
    members = INTEGRATION.expand_group(hass, resolve(hass, get_runtime(hass).registry, "light.room"))

    assert [INTEGRATION.capability(hass, member) for member in members] == ["hue", None]
    assert await call(hass, "stop", {"entity_id": "light.room"}) == {"light.one": SENT}
    bridge.puts.clear()
    assert await call(hass, "set_attributes", {"entity_id": "light.room", "brightness": 40}) == {"light.one": SENT}
    assert [path for path, _ in bridge.puts] == ["light/one"]


async def test_set_attributes_on_a_mixed_room_writes_its_hue_lights_alone(hass, bridge):
    # set_attributes takes a room's members (no native groups); another brand's is skipped with the option off.
    await mixed_room(hass, bridge)

    response = await call(hass, "set_attributes", {"entity_id": "light.room", "brightness": 40})

    assert response == {"light.one": SENT}
    assert [path for path, _ in bridge.puts] == ["light/one"]


async def test_get_attributes_on_a_mixed_room_answers_for_its_hue_lights(hass, bridge):
    # With the option off the room falls back, so the response is keyed by its Hue light, not the room.
    await mixed_room(hass, bridge)

    response = await call(hass, "get_attributes", {"entity_id": "light.room"})

    assert list(response) == ["light.one"]
