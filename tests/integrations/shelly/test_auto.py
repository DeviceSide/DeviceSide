"""Shelly set_auto_off / set_auto_on / clear_auto_off / clear_auto_on: a GetConfig, a SetConfig only on a difference,
and a GetConfig read-back."""

from unittest.mock import call as rpc_call

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.shelly.auto import ShellyClearAuto, ShellySetAuto
from custom_components.deviceside.integrations.shelly.rpc import AUTO_DELAY_LIMITS

from ...conftest import call, refusal, result
from ...fixtures.shelly import OTHER_LIGHT_COMPONENTS, add_shelly_entity, failing, shelly_device

pytestmark = pytest.mark.usefixtures("setup_production")

CONFIRMED = {"status": "confirmed", "integration": "shelly"}
WHICH = ["off", "on"]


def set_configs(call_rpc) -> list:
    return [args for args in call_rpc.await_args_list if args.args[0].endswith(".SetConfig")]


@pytest.mark.parametrize("which", WHICH)
async def test_set_writes_each_capability_in_scope(hass, which):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")
    add_shelly_entity(hass, entry, "light.lamp", "switch:1")
    add_shelly_entity(hass, entry, "light.bulb", "rgbcct:2")

    response = await call(
        hass, f"set_auto_{which}", {"entity_id": ["switch.gate", "light.lamp", "light.bulb"], "duration": 5}
    )

    assert response == {"switch.gate": CONFIRMED, "light.lamp": CONFIRMED, "light.bulb": CONFIRMED}
    config = {f"auto_{which}": True, f"auto_{which}_delay": 5.0}
    assert sorted(set_configs(call_rpc), key=lambda args: args.args[1]["id"]) == [
        rpc_call("Switch.SetConfig", {"id": 0, "config": config}),
        rpc_call("Switch.SetConfig", {"id": 1, "config": config}),
        rpc_call("RGBCCT.SetConfig", {"id": 2, "config": config}),
    ]


@pytest.mark.parametrize("which", WHICH)
async def test_set_to_the_held_delay_sends_nothing(hass, which):
    entry, call_rpc = shelly_device(hass, config={f"auto_{which}": True, f"auto_{which}_delay": 5.004})
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")

    response = await call(hass, f"set_auto_{which}", {"entity_id": "switch.gate", "duration": 5})

    assert response == {"switch.gate": result("shelly", "unchanged", detail="already_set")}
    assert not set_configs(call_rpc)


async def test_set_with_another_delay_rewrites_it(hass):
    entry, call_rpc = shelly_device(hass, config={"auto_off": True, "auto_off_delay": 60.0})
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")

    assert await call(hass, "set_auto_off", {"entity_id": "switch.gate", "duration": 2.5}) == {"switch.gate": CONFIRMED}
    assert set_configs(call_rpc) == [
        rpc_call("Switch.SetConfig", {"id": 0, "config": {"auto_off": True, "auto_off_delay": 2.5}})
    ]


@pytest.mark.parametrize("which", WHICH)
async def test_clear_disables_without_touching_the_delay(hass, which):
    entry, call_rpc = shelly_device(hass, config={f"auto_{which}": True, f"auto_{which}_delay": 5.0})
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")

    assert await call(hass, f"clear_auto_{which}", {"entity_id": "switch.gate"}) == {"switch.gate": CONFIRMED}
    assert set_configs(call_rpc) == [rpc_call("Switch.SetConfig", {"id": 0, "config": {f"auto_{which}": False}})]


@pytest.mark.parametrize("which", WHICH)
async def test_clear_when_already_clear_sends_nothing(hass, which):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")

    response = await call(hass, f"clear_auto_{which}", {"entity_id": "switch.gate"})

    assert response == {"switch.gate": result("shelly", "unchanged", detail="already_clear")}
    assert not set_configs(call_rpc)


async def test_clear_leaves_the_other_setting_alone(hass):
    entry, call_rpc = shelly_device(hass, config={"auto_off": True, "auto_on": True})
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")

    await call(hass, "clear_auto_off", {"entity_id": "switch.gate"})

    assert await call(hass, "get_attributes", {"entity_id": "switch.gate"}) == {
        "switch.gate": {"auto_off": None, "auto_on": {"duration": 60.0}}
    }


