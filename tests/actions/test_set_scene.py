"""set_scene on Home Assistant scenes: each light routed through set_attributes (core/ha_scene.py, route)."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.components.homeassistant.scene import DATA_PLATFORM, SceneConfig
from homeassistant.core import Context, State
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.deviceside.actions.set_scene import SetScene
from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.action import Action, Ride
from custom_components.deviceside.core.models import Status
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.scope import AdapterScope, labs, verified

from ..conftest import allow_labs, call, refusal, result
from ..fakes.fake_integration import FakeSetAttributes
from ..fakes.scripted import ScriptedAdapter
from ..fixtures.fake import add_fake_entity, add_fake_native_group, add_ha_group, fake_config_entry

pytestmark = pytest.mark.usefixtures("setup_integration")

SCENE = "scene.evening"
SENT = result("homeassistant", "sent")


class SpecialSetAttributes(ScriptedAdapter):
    action = "set_attributes"
    integration = "fake_special"
    scope = AdapterScope(fields=verified("brightness"))


@pytest.fixture
def fake(hass):
    return fake_config_entry(hass)


@pytest.fixture
def special(hass, setup_integration):
    """fake_special with a set_attributes adapter, as a second integration a scene's lights may be on."""
    registry = get_runtime(hass).registry
    adapter = SpecialSetAttributes()
    adapter.kind = registry.adapter("set_attributes", "fake").kind
    registry._adapters[("set_attributes", "fake_special")] = adapter
    yield
    del registry._adapters[("set_attributes", "fake_special")]


@pytest.fixture
def turn_off(hass):
    return async_mock_service(hass, "light", "turn_off")


def on(entity_id: str, **attributes) -> State:
    return State(entity_id, "on", attributes)


def scene(hass, states: list[State], entity_id: str = SCENE) -> str:
    """A Home Assistant scene holding the states, as core's scene platform keeps one."""
    platform = hass.data.get(DATA_PLATFORM) or SimpleNamespace(entities={})
    platform.entities[entity_id] = SimpleNamespace(
        scene_config=SceneConfig("abc", "Evening", None, {state.entity_id: state for state in states})
    )
    hass.data[DATA_PLATFORM] = platform
    hass.states.async_set(entity_id, "unknown")
    return entity_id


def sent(reset_script) -> list[tuple[str, str, object, list[str]]]:
    """Each set_attributes execute: its integration, brightness and targets, in a stable order."""
    return sorted(
        (integration, request.brightness, targets)
        for integration, action, request, targets in reset_script.calls
        if action == "set_attributes"
    )


def test_set_scene_rides_set_attributes_for_ha_scenes():
    assert SetScene.rides == Ride("set_attributes", "scene", "homeassistant")
    assert Action.rides is None


async def test_only_a_loaded_ha_scene_is_claimed(hass):
    scene(hass, [on("light.a", brightness=255)])
    assert SetScene.claims(hass, SCENE)
    assert not SetScene.claims(hass, "scene.bridge")
    assert not Action.claims(hass, SCENE)


async def test_a_scene_across_two_integrations_writes_each_light(hass, fake, special, reset_script):
    add_fake_entity(hass, fake, "light.a")
    add_fake_entity(hass, fake, "light.b")
    add_fake_entity(hass, fake, "light.s", identifier="special_s")
    scene(hass, [on("light.a", brightness=255), on("light.b", brightness=51), on("light.s", brightness=255)])

    assert await call(hass, "set_scene", {"entity_id": SCENE}) == {SCENE: SENT}

    assert sent(reset_script) == [
        ("fake", 20.0, ["light.b"]),
        ("fake", 100.0, ["light.a"]),
        ("fake_special", 100.0, ["light.s"]),
    ]


async def test_lights_with_the_same_write_share_one_call(hass, fake, reset_script):
    add_fake_entity(hass, fake, "light.a")
    add_fake_entity(hass, fake, "light.b")
    scene(hass, [on("light.a", brightness=255), on("light.b", brightness=255)])

    await call(hass, "set_scene", {"entity_id": SCENE})

    assert sent(reset_script) == [("fake", 100.0, ["light.a", "light.b"])]


async def test_a_light_with_no_adapter_is_skipped_and_logged_while_the_rest_run(hass, fake, reset_script, caplog):
    add_fake_entity(hass, fake, "light.a")
    add_fake_entity(hass, fake, "light.s", identifier="special_s")  # fake_special has no set_attributes here
    scene(hass, [on("light.a", brightness=255), on("light.s", brightness=255)])

    assert await call(hass, "set_scene", {"entity_id": SCENE}) == {SCENE: SENT}

    assert sent(reset_script) == [("fake", 100.0, ["light.a"])]
    assert "set_scene skipped targets that can't take it: light.s (no_adapter), so they got no command" in caplog.text


