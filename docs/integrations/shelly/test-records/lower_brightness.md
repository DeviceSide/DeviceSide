# Shelly · lower_brightness

| | |
|---|---|
| Result | pass |
| Ran | 1 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `5aa4aa4` |
| Home Assistant | 2026.10.4 |
| Device | Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `lower_to_off[group]` | group: none in the profile | skipped |
| `light_raised_mid_room_lower[group]` | group: none in the profile | skipped |
