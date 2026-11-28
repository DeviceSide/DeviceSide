# TP-Link call patterns for DeviceSide's actions: Kasa and Tapo (2026-11-28)

Research date: 2026-11-28. Scope: which calls, reached through Home Assistant's `tplink` integration and its
`python-kasa` device objects, would serve DeviceSide's actions on Kasa and Tapo plugs, strips, switches, dimmers and
bulbs, and what core already offers. Feeds the decision: whether a `tplink` integration clears CONTRIBUTING's
development principles, and which actions it carries. Section 9's KP115 probe is the only hardware run behind it.

Unreachable from this session: home-assistant.io, community.home-assistant.io, community.hubitat.com,
community.tp-link.com and tapo.com (DNS refused by the sandbox). Forum and vendor-FAQ items in the Signal section are
cited from search-result titles and snippets, not read in full, and say so. GitHub was reachable.

## Evidence tags

- **[code]**: library or integration source, pinned below.
- **[fixture]**: python-kasa's test fixtures, real device dumps per model, hardware and firmware
  (`tests/fixtures/{iot,smart}/<model>_<hw>_<fw>.json`).
- **[inferred]**: my reading, not observed.
- **[signal]**: another implementation, an upstream issue or a forum post. Never proof of a call.

Pinned primary sources:

- python-kasa: `python-kasa/python-kasa@0580eacc3e9433c69cbf733427ddb14140b46b41` (2026-11-28, version 0.13.0, the
  version core pins), written `PK/<path>#L<n>`.
- HA core: `home-assistant/core@68475ac0d1c833aa395b1b222ee50c9c04be554c` (2026-11-28), `tplink` files written
  `HA/<file>#L<n>`. `manifest.json` requires `python-kasa[speedups]==0.13.0`.

## 1. What core `tplink` already offers

