# Deferred work

Work decided against for now, and what reopens it. An issue is committed work with a clear done; a proposal nobody
has committed to is an entry here, added by PR. A user's device or feature request stays an issue. Device gaps stay
in code (`NotBuilt`, `NoKnownMethod`), never here.

Each entry says what it is, why not now, and the observable conditions that reopen it: any one suffices. An entry
with no such condition isn't added. Each RC lists the entries whose condition has been met (the `release` skill),
and deletes those nobody defends.

## Device facts across integrations

A firmware fact proven on one integration counts on every integration that sends the device the identical call: a
device Verified on Zigbee2MQTT becomes Documented on ZHA when ZHA sends it the same frames, and a harmful failure
banned on one integration is refused wherever that call reaches that device.

- **Call signatures:** named constants in core for each wire-level call shape, such as
  `zcl.on_off.timed_off.tenths` and `zcl.on_off.timed_off.tuya_seconds`. Each class names the signature it sends,
  and a frame-pinning test in each package keeps it honest.
- **Device facts:** in `docs/models.yaml`, keyed on model ID, manufacturer string (and firmware where it decides)
  and signature. Each records works (with unit), doesn't work or harms, and its source.
- **Lofting:** `gen_compat` and `check_release` derive Documented levels and `harms` entries from the facts:
  never above Documented, never across signatures (ZHA's spec tenths call and Zigbee2MQTT's Tuya seconds recipe are
  different calls).

`IKEA_TIMER_HARMED`, today an entry in both `integrations/zha/refusals.py` and `integrations/zigbee2mqtt/refusals.py`
built from the catalog's reason (`zigbee/ikea.py`), would become one derived ban. Until then, a PR
argues Documented by hand under tenet 5 (`docs/evidence.md`).

**Why not now:** two integrations share Zigbee calls, with one ban held on both. Signatures can't be frame-pinned on
Zigbee2MQTT, where the converter builds the frame.

**Revisit when:**
- a third integration reads a `zigbee/` catalog module (`tests/core/test_deferred.py` fails);
- three PRs have argued Documented by hand (`docs/evidence.md`, tenet 5) on a call another integration holds
  evidence for;
- a ban or reason is fixed on one Zigbee integration and missed on the other.

**Plan:** [`docs/plans/2026-11-14-device-facts-across-integrations.md`](plans/2026-11-14-device-facts-across-integrations.md)

## Attended units probe

A user with a Labs device can't tell whether it reads a timed-off call in tenths or seconds, ignores it, or
misbehaves. The probe, run attended from a button (not a service) with a warning about the connected load, sends
one timed-off call (`on_time=30`: 3 s in tenths, 30 s in seconds), times the off report and reads `OnTime` twice a
second apart. It asks the user only when the signals disagree or the device doesn't report, always ends with a plain
Off, probes from both on and off, and produces a prefilled device report (model ID, Zigbee manufacturer string,
firmware, integration, call, both measurements; no household identifiers). A maintainer folds credible results into
the evidence; a probe never changes a level locally. Its first step is to check whether Zigbee2MQTT can send a raw
ZCL command without a converter (ZHA can, through `zha.issue_zigbee_cluster_command`).

