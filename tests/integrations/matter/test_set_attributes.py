"""Matter set_attributes: Level and Color Control MoveTo commands with the ExecuteIfOff override, then a read-back."""

from dataclasses import asdict

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.matter import set_attributes as adapter
from custom_components.deviceside.integrations.matter.set_attributes import MatterSetAttributes

from ...conftest import allow_labs, call, refusal, sent
from ...fixtures.matter import NODE_ID, add_matter_entity, light_device, matter_device

EP = 1
OTHER = {"status": "confirmed", "integration": "matter", "capability": "other"}
# The ExecuteIfOff override, for this command only, and the write fade: 4 tenths of a second.
OPTIONS = {"transitionTime": 4, "optionsMask": 1, "optionsOverride": 1}
# Color Control's FeatureMap (0xFFFC): HS 0x01, XY 0x08, CT 0x10.
HS_XY_CT = 0x19
COLOR = {"1/768/65532": HS_XY_CT}

pytestmark = pytest.mark.usefixtures("mock_chip", "setup_production")


@pytest.fixture(autouse=True)
def labs_on(hass, setup_production):
    """Every Matter light class is in Labs: these tests run the call with Labs on."""
    allow_labs(hass)


@pytest.fixture(autouse=True)
def no_fade_wait(monkeypatch):
    """The read-back's wait for the fade, off so tests don't sleep; the test of it sets its own."""
    monkeypatch.setattr(adapter, "WRITE_FADE_WAIT_S", 0.0)


def light(hass, state="on", modes=("brightness",), attributes=None, **node):
    """A Matter light with Level Control (CurrentLevel 100), registered as light.bulb."""
    entry, send_cmd, read_attr, node_state = light_device(hass, attributes, **node)
    add_matter_entity(hass, entry, "light.bulb", state=state, attributes={"supported_color_modes": list(modes)})
    return send_cmd, read_attr, node_state


def commands(send_cmd) -> list[dict]:
    return [asdict(args.kwargs["command"]) for args in send_cmd.await_args_list]


def reads(read_attr) -> list[str]:
    return [args.kwargs["attribute_path"] for args in read_attr.await_args_list]


async def set_attrs(hass, **fields):
    return await call(hass, "set_attributes", {"entity_id": "light.bulb", **fields})


async def test_a_lit_light_takes_the_level_with_the_override_and_confirms(hass):
    send_cmd, read_attr, _ = light(hass)

    response = await set_attrs(hass, brightness=50)

    assert response == {"light.bulb": OTHER}
    send_cmd.assert_awaited_once()
    kwargs = send_cmd.call_args.kwargs
    assert (kwargs["node_id"], kwargs["endpoint_id"]) == (NODE_ID, EP)
    # 50 % of 254, as MoveToLevel, with the fade and ExecuteIfOff (mask 1, override 1) as literals.
    assert commands(send_cmd) == [
        {
            "command": "LevelControl.MoveToLevel",
            "level": 127,
            "transitionTime": 4,
            "optionsMask": 1,
            "optionsOverride": 1,
        }
    ]
    assert reads(read_attr) == ["1/8/0"]  # a lit light isn't asked for its OnLevel


async def test_an_off_light_gets_move_to_level_never_the_with_on_off_variant_and_stays_off(hass):
    send_cmd, read_attr, _ = light(hass, state="off")

    response = await set_attrs(hass, brightness=50)

    assert response == {"light.bulb": OTHER}
    assert [command["command"] for command in commands(send_cmd)] == ["LevelControl.MoveToLevel"]
    assert commands(send_cmd)[0]["optionsMask"] == 1
    assert commands(send_cmd)[0]["optionsOverride"] == 1
    assert commands(send_cmd)[0]["transitionTime"] == 4
    assert reads(read_attr) == ["1/8/0", "1/8/17"]  # CurrentLevel, then OnLevel (an off light's next on)


async def test_an_off_light_with_on_level_set_is_sent_and_on_level_is_never_written(hass):
    """The next On goes to OnLevel, so the values stored aren't what the light will show: never confirmed."""
    send_cmd, _, node = light(hass, state="off", attributes={"1/8/17": 20})

    response = await set_attrs(hass, brightness=50)

    assert response == {"light.bulb": {**OTHER, "status": "sent", "detail": "on_level_set"}}
    assert [command["command"] for command in commands(send_cmd)] == ["LevelControl.MoveToLevel"]
    assert node.attributes["1/8/17"] == 20


