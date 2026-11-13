"""ZHA stop: level Stop to each lit light, StopMoveStep where a color move of ours runs, the halt recorded, and a
refresh at once."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.transition import BRIGHTNESS, SATURATION
from custom_components.deviceside.integrations.zha.fade import hue_moves, transition_cache

from .conftest import IEEE, SENT, A, B, bulb, call_as, sent
from ...conftest import advance, call, result, wall_clock_now

DISPATCHER = "custom_components.deviceside.core.dispatcher"

pytestmark = pytest.mark.usefixtures("setup_production", "clock")

LEVEL_STOP = (0x0008, 0x03, {})
STOP_MOVE_STEP = (0x0300, 0x47, {"options_mask": 0, "options_override": 0})


@pytest.fixture(autouse=True)
def zcl_reads(bulbs):
    return bulbs


async def test_a_lit_light_gets_level_stop_and_a_refresh_at_once(hass, commands, refreshes):
    bulb(hass)

    assert await call(hass, "stop", {"entity_id": "light.bulb"}) == {"light.bulb": SENT}
    assert sent(commands) == [LEVEL_STOP]
    assert [refresh.data for refresh in refreshes] == [{"entity_id": "light.bulb"}]


async def test_a_brightness_move_halts_where_it_is_predicted(hass, commands, clock):
    bulb(hass)
    await call(hass, "raise_brightness", {"entity_id": "light.bulb"})
    clock.now += 1

    await call(hass, "stop", {"entity_id": "light.bulb"})

    assert sent(commands)[1:] == [LEVEL_STOP]
    cache = transition_cache(hass)
    assert cache.halted("light.bulb", BRIGHTNESS)
    assert cache.value("light.bulb", BRIGHTNESS, 0) == pytest.approx(80)


async def test_a_saturation_move_also_gets_stop_move_step(hass, commands, clock):
    bulb(hass)
    await call(hass, "raise_saturation", {"entity_id": "light.bulb"})
    clock.now += 1

    await call(hass, "stop", {"entity_id": "light.bulb"})

    assert sent(commands)[1:] == [STOP_MOVE_STEP, LEVEL_STOP]
    assert transition_cache(hass).value("light.bulb", SATURATION, 0) == pytest.approx(80)


async def test_a_hue_cycle_gets_stop_move_step_and_ends(hass, commands):
    bulb(hass)
    await call(hass, "raise_hue", {"entity_id": "light.bulb"})

    await call(hass, "stop", {"entity_id": "light.bulb"})

    assert sent(commands)[1:] == [STOP_MOVE_STEP, LEVEL_STOP]
    assert hue_moves(hass) == set()


async def test_no_stop_move_step_for_a_light_without_color(hass, commands):
    bulb(hass, modes=["color_temp"])
    hue_moves(hass).add("light.bulb")

    await call(hass, "stop", {"entity_id": "light.bulb"})

    assert sent(commands) == [LEVEL_STOP]


async def test_a_halted_soft_off_keeps_the_light_on(hass, commands, clock):
    """The stop cancels the restore: the light stays on at the halted level, as on Hue."""
    bulb(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", {"entity_id": "light.bulb"})
    clock.now += 1
    hass.states.async_set("light.bulb", "off", {"supported_color_modes": ["color_temp", "xy"]})  # reported early

    assert await call(hass, "stop", {"entity_id": "light.bulb"}) == {"light.bulb": SENT}
    await advance(hass, start, 10)

    assert sent(commands)[1:] == [LEVEL_STOP]
    assert transition_cache(hass).value("light.bulb", BRIGHTNESS, 0) == pytest.approx(40)


async def test_cancels_each_attributes_end_refresh(hass, commands, refreshes):
    bulb(hass)
    start = wall_clock_now()
    await call(hass, "raise_brightness", {"entity_id": "light.bulb"})
    await call(hass, "raise_saturation", {"entity_id": "light.bulb"})

    await call(hass, "stop", {"entity_id": "light.bulb"})
    await advance(hass, start, 10)

    assert len(refreshes) == 1  # the stop's own


async def test_an_off_light_is_unchanged(hass, commands, refreshes):
    bulb(hass, state="off")

    assert await call(hass, "stop", {"entity_id": "light.bulb"}) == {
        "light.bulb": result("zha", "unchanged", detail="off")
    }
    assert not commands
    assert not refreshes


async def test_a_groups_lit_members_get_one_groupcast(hass, two_light_group, commands, group_commands):
    bulb(hass, "light.a", A)
    bulb(hass, "light.b", B)

    assert await call(hass, "stop", {"entity_id": "light.zha_group"}) == {"light.a": SENT, "light.b": SENT}
    assert [command.data for command in group_commands] == [
        {"group": 2, "cluster_id": 0x0008, "command": 0x03, "args": []}
    ]
    assert not commands


async def test_a_groups_hue_cycle_gets_one_stop_move_step_groupcast(hass, two_light_group, commands, group_commands):
    bulb(hass, "light.a", A)
    bulb(hass, "light.b", B)
    await call(hass, "raise_hue", {"entity_id": "light.zha_group"})

    assert await call(hass, "stop", {"entity_id": "light.zha_group"}) == {"light.a": SENT, "light.b": SENT}
    # StopMoveStep's options_mask and options_override, positional, then Level Stop.
    assert [command.data for command in group_commands[1:]] == [
        {"group": 2, "cluster_id": 0x0300, "command": 0x47, "args": [0, 0]},
        {"group": 2, "cluster_id": 0x0008, "command": 0x03, "args": []},
    ]
    assert not commands
    assert hue_moves(hass) == set()


async def test_a_group_with_an_off_member_stops_each_lit_one(hass, two_light_group, commands, group_commands):
    bulb(hass, "light.a", A)
    bulb(hass, "light.b", B, state="off")

    response = await call(hass, "stop", {"entity_id": "light.zha_group"})

    assert response == {"light.a": SENT, "light.b": result("zha", "unchanged", detail="off")}
    assert [command.data["ieee"] for command in commands] == [A]
    assert not group_commands


async def test_non_admin_caller_is_refused(hass, admin_command, hass_read_only_user, refreshes):
    bulb(hass)

    with pytest.raises(HomeAssistantError) as raised:
        await call_as(hass, hass_read_only_user, "stop", {"entity_id": "light.bulb"})

    assert raised.value.translation_placeholders["summary"] == "light.bulb: admin_required"
    assert not admin_command
    assert not refreshes


async def test_a_failed_stop_rejects_and_keeps_the_move(hass, commands, clock):
    bulb(hass)
    await call(hass, "raise_brightness", {"entity_id": "light.bulb"})

    async def fail(call: ServiceCall) -> None:
        raise HomeAssistantError("no route")

    hass.services.async_register("zha", "issue_zigbee_cluster_command", fail)
    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "stop", {"entity_id": "light.bulb"})

    assert raised.value.translation_placeholders["summary"] == "light.bulb: error"
    assert transition_cache(hass).running("light.bulb", BRIGHTNESS) is not None


async def test_a_slow_groupcast_times_out_its_members_and_keeps_the_others(hass, two_light_group, commands):
    """The run's deadline holds a groupcast as gather() holds a unicast: the lights already stopped keep SENT."""
    bulb(hass, "light.a", A)
    bulb(hass, "light.b", B)
    bulb(hass)

    async def hang(call: ServiceCall) -> None:
        await asyncio.sleep(1)

    hass.services.async_register("zha", "issue_zigbee_group_command", hang)
    with patch(f"{DISPATCHER}.ADAPTER_TIMEOUT_S", 0.05), pytest.raises(HomeAssistantError) as raised:
        await call(hass, "stop", {"entity_id": ["light.zha_group", "light.bulb"]})

    assert raised.value.translation_placeholders["summary"] == "light.a: timeout, light.b: timeout"
    assert [command.data["ieee"] for command in commands] == [IEEE]


async def test_one_light_of_three_failing_rejects_only_it(hass, commands, clock):
    c = "00:00:00:00:00:00:00:0c"
    for entity_id, ieee in (("light.a", A), ("light.b", B), ("light.c", c)):
        bulb(hass, entity_id, ieee)
    await call(hass, "raise_brightness", {"entity_id": ["light.a", "light.b", "light.c"]})
    for entity_id in ("light.a", "light.b", "light.c"):
        hue_moves(hass).add(entity_id)
    clock.now += 1

    async def fail_b(service: ServiceCall) -> None:
        if service.data["ieee"] == B:
            raise HomeAssistantError("no route")

    hass.services.async_register("zha", "issue_zigbee_cluster_command", fail_b)
    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "stop", {"entity_id": ["light.a", "light.b", "light.c"]})

    assert raised.value.translation_placeholders["summary"] == "light.b: error"
    cache = transition_cache(hass)
    assert cache.halted("light.a", BRIGHTNESS)
    assert cache.halted("light.c", BRIGHTNESS)
    assert cache.running("light.b", BRIGHTNESS) is not None  # still the move it was
    assert hue_moves(hass) == {"light.b"}
