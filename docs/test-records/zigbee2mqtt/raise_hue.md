# Zigbee2MQTT · raise_hue

| | |
|---|---|
| Result | pass |
| Date | 2026-11-03 |
| Source | rig run (`scripts/rig.py`), commit `5d39db8` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue Essential lamp (`LCA016`), firmware `1.164.2` |

## Tests

| Test | Target | Result |
|---|---|---|
| `cycles_up_the_wheel[light_color]` | `light` (light_color) | pass |
| `cycles_up_the_wheel[group_color]` | `light` (group_color) | pass |
