# Shelly · set_auto_off

| | |
|---|---|
| Result | pass |
| Date | 2026-11-08 |
| Source | rig run (`scripts/rig.py`), commit `e0b8ea9` |
| Profile | shelly_bulb |
| Home Assistant | 2026.10.4 |
| Device | Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `applies_to_any_turn_on[switch_plug]` | switch_plug: none in the profile | skipped |
| `applies_to_any_turn_on[light_color]` | `light` (light_color) | pass |
| `takes_the_bounds[switch_plug]` | switch_plug: none in the profile | skipped |
| `takes_the_bounds[light_color]` | `light` (light_color) | pass |
| `turn_on_for_shorter_wins_per_call[switch_plug]` | switch_plug: none in the profile | skipped |
| `turn_on_for_shorter_wins_per_call[light_color]` | `light` (light_color) | pass |
| `turn_on_for_longer_wins_per_call[switch_plug]` | switch_plug: none in the profile | skipped |
| `turn_on_for_longer_wins_per_call[light_color]` | `light` (light_color) | pass |
