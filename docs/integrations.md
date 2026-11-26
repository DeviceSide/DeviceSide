# Integrations

What the [README](../README.md) features do on every integration, and what none can do. Each integration has its own
page, with its limits and what DeviceSide changes in your setup:

<!-- integrations:start -->
- [Zigbee2MQTT](integrations/zigbee2mqtt/index.md)
- [ZHA](integrations/zha/index.md)
- [Shelly](integrations/shelly/index.md)
- [Hue](integrations/hue/index.md)
- [Matter](integrations/matter/index.md)
- [Control4](integrations/control4/index.md)
<!-- integrations:end -->

What holds for a brand on both Zigbee integrations is on the [Zigbee page](integrations/zigbee.md). Which devices
each feature is proven on is on the [device compatibility page](device-compatibility.md). How the
commands work on the wire, and what was measured on real bulbs, is in [internals.md](internals.md) and each integration's own.

## All integrations

- **Refused targets.** A target that can't take an action fails the call if you named it, and is skipped if it
  came through an area, device, label or group ([action-behavior.md](action-behavior.md)). The error names the
  reason, such as `not_built`.
- **Groups.** For timers and smooth moves, Zigbee2MQTT and ZHA groups, Hue rooms and zones, and Control4 light groups get one
  command, so their lights move together. `set_attributes` writes a ZHA group's or Hue room's lights one by one. A group
  that can't take a call falls back to its lights, each on its own (the rules: Native groups in
  [`core/dispatcher.py`](../custom_components/deviceside/core/dispatcher.py); each integration's page lists its cases).
  Any other group, such as a light group helper, is expanded and each light gets its own command.
- **Switches shown as lights.** A light made from a supported switch with Home Assistant's "Change device type of a
  switch" helper is treated as that switch: light fields are dropped and the timer still runs. An inverted one is
  refused (`inverted_wrapper`).
- **No color temperature moves.** Every stop of a color temperature fade on a Hue bulb, the Hue bridge's own
  included, makes a visible jump, so there is no raise or lower for it.
- **Fades pick up where the last one stopped.** DeviceSide remembers each raise, lower and `stop` for a few
  seconds after it ends (2 s on Zigbee, 15 s on Hue), so releasing and pressing again doesn't jump. A light
  command from Home Assistant clears it at once; a change from a remote or app in that window may be missed.
- **Dimming to 0 % is a soft off.** The light fades out and keeps its level, so a plain turn on brings it back
  there. Raising brightness on a light that is off fades in from the bottom.

## Home Assistant scenes

`set_scene` takes a scene made in Home Assistant, in the UI or in YAML, as well as a Hue bridge scene
([Hue](integrations/hue/index.md)). It writes each of the scene's lights as set without turning on does, so it works
wherever that does (the [feature table](device-compatibility.md) shows where), with each light's own [evidence
level](evidence.md#levels). It reads the scene each time it runs, so an edit applies at once.

- **A light the scene holds on** gets the scene's brightness and its one color, picked by the state's color mode, as
  Home Assistant picks it when it activates the scene (RGBW and RGBWW take the scene's hue and saturation). It stays
  off if it was off, and changes at once if it was on. Effects and transitions aren't written.
- **A light the scene holds off** is turned off, by Home Assistant's own turn off.
- **A light DeviceSide can't write** (no adapter, a refused class, a Labs class with Labs off) is skipped and logged,
  and the rest run, as in a group; an unavailable light is left out quietly. Switches, covers and the scene's other
  non-light entities are left alone.
- **Groups in the scene**, light group helpers and native groups alike, are handled as in any call.

The response has one entry for the scene ([action-behavior.md](action-behavior.md#what-a-response-looks-like)).

## What can't be done, and why

The README's prohibited signs mark these: a feature that is impossible on that whole integration, for every device
we know of. Each is a limit of the device protocol or the bridge, not a feature waiting to be built. A feature only
some devices can't do is not marked there.

- **Turn off with timer on Matter, and on Zigbee groups and Zigbee devices other than Tuya's.** The Zigbee and
  Matter timer command (`OnWithTimedOff`) turns a device on, then off. There is no command for off, then on, so
  Matter, Zigbee groups and non-Tuya Zigbee lights and switches have no call for it. Tuya's Zigbee devices have
  one: Tuya's own countdown toggles the device when it ends. DeviceSide sends it to the Tuya datapoint devices with one
  countdown on Zigbee2MQTT
  ([Zigbee2MQTT](integrations/zigbee2mqtt/index.md#tuya-datapoint-devices-with-one-countdown)), and a group with
  one falls back to its devices. On Tuya's other devices it isn't built yet; some Tuya firmware also toggles on
  `OnWithTimedOff` from off, though not all (one TS011F ignores it when off).
- **Turn on or off with timer on Hue.** The bridge's own timers keep running through a plain on or off, from Home
  Assistant, the Hue app or a dimmer switch, and the Hue app doesn't show them. To time Hue bulbs, pair them with
  ZHA, Zigbee2MQTT or Matter.
- **Smooth hue change on Hue.** A trip around the color wheel isn't a straight line the bridge can fade along.
  Smooth saturation changes work.

## Zigbee plugs and switches

`turn_on_for` isn't built for Zigbee plugs and switches, but for the Zigbee2MQTT Tuya countdown plugs
([TS011F](integrations/zigbee2mqtt/index.md#tuya-ts011f-plugs)) and Tuya datapoint devices with one countdown
([datapoint](integrations/zigbee2mqtt/index.md#tuya-datapoint-devices-with-one-countdown)), which DeviceSide drives by
Tuya's own countdown; [ZHA doesn't support it yet](integrations/zha/index.md#tuya-plugs-and-switches). Few devices honor
the Zigbee timer command ([the Zigbee timer](integrations/zigbee.md#the-zigbee-timer)): IKEA's are moving to Thread,
and Sonoff and Tuya run their own countdowns.

`set_auto_off` and `clear_auto_off` on Zigbee are built on Zigbee2MQTT alone, for Sonoff's single-channel relays and two
Tuya switches ([Sonoff](integrations/zigbee2mqtt/index.md#sonoff-inching-relays),
[Tuya](integrations/zigbee2mqtt/index.md#tuya-inching-switches)). The setting can't be read back, so the result is
`sent`; ZHA has no call to send yet.

Each maker's level is on the [compatibility page](device-compatibility.md#zigbee2mqtt). A contributor with a plug that
passes can add it ([how to help](../CONTRIBUTING.md#how-to-help)).
