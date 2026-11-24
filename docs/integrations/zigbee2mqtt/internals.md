# Zigbee2MQTT internals

How the Zigbee2MQTT adapters address a target, what they send and read back, and what was measured on real hardware.
What a user sees is in [index.md](index.md) and isn't repeated here; what every integration shares is in
[internals.md](../../internals.md). Result and detail codes are in the code. Code comments cite the sections here.

## Addressing

Only devices Z2M registered through MQTT discovery are found: the device carries the identifier
`("mqtt", "zigbee2mqtt_<address>")`.

- **Devices** use the IEEE address: topic `zigbee2mqtt/<ieee>/set`. Z2M's `resolveEntity` matches the IEEE-keyed
  `devices` map before `friendly_name`, so a rename doesn't break it.
- **Groups** have address `<encoded base topic>_<group ID>`, the base topic as character codes with no separator
  (`1221051039810110150109113116116` for `zigbee2mqtt`; `getEncodedBaseTopic` in Z2M's
  `lib/extension/homeassistant.ts`), and topic `zigbee2mqtt/<group ID>/set`. `resolveEntity` falls back to the
  ID-keyed `groups` map, so a rename doesn't break it either, but a device whose friendly name is that number wins.
  Members come from `zigbee2mqtt/bridge/groups`, features from `zigbee2mqtt/bridge/devices`, and each entity's
  options from Z2M's settings (`bridge/info`). All three are held for the entry's life (`bridge_cache.py`):
  subscribed once MQTT is up, kept as Z2M republishes them (devices and groups on a device or group change, settings
  on every settings change and on start; Tested behavior), and read fresh only while nothing has arrived since the
  last connect. Options DeviceSide sets are written through to the held settings once Z2M confirms them, until its
  next `bridge/info`.
