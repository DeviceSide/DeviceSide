# Shelly · turn_off_for

| | |
|---|---|
| Result | pass |
| Date | 2026-11-05 |
| Source | rig run (`scripts/rig.py`), commit `481b74a` |
| Profile | shelly |
| Home Assistant | 2026.10.2 |
| Device | Shelly 1 Mini Gen4 (`S4SW-001X8EU`), firmware `20261026-122156/2.0.3-g4601943`; Shelly 1 Mini Gen3 (`S3SW-001X8EU`), firmware `20261026-122213/2.0.3-g4601943`; Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `off_then_on[switch_plug]` | `switch` (switch_plug) | pass |
| `off_then_on[light_onoff]` | `light` (light_onoff) | pass |
| `off_then_on[light_wrapped]` | `light` (light_wrapped) | pass |
| `bulb_off_then_on[light_dimmable]` | `light` (light_dimmable) | pass |
