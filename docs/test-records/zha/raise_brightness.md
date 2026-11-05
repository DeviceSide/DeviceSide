# ZHA · raise_brightness

| | |
|---|---|
| Result | pass |
| Date | 2026-11-03 |
| Source | rig run (`scripts/rig.py`), commit `0bd4f6d` |
| Profile | lab |
| Home Assistant | 2026.10.2 |
| Device | LTA009, firmware `0x01002a00`; ZBDongle-E, firmware `unknown` |

## Tests

| Test | Target | Result |
|---|---|---|
| `raise[light_ct]` | `light` (light_ct) | pass |
| `raise[group]` | `light` (group) | pass |
| `raise_from_off[light_ct]` | `light` (light_ct) | pass |
| `raise_from_off[group]` | `light` (group) | pass |
| `raise_after_soft_off[light_ct]` | `light` (light_ct) | pass |
| `raise_after_soft_off[group]` | `light` (group) | pass |
| `raise_stop_raise[light_ct]` | `light` (light_ct) | pass |
| `raise_stop_raise[group]` | `light` (group) | pass |
