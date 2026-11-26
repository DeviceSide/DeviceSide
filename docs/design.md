# Design

How DeviceSide is built and why. What each integration does for users is in its bundle's `index.md`, under
`docs/integrations/<integration>/`, with what they share in [integrations.md](integrations.md); what goes on the wire,
and what was measured on real devices, is in the bundle's `internals.md`, with what they share in
[internals.md](internals.md).

## Glossary

Code and docs use these terms. Each one's rules live where its link points.

- **Action**: what the user calls, e.g. `deviceside.turn_on_for`.
- **Feature**: the user experience one or more actions deliver (turn on with timer, smooth dimming). Prose only.
- **Integration**: the HA integration that is the first hop to the device, e.g. ZHA or MQTT.
- **Bridge**: a separate system between the integration and the device, named only when the integration alone
  doesn't say how the device is reached (Zigbee2MQTT behind MQTT); the Hue Bridge is not counted.
- **Adapter**: one action on one integration (or bridge).
- **Capability**: the code's name for a Class (`IntegrationInfo.capability`, `AdapterScope.capabilities`, a result's
  `capability`).
- **Class**: the set of devices that get the same call and run the same firmware family, as the integration names
  it; each stands on its own evidence. Rules: [evidence.md](evidence.md#device-classes).
- **Family**: a vendor's classes on one integration, as a package of their own
  (`integrations/<x>/families/<family>/`), so a vendor is one path with its own maintainers. Rules:
  [Writing an integration](#core-contract), Family.
- **Catalog**: the Zigbee strings and sourced firmware facts that two integrations' families of one key both read
  (`custom_components/deviceside/zigbee/<family>.py`), and generated device tables any Zigbee integration may read
  (`zigbee/standard_lights.py`): patterns and facts only, no levels and no calls.
- **Placed**: a device whose class rests on everything the integration will report about it; until then its class is
  `Unplaced` (`core/scope.py`). Rules: [evidence.md](evidence.md#no-known-method-not-built-yet-in-labs); when a device
  counts as placed: each integration's page, as [Zigbee2MQTT's](integrations/zigbee2mqtt/index.md#device-classes).
- **Not supported**: DeviceSide can't do this action for the target (`target_not_supported`,
  `integration_not_supported`); for a class, either no known method or not built yet.
- **No known method**: a class no known call works on for an action, a device limit as far as anyone knows. Rules:
  [evidence.md](evidence.md#no-known-method-not-built-yet-in-labs).
- **Not built yet**: a class a known or plausible call would serve for an action, and nobody has built it. Rules:
  [evidence.md](evidence.md#no-known-method-not-built-yet-in-labs).
- **Field**: an action parameter, e.g. `brightness`.
- **Entity domain**: light, switch. "Domain" alone is fine where unambiguous.
- **Scope**: the entity domains, classes and fields an adapter is built for, each at its level; outside it, a call is
  refused. Its `AdapterScope` fields: [Writing an integration](#core-contract).
- **Level**: how a scope item is proven: Verified, Documented or Labs. Rules: [evidence.md](evidence.md#levels).
  User wording: [device-compatibility.md](device-compatibility.md#levels-of-proof).
- **Labs**: the lowest level, and the flag on a scope item (`labs(...)`) that no pass or Documented route admits yet, or
  that a maintainer holds back; also the option (`labs`, off by default) that lets calls touching a flagged item
  through. Only the dispatcher reads the option. Rules: [evidence.md](evidence.md#the-labs-flag).
- **Maintainer**: a GitHub handle in an integration's `IntegrationInfo.maintainers`, or a family's in its `Family`'s
  `maintainers`. Rules: [CLAUDE.md](../CLAUDE.md#maintainers). User wording:
  [device-compatibility.md](device-compatibility.md#levels-of-proof).
- **Repo maintainer**: a handle in `REPO_MAINTAINERS` (`scripts/gen_codeowners.py`), with admin on the repo; distinct
  from an integration's Maintainer. Rules: [CLAUDE.md](../CLAUDE.md#maintainers).
- **Caveat**: a risk mark on an adapter (`AdapterScope.caveat`), set by a repo maintainer; it ships live. Rules:
  [evidence.md](evidence.md#caveats).
- **Call transcript**: what the unit tests saw an action send on the wire and make of the replies,
  `tests/integrations/<x>/calls/<action>.json`, one **segment** per distinct run; sign-offs bind to it. Rules:
  [evidence.md](evidence.md#release-gate).
- **Sign-off**: an action's standing rig records, or a maintainer's `_manual.json` row naming it, which a release
  needs for each action whose calls changed since the last tag. Rules: [evidence.md](evidence.md#release-gate).
- **Rig**: a tool that tests DeviceSide's features automatically with real hardware on a live Home Assistant instance,
  and writes up the results as test records.
- **Test record**: the evidence that an adapter works on real hardware, in
  `docs/integrations/<integration>/test-records/`. Format: [evidence.md](evidence.md#sign-off-format).
- **Device report**: a user's "works" or "doesn't work" for an action on a model, filed with the device report form;
  the GitHub issue is its record. A working one, cited in a maintainer's `_manual.json` row, can release a Labs item.
  How it counts: [evidence.md](evidence.md#the-labs-flag); contrary reports:
  [Levels](evidence.md#levels).
- **Profile**: one test setup on the rig's HA, the entities a run may move by integration and role; a record names the
  one it ran on (`lab`, `house`).

## Principles

What gets built, and the evidence it needs: [CONTRIBUTING.md](../CONTRIBUTING.md#development-principles). How it is
built:

- **On the device.** Once the command is sent, the behavior completes (or degrades to plain device behavior) with
  HA offline.
- **One action per user intent, not per protocol primitive.** Zigbee has move, step and move-to; DeviceSide has one
  raise and one lower per attribute, and the adapter picks the command.
- **Human terms.** Fields describe what the light should do, never how the device does it: no rates, steps, mireds
  or cluster vocabulary. The adapter converts.
- **Behave as core does.** When to raise, what to skip and what a response holds follow HA core's own actions:
  [action-behavior.md](action-behavior.md).
- **Drop-in for Hue Smooth Dimming:** [action-behavior.md](action-behavior.md#replacing-hue_dimmer).
- **Highest aggregation the device accepts.** A group goes to the device as one command where the integration has
  a native group, to cut radio traffic and popcorning.

### Naming

1. `verb_object`, in HA vocabulary only: objects are the names HA's own services and state attributes use
   (`brightness`, `attributes`, `scene`). Protocol vocabulary (`level`, `OnLevel`, `toggle_after`) never appears in an
   action or field name.
2. Commands use HA's command verbs: `turn_on_for`, `raise_brightness`, `stop`, `set_attributes`.
3. A persistent setting (how the device behaves from now on) is `set_<behavior>` with the trigger in plain English:
   `set_auto_off`, `set_auto_on`. It is undone by `clear_<behavior>`, as core does (`sonos.clear_sleep_timer`), never
   by a zero value: in core a zero duration means "now". `clear_`, not `cancel_`: core's `cancel` stops something
   already running (`timer.cancel`).
4. Field names are `light.turn_on`'s wherever one exists; a feature-specific field gets plain words (`duration`,
   `sweep_time`, `limit`).

## Scope

Which integrations have which actions: the feature table on docs/device-compatibility.md (`scripts/gen_features.py`);
each integration's page: [integrations.md](integrations.md). What can't be built where, and why: `NO_PATH` in
`scripts/gen_features.py`, explained to users in [integrations.md](integrations.md#what-cant-be-done-and-why). Per
device class: [device-compatibility.md](device-compatibility.md). Each adapter's `AdapterScope` says what it covers.

- **`turn_on_for`, `turn_off_for`**: on, then off after `duration` (or the reverse), timed on the device.
  `turn_on_for` takes the `light.turn_on` fields.
- **`set_auto_off`, `set_auto_on`, `clear_auto_off`, `clear_auto_on`**: a setting stored on the device, applied after
  every turn-on (or turn-off) from any source. A call that changes nothing sends nothing.
- **`raise_*`, `lower_*`, `stop`**: one action per attribute (brightness, hue, saturation) and direction, as HA names
  its direction actions (`cover.open_cover`). `sweep_time` is how long a full range takes, `limit` ends the move
  early, and `stop` halts every move on the target. No color temperature move: every stop of a Hue fade jumps visibly.
- **`set_attributes`, `get_attributes`**: write brightness, color or color temperature without turning on, and read what
  HA doesn't show: the device's actual values (mid-move, where the move has reached), never a cached last write. Every
  timed or set-while-off adapter needs a matching `get_attributes` on its integration.
- **`set_scene`**: a scene's settings, written to each light while it's off. A Hue bridge scene goes to Hue's adapter;
  a Home Assistant scene is written light by light through `set_attributes`, so it serves every integration that has
  that ([integrations.md](integrations.md#home-assistant-scenes)). Other native scenes: [deferred.md](deferred.md).

Not built yet: turn-on defaults (`OnLevel`) and other entity domains (cover, valve, lock). Each new one, and each new
integration, is weighed against the broad-appeal principle in
[CONTRIBUTING.md](../CONTRIBUTING.md#development-principles).

## Architecture

Facts from HA core this rests on:

- `helpers/group.py:expand_entity_ids` expands only `group.*`. A light or switch group helper is not expanded by
  target extraction, so `core/groups.py` expands it through `get_entity_ids`.
- `zha.issue_zigbee_cluster_command` is an admin service, so adapters forward the caller's `call.context`.
- HA auto-imports top-level modules named after entity platforms and after `group`, `diagnostics`, `repairs` and the
  like, so adapters live under `integrations/` and nothing at the top level is called `light.py`.
- Schemas use `probatio` and reuse `light.const.LIGHT_TURN_ON_SCHEMA` entries, so ranges never drift from core,
  bar brightness: it is a percent in every action, as in Hue Smooth Dimming. `turn_on_for` converts it to 1–255 where
  it calls `light.turn_on`, never to 0, and never as `brightness_pct`, which core (`light/helper.py`) rounds to 0
  below 0.2%. 0.4 % is level 1, the lowest a light takes, and every level 1–254 is reachable: no shared conversion
  raises the floor. A device, or a layer below DeviceSide, that can't reach level 1 is a device fact in its bundle's
  `internals.md` and a class limit in its `index.md`.

### core/

```
models.py        Status, ActionKind, Request, Target, EntityResult, LightFields
scope.py         AdapterScope, IntegrationInfo, Family, DurationLimits: what an integration declares
rules.py         Rule and its composer: which devices are a class's, for an integration with families
errors.py        Reason, TargetNotSupported: why a target is refused
fields.py        the fields a target lacks, read as light.turn_on's filter_turn_on_params reads them
duration.py      clamp: fits a request's duration to a call's limits
action.py        Action base class
actions.py       registers the actions; refuses calls until the config entry loads
adapter.py       Adapter base class; gather() runs sends under the concurrency limits
registry.py      AdapterRegistry: discovery, guarded import, lookup, matrix
resolver.py      entity_id -> Target, or the reason it can't be served
groups.py        HA group expansion, any domain
ha_scene.py      Home Assistant scenes: which entities are one, each light's write, set_scene's route
dispatcher.py    parse, extract, expand, resolve, plan, run, raise rule, response
ha_watch.py      drops predictions a light or scene call from HA leaves stale
ha_entity.py     guarded access to HA's live entity objects
transition.py    a move's predicted value, per integration
level_fade.py    LevelFade: raise and lower from the level the device reports, in one timed set
zcl.py           ZCL facts the ZHA, Zigbee2MQTT and Matter packages share
zcl_*.py         what the Zigbee integrations share: fade planning, a get_attributes row, set_attributes commands
color.py         colors read and written alike across integrations
timer.py         a get_attributes row's on/off timer entry
readback.py      read_back: the read after an accepted write; a failed read reports sent
runtime.py       DeviceSideData in hass.data: registry, dispatcher, semaphores, integration state
```

### Core contract

**Writing an integration.** An integration's module exports `INTEGRATION` (an `IntegrationInfo`) and `ADAPTERS`; each
adapter has an `AdapterScope`. What each can declare (`core/scope.py` holds each one's contract):

| Hook or field | What it buys | Where its rules live |
|---|---|---|
| `IntegrationInfo.capability`, `classes`, `default_class` | Each target's class, so each class stands on its own evidence: a device class, not a call pattern. `classes` gives its entity domains. | [evidence.md](evidence.md#device-classes); `capability`, `classes`, `Unplaced` in `core/scope.py`; `check_integration`, `check_classes` in `core/registry.py` |
| **Family**: `IntegrationInfo.families` (`Family`, `FamilyScope`), `integrations/<x>/refusals.py` | A vendor's classes as one path with its own maintainers; opt-in. The integration keeps the transport, default class, rule order and every refusal entry. | `Family`, `FamilyScope`, `class_scope` in `core/scope.py`; `check_families` in `core/registry.py`; `core/rules.py`; [CLAUDE.md](../CLAUDE.md#maintainers) |
| **Groups**: `IntegrationInfo.is_group`, `expand_group`, `AdapterScope.native_groups` | A native group (a Hue zone) goes to the device as one command. `is_group` recognizes it; `expand_group` lists its members, sync, no I/O. | `core/dispatcher.py`'s module docstring, Native groups (fallback, refusal); [evidence.md](evidence.md#device-classes), Groups |
| `IntegrationInfo.setup`, `remove` | `setup` starts what the integration keeps running while loaded, as a background task; `remove` undoes what it changed outside HA. The root names no integration. | `IntegrationInfo` in `core/scope.py`; `_guarded` in `__init__.py` (a hook that raises is logged and isolated) |
| `IntegrationInfo.detect` | Picks this integration over a generic sibling on the same `ha_domain` (Zigbee2MQTT over plain MQTT). | [evidence.md](evidence.md#the-split-rule); Resolver, below |
| `IntegrationInfo.unsupported` | Refuses a gateway or API DeviceSide never supports, as `integration_not_supported` with its reason; no adapters, kept out of the cards and gates. | `IntegrationInfo` in `core/scope.py`; `AdapterRegistry` in `core/registry.py` |
| `IntegrationInfo.zigbee_manufacturer` | The device's own Zigbee manufacturer string for the device report form, where HA's registry holds another. | `IntegrationInfo` in `core/scope.py` |
| `IntegrationInfo.call_resolver` | Drops what a light or scene call from HA leaves stale. | `core/ha_watch.py` |
| `IntegrationInfo.max_concurrency`, `AdapterScope.max_concurrency` | How many sends run at once. | [Concurrency](#concurrency) |
| `AdapterScope.domains`, `fields` | The entity domains and fields the adapter is built for, each at its level; outside them a call is refused (`domain_not_tested`, `fields_not_tested`). | [evidence.md](evidence.md#levels); `Adapter.supports` in `core/adapter.py` |
| `AdapterScope.drops`, `unlisted` | Fields the integration can never send, dropped as a lacked field is; fields its devices take though the light's state says they can't. | [action-behavior.md](action-behavior.md#when-to-stop-an-automation): Lacks a field, Unlisted fields depart from core |
| `AdapterScope.capabilities` | A level per class, and per domain where its entry names some (`OnDomains`). | [evidence.md](evidence.md#device-classes) |
| `AdapterScope.class_labs` | Fields in Labs on some classes alone (`labs_fields(...)`). With the option off the dispatcher drops them there (`fields_dropped`), not on a native group. | [evidence.md](evidence.md#levels); `core/dispatcher.py`'s module docstring, Planning |
| `AdapterScope.no_known_method`, `not_built` | A class refused with a reason (`NoKnownMethod`, `NotBuilt`); in none of `capabilities`, `no_known_method` and `not_built` is not built. `not_built` holds only classes today's call would harm. | [evidence.md](evidence.md#no-known-method-not-built-yet-in-labs); `AdapterScope.refusal` and `harms` in `core/scope.py` |
| `AdapterScope.own_calls` | A class's own call (`OwnCall`), handed to the adapter in place of `execute`, with optional duration limits. Each such class is in `capabilities`. | [evidence.md](evidence.md#the-split-rule); `OwnCall` in `core/scope.py` |
| `AdapterScope.own_calls_only`, `OwnCallsOnly` | Serves only its classes' own calls (Zigbee2MQTT's `turn_off_for`). A flag, not refusal entries: an unnameable class matches no entry and would reach `execute`. | `AdapterScope.refusal` in `core/scope.py`; `OwnCallsOnly` in `core/adapter.py`; `AdapterRegistry` in `core/registry.py` |
| `AdapterScope.duration` | The durations the call can carry (`DurationLimits`): a request outside them is clamped, and the result says so. | [action-behavior.md](action-behavior.md#when-to-stop-an-automation): A value the device can't reach; `core/duration.py` |
| `AdapterScope.confirmable`, `options`, `notes` | Declarations the rig reads: `confirmable`, a run expects `confirmed`; `options`, DeviceSide options that change what it does (`predicted_state`); `notes`, free text. | `AdapterScope` in `core/scope.py`; [evidence.md](evidence.md#sign-off-format) (`<action>-<option>.json` records) |
| `AdapterScope.caveat` | A risk mark, set by a repo maintainer; changes no call. | [evidence.md](evidence.md#caveats) |

**Writing an action.** An action's module exports `ACTION`, an `Action` subclass (`core/action.py`). One that serves
some targets through another action's adapters also declares:

| Hook or field | What it buys | Where its rules live |
|---|---|---|
| `Action.claims`, `route` | Entities the action routes itself, kept from resolution: `route` plans them beside the other targets, so a refused named one raises before any send. | `Action` and `Routed` in `core/action.py`; `Dispatcher.handle` |
| `Action.rides` (`Ride`) | The action whose adapters serve the routed targets, named as a domain on an HA integration; generators derive its target filter and cells from it. | `Ride` in `core/action.py`; `scripts/gen_services.py`, `gen_features.py`, `gen_compat.py` |

Core around them:

- **Registry.** `pkgutil` discovery over `actions/` and `integrations/`. Modules export data (`ACTION`,
  `INTEGRATION`, `ADAPTERS`), not decorators, so import has no side effects, order is sorted and deterministic, and
  `check_release.py` and the rig, from outside the repo, import the registry without `hass`, so a change to
  `AdapterRegistry`'s interface needs the rig's matching change. A failing integration import (its core
  integration isn't installed) records it unavailable and setup carries on. It checks each integration and scope as
  it registers them (`core/registry.py`).
- **Resolver.** Candidates are the available integrations whose `ha_domain` is the entity's registry platform;
  one with a `detect` hook wins first. A `switch_as_x` light resolves to the switch it wraps, and results report the
  light.
- **Dispatcher.** HA groups are always expanded, in one place (`core/groups.py`), because no device can address them;
  members carry `via_group`. Then it resolves each target, buckets targets by adapter, drops the fields a target
  lacks, checks `supports()`, the class and the Labs gate, clamps durations, runs every adapter concurrently
  under `ADAPTER_TIMEOUT_S`, and raises or skips per [action-behavior.md](action-behavior.md). The rules, native
  groups' included: `core/dispatcher.py`'s module docstring.
- **Results.** Commands answer optionally, per entity: `{status, integration, capability?, clamped_to?, detail?}`
  (a native group's `capabilities?` and `member_capabilities?` in place of `capability?`), where status is
  `sent`, `confirmed` (read back from the device) or `unchanged` (nothing to send). Queries answer only, in core's
  shape: each target's data under its entity_id, as `weather.get_forecasts` does, the class among it. The class is
  the one the dispatcher used, for an integration that names classes, so a record holds the class a call reached.
- **Actions** register once in `async_setup` and refuse calls until the config entry loads.

### Concurrency

Each command runs under two semaphores, applied in `Adapter.gather()`: the integration's
(`IntegrationInfo.max_concurrency`) and the adapter's (`AdapterScope.max_concurrency`). Hue's is 2 because aiohue's
cap of 3 is shared with core. `execute` gets all of an adapter's targets at once, so native group commands stay
possible. A per-device lock (`LevelFade.guard`, and the stop that shares it) is `gather`'s `hold`, taken before the
slot under the same deadline, so a call waiting on its device holds no slot (`Adapter.slot`).

### services.yaml, strings, icons

- `services.yaml` holds only target filters and field selectors; names and descriptions are in `translations/en.json`.
  Target filters list exactly the integrations with an adapter for the action, with the entity domains it serves, and
  the target an `Action.rides` names; `scripts/gen_services.py` generates them from the registry. They are a UI
  convenience: adapters enforce scope through `supports()`.
- Field filters can only test `supported_features` and attributes, not domain, so light fields copy
  `light/services.yaml`'s `supported_color_modes` filters; a switch-only selection shows just `duration`.
- Adding an action means a block each in `services.yaml`, `translations/en.json` and `icons.json`;
  `tests/core/test_actions_setup.py` checks all three.

### Coverage view

The Settings form in Configure (`coverage.py`) shows, above the options, a row per light and switch entity, one cell per
feature.

- **A cell** says the feature runs now (Verified, Documented) or needs Labs; a refused feature is an empty cell, as a
  blank is unsupported, and an entity with no cell has no row.
- **Source.** It reads `dispatcher.judge`, the per-target decision a call makes (supports(), the class, the refusal,
  then the Labs gate), on each action of a feature with Labs off, never a copy of it, so a cell can't disagree with a
  call.
- **Several actions.** A feature riding several actions takes its weakest; Smooth color is hue and saturation in one
  column, the weaker of the two, a refused one counting as empty.
- **Waiting.** An integration whose classes wait on a report (Z2M's bridge/devices) says so through
  `IntegrationInfo.capability_ready`; the form waits on it for at most 10 s, then shows what it has.
- **Features.** The features and their actions are `features.py`'s, which the README's cards read too; the integrations'
  order is `registry.CARD_ORDER`, a copy of the bundles' `column_order` that `tests/test_card_order.py` keeps equal.

## Release gates

The rules are in [evidence.md](evidence.md#release-gate); each gate's mechanics are in the header of the script or
workflow named.

- **Coverage:** `scripts/check_release.py --coverage`, in CI.
- **Sign-offs:** `check_release.py --signoffs`, in `cut-release`.
- **Release notes:** `docs/release-notes/vX.Y.Z.md`, which `cut-release` requires and publishes.
- **Tags:** `scripts/check_tag.py`, in `cut-release-candidate.yml` and `cut-release.yml`, the only way a tag is made.
- **RC audit:** `scripts/check_audit.py`, in `cut-release-candidate`.
- **Testing:** unit tests mock each integration at its boundary (its client, service or broker) against a real
  `hass`, and record each action's call transcript there (`tests/transcripts.py`, the boundaries in
  `tests/integrations/<x>/wire.py`); the rig runs against a live HA and writes the records.
