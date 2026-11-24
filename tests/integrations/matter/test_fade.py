"""Matter raise and lower: a live read of OnOff and the level, then one MoveTo with a TransitionTime for the distance
left; the soft off's restore and what cancels it; hue as MoveHue or EnhancedMoveHue until a stop."""

import asyncio
from dataclasses import asdict
from datetime import timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.matter.fade import cancel_restore, hue_moves, soft_off_restores
from custom_components.deviceside.integrations.matter.raise_brightness import MatterRaiseBrightness
from custom_components.deviceside.integrations.matter.raise_hue import MatterRaiseHue

from ...conftest import advance, allow_labs, call, refusal, result, sent, wall_clock_now
from ...fixtures.matter import NODE_ID, add_matter_entity, light_device, matter_device

SENT = result("matter", "sent", capability="other")
BULB = {"entity_id": "light.bulb"}
# Color Control's FeatureMap: HS, and HS with EHUE.
HS, EHUE = 0x01, 0x03
pytestmark = pytest.mark.usefixtures("mock_chip", "setup_production")


@pytest.fixture(autouse=True)
def labs_on(hass, setup_production):
    """Every Matter light class is in Labs: these tests run the call with Labs on."""
    allow_labs(hass)


def light(hass, on=True, level=127, features=EHUE, saturation=127, modes=("hs",), extra=None, **node):
    """A Matter light on endpoint 1, lit at CurrentLevel 127 (50 %) and CurrentSaturation 127, registered as
    light.bulb; `features` is its Color Control FeatureMap, `extra` more of its attributes."""
    attributes = {"1/6/0": on, "1/8/0": level, "1/768/65532": features, "1/768/1": saturation} | (extra or {})
    entry, send_cmd, read_attr, node_state = light_device(hass, attributes, **node)
    add_matter_entity(
        hass, entry, "light.bulb", state="on" if on else "off", attributes={"supported_color_modes": list(modes)}
    )
    return send_cmd, read_attr, node_state


def commands(send_cmd) -> list[dict]:
    return [asdict(args.kwargs["command"]) for args in send_cmd.await_args_list]


def reads(read_attr) -> list[str]:
    return [args.kwargs["attribute_path"] for args in read_attr.await_args_list]


def level_command(name: str, level: int, tenths: int, override: int = 0) -> dict:
    return {
        "command": f"LevelControl.{name}",
        "level": level,
        "transitionTime": tenths,
        "optionsMask": override,
        "optionsOverride": override,
    }


# A light at level 1, put there with ExecuteIfOff before a raise turns it on: it fades in from the bottom.
PRESET = level_command("MoveToLevel", 1, 0, override=1)
# The soft off's restore of 50 %: MoveToLevel, never the WithOnOff variant, with ExecuteIfOff, so the light stays off.
RESTORE_50 = level_command("MoveToLevel", 127, 0, override=1)


# Brightness


async def test_a_raise_reads_the_light_then_sends_with_on_off_for_the_distance_left(hass):
    send_cmd, read_attr, _ = light(hass)

    assert await call(hass, "raise_brightness", BULB) == {"light.bulb": SENT}

    assert reads(read_attr) == ["1/6/0", "1/8/0"]  # live, not the cache
    # 50 % left at the default 5 s sweep: 2.5 s.
    assert commands(send_cmd) == [level_command("MoveToLevelWithOnOff", 254, 25)]
    kwargs = send_cmd.call_args.kwargs
    assert (kwargs["node_id"], kwargs["endpoint_id"]) == (NODE_ID, 1)


async def test_a_raise_from_off_presets_level_1_with_move_to_level_then_turns_on_with_on_off(hass):
    send_cmd, _, _ = light(hass, on=False, level=200)

    assert await call(hass, "raise_brightness", {**BULB, "limit": 60}) == {"light.bulb": SENT}

    # MoveToLevel (not WithOnOff) with ExecuteIfOff first, then the whole distance from 0: 60 % of 5 s.
    assert commands(send_cmd) == [PRESET, level_command("MoveToLevelWithOnOff", 152, 30)]


async def test_a_lower_to_a_limit_is_move_to_level(hass):
    send_cmd, _, _ = light(hass)

    assert await call(hass, "lower_brightness", {**BULB, "limit": 20}) == {"light.bulb": SENT}

    assert commands(send_cmd) == [level_command("MoveToLevel", 51, 15)]
    assert soft_off_restores(hass) == {}


