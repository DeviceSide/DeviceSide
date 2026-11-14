# Matter · turn_on_for

| | |
|---|---|
| Result | pass |
| Ran | 1 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `308bd61` |
| Home Assistant | 2026.10.4 |
| Device | WiZ Smart Plug (`8979`), firmware `v1.4` |

## Tests

| Test | Target | Result |
|---|---|---|
| `on_then_off[switch_plug]` | `switch` (switch_plug) | pass |
| `drops_brightness_on_a_wrapper[light_wrapped]` | light_wrapped: none in the profile | skipped |
| `bulb_on_then_off[light_dimmable]` | light_dimmable: none in the profile | skipped |
