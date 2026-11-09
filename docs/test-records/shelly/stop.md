# Shelly · stop

| | |
|---|---|
| Result | pass |
| Date | 2026-11-09 |
| Source | rig run (`scripts/rig.py`), commit `63b2d95` |
| Profile | shelly |
| Home Assistant | 2026.10.4 |
| Device | Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `halts_a_raise[light_ct]` | `light` (light_ct) | pass |
| `halts_a_raise[group]` | group: none in the profile | skipped |
| `halts_a_lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `halts_a_lower_to_off[group]` | group: none in the profile | skipped |
| `stop_when_idle[light_ct]` | `light` (light_ct) | pass |
| `halts_brightness_and_saturation[light_color]` | light_color: none in the profile | skipped |
| `halts_brightness_and_saturation[light_color] observed` | light_color: none in the profile | skipped |
| `halts_brightness_and_saturation[group_color]` | group_color: none in the profile | skipped |
