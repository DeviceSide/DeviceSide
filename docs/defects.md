# Upstream defects

Workarounds DeviceSide carries for behavior in Home Assistant Core that could be fixed upstream. Each integration's
own, in the libraries and firmware it drives, are under Upstream defects in its internals:
[Shelly](integrations/shelly/internals.md#upstream-defects),
[Zigbee2MQTT](integrations/zigbee2mqtt/internals.md#upstream-defects),
[ZHA](integrations/zha/internals.md#upstream-defects), [Matter](integrations/matter/internals.md#upstream-defects) and
[Hue](integrations/hue/internals.md#upstream-defects).

Search each tracker for duplicates before filing: only the issues our code already cites (Koenkk/zigbee2mqtt#28757,
#33025) have been checked upstream.

## Core

- **HA Core (zha and hue lights): the level kept for the next plain on overrides one the bulb stored while off**
  (ZHA's `_off_brightness`, Hue's `_last_brightness` and `_restore_brightness`). Workaround: overwriting those
  private attributes (`core/ha_entity.replace_if_set`), our most fragile one. Fix: drop the kept level when a
  report shows the level changed while off, or a supported way to set it. Intentional behavior (a fade-off keeps
  its level), so expect pushback, but a rename in core silently breaks us.
- **HA Core MQTT light: a state whose `color_mode` isn't in `supported_color_modes` is dropped,** keeping the old
  color. Accepting or converting it would fix every MQTT integration, not just Z2M. Core is strict about color
  modes.
- **HA Core zha: a public accessor for the gateway.** Importing it means declaring `after_dependencies`, which
  holds our setup while ZHA is stuck, so we read `hass.data["zha"]` (`zcl.gateway`). A nice-to-have for one
  consumer.

## Not worth filing

- **Firmware:** the Tuya TS011F countdown, on ZHA and Zigbee2MQTT alike
  ([device compatibility](device-compatibility.md#tuya-ts011f)). A vendor problem.
