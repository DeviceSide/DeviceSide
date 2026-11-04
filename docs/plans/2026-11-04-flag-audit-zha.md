# ZHA flag audit (2026-11-04)

Which ZHA adapters the committed lab records prove across their whole `AdapterScope`, under CLAUDE.md's "Clearing it"
and "Proof follows the call". Every ZHA adapter has `domains={"light"}`, `capabilities=None` (ZHA has no capability
split) and no `options`, so the items to prove are the light domain and each field.

A test with an `observe:` block proves its scope only when its observed case passes too
(`2026-10-26-rig-observed-tests.md`, Records). An observed case owed keeps its adapter flagged, even where other
tests cover the same scope items.

Every record below is from the lab profile, on the commit that ships: no ZHA, core or action code changed after
`5d39db8` except `zha/set_attributes.py` in #197, whose record ran on that change (`ee3371b`). The step files changed
since only by setup waits and one Hue-only setup color, so each case sends the calls it did then. Devices: `LTA009`
(light_ct and group member), `LWA012` (light_dimmable), `LCA016` (light_color).

## Verdicts

| Adapter | Scope item: record, case | Verdict |
|---|---|---|
| `get_attributes` | light: `get_attributes.md`, `reads_while_off[light_ct]`, `[group]`, `reads_color_while_off[light_color]`, `reads_a_running_timer[light_dimmable]` | **clear** |
| `raise_brightness` | light, brightness: `raise_brightness.md`, `raise`, `raise_from_off`, `raise_after_soft_off`, `raise_stop_raise`, each `[light_ct]` and `[group]` | **clear** |
| `lower_brightness` | light, brightness: `lower_brightness.md`, `lower_to_off`, `lower_to_a_limit`, `lower_stop_lower`, each `[light_ct]` and `[group]`; `light_raised_mid_room_lower[group]`. Owed: `soft_off_keeps_level[light_ct] observed`, `[group] observed` (not observed) | flagged |
| `raise_hue` | light, hue: `raise_hue.md`, `cycles_up_the_wheel[light_color]`; groupcast: composed group proof, the brightness `[group]` cases (proposal 2) | **clear** |
| `lower_hue` | light, hue: `lower_hue.md`, `cycles_down_the_wheel[light_color]`; groupcast: composed group proof, the brightness `[group]` cases (proposal 2) | **clear** |
| `raise_saturation` | light, saturation: `raise_saturation.md`, `saturation_to_a_limit[light_color]`; groupcast: composed group proof, the brightness `[group]` cases (proposal 2) | **clear** |
| `lower_saturation` | light, saturation: `lower_saturation.md`, `saturation_to_a_limit[light_color]`; groupcast: composed group proof, the brightness `[group]` cases (proposal 2) | **clear** |
| `stop` | light: `stop.md`, `halts_a_raise`, `halts_a_lower_to_off`, `stop_when_idle`, each `[light_ct]` and `[group]`; color halts on `[light_color]`. Owed: `hue_cycle_stop[light_color] observed`, `saturation_down_stop[light_color] observed` (not observed) | flagged |
| `set_attributes` | light, brightness, color_temp_kelvin: `set_attributes.md`, `sets_while_off`, `sets_after_a_soft_off`, each `[light_ct]` and `[group]`; hs_color: `sets_hs_while_off[light_color]`; xy_color: `sets_xy_while_off[light_color]`; min_brightness: `min_brightness_raises`, `min_brightness_leaves_brighter`, each `[light_ct]` and `[group]`; max_brightness: `max_brightness_lowers[light_ct]`, `[group]`; rgb_color: none (only `sets_color_while_off[light_color]` sends it, and its observed case is not observed; the automated case checks only that the light stays off) | flagged |
| `turn_on_for` | light: `turn_on_for.md`, `bulb_on_then_off[light_dimmable]`, `group_on_then_off[group]`; brightness: `bulb_brightness_then_off[light_dimmable]`, `group_brightness_then_off[group]`; color_temp_kelvin: `bulb_color_temp_then_off[light_ct]` | **clear** |

## Cases still needed

| Adapter | Case | Where |
|---|---|---|
| `lower_brightness` | `soft_off_keeps_level[light_ct] observed`, `soft_off_keeps_level[group] observed` | watched lab session (white bulb and ZHA group) |
| `stop` | `hue_cycle_stop[light_color] observed`, `saturation_down_stop[light_color] observed` | watched color session, the color bulb on ZHA |
| `set_attributes` | `sets_color_while_off[light_color] observed` | watched color session, the color bulb on ZHA |

None needs the house profile. All five fit one watched session per bulb, filtered to `lower_brightness`, `stop` and
`set_attributes`; the automated twins already pass.

## Differs from the brief

The brief listed only `sets_color_while_off` as owed on ZHA, as does TODO's "ZHA A60 run". The step files owe four
more: #167 (3 Nov) widened `hue_cycle_stop` and `saturation_down_stop` to ZHA and added the ZHA-only
`soft_off_keeps_level`, each with an `observe:` block and no `observe: only:`, after the 9d ledger (#134, 31 Oct)
pruned observed cases.

## Proposals (both decided by Jason on 4 Nov: `2026-11-04-flag-clearing-follow-up.md`)

1. **Ledger the three blocks #167 added.** Keep them watched, or judge them deducible and limit each `observe:` with
   `only:`. The ledger made the Z2M `hue_cycle_stop` and `saturation_down_stop` watched because a Hue bulb's output
   departs from what it reports mid-fade, and the ZHA cases run the same bulb, so watching them looks right.
   `soft_off_keeps_level` checks HA's level after the plain on, not a dim start or a glow while dark.
2. **Color groupcast on ZHA.** `fade.py` sends one groupcast when every member of a ZHA group moves. The hue and
   saturation groupcast never ran: every `group_color` case skips, as ZHA makes no entity for the lab's one-member
   color group. Under the composed group proof (CLAUDE.md, "Proof follows the call"), the path is proven by the
   brightness groupcasts of the same `fade.py` class (`raise_brightness.md` and `lower_brightness.md`, each case's
   `[group]`), and each color command by its `[light_color]` case, so the four color ramps are cleared. A second color
   bulb in a ZHA group would still run it end to end.
