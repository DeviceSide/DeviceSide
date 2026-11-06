# DeviceSide

[![HACS Default](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz/) [![Latest Version](https://img.shields.io/github/v/release/jasonmx/DeviceSide?sort=date)](https://github.com/jasonmx/DeviceSide/releases) ![Installs](https://img.shields.io/badge/dynamic/json?color=blue&label=Installs&query=deviceside.total&url=https://analytics.home-assistant.io/custom_integrations.json) [![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buymeacoffee&logoColor=black)](https://www.buymeacoffee.com/jasonmx)

DeviceSide unlocks native features in your lights, switches and plugs on Zigbee, Shelly, Philips Hue and Matter.

## Key Features

* **Auto-off/on:** Turn devices off/on automatically, even if HA goes offline or restarts.

* **Dim smoothly:** Press to dim and release to stop, using third-party buttons. No more jittery steps or overshoots.

* **Change colors smoothly:** Press to change hue or saturation, release to stop.

* **Flash-free turn-on:** Set brightness, color, color temperature or scenes without turning the lights on

* **Zero setup:** Connects to your devices automatically via the core integrations

| Feature by Integration                                                              | ZHA | Z2M | Shelly | Hue Bridge | Matter |
|:----------------------------------------------------------------------------------- |:---:|:---:|:------:|:----------:|:------:|
| [Turn on with timer](#turn-on-with-timer)                                           | ✅   | ✅   | ✅      |            | ✅      |
| [Turn off with timer](#turn-off-with-timer)                                         |     |     | ✅      |            |        |
| [Auto-off/on (aka inching)](#auto-off-and-auto-on)                                  |     |     | ✅      |            |        |
| [Smooth dimming](#smooth-dimming)                                                   | ✅   | ✅   |        | ✅          |        |
| [Smooth saturation change](#smooth-color-transitions)                               | ✅   | ✅   |        | ✅          |        |
| [Smooth hue change](#smooth-color-transitions)                                      | ✅   | ✅   |        |            |        |
| [Set brightness, color or CT<br>without turning on](#set-lights-without-turning-on) | ✅   | ✅   |        | ✅          |        |
| [Set scene without turning on](#set-lights-without-turning-on)                      |     |     |        | ✅          |        |
| [Get attributes](#get-attributes)                                                   | ✅   | ✅   | ✅      | ✅          | ✅      |

Details per integration are in [docs/integrations.md](docs/integrations.md). Tested models and support levels are on the [compatibility page](docs/compatibility.md).

### Will it work with my device?

Maybe. A key reason these features aren't supported in HA core is that device makers implement them inconsistently. So the first release of DeviceSide only supports devices I could probe and test myself on an automated rig. Each ✅ above indicates a feature that works on at least one device per integration.

If you own a device that isn't [listed as tested](https://github.com/jasonmx/DeviceSide/blob/main/docs/compatibility.md), please try it and report the result.

## Get started

### Requirements

* At least one of the [ZHA](https://www.home-assistant.io/integrations/zha/), [Z2M](https://www.zigbee2mqtt.io) via [MQTT](https://www.home-assistant.io/integrations/mqtt/), [Shelly](https://www.home-assistant.io/integrations/shelly/), [Hue](https://www.home-assistant.io/integrations/hue) or [Matter](https://www.home-assistant.io/integrations/matter/) integrations installed.

* Not supported yet: Hue Bridge v1, Shelly Gen 1, Zigbee plugs/switches

### Install from Marketplace

<details>
<summary>Show me how</summary>

1. Open the DeviceSide repository

   [![Open the DeviceSide HACS repository in your Home Assistant instance.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jasonmx&repository=DeviceSide&category=integration)

2. Click **Download**

3. Restart Home Assistant

4. Add the integration

   [![Add DeviceSide to your Home Assistant instance.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=deviceside)

</details>

<details>
<summary>Coming from Hue Smooth Dimming?</summary>

DeviceSide's actions are drop-in replacements for [Hue Smooth Dimming](https://github.com/jasonmx/hue-smooth-dimming), apart from a name change on the `raise` and `lower` actions. To migrate to DeviceSide, make these changes to your YAML:

* `hue_dimmer.raise` → `deviceside.raise_brightness`
* `hue_dimmer.lower` → `deviceside.lower_brightness`
* `hue_dimmer` → `deviceside`

</details>

## Usage

### Turn on with timer

Action: `turn_on_for`

Also known as `on with timed off` (Zigbee, Matter), `on_time` (Zigbee2MQTT), `toggle_after` (Shelly), and `countdown`.

Turn on, then off after a delay. Timer runs on the device, for this turn-on only: it doesn't change a Shelly's own [Auto-off](#auto-off-and-auto-on) setting. Example use case:

- Run a fan for 20 minutes after a shower.

###### Example: heater off after 4 hours, with a warning

```yaml
actions:
  - action: deviceside.turn_on_for
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

| Field               | Description                                                                                                            |
|:------------------- |:---------------------------------------------------------------------------------------------------------------------- |
| `target`            | Lights and switches (required)                                                                                         |
| `duration`          | Delay until the device turns off (required). Up to 7 days on Shelly, 6,553.4 s (about 1 h 49 min) on Zigbee and Matter |
| `brightness`        | Brightness (minimum 0.4%). ZHA, Z2M, Shelly                                                                            |
| `color_temp_kelvin` | Color temperature (2000–6500 K). ZHA, Z2M, Shelly                                                                      |
| `rgb_color`         | Color as `[red, green, blue]` (0–255 each). Z2M, Shelly                                                                |
| `hs_color`          | Color as `[hue, saturation]` (0–360, 0–100). Z2M, Shelly                                                               |
| `xy_color`          | Color as `[x, y]`. Z2M, Shelly                                                                                         |
| `transition`        | Fade time (0–300 s). Z2M, Shelly                                                                                       |
| `response_variable` | Variable that receives the response from each entity (optional)                                                        |

<details>
<summary>Results</summary>

Each targeted entity reports a `status` in the response variable:

| Status      | Meaning                                            |
| ----------- | -------------------------------------------------- |
| `confirmed` | Command accepted; device reported a running timer  |
| `sent`      | Command accepted; timer not confirmed in read-back |
| `unchanged` | Nothing to send; `detail` says why                 |

If a requested duration is out of range, `clamped_to` reports the duration the device actually used, in seconds. A field the entity can't take, like brightness on a plug, is dropped and the rest of the call goes ahead, with `detail: fields_dropped`.

If a device fails, the action fails and stops the automation.

</details>

#### Cancel a timer

The following actions cancel a `turn_on_for` timer:

* Turn off

* Start a new timer (replaces the old timer)

* Turn on (i.e. leave on). Tested on Shelly only

### Turn off with timer

Action: `turn_off_for`

Turn off, then on after a delay. Timer runs on the device. Example use case:

- Power-cycle a router.

| Field               | Description                                                     |
|:------------------- |:--------------------------------------------------------------- |
| `target`            | Shelly lights and switches (required)                           |
| `duration`          | Delay until the device turns on (required). Up to 7 days        |
| `response_variable` | Variable that receives the response from each entity (optional) |

<details>
<summary>Results</summary>

Each targeted entity reports a `status` in the response variable:

| Status      | Meaning                                            |
| ----------- | -------------------------------------------------- |
| `confirmed` | Command accepted; device reported a running timer  |
| `sent`      | Command accepted; timer not confirmed in read-back |
| `unchanged` | Nothing to send; `detail` says why                 |

If a requested duration is out of range, `clamped_to` reports the duration the device actually used, in seconds.

If a device fails, the action fails and stops the automation.

</details>

#### Cancel a timer

The following actions cancel a `turn_off_for` timer:

* Turn on

* Start a new timer with either action (restarts the countdown)

* Turn off (i.e. leave off)

### Auto-off (aka inching) and auto-on

Actions: `set_auto_off`, `set_auto_on`, `clear_auto_off`, `clear_auto_on`

Configure a persistent auto-off delay, that fires on every turn-on (and vice versa) independent of Home Assistant. Example use cases:

- Inch a garage door by pulsing its relay for 1 second.
- Turn off an ironing station automatically after an hour.

>  [!NOTE] Devices go unavailable briefly after each config change, while the Shelly integration reloads them.

###### Example: garage door inching

```yaml
action: deviceside.set_auto_off
target:
  entity_id: switch.garage_door
data:
  duration: 1
```

| Field               | Description                                                     |
|:------------------- |:--------------------------------------------------------------- |
| `target`            | Shelly lights and switches (required)                           |
| `duration`          | Delay until the device turns off/on. Up to 7 days (required)    |
| `response_variable` | Variable that receives the response from each entity (optional) |

`clear_auto_off` and `clear_auto_on` take only a target.

<details>
<summary>Results</summary>

Each targeted entity reports a `status` in the response variable:

| Status      | Meaning                                                   |
| ----------- | --------------------------------------------------------- |
| `confirmed` | Setting written; the device reported it in read-back      |
| `sent`      | Setting written; not confirmed in read-back               |
| `unchanged` | The device already holds this setting, so nothing is sent |

If a device fails, the action fails and stops the automation.

</details>

### Smooth dimming

Create "press to dim, release to stop" automations. Transitions run natively on the device.

###### Example: two-button dimmer

```yaml
left_button_held:
  - action: deviceside.lower_brightness

right_button_held:
  - action: deviceside.raise_brightness

buttons_released:
  - action: deviceside.stop
```

| Action             | Description                                    |
|:------------------ |:---------------------------------------------- |
| `raise_brightness` | Start raising brightness, turning the light on |
| `lower_brightness` | Start lowering brightness                      |
| `stop`             | Freeze the move                                |

| Field        | Description                                                                                                                                |
|:------------ |:------------------------------------------------------------------------------------------------------------------------------------------ |
| `target`     | Lights and groups (required)                                                                                                               |
| `sweep_time` | Duration of a full 0–100% sweep (default 5s)                                                                                               |
| `limit`      | Raise: maximum brightness (default 100%).<br>Lower: minimum brightness (default 0%). The light turns off at 0%; choose 0.4%+ to keep it on |

To dim multiple Zigbee lights together, target a Hue, Z2M or ZHA group instead of separate lights or an HA group. Native groups move in sync via group-wide Zigbee messages.

### Smooth color changes

Create "press to change color, release to stop" automations. Transitions run natively on the device.

###### Example: hold to cycle color

```yaml
button_held:
  - action: deviceside.raise_hue

button_released:
  - action: deviceside.stop
```

| Action             | Description                                                     |
|:------------------ |:--------------------------------------------------------------- |
| `raise_saturation` | Start raising saturation, toward a richer color                 |
| `lower_saturation` | Start lowering saturation, toward white                         |
| `raise_hue`        | Start cycling hue: red, yellow, green, blue. Runs until `stop`  |
| `lower_hue`        | Start cycling hue: red, magenta, blue, green. Runs until `stop` |
| `stop`             | Freeze the move                                                 |

| Field        | Description                                                                                                       |
|:------------ |:----------------------------------------------------------------------------------------------------------------- |
| `target`     | Lights and groups (required)                                                                                      |
| `sweep_time` | Duration of a full 0–100% saturation sweep or 360º hue sweep (default 5s)                                         |
| `limit`      | Raise saturation: maximum (default 100%).<br>Lower saturation: minimum (default 0%). <br/>Hue moves take no limit |

Groups move in step, as for dimming.

### Flash-free turn-on

Set brightness, color temperature, color or scenes while the lights are off, so that they turn on predictably without unsightly color or brightness flashes.

###### Example: set scene for next turn-on

```yaml
description: Stage the Relax scene in the living room at 22:00, without turning the lights on.
triggers:
  - trigger: time
    at: "22:00:00"
actions:
  - action: deviceside.set_scene
    target:
      entity_id: scene.living_room_relax
```

###### GUI example: rearm turn-on brightness after turn-off

See [docs/examples/set-turn-on-brightness.md](docs/examples/set-turn-on-brightness.md).

#### Set brightness, color temperature or color without turning on

Action: `set_attributes`

Sets brightness, color temperature or color without changing on/off state.

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

#### Set scene without turning on

Action: `set_scene`

Currently implemented for Hue scenes on the Hue integration only.

| Field    | Description          |
|:-------- |:-------------------- |
| `target` | Hue scene (required) |

### Get attributes

Action: `deviceside.get_attributes`

Read device attributes that aren't exposed reliably by Home Assistant:

* Check a device's on/off timer and auto-off/on settings.

* Check a light's brightness, color or color temperature while it's off or transitioning.

###### Example: how long until the heater turns off

```yaml
actions:
  - action: deviceside.get_attributes
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

| Field    | Description                    |
|:-------- |:------------------------------ |
| `target` | Lights and switches (required) |

A record holds the keys the device reports: `brightness` (%), `color_temp_kelvin`, `rgb_color`, `hs_color`, `xy_color`, `timer`, `auto_off` and `auto_on`.

* When a timer is running, the `timer` key holds `turns` (`on` / `off`), `ends_at` (UTC) and `remaining_s`.

* On devices that support auto-off/on, `auto_off` and `auto_on` each hold `duration` (seconds) while set and are `null` while clear. A missing record means the setting couldn't be read.

## Usability patches

* **Color lights on Zigbee2MQTT:**

  * Home Assistant shows the wrong color for full-color bulbs in hue-saturation (HS) mode. DeviceSide fixes this by [announcing both XY and HS color modes](docs/integrations.md#what-deviceside-changes-in-zigbee2mqtt).

  * Hue bulbs: before a `turn_on_for` with a color, DeviceSide enables Z2M's Hue native control for that bulb, so it turns on without flashing its old color.

* **Hue Bridge:** When a brightness move starts, the bridge reports its target brightness (e.g. 0% or 100%) to Home Assistant, which is jarring for moves that you plan to stop. DeviceSide suppresses the bridge's report as a transition starts, and reports the new brightness once the transition stops.

The HS mode and Hue Bridge patches are on by default; turn them off in **Configure > Settings**.

## Uninstall

This integration follows standard integration removal.

1. Open the integration

   [![Open the DeviceSide integration in your Home Assistant instance.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=deviceside)

2. Open the ⋮ menu and choose **Delete**
