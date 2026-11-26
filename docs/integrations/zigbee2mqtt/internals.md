# Zigbee2MQTT internals

How the Zigbee2MQTT adapters address a target, what they send and read back, and what was measured on real hardware.
What a user sees is in [index.md](index.md) and isn't repeated here; what every integration shares is in
[internals.md](../../internals.md). Result and detail codes are in the code. Code comments cite the sections here.

## Addressing

Only devices Z2M registered through MQTT discovery are found: the device carries the identifier
`("mqtt", "zigbee2mqtt_<address>")`.

**Devices** use the IEEE address: topic `<base topic>/<ieee>/set`. Z2M's `resolveEntity` matches the IEEE-keyed
`devices` map before `friendly_name`, so a rename doesn't break it.

**Groups** have address `<encoded base topic>_<group ID>`, the base topic as character codes with no separator
(`1221051039810110150109113116116` for `zigbee2mqtt`; `getEncodedBaseTopic` in Z2M's
`lib/extension/homeassistant.ts`), and topic `<base topic>/<group ID>/set`. `resolveEntity` falls back to the
ID-keyed `groups` map, so a rename doesn't break it either, but a device whose friendly name is that number wins. Z2M
discovers one entity per member `expose` type (light, switch, lock, cover; `GROUP_SUPPORTED_TYPES` and `getConfigs`
in `lib/extension/homeassistant.ts`), so a group of switches is `switch.<group>`, and a mixed group has a light and a
switch. A group entity has no endpoint name, `object_id` `switch` (or `light`) and `unique_id`
`<group ID>_switch_<base>`; a groupcast from either entity reaches every member, whatever its domain.

Members come from `<base topic>/bridge/groups`, features from `<base topic>/bridge/devices`, and each entity's
options from Z2M's settings (`bridge/info`). All three are held for the entry's life (`bridge_cache.py`): subscribed
once MQTT is up, kept as Z2M republishes them (devices and groups on a device or group change, settings on every
settings change and on start; Tested behavior), and read fresh only while nothing has arrived since the last connect.
Options DeviceSide sets are written through to the held settings once Z2M confirms them, until its next `bridge/info`.

**The base topic** is per bridge, read from HA's registries, so any base topic and several instances on one broker
work ([research](research/2026-11-24-base-topics.md)). Z2M links each device and group to its bridge (`via_device`)
and gives every bridge entity the unique_id `bridge_<coordinator ieee>_<object_id>_<base topic>`, the base topic
verbatim (spaces and `/` included). A target's base is that suffix on its device's `via_device_id` bridge, disabled
bridge entities included (three of the eight object_ids are disabled by default). Its topics, bridge cache, restore
journal and `Address` all carry it, as two instances can both have group 7. A group's encoded base must match its
bridge's, else it is refused. A target with no bridge or no bridge entity is `not_addressable` (a DEBUG line says
so); no default base topic is guessed, as a wrong one reaches nothing silently. Run live on one instance with the
default base; a custom base and several instances rest on upstream source (2.14.3) and unit tests.

- **A renamed base topic.** Z2M puts the base in every unique_id, so a rename leaves HA with the old entities
  (unavailable) beside new `_2` ones, and the bridge names two bases. DeviceSide can't tell which is live, so that
  instance is `not_addressable` until the old entities are removed; a DEBUG line says so. From the code and a user's
  report, not run on a rename.
- **Restore journal on a rename.** An owed restore on a base that is then renamed stays owed and unpaid; rare, so
  nothing prunes it.

**Multi-endpoint devices.** DeviceSide's set and get topics name the device alone, with unsuffixed keys (`state`), so
Z2M sends the call to the device's default endpoint, and no read here takes a gang's suffixed state keys. So a device
target is addressed only when it is the device's unsuffixed state entity (`addressing.not_addressable`, which each
adapter's `supports()` calls; why, from Z2M's source: [research](research/2026-11-26-multi-endpoint-addressing.md)):

