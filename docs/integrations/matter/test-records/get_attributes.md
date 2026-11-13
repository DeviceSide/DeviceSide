# Matter · get_attributes

| | |
|---|---|
| Result | pass |
| Ran | 2 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `308bd61` |
| Home Assistant | 2026.10.4 |
| Device | WiZ Smart Plug (`8979`), firmware `v1.4` |

## Tests

| Test | Target | Result |
|---|---|---|
| `reads_while_off[light_ct]` | light_ct | skipped |
| `reads_a_running_timer[switch_plug]` | `switch` (switch_plug) | pass |
| `reads_a_running_timer[light_dimmable]` | light_dimmable: none in the profile | skipped |
| `reads_no_timer_after_a_turn_off[switch_plug]` | `switch` (switch_plug) | pass |