@pytest.mark.parametrize(
    ("action", "data", "on", "level", "detail"),
    [
        pytest.param("lower_brightness", {}, False, 127, "off", id="lower_off"),
        pytest.param("raise_brightness", {}, True, 254, "at_limit", id="raise_at_the_top"),
        pytest.param("lower_brightness", {"limit": 50}, True, 127, "at_limit", id="lower_at_the_limit"),
    ],
)
async def test_nothing_to_make_is_unchanged_with_nothing_sent(hass, action, data, on, level, detail):
    send_cmd, _, _ = light(hass, on=on, level=level)

    response = await call(hass, action, {**BULB, **data})

    assert response == {"light.bulb": result("matter", "unchanged", capability="other", detail=detail)}
    send_cmd.assert_not_awaited()


async def test_a_sweep_time_past_the_longest_transition_is_clamped(hass):
    send_cmd, _, _ = light(hass, on=False)

    response = await call(hass, "raise_brightness", {**BULB, "sweep_time": 7000})

    assert response == {"light.bulb": {**SENT, "clamped_to": 6553.4}}
    assert commands(send_cmd)[-1]["transitionTime"] == 65534


# The soft off and its restore


async def test_a_lower_to_0_is_a_soft_off_whose_start_level_goes_back_once_it_has_run(hass):
    send_cmd, read_attr, node = light(hass)
    start = wall_clock_now()

    assert await call(hass, "lower_brightness", BULB) == {"light.bulb": SENT}
    assert commands(send_cmd) == [level_command("MoveToLevelWithOnOff", 0, 25)]
    assert node.attributes["1/6/0"] is False
    await advance(hass, start, 3.0)
    assert len(commands(send_cmd)) == 1  # not before the fade's end plus 1 s

    await advance(hass, start, 3.6)

    assert commands(send_cmd)[-1] == RESTORE_50
    assert reads(read_attr)[-1] == "1/6/0"  # it reads off first
    assert node.attributes["1/8/0"] == 127
    assert soft_off_restores(hass) == {}


async def test_a_set_attributes_brightness_inside_the_restore_window_is_not_overwritten(hass):
    send_cmd, _, node = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)

    response = await call(hass, "set_attributes", {**BULB, "brightness": 20})
    await advance(hass, start, 3.6)

    assert response["light.bulb"]["status"] == "confirmed"
    assert len(commands(send_cmd)) == 2  # the soft off, then the write: the restore sends nothing
    assert node.attributes["1/8/0"] == 51
    assert soft_off_restores(hass) == {}


async def test_a_light_turned_on_elsewhere_before_the_restore_keeps_its_level(hass):
    send_cmd, _, node = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    node.attributes["1/6/0"] = True

    await advance(hass, start, 3.6)

    assert len(commands(send_cmd)) == 1


@pytest.mark.parametrize(
    ("service", "data"),
    [
        pytest.param("turn_on", {"brightness_pct": 40}, id="turn_on"),
        pytest.param("turn_off", {}, id="turn_off"),
    ],
)
async def test_a_light_call_from_ha_cancels_the_restore(hass, service, data):
    send_cmd, _, _ = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    async_mock_service(hass, "light", service)

    await hass.services.async_call("light", service, {**BULB, **data}, blocking=True)
    await advance(hass, start, 3.6)

    assert commands(send_cmd) == [level_command("MoveToLevelWithOnOff", 0, 25)]
    assert soft_off_restores(hass) == {}


async def test_a_light_call_from_ha_to_every_light_cancels_the_restore(hass):
    send_cmd, _, _ = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    async_mock_service(hass, "light", "turn_on")

    await hass.services.async_call("light", "turn_on", {"entity_id": "all"}, blocking=True)
    await advance(hass, start, 3.6)

    assert len(commands(send_cmd)) == 1


async def test_a_light_call_from_ha_during_the_soft_off_send_cancels_its_restore(hass):
    send_cmd, _, _ = light(hass)
    start = wall_clock_now()
    async_mock_service(hass, "light", "turn_off")
    apply = send_cmd.side_effect

    async def off_from_ha_in_flight(node_id, endpoint_id, command):
        apply(node_id, endpoint_id, command)
        await hass.services.async_call("light", "turn_off", BULB, blocking=True)

    send_cmd.side_effect = off_from_ha_in_flight

    await call(hass, "lower_brightness", BULB)
    await advance(hass, start, 3.6)

    assert len(commands(send_cmd)) == 1
    assert soft_off_restores(hass) == {}


