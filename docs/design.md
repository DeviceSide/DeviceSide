# Design

How DeviceSide is built and why. What each integration does for users is in [integrations.md](integrations.md); what
goes on the wire, and what was measured on real devices, is in [integration-internals.md](integration-internals.md).

## Glossary

Code and docs use these terms. "Platform", "backing" and "claim" are retired; `services.yaml` keeps its name because
HA requires it.

- **Action**: what the user calls, e.g. `deviceside.turn_on_for`.
- **Feature**: the user experience one or more actions deliver (turn on with timer, smooth dimming). Prose only.
- **Integration**: the HA integration that is the first hop to the device (Shelly, ZHA, MQTT, Hue).
- **Bridge**: a separate system between the integration and the device, named only when the integration alone
  doesn't say how the device is reached (Zigbee2MQTT behind MQTT). The Hue Bridge is not counted.
- **Adapter**: one action on one integration (or bridge).
- **Capability**: the device-side functional unit the adapter's call reaches, in vendor terms (Shelly component,
  Zigbee or Matter cluster).
- **Field**: an action parameter, e.g. `brightness`.
- **Entity domain**: light, switch. "Domain" alone is fine where unambiguous.
- **Scope**: the entity domains, capabilities and fields an adapter is known to work with, on tested hardware.
  Outside it, calls are refused as not yet tested.
- **Rig**: the maintainer's live Home Assistant and devices, and the private tool that runs DeviceSide's actions on
  them and writes test records. It is kept outside this repo; the records are its output here.
- **Test record**: the evidence that an adapter works on real hardware, from a rig run:
  `docs/test-records/<integration>/<action>*.md`. Clearing `experimental` cites one.
- **Profile**: one test setup on the rig's HA, the entities a run may move by integration and role; a record names the
  one it ran on (`lab`, `house`).

## Principles

- **On the device.** Once the command is sent, the behavior completes (or degrades to plain device behavior) with
  HA offline. No HA-side timers, polling or emulation; docs show how to build emulation with `set_attributes` and an
  automation instead.
- **What gets built:** see [CONTRIBUTING.md](../CONTRIBUTING.md#what-gets-built).
- **One action per user intent, not per protocol primitive.** Zigbee has move, step and move-to; DeviceSide has one
  raise and one lower per attribute, and the adapter picks the command.
- **Human terms.** Fields describe what the light should do, never how the device does it: no rates, steps, mireds
  or cluster vocabulary. The adapter converts.
- **Behave as core does.** When to raise, what to skip and what a response holds follow HA core's own actions:
  [action-behavior.md](action-behavior.md).
- **Drop-in for Hue Smooth Dimming.** `set_attributes`, `get_attributes` and `set_scene` take its field names,
  units (brightness in percent) and response shape; its `raise`/`lower` are `raise_brightness`/`lower_brightness`.
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

Integrations: Zigbee2MQTT (via `mqtt`), ZHA, Matter, Shelly Gen2+ and Hue (CLIP v2). Which adapter exists, and its
scope, is in each adapter's `AdapterScope`; `scripts/check_release.py` lists every adapter and whether it is
experimental.

- **`turn_on_for`, `turn_off_for`** (turn on with timer, turn off with timer): on, then off after `duration` (or
  the reverse), timed on the device. `turn_off_for` is Shelly only: Zigbee and Matter `OnWithTimedOff` is on-then-off only.
  `turn_on_for` accepts the `light.turn_on` fields; Shelly sends them in one RPC, the others send a `light.turn_on`
  first. What cancels a timer differs by integration ([integrations.md](integrations.md)). Hue has neither: its bridge
  timers ignore manual on/off, so they can't be cancelled the way users expect.
- **`set_auto_off`, `set_auto_on`, `clear_auto_off`, `clear_auto_on`** (auto-off and auto-on): Shelly only. A
  persistent setting stored on the device, applied after every turn-on (or turn-off) from any source: button, app,
  schedule or Home Assistant. Core's Shelly integration doesn't expose it. A call that changes nothing sends
  nothing and returns `unchanged`; one that does writes flash and makes core reload the Shelly entry about a
  minute later ([integrations.md](integrations.md)).
- **`raise_*`, `lower_*`, `stop`**: one action per attribute (brightness, saturation, hue) and direction, as HA names
  its direction actions (`cover.open_cover`, `fan.increase_speed`). `sweep_time` is how long a full range takes, so
  the speed is the same wherever the move starts; `limit` ends the move early. A call already at or past its limit
  returns `unchanged`. `stop` halts every move in flight on the target. There is no hue limit, and no color
  temperature move: every stop of a Hue bulb's color temperature fade jumps visibly. Hue has no hue moves: a hue
  rotation isn't a straight line in xy, so it can't be one bridge command.
- **`set_attributes`, `get_attributes`**: write brightness, color or color temperature to a light without turning
  it on, and read what HA doesn't show (attributes while off, a running timer, Shelly's auto-off and auto-on). Every timed or set-while-off adapter
  needs a matching `get_attributes` on its integration.
