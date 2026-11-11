# Hue · lifecycle

| | |
|---|---|
| Result | pass |
| Date | 2026-11-11 |
| Source | rig run (`scripts/rig.py`), commit `32dc547` |
| Home Assistant | 2026.10.4 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `works_after_a_reload[light_ct]` | `light` (light_ct) | pass |
| `refuses_while_disabled[light_ct]` | `light` (light_ct) | pass |
