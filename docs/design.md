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
  (`custom_components/deviceside/zigbee/<family>.py`): patterns and facts only, no levels and no calls.
- **Placed**: a device whose class rests on everything the integration will report about it; until then its class is
  `Unplaced` (`core/scope.py`). Rules: [evidence.md](evidence.md#no-known-method-not-built-yet-on-trial); when a
  device counts as placed: each integration's page, as [Zigbee2MQTT's](integrations/zigbee2mqtt/index.md#device-classes).
- **Not supported**: DeviceSide can't do this action for the target (`target_not_supported`,
  `integration_not_supported`); for a class, either no known method or not built yet.
- **No known method**: a class no known call works on for an action, a device limit as far as anyone knows. Rules:
  [evidence.md](evidence.md#no-known-method-not-built-yet-on-trial).
- **Not built yet**: a class a known or plausible call would serve for an action, and nobody has built it. Rules:
  [evidence.md](evidence.md#no-known-method-not-built-yet-on-trial).
- **Field**: an action parameter, e.g. `brightness`.
- **Entity domain**: light, switch. "Domain" alone is fine where unambiguous.
- **Scope**: the entity domains, classes and fields an adapter is built for, each at its level; outside it, a call is
  refused. Its `AdapterScope` fields: [Writing an integration](#core-contract).
- **Level**: how a scope item is proven: Verified, Documented or Experimental. Rules: [evidence.md](evidence.md#levels).
  User wording: [device-compatibility.md](device-compatibility.md#levels-of-proof).
- **Experimental**: the lowest level, and the flag on a scope item (`experimental(...)`) not yet judged ready for
  everyone. Rules: [evidence.md](evidence.md#the-experimental-flag).
- **Experimental features**: the option (`experimental_features`, off by default) that lets calls touching a flagged
  item through. Only the dispatcher reads it.
- **Labs**: the name users see for the Experimental level and the Experimental features option: the option's label,
  the cards' ⚪ legend and user docs. Code, contributor docs and the evidence rules say Experimental.
- **Maintainer**: a GitHub handle in an integration's `IntegrationInfo.maintainers`, or a family's in its `Family`'s
  `maintainers`. Rules: [CLAUDE.md](../CLAUDE.md#maintainers). User wording:
  [device-compatibility.md](device-compatibility.md#maintainers).
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
  the GitHub issue is its record. How it counts: [evidence.md](evidence.md#the-experimental-flag); contrary reports:
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

Which integrations have which actions: the README feature table (`scripts/gen_features.py`); each integration's page:
[integrations.md](integrations.md). What can't be built where, and why: `NO_PATH` in `scripts/gen_features.py`,
explained to users in [integrations.md](integrations.md#what-cant-be-done-and-why). Per device class:
[device-compatibility.md](device-compatibility.md). Each adapter's `AdapterScope` says what it covers.

- **`turn_on_for`, `turn_off_for`**: on, then off after `duration` (or the reverse), timed on the device.
  `turn_on_for` takes the `light.turn_on` fields.
- **`set_auto_off`, `set_auto_on`, `clear_auto_off`, `clear_auto_on`**: a setting stored on the device, applied after
  every turn-on (or turn-off) from any source. A call that changes nothing sends nothing.
- **`raise_*`, `lower_*`, `stop`**: one action per attribute (brightness, saturation, hue) and direction, as HA names
  its direction actions (`cover.open_cover`). `sweep_time` is how long a full range takes, `limit` ends the move
  early, and `stop` halts every move on the target. No color temperature move: every stop of a Hue fade jumps visibly.
- **`set_attributes`, `get_attributes`**: write brightness, color or color temperature without turning on, and read
  what HA doesn't show. Every timed or set-while-off adapter needs a matching `get_attributes` on its integration.
- **`set_scene`**: a scene's settings, written to each light while it's off. A Zigbee scene recall turns lights on, so
  Zigbee would follow the same pattern.

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
  below 0.2%.

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
| `IntegrationInfo.capability`, `classes`, `default_class` | Each target's class, so each class stands on its own evidence. `capability` is sync and cheap, no I/O; it gives the default class to a device no rule matches, `Unplaced` to one not yet placed, `None` only to one it can't class at all. Every adapter sees the same class and maps the classes it serves to its own branch: a class is a device class, not a call pattern, as patterns are per action. `classes` gives each class the entity domains a device in it can be (a family's from its `Family`), so no scope holds a class on an action none of those domains reaches. | [evidence.md](evidence.md#device-classes); `Unplaced` in `core/scope.py`; the registry's checks: `check_integration` and `check_classes` in `core/registry.py` |
| **Family**: `IntegrationInfo.families` (`Family`, `FamilyScope`), `integrations/<x>/refusals.py` | A vendor's classes as one path with its own maintainers: a `Family` names its classes and holds their rules, levels and own calls. Opt-in: an integration with none holds its classes itself. The integration keeps the transport, the default class, the rule order between families (`families/__init__.py`) and every refusal entry (`refusals.py`, merged in by `class_scope`). | `Family`, `FamilyScope` and `class_scope` in `core/scope.py`; `check_families` in `core/registry.py`; `core/rules.py`; [CLAUDE.md](../CLAUDE.md#maintainers) |
| **Groups**: `IntegrationInfo.is_group`, `expand_group`, `AdapterScope.native_groups` | A native group (a Hue zone, say) goes to the device as one command. `is_group` recognizes one; `expand_group` lists its members, sync and with no I/O; an adapter with `native_groups` gets the group as one target. `expand_group`'s members give the group its classes and are what it falls back to when a member's class is refused, takes a call of its own, or is Experimental with the option off; an adapter without `native_groups` gets them as its targets. | `core/dispatcher.py`'s module docstring, Native groups; [evidence.md](evidence.md#device-classes), Groups |
| `IntegrationInfo.setup`, `remove` | `setup` starts what the integration keeps running while the entry is loaded, as the entry's background task, and registers its own teardown with `entry.async_on_unload`; `remove` undoes what it changed outside HA as DeviceSide is deleted. A hook that raises is logged and isolated. The component root names no integration. | `IntegrationInfo` in `core/scope.py`; `_guarded` in `__init__.py` |
| `IntegrationInfo.detect` | Picks this integration over a generic sibling on the same `ha_domain` (Zigbee2MQTT over plain MQTT): a different gateway or API is an integration of its own. | [evidence.md](evidence.md#the-split-rule); Resolver, below |
| `IntegrationInfo.unsupported` | Refuses a gateway or API DeviceSide never supports, as `integration_not_supported` with its reason: listed in its sibling's module as `UNSUPPORTED`, it claims entities by `detect`, has no adapters, and is kept out of the cards and gates. | `IntegrationInfo` in `core/scope.py`; `AdapterRegistry` in `core/registry.py` |
| `IntegrationInfo.zigbee_manufacturer` | The device's own Zigbee manufacturer string for the device report form, where HA's registry holds another. | `IntegrationInfo` in `core/scope.py` |
| `IntegrationInfo.call_resolver` | Drops what a light or scene call from HA leaves stale. | `core/ha_watch.py` |
| `IntegrationInfo.max_concurrency`, `AdapterScope.max_concurrency` | How many sends run at once. | [Concurrency](#concurrency) |
| `AdapterScope.domains`, `fields` | The entity domains and fields the adapter is built for, each at its level; outside them a call is refused (`domain_not_tested`, `fields_not_tested`). Flagging every domain flags the whole adapter. | [evidence.md](evidence.md#levels); `Adapter.supports` in `core/adapter.py` |
| `AdapterScope.drops`, `unlisted` | Fields the integration can never send, dropped as a lacked field is; fields its devices take though the light's state says they can't. | [action-behavior.md](action-behavior.md#when-to-stop-an-automation): Lacks a field, Unlisted fields depart from core |
| `AdapterScope.capabilities` | A level per class, and per domain where its entry names some (`OnDomains`). | [evidence.md](evidence.md#device-classes) |
| `AdapterScope.no_known_method`, `not_built` | A class refused with a reason and a source (`NoKnownMethod`, `NotBuilt`). A class the integration names that the scope leaves out of `capabilities`, `no_known_method` and `not_built` is not built yet and refused; `not_built` holds only a class today's call would harm, on an action whose failure harms (`Action.failure_harms`, which the registry checks). A class is in at most one of the three. | [evidence.md](evidence.md#no-known-method-not-built-yet-on-trial); `AdapterScope.refusal` and `harms` in `core/scope.py` |
| `AdapterScope.own_calls` | A class's own call (`OwnCall`), which the dispatcher hands the adapter in place of `execute`, optionally with its own duration limits (else the scope's `duration`). Each class in it must be in `capabilities`. | [evidence.md](evidence.md#the-split-rule); `OwnCall` in `core/scope.py` |
| `AdapterScope.duration` | The durations the call can carry (`DurationLimits`): a request outside them is clamped, and the result says so. | [action-behavior.md](action-behavior.md#when-to-stop-an-automation): A value the device can't reach; `core/duration.py` |
| `AdapterScope.confirmable`, `options`, `notes` | Declarations core doesn't act on, read by the rig: `confirmable`, that a run expects status `confirmed`, not `sent`; `options`, the DeviceSide options that change what it does (`predicted_state`), whose rig records are `<action>-<option>.json`; `notes`, free text. | `AdapterScope` in `core/scope.py`; [evidence.md](evidence.md#sign-off-format) |
| `AdapterScope.caveat` | A risk mark, set by a repo maintainer; changes no call. | [evidence.md](evidence.md#caveats) |

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
  lacks, checks `supports()`, the class and the Experimental gate, clamps durations, runs every adapter concurrently
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

- `services.yaml` holds only target filters and field selectors; names and descriptions are in `strings.json`.
  Target filters list exactly the integrations with an adapter for the action. They are a UI convenience: adapters
  enforce scope through `supports()`.
- Field filters can only test `supported_features` and attributes, not domain, so light fields copy
  `light/services.yaml`'s `supported_color_modes` filters; a switch-only selection shows just `duration`.
- Adding an action means a block each in `services.yaml`, `strings.json` and `icons.json`;
  `tests/core/test_actions_setup.py` checks all three.

## Release gates

The rules are in [evidence.md](evidence.md#release-gate); each gate's mechanics are in the header of the script or
workflow named.

- **Coverage:** `scripts/check_release.py --coverage`, in CI.
- **Sign-offs:** `check_release.py --signoffs`, in `cut-release`; `--notes` writes the call for testers in both cut
  workflows.
- **Tags:** `scripts/check_tag.py`, in `cut-release-candidate.yml` and `cut-release.yml`, the only way a tag is made.
- **RC audit:** `scripts/check_audit.py`, in `cut-release-candidate`.
- **Testing:** unit tests mock each integration at its boundary (its client, service or broker) against a real
  `hass`, and record each action's call transcript there (`tests/transcripts.py`, the boundaries in
  `tests/integrations/<x>/wire.py`); the rig runs against a live HA and writes the records.
