# Zigbee2MQTT base topics: where a target's base topic comes from (2026-11-24)

Probe date: 2026-11-24. Scope: whether a Zigbee2MQTT device's or group's base topic can be read exactly from Home
Assistant's public registries, so DeviceSide can address any base topic and several instances on one broker (#575).
Spec: `docs/plans/2026-11-24-z2m-any-base-topic.md`, step 1. Upstream source pinned to Zigbee2MQTT tag
[`2.14.3`](https://github.com/Koenkk/zigbee2mqtt/blob/2.14.3/lib/extension/homeassistant.ts), the version #575's
reporter runs. No names, IDs or addresses below: IEEEs are `0x<ieee>`.

## 1. The report (#575)

A user's Zigbee2MQTT add-on options, from a preconfigured install package, held the base topic `'    zigbee2mqtt'`:
four leading spaces. HA's UI doesn't show them. Every DeviceSide light action refused their Z2M lights as
`not_addressable`, because DeviceSide built every topic on `zigbee2mqtt`. Publishing `{"brightness_move": 50}` to
`    zigbee2mqtt/<name>/set` dimmed the lights, so the devices themselves were fine. Renaming the base topic to the
default fixed it, but Zigbee2MQTT puts the base topic in every entity's unique_id, so a rename duplicates every Z2M
entity in HA (new `_2` entities, the old ones unavailable). The reporter restored a backup, then rewrote the suffix
in `.storage/core.entity_registry` with HA stopped. That's why renaming isn't a workable fix for users.

## 2. Upstream: what Zigbee2MQTT tells HA (`lib/extension/homeassistant.ts` at 2.14.3)

- The bridge is an entity of its own: `options.ID = \`bridge_${ieeeAdress}\``, the coordinator's IEEE (`Bridge`
  constructor, L478-L490).
- Every discovered entity's unique_id is `${entity.options.ID}_${config.object_id}_${settings.get().mqtt.base_topic}`
  (L1854). For the bridge's entities that's `bridge_<coordinator ieee>_<object_id>_<base topic>`, the base topic
  verbatim: spaces and `/` included.
- The bridge's object_ids are fixed: `connection_state`, `restart_required`, `restart`, `log_level`, `version`,
  `coordinator_version`, `network_map`, `permit_join` (`getBridgeEntity`, L2304-L2415).
- A device's identifier is `zigbee2mqtt_<ieee>`; a group's is `zigbee2mqtt_<encoded base topic>_<group id>`, where the
  encoded base topic is each character's code point in decimal, concatenated (`getDevicePayload` L2177/L2186,
  `getEncodedBaseTopic` L2249-L2255). The bridge's is `zigbee2mqtt_bridge_<coordinator ieee>`.
- Every device and group payload carries `via_device = this.bridgeIdentifier`, the bridge's identifier (L564,
  L2225-L2228). The bridge's own payload has none.

So a target's base topic is the unique_id of any entity on its `via_device` (the bridge), with
`bridge_<ieee>_<object_id>_` stripped. Two instances on one broker have different coordinators, so different
bridges, and each device and group links to its own.

## 3. Live: the household's registries

Read only: the MQTT config entry's diagnostics (each entity's discovery payload and unique_id) and one template over
`integration_entities('mqtt')` giving each entity's device, its `via_device_id` and identifiers. One Zigbee2MQTT
instance, on the default base topic.

| What | Seen |
|---|---|
| Bridge devices (identifier `zigbee2mqtt_bridge_0x<ieee>`) | 1 |
| Bridge entity unique_ids | `bridge_0x<ieee>_connection_state_zigbee2mqtt`, `…_log_level_zigbee2mqtt`, `…_permit_join_zigbee2mqtt`, `…_restart_zigbee2mqtt`, `…_version_zigbee2mqtt` |
| Parsed base topic, every one | `'zigbee2mqtt'` |
| Z2M devices whose registry `via_device_id` is the bridge | 36 of 36 (3 with a light) |
| Z2M groups whose registry `via_device_id` is the bridge | 1 of 1 (with a light), encoded base `1221051039810110150109113116116` = `zigbee2mqtt` |
| Discovery payloads with `via_device` = `zigbee2mqtt_bridge_0x<ieee>` | 281 device-entity payloads and 1 group-entity payload; the 5 bridge payloads have none |

Five of the eight bridge object_ids show, consistent with the diagnostics listing only the entities MQTT has loaded: the other three
(`restart_required`, `coordinator_version`, `network_map`) are disabled by default upstream (`enabled_by_default:
false`, L2334, L2391, L2403), so a reader keyed on one object_id could miss. Reading every entity-registry entry of the bridge, disabled
ones included, and matching any of the eight is what holds; this probe didn't read disabled registry entries, so
step 2's unit tests pin that read.

## Findings

1. A Z2M device's or group's base topic is exact from public registries: its device's `via_device_id` is its
   bridge, and any of the bridge's entity unique_ids ends in the base topic. Upstream and live agree on the default base; a custom base
   and two instances rest on upstream alone, untested live.
2. A group's identifier encodes its instance's base topic, so it can be checked against its bridge's.
3. The base topic is used verbatim: #575's leading spaces are part of it, and HA's UI hides them.
