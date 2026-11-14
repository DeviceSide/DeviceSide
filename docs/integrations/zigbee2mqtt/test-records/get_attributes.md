# Zigbee2MQTT · get_attributes

| | |
|---|---|
| Result | pass |
| Ran | 5 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `e385562` |
| Home Assistant | 2026.10.4 |
| Device | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1`; Hue Essential White and Color Ambiance A60 (`8720169392182`), firmware `1.164.2`; Group, firmware `Zigbee2MQTT 2.14.3`; Hue white A60 bulb B22 bluetooth (`9290018217`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `reads_while_off[light_ct]` | `light` (light_ct) | pass |
| `reads_xy_while_off[light_color]` | `light` (light_color) | pass |
| `reads_a_group_timer[group]` | `light` (group) | pass |
| `keeps_and_reads_hs_while_off[light_color]` | `light` (light_color) | pass |
| `reads_a_running_timer[switch_plug]` | switch_plug: none in the profile | skipped |
| `reads_a_running_timer[light_dimmable]` | `light` (light_dimmable) | pass |
| `reads_no_timer_after_a_turn_off[switch_plug]` | switch_plug: none in the profile | skipped |
