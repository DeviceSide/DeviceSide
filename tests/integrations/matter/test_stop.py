"""Matter stop: Level Stop and StopMoveStep to each lit light, the soft-off restore and hue cycle it ends, and the two
reads that say where the light halted."""

import asyncio
from dataclasses import asdict

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.matter import stop as adapter
from custom_components.deviceside.integrations.matter.fade import hue_moves, soft_off_restores
from custom_components.deviceside.integrations.matter.stop import MatterStop

from ...conftest import advance, allow_labs, call, refusal, result, sent, wall_clock_now
from ...fixtures.matter import add_matter_entity, light_device, matter_device

CONFIRMED = result("matter", "confirmed", capability="other")
BULB = {"entity_id": "light.bulb"}
LEVEL_STOP = {"command": "LevelControl.Stop", "optionsMask": 0, "optionsOverride": 0}
COLOR_STOP = {"command": "ColorControl.StopMoveStep", "optionsMask": 0, "optionsOverride": 0}
# Color Control's FeatureMap: HS, and xy only.
HS, XY = 0x01, 0x08
pytestmark = pytest.mark.usefixtures("mock_chip", "setup_production")


@pytest.fixture(autouse=True)
def labs_on(hass, setup_production):
    allow_labs(hass)


@pytest.fixture(autouse=True)
def no_read_gap(monkeypatch):
    """The gap between the two reads, off so tests don't sleep; the test of it sets its own."""
    monkeypatch.setattr(adapter, "READ_GAP_S", 0.0)


def light(hass, on=True, features=HS, **node):
    """A Matter light on endpoint 1 at CurrentLevel 127, registered as light.bulb; `features` is its Color Control
    FeatureMap, None for a light with no Color Control server."""
    attributes = {"1/6/0": on, "1/8/0": 127}
    if features is not None:
        attributes |= {"1/768/65532": features, "1/768/1": 127, "1/768/0": 10}
    entry, send_cmd, read_attr, node_state = light_device(hass, attributes, **node)
    add_matter_entity(hass, entry, "light.bulb", state="on" if on else "off")
    return send_cmd, read_attr, node_state


def commands(send_cmd) -> list[dict]:
    return [asdict(args.kwargs["command"]) for args in send_cmd.await_args_list]


def reads(read_attr) -> list[str]:
    return [args.kwargs["attribute_path"] for args in read_attr.await_args_list]


async def test_a_lit_light_with_no_color_server_gets_level_stop_alone(hass):
    send_cmd, read_attr, _ = light(hass, features=None)

    assert await call(hass, "stop", BULB) == {"light.bulb": CONFIRMED}

    assert commands(send_cmd) == [LEVEL_STOP]
    # OnOff after the stop, then two reads of OnOff and CurrentLevel.
    assert reads(read_attr) == ["1/6/0", "1/6/0", "1/8/0", "1/6/0", "1/8/0"]
    kwargs = send_cmd.call_args.kwargs
    assert kwargs["endpoint_id"] == 1


async def test_a_light_with_a_color_server_also_gets_stop_move_step_and_reads_saturation_and_hue(hass):
    send_cmd, read_attr, _ = light(hass)

    assert await call(hass, "stop", BULB) == {"light.bulb": CONFIRMED}

    assert commands(send_cmd) == [LEVEL_STOP, COLOR_STOP]
    assert reads(read_attr)[1:5] == ["1/6/0", "1/8/0", "1/768/1", "1/768/0"]


async def test_a_light_without_the_hs_feature_gets_stop_move_step_but_reads_the_level_alone(hass):
    send_cmd, read_attr, _ = light(hass, features=XY)

    assert await call(hass, "stop", BULB) == {"light.bulb": CONFIRMED}

    assert commands(send_cmd) == [LEVEL_STOP, COLOR_STOP]
    assert set(reads(read_attr)) == {"1/6/0", "1/8/0"}


async def test_an_off_light_is_unchanged_with_off_and_read_once(hass):
    send_cmd, read_attr, _ = light(hass, on=False)

    response = await call(hass, "stop", BULB)

    assert response == {"light.bulb": result("matter", "unchanged", capability="other", detail="off")}
    assert commands(send_cmd) == [LEVEL_STOP, COLOR_STOP]
    assert reads(read_attr) == ["1/6/0"]


