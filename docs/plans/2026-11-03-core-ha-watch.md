# 13f follow-up: one core watch for light calls from HA

`TODO.md` 13f follow-up. A light or scene call made from HA (a dashboard, an automation, a script) can change a light
while a fade of ours runs. Its prediction then goes stale, and the light's next move or stop plans from the wrong
value. 13f's lab probe found this on ZHA (`docs/plans/2026-10-28-zha-move-stop.md`, handoff step 2).

Hue and ZHA each run their own listener for these calls: `ReportFilter._on_service_call` in `hue/report_filter.py`,
and `watch_ha_changes` in `zha/fade.py`. Z2M has none. This change moves all three onto one listener in `core/`, with
a resolver for each integration.

## Decisions (interview, 3 Nov)

- **A call drops every prediction of each light it names**, brightness and saturation, whatever fields it sets. This
  is what Hue and ZHA do today, so Hue's released behavior stays the same.
- **ZHA: a call cancels a pending soft-off restore.** The call replaces our fade, as on Hue, where a forget drops the
  ends still to show. The end refresh still runs. An HA off during a soft off leaves the bulb at its mid-fade level.
- **ZHA and Z2M: a call that sets a color or turns the light off clears the light's `hue_moves` mark**, since that ends
  the bulb's hue cycle. The calls that do this are `turn_off`, `toggle`, and a `turn_on` with any of `hs_color`,
  `xy_color`, `rgb_color`, `rgbw_color`, `rgbww_color`, `color_name`, `color_temp_kelvin`, `white` or `effect`. A
  brightness-only call keeps the mark.

## Design

**`core/ha_watch.py`.** One `EVENT_CALL_SERVICE` listener for the `light` and `scene` domains. It attaches in
`async_setup_entry` (as built: unloading detaches every listener, and a reload runs only that) and detaches with the
entry, through `runtime.listen`. For each call it:

1. Returns at once if no resolver is busy (`busy(hass)`: has predictions, ends still to show, or hue marks). Most
   light calls cost nothing.
2. Resolves the call's target once: `entity_id: all`, or `async_extract_referenced_entity_ids` (referenced and
   indirectly referenced) with each entity's registry entry.
3. Hands each integration's resolver the entries whose platform it owns, together with a `Call` (domain, service,
   service data, `ends_hue_cycle`).

A resolver is declared once for each integration, from the integration package (as built: `IntegrationInfo.call_resolver`,
not a `register()` call, so the registry stays free of side effects), and has this shape:

```python
class CallResolver(Protocol):
    def busy(self, hass) -> bool: ...
    def forget(self, hass, call: Call, entries: list[RegistryEntry] | ALL) -> Awaitable[None] | None: ...
```

`forget` maps entries to the integration's cache keys, drops them, and runs whatever must follow (the "hook after the
forget"). Most resolvers are synchronous and finish before the listener returns, so they are applied before the call's
service runs.

**Z2M groups need an async resolver.** A Z2M group's members come only from the retained `bridge/groups` message
(`member_lights` is async). In that case the core holds the task in a pending set, and `ha_watch.settled(hass)` awaits
that set. The dispatcher calls `settled` before it runs any adapter, so a move made straight after an HA call always
plans after that call's forget. Direct Z2M lights, Hue and ZHA stay synchronous.

**Hue** (`hue/report_filter.py`): `_on_service_call`, `_lights` and `_is_light_call` move into the Hue resolver. The
resolver finds the bridge's filter by `entry.config_entry_id` in `integration_state[FILTERS]` and calls the existing
`forget(hass, light_id)`, so `_forgotten`, `hand_back` and the end keys stay unchanged. `ReportFilter.attach` keeps
only the bridge event subscription. `forget`, `write_forgetting` and `_scene_lights` keep their signatures: the
bridge's scene events and the adapters still use them. For `entity_id: all`, the resolver forgets every light of every
attached bridge, as today.

**ZHA** (`zha/fade.py`): `watch_ha_changes` and its call from `ZHARamp.execute` are deleted. The resolver maps a group
entity to `light_members` and any other entity to its own entity_id (as today), then:
- calls `cache.forget(light_id)`
- discards `light_id` from a new `zha_restores` set; `end_job` restores only lights still in that set, and the fade
  adds its restores to it when it starts
- clears the hue mark when `ends_hue_cycle`

For `entity_id: all`, it does the same to every light the cache, `zha_restores` and `hue_moves` hold.

**Z2M** (`zigbee2mqtt/fade.py`): a new resolver. A light entity maps to itself. A group entity maps to its members
through `member_lights` (async). The resolver then forgets those lights and clears their hue marks when
`ends_hue_cycle`. The end read-back stays: it reads the bulb.

**Our own calls.** Hue and ZHA send commands outside the `light` domain, and Z2M publishes over MQTT. The one
exception is Z2M's `turn_on_for`, which calls `light.turn_on`, so its target's predictions are now dropped. That is
right: it changes the light.

No change to `experimental`: Hue keeps its behavior (this is a refactor), and the ZHA and Z2M ramp adapters are
already experimental.

## Steps

1. `core/ha_watch.py`, with unit tests (`tests/core/test_ha_watch.py`): the idle short cut, `all`, area and device
   targets, a registry entry for another platform, async resolution with `settled`, detach on unload, and a resolver
   that raises (logged, so the others still run).
2. Hook `settled` into the dispatcher before adapters run, and attach the watch in `async_setup`.
3. Move Hue onto the watch. Move the tests that drive `_on_service_call` so they call through the watch instead, and
   keep their assertions word for word: they are the evidence that Hue's behavior is unchanged.
4. Move ZHA onto the watch. Add `zha_restores` and the hue-mark rule, with tests: an HA off during a soft off leaves no
   restore and still refreshes; a brightness-only call keeps the hue mark, and a color call clears it.
5. Add the Z2M resolver, with tests: a call during a fade drops the prediction, so a `stop` after it halts from HA's
   state; a group call drops its members (async, through `settled`); the hue-mark rule.
6. `.venv/bin/pytest`, `pre-commit run --all-files`, and check that each touched adapter module still has ≥95%
   coverage.
7. `/audit-code` on the diff, then fix what it finds.
8. **Rig run, with Jason's go** (the morning pre-authorization ends at 11:30). Run each in the background with
   `DEVICE_SIDE_RIG_APPROVED=1` once approved; it queues behind the lock (`--wait-free` only waits, and runs nothing). On `--profile lab --unattended`:
   - Hue predicted-state: `--integration hue --action raise_brightness --action lower_brightness --action stop`
     (this selects the `-predicted_state` step files)
   - Z2M: `--integration zigbee2mqtt --action raise_brightness --action lower_brightness --action stop`
   - ZHA, one short run of the case the old watch fixed: `--integration zha --action stop -k halts_a_raise`

   Brief Jason on any failure before rerunning.
9. Tick the 13f follow-up in `TODO.md`, then open a PR into `release/v0.0.2` (or whichever of it and `main` is newer).

## Coordination

7c2 (Hue saturation, `../device_side-hue-saturation`, branch `wt/hue-saturation`) adds a `SATURATION` entry to
`hue/attributes.py` and may touch `classify`/`owned` in `report_filter.py`. It leaves the call path, `forget`,
`_forgotten` and `fading` alone. `forget()` and `write_forgetting()` keep their signatures here. Whichever PR lands
second merges the other in (no rebase).
