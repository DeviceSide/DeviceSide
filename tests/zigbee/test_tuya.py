"""The catalog's Tuya patterns against example strings: both Zigbee stacks' rules read them, so a change here that
moves a string fails before either stack's classes do."""

import re

import pytest

from custom_components.deviceside.zigbee import tuya


@pytest.mark.parametrize(
    ("pattern", "matching", "others"),
    [
        pytest.param(
            tuya.DATAPOINT_MANUFACTURER,
            ["_TZE200_abcdefgh", "_TZE204_abcdefgh", "_TZE284_abcdefgh"],
            ["_TZ3000_abcdefgh", "_TYZB01_abcdefgh", "_TZE20_abcdefgh", "TZE200_abcdefgh", "_tze200_abcdefgh"],
            id="datapoint_manufacturer",
        ),
        pytest.param(
            tuya.ZCL_MANUFACTURER,
            ["_TZ3000_abcdefgh", "_TZ3210_abcdefgh", "_TYZB01_abcdefgh", tuya.COUNTDOWN_HARMED_MANUFACTURER],
            ["_TZE200_abcdefgh", "_TZ300_abcdefgh", "_TYZB1_abcdefgh", "TZ3000_abcdefgh", "Signify Netherlands B.V."],
            id="zcl_manufacturer",
        ),
        pytest.param(tuya.DATAPOINT_MODEL, ["TS0601"], ["TS0601_switch", "TS011F", "ts0601"], id="datapoint_model"),
        pytest.param(
            tuya.ZCL_MODEL,
            ["TS0001", "TS0011", "TS0505B", "TS0726", "TS0001_switch", tuya.DATAPOINT_MODEL],
            # A TS011F has three digits, so only its manufacturer string says it is Tuya's.
            ["TS011F", tuya.COUNTDOWN_HARMED_MODEL, "TS011", "TS", "ts0001", "LCT015", "XTS0001"],
            id="zcl_model",
        ),
    ],
)
def test_a_pattern_fully_matches_its_strings_alone(pattern, matching, others):
    assert [string for string in matching if not re.fullmatch(pattern, string)] == []
    assert [string for string in others if re.fullmatch(pattern, string)] == []


def test_the_harmed_string_is_the_reported_plug():
    """The identity itself (Zigbee2MQTT #30493), which a rule escapes and matches whole."""
    assert (tuya.COUNTDOWN_HARMED_MANUFACTURER, tuya.COUNTDOWN_HARMED_MODEL) == ("_TZ3000_gjnozsaz", "TS011F")


def test_the_catalog_imports_nothing():
    """Patterns and facts only: a Home Assistant or DeviceSide import would tie both stacks to it."""
    assert not [name for name, value in vars(tuya).items() if not name.startswith("__") and not isinstance(value, str)]
