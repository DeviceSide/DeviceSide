# Shelly · raise_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-11 |
| Source | rig run (`scripts/rig.py`), commit `3507e87` |
| Profile | shelly |
| Home Assistant | 2026.10.4 |
| Device | Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `raise[light_ct]` | `light` (light_ct) | pass |
| `raise[group]` | group: none in the profile | skipped |
| `raise_after_soft_off[light_ct]` | `light` (light_ct) | pass |
| `raise_after_soft_off[group]` | group: none in the profile | skipped |
