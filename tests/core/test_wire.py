"""The wire trace: an event per call, only while its logger is at DEBUG."""

import json
import logging
from types import SimpleNamespace

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.deviceside.core.wire import WIRE_EVENT, WIRE_LOGGER, wire_trace
from custom_components.deviceside.integrations.hue import bridge

from ..conftest import traced


async def test_the_trace_is_off_unless_its_logger_is_at_debug(hass):
    events = async_capture_events(hass, WIRE_EVENT)
    level = WIRE_LOGGER.level
    WIRE_LOGGER.setLevel(logging.INFO)
    try:
        wire_trace(hass, "light.lamp", "zcl", "0x0008/0x00", {"level": 1})
        await hass.async_block_till_done()
    finally:
        WIRE_LOGGER.setLevel(level)

    assert events == []


async def test_a_call_fires_one_serializable_event(hass, wire):
    wire_trace(hass, "light.lamp", "clip", "light.put", {"dimming_delta": {"action": "stop"}})
    await hass.async_block_till_done()

    assert traced(wire) == [("light.lamp", "clip", "light.put", {"dimming_delta": {"action": "stop"}})]
    json.dumps(wire[0].data)


async def test_a_listener_cannot_change_the_payload_it_was_sent(hass, wire):
    payload = {"dimming_delta": {"action": "stop"}}
    wire_trace(hass, "light.lamp", "clip", "light.put", payload)
    await hass.async_block_till_done()

    wire[0].data["params"]["dimming_delta"]["action"] = "up"
    assert payload == {"dimming_delta": {"action": "stop"}}


async def test_a_device_with_no_entity_is_not_traced(hass, wire):
    wire_trace(hass, None, "clip", "light.put", {})
    await hass.async_block_till_done()

    assert wire == []


async def test_off_the_trace_skips_the_entity_lookup(hass, monkeypatch):
    """A Hue write names its entity through the registry only while the trace is on."""
    looked_up = []
    monkeypatch.setattr(er.EntityRegistry, "async_get_entity_id", lambda self, *args: looked_up.append(args))
    level = WIRE_LOGGER.level
    WIRE_LOGGER.setLevel(logging.INFO)
    try:
        bridge.trace(hass, SimpleNamespace(item_type=SimpleNamespace(value="light")), "light-1", "put", {})
    finally:
        WIRE_LOGGER.setLevel(level)

    assert looked_up == []


def test_the_logger_sits_under_the_integrations_own():
    """So raising custom_components.deviceside to DEBUG, as a debug log does, turns the trace on too."""
    assert WIRE_LOGGER.name == "custom_components.deviceside.wire"
