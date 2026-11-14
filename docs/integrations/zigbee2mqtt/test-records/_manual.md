# Zigbee2MQTT · manual sign-offs

| Date | Commit | Tester | Devices | Passed |
|---|---|---|---|---|
| 2026-11-13 | `c868be9` | @jasonmx | `9290024684`, `8720169392182` | `get_attributes`, `lower_brightness`, `lower_hue`, `lower_saturation`, `raise_brightness`, `raise_hue`, `raise_saturation`, `set_attributes`, `stop`, `turn_on_for` |

Why manual, on a rig-covered integration: the rig records here are a whole lab run at `e385562` (8 actions) plus
`stop` and `lower_brightness` rerun at `a47b753` after #407 dropped the soft-off pin from `stop.py`, its only change
to the package since. The gate wants one commit per rig sign-off, and a maintainer judged that `stop.py` could reach
no other action, so no rerun of the rest.