- **`set_scene`**: Hue only. A Zigbee scene recall turns lights on.

Out of scope until users ask: turn-on defaults (`OnLevel`), Zigbee plugs and switches, Shelly Gen1, Hue bridge v1,
other domains (cover, valve, lock), and other integrations (Z-Wave JS, Tuya, ESPHome, Tasmota, TP-Link Kasa). What v0.1.0 refuses for want of hardware
the rig lacks, and which entries a tester could prove: [hardware-the-rig-lacks.md](hardware-the-rig-lacks.md).

## Architecture

Facts from HA core this rests on:

- `helpers/group.py:expand_entity_ids` expands only `group.*`. A light or switch group helper is not expanded by
  target extraction, so `core/groups.py` expands it through `get_entity_ids`.
- `zha.issue_zigbee_cluster_command` is an admin service, so adapters forward the caller's `call.context`.
- HA auto-imports top-level modules named after entity platforms and after `group`, `diagnostics`, `repairs` and the
  like, so adapters live under `integrations/` and nothing at the top level is called `light.py`.
- Schemas use `probatio` and reuse `light.const.LIGHT_TURN_ON_SCHEMA` entries, so ranges never drift from core.
  `set_attributes` keeps Hue Smooth Dimming's percent brightness instead.

### Layout

```
custom_components/deviceside/
  __init__.py, config_flow.py, const.py, manifest.json, services.yaml, strings.json, icons.json, translations/
  core/
    models.py        Status, ActionKind, Request, Target, EntityResult, LightFields
    scope.py         AdapterScope, IntegrationInfo, DurationLimits
    action.py        Action base class
    adapter.py       Adapter base class; gather() runs sends under the concurrency limits
    registry.py      AdapterRegistry: discovery, guarded import, lookup, matrix
    resolver.py      entity_id -> Target, or the reason it can't be served
    groups.py        HA group expansion, any domain
    dispatcher.py    parse, extract, expand, resolve, plan, run, raise rule, response
    ha_watch.py      drops predictions a light or scene call from HA leaves stale
    transition.py    a move's predicted value, per integration
    runtime.py       DeviceSideData in hass.data: registry, dispatcher, semaphores, integration state
  actions/           one module per action, each exporting ACTION
  integrations/<integration>/   INTEGRATION, ADAPTERS, one module per adapter, shared helpers
scripts/             release, tag and audit checks, household check
tests/{core,actions,integrations,scripts}   unit tests, mirroring the code; tests/fakes holds a fake integration
```

### Core contract