async def test_on_level_read_on_a_lit_light_is_skipped_so_a_set_one_does_not_matter(hass):
    _, read_attr, _ = light(hass, attributes={"1/8/17": 20})

    assert await set_attrs(hass, brightness=50) == {"light.bulb": OTHER}
    assert "1/8/17" not in reads(read_attr)


async def test_on_level_set_wins_over_a_value_that_did_not_read_back(hass):
    _, _, node = light(hass, state="off", attributes={"1/8/17": 20})
    node.attributes["1/8/0"] = 100
    node.apply = lambda *args: None  # the light keeps nothing

    response = await set_attrs(hass, brightness=50)

    assert response["light.bulb"]["detail"] == "on_level_set"


@pytest.mark.parametrize(
    ("modes", "field", "command", "fields", "paths"),
    [
        (
            ("color_temp",),
            {"color_temp_kelvin": 4000},
            "ColorControl.MoveToColorTemperature",
            {"colorTemperatureMireds": 250},
            ["1/768/7"],
        ),
        (
            ("xy",),
            {"xy_color": [0.5, 0.25]},
            "ColorControl.MoveToColor",
            {"colorX": 32768, "colorY": 16384},
            ["1/768/3", "1/768/4"],
        ),
        (
            ("hs",),
            {"hs_color": [180, 50]},
            "ColorControl.MoveToHueAndSaturation",
            {"hue": 127, "saturation": 127},
            ["1/768/0", "1/768/1"],
        ),
    ],
    ids=["color_temp", "xy", "hs"],
)
async def test_each_color_is_its_own_move_to_command_read_back_from_its_attributes(
    hass, modes, field, command, fields, paths
):
    send_cmd, read_attr, _ = light(hass, modes=modes, attributes=COLOR)

    response = await set_attrs(hass, **field)

    assert response == {"light.bulb": OTHER}
    assert commands(send_cmd) == [{"command": command, **fields, **OPTIONS}]
    assert reads(read_attr) == paths


async def test_brightness_goes_before_the_color_and_both_are_read_back(hass):
    send_cmd, read_attr, _ = light(hass, modes=("color_temp",), attributes=COLOR)

    response = await set_attrs(hass, brightness=50, color_temp_kelvin=4000)

    assert response == {"light.bulb": OTHER}
    assert [command["command"] for command in commands(send_cmd)] == [
        "LevelControl.MoveToLevel",
        "ColorControl.MoveToColorTemperature",
    ]
    assert reads(read_attr) == ["1/8/0", "1/768/7"]


@pytest.mark.parametrize(
    ("read", "status"),
    [(127, "confirmed"), (128, "confirmed"), (126, "confirmed"), (129, "sent"), (125, "sent"), (None, "sent")],
    ids=["as_sent", "one_above", "one_below", "two_above", "two_below", "null"],
)
async def test_the_level_is_confirmed_within_one_step_of_what_was_sent(hass, read, status):
    _, _, node = light(hass)
    node.apply = lambda *args: node.attributes.update({"1/8/0": read})

    response = await set_attrs(hass, brightness=50)

    expected = {"status": status} if status == "confirmed" else {"status": status, "detail": "attributes_not_reported"}
    assert response == {"light.bulb": {**OTHER, **expected}}


async def test_a_color_the_light_did_not_keep_is_sent(hass):
    """The level reads as sent, the color temperature doesn't: one attribute off is enough."""
    _, _, node = light(hass, modes=("color_temp",), attributes=COLOR)
    apply = node.apply

    def keep_level_only(endpoint_id, command):
        apply(endpoint_id, command)
        node.attributes["1/768/7"] = 370

    node.apply = keep_level_only

    response = await set_attrs(hass, brightness=50, color_temp_kelvin=4000)

    assert response == {"light.bulb": {**OTHER, "status": "sent", "detail": "attributes_not_reported"}}


@pytest.mark.parametrize("path", ["1/8/0", "1/8/17"], ids=["current_level", "on_level"])
async def test_a_read_that_fails_is_sent_with_readback_failed(hass, path):
    _, _, node = light(hass, state="off")
    node.refused.add(path)

    response = await set_attrs(hass, brightness=50)

    assert response == {"light.bulb": {**OTHER, "status": "sent", "detail": "readback_failed"}}


async def test_the_read_waits_for_the_fade(hass, monkeypatch):
    monkeypatch.setattr(adapter, "WRITE_FADE_WAIT_S", 0.05)
    send_cmd, read_attr, node = light(hass)
    times = {}
    loop = hass.loop

    def stamp_sent(*args):
        times.setdefault("sent", loop.time())

    node.apply = stamp_sent
    read = read_attr.side_effect
    read_attr.side_effect = lambda **kwargs: times.setdefault("read", loop.time()) and read(**kwargs)

    await set_attrs(hass, brightness=50)

    assert times["read"] - times["sent"] >= 0.05


