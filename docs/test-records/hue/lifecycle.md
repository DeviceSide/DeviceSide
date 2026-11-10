# Hue · lifecycle

| | |
|---|---|
| Result | pass |
| Date | 2026-11-10 |
| Source | rig run (`scripts/rig.py`), commit `c2916f1` |
| Profile | lab |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `works_after_a_reload[light_ct]` | `light` (light_ct) | pass |
| `refuses_while_disabled[light_ct]` | `light` (light_ct) | pass |