async def test_a_later_move_cancels_the_restore(hass):
    send_cmd, _, _ = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)

    # The light is off at level 1 now: the raise presets and turns it on.
    await call(hass, "raise_brightness", {**BULB, "limit": 30})
    await advance(hass, start, 3.6)

    assert commands(send_cmd) == [
        level_command("MoveToLevelWithOnOff", 0, 25),
        PRESET,
        level_command("MoveToLevelWithOnOff", 76, 15),
    ]
    assert soft_off_restores(hass) == {}


async def test_the_cancel_hook_drops_the_restore(hass):
    """What stop calls (plan Decision 10): a halted soft off stays on at the halt level."""
    send_cmd, _, _ = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)

    cancel_restore(hass, "light.bulb")
    await advance(hass, start, 3.6)

    assert len(commands(send_cmd)) == 1


async def test_a_second_soft_off_restores_its_own_start(hass):
    """A soft off while one runs replaces its restore: the light is still lit, and the start is where it is now."""
    send_cmd, _, node = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    node.attributes.update({"1/6/0": True, "1/8/0": 64})  # still fading, at 25 %

    await call(hass, "lower_brightness", BULB)
    await advance(hass, start, 3.6)

    assert commands(send_cmd)[1:] == [
        level_command("MoveToLevelWithOnOff", 0, 13),
        level_command("MoveToLevel", 64, 0, override=1),
    ]


async def test_a_move_whose_send_fails_puts_the_earlier_restore_back(hass):
    send_cmd, _, node = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    node.attributes.update({"1/6/0": True, "1/8/0": 64})
    apply = send_cmd.side_effect

    def fail_once(node_id, endpoint_id, command):
        if send_cmd.await_count == 2:
            raise ConnectionError("device unreachable")
        return apply(node_id, endpoint_id, command)

    send_cmd.side_effect = fail_once

    with pytest.raises(HomeAssistantError):
        await call(hass, "lower_brightness", {**BULB, "limit": 10})
    node.attributes["1/6/0"] = False
    await advance(hass, start, 3.6)

    assert commands(send_cmd)[-1] == RESTORE_50


async def test_a_failed_restore_is_logged_and_the_light_stays_off(hass, caplog):
    send_cmd, _, node = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    node.refused.add("1/6/0")

    await advance(hass, start, 3.6)

    assert len(commands(send_cmd)) == 1
    assert "matter couldn't put back light.bulb's level after a soft off" in caplog.text


async def test_an_ha_light_call_during_the_restores_own_read_leaves_the_light_alone(hass):
    """The call replaces our fade: the restore's MoveToLevel would jump a light it turns on to the old level."""
    send_cmd, read_attr, _ = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    async_mock_service(hass, "light", "turn_on")
    read = read_attr.side_effect

    async def turn_on_during_the_read(node_id, attribute_path):
        await hass.services.async_call("light", "turn_on", BULB, blocking=True)
        return read(node_id, attribute_path)

    read_attr.side_effect = turn_on_during_the_read
    await advance(hass, start, 3.6)

    assert commands(send_cmd) == [level_command("MoveToLevelWithOnOff", 0, 25)]
    assert soft_off_restores(hass) == {}


async def test_a_move_arriving_during_the_restores_own_read_goes_out_after_it(hass):
    """The light's lock holds the move until the restore is done: the restore reaches the light while it is still off,
    and nothing of it follows the move's commands."""
    send_cmd, read_attr, _ = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    read = read_attr.side_effect
    moves = []

    def raise_during_the_read(node_id, attribute_path):
        if not moves:
            moves.append(hass.async_create_task(call(hass, "raise_brightness", {**BULB, "limit": 30})))
        return read(node_id, attribute_path)

    read_attr.side_effect = raise_during_the_read
    await advance(hass, start, 3.6)
    await moves[0]

    assert commands(send_cmd) == [
        level_command("MoveToLevelWithOnOff", 0, 25),
        RESTORE_50,
        PRESET,
        level_command("MoveToLevelWithOnOff", 76, 15),
    ]


