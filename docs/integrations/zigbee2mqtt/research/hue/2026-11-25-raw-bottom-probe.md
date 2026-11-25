# Hue on Zigbee2MQTT: the raw bottom and Z2M's restore memory, rig probes (2026-11-25)

Rig probes of 2026-11-25, 12:19 to 12:28 local, for step 4 of
[the plan](../../../../plans/2026-11-25-brightness-floor.md) (Decision 8): what Z2M's restore-after-soft-off memory
does around step 3's raw bottom, and whether the raw lower to 0.4 % keeps the bulb at level 1. DeviceSide's
integration tree `899bb7f5a25c` (commit `8b7b7f9c`), as HA loaded it. Every value below is from the runs' captured
logs (HA's at DEBUG for `deviceside` and `mqtt`, which carry every `/set` publish, and Z2M's info lines, which carry
its state publishes) and their run reports.

## Setup

- Devices: the Hue white ambiance E27 of [step 2's probe](2026-11-25-brightness-floor-probe.md) (LTA009, firmware
  1.163.1), and a Hue White (LWA012), roamed from the Hue bridge to Zigbee2MQTT by the rig, DeviceSide class `hue`.
  The rig made a Z2M group of the two, both Hue lights, so the group goes raw (`RAW_BOTTOM`). The lab's Hue color
  bulb was unreachable on the Hue bridge, so it sat out. The same Z2M install as step 2's (2.14.3), not re-read.
- Two runs of probe step files, run uncommitted and then deleted; no test record was written. Each probe ran with
  the CT bulb's `hue_native_control` off (Z2M's default) and then on, set by the case. Brightness is read live
  (`deviceside.get_attributes`: `currentLevel` on a lit light, Z2M's held brightness on an off one), in percent.

## (a) A member soft-off, then a group raise lighting it, then a plain on

Option off. Jump: the member went back to its soft-off level.

| Time | What |
|---|---|
| 12:19:48.976 | HA sets the group `{"state":"ON","brightness":102}` (40 %) |
| 12:19:51.089 | HA turns the CT bulb off, `{"state":"OFF","transition":1.0}`; Z2M publishes it OFF, brightness 102 |
| 12:19:52.664 | HA turns the group off, plain |
| 12:19:55.247 | DeviceSide's raise from off: one raw groupcast to the group, `moveToLevelWithOnOff` level 1, `transtime` 0 |
| 12:19:55.251 | then the group's `{"state": "ON", "brightness": 254, "transition": 5.0}` through the converter |
| 12:20:05 | the CT bulb reads 100 % |
| 12:20:06.129 | HA's plain `light.turn_on` to the CT bulb: `{"state":"ON"}` |
| 12:20:06.242 | Z2M publishes the CT bulb at brightness 102; it reads 40.2 % at 12:20:08 and 12:20:09 |

**Control, no DeviceSide call** (second run): the same, with HA's plain `light.turn_on` of the group at brightness
254 (12:27:29.682) in place of the raise. The member read 100 %, then HA's plain on (12:27:33.475) brought it to
brightness 102 (12:27:33.624), 40.2 %. Z2M keeps the memory per device, and a group's set doesn't clear a member's,
with or without DeviceSide.

Option on: no jump. The raise (12:21:02.985) took the member to 100 %, and the plain on (12:21:13.763) left it at 254.

## (b) A raw lower to 0.4 %, then an off with a transition, then a plain on

**b1, the off before the end read-back,** option off. Jump: back to the level before the fade.

| Time | What |
|---|---|
| 12:20:12.035 | HA sets the CT bulb `{"state":"ON","brightness":76}` (30 %) |
| 12:20:13.209 | DeviceSide's lower: raw `moveToLevelWithOnOff` level 1, `transtime` 15; Z2M publishes no state |
| 12:20:15.185 | HA's `{"state":"OFF","transition":1.0}`, 2.0 s after; Z2M publishes OFF, brightness 76, at 12:20:15.241 |
| 12:20:15.736 | the end read-back: Z2M publishes OFF, brightness 1 |
| 12:20:18.252 | HA's plain `{"state":"ON"}`; Z2M publishes ON, brightness 76, at 12:20:18.301; it reads 29.9 % |

**b2, the off after the end read-back,** option off: 0.4 %, not the 0.8 % the source reading predicted, as the bulb
was already off. The raw lower at 12:20:25.076; at the end read-back, 12:20:27.615, Z2M published OFF, brightness 1,
before HA sent anything. The off with a transition (12:20:32.041) found Z2M's state OFF, so nothing was stored, and
the plain on (12:20:35.071) published ON, brightness 1: 0.4 %.

**Kept level, a plain off and on,** option off: 0.4 %, with the same caveat. The raw lower at 12:20:42.050 left Z2M
at OFF, brightness 1 (12:20:44.572); the plain off (12:20:48.947) and on (12:20:50.971) gave ON, brightness 1.

Option on, all three: 0.4 % on the plain on. In b1 (raw lower 12:21:20.826, off with a transition 12:21:22.809, plain
on 12:21:25.866), Z2M published ON, brightness 1. In b2 the raw lower (12:21:32.614) again left Z2M at OFF, brightness 1
(12:21:35.134), before any off.

## The raw lower to 0.4 % leaves the bulb off

Second run, option off. `lower_brightness` from 30 % to a 0.4 % limit: raw `moveToLevelWithOnOff` level 1,
`transtime` 15 (12:27:40.234). At the end read-back, 12:27:42.782, Z2M published OFF, brightness 1, and Home
Assistant showed the light off when the case checked. The level reads 0.4 % all the same, as an off light's brightness
is the one Z2M holds, so `lower_to_the_lowest_level`'s sample passes. The same in every raw lower above. Nobody
watched the lamp: what was read is the bulb's `onOff`, answering DeviceSide's `genOnOff` read.

`set_attributes` 0.4 % on the lit bulb, the same session: raw `moveToLevel` level 1, `transtime` 4,
`optionsMask`/`optionsOverride` 1 (12:27:50.838). Z2M published ON, brightness 1, at 12:27:51.502, and it stayed on
at 0.4 %. On ZHA, step 2's lower sent `move_to_level`, without On/Off, and the bulb held level 1 lit.

## Reading

- The bypass's `moveToLevelWithOnOff` to level 1 turns a Hue bulb off at the end of the fade. Level 1 is the
  bulb's lowest, and the likely mechanism is ZCL's rule for Level Control's "with On/Off" commands: a level that ends
  at the minimum sets OnOff off. That is the case `turnsOffAtBrightness1` steps around. The rule wasn't checked
  against the ZCL text here. The same level sent as `moveToLevel`, without On/Off, holds lit (`set_attributes`,
  and ZHA's lower).
- (a) is Z2M's own: its restore memory is per device, and a group's set doesn't clear a member's, so a member soft-off
  before a group change jumps to its old level on its next plain on. Plain HA group commands do the same. The group
  raise's raw bottom was one groupcast to the all-off group, not a per-member publish.
- (b1) comes from the raw command drawing no state: until the end read-back, Z2M holds the level from before the fade,
  so an off with a transition in that window, about the fade's length and 1 s more, stores that level. Before the
  bypass, the converter's publish moved Z2M's state to the end level at once (step 2's probe: brightness 2, 0.15 s
  after the publish).
- b2 and the kept-level check read 0.4 % only because the bulb was already off. Neither measured a lit bulb at level 1.
- With `hue_native_control` on, no probe jumped: Philips' converter kept no restore memory here.
