# Aqara bulb to Verified on Zigbee2MQTT, then Documented by call pattern

2026-11-24. Planned from [the handoff](2026-11-24-aqara-verified-handoff.md); branch `wt/aqara-verified`, worktree
`deviceside-wt/aqara-verified`.

## Context

Jason's goal: (1) the Aqara color bulb (Z2M definition T2_E27, model `lumi.light.agl003`, manufacturer `Aqara`)
Verified on DeviceSide for every action it supports; (2) a judgment call on which other devices can be Documented by a
shared call pattern. Since #605/#607 the bulb is placed as `other` and takes dimming, stop and set/get attributes in
Labs. The 2026-11-24 23:29 rig run passed those (17 pass / 16 fail / 28 skip) but wrote **no records**: `lab_aqara`
has no group roles, and the rig never overwrites a record with one that skips a case it passed (ha-rig `docs/rig.md`,
"A record never narrows to a profile"). Open facts: the bulb looks xy-only (stays `color_mode: xy`, `currentHue`
UNSUPPORTED_ATTRIBUTE); its timer behavior is unprobed; one unexplained `no genLevelCtrl reply` timeout.

## Decisions (interview, 2026-11-24)

1. **Hue/saturation:** probe first (read ColorCapabilities 0x400A; one moveHue and one moveSaturation write). Ignored:
   not built on `aqara` (a host-side xy emulation is plausible, so never no known method), said in index.md; the moves
   aren't harmful actions, so no `NotBuilt` entry. Runs: build and verify, with the rig reading xy if it can't read hue.
2. **Timers:** probe genOnOff onWithTimedOff (`on_time`): turns off on time; a second, shorter timer replaces it or
   not; `on_time: 0`. Pass: `turn_on_for` on `aqara` (Labs until the rig record, then Verified). Fail: a
   `NotBuilt` entry for `aqara` in `integrations/zigbee2mqtt/refusals.py` citing the probe. `turn_off_for` stays
   not built (no Zigbee call). DeviceSide's own soft timer is out of scope.
3. **Class:** a new `aqara` family, Z2M only: class `aqara` = lights whose Zigbee manufacturer string is `Aqara`,
   like `hue`/`sengled`/`gledopto` (a record on a maker outside the named classes adds a class named for it:
   `docs/evidence.md`, Unknown is flagged). Verified on agl003's record for the actions it passes, for the whole
   class. `LUMI`-string lights stay in `other`. ZHA later, on a ZHA run.