- **The base topic is per bridge, read from HA's registries, so any base topic and several instances on one broker
  work** ([research](research/2026-11-24-base-topics.md)). Z2M links each device and group to its bridge (`via_device`)
  and gives every bridge entity the unique_id `bridge_<coordinator ieee>_<object_id>_<base topic>`, the base topic
  verbatim (spaces and `/` included; #575's was `'    zigbee2mqtt'`). A target's base is that suffix on its device's
  `via_device_id` bridge, disabled bridge entities included (three of the eight object_ids are disabled by default).
  Its topics, bridge cache, restore journal and `Address` all carry it, as two instances can both have group 7. A
  group's encoded base must match its bridge's, else it is refused. A target with no bridge or no bridge entity is
  `not_addressable` (a DEBUG line says so); no default base topic is guessed, as a wrong one reaches nothing silently.
  Verified live on one instance with the default base; a custom base and several instances rest on upstream source
  (2.14.3) and unit tests, unprobed live.
- **A renamed base topic.** HA keeps the old bridge entities, with the old base in their unique_ids, until they are
  removed, so the bridge then names two bases. DeviceSide can't tell which is live, so that instance is
  `not_addressable` until the stale entities are removed; a DEBUG line (`addressing.py`) names it. Unprobed: from
  Z2M's source, not seen on a rename.
- **Restore journal on a rename.** An owed restore on a base that is then renamed stays owed and unpaid; rare, so
  nothing prunes it.
- **Multi-endpoint devices.** DeviceSide's set and get topics name the device alone, with unsuffixed keys
  (`state`), so Z2M sends the call to the device's default endpoint: the definition's `default`, else its first
  (`endpoint()` in Z2M's [`lib/model/device.ts`](https://github.com/Koenkk/zigbee2mqtt/blob/2.6.0/lib/model/device.ts),
  called from `lib/extension/publish.ts`). Another endpoint needs `zigbee2mqtt/<device>/<endpoint>/set` or a
  suffixed key (`state_l2`), which DeviceSide doesn't send. `bridge/groups` lists each member as `{ieee_address,
  endpoint}`, the endpoint by number, so a group can hold gang 2 of a two-gang alone. The endpoint can be matched to
  its entity: since Z2M 2.6.0 `bridge/devices` names each endpoint (`endpoints.<number>.name`, the definition's
  `l1`; `publishDevices` in [`lib/extension/bridge.ts`](https://github.com/Koenkk/zigbee2mqtt/blob/2.6.0/lib/extension/bridge.ts),
  absent in 2.5.1), and Z2M's discovery gives that entity unique_id `<ieee>_<domain>_<name>_<base topic>` (object_id
  `light_l1`, `lib/extension/homeassistant.ts`). Matching it is no use until the call can reach that endpoint, which
  also needs the endpoint's suffixed state keys read back. So a device target is addressed only when it is its
  device's unsuffixed state entity: Z2M names a `switch`/`light` expose with no endpoint's entity `<domain>` (unique_id
  `<ieee>_<domain>_zigbee2mqtt`, `${ID}_${object_id}_${base_topic}` in `lib/extension/homeassistant.ts`), the entity
  defined by the unsuffixed `state` key DeviceSide sends and reads, so call and entity agree whichever endpoint is the
  default. Every other entity in the domain is suffixed: a gang is `<domain>_<endpoint>` (`switch_l1`), and every
  writable `binary` expose is a `switch_<name>` (a plug's child lock, `config` category; a presence sensor's
  indicator; a radar's toggles, uncategorized), disabled or not. A count of the device's entities in the domain
  refused every TS011F plug for its child lock (rig run B, 2026-11-16). The rule is argued, not tested, for a
  device with an unsuffixed entity beside suffixed gangs, none of which is in hand: it addresses the unsuffixed one.
  Such a device target is never addressed on its own:
  - **Targeted itself** (named, or by area, label or `group.*`), every such light or switch, and every config switch,
    is refused as `not_addressable` by every Z2M action (`addressing.not_addressable`, which each adapter's
    `supports()` calls), a gang's first too: the default endpoint is the definition's (`default`, else the device's first endpoint), which
    HA's registry doesn't show, and such a device publishes its state under suffixed keys (`state_l1`), which no
    read here takes. A `switch_as_x` light on the device is none of this.
  - **As a group's member**, `members.py` lists a device by its unsuffixed state entity, addressable, else (a gang) by its first entity, not addressable (`Target.addressable`): its
    class counts; a group that falls back skips it as `not_addressable`; `member_lights` leaves it out (logged at
    DEBUG). Fade, stop and set attributes plan from every member's state while the groupcast still reaches that
    endpoint, so they refuse a group with such an available member as `not_addressable`; get attributes averages the
    others, and refuses a group with no other available light. A groupcast-only action (`turn_on_for`) reaches the
    endpoint the group holds, so it is unaffected.

  The fix that addresses each endpoint, its topic named by the Z2M 2.6.0+ endpoint names, is future work
  ([TODO](../../../TODO.md)).

## Modules

One section per adapter module, named after it.

### `classes`

The class rules read the registry device (Z2M's vendor and definition) and, for a device the bridge cache's
`bridge/devices` lists, its Zigbee `manufacturer` and `model_id` there, and its definition's `model` and top-level
expose names, indexed by IEEE once per payload (Tested behavior: the registry holds no Zigbee strings). The rules,
each family's are in its package (`families/<family>/`), the order between families in `families/__init__.py`, and
the registry fallback's limit in the `classes.py` docstring.

Which adapters send a Level command to a light that is off, as a Sengled E11-G13 jumps to full on `MoveToLevel`
while off on ZHA ([ZHA internals](../zha/internals.md), Tested behavior). Read from the code, 2026-11-14; nothing
probed on Z2M:

- `set_attributes`: `MoveToLevel` with `ExecuteIfOff`, then its kept-level publish,
  `{"state": null, "brightness", "transition"}`, a `MoveToLevel` without it. The E11-G13 jumped on both on ZHA.
- `raise_brightness` from off: `{"state": "ON", "brightness": 1, "transition": 0}`, which Z2M sends as
  `moveToLevelWithOnOff`, then the fade, the same.
- `turn_on_for` with brightness: Home Assistant's `light.turn_on`, `{"state": "ON", "brightness"}`, also
  `moveToLevelWithOnOff`.
- `lower_brightness`, the hue and saturation ramps and `stop` send no Level command to an off light.

`moveToLevelWithOnOff` from off is untested on the Sengled. The `sengled` family holds no scope, so no feature is
built for it, until a Sengled run.

### `color_modes`

The Home Assistant override is set to `xy`, `hs` and, where present, `color_temp`, on lights
exposing both `color_xy` and `color_hs`, and on groups whose members all qualify. Z2M re-announces at once and
Home Assistant keeps the entity. Rerun at setup and on every device or group announcement, reading Z2M's settings
each time. Z2M can't delete an override (`null` strips the key from the announcement instead), so opting out
writes back the modes Z2M announces by itself, wherever the value is still DeviceSide's. Z2M declined to
announce both by default, as some lights handle mixed modes badly
([#33025](https://github.com/Koenkk/zigbee2mqtt/issues/33025)).

### `native_control`

`hue_native_control` makes Z2M send on, brightness, color and color temperature as one Philips command
rather than ZCL ones. Each action that needs it one way declares it (`NEED` in `families/hue/`; `native_control.py`
holds it there): on for a
`turn_on_for` with a color or color temperature (a Hue bulb, manufacturer `Philips`, lights in the new color and
keeps the timer); off for a brightness fade (native, a long raise runs about 2.3x faster than its transition, and
a soft off reports `onOff: 0` at once); off for a saturation fade too (native, Philips' converter turns a hueless
color to xy, so it would run as `MoveToColor` and jump at a stop). Other actions leave it alone. Where the
setting differs, it's set (Z2M's settings read on each call, up to 5 s for Z2M), the command published, and the
user's value written back after Z2M's next state publish for the target (1 s cap). The action returns once its
command is out; the write-back runs after it, and a `turn_on_for` waits for any pending one on its target before
its timer, its own or an earlier action's. Z2M reads a command's options as it takes it
(`lib/extension/publish.ts`), so a fade already sent runs on unchanged. One lock per device or group holds from the
set to the restore, so the next action that sets it waits for the write-back. A group uses its own options, not its
members', so it's set on the group when any member is a Hue bulb. A failed set or restore logs a warning, and the
command goes out anyway.

### `restore_journal`

The journal (`restore_journal.py`, HA storage `deviceside.zigbee2mqtt_restore_journal`) keeps the
user's value owed, by device or group, from just before the set's request goes out until Z2M confirms it written
back, so a restart or a failed restore can't leave the option flipped for good. An earlier entry is never
replaced: it holds the user's own value, where a later set may start from a flipped one. A set Z2M refused strikes
its entry. Every write-back writes the owed value, not the opposite of the action's need, and an action on an
address with a value still owed writes it back after its own publish even when its need already matched.
Each time `bridge/state` says online (its retained message at startup included, and after a Z2M that was offline
comes back), the replay pays what's owed: for each entry, under the same per-address lock the actions take, it
writes the value only if the option still holds the flipped one (one the user set back in Z2M's UI is left), and
strikes it once Z2M has it. An entry an action paid while the replay waited for its lock is skipped. One replay
runs at a time; an online that arrives during it runs it once more after, since its failures may date from Z2M
going down. An entry that fails again stays owed, for the next online, the next start or the next action on the
address. A malformed entry on disk is dropped with a warning; the rest replay.

### `read`

`filtered_cache` gets `deviceside_read` appended. Z2M deep-merges a read's answer into the cached state that
every later message carries, so an unfiltered answer would look fresh forever. If it can't be set, the read
raises.

### `turn_on_for`

Publishes `{"state": "ON", "on_time": <s>}`; Z2M sends `OnWithTimedOff` (`on_time` to 0.1 s; max 6553.4 s). With
fields, `light.turn_on` goes first, and the timer waits for Z2M's state publish on `zigbee2mqtt/<friendly name>`
(up to 5 s). Sent straight after, Z2M would publish the light's state from before the fields landed, which Home
Assistant keeps, and the two would contend on the mesh, delaying the timer by seconds.

Z2M publishes no state for a timed command (the `on_time` branch of `on_off` in zigbee-herdsman-converters returns
none) and turns reporting off for Hue bulbs. So DeviceSide publishes `{"state": ""}` to the get topic 1 s after
the start (without fields only), and at the end + 1 s and end + max(5 s, 2 % of the duration), for a slow bulb
clock. A new call replaces pending reads. Attribute reporting isn't used instead: it would need setting up on every
bulb, and Z2M turned it off for Hue on purpose. A group gets one publish and one groupcast read; Z2M shows it off
once every member is.

**Tuya's countdown** (converter A, plan step 5 part 3): a TS011F plug in a `tuya_countdown` class gets one publish,
`{"state": "ON", "countdown": N}`, N whole seconds from 1 to 43200 (`COUNTDOWN_LIMITS` in `families/tuya/countdown.py`; core rounds and clamps, and
reports either in `clamped_to`). No `on_time` (it has no converter there, Tested behavior) and no state reads: the plug
reports its state at expiry (probe P1, P2, P6, P7), and the time left can't be read, so the result is `sent`. A Z2M
group's call carries `on_time`, so a group with such a plug falls back to its members (`AdapterScope.own_calls`). A
plug Z2M exposes as a switch is the group's stand-in (`members._stand_in`), which no light entity addresses, so the
fallback skips it (`not_addressable`).

- **What Z2M sends.** `tuya.tz.on_off_countdown` (ZHC
  [`src/lib/tuya.ts#L3351-L3407`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/lib/tuya.ts#L3351-L3407),
  the same in 26.125.0, the lab's, and 26.131.0, the research pin) awaits `genOnOff` `on`, then awaits 0x42
  `{ctrlbits: 0, ontime: N, offwaittime: N}`, in that order ("on/off/toggle cancels onWithTimedOff"); it publishes
  `state: ON, countdown: N`.
