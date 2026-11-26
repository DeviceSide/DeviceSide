"""core.ha_scene: recognizing a Home Assistant scene, and turning each light's scene state into what to write."""

import logging
from types import SimpleNamespace

import pytest
from homeassistant.components.homeassistant.scene import DATA_PLATFORM, SceneConfig
from homeassistant.core import State

from custom_components.deviceside.actions.set_attributes import SetAttributesRequest
from custom_components.deviceside.core import ha_scene as module
from custom_components.deviceside.core.ha_scene import OFF, SKIPPED, is_ha_scene, light_write, scene_lights
from custom_components.deviceside.core.models import LightFields

LAMP = "light.lamp"


def _on(**attributes) -> State:
    return State(LAMP, "on", attributes)


def _scene(hass, entity_id: str, states: dict[str, State], scene_id: str | None = "abc") -> SimpleNamespace:
    entity = SimpleNamespace(scene_config=SceneConfig(scene_id, "Evening", None, states))
    platform = hass.data.get(DATA_PLATFORM) or SimpleNamespace(entities={})
    platform.entities[entity_id] = entity
    hass.data[DATA_PLATFORM] = platform
    return entity


# Recognition


async def test_a_ui_scene_is_recognized_with_its_light_states(hass):
    _scene(hass, "scene.evening", {LAMP: _on(brightness=255), "light.hall": State("light.hall", "off")})
    assert is_ha_scene(hass, "scene.evening")
    assert scene_lights(hass, "scene.evening") == {
        LAMP: SetAttributesRequest(brightness=100.0),
        "light.hall": OFF,
    }


async def test_a_yaml_scene_with_no_id_is_recognized(hass):
    """It has no entity registry entry, so the platform's own entities are what finds it."""
    _scene(hass, "scene.relax", {LAMP: _on(brightness=51)}, scene_id=None)
    assert is_ha_scene(hass, "scene.relax")
    assert scene_lights(hass, "scene.relax") == {LAMP: SetAttributesRequest(brightness=20.0)}


async def test_no_scene_platform_or_another_entity_is_not_a_scene(hass):
    assert not is_ha_scene(hass, "scene.evening")
    assert scene_lights(hass, "scene.evening") is None
    _scene(hass, "scene.evening", {LAMP: _on(brightness=10)})
    assert not is_ha_scene(hass, "scene.other")
    assert scene_lights(hass, "scene.other") is None
    assert not is_ha_scene(hass, "light.lamp")


async def test_a_scene_without_scene_config_warns_once_and_reads_as_gone(hass, caplog, monkeypatch):
    """A rename in HA must not raise."""
    monkeypatch.setattr(module, "_unreadable", set())
    hass.data[DATA_PLATFORM] = SimpleNamespace(entities={"scene.evening": SimpleNamespace()})
    with caplog.at_level(logging.WARNING, logger=module.__name__):
        assert not is_ha_scene(hass, "scene.evening")
        assert scene_lights(hass, "scene.evening") is None
    assert [record.message for record in caplog.records] == [
        "SimpleNamespace.scene_config.states is not what Home Assistant's scene platform held, "
        "so its scenes can't be read"
    ]


async def test_a_scene_removed_mid_call_reads_as_gone_on_the_next_read(hass):
    _scene(hass, "scene.evening", {LAMP: _on(brightness=255)})
    assert scene_lights(hass, "scene.evening") is not None
    del hass.data[DATA_PLATFORM].entities["scene.evening"]
    assert scene_lights(hass, "scene.evening") is None
    assert not is_ha_scene(hass, "scene.evening")


async def test_an_edited_scene_applies_on_the_next_read(hass):
    entity = _scene(hass, "scene.evening", {LAMP: _on(brightness=255)})
    entity.scene_config = SceneConfig("abc", "Evening", None, {LAMP: _on(brightness=51)})
    assert scene_lights(hass, "scene.evening") == {LAMP: SetAttributesRequest(brightness=20.0)}


async def test_non_lights_and_other_states_are_skipped_at_debug(hass, caplog):
    _scene(
        hass,
        "scene.evening",
        {
            "switch.plug": State("switch.plug", "on"),
            "cover.blind": State("cover.blind", "open"),
            "light.gone": State("light.gone", "unavailable"),
            LAMP: _on(brightness=255),
        },
    )
    with caplog.at_level(logging.DEBUG, logger=module.__name__):
        assert scene_lights(hass, "scene.evening") == {LAMP: SetAttributesRequest(brightness=100.0)}
    assert [(record.levelno, record.message) for record in caplog.records] == [
        (logging.DEBUG, "Scene scene.evening: skipping switch.plug, not a light"),
        (logging.DEBUG, "Scene scene.evening: skipping cover.blind, not a light"),
        (logging.DEBUG, "Scene scene.evening: skipping light.gone, state unavailable is neither on nor off"),
    ]


# State to request


def test_an_off_light_is_off_whatever_its_attributes():
    assert light_write(State(LAMP, "off", {"brightness": 255})) == OFF


def test_an_on_light_with_nothing_to_write_is_unchanged():
    assert light_write(_on()) is None
    assert light_write(_on(color_mode="onoff")) is None
    assert light_write(_on(effect="rainbow")) is None  # set_attributes has no effect field


@pytest.mark.parametrize(
    ("brightness", "percent"),
    [(1, 100 / 255), (255, 100.0), (128, 128 / 255 * 100)],
)
def test_brightness_is_a_percent_with_no_floor_raised(brightness, percent):
    request = light_write(_on(brightness=brightness))
    assert request == SetAttributesRequest(brightness=percent)
    assert request.brightness == pytest.approx(percent)


