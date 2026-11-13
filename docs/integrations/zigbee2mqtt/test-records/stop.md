# Zigbee2MQTT · stop

| | |
|---|---|
| Result | pass |
| Ran | 9 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `e385562` |
| Home Assistant | 2026.10.4 |
| Device | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1`; Group, firmware `Zigbee2MQTT 2.14.3`; Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `halts_a_raise[light_ct]` | `light` (light_ct) | pass |
| `halts_a_raise[group]` | `light` (group) | pass |
| `halts_a_lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `halts_a_lower_to_off[light_ct] observed` | light_ct | skipped |
| `halts_a_lower_to_off[group]` | `light` (group) | pass |
| `stop_when_idle[light_ct]` | `light` (light_ct) | pass |
| `halts_brightness_and_saturation[light_color]` | `light` (light_color) | pass |
| `halts_brightness_and_saturation[light_color] observed` | light_color | skipped |
| `halts_brightness_and_saturation[group_color]` | `light` (group_color) | pass |
| `halts_brightness_and_hue[light_color]` | `light` (light_color) | pass |
| `halts_brightness_and_hue[group_color]` | `light` (group_color) | pass |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `halts_a_lower_to_off[light_ct] observed`: none on file
- `halts_brightness_and_saturation[light_color] observed`: none on file
