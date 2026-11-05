# Shelly · set_auto_on

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
| `applies_to_any_turn_off[switch_plug]` | switch_plug: none in the profile | skipped |
| `applies_to_any_turn_off[light_color]` | `light` (light_color) | pass |
| `takes_the_bounds[switch_plug]` | switch_plug: none in the profile | skipped |
| `takes_the_bounds[light_color]` | `light` (light_color) | pass |