async def test_a_setting_the_read_back_does_not_show_is_sent_only(hass):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")
    respond = call_rpc.side_effect

    async def ignores_set_config(method, params):
        return {"restart_required": False} if method.endswith(".SetConfig") else respond(method, params)

    call_rpc.side_effect = ignores_set_config

    assert await call(hass, "set_auto_off", {"entity_id": "switch.gate", "duration": 5}) == {
        "switch.gate": {"status": "sent", "integration": "shelly", "detail": "config_not_reported"}
    }


async def test_a_failed_read_back_is_sent_only(hass):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")
    failing(call_rpc, "GetConfig", after=1)

    assert await call(hass, "set_auto_on", {"entity_id": "switch.gate", "duration": 5}) == {
        "switch.gate": {"status": "sent", "integration": "shelly", "detail": "readback_failed"}
    }
    assert len(set_configs(call_rpc)) == 1


@pytest.mark.parametrize("verb", ["GetConfig", "SetConfig"])
async def test_a_device_error_before_the_write_lands_raises(hass, verb):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")
    failing(call_rpc, verb)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "set_auto_off", {"entity_id": "switch.gate", "duration": 5})

    assert raised.value.translation_key == "targets_failed"


async def test_a_delay_over_the_ceiling_is_clamped(hass):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")
    ceiling = AUTO_DELAY_LIMITS.max_s

    response = await call(hass, "set_auto_off", {"entity_id": "switch.gate", "duration": {"days": 8}})

    assert response == {"switch.gate": {**CONFIRMED, "clamped_to": ceiling}}
    assert set_configs(call_rpc)[0].args[1]["config"]["auto_off_delay"] == ceiling


@pytest.mark.parametrize("which", WHICH)
async def test_zero_duration_is_rejected(hass, which):
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.gate", "switch:0")

    with pytest.raises(ServiceValidationError) as raised:
        await call(hass, f"set_auto_{which}", {"entity_id": "switch.gate", "duration": 0})

    assert raised.value.translation_key == "invalid_duration"
    assert not call_rpc.await_args_list


@pytest.mark.parametrize("action", ["set_auto_off", "set_auto_on", "clear_auto_off", "clear_auto_on"])
async def test_out_of_scope_targets_are_refused(hass, action):
    gen1, _ = shelly_device(hass, gen1=True, mac="112233445566")
    add_shelly_entity(hass, gen1, "switch.old_relay", "relay_0")
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, "switch.child_lock", "boolean:200-boolean_child_lock")
    data = {"duration": 5} if action.startswith("set_") else {}

    assert await refusal(hass, action, {"entity_id": "switch.old_relay", **data}) == "gen1_unsupported"
    assert await refusal(hass, action, {"entity_id": "switch.child_lock", **data}) == "not_addressable"
    assert not call_rpc.await_args_list


@pytest.mark.parametrize("which", WHICH)
@pytest.mark.parametrize(("key", "component"), [*OTHER_LIGHT_COMPONENTS, ("rgbcct:0", "RGBCCT")])
async def test_documented_components_take_the_same_set_config(hass, which, key, component):
    entry, call_rpc = shelly_device(hass, config={f"auto_{which}": True, f"auto_{which}_delay": 60.0})
    add_shelly_entity(hass, entry, "light.strip", key)

    assert await call(hass, f"set_auto_{which}", {"entity_id": "light.strip", "duration": 5}) == {
        "light.strip": CONFIRMED
    }
    assert await call(hass, f"clear_auto_{which}", {"entity_id": "light.strip"}) == {"light.strip": CONFIRMED}
    assert set_configs(call_rpc) == [
        rpc_call(f"{component}.SetConfig", {"id": 0, "config": {f"auto_{which}": True, f"auto_{which}_delay": 5.0}}),
        rpc_call(f"{component}.SetConfig", {"id": 0, "config": {f"auto_{which}": False}}),
    ]


def test_the_auto_adapters_prove_switch_and_document_the_light_components():
    """The rig tests auto-off/on on a relay, which clears the flag; every light component, RGBCCT included, rides it
    as Documented."""
    for adapter in (ShellySetAuto, ShellyClearAuto):
        assert not adapter.scope.experimental
        assert adapter.scope.capabilities == {
            "Switch": Level.VERIFIED,
            **dict.fromkeys(("Light", "CCT", "RGB", "RGBW", "RGBCCT"), Level.DOCUMENTED),
        }
