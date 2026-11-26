# What decides the wire call on ZHA: quirks and the frame

Read 2026-11-14 from the source Home Assistant 2026.10.2 to 2026.10.4 pins (zha 2.3.1, its zigpy 2.3.0, zha-quirks
2.3.0; links at those commits). Moved here from [ZHA internals](../internals.md#classes), whose `classes` table
sums it up, on 2026-11-26; the text is as it stood.

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
  with an off 10 s later ([lab probe](../../zigbee2mqtt/research/2026-11-14-lab-probe.md), §2, C1 and C5). No quirk at
  that commit defines or rewrites `on_with_timed_off`. Other Tuya ZCL firmwares read the spec's `on_time` as seconds
  too (Z2M #22182 on two TS011F strings, #28914 on a TS0001:
  [tuya-countdown](../../zigbee2mqtt/research/2026-11-14-tuya-countdown.md), §3); none of those reports is on the recipe.
- **A Tuya datapoint quirk answers it itself.** The TS0601 quirks' On/Off clusters (`zhaquirks.tuya.mcu`
  `TuyaOnOff`, the quirk builder's default `TuyaOnOffNM`, and the older `zhaquirks.tuya` `TuyaOnOff`) turn On and Off
  into datapoints and answer every other command with `UNSUP_CLUSTER_COMMAND`, sending nothing
  ([mcu/\_\_init\_\_.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/mcu/__init__.py#L387-L434),
  [tuya/\_\_init\_\_.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/__init__.py#L608-L658)). zha then raises, so `turn_on_for` fails
  after its `light.turn_on`, if it sent one. Reads of such a cluster answer from its cache, never the device
  ([`LocalDataCluster`](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/__init__.py#L125-L147)).
- **Sonoff's ZBMINIR2 quirk keeps the standard On/Off cluster** ([zbminir2.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/sonoff/zbminir2.py#L52-L84)),
  so firmware 1.1.0 and later, which honors `0x42` in tenths, gets the Hue bulbs' frame; 1.0.1 doesn't advertise
  the command ([research](../../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §3, Sonoff row), so it
  would refuse it at once, which shows. No class of its own: it stays in `other`.
- **Sonoff's SWV valve quirk keeps it too** ([swv.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/sonoff/swv.py#L38-L72)), and the valve reads
  `on_time` as whole seconds (Z2M #27980, which Z2M fixed by dividing by 10:
  [research](../../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §3, Sonoff row), so DeviceSide's tenths
  would keep it open ten times as long: `sonoff_swv`, not built yet, harmed by today's call, as a call in seconds
  would serve it.
- **Which Tuya ZCL devices take seconds.** The reports and the probe cover plugs and switches only: TS011F, TS0001
  (Z2M #22182, #28914) and the models Z2M drives by Tuya's countdown (TS0001 to TS0004, TS0011, TS0726:
  [research](../../zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §3, Tuya ZCL row). Those are
  `tuya_countdown`. Tuya's other ZCL devices (bulbs such as TS0505B, dimmers, `_TYZB01_…` white labels, which Z2M
  drives with a third field layout) are `tuya_zcl`: nobody has probed whether they read the spec's tenths or seconds,
  so neither call is known safe, and `turn_on_for` refuses them, not built yet, harmed by today's call.
- **A datapoint quirk answers the other actions too.** Its Level cluster turns a move into a datapoint and drops the
  transition ([mcu/\_\_init\_\_.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/mcu/__init__.py#L695-L770)), and its reads come from
  its cache, so no adapter's call reaches a `tuya_mcu` device as sent: not built yet on every action, with an
  entry on `turn_on_for`, whose failure harms.
- **Some datapoint devices carry ZCL-style strings.** A TS0601 quirk matches `_TZ3000_uim07oem`
  ([ts0601_switch.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/ts0601_switch.py#L88)), and the TS0049 valve `_TZ3210_0jxeoadc` gets the
  builder's datapoint On/Off ([tuya_valve.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/tuya/tuya_valve.py#L652-L663)), so the strings alone
  would send Tuya's recipe to a quirk that answers its `0x42` with `UNSUP_CLUSTER_COMMAND` after its plain On opened
  the valve. Only the quirk shows them.
- **The registry can hold a quirk's names, not the device's.** HA's ZHA writes the registry from zha's
  `manufacturer` and `model` ([device.py](https://github.com/zigpy/zha/blob/0ea5e1adb01692b7014d6f77b8255787af899d36/zha/zigbee/device.py#L513-L548): the Basic strings, or
  `unk_manufacturer` and `unk_model` when the interview couldn't read them), and a v2 quirk with a friendly name
  replaces both ([builder/device.py](https://github.com/zigpy/zha-device-handlers/blob/d6fcec59eff9f63f154723500be9378be926d927/zhaquirks/builder/device.py#L53-L61)). No Tuya quirk sets one at that
  commit, and the lab's registry held the raw strings ([Tested behavior](../internals.md#tested-behavior)), but one could, hiding `_TZ3000_…`. zigpy's
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
