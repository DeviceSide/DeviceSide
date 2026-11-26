# set_scene on Home Assistant scenes (v0.3.0)

## Context

#617 showed how much users lean on `set_scene`. Today it serves Hue bridge scenes only
(`integrations/hue/set_scene.py`). A Home Assistant scene is a list of entity states, and `set_scene` on one is
`set_attributes` per light, so every integration with a `set_attributes` adapter (Hue, ZHA, Zigbee2MQTT, Matter,
Shelly, Control4) can serve it with no code of its own. Outcome: `deviceside.set_scene` takes a
`scene.homeassistant` entity and writes each light's settings without turning it on, wherever `set_attributes`
works. Ships in v0.3.0, not v0.2.0: the PR stays a draft and merges only once v0.2.0 is tagged (or cut to a
`release/v0.2.0` branch), so no v0.2.0 RC carries it.

## Decisions (Jason, 2026-11-26)

1. **Scope:** build the route for HA scenes. One research file settles Zigbee2MQTT native scenes; every other
   non-Hue native scene goes to `docs/deferred.md`.
2. **A light the scene holds as off is turned off**, through core's `light.turn_off`, as Hue's `set_scene` sends
   `on: false`.
3. **Members that can't be served are skipped and logged, like a group's.** The scene is refused only when none of
   its lights can run; a device failure raises once every light has run.
4. **Shown per integration, derived:** an integration with `set_attributes` and no `set_scene` adapter gets a
   set scene cell derived from `set_attributes`.
5. **No rig step file here** (Jason, 2026-11-26): this PR leaves `tests/rig/steps/set_scene.yaml` untouched. A separate
   ha-rig plan owns the HA-scene case, its role and where its record lands; its step file lands in a small PR paired
   with that rig change.
6. **The scene's entry reads like a group's** (ha-rig plan for this case, 2026-11-26): `member_capabilities` and
   the lights' shared integration, so the rig binds the record to the lights' classes.

Approach chosen: a core route (no per-integration adapters, no pseudo-integration). Rejected: a `homeassistant`
pseudo-integration whose adapter re-enters the dispatcher (circular, meaningless class levels); native scene adapters
per protocol (only Hue exposes scene entities with readable contents).

## Design

**Recognizing an HA scene.** New `core/ha_scene.py`. An HA scene is an entity in
`hass.data["homeassistant_scene"].entities` (core's `DATA_PLATFORM`, as core's `entities_in_scene` reads it), not
an entity-registry lookup: a YAML scene with no `id` has no registry entry. Its states are
`entity.scene_config.states`, read on every call so a scene edit or reload applies. Access goes through
`core/ha_entity.py`'s guarded pattern, since `scene_config` is core-internal.

