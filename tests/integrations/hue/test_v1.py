"""The Hue v1 bridge: a separate integration on the hue domain, declared only to refuse its entities (v1.py), so no Hue
adapter sees one. Unit tests only: there is no v1 bridge on the rig (plan Decision 32)."""

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.errors import TargetNotSupported
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.hue import v1

from .conftest import call
from ...conftest import call as call_service
from ...fixtures.hue import HueBridge, add_hue_entity, hue_entry

pytestmark = pytest.mark.usefixtures("setup_production")


async def v1_lamp(hass, bridge, entity_id: str = "light.lamp") -> str:
    bridge.light("light-1", on=True)
    entry = await hue_entry(hass, bridge, api_version=1)
    return add_hue_entity(hass, entry, entity_id, "light-1", state="on")


@pytest.mark.parametrize(
    ("action", "data"),
    [
        pytest.param("raise_brightness", {}, id="raise_brightness"),
        pytest.param("lower_brightness", {}, id="lower_brightness"),
        pytest.param("raise_saturation", {}, id="raise_saturation"),
        pytest.param("lower_saturation", {}, id="lower_saturation"),
        pytest.param("stop", {}, id="stop"),
        pytest.param("get_attributes", {}, id="get_attributes"),
        pytest.param("set_attributes", {"brightness": 40}, id="set_attributes"),
        pytest.param("set_scene", {}, id="set_scene"),
        # No Hue adapter at all: still refused as v1, not as no_adapter.
        pytest.param("turn_on_for", {"duration": 5}, id="turn_on_for"),
        pytest.param("raise_hue", {}, id="raise_hue"),
    ],
)
async def test_a_named_v1_target_raises_naming_the_v1_bridge(hass, bridge, action, data):
    if action == "set_scene":
        bridge.scene("scene-1", [])
        entry = await hue_entry(hass, bridge, api_version=1)
        entity_id = add_hue_entity(hass, entry, "scene.relax", "scene-1")
    else:
        entity_id = await v1_lamp(hass, bridge)

    with pytest.raises(TargetNotSupported) as raised:
        await call_service(hass, action, {"entity_id": entity_id, **data})

    assert raised.value.reason == "integration_not_supported"
    assert raised.value.translation_key == "doesnt_work"
    assert raised.value.translation_placeholders["why"] == v1.WHY
    assert "v1" in v1.WHY
    assert bridge.puts == []


async def test_an_indirect_v1_target_is_skipped_beside_a_v2_light(hass, bridge):
    await v1_lamp(hass, bridge, "light.old")
    v2 = HueBridge()
    v2.light("light-2", on=True, brightness=60.0)
    entry = await hue_entry(hass, v2)
    add_hue_entity(hass, entry, "light.new", "light-2", state="on", attributes={"brightness": 153})
    hass.states.async_set("group.both", "on", {"entity_id": ["light.old", "light.new"]})

    response = await call(hass, "stop", {"entity_id": "group.both"})

    assert list(response) == ["light.new"]
    assert bridge.puts == []
    assert v2.puts


async def test_an_indirect_v1_target_is_reported_skipped(hass, bridge, caplog):
    await v1_lamp(hass, bridge, "light.old")
    hass.states.async_set("group.old", "on", {"entity_id": ["light.old"]})

    await call_service(hass, "stop", {"entity_id": "group.old"}, return_response=False)

    assert "light.old (integration_not_supported)" in caplog.text


async def test_v1_entities_resolve_to_the_v1_integration_and_v2_to_hue(hass, bridge):
    await v1_lamp(hass, bridge, "light.old")
    v2 = HueBridge()
    v2.light("light-2")
    add_hue_entity(hass, await hue_entry(hass, v2), "light.new", "light-2")
    registry = get_runtime(hass).registry

    assert resolve(hass, registry, "light.old").integration == "hue_v1"
    assert resolve(hass, registry, "light.new").integration == "hue"


async def test_detect_claims_only_a_v1_config_entry(hass, bridge):
    old = await v1_lamp(hass, bridge, "light.old")
    v2 = HueBridge()
    v2.light("light-2")
    new = add_hue_entity(hass, await hue_entry(hass, v2), "light.new", "light-2")
    entities = er.async_get(hass)
    orphan = entities.async_get_or_create("light", "hue", "orphan")

    assert v1.detect(hass, entities.async_get(old), None)
    assert not v1.detect(hass, entities.async_get(new), None)
    assert not v1.detect(hass, orphan, None)
