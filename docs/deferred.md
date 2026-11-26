# Deferred work

Work decided against for now, and what reopens it. An issue is committed work with a clear done; a proposal nobody
has committed to is an entry here, added by PR. A user's device or feature request stays an issue. Device gaps stay
in code (`NotBuilt`, `NoKnownMethod`), never here.

Each entry says what it is, why not now, and the observable conditions that reopen it: any one suffices. An entry
with no such condition isn't added. Each RC lists the entries whose condition has been met (the `release` skill),
and deletes those nobody defends.

## Device facts across integrations

A firmware fact proven on one integration counts on every integration that sends the identical call, so a ban or
Documented level would be derived once from device facts in `docs/models.yaml` (keyed on model ID, manufacturer string,
firmware where it decides, and a named call signature such as `zcl.on_off.timed_off.tenths`), never across signatures.
`IKEA_TIMER_HARMED`, an entry in both `refusals.py` files, would become one derived ban. Until then a PR argues
Documented by hand under tenet 5 (`docs/evidence.md`).

**Why not now:** two integrations share Zigbee calls, with one ban held on both, and signatures can't be frame-pinned on
Zigbee2MQTT, where the converter builds the frame.

**Revisit when:**
- a third integration reads a `zigbee/` catalog module (`tests/core/test_deferred.py` fails);
- three PRs have argued Documented by hand (`docs/evidence.md`, tenet 5) on a call another integration holds evidence
  for;
- a ban or reason is fixed on one Zigbee integration and missed on the other.

## Attended units probe

A button (not a service), run attended with a warning about the connected load, would send one timed-off call
(`on_time=30`: 3 s in tenths, 30 s in seconds), time the off report, read `OnTime` twice a second apart, always end with
a plain Off, and produce a prefilled device report with no household identifiers. It asks the user only when the signals
disagree. A maintainer folds credible results into the evidence; a probe never changes a level locally. First check
whether Zigbee2MQTT can send a raw ZCL command without a converter (ZHA can, through
`zha.issue_zigbee_cluster_command`).

