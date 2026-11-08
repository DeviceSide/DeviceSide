# Shelly · lifecycle

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
| `works_after_a_reload[switch_plug]` | switch_plug: none in the profile | skipped |
| `works_after_a_reload[light_ct]` | `light` (light_ct) | pass |
| `refuses_while_disabled[switch_plug]` | switch_plug: none in the profile | skipped |
| `refuses_while_disabled[light_ct]` | `light` (light_ct) | pass |
