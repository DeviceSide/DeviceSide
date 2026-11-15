# Tuya datapoint countdown on Zigbee2MQTT (v0.1.x)

**Target: v0.1.x, after v0.1.0.** Deferred from the device-classes plan's step 5 part 3 by its Decision 73
([plan](2026-11-14-device-classes.md)). Nothing here is built for v0.1.0.

## Coordination

Intent: serve `turn_on_for`, and for the first time `turn_off_for`, on the Tuya datapoint devices Zigbee2MQTT gives a
countdown in seconds, behind `experimental`, by the safe call pattern.
Touches: `custom_components/deviceside/integrations/zigbee2mqtt/` (`classes.py`, `turn_on_for.py`, a new
`turn_off_for.py`), its tests and bundle, `scripts/gen_features.py` (`NO_PATH`), `docs/integrations.md` (What can't
be done), README (regenerated). Per-class duration limits touch core, so an Opus audit.
Tests-with: a rig step file for the class, in `tests/integrations/zigbee2mqtt/rig/`, if a lab device joins.
Depends-on: v0.1.0 shipped; the device-classes plan's step 5 part 3 (converter A), whose class split and
duration-limit work this reuses.

## Why

- Today `tuya_mcu` is not yet supported on `turn_on_for`, with `harms` (Decisions 70 and 71): Z2M turns `on_time`
  into a plain On, and the device stays on. Z2M's own `countdown` would serve many of them.
- A datapoint countdown toggles the device when it reaches zero, unlike Zigbee's On-With-Timed-Off (0x42), so it can
  also give `turn_off_for`: send OFF, then a countdown that turns the device back on. Converter A's 0x42 can't
  (Decision 73), so this is the one Zigbee path to `turn_off_for`.

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
6. **Docs:** `NO_PATH` and What can't be done keep `turn_off_for` impossible for every non-datapoint Zigbee device
   and for Z2M groups; the card lists the class as Experimental on both actions.

## Open

- Whether a lost ON, or a device already off, leaves a toggle-type countdown turning it on at the end (research, §5):
  the pattern's report wait guards the first; a probe on one device should check the second before release.
- Whether DP 11 on FK-BV05 and ZVL-PRO is a live timer or a preset (research, §4).
- A lab device: none of the 54 is in the lab yet.