- **Registry.** `pkgutil` discovery over `actions/` and `integrations/`. Modules export data (`ACTION`,
  `INTEGRATION`, `ADAPTERS`), not decorators, so import has no side effects, order is sorted and deterministic, and
  `check_release.py` and the rig, from outside the repo, import the registry without `hass`, so a change to
  `AdapterRegistry`'s interface needs the rig's matching change. A failing integration import (its core
  integration isn't installed) records it unavailable and setup carries on.
- **Resolver.** Candidates are the available integrations whose `ha_domain` is the entity's registry platform;
  one with a `detect` hook wins first (Z2M over plain MQTT). A `switch_as_x` light resolves to the switch it wraps,
  and results report the light.
- **Groups.** HA groups are always expanded, in one place, because no device can address them; members carry
  `via_group`. Native groups (Hue `grouped_light`, Z2M and ZHA groups) pass through as one target. An adapter with
  `native_groups` gets the group; for one without, the dispatcher calls the integration's `expand_group`, or refuses
  with `group_not_supported` when there is none.
- **Dispatcher.** Buckets targets by adapter, drops fields a target lacks, checks `supports()` (domain, fields and
  capabilities in scope), clamps durations to `AdapterScope.duration`, then runs every adapter concurrently under
  `ADAPTER_TIMEOUT_S`. An adapter exception rejects its targets. A named target that can never take the action
  raises before anything is sent; an indirect one is skipped and logged; a device failure raises once every target
  has run.
- **Results.** Commands answer optionally, per entity: `{status, integration, clamped_to?, detail?}`, where status is
  `sent`, `confirmed` (read back from the device) or `unchanged` (nothing to send). Queries answer only, in core's
  shape: each target's data under its entity_id, as `weather.get_forecasts` does.
- **Actions** register once in `async_setup` and refuse calls until the config entry loads.

### Concurrency

Each command runs under two semaphores, applied in `Adapter.gather()`: the integration's
(`IntegrationInfo.max_concurrency`: Hue, ZHA and Matter 2; Shelly and Z2M 4) and the adapter's
(`AdapterScope.max_concurrency`). Hue is 2 because aiohue's cap of 3 is shared with core. `execute` gets all of an
adapter's targets at once, so native group commands stay possible.

### services.yaml, strings, icons

- `services.yaml` holds only target filters and field selectors; names and descriptions are in `strings.json`.
  Target filters list exactly the integrations with an adapter for the action. They are a UI convenience: adapters
  enforce scope through `supports()`.
- Field filters can only test `supported_features` and attributes, not domain, so light fields copy
  `light/services.yaml`'s `supported_color_modes` filters; a switch-only selection shows just `duration`.
- Adding an action means a block each in `services.yaml`, `strings.json` and `icons.json`;
  `tests/core/test_actions_setup.py` checks all three.

## Release gates

- **Coverage.** CI runs `scripts/check_release.py --coverage`, failing any adapter module under 95% line coverage.
- **Release flag.** `experimental=True` keeps an adapter out of a stable release; `cut-release` runs
  `check_release.py --release`, which fails on any. Setting and clearing it: [CLAUDE.md](../CLAUDE.md#release-flag).
- **Record freshness.** `cut-release-candidate` and `cut-release` run `check_release.py --records`, failing any
  released adapter with no test record, or one whose code changed after the commit a record cites. An adapter's code
  is its module, its integration package's `__init__.py` and the package modules it imports, transitively; `core/`
  and `actions/` are not, as they are unit-tested and shared by every adapter. Experimental adapters are exempt.
  There is no runtime gate: a capability or field nobody has tested is left out of scope, so `supports()` refuses it.
- **Tags** come only from the `cut-release-candidate` and `cut-release` workflows (a tag ruleset refuses others).
  `scripts/check_tag.py` refuses a tag that isn't `vX.Y.Z` or `vX.Y.ZrcN` or doesn't match its branch, and an RC
  needs its audit record (`scripts/check_audit.py`).
- **Testing.** Unit tests mock each integration at its boundary (`mqtt.publish`, the ZHA service, the Shelly RPC,
  the Matter client, aiohue) against a real `hass`. The rig runs step files against a live HA and writes the test
  records.
