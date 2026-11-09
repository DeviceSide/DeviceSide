# Zigbee2MQTT · raise_saturation

| | |
|---|---|
| Result | pass |
| Date | 2026-11-09 |
| Source | rig run (`scripts/rig.py`), commit `8cbd97f` |
| Profile | lab |
| Home Assistant | 2026.10.4 |
| Device | Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2`; Group, firmware `Zigbee2MQTT 2.14.3` |

## Tests

| Test | Target | Result |
|---|---|---|
| `saturation_to_a_limit[light_color]` | `light` (light_color) | pass |
| `saturation_to_a_limit[group_color]` | `light` (group_color) | pass |
| `saturation_stop_raise[light_color]` | `light` (light_color) | pass |
| `saturation_stop_raise[group_color]` | `light` (group_color) | pass |
