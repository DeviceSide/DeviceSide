"""Matter turn_on_for: OnWithTimedOff on the OnOff cluster, with OnTime read-back."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.deviceside.core.scope import Level
from custom_components.deviceside.integrations.matter.turn_on_for import MatterTurnOnFor

from ...conftest import call, sent
from ...fixtures.matter import (
    NODE_ID,
    add_matter_entity,
    matter_device,
    on_time_reads,
)

CONFIRMED = {"status": "confirmed", "integration": "matter"}
EP = 1  # endpoint_id used across tests

pytestmark = pytest.mark.usefixtures("mock_chip", "setup_production")


@pytest.mark.parametrize("entity_id", ["switch.plug", "light.bulb"])
async def test_sends_on_with_timed_off_and_confirms(hass, entity_id):
    """A plug, or a Matter light (Documented) on the plug's proof: OnWithTimedOff on its endpoint, then OnTime and
    OnOff read back; a running timer confirms."""
    entry, send_cmd, read_attr = matter_device(hass, endpoint_id=EP)
    add_matter_entity(hass, entry, entity_id, endpoint_id=EP)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {entity_id: CONFIRMED}
    send_cmd.assert_awaited_once()
    call_kwargs = send_cmd.call_args.kwargs
    assert (call_kwargs["node_id"], call_kwargs["endpoint_id"]) == (NODE_ID, EP)
    assert vars(call_kwargs["command"]) == {"onOffControl": 0, "onTime": 50, "offWaitTime": 0}  # 5 s in tenths
    assert [args.kwargs["attribute_path"] for args in read_attr.await_args_list] == [f"{EP}/6/16385", f"{EP}/6/0"]


async def test_duration_converted_to_tenths(hass):
    """Duration in seconds is multiplied by 10 and rounded to integer tenths."""
    entry, send_cmd, _ = matter_device(hass, endpoint_id=EP)
    add_matter_entity(hass, entry, "switch.bulb", endpoint_id=EP)

    await call(hass, "turn_on_for", {"entity_id": "switch.bulb", "duration": {"seconds": 1, "milliseconds": 500}})

    cmd = send_cmd.call_args.kwargs["command"]
    assert cmd.onTime == 15  # 1.5 s * 10 = 15 tenths


def test_light_is_documented_and_plug_verified():
    assert MatterTurnOnFor.scope.level("light") is Level.DOCUMENTED
    assert MatterTurnOnFor.scope.level("switch") is Level.VERIFIED


@pytest.mark.parametrize(
    "reads",
    [on_time_reads(0).side_effect, on_time_reads(50, on=False).side_effect, lambda *args, **kwargs: {}],
    ids=["zero", "off_with_on_time", "path_missing"],
)
@pytest.mark.parametrize("entity_id", ["switch.plug", "light.bulb"])
async def test_no_running_timer_does_not_confirm(hass, reads, entity_id):
    """OnTime 0, OnTime > 0 with OnOff off, or a read without the OnTime path: no running timer, so SENT."""
    entry, _, read_attr = matter_device(hass, endpoint_id=EP)
    read_attr.side_effect = reads
    add_matter_entity(hass, entry, entity_id, endpoint_id=EP)

    response = await call(hass, "turn_on_for", {"entity_id": entity_id, "duration": 5})

    assert response == {entity_id: {"status": "sent", "integration": "matter", "detail": "timer_not_reported"}}


async def test_readback_fails_returns_sent(hass):
    """If read_attribute raises, the result is SENT with readback_failed."""
    entry, send_cmd, read_attr = matter_device(hass, endpoint_id=EP)
    read_attr.side_effect = ConnectionError("lost connection")
    add_matter_entity(hass, entry, "switch.bulb", endpoint_id=EP)

    response = await call(hass, "turn_on_for", {"entity_id": "switch.bulb", "duration": 5})

    assert response == {"switch.bulb": {"status": "sent", "integration": "matter", "detail": "readback_failed"}}


@pytest.mark.parametrize(
    ("read_on_time", "status"),
    [(50, "confirmed"), (20, "confirmed"), (19, "sent"), (51, "sent"), (600, "sent")],
    ids=["as_sent", "3_s_counted_down", "older_than_the_slack", "over_the_request", "another_timer"],
)
async def test_confirms_only_the_timer_sent(hass, read_on_time, status):
    """OnTime counts down from the 50 tenths sent: within 3 s under it is ours, anything else another timer."""
    entry, send_cmd, read_attr = matter_device(hass, endpoint_id=EP)
    read_attr.side_effect = on_time_reads(read_on_time).side_effect
    add_matter_entity(hass, entry, "switch.bulb", endpoint_id=EP)

    response = await call(hass, "turn_on_for", {"entity_id": "switch.bulb", "duration": 5})

    assert response["switch.bulb"]["status"] == status


async def test_send_error_rejects_target(hass):
    """If send_device_command raises, the target is REJECTED and targets_failed is raised."""
    entry, send_cmd, _ = matter_device(hass, endpoint_id=EP)
    send_cmd.side_effect = ConnectionError("device unreachable")
    add_matter_entity(hass, entry, "switch.bulb", endpoint_id=EP)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "turn_on_for", {"entity_id": "switch.bulb", "duration": 5})

    assert raised.value.translation_key == "targets_failed"


async def test_duration_beyond_limit_is_clamped(hass):
    """A duration longer than 6553.4 s is clamped to the limit."""
    entry, send_cmd, _ = matter_device(hass, endpoint_id=EP)
    add_matter_entity(hass, entry, "switch.bulb", endpoint_id=EP)

    response = await call(hass, "turn_on_for", {"entity_id": "switch.bulb", "duration": {"hours": 2}})

    assert response["switch.bulb"]["clamped_to"] == 6553.4
    cmd = send_cmd.call_args.kwargs["command"]
    assert cmd.onTime == round(6553.4 * 10)


async def test_the_command_is_logged_without_the_node(hass, wire):
    entry, _, _ = matter_device(hass, endpoint_id=EP)
    add_matter_entity(hass, entry, "switch.bulb", endpoint_id=EP)

    await call(hass, "turn_on_for", {"entity_id": "switch.bulb", "duration": 5})

    assert sent(wire) == [
        "switch.bulb: sending matter OnOff.OnWithTimedOff {'on_off_control': 0, 'on_time': 50, 'off_wait_time': 0}"
    ]
