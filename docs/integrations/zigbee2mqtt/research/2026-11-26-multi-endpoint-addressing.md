# Multi-endpoint devices on Zigbee2MQTT: what a call reaches

Read from Zigbee2MQTT's source (2.5.1 and 2.6.0) and DeviceSide's code. Moved here from
[Zigbee2MQTT internals](../internals.md#addressing), which keeps its two tables, on 2026-11-26; the text is as it
stood.

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
[per-endpoint addressing](../../../deferred.md#per-endpoint-addressing-on-zigbee2mqtt).
