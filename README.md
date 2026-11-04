# Device Side

[![HACS Default](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz/) [![Latest Version](https://img.shields.io/github/v/release/jasonmx/device-side?sort=date)](https://github.com/jasonmx/device-side/releases) [![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buymeacoffee&logoColor=black)](https://www.buymeacoffee.com/jasonmx)

Device Side unlocks native features in your lights, switches and plugs on the Zigbee, Shelly, Philips Hue and Matter integrations. It allows you to:

* **Delay a turn-off:** Tell a device to turn off automatically, even if HA goes offline.

* **Dim smoothly:** Press to dim and release to stop, using third-party buttons.

* **Change colors smoothly:** Press to change color, release to stop.

* **Set lights without turning on:** Pre-stage brightness, color, CT and scenes.

Device Side also patches some usability quirks in individual integrations.

## How It Helps You 🔅💡🔆

* **Convenient & reliable:** Use one-shot actions that survive HA restarts.
* **Silky smooth:** Brightness and color transitions are continuous and precise. No more jittery steps or overshoots.
* **Predictable:** Prepare your lights to turn on how you want them, without unsightly color flashes or brightness extremes.
* **Zero setup:** Connects to your devices automatically via the core integrations.

## Features

| Action                                 | ZHA | Zigbee2MQTT | Shelly | Hue Bridge | Matter |
|:-------------------------------------- |:---:|:-----------:|:------:|:----------:|:------:|
| `turn_on_for`                          | ✅  | ✅          | ✅     |            | ✅     |
| `turn_off_for`                         |     |             | ✅     |            |        |
| `raise_brightness`, `lower_brightness` | ✅  | ✅          |        | ✅         |        |
| `raise_saturation`, `lower_saturation` | ✅  | ✅          |        | ✅         |        |
| `raise_hue`, `lower_hue`               | ✅  | ✅          |        |            |        |
| `stop`                                 | ✅  | ✅          |        | ✅         |        |
| `set_attributes`                       | ✅  | ✅          |        | ✅         |        |
| `set_scene`                            |     |             |        | ✅         |        |
| `get_attributes`                       | ✅  | ✅          | ✅     | ✅         | ✅     |

### Timed on/off

Turn on or off, with a delayed flip back. Flip-back timer runs on the device. Example use cases:

- Cut power to a heater or ironing station after 4 hours, in case someone forgets to turn it off.
- Run a bathroom fan for 20 minutes after a shower.
- Power-cycle your router via a smart plug.

### Smooth Dimming & Color Transitions

Create polished “press to dim or change color, release to stop" automations. Transitions run natively on the device, with one command to start and a second to stop.

### Set Lights Without Turning On

Set scenes, brightness, color and color temperature while the lights are off, so that they turn on smoothly without unsightly color or brightness flashes.

### Get Attributes

Read device attributes that aren't exposed reliably by Home Assistant. Example use cases:

* Check a device's on/off timer.

* Check a light's brightness, color or color temperature while it's off or transitioning.

### Usability patches

* On Zigbee2MQTT, Device Side fixes Home Assistant showing the wrong color for full-color bulbs, by [announcing both of their color modes](docs/integrations.md#what-device-side-changes-in-zigbee2mqtt).

* When a brightness move starts, the Hue bridge reports its target brightness (e.g. 0% or 100%), which is jarring on moves that you plan to stop. Device Side shows the starting brightness until the transition ends or is stopped, and then shows the new brightness.

These are on by default; turn them off in Device Side's options.

Details per integration are in [docs/integrations.md](docs/integrations.md), including the Zigbee2MQTT options Device Side sets on your devices.

**Disclaimer:** Some devices pretend to support features that they don't. Test each of your devices with the Device Side actions before relying on device-native features.

## Get Started

### Requirements

* At least one of [ZHA](https://www.home-assistant.io/integrations/zha/), [Z2M](https://www.zigbee2mqtt.io) via [MQTT](https://www.home-assistant.io/integrations/mqtt/), [Shelly](https://www.home-assistant.io/integrations/shelly/), [Philips Hue](https://www.home-assistant.io/integrations/hue) or [Matter](https://www.home-assistant.io/integrations/matter/) integrations installed.

* Not supported: Hue Bridge v1, Shelly Gen 1, Zigbee plugs and switches

### Install from HACS

<details>
<summary>Show me how</summary>

1. Open the Device Side HACS repository

   [![Open the Device Side HACS repository in your Home Assistant instance.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jasonmx&repository=device-side&category=integration)

2. Click **Download**

3. Restart Home Assistant

4. Add the integration

   [![Add Device Side to your Home Assistant instance.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=device_side)

</details>

### Coming from Hue Smooth Dimming

Device Side's actions take the same fields. Change the domain from `hue_dimmer` to `device_side`, and rename `raise` to `raise_brightness` and `lower` to `lower_brightness`. Move your automations over, then remove Hue Smooth Dimming.

## Usage

### Timed on/off

| Action                     | Description                                     |
|:-------------------------- |:----------------------------------------------- |
| `device_side.turn_on_for`  | Turns on, then off automatically after a delay. |
| `device_side.turn_off_for` | Turns off, then on automatically after a delay. |

| Field               | Actions     | Description                                                                                                           |
|:------------------- |:----------- |:--------------------------------------------------------------------------------------------------------------------- |
| `target`            | all         | Lights and switches (required)                                                                                        |
| `duration`          | all         | How long until the device toggles (required). Up to 7 days on Shelly, 1 h 49 min on Zigbee and Matter                |
| `brightness`        | turn_on_for | Brightness (1–255). ZHA, Z2M, Shelly                                                                                  |
| `color_temp_kelvin` | turn_on_for | Color temperature (2000–6500 K). ZHA, Z2M, Shelly                                                                     |
| `rgb_color`         | turn_on_for | Color as `[red, green, blue]` (0–255 each). Z2M, Shelly                                                               |
| `hs_color`          | turn_on_for | Color as `[hue, saturation]` (0–360, 0–100). Z2M                                                                      |
| `xy_color`          | turn_on_for | Color as `[x, y]`. Z2M                                                                                                |
| `transition`        | turn_on_for | Fade time (0–300 s). Z2M, Shelly                                                                                      |
| `response_variable` | all         | Name of a variable that receives a result for each entity (optional). In the visual editor it's **Response variable** |

**Cancel:** to cancel a timer, send a new action (e.g. `turn_on`, `turn_off`, `toggle` or a new timed on/off).
On ZHA, only `turn_off` or a new `turn_on_for` cancels; to keep the light on, turn it off, then on.

#### Results

Each targeted entity gets a `status` in the response variable:

| Status      | Meaning                                            |
| ----------- | -------------------------------------------------- |
| `confirmed` | Command accepted; device reported a running timer  |
| `sent`      | Command accepted; timer not confirmed in read-back |
| `unchanged` | Nothing to send; `detail` says why                 |

If a requested duration is out of range, `clamped_to` reports the duration the device actually used, in seconds. A field the entity can't take, like brightness on a plug, is dropped and the rest of the call goes ahead, with `detail: fields_dropped`.

Failures follow Home Assistant's own actions. The action fails, stopping the automation, if an entity you listed by name can't take it (the error says why) or if a device fails (every entity is still sent the command first, and the error lists the ones that failed). An entity reached through an area, device, label or group that can't take the action is skipped and logged, and unavailable entities are skipped. Skipped entities are left out of the response.

#### YAML Example: Heater off after 4 hours, with a warning

```yaml
actions:
  - action: device_side.turn_on_for
    target:
      entity_id: switch.heater
    data:
      duration: "04:00:00"
    response_variable: result
  - if: "{{ result['switch.heater'].status != 'confirmed' }}"
    then:
      - action: notify.notify
        data:
          message: "Heater timer not confirmed: {{ result['switch.heater'].status }}"
```

***

### Smooth Dimming & Color Transitions

| Action                         | Description                                                    |
|:------------------------------ |:-------------------------------------------------------------- |
| `device_side.raise_brightness` | Start raising brightness, turning the light on                 |
| `device_side.lower_brightness` | Start lowering brightness                                      |
| `device_side.raise_saturation` | Start raising saturation, toward a richer color                |
| `device_side.lower_saturation` | Start lowering saturation, toward white                        |
| `device_side.raise_hue`        | Start cycling hue: red, yellow, green, blue. Runs until `stop` |
| `device_side.lower_hue`        | Start cycling hue: red, magenta, blue, green. Runs until `stop` |
| `device_side.stop`             | Freeze every move on the target where it is                    |

| Field        | Actions                             | Description                                                                         |
|:------------ |:----------------------------------- |:----------------------------------------------------------------------------------- |
| `target`     | all                                 | Lights and groups (required)                                                        |
| `sweep_time` | raise, lower                        | Seconds a full 0–100% sweep takes, or one turn of the color wheel (default 5 s)     |
| `limit`      | raise_brightness, raise_saturation  | Maximum (default 100%)                                                              |
| `limit`      | lower_brightness                    | Minimum brightness (default 0%). The light turns off at 0%. Choose 0.4%+ to keep it on |
| `limit`      | lower_saturation                    | Minimum saturation (default 0%)                                                     |

To move several lights in step, target a Hue room or zone, or a Zigbee2MQTT or ZHA group, instead of separate lights. One group-wide Zigbee message then moves them together.

#### YAML Example: Two-button dimmer

```yaml
left_button_held:
  - action: device_side.lower_brightness

right_button_held:
  - action: device_side.raise_brightness

buttons_released:
  - action: device_side.stop
```

***

### Set Lights Without Turning On

| Action                       | Description                                                       |
|:---------------------------- |:----------------------------------------------------------------- |
| `device_side.set_scene`      | Set a Hue scene without turning its lights on                     |
| `device_side.set_attributes` | Set brightness, color temp or color without changing on/off state |

| Field               | Actions        | Description                                |
|:------------------- |:-------------- |:------------------------------------------ |
| `target`            | set_scene      | Hue scenes (required)                      |
| `target`            | set_attributes | Lights and groups (required)               |
| `brightness`        | set_attributes | Brightness level (%)                       |
| `min_brightness`    | set_attributes | Enforce a minimum brightness (%)           |
| `max_brightness`    | set_attributes | Enforce a maximum brightness (%)           |
| `color_temp_kelvin` | set_attributes | Color temperature (K)                      |
| `rgb_color`         | set_attributes | Color as `[red, green, blue]` (0–255 each) |
| `hs_color`          | set_attributes | Color as `[hue, saturation]` (0–360, 0–100) |
| `xy_color`          | set_attributes | Color as `[x, y]`                          |

#### YAML Example: Set scene for next turn-on

```yaml
description: Stage the Relax scene in the living room at 22:00, without turning the lights on.
triggers:
  - trigger: time
    at: "22:00:00"
actions:
  - action: device_side.set_scene
    target:
      entity_id: scene.living_room_relax
```

To set brightness for the next turn-on from the visual editor, see [docs/examples/set-turn-on-brightness.md](docs/examples/set-turn-on-brightness.md).

***

### Get Attributes

`device_side.get_attributes` returns one record per target: brightness, color temp and color (RGB, HS, XY), even while the light is off or moving, and any on/off timer running on the device.

| Field               | Description                                         |
|:------------------- |:--------------------------------------------------- |
| `target`            | Lights and switches (required)                      |
| `response_variable` | Name of a variable that receives the records (required) |

***

## Uninstall

This integration follows standard integration removal.

1. Open the integration

[![Open the Device Side integration in your Home Assistant instance.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=device_side)

2. Open the ⋮ menu and choose **Delete**
