"""ZHA turn_on_for: optional light.turn_on, OnWithTimedOff through issue_zigbee_cluster_command (or one
issue_zigbee_group_command for a ZHA group's members), then an OnOff and OnTime read-back."""

import logging
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.deviceside.integrations.zha import turn_on_for, zcl
from custom_components.deviceside.integrations.zha.addressing import address

from .conftest import call, call_as
from ...conftest import allow_experimental, refusal, sent
from ...fixtures.zha import IEEE, StandardOnOff, add_zha_entity, quirk_on_off, zha_entry, zha_group

CONFIRMED = {"status": "confirmed", "integration": "zha"}


def reads(remaining, on=True) -> dict:
    """What zcl.read_attributes returns: OnOff, and OnTime in tenths."""
    return {zcl.ON_OFF: on, zcl.ON_TIME: remaining}


@pytest.fixture(autouse=True)
def readback(monkeypatch):
    """zcl.read_attributes, reading back on with the 5 s every test requests unless it sets its own."""
    read = AsyncMock(return_value=reads(50))
    monkeypatch.setattr(zcl, "read_attributes", read)
    return read


@pytest.fixture(autouse=True)
def no_reread_wait(monkeypatch):
    monkeypatch.setattr(turn_on_for, "_REREAD_S", 0)


@pytest.fixture
def turn_ons(hass):
    return async_mock_service(hass, "light", "turn_on")


async def test_light_sends_on_with_timed_off(hass, setup_production, commands, turn_ons):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5})

    assert response == {"light.bulb": CONFIRMED}
    assert not turn_ons
    assert len(commands) == 1
    assert commands[0].data == {
        "ieee": IEEE,
        "endpoint_id": 11,
        "cluster_id": 6,
        "cluster_type": "in",
        "command": 0x42,
        "command_type": "server",
        "params": {"on_off_control": 0, "on_time": 50, "off_wait_time": 0},
    }


async def test_brightness_calls_turn_on_first(hass, setup_production, commands, turn_ons):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5, "brightness": 50})

    assert response == {"light.bulb": CONFIRMED}
    assert turn_ons[0].data == {"entity_id": "light.bulb", "brightness": 128}
    assert len(commands) == 1


async def test_untested_field_is_refused(hass, setup_production, commands, turn_ons):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")

    data = {"entity_id": "light.bulb", "duration": 5, "hs_color": [30, 50]}
    assert await refusal(hass, "turn_on_for", data) == "fields_not_tested"
    assert not commands


async def test_duration_in_tenths_and_clamped(hass, setup_production, commands, turn_ons, readback):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    readback.return_value = reads(65534)

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": {"hours": 2}})

    assert response == {"light.bulb": {**CONFIRMED, "clamped_to": 6553.4}}
    assert commands[0].data["params"]["on_time"] == 65534


@pytest.mark.parametrize("remaining", [50, 20])
async def test_on_time_within_slack_confirms(hass, setup_production, commands, readback, remaining):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    readback.return_value = reads(remaining)

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5})

    assert response == {"light.bulb": CONFIRMED}
    readback.assert_awaited_once_with(hass, (IEEE, 11), 0x0006, (0x0000,), optional=(0x4001,))


@pytest.mark.parametrize("remaining", [0, 51, 19])
async def test_on_time_outside_slack_is_sent(hass, setup_production, commands, readback, remaining):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    readback.return_value = reads(remaining)

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5})

    assert response == {"light.bulb": {"status": "sent", "integration": "zha", "detail": "timer_not_reported"}}


async def test_a_running_timer_on_a_device_that_stayed_off_is_sent(hass, setup_production, commands, readback):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    readback.return_value = reads(50, on=False)

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5})

    assert response == {"light.bulb": {"status": "sent", "integration": "zha", "detail": "not_on"}}