- **The harm the order prevents.** 0x42 alone on an off plug toggles it on at N, and it stays on (probe P1b). The On's
  `await` rejects when herdsman can't deliver it (`Endpoint.zclCommand` rethrows a failed send,
  [`endpoint.ts`](https://github.com/Koenkk/zigbee-herdsman/blob/199c2f222a2b63c5c341af0c1bceda56845d34e0/src/controller/model/endpoint.ts#L1196-L1212),
  read 2026-11-15; `command` doesn't check the reply's status), so the converter throws before 0x42: a lost On sends
  nothing more, and Z2M logs the set as failed (`Publish 'set' 'state' … failed`), which `set_check` makes `rejected`.
  So no state check goes before or after the publish. What stays: an On that reached the plug but whose delivery failed,
  or a 0x42 that failed after the On was delivered, leaves it on with no timer; Z2M logs the set as failed and the call
  answers `rejected` (raising `targets_failed`), unless the bridge cache isn't live, when `set_check` is off and the
  call answers `sent`; and a button press between the two frames (milliseconds) would put the toggle on an off plug.
- **The class rule** reads `bridge/devices`' definition: model `TS011F`, a top-level expose of property `countdown` with
  no `endpoint` (a multi-gang one exposes one per endpoint: ZHC 26.131.0's `withEndpoint` keeps the name `countdown` and
  sets `property` `countdown_l1` and `endpoint` `l1`, so it isn't matched), and a definition other than the datapoint
  `ZOT60` ([research](research/2026-11-14-tuya-countdown.md), §1). Before `bridge/devices` lists the plug, the registry
  places it in `tuya_ts011f`, Unplaced, refused as `class_unknown`.

### `set_attributes`

Z2M's generic `command` payload, one per field. A color goes as xy, or hue and saturation on a light without xy.
Z2M publishes no state after a raw command, so each written cluster is read back live from each light, which also
updates Z2M's and Home Assistant's state. Level and color temperature are compared (`not_stored` if they differ);
color isn't, as the bulb clamps it to its gamut. A group is one groupcast per field, then every member is read.
`min_brightness`/`max_brightness` alone clamp each member from its own level, so each gets its own commands; an off
light is clamped from the brightness Z2M holds.

### `get_attributes`

Z2M's generic read, `{"read": {"cluster", "attributes", "state_property": "deviceside_read"}}`, one cluster at a
time, answered on the state topic:

- `genOnOff` (`onOff`, `onTime` in tenths): the timer.
- `genLevelCtrl` (`currentLevel`), only when the light is on. An off light's brightness is Z2M's, from the state the
  `genOnOff` answer carries: after an off with a transition the bulb holds 0.4 % while Z2M keeps the level it
  restores, a Hue bulb's own fade dims it for about a second after a plain off, and reading it would overwrite
  Z2M's kept level.
- `lightingColorCtrl`: `colorMode`, then only the attributes of the light's own modes, since one missing attribute
  fails the whole read.

A failed read raises at once when Z2M logs it on `zigbee2mqtt/bridge/logging`, else after 5 s. A group reads its
members in turn: averages over the lit ones (all, when all are off), and a `timer` only when every lit member has
one, the longest.

### `fade`

- `raise_brightness`: `{"state": "ON", "brightness", "transition"}`. An off bulb keeps its level and would fade up
  from it, so it first gets `{"state": "ON", "brightness": 1, "transition": 0}` (one publish to an all-off group,
  else per off member).
- `lower_brightness` to 0 %: `{"state": "OFF", "transition"}`, Z2M's soft off.
- Saturation: `{"color": {"saturation"}, "transition"}` with `hue_native_control` held off (`native_control`):
  zigbee-herdsman-converters' `light_color` sends a color with only a saturation as `moveToSaturation` with `transtime`
  on a light whose definition has `supportsHueAndSaturation` (any that exposes `color_hs`, as the A60's
  `philips.m.light` does with `modes: ["xy", "hs"]`), as a `MoveToSaturation` fade's stop doesn't jump (Tested
  behavior). With the option on, Philips' `light` converter turns any color to xy, so a hueless one doesn't go out as
  `moveToSaturation`. No hue rides in the payload, so each bulb keeps its own and a group is one publish. A light in
  color temperature (its stored hue may be stale, untested) makes the payload `{"color": {"hue", "saturation"}}`, the
  light's current hue, which goes out as `moveToHueAndSaturation`. Source, `Koenkk/zigbee-herdsman-converters`
  `f368dcd1`: `src/converters/toZigbee.ts` (`light_color`), `src/lib/philips.ts` (`light`, `hue_native_control`),
  `src/lib/modernExtend.ts` (`light`: `meta.supportsHueAndSaturation`).
- A brightness or saturation fade's `transition` is at most the longest ZCL transition (`docs/internals.md`, Fades),
  with `clamped_to` when a longer one is cut; the prediction matches.
- Hue: `hue_move` at `254 / sweep_time` steps per second (ZCL allows 1 to 254).

### `stop`

`stop`: `brightness_move: stop`, `hue_move: stop` for a running hue cycle, and a raw `stopMoveStep` for a
saturation fade, since `saturation_move: stop` halts the attribute and lets the xy fade drift on. Each is its own
publish, color first: Z2M reads back about 0.7 s after a brightness stop before sending the next key.

A soft off of ours is halted by `brightness_move: stop` alone: `lower_brightness` turns `hue_native_control` off for
its publish (`native_control`), so the soft off runs as a ZCL transition, which a ZCL stop ends. Z2M reports `OFF`
from the start of a soft off, so HA shows the light off until Z2M's read-back after the stop. Lab probe, LTA009 on
Z2M 2.14.3, a 10 s soft off from full stopped 3.2 s in: the bulb held `currentLevel` 175 for 4 s on the stop alone,
where the linear prediction was 172; HA showed `on` 0.59 s after the stop, at Z2M's stale 254 for 40 ms, then 175.
The pin this replaced (on at the predicted brightness) made `on` immediate but jumped the bulb to the prediction, a
flicker seen by eye.

- **Rare case:** the `hue_native_control` set fails or times out (MQTT or Z2M slow or down; `native_control` logs
  "Couldn't set Zigbee2MQTT's hue_native_control to ..." and sends the command anyway). The soft off then goes out as
  Philips' own command, which `brightness_move: stop` doesn't end, so the light fades on to off after a stop.
- **How often:** no field data (no telemetry). 85 lab rig logs, 2026-11-08 to 13, on one Z2M 2.14.3, hold no
  set-failed and no restore-failed warning (172 sets visible, in the debug-logged runs only).
- **Fix if it bites:** restore the pin, `{"state": "ON", "brightness", "transition": 0}` at the predicted brightness
  after the stop, but only for a soft off whose native-control set failed (`native_control` reports it; the stop
  picks those lights out). `6710d79` pinned every soft off, from when the stop didn't end the Philips command;
  #302 made native control per action, and #407 dropped the pin.

### `set_check`

Z2M reports a set it couldn't send only on `bridge/logging`, at error level:
`Publish 'set' '<key>' to '<friendly name>' failed: '<error>'`, then goes on to the message's next key and publishes
the message's state after the last (`lib/extension/publish.ts`). So a key's failure line comes before its message's
state. raise, lower, stop and turn_on_for settle after their publishes until each entity published to has a state
publish or a failure line, else 2 s past its last publish; a failure line makes the target `rejected`, with the status
it names (`busy`) or `send_failed`. set_attributes checks without the settle. The settle never delays a publish.
`hue_move`, a raw `command` and `on_time` draw no state, so a publish of one waits only 0.25 s, a groupcast's BUSY:
waiting the 2 s answered raise_hue 2 s late, and a script that waited, then stopped, ran the hue 2 s on (rig run
2026-11-13: +92° on a 3 s raise, expected +54°). A unicast's BUSY on them answers `sent`.

### `color_refresh`

Z2M publishes a fade's end value at once and reads back within a second of a brightness or hue stop. Once a fade has
run, DeviceSide gets `{"state": "", "brightness": ""}`, in case a mid-fade `get_attributes` overwrote the end
value. A saturation stop is raw, and after an xy stop Z2M's read-back carries its cached end-point x/y, so Device
Side gets `{"color": ""}` 1 s after a saturation stop and at the end of a saturation fade. Z2M reads a group's stop
back from its first member only, so these reads go to each member. After a hue or saturation command the bulb is in
hs mode; Home Assistant accepts that only with the color-modes option on.

## Tested behavior

Measured 2026-10-28 on Z2M 2.14.2 with Hue bulbs (a CT bulb and the A60), Home Assistant 2026.10.2.

- **Color-mode override.** It deep-merges into the device's options, and Z2M republishes the discovery message at
  once, with no restart; Home Assistant's entity keeps its entity ID and shows `color_temp`, `hs` and `xy`. A
  group's options behave the same. A `null` can't remove it: `supported_color_modes: null` deletes the key from the
  announcement, `light: null` drops the light from discovery, and `homeassistant: null` the whole device. With it,
  after `hue_move` and `hue_move: stop` Home Assistant takes Z2M's `hs` state, with no "Invalid color mode" in its
  log. With Hue native control on, HA's `hs_color`, `xy_color`, `rgb_color` and `color_temp_kelvin` each land on
  the A60 on cue with no flicker (watched by eye); HA sends `color: {h, s}` for hs and RGB, `{x, y}` for xy and
  `color_temp` for a temperature. Its rig case, `keeps_and_reads_hs_while_off`, rides in
  [`get_attributes.json`](test-records/get_attributes.json). Turning the option off is unit-tested only: the rig can't
  cleanly remove the override the option writes.
- **Stops, by eye** (a 10 s fade halted 3 s in). Brightness and hue stops freeze cleanly. Every color temperature
  stop jumps, whichever command halts it, the Hue bridge's own included. With brightness and color temperature in
  one fade, a brightness stop leaves the color temperature fading on to its end. `saturation_move: stop` lets an xy
  fade drift on for about 3 s; a raw `stopMoveStep` holds it.
- **bridge/info is republished on every settings change** (measured 2026-11-10 on Z2M 2.14.3, Home Assistant
  2026.10.4), to a subscriber that stays subscribed: after an options request over MQTT, for a device and for a
  group; after a change in Z2M's frontend; and after a Z2M restart, 0.02 s after `bridge/state` goes online, with the
  values kept. On an options request it arrives 0.03 to 0.10 s after the request and microseconds before the reply
  (seven group flips). The reply's `data.to` holds the entity's options after the write, without `friendly_name`.
- **Saturation fade stops.** The wire call is the same as on ZHA, so the A60's ZHA evidence carries over: halted by
  `StopMoveStep`, a `MoveToSaturation` fade looked closest to smooth and kept its hue, where an xy (`MoveToColor`) fade
  jumped at the stop
  ([zha research](../zha/research/2026-11-15-a60-stop-halt-probe.md)). Watched through Zigbee2MQTT on the same bulb
  (rig run 2026-11-16): the same, no jump and no drift, with a slight step back in saturation at the stop, as on ZHA.
  Left as is: it would need firmware tuning.
- **After an xy stop,** Z2M's read-back carries its cached end-point x/y, not where the bulb halted; a
  `{"color": ""}` get publishes the halted x/y.

Device strings and timers, 2026-11-14 on Z2M 2.14.3 (ZHC 26.125.0), Home Assistant 2026.10.4. Probe:
[research/2026-11-14-lab-probe.md](research/2026-11-14-lab-probe.md).

- **The registry holds Z2M's definition, not the Zigbee strings.** A TS011F plug registers as manufacturer `Tuya`,
  model `Smart plug (with power monitoring)`, `model_id` `TS011F_plug_1`; its Zigbee model `TS011F` and manufacturer
  `_TZ3000_…` are only in `bridge/devices`, with the `countdown` expose. A Sengled E11-G13 registers as `Sengled`,
  `Element classic (A19)`, `model_id` `E11-G13`, and `sw_version` is Z2M's own version. A group registers as
  `Zigbee2MQTT` / `Group`, and its members each resolve to a device.
- **`TS011F_plug_1` has no `on_time` converter:** `{"state": "ON", "on_time": 10}` logs `No converter available for
  'on_time'` and turns the plug on with no timer. Tuya's own recipe and `countdown` work: shared
  [internals.md](../../internals.md), Tested behavior.
- **A Sengled E11-G13 ignores `0x42` silently** (ZHA rejects it, [ZHA internals](../zha/internals.md)): in tenths
  or whole seconds, from off or after a plain On, Z2M logs it invoked and the bulb doesn't change state. It has no
  `onTime` or `offWaitTime` (`UNSUPPORTED_ATTRIBUTE`). So `{"state": "ON", "on_time": 10}`, which the light
  converter sends as `0x42` alone, leaves it off.

Tuya's countdown, 2026-11-15 on the lab TS011F (`_TZ3000_0zfrhq4i`, `TS011F_plug_1`, build `0122052017`), Z2M 2.14.3
(ZHC 26.125.0), Home Assistant 2026.10.4. Probe:
[research/2026-11-15-tuya-countdown-probe.md](research/2026-11-15-tuya-countdown-probe.md).

- **The countdown toggles at expiry.** From on, the plug ends off (P1); from off, 0x42 alone leaves it off and turns
  it on at N, and it stays on (P1b).
- **A new countdown replaces the running one** (P2), and an off, `countdown: 0` or a local button toggle cancels it
  (P3 to P5).
- **The time left can't be read:** `/get` and the plug's reports carry the value last set (P6).
- **Bounds:** 1 and 43200 s reach the plug; Z2M refuses 43201 before sending anything, `state` included (P7).

## Upstream defects

Workarounds the adapters carry for behavior upstream that could be fixed there. Only the issues our code already
cites have been checked upstream: search each tracker for duplicates before filing.

- **zigbee-herdsman-converters: `saturation_move: stop` doesn't halt a hue/saturation `color` fade; it drifts on
  for about 3 s.** The stop key doesn't match the command that started the fade (`hue_move: stop` does halt a
  hue cycle cleanly). The converter should send `stopMoveStep` (0x47), which halts every color move. Workaround:
  a raw `stopMoveStep` (`integrations/zigbee2mqtt/stop.py`). A one-line converter fix with a by-eye repro; the
  Hue bulbs honoring it is observed, not guaranteed by ZCL. Whether it needs `hue_native_control` is untested.
