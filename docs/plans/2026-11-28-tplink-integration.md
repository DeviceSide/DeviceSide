# TP-Link integration: Kasa and Tapo countdowns

Copy this plan to `docs/plans/2026-11-28-tplink-integration.md` as the first commit, on branch `wt/tplink-integration`
off `main` in its own worktree, then `pr-draft docs/plans/2026-11-28-tplink-integration.md`.

## Coordination

Intent: add a `tplink` integration (core's `tplink`, python-kasa device objects) serving `turn_on_for`,
`turn_off_for` and `get_attributes`' `timer` on Kasa (IOT) and Tapo (SMART) plugs, switches, outlets and SMART
lights, from the device's own countdown rule.
Touches: `custom_components/deviceside/integrations/tplink/`, `tests/integrations/tplink/`, `tests/fixtures/tplink.py`,
`docs/integrations/tplink/`, `custom_components/deviceside/core/registry.py` (`CARD_ORDER`), `tests/test_card_order.py`
(if it lists columns), `scripts/gen_features.py` (`NO_PATH`), `docs/integrations.md`, `docs/deferred.md`,
`docs/word-budgets.yaml`, `README.md`, `docs/plans/`, generated files (`services.yaml` targets, CODEOWNERS,
`docs/device-compatibility.md`, device report form).
Depends-on: none.

## Context

TP-Link is a top-30 HA integration with long-running user demand for a timed off (research §7). Core's `tplink`
exposes no countdown; python-kasa has none it can write. The research
([call patterns](../research/2026-11-28-tplink-call-patterns.md), [KP115 probe](../research/2026-11-28-tplink-kp115-probe.md))
recommends a first scope of countdowns plus their read-back. Everything else is left to core, has no known method,
or waits for an owner (below).

## Decisions (Jason, 2026-11-28)

1. **SMART classes ship now, in Labs**: SMART plug/switch, strip child, hub child switch, and SMART lights (dimmers and
   bulbs). The call comes from the `tapo` library (signal) and python-kasa fixtures show the rule's shape. No source
   says what a manual switch does to a SMART rule.
2. **Current evidence rules apply.** Shipped code on another platform is a Labs source, not a pass. Hubitat's Kasa and
   Tapo drivers implement no countdown anyway. Any change to that rule is its own evidence.md PR, outside this plan.
3. **One IOT plug-and-switch class** (python-kasa `IotPlug` and `IotWallSwitch`: KP115, HS1xx, KP10x, HS200, HS210,
   KS200…): `verified(...)`, with its record coming from the release's rig run on the KP115, the only TP-Link device
   the rig reaches (tenet 8: no merge waits on it). A model that departs gets split off on its own.
4. **IOT strip outlets are their own class, in Labs** (`context.child_ids` addressing, unprobed).
5. **File the python-kasa namespace finding upstream** (step 5).

Claude's calls, for Jason to overrule in review:

6. **No light fields** on `turn_on_for` in this scope: the device turns on at its last state. Fields would need a
   SMART `set_device_info` call, which is unsourced while off (research §5).
7. **No class for a SMART device without the `countdown` component.** It answers the add with a device error, which
   comes back as REJECTED at once. The failure is visible, so it can't harm (tenet 6).
8. **Raw calls through the public `device.protocol.query(...)`**, not the private `_query_helper`. A SMART child's
   protocol already wraps `control_child`; an IOT outlet adds `{"context": {"child_ids": [id]}}` itself.
9. **IOT dimmers and bulbs are not built** (namespace unsourced): left out of every scope, plus a `docs/deferred.md`
   entry. IOT dimmer `set_attributes` brightness is deferred too (core's comment sources it; reopens with an HS220 or
   KS230 owner).
10. **Smooth moves and `stop`: no known method** on every class (no stop or move call exists). Recorded as `NO_PATH`
    cells for the tplink column, not as adapters. SMART auto-off is left to core (`index.md` points users to its
    entities); `set_auto_on` has no call on any class.

## Classes (`integrations/tplink/classes.py`)

| Class | Matches (python-kasa object) | Domains | turn_on_for / turn_off_for |
|---|---|---|---|
| `iot_plug` | IOT `plug`, `wallswitch` | switch | `verified` |
| `iot_strip_outlet` | IOT `stripsocket` | switch | `labs` |
| `smart_plug` | SMART `plug`, `wallswitch`, no parent | switch | `labs` |
| `smart_strip_child` | SMART child of a strip | switch | `labs` |
| `smart_hub_child` | SMART child switch of a hub (S210, S220) | switch | `labs` |
| `smart_light` | SMART `bulb`, `dimmer`, `lightstrip` (and dimmer children, e.g. KS240) | light | `labs` |
| `iot_light` | IOT `bulb`, `dimmer`, `lightstrip` | light | not built |

Key on python-kasa's `device_type` and IOT vs SMART, read from the config entry's device object
(`entry.runtime_data.parent_coordinator.device` and its `children`) by name: **never import `kasa` or
`homeassistant.components.tplink`**, so the module loads where TP-Link isn't installed (`shelly/addressing.py`'s
docstring). The entity is the device's primary `state` entity, whose unique_id is core's `legacy_device_id(device)`
(`tplink/entity.py` `_get_feature_unique_id`). Reimplement that two-line function, citing core. A strip parent's entity
and any other tplink entity can't be addressed (`unsupported_reason`). A device not yet loaded has no class
(`class_unknown`, as the action harms).

