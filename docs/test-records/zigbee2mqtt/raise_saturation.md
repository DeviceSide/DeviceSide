# Zigbee2MQTT · raise_saturation

| | |
|---|---|
| Result | pass |
| Date | 2026-11-04 |
| Source | rig run (`scripts/rig.py`), commit `c3c83fe` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2`; Group, firmware `Zigbee2MQTT 2.14.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `saturation_to_a_limit[light_color]` | `light` (light_color) | pass |
| `saturation_to_a_limit[group_color]` | `light` (group_color) | pass |
| `saturation_stop_raise[light_color]` | `light` (light_color) | pass |
| `saturation_stop_raise[group_color]` | `light` (group_color) | pass |
