"""lacking(): the fields a target's state says it can't take, less those its adapter takes unlisted."""

from types import SimpleNamespace

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.core import State

from custom_components.deviceside.actions.set_attributes import SetAttributesRequest
from custom_components.deviceside.core.fields import lacking
from custom_components.deviceside.core.models import LightFields

REQUEST = SetAttributesRequest(light=LightFields(color_temp_kelvin=3000, transition=1), brightness=50)
DIMMABLE = {"supported_color_modes": [ColorMode.BRIGHTNESS], "supported_features": 0}


def target(entity_id: str, attributes: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(domain=entity_id.split(".")[0], state=State(entity_id, "on", attributes or {}))


def test_a_light_lacks_what_its_state_says_it_cant_take():
    assert lacking(target("light.a", DIMMABLE), REQUEST) == {"color_temp_kelvin", "transition"}


def test_a_light_whose_state_lists_nothing_lacks_nothing():
    assert lacking(target("light.a"), REQUEST) == frozenset()


def test_an_unlisted_field_is_never_lacked_by_a_light_and_the_others_still_are():
    assert lacking(target("light.a", DIMMABLE), REQUEST, frozenset({"color_temp_kelvin"})) == {"transition"}


@pytest.mark.parametrize("unlisted", [frozenset(), frozenset({"color_temp_kelvin"})])
def test_a_switch_lacks_every_field_unlisted_or_not(unlisted):
    assert lacking(target("switch.s"), REQUEST, unlisted) == REQUEST.fields_present()