async def test_a_named_scene_none_of_whose_lights_can_run_raises_before_anything_is_sent(hass, fake, reset_script):
    add_fake_entity(hass, fake, "light.s", identifier="special_s")
    add_fake_entity(hass, fake, "light.a")
    scene(hass, [on("light.s", brightness=255)])
    scene(hass, [on("light.a", brightness=255)], entity_id="scene.other")

    assert await refusal(hass, "set_scene", {"entity_id": [SCENE, "scene.other"]}) == "no_adapter"
    assert reset_script.calls == []


async def test_an_indirect_scene_none_of_whose_lights_can_run_is_skipped_and_logged(hass, fake, reset_script, caplog):
    add_fake_entity(hass, fake, "light.s", identifier="special_s")
    add_fake_entity(hass, fake, "light.a")
    scene(hass, [on("light.s", brightness=255)])
    scene(hass, [on("light.a", brightness=255)], entity_id="scene.other")

    assert await call(hass, "set_scene", {"entity_id": "all"}) == {"scene.other": SENT}
    assert f"{SCENE} (no_adapter), light.s (no_adapter)" in caplog.text


async def test_a_light_held_off_is_turned_off_with_the_callers_context(hass, fake, reset_script, turn_off):
    add_fake_entity(hass, fake, "light.a")
    scene(hass, [on("light.a", brightness=255), State("light.b", "off"), State("light.c", "off")])
    context = Context()

    response = await hass.services.async_call(
        DOMAIN, "set_scene", {"entity_id": SCENE}, blocking=True, return_response=True, context=context
    )

    assert response == {SCENE: SENT}
    assert [(c.data["entity_id"], c.context) for c in turn_off] == [(["light.b", "light.c"], context)]
    assert [request.context for _, _, request, _ in reset_script.calls] == [context]


async def test_a_scene_of_only_off_lights_is_sent(hass, turn_off):
    scene(hass, [State("light.b", "off")])

    assert await call(hass, "set_scene", {"entity_id": SCENE}) == {SCENE: SENT}
    assert len(turn_off) == 1


async def test_a_failed_turn_off_rejects_the_scene_after_the_rest_ran(hass, fake, reset_script, caplog):
    add_fake_entity(hass, fake, "light.a")
    scene(hass, [on("light.a", brightness=255), State("light.b", "off")])  # no light.turn_off service: it fails

    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "set_scene", {"entity_id": SCENE})

    assert err.value.translation_placeholders == {"summary": f"{SCENE}: some_lights_failed"}
    assert sent(reset_script) == [("fake", 100.0, ["light.a"])]
    assert f"set_scene {SCENE}: turning off light.b failed" in caplog.text


async def test_a_nested_ha_light_group_and_a_native_group_are_expanded(hass, fake, reset_script):
    for entity_id in ("light.a", "light.b"):
        add_fake_entity(hass, fake, entity_id)
    add_ha_group(hass, "light.inner", ["light.a"])
    add_ha_group(hass, "light.room", ["light.inner", "light.b"])
    for entity_id in ("light.c", "light.d"):
        add_fake_entity(hass, fake, entity_id)
    add_fake_native_group(hass, fake, "light.fake_group", ["light.c", "light.d"])
    scene(hass, [on("light.room", brightness=255), on("light.fake_group", brightness=255)])

    assert await call(hass, "set_scene", {"entity_id": SCENE}) == {SCENE: SENT}

    # The fake's set_attributes can't address a native group, so core expands it too.
    assert sent(reset_script) == [("fake", 100.0, ["light.a", "light.b", "light.c", "light.d"])]


async def test_a_light_reached_through_the_scene_has_it_as_its_group(hass, fake, reset_script):
    add_fake_entity(hass, fake, "light.a")
    add_fake_entity(hass, fake, "light.b")
    add_ha_group(hass, "light.room", ["light.b"])
    scene(hass, [on("light.a", brightness=255), on("light.room", brightness=255)])
    seen = []

    async def execute(adapter, hass, request, targets):
        seen.extend((target.entity_id, target.via_group, target.named) for target in targets)
        return [adapter.result(target, Status.SENT) for target in targets]

    with patch.object(FakeSetAttributes, "execute", execute):
        await call(hass, "set_scene", {"entity_id": SCENE})

    assert seen == [("light.a", SCENE, False), ("light.b", "light.room", False)]


