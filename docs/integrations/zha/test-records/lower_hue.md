# ZHA · lower_hue

| | |
|---|---|
| Result | pass |
| Date | 2026-11-07 |
| Source | rig run (`scripts/rig.py`), commit `1de5a51` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | LCA016, firmware `0x01001200` |

## Tests

| Test | Target | Result |
|---|---|---|
| `cycles_down_the_wheel[light_color]` | `light` (light_color) | pass |
| `cycles_down_the_wheel[group_color]` | group_color: none in the profile | skipped |
