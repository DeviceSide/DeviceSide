"""Schema and parse for set_auto_off / set_auto_on / clear_auto_off / clear_auto_on."""

import probatio
import pytest
from homeassistant.core import ServiceCall

from custom_components.deviceside.actions.clear_auto_off import ClearAutoOff
from custom_components.deviceside.actions.clear_auto_on import ClearAutoOn
from custom_components.deviceside.actions.set_auto_off import SetAutoOff
from custom_components.deviceside.actions.set_auto_on import SetAutoOn
from custom_components.deviceside.core.models import ActionKind, Request


def _parse(hass, action, data):
    return action.parse(hass, ServiceCall(hass, "deviceside", action.key, action.schema()(data)))


@pytest.mark.parametrize("action", [SetAutoOff, SetAutoOn])
async def test_set_takes_a_duration_rounded_to_10ms(hass, action):
    request = _parse(hass, action, {"entity_id": "switch.a", "duration": {"minutes": 1, "milliseconds": 506}})
    assert request.duration_s == 60.51


@pytest.mark.parametrize("action", [SetAutoOff, SetAutoOn])
def test_set_requires_a_duration_and_no_light_fields(action):
    with pytest.raises(probatio.Invalid):
        action.schema()({"entity_id": "switch.a"})
    with pytest.raises(probatio.Invalid):
        action.schema()({"entity_id": "light.a", "duration": 5, "brightness": 10})


@pytest.mark.parametrize("action", [ClearAutoOff, ClearAutoOn])
async def test_clear_takes_only_a_target(hass, action):
    assert _parse(hass, action, {"entity_id": "switch.a"}) == Request()
    with pytest.raises(probatio.Invalid):
        action.schema()({"entity_id": "switch.a", "duration": 0})


@pytest.mark.parametrize("action", [SetAutoOff, SetAutoOn, ClearAutoOff, ClearAutoOn])
def test_each_is_a_setting_on_lights_and_switches(action):
    assert action.kind is ActionKind.SETTING
    assert action.domains == {"light", "switch"}
