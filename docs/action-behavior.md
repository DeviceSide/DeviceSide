# How actions behave

When an action stops an automation, what it skips and what its response holds all match Home Assistant core,
since users, blueprints and templates already expect core's behavior. For a case not covered here, read core's code
and match it; DeviceSide's own habits are not precedents.

The facts below were read from HA 2026.10.2: `helpers/service.py` (`entity_service_call` and the functions it
calls), `helpers/target.py` (`async_extract_referenced_entity_ids`), `components/light/helper.py`
(`filter_turn_on_params`) and `helpers/template/extensions/functional.py` (`merge_response`). Re-read them when HA
changes; `.venv` holds the version CI runs.

## When to stop an automation

An exception from an action stops the automation unless the step sets `continue_on_error`. Core raises only
when the call is wrong or a device failed, never because some targets didn't apply:

| Situation | Core | DeviceSide |
|---|---|---|
| Invalid input (out of range, wrong type) | Raises at the schema | Raise at the schema |
| A target is unavailable or missing | Skips it, logs "Referenced entities ... are missing or not currently available" | Skip and log alike |
| No target given (an empty selection) | Returns, nothing raised | Return |
| No targets left after skipping | Returns, nothing raised | Return |
| The same, when the caller asked for a response | Raises: no entity matched | Raise `no_entities_matched` |
| `entity_id: all` | Targets every entity of the domain, none named, so none raises or logs as missing | Same: every light and switch is indirect, so one that can't take the action is skipped with the warning |
| A target the caller named can never support the action | Raises `ServiceNotSupported` | Raise `target_not_supported`, before anything is sent |
| The same target reached indirectly | Skips it silently | Skip it, with one warning per call listing each target and why |
| A named entity of a domain the action doesn't take (a sensor in a light action) | Logs it as missing and carries on | Raise `target_not_supported` (`domain_not_supported`): the call names the wrong entity, which a log line would hide |
| A light can't take one field (color on a white bulb) | Drops the field silently and acts on the rest | Drop it, act on the rest, `detail: fields_dropped` |
| The device or its integration fails | The error propagates | Run every target, then raise `targets_failed` listing the failures |
| DeviceSide's entry isn't loaded (disabled, or its setup failed) | Raises `service_config_entry_not_loaded` | Raise `not_loaded`, before anything is resolved |

Why: a mixed room must not abort an automation over the lights that can't take part, but a call that names
the wrong entity, or a device that failed, should stop it, because carrying on would hide the mistake.

**Named or indirect.** A target is named when the caller listed its entity ID. Everything else is indirect:
an area, device or label, a member of an HA group (`group.*` or a group helper), or a member of a native group
the dispatcher expanded. Core treats a `group.*` member as named; DeviceSide doesn't, because a group is a
deliberately mixed set. An indirect entity outside the action's domains is never a target, as in core.

Two outcomes for a field or target that can't be served, by what holds it back:

| Refused: **can never support** (a reason that holds whatever the device's state) | Dropped: **lacks a field** (the target can't take that one field) |
|---|---|
| No adapter | A field the target's state says it lacks, read as `filter_turn_on_params` reads it: a color only without any color mode, color temperature only without that or a color mode, since core converts between them first |
| An integration or gateway DeviceSide doesn't support (`integration_not_supported`) | A field only the adapter knows is lacked (`AdapterScope.drops`, a color gamut, a component's fields) |
| A domain or option nobody has tested | A field tested on one kind of component but not yet ported or recorded for another |
| A class with no known method or not built yet (`no_known_method`, `not_built`) | A field in Labs on the target's class while the Labs option is off (`AdapterScope.class_labs`, [evidence.md](evidence.md#levels)) |
| An entity the integration can't address | Every light field, on a `switch` or a `switch_as_x` light, so a timed call still runs its timer |
| A field the adapter has never been tested with: refused, never dropped | |

A call left nothing to do by dropping is `unchanged` with `fields_dropped`. An empty group is skipped silently, as core's group expansion yields nothing for one.

