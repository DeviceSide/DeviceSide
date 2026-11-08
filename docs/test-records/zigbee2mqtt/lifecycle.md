# Zigbee2MQTT · lifecycle

| | |
|---|---|
| Result | pass |
| Date | 2026-11-07 |
| Source | rig run (`scripts/rig.py`), commit `cbc2156` |
| Profile | lab |
| Home Assistant | 2026.10.4 |
| Device | Hue white ambiance E27 1100lm with Bluetooth (`9290024684`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `works_after_a_reload[switch_plug]` | switch_plug: none in the profile | skipped |
| `works_after_a_reload[light_ct]` | `light` (light_ct) | pass |
| `refuses_while_disabled[switch_plug]` | switch_plug: none in the profile | skipped |
| `refuses_while_disabled[light_ct]` | `light` (light_ct) | pass |