| Entity in the domain | Example (unique_id) | Addressed |
|---|---|---|
| The unsuffixed state entity of a `switch` or `light` expose with no endpoint | `<ieee>_<domain>_<base topic>` (`${ID}_${object_id}_${base_topic}` in `lib/extension/homeassistant.ts`) | Yes |
| A gang | `<ieee>_<domain>_<endpoint>_<base topic>` (`switch_l1`) | No: `not_addressable`, the first gang too |
| A writable `binary` expose | `switch_<name>`: a plug's child lock (`config` category), a presence sensor's indicator, a radar's toggles | No: `not_addressable`, disabled or not |
| A `switch_as_x` light on the device | | Served as the switch it wraps |

As a group's member, `members.py` lists such a device by its first entity, not addressable (`Target.addressable`):
its class counts, and `member_lights` leaves it out. A group can hold one gang alone, and its groupcast reaches it:

| Action on a group with such an available member | Result |
|---|---|
| Fade, stop, set attributes | `not_addressable`: they plan from every member's state |
| Get attributes | Averages the other lights; `not_addressable` with no other available light |
| `turn_on_for` (groupcast only) | Unaffected |
| Any fallback to members | Skips it as `not_addressable` |

Addressing each endpoint is deferred: [per-endpoint addressing](../../deferred.md#per-endpoint-addressing-on-zigbee2mqtt).

## Modules

One section per adapter module, named after it.

### `classes`

The class rules read the registry device (Z2M's vendor and definition) and, for a device the bridge cache's
`bridge/devices` lists, its Zigbee `manufacturer` and `model_id` there, and its definition's `model` and top-level
expose names, indexed by IEEE once per payload (Tested behavior: the registry holds no Zigbee strings). Each family's
rules are in its package (`families/<family>/`), the order between families in `families/__init__.py`, and the
registry fallback's limit in the `classes.py` docstring. A device identifier is read by its first two parts
(`core/identifiers.py`).

### `standard_lights`

The table the `standard_light` class keys on (`classes.py`; the rule is last in `families/__init__.py`, after every
family's, so a family keeps its own lights). Evidence: [the converter survey](../../research/2026-11-25-z2m-converter-survey.md).

Membership, the table's layout (`zigbee/standard_lights.py`, read by any Zigbee integration) and the bump each RC
opens are in the docstrings of `scripts/zhc_table.py` and `zigbee/standard_lights.py`; [the standard lights
page](standard-lights.md) is rendered from the table.

- **The option fields.** ZHC's own light converters send `optionsMask` and `optionsOverride` 0/0; DeviceSide's
  `set_attributes` builds a raw `command` with 1/1 (ExecuteIfOff), and `get_attributes` a raw `read`, which no
  light flag touches. So those two aren't on Z2M's usage. They qualify as every known failure is visible to the
  caller: a light that rejects the option fields answers MALFORMED_COMMAND, which raises; a write that doesn't land
  fails the read-back (`not_stored`); an attribute the light lacks fails the read (UNSUPPORTED_ATTRIBUTE). The one
  silent case, `disableDefaultResponse`, keeps a definition out.

### `color_modes`

Z2M announces only one of a full-color light's two color modes, usually XY, so Home Assistant ignores its
hue-saturation (HS) updates and keeps the old color after a hue or saturation change, a Hue gradient scene, a remote
or a power cut ([Koenkk/zigbee2mqtt#28757](https://github.com/Koenkk/zigbee2mqtt/issues/28757)).

The Home Assistant override is set to `xy`, `hs` and, where present, `color_temp`, on lights
exposing both `color_xy` and `color_hs`, and on groups whose members all qualify. Z2M re-announces at once and
Home Assistant keeps the entity. Rerun at setup and on every device or group announcement, reading Z2M's settings
each time. Z2M can't delete an override (`null` strips the key from the announcement instead), so opting out
writes back the modes Z2M announces by itself, wherever the value is still DeviceSide's. Z2M declined to
announce both by default, as some lights handle mixed modes badly
([#33025](https://github.com/Koenkk/zigbee2mqtt/issues/33025)).

### `native_control`

`hue_native_control` makes Z2M send on, brightness, color and color temperature as one Philips command rather than ZCL
ones. Which actions need it which way, and why, is `NEED` in `families/hue/`; the set, the publish, the per-target
lock and the write-back are in `native_control.py`'s docstring.

### `restore_journal`

The journal keeps the user's `hue_native_control` value owed, by device or group, until Z2M confirms it written back,
so a restart or a failed restore can't leave the option flipped for good; an earlier entry is never replaced. Its
rules and replay: `restore_journal.py`'s docstring.

### `read`

`filtered_cache` gets `deviceside_read` appended. Z2M deep-merges a read's answer into the cached state that
every later message carries, so an unfiltered answer would look fresh forever. If it can't be set, the read
raises.

### `turn_on_for`

Publishes `{"state": "ON", "on_time": <s>}`; Z2M sends `OnWithTimedOff` (`on_time` to 0.1 s; max 6553.4 s). With
fields, `light.turn_on` goes first, and the timer waits for Z2M's state publish on `<base topic>/<friendly name>`
(up to 5 s). Sent straight after, Z2M would publish the light's state from before the fields landed, which Home
Assistant keeps, and the two would contend on the mesh, delaying the timer by seconds.

Z2M publishes no state for a timed command (the `on_time` branch of `on_off` in zigbee-herdsman-converters returns
none) and turns reporting off for Hue bulbs. So DeviceSide publishes `{"state": ""}` to the get topic 1 s after
the start (without fields only), and at the end + 1 s and end + max(5 s, 2 % of the duration), for a slow bulb
clock. A new call replaces pending reads. Attribute reporting isn't used instead: it would need setting up on every
bulb, and Z2M turned it off for Hue on purpose. A group gets one publish and one groupcast read; Z2M shows it off
once every member is.

**Tuya's countdown** (converter A): a TS011F plug in a `tuya_countdown` class gets one publish,
`{"state": "ON", "countdown": N}`, N whole seconds from 1 to 43200 (`COUNTDOWN_LIMITS` in `families/tuya/countdown.py`; core rounds and clamps, and
reports either in `clamped_to`). No `on_time` (it has no converter there, Tested behavior) and no state reads: the plug
reports its state at expiry (probe P1, P2, P6, P7), and the time left can't be read, so the result is `sent`. A Z2M
group's call carries `on_time`, so a group with such a plug falls back to its members (`AdapterScope.own_calls`). A
plug Z2M exposes as a switch is the group's stand-in (`members._stand_in`), which no light entity addresses, so the
fallback skips it (`not_addressable`).

- **The order.** Converter A (`tuya.tz.on_off_countdown`) awaits `genOnOff` `on`, then 0x42
  `{ctrlbits: 0, ontime: N, offwaittime: N}`. 0x42 alone on an off plug toggles it on at N for good (probe P1b), and a
  lost On throws before 0x42 and Z2M logs the set failed, which `set_check` makes `rejected`, so no state check goes
  before or after the publish. An On delivered but reported failed, or a 0x42 lost after it, leaves the plug on with no
  timer, answered `rejected` (`sent` when the bridge cache isn't live); a button press in the milliseconds between
  the frames would put the toggle on an off plug. Source walk:
  [research](research/2026-11-14-tuya-countdown.md), §1.
- **The class rule** reads `bridge/devices`' definition: model `TS011F`, a top-level `countdown` expose with no
  `endpoint` (a multi-gang one's is `countdown_l1`), and a definition other than the datapoint `ZOT60`. Before
  `bridge/devices` lists the plug, the registry places it in `tuya_ts011f`, Unplaced, refused as `class_unknown`.

**Tuya's datapoint countdown** (converter B): a device in a `tuya_datapoint` class gets one publish,
`{"state": "ON", "countdown": N}`, after any light fields: [`turn_off_for`](#turn_off_for) gives the call and its
evidence. A Z2M group can't carry it, so a group with one falls back to its members.

### `turn_off_for`

Serves only its classes' own calls (`AdapterScope.own_calls_only`, [design](../../design.md)): Tuya's datapoint
countdown, below. Every other class is refused as `not_built` with no entry, and a target not yet placed (no class, or
the registry fallback's) as `class_unknown`. `native_groups=False`: a Z2M group's set never reaches a datapoint
(`tz.datapoints` throws "Not supported for groups"), so a group falls back to its members. `confirmable=False`.

**Tuya's datapoint countdown** (`families/tuya/datapoint.py`, converter B; turn_on_for's call on the same classes):
one publish to the set topic, `{"state": "OFF", "countdown": N}` (turn_on_for: `"ON"`), N whole seconds from 1 to
the class's limit, the definition's `countdown` expose `value_max` (`DATAPOINT_DEFINITIONS`, a class per limit as
core clamps by class: 43,200, 86,400 or 7,210 s; core rounds and clamps, and reports either in `clamped_to`). On
turn_on_for, light fields go first by `light.turn_on`, waiting for Z2M's state (`light_turn_on.py`), then the
countdown publish, which carries `state` again and no light fields. No reads: the time left isn't served, so the
result is `sent`, or `rejected` by `set_check`. Evidence: Z2M 2.14.3 and the ZHC it ships, v26.125.0, read
2026-11-24 ([research](research/2026-11-24-tuya-datapoint-call.md)); no datapoint device probed.

- **The order.** `tz.datapoints` sends the payload's keys in order, awaiting each, so a lost `state` throws before
  `countdown` goes out and `set_check` answers `rejected`. Its state publish is Z2M's own optimistic echo, so a wait
  for a report would have no signal: one publish, as for converter A. What stays is converter A's: a device switched
  with no timer, answered `rejected`, or a local toggle between the frames.
- **GL-SPI-206P** sends the on/off datapoint twice; a lost first one with a second that lands arms the countdown while
  `set_check` answers `rejected`. **Dimmers** skip the state datapoint when a payload holds `brightness`, which the
  countdown publish never does. **D5Z** publishes `countdown: 0` on every state change; nothing reads it.
- **The class rule** reads `bridge/devices`' definition: its `model` in `DATAPOINT_DEFINITIONS` and a top-level
  `countdown` expose with no endpoint, the single-endpoint guard. The rules run before `tuya_ts011f` (the ZOT60 is a
  TS011F) and `tuya_mcu`. Until `bridge/devices` lists the device it is Unplaced, refused as `class_unknown`. D1Z and
  SFD02-Z_2 are newer than the ZHC Z2M 2.14.3 ships, so match nothing on it.

**Cancelling** follows Tuya's General Countdown guide, written for its Wi-Fi and Bluetooth lamp panels; that these
Zigbee devices follow it is an inference, which Z2M's own description of the setting, "Toggle the device after a set
duration", agrees with ([research](research/2026-11-24-tuya-datapoint-call.md), §2).

Source walk, the toggle and the definitions checked: [research](research/2026-11-24-tuya-datapoint-call.md).

### `set_auto_off` and `clear_auto_off`

Persistent auto-off, "inching", one publish to the set topic, by Z2M's composite `inching_control_set`. They serve only
their classes' own calls (`AdapterScope.own_calls_only`): the Sonoff and Tuya inching classes. Every other class is
refused as `not_built`, and a target not yet placed as `class_unknown`. `native_groups=False`, so a Z2M group falls
back to its members. `confirmable=False`: the result is `sent`, or `rejected` by `set_check`, as the composite is
SET only and Z2M's state for it is the last write's echo. Each class rule reads `bridge/devices`' definition: its
`model` (Sonoff) or maker string (Tuya) in the allowlist, and a top-level `inching_control_set` expose. The wire bytes,
readback, the off's report and the strings tried: [Sonoff](research/sonoff/2026-11-24-inching.md),
[Tuya](research/tuya/2026-11-24-inching.md) (ZHC at
[`ed29f800`](https://github.com/Koenkk/zigbee-herdsman-converters/tree/ed29f80014f11cd3234e0e7371d1aace44e08982), read
2026-11-24; no device probed).

**Sonoff** (`families/sonoff/inching.py`): `{"inching_control_set": {"inching_control": "ENABLE", "inching_time": t,
"inching_mode": "OFF"}}`; clear sends `"DISABLE"`, `inching_time` 0.5, `inching_mode` `"OFF"`.

- **The mode-ON trap.** The mode bit is set unless `inching_mode` reads `"OFF"`, so a write that omits it is mode ON:
  the relay switches on at once and turns back on after every off
  ([ZHC #13383](https://github.com/Koenkk/zigbee-herdsman-converters/issues/13383)). Both calls always send `"OFF"`.
- **A 16-bit time.** ZHC writes the time into two bytes and zeroes the next two, while the ZHA quirk PR reads all four
  as one 32-bit value (ZHADH #5317). So on the 86,399.5 s models (MINI-ZBDIM, MINI-ZB1GSP, MINI-ZB1GS) anything over
  32,767.5 s would truncate through ZHC. `DurationLimits` is 0.5 s to 3,599.5 s step 0.5 s on every model, so one class
  holds them all (inferred from the source, not tested on a device).
- **Mode OFF is relay-neutral:** arming it changes no state, and `clear_auto_off` leaves the output as it is, inferred
  from DISABLE being the same write with the enable bit clear (inferred, not reported).

**Tuya** (`families/tuya/inching.py`): `{"inching_control_set": {"inching_control_1": "ENABLE", "inching_time_1": N}}`;
clear sends `"DISABLE"` and `inching_time_1` 1, as a gang missing either field is skipped. N is whole seconds, 1 to
65,535 (a 16-bit count on the wire).

- **Gang 4 and up are mis-encoded.** The channel byte is `2 ** (i-1)` where Tuya's document gives `(i-1) << 1`: equal
  for gangs 1 to 3, wrong from the fourth ([ZHC #13655](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13655),
  open). Inferred from the code and the PR, not tested. On the TS0004 in that PR a write for one gang also disabled the
  others. So multi-gang waits.
- **No shared channel:** neither inching string is in a class `turn_on_for` serves, so inching and a countdown never
  share a channel.

### `set_attributes`

Z2M's generic `command` payload, one per field. A color goes as xy, or hue and saturation on a light without xy.
Z2M publishes no state after a raw command, so each written cluster is read back live from each light, which also
updates Z2M's and Home Assistant's state. Level and color temperature are compared (`not_stored` if they differ);
color isn't, as the bulb clamps it to its gamut. A group is one groupcast per field, then every member is read.
`min_brightness`/`max_brightness` alone clamp each member from its own level, so each gets its own commands; an off
light is clamped from the brightness Z2M holds. A level write is followed by Z2M's own kept-level payload,
`{"state": null, "brightness", "transition"}`: after an off with a transition Z2M restores the level it kept on the next
plain on, which a raw command doesn't replace. It is left out only for a level 1 written where every light it reaches
is a lit Hue light (`families/hue` `RAW_BOTTOM`): the bulb has taken the raw write, and the payload, through the
converter, moved a lit Hue bulb from level 1 to 2 (`fade`, the bottom). On
another brand's light (`other`) the call is the same: no
departure is reported among its vendors, and a bulb older than ZCL rev 7 rejects the override fields
(MALFORMED_COMMAND), which raises ([research](research/2026-11-24-other-brands-execute-if-off-and-reads.md)).

### `get_attributes`

Z2M's generic read, `{"read": {"cluster", "attributes", "state_property": "deviceside_read"}}`, one cluster at a
time, answered on the state topic:

- `genOnOff` (`onOff`, `onTime` in tenths): the timer. Another brand's light (`other`) and an Aqara light (`aqara`, whose bulb has no `onTime`: [probe](research/aqara/2026-11-25-agl003-probe.md), section 1) are asked `onOff` alone: ZCL
  doesn't require `onTime`, one unsupported attribute fails the whole cluster read (herdsman `Endpoint.read`), and no
  timer action serves `other` ([research](research/2026-11-24-other-brands-execute-if-off-and-reads.md)).
- `genLevelCtrl` (`currentLevel`), only when the light is on. An off light's brightness is Z2M's, from the state the
  `genOnOff` answer carries: after an off with a transition the bulb holds 0.4 % while Z2M keeps the level it
  restores, a Hue bulb's own fade dims it for about a second after a plain off, and reading it would overwrite
  Z2M's kept level.
- `lightingColorCtrl`: `colorMode`, then only the attributes of the light's own modes, since one missing attribute
  fails the whole read.

A failed read raises at once when Z2M logs it on `<base topic>/bridge/logging`, else after 5 s. A group reads its
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
  light's current hue, which goes out as `moveToHueAndSaturation`. Source, zigbee-herdsman-converters at
  [`f368dcd1`](https://github.com/Koenkk/zigbee-herdsman-converters/commit/f368dcd1): `src/converters/toZigbee.ts` (`light_color`), `src/lib/philips.ts` (`light`, `hue_native_control`),
  `src/lib/modernExtend.ts` (`light`: `meta.supportsHueAndSaturation`).
- A brightness or saturation fade's `transition` is at most the longest ZCL transition (`docs/internals.md`, Fades),
  with `clamped_to` when a longer one is cut; the prediction matches.
- Hue: `hue_move` at `254 / sweep_time` steps per second (ZCL allows 1 to 254).

**The bottom.** zigbee-herdsman-converters' `light_onoff_brightness` sends a brightness of 1 as level 2 on a definition
with `turnsOffAtBrightness1` ([toZigbee.ts L1378](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1378)), and on a group only when every
member's definition has it (`allEqual`, [L1258](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1258)); it sends the level with
`moveToLevelWithOnOff`, which at a light's minimum sets OnOff off (Tested behavior). `philips.m.light` sets the flag
([philips.ts L315](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/philips.ts#L315)), as do 92 Innr and 28 ADEO definitions
([survey](../../research/2026-11-25-z2m-converter-survey.md)) and some IKEA, Gledopto and Aqara ones. DeviceSide can't
read the flag, so a lower whose publish would carry brightness 1 (2 or less for a standard light) goes by class; the
rule is `fade.py`'s docstring:

| Lights the lower reaches | Call | Level |
|---|---|---|
| Hue and Aqara lights alone (`families/hue` and `families/aqara` `RAW_BOTTOM`, joined in `fade.py` `RAW_BOTTOM`) | Raw `moveToLevel` | 1 (0.4 %) |
| Standard lights, alone or with Hue and Aqara lights (`standard_lights.py` `BOTTOM_LEVEL`) | Raw `moveToLevel`, for a lower to 0.8 % or below | 2 (0.8 %), the highest any member's class declares |
| Other lights whose definition is flagged | The converter's `moveToLevelWithOnOff` | 2 (0.8 %) |
| Other lights not flagged | The converter's `moveToLevelWithOnOff` | 1, which switches the light off |
| A group with an `other` member | The converter, for the whole group (`allEqual`) | 2 when every member is flagged; else 1, which switches its lit lights off and lights its off ones |

The raw call is `set_attributes`' and ZHA's: `{"command": {"cluster": "genLevelCtrl", "command": "moveToLevel",
"payload": {"level", "transtime", "optionsMask": 0, "optionsOverride": 0}}}`, `transtime` in tenths as the converter's
([L1403](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1403)). With no On/Off it never sets OnOff, and below a light's MinLevel it
clamps to MinLevel (ZCL, Level Control, Move to Level), so it holds any MinLevel lit.

- **Hue and Aqara** go to level 1 on a probe of each holding it lit (Tested behavior); the raw bottom serves the whole
  Aqara class on the T2's evidence, so an Aqara definition ZHC flags would get a raw level 1 untested.
- **A standard light's bottom is level 2,** not 1, as no standard light has been probed holding level 1 on the raw
  call. A probe of one holding level 1 lit on the raw `moveToLevel` reopens it, lowering `BOTTOM_LEVEL` to 1. The result carries no `clamped_to`, as Z2M's own flagged bottom reports
  none.
- **Other flagged lights** keep Z2M's 2: Innr's turn off at level 1
  ([research](research/2026-11-24-other-brands-dimming.md)). An unflagged `other` light, and a group with an `other`
  member: [deferred.md](../../deferred.md#the-raw-bottom-for-other-lights-on-zigbee2mqtt).
- **Z2M's restore memory.** An off with a transition stores Z2M's brightness, and the next plain on restores it through
  the converter; only a converter brightness set clears it, and a raw command touches neither
  ([L1320](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1320)–[L1384](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1384)). So an off with a transition
  after a raw lower, before the end read-back (the fade's length and about 1 s, `END_READ_S`), stores the level from
  before the lower: a known limit (Tested behavior). After the read-back, a lit bulb at level 1 would store 1, which the
  converter sends as 2 (from source; not measured).

### `stop`

`stop`: `brightness_move: stop`, `hue_move: stop` for a running hue cycle, and a raw `stopMoveStep` for a
saturation fade, since `saturation_move: stop` halts the attribute and lets the xy fade drift on. Each is its own
publish, color first: Z2M reads back about 0.7 s after a brightness stop before sending the next key.

A soft off of ours is halted by `brightness_move: stop` alone: `lower_brightness` turns `hue_native_control` off for
its publish (`native_control`), so the soft off runs as a ZCL transition, which a ZCL stop ends, holding the bulb
where it halted (Tested behavior). Z2M reports `OFF` from the start of a soft off, so HA shows the light off until
Z2M's read-back after the stop. If the `hue_native_control` set fails or times out (MQTT or Z2M slow or down;
`native_control` logs "Couldn't set Zigbee2MQTT's hue_native_control to ..." and sends the command anyway), the soft
off goes out as Philips' own command, which `brightness_move: stop` doesn't end, so the light fades on to off after a
stop ([deferred](../../deferred.md#a-stop-after-a-failed-native-control-set-on-zigbee2mqtt)).

### `set_check`

Z2M reports a set it couldn't send only on `bridge/logging`, at error level:
`Publish 'set' '<key>' to '<friendly name>' failed: '<error>'`, then goes on to the message's next key and publishes
the message's state after the last (`lib/extension/publish.ts`). So a key's failure line comes before its message's
state. raise, lower, stop, turn_on_for and turn_off_for settle after their publishes until each entity published to
has a state publish or a failure line, else 2 s past its last publish; a failure line makes the target `rejected`,
with the status it names (`busy`) or `send_failed`. set_attributes checks without the settle. The settle never
delays a publish. `hue_move`, a raw `command` and `on_time` draw no state, so a publish of one waits only 0.25 s,
for a groupcast's BUSY (Tested behavior: why not 2 s). A unicast's BUSY on them answers `sent`.

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
- **A soft off halted by `brightness_move: stop`** (lab probe, an LTA009 on Z2M 2.14.3): a 10 s soft off from full,
  stopped 3.2 s in, held `currentLevel` 175 for 4 s, where the linear prediction was 172; HA showed `on` 0.59 s after
  the stop, at Z2M's stale 254 for 40 ms, then 175.
- **A groupcast's settle on `hue_move`** (rig run 2026-11-13): waiting 2 s answered `raise_hue` 2 s late, and a
  script that waited, then stopped, ran the hue 2 s on: +92° on a 3 s raise, where +54° was expected.
- **A groupcast refused BUSY is lost** (rig, 2026-11-11): Z2M logged `[ZCL GROUP groupId=<id>] Failed to send with
  status=BUSY.` about 20 ms after a group `brightness` set, and the group never moved.
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

The brightness floor, 2026-11-25 on Z2M 2.14.3, an LTA009 (firmware 1.163.1), its level read live
([brightness floor](research/hue/2026-11-25-brightness-floor-probe.md), [raw bottom](research/hue/2026-11-25-raw-bottom-probe.md),
[rig run](research/hue/2026-11-25-move-to-level-bottom-rig.md)):

| Case | Result |
|---|---|
| Lower from 30 % to 0.4 % through the converter (`{"brightness": 1}`) | Level 2, 0.8 % (ZHA: 1) |
| `set_attributes` at 0.4 %, lit: raw level 1, then the kept-level publish 3 ms later | Read 2, `not_stored`, with `hue_native_control` off; 1 with it on (ZHA: 1) |
| `turn_on_for` at 0.4 % from off, with the option on | Read 1 through the timer; Philips' native converter clamps to 1–254 ([philips.ts L420](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/philips.ts#L420)) |
| Raw `moveToLevel` lower to level 1, a bulb and an all-Hue group of three with one off | Held lit at 1; the off member stayed off at its own level |
| Raw `moveToLevelWithOnOff` to level 1 | Off (`onOff` read off, level read 0.4 %) |
| A member soft-off at 40 %, a group raise from off to 100 %, a plain on to the member (option off) | 40.2 %, as with plain HA group commands; with the option on nothing jumped |
| Raw lower 30 % to 0.4 %, then an off with a transition 2 s later, before the end read-back | The plain on restored 29.9 % |

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

An Aqara T2 E27 color bulb (`lumi.light.agl003`, date code `20260605`), 2026-11-25 on Z2M 2.14.3 (ZHC 26.125.0), Home
Assistant 2026.10.4, EmberZNet ([probe](research/aqara/2026-11-25-agl003-probe.md)):

| Case | Result |
|---|---|
| Color capabilities | 24, xy and color temperature; hue, saturation and color loop attributes `UNSUPPORTED_ATTRIBUTE`; `moveHue` and `moveSaturation` change nothing (section 1, 2) |
| `OnTime`, `OffWaitTime`, and `{"state": "ON", "on_time": N}` from off | Unsupported; never turned on, Z2M logging nothing at `warning`; its own fade is 1.5 s (section 3) |
| Lower to 0.4 % through the converter (unflagged, `moveToLevelWithOnOff` to 1) | Off 2 s later; the raw `moveToLevel` to 1 held it lit (rig run 2026-11-25) |
| `set_attributes` at once after `light.turn_off` | Timed out in 1 of 10 (`no genLevelCtrl reply`, a hung `moveToLevel` that later requests waited behind), 0 of 10 after HA showed off; cause unexplained (section 4) |

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

- **zigbee-herdsman-converters: `saturation_move: stop` doesn't halt a hue/saturation `color` fade,** which drifts
  on (Tested behavior). The stop key doesn't match the command that started the fade (`hue_move: stop` does halt a
  hue cycle cleanly). Fix: send `stopMoveStep` (0x47), which halts every color move; workaround: `stop`. A one-line
  converter fix with a by-eye repro; the Hue bulbs honoring it is observed, not guaranteed by ZCL. Whether it needs
  `hue_native_control` is untested.
- **zigbee-herdsman-converters: `on_off` with `on_time` publishes no state.** The `on_time` branch returns
  nothing, unlike the others. Workaround: `turn_on_for`'s scheduled reads. Fix: return `{state: "ON"}` as the plain
  branch does.
- **Zigbee2MQTT: after an xy stop, the read-back publishes the cached end-point x/y,** not where the bulb halted.
  Workaround: `color_refresh`. Fix: re-read `currentX`/`currentY` (or drop the optimistic value) on a color stop.
- **Zigbee2MQTT: a group stop is read back from its first member only;** the others keep the optimistic end
  value. Workaround: a read per member. Per-member reads on large groups cost mesh traffic, so expect discussion.
- **Zigbee2MQTT: a `read` answer with `state_property` is deep-merged into the cached state forever,** so every
  later state message carries it. Workaround: `read`. Fix: a non-persisting read, or `state_property` keys kept out of the cache. They may answer "use
  `filtered_cache`".
- **zigbee-herdsman (Ember adapter): a groupcast the coordinator refuses with BUSY isn't retried.**
  `sendZclFrameToGroup` makes one `ezsp.send` (multicast) and throws on any status but success, while a unicast
  retries BUSY up to `QUEUE_MAX_SEND_ATTEMPTS` (3), 500 ms apart (`src/adapter/ember/adapter/emberAdapter.ts`).
  Seen on the rig (Tested behavior). Workaround: none for the send; `set_check` reports
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
