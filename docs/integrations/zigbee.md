# Zigbee

What holds for a brand's devices on both Zigbee integrations, [Zigbee2MQTT](zigbee2mqtt/index.md) and
[ZHA](zha/index.md). Each integration's page says how it tells the brands apart and what differs on it; which devices
each feature is proven on is on the [device compatibility page](../device-compatibility.md).

## Why brands have classes

Zigbee devices given the same command can answer it differently, by brand and firmware
([research](zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)), so a test on one brand proves nothing about
another. Each integration gives a brand, or a model, that answers differently a class of its own.

## Smooth dimming and stop

A Zigbee 3.0 certified dimmable light must take the standard dimming and stop commands
([internals](../internals.md#shared)), and DeviceSide sends them to every brand's light exactly as it sends them to a
Hue bulb. So a brand's lights can take smooth dimming and stop with no test of their own. DeviceSide can't tell an
uncertified light apart, and one that fails the commands shows it at once.

## The Zigbee timer

Turn on with timer sends the standard Zigbee timer (`OnWithTimedOff`), counted in tenths of a second. Many devices
don't run it as the standard says:

| Devices | What the timer does | Source |
|---|---|---|
| IKEA TRÅDFRI lights | Most run it. Two GU10 white spectrum bulbs, LED2005R5 and LED2106R3, turn on with it and never turn off | [research](zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §3; [Zigbee2MQTT #29158](https://github.com/Koenkk/zigbee2mqtt/issues/29158) |
| Other brands' lights | Too few reports say a brand runs it, and some lights turn on and never off | [research](zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| Plugs and switches, Hue's and IKEA's included | Most ignore it or read it as a delayed toggle, so one could stay on | [Zigbee plugs and switches](../integrations.md#zigbee-plugs-and-switches) |
| Sengled bulbs | Not taken: the E11-G13 rejects it, and misses it silently through Zigbee2MQTT or in a group; Sengled's other bulbs don't list the command | [lab probe](zigbee2mqtt/research/2026-11-14-lab-probe.md); [research](zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md) |
| Tuya TS011F plugs | The standard call fails: of two plugs, one stored it and stayed off, the other turned on 106 s after a 10 s request and stayed on. Tuya's own recipe, a plain on, then the timer in whole seconds, turned both off on time | [internals](../internals.md#tested-behavior) |
| Tuya TS011F `_TZ3000_gjnozsaz` | Tuya's own countdown is reported to restart at random, so the plug may not turn off when asked | [Zigbee2MQTT #30493](https://github.com/Koenkk/zigbee2mqtt/issues/30493) |

## IKEA

On IKEA lights, lower brightness to off may stop at the lowest level instead of turning the light off
([evidence](hue/internals.md#device-classes)).

## Sengled

Written while off, a Sengled E11-G13 jumps to full brightness, with or without the standard override that should
keep it off ([ZHA internals](zha/internals.md#tested-behavior)), so nothing predicts which standard commands Sengled's
bulbs take.

## Tuya

Tuya builds devices that other brands sell (Lidl, Moes, BlitzWolf, AVATTO, Gledopto's GL-SPI-206P and more). The
device's own Zigbee manufacturer string says it is Tuya's whatever the label: `_TZE…` for a datapoint device,
`_TZ3000_…`, `_TZ3210_…` or `_TYZB01_…` for the rest
([research](zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md), §4).

| Kind | Models | What sets it apart |
|---|---|---|
| ZCL plugs and switches | TS011F, TS0001 to TS0004, TS0011, TS0726 | The standard on/off commands, but most run Tuya's own countdown in place of the Zigbee timer |
| Other ZCL devices | Bulbs such as TS0505B, dimmers, `_TYZB01_…` white labels | The standard commands; their timer is unprobed, and may be read in seconds, as the plugs read it |
| Datapoint devices | TS0601 | Tuya's own protocol alone: the integration turns DeviceSide's commands into Tuya's, and no standard read or write reaches them |

None has passed on DeviceSide's dimming, color or write commands, and nothing predicts Tuya's firmware takes them.
