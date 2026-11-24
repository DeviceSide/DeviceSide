# Matter lights: set while off, raise/lower, stop (2026-11-24)

## Context

Matter has 247k installs (42% of HA) and is growing fastest, but DeviceSide gives it only `turn_on_for` and
`get_attributes`. HA's matter light sends brightness as `MoveToLevelWithOnOff`, so it can't set a light while it's off
(open core issue home-assistant/core#175904; set-while-off is the most-asked feature in the demand sample). It also
has no hold-to-dim and no stop. Ranked #1 in `notes/2026-11-24-next-classes-by-reach.md`. Outcome: `set_attributes`,
`raise/lower_brightness`, `raise/lower_saturation`, `raise/lower_hue` and `stop` on Matter lights, all in Labs.

Research: [`docs/integrations/matter/research/2026-11-24-level-color.md`](../integrations/matter/research/2026-11-24-level-color.md)
(SHA-pinned), committed with this plan; step 1 checks its pinned links.

## Coordination

Intent: Matter lights get set_attributes (ExecuteIfOff), raise/lower brightness, saturation and hue, and stop, in Labs on certified single- and multi-endpoint nodes.
Touches: custom_components/deviceside/integrations/matter/**, custom_components/deviceside/core/level_fade.py, custom_components/deviceside/core/zcl.py, custom_components/deviceside/integrations/zha/zcl.py, tests/integrations/matter/**, docs/integrations/matter/**, docs/device-compatibility.md, README.md, docs/deferred.md, docs/plans/2026-11-24-matter-light-actions.md

## Decisions

1. **No rig run.** No Matter light is on the rig. Everything ships in Labs, admitted by research (evidence.md, In
   Labs). Device reports are the way up. Tenet 8: no decision waits on a run.
2. **Classes:** `labs(OTHER, MULTI_ENDPOINT)` on every new adapter. `bridged` and `uncertified` are not built and are
   left out of `capabilities`, with no `NotBuilt` entries, because these actions don't harm and the registry refuses
   such an entry. Why multi_endpoint is in: it was split off because certification runs the timer reads on one
   endpoint, and writes earn no certification credit anyway. The Level and Color server is per endpoint, so endpoint
   count doesn't decide the outcome.
3. **Labs admission evidence** (goes in the research file and the PR body): Level Control commands 0x00–0x07 and
   OptionsMask/OptionsOverride are mandatory since 1.0. TC-LVL-3.1 steps 5–6 check ExecuteIfOff on MoveToLevel to an
   off light, and TC-CC-5.1 does the same for MoveToColor, both since 1.0. TC-LVL-4.1 and 6.1 cover Move and
   Stop/StopWithOnOff. TC-CC-3.x–9.x cover the hue, saturation, xy, CT, EnhancedMoveHue and StopMoveStep commands,
   gated by feature. Not certified with the override: HS and CT moves. HA core already sends them with mask 1 /
   override 1.
4. **Fade method:** `core/level_fade.py`'s LevelFade, as Shelly and Control4 use it. A live `read_attribute` of
   CurrentLevel or CurrentSaturation, because the reference server interpolates mid-transition and a subscription
   reports at most once per max(1 s, T/4). Then one MoveTo with a TransitionTime for the distance left. `heading_there`
   is always False. Hue is EnhancedMoveHue where the light has the EHUE feature, else MoveHue, at a rate from
   `core/zcl_fade.hue_cycle`, running until stop, as on ZHA. A light with neither (HS feature off) is unchanged with
   `fields_dropped`.
5. **Raise from off** (brightness only): first `MoveToLevel(1)` with ExecuteIfOff, then
   `MoveToLevelWithOnOff(end, T)`, so the light fades in from the bottom (ZHA's preset). **Lower to 0** is
   `MoveToLevelWithOnOff(0, T)`. Once the fade has run, the start level goes back with `MoveToLevel(start)` and
   ExecuteIfOff, so the light stays off and comes back at its old level, as on Hue and ZHA. A later brightness move, a stop,
   or a light call from HA cancels that restore (a color move leaves it: the level fade still ends off), using the same job key and `ha_watch` resolver pattern as
   `zha/fade.py`'s `soft_off_restores`.
6. **Saturation on an off light** is unchanged with `off`. Add `raises_from_off: ClassVar[bool] = True` to LevelFade.
   Matter's saturation adapters set it False. Shelly and Control4 don't change. This is the only core change (it needs a
   repo maintainer).
7. **set_attributes:** `core/zcl_write.commands()` builds the command list. Each command is sent with
   TransitionTime `WRITE_FADE_TENTHS`, optionsMask 1 and optionsOverride 1. Brightness is MoveToLevel, never
   WithOnOff. Then wait `WRITE_FADE_WAIT_S` and read back.
8. **Read-back confirms (your call).** set_attributes is confirmed when CurrentLevel and the color attributes read
   what was sent (within one step), otherwise sent with a detail. Stop reads CurrentLevel (and saturation/hue on a light
   with the HS feature, as saturation moves aren't tracked) twice, 0.2 s apart: equal values are confirmed, unequal ones are sent with `still_fading`,
   and a light reading off is unchanged with `off`. A failed read is sent with `readback_failed`. **The read-back may be
   dropped per class once a class leaves Labs on a pass:** record this in `docs/deferred.md` (reopens when a class's
   Labs flag lifts).
9. **OnLevel overrides ExecuteIfOff.** By spec, the next On goes to OnLevel if it's non-null. set_attributes on an off
   light reads OnLevel (`<ep>/8/17`). When it's non-null the result is sent with `on_level_set`, and DeviceSide never
   writes OnLevel because that's the user's device setting. index.md states it. Separately, the IKEA KAJPLATS honors the
   write but resumes at its old level (PR #174089): name it in internals.md's quirks. That's Labs evidence, not a split
   yet.
10. **Stop** sends Level `Stop` (mask 0) to each lit light, plus `StopMoveStep` on lights with a Color Control
    server, always, since it's harmless with nothing moving. It cancels the pending soft-off restore, so a halted soft
    off stays on at the halt level, as on ZHA.
11. **Addressing:** a light's Level Control (cluster 8) and Color Control (cluster 0x0300) are on the same endpoint as
    its OnOff entity (`addressing.onoff_endpoint`). A light with no Level Control server on that endpoint gets
    `not_dimmable` (Shelly's reason). Color features come from Color Control's FeatureMap (`<ep>/768/65532`), read
    from the node cache, sync, as `lt_feature` does. The LT check stays for these adapters too.
12. **Set_attributes reads HA's color modes** (decided during step 2): `core/zcl_write.commands()` takes HA's
    `supported_color_modes`, which HA derives from the Color FeatureMap, so set_attributes doesn't read the FeatureMap;
    `addressing.color_features` serves step 5's hue check. OnLevel is read only when the call sets a brightness, since it
    decides only the level the next On comes up at.
13. **Groups:** HA's Matter has no group entities. Nothing to do.
14. **set_attributes leaves the slots before its wait** (decided after PR 1, from its audit Medium; built in step 5).
    PR 1's `send` holds an integration slot (Matter's `max_concurrency` is 2) through `WRITE_FADE_WAIT_S` and the
    read-back, so a call to n lights takes about 0.6 s per pair more than it needs. `execute` becomes two passes: a
    first `self.gather` sends each light's commands in its slot and keeps what its read-back needs (expected values,
    OnLevel or not, dropped) by `reported_id`; then one `asyncio.sleep(WRITE_FADE_WAIT_S)` outside every slot; then a
    second `self.gather` over the lights that sent something runs `read_back`, each in a slot of its own, so the
    deadline still bounds it. A light the first pass rejected or left unchanged keeps that result. ZHA's refreshes run
    outside the slots for the same reason (`zha/set_attributes.py`). Tests pin, with `max_concurrency` 2 and four
    lights, that every light's commands go out before the first read, and that one sleep runs per call. The call
    transcript keeps its commands and reads; only their order across lights may change.

## Steps

**PR 1: set_attributes** (branch `wt/matter-set-attributes`, `pr-draft` this plan)

1. Check the research file's pinned links (fix any that are off). Add Level and Color addressing helpers to `integrations/matter/addressing.py`: cluster IDs, the
   attribute paths for CurrentLevel, OnLevel, CurrentX/Y, CurrentHue/Saturation, ColorTemperatureMireds, the Color
   FeatureMap, and a `has_level(node, ep)`. Add lazy `chip.clusters` builders beside `make_on_with_timed_off`. Before
   relying on any field name other than `optionsMask`/`optionsOverride`, check it against Objects.py.
2. `integrations/matter/set_attributes.py`: Decisions 7–9, 11. Scope: `domains=labs(Platform.LIGHT)` per
   Decision 2 (as other Labs adapters write it), fields as Shelly/ZHA list them, `confirmable=True`.
   `classes.py` gains a `LIGHT_ACTIONS = labs(OTHER, MULTI_ENDPOINT)` with a comment citing Decision 2. Tests in
   `tests/integrations/matter/test_set_attributes.py`, plus a new call transcript. Mirror
   `tests/integrations/matter/wire.py`.
3. Docs: in index.md, replace "On/off only: brightness and color fields are refused" with the real state and add a
   `## Flash-free turn-on` section (ExecuteIfOff, OnLevel; the heading every integration uses, which the README links). Add a `### set_attributes` module section to internals.md
   with the quirks. Run `scripts/gen_compat.py` and the README regeneration. Add the read-back entry to deferred.md.
   Then the audit and ready, per the global rules.

**PR 2: raise/lower and stop** (branch `wt/matter-light-fades`, off main after PR 1 merged as `fde92568`)

4. Core: `raises_from_off` on LevelFade (Decision 6), with a unit test in core's tests.
5. `integrations/matter/fade.py`: a MatterFade(LevelFade) for brightness and saturation (Decisions 4–6), and a hue
   adapter on the ZHA hue-move pattern (it tracks the cycling lights for stop). Add the six thin action modules, the
   way `zha/raise_brightness.py` is, and register them in `ADAPTERS`. Also Decision 14: set_attributes' wait and
   read-back leave the slots; while there, fix the two PR 1 audit Lows on lines this touches (`color_feature_map_path`
   unused by `color_features`; `unsupported_reason`'s docstring saying "OnOff timer").
6. `integrations/matter/stop.py`: Decisions 8 and 10.
7. Docs, as step 3: index.md sections for smooth dimming and stop, internals.md module sections, regenerate. Then the
   audit and ready.

Risky step for its own audit range: step 5 (the soft-off restore's job and cancel).

## Handoff

- **Done:** PR 1, steps 1–3, merged as #591 (`fde92568`). Decision 14 (the audit Medium) added after it, for step 5.
- **Next:** PR 2, steps 4–7, on `wt/matter-light-fades` (worktree `deviceside-wt-matter-light-fades`), draft PR
  opened with this plan. Start at step 4. Step 5 gets its own `/audit-code` range.
- **Carried from PR 1:** Decision 12. The Level/Color IDs, color capability bits (`HUE_SATURATION`, `ENHANCED_HUE`,
  `XY_COLOR`, `TEMPERATURE_COLOR`) and `XY_SCALE` live in `core/zcl.py`. `addressing.color_features` and
  `make_command` exist for step 5's hue check and the Move/Stop builders.
- **Open decisions:** none.

## Verification

- Each push: `.venv/bin/pytest -n auto --transcripts=check`. The new transcripts are generated on purpose:
  `docs/evidence.md`, Release gate (no sign-off needed for Labs-only scope beyond what that section says).
- Unit tests pin, as literals: optionsMask 1 / optionsOverride 1 and TransitionTime 4 on set_attributes;
  MoveToLevel (not WithOnOff) for an off light; the preset then WithOnOff on raise from off; the restore after a soft
  off and its cancel by an HA light call and by stop; confirmed/sent/`on_level_set`/`still_fading`/`readback_failed`;
  `not_dimmable`; bridged and uncertified refused as not built; Labs off refuses `other`.
- `scripts/gen_compat.py --check` and the CI generators pass.
- No live check (Decision 1). The first Labs device report on a Matter light is the next evidence.
