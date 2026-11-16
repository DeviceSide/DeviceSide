# Timed-on units and behavior per device, at scale: sources and cleansing (2026-11-14)

Research date: 2026-11-14. Scope: how DeviceSide could gather, per device, the unit and behavior of a timed on
(On With Timed Off, 0x42, and Tuya's countdowns) at scale, keep that data clean as reports conflict and firmware
moves, and how each option fits the levels and the harm rule in [`docs/evidence.md`](../evidence.md). Feeds the
[device-classes plan](../plans/2026-11-14-device-classes.md) (Decisions 34 and 35, step 5 part 3) and later steps.
Builds on [the Tuya countdown research](../integrations/zigbee2mqtt/research/2026-11-14-tuya-countdown.md) and
[the timed-on call patterns](../integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), whose
findings it doesn't repeat.

Five angles were researched in parallel: mining upstream code, measuring in the field, crowd reports, reading the
device, and existing device databases. Tags: **[code]** pinned upstream source, **[repo]** a DeviceSide file,
**[report]** an upstream issue, **[doc]** upstream docs, **[inference]** this note's reasoning. Counts are approximate.
Device names quoted in upstream issues are left out.

**Hosts not reachable from the research session:** developer.tuya.com, csa-iot.org and on.dcl.csa-iot.org,
zigbee.blakadder.com, wikidata.org, openstreetmap.org, cve.org and the home-assistant.io doc sites. Tuya, CSA and
ZCL facts come from code and docs mirrored on GitHub; Wikidata, OpenStreetMap and ProtonDB are cited from general
knowledge and marked so. Nothing below was run on a device.

Pinned sources:

| Source | Commit | License |
|---|---|---|
| zigbee-herdsman-converters (ZHC), = npm `26.131.0` | `afdaa028a0972d801da762196ddfb2df631ea0cc` | MIT |
| Zigbee2MQTT | `3c841fdfd66c92239921ef84fde8f039c64e1662` | GPL-3.0 |
| zigbee2mqtt.io (docs) | `df1ef460` | GPL-3.0 |
| zigpy/zha-device-handlers | `b07fa76876e081d48744968f9fb806e7f1fee0ee` | Apache-2.0 |
| zigpy | `64b51ef` | GPL-3.0 |
| home-assistant/core (Tuya fixtures) | `fa470750e69e8922dc20628f186b56db10e4f95b` | Apache-2.0 |
| make-all/tuya-local | `cf1f04ab9c37a6aa74d94cbe15effa70e9b4a8ec` | MIT |
| project-chip/connectedhomeip | `c55ddad` | Apache-2.0 |
| zigbee-alliance/distributed-compliance-ledger | `7319bed3` | Apache-2.0 (code) |
| dresden-elektronik/deconz-rest-plugin | `c24e81cf` | BSD-3-Clause |
| openhab/org.openhab.binding.zigbee | `96f8801a` | EPL-2.0 |
| SmartThingsCommunity/SmartThingsEdgeDrivers | `30decd1b` | Apache-2.0 |
| JohanBendz/com.tuya.zigbee (Homey) | `61577d8e` | MIT |
| kkossev/Hubitat | `77f95e82` | Apache-2.0 (per file) |
| blakadder/zigbee | `d96e8aaf` | unclear: both an MIT `LICENSE` and an EPL-2.0 `LICENSE.md` |

`ZHC/<path>#L<n>` below is `https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/<path>#L<n>`.

## 1. Mining upstream code

**ZHC is the one source that encodes, per device and per manufacturer string, which timer call is sent and in what
unit.** Run, not parsed: a regex over the TypeScript misses copied converters (`{...tz.on_off, key: [...]}`; 584 Hue
definitions carry unnamed copies of the light converter). Installing the npm package with scripts disabled, preparing
all 4,667 definitions and identifying each converter by its `convertSet` function takes about a second and catches
the copies [code, prototype in the research session; not committed].

| Route | Definitions | Fingerprints | Unit on the wire |
|---|---|---|---|
| A: Tuya countdown over 0x42 | 49 | 203, plus the catch-alls `TS011F`, `TS0001`, `TS0002` | whole seconds in both fields |
| B: Tuya datapoint countdown | 79 | 213 (209 `TS0601`; one `TS011F`, ZOT60) | raw; the expose label says the unit |
| C: eWeLink countdown | 1 | model ID only | tenths |
| standard `tz.on_off` | 811 | 293 | tenths |
| light converter | 1,567 | 223 | tenths |
| local per-model converters | 69 | 21 | varies (Sonoff SWV: seconds) |

- 25 definitions reach more than one route, so a generated table records which converter wins by `toZigbee` order.
- **Route B's unit comes from the expose label, not the converter.** `valueConverter.countdown` is `raw()`
  ([`ZHC/src/lib/tuya.ts#L1637`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L1637)),
  and the shared `tuyaExposes.countdown()` hardcodes seconds, 0..43200, "Toggle…"
  ([`#L708-L715`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L708-L715)).
  Per datapoint: about 140 seconds 0..43200 (mostly the template), 27 seconds 0..86400, about 10 minutes, 7 custom,
  and one labeled hours whose wire value is seconds (`_TZE284_z5jz7wpo`). A template row is a copied default, not a
  measurement [inference].
- **Route A's maker-name predicate can be evaluated per string:** of the strings it names, 93 show a countdown and 20
  don't, but the converter is installed for all of them, so `on_time` has no converter on any of them
  ([Tuya research §1](../integrations/zigbee2mqtt/research/2026-11-14-tuya-countdown.md#1-three-converters-behind-one-name)).
- **Matching is more than (model, maker):** ZHC's `findByDevice` weighs priority, `applicationVersion`,
  `softwareBuildID`, endpoints and a `zigbeeModel` fallback
  ([`ZHC/src/index.ts#L525-L649`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/index.ts#L525-L649));
  9 route-A fingerprints already carry firmware fields.

**Reliability: ZHC states routing, not behavior.** The route is a fact of that ZHC version; the unit and semantics
are one contributor's claim [inference]:

- Only `test/toZigbee.test.ts` and `test/librasoft.test.ts` mention `onWithTimedOff` or a countdown; the Tuya
  countdown converter has no test [code].
- About 10 of 71 timer-related commits correct a unit, datapoint or enablement: `a204ef11` (SWV `on_time` ×10),
  `1c0ee2a6` and `8fb5436e` (one thermostat's units fixed twice), `96e764e3` then `e2633aae` five days later
  (inching added, then removed, for one string), `099ea3a3` then `d029330a` (`on_time` removed from, then re-added
  to, the light converter) [code].
- Upstream issues report route-A strings that don't honor the countdown (Z2M #30493, ZHC #9786), which is why
  Decision 35 holds a string Verified only by its own evidence.
- Identity blurs: any unlisted `TS011F` string falls to the catch-all `TS011F_plug_1` (route A), so a catch-all row
  covers strings nobody saw; 40 of 200 white labels on route A/B definitions have no fingerprint; a fingerprinted
  white label changes `definition.model` (`_TZ3000_okaz9tjs` now resolves to another maker's model), so a key uses
  the Zigbee model ID and manufacturer string, not the definition's model.

**ZHA quirks** carry no switch countdown mapping; the only countdown-like entries are valves, in minutes
([`tuya_valve.py#L387`](https://github.com/zigpy/zha-device-handlers/blob/b07fa76876e081d48744968f9fb806e7f1fee0ee/zhaquirks/tuya/tuya_valve.py#L387)).
For TS0601 devices, `TuyaOnOff.command` answers 0x42 on the host with UNSUP_CLUSTER_COMMAND
([`mcu/__init__.py#L398-L446`](https://github.com/zigpy/zha-device-handlers/blob/b07fa76876e081d48744968f9fb806e7f1fee0ee/zhaquirks/tuya/mcu/__init__.py#L398-L446)):
that status is the quirk's, not the device's. On ZHA the mineable fact is routing alone. **zigpy** holds the cluster
schema only.

**Tuya's declared schema, by proxy.** HA core's Tuya cloud fixtures (334 files, 128 with a countdown) give
`cz`/`kg`/`pc` `countdown_N` mostly in seconds 0..86400, some 0..43200, valves in minutes, with inconsistent unit
strings ("s", "秒", empty) [code]. ZHC caps the 0x42 countdown at 43200 s "per Tuya documentation"
([`ZHC/src/lib/tuya.ts#L3365`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L3365)),
so the two ranges disagree. Joining a Tuya manufacturer string's 8-character suffix to a cloud `product_id` is a
community convention [inference]: 26 HA fixtures and 37 tuya-local configs join to ZHC fingerprints. The two joined
route-B devices agree with ZHC; one tuya-local `TS011F` product gives a seconds timer where ZHC routes plain
`tz.on_off`. tuya-local is Wi-Fi, so a shared product ID needn't mean the same Zigbee firmware [inference].

**Freshness.** ZHC released about every two days in 2026 (171 releases; 618 commits touched `devices/tuya.ts`)
[code]. A pin plus a scheduled job that installs `@latest`, regenerates the table and opens a PR with the changed
routes, strings and units keeps up without promoting anything automatically [inference].

**On Z2M a static table may not be needed at runtime** [inference]: `bridge/devices` already carries each device's
`model_id`, `manufacturer`, `definition.model` and countdown exposes from the ZHC version the user actually runs,
which may differ from any pin. The class rules already read it (Decision 18). A mined table serves review, docs, the
seed list and strings not yet seen.

## 2. Reading the device

What the device can say without a timed run is little, and mostly negative.

| Signal | Needs a command? | Tells | Reliability |
|---|---|---|---|
| UNSUPPORTED_ATTRIBUTE (0x86) on OnTime 0x4001 | no | no ZCL timer | high when absent (the Sengled [repo]); presence proves nothing |
| Zigbee command discovery | no | advertises 0x42 | Tuya often doesn't answer [inference] |
| Basic and OTA versions | no | firmware identity | weak on Tuya (below) |
| Z2M `definition` and exposes in `bridge/devices` | no | Z2M's routing | already in use |
| Default Response 0x81 / 0x85 | yes | doesn't take 0x42 | reliable only when it comes |
| OnTime count-down rate | yes, a running timer | tenths vs seconds | high on the devices measured |
| Tuya `dataQuery` (0xEF00) | yes, reports only | which datapoints exist | no unit, range or meaning |
| Tuya cloud schema | no, but a cloud account | units and ranges | unavailable for devices paired to Z2M or ZHA |
| Matter FeatureMap (LT), AcceptedCommandList | no | 0x42 accepted, tenths by spec | high, backed by certification |
| CSA DCL lookup | no, but internet | certified at a version | no feature data |

- **The count-down rate is the one strong unit signal.** By spec OnTime and OffWaitTime drop by 1 every 0.1 s
  (zigpy `general.py` L902-903; the Matter reference server ticks every 100 ms, `OnOffLightingCluster.cpp`
  L290-352). Measured: a Hue LTA004 read 290, 250, 200 at 1, 5 and 10 s into a 30 s timer
  ([ZHA internals](../integrations/zha/internals.md)); the lab TS011F on ZHA dropped 1 a second in both fields, even
  while off ([lab probe §2](../integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md)). It needs a timer
  already running, and on Tuya starting one can harm: the ZHA lab plug switched itself on after a 0x42 from off. So
  it is a check after the call, not a probe before it.
- **A single read can't tell the units apart:** devices store the raw value they are sent (Z2M lab C1 read back 100,
  C2 read back 10), and the Z2M lab plug stored the value and never counted it down ([lab probe
  §2](../integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md)).
- **Statuses:** Shelly's `statusCode 133` ([Z2M #27265](https://github.com/Koenkk/zigbee2mqtt/issues/27265)) is
  0x85 INVALID_FIELD, not UNSUP_COMMAND (zigpy `foundation.py` L31-38). Silence or SUCCESS means nothing: Tuya plugs
  answer SUCCESS and run their own logic.
- **Firmware identity is uneven** [code]: Z2M's `bridge/devices` carries `software_build_id` and `date_code` but not
  `appVersion` (`lib/extension/bridge.ts` L877-884), and when a Tuya device sends no build ID, ZHC makes one up from
  `appVersion` (`tuyaFirmwareId`, `ZHC/src/lib/tuya.ts#L4511-L4532`; 64 → 1.0.0), or for TS0601 asks the MCU.
  ZHA's `sw_version` is the OTA `CurrentFileVersion`. The two integrations publish different fields, so a firmware
  rule would need one both can read, such as `appVersion` [inference]. A TS0601's behavior lives in its MCU, which
  the Zigbee module's `appVersion` doesn't identify.
- **Tuya has no schema command on the Zigbee wire**: cluster 0xEF00 offers dataRequest, dataQuery, sendData,
  mcuVersionRequest, OTA, time sync, gateway status and weather (zigbee-herdsman `cluster.ts`). Tuya's "query
  product info" runs on the serial link between MCU and radio [inference; docs not fetched]. The cloud
  specifications endpoint (`/v1.1/m/life/{device_id}/specifications`, tuya-device-sharing-sdk) needs a Tuya account
  and cloud device ID that a directly paired device doesn't have.
- **Matter has no unit ambiguity on paper.** OnTime, OffWaitTime and OnWithTimedOff are mandatory exactly under the
  Lighting feature (FeatureMap bit 0; `data_model/1.4/clusters/OnOff.xml`), and certification test TC-OO-2.3 sends
  OnTime 300 and requires everything at 0 after 40 s (`Test_TC_OO_2_3.yaml` L698-776), which a seconds device fails.
  Limits [inference]: it covers only the certified software version and doesn't catch a timer that runs fast, and a
  Matter bridge exposing Zigbee children behaves as its translation does. The DCL's ComplianceInfo holds vid, pid,
  software version, certification type, date and an optional `supportedClusters`, but no FeatureMap or PICS
  (`compliance_info.proto` L9-39), and no Zigbee strings to join on.

## 3. Measuring in the field

An opt-in, attended probe a user starts from the options flow [inference throughout, from the repo's lab data]:

- **Probe A, rate** (where OnTime exists): from on, send DeviceSide's shipped call for 10 to 30 s, read OnTime twice
  about 2 s apart (about 10/s is tenths, 1/s seconds, 0 stored but not run, unsupported no timer), then send Off and
  verify. About 5 s of device time. Open: Z2M showed the genOnOff read result only as a log line in the lab; whether
  code can read it is unchecked.
- **Probe B, timing** (fallback): request 3 s, once from off and once from on, and watch about 40 s (10× plus
  margin). From off catches a toggle or delayed on ([Z2M #22182](https://github.com/Koenkk/zigbee2mqtt/issues/22182),
  ZHA lab C1) or a device that only takes the call when on
  ([Z2M #28914](https://github.com/Koenkk/zigbee2mqtt/issues/28914)); from on catches never-off (Z2M lab C6, the
  IKEA unicast case [Z2M #29158](https://github.com/Koenkk/zigbee2mqtt/issues/29158)). With a 3 s request, tenths
  reads 0 to 6 s and seconds 27 to 33 s, so one clean sample per start state classifies; behavior, not noise, is the
  risk. Timing must come from the probe's own reads about once a second: HA's timestamps show when HA heard, and Z2M
  publishes no state for a timed command ([`turn_on_for.py`](../../custom_components/deviceside/integrations/zigbee2mqtt/turn_on_for.py)).
- **It sends DeviceSide's own call, never a raw 0x42** (tenet 5): on Z2M the outcome depends on the converter as
  well as the device.
- **Harm bounds.** Risks: a 3 s request running 30 s, a delayed on that stays on, never-off, and the load (a pump,
  heater, valve or compressor). Bounds: attended only, never from an automation; the user confirms the load is safe
  to cycle, defaulting to No; never on a class listed as doesn't work with `harms`, nor on `class_unknown`, nor on a
  battery device; always end with a verified Off or restore; abort and send Off on an outside state change, two failed
  reads, unavailability or cancel. **Gap:** whether a plain Off or `countdown: 0` cancels a pending Tuya countdown is
  what probes P3 and P4 of [step 5 part 3](../plans/2026-11-14-device-classes.md#step-5-part-3-probe-spec) answer;
  until then a Tuya probe can't promise a clean exit.
- **Privacy.** A result carries the integration, Zigbee model ID and manufacturer string, firmware, Z2M definition
  model, router or end device, HA, DeviceSide and Z2M or ZHA versions, whether Experimental features was on, the class
  reached, the probe kind, the request, the start state, the rounded ratio or rate, the outcome and the day. Never
  entity IDs, names, areas, IEEE addresses, MQTT topics, hostnames, instance IDs or exact times. HA's own
  device-database snapshot sends per device only manufacturer, model, model ID, sw and hw version, entry type and
  via device, and filters out custom integrations (`components/analytics/analytics.py`, `_device_payload`), so it is
  the field set to mirror but not a channel DeviceSide can use [code]. Diagnostics aren't a safe vehicle: MQTT
  redacts only the username and password (`components/mqtt/diagnostics.py`), so Z2M topics and friendly names pass
  through [code].
- **Flow back:** a prefilled device report through the existing issue URL, reviewed and submitted by the user. A
  telemetry endpoint needs a server this public repo can't hold.

## 4. Crowd reports and cleansing

**Today's path already fits tenet 7:** device report → `scripts/route_issue.py` labels and assigns → a maintainer's
`_manual.json` row, which `check_release` accepts only from a maintainer. The report is evidence; the maintainer
signs. Four gaps [repo]:

- **G1. A manual row can't cite a report.** [`docs/evidence.md`](../evidence.md#the-experimental-flag) says users'
  reports are "cited in a maintainer's `_manual.json` sign-off", but the schema's `manual_row` has
  `additionalProperties: false` and only `date`, `commit`, `tester`, `devices`, `passed`, `no_call_changed`
  ([schema](../test-records.schema.json)). No `_manual.json` exists yet, so adding a field breaks nothing.
- **G2. A manual device has no firmware**, while `test_device` and `fact_device` do.
- **G3. The report form can't carry the key Decision 35 uses.** `config_flow._device_facts` prefills from HA's device
  registry; on Z2M that is the definition's model and vendor, without the `_TZ3000_…` / `_TZE…` string that only
  `bridge/devices` shows, and without the class DeviceSide placed the device in.
- **G4. The form can't tell a harm from a plain failure:** one "didn't work" box per action, where the measured ratio
  is the diagnosis (10× is tenths vs seconds, never is ignored, came on then flipped is a toggle).

**Weighting, conflicts and decay** [inference, argued]:

- **No scores in code.** The maintainer checks the full key (model ID, manufacturer string, firmware, integration),
  that the reported class matches the rule the row credits, that the outcome is measured rather than "worked", and
  the DeviceSide version, which fixes the call.
- **Asymmetry for harms actions.** One credible failure outweighs any number of successes: a false "works" leaves a
  device on unattended, a false "doesn't work" shows a refusal at once; and successes don't generalize across a string
  that may cover several hardware revisions, while one failure disproves the universal claim. For dimming and color
  the asymmetry doesn't hold. Aggregating ratings (ProtonDB-style) hides the one failing configuration, so it has no
  place for harms actions.
- **A tension to settle:** evidence.md's "Contrary evidence" says a misbehavior report doesn't change the level;
  Decision 35 says a string reported failing is doesn't work. One reading: for a harms action on one string, a
  report with a measured outcome is itself the finding, and the demotion lands as the root-cause PR (a `doesnt_work`
  rule, `harms=True`, the issue as source) that moves only that string, per "split off the exception, not the
  class".
- **Conflict ladder, cheapest check first:** different call (DeviceSide version or class) is no conflict; different
  routing (Z2M vs ZHA, or a converter version) keys on routing (Decision 34); different firmware is the boundary the
  split rule waits for; same everything with different results is a white-label collision or user error, so ask for
  the debug log or a cheap probe, and the string is doesn't work until resolved; user error closes the report.
- **Decay: none by time** (tenet 3). A failing report on a Verified string, or on a firmware none of its rows covers,
  reopens it; a new firmware alone reopens nothing, and a passing report on it adds a row.

**Prior art, what to borrow:**

| Source | Mechanism | Borrow |
|---|---|---|
| Wikidata (general knowledge) | ranks preferred / normal / deprecated with a reason; sourced claims kept, not deleted; qualifiers | keep contradicted evidence (`_facts.json` is add-only already); `firmware` as the qualifier |
| OpenStreetMap (general knowledge) | verifiability, "on the ground" rule, changesets with a source, a working group for disputes | observed behavior beats converter code (tenet 2); the PR citing the report; a repo maintainer as escalation |
| [blakadder](https://github.com/blakadder/zigbee) | Google form plus "edit on GitHub"; binary marks per integration | the shape DeviceSide has, and why it can't answer tenths vs seconds |
| [Z2M device pages](https://github.com/Koenkk/zigbee2mqtt.io/blob/master/package.json) | generated from ZHC definitions | "supported" is evidence of routing, never of behavior |
| [CVE record format](https://github.com/CVEProject/cve-schema/blob/main/schema/CVE_Record_Format.json) | scoped CNAs, a `disputed` tag, version ranges with `versionType`, `defaultStatus` | CNAs ≈ integration maintainers; `defaultStatus` ≈ the default class; prefer explicit firmware sets to ranges, as Tuya firmware strings aren't reliably ordered |
| [MDN browser-compat-data](https://github.com/mdn/browser-compat-data/blob/main/schemas/compat-data-schema.md) | `version_added`, `partial_implementation` with notes, ranged values "used sparingly", `mirror` | a row means "verified on this firmware", never "since"; `mirror` ≈ tenet 5 inheritance, and its failure mode ≈ white labels |
| Debian popcon (general knowledge) | install counts | frequency orders triage; it is not evidence |

**Maintainer load** [inference]: about 20 to 30 minutes for a clean pass report, with a wait of days when the
manufacturer string or measured time must be asked for (perhaps half of Tuya reports today); 1 to 3 hours for a
failure that needs a root cause. A few reports a month after the seed triage.

## 5. Existing device databases

Only ZHC encodes per-device 0x42 units; kkossev's Hubitat drivers give scattered hints. The rest help with identity
at most.

| Source | Coverage | Timer units? | Curation | License | Reuse |
|---|---|---|---|---|---|
| ZHC | about 2,300 Tuya strings | yes: tenths by default, Tuya seconds per string, datapoints in s or min | reviewed PRs with tests; split per string; no tiers, no firmware keying | MIT | derive with citation; read live exposes |
| zigbee2mqtt.io | same as ZHC | prose on device pages only | generated | GPL-3.0 | link only |
| ZHA quirks | about 390 Tuya strings | vendor attributes only (Third Reality plug, s; Tuya valve, min) | PR review | Apache-2.0 | derive with citation |
| deCONZ DDFs | 761 files; Gold 468, Silver 11, Draft 5 | no; REST `ontime` passed through for all | status tiers | BSD-3-Clause | identity cross-check |
| openHAB Zigbee | 23 discovery entries | no; tenths for all | PR | EPL-2.0 | link only |
| SmartThings Edge | 499 zigbee-switch fingerprints, 11 Tuya strings | no; tenths where sent | Samsung PRs | Apache-2.0 | link only |
| Homey Tuya app | about 650 strings | datapoint comments (e.g. "0-86400 seconds") | one maintainer, "preserve installed-device behaviour" | MIT | cross-check |
| kkossev Hubitat | about 700 strings | some: Sonoff SWV seconds over 0x42; a read of the on/off cluster cancels its timer | one maintainer, no review | Apache-2.0 | leads to probe, cited |
| blakadder | 2,693 entries; last commit 2025-10-03 | no | form, unverified, stale | unclear | alias lookup, link |
| CSA products / DCL | numeric Matter vid/pid | no | certification | site terms restrict reuse (search snippet, unread) | link only |

Sources: ZHC as above; `zigbee2mqtt.io` `docs/devices/TS011F_plug_1.md` L117-124; `thirdreality/plug.py` L166-177;
deCONZ `rest_lights.cpp` L1126; openHAB `ZigBeeConverterSwitchOnoff.java` L298-303; SmartThings frient-IO `init.lua`
L151-176; Homey `lib/TuyaDataPoints.js` L239 and `MAINTAINING.md`; Hubitat `Tuya Zigbee Valve.groovy` L1845-1861 and
L1942-1946; DCL `model.proto`, `compliance_info.proto`.

**Licensing** (not legal advice; the maintainer's call): facts such as "string X takes 0x42 in seconds" are generally
not copyrightable, but a compiled database can be protected (the EU's sui generis database right) and site terms can
restrict reuse. MIT, Apache-2.0 and BSD allow a derived table in this MIT repo with their notices (Apache-2.0 also
asks that changes be stated). Copy no GPL-3.0 text or code (zigpy, Z2M, its docs) and no CSA content; citing and
linking is fine. Tuya's docs terms are unknown: cite only.

**No source keys timer behavior on firmware.**

## 6. The options compared

| Option | Coverage | Accuracy | Cost to build | Harm risk | Maintainer load | Fits the levels as |
|---|---|---|---|---|---|---|
| Live routing from the integration (Z2M `bridge/devices`) | every Z2M device, the user's own ZHC version | exact for routing; says nothing of behavior | built (Decision 18) | none | none | keys a class (Decision 34) |
| Mined ZHC table | about 4,700 definitions | routing exact; units a claim, about 1 in 7 timer commits corrects one | small: a script and a scheduled PR | none | a review per diff | seed list, probe targets, doesn't-work candidates; never Verified or Documented |
| Tuya cloud fixtures, tuya-local join | about 60 joined strings | declared units; Wi-Fi firmware may differ | small | none | low | second opinion in research |
| Other device databases | identity only, except Hubitat hints | low for timers | small | none | low | leads, cited |
| Read-only device signals | per device | high for "no timer", nothing for units | small per integration | none | none | refuse or place; can only narrow |
| Rate check after the call | every timed on where OnTime reads | high on devices measured | moderate: a second read in confirmation | the call is already sent | none | `sent` instead of `confirmed`, a warning, a log line for the first report (tenet 4) |
| Attended probe | users who opt in | high per device | high: a flow, bounds, a payload | bounded by the rules in §3, not zero | per report | a user report a maintainer cites |
| Crowd reports | users who report | varies; good with a measured outcome | small: schema and form fields | none beyond the run reported | 20 min to 3 h each | `_manual.json` row citing reports (Verified per string), or a `harms` doesn't-work entry |

Matter needs none of this machinery while its FeatureMap check holds: the unit is fixed by spec and certification
checks it ([Matter index](../integrations/matter/index.md)).

## 7. Recommended layers [inference]

Each layer can only narrow what the one below allows, except a maintainer's sign-off, which is the only thing that
raises a level.

1. **Identity and routing:** the integration's own report (Z2M `bridge/devices`; ZHA's quirk and registry), as
   today. Keys the class (Decision 34).
2. **Upstream mining as research, not code:** a dated run of the ZHC miner in `zigbee2mqtt/research/`, giving the
   seed list Decision 35 asks for and the probe targets. Classes and doesn't-work entries cite it. Freshness by a
   scheduled diff PR, later.
3. **Read-only refusals:** UNSUPPORTED_ATTRIBUTE on OnTime, a Matter device without LT. Each needs evidence the
   failure happens to users before it's built (tenet 6); the Sengled and `no_lt_feature` already have it.
4. **A second read in the confirmation:** catches a seconds device after the fact; reports `sent`, warns, and logs
   the rates so the first bug report holds the diagnosis.
5. **Crowd reports with measured outcomes**, through the existing form and `_manual.json`, with the asymmetry for
   harms actions.
6. **The attended probe**, last, once P3 and P4 show how to cancel a Tuya countdown.

No local auto-select of a unit per device: it would put a fact in one user's storage (one fact, one home), run an
unreviewed call outside the registry and the doesn't-work refusal (unknown is flagged, never Verified), and need
invalidation on firmware updates (tenet 6). A local result may only narrow: refuse a device that failed.

**Before v0.1.0** (small, and each names its failure):

- **Form prefill of the Zigbee manufacturer string, Zigbee model ID, firmware and placed class** (G3; a shared file,
  so a repo maintainer). Without it a Tuya report can't be matched to the string Decision 35 keys on.
- **`manual_row.reports`, optional issue URLs** (G1). Without it, when a report on a Verified string is contradicted,
  nobody can find the rows that rested on it; today the citation evidence.md asks for has no field. Binding-rule
  surface, so an Opus audit.
- **The mined seed list** for step 5 part 3, step 1, as a dated research file.
- **The `turn_on_for` DEBUG line carries the OnTime read-back** where the adapter reads it, per
  [`docs/logging.md`](../logging.md), if it doesn't already.

**Later:**

- `manual_device.firmware` (G2), once a class rule matches on firmware (the plan's Deferred list).
- A timed-outcome line in the report form (G4).
- The second read in confirmation (layer 4), with the step that first builds ZHA's or Z2M's read-back.
- `scripts/draft_manual_row.py <issue>` and dedupe by (integration, model ID, manufacturer string) at routing, when
  volume shows the need.
- A warn-only `gen_compat --check` for Verified strings resting only on reopened reports.
- The scheduled ZHC diff PR.
- The attended probe.

## 8. Open questions for the maintainer

1. **Contrary evidence vs Decision 35:** does a measured failure report on one string count as the finding for a
   harms action, or must a maintainer reproduce it first? evidence.md and Decision 35 read differently today.
2. **Should mined routing ever carry level weight,** for example Documented for a string ZHC routes identically to a
   Verified sibling? This note says no (a route isn't behavior, and route A has known departing strings), but the
   Documented test is the maintainer's to apply.
3. **Firmware field for rules:** `appVersion`, which both Z2M and ZHA can read, or each integration's own field?
   Z2M sometimes synthesizes `software_build_id` for Tuya.
4. **Is a seconds-reading device "doesn't work, harms" or "not yet supported"** once a seconds call exists for it?
   Today's call harms it; Decision 3 settled the TS011F case one way, and a general rule would save a decision per
   class.
5. **The probe at all:** is an attended in-field probe worth building, given that it sends a call that may harm,
   however bounded? Or do crowd reports with measured outcomes suffice?
6. **Copying a derived ZHC table into the repo** (MIT, with notice) versus citing upstream lines only.
7. **The ranges:** ZHC caps the 0x42 countdown at 43,200 s "per Tuya documentation", while Tuya's cloud schemas show
   0..86,400 s for many plugs. Which bound does the per-class duration limit (part 3, step 5) take, given that
   neither is measured?
8. **Home of this file:** CLAUDE.md's "Where facts go" names `<x>/research/` for dated sources but no shared home for
   a cross-integration one. This note creates `docs/research/`; the table could add it as the shared home, or the
   note could move to `zigbee2mqtt/research/`, where most of its sources sit.
