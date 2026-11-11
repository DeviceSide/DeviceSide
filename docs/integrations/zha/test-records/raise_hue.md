# ZHA · raise_hue

| | |
|---|---|
| Result | pass |
| Date | 2026-11-06 |
| Source | rig run (`scripts/rig.py`), commit `1600b87` |
| Home Assistant | 2026.10.2 |
| Device | LCA016, firmware `0x01001200` |

## Tests

| Test | Target | Result |
|---|---|---|
| `cycles_up_the_wheel[light_color]` | `light` (light_color) | pass |
| `cycles_up_the_wheel[group_color]` | group_color: none in the profile | skipped |
| `hue_stop_raise[light_color]` | `light` (light_color) | pass |
| `hue_stop_raise[group_color]` | group_color: none in the profile | skipped |