async def test_labs_off_drops_a_labs_class_light_and_the_rest_run(hass, fake, reset_script, caplog):
    registry = get_runtime(hass).registry
    info = registry.integrations["fake"]
    registry.integrations["fake"] = replace(
        info,
        capability=lambda hass, target: target.entity_id.partition(".")[2].upper(),
        classes={"A": frozenset({"light"}), "B": frozenset({"light"})},
    )
    add_fake_entity(hass, fake, "light.a")
    add_fake_entity(hass, fake, "light.b")
    scene(hass, [on("light.a", brightness=255), on("light.b", brightness=255)])
    scope = replace(FakeSetAttributes.scope, capabilities=verified("A") | labs("B"))
    allow_labs(hass, False)
    try:
        with patch.object(FakeSetAttributes, "scope", scope):
            assert await call(hass, "set_scene", {"entity_id": SCENE}) == {SCENE: SENT}
            assert sent(reset_script) == [("fake", 100.0, ["light.a"])]
            assert "light.b (labs_off)" in caplog.text

            scene(hass, [on("light.b", brightness=255)])
            assert await refusal(hass, "set_scene", {"entity_id": SCENE}) == "labs_off"

            allow_labs(hass, True)
            reset_script.reset()
            assert await call(hass, "set_scene", {"entity_id": SCENE}) == {SCENE: SENT}
            assert sent(reset_script) == [("fake", 100.0, ["light.b"])]
    finally:
        registry.integrations["fake"] = info


@pytest.mark.parametrize(
    ("failing", "detail"), [(["light.b"], "some_lights_failed"), (["light.a", "light.b"], "error")]
)
async def test_a_device_failure_raises_once_every_light_has_run(hass, fake, reset_script, failing, detail):
    for entity_id in ("light.a", "light.b", "light.c"):
        add_fake_entity(hass, fake, entity_id)
    scene(hass, [on("light.a", brightness=255), on("light.b", brightness=255), on("light.c")])
    for entity_id in failing:
        reset_script.outcomes[entity_id] = RuntimeError("radio busy")

    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "set_scene", {"entity_id": SCENE})

    assert err.value.translation_key == "targets_failed"
    assert err.value.translation_placeholders == {"summary": f"{SCENE}: {detail}"}
    assert reset_script.started == ["light.a", "light.b"]


async def test_a_light_whose_color_is_missing_is_skipped_and_logged(hass, fake, reset_script, caplog):
    add_fake_entity(hass, fake, "light.a")
    add_fake_entity(hass, fake, "light.b")
    scene(hass, [on("light.a", color_mode="xy", brightness=255), on("light.b", brightness=255)])

    assert await call(hass, "set_scene", {"entity_id": SCENE}) == {SCENE: SENT}

    assert sent(reset_script) == [("fake", 100.0, ["light.b"])]
    assert "light.a (color_missing)" in caplog.text


async def test_a_scene_with_nothing_to_write_is_unchanged(hass, fake, reset_script):
    add_fake_entity(hass, fake, "light.a")
    scene(hass, [on("light.a"), State("switch.plug", "on")])

    assert await call(hass, "set_scene", {"entity_id": SCENE}) == {
        SCENE: result("homeassistant", "unchanged", detail="nothing_to_set")
    }
    assert reset_script.calls == []


async def test_a_light_left_nothing_to_write_after_drops_is_unchanged(hass, fake, reset_script):
    """A light that lacks the scene's color drops it, as set_attributes does, so it is left nothing: unchanged."""
    add_fake_entity(hass, fake, "light.a", attributes={"supported_color_modes": ["brightness"]})
    scene(hass, [on("light.a", color_mode="color_temp", color_temp_kelvin=2700)])

    assert await call(hass, "set_scene", {"entity_id": SCENE}) == {
        SCENE: result("homeassistant", "unchanged", detail="nothing_to_set")
    }


async def test_a_scene_whose_lights_are_each_unavailable_gets_no_result(hass, fake, reset_script):
    add_fake_entity(hass, fake, "light.a", state="unavailable")
    add_fake_entity(hass, fake, "light.b")
    scene(hass, [on("light.a", brightness=255)])
    scene(hass, [on("light.b", brightness=255)], entity_id="scene.other")

    assert await call(hass, "set_scene", {"entity_id": [SCENE, "scene.other"]}) == {"scene.other": SENT}


async def test_a_scene_removed_before_planning_is_rejected(hass, fake, reset_script):
    scene(hass, [on("light.a", brightness=255)])
    with (
        patch("custom_components.deviceside.core.ha_scene.scene_lights", return_value=None),
        pytest.raises(HomeAssistantError) as err,
    ):
        await call(hass, "set_scene", {"entity_id": SCENE})

    assert err.value.translation_placeholders == {"summary": f"{SCENE}: scene_not_found"}
