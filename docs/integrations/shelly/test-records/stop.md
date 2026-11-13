# Shelly · stop

| | |
|---|---|
| Result | pass |
| Ran | 3 passed, 5 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `5aa4aa4` |
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
| `halts_brightness_and_saturation[light_color]` | light_color | skipped |
| `halts_brightness_and_saturation[light_color] observed` | light_color | skipped |
| `halts_brightness_and_saturation[group_color]` | group_color | skipped |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `halts_brightness_and_saturation[light_color] observed`: none on file
