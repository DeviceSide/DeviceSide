"""Shelly addressing: a Gen1 device, and a component no action reaches, are refused by every adapter before any RPC."""

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.integrations.shelly import INTEGRATION

from ...conftest import refusal
from ...fixtures.shelly import add_shelly_entity, shelly_device

pytestmark = pytest.mark.usefixtures("setup_production")

# A Gen1 light under a key Gen2 would address: the refusal is the generation's, not the key's.
GEN1 = {"light": ("light.old_bulb", "rgbcct:0"), "switch": ("switch.old_relay", "relay_0")}
OUT_OF_REACH = {"light": ("light.other", "script:1"), "switch": ("switch.child_lock", "boolean:200-boolean_child_lock")}


@pytest.mark.parametrize(
    ("action", "domain", "data"),
    [
        ("get_attributes", "switch", {}),
        ("turn_on_for", "switch", {"duration": 5}),
        ("turn_off_for", "switch", {"duration": 5}),
        ("set_auto_off", "switch", {"duration": 5}),
        ("set_auto_on", "switch", {"duration": 5}),
        ("clear_auto_off", "switch", {}),
        ("clear_auto_on", "switch", {}),
        ("raise_brightness", "light", {}),
        ("lower_brightness", "light", {}),
        ("stop", "light", {}),
        ("set_attributes", "light", {"brightness": 40}),
    ],
)
async def test_gen1_and_a_component_out_of_reach_are_refused(hass, action, domain, data):
    gen1, gen1_rpc = shelly_device(hass, gen1=True, mac="112233445566")
    add_shelly_entity(hass, gen1, *GEN1[domain], state="on")
    entry, call_rpc = shelly_device(hass)
    add_shelly_entity(hass, entry, *OUT_OF_REACH[domain], state="on")

    assert await refusal(hass, action, {"entity_id": GEN1[domain][0], **data}) == "gen1_unsupported"
    assert await refusal(hass, action, {"entity_id": OUT_OF_REACH[domain][0], **data}) == "not_addressable"
    assert not gen1_rpc.await_args_list
    assert not call_rpc.await_args_list


@pytest.mark.parametrize(("key", "component"), [("switch:0", "Switch"), ("rgbcct:0", "RGBCCT"), ("script:1", None)])
def test_a_class_is_the_rpc_component_its_key_names(hass, key, component):
    """Literal mappings, so a change to the key table shows here rather than in a conftest that derives them."""
    entry = er.async_get(hass).async_get_or_create("light", "shelly", f"aabbccddeeff-{key}")
    target = Target(entry.entity_id, "light", "shelly", entry, None, None, None)
    assert INTEGRATION.capability(hass, target) == component
