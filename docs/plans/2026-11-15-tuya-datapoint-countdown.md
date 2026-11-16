# Tuya datapoint countdown on Zigbee2MQTT (v0.1.x)

**Target: v0.1.x, after v0.1.0.** Deferred from the device-classes plan's step 5 part 3 by its Decision 73
([plan](2026-11-14-device-classes.md)). Nothing here is built for v0.1.0.

## Coordination

Intent: serve `turn_on_for`, and for the first time `turn_off_for`, on the Tuya datapoint devices Zigbee2MQTT gives a
countdown in seconds, behind `experimental`, by the safe call pattern; and probe whether 0x42's toggle gives Tuya ZCL
devices `turn_off_for` too (Open).
Touches: `custom_components/deviceside/integrations/zigbee2mqtt/` (`classes.py`, `turn_on_for.py`, a new
`turn_off_for.py`), its tests and bundle, `scripts/gen_features.py` (`NO_PATH`), `docs/integrations.md` (What can't
be done), README (regenerated). Per-class duration limits touch core, so an Opus audit.
Tests-with: a rig step file for the class, in `tests/integrations/zigbee2mqtt/rig/`, if a lab device joins.
Depends-on: v0.1.0 shipped; the device-classes plan's step 5 part 3 (converter A), whose class split and
duration-limit work this reuses.

## Why

- Today `tuya_mcu` is not yet supported on `turn_on_for`, with `harms` (Decisions 70 and 71): Z2M turns `on_time`
  into a plain On, and the device stays on. Z2M's own `countdown` would serve many of them.
- A datapoint countdown toggles the device when it reaches zero, unlike the spec's On-With-Timed-Off (0x42), which
  turns a device on, then off, so it can also give `turn_off_for`: send OFF, then a countdown that turns the device
  back on. It is plausible on Tuya Zigbee devices generally (Decision 73): the datapoint countdown, reachable on ZHA
  too as a raw 0xEF00 `dataRequest`, and possibly 0x42 itself on Tuya ZCL firmware, which varies (below, Open).
  Non-Tuya Zigbee devices have no call for it.

## Source

The definitions, the rule and the payloads: the datapoint research note,
[2026-11-14-tuya-datapoint-countdown.md](../integrations/zigbee2mqtt/research/2026-11-14-tuya-datapoint-countdown.md),
and the converter note's converter B,
[2026-11-14-tuya-countdown.md](../integrations/zigbee2mqtt/research/2026-11-14-tuya-countdown.md), §1. The class's
key, guard and exclusions: Decision 67, which stays as written.

## Design

1. **The class** (Decision 67): keyed on the call path, a definition whose countdown is a Tuya datapoint, not the
   `TS0601` model (Decision 34). It qualifies with a settable `countdown` (or `countdown_<x>`) in unit `s`, and an
   on/off `state` of the same suffix, paired by property name. About 54 definitions and 152 maker strings. Excluded:
   LYAI-14, ZBN-DJ-63, `TS0601_fan_switch`, `TS0601_smart_temperature_switch`, timers in minutes or hours, the enum
   timer, the garage opener, Manhot MH03 and Moes ZS-D. A Tuya datapoint device outside it keeps today's refusal.
   The expose doesn't tell converter A from B, so the rule also reads the identity (research, converter note §1).
2. **The safe call pattern** (Decision 67), for every countdown armed on this path: (1) send the state; (2) wait for
   the device to report it; (3) only then send the countdown, at most the expose's own `value_max`; (4) if the report
   doesn't come, arm nothing, and report that rather than `sent`.
   - `turn_on_for`: state ON, then the countdown.
   - `turn_off_for`: state OFF, then the countdown, which turns the device back on at zero.
3. **Payloads:** a single-endpoint device on its base topic; a multi-gang one with suffixed keys (`state_l1`,
   `countdown_l1`) or on `<device>/l1/set`, never unsuffixed keys on the base topic (research, §2). This is per
   endpoint, so it waits on, or extends, the multi-endpoint addressing the Z2M `internals.md` records as future work.
4. **Duration limits per class:** whole seconds, 1 to the expose's `value_max` (43,200 or 86,400).
5. **Level:** `experimental(...)` everywhere. A maker string is Verified only by its own record or manual row
   (Decision 35).
6. **Docs:** `NO_PATH` marks `turn_off_for` impossible only on Zigbee groups (and Matter); What can't be done says in
   prose that non-Tuya Zigbee devices have no call for it, as the blank cell can't. The card lists the class as
   Experimental on both actions.

## Open

- Whether a lost ON, or a device already off, leaves a toggle-type countdown turning it on at the end (research, §5):
  the pattern's report wait guards the first; a probe on one device should check the second before release.
- Whether DP 11 on FK-BV05 and ZVL-PRO is a live timer or a preset (research, §4).
- A lab device: none of the 54 is in the lab yet.
- **The 0x42 toggle, a probe question.** Tuya ZCL firmware may toggle on 0x42 from off, which would give converter A's
  devices `turn_off_for` without a datapoint: Z2M #22182's TS011F toggled after 150 s, from on or off
  ([converter note](../integrations/zigbee2mqtt/research/2026-11-14-tuya-countdown.md)), and the lab probe's
  `_TZ3000_typdpbpg` on ZHA switched on from off at the timer's end
  ([lab probe](../integrations/zigbee2mqtt/research/2026-11-14-lab-probe.md)). It varies by firmware:
  `_TZ3000_0zfrhq4i` ignores it from off. Probe, per maker string, OFF then 0x42 `{0, N, N}`: whether it turns on
  at N, and whether a later state set cancels it.
- **ZHA's route:** the datapoint countdown as a raw 0xEF00 `dataRequest`, if ZHA joins this plan.
- **Inching, a probe question** (device-classes plan, Decision 41). Tuya's inching (cluster `0xE000`, command `0xFB`,
  `setInchingSwitch`; [timed-on research](../integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md),
  §3, Tuya ZCL row) may give TS011F strings a working timed off where the countdown misbehaves. Probe, per maker
  string, `_TZ3000_gjnozsaz` included (Z2M #30493): whether it turns the plug off at N, whether it persists across
  calls (the research calls it a persistent setting), and whether a state set cancels it.
