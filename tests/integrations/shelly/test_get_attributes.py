"""Shelly get_attributes: a GetStatus and a GetConfig per target, shaped as Hue's row plus the shared timer row and
the auto_off / auto_on settings."""

from datetime import UTC, datetime, timedelta
from unittest.mock import call as rpc_call

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.color import color_RGB_to_hs, color_RGB_to_xy

from custom_components.deviceside.integrations.shelly.get_attributes import config_row, status_row

from ...conftest import call, refusal
from ...fixtures.fake import add_switch_as_x
from ...fixtures.shelly import TIMER_STARTED_AT, add_shelly_entity, failing, shelly_device

pytestmark = pytest.mark.usefixtures("setup_production")

# Two seconds into a fixture timer.
NOW = datetime.fromtimestamp(TIMER_STARTED_AT, UTC) + timedelta(seconds=2)
BULB = {"brightness": 40, "ct": 4000, "rgb": [255, 0, 0]}
# The settings rows of a device with neither auto-off nor auto-on set, as every fixture device ships.
NO_AUTO = {"auto_off": None, "auto_on": None}


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(dt_util, "utcnow", lambda: NOW)


def timer(turns: str, remaining_s: float) -> dict:
    ends_at = (NOW + timedelta(seconds=remaining_s)).isoformat()
    return {"turns": turns, "ends_at": ends_at, "remaining_s": remaining_s}


@pytest.mark.parametrize(("action", "turns"), [("turn_on_for", "off"), ("turn_off_for", "on")])
async def test_switch_reports_the_running_timer(hass, action, turns):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:1")
    await call(hass, action, {"entity_id": "switch.porch", "duration": 5})

    response = await call(hass, "get_attributes", {"entity_id": "switch.porch"})

    assert response == {"switch.porch": {"timer": timer(turns, 3.0), **NO_AUTO}}
    assert call_rpc.await_args_list[-2:] == [
        rpc_call("Switch.GetStatus", {"id": 1}),
        rpc_call("Switch.GetConfig", {"id": 1}),
    ]


async def test_switch_as_x_light_reads_the_switch(hass):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")
    add_switch_as_x(hass, "light.porch", "switch.porch")
    await call(hass, "turn_on_for", {"entity_id": "light.porch", "duration": 5})

    response = await call(hass, "get_attributes", {"entity_id": "light.porch"})

    assert response == {"light.porch": {"timer": timer("off", 3.0), **NO_AUTO}}
    assert rpc_call("Switch.GetStatus", {"id": 0}) in call_rpc.await_args_list


async def test_switch_without_a_timer_reports_only_its_settings(hass):
    entry, _ = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")

    assert await call(hass, "get_attributes", {"entity_id": "switch.porch"}) == {"switch.porch": NO_AUTO}


async def test_bulb_in_cct_mode_reports_color_temperature_only(hass):
    entry, _ = shelly_device(hass, status={**BULB, "output": True, "mode": "cct"})
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0", state="on")

    response = await call(hass, "get_attributes", {"entity_id": "light.bulb"})

    assert response == {"light.bulb": {"brightness": 40, "color_temp_kelvin": 4000, **NO_AUTO}}


async def test_bulb_in_rgb_mode_reports_color_as_hue_does(hass):
    entry, _ = shelly_device(hass, status={**BULB, "output": True, "mode": "rgb"})
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0", state="on")

    response = await call(hass, "get_attributes", {"entity_id": "light.bulb"})

    assert response == {
        "light.bulb": {
            "brightness": 40,
            "rgb_color": [255, 0, 0],
            "hs_color": list(color_RGB_to_hs(255, 0, 0)),
            "xy_color": list(color_RGB_to_xy(255, 0, 0)),
            **NO_AUTO,
        }
    }


async def test_bulb_off_still_reads_and_carries_its_timer(hass):
    # The bulb keeps brightness, ct and rgb in its status while off (probed on a Multicolor Bulb Gen3).
    entry, _ = shelly_device(hass, status={**BULB, "mode": "cct"})
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0")
    await call(hass, "turn_off_for", {"entity_id": "light.bulb", "duration": 30})

    response = await call(hass, "get_attributes", {"entity_id": "light.bulb"})

    assert response == {
        "light.bulb": {"brightness": 40, "color_temp_kelvin": 4000, "timer": timer("on", 28.0), **NO_AUTO}
    }


def test_unknown_mode_reports_brightness_only():
    # Both ct and rgb are always in the status; neither is current in a mode this adapter doesn't know.
    assert status_row("RGBCCT", {**BULB, "output": True, "mode": "white"}, NOW) == {"brightness": 40}


