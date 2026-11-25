"""Hue's classes (classes.py): a light's by its device's manufacturer, a scene's by the lights it writes, a room's by
its members, a light with no entity included; and what each class's level does at the gate."""

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside import actions
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.hue import ADAPTERS, INTEGRATION, classes

from .conftest import SENT, STOP, call, color_lamp, hs_xy, lamp
from ...conftest import call as call_service
from ...conftest import refusal, result
from ...fixtures.hue import add_hue_entity, add_hue_group, hue_entry, light_action

pytestmark = pytest.mark.usefixtures("setup_production")

IKEA = "IKEA of Sweden"


def capability(hass, entity_id: str) -> str | None:
    return INTEGRATION.capability(hass, resolve(hass, get_runtime(hass).registry, entity_id))


GL_C_008P = ("GLEDOPTO", "GL-C-008P")


@pytest.mark.parametrize(
    ("manufacturer", "model_id", "expected"),
    [
        (classes.SIGNIFY, None, "hue"),
        (IKEA, None, "other"),
        ("Signify", None, "other"),
        (*GL_C_008P, "gledopto_gl_c_008p"),
        ("Gledopto", "C-ZB-LC20v2-RGBCCT", "gledopto_gl_c_008p"),
        ("GLEDOPTO", "GL-C-006P", "other"),
    ],
)
async def test_a_light_is_classed_by_its_devices_manufacturer_and_model(hass, bridge, manufacturer, model_id, expected):
    entity_id = await lamp(hass, bridge, manufacturer=manufacturer, model_id=model_id)

    assert capability(hass, entity_id) == expected


async def test_a_light_with_no_device_cant_be_classed(hass, bridge):
    entity_id = await lamp(hass, bridge)
    er.async_get(hass).async_update_entity(entity_id, device_id=None)

    assert capability(hass, entity_id) is None


async def scene(
    hass, bridge, manufacturers: dict[str, str | tuple[str, str]], *, smart: bool = False, missing: bool = False
) -> str:
    """scene.relax over one light per entry, made by that manufacturer; `missing` adds one the bridge doesn't list."""
    for light_id, maker in manufacturers.items():
        manufacturer, model_id = maker if isinstance(maker, tuple) else (maker, None)
        bridge.light(light_id, manufacturer=manufacturer, model_id=model_id)
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
        pytest.param({"one": classes.SIGNIFY, "two": GL_C_008P}, "gledopto_gl_c_008p", id="one_gl_c_008p"),
        pytest.param({"one": IKEA, "two": GL_C_008P}, "other", id="two_others"),
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
def test_hue_is_verified_and_other_documented_on_every_adapter(adapter):
    # other on a bridge's one request (docs/evidence.md, Levels): every light gets the same CLIP v2 request. The
    # GL-C-008P shares other's levels but get_attributes', as it misreports its color temperature mode (core #93459).
    levels = {"hue": Level.VERIFIED, "other": Level.DOCUMENTED}
    if adapter.action != "get_attributes":
        levels["gledopto_gl_c_008p"] = Level.DOCUMENTED
    assert adapter.scope.capabilities == levels


def test_only_set_scene_lists_smart_scenes_and_none_harms():
    listed = {
        adapter.action: set(adapter.scope.no_known_method) for adapter in ADAPTERS if adapter.scope.no_known_method
    }

    assert listed == {"set_scene": {"smart_scene"}}
    # set_scene's failure doesn't harm, and no other Hue adapter holds an entry.
    failure_harms = {action.key: action.failure_harms for action in actions.discover()}
    assert not any(adapter.scope.harms(failure_harms[adapter.action]) for adapter in ADAPTERS)


# Each light action's data on a color lamp: every field the action needs, so only the class decides.
LIGHT_ACTIONS = {
    "get_attributes": {},
    "lower_brightness": {},
    "lower_saturation": {},
    "raise_brightness": {},
    "raise_saturation": {},
    "set_attributes": {"brightness": 40},
    "stop": {},
}


def test_every_adapter_is_a_light_action_or_set_scene():
    assert {adapter.action for adapter in ADAPTERS} == {*LIGHT_ACTIONS, "set_scene"}


@pytest.mark.parametrize("action", LIGHT_ACTIONS)
async def test_another_makers_light_runs_every_light_action_with_labs_off(hass, bridge, action):
    entity_id = await color_lamp(hass, bridge, manufacturer=IKEA)

    response = await call(hass, action, {"entity_id": entity_id, **LIGHT_ACTIONS[action]})

    assert list(response) == [entity_id]
    # A read sends nothing; every write goes to the light.
    assert [path for path, _ in bridge.puts] == ([] if action == "get_attributes" else ["light/light-1"])


@pytest.mark.parametrize("action", [action for action in LIGHT_ACTIONS if action != "get_attributes"])
async def test_a_gl_c_008p_runs_every_light_action_but_get_attributes(hass, bridge, action):
    entity_id = await color_lamp(hass, bridge, manufacturer=GL_C_008P[0], model_id=GL_C_008P[1])

    response = await call(hass, action, {"entity_id": entity_id, **LIGHT_ACTIONS[action]})

    assert list(response) == [entity_id]
    assert [path for path, _ in bridge.puts] == ["light/light-1"]


