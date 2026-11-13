# Zigbee2MQTT · lower_brightness

| | |
|---|---|
| Result | pass |
| Ran | 5 passed, 0 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `308bd61` |
| Home Assistant | 2026.10.4 |
| Device | Zigbee LED 9W A19 bulb, dimmable & tunable (`ZL1000100-CCT-US-V1A02`), firmware `2.2`; Group, firmware `Zigbee2MQTT 2.14.3` |

## Tests

| Test | Target | Result |
|---|---|---|
| `lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `lower_to_off[group]` | `light` (group) | pass |
| `lower_to_a_limit[light_ct]` | `light` (light_ct) | pass |
| `lower_to_a_limit[group]` | `light` (group) | pass |
| `light_raised_mid_room_lower[group]` | `light` (group) | pass |