@pytest.mark.parametrize(
    "read",
    [
        {"side_effect": ImportError("No module named 'zha'")},
        {"side_effect": LookupError("ZHA device not found")},
        {"return_value": reads(None)},  # an uncomparable OnTime
        {"return_value": reads(50, on=None)},  # an OnOff that is neither on nor off
        {"return_value": {}},  # a value missing
    ],
)
async def test_failed_read_is_sent(hass, setup_production, commands, readback, read):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    readback.configure_mock(**read)

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5})

    assert response == {"light.bulb": {"status": "sent", "integration": "zha", "detail": "readback_failed"}}


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (True, CONFIRMED),
        # A plug that keeps OnTime but stays off.
        (False, {"status": "sent", "integration": "zha", "detail": "not_on"}),
    ],
)
async def test_switch_is_experimental(hass, setup_production, commands, turn_ons, readback, on, expected):
    add_zha_entity(hass, zha_entry(hass), "switch.plug")
    readback.return_value = reads(50, on=on)
    data = {"entity_id": "switch.plug", "duration": 5}

    assert await refusal(hass, "turn_on_for", data) == "experimental_off"
    assert not commands

    allow_experimental(hass)
    assert await call(hass, "turn_on_for", data) == {"switch.plug": expected}
    assert not turn_ons
    assert commands[0].data["command"] == 0x42
    assert commands[0].data["params"] == {"on_off_control": 0, "on_time": 50, "off_wait_time": 0}


async def test_entity_without_a_light_unique_id_is_not_addressable(hass, setup_production, commands, turn_ons):
    add_zha_entity(hass, zha_entry(hass), "light.quirk", unique_id=f"{IEEE}-1-6-child_lock")

    assert await refusal(hass, "turn_on_for", {"entity_id": "light.quirk", "duration": 5}) == "not_addressable"


async def test_zha_error_rejects_that_target(hass, setup_production, turn_ons):
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.gone", ieee="00:00:00:00:00:00:00:01")
    add_zha_entity(hass, entry, "light.bulb")

    # A plain handler, since a mock service can't raise; the admin check has its own tests below.
    async def handler(service: ServiceCall) -> None:
        if service.data["ieee"] != IEEE:
            raise ValueError(f"Device with IEEE {service.data['ieee']} not found")

    hass.services.async_register("zha", "issue_zigbee_cluster_command", handler)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "turn_on_for", {"entity_id": ["light.bulb", "light.gone"], "duration": 5})

    assert raised.value.translation_key == "targets_failed"
    assert "light.gone: error" in raised.value.translation_placeholders["summary"]


BULB_FOR_5 = {"entity_id": "light.bulb", "duration": 5}


async def test_admin_caller_reaches_zha(hass, setup_production, admin_command, hass_admin_user):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")

    assert await call_as(hass, hass_admin_user, "turn_on_for", BULB_FOR_5) == {"light.bulb": CONFIRMED}
    assert admin_command[0].context.user_id == hass_admin_user.id
    assert admin_command[0].service == "issue_zigbee_cluster_command"


async def test_non_admin_caller_is_refused_by_zha(hass, setup_production, admin_command, hass_read_only_user, readback):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")

    with pytest.raises(HomeAssistantError) as raised:
        await call_as(hass, hass_read_only_user, "turn_on_for", BULB_FOR_5)

    assert raised.value.translation_placeholders["summary"] == "light.bulb: admin_required"
    assert not admin_command
    readback.assert_not_awaited()


@pytest.mark.parametrize(
    ("unique_id", "expected"),
    [
        (f"{IEEE}-11", (IEEE, 11)),
        (f"{IEEE}-1-6", None),
        (f"{IEEE}-x", None),
        ("light_zha_group_0x0002", None),
    ],
)
def test_address(unique_id, expected):
    assert address(unique_id) == expected


A, B = "00:00:00:00:00:00:00:0a", "00:00:00:00:00:00:00:0b"


@pytest.fixture
def group_commands(hass):
    return async_mock_service(hass, "zha", "issue_zigbee_group_command")


@pytest.fixture
def two_light_group(hass, zha_groups):
    """light.zha_group, ZHA group 2, of light.a and light.b."""
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.zha_group", unique_id="light_zha_group_0x0002")
    add_zha_entity(hass, entry, "light.a", ieee=A)
    add_zha_entity(hass, entry, "light.b", ieee=B)
    zha_groups[2] = zha_group((A, 11), (B, 11))
    return entry


async def test_group_members_get_one_groupcast_and_a_read_back_each(
    hass, setup_production, two_light_group, commands, group_commands, turn_ons, readback
):
    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response == {"light.a": CONFIRMED, "light.b": CONFIRMED}
    assert [command.data for command in group_commands] == [
        {"group": 2, "cluster_id": 6, "command": 0x42, "args": [0, 50, 0]}
    ]
    assert not commands
    assert not turn_ons
    assert sorted(read.args[1].ieee for read in readback.await_args_list) == [A, B]


