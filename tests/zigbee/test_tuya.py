"""The catalog's Tuya patterns against example strings: both Zigbee stacks' rules read them, so a change here that
moves a string fails before either stack's classes do. Which device gets which class is each stack's snapshot
(tests/integrations/<x>/test_classification.py)."""

import ast
import re
from pathlib import Path

import pytest

from custom_components.deviceside.zigbee import tuya


@pytest.mark.parametrize(
    ("pattern", "matching", "others"),
    [
        pytest.param(
            tuya.DATAPOINT_MANUFACTURER_PATTERN,
            ["_TZE200_abcdefgh", "_TZE204_abcdefgh", "_TZE284_abcdefgh"],
            ["_TZ3000_abcdefgh", "_TYZB01_abcdefgh", "_TZE20_abcdefgh", "TZE200_abcdefgh", "_tze200_abcdefgh"],
            id="datapoint_manufacturer",
        ),
        pytest.param(
            tuya.ZCL_MANUFACTURER_PATTERN,
            ["_TZ3000_abcdefgh", "_TZ3210_abcdefgh", "_TYZB01_abcdefgh", tuya.COUNTDOWN_HARMED_MANUFACTURER],
            [
                "_TZE200_abcdefgh",
                "_TZ300_abcdefgh",
                "_TYZB1_abcdefgh",
                "_TYST11_abcdefgh",
                "TZ3000_abcdefgh",
                "Signify Netherlands B.V.",
            ],
            id="zcl_manufacturer",
        ),
        pytest.param(
            tuya.ZCL_MODEL_PATTERN,
            ["TS0001", "TS0011", "TS0505B", "TS0726", "TS0001_switch", "TS0601x", tuya.DATAPOINT_MODEL],
            # A TS011F has three digits, so only its manufacturer string says it is Tuya's.
            [tuya.TS011F_MODEL, "TS130F", "TS011", "TS", "ts0001", "LCT015", "XTS0001"],
            id="zcl_model",
        ),
    ],
)
def test_a_pattern_fully_matches_its_strings_alone(pattern, matching, others):
    assert [string for string in matching if not re.fullmatch(pattern, string)] == []
    assert [string for string in others if re.fullmatch(pattern, string)] == []


def test_a_pattern_is_named_one_and_every_other_constant_is_a_literal_string():
    """The name says which a rule may use as it is and which it must escape: a `*_PATTERN` holds a regex, and no other
    constant holds anything `re.escape` would change but the `_` of Tuya's manufacturer strings."""
    constants = {name: value for name, value in vars(tuya).items() if name.isupper()}

    assert all(isinstance(value, str) for value in constants.values())
    assert {name for name in constants if name.endswith("_PATTERN")} == {
        "DATAPOINT_MANUFACTURER_PATTERN",
        "ZCL_MANUFACTURER_PATTERN",
        "ZCL_MODEL_PATTERN",
    }
    literals = {name: value for name, value in constants.items() if not name.endswith("_PATTERN")}
    assert [name for name, value in literals.items() if not re.fullmatch(r"\w+", value)] == []


def test_the_harmed_plug_s_model_is_the_ts011f():
    """One string, named once: the model both stacks' countdown rules read is the reported plug's."""
    assert tuya.COUNTDOWN_HARMED_MODEL is tuya.TS011F_MODEL


def test_the_catalog_imports_nothing():
    """Patterns and facts only: a Home Assistant or DeviceSide import would tie both stacks to it."""
    tree = ast.parse(Path(tuya.__file__).read_text())

    assert [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)] == []