async def test_min_and_max_brightness_clamp_the_level_the_light_has(hass):
    send_cmd, read_attr, _ = light(hass, attributes={"1/8/0": 254})

    response = await set_attrs(hass, max_brightness=50)

    assert response == {"light.bulb": OTHER}
    assert commands(send_cmd)[0]["level"] == 127
    assert reads(read_attr)[0] == "1/8/0"  # the level it has, read before the command


async def test_a_light_already_within_the_limits_is_unchanged_with_nothing_sent(hass):
    send_cmd, _, _ = light(hass, attributes={"1/8/0": 100})

    response = await set_attrs(hass, min_brightness=10, max_brightness=90)

    assert response == {
        "light.bulb": {"status": "unchanged", "integration": "matter", "capability": "other", "detail": "within_limits"}
    }
    send_cmd.assert_not_awaited()


async def test_a_color_the_light_cannot_take_is_dropped_and_the_rest_sent(hass):
    send_cmd, _, _ = light(hass, modes=("brightness",))

    response = await set_attrs(hass, brightness=50, hs_color=[180, 50])

    assert response == {"light.bulb": {**OTHER, "detail": "fields_dropped"}}
    assert [command["command"] for command in commands(send_cmd)] == ["LevelControl.MoveToLevel"]


async def test_a_light_with_no_level_control_is_not_dimmable(hass):
    entry, send_cmd, _ = matter_device(hass, vendor_id=4874, product_id=80)  # OnOff only: no 1/8/0 in its cache
    add_matter_entity(hass, entry, "light.bulb", attributes={"supported_color_modes": ["onoff"]})

    assert await refusal(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 50}) == "not_dimmable"
    send_cmd.assert_not_awaited()


async def test_a_light_with_level_control_but_no_lighting_feature_is_refused_as_before(hass):
    entry, send_cmd, _, _ = light_device(hass, feature_map=0x0000)
    add_matter_entity(hass, entry, "light.bulb", attributes={"supported_color_modes": ["brightness"]})

    assert await refusal(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 50}) == "no_lt_feature"


async def test_a_send_that_fails_rejects_the_light(hass):
    send_cmd, _, _ = light(hass)
    send_cmd.side_effect = ConnectionError("device unreachable")

    with pytest.raises(HomeAssistantError) as raised:
        await set_attrs(hass, brightness=50)

    assert raised.value.translation_key == "targets_failed"


async def test_each_command_is_logged_without_the_node(hass, wire):
    light(hass, modes=("color_temp",), attributes=COLOR)

    await set_attrs(hass, brightness=50, color_temp_kelvin=4000)

    assert sent(wire) == [
        "light.bulb: sending matter LevelControl.MoveToLevel "
        "{'level': 127, 'transitionTime': 4, 'optionsMask': 1, 'optionsOverride': 1}",
        "light.bulb: sending matter ColorControl.MoveToColorTemperature "
        "{'colorTemperatureMireds': 250, 'transitionTime': 4, 'optionsMask': 1, 'optionsOverride': 1}",
    ]


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        ({}, "other"),
        # A second On/Off endpoint beside the fixture's endpoint 1: certification tests one, but the Level and Color
        # servers are per endpoint, so it is admitted too (plan Decision 2).
        ({"attributes": {"2/6/65532": 1}}, "multi_endpoint"),
    ],
    ids=["other", "multi_endpoint"],
)
async def test_the_admitted_classes_run_in_labs(hass, node, expected):
    send_cmd, _, _ = light(hass, **node)

    response = await set_attrs(hass, brightness=50)

    assert response["light.bulb"]["capability"] == expected
    send_cmd.assert_awaited_once()


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
    add_matter_entity(hass, entry, "light.bulb", attributes={"supported_color_modes": ["brightness"]})

    assert await refusal(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 50}) == "not_built"
    send_cmd.assert_not_awaited()


async def test_labs_off_refuses_other(hass):
    allow_labs(hass, False)
    send_cmd, _, _ = light(hass)

    assert await refusal(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 50}) == "labs_off"
    send_cmd.assert_not_awaited()


def test_the_light_domain_and_the_two_classes_are_labs():
    scope = MatterSetAttributes.scope
    assert scope.capabilities == {"other": Level.LABS, "multi_endpoint": Level.LABS}
    assert scope.level("light", ["other"]) is Level.LABS
    assert not scope.not_built
