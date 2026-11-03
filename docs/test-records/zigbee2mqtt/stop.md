# Zigbee2MQTT · stop

| | |
|---|---|
| Result | pass |
| Date | 2026-11-03 |
| Source | rig run (`scripts/rig.py`), commit `0558894` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1`; Hue Essential lamp (`LCA016`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `halts_a_raise[light_ct]` | `light` (light_ct) | pass |
| `halts_a_raise[group]` | `light` (group) | pass |
| `halts_a_lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `halts_a_lower_to_off[light_ct] observed` | `light` (light_ct) | not observed |
| `halts_a_lower_to_off[group]` | `light` (group) | pass |
| `stop_when_idle[light_ct]` | `light` (light_ct) | pass |
| `stop_when_idle[group]` | `light` (group) | pass |
| `hue_cycle_stop[light_color]` | `light` (light_color) | pass |
| `hue_cycle_stop[light_color] observed` | `light` (light_color) | not observed |
| `hue_cycle_stop[group_color]` | `light` (group_color) | pass |
| `saturation_down_stop[light_color]` | `light` (light_color) | pass |
| `saturation_down_stop[light_color] observed` | `light` (light_color) | not observed |
| `saturation_down_stop[group_color]` | `light` (group_color) | pass |
| `halts_brightness_and_saturation[light_color]` | `light` (light_color) | pass |
| `halts_brightness_and_saturation[group_color]` | `light` (group_color) | pass |
| `halts_brightness_and_hue[light_color]` | `light` (light_color) | pass |
| `halts_brightness_and_hue[group_color]` | `light` (group_color) | pass |

Tests marked `not observed` had nobody watching.