**Why not now:** on the datapoint path it depends on the Tuya datapoint countdown (#582 for single-endpoint devices)
and its cancel path.

**Revisit when:**
- a device report leaves it unclear whether a timed device reads its timer in tenths or seconds.

**Plan:** [`docs/plans/2026-11-14-units-probe.md`](plans/2026-11-14-units-probe.md)

## Repair notice on a first Labs call

The first time a Labs call runs on a device, one Home Assistant repair issue says the feature is on trial there and
asks the user to report whether it worked, linking the device report form. Raised once per device and action,
dismissable, never for Verified or Documented calls, so Labs items that show only as a folded line on a card still
return a signal. Shape: after a call runs at `Level.LABS`, the dispatcher calls a small `core/` helper that
raises the issue (`issue_registry.async_create_issue`, keyed on the action and device ID, `is_persistent=False`,
`is_fixable=False`, `learn_more_url` at the report form), its text in `strings.json`. No adapter changes.

**Why not now:** no evidence yet that the report rate limits lifting Labs flags; the Labs option already asks for
reports.

**Revisit when:**
- at the second release after v0.1.0, a Labs class still has no device report;
- a Labs item that entered with no pass has no device report one release after it shipped.

**Plan:** [`docs/plans/2026-11-18-experimental-listing.md`](plans/2026-11-18-experimental-listing.md), Decision 6

## Field lifts checked against a record

The coverage check would ask a field lifted out of Labs (a `labs_fields(...)` entry removed, or a field lifted in
`fields`) for a passing test that sent it, as it asks a Verified class or domain for one. Until then a field lifts on
the maintainer's word (`docs/evidence.md`, The Labs flag).

**Why not now:** a record doesn't say which fields a test sent, and the rig that writes the records is another repo,
so no check can ask a field for its record.

**Revisit when:**
- a field is found lifted out of Labs with no record or row of a test that sent it;
- the record schema (`docs/test-records.schema.json`) gains the fields a test sent.

**Plan:** [`docs/plans/2026-11-24-labs-until-tested.md`](plans/2026-11-24-labs-until-tested.md), Decision 8

## Per-family test records and docs

A family's maintainers own its code, unit tests and new research, while the test records, `index.md`,
`internals.md` and `devices.yaml` stay whole and the integration's (CLAUDE.md, Maintainers). Splitting them by
family touches the record layout and `docs/test-records.schema.json`, `check_release.py --signoffs` and
`gen_compat.py` reading them, and the paths in `FAMILY_PATHS` (`scripts/gen_codeowners.py`).

**Why not now:** no family maintainer signs off their own classes yet.

**Revisit when:**
- a family maintainer signs off their own classes.

**Plan:** none.

## Rig kit for maintained adapters

A kit of the rig, so an integration's maintainers can commit records for hardware the rig lacks.

**Why not now:** maintainers sign off by hand (`docs/evidence.md`).

**Revisit when:**
- a maintainer needs to commit records for hardware the rig lacks.

**Plan:** none.

## Shared IKEA family rules and tests across Zigbee integrations

`integrations/zha/families/ikea/__init__.py` and `integrations/zigbee2mqtt/families/ikea/__init__.py` are about 50
near-identical lines, and their `test_classes.py` files are near-copies (the v0.1.0rc2 audit, §1 and §5; #532).
Sharing the rules would put them beside the catalog's strings (`custom_components/deviceside/zigbee/ikea.py`), with
one test parametrized over both stacks. The shared refusal reasons are already in the catalog (#583).

**Why not now:** one family is a near-copy, and sharing its rules lets one integration's family maintainer change
the other's classification.

**Revisit when:**
- a second family's rule file is a near-copy on both integrations.

**Plan:** none.

## Per-endpoint addressing on Zigbee2MQTT

Address each endpoint of a multi-light device by its topic, with the endpoint names Zigbee2MQTT 2.6.0+ publishes, and
read its suffixed state keys back. Today every light or switch of a device with several in its domain is refused as
`not_addressable` ([internals](integrations/zigbee2mqtt/internals.md#addressing)).

The same addressing would serve the multi-gang Tuya datapoint devices (TS0601 and kin), and every definition whose
countdown is named per endpoint (`countdown_l1`), with the datapoint countdown: `turn_on_for` and `turn_off_for` by
suffixed `state` and `countdown` keys. It would serve inching on the multi-gang devices too (MINI-ZB2GS, NFZB-2, MW783Z, a 3-gang with a backlight): suffixed
fields in one `inching_control_set`, once the gang 4 encoding and the whole-table write are settled
([internals](integrations/zigbee2mqtt/internals.md#set_auto_off-and-clear_auto_off)). #582 serves the single-endpoint ones; the rest stay `tuya_mcu`, refused as
not built (`integrations/zigbee2mqtt/refusals.py`; the multi-gang payload rules are in
[the research](integrations/zigbee2mqtt/research/2026-11-14-tuya-datapoint-countdown.md)).

**Why not now:** the refusal is safe and predictable, and no user has reported such a device or asked for timed
actions on a multi-gang Tuya one.

**Revisit when:**
- a device report or request names a multi-light Zigbee2MQTT device refused as `not_addressable`;
- a device report or request asks for `turn_on_for` or `turn_off_for` on a multi-gang Tuya datapoint device;
- a device report or request asks for `set_auto_off` on a multi-gang inching device.

**Plan:** the multi-gang payloads: [`docs/plans/2026-11-15-tuya-datapoint-countdown.md`](plans/2026-11-15-tuya-datapoint-countdown.md),
Design 3.

## Matter set_attributes and stop without the read-back

Matter's `set_attributes` reads back every attribute it set, 0.6 s after the last command, to tell `confirmed` from
`sent` ([internals](integrations/matter/internals.md#set_attributes)), and its `stop` reads each light twice to tell
`confirmed` from `still_fading` ([internals](integrations/matter/internals.md#stop)). A class that
leaves Labs on a pass could drop them, saving the waits and the reads, and report `sent` as ZHA does.

**Why not now:** every Matter class is in Labs, admitted by research. A light answers SUCCESS to a `set_attributes`
command it didn't carry out (one the override fails to unblock does), and `stop`'s reads are what tell a light that
halted from one still moving, so the reads are the only signal a device report has.

**Revisit when:**
- a Matter class's `set_attributes` or `stop` leaves Labs on a pass.

**Plan:** [`docs/plans/2026-11-24-matter-light-actions.md`](plans/2026-11-24-matter-light-actions.md), Decision 8

## The raw bottom for other lights on Zigbee2MQTT

A lower to 0.4 % sends level 1 as a raw `moveToLevel` to Hue and Aqara lights alone, and level 2 to standard lights
([internals](integrations/zigbee2mqtt/internals.md#fade)). An unflagged `other` light switches off at it, as
Zigbee2MQTT's converter sends level 1 as `moveToLevelWithOnOff`; a flagged one stops at 0.8 %. Sending it raw to every
light would fix the first and lowers the second to 0.4 %.

Open with it: a mixed group (a member of `other`) goes through the converter whole, so an off member lights at the
lower (`moveToLevelWithOnOff`, which has On/Off), where a raw `moveToLevel` leaves it off.

**Why not now:** `other` has no record of holding level 1 on a raw `moveToLevel`, and Innr's lights are reported to
turn off at level 1, which a raw call would not prevent. Standard lights get it at level 2 on their membership (ZHC's
standard converters, with no meta or override touching the call), which an `other` light lacks.

**Revisit when:**
- a report of an unflagged `other` light switching off at a lower to 0.4 %: then `scripts/zhc_table.py` emits a
  bottom membership (a standard brightness converter and no flag touching it, whatever the other actions' departures),
  not a separate list of `turnsOffAtBrightness1` models, which would send the raw call to overridden and
  `omitOptionalLevelAndColorParams` lights;
- a probe of a standard light holding level 1 lit on a raw `moveToLevel` (lowers its bottom to 1);
- a probe of an unflagged `other` light holding level 1 lit on a raw `moveToLevel`.

**Plan:** [`docs/plans/2026-11-25-brightness-floor.md`](plans/2026-11-25-brightness-floor.md), Decisions 11 and 12

## Inching readback on Zigbee2MQTT

Read the persisted inching setting back, so `set_auto_off` and `clear_auto_off` could be `confirmed` and
`get_attributes` could report it. Z2M's state for the composite is the last write's echo
([internals](integrations/zigbee2mqtt/internals.md#set_auto_off-and-clear_auto_off)).

**Why not now:** no read path is evidenced: ZHC has no `convertGet`, and a Sonoff report is a candidate on newer
firmware only.

**Revisit when:**
- a Tuya device is shown to answer a read of 0xD003 with a record that decodes (a run or a report);
- a Sonoff device is shown to report its inching setting (a 0x17 report on firmware 1.1.0 or later).

**Plan:** none.

## Inching on ZHA

`set_auto_off` and `clear_auto_off` on ZHA for Sonoff and Tuya inching. A ZHA call can't be sent: the Sonoff 0xFC11
quirk declares no `protocolData` command, and Tuya's `TuyaZBE000Cluster` has no attributes or commands.

**Why not now:** nothing to send through.

**Revisit when:**
- a zha-device-handlers quirk that declares the command is released (the Sonoff PRs #5135 and #5317 are open).

**Plan:** none.

## Auto-on (inching mode ON) on Zigbee2MQTT

`set_auto_on` and `clear_auto_on` for Sonoff relays: inching mode ON turns the relay off when triggered, then back on
after the time. Mode is one setting shared with auto-off, so the two can't both be held.

**Why not now:** one slot serves both, and no request for auto-on on Sonoff has come in.

**Revisit when:**
- a request asks for auto-on on a Sonoff relay.

**Plan:** none.

## More Tuya inching strings on Zigbee2MQTT

Admit further single-endpoint Tuya strings that Z2M enables inching for. Only two have a measured time; several
others are reported to have no effect ([research](integrations/zigbee2mqtt/research/tuya/2026-11-24-inching.md), §4).

**Why not now:** a string is admitted on evidence, and the rest have none or a negative.

**Revisit when:**
- a pass, or a report with a measured time, names another single-endpoint string.

**Plan:** none.

## Sonoff S60 inching on Zigbee2MQTT

`set_auto_off` and `clear_auto_off` on the S60ZBTPF and S60ZBTPG, which are refused as not built.

**Why not now:** `DISABLE` is reported to have no effect, so `clear_auto_off` would leave the plug pulsing.

**Revisit when:**
- a report or run shows `DISABLE` stopping the pulse on an S60.

**Plan:** none.

## Native scenes beyond Hue

`set_scene` on a scene the device or its controller holds, written per light with `set_attributes` so no light turns
on, as Hue's bridge scenes are. Today it takes Hue bridge scenes and Home Assistant scenes
([plan](plans/2026-11-26-set-scene-ha-scenes.md)). It needs a scene entity whose contents can be read; checked against
HA core 2026.11.3 on 2026-11-26:

- **ZHA, Matter, Shelly, Control4:** HA exposes no scene entity. None of the four core integrations has a `scene.py`,
  and none forwards `Platform.SCENE` (`zha/__init__.py` `PLATFORMS`, `matter/discovery.py` `DISCOVERY_SCHEMAS`,
  `shelly/__init__.py` `PLATFORMS`, `control4/__init__.py` `PLATFORMS`). DeviceSide's Control4 adapter rides the
  core integration ([internals](integrations/control4/internals.md)).
- **Zigbee2MQTT:** scenes are HA `scene` entities on the `mqtt` platform, but command-only (`scene_recall`), and
  their contents are in Zigbee2MQTT's `database.db` alone, reaching MQTT only on a recall
  ([research](integrations/zigbee2mqtt/research/2026-11-26-scenes.md)).

**Why not now:** there is nothing to read the scene's settings from, so it can't be written without recalling it,
which turns the lights on.

**Revisit when:**
- one of these integrations exposes scene entities with readable contents (an HA scene platform holding each
  light's settings, or a Zigbee2MQTT topic or bridge response that carries a scene's state).

**Plan:** none.

## Split this register into a file per entry

One file per entry, in place of this page, once one file costs more than it saves.

**Why not now:** seventeen entries.

**Revisit when:**
- it holds more than 30 entries;
- merge conflicts in it become routine.

**Plan:** none.
