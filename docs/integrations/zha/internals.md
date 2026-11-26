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

zha sends every command through the cluster object the device's quirk put on the endpoint, and zigpy serializes the
standard ZCL frame unless that cluster overrides the command; `OnWithTimedOff`'s `on_time` goes out as a plain number,
so the firmware decides its unit. Read from the source Home Assistant 2026.10.2 to 2026.10.4 pins (zha 2.3.1, zigpy
2.3.0, zha-quirks 2.3.0), 2026-11-14: [research](research/2026-11-26-quirk-call-path.md).

| Devices | What reaches them | Class |
|---|---|---|
| Hue, IKEA and other brands, with no quirk or one keeping the standard On/Off cluster | The standard frame; the firmware decides | By brand: the device's raw Zigbee manufacturer and model |
| Tuya's countdown plugs and switches: TS011F, TS0001 to TS0004, TS0011, TS0726 | The standard frame (the TS011F quirk adds attributes, no command), read as whole seconds | `tuya_countdown` |
| Tuya's other ZCL devices: bulbs such as TS0505B, dimmers, `_TYZB01_…` white labels | The standard frame, in units nobody has probed | `tuya_zcl` |
| Tuya datapoint devices: TS0601, and ZCL-style strings a datapoint quirk takes (`_TZ3000_uim07oem`, the TS0049 valve `_TZ3210_0jxeoadc`) | The quirk turns On and Off into datapoints and answers every other command, `0x42` included, with `UNSUP_CLUSTER_COMMAND`, sending nothing: `turn_on_for` fails after its `light.turn_on`, and Tuya's recipe would fail after its plain On had opened the TS0049 valve. Its Level cluster drops a move's transition, and its reads come from its cache | `tuya_mcu`, keyed on the quirk: the module that defines the On/Off cluster's `command` |
| Sonoff ZBMINIR2 | The standard frame: 1.1.0 and later honor `0x42` in tenths; 1.0.1 doesn't advertise it, so it refuses it at once | `other` |
| Sonoff SWV valve | The standard frame, read as whole seconds, so ten times as long | `sonoff_swv` |

The strings and quirk are final once entities exist: zigpy reads the Basic manufacturer and model in the interview and
picks the quirk once, when the device is initialized, before ZHA makes its entities. The registry can hold a v2
quirk's friendly name in place of the device's strings, so the class reads the raw strings from zigpy's device through
the gateway, never the registry. Each family's rules are in its package (`families/<family>/`), and the order between
families in `families/__init__.py`.

### `turn_on_for`

`OnWithTimedOff` (cluster `0x0006`, command `0x42`, `on_off_control: 0`, `off_wait_time: 0`), after
`light.turn_on` when there are fields. Then OnOff (`0x0000`) and OnTime (`0x4001`) are read in one uncached
request: `confirmed` when on and OnTime is above 0, at most the request and no more than 3 s under it.

