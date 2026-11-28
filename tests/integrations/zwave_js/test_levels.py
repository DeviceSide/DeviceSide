"""The Multilevel Switch level (0 to 99) and DeviceSide's brightness percent, both ways."""

import pytest

from custom_components.deviceside.integrations.zwave_js.levels import MAX_LEVEL, level_to_percent, percent_to_level


@pytest.mark.parametrize(("level", "percent"), [(0, 0.0), (1, 1.0), (2, 2.0), (50, 50.5), (98, 99.0), (99, 100.0)])
def test_a_level_reads_as_a_percent_to_one_decimal(level, percent):
    assert level_to_percent(level) == percent


@pytest.mark.parametrize(
    ("percent", "level"),
    [(0, 0), (-5, 0), (0.1, 1), (0.4, 1), (0.5, 1), (1, 1), (1.4, 1), (50, 50), (99, 98), (99.5, 99), (100, 99)],
)
def test_a_percent_maps_to_a_level_with_a_floor_of_one(percent, level):
    """Any lit percent is at least level 1, the lowest the light has: never rounded down to off."""
    assert percent_to_level(percent) == level


def test_every_level_round_trips():
    assert [percent_to_level(level_to_percent(level)) for level in range(MAX_LEVEL + 1)] == list(range(MAX_LEVEL + 1))
