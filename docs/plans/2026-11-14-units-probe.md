# Units probe: users measure an unknown device's timer unit

**When:** after v0.1.0 ships (Jason, 2026-11-14). Tracked in the issue named in the PR that lands this plan.

## Coordination

Intent: A user with an Experimental device runs an attended probe from DeviceSide. It measures whether the device
reads a timed-off call in tenths or seconds, ignores it, or misbehaves, ends safely whatever happens, and turns the
result into a prefilled GitHub issue that a maintainer can fold into the evidence.
Touches: a new probe flow in custom_components/deviceside (a button or repair flow, not a service), the ZHA and
Zigbee2MQTT packages' probe adapters, docs/evidence.md (what a probe report proves), the issue template
`.github/ISSUE_TEMPLATE/`, docs/logging.md, and tests.
Tests-with: none.
Depends-on: the device-classes plan's step 7a (OnTime read-back, Zigbee manufacturer string in the form), and the
countdown probe (step 5 part 3, P3/P4), which shows how to cancel a running Tuya countdown. Probing on the datapoint
path needs that answer. Benefits from `2026-11-14-device-facts-across-integrations.md`, so that one result lofts
across integrations, but doesn't need it.

## Why

- The thorniest fact in timed actions is the unit. The Zigbee spec says tenths, much Tuya firmware reads seconds,
  some devices ignore the call, and datapoint countdowns come in seconds, minutes or hours. No upstream source is
  reliable for units (the timer-units research, 2026-11-14): mined data can seed classes and probe targets, never a
  level.
- The rig can test only the maintainer's devices. Users own the long tail, and a probe lets each of them settle their
  own device's unit in seconds, with evidence a maintainer can trust.

## Design

### 1. Measure, don't ask

- DeviceSide already listens to state. The probe sends one timed-off call and times the off report itself: about a
  tenth of the value means tenths, about the value means seconds, and no off report means the call was ignored.
- A second, independent signal: during the run it reads `OnTime` twice, a second apart. A drop of about 10 means
  tenths, about 1 means seconds. The research found this countdown rate the strongest unit signal.
- The user is asked only when the two signals disagree, or when the device doesn't report its state: "Did it turn
  off after about 3 s, about 30 s, or not at all?"

### 2. Safe by construction

- **A value whose readings can't be confused:** `on_time=30` gives 3 s for tenths and 30 s for seconds, a bounded
  worst case.
- **Always end in a known state:** a plain Off at the longest expected time plus a margin, whatever the probe saw, so
  an ignored or misread call never leaves the device on.
- **Attended only:** run from a button on the device's DeviceSide page, never a service an automation could call. It
  shows a warning about what is plugged in, such as a heater or a pump.
- **Probe from both on and off,** since the lab probe showed starting from off can behave differently.
- **Datapoint path only after P3/P4:** a Tuya countdown toggles at zero, so the probe needs a proven way to cancel it
  before it can run there.
- Matter needs no probe: its spec fixes the unit and certification tests it (TC-OO-2.3).

### 3. A one-click report

- The probe drafts a prefilled GitHub issue: model ID, Zigbee manufacturer string, firmware, integration, the call
  sent (its signature, once call signatures exist), both measurements and the verdict. It holds no household
  identifiers: no entity IDs, names, IEEE addresses or hostnames.
- This fits how reports arrive, which is mostly as issues (Decision 69). A maintainer folds credible results into
  records or doesn't-work entries under Decision 68. With call signatures, one probe result lofts across
  integrations.
- A probe never changes a level on the user's own install. Automatically choosing the unit locally is out of scope
  (see Open questions).

## Steps

1. **Probe the probe.** Settle whether Zigbee2MQTT can send a raw ZCL command with no converter (unknown). ZHA can,
   through `zha.issue_zigbee_cluster_command`. Record the finding in each bundle's internals.md.
2. **ZHA probe.** Run the 0x42 probe on ZHA, with timing, OnTime read-back, the safe end, and the attended button.
   Unit tests pin the frames and the safe end.
3. **Report.** Add the issue template and the prefill, plus an evidence.md note on what a probe report proves (a
   credible report under Decision 68, not a record).
4. **Zigbee2MQTT probe,** per step 1's finding.
5. **Datapoint path,** after P3/P4.

## Open questions

- Should a user's own probe result switch their own device to the measured unit locally? The research advised
  against any automatic local choice. Revisit once probe reports show how often units vary between firmware versions
  of one model.
- Do repeated probe reports from different users, which agree, make a device Verified without a maintainer's run?
  Tenet 7 says maintainers judge sufficiency, so likely a `_manual.json` row whose PR body cites them.
