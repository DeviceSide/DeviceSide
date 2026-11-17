"""scripts/check_ha_literals.py: a string literal where HA defines the name, and the 0-255 brightness guard."""

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("check_ha_literals", REPO / "scripts" / "check_ha_literals.py")
check_ha_literals = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_ha_literals)


def flagged(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "mod.py"
    path.write_text(body)
    return check_ha_literals.violations(path)


@pytest.mark.parametrize(
    ("body", "constant"),
    [
        ("await hass.services.async_call('light', SERVICE_TURN_ON, {})", "Platform.LIGHT"),
        ("await hass.services.async_call(domain='switch', service=SERVICE_TURN_ON)", "Platform.SWITCH"),
        ("await hass.services.async_call(Platform.LIGHT, 'turn_off', {})", "SERVICE_TURN_OFF"),
        ("await hass.services.async_call(Platform.LIGHT, service='toggle')", "SERVICE_TOGGLE"),
        ("await hass.services.async_call(Platform.LIGHT, SERVICE_TURN_ON, {'entity_id': x})", "ATTR_ENTITY_ID"),
        ("await hass.services.async_call(Platform.LIGHT, SERVICE_TURN_ON, {'hs_color': x})", "ATTR_HS_COLOR"),
        ("ok = entry.domain == 'light'", "Platform.LIGHT"),
        ("ok = entry.platform in (Platform.LIGHT, 'scene')", "Platform.SCENE"),
        ("ok = 'light' == entry.domain", "Platform.LIGHT"),
        ("x = Adapter(domains=verified('light', Platform.SWITCH))", "Platform.LIGHT"),
        ("ok = state.state == 'on'", "STATE_ON"),
        ("ok = light.state.state != 'off'", "STATE_OFF"),
        ("v = state.attributes.get('color_mode')", "ATTR_COLOR_MODE"),
        ("v = state.attributes['min_color_temp_kelvin']", "ATTR_MIN_COLOR_TEMP_KELVIN"),
    ],
)
def test_a_literal_in_an_ha_position_is_flagged_with_its_constant(tmp_path, body, constant):
    found = flagged(tmp_path, body + "\n")
    assert len(found) == 1
    assert constant in found[0]


def test_constants_pass(tmp_path):
    body = (
        "await hass.services.async_call(Platform.LIGHT, SERVICE_TURN_ON, {ATTR_ENTITY_ID: x})\n"
        "ok = entry.domain == Platform.LIGHT and state.state == STATE_ON\n"
        "v = state.attributes.get(ATTR_COLOR_MODE)\n"
    )
    assert flagged(tmp_path, body) == []


def test_a_vendor_payload_is_not_flagged(tmp_path):
    body = (
        "payload = {'state': 'on', 'brightness': 5, 'entity_id': 'x'}\n"
        "COMPONENTS = {'switch': 'Switch', 'light': 'Light'}\n"
        "ok = component == 'switch' and reply['state'] == 'on'\n"
        "v = reply.get('brightness')\n"
    )
    assert flagged(tmp_path, body) == []


def test_an_escape_with_a_reason_passes(tmp_path):
    body = "ok = entry.domain == 'light'  # ha-literal: Shelly's component key\n"
    assert flagged(tmp_path, body) == []


@pytest.mark.parametrize("marker", ["# ha-literal:", "# ha-literal", "# ha-literal:   "])
def test_an_escape_without_a_reason_is_flagged(tmp_path, marker):
    assert len(flagged(tmp_path, f"ok = entry.domain == 'light'  {marker}\n")) == 1


def test_a_multi_line_call_is_flagged_on_the_literal_line(tmp_path):
    body = "await hass.services.async_call(\n    Platform.LIGHT,\n    'turn_on',\n    {},\n)\n"
    found = flagged(tmp_path, body)
    assert len(found) == 1
    assert ":3:" in found[0]


def test_attr_brightness_without_a_marker_is_flagged(tmp_path):
    found = flagged(tmp_path, "data = {ATTR_BRIGHTNESS: 255}\n")
    assert len(found) == 1
    assert "BRIGHTNESS_FIELD" in found[0]


def test_attr_brightness_as_an_attribute_is_flagged(tmp_path):
    assert len(flagged(tmp_path, "v = light.ATTR_BRIGHTNESS\n")) == 1


def test_attr_brightness_with_a_reason_passes(tmp_path):
    assert flagged(tmp_path, "data = {ATTR_BRIGHTNESS: 255}  # ha-255: service data is a byte\n") == []


@pytest.mark.parametrize("marker", ["# ha-255:", "# ha-255", "# ha-255:  "])
def test_attr_brightness_marker_without_a_reason_is_flagged(tmp_path, marker):
    assert len(flagged(tmp_path, f"data = {{ATTR_BRIGHTNESS: 255}}  {marker}\n")) == 1


def test_the_attr_brightness_import_is_not_flagged(tmp_path):
    body = "from homeassistant.components.light import ATTR_BRIGHTNESS\n"
    assert flagged(tmp_path, body) == []
    assert flagged(tmp_path, "from homeassistant.components.light import ATTR_BRIGHTNESS as B\n") == []