@pytest.mark.parametrize(
    ("started_at", "remaining_s"),
    [
        (TIMER_STARTED_AT + 10, 5.0),  # device clock ahead of HA's: never more than the duration
        (TIMER_STARTED_AT - 10, 0.0),  # timer overdue: never negative
    ],
)
def test_remaining_time_is_clamped_to_the_duration(started_at, remaining_s):
    status = {"output": True, "timer_started_at": started_at, "timer_duration": 5.0}

    assert status_row("Switch", status, NOW) == {"timer": timer("off", remaining_s)}


async def test_gen1_and_non_timer_entities_are_refused(hass):
    gen1, _ = shelly_device(hass, gen1=True, mac="112233445566")
    add_shelly_entity(hass, gen1, "switch.old_relay", "relay_0")
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.child_lock", "boolean:200-boolean_child_lock")

    assert await refusal(hass, "get_attributes", {"entity_id": "switch.old_relay"}) == "gen1_unsupported"
    assert await refusal(hass, "get_attributes", {"entity_id": "switch.child_lock"}) == "not_addressable"
    assert not call_rpc.await_args_list


@pytest.mark.parametrize(
    ("key", "component"), [("light:0", "Light"), ("cct:0", "CCT"), ("rgb:0", "RGB"), ("rgbw:0", "RGBW")]
)
async def test_documented_components_report_timer_and_settings_only(hass, key, component):
    # Their light state isn't read yet: status_row has no branch for these components.
    entry, call_rpc = shelly_device(hass, status={"brightness": 40, "ct": 4000, "rgb": [255, 0, 0]})
    add_shelly_entity(hass, entry, "light.lamp", key)
    await call(hass, "turn_on_for", {"entity_id": "light.lamp", "duration": 5})

    response = await call(hass, "get_attributes", {"entity_id": "light.lamp"})

    assert response == {"light.lamp": {"timer": timer("off", 3.0), **NO_AUTO}}
    assert call_rpc.await_args_list[-2:] == [
        rpc_call(f"{component}.GetStatus", {"id": 0}),
        rpc_call(f"{component}.GetConfig", {"id": 0}),
    ]


async def test_get_status_error_raises(hass):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")
    call_rpc.side_effect = ConnectionError("device unreachable")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "get_attributes", {"entity_id": "switch.porch"})

    assert raised.value.translation_key == "targets_failed"
    assert raised.value.translation_placeholders == {"summary": "switch.porch: error"}


async def test_mixed_targets_read_in_one_call(hass):
    entry, call_rpc = shelly_device(hass, status={**BULB, "mode": "cct"})
    add_shelly_entity(hass, entry, "switch.porch", "switch:0")
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0")
    await call(hass, "turn_on_for", {"entity_id": "switch.porch", "duration": 5})

    response = await call(hass, "get_attributes", {"entity_id": ["switch.porch", "light.bulb"]})

    assert response == {
        "switch.porch": {"timer": timer("off", 3.0), **NO_AUTO},  # a Switch reads no light attributes
        "light.bulb": {"brightness": 40, "color_temp_kelvin": 4000, **NO_AUTO},
    }


@pytest.mark.parametrize("key", ["switch:0", "rgbcct:0"])
async def test_settings_set_by_the_actions_are_reported(hass, key):
    entity_id = "light.porch"
    entry, _ = shelly_device(hass, status={**BULB, "mode": "cct"})
    add_shelly_entity(hass, entry, entity_id, key)
    await call(hass, "set_auto_off", {"entity_id": entity_id, "duration": 90})

    response = await call(hass, "get_attributes", {"entity_id": entity_id})

    assert response[entity_id]["auto_off"] == {"duration": 90.0}
    assert response[entity_id]["auto_on"] is None


def test_config_row():
    config = {"auto_on": True, "auto_on_delay": 12.5, "auto_off": False, "auto_off_delay": 60.0, "name": None}

    assert config_row(config) == {"auto_on": {"duration": 12.5}, "auto_off": None}


def test_config_row_leaves_out_settings_the_component_lacks():
    assert config_row({"name": None}) == {}


async def test_get_config_error_keeps_the_status_row(hass):
    entry, call_rpc = shelly_device(hass, status={**BULB, "mode": "cct"})
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:0")
    failing(call_rpc, "GetConfig")

    response = await call(hass, "get_attributes", {"entity_id": "light.bulb"})

    # No auto_off or auto_on key: unknown, which a None (disabled) would misstate.
    assert response == {"light.bulb": {"brightness": 40, "color_temp_kelvin": 4000}}