async def test_a_restore_due_while_a_move_holds_the_light_sends_nothing(hass):
    """A move between its read and its send holds the light's lock: the restore waits, then finds the move took it."""
    send_cmd, read_attr, _ = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    read = read_attr.side_effect
    fired = []

    async def restore_due_during_the_moves_read(node_id, attribute_path):
        if not fired:
            fired.append(True)
            # The restore's timer fires and its job starts, waiting on the lock (not awaited: the move holds it).
            async_fire_time_changed(hass, start + timedelta(seconds=3.6))
            for _ in range(5):
                await asyncio.sleep(0)
        return read(node_id, attribute_path)

    read_attr.side_effect = restore_due_during_the_moves_read
    await call(hass, "raise_brightness", {**BULB, "limit": 30})
    await hass.async_block_till_done()

    assert commands(send_cmd) == [
        level_command("MoveToLevelWithOnOff", 0, 25),
        PRESET,
        level_command("MoveToLevelWithOnOff", 76, 15),
    ]
    assert soft_off_restores(hass) == {}


# Saturation


async def test_saturation_is_move_to_saturation_on_a_lit_light(hass):
    send_cmd, read_attr, _ = light(hass, saturation=127)

    assert await call(hass, "raise_saturation", {**BULB, "limit": 80}) == {"light.bulb": SENT}

    assert reads(read_attr) == ["1/6/0", "1/768/1"]
    assert commands(send_cmd) == [
        {
            "command": "ColorControl.MoveToSaturation",
            "saturation": 203,
            "transitionTime": 15,
            "optionsMask": 0,
            "optionsOverride": 0,
        }
    ]


async def test_saturation_on_an_off_light_is_unchanged_with_off(hass):
    send_cmd, _, _ = light(hass, on=False)

    response = await call(hass, "raise_saturation", BULB)

    assert response == {"light.bulb": result("matter", "unchanged", capability="other", detail="off")}
    send_cmd.assert_not_awaited()


@pytest.mark.parametrize("action", ["raise_saturation", "raise_hue"])
async def test_a_light_without_the_hs_feature_drops_saturation_and_hue(hass, action):
    """An xy-only light: HA shows it in color, but it has no hue or saturation to move."""
    send_cmd, read_attr, _ = light(hass, features=0x08, modes=("xy",))

    response = await call(hass, action, BULB)

    assert response == {"light.bulb": result("matter", "unchanged", capability="other", detail="fields_dropped")}
    send_cmd.assert_not_awaited()
    read_attr.assert_not_awaited()


async def test_a_saturation_move_ends_the_hue_cycle(hass):
    light(hass)
    await call(hass, "raise_hue", BULB)

    await call(hass, "lower_saturation", BULB)

    assert hue_moves(hass) == set()


# Hue


@pytest.mark.parametrize(
    ("action", "features", "data", "command", "rate", "mode", "clamped_to"),
    [
        pytest.param("raise_hue", EHUE, {}, "EnhancedMoveHue", 13107, 1, None, id="enhanced_up"),
        pytest.param("lower_hue", EHUE, {}, "EnhancedMoveHue", 13107, 3, None, id="enhanced_down"),
        pytest.param("raise_hue", HS, {}, "MoveHue", 51, 1, None, id="move_hue"),
        pytest.param("raise_hue", HS, {"sweep_time": 1000}, "MoveHue", 1, 1, 254, id="move_hue_clamped"),
        pytest.param("raise_hue", EHUE, {"sweep_time": 0.5}, "EnhancedMoveHue", 65535, 1, 1.0, id="enhanced_clamped"),
    ],
)
async def test_hue_cycles_with_enhanced_move_hue_where_the_light_has_ehue_else_move_hue(
    hass, action, features, data, command, rate, mode, clamped_to
):
    send_cmd, read_attr, _ = light(hass, features=features)

    response = await call(hass, action, {**BULB, **data})

    expected = SENT if clamped_to is None else {**SENT, "clamped_to": clamped_to}
    assert response == {"light.bulb": expected}
    assert reads(read_attr) == ["1/6/0"]
    assert commands(send_cmd) == [
        {
            "command": f"ColorControl.{command}",
            "moveMode": mode,
            "rate": rate,
            "optionsMask": 0,
            "optionsOverride": 0,
        }
    ]
    assert hue_moves(hass) == {"light.bulb"}


async def test_hue_on_an_off_light_is_unchanged_with_off(hass):
    send_cmd, _, _ = light(hass, on=False)

    response = await call(hass, "raise_hue", BULB)

    assert response == {"light.bulb": result("matter", "unchanged", capability="other", detail="off")}
    send_cmd.assert_not_awaited()
    assert hue_moves(hass) == set()


