"""ZHA's Tuya family: the datapoint rule group, on the quirk and the datapoint strings, and the ZCL group, on the
reported string, the countdown models and the rest of Tuya's ZCL strings, each alone; the catalog they read; and its
levels. The order between the groups and the other families' is the integration's (test_classification.py), as are
turn_on_for's refusals (test_refusals.py)."""

import re

import pytest

from custom_components.deviceside.core.rules import match
from custom_components.deviceside.core.scope import Level, OnDomains
from custom_components.deviceside.integrations.zha import rules
from custom_components.deviceside.integrations.zha.families import tuya
from custom_components.deviceside.zigbee import tuya as catalog

MCU_QUIRK = "zhaquirks.tuya.mcu"


@pytest.mark.parametrize(
    ("manufacturer", "model", "quirk", "expected"),
    [
        ("_TZE200_abcdefgh", "TS0601", None, tuya.TUYA_MCU),
        ("_TZE204_abcdefgh", "Something", None, tuya.TUYA_MCU),
        # A datapoint device with a ZCL manufacturer string, or a model of its own, which only its quirk shows.
        ("_TZ3000_uim07oem", "TS0601", MCU_QUIRK, tuya.TUYA_MCU),
        ("_TZ3210_0jxeoadc", "TS0049", MCU_QUIRK, tuya.TUYA_MCU),
        ("_TZ3000_abcdefgh", "TS0001", "zhaquirks.tuya", tuya.TUYA_MCU),
        # A quirk elsewhere that defines its own command isn't Tuya's routing.
        ("_TZ3000_abcdefgh", "TS0001", "zhaquirks.tuyaish", None),
        # A ZCL device, whose quirk keeps zigpy's command.
        ("_TZ3000_typdpbpg", "TS011F", "zigpy.zcl", None),
    ],
)
def test_datapoint_rules(manufacturer, model, quirk, expected):
    assert match(tuya.DATAPOINT_RULES, rules.read(manufacturer, model, quirk)) == expected


@pytest.mark.parametrize(
    ("manufacturer", "model", "expected"),
    [
        # The lab's string (research/2026-11-14-lab-probe.md, §1).
        ("_TZ3000_typdpbpg", "TS011F", tuya.TUYA_COUNTDOWN),
        # The string reported harmed on the recipe's frame, banned on that model only (plan Decision 35).
        ("_TZ3000_gjnozsaz", "TS011F", tuya.TUYA_COUNTDOWN_HARMED),
        ("_TZ3000_gjnozsaz", "TS0001", tuya.TUYA_COUNTDOWN),
        # Reported on other calls, so not banned.
        ("_TZ3000_dg7fdg92", "TS011F", tuya.TUYA_COUNTDOWN),
        ("_TZ3000_okaz9tjs", "TS011F", tuya.TUYA_COUNTDOWN),
        # The countdown models go before Tuya's other ZCL strings, which hold its bulbs and white labels.
        ("_TZ3000_abcdefgh", "TS0001", tuya.TUYA_COUNTDOWN),
        ("Lidl", "TS0004", tuya.TUYA_COUNTDOWN),
        ("_TZ3000_abcdefgh", "TS0011", tuya.TUYA_COUNTDOWN),
        ("_TZ3000_abcdefgh", "TS0726", tuya.TUYA_COUNTDOWN),
        ("_TZ3210_abcdefgh", "TS0505B", tuya.TUYA_ZCL),
        ("_TZ3000_abcdefgh", "TS0121", tuya.TUYA_ZCL),
        ("_TYZB01_abcdefgh", "Plug", tuya.TUYA_ZCL),
        ("Lidl", "TS0505B", tuya.TUYA_ZCL),
        # A Tuya string no rule reads.
        ("_TYST11_abcdefgh", "abcdefgh", None),
    ],
)
def test_zcl_rules(manufacturer, model, expected):
    assert match(tuya.ZCL_RULES, rules.read(manufacturer, model, "zigpy.zcl")) == expected


def test_the_rules_read_the_catalog_s_strings():
    """One home for Tuya's Zigbee strings, shared with Zigbee2MQTT: the family restates none. A pattern is the
    catalog's own object; a literal string is the catalog's, escaped."""
    read = {
        (rule.capability, name): pattern
        for rule in (*tuya.DATAPOINT_RULES, *tuya.ZCL_RULES)
        for name, pattern in rule.conditions.items()
    }

    assert read["tuya_mcu", "manufacturer"] is catalog.DATAPOINT_MANUFACTURER_PATTERN
    assert read["tuya_zcl", "manufacturer"] is catalog.ZCL_MANUFACTURER_PATTERN
    assert read["tuya_zcl", "model"] is catalog.ZCL_MODEL_PATTERN
    assert read["tuya_mcu", "model"] == re.escape(catalog.DATAPOINT_MODEL)
    assert read["tuya_countdown_harmed", "manufacturer"] == re.escape(catalog.COUNTDOWN_HARMED_MANUFACTURER)
    assert read["tuya_countdown_harmed", "model"] == re.escape(catalog.COUNTDOWN_HARMED_MODEL)
    assert read["tuya_countdown", "model"].split("|")[0] == re.escape(catalog.TS011F_MODEL)


def test_the_zcl_classes_are_untested_on_every_action_they_are_served_on():
    """turn_on_for, which the integration refuses every Tuya class on (test_refusals.py), is left out."""
    assert "turn_on_for" not in tuya.FAMILY.scopes
    assert {
        getattr(level, "level", level) for scope in tuya.FAMILY.scopes.values() for level in scope.capabilities.values()
    } == {Level.EXPERIMENTAL}


def test_only_a_tuya_zcl_light_is_read():
    """get_attributes reads only what another action serves (docs/evidence.md, "A read serves only"): no action serves a
    Tuya plug or switch yet."""
    assert tuya.FAMILY.scopes["get_attributes"].capabilities == {
        tuya.TUYA_ZCL: OnDomains(Level.EXPERIMENTAL, frozenset({"light"}), only=True)
    }


def test_the_datapoint_class_is_in_no_scope():
    """Its quirk answers what DeviceSide sends itself, so it needs a call that isn't built."""
    assert {action for action, scope in tuya.FAMILY.scopes.items() if tuya.TUYA_MCU in scope.capabilities} == set()