async def test_the_stop_goes_out_before_the_onoff_read(hass):
    send_cmd, read_attr, _ = light(hass)
    read = read_attr.side_effect
    sent_before_reads = []

    def note_the_sends(node_id, attribute_path):
        sent_before_reads.append(send_cmd.await_count)
        return read(node_id, attribute_path)

    read_attr.side_effect = note_the_sends

    await call(hass, "stop", BULB)

    assert sent_before_reads[0] == 2


async def test_a_soft_off_that_finished_before_the_stop_still_restores(hass):
    send_cmd, _, node = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    node.attributes["1/6/0"] = False  # the fade reached 0: the light is off, its restore pending
    node.attributes["1/8/0"] = 1

    response = await call(hass, "stop", BULB)
    await advance(hass, start, 3.6)

    assert response == {"light.bulb": result("matter", "unchanged", capability="other", detail="off")}
    assert [command["command"] for command in commands(send_cmd)][-1] == "LevelControl.MoveToLevel"
    assert soft_off_restores(hass) == {}


async def test_a_light_that_reads_off_after_the_stop_is_unchanged_with_off(hass):
    send_cmd, read_attr, node = light(hass)
    read = read_attr.side_effect

    def off_after_the_stop(node_id, attribute_path):
        if send_cmd.await_count:
            node.attributes["1/6/0"] = False
        return read(node_id, attribute_path)

    read_attr.side_effect = off_after_the_stop

    response = await call(hass, "stop", BULB)

    assert response == {"light.bulb": result("matter", "unchanged", capability="other", detail="off")}


@pytest.mark.parametrize(
    ("path", "moves"),
    [("1/8/0", "level"), ("1/768/1", "saturation"), ("1/768/0", "hue")],
)
async def test_a_light_whose_reads_differ_is_sent_with_still_fading(hass, path, moves):
    _, read_attr, node = light(hass)
    read = read_attr.side_effect
    seen = []

    def keeps_moving(node_id, attribute_path):
        if attribute_path == path:
            seen.append(attribute_path)
            node.attributes[path] = 100 + len(seen)
        return read(node_id, attribute_path)

    read_attr.side_effect = keeps_moving

    response = await call(hass, "stop", BULB)

    assert response == {"light.bulb": result("matter", "sent", capability="other", detail="still_fading")}


async def test_a_failed_read_after_the_stop_is_sent_with_readback_failed(hass):
    send_cmd, read_attr, node = light(hass)
    read = read_attr.side_effect

    def fails_after_the_stop(node_id, attribute_path):
        if send_cmd.await_count and attribute_path == "1/8/0":
            raise ConnectionError("lost connection")
        return read(node_id, attribute_path)

    read_attr.side_effect = fails_after_the_stop

    response = await call(hass, "stop", BULB)

    assert response == {"light.bulb": result("matter", "sent", capability="other", detail="readback_failed")}
    assert commands(send_cmd) == [LEVEL_STOP, COLOR_STOP]


async def test_the_two_reads_are_one_gap_apart_outside_every_slot(hass, monkeypatch):
    monkeypatch.setattr(adapter, "READ_GAP_S", 0.0123)
    light(hass)
    waits = []
    real_sleep = asyncio.sleep

    async def sleep(delay, *args, **kwargs):
        if delay == 0.0123:
            waits.append(delay)
        return await real_sleep(delay, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", sleep)

    await call(hass, "stop", BULB)

    assert waits == [0.0123]


async def test_a_failed_stop_rejects_the_light(hass):
    send_cmd, _, _ = light(hass)
    send_cmd.side_effect = ConnectionError("device unreachable")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "stop", BULB)

    assert raised.value.translation_placeholders == {"summary": "light.bulb: error"}


# What a stop ends


async def test_a_halted_soft_off_stays_on_and_its_restore_is_cancelled(hass):
    send_cmd, _, node = light(hass)
    start = wall_clock_now()
    await call(hass, "lower_brightness", BULB)
    node.attributes["1/6/0"] = True  # the fade is still running: the light reads on, at the halt level
    node.attributes["1/8/0"] = 64

    assert await call(hass, "stop", BULB) == {"light.bulb": CONFIRMED}
    node.attributes["1/6/0"] = False  # (what an uncancelled restore would see)
    await advance(hass, start, 3.6)

    assert [command["command"] for command in commands(send_cmd)] == [
        "LevelControl.MoveToLevelWithOnOff",
        "LevelControl.Stop",
        "ColorControl.StopMoveStep",
    ]
    assert soft_off_restores(hass) == {}


