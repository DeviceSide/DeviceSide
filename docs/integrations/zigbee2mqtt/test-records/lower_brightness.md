# Zigbee2MQTT · lower_brightness

| | |
|---|---|
| Result | pass |
| Ran | 5 passed, 0 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `a47b753` |
| Home Assistant | 2026.10.4 |
| Device | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1`; Group, firmware `Zigbee2MQTT 2.14.3` |

## Tests

| Test | Target | Result |
|---|---|---|
| `lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `lower_to_off[group]` | `light` (group) | pass |
| `lower_to_a_limit[light_ct]` | `light` (light_ct) | pass |
| `lower_to_a_limit[group]` | `light` (group) | pass |
| `light_raised_mid_room_lower[group]` | `light` (group) | pass |
