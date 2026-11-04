# Device Side

[![HACS Default](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz/) [![Latest Version](https://img.shields.io/github/v/release/jasonmx/device-side?sort=date)](https://github.com/jasonmx/device-side/releases) [![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buymeacoffee&logoColor=black)](https://www.buymeacoffee.com/jasonmx)

Device Side unlocks native features in lights on the Zigbee and Philips Hue integrations, lights, switches and plugs on Shelly, and switches and plugs on Matter. It allows you to:

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

| Feature                                                                             | ZHA | Z2M | Shelly | Hue Bridge | Matter |
|:----------------------------------------------------------------------------------- |:---:|:---:|:------:|:----------:|:------:|
| [Delayed off](#delayed-off)                                                         | ✅   | ✅   | ✅      |            | ✅      |
| [Delayed on](#delayed-on)                                                           |     |     | ✅      |            |        |
| [Smooth dimming](#smooth-dimming)                                                   | ✅   | ✅   |        | ✅          |        |
| [Smooth saturation change](#smooth-color-transitions)                               | ✅   | ✅   |        | ✅          |        |
| [Smooth hue change](#smooth-color-transitions)                                      | ✅   | ✅   |        |            |        |
| [Set brightness, color or CT<br>without turning on](#set-lights-without-turning-on) | ✅   | ✅   |        | ✅          |        |
| [Set scene without turning on](#set-lights-without-turning-on)                      |     |     |        | ✅          |        |
| [Get attributes](#get-attributes)                                                   | ✅   | ✅   | ✅      | ✅          | ✅      |

Details per integration are in [docs/integrations.md](docs/integrations.md).

**Warning:** Some devices accept commands for features that they don't fully support. Test each of your devices with Device Side before relying on device-native features.

### Delayed Off

Action: `turn_on_for`

Turn on, then off after a delay. Timer runs on the device. Example use cases:

- Cut power to a heater or ironing station after 4 hours, in case someone leaves it on.
- Run a fan for 20 minutes after a shower.

### Delayed On

Action: `turn_off_for`

Turn off, then on after a delay. Timer runs on the device. Example use case:

- Power-cycle a router.

### Smooth Dimming

Actions: `raise_brightness`, `lower_brightness`, `stop`

Create "press to dim, release to stop" automations. Transitions run natively on the device.

### Smooth Color Transitions

Actions: `raise_saturation`, `lower_saturation`, `raise_hue`, `lower_hue`, `stop`

Create "press to change color, release to stop" automations. Transitions run natively on the device.

### Set Lights Without Turning On

Actions: `set_attributes`, `set_scene`

Set scenes, brightness, color and color temperature while the lights are off, so that they turn on smoothly without unsightly color or brightness flashes.

### Get Attributes

Action: `get_attributes`

Read device attributes that aren't exposed reliably by Home Assistant:

* Check a device's on/off timer.

* Check brightness, color or color temperature while a light is off or transitioning.

### Usability patches

* **Color lights on Zigbee2MQTT:**

  * Home Assistant shows the wrong color for full-color bulbs in hue-saturation (HS) mode. Device Side fixes this by [announcing both of their color modes](docs/integrations.md#what-device-side-changes-in-zigbee2mqtt).

  * Hue bulbs: before a delayed off with a color, Device Side turns on Z2M's Hue native control setting for that bulb, so it comes on in the new color instead of flashing its last one.

* **Hue Bridge:** When a brightness move starts, the bridge reports its target brightness (e.g. 0% or 100%) to Home Assistant, which is jarring for moves that you plan to stop. Device Side suppresses the bridge's report when a transition starts, and reports the new brightness once the transition stops.

The HS mode and Hue Bridge patches are on by default; turn them off in Device Side's options.

## Get Started

### Requirements

* At least one of the [ZHA](https://www.home-assistant.io/integrations/zha/), [Z2M](https://www.zigbee2mqtt.io) via [MQTT](https://www.home-assistant.io/integrations/mqtt/), [Shelly](https://www.home-assistant.io/integrations/shelly/), [Hue](https://www.home-assistant.io/integrations/hue) or [Matter](https://www.home-assistant.io/integrations/matter/) integrations installed.

* Not supported yet: Hue Bridge v1, Shelly Gen 1, Zigbee plugs/switches, Matter lights

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

### Coming from [Hue Smooth Dimming](https://github.com/jasonmx/hue-smooth-dimming)

Device Side's actions are drop-in replacements for Hue Smooth Dimming, apart from a name change on the `raise` and `lower` actions. To migrate to Device Side, make these YAML edits in your automations:

* change `hue_dimmer` to `device_side`. E.g. `hue_dimmer.stop` → `device_side.stop`

* change `raise` to `raise_brightness`

* change `lower` to `lower_brightness`

## Usage

### Delayed Off/On

**Delayed off:** `device_side.turn_on_for` turns on, then off automatically after a delay.

| Field               | Description                                                                                                            |
|:------------------- |:---------------------------------------------------------------------------------------------------------------------- |
| `target`            | Lights and switches (required)                                                                                         |
| `duration`          | Delay until the device turns off (required). Up to 7 days on Shelly, 6,553.4 s (about 1 h 49 min) on Zigbee and Matter |
| `brightness`        | Brightness (1–255). ZHA, Z2M, Shelly                                                                                   |
| `color_temp_kelvin` | Color temperature (2000–6500 K). ZHA, Z2M, Shelly                                                                      |
| `rgb_color`         | Color as `[red, green, blue]` (0–255 each). Z2M, Shelly                                                                |
| `hs_color`          | Color as `[hue, saturation]` (0–360, 0–100). Z2M                                                                       |
| `xy_color`          | Color as `[x, y]`. Z2M                                                                                                 |
| `transition`        | Fade time (0–300 s). Z2M, Shelly                                                                                       |
| `response_variable` | Variable that receives the response from each entity (optional)                                                        |

**Delayed on:** `device_side.turn_off_for` turns off, then on automatically after a delay.

| Field               | Description                                                     |
|:------------------- |:--------------------------------------------------------------- |
| `target`            | Shelly lights and switches (required)                           |
| `duration`          | Delay until the device turns on (required). Up to 7 days        |
| `response_variable` | Variable that receives the response from each entity (optional) |

**Cancel:** The following actions cancel a delayed on/off timer:

* Turn off a device that was on, or vice versa

* Send a new delayed on/off command (restarts the countdown)

* Send `turn_on` to a device that's already on (Shelly, and most lights on Z2M)

* Send `turn_off` to a device that's already off (Shelly only)

#### Results

Each targeted entity reports a `status` in the response variable:

| Status      | Meaning                                            |
| ----------- | -------------------------------------------------- |
| `confirmed` | Command accepted; device reported a running timer  |
| `sent`      | Command accepted; timer not confirmed in read-back |
| `unchanged` | Nothing to send; `detail` says why                 |

If a requested duration is out of range, `clamped_to` reports the duration the device actually used, in seconds. A field the entity can't take, like brightness on a plug, is dropped and the rest of the call goes ahead, with `detail: fields_dropped`.

If a device fails, the action fails and stops the automation.

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

### Smooth Dimming

| Action                         | Description                                    |
|:------------------------------ |:---------------------------------------------- |
| `device_side.raise_brightness` | Start raising brightness, turning the light on |
| `device_side.lower_brightness` | Start lowering brightness                      |
| `device_side.stop`             | Freeze every move on the target where it is    |

| Field        | Description                                                                                                                                |
|:------------ |:------------------------------------------------------------------------------------------------------------------------------------------ |
| `target`     | Lights and groups (required)                                                                                                               |
| `sweep_time` | Seconds a full 0–100% sweep takes (default 5 s). Raise and lower only                                                                      |
| `limit`      | Raise: maximum brightness (default 100%).<br>Lower: minimum brightness (default 0%). The light turns off at 0%; choose 0.4%+ to keep it on |

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

### Smooth Color Transitions

| Action                         | Description                                                     |
|:------------------------------ |:--------------------------------------------------------------- |
| `device_side.raise_saturation` | Start raising saturation, toward a richer color                 |
| `device_side.lower_saturation` | Start lowering saturation, toward white                         |
| `device_side.raise_hue`        | Start cycling hue: red, yellow, green, blue. Runs until `stop`  |
| `device_side.lower_hue`        | Start cycling hue: red, magenta, blue, green. Runs until `stop` |
| `device_side.stop`             | Freeze every move on the target where it is                     |

| Field        | Description                                                                                                       |
|:------------ |:----------------------------------------------------------------------------------------------------------------- |
| `target`     | Lights and groups (required)                                                                                      |
| `sweep_time` | Seconds a full 0–100% saturation sweep or one turn of the color wheel takes (default 5 s). Raise and lower only   |
| `limit`      | Raise saturation: maximum (default 100%).<br>Lower saturation: minimum (default 0%). <br/>Hue moves take no limit |

Groups move in step, as for dimming.

#### YAML Example: Hold to cycle color

```yaml
button_held:
  - action: device_side.raise_hue

button_released:
  - action: device_side.stop
```

***

### Set Lights Without Turning On

**Set brightness, color or CT:** `device_side.set_attributes` sets brightness, color temp or color without changing on/off state.

| Field               | Description                                 |
|:------------------- |:------------------------------------------- |
| `target`            | Lights and groups (required)                |
| `brightness`        | Brightness level (%)                        |
| `min_brightness`    | Enforce a minimum brightness (%)            |
| `max_brightness`    | Enforce a maximum brightness (%)            |
| `color_temp_kelvin` | Color temperature (K)                       |
| `rgb_color`         | Color as `[red, green, blue]` (0–255 each)  |
| `hs_color`          | Color as `[hue, saturation]` (0–360, 0–100) |
| `xy_color`          | Color as `[x, y]`                           |

**Set scene:** `device_side.set_scene` sets a Hue scene without turning its lights on.

| Field    | Description           |
|:-------- |:--------------------- |
| `target` | Hue scenes (required) |

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

`device_side.get_attributes` returns one record per target, containing:

* Brightness, color temp and color (RGB, HS, XY) of lights, even while off or moving.

* Any delayed on/off timer running on the device.

| Field    | Description                    |
|:-------- |:------------------------------ |
| `target` | Lights and switches (required) |

A record holds the keys the device reports: `brightness` (%), `color_temp_kelvin`, `rgb_color`, `hs_color`, `xy_color`, and `timer` while one is running.

The `timer` key holds `turns` (`on` or `off`), `ends_at` (UTC) and `remaining_s`.

#### YAML Example: How long until the heater turns off

```yaml
actions:
  - action: device_side.get_attributes
    target:
      entity_id: switch.heater
    response_variable: result
  - action: notify.notify
    data:
      message: >
        {% set timer = result['switch.heater'].get('timer') %}
        {% if timer %}Heater turns {{ timer.turns }} in {{ (timer.remaining_s / 60) | round | int }} min.
        {% else %}No heater timer running.{% endif %}
```

***

## Uninstall

This integration follows standard integration removal.

1. Open the integration

   [![Open the Device Side integration in your Home Assistant instance.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=device_side)

2. Open the ⋮ menu and choose **Delete**
