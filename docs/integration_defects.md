# Upstream defects and gaps

Workarounds DeviceSide carries for behavior in the integrations it drives, and in Home Assistant Core, that could
be fixed upstream. Ranked by how likely the maintainers are to recognize the gap and accept a fix. Only the
issues our code already cites (Koenkk/zigbee2mqtt#28757, #33025) have been checked upstream: search each tracker
for duplicates before filing. Measurements behind each entry are in
[integration-internals.md](integration-internals.md).

## Ranked

1. **ZHA (zigpy/zha): color temperature attribute reports are never applied to the entity.** HA shows a stale
   color temperature after any change it didn't send. Workaround: `homeassistant.update_entity` after every write
   (`integrations/zha/set_attributes.py`) and uncached live reads in `get_attributes`. A plain state-sync bug,
   easy to reproduce: change the color temperature from a remote. Already tracked as
   [zigpy/zha#855](https://github.com/zigpy/zha/issues/855) (open; a maintainer agrees it should be fixed as
   brightness was, and a fix sits on the `zigpy-bot/light-color-reports` branch, no PR yet). Don't file a new issue.
2. **zigbee-herdsman-converters: `saturation_move: stop` doesn't halt a hue/saturation `color` fade; it drifts on
   for about 3 s.** The stop key doesn't match the command that started the fade (`hue_move: stop` does halt a
   hue cycle cleanly). The converter should send `stopMoveStep` (0x47), which halts every color move. Workaround:
   a raw `stopMoveStep` (`integrations/zigbee2mqtt/stop.py`). A one-line converter fix with a by-eye repro; the
   Hue bulbs honoring it is observed, not guaranteed by ZCL. Whether it needs `hue_native_control` is untested.
3. **zigbee-herdsman-converters: `on_off` with `on_time` publishes no state.** The `on_time` branch returns
   nothing, unlike the others. Workaround: scheduled `{"state": ""}` reads at start + 1 s, end + 1 s and end +
   max(5 s, 2 %). Fix: return `{state: "ON"}` as the plain branch does.
4. **Zigbee2MQTT: after an xy stop, the read-back publishes the cached end-point x/y,** not where the bulb halted.
   Workaround: a `{"color": ""}` get 1 s after a saturation stop. Fix: re-read `currentX`/`currentY` (or drop the
   optimistic value) on a color stop.
5. **Zigbee2MQTT: a group stop is read back from its first member only;** the others keep the optimistic end
   value. Workaround: a read per member. Per-member reads on large groups cost mesh traffic, so expect discussion.
6. **zha-quirks: define Signify's `0xFC03` `multiColor` command on the Hue cluster,** so
   `zha.issue_zigbee_cluster_command` can send it. Workaround: straight to zigpy, re-implementing ZHA's admin
   check (`zcl.hue_turn_on`, `require_admin`). Additive quirk work; Z2M's `philips.ts` is prior art.
7. **Zigbee2MQTT: a `read` answer with `state_property` is deep-merged into the cached state forever,** so every
   later state message carries it. Workaround: `deviceside_read` appended to each device's `filtered_cache`.
   Fix: a non-persisting read, or `state_property` keys kept out of the cache. They may answer "use
   `filtered_cache`".
8. **ZHA: `update_entity` does nothing while the transition flag is up,** and "on" reports are ignored for 1.5 s
   after `turn_off`. Workaround: poll the flag up to 3 s and refresh again after long fades
   (`TRANSITION_WAIT_S`, the late refresh). The guard is deliberate; pitch it narrowly: an explicit
   `update_entity` bypasses it.
9. **HA Core (zha and hue lights): the level kept for the next plain on overrides one the bulb stored while off**
   (ZHA's `_off_brightness`, Hue's `_last_brightness` and `_restore_brightness`). Workaround: overwriting those
   private attributes (`core/ha_entity.replace_if_set`), our most fragile one. Fix: drop the kept level when a
   report shows the level changed while off, or a supported way to set it. Intentional behavior (a fade-off keeps
   its level), so expect pushback, but a rename in core silently breaks us.
10. **HA Core MQTT light: a state whose `color_mode` isn't in `supported_color_modes` is dropped,** keeping the old
    color. Accepting or converting it would fix every MQTT integration, not just Z2M. Core is strict about color
    modes.
11. **Zigbee2MQTT: announce both xy and hs.** Declined in #33025, hence the `homeassistant.light` override
    (`integrations/zigbee2mqtt/color_modes.py`). The remaining angle is narrower: opt-in per device, or only for
    Signify bulbs known to handle mixed modes.
12. **Zigbee2MQTT discovery identifiers.** A device's identifier lacks the base topic and a group's encodes it as
    unseparated character codes; a device whose friendly name is a bare number shadows the group with that ID in
    `resolveEntity`. Real but edge cases.
13. **HA Core zha: a public accessor for the gateway.** Importing it means declaring `after_dependencies`, which
    holds our setup while ZHA is stuck, so we read `hass.data["zha"]` (`zcl.gateway`). A nice-to-have for one
    consumer.
14. **zigbee-herdsman-converters (candidate, not probed): `brightness_move: stop` leaves a color temperature fade
    running to its end** when brightness and color temperature fade together. Possibly the same gap as item 2,
    fixed by a `stopMoveStep`; untested. Probe it on a Hue CT bulb before filing, and file it separately: a color
    temperature stop that jumps whichever command halts it is a different problem.

## Not worth filing

- **Hue bridge behavior:** a `grouped_light` write misses lights that are off, there is no xy stop, a dimming stop
  is refused during a soft off, and timers survive on and off. Signify firmware and API, not HA or aiohue.
- **The `predicted_state` report filter** edits aiohue's event dicts before its controllers run. A supported hook
  would be fair to ask aiohue for, but few others need one.
- **Firmware:** the Sengled E11-G13 jumping to full, the Tuya TS011F countdown, a WiZ plug never reporting OnTime
  on its subscription. Vendor problems; a report to WiZ at most.
- **ZHA group commands give no delivery feedback.** That is how a Zigbee groupcast works.