def test_brightness_1_is_below_half_a_percent():
    """Level 1 is the lowest level, 0.4 %: it must not become 1 %."""
    assert light_write(_on(brightness=1)).brightness == pytest.approx(0.392, abs=0.001)


def test_brightness_0_writes_nothing():
    """Core would turn the light off for brightness 0; the scene holds it on."""
    assert light_write(_on(brightness=0)) is None


def test_a_color_with_no_brightness_writes_the_color_alone():
    assert light_write(_on(color_mode="hs", hs_color=(30.0, 60.0))) == SetAttributesRequest(
        light=LightFields(hs_color=(30.0, 60.0))
    )


@pytest.mark.parametrize(
    ("attributes", "light"),
    [
        ({"color_mode": "color_temp", "color_temp_kelvin": 2700}, LightFields(color_temp_kelvin=2700)),
        ({"color_mode": "hs", "hs_color": (30.0, 60.0)}, LightFields(hs_color=(30.0, 60.0))),
        ({"color_mode": "rgb", "rgb_color": (255, 128, 0)}, LightFields(rgb_color=(255, 128, 0))),
        ({"color_mode": "xy", "xy_color": (0.5, 0.4)}, LightFields(xy_color=(0.5, 0.4))),
    ],
)
def test_the_color_mode_picks_the_one_color(attributes, light):
    """Every color attribute is present, as in a real light's state; only the mode's is written."""
    everything = {
        "color_temp_kelvin": 3000,
        "hs_color": (1.0, 2.0),
        "rgb_color": (1, 2, 3),
        "xy_color": (0.1, 0.2),
    }
    request = light_write(_on(brightness=255, **{**everything, **attributes}))
    assert request == SetAttributesRequest(light=light, brightness=100.0)


@pytest.mark.parametrize("mode", ["rgbw", "rgbww"])
def test_rgbw_modes_take_the_states_hs_color(mode):
    request = light_write(
        _on(
            color_mode=mode,
            hs_color=(40.0, 10.0),
            rgbw_color=(1, 2, 3, 4),
            rgbww_color=(1, 2, 3, 4, 5),
            brightness=255,
        )
    )
    assert request == SetAttributesRequest(light=LightFields(hs_color=(40.0, 10.0)), brightness=100.0)


def test_an_unknown_color_mode_takes_the_first_color_present():
    state = _on(color_mode="unknown", color_temp_kelvin=2700, rgb_color=(1, 2, 3), xy_color=(0.1, 0.2))
    assert light_write(state) == SetAttributesRequest(light=LightFields(color_temp_kelvin=2700))
    assert light_write(_on(rgb_color=(1, 2, 3), xy_color=(0.1, 0.2))) == SetAttributesRequest(
        light=LightFields(rgb_color=(1, 2, 3))
    )
    assert light_write(_on(hs_color=(5.0, 6.0), color_temp_kelvin=2700)) == SetAttributesRequest(
        light=LightFields(hs_color=(5.0, 6.0))
    )


def test_white_mode_writes_the_brightness_alone():
    """Core's white is a brightness, and a white-mode state holds no hs_color."""
    assert light_write(_on(color_mode="white", brightness=255)) == SetAttributesRequest(brightness=100.0)
    assert light_write(_on(color_mode="white")) is None


@pytest.mark.parametrize(
    ("mode", "missing"), [("xy", "xy_color"), ("rgbw", "hs_color"), ("color_temp", "color_temp_kelvin")]
)
def test_a_color_mode_whose_color_is_missing_is_skipped_with_a_warning(caplog, mode, missing):
    """As core's reproduce_state sends nothing for it, not even the brightness."""
    with caplog.at_level(logging.DEBUG, logger=module.__name__):
        assert light_write(_on(color_mode=mode, brightness=255)) == SKIPPED
    assert [(record.levelno, record.message) for record in caplog.records] == [
        (logging.WARNING, f"Skipping light.lamp: its scene state names color mode {mode} but holds no {missing}")
    ]


async def test_a_skipped_light_is_in_the_scene_lights(hass):
    _scene(hass, "scene.evening", {LAMP: _on(color_mode="xy"), "light.hall": _on(brightness=255)})
    assert scene_lights(hass, "scene.evening") == {LAMP: SKIPPED, "light.hall": SetAttributesRequest(brightness=100.0)}


async def test_an_unreadable_scene_platform_warns_once_and_reads_as_no_scene(hass, caplog, monkeypatch):
    monkeypatch.setattr(module, "_unreadable", set())
    hass.data[DATA_PLATFORM] = SimpleNamespace()
    with caplog.at_level(logging.WARNING, logger=module.__name__):
        assert not is_ha_scene(hass, "scene.evening")
        assert scene_lights(hass, "scene.evening") is None
    assert [record.message for record in caplog.records] == [
        "EntityPlatform.entities is not what Home Assistant's scene platform held, so its scenes can't be read"
    ]


def test_a_yaml_scene_lists_become_the_tuples_a_light_state_holds():
    assert light_write(_on(color_mode="rgb", rgb_color=[255, 128, 0])) == SetAttributesRequest(
        light=LightFields(rgb_color=(255, 128, 0))
    )
    assert light_write(_on(color_mode="xy", xy_color=[0.5, 0.4])) == SetAttributesRequest(
        light=LightFields(xy_color=(0.5, 0.4))
    )