**Not yet classed** (`class_unknown`), where a call is known to harm a class, is refused the same way, raised if named
and skipped if not, but it is usually transient: it holds only until the integration has reported the device or group
([evidence.md](evidence.md#no-known-method-not-built-yet-in-labs)). That usually takes seconds, so an automation firing
at startup can get it; if the integration never reports it (DeviceSide couldn't connect to it), it holds until
DeviceSide reloads, and a device that never finishes pairing holds until it is paired again. A target DeviceSide can't
class at all (an entity with no device, a classifier that raised) is refused the same way, for good. A native group with a member refused either way falls back to its members, like any refused member (Native groups in
[`core/dispatcher.py`](../custom_components/deviceside/core/dispatcher.py)).

**Unlisted fields depart from core.** An adapter may name, in `AdapterScope.unlisted`, fields its devices take although
the light's state says they can't; a light never lacks those for that adapter, where `filter_turn_on_params` would drop
them. Why: DeviceSide fills design gaps between an upstream integration and HA
([integrations.md](integrations.md)): an integration that leaves a mode out of `supported_color_modes` shouldn't stop
a device that has it. HA's own UI still shows the light without the mode, and
`light.turn_on` still drops the field. An unlisted field must be in the adapter's `fields`, at its own level: fields are
never Documented, so it starts in Labs. A `switch` still lacks every light field.

**A value the device can't reach** passes the schema but lies outside what the device can do: a timer longer than its
counter, or a `sweep_time` outside what the device's native move takes. It is clamped
to that range and the result carries `clamped_to`, the value used. It isn't refused, as the call can still do the
nearest thing, and it isn't `fields_dropped`, which is for a field the light lacks. Rounding inside the range isn't
reported, except where the device's timer runs in coarser steps than the request (whole seconds, say): there the
result carries `clamped_to` too, as the timer won't end when asked.

## What a response looks like

Core's entity actions return `{entity_id: <that entity's data>}`, one entry per entity that ran, for example
`{"weather.home": {"forecast": [...]}}` from `weather.get_forecasts`. There is no status per entity: a failure
raises or the entity is skipped.

A response entry holds these keys:

| Key | On | Holds |
|---|---|---|
| `timer` | a query, for a target with an on/off timer running (from `turn_on_for`, `turn_off_for` or the device's own) | `{turns, ends_at, remaining_s}`: `turns` is `on` or `off`, the state the timer leaves it in; `ends_at` is UTC ISO 8601; `remaining_s` is seconds, to one decimal. Absent with no timer running. The time left is always the device's; DeviceSide never tracks one. A device whose time left DeviceSide can't read is refused (`no_known_method`); one it can read but not trust at the moment (its clock unsynced) has no `timer` key. The integration's page says which. |
| `auto_off`, `auto_on` | a query, for a target whose device has these settings | `{duration}` (seconds) while set, `null` while clear. A key is absent when the setting couldn't be read, so absent never means clear. |
| `status` | a command | `confirmed`, `sent` or `unchanged` |
| `integration`, `detail`, `clamped_to` | a command | the integration; `detail` and `clamped_to` where they apply |
| `capability` | an entry, on an integration that names [classes](evidence.md#device-classes) | the class the call reached (a string: `"RGBCCT"`). A command's is beside `status`, a query's among its data. Absent when the integration couldn't name one, or only provisionally (a device not yet [placed](design.md#glossary)). Appears on an `unchanged` entry too |
| `capabilities` | a native group's entry | its members' classes once each, sorted (a list: `["hue", "other"]`). Absent when any member's is absent, so a list stands for the whole group and never for a class that could still move |
| `member_capabilities` | a native group's entry | each member's entity_id to its class (a map: `{"light.one": "hue", "light.two": "other"}`), as the one call reached each member. Absent when no member is left. Appears on an `unchanged` entry too, where nothing was sent: a reader crediting evidence credits only an entry whose status shows a send |

`member_capabilities` leaves out a member with no class or only a provisional one, and only that member, so a group with one member not yet placed still names the rest. It also leaves out every member core didn't reach through its own available entity (availability judged when the call is planned), whose class still counts in `capabilities`: one that is unavailable; one core resolves only through a stand-in, as a plug in a light group (which HA exposes as a switch, or a `switch_as_x` light wraps) or a disabled member; and a device with more than one entity in the group's domain, which DeviceSide can't address on its own.

- **Queries** (`get_attributes`, on lights and switches) return core's shape: each target's data under its entity ID, nothing else, the class among it. A target that couldn't be read raises `targets_failed` once every target has run, as any device failure does. Templates read `response['light.desk'].brightness`.
- **`merge_response`** turns that shape into a list of the entities' dicts with `entity_id` added to each, so
  a blueprint can loop without knowing the IDs. It requires every value to be a dict and raises if one already
  has an `entity_id` key, so query data never carries `entity_id`.
- **One entry per target.** A room returns one entry, not one per light as well, so `merge_response` lists each
  target once.
- **Commands and settings** return nothing in core. DeviceSide keeps an optional status response, one entry per target that ran. Skipped targets are left out, as core leaves them out, and `unsupported` or `rejected` never reach a response: the call skips or raises instead. A call that has nothing to do succeeds quietly as `unchanged` with a `detail`, checked before the target's class, so nothing-to-do wins over no known method or not built yet. A named target whose class has no known method, or is not built yet and is harmed by today's call, raises with the reason why.
- **A native group** that falls back to its members has no entry of its own, so no `member_capabilities`: each member's entry carries its `capability`. When it is refused, and what its members answer for: Native groups in [`core/dispatcher.py`](../custom_components/deviceside/core/dispatcher.py).

## Replacing hue_dimmer

DeviceSide's actions are drop-in replacements for those of Hue Smooth Dimming (`hue_dimmer`,
[jasonmx/hue-smooth-dimming](https://github.com/jasonmx/hue-smooth-dimming)): a user changes only the domain, and
renames `raise`/`lower` to `raise_brightness`/`lower_brightness`, which take the same fields. That means the same
field names and units (brightness in percent), names and descriptions in the UI, the same response shape, and
hue_dimmer's input habits: `0` leaves `min_brightness`, `max_brightness` or `color_temp_kelvin` unset, and given
several colors, `rgb_color` wins, then `hs_color`, then `xy_color`. Before changing any of these, check hue_dimmer
and say what breaks for its users. README's migration box is the user-facing version of this section.
