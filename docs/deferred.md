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
return a signal. Shape: after a call runs at `Level.EXPERIMENTAL`, the dispatcher calls a small `core/` helper that
raises the issue (`issue_registry.async_create_issue`, keyed on the action and device ID, `is_persistent=False`,
`is_fixable=False`, `learn_more_url` at the report form), its text in `strings.json`. No adapter changes.

**Why not now:** no evidence yet that the report rate limits lifting Labs flags; the Labs option already asks for
reports.

**Revisit when:**
- at the second release after v0.1.0, a Labs class still has no device report.

**Plan:** [`docs/plans/2026-11-18-experimental-listing.md`](plans/2026-11-18-experimental-listing.md), Decision 6

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
suffixed `state` and `countdown` keys. #582 serves the single-endpoint ones; the rest stay `tuya_mcu`, refused as
not built (`integrations/zigbee2mqtt/refusals.py`; the multi-gang payload rules are in
[the research](integrations/zigbee2mqtt/research/2026-11-14-tuya-datapoint-countdown.md)).

**Why not now:** the refusal is safe and predictable, and no user has reported such a device or asked for timed
actions on a multi-gang Tuya one.

**Revisit when:**
- a device report or request names a multi-light Zigbee2MQTT device refused as `not_addressable`;
- a device report or request asks for `turn_on_for` or `turn_off_for` on a multi-gang Tuya datapoint device.

**Plan:** the multi-gang payloads: [`docs/plans/2026-11-15-tuya-datapoint-countdown.md`](plans/2026-11-15-tuya-datapoint-countdown.md),
Design 3.

## Split this register into a file per entry

One file per entry, in place of this page, once one file costs more than it saves.

**Why not now:** eight entries.

**Revisit when:**
- it holds more than 30 entries;
- merge conflicts in it become routine.

**Plan:** none.