**Why not now:** on the datapoint path it depends on the Tuya datapoint countdown (#582 for single-endpoint devices) and
its cancel path.

**Revisit when:**
- a device report leaves it unclear whether a timed device reads its timer in tenths or seconds.

## Repair notice on a first Labs call

The first Labs call on a device would raise one dismissable Home Assistant repair issue, once per device and action,
saying the feature is on trial there and linking the device report form, so a Labs item shown only under a card's ⚪
Labs line still returns a signal. A small `core/` helper called by the dispatcher would raise it
(`issue_registry.async_create_issue`, `is_persistent=False`, `is_fixable=False`); no adapter changes. First proposed
as #515, after v0.1.0.

**Why not now:** no evidence yet that the report rate limits lifting Labs flags; the Labs option already asks for
reports.

**Revisit when:**
- at the second release after v0.1.0, a Labs class still has no device report;
- a Labs item that entered with no pass has no device report one release after it shipped.

## Field lifts checked against a record

The coverage check would ask a field lifted out of Labs (a `labs_fields(...)` entry removed, or a field lifted in
`fields`) for a passing test that sent it, as it asks a Verified class or domain for one. Until then a field lifts on
the maintainer's word (`docs/evidence.md`, The Labs flag).

**Why not now:** a record doesn't say which fields a test sent, and the rig that writes the records is another repo, so
no check can ask a field for its record.

**Revisit when:**
- a field is found lifted out of Labs with no record or row of a test that sent it;
- the record schema (`docs/test-records.schema.json`) gains the fields a test sent.

## Per-family test records and docs

A family's maintainers own its code, unit tests and new research, while the test records, `index.md`, `internals.md` and
`devices.yaml` stay whole and the integration's (CLAUDE.md, Maintainers). Splitting them by family touches the record
layout, `docs/test-records.schema.json`, `check_release.py --signoffs`, `gen_compat.py` and `FAMILY_PATHS`
(`scripts/gen_codeowners.py`).

**Why not now:** no family maintainer signs off their own classes yet.

**Revisit when:**
- a family maintainer signs off their own classes.

## Rig kit for maintained adapters

A kit of the rig, so an integration's maintainers can commit records for hardware the rig lacks.

**Why not now:** maintainers sign off by hand (`docs/evidence.md`).

**Revisit when:**
- a maintainer needs to commit records for hardware the rig lacks.

## Shared IKEA family rules and tests across Zigbee integrations

`integrations/zha/families/ikea/__init__.py` and `integrations/zigbee2mqtt/families/ikea/__init__.py` are about 50
near-identical lines, and their `test_classes.py` files are near-copies (the v0.1.0rc2 audit, §1 and §5; #532). Sharing
the rules would put them beside the catalog's strings (`custom_components/deviceside/zigbee/ikea.py`), with one test
parametrized over both stacks. The shared refusal reasons are already in the catalog (#583).

**Why not now:** one family is a near-copy, and sharing its rules lets one integration's family maintainer change the
other's classification.

**Revisit when:**
- a second family's rule file is a near-copy on both integrations.

## Per-endpoint addressing on Zigbee2MQTT

Address each endpoint of a multi-light device by its topic, with the endpoint names Zigbee2MQTT 2.6.0+ publishes, and
read its suffixed state keys back. Today every light or switch of a device with several in its domain is refused as
`not_addressable` ([internals](integrations/zigbee2mqtt/internals.md#addressing)). It would also serve the multi-gang
Tuya datapoint devices (a countdown per endpoint, `countdown_l1`; #582 serves the single-endpoint ones, the rest stay
`tuya_mcu`, refused as not built;
[payload rules](integrations/zigbee2mqtt/research/2026-11-14-tuya-datapoint-countdown.md)) and multi-gang inching, once
the gang 4 encoding and the whole-table write are settled
([internals](integrations/zigbee2mqtt/internals.md#set_auto_off-and-clear_auto_off)).

**Why not now:** the refusal is safe and predictable, and no user has reported such a device or asked for timed actions
on a multi-gang Tuya one.

**Revisit when:**
- a device report or request names a multi-light Zigbee2MQTT device refused as `not_addressable`;
- a device report or request asks for `turn_on_for` or `turn_off_for` on a multi-gang Tuya datapoint device;
- a device report or request asks for `set_auto_off` on a multi-gang inching device.

## Matter set_attributes and stop without the read-back

Matter's `set_attributes` reads back every attribute it set, 0.6 s after the last command, and its `stop` reads each
light twice ([set_attributes](integrations/matter/internals.md#set_attributes),
[stop](integrations/matter/internals.md#stop)). A class that leaves Labs on a pass could drop them, saving the waits and
the reads, and report `sent` as ZHA does.

**Why not now:** every Matter class is in Labs, admitted by research. A light answers SUCCESS to a `set_attributes`
command it didn't carry out (one the override fails to unblock does), and `stop`'s reads are what tell a halted light
from one still moving, so the reads are the only signal a device report has.

**Revisit when:**
- a Matter class's `set_attributes` or `stop` leaves Labs on a pass.

## The raw bottom for other lights on Zigbee2MQTT

A lower to 0.4 % sends level 1 as a raw `moveToLevel` to Hue and Aqara lights alone, and level 2 to standard lights
([internals](integrations/zigbee2mqtt/internals.md#fade)); DeviceSide can't read ZHC's `turnsOffAtBrightness1`
(definition metadata, not in Zigbee2MQTT's API), so the rule goes by class. An unflagged `other` light switches off at
it, as the converter sends level 1 as `moveToLevelWithOnOff`; a flagged one stops at 0.8 %. Sending raw to every light
would fix the first and lower the second. A flagged-model list would add 80 to 95 unflagged definitions, most off the
table because their brightness path departs (overridden converters, `omitOptionalLevelAndColorParams` lights), which
only the table's generator tells apart. A mixed group goes through the converter whole, so an off member lights at the
lower.

**Why not now:** `other` has no record of holding level 1 on a raw `moveToLevel`, and Innr's lights are reported to turn
off at level 1, which a raw call would not prevent.

**Revisit when:**
- a report of an unflagged `other` light switching off at a lower to 0.4 %: then `scripts/zhc_table.py` emits a bottom
  membership (a standard brightness converter and no flag touching it), not a list of `turnsOffAtBrightness1` models;
- a probe of a standard light holding level 1 lit on a raw `moveToLevel` (lowers its bottom to 1);
- a probe of an unflagged `other` light holding level 1 lit on a raw `moveToLevel`.

## Inching readback on Zigbee2MQTT

Read the persisted inching setting back, so `set_auto_off` and `clear_auto_off` could be `confirmed` and
`get_attributes` could report it. Z2M's state for the composite is the last write's echo
([internals](integrations/zigbee2mqtt/internals.md#set_auto_off-and-clear_auto_off)).

**Why not now:** no read path is evidenced: ZHC has no `convertGet`, and a Sonoff report is a candidate on newer
firmware only.

**Revisit when:**
- a Tuya device is shown to answer a read of 0xD003 with a record that decodes (a run or a report);
- a Sonoff device is shown to report its inching setting (a 0x17 report on firmware 1.1.0 or later).

## Inching on ZHA

`set_auto_off` and `clear_auto_off` on ZHA for Sonoff and Tuya inching. A ZHA call can't be sent: the Sonoff 0xFC11
quirk declares no `protocolData` command, and Tuya's `TuyaZBE000Cluster` has no attributes or commands.

**Why not now:** nothing to send through.

**Revisit when:**
- a zha-device-handlers quirk that declares the command is released (the Sonoff PRs #5135 and #5317 are open).

## Auto-on (inching mode ON) on Zigbee2MQTT

`set_auto_on` and `clear_auto_on` for Sonoff relays: inching mode ON turns the relay off when triggered, then back on
after the time. Mode is one setting shared with auto-off, so the two can't both be held.

**Why not now:** one slot serves both, and no request for auto-on on Sonoff has come in.

**Revisit when:**
- a request asks for auto-on on a Sonoff relay.

## More Tuya inching strings on Zigbee2MQTT

Admit further single-endpoint Tuya strings that Z2M enables inching for. Only two have a measured time; several others
are reported to have no effect ([research](integrations/zigbee2mqtt/research/tuya/2026-11-24-inching.md), §4).

**Why not now:** a string is admitted on evidence, and the rest have none or a negative.

**Revisit when:**
- a pass, or a report with a measured time, names another single-endpoint string.

## Sonoff S60 inching on Zigbee2MQTT

`set_auto_off` and `clear_auto_off` on the S60ZBTPF and S60ZBTPG, which are refused as not built.

**Why not now:** `DISABLE` is reported to have no effect, so `clear_auto_off` would leave the plug pulsing.

**Revisit when:**
- a report or run shows `DISABLE` stopping the pulse on an S60.

## A stop after a failed native-control set on Zigbee2MQTT

When `hue_native_control` can't be set for a soft off (MQTT or Zigbee2MQTT slow or down; `native_control` logs "Couldn't
set Zigbee2MQTT's hue_native_control to ..." and sends anyway), the soft off goes out as Philips' own command, which
`brightness_move: stop` doesn't end, so the light fades on to off after a stop
([internals](integrations/zigbee2mqtt/internals.md#stop)). The fix: after the stop, publish
`{"state": "ON", "brightness", "transition": 0}` at the predicted brightness, only for a soft off whose set failed
(after every stop it flickered the bulb).

**Why not now:** no field data (no telemetry), and 85 lab rig logs, 2026-11-08 to 13, on one Zigbee2MQTT 2.14.3, hold no
set-failed or restore-failed warning (172 sets visible, in the debug-logged runs only).

**Revisit when:**
- a report or log shows a light fading on to off after a stop, with that warning.

## Sengled lights on Zigbee2MQTT

Place Sengled's other features on Zigbee2MQTT with a run. Written while off, the E11-G13 jumps to full brightness on
ZHA, with `MoveToLevel` with or without `ExecuteIfOff` ([ZHA internals](integrations/zha/internals.md#tested-behavior)).
Zigbee2MQTT sends an off light a Level command in `set_attributes` (`MoveToLevel` with `ExecuteIfOff`, then its
kept-level publish without it), `raise_brightness` from off and `turn_on_for` with brightness (both
`moveToLevelWithOnOff`, untested on the Sengled); `lower_brightness`, the hue and saturation ramps and `stop` send none.
The `sengled` family holds no scope, so every feature is refused until a run.

**Why not now:** nothing probed on Zigbee2MQTT, and no request for a Sengled feature.

**Revisit when:**
- a device report or request names a Sengled bulb on Zigbee2MQTT.

## Tuya's recipe on ZHA

Turn on with timer for Tuya's countdown plugs and switches on ZHA (`tuya_countdown`), by unicast: `light.turn_on` when
there are fields, a plain `On`, then `OnWithTimedOff` with `on_time` and `off_wait_time` both the duration in whole
seconds, read back in seconds (OnTime reads 0 for about a second after the call). It is Zigbee2MQTT's converter frame
([tuya-countdown](integrations/zigbee2mqtt/research/2026-11-14-tuya-countdown.md), §1) and the lab probe's C5
([lab probe](integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md), §2). Until it returns, `turn_on_for` refuses
the Tuya classes as not built yet, harmed by today's call, and `get_attributes` reads none of them (`check_queries`);
after, it reads OnTime in whole seconds, ten times the spec's tenths.

**Why not now:** it was built, then taken out for v0.1.0's scope, not its units.

**Revisit when:**
- a device report or request asks for turn on with timer on a Tuya plug or switch on ZHA.

## Split this register into a file per entry

One file per entry, in place of this page, once one file costs more than it saves.

**Why not now:** nineteen entries.

**Revisit when:**
- it holds more than 30 entries;
- merge conflicts in it become routine.
