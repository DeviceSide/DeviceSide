# Shelly · turn_off_for

| | |
|---|---|
| Result | pass |
| Ran | 2 passed, 0 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `5aa4aa4` |
| Home Assistant | 2026.10.4 |
| Device | Shelly 1 Mini Gen3 (`S3SW-001X8EU`), firmware `20261026-122213/2.0.3-g4601943`; Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `off_then_on[switch_plug]` | `switch` (switch_plug) | pass |
| `bulb_off_then_on[light_dimmable]` | `light` (light_dimmable) | pass |