**State to request.** `ha_scene.py` turns one light `State` into either "off" or a `SetAttributesRequest`
(`actions/set_attributes.py`), following core's `light/reproduce_state.py`:
- brightness 0-255 to percent, no floor raised (level 1 is 0.4 %);
- one color, picked by the state's `color_mode` (`COLOR_MODE_TO_ATTRIBUTE`): `color_temp_kelvin`, `hs_color`,
  `rgb_color` or `xy_color`; `rgbw` and `rgbww` modes take the state's `hs_color`; `white` mode writes brightness
  alone (core's `white` is a brightness); an unknown mode takes the first writable color present, in core's order;
- a light whose mode's color is missing is skipped with a WARNING, as core's `reproduce_state` sends nothing for it;
- `effect` is not written (no `set_attributes` field), as Hue's `set_scene` skips effects;
- an on light with nothing to write is `unchanged`.
Non-light entities (switches, covers) are skipped at DEBUG: they are not a fault.

**The route.** `Dispatcher.handle` resolves through `resolve()`, which refuses platform `homeassistant`, so HA
scenes are taken out before `resolve_targets`. The seam, as built: `Action.claims` (default: none) picks entity IDs
from `members`, and `Action.route` plans them; `SetScene` claims HA scenes. Both routes plan before either sends
(`plan_adapters`, then `run_planned`), so a named target refused on either raises before anything is sent. For
each claimed scene:
1. lights held on, grouped by identical request: expand HA groups (`core/groups.py:expand_ha_groups`), resolve each
   with the scene as `via_group` (a light in a nested group keeps that group, for clearer skip logs) and
   `named=False` (indirect), then `plan_adapters("set_attributes", …)`.
   Native groups, fallback, field drops, class refusals and the Labs gate all apply unchanged, per light;
2. lights held off: one blocking `light.turn_off` with the call's context;
3. fold the light results into one result for the scene, in Hue's vocabulary: `sent` when any light was written or
   turned off; `unchanged` when none needed it; `rejected` with `some_lights_failed` or `error` on device
   failures (so the call raises `targets_failed`); refused when no light could run, raised if the scene was named,
   with its lights' ranked reason and its text (`rank`). Skipped lights, and an adapter's `unsupported` at run time,
   are logged by the existing skipped-targets warning, never a failure. The scene's entry carries
   `member_capabilities`, as a native group's does, and names the lights' integration when they share one,
   `homeassistant` otherwise (Decision 6).

**Levels.** The route has no level of its own: each light is gated by `set_attributes`' scope, so evidence is
inherited (tenet 5: same call, same class). No transcript in `tests/integrations/*/calls/` changes, so no existing
rig case reopens (tenet 9).

**Derived cells.** `Action` gains a class attribute naming the action it rides (`SetScene`: `set_attributes`)
and the extra entity targets it serves (`scene` on `homeassistant`). Generators read it:
- `scripts/gen_services.py` `targets()`: `set_scene`'s target block gains `domain: scene, integration: homeassistant`;
- `scripts/gen_features.py` `built()`: an integration with no adapter for the action takes the ridden action's
  cell, linked to the shared section in `docs/integrations.md`; Hue keeps its own adapter's cell;
- `scripts/gen_compat.py`: a class's set scene entry follows the same rule, at the ridden action's level and record.
The coverage view (`coverage.py`) is unchanged: it has no set scene column, and "Set while off" already says it.

## Steps

0. Save this plan as `docs/plans/2026-11-26-set-scene-ha-scenes.md`; worktree `wt/set-scene-ha-scenes`;
   `pr-draft` it.
1. **Research and deferrals.** `/research`: are Zigbee2MQTT scenes discovered as HA scene entities, and can a
   scene's contents be read (bridge topics, `database.db`, a View Scene converter)? File:
   `docs/integrations/zigbee2mqtt/research/2026-11-26-scenes.md`. Add `docs/deferred.md` entries: native scenes on
   ZHA, Matter, Shelly and Control4 (no scene entity in HA; verify each claim against core before writing it), and
   Zigbee2MQTT's per the research. Reopens: the integration exposes scene entities with readable contents. If the
   research finds Z2M scenes buildable, file an issue; don't build it here.
2. **`core/ha_scene.py`** and `tests/core/test_ha_scene.py`: recognition, state to request, each color mode,
   brightness 1 and 255, off, non-lights, a scene removed mid-call.
3. **The route** (risky: `core/dispatcher.py`, gets its own `/audit-code`): the `Action` seam, `SetScene`,
   result folding. Tests in `tests/core/test_dispatcher.py` and `tests/actions/test_set_scene.py`: a scene across
   two integrations; a light with no adapter skipped while the rest run; no light servable raises when named; an
   off light turned off; a nested HA light group and a native group; Labs off drops a Labs-class light; a device
   failure raises after all ran; a Hue bridge scene and an HA scene in one call.
4. **Generators:** the ridden-action rule in `gen_services.py`, `gen_features.py`, `gen_compat.py` and their
   tests (`tests/scripts/`); regenerate `services.yaml`, README, `docs/device-compatibility.md`.
   `scripts/check_release.py --records` must not demand a `set_scene` record from an integration with no
   `set_scene` adapter: confirm, and pin it with a test.
5. **Docs:** `docs/design.md` (Scope's `set_scene` bullet, `core/` listing, the seam in Core contract),
   `docs/action-behavior.md` (what a scene's result holds, what is skipped), a "Home Assistant scenes" section in
   `docs/integrations.md`, `translations/en.json`. The rig case for an HA scene is not here (Decision 5).

**Doc shape** (docs scrub, #626 step 3 and 4): living docs cite no `Decision N`, `plans/` path or SHA;
`docs/deferred.md` entries about 80 words; `docs/design.md` contract cells 25 words or fewer; scene results in
`docs/action-behavior.md` as rows of its Refused | Dropped and response-key tables. `scripts/check_docs.py` will hold a
word budget per living doc: fit it, or raise the budget line in this PR.

## Reuse

`SetAttributesRequest` and `LightFields` (`actions/set_attributes.py`, `core/models.py`);
`Dispatcher.run_adapters`, `_skip`, `_rank` (`core/dispatcher.py`); `expand_ha_groups` (`core/groups.py`);
`resolve` (`core/resolver.py`); `ha_entity` (`core/ha_entity.py`); Hue's result details
(`integrations/hue/set_scene.py`); HA's `ColorMode` and light attribute constants, never literals.

## Verification

- `.venv/bin/pytest -n auto --transcripts=check` passes with no transcript changed.
- `scripts/gen_services.py --check`, `scripts/gen_features.py --check`, `scripts/gen_compat.py --check` clean.
- Live: the HA-scene rig case lands with its ha-rig change (Decision 5), not in this PR.
- PR audit by an Opus auditor (`docs/evidence.md` or `docs/design.md` rule text may change), then `owner-findings`.

## Coordination

Intent: set_scene takes Home Assistant scenes on every integration with set_attributes, by a core route that
writes each light through set_attributes; non-Hue native scenes are researched (Zigbee2MQTT) or deferred.
Touches: custom_components/deviceside/core/ha_scene.py, custom_components/deviceside/core/dispatcher.py, custom_components/deviceside/core/action.py, custom_components/deviceside/actions/set_scene.py, custom_components/deviceside/services.yaml, custom_components/deviceside/translations/en.json, scripts/gen_services.py, scripts/gen_features.py, scripts/gen_compat.py, tests/core/**, tests/actions/**, tests/scripts/**, docs/design.md, docs/action-behavior.md, docs/integrations.md, docs/deferred.md, docs/device-compatibility.md, docs/integrations/zigbee2mqtt/research/**, README.md, docs/plans/2026-11-26-set-scene-ha-scenes.md

## Implementing session

Model: `opus`. The dispatcher seam and the result folding are design calls a test wouldn't catch if wrong, and the
docs are public.

```
cd ~/projects/ha/deviceside && claude --model opus 'Implement docs/plans/2026-11-26-set-scene-ha-scenes.md, starting at step 0.'
```

## Handoff

2026-11-26, from the session that ran step 5.

- **Done:** steps 0-5, each with its plan review (and step 3's `/audit-code`) recorded in a `Step N done` commit.
  Full suite `--transcripts=check` passes, no transcript changed; all three generators' `--check` clean.
- **Waiting:** the PR stays a draft until v0.2.0 is tagged (or cut to `release/v0.2.0`); neither exists yet.
- **Then, in the turn that marks it ready:** merge main and rerun the generators. Docs scrub step 3 (#631) and #632
  are already merged in, the scene bullet fitted to the new tables. #633 adds `scripts/check_docs.py`: if a doc
  overruns its budget, raise that line in `docs/word-budgets.yaml` here. Then the whole-PR audit (Opus auditor:
  `docs/design.md` rule text changes) and `owner-findings`.
- **Peers:** ha-rig session "ha-scene-rig-77" (agent-inbox, jasonmx/HA-rig#110) reads `SetScene.rides.action` and
  the scene entry's `member_capabilities`/integration; tell it if either shape changes. Docs scrub sessions
  "docs-scrub-84" / "docs-scrub-pare-living-docs" know of the overlap.
- **Branch / worktree / PR:** `wt/set-scene-ha-scenes`, `/Users/jason/projects/ha/deviceside-wt/set-scene-ha-scenes`, #630 (draft).
- **Open decisions:** none.
