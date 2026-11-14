# ZHA · raise_hue

| | |
|---|---|
| Result | pass |
| Ran | 1 passed, 2 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `7b50c5b` |
| Home Assistant | 2026.10.4 |
| Device | LCA016, firmware `0x01001200` |

## Tests

| Test | Target | Result |
|---|---|---|
| `hue_stop_raise[light_color]` | `light` (light_color) | pass |
| `hue_stop_raise[light_color] observed` | light_color | skipped |
| `hue_stop_raise[group_color]` | group_color: none in the profile | skipped |

Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:

- `hue_stop_raise[light_color] observed`: none on file
