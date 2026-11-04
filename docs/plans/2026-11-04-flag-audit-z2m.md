# Zigbee2MQTT flag audit (4 Nov)

Which Z2M adapters' committed test records prove their whole `AdapterScope`, under CLAUDE.md's "Clearing it" and
"Proof follows the call". Base `release/v0.0.2` at `b57bea3` (#196 included; it touches no adapter, record or step
file). `move*.md` is the retired action and is never cited.

No Z2M adapter has `options`, and every one has `capabilities=None`, so the scope to prove is `domains` (`light` for
all) and `fields`. A group publishes to a different topic from a light, so a `native_groups` adapter also needs its
group case, though the rule doesn't name it. Cases whose roles are out of scope don't count against an adapter:
`switch_plug` is a switch, and `light_wrapped` resolves to the switch it wraps (`core/resolver.py`).

## Verdicts

| Adapter | Scope item | Record and case | Verdict |
|---|---|---|---|
| `get_attributes` | `light` | `get_attributes.md` (5d39db8): `reads_while_off[light_ct]`, `[group]`, `reads_xy_while_off[light_color]`, `reads_a_group_timer[group]`, `reads_a_running_timer[light_dimmable]` | **clear** |
| `turn_on_for` | `light` | `turn_on_for.md` (5d39db8): `bulb_on_then_off[light_dimmable]`, `group_on_then_off[group]` | **clear** |
| | `brightness` | `bulb_brightness_then_off[light_dimmable]` | |
| | `color_temp_kelvin` | `bulb_color_temp_then_off[light_ct]` | |
| | `hs_color` | `bulb_hs_then_off[light_color]` | |
| | `rgb_color` | `bulb_rgb_then_off[light_color]` | |
| | `xy_color` | `bulb_xy_then_off[light_color]` | |
| | `transition` | `bulb_transition_then_off[light_dimmable]` | |
| `raise_brightness` | `light`, `brightness` | `raise_brightness.md` (f5db697): `raise`, `raise_from_off`, `raise_after_soft_off`, `raise_stop_raise`, each `[light_ct]` and `[group]` | **clear** (note 1) |
| `lower_brightness` | `light`, `brightness` | `lower_brightness.md` (f5db697): `lower_to_off`, `lower_to_a_limit`, `lower_stop_lower`, each `[light_ct]` and `[group]`; `light_raised_mid_room_lower[group]` | **clear** (note 1) |
| `raise_hue` | `light`, `hue` | `raise_hue.md` (5d39db8): `cycles_up_the_wheel[light_color]`, `[group_color]` | **clear** |
| `raise_saturation` | `light`, `saturation` | `raise_saturation.md` (5d39db8): `saturation_to_a_limit[light_color]`, `[group_color]` | **clear** |
| `lower_saturation` | `light`, `saturation` | `lower_saturation.md` (5d39db8): `saturation_to_a_limit[light_color]`, `[group_color]` | **clear** |
| `lower_hue` | `light`, `hue` | `lower_hue.md` (37ffeaa, before the lab): `cycles_down_the_wheel[light_color]` only; `[group_color]` skipped | **flagged**: no group case |
| `set_attributes` | `light`, `brightness`, `color_temp_kelvin` | `set_attributes.md` (f76c08f): `sets_while_off`, `sets_after_a_soft_off`, each `[light_ct]` and `[group]` | **flagged**: `rgb_color` |
| | `hs_color` | `sets_hs_while_off[light_color]`, `[group_color]` | |
| | `xy_color` | `sets_xy_while_off[light_color]`, `[group_color]` | |
| | `rgb_color` | `sets_color_while_off[light_color]` passes unattended; its observed case is `not observed` | |
| | `min_brightness` | `min_brightness_raises`, `min_brightness_leaves_brighter`, each `[light_ct]` and `[group]` | |
| | `max_brightness` | `max_brightness_lowers[light_ct]`, `[group]` | |
| `stop` | `light` | `stop.md` (0558894): every unattended case passes on `light_ct`, `group`, `light_color` and `group_color`; three observed cases are `not observed` | **flagged**: observed cases |

Notes:

1. Both brightness records predate #181, which added `Z2MCallResolver` to `fade.py`. It drops a light's prediction
   when HA sends it a light call and leaves the published payload as it was (the moved helpers are identical in
   `core/transition.py`), so the call these records prove is unchanged. `stop.md` (0558894, after #181) also calls
   both adapters on `light_ct` and `group` in `halts_a_raise` and `halts_a_lower_to_off`, and they pass. The rig run
   before the RC covers the rest.
2. `set_attributes.md` predates #192's last change (a mismatched read is retried twice before `not_stored`). That is a
   fix the rig covers, and the watched rerun below writes a fresh record anyway.
3. Lab `light_color` is the A60 (`LCA016` in the records), and `group_color` is the rig-made group of it, as TODO's
   "Z2M A60 run" asks. #196 notes this bulb sometimes drops a read over a healthy link, so a failed setup read there is
   worth one rerun before suspecting the adapter.
4. `light_onoff` (a Z2M on/off-only light) is skipped in `turn_on_for.md` and `get_attributes.md`, but it is in scope
   by domain. It gets the same `genOnOff` `OnWithTimedOff` and the same read as `light_dimmable`, so the bulb's record
   proves it under "Proof follows the call". `turn_on_for`'s scope comment says Zigbee relays rarely honor that
   command, though, and a relay module that Z2M exposes as a light would be one. See proposal B.

## Cases still needed

Each observed case is in the step file's `observe:` and is marked `not observed` in its record.

| Adapter | Case | Where |
|---|---|---|
| `lower_hue` | `cycles_down_the_wheel[light_color]` and `[group_color]` (no `observe:`) | unattended lab: `scripts/rig.py --profile lab --integration zigbee2mqtt --action lower_hue` |
| `set_attributes` | `sets_color_while_off[light_color]` observed, with the rest of the suite for a fresh record | watched lab session |
| `stop` | `halts_a_lower_to_off[light_ct]` observed (its `observe:` is Z2M only) | watched lab session |
| `stop` | `hue_cycle_stop[light_color]` observed | watched lab session |
| `stop` | `saturation_down_stop[light_color]` observed | watched lab session |

All four observed cases fit one watched lab session, with Z2M `stop` and `set_attributes` on the lab bench. None
needs the house profile. Its fixed bulbs add nothing that these cases ask for.

## Proposals (design calls, not made here)

- **A. `lower_hue` without a group run.** Narrowing it to `native_groups=False` would drop group support that
  `raise_hue` already has proven, and expand groups into members instead. Not recommended: the unattended rerun is
  cheaper.
- **B. On/off-only Z2M lights in `turn_on_for`.** If relay modules exposed as lights are a risk, set `capabilities`
  so only lights with a level cluster are in scope, as was done for switches. Not needed by the rule. It's a question
  of how far "Proof follows the call" should stretch for devices that may not honor the command.