async def test_group_fields_turn_on_the_group_entity_once(
    hass, setup_production, two_light_group, group_commands, turn_ons
):
    await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5, "brightness": 47})

    assert [turn_on.data for turn_on in turn_ons] == [{"entity_id": "light.zha_group", "brightness": 120}]
    assert len(group_commands) == 1


@pytest.mark.parametrize(("on", "detail"), [(False, "not_on"), (True, "timer_not_reported")])
async def test_a_member_without_on_time_reports_no_timer(
    hass, setup_production, two_light_group, group_commands, readback, on, detail
):
    """A member that can't run the timer drops the groupcast silently; its read-back says so."""
    readback.side_effect = lambda hass, addr, *args, **kwargs: {zcl.ON_OFF: on} if addr.ieee == B else reads(50)

    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response == {"light.a": CONFIRMED, "light.b": {"status": "sent", "integration": "zha", "detail": detail}}
    assert [read.args[1].ieee for read in readback.await_args_list].count(B) == 1 + turn_on_for._REREADS


@pytest.mark.parametrize("first", [reads(0, on=False), reads(0)])
async def test_a_member_read_before_the_groupcast_lands_is_read_again(
    hass, setup_production, two_light_group, group_commands, readback, first
):
    """A unicast read can overtake the groupcast: no timer at first, then the timer is running."""
    late = iter([first, reads(48)])
    readback.side_effect = lambda hass, addr, *args, **kwargs: next(late) if addr.ieee == B else reads(50)

    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response == {"light.a": CONFIRMED, "light.b": CONFIRMED}


async def test_a_member_whose_read_fails_is_not_read_again(
    hass, setup_production, two_light_group, group_commands, readback
):
    readback.side_effect = lambda hass, addr, *args, **kwargs: {} if addr.ieee == B else reads(50)

    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response["light.b"]["detail"] == "readback_failed"
    assert [read.args[1].ieee for read in readback.await_args_list].count(B) == 1


async def test_a_unicast_is_read_back_once(hass, setup_production, commands, readback):
    """A unicast returns once the light has taken it, so there is nothing to wait for."""
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    readback.return_value = reads(0)

    response = await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5})

    assert response["light.bulb"]["detail"] == "timer_not_reported"
    assert readback.await_count == 1


async def test_a_group_zha_no_longer_knows_is_skipped_as_empty(hass, setup_production, zha_groups, group_commands):
    add_zha_entity(hass, zha_entry(hass), "light.zha_group", unique_id="light_zha_group_0x0002")

    await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5}, return_response=False)

    assert not group_commands


async def test_a_light_named_directly_or_through_an_ha_group_gets_its_own_command(
    hass, setup_production, two_light_group, commands, group_commands
):
    add_zha_entity(hass, two_light_group, "light.bulb")
    hass.states.async_set("group.room", "on", {"entity_id": ["light.bulb"]})

    response = await call(hass, "turn_on_for", {"entity_id": ["group.room", "light.zha_group"], "duration": 5})

    assert response == {"light.bulb": CONFIRMED, "light.a": CONFIRMED, "light.b": CONFIRMED}
    assert [command.data["ieee"] for command in commands] == [IEEE]
    assert len(group_commands) == 1


async def test_non_admin_caller_is_refused_for_every_member(
    hass, setup_production, two_light_group, admin_command, commands, hass_read_only_user, readback
):
    """Only the group command is ZHA's admin one here: a fallback to a per-member cluster command would be sent."""
    with pytest.raises(HomeAssistantError) as raised:
        await call_as(hass, hass_read_only_user, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert raised.value.translation_placeholders["summary"] == "light.a: admin_required, light.b: admin_required"
    assert not admin_command
    assert not commands
    readback.assert_not_awaited()


async def test_a_failed_groupcast_rejects_only_that_groups_members(
    hass, setup_production, two_light_group, commands, readback
):
    add_zha_entity(hass, two_light_group, "light.bulb")

    async def handler(service: ServiceCall) -> None:
        raise ValueError("broadcast table full")

    hass.services.async_register("zha", "issue_zigbee_group_command", handler)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "turn_on_for", {"entity_id": ["light.bulb", "light.zha_group"], "duration": 5})

    # light.bulb was confirmed, so it is not among the failures.
    assert raised.value.translation_placeholders["summary"] == "light.a: error, light.b: error"


