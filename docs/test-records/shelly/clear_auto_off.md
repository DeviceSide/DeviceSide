# Shelly · clear_auto_off

| | |
|---|---|
| Result | pass |
| Date | 2026-11-05 |
| Source | rig run (`scripts/rig.py`), commit `5215989` |
| Profile | shelly_bulb |
| Home Assistant | 2026.10.2 |
| Device | Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `clears[switch_plug]` | switch_plug: none in the profile | skipped |
| `clears[light_color]` | `light` (light_color) | pass |
| `unchanged_when_clear[switch_plug]` | switch_plug: none in the profile | skipped |
| `unchanged_when_clear[light_color]` | `light` (light_color) | pass |
| `countdown_survives_a_clear[switch_plug]` | switch_plug: none in the profile | skipped |
| `countdown_survives_a_clear[light_color]` | `light` (light_color) | pass |