## The calls (`integrations/tplink/protocol.py`)

`DurationLimits(min_s=1, max_s=86400, step_s=1)` for every class. IOT's range comes from the probe (0 s is a silent
no-op, so it's never sent). SMART's 24 h is the `tapo` library's cap, from signal.

| | IOT (namespace `count_down`) | SMART |
|---|---|---|
| switch now | `system.set_relay_state {state}` | `set_device_info {device_on}` |
| clear | `count_down.delete_all_rules {}` | `remove_countdown_rules {remove_all: true}` |
| add | `count_down.add_rule {enable: 1, delay, act, name: "deviceside"}` | `add_countdown_rule {enable: true, delay, desired_states: {on}}` |
| read | `count_down.get_rules {}` (+ `system.get_sysinfo` in the same request) | `get_countdown_rules {}` (never `null` params: a P110 answers `-1008`), `get_device_info` |
| running | a rule with `enable: 1`; `remain` s; `act` 0 off, 1 on | a rule with `enable: true`; `remain` s; `desired_states.on` |

- **Order: switch, clear, add.** Switching first matters: on IOT an off cancels a running rule, and an on to a device
  already on leaves the rule (probe §3). A spent rule blocks the next add with `-10`, so the clear always runs.
- **Judge** as Shelly's `set_with_timer` does: read back, then CONFIRMED when the state matches and a running rule's
  delay and target match. Otherwise SENT with `timer_not_reported`. A device error raises, so it comes back REJECTED.
- **Per-target hold** (`Adapter.gather(..., hold=...)`) keeps a target's three calls together. Outlets already queue on
  their parent's protocol lock.
- **HA state:** after the send, `await coordinator.async_request_refresh()` on the entry's parent coordinator. Core
  polls every 5 s otherwise.
- **`get_attributes`** returns `timer` alone, via `core/timer.py` `timer_row(turns, remain, now)`. A target with no
  running rule has no `timer` key. Its scope holds the same classes and domains as the timer actions (`check_queries`).
- **Logging** per `docs/logging.md`: the per-call DEBUG line, and never an address or device id.

## Steps

Each step: implementer `sonnet` (the plan settles the calls, and the transcripts and unit tests catch a wrong
payload), then a fresh `plan-reviewer`, `opus`. Check each step with `.venv/bin/pytest -n auto --transcripts=check`.
Every step must not: mark the PR ready, merge, start the next step, or change another integration's package.

