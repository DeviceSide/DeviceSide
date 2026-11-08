# Zigbee2MQTT · set_attributes

| | |
|---|---|
| Result | pass |
| Date | 2026-11-08 |
| Source | rig run (`scripts/rig.py`), commit `b39eb15` |
| Profile | lab |
| Home Assistant | 2026.10.4 |
| Device | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1`; Group, firmware `Zigbee2MQTT 2.14.3`; Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `sets_while_off[light_ct]` | `light` (light_ct) | pass |
| `sets_while_off[group]` | `light` (group) | pass |
| `sets_after_a_soft_off[light_ct]` | `light` (light_ct) | pass |
| `sets_after_a_soft_off[group]` | `light` (group) | pass |
| `sets_color_while_off[light_color]` | `light` (light_color) | pass |
| `sets_color_while_off[light_color] observed` | `light` (light_color) | not observed |
| `sets_hs_while_off[light_color]` | `light` (light_color) | pass |
| `sets_hs_while_off[group_color]` | `light` (group_color) | pass |
| `sets_xy_while_off[light_color]` | `light` (light_color) | pass |
| `sets_xy_while_off[group_color]` | `light` (group_color) | pass |
| `min_brightness_raises[light_ct]` | `light` (light_ct) | pass |
| `min_brightness_raises[group]` | `light` (group) | pass |
| `min_brightness_leaves_brighter[light_ct]` | `light` (light_ct) | pass |
| `min_brightness_leaves_brighter[group]` | `light` (group) | pass |
| `max_brightness_lowers[light_ct]` | `light` (light_ct) | pass |
| `max_brightness_lowers[group]` | `light` (group) | pass |

Tests marked `not observed` had nobody watching.
