# Persistent auto-off on Zigbee2MQTT: Sonoff and Tuya inching (Labs)

Copy this plan to `docs/plans/2026-11-24-zigbee2mqtt-inching.md` as the first commit (`pr-draft` on that path), on
branch `wt/z2m-inching` off `main`. Inputs (gitignored, copied into the repo in step 1):
[tuya-inching.md](file:///Users/jason/projects/ha/deviceside/notes/2026-11-24-coverage-research/tuya-inching.md),
[sonoff-inching.md](file:///Users/jason/projects/ha/deviceside/notes/2026-11-24-coverage-research/sonoff-inching.md),
demand in `notes/2026-11-24-coverage-research/auto-off-demand.md` (mostly garage, gate and staircase pulses: a
persistent auto-off of a second or two).

## Coordination

Intent: serve `set_auto_off` and `clear_auto_off`, in Labs, on Zigbee2MQTT for single-channel Sonoff relays (0xFC11
inching) and two evidenced Tuya strings (0xE000 inching), by one publish of Z2M's `inching_control_set`; the first
persistent setting on Zigbee.
Touches: `custom_components/deviceside/integrations/zigbee2mqtt/` (new `set_auto_off.py`, `clear_auto_off.py`, a new
`families/sonoff/`, `families/tuya/` (new `inching.py`), `families/__init__.py`, `refusals.py`, `__init__.py`),
`tests/integrations/zigbee2mqtt/`, `docs/integrations/zigbee2mqtt/` (`index.md`, `internals.md`, `devices.yaml`,
`research/sonoff/`, `research/tuya/`), `docs/deferred.md`, `docs/integrations.md`, `docs/plans/`, README and
`docs/device-compatibility.md` and other generated files (regenerated).
Depends-on: none.

## Context

Shelly is the only integration with `set_auto_off` today (`integrations/shelly/auto.py`). Z2M exposes both vendors'
inching under one composite key, `inching_control_set` (access SET only: write-only, no `/get`, and Z2M publishes the
value written as state). Tuya's countdown plug `TUYA_COUNTDOWN_HARMED` (`_TZ3000_gjnozsaz`, TS011F) is not built
pending inching (plan 2026-11-14-device-classes, Decision 41); research gives it no inching evidence, so it stays as is.

## Decisions (Jason, 2026-11-24)

1. **One plan, one PR**, both vendors: they share the key and the adapters.
2. **Tuya: the evidenced single-endpoint strings only**, in Labs: WHD02 `_TZ3000_skueekg3` (zigbee model TS0001;
   ZHC#13879: 5 s and 63 s measured, readback right) and Mowe MW781Z `_TZ300A_rncj86af` (TS0726; ZHC#13118: 5 s
   measured). NFZB-2 and MW783Z are multi-gang, so out with multi-gang. Every other definition ZHC gives inching
   stays where it is classed today; `_TZ3000_mzcp0of6` and `_TZ3000_p26flek3` were reported having no effect.
3. **Sonoff: every single-channel model exposing `inching_control_set`**, in Labs, as one firmware family on one
   call: ZBMINIR2 (and its white label MINI-ZBD), ZBMicro, MINI-ZB1GS, MINI-ZB1GSP, BASIC-ZB1GSP, S61SZBTPB,
   MINI-ZBDIM (a light). S60ZBTPF and S60ZBTPG are not built: DISABLE reported having no effect (Z2M#31799), so
   `clear_auto_off` would leave the plug pulsing. MINI-ZB2GS waits on per-endpoint addressing.
4. **Sent, no readback.** `confirmable=False` (status `sent`; a logged Z2M failure is `rejected` via `set_check`).
   `get_attributes` reports no auto-off setting for these classes: Z2M's state is the last write's echo, and the
   device may disagree (S60 showed inactive after pairing while inching ran, Z2M#31604). A read path reopens it
   (`docs/deferred.md`, step 4).
5. **Z2M only.** ZHA has no quirk command for either (Sonoff: the 0xFC11 quirk declares no `protocolData`, PRs
   ZHADH#5135 and #5317 open; Tuya: `TuyaZBE000Cluster` has no attributes or commands), so a ZHA call can't be sent.
   Deferred, reopened by a quirk that declares the command.

## Design

### The adapters

New `integrations/zigbee2mqtt/set_auto_off.py` (`Z2MSetAutoOff(Z2MAdapter[TimedRequest])`) and `clear_auto_off.py`
(`Z2MClearAutoOff(Z2MAdapter[Request])`), registered in `__init__.py` `ADAPTERS`. Each serves only its classes' own
calls: `own_calls_only=True` (as `turn_off_for.py`), `**class_scope("set_auto_off")` / `("clear_auto_off")` from the
families' `labs(...)` scopes, `native_groups=False` (a group's call isn't the composite; it falls back to members),
`confirmable=False`, `supports` adds `not_addressable` as `turn_off_for` does. Domains: switch and light (MINI-ZBDIM).
Every other Z2M class is refused as not built by `own_calls_only`; no refusal entry is needed for that.

### Sonoff (new Z2M family `families/sonoff/`, `maintainers=()`)

- Class `sonoff_inching`: a rule on `definition_model` in the Decision 3 allowlist (escaped) **and** `exposes`
  containing `inching_control_set`. An allowlist, as `docs/evidence.md` (In Labs) admits only the identities research
  names; `exposes` holds device-wide properties only (`rules.definition_fields`), which also keeps MINI-ZB2GS out (its
  composite is per endpoint, ZHC `exposeEndpoints`). Confirm each definition model string at ZHC's current release.
- Class `sonoff_s60`: `definition_model` S60ZBTPF|S60ZBTPG with the same expose; a `NotBuilt` entry in
  `refusals.py` on both actions, source the Sonoff research file, reason Decision 3's. Its other actions keep what
  they have today: check `test_classification.py` and give the class every refusal entry the class it leaves held.
- Rule group placement in `families/__init__.py`: after Tuya's `ZIGBEE_RULES` (no Tuya device has these definition
  models), with a one-line comment.
- Call (`families/sonoff/inching.py`): `set_auto_off` publishes
  `{"inching_control_set": {"inching_control": "ENABLE", "inching_time": t, "inching_mode": "OFF"}}`;
  `clear_auto_off` publishes `{"inching_control_set": {"inching_control": "DISABLE", "inching_time": 0.5,
  "inching_mode": "OFF"}}`. `inching_mode` is always sent: ZHC sets mode ON (auto-on) unless it reads `"OFF"`
  (ZHC `src/devices/sonoff.ts` L2740 at `ed29f800`; ZHC#13383), and mode ON switches the relay on at once.
  `DurationLimits(min_s=0.5, max_s=3599.5, step_s=0.5)` on every model: ZHC writes a 16-bit time, so the 86399.5 s
  models can't take more than 32767.5 s through it, and one limit keeps one class.

### Tuya (`families/tuya/inching.py`, beside `countdown.py`)

- Class `tuya_inching`: a rule on `zigbee_manufacturer` in the two Decision 2 strings (catalog constants in
  `zigbee/tuya.py`, as the countdown strings are) **and** `exposes` containing `inching_control_set` (ZHC enables
  WHD02's only on modelID TS0001, so the TS000F variant stays out). Placed in `ZIGBEE_RULES` before the rule that
  classes these strings today (likely `TUYA_ZCL`; pin it in `test_classification.py`). The class inherits that
  class's refusal entries on every other action, so nothing but auto-off changes for these devices.
- Call: `set_auto_off` publishes `{"inching_control_set": {"inching_control_1": "ENABLE", "inching_time_1": N}}`;
  `clear_auto_off` publishes `{"inching_control_set": {"inching_control_1": "DISABLE", "inching_time_1": 1}}`. Both
  fields are required: ZHC skips a gang missing either and sends an empty payload (ZHC `src/lib/tuya.ts` L2905).
  `DurationLimits(min_s=1, max_s=65535, step_s=1)` (Z2M expose L927-929; the wire is uint16 seconds, so no sub-second).
- No interaction with `turn_on_for` to handle: neither string is in a class `turn_on_for` serves (pin that in a test).
  If one were, inching and the countdown would share a channel, which research leaves unknown.

### Docs

- `docs/integrations/zigbee2mqtt/index.md`: a `###` per new class (`sonoff_inching`, `sonoff_s60`, `tuya_inching`)
  saying what sets it apart, why it is admitted (research, Decision 2/3), and the user-visible limits: Tuya whole
  seconds from 1 s, Sonoff half seconds from 0.5 s to about an hour; the status is `sent`, as the setting can't be
  read back; auto-on is not offered.
- `internals.md`: the two wire calls, with the ZHC citations at `ed29f800`; the mode-ON default trap; ZHC's 16-bit
  Sonoff time; Tuya's base64 payload and the gang-4 encoding defect (why multi-gang waits); the off arrives as an
  On/Off report (ZHC#13118, ZHC#13383).
- `devices.yaml`: the classes' card phrases and sections, naming the models.
- `docs/integrations.md`: no shared set_auto_off rows exist, so one short paragraph under Zigbee plugs and switches (built on Z2M only, results `sent`, no ZHA call).

## Steps

1. **Research and plan.** Copy the two notes into `docs/integrations/zigbee2mqtt/research/sonoff/2026-11-24-inching.md`
   and `research/tuya/2026-11-24-inching.md` unchanged but for a header line (dated sources, never edited after);
   check they hold no household names. Commit the plan; `pr-draft`.
2. **Adapters and Sonoff.** `set_auto_off.py`, `clear_auto_off.py`, `families/sonoff/`, the rule group, the
   `sonoff_s60` refusals, fixture devices for each admitted model and S60 and MINI-ZB2GS (from ZHC's definitions),
   unit tests pinning each payload as a literal (enable, disable, 0.5 s, 3599.5 s, a clamp) and the classification.
3. **Tuya.** `inching.py`, the class, its catalog strings, rule placement, inherited refusals, fixture devices for
   both strings plus a TS000F `_TZ3000_skueekg3` and an enabled-but-unevidenced string (`_TZ3000_mzcp0of6`) that must
   not class as `tuya_inching`, payload tests as in step 2.
4. **Docs and deferred.** The Docs section; `docs/deferred.md` entries, each with what reopens it: inching readback
   (Tuya 0xD003 reads, a Sonoff 0x17 report on newer firmware: reopens `confirmable` and `get_attributes`); ZHA
   inching (a quirk declaring the command); Sonoff auto-on (inching mode ON: one slot shared with auto-off); further
   Tuya strings (a pass, or a report with a measured time); S60 (a report that DISABLE works). Multi-gang inching
   (MINI-ZB2GS, NFZB-2, MW783Z, the 3-gang with backlight): a line in the existing per-endpoint addressing entry.
   Regenerate (`scripts/gen_compat.py` and the rest CI `--check`s).

Check before each push: `.venv/bin/pytest -n auto --transcripts=check`. New calls, so no existing transcript should
change; a changed one is a finding.

## Verification

No hardware run gates the merge (Labs on research, evidence tenet 8). The rig cases come with lifting the flag: a
Sonoff ZBMINIR2 `set_auto_off` 1 s then on, expect an off report about 1 s later, then `clear_auto_off` and on,
expect it to stay on; the same on a `tuya_inching` string. Write them as rig steps in
`tests/integrations/zigbee2mqtt/rig/` only if a maintainer has the device; otherwise note them in the PR body.

## Implementation

Model: **sonnet** for the session and each step's implementer. The plan settles the classes, payloads and limits, and
unit tests pin each payload. No core change is expected (`own_calls_only` exists); if one turns up, stop and bring it
to Jason. Plan reviewer: opus. The PR touches the Labs flag (`labs(...)`), so its audit has an Opus auditor
(CLAUDE.md, Pull requests).