1. **Package, classes, addressing, fixture.** `integrations/tplink/__init__.py` (`INTEGRATION = IntegrationInfo(key=
   "tplink", title="TP-Link", ha_domain="tplink", maintainers=("jasonmx",), capability=…, classes=…)`), `classes.py`,
   `addressing.py`. `tests/fixtures/tplink.py` fakes the IOT and SMART device objects and their children behind a
   `MockConfigEntry` with `runtime_data.parent_coordinator`, modeled on `tests/fixtures/shelly.py`.
   `tests/integrations/tplink/wire.py` names the boundary (`protocol.query`). `test_classes.py` places each row of
   the class table. Add `"tplink"` to `CARD_ORDER`, plus the bundle's `devices.yaml` `column_order` stub.
2. **`turn_on_for` and `turn_off_for`** (risky: a harmful action, so also an `/audit-code` of its range). Adapters,
   `protocol.py`, tests pinning each payload for IOT plug, IOT outlet (with `child_ids`) and SMART, plus the judge's
   three outcomes. Then `scripts/gen_transcripts.py` for `calls/turn_on_for.json` and `turn_off_for.json`, and
   `scripts/gen_services.py`.
3. **`get_attributes`.** The `timer` row from each family's read, with tests for running, spent (`enable` 0) and
   absent rules, plus its transcript.
4. **Docs and shared regen** (implementer `opus`: user-facing text). Bundle `docs/integrations/tplink/`: `index.md`
   in Hue's shape, a `###` per class under `## Device classes`, no levels. Also a line that Tapo auto-off is core's
   entities, and the point that a manual off cancels a Kasa countdown (probe §3). `internals.md`: the calls table above,
   the probe's findings, the python-kasa namespace finding, and that SMART switch behavior is unsourced, all cited.
   `devices.yaml`: card phrases, sections, models (KP115 tested). Then `docs/word-budgets.yaml` lines,
   `scripts/gen_features.py` `NO_PATH` for the smooth rows on tplink with a comment each, and `docs/integrations.md`'s
   "what can't be done" section to match. `docs/deferred.md` gets entries for decision 9. Update README's duration rows
   for `turn_on_for` and `turn_off_for` (up to 24 h on TP-Link). Then run every generator: `gen_services`,
   `gen_codeowners`, `gen_compat`, `gen_features`, and `scripts/check_docs.py`.
5. **Upstream issue** (orchestrator, after step 4's `internals.md` lands). Search python-kasa's issues for
   `count_down` first, and comment on an existing issue rather than open a duplicate. Otherwise file one: the IOT
   `Countdown` module queries `countdown`, a KP115(UK) fw 1.0.20 answers `-1 "module not support"` there and serves
   `count_down`, and the module is registered on strips and bulbs, which weren't probed. Link the probe file at a
   commit-pinned URL. No household details. Then cite the issue in `internals.md`.
6. **Audit and ready**, per the global rules: `audit-gate` (the PR touches `labs(...)`, so an Opus auditor), then
   `owner-findings`, fix Critical and High, `gh pr ready`, and `merge-green <n> --squash --delete-branch`.

## Verification

- `.venv/bin/pytest -n auto --transcripts=check` green. Every generator's `--check` and `scripts/check_docs.py` pass.
- With the Labs option off, a fake SMART plug, outlet or light refuses `turn_on_for`, while the IOT plug runs it. With
  it on, all of them run. A fake IOT bulb refuses as not built.
- **Rig (Jason, at the release's run, deciding `iot_plug`'s Verified level):** add the KP115's switch entity to the
  ha-rig profile, then run the shared `turn_on_for`, `turn_off_for` and `get_attributes` steps on it.
  `check_release.py --records` flags the class until the record lands. If it fails, root-cause it and fix the code, or
  move the class to `labs(...)` before the RC.

## Implementing session

Model `sonnet`, reason: the plan settles the calls, classes and levels, and transcripts and unit tests catch a wrong
payload. Step 4's user-facing text goes to an `opus` implementer.