- **zigbee-herdsman-converters: `on_off` with `on_time` publishes no state.** The `on_time` branch returns
  nothing, unlike the others. Workaround: scheduled `{"state": ""}` reads at start + 1 s, end + 1 s and end +
  max(5 s, 2 %). Fix: return `{state: "ON"}` as the plain branch does.
- **Zigbee2MQTT: after an xy stop, the read-back publishes the cached end-point x/y,** not where the bulb halted.
  Workaround: a `{"color": ""}` get 1 s after a saturation stop. Fix: re-read `currentX`/`currentY` (or drop the
  optimistic value) on a color stop.
- **Zigbee2MQTT: a group stop is read back from its first member only;** the others keep the optimistic end
  value. Workaround: a read per member. Per-member reads on large groups cost mesh traffic, so expect discussion.
- **Zigbee2MQTT: a `read` answer with `state_property` is deep-merged into the cached state forever,** so every
  later state message carries it. Workaround: `deviceside_read` appended to each device's `filtered_cache`.
  Fix: a non-persisting read, or `state_property` keys kept out of the cache. They may answer "use
  `filtered_cache`".
- **zigbee-herdsman (Ember adapter): a groupcast the coordinator refuses with BUSY isn't retried.**
  `sendZclFrameToGroup` makes one `ezsp.send` (multicast) and throws on any status but success, while a unicast
  retries BUSY up to `QUEUE_MAX_SEND_ATTEMPTS` (3), 500 ms apart (`src/adapter/ember/adapter/emberAdapter.ts`).
  Seen on the house rig 2026-11-11: Z2M logged `[ZCL GROUP groupId=<id>] Failed to send with status=BUSY.` about
  20 ms after a group `brightness` set, and the group never moved. Workaround: none for the send; `set_check` reports
  the target failed. Fix: retry a group send on BUSY as a unicast is. Not yet filed.
- **Zigbee2MQTT: announce both xy and hs.** Declined in #33025, hence the `homeassistant.light` override
  (`integrations/zigbee2mqtt/color_modes.py`). The remaining angle is narrower: opt-in per device, or only for
  Signify bulbs known to handle mixed modes.
- **Zigbee2MQTT discovery identifiers.** A device's identifier lacks the base topic and a group's encodes it as
  unseparated character codes; a device whose friendly name is a bare number shadows the group with that ID in
  `resolveEntity`. Real but edge cases.
- **zigbee-herdsman-converters (candidate, not probed): `brightness_move: stop` leaves a color temperature fade
  running to its end** when brightness and color temperature fade together. Possibly the same gap as the `saturation_move: stop` one above,
  fixed by a `stopMoveStep`; untested. Probe it on a Hue CT bulb before filing, and file it separately: a color
  temperature stop that jumps whichever command halts it is a different problem.
