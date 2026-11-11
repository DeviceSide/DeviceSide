# ZHA · lower_saturation

| | |
|---|---|
| Result | pass |
| Date | 2026-11-08 |
| Source | rig run (`scripts/rig.py`), commit `8aae106` |
| Home Assistant | 2026.10.4 |
| Device | LCA016, firmware `0x01001200` |

## Tests

| Test | Target | Result |
|---|---|---|
| `saturation_to_a_limit[light_color]` | `light` (light_color) | pass |
| `saturation_to_a_limit[group_color]` | group_color: none in the profile | skipped |
