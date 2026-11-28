"""Z-Wave's Multilevel Switch levels and DeviceSide's percent, both ways.

A level is 0 to 99 (docs/research/2026-11-27-zwave-call-patterns.md, section 2: 0 is off, 99 full, 255 "restore
previous" on a Set, which this never sends), so the lowest lit level, 1, is about 1 %, coarser than a Zigbee light's.
The floor follows core: HA maps brightness to a level with a floor of 1 for any lit brightness (HA/light.py#L96-L101,
home-assistant/core@66e9f19b16aa03edd174127b65cc80d066b8a39e), and DeviceSide never raises it silently.
"""

MAX_LEVEL = 99  # Multilevel Switch's highest level, "full"


def level_to_percent(level: int) -> float:
    """A level's brightness percent, to one decimal as the other integrations' rows give it: 0 is 0, 99 is 100."""
    return round(level * 100 / MAX_LEVEL, 1)


def percent_to_level(percent: float) -> int:
    """The level for a brightness percent: 0 is off, any other is at least level 1, the lowest the light has, and 100
    is 99."""
    if percent <= 0:
        return 0
    return min(MAX_LEVEL, max(1, round(percent * MAX_LEVEL / 100)))
