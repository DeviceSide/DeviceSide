# Zigbee2MQTT · lower_saturation

| | |
|---|---|
| Result | pass |
| Date | 2026-11-02 |
| Source | rig run (`scripts/rig.py`), commit `f5db697` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue Essential lamp (`LCA016`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `saturation_to_a_limit[light_color]` | `light` (light_color) | pass |
| `saturation_to_a_limit[group_color]` | `light` (group_color) | pass |
