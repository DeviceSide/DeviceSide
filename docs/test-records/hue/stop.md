# Hue · stop

| | |
|---|---|
| Result | pass |
| Date | 2026-11-02 |
| Source | rig run (`scripts/rig.py`), commit `f5db697` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `halts_a_raise[light_ct]` | `light` (light_ct) | pass |
| `halts_a_raise[group]` | `light` (group) | pass |
| `halts_a_lower_to_off[light_ct]` | `light` (light_ct) | pass |
| `halts_a_lower_to_off[group]` | `light` (group) | pass |
| `stop_when_idle[light_ct]` | `light` (light_ct) | pass |
| `stop_when_idle[group]` | `light` (group) | pass |
