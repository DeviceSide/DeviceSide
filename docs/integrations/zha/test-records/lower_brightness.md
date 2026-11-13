# ZHA · lower_brightness

| | |
|---|---|
| Result | pass |
| Ran | 5 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `7b50c5b` |
| Home Assistant | 2026.10.4 |
| Device | LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `lower_to_off[group]` | `light` (group) | pass |
| `soft_off_keeps_level[light_ct]` | light_ct | skipped |
| `soft_off_keeps_level[group]` | group | skipped |
| `lower_to_a_limit[light_ct]` | `light` (light_ct) | pass |
| `lower_to_a_limit[group]` | `light` (group) | pass |
| `light_raised_mid_room_lower[group]` | `light` (group) | pass |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `soft_off_keeps_level[light_ct]`: none on file
- `soft_off_keeps_level[group]`: none on file
