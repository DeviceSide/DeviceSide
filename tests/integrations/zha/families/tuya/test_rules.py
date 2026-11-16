"""Tuya's rules on ZHA: the datapoint group, on the quirk and the datapoint strings, and the ZCL group, on the reported
string, the countdown models and the rest of Tuya's ZCL strings. Each group alone; the order between them is the
integration's (test_classification.py)."""

import pytest

from custom_components.deviceside.integrations.zha import rules
from custom_components.deviceside.integrations.zha.families import tuya

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
    assert rules.match(tuya.DATAPOINT_RULES, manufacturer, model, quirk) == expected


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
    assert rules.match(tuya.ZCL_RULES, manufacturer, model, "zigpy.zcl") == expected


def test_the_datapoint_class_is_in_no_scope_but_turn_on_fors_refusal():
    """Its quirk answers what DeviceSide sends itself, so it needs a call that isn't built."""
    held = {action for action, scope in tuya.FAMILY.scopes.items() if tuya.TUYA_MCU in scope.capabilities}
    assert held == set()
    assert tuya.TUYA_MCU in tuya.FAMILY.scopes["turn_on_for"].not_built
