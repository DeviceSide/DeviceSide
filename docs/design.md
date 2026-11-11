# Design

How DeviceSide is built and why. What each integration does for users is in its bundle's `index.md`, under
`docs/integrations/<integration>/`, with what they share in [integrations.md](integrations.md); what goes on the wire,
and what was measured on real devices, is in the bundle's `internals.md`, with what they share in
[internals.md](internals.md).

## Glossary

Code and docs use these terms.

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
- **Scope**: the entity domains, capabilities and fields an adapter is built for, each at a Level. Outside it, calls
  are refused as not yet tested.
- **Level**: how well a scope item is proven (Verified, Reported, Documented or Experimental): rules in
  [CLAUDE.md](../CLAUDE.md#release-flag).
- **Support**: who fixes a bug in a call, from the proof behind each item it touches: rules in
  [CLAUDE.md](../CLAUDE.md#release-flag).
- **Experimental features**: the option (`experimental_features`, off by default) that lets calls touching an
  Experimental item through. Only the dispatcher reads it.
- **Release flag**: `experimental=True` on an adapter's scope keeps the whole adapter in release candidates only. Not
  the Experimental level, which gates an item at runtime. Rules: [CLAUDE.md](../CLAUDE.md#release-flag).
- **Rig**: the maintainer's live Home Assistant and devices, and the private tool that runs DeviceSide's actions on
  them and writes test records. It is kept outside this repo; the records are its output here.
- **Test record**: the evidence that an adapter works on real hardware, from a rig run:
  `docs/integrations/<integration>/records/<action>*.md`. Clearing `experimental` cites one.
- **Device report**: a user's "works" or "doesn't work" for an action on a model. In the bundle's `devices.yaml` each
  one names the `item` its call reached (the domain, or the capability for an adapter that lists them). An accepted
  "works" on an item's call makes it Reported; a "doesn't work" is evidence for a fix or for leaving the item out.
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

Integrations: Zigbee2MQTT (via `mqtt`), ZHA, Matter, Shelly Gen2+ and Hue (CLIP v2). Each adapter's `AdapterScope`
says what it covers, and `scripts/check_release.py` lists every adapter. Each integration's docs, data and records
are its bundle, `docs/integrations/<integration>/`, which [CLAUDE.md](../CLAUDE.md#where-facts-go) lays out. What
can't be built where, and why: `NO_PATH` in `scripts/gen_features.py`, the
README's prohibited signs, explained to users in
[integrations.md](integrations.md#what-cant-be-done-and-why).

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

Not built yet: turn-on defaults (`OnLevel`), Shelly Gen1, Hue bridge v1, other domains (cover, valve, lock) and other
integrations (Z-Wave JS, Tuya, ESPHome, Tasmota, TP-Link Kasa). Each is weighed against the broad-appeal principle
in [CONTRIBUTING.md](../CONTRIBUTING.md#development-principles). Per device class:
[device-compatibility.md](device-compatibility.md).

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
  `ADAPTER_TIMEOUT_S`: `Adapter.slot` (which `gather` runs each target in) rejects with `timeout` only the targets
  not done by then, so those that finished keep their results. An adapter exception rejects its targets. A named
  target that can never take the action raises before anything is sent; an indirect one is skipped and logged; a
  device failure raises once every target has run.
- **Experimental items** are gated here, at runtime. After `supports()` passes a target and fields are dropped,
  `Dispatcher.run_adapters` takes the call's level from its domain, the capability `Adapter.capability()` names
  (Shelly: the RPC component; one it can't name counts as Experimental) and the fields it still carries. An
  Experimental one is refused as `experimental_off` while the option is off, raising its own message for a named
  target. A call left nothing to send is unchanged, not refused.
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

Each gate's rules are in the header of the script or workflow named.

- **Coverage:** `scripts/check_release.py --coverage`, in CI.
- **Release flag:** `check_release.py --release`, in `cut-release`.
- **Record freshness:** `check_release.py --records`, in both cut workflows.
- **Tags:** `scripts/check_tag.py`, in `.github/workflows/cut-release-candidate.yml` and `cut-release.yml`, the only
  way a tag is made.
- **RC audit:** `scripts/check_audit.py`, in `cut-release-candidate`.
- **Testing:** unit tests mock each integration at its boundary (MQTT's publish and subscribe, the ZHA service, the
  Shelly RPC, the Matter client, aiohue) against a real `hass`. The rig runs against a live HA and writes the test
  records.

**Extensions (planned):** an adapter its contributor maintains, on hardware the rig lacks, marked 🧩 on the cards.
Its route to stable, other than the rig, is left open.
