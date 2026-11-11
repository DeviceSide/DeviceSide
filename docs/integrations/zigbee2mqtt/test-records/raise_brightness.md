# Zigbee2MQTT · raise_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-09 |
| Source | rig run (`scripts/rig.py`), commit `be4d36a` |
| Home Assistant | 2026.10.4 |
| Device | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1`; Group, firmware `Zigbee2MQTT 2.14.3` |

## Tests

| Test | Target | Result |
|---|---|---|
| `raise[light_ct]` | `light` (light_ct) | pass |
| `raise[group]` | `light` (group) | pass |
| `raise_after_soft_off[light_ct]` | `light` (light_ct) | pass |
| `raise_after_soft_off[group]` | `light` (group) | pass |