4. **Records:** an ha-rig change so a run writes the cases it ran into a record while keeping the rows it skipped as
   not applying (here: Hue's group cases), rather than keeping the whole record. Its own ha-rig PR, which this PR's
   step 4 waits on.
5. **Timeout:** repro ~10 runs of the setup step that hit it, with Z2M debug logging. Reproduces: root-cause and fix,
   or record the limit, before Verified. Doesn't: record it in `internals.md` as seen once, unexplained, and proceed.
6. **Goal 2 (Documented) is open:** Jason wants the evidence of what vendors publish first (step 6). Today's rule:
   a class spanning vendors is never Documented by a sibling's pass, and the sibling route needs the vendor's own docs
   giving the call identically.

## Step 1 rulings (2026-11-25, from [the probe](../integrations/zigbee2mqtt/research/aqara/2026-11-25-agl003-probe.md))

7. **Decision 1, Ignored:** ColorCapabilities 24 (xy and color temperature only), hue and saturation attributes
   UNSUPPORTED_ATTRIBUTE, moveHue/moveSaturation leave CurrentX/Y unchanged. Hue and saturation actions not built on
   `aqara`, said in index.md; no `NotBuilt` entry.
8. **Decision 2, Fail:** `{"state":"ON","on_time":N}` from off never turned the bulb on (N 10, 30 then 10, 0); OnTime
   and OffWaitTime unsupported. A `NotBuilt` entry for `aqara` turn_on_for citing the probe; get_attributes keeps
   asking no OnTime, now on the probe.
9. **Decision 5, Reproduces, limit recorded:** 1 in 10 when a while-off moveToLevel lands during the bulb's own 1.5 s
   off fade (the rig's put-back: turn_off then set_attributes with no wait); 0 in 10 after HA shows off. Z2M's frame
   logging was off, so no deeper root cause. Recorded in internals.md (mechanism, counts) and index.md (the user-facing
   limit); not a blocker for Verified, as the test case's sequence never hit it.

## Steps

**No rig run or write probe before 07:45 local on 2026-11-25** (Jason, 2026-11-24): work that needs no device (steps 2, 3, 6) goes first. Every rig run and every write probe needs Jason's yes (`DEVICE_SIDE_RIG_RESTRICTED=1`). Read-only probes run through
ha-rig's HAClient: `in-dir /Users/jason/projects/ha/ha-rig uv run python -I <script>`. No entity IDs, names, MACs or
hostnames in commits, docs or research files.

1. **Probes** (Decisions 1, 2, 5). Write `docs/integrations/zigbee2mqtt/research/aqara/2026-11-2x-agl003-probe.md`:
   ColorCapabilities and the color attributes the bulb reports; moveHue/moveSaturation result (moved? xy changed?);
   the three `on_time` cases with timings; the timeout repro count and Z2M log lines. Then rule Decisions 1, 2 and 5
   from the results and record them here.
2. **ha-rig records** (Decision 4), in `/Users/jason/projects/ha/ha-rig`, its own worktree and draft PR; opus, as how
   a record holds cases run on different profiles is a design call. Check: the rig's own pytest, and a dry staging of
   the 23:29 run's results showing Hue's group rows kept and the Aqara rows added. Add it to Coordination's Depends-on.
3. **`aqara` family** (Decision 3), in Labs first. `families/aqara/__init__.py` on the `sengled` pattern
   (`Family(key="aqara", maintainers=(), classes={AQARA: {Platform.LIGHT}})`, a `Rule` on `zigbee_manufacturer: Aqara`, as Z2M's vendor `Aqara` also covers `LUMI`-string lights);
   added to `FAMILIES` and `RULES` in `families/__init__.py` after Tuya's Zigbee rules, with the order comment;
   `labs(...)` on the actions `other` takes today, plus whatever step 1 admits; refusal entries per Decision 2 in
   `refusals.py` (integration path, integration maintainer). Classification test and snapshot
   (`tests/integrations/zigbee2mqtt/test_classification.py`), `docs/integrations/zigbee2mqtt/index.md` `### Aqara`
   in Hue's shape, `devices.yaml` card phrase, `docs/models.yaml`, regenerate with `scripts/gen_compat.py` and
   `scripts/gen_codeowners.py`. Check: `.venv/bin/pytest -n auto --transcripts=check`.
4. **Rig run → Verified** (after step 2 merges). `lab_aqara` restricted run, Labs on; records written. Lift each
   action whose cases passed to `verified(...)` on `aqara`, lights; the rest stay Labs or not built per step 1.
   The coverage check (`docs/evidence.md`, The coverage check) must pass. Decision for this run: lifting the Labs flag. The rig carries rows only onto an identical call transcript (HA-rig#108), and the Z2M records for get_attributes, lower_hue, lower_saturation and turn_on_for cite an older transcript than HEAD's: their Aqara rows land only after a Hue-profile rerun of those suites (Jason's yes), or the rig prints `Kept`.
5. **Audit and ready**: `audit-gate` on the PR diff, `owner-findings`, then `gh pr ready` (default-branch PR: Jason
   merges).
6. **Goal 2 research** (Decision 6), independent of steps 1-5: `/research` into what Zigbee vendors publish about their
   lights' ZCL calls (Aqara, Innr, Ledvance, IKEA, Signify's Hue developer docs, Sengled, Gledopto, Tuya), and what Zigbee
   3.0 / ZLL certification tests for Level Control and Color Control (moveToLevel with ExecuteIfOff, attribute reads).
   Output: `docs/research/2026-11-2x-vendor-call-documentation.md`. Then bring Jason the decision (keep the rule, amend
   `docs/evidence.md` with a call-pattern route, or a narrower route) via `/grilling`; an amendment is a binding-rule
   change with its own plan and an opus auditor.

## Verification

- Unit: `.venv/bin/pytest -n auto --transcripts=check`; the classification test places agl003's strings in `aqara`
  and a `LUMI` bulb in `other`; `scripts/gen_compat.py --check` and `scripts/gen_codeowners.py --check` clean.
- Hardware: step 4's run writes `docs/integrations/zigbee2mqtt/test-records/*.json` rows with `class: aqara`, and
  existing Hue rows are unchanged in the diff.
- Card: `docs/device-compatibility.md` shows Aqara lights at the levels the records give.

## Coordination

Intent: Aqara color bulbs Verified on Zigbee2MQTT as a new `aqara` class, on probes and rig records; research what
vendors publish to decide whether a call pattern can make other devices Documented.
Touches: custom_components/deviceside/integrations/zigbee2mqtt/families/aqara/**, custom_components/deviceside/integrations/zigbee2mqtt/families/__init__.py, custom_components/deviceside/integrations/zigbee2mqtt/refusals.py, tests/integrations/zigbee2mqtt/**, docs/integrations/zigbee2mqtt/**, docs/models.yaml, docs/device-compatibility.md, docs/research/**, README.md, .github/CODEOWNERS
Depends-on: jasonmx/HA-rig#108