async def test_a_gl_c_008p_is_refused_get_attributes_as_not_built(hass, bridge):
    # It misreports its color temperature mode (core #93459), and get_attributes reports the light's actual value.
    entity_id = await color_lamp(hass, bridge, manufacturer=GL_C_008P[0], model_id=GL_C_008P[1])

    assert await refusal(hass, "get_attributes", {"entity_id": entity_id}) == "not_built"


async def test_a_scene_writing_another_makers_light_runs_with_labs_off(hass, bridge):
    entity_id = await scene(hass, bridge, {"one": classes.SIGNIFY, "two": IKEA})

    response = await call(hass, "set_scene", {"entity_id": entity_id})

    assert response == {entity_id: SENT}
    assert sorted(path for path, _ in bridge.puts) == ["light/one", "light/two"]


async def mixed_room(hass, bridge, *, entity_for_two: bool = True, two: str | None = IKEA, color: bool = False) -> str:
    """light.room over a Hue light (one) and a second light (two, an IKEA one unless `two` names another maker), both
    on at 60 %, color bulbs if `color`; `entity_for_two` False leaves the second light without a light entity in HA,
    as the bridge still lists it."""
    xy = hs_xy(200.0, 50.0) if color else None
    bridge.light("one", on=True, xy=xy)
    bridge.light("two", on=True, xy=xy, **({"manufacturer": two} if two else {}))
    bridge.room("grouped-1", ["one", "two"], brightness=60.0)
    entry = await hue_entry(hass, bridge)
    members = [add_hue_entity(hass, entry, "light.one", "one", state="on")]
    if entity_for_two:
        members.append(add_hue_entity(hass, entry, "light.two", "two", state="on"))
    add_hue_group(hass, entry, "light.room", "grouped-1", members)
    return "light.room"


@pytest.mark.parametrize("action", LIGHT_ACTIONS)
async def test_a_room_with_another_makers_light_runs_as_a_room_on_every_light_action(hass, bridge, action):
    # Labs off: the room takes the weakest of its members' levels, Documented, so nothing falls back. set_attributes
    # writes a room light by light (no native groups), and a read sends nothing.
    await mixed_room(hass, bridge, color=True)

    response = await call_service(hass, action, {"entity_id": "light.room", **LIGHT_ACTIONS[action]})

    members = {"light.one": "hue", "light.two": "other"}
    if action == "set_attributes":
        assert {entity_id: entry["capability"] for entity_id, entry in response.items()} == members
        assert [path for path, _ in bridge.puts] == ["light/one", "light/two"]
        return
    assert list(response) == ["light.room"]
    assert response["light.room"]["capabilities"] == ["hue", "other"]
    assert response["light.room"]["member_capabilities"] == members
    paths = {path for path, _ in bridge.puts}
    assert paths == (set() if action == "get_attributes" else {"grouped_light/grouped-1"}), paths


async def test_a_room_runs_whole_and_names_each_member_class(hass, bridge):
    await mixed_room(hass, bridge, two=None)

    response = await call_service(hass, "stop", {"entity_id": "light.room"})

    assert response == {
        "light.room": result(
            "hue", "sent", capabilities=["hue"], member_capabilities={"light.one": "hue", "light.two": "hue"}
        )
    }
    assert bridge.puts == [("grouped_light/grouped-1", STOP)]


async def test_a_room_light_with_no_entity_is_left_out_of_the_member_map(hass, bridge):
    # Its class counts in the room's capabilities, as the room's write reaches it, but it has no entity of its own to
    # show the call reached it, so member_capabilities names only the light that has one (docs/action-behavior.md).
    await mixed_room(hass, bridge, entity_for_two=False, two=None)

    response = await call_service(hass, "stop", {"entity_id": "light.room"})

    assert response == {
        "light.room": result("hue", "sent", capabilities=["hue"], member_capabilities={"light.one": "hue"})
    }
    assert bridge.puts == [("grouped_light/grouped-1", STOP)]


async def test_a_room_light_with_no_entity_still_classes_the_room(hass, bridge):
    # The room's write would reach the IKEA light, so the room takes its class, and runs whole at its level.
    await mixed_room(hass, bridge, entity_for_two=False)

    target = resolve(hass, get_runtime(hass).registry, "light.room")
    members = INTEGRATION.expand_group(hass, target)
    assert [INTEGRATION.capability(hass, member) for member in members] == ["hue", "other"]
    assert members[1].state is None
    assert not members[1].addressable
    assert members[0].addressable

    response = await call_service(hass, "stop", {"entity_id": "light.room"})

    assert response == {
        "light.room": result("hue", "sent", capabilities=["hue", "other"], member_capabilities={"light.one": "hue"})
    }
    assert bridge.puts == [("grouped_light/grouped-1", STOP)]


async def test_a_room_light_ha_has_no_device_for_classes_the_room_unknown(hass, bridge):
    # Its class can't be named, so the room counts as a Labs item: with the option off it falls back to its lights
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
    assert list(await call(hass, "get_attributes", {"entity_id": "light.room"})) == ["light.one"]
