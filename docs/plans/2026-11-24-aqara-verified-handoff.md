# Handoff: Aqara bulb to Verified, then Documented by call pattern

2026-11-24. From the session that shipped #605 and #607. For the session that plans this goal; nothing here is decided.

## Jason's goal

1. Get the Aqara color bulb (Z2M; definition Aqara T2_E27, Zigbee model `lumi.light.agl003`, manufacturer string `Aqara`)
   Verified on DeviceSide for every action it supports.
2. Then a judgment call on which other devices can be Documented: in an `aqara` family, or more generally across vendors
   that share the call pattern (as #605 did for set_attributes/get_attributes on `other` in Labs).

Run `/plan` (built-in plan mode), interview Jason (AskUserQuestion; `/grilling` for dependent decisions), save the plan
in `docs/plans/` with a `## Coordination` section, `pr-draft <plan>`, then end with the implementing session's model and prompt.

## Where things stand (main at ae15b1b0 or later)

- #605: Z2M `other` takes set_attributes and get_attributes in Labs, lights only; get_attributes on `other` reads
  `genOnOff` for `onOff` alone (no `onTime`). Research: `docs/integrations/zigbee2mqtt/research/2026-11-24-other-brands-execute-if-off-and-reads.md`,
  `.../2026-11-24-other-brands-dimming.md` (dimming on `other` safe in Labs; suggests rewording `docs/internals.md` Shared's
  Zigbee 3.0 reason, not acted on, shared doc, repo maintainer).
- #607: `core/identifiers.py`; a 3-part HomeKit identifier had crashed Z2M's bridge cache at setup, leaving every non-Hue Z2M
  device Unplaced. Fixed; the bulb is now placed as `other`.
- Rig rerun 2026-11-24 23:29 (`lab_aqara`, restricted, Labs on in the rig HA): 17 pass / 16 fail / 28 skip, **no records
  written**: the profile has no group/group_color roles, so the rig kept the existing (Hue-based) records for
  lower/raise_brightness and set_attributes. Getting records for a single-bulb profile is a rig question (ha-rig repo).
  - Pass: brightness raise/lower, stop, every set_attributes case, most get_attributes.
  - not_built on `other`: turn_on_for, turn_off_for (timer), raise/lower_saturation, hue moves (fail at `mark_hue`:
    "returned no hue").
  - Device fact: given hs while off, stays `color_mode: xy`; Z2M reports `currentHue` UNSUPPORTED_ATTRIBUTE. Likely
    xy-only (no hue/saturation attributes), which bears on which actions it "supports" (hue/saturation may be no known
    method rather than not built: `docs/evidence.md`, memory: not-built vs can't).
  - Surprise, unexplained: one `TimeoutError('no genLevelCtrl reply')`: a while-off `moveToLevel` with
    optionsMask/Override 1 got no Zigbee reply in 10 s, in a setup step (likely a hue/saturation case), once. Root-cause
    or rule out before Verified (Evidence 4).
  - Report: `/var/folders/wk/kszxz30j6wd2vmmnd02c5bfc0000gn/T/deviceside-rig/rig-run-2026-11-24-232946.md` (+ .ha.log, .z2m.log).

## Questions the plan has to settle (interview)

- What "every action it supports" means for an xy-only bulb: hue/saturation via xy conversion, or refused with a reason?
- Timer actions on it: own off (DeviceSide's soft timer, not built) vs the bulb's `onTime` (does it run genOnOff
  onWithTimedOff? probe first, Evidence 2).
- An `aqara` family (Z2M maintainers; `Family.maintainers`; families/__init__.py rule order) vs placing the bulb in an
  existing class; and ZHA too, or Z2M only?
- Records: how the rig writes them for a single-bulb profile (ha-rig change) vs adding a group of Aqara bulbs.
- Documented by shared call pattern: which calls (ZCL moveToLevel/ExecuteIfOff writes, reads) and which vendors' evidence
  suffices (Evidence 5: proof follows the call and the class). Levels and the release gate: `docs/evidence.md`.

## Rules to keep in mind

- Public repo: no household entity IDs, device names, MACs or hostnames (the rig's entity is named after the bulb; keep it
  out of commits and docs).
- Restricted rig profile: each run needs Jason's yes for `DEVICE_SIDE_RIG_RESTRICTED=1`.
- Reading the rig live works through ha-rig's HAClient (admin token from ha-rig's `.env.rig`), run with
  `in-dir /Users/jason/projects/ha/ha-rig uv run python -I <script>`; read-only probes only without Jason's yes.
