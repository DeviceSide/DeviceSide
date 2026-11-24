# Other brands: set_attributes and get_attributes in Labs (Zigbee2MQTT)

2026-11-24. PR #605, branch `wt/aqara-z2m-run`, worktree `deviceside-wt/aqara-z2m-run`.

## Coordination

Intent: Put Zigbee2MQTT's `other` class in Labs on set_attributes and get_attributes, lights only, and stop reading
`onTime` on `other`, so a first rig run on an Aqara bulb can exercise every Labs action.
Touches: custom_components/deviceside/integrations/zigbee2mqtt/classes.py, custom_components/deviceside/integrations/zigbee2mqtt/read.py, custom_components/deviceside/integrations/zigbee2mqtt/get_attributes.py, custom_components/deviceside/integrations/zigbee2mqtt/set_attributes.py, tests/integrations/zigbee2mqtt/**, docs/integrations/zigbee2mqtt/index.md, docs/integrations/zigbee2mqtt/internals.md, docs/device-compatibility.md, README.md

## Why

A rig run of `lab_aqara` (Aqara color bulb, Z2M) on 2026-11-24 tested nothing: the bulb is in `other`, and every case
was refused `not_built` at its `set_attributes` setup, the dimming cases included.
Research: [2026-11-24-other-brands-execute-if-off-and-reads.md](../integrations/zigbee2mqtt/research/2026-11-24-other-brands-execute-if-off-and-reads.md).

## Decisions (Jason, 2026-11-24)

1. **set_attributes: `other` in Labs, lights only.** A failed write doesn't harm (docs/evidence.md, "When today's call
   harms a class"; users try a Labs action before relying on it). The research found no departure among `other`'s
   vendors; the known ones (Sengled, IKEA KAJPLATS) are outside `other`. A pre-rev-7 bulb rejects the override fields
   (MALFORMED_COMMAND), which raises. No new guard: the existing read-back already rejects a bulb that jumps to full as
   `not_stored`.
2. **Devices known to turn on unwanted when written stay refused** (sharp edges for later users). Today that is Sengled
   (own family, in no scope); add any new one as it's reported.
3. **get_attributes: `other` in Labs, lights only, without `onTime`.** On Z2M one unsupported attribute fails a whole
   cluster read (herdsman `Endpoint.read`), `onTime` isn't required, and no timer action serves `other`, so the
   read asks `genOnOff` for `onOff` alone there. A bulb that advertises XY but can't read `currentX`/`currentY`
   (Paulmann RGBW) fails with an error: accepted, not pre-screened.
4. **Switches, plugs and relays stay out**: the real harm is in loads (heaters, routers). Timer and on/off actions on
   `other` keep their entries.
5. Next actions, later, one at a time from least to most harm; not this PR.

## Steps (one step; no implementer/reviewer split)

1. `classes.py` OTHER_LEVELS: `get_attributes` and `set_attributes` to `labs(OTHER)`, scoped to lights (`OnDomains` /
   `domains=` as core/scope.py takes it); rewrite the comment to cite the research.
2. `read.py` `clusters` (or get_attributes' caller): no `onTime` for a target in `other`; the timer field reads absent.
   Keep the read-back in set_attributes unchanged.
3. Unit tests pin both levels and the `other` read's attribute list as literals. `scripts/gen_compat.py` and the other
   generators regenerate; `index.md` "Other brands" says set and read are in Labs on lights; `internals.md` cites the research.
4. `.venv/bin/pytest -n auto --transcripts=check`; push; audit gate (Labs flag: Opus auditor), then `owner-findings`.
5. Rig: `../../ha-rig/scripts/rig.py --profile lab_aqara --facts --unattended` from the worktree. The profile is
   restricted: ask Jason before each run for `DEVICE_SIDE_RIG_RESTRICTED=1`. Commit the records; a pass is evidence
   for a future `aqara` class, not for `other`.

## Handoff

2026-11-24, second session. Branch `wt/aqara-z2m-run`, worktree `deviceside-wt/aqara-z2m-run`, draft PR #605.

- **Done:** steps 1–3 in 286b0b42 (`_LIGHTS = labs(OTHER, domains=(LIGHT,), only=True)` on get/set_attributes; `read.clusters(target, device_class)` asks `other` for `onOff` alone; tests and docs; generators run; `--transcripts=check` green, 3571 passed).
  Step 5 ran (Jason approved the restricted run and turned Labs on in the rig HA's DeviceSide options; ha-rig has no Labs switch).
  Report: `/var/folders/wk/kszxz30j6wd2vmmnd02c5bfc0000gn/T/deviceside-rig/rig-run-2026-11-24-211936.md`. 17 of 37 planned cases passed
  (brightness fades, stop, set_attributes, most get_attributes). **No records written**: the rig kept the Hue-based
  records, since lab_aqara skips their group cases. So nothing to commit from the run.
- **Failures, by cause:**
  1. **Surprise (Evidence 4): the Aqara bulb is Unplaced.** turn_on_for/turn_off_for raise `class_unknown` (also
     `reads_a_running_timer` at its turn_on_for step), so `capability` returns Unplaced: bridge/devices lacks
     `interview_completed` or a Zigbee string for it. Root-cause it (the DEBUG line from `classes.capability` names
     the reason) before the next run. turn_on_for would refuse `other` as not_built anyway.
  2. Device fact: `keeps_and_reads_hs_while_off`: given hs while off, the bulb stays in `color_mode: xy`.
  3. Not built, as expected: hue moves fail at `mark_hue` ("returned no hue"); saturation raises not_built.
- **Also in the tree, uncommitted until this handoff:** `research/2026-11-24-other-brands-dimming.md` (Jason asked
  mid-session: is dimming on `other` safe like set/get). Verdict: safe in Labs as is, no guard. The stated reason
  (Zigbee 3.0 certification) is thinner than the evidence (same call as Hue, model-level departures only: Müller
  Licht tint older firmware, AwoX/Eglo soft-off). It suggests rewording `docs/internals.md` Shared. Not acted on.
- **Next:** step 4's audit: `audit-gate brief pr` → spawn → `audit-gate record` → `audit-gate status`, then
  `owner-findings`, fix Critical/High, then `gh pr ready` with the PR summary (Labs-flag surface: Opus auditor).
  Report items 1–2 and the research verdict to Jason.
- **Open (Jason):** reword the Shared dimming reason per the research (separate PR, shared doc, repo maintainer);
  an `aqara` family once records exist (Z2M maintainers).
