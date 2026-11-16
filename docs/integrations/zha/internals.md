# ZHA internals

How the ZHA adapters address a target, what they send and read back, and what was measured on real hardware.
What a user sees is in [index.md](index.md) and isn't repeated here; what every integration shares is in
[internals.md](../../internals.md). Result and detail codes are in the code. Code comments cite the sections here.

## Addressing

Commands go through `zha.issue_zigbee_cluster_command` and `zha.issue_zigbee_group_command` (admin-only; Device
Side passes the caller's context). The unique ID is `{ieee}-{endpoint_id}`; a longer one on the same endpoint (a
quirk's extra entity) is `not_addressable`, so a timer can't land on the wrong entity. A ZHA group entity
(`{platform}_zha_group_0x{group_id:04x}`) expands to its members for results; commands use the group where noted.

## Modules

One section per adapter module, named after it.

### `classes`

What decides the wire call on ZHA, read from the source Home Assistant 2026.10.2 to 2026.10.4 pins (zha 2.3.1, its
zigpy 2.3.0, zha-quirks 2.3.0; links at those commits), 2026-11-14:

- **The quirk's cluster object carries every command.** `zha.issue_zigbee_cluster_command` looks up the endpoint's
  cluster, the one the device's quirk put there, and calls its command by name, with the params converted to the
  command's schema ([`Device.issue_cluster_command`](https://github.com/zigpy/zha/blob/0ea5e1adb01692b7014d6f77b8255787af899d36/zha/zigbee/device.py#L1421-L1461)). A quirk's cluster can
  override `command`; if it doesn't, zigpy serializes the standard ZCL frame.
- **`OnWithTimedOff` carries no units.** zigpy's schema is `on_off_control`, then `on_time` and `off_wait_time` as
  plain `uint16` ([general.py](https://github.com/zigpy/zigpy/blob/fb63170d520e42c77ecd73e9dfc3061f980fc20d/zigpy/zcl/clusters/general.py#L889-L896)), so DeviceSide's tenths (`100` for
  10 s) reach the device as the number `100`. Nothing on the way converts them; the firmware decides what the number
  means.
- **Tuya's ZCL quirks keep that frame.** zigpy matches `zhaquirks.tuya.ts011f_plug:Plug` by the model `TS011F` and
  the endpoint layout, never the `_TZ3000_…` string ([ts011f_plug.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/ts011f_plug.py#L43-L103)),
  and replaces the On/Off cluster with `TuyaZBOnOffAttributeCluster`, which adds attributes and no command
  ([tuya/\_\_init\_\_.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/__init__.py#L1038-L1047)). So the plug gets the frame a Hue bulb
  gets, and reads `on_time` as whole seconds: the lab's `_TZ3000_typdpbpg` counted `100` down once a second while
  off and switched on at 106 s, while Tuya's recipe (a plain On, then `0x42` with the seconds in both fields) ended
  with an off 10 s later ([lab probe](../zigbee2mqtt/research/2026-11-14-lab-probe.md), §2, C1 and C5). No quirk at
  that commit defines or rewrites `on_with_timed_off`. Other Tuya ZCL firmwares read the spec's `on_time` as seconds
  too (Z2M #22182 on two TS011F strings, #28914 on a TS0001:
  [tuya-countdown](../zigbee2mqtt/research/2026-11-14-tuya-countdown.md), §3); none of those reports is on the recipe.
- **A Tuya datapoint quirk answers it itself.** The TS0601 quirks' On/Off clusters (`zhaquirks.tuya.mcu`
  `TuyaOnOff`, the quirk builder's default `TuyaOnOffNM`, and the older `zhaquirks.tuya` `TuyaOnOff`) turn On and Off
  into datapoints and answer every other command with `UNSUP_CLUSTER_COMMAND`, sending nothing
  ([mcu/\_\_init\_\_.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/mcu/__init__.py#L387-L434),
  [tuya/\_\_init\_\_.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/__init__.py#L608-L658)). zha then raises, so `turn_on_for` fails
  after its `light.turn_on`, if it sent one. Reads of such a cluster answer from its cache, never the device
  ([`LocalDataCluster`](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/__init__.py#L125-L147)).
- **Sonoff's ZBMINIR2 quirk keeps the standard On/Off cluster** ([zbminir2.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/sonoff/zbminir2.py#L52-L84)),
  so firmware 1.1.0 and later, which honors `0x42` in tenths, gets the Hue bulbs' frame; 1.0.1 doesn't advertise
  the command ([research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §3, Sonoff row), so it
  would refuse it at once, which shows. No class of its own: it stays in `other`.
- **Sonoff's SWV valve quirk keeps it too** ([swv.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/sonoff/swv.py#L38-L72)), and the valve reads
  `on_time` as whole seconds (Z2M #27980, which Z2M fixed by dividing by 10:
  [research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §3, Sonoff row), so DeviceSide's tenths
  would keep it open ten times as long: `sonoff_swv`, not built yet, `harms`, as a call in seconds would serve it.
- **Which Tuya ZCL devices take seconds.** The reports and the probe cover plugs and switches only: TS011F, TS0001
  (Z2M #22182, #28914) and the models Z2M drives by Tuya's countdown (TS0001 to TS0004, TS0011, TS0726:
  [research](../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §3, Tuya ZCL row). Those are
  `tuya_countdown`. Tuya's other ZCL devices (bulbs such as TS0505B, dimmers, `_TYZB01_…` white labels, which Z2M
  drives with a third field layout) are `tuya_zcl`: nobody has probed whether they read the spec's tenths or seconds,
  so neither call is known safe, and `turn_on_for` refuses them, not built yet (`harms`).
- **A datapoint quirk answers the other actions too.** Its Level cluster turns a move into a datapoint and drops the
  transition ([mcu/\_\_init\_\_.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/mcu/__init__.py#L695-L770)), and its reads come from
  its cache, so no adapter's call reaches a `tuya_mcu` device as sent: not built yet on every action, with
  `harms` on `turn_on_for`.
- **Some datapoint devices carry ZCL-style strings.** A TS0601 quirk matches `_TZ3000_uim07oem`
  ([ts0601_switch.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/ts0601_switch.py#L88)), and the TS0049 valve `_TZ3210_0jxeoadc` gets the
  builder's datapoint On/Off ([tuya_valve.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/tuya_valve.py#L652-L663)), so the strings alone
  would send Tuya's recipe to a quirk that answers its `0x42` with `UNSUP_CLUSTER_COMMAND` after its plain On opened
  the valve. Only the quirk shows them.
- **The registry can hold a quirk's names, not the device's.** HA's ZHA writes the registry from zha's
  `manufacturer` and `model` ([device.py](https://github.com/zigpy/zha/blob/0ea5e1adb01692b7014d6f77b8255787af899d36/zha/zigbee/device.py#L513-L548): the Basic strings, or
  `unk_manufacturer` and `unk_model` when the interview couldn't read them), and a v2 quirk with a friendly name
  replaces both ([builder/device.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/builder/device.py#L53-L61)). No Tuya quirk sets one at that
  commit, and the lab's registry held the raw strings (Tested behavior), but one could, hiding `_TZ3000_…`. zigpy's
  device ([`Device.device`](https://github.com/zigpy/zha/blob/0ea5e1adb01692b7014d6f77b8255787af899d36/zha/zigbee/device.py#L465-L467))
  holds the strings a quirk leaves it: a v2 quirk leaves them; a v1 quirk's `replacement` can rewrite them
  (`BaseCustomDevice`'s `set_device_attr`,
  [device.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/device.py#L51-L60)),
  which no Tuya quirk does at that commit.
- **The strings and quirk are final once entities exist.** zigpy reads the Basic manufacturer and model in the
  interview ([device.py](https://github.com/zigpy/zigpy/blob/fb63170d520e42c77ecd73e9dfc3061f980fc20d/zigpy/device.py#L835-L853))
  and picks the quirk once, when the device is initialized
  ([application.py](https://github.com/zigpy/zigpy/blob/fb63170d520e42c77ecd73e9dfc3061f980fc20d/zigpy/application.py#L630-L668));
  ZHA makes the device's entities after that.

So two things decide the outcome. Where the quirk routes On/Off itself (Tuya's datapoint quirks), the quirk does, and
`tuya_mcu` keys on it: the module that defines the On/Off cluster's `command`. Everywhere else the frame is the
standard one and the firmware decides, so the class keys on the device's raw Zigbee manufacturer and model, read
from zigpy's device through the gateway, never the registry. Each family's rules are in its package
(`families/<family>/`), and the order between families in `families/__init__.py`.

### `turn_on_for`

`OnWithTimedOff` (cluster `0x0006`, command `0x42`, `on_off_control: 0`, `off_wait_time: 0`), after
`light.turn_on` when there are fields. Then OnOff (`0x0000`) and OnTime (`0x4001`) are read in one uncached
request: `confirmed` when on and OnTime is above 0, at most the request and no more than 3 s under it.

**Tuya's recipe, parked** (plan Decision 74). A Tuya countdown device (`tuya_countdown`) would take the recipe by
unicast: `light.turn_on` when there are fields, a plain `On`, then `OnWithTimedOff` with `on_time` and
`off_wait_time` both the duration in whole seconds, read back in seconds; OnTime reads 0 for about a second after the
call (C5: `0.1 | 1 | 0 | 10`, then `1.1 | 1 | 10 | 10`). It is the frame Z2M's converter A sends
(`tuya.tz.on_off_countdown`, [tuya-countdown](../zigbee2mqtt/research/2026-11-14-tuya-countdown.md), §1) and the lab
probe's C5. It was built and then taken out for v0.1.0's scope, not its units; until it returns, `turn_on_for`
refuses the Tuya classes as not built yet, with `harms`. `get_attributes` reads a `tuya_countdown` OnTime as
seconds.

A group gets one `light.turn_on` and one group `OnWithTimedOff` when the lights the call reaches are every device
endpoint in the group but the coordinator; per-member commands would start about 0.7 s apart across 8 lights.
Otherwise each light gets its own: a groupcast reaches every member, so a plug in a light group, which has a switch
entity and no light, or a member the call refused or flagged, would take the timer (zha's group light entity reaches
only its lights; [`Group.members`](https://github.com/zigpy/zha/blob/0ea5e1adb01692b7014d6f77b8255787af899d36/zha/zigbee/group.py#L190-L197) drops a member ZHA doesn't know, which zigpy's
group still holds, so a group with one isn't covered either). A group command gets no reply, so every member is still read back. A slow end device (the rig's
Sengled) can read `not_on` before it takes the group's `light.turn_on` (Tested behavior). A member's read can also
overtake the group `OnWithTimedOff`: on the rig (2026-11-13, house run), the LTA004 read on with no timer straight
after a groupcast with brightness, then went off 6.57 s after coming on, where the cases before it went off at 6.0 to
6.1 s; the timer had landed about 0.5 s after the group's `light.turn_on`. So a member that reads `not_on` or no
timer is read again every 0.5 s, up to 3 times, before it is reported `sent`.

### `set_attributes`

Commands go one after another: `brightness` as a percent of level 254 (`0` sends level 1), color temperature as
mireds clamped to the light's range, color as `MoveToColor`, or `MoveToHueAndSaturation` on a light without xy. A
color light without color temperature takes one as a color, as core does. `min_brightness`/`max_brightness` read
CurrentLevel live. Then, once every light's commands are sent and outside the concurrency slots, each light at least
one command reached gets `homeassistant.update_entity`, since ZHA never applies a color temperature report; ZHA skips
it while the light is transitioning (1.5 s after a plain off), so DeviceSide waits up to 3 s, and after a longer
off fade refreshes again when it ends. Models in `DROPS_WHILE_OFF` (`families/sengled/`) are refused. The wait reads zha's private
`entity_data.entity` and its `is_transitioning`; a zha release without them is logged once, and the refresh then
goes ahead without waiting.

### `get_attributes`

Uncached reads, one cluster at a time: OnOff and OnTime always, Level when the light dims, Color when it has a color
mode. Color is the active mode (EnhancedColorMode where present, else ColorMode). The timer counts only while the
light reads on, as a TS011F counts OnTime down while off.

### `fade`

- `raise_brightness`: `MoveToLevelWithOnOff`. A light that is off first gets `MoveToLevel` to 1 with
  `ExecuteIfOff` and no transition. A Hue bulb ignores that and fades from its stored level, so it is turned on at
  level 1 by Signify's `multiColor` (cluster `0xFC03`, as Z2M's `hue_native_control` sends), straight through
  zigpy, as ZHA has no action for it; the same admin check applies.
- `lower_brightness`: `MoveToLevel` to a limit; to 0 %, `MoveToLevelWithOnOff`, which leaves the bulb at level 1.
  1 s after the fade should end, OnOff is read and an off light gets `MoveToLevel` back to its starting level with
  `ExecuteIfOff`. A stop or a new brightness call cancels that restore.
- Saturation: `MoveToSaturation` to the end saturation on a light whose ColorCapabilities (read as for hue, below)
  report hue and saturation and that shows a color (`hs` or `xy`), as a `MoveToColor` fade's stop visibly jumps
  (Tested behavior). It carries no hue, so each bulb keeps its own and a group's members share one groupcast. A light
  without hue and saturation, or in color temperature (its stored hue may be stale, untested), gets `MoveToColor` to
  the xy of its current hue at the end saturation, one command each. Hue instead fades a room at the room's hue, as
  its `grouped_light` write carries one color.
- Hue: `EnhancedMoveHue` at `65535 / sweep_time` steps per second; a light without enhanced hue in
  ColorCapabilities (zigpy's cache, else one live read) gets `fields_dropped`, and a read that fails rejects the
  move with `error`.
- A hue move marks its lights as cycling before the send, so a cancel mid-send still leaves them to a later stop; the
  lights it failed for are unmarked after.

A transition longer than ZCL's 6553.4 s runs at that. The bulb reports brightness during a fade, never color, so
DeviceSide calls `homeassistant.update_entity` 1 s after a fade should end and straight after a stop; raw commands
leave ZHA's transition guard down, so the read is the bulb's.

ZHA can't tell a change from a remote or app from the bulb's own reports, so the remembered position can go stale.
To keep hold-to-dim instant, the brightness fade is sent first and CurrentLevel read just after; the read, timed at
the middle of its round trip, lies on the bulb's ramp, so DeviceSide fits the ramp's real start to it. A brightness
call the remembered value says is `at_limit` or `off` is replanned from Home Assistant's state.

A group gets one command when every light in it moves; otherwise, such as a soft off with a member off, each moving
member gets its own, since a group soft off would drop an off member's stored level. The bottom level and the
restore are always per member.

A failed command rejects only the lights it was for, each keeping the remembered position and soft off restore it
had; the rest fade on. A groupcast that fails rejects every member it was for. A member whose bottom level failed
gets no fade, and the rest get one command each, as a groupcast would reach it.

### `stop`

`stop`: `StopMoveStep` where a color move runs, then Level `Stop`, each sent per light (one groupcast where the
lights are a whole group). A light either command fails for is rejected (`admin_required`, else `error`) and keeps
its move, hue cycle and soft-off restore; the lights that halted record the halt and drop theirs.

## Tested behavior

Color fades, on a Philips Hue A60 (LCA016, firmware 1.164.2): `MoveToColor` runs linearly in the bulb's own hue and
saturation, not along a straight xy line, so a saturation fade toward white swings the hue (136° to 100° in 2.5 s of
a 9 s fade). `StopMoveStep` halts on that path, and the reads hold after it; the same on Zigbee2MQTT. Probe:
[research/2026-11-13-a60-color-fade-path.md](research/2026-11-13-a60-color-fade-path.md). Watched, the stop of that
saturation fade shows as a jump in saturation, on ZHA and Zigbee2MQTT, though the reads have none: the bulb renders
the fade unlike the state it reports
([research/2026-11-13-a60-stop-jump-watched.md](research/2026-11-13-a60-stop-jump-watched.md)). A `MoveToSaturation`
fade halted the same way looked closest to smooth, staying at its hue, with a small step back at the halt left as is;
halting the `MoveToColor` fade at its straight-line xy, as Hue does, also left a small step:
[research/2026-11-15-a60-stop-halt-probe.md](research/2026-11-15-a60-stop-halt-probe.md).

Timers, on a Philips Hue LTA004 (firmware `0x01001416`, Home Assistant 2026.10.2). Firmware decides this, so other
devices may differ.

- OnTime counts down in tenths (a 30 s timer read 290, 250, 200 and 99 at 1, 5, 10 and 20 s; off at 30.2 s) and
  reads 0 with no timer.
- A new timer replaces the old one, longer or shorter.
- `light.turn_on`, plain (`On`) or with brightness (`move_to_level_with_on_off`), leaves the timer running.
  `light.turn_off` clears it.
- Nothing ends a timer with the light left on: writing OnTime 0 (status `SUCCESS`), `OnWithTimedOff` with
  `on_time: 0`, or a 0.1 s timer each turned the bulb off within 0.3 s. Writing OnTime resets the time left (100
  with 15.6 s left: off 10 s later). With no timer running, writing 0 changes nothing.

Writes while off: the LTA004, LWA012, LTA009 and LCA016 store `MoveToLevel` and `MoveToColorTemp` with `ExecuteIfOff`, at any delay
0 to 2 s after a plain off, and drop them without it. A Sengled E11-G13 (firmware `0x00000009`) takes `MoveToLevel`
while on, but while off, with the override or without, jumps CurrentLevel to 255 and comes on at full.

Moves, on the LTA004: a Level `Stop` 3 s into a 6 s soft off from 200
held at 100 with the bulb on, and Home Assistant showed 100 from the bulb's report. A 4 s fade read its end level by
3.9 s; a 4 s soft off read off, at level 1, by 4.3 s. Group `MoveToLevelWithOnOff` and `Stop` act as the unicast
ones.

Groups (2026-10-27, the LTA004, a Sengled E11-G13 and a plug): a unicast `turn_on_for` takes about 0.23 s per member
(0.34 s with brightness), so under `max_concurrency` 2 the last of 8 lights starts 0.7 to 1 s after the first. A
group `OnWithTimedOff` returns in 0.02 s, zigpy's own success with no delivery feedback, and a member that refuses
the command (the Sengled, `UNSUP_CLUSTER_COMMAND` by unicast) misses it silently, so each member is read back.

Device strings, 2026-11-14 on Home Assistant 2026.10.4. Probe:
[lab-probe](../zigbee2mqtt/research/2026-11-14-lab-probe.md), §1.

- **The registry holds the raw Zigbee strings** for these devices (none has a quirk friendly name: `classes`), manufacturer and model, with `model_id` empty: a TS011F plug is
  `_TZ3000_typdpbpg` / `TS011F`, a Sengled `sengled` / `E11-G13`, Hue bulbs `Signify Netherlands B.V.` and their
  model ID (`LTA009`). `sw_version` is the Zigbee firmware in hex.
- **Beyond it, readable through `zcl.gateway`:** the TS011F has quirk `zhaquirks.tuya.ts011f_plug:Plug` (no
  `quirk_id`), `manufacturer_code` 4417, and the Tuya clusters `0xe000` and `0xe001` on endpoint 1. The Sengled
  (4448) and the Hue bulbs (4107) have no quirk.
- **A group's light entity resolves to the coordinator's device** (here `SONOFF` / `ZBDongle-E`); its members each
  resolve to their own.
- The TS011F's timer: shared [internals.md](../../internals.md), Tested behavior.

## Upstream defects

Workarounds the adapters carry for behavior upstream that could be fixed there. Only the issues our code already
cites have been checked upstream: search each tracker for duplicates before filing.

- **ZHA (zigpy/zha): color temperature attribute reports are never applied to the entity.** HA shows a stale
  color temperature after any change it didn't send. Workaround: `homeassistant.update_entity` after every write
  (`integrations/zha/set_attributes.py`) and uncached live reads in `get_attributes`. A plain state-sync bug,
  easy to reproduce: change the color temperature from a remote. Already tracked as
  [zigpy/zha#855](https://github.com/zigpy/zha/issues/855) (open; a maintainer agrees it should be fixed as
  brightness was, and a fix sits on the `zigpy-bot/light-color-reports` branch, no PR yet). Don't file a new issue.
- **zha-quirks: define Signify's `0xFC03` `multiColor` command on the Hue cluster,** so
  `zha.issue_zigbee_cluster_command` can send it. Workaround: straight to zigpy, re-implementing ZHA's admin
  check (`zcl.hue_turn_on`, `zcl.require_admin`). Additive quirk work; Z2M's `philips.ts` is prior art.
- **ZHA: `update_entity` does nothing while the transition flag is up,** and "on" reports are ignored for 1.5 s
  after `turn_off`. Workaround: poll the flag up to 3 s and refresh again after long fades
  (`TRANSITION_WAIT_S`, the late refresh). The guard is deliberate; pitch it narrowly: an explicit
  `update_entity` bypasses it.

Not worth filing:

- **Firmware:** the Sengled E11-G13 jumping to full. A vendor problem.
- **ZHA group commands give no delivery feedback.** That is how a Zigbee groupcast works.
