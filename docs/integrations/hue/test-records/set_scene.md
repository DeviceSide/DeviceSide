# Hue · set_scene

| | |
|---|---|
| Result | pass |
| Ran | 2 passed, 0 skipped |
| Date | 2026-11-13 |
| Source | rig run (`scripts/rig.py`), commit `4c074d9` |
| Home Assistant | 2026.10.4 |
| Device | Zone, firmware `unknown`; Hue ambiance lamp (`LTA009`), firmware `1.163.1` |

## Tests

| Test | Target | Result |
|---|---|---|
| `sets_while_off[scene]` | `scene` (scene) | pass |
| `applies_while_on[scene]` | `scene` (scene) | pass |
