# Shelly · get_attributes

| | |
|---|---|
| Result | pass |
| Ran | 6 passed, 0 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `308bd61` |
| Home Assistant | 2026.10.4 |
| Device | Shelly Multicolor Bulb Gen3 (`S3BL-C010007AEU`), firmware `20261026-122229/2.0.3-g4601943`; Shelly 1 Mini Gen3 (`S3SW-001X8EU`), firmware `20261026-122213/2.0.3-g4601943` |

## Tests

| Test | Target | Result |
|---|---|---|
| `reads_while_off[light_ct]` | `light` (light_ct) | pass |
| `reads_rgb_while_off[light_color]` | `light` (light_color) | pass |
| `reads_a_running_timer[switch_plug]` | `switch` (switch_plug) | pass |
| `reads_a_running_timer[light_dimmable]` | `light` (light_dimmable) | pass |
| `reads_no_timer_after_a_turn_off[switch_plug]` | `switch` (switch_plug) | pass |
| `reads_an_auto_on_timer[switch_plug]` | `switch` (switch_plug) | pass |