@pytest.mark.parametrize(
    ("service", "data", "cycling"),
    [
        pytest.param("turn_on", {"brightness_pct": 40}, {"light.bulb"}, id="brightness_only"),
        pytest.param("turn_on", {"hs_color": [30, 80]}, set(), id="color"),
        pytest.param("turn_off", {}, set(), id="off"),
    ],
)
async def test_a_light_call_from_ha_that_sets_a_color_ends_the_hue_cycle(hass, service, data, cycling):
    light(hass)
    await call(hass, "raise_hue", BULB)
    async_mock_service(hass, "light", service)

    await hass.services.async_call("light", service, {**BULB, **data}, blocking=True)

    assert hue_moves(hass) == cycling


# Addressing, classes and Labs


@pytest.mark.parametrize("action", ["raise_brightness", "raise_saturation", "raise_hue"])
async def test_a_light_with_no_level_control_is_not_dimmable(hass, action):
    entry, send_cmd, _ = matter_device(hass, vendor_id=4874, product_id=80)  # OnOff only: no 1/8/0 in its cache
    add_matter_entity(hass, entry, "light.bulb", state="on", attributes={"supported_color_modes": ["hs"]})

    assert await refusal(hass, action, BULB) == "not_dimmable"
    send_cmd.assert_not_awaited()


async def test_a_light_without_the_lighting_feature_is_refused(hass):
    entry, _, _, _ = light_device(hass, feature_map=0x0000)
    add_matter_entity(hass, entry, "light.bulb", state="on", attributes={"supported_color_modes": ["brightness"]})

    assert await refusal(hass, "raise_brightness", BULB) == "no_lt_feature"


async def test_a_multi_endpoint_light_runs_in_labs(hass):
    send_cmd, _, _ = light(hass, extra={"2/6/65532": 1})

    response = await call(hass, "raise_brightness", BULB)

    assert response["light.bulb"]["capability"] == "multi_endpoint"
    send_cmd.assert_awaited_once()


@pytest.mark.parametrize(
    "node",
    [
        {"vendor_id": 0xFFF1},
        {"vendor_id": 4757, "attributes": {"1/29/0": [{"0": 14, "1": 1}], "2/29/0": [{"0": 19, "1": 1}]}},
    ],
    ids=["uncertified", "bridged"],
)
@pytest.mark.parametrize("action", ["raise_brightness", "lower_saturation", "lower_hue"])
async def test_uncertified_and_bridged_lights_are_not_built_even_with_labs_on(hass, node, action):
    entry, send_cmd, _, _ = light_device(hass, **node)
    add_matter_entity(hass, entry, "light.bulb", state="on", attributes={"supported_color_modes": ["hs"]})

    assert await refusal(hass, action, BULB) == "not_built"
    send_cmd.assert_not_awaited()


@pytest.mark.parametrize("action", ["raise_brightness", "raise_saturation", "raise_hue"])
async def test_labs_off_refuses_other(hass, action):
    allow_labs(hass, False)
    send_cmd, _, _ = light(hass)

    assert await refusal(hass, action, BULB) == "labs_off"
    send_cmd.assert_not_awaited()


@pytest.mark.parametrize("adapter", [MatterRaiseBrightness, MatterRaiseHue])
def test_the_light_domain_and_the_two_classes_are_labs(adapter):
    scope = adapter.scope
    assert scope.capabilities == {"other": Level.LABS, "multi_endpoint": Level.LABS}
    assert scope.level("light", ["other"]) is Level.LABS
    assert not scope.not_built


async def test_a_send_that_fails_rejects_the_light(hass):
    send_cmd, _, _ = light(hass)
    send_cmd.side_effect = ConnectionError("device unreachable")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "raise_hue", BULB)

    assert raised.value.translation_placeholders == {"summary": "light.bulb: error"}
    assert hue_moves(hass) == set()


async def test_each_command_is_logged_without_the_node(hass, wire):
    light(hass, on=False)

    await call(hass, "raise_brightness", BULB)

    assert sent(wire) == [
        "light.bulb: sending matter LevelControl.MoveToLevel "
        "{'level': 1, 'transitionTime': 0, 'optionsMask': 1, 'optionsOverride': 1}",
        "light.bulb: sending matter LevelControl.MoveToLevelWithOnOff "
        "{'level': 254, 'transitionTime': 50, 'optionsMask': 0, 'optionsOverride': 0}",
    ]
