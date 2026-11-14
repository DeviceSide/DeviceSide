# Hue · lifecycle

| | |
|---|---|
| Result | pass |
| Ran | 2 passed, 0 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `4c074d9` |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `works_after_a_reload[light_ct]` | `light` (light_ct) | pass |
| `refuses_while_disabled[light_ct]` | `light` (light_ct) | pass |