async def test_the_fields_and_the_timer_are_logged_in_order(hass, setup_production, commands, turn_ons, wire):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")

    await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5, "brightness": 50})

    assert sent(wire) == [
        "light.bulb: sending ha light.turn_on {'brightness': 128}",
        "light.bulb: sending zcl 0x0006/0x42 {'on_off_control': 0, 'on_time': 50, 'off_wait_time': 0}",
    ]


# Device classes (classes.py): the entries for classes the call harms hold with Experimental features on.

TS011F = ("_TZ3000_typdpbpg", "TS011F")
C = "00:00:00:00:00:00:00:0c"


@pytest.mark.parametrize(
    ("strings", "on_off", "domain", "reason"),
    [
        # Tuya's recipe would serve it, but is parked (plan Decision 74).
        (TS011F, StandardOnOff, "switch", "not_supported"),
        (("_TZ3000_abcdefgh", "TS0001"), StandardOnOff, "switch", "not_supported"),
        # A Tuya bulb outside the countdown models: nobody has probed its timer.
        (("_TZ3210_abcdefgh", "TS0505B"), StandardOnOff, "light", "not_supported"),
        (("_TZE200_abcdefgh", "TS0601"), StandardOnOff, "light", "not_supported"),
        (("_TZ3210_0jxeoadc", "TS0049"), quirk_on_off("zhaquirks.tuya.mcu"), "switch", "not_supported"),
        (("sengled", "E11-G13"), StandardOnOff, "light", "not_supported"),
        (("SONOFF", "SWV"), StandardOnOff, "switch", "not_supported"),
        # Fails the countdown that serves its siblings; Tuya's inching would plausibly serve it (plan Decision 41).
        (("_TZ3000_gjnozsaz", "TS011F"), StandardOnOff, "switch", "not_supported"),
    ],
)
async def test_a_class_the_call_harms_is_refused_with_experimental_on(
    hass, setup_production, commands, turn_ons, strings, on_off, domain, reason
):
    add_zha_entity(hass, zha_entry(hass), f"{domain}.device", strings=strings, on_off=on_off)
    allow_experimental(hass)

    assert await refusal(hass, "turn_on_for", {"entity_id": f"{domain}.device", "duration": 5}) == reason
    assert not commands
    assert not turn_ons


async def test_a_tuya_member_in_a_group_is_refused_and_the_rest_get_their_own(
    hass, setup_production, two_light_group, zha_groups, commands, group_commands
):
    """The Tuya light is refused, and a groupcast would still reach it, so the Hue bulbs get one command each."""
    add_zha_entity(hass, two_light_group, "light.strip", ieee=C, strings=("_TZ3000_abcdefgh", "TS0001"))
    zha_groups[2] = zha_group((A, 11), (B, 11), (C, 11))
    allow_experimental(hass)

    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response == {"light.a": CONFIRMED, "light.b": CONFIRMED}
    assert not group_commands
    assert sorted(command.data["ieee"] for command in commands) == [A, B]


async def test_a_device_whose_strings_werent_read_is_refused_with_experimental_on(hass, setup_production, commands):
    """It could be a Tuya datapoint device, so where the call harms a class it is refused as class_unknown."""
    add_zha_entity(hass, zha_entry(hass), "switch.plug", strings=(None, None))
    allow_experimental(hass)

    assert await refusal(hass, "turn_on_for", {"entity_id": "switch.plug", "duration": 5}) == "class_unknown"
    assert not commands


async def test_another_brand_runs_only_with_experimental_on(hass, setup_production, commands):
    add_zha_entity(hass, zha_entry(hass), "light.ikea", strings=("IKEA of Sweden", "TRADFRI bulb E27 WS opal 980lm"))
    data = {"entity_id": "light.ikea", "duration": 5}

    assert await refusal(hass, "turn_on_for", data) == "experimental_off"
    assert not commands

    allow_experimental(hass)
    assert await call(hass, "turn_on_for", data) == {"light.ikea": CONFIRMED}
    assert commands[0].data["params"] == {"on_off_control": 0, "on_time": 50, "off_wait_time": 0}


