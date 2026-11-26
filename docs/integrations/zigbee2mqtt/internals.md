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
Z2M sends the call to the device's default endpoint: the definition's `default`, else its first (`endpoint()` in Z2M's
[`lib/model/device.ts`](https://github.com/Koenkk/zigbee2mqtt/blob/2.6.0/lib/model/device.ts), called from
`lib/extension/publish.ts`). Another endpoint needs `<base topic>/<device>/<endpoint>/set` or a suffixed key
(`state_l2`), which DeviceSide doesn't send, and such a device publishes its state under suffixed keys (`state_l1`),
which no read here takes. So a device target is addressed only when it is the device's unsuffixed state entity, the
one the `state` key DeviceSide sends and reads defines, whichever endpoint is the default:

| Entity in the domain | Example (unique_id) | Addressed |
|---|---|---|
| The unsuffixed state entity of a `switch` or `light` expose with no endpoint | `<ieee>_<domain>_<base topic>` (`${ID}_${object_id}_${base_topic}` in `lib/extension/homeassistant.ts`) | Yes |
| A gang | `<ieee>_<domain>_<endpoint>_<base topic>` (`switch_l1`) | No: `not_addressable`, the first gang too |
| A writable `binary` expose | `switch_<name>`: a plug's child lock (`config` category), a presence sensor's indicator, a radar's toggles | No: `not_addressable`, disabled or not |
| A `switch_as_x` light on the device | | Served as the switch it wraps |

Counting the device's entities in the domain instead would refuse every TS011F plug for its child lock. The rule is
argued, not tested, for a device with an unsuffixed entity beside suffixed gangs, none of which is in hand: it addresses
the unsuffixed one. The refusal is `addressing.not_addressable`, which each adapter's `supports()` calls, for a target
named or reached by area, label or `group.*`.

As a group's member, `members.py` lists a device by its unsuffixed state entity, addressable, else (a gang) by its
first entity, not addressable (`Target.addressable`): its class counts, and `member_lights` leaves it out (logged at
DEBUG). `bridge/groups` lists each member as `{ieee_address, endpoint}`, the endpoint by number, so a group can hold
gang 2 of a two-gang alone, and its groupcast reaches that endpoint:

| Action on a group with such an available member | Result |
|---|---|
| Fade, stop, set attributes | `not_addressable`: they plan from every member's state |
| Get attributes | Averages the other lights; `not_addressable` with no other available light |
| `turn_on_for` (groupcast only) | Unaffected |
| Any fallback to members | Skips it as `not_addressable` |

Since Z2M 2.6.0 `bridge/devices` names each endpoint (`endpoints.<number>.name`, the definition's `l1`;
`publishDevices` in [`lib/extension/bridge.ts`](https://github.com/Koenkk/zigbee2mqtt/blob/2.6.0/lib/extension/bridge.ts),
absent in 2.5.1), and Z2M's discovery gives that entity unique_id `<ieee>_<domain>_<name>_<base topic>` (object_id
`light_l1`). Matching it is no use until the call can reach that endpoint and read its suffixed keys back:
[per-endpoint addressing](../../deferred.md#per-endpoint-addressing-on-zigbee2mqtt).

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

- **Membership.** A zigbee-herdsman-converters (ZHC) light definition (its resolved exposes hold a `light`), resolved
  with ZHC's own `prepareDefinition`, as Z2M runs it, whose converter for every key DeviceSide publishes is ZHC's
  standard one: `state` and `brightness` on `light_onoff_brightness` (`state` on `on_off` only for a light with
  no brightness: `on_off` beside a brightness converter sends a plain On or Off, the departure ZHC fixed on Inovelli
  and Legrand), `transition` on `ignore_transition`, `color` on `light_color` or `light_color_colortemp`,
  `hue_move` on `light_hue_saturation_move`, `brightness_move` on `light_brightness_move`, and the generic
  `command` and `read`. Its `meta` sets no flag but those that leave DeviceSide's calls alone
  (`supportsHueAndSaturation`, `multiEndpoint`, `multiEndpointSkip`, `applyRedFix`, `disableActionGroup`,
  `overrideHaDiscoveryPayload`, `thermostat`), so `turnsOffAtBrightness1` (the brightness floor), the option-field,
  enhanced-hue and default-response flags keep a definition out, and so does a flag ZHC adds, until a maintainer has
  read it. One exposing `color_hs` without `supportsHueAndSaturation` is out, as its saturation fade goes out as
  `moveToColor`, not the call on record. A definition model is the key, with each white label that has a fingerprint
  (Z2M publishes its model when the fingerprint matches); a model string two definitions publish is left out.
- **The table** is the Zigbee catalog's `zigbee/standard_lights.py`, so another Zigbee integration can read it: between
  its markers, generated, the ZHC release and `MODELS`, each member with the Zigbee strings ZHC matches it on (its
  zigbeeModel IDs and its fingerprints' model ID and manufacturer), and `PAIRS`, each (model ID, manufacturer) key whose
  every definition is a member and none a split-off, the one key another integration may use (the module docstring says
  how); outside them, hand-kept, `EXCLUDED` (a split-off, its action and source, keyed on the definition model, as no
  rule reads firmware) and `KEPT` (a departure a maintainer kept, with the reason). [The standard lights
  page](standard-lights.md) is rendered from it.
- **The bump**, the first item of each RC (the release skill): `scripts/zhc_table.py --pin <ZHC release>` clones and
  builds ZHC at the tag, resolves its definitions (`scripts/zhc_table/resolve.mjs`), rewrites the table and the page,
  and prints the bump PR's body: additions; departures, each **review** when the model was a member at the last full
  release, else **leaves**; and trait changes on the families' definitions, flagged, never classifying, which builds
  the previous pin too. Family is read off what a definition shows (its vendor, models, fingerprints and exposes, and
  IKEA's Zigbee manufacturer string tried on IKEA's), so it is approximate. `--check`, in the Tests workflow, needs
  no network. `scripts/check_audit.py` fails an RC cut from `main` whose pin hasn't moved since the previous RC
  tag, unless its audit record says `ZHC bump skipped: <reason>`.
- **The option fields.** ZHC's own light converters send `optionsMask` and `optionsOverride` 0/0; DeviceSide's
  `set_attributes` builds a raw `command` with 1/1 (ExecuteIfOff), and `get_attributes` a raw `read`, which no
  light flag touches. So those two aren't on Z2M's usage. They qualify as every known failure is visible to the
  caller: a light that rejects the option fields answers MALFORMED_COMMAND, which raises; a write that doesn't land
  fails the read-back (`not_stored`); an attribute the light lacks fails the read (UNSUPPORTED_ATTRIBUTE). The one
  silent case, `disableDefaultResponse`, keeps a definition out.

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

- **What Z2M sends.** `tz.datapoints` ([ZHC `src/lib/tuya.ts#L3237-L3278`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/c18c32d94c77f683fa768618d1fd32b348fdd7b9/src/lib/tuya.ts#L3237-L3278)) takes
  the whole payload in one call, loops its keys in order and awaits each `sendDataPoints`, whose `entity.command`
  rethrows a failed send; so a lost `state` throws before `countdown` goes out, and Z2M logs
  `Publish 'set' 'state' … failed`, which `set_check` makes `rejected` (research §1).
- **Why one publish, not state then a wait for its report.** `tz.datapoints` returns every key it sent as the state,
  and Z2M publishes that optimistically, so the state publish after a set is Z2M's own echo, not the device's report: a
  wait would have no signal. The order and the `await` give the guarantee the wait was for, as converter A's do (The
  harm the order prevents, above).
- **What stays.** A `state` that reached the device but whose delivery herdsman reports failed, or a `countdown` that
  fails after the `state` went out, leaves the device switched with no timer, answered `rejected`; a local toggle in
  the milliseconds between the two frames would put the timer on the other state.
- **GL-SPI-206P sends the on/off datapoint twice.** Its own `glspi206p_light` converter takes `state` and sends DP 1;
  `tz.datapoints` takes `countdown` and sends DP 1 again before it. A lost first DP 1 throws and Z2M logs the set
  failed; if the second then succeeds, the countdown is armed while `set_check` answers `rejected` (research §1).
- **Dimmers** skip the state datapoint when a payload holds `brightness` (`skip.stateOnAndBrightnessPresent`): the
  countdown publish holds none. **D5Z** publishes `countdown: 0` on every state change, so its readback shows 0 while
  the timer runs; nothing reads it.
- **The toggle.** Tuya's General Countdown page (the [index](index.md#tuya-datapoint-devices-with-one-countdown) gives
  what it says), fetched 2026-11-24, also clears the countdown on a countdown of 0, and gives its range as "0 - 1440"
  with no unit; ZHC's expose text adds "(one time action)" (research §2).
- **The class rule** reads `bridge/devices`' definition: its `model` in the allowlist (`DATAPOINT_DEFINITIONS`,
  each checked at ZHC v26.125.0 and v26.136.0, research §3) and a top-level expose `countdown` with no endpoint, the
  single-endpoint guard. The rules run before `tuya_ts011f` (the ZOT60 is a TS011F) and `tuya_mcu`. The registry
  can't see exposes, so until `bridge/devices` lists the device it is Unplaced, refused as `class_unknown`. D1Z
  (ZHC v26.126.0) and SFD02-Z_2 (v26.127.0) are newer than the ZHC Z2M 2.14.3 ships, so match nothing on it.

### `set_auto_off` and `clear_auto_off`

Persistent auto-off, "inching", one publish to the set topic, by Z2M's composite `inching_control_set`. They serve only
their classes' own calls (`AdapterScope.own_calls_only`): the Sonoff and Tuya inching classes, below. Every other class
is refused as `not_built`, and a target not yet placed as `class_unknown`. `native_groups=False`, so a Z2M group falls
back to its members. `confirmable=False`: the result is `sent`, or `rejected` by `set_check`. Evidence: ZHC at
`ed29f800`, read 2026-11-24, and upstream reports, which the research gives byte by byte; no device was probed
([Sonoff](research/sonoff/2026-11-24-inching.md), [Tuya](research/tuya/2026-11-24-inching.md)).

- **No readback.** The composite's access is SET only: no `/get`, and no converter reads it. Z2M publishes the value
  written as state, so its state is the last write, not the device's; the S60 showed inching inactive after pairing
  while it ran ([Zigbee2MQTT #31604](https://github.com/Koenkk/zigbee2mqtt/issues/31604)). So `get_attributes` reports
  no auto-off setting for these classes. Tuya's device reports attribute 0xD003, which ZHC decodes but can't `get`;
  the report is best effort, and ZHC decodes a phantom gang on some devices
  ([Zigbee2MQTT #32248](https://github.com/Koenkk/zigbee2mqtt/issues/32248)).
- **The off arrives as an On/Off report,** `ON` then `OFF` at the set time (ZBMINIR2:
  [ZHC #13383](https://github.com/Koenkk/zigbee-herdsman-converters/issues/13383), 1 s; Mowe:
  [ZHC #13118](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13118), 5 s). Whether a 0.5 s pulse is
  reported on every model is unknown.

**Sonoff** (`families/sonoff/inching.py`): `{"inching_control_set": {"inching_control": "ENABLE", "inching_time": t,
"inching_mode": "OFF"}}`; clear sends `"DISABLE"`, `inching_time` 0.5, `inching_mode` `"OFF"`. ZHC's
`sonoffExtend.inchingControlSet` ([`sonoff.ts#L2686-L2775`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/ed29f80014f11cd3234e0e7371d1aace44e08982/src/devices/sonoff.ts#L2686-L2775))
sends cluster 0xFC11 command `protocolData` (0x01), manufacturer code 0x1286, with a mode byte, the channel and the
time in 0.5 s units.

- **The mode-ON trap.** The mode bit is set unless `inching_mode` reads `"OFF"`, so a write that omits it is mode ON:
  the relay switches on at once and turns back on after every off
  ([ZHC #13383](https://github.com/Koenkk/zigbee-herdsman-converters/issues/13383)). Both calls always send `"OFF"`.
- **A 16-bit time.** ZHC writes the time into two bytes and zeroes the next two, while the ZHA quirk PR reads all four
  as one 32-bit value (ZHADH #5317). So on the 86,399.5 s models (MINI-ZBDIM, MINI-ZB1GSP, MINI-ZB1GS) anything over
  32,767.5 s would truncate through ZHC. `DurationLimits` is 0.5 s to 3,599.5 s step 0.5 s on every model, so one class
  holds them all (inferred from the source, not tested on a device).
- **Mode OFF is relay-neutral.** Arming mode OFF changes no state; the relay pulses on its next turn-on (ZHC #13383).
  That `clear_auto_off` leaves the output as it is follows from DISABLE being the same write with the enable bit clear
  (inferred, not reported).
- **Refused:** the S60ZBTPF and S60ZBTPG, as `DISABLE` is reported to have no effect on firmware 1.0.2
  ([Zigbee2MQTT #31799](https://github.com/Koenkk/zigbee2mqtt/issues/31799)); the MINI-ZB2GS, whose composite is per
  endpoint (suffixed fields), until per-endpoint addressing.
- **The class rule** reads `bridge/devices`' definition: its `model` in the allowlist and a top-level
  `inching_control_set` expose.

**Tuya** (`families/tuya/inching.py`): `{"inching_control_set": {"inching_control_1": "ENABLE", "inching_time_1": N}}`;
clear sends `"DISABLE"` and `inching_time_1` 1. N is whole seconds, 1 to 65,535 (the expose's min, max and step; the
wire is a 16-bit count of seconds). ZHC's `valueConverter.inchingSwitch.to` and `tz.inchingSwitch`
([`lib/tuya.ts#L2901-L2918`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/ed29f80014f11cd3234e0e7371d1aace44e08982/src/lib/tuya.ts#L2901-L2918),
[`#L3406-L3419`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/ed29f80014f11cd3234e0e7371d1aace44e08982/src/lib/tuya.ts#L3406-L3419))
send each gang's channel, enable bit and seconds as base64 text, command 0xFB on cluster 0xE000, endpoint 1: four bytes
a gang, not the three Tuya's document shows, which works on hardware
([ZHC #13118](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13118),
[#13879](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13879)).

- **Both fields are required.** A gang missing either is skipped and the command carries an empty payload, so each call
  sends the time too, 1 s with a disable.
- **Gang 4 and up are mis-encoded.** The channel byte is `2 ** (i-1)` where Tuya's document gives `(i-1) << 1`: equal
  for gangs 1 to 3, wrong from the fourth ([ZHC #13655](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13655),
  open). Inferred from the code and the PR, not tested. And on the TS0004 in that PR a write for one gang disabled the
  others, unknown elsewhere. So multi-gang waits.
- **The two strings.** WHD02 `_TZ3000_skueekg3` (5 s and 63 s measured, read back right) and Mowe MW781Z
  `_TZ300A_rncj86af` (5 s measured). `_TZ3000_mzcp0of6` and `_TZ3000_p26flek3` were reported to have no effect. The
  class rule reads the maker string and a top-level `inching_control_set` expose (ZHC enables the WHD02's only on model
  `TS0001`, so its `TS000F` variant is out). Neither string is in a class `turn_on_for` serves, so inching and a
  countdown never share a channel.

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
  light's current hue, which goes out as `moveToHueAndSaturation`. Source, `Koenkk/zigbee-herdsman-converters`
  `f368dcd1`: `src/converters/toZigbee.ts` (`light_color`), `src/lib/philips.ts` (`light`, `hue_native_control`),
  `src/lib/modernExtend.ts` (`light`: `meta.supportsHueAndSaturation`).
- A brightness or saturation fade's `transition` is at most the longest ZCL transition (`docs/internals.md`, Fades),
  with `clamped_to` when a longer one is cut; the prediction matches.
- Hue: `hue_move` at `254 / sweep_time` steps per second (ZCL allows 1 to 254).

**The bottom.** zigbee-herdsman-converters' `light_onoff_brightness` sends a brightness of 1 as level 2 on a definition
with `turnsOffAtBrightness1` ([toZigbee.ts L1378](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1378)), and on a group only when every
member's definition has it (`allEqual`, [L1258](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1258)). `philips.m.light` sets it by
default ([philips.ts L315](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/philips.ts#L315)), as do 92 Innr definitions
([research](research/2026-11-24-other-brands-execute-if-off-and-reads.md)), 28 ADEO ones
([adeo.ts](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/devices/adeo.ts)), and 15 IKEA, 3 Gledopto and 3 Aqara ones (counted at that ZHC commit in
[#610](https://github.com/DeviceSide/DeviceSide/pull/610)). With `hue_native_control` off, every
brightness publish through the converter rides it: a fade to a limit that rounds to level 1, `set_attributes`'
kept-level publish after a raw level 1, and raise's from-off `"brightness": 1` (read from source; the fade that
follows hides it). The converter sends a level with `moveToLevelWithOnOff`, and a command with On/Off to a light's
minimum level sets OnOff off, likely ZCL's rule, which `turnsOffAtBrightness1` steps around (Tested behavior). DeviceSide
can't read the flag, which is ZHC's definition metadata, so a lower whose publish would carry a brightness of 1, or of 2
or less for a standard light, goes past the converter by class:

| Lights the lower reaches | Call | Level |
|---|---|---|
| Hue and Aqara lights alone (`families/hue` and `families/aqara` `RAW_BOTTOM`, joined in `fade.py` `RAW_BOTTOM`) | Raw `moveToLevel` | 1 (0.4 %) |
| Standard lights, alone or with Hue and Aqara lights (`standard_lights.py` `BOTTOM_LEVEL`) | Raw `moveToLevel`, for a lower to 0.8 % or below | 2 (0.8 %), the highest any member's class declares |
| Other lights whose definition is flagged | The converter's `moveToLevelWithOnOff` | 2 (0.8 %) |
| Other lights not flagged | The converter's `moveToLevelWithOnOff` | 1, which switches the light off |
| A group with an `other` member | The converter, for the whole group (`allEqual`) | 2 when every member is flagged; else 1, which switches its lit lights off and lights its off ones |

The raw call is the one `set_attributes` and ZHA's lower send, through Z2M's `command` payload:
`{"command": {"cluster": "genLevelCtrl", "command": "moveToLevel", "payload": {"level", "transtime", "optionsMask": 0, "optionsOverride": 0}}}`,
`transtime` the transition in tenths, as the converter's ([toZigbee.ts L1403](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1403)). With
no On/Off it never sets OnOff, and below a light's MinLevel it clamps to MinLevel (Zigbee Cluster Library
specification, Level Control cluster, Move to Level command), so it holds any MinLevel lit. A raw command draws no
state from Z2M, so Home Assistant follows at the fade's end read-back, or at a report from the bulb;
`brightness_move: stop` halts it as it does the converter's, both ZCL transitions. A raise from off keeps the
converter's bottom, so it starts at level 2 before fading up, which the fade hides. `set_attributes` leaves out its
kept-level publish only for a level 1 on lit Hue lights (`set_attributes`).

- **Hue and Aqara** go to level 1 on a probe of each holding it lit (Tested behavior). ZHC flags 3 Aqara definitions;
  the raw bottom serves the whole class on the T2's evidence, so a flagged definition in it would get a raw level 1
  untested.
- **A standard light's bottom is level 2,** not 1, as no standard light has been probed holding level 1 on the raw
  call. Every standard light is unflagged (a `turnsOffAtBrightness1` definition is no member,
  `zigbee/standard_lights.py`), so the converter would switch it off at level 1, and at level 2 one whose MinLevel is
  2. Its evidence is the call's: `moveToLevel` is a command every Zigbee 3.0 dimmable light must take, and a rejection
  reaches the caller (`docs/evidence.md`). The result carries no `clamped_to`: a ramp's is the `sweep_time` used, and
  Z2M's own flagged bottom is unreported too. A probe of a standard light holding level 1 lit on the raw `moveToLevel`
  reopens it, lowering `BOTTOM_LEVEL` to 1.
- **Other flagged lights** keep Z2M's 2, so their lowest is 0.8 %: Innr's turn off at level 1
  ([research](research/2026-11-24-other-brands-dimming.md), from Z2M #4035); ADEO's is read from the flag, not reported.
  A probe that shows one holds level 1 reopens the bypass for its family. An unflagged `other` light, and a group with
  an `other` member, are open: [deferred.md](../../deferred.md#the-raw-bottom-for-other-lights-on-zigbee2mqtt).

**Z2M's restore memory around a raw command**, from source and probed. An off with a transition, while Z2M's state is
ON, stores that state's brightness and sets `turnedOffWithTransition`
([L1320](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1320)–[L1329](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1329)); the next on with no
brightness restores the stored level through the converter ([L1336](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1336),
[L1354](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1354)–[L1356](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1356)), and only a converter
brightness set clears the flag ([L1382](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1382)–[L1384](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/converters/toZigbee.ts#L1384)).
A raw command touches neither. The memory is per device, and a group's set doesn't clear a member's. So after a raw
lower, an off with a transition before the end read-back stores the level from before the lower: a known limit, whose
window is the fade's length and about 1 s more (`END_READ_S`). The converter's publish would have moved Z2M's state to
the end level at once. After the read-back, a lit bulb at level 1 would store 1, which the converter sends as 2,
0.8 % (from source; not measured). Measured: Tested behavior.

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
for a groupcast's BUSY: a 2 s settle answered `raise_hue` 2 s late (Tested behavior). A
unicast's BUSY on them answers `sent`.

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

The brightness floor, 2026-11-25 on Z2M 2.14.3, an LTA009 (firmware 1.163.1), its level read live (`currentLevel`).
Probes: [brightness floor](research/hue/2026-11-25-brightness-floor-probe.md),
[raw bottom](research/hue/2026-11-25-raw-bottom-probe.md), [rig run](research/hue/2026-11-25-move-to-level-bottom-rig.md).

- **Through the converter, Z2M sends level 1 as 2.** `lower_brightness` from 30 % to a 0.4 % limit published
  `{"brightness": 1, "transition": 1.5}`: Z2M reported brightness 2, and the bulb read 2, 0.8 %. The same bulb on ZHA
  read 1 (`lower_to_the_lowest_level`).
- **`set_attributes` at 0.4 % on the lit bulb:** with `hue_native_control` off, the raw `moveToLevel` to 1, then the
  kept-level publish 3 ms later; three read-backs gave 2, so it was rejected `not_stored`. With it on, the same two
  publishes read back 1. On ZHA it read 1 (`sets_the_lowest_level_while_lit`).
- **`turn_on_for` at 0.4 % from off,** a probe: `light.turn_on`'s `{"state": "ON", "brightness": 1}`, sent with the
  option on, read 1 through the timer. Philips' native-control converter clamps a brightness to 1–254
  ([philips.ts L420](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/lib/philips.ts#L420)); other paths with the option on weren't measured.
- **A raw `moveToLevel` to level 1 holds the bulb lit:** a lower to 0.4 % held it at level 1
  (`lower_to_the_lowest_level`), and, groupcast to an all-Hue group of three with one member off, held the two lit ones
  at level 1 and left the off one off at its own level.
- **A raw `moveToLevelWithOnOff` to level 1 turns it off:** the lower ended with `onOff` read off, so Z2M and Home
  Assistant showed it off, while the level read 0.4 %, the brightness Z2M holds for an off light.
- **Z2M's restore memory,** with `hue_native_control` off, Z2M's default (with it on, nothing jumped). A member soft-off
  at 40 %, then a group raise from off to 100 %, then a plain on to that member: it went back to 40.2 %, as plain Home
  Assistant group commands did with no DeviceSide call. A raw lower from 30 % to 0.4 %, then an off with a transition
  2 s later, before the end read-back: the off stored Z2M's 30 %, and the plain on restored 29.9 %.

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
Assistant 2026.10.4, EmberZNet. Probe: [research/aqara/2026-11-25-agl003-probe.md](research/aqara/2026-11-25-agl003-probe.md).

- **No hue or saturation.** ColorCapabilities reads 24 (xy and color temperature: bits 3 and 4). `CurrentHue`,
  `EnhancedCurrentHue`, `CurrentSaturation` and `ColorLoopActive` read `UNSUPPORTED_ATTRIBUTE`, and `moveHue` and
  `moveSaturation` (rate 30, 2.65 s, then stop) left CurrentX, CurrentY and ColorMode unchanged. Home Assistant
  sends xy for an hs color, so the bulb stays in `xy` mode.
- **No `OnTime` or `OffWaitTime`** (`UNSUPPORTED_ATTRIBUTE`; `StartUpOnOff` and `GlobalSceneControl` too), and
  its discovery lists genOnOff commands 0, 1 and 2 only. `{"state": "ON", "on_time": N}` from off, which the
  converter sends as `0x42`, never turned the bulb on: N 10, then 30 replaced by 10, then 0, each read every 1 s for
  25 to 43 s, every read answered, Z2M logging nothing at `warning`. It also fades by its own 1.5 s
  (`onOffTransitionTime` 15).
- **The converter's bottom switches it off.** A lower to 0.4 % (the bulb is unflagged) published
  `{"brightness": 1, "transition": 1.5}`, which the converter sends as `moveToLevelWithOnOff` to level 1, and the bulb
  reported itself off 2 s later; the same level as a raw `moveToLevel` (`set_attributes`) held it lit, read 1 (rig
  run 2026-11-25, 13:43).
- **`no genLevelCtrl reply` is a hung `moveToLevel`.** `light.turn_off`, then at once `set_attributes` (the rig's
  put-back) timed out in 1 of 10 runs; the same after Home Assistant showed off (about 0.1 s), in 0 of 10. In both
  series the write landed inside the bulb's 1.5 s off fade, and in the timeout run DeviceSide sent after Z2M published
  OFF, so the trigger is unexplained. The bulb sent no default response within
  herdsman's 10 s (`disableDefaultResponse: false`), the later `CurrentLevel` read was answered only 0.27 s after
  the `moveToLevel` timed out, and a plain `turn_on` sent meanwhile took effect then too: requests after the hung
  one waited behind it. Z2M's own kept-level `moveToLevel` (no override) was not held, and the color temperature
  didn't land (the bulb came on in `xy`). In two other runs the read saw a level between the old and the written one
  (the off fade and the 0.4 s write fade overlapping) and the 0.5 s retry read it right. Z2M's frame logging
  (`log_debug_to_mqtt_frontend`) was off, so the frames, and whether the color temperature command was lost or held,
  are not seen.

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