Tuya's countdown plugs and switches would take Tuya's own recipe, which was built and parked:
[Tuya's recipe on ZHA](../../deferred.md#tuyas-recipe-on-zha).

A group gets one `light.turn_on` and one group `OnWithTimedOff` when the lights the call reaches are every device
endpoint in the group but the coordinator; per-member commands would start about 0.7 s apart across 8 lights. Otherwise
each light gets its own: a groupcast reaches every member, so a plug in a light group, which has a switch entity and no
light, or a member the call refused or flagged, would take the timer (zha's group light entity reaches only its lights;
[`Group.members`](https://github.com/zigpy/zha/blob/0ea5e1adb01692b7014d6f77b8255787af899d36/zha/zigbee/group.py#L190-L197)
drops a member ZHA doesn't know, which zigpy's group still holds, so a group with one isn't covered either). A group
command gets no reply, so every member is still read back, and a slow member's read can come before it takes the group's
`light.turn_on` or `OnWithTimedOff` (Tested behavior). So a member that reads `not_on` or no timer is read again every
0.5 s, up to 3 times, before it is reported `sent`.

### `set_attributes`

Commands go one after another: `brightness` as a percent of level 254 (`0` sends level 1), color temperature as
mireds clamped to the light's range, color as `MoveToColor`, or `MoveToHueAndSaturation` on a light without xy. A
color light without color temperature takes one as a color, as core does. `min_brightness`/`max_brightness` read
CurrentLevel live. Then, once every light's commands are sent and outside the concurrency slots, each light at least
one command reached gets `homeassistant.update_entity`, since ZHA never applies a color temperature report; ZHA skips
it while the light is transitioning (1.5 s after a plain off), so DeviceSide waits up to 3 s, and after a longer
off fade refreshes again when it ends. Models in `zcl.DROPS_WHILE_OFF` are refused. The wait reads zha's private
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

A transition longer than ZCL carries is clamped, with `clamped_to` (`docs/internals.md`, Fades). The bulb reports
brightness during a fade, never color, so DeviceSide calls `homeassistant.update_entity` 1 s after a fade should end and
straight after a stop; raw commands leave ZHA's transition guard down, so the read is the bulb's.

The remembered position, a group's one command or per-member ones, and failures: `fade.py`'s docstring.

### `stop`

`stop`: `StopMoveStep` where a color move runs, then Level `Stop`, each sent per light (one groupcast where the
lights are a whole group). A light either command fails for is rejected (`admin_required`, else `error`) and keeps
its move, hue cycle and soft-off restore; the lights that halted record the halt and drop theirs.

## Tested behavior

Color fades, on a Philips Hue A60 (LCA016, firmware 1.164.2): `MoveToColor` runs in the bulb's own hue and saturation,
so a saturation fade toward white swings the hue, and its stop shows as a jump though the reads have none; a
`MoveToSaturation` fade halted by `StopMoveStep` looked closest to smooth
([path](research/2026-11-13-a60-color-fade-path.md), [watched](research/2026-11-13-a60-stop-jump-watched.md),
[halt](research/2026-11-15-a60-stop-halt-probe.md)).

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

Writes while off: the LTA004, LWA012, LTA009 and LCA016 store `MoveToLevel` and `MoveToColorTemp` with `ExecuteIfOff`,
at any delay 0 to 2 s after a plain off, and drop them without it. A Sengled E11-G13 (firmware `0x00000009`) takes
`MoveToLevel` while on, but while off, with the override or without, jumps CurrentLevel to 255 and comes on at full.

Moves, on the LTA004: a Level `Stop` 3 s into a 6 s soft off from 200
held at 100 with the bulb on, and Home Assistant showed 100 from the bulb's report. A 4 s fade read its end level by
3.9 s; a 4 s soft off read off, at level 1, by 4.3 s. Group `MoveToLevelWithOnOff` and `Stop` act as the unicast
ones.

A member's read can overtake the group `OnWithTimedOff` (rig, 2026-11-13): the LTA004 read on with no timer straight
after a groupcast with brightness, then went off 6.57 s after coming on, where the cases before it went off at 6.0 to
6.1 s; the timer had landed about 0.5 s after the group's `light.turn_on`. A slow end device (the Sengled) can read
`not_on` before it takes the group's `light.turn_on`.

Groups (2026-10-27, the LTA004, a Sengled E11-G13 and a plug): a unicast `turn_on_for` takes about 0.23 s per member
(0.34 s with brightness), so under `max_concurrency` 2 the last of 8 lights starts 0.7 to 1 s after the first. A
group `OnWithTimedOff` returns in 0.02 s, zigpy's own success with no delivery feedback, and a member that refuses
the command (the Sengled, `UNSUP_CLUSTER_COMMAND` by unicast) misses it silently, so each member is read back.

Device strings, 2026-11-14 on Home Assistant 2026.10.4. Probe:
[lab-probe](../zigbee2mqtt/research/2026-11-14-lab-probe.md), §1.

- **The registry holds the raw Zigbee strings** for these devices (none has a quirk friendly name: `classes`),
  manufacturer and model, with `model_id` empty: a TS011F plug is `_TZ3000_typdpbpg` / `TS011F`, a Sengled `sengled` /
  `E11-G13`, Hue bulbs `Signify Netherlands B.V.` and their model ID (`LTA009`). `sw_version` is the Zigbee firmware in
  hex.
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