async def test_a_group_with_a_harmed_member_runs_its_others_one_by_one(
    hass, setup_production, two_light_group, zha_groups, commands, group_commands
):
    """The Sengled is refused, and a groupcast would reach it, so the Hue bulbs get one command each."""
    add_zha_entity(hass, two_light_group, "light.sengled", ieee=C, strings=("sengled", "E11-G13"))
    zha_groups[2] = zha_group((A, 11), (B, 11), (C, 11))

    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response == {"light.a": CONFIRMED, "light.b": CONFIRMED}
    assert not group_commands
    assert sorted(command.data["ieee"] for command in commands) == [A, B]


async def test_a_plug_with_no_light_in_the_group_stops_the_groupcast(
    hass, setup_production, two_light_group, zha_groups, commands, group_commands
):
    """ZHA's group light reaches only its lights, but a groupcast reaches the plug too."""
    add_zha_entity(hass, two_light_group, "switch.plug", ieee=C, unique_id=f"{C}-1", strings=("_TZE200_x", "TS0601"))
    zha_groups[2] = zha_group((A, 11), (B, 11), (C, 1))

    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response == {"light.a": CONFIRMED, "light.b": CONFIRMED}
    assert not group_commands
    assert sorted(command.data["ieee"] for command in commands) == [A, B]


async def test_a_member_zha_doesnt_know_stops_the_groupcast(
    hass, setup_production, two_light_group, zha_groups, commands, group_commands
):
    zha_groups[2] = zha_group((A, 11), (B, 11), unknown=1)

    await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert not group_commands
    assert sorted(command.data["ieee"] for command in commands) == [A, B]


async def test_the_coordinator_in_the_group_keeps_the_groupcast(
    hass, setup_production, two_light_group, zha_groups, commands, group_commands
):
    zha_groups[2] = zha_group((A, 11), (B, 11), coordinator=C)

    await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert len(group_commands) == 1
    assert not commands


async def test_a_flagged_member_left_out_stops_the_groupcast(
    hass, setup_production, two_light_group, zha_groups, commands, group_commands
):
    """With Experimental features off, another brand's bulb is skipped, and a groupcast would still reach it."""
    add_zha_entity(hass, two_light_group, "light.ikea", ieee=C, strings=("IKEA of Sweden", "TRADFRI bulb"))
    zha_groups[2] = zha_group((A, 11), (B, 11), (C, 11))

    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response == {"light.a": CONFIRMED, "light.b": CONFIRMED}
    assert not group_commands
    assert sorted(command.data["ieee"] for command in commands) == [A, B]


async def test_a_group_member_that_cant_be_classed_is_skipped_and_the_rest_get_their_own(
    hass, setup_production, two_light_group, zha_groups, commands, group_commands
):
    """A member whose strings weren't read could be a harmed class: skipped as class_unknown, even with Experimental
    features on; the others get one command each, as a groupcast would reach it."""
    add_zha_entity(hass, two_light_group, "light.unread", ieee=C, strings=(None, None))
    zha_groups[2] = zha_group((A, 11), (B, 11), (C, 11))
    allow_experimental(hass)

    response = await call(hass, "turn_on_for", {"entity_id": "light.zha_group", "duration": 5})

    assert response == {"light.a": CONFIRMED, "light.b": CONFIRMED}
    assert not group_commands
    assert sorted(command.data["ieee"] for command in commands) == [A, B]


async def test_the_debug_log_holds_the_read_back_values(hass, setup_production, commands, readback, caplog):
    """A seconds device departs in these values (tenet 4); the log names the entity, never the address."""
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    readback.return_value = reads(50, on=False)

    with caplog.at_level(logging.DEBUG, logger=turn_on_for.__name__):
        await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5})

    assert "light.bulb: turn_on_for read back OnOff 0, OnTime 50 (sent 50 tenths)" in caplog.text
    assert IEEE not in caplog.text


async def test_a_light_without_on_time_logs_none_for_it(hass, setup_production, commands, readback, caplog):
    add_zha_entity(hass, zha_entry(hass), "light.bulb")
    readback.return_value = {zcl.ON_OFF: 1}

    with caplog.at_level(logging.DEBUG, logger=turn_on_for.__name__):
        await call(hass, "turn_on_for", {"entity_id": "light.bulb", "duration": 5})

    assert "light.bulb: turn_on_for read back OnOff 1, OnTime None (sent 50 tenths)" in caplog.text
