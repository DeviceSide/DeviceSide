# Zigbee2MQTT · turn_on_for

| | |
|---|---|
| Result | pass |
| Ran | 7 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `e385562` |
| Home Assistant | 2026.10.4 |
| Device | Hue white A60 bulb B22 bluetooth (`9290018217`), firmware `1.163.1`; Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1`; Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2`; Group, firmware `Zigbee2MQTT 2.14.3` |

## Tests

| Test | Target | Result |
|---|---|---|
| `on_then_off[switch_plug]` | switch_plug: none in the profile | skipped |
| `drops_brightness_on_a_wrapper[light_wrapped]` | light_wrapped: none in the profile | skipped |
| `bulb_on_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `bulb_color_temp_then_off[light_ct]` | `light` (light_ct) | pass |
| `bulb_transition_then_off[light_dimmable]` | `light` (light_dimmable) | pass |
| `bulb_rgb_then_off[light_color]` | `light` (light_color) | pass |
| `bulb_hs_then_off[light_color]` | `light` (light_color) | pass |
| `bulb_xy_then_off[light_color]` | `light` (light_color) | pass |
| `group_on_then_off[group]` | `light` (group) | pass |