async def test_a_stop_ends_the_hue_cycle(hass):
    light(hass)
    await call(hass, "raise_hue", BULB)
    assert hue_moves(hass) == {"light.bulb"}

    await call(hass, "stop", BULB)

    assert hue_moves(hass) == set()


async def test_a_stop_that_finds_the_light_off_still_ends_the_hue_cycle(hass):
    _, _, node = light(hass)
    await call(hass, "raise_hue", BULB)
    node.attributes["1/6/0"] = False  # turned off from outside HA
    assert hue_moves(hass) == {"light.bulb"}

    await call(hass, "stop", BULB)

    assert hue_moves(hass) == set()


async def test_a_stop_during_a_moves_read_goes_out_after_the_move(hass):
    """The light's lock holds the stop until the move has sent: the stop halts the fade, not ahead of it."""
    send_cmd, read_attr, _ = light(hass)
    read = read_attr.side_effect
    stops = []

    def stop_during_the_read(node_id, attribute_path):
        if not stops:
            stops.append(hass.async_create_task(call(hass, "stop", BULB)))
        return read(node_id, attribute_path)

    read_attr.side_effect = stop_during_the_read

    await call(hass, "raise_brightness", {**BULB, "limit": 90})
    await stops[0]

    assert [command["command"] for command in commands(send_cmd)] == [
        "LevelControl.MoveToLevelWithOnOff",
        "LevelControl.Stop",
        "ColorControl.StopMoveStep",
    ]


# Addressing, classes and Labs


async def test_a_light_with_no_level_control_is_not_dimmable(hass):
    entry, send_cmd, _ = matter_device(hass, vendor_id=4874, product_id=80)  # OnOff only
    add_matter_entity(hass, entry, "light.bulb", state="on")

    assert await refusal(hass, "stop", BULB) == "not_dimmable"
    send_cmd.assert_not_awaited()


async def test_a_multi_endpoint_light_runs_in_labs(hass):
    entry, _, _, _ = light_device(hass, {"1/6/0": True, "2/6/65532": 1})
    add_matter_entity(hass, entry, "light.other", state="on")

    response = await call(hass, "stop", {"entity_id": "light.other"})

    assert response["light.other"]["capability"] == "multi_endpoint"


@pytest.mark.parametrize(
    "node",
    [
        {"vendor_id": 0xFFF1},
        {"vendor_id": 4757, "attributes": {"1/29/0": [{"0": 14, "1": 1}], "2/29/0": [{"0": 19, "1": 1}]}},
    ],
    ids=["uncertified", "bridged"],
)
async def test_uncertified_and_bridged_lights_are_not_built_even_with_labs_on(hass, node):
    entry, send_cmd, _, _ = light_device(hass, **node)
    add_matter_entity(hass, entry, "light.bulb", state="on")

    assert await refusal(hass, "stop", BULB) == "not_built"
    send_cmd.assert_not_awaited()


async def test_labs_off_refuses_other(hass):
    allow_labs(hass, False)
    send_cmd, _, _ = light(hass)

    assert await refusal(hass, "stop", BULB) == "labs_off"
    send_cmd.assert_not_awaited()


def test_the_light_domain_and_the_two_classes_are_labs():
    scope = MatterStop.scope
    assert scope.capabilities == {"other": Level.LABS, "multi_endpoint": Level.LABS}
    assert scope.level("light", ["other"]) is Level.LABS
    assert not scope.not_built


async def test_each_command_is_logged_without_the_node(hass, wire):
    light(hass)

    await call(hass, "stop", BULB)

    assert sent(wire) == [
        "light.bulb: sending matter LevelControl.Stop {'optionsMask': 0, 'optionsOverride': 0}",
        "light.bulb: sending matter ColorControl.StopMoveStep {'optionsMask': 0, 'optionsOverride': 0}",
    ]