Core turns a python-kasa `Feature` into an entity only when the platform has a description for its id
(HA/entity.py#L381-L410). The ones that matter here [code]:

| Feature | Entity | Source |
|---|---|---|
| `auto_off_enabled` | switch | HA/switch.py#L49 |
| `auto_off_minutes` | number, minutes | HA/number.py#L51-L53 |
| `auto_off_at` | sensor, when the running auto-off fires | HA/sensor.py#L102 |
| `smooth_transitions` (on_off_gradually v1) | switch | HA/switch.py#L52 |
| `smooth_transition_on`, `smooth_transition_off` (v2+) | number, seconds | HA/number.py#L43-L49 |
| `light.turn_on`/`turn_off` `transition` | ms to python-kasa | HA/light.py#L202-L203, #L276-L279 |

These arrived with core PR #120060, "Upgrade tplink with new platforms, features and device support", merged
2024-06-25 ([commit history of number.py](https://github.com/home-assistant/core/commits/dev/homeassistant/components/tplink/number.py),
read 2026-11-28); the PR has no milestone, so the release is [inferred] 2024.7.

Not exposed: any countdown (python-kasa has no feature for it, section 2), the IOT dimmer's fade and gentle times
(`dimmer_fade_on_time` and siblings, PK/kasa/iot/modules/dimmer.py#L63-L125, have no number description), and
`smooth_transition_change` (PK/kasa/smart/modules/lighttransition.py#L97-L109, no switch description). Core's only
services are `sequence_effect` and `random_effect` (HA/services.yaml#L1, #L78). Polling is every 5 s
(HA/__init__.py#L64).

## 2. Countdown (`turn_on_for`, `turn_off_for`)

### IOT (Kasa, legacy protocol)

python-kasa has a `Countdown` module that only reads rules, enables the service and deletes rules: no add or edit
(PK/kasa/iot/modules/countdown.py#L1-L7, PK/kasa/iot/modules/rulemodule.py#L65-L94) [code]. It is registered on strips,
strip sockets and bulbs (PK/kasa/iot/iotstrip.py#L121, #L352; PK/kasa/iot/iotbulb.py#L238), not on plugs, wall
switches or dimmers (PK/kasa/iot/iotplug.py#L58-L66; IotWallSwitch and IotDimmer subclass IotPlug). It addresses the
namespace `countdown`, while the device names its mode `count_down` (`"active_mode": "count_down"`,
PK/tests/fixtures/iot/KP105(UK)_1.0_1.0.5.json#L79) [fixture]. Unknown namespaces answer
`{"err_code": -1, "err_msg": "module not support"}` (PK/tests/fixtures/iot/HS220(US)_2.0_1.0.3.json#L13-L16), and
python-kasa then drops the module (PK/kasa/iot/iotmodule.py#L69-L76). So the module may never be live on hardware
[inferred]. No IOT fixture holds a countdown reply: `dump_devinfo` doesn't ask for one (PK/devtools/dump_devinfo.py#L394-L426).

The call, then, is not in a primary source. Its shape from the signal (section 7): `count_down.add_rule`
`{enable, delay, act, name}`, `delay` in seconds, `act` 0 off or 1 on; one rule at most, a second `add_rule` failing
with `-10 "table is full"`; `delete_all_rules` clears it; strip outlets addressed with `context.child_ids`. On a KP115
(section 9) `get_rules` reports time left (`remain`), the maximum delay is 86400 s, and a manual off cancels a running
rule.

DeviceSide can send it with python-kasa's own raw path: `IotDevice._query_helper(target, cmd, arg, child_ids)`, which
adds `{"context": {"child_ids": [...]}}` for an outlet (PK/kasa/iot/iotdevice.py#L232-L243, #L254-L269). That method
is private; the CLI's `kasa command --module <ns> <cmd> <params>` uses it (PK/kasa/cli/main.py#L421-L439) [code].

### SMART (Tapo, newer Kasa)

Devices list a `countdown` component; 62 fixture models have version 2, the P100 on firmware 1.1.3 version 1 [fixture]
(component scan over `PK/tests/fixtures/smart`, 2026-11-28). python-kasa has no countdown module
(`PK/kasa/smart/modules/` holds none); its fixture dumper reads `get_countdown_rules` only
(PK/devtools/helpers/smartrequests.py#L227-L231, #L383) [code]. The replies show the rule's shape [fixture]:

```
"get_countdown_rules": {"countdown_rule_max_count": 1, "enable": false,
  "rule_list": [{"delay": 300, "desired_states": {"on": true}, "enable": false, "id": "C1", "remain": 0}]}
```

(PK/tests/fixtures/smart/P110(UK)_1.0_1.3.0.json#L127-L139; an off rule of 120 s on an L630 bulb,
L630(EU)_1.0_1.1.2.json#L143-L155). So: one rule per device, seconds, a target state, and `remain` for the time left,
which `get_attributes`' `timer` needs. A spent rule stays in the list, disabled, with `remain: 0` [fixture]. Error codes
`-1901` to `-1903` name countdown failures, conflict and save (PK/kasa/exceptions.py#L134-L136) [code].

The write call is not in a primary source. The Rust/Python `tapo` library sends `add_countdown_rule`
`{enable: true, delay, desired_states: {on}}`, clears with `remove_countdown_rules {remove_all: true}` first because a
P110 "rejects a second `add_countdown_rule` while one is armed", and caps `delay` at 24 h, "the maximum the Tapo app
allows" (section 7) [signal]. SMART calls go through `SmartDevice._query_helper(method, params)`
(PK/kasa/smart/smartdevice.py#L708-L709); a strip or hub child's protocol wraps each call in `control_child` with its
`device_id` (PK/kasa/protocols/smartprotocol.py#L495-L511; PK/kasa/smart/smartchilddevice.py#L51) [code].

### A running countdown when the device is switched

IOT, on a KP115: a button off or `set_relay_state` off cancels a running rule, a later on doesn't restore it, and an
on to a plug already on leaves it running; a spent or cancelled rule stays in the list, disabled (section 9). SMART:
unsourced; no primary source says whether a plain on or off cancels, restarts or leaves a rule.

## 3. Auto-off (`set_auto_off`, `clear_auto_off`)

SMART only. The `auto_off` component (version 2 in 25 fixture models: P1xx plugs, P3xx strip children, TP10/TP15,
EP25, KP125M, KS205, HS200 v5.26, S500, S505, TS15) [fixture]:

- **Calls.** `get_auto_off_config` → `{enable, delay_min}`; `set_auto_off_config {enable, delay_min}`, minutes, both
  fields sent on every write (PK/kasa/smart/modules/autooff.py#L57-L82) [code].
- **Read-back.** `auto_off_status` (`"on"` while running) and `auto_off_remain_time` (seconds) in `get_device_info`;
  python-kasa derives `auto_off_at` (PK/kasa/smart/modules/autooff.py#L84-L97). A TS15 dump has it enabled at 20 min
  (PK/tests/fixtures/smart/TS15(US)_1.0_1.2.2.json#L112-L115, #L130-L131) [fixture]. Every other dump shows the
  default, 120 min, disabled.
- **Strip parents** carry the component for their children but not the status, so the module skips them
  (PK/kasa/smart/modules/autooff.py#L99-L105).

IOT: no auto-off call in python-kasa [code]; the Kasa app's auto-off on legacy devices is not a device setting in any
source read. `set_auto_off` on IOT is no known method.

**Core covers SMART auto-off fully**: enable, delay and the running timer's end are entities (section 1), on every
device whose python-kasa module loads. Per CONTRIBUTING's Feature gaps, DeviceSide leaves it to core. The one thing
core lacks, a unit finer than minutes, the device doesn't have either.

## 4. Dimmers and bulbs

### No stop

No call in python-kasa stops a level change, starts one, or steps relatively; no fixture component names one [code]
[fixture] (rg for stop, step, relative and move over `PK/kasa/iot`, `PK/kasa/smart/modules/{brightness,light,color,
colortemperature,lighttransition}.py`; component scan of every SMART fixture, 2026-11-28). Both Hubitat drivers
emulate a level change with hub-side 4 % steps once a second, and "stop" only cancels their own loop (section 7)
[signal]. **Smooth moves (`raise_*`, `lower_*`, `stop`) have no known method on TP-Link.** A read of the moving level
might allow a stop by writing it back; that reading is unsourced on IOT dimmers (a Hubitat comment hints it,
section 7) and absent on SMART, where python-kasa ignores transitions.

### Transitions

- **IOT dimmers** (HS220 v1/v2, KS220, KS230, ES20M, KP405): `smartlife.iot.dimmer.set_dimmer_transition
  {brightness, duration}`, ms; it turns the dimmer on (PK/kasa/iot/iotdimmer.py#L106-L136, #L161-L186) [code]. No
  maximum is stated. Device presets: `fadeOnTime`/`fadeOffTime` 0-10 s and `gentleOnTime`/`gentleOffTime` 0-120 s,
  bounds python-kasa calls "arbitrary", `rampRate` 10-50 "verified against KS220" for the buttons
  (PK/kasa/iot/modules/dimmer.py#L28-L40, #L256-L270; values in PK/tests/fixtures/iot/HS220(US)_2.0_1.0.3.json#L3-L11).
- **IOT bulbs** (KL, LB): `transition_period` in ms on `smartlife.iot.smartbulb.lightingservice.transition_light_state` (PK/kasa/iot/iotbulb.py#L212-L213, #L339-L367).
- **SMART** (Tapo bulbs, SMART dimmers): no per-command duration. Every setter documents "transition is not supported
  and will be ignored" (PK/kasa/smart/modules/light.py#L100-L115; brightness.py#L52-L76; color.py#L60-L68). The fade
  is the `on_off_gradually` preset: v1 one switch, v2 separate on and off durations, v3 `max_duration` (60 s in every
  dump), v4 (L530EA) `change_state`, a fade between states while on (PK/kasa/smart/modules/lighttransition.py#L24-L28,
  #L111-L160; PK/tests/fixtures/smart/HS220(US)_3.26_1.0.1.json#L222-L233) [code][fixture].

The fade presets act on turning on and off, not on a level change (bar v4's switch), so they don't serve a move with
`limit`. An IOT dimmer or bulb transition could carry one (a set to `limit` over the computed time), but without a stop
the move set isn't complete; `limit` alone isn't worth building [inferred].

## 5. Set while off (`set_attributes`)

- **IOT dimmers: brightness, yes.** `smartlife.iot.dimmer.set_brightness` changes the level without turning on; only
  `set_dimmer_transition` turns on. Core's own comment: "The device logic is to change the settings without turning it
  on except when transition is defined", which is why core always sends a 1 ms transition (HA/light.py#L208-L214)
  [code]. The core issue it cites, #57265 (2021-10-07, HS220 fw 1.5.11), reported exactly that (section 7) [signal].
  The level reads back from `sys_info.brightness` (PK/kasa/iot/iotdimmer.py#L93-L104).
- **IOT bulbs: unsourced.** python-kasa always sends `on_off`, 1 unless asked otherwise; `LightState(light_on=False,
  brightness=…)` sends `on_off: 0` with the values and `ignore_default: 1` (PK/kasa/iot/modules/light.py#L185-L202;
  PK/kasa/iot/iotbulb.py#L351-L361). Whether the bulb stores them in `dft_on_state` (where an off bulb reports its
  values, PK/kasa/iot/iotbulb.py#L292-L297) or turns on is not shown.
- **SMART bulbs and dimmers: unsourced.** `set_device_info` with `device_on: false` and the values is what
  `set_state` sends (PK/kasa/smart/modules/light.py#L117-L130); no source says what the device does. Core relies on
  `set_device_info {brightness}` alone turning a SMART light on (HA/light.py#L248-L256) [inferred].

## 6. Transport and classes

- **Calls** go through the config entry's device object, `entry.runtime_data.parent_coordinator.device`
  (HA/coordinator.py#L25-L30; HA/__init__.py#L245-L256), and its children, not through a service [code].
- **Local only.** python-kasa speaks only to the device's LAN address. Firmware using TPAP encryption isn't supported
  (PK/SUPPORTED.md#L12-L14: EP25 2.6 fw 1.4.1, KP125M fw 1.4.1, P110 EU fw 1.4.0, P110M FR fw 1.4.1, S505D fw 1.4.0),
  so such a device never loads in core and needs no DeviceSide refusal. No cloud-only family reaches core [code].
- **Concurrency.** python-kasa serializes each device's queries behind one lock (PK/kasa/protocols/iotprotocol.py#L76,
  #L85; smartprotocol.py#L118, #L138) and batches SMART requests five at a time (smartprotocol.py#L106). Core notes
  "the iot HS300 allows a limited number of concurrent requests" and polls its outlets' energy at 60 s
  (HA/coordinator.py#L121-L141) [code]. Since outlets share the parent's protocol (PK/kasa/iot/iotstrip.py#L338-L341),
  DeviceSide's sends to several outlets queue on one lock; no rate limit is documented.
- **Addressing.** IOT outlets: `context.child_ids` on the parent's connection. SMART strip and hub children:
  `control_child` with the child's `device_id` (section 2).

First cut by family:

| Class | Models (PK/README.md#L190-L211) | Countdown | Auto-off | Set while off |
|---|---|---|---|---|
| IOT plug and wall switch | HS100, HS103, HS105, HS110, KP100, KP105, KP115, KP401, EP10; HS200 to v5.0, HS210, KS200 | `count_down`, probed on a KP115 (section 9) | none | n/a |
| IOT strip outlet | HS300, KP303, KP400, HS107, KP200, EP40 | `count_down` with `child_ids`, from signal | none | n/a |
| IOT dimmer | HS220 v1/v2, KS220, KS230, ES20M, KP405 | `count_down` assumed, unsourced | none | brightness (core) |
| IOT bulb and light strip | KL, LB | namespace unsourced | none | unsourced |
| SMART plug and switch | P100-P135, TP10, TP15, EP25 v2.6, KP125M, KS205, HS200 v5.26, S500, S505, TS15 | `countdown` v2 (fixture), write from signal | core | n/a |
| SMART strip child | P210M, P300, P304M, P306, P316M, TP25, EP40M | per child, via `control_child` | core | n/a |
| SMART hub child switch | S210, S220 (`countdown` v2, PK/tests/fixtures/smart/child/S210(EU)_1.0_1.9.0.json) | via the hub's `control_child` | none in dumps | n/a |
| SMART dimmer and bulb | HS220 v3.26, KS225, KS240, S500D, S505D, S515D; L5xx, L6xx, L9xx | `countdown` v2 (fixture) | none in dumps | unsourced |

## 7. Signal

Other implementations, issues and forums: demand, failure modes, and how others send the calls. None of it proves a
call.

- **python-kasa discussion #284** (2022-01-10, answer by the library's maintainer on a KP115): one countdown rule only,
  "not removed automatically"; add a disabled rule with `count_down add_rule {"enable": 0, "delay": 5, "act": 0,
  "name": "test"}`, start it with `edit_rule` setting `enable: 1`; the rule disables itself after firing. A 2023-11-05
  reply on an HS110(UK) got `-10 "table is full"` from `add_rule`
  ([discussion](https://github.com/python-kasa/python-kasa/discussions/284), read 2026-11-28). The later replies,
  2025-08 to 2026-06, ask how to do it from python-kasa: demand for a library call.
- **tplink-smarthome-api** (the library behind Homebridge's TP-Link plugin) sends `count_down` `get_rules`,
  `add_rule {enable, delay, act, name}` after `delete_all_rules`, `edit_rule`, with the outlet's child id
  ([timer.ts#L32-L139](https://github.com/plasticrake/tplink-smarthome-api/blob/33f55531e6d5935d57a065fb95fa5dc340c4f392/src/plug/timer.ts#L32-L139);
  plugs only, [index.ts#L267](https://github.com/plasticrake/tplink-smarthome-api/blob/33f55531e6d5935d57a065fb95fa5dc340c4f392/src/plug/index.ts#L267)).
  Its simulator models the same API and the `-10` error, with no `remain` field
  ([hs.js#L197-L218](https://github.com/plasticrake/tplink-smarthome-simulator/blob/c8a3155ffde27effe74d57b46e510c6334a01e25/src/devices/hs.js#L197-L218)).
  The Homebridge plugin itself uses no timer
  ([homebridge-tplink-smarthome@e716f80](https://github.com/plasticrake/homebridge-tplink-smarthome/tree/e716f80cf6fd5db4ea7f56c14ee4a4b1c56779d1/src), rg for timer, countdown, auto-off).
- **tapo** (Rust and Python, v0.10.0, 2026-09-28) added `set_timer`, `get_timer` and `clear_timer` for P1xx plugs:
  `add_countdown_rule {enable, delay, desired_states: {on}}`, `get_countdown_rules {}` (a P110 rejects `params: null`
  with `-1008`), `remove_countdown_rules {remove_all: true}` before every add, delay 1 s to 24 h, and `remain` read as
  the time left
  ([api_client.rs#L2163-L2223](https://github.com/mihai-dinculescu/tapo/blob/4d9f7df2788491be444ca0066cf87d89b29f6e95/tapo/src/api/api_client.rs#L2163-L2223);
  [tapo_request.rs#L107-L110, #L137-L140](https://github.com/mihai-dinculescu/tapo/blob/4d9f7df2788491be444ca0066cf87d89b29f6e95/tapo/src/requests/tapo_request.rs#L107-L140);
  [timer_result.rs#L6-L43](https://github.com/mihai-dinculescu/tapo/blob/4d9f7df2788491be444ca0066cf87d89b29f6e95/tapo/src/responses/timer_result.rs#L6-L43)).
  The second implementation of the SMART call, and the only one.
- **Hubitat, DaveGut's Kasa integration** (the built-in Hubitat app's source): no countdown or auto-off. Level change is
  a hub loop of +4 % a second; `stopLevelChange` unschedules it and refreshes
  ([DimmingSwitch.groovy#L242-L297](https://github.com/DaveGut/Kasa-Hubitat/blob/23c1088b7440a5f546db90ba87a351d609a28531/DeviceDrivers/DimmingSwitch.groovy#L242-L297)).
  `setLevel` always sends `on_off: 1` (IOT) or `device_on: true` (SMART) with a transition, and caps its transition
  preference at 10 s (#L194-L240); after a dimmer transition it waits, as "Dimming switch return actual level"
  (#L368-L374), a hint that an IOT dimmer reports its level mid-fade.
- **Hubitat, DaveGut's Tapo integration**: the same 4 % loop, `stopLevelChange` only unschedules
  ([tpLink_dimmer.groovy#L267-L298](https://github.com/DaveGut/tpLink_Hubitat/blob/19544bbb0c23fde89546ef02fc56e55410a704b6/Drivers/tpLink_dimmer.groovy#L267-L298));
  no countdown or auto-off.
- **openHAB** `tplinksmarthome` and `tapocontrol` bindings: no countdown or auto-off; `tapocontrol` knows only the
  countdown error codes
  ([TapoErrorCode.java#L59-L61](https://github.com/openhab/openhab-addons/blob/38702ed017dd8d37236d339c73cea70190105807/bundles/org.openhab.binding.tapocontrol/src/main/java/org/openhab/binding/tapocontrol/internal/constants/TapoErrorCode.java#L59-L61)).
- **HA core #57265** (2021-10-07, closed 2021-10-08 by PR #57285): `light.turn_on` with brightness on an HS220 "will set
  the turn-on brightness level but will not actually turn on the light"
  ([issue](https://github.com/home-assistant/core/issues/57265), read 2026-11-28).
- **Forums (titles and snippets only, pages unreachable).** Long-running requests for a timed off on Kasa, e.g.
  "Kasa/HS200 Feature Request - Turn off X Minutes after Turned On" (2017-2018,
  [thread](https://community.tp-link.com/us/home/forum/topic/94278)); "Auto-Off Timer with HS105 seems to only works
  when turned on via the app" ([thread](https://community.tp-link.com/en/smart-home/forum/topic/546862), undated);
  "Auto-off does not work when trigger by action" (2026-02,
  [thread](https://community.tp-link.com/us/home/forum/topic/857962)); "P300 turns off after 2 hours", the 120 min
  default left enabled ([thread](https://community.tp-link.com/en/home/forum/topic/853952)). TP-Link's FAQ says Tapo
  ranks "Timer > Schedule > Away mode"
  ([FAQ](https://tapo.com/uk/faqs/common-questions-about-schedule-timer-away-mode-of-smart-home-devices/)). No HA blueprint
  or community thread on TP-Link "on for N minutes" or hold-to-dim was found by search; the HA forum couldn't be read.

## 8. Summary for scope

| Action | IOT | SMART | Notes |
|---|---|---|---|
| `turn_on_for`, `turn_off_for` | `count_down` rule, call from signal | `add_countdown_rule`, call from signal; read shape in fixtures | not in core; one rule per device or outlet; IOT: a manual off cancels the rule (section 9) |
| `get_attributes` `timer` | `remain` in `get_rules` (section 9) | `remain` in `get_countdown_rules` | |
| `set_auto_off`, `clear_auto_off` | no known method | `set_auto_off_config`, minutes | core has it: leave to core |
| `set_auto_on`, `clear_auto_on` | none | none | no known method |
| `raise_*`, `lower_*`, `stop` | no stop | no stop, no per-command transition | no known method |
| `set_attributes` brightness | dimmers: `set_brightness` (core comment) | unsourced | |
| `set_attributes` color, color temperature | unsourced | unsourced | |

## 9. Probes

Run on a KP115 (IOT plug) on 2026-11-28 with python-kasa's CLI
(`kasa --host <address> command --module <namespace> <cmd> '<params>'`, PK/kasa/cli/main.py#L421-L439) and the device's
`sys_info`; the KP105 planned alongside it died before the run. Commands, raw replies and timings:
[2026-11-28-tplink-kp115-probe.md](2026-11-28-tplink-kp115-probe.md). Each names the decision it took (Evidence tenets
2 and 8).

1. **Namespace and read shape.** `count_down get_rules` answers; `countdown get_rules` is `-1 "module not support"`,
   so python-kasa's `Countdown` module queries a namespace this plug doesn't serve (a finding for its maintainers). A
   rule reads `{id, name, enable, delay, act, remain}`, `remain` in whole seconds. Took: the namespace is
   `count_down`, and `get_attributes` `timer` reads `remain`, so IOT countdowns aren't refused.
2. **Add, replace, delete.** A second `add_rule` is `-10 "table is full"`; `delete_all_rules` then `add_rule` works.
   Took: the send sequence is delete-then-add.
3. **Manual switch during a countdown.** A button off, or `set_relay_state` off as HA sends it, cancels a running rule
   (`enable: 0`, `remain: 0`), and a later on doesn't restore it: the plug stayed on past the fire time. A
   `set_relay_state` on to a plug already on leaves the rule running. Took: no stale rule after a manual switch, so
   no Labs caveat on that ground; a plain off ends the timer.
4. **Firing and residue.** A rule fires on time and stays in the list, disabled with `remain: 0`, blocking the next
   `add_rule` with `-10`. `sys_info.active_mode` is `count_down` only while a rule runs. Took: delete before every
   add; a rule with `enable: 1` is a running timer.
5. **Long delay.** 86400 s is accepted, 86401 s and 604800 s are `-3 "invalid argument"`. Took: the IOT maximum is
   86400 s. The minimum wasn't probed.

None reaches strip outlets, wall switches, SMART devices, dimmers or bulbs: those stay at the level their sources give
until an owner probes.

## 10. Recommendation

**Build part.** A `tplink` integration whose first scope is `turn_on_for` and `turn_off_for`, with
`get_attributes` (`timer`), on plugs, wall switches and strip outlets:

- **IOT plug and wall switch, IOT strip outlet**: build, from the KP115 probe (section 9): `count_down`
  `delete_all_rules` then `add_rule {enable: 1, delay, act, name}`, `delay` up to 86400 s, `timer` from `remain`. A
  manual off cancels the rule, so no stale-rule caveat. Wall switches and strip outlets send the same call (an outlet
  adds `context.child_ids`) but weren't probed.
- **SMART plug and switch, SMART strip child, SMART hub child switch**: Labs, from the fixtures' rule shape and the
  `tapo` library's call, until a SMART owner's run.
- **Leave to core**: SMART auto-off (fully exposed since 2024.7).
- **No known method**: smooth moves and `stop` on every class (no stop or move call), auto-on, IOT auto-off.
- **Not in the first scope**: `set_attributes` brightness on IOT dimmers (core's own comment sources it, but it needs
  an HS220 or KS230 owner for its `get_attributes` and the classes' other calls), and countdowns on dimmers and bulbs
  (IOT bulb namespace unsourced).

The SMART classes stay in Labs until a SMART run shows what a manual switch does to their rule.

Smooth moves reopen when a TP-Link firmware or python-kasa adds a stop or move call, or an HS220 or KS230 owner shows a
mid-fade `sys_info.brightness` read and a `set_brightness` to it halt a `set_dimmer_transition` without a jump.
