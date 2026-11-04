# Hue flag audit (4 Nov)

Which Hue adapters with `experimental=True` the committed records in `docs/test-records/hue/` prove, under
CLAUDE.md's "Clearing it" and "Proof follows the call". Every record is from the lab profile on 3 Nov
(`light_ct`: Hue ambiance lamp LTA009; `light_color`: Hue Essential lamp LCA016; `group`: a Hue zone), at
commit `5d39db8` or `7c2de38`. Neither Hue's adapters, core nor the step files they ran changed after the commit
each record ran on. `move*.md` are from the retired move action and are not cited.

The rig sets each of an adapter's options per suite: on when the step file lists it, off otherwise
(`run` in `tests/rig/engine.py`). So `<action>.md` proves an option off and
`<action>-predicted_state.md` proves it on.

**Result:** four adapters clear (`get_attributes`, `raise_brightness`, `lower_brightness`, `set_scene`); four stay
flagged (`set_attributes`, `stop`, `raise_saturation`, `lower_saturation`).

## Cleared

| Adapter | Scope item | Record and cases | Verdict |
|---|---|---|---|
| `get_attributes` | domain `light` | `get_attributes.md`: `reads_while_off[light_ct]`, `[group]`, `predicts_mid_move[light_ct]`, `[group]`, `reads_color_while_off[light_color]` | proven |
| | fields, options | none in scope | — |
| `raise_brightness` | domain `light` | `raise_brightness.md`: all 12 cases, `light_ct` and `group` | proven |
| | field `brightness` | the same | proven |
| | `predicted_state` off | `raise_brightness.md` | proven |
| | `predicted_state` on | `raise_brightness-predicted_state.md`: all 7 cases | proven |
| `lower_brightness` | domain `light` | `lower_brightness.md`: all 7 cases, `light_ct` and `group` | proven |
| | field `brightness` | the same | proven |
| | `predicted_state` off | `lower_brightness.md` | proven |
| | `predicted_state` on | `lower_brightness-predicted_state.md`: `soft_off_stays_on_until_its_end[light_ct]`, `[group]` | proven |
| `set_scene` | domain `scene` | `set_scene.md`: `sets_while_off[scene]`, `applies_while_on[scene]` | proven |

No observed case is owed on any of them: the only `observe` block in their step files, `lower_brightness.yaml`'s
`soft_off_keeps_level`, is ZHA-only.

Notes, not scope items:

- `get_attributes`: its five skipped cases are timer reads (`turn_on_for`), which Hue has no adapter for. A Hue light
  without dimming (a smart plug) is untested, but the call is the same read of aiohue's cached light resource, which
  then leaves out brightness.
- `set_scene`: the step file leaves out scenes with a light off, All-Day and dynamic scenes, a large room and a second
  bridge (§5.4–5.8). Each replays the scene as the per-light `write_light` calls the record exercised; a light off
  in the scene adds `on: false` to its write, which no record sent. Smart scenes are refused.

## Left flagged

| Adapter | Scope item | Record and cases | Verdict |
|---|---|---|---|
| `set_attributes` | domain `light` | `set_attributes.md`: all 16 automated cases | proven |
| | `brightness`, `color_temp_kelvin` | `sets_while_off[light_ct]`, `[group]`, `sets_after_a_soft_off[light_ct]`, `[group]` | proven |
| | `hs_color` | `sets_hs_while_off[light_color]`, `[group_color]` | proven |
| | `xy_color` | `sets_xy_while_off[light_color]`, `[group_color]`, `clamps_xy_to_the_gamut[light_color]` | proven |
| | `min_brightness` | `min_brightness_raises`, `min_brightness_leaves_brighter`, each `[light_ct]`, `[group]` | proven |
| | `max_brightness` | `max_brightness_lowers[light_ct]`, `[group]` | proven |
| | `rgb_color` | `sets_color_while_off[light_color]` passed automated; its observed case is `not observed` | **owed** |
| `stop` | domain `light` | `stop.md`: all 10 automated cases | proven |
| | `predicted_state` off | `stop.md` | proven, except two observed cases |
| | `predicted_state` on | `stop-predicted_state.md`: all 4 cases | proven |
| | observed | `saturation_down_stop[light_color]`, `halts_brightness_and_saturation[light_color]`: `not observed` | **owed** |
| `raise_saturation` | domain `light`, field `saturation` | `raise_saturation.md`: `saturation_to_a_limit[light_color]`, `[group_color]` | proven |
| | `predicted_state` off | `raise_saturation.md` | proven |
| | `predicted_state` on | none: there is no `raise_saturation-predicted_state.yaml` | **none** |
| `lower_saturation` | domain `light`, field `saturation` | `lower_saturation.md`: `saturation_to_a_limit[light_color]`, `[group_color]` | proven |
| | `predicted_state` off | `lower_saturation.md` | proven |
| | `predicted_state` on | none: there is no `lower_saturation-predicted_state.yaml` | **none** |

`rgb_color` rests on the observation alone: the automated `sets_color_while_off` checks that the light stays off,
and nothing reads its color after the turn on.

### Cases still needed

| Adapter | Case | Where |
|---|---|---|
| `set_attributes` | `sets_color_while_off[light_color]`, observed | watched lab session |
| `stop` | `saturation_down_stop[light_color]`, observed | watched lab session |
| `stop` | `halts_brightness_and_saturation[light_color]`, observed (does the predicted-xy halt jump?) | watched lab session |
| `raise_saturation` | a `raise_saturation-predicted_state.yaml` suite (`options: [predicted_state]`), `light_color` and `group_color` | unattended lab, once the step file exists |
| `lower_saturation` | a `lower_saturation-predicted_state.yaml` suite, the same | unattended lab, once the step file exists |

All three watched cases are in the Hue `stop` and `set_attributes` suites, so one watched lab session
(`--profile lab --integration hue --action stop --action set_attributes`) covers them. The saturation suites need
`light_color` on Hue, which the lab and the house profile (the A60 roaming) both have.

## Proposals (design calls, not made here)

- **Drop `predicted_state` from the saturation scopes**, instead of writing and running the two new suites.
  `HueFade`'s docstring says saturation shows the bridge's end xy at once with the option on too, so the option may
  not change what these adapters do. It does change `report_filter`'s mode (hiding on), so whether it is truly inert
  is for Jason to judge.
- **Read the color back in `sets_color_while_off`** (an `expect_state` on `hs_color` after the turn on), so
  `rgb_color`'s value is proven unattended. The observation would still be needed for the flash of the old color.
