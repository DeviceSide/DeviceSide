# What decides a call on Hue: the aiohue and core code walk, and the Müller Licht candidate

Research note, 2026-11-26. Reading only: the source of aiohue 4.9.0 and Home Assistant core 2026.10.2 (the versions in
`pyproject.toml`'s lock), read 2026-11-14, and Hue Smooth Dimming's code. No probe was run. It moves here the source
walk that Hue's class admission rested on in [internals](../internals.md#device-classes), and the Müller Licht
candidate from the reports in [the color mode note](2026-11-25-color-mode-misread.md).

**Question.** Does anything in the stack between DeviceSide and a Hue bridge's light route a call by the light's
brand, so that a class could key on what the call does rather than on who made the light?

**Answer.** No. DeviceSide's request is the same for every light, and the bridge, whose firmware is closed, picks the
Zigbee command. Per-light data changes a payload, never the call. The one routing core does by device,
`product_data.certified`, changes how a light's state reads. So the class keys on identity: `hue` on the manufacturer
`Signify Netherlands B.V.`, and every other maker in `other`.

## 1. DeviceSide's request is the same for every light

aiohue's `set_state` builds the CLIP v2 PUT from its arguments alone, with no branch on the light, bar effects, which
DeviceSide never sends
([`v2/controllers/lights.py`](https://github.com/home-assistant-libs/aiohue/blob/4.9.0/aiohue/v2/controllers/lights.py#L74-L105)),
and `stop`'s raw PUT (`bridge.put`) sends its body as given. The bridge picks the Zigbee command, and its firmware is
closed: nothing in CLIP v2 shows which command it sent, nor routes a light by a field DeviceSide could read.

Hue's results are the bridge's and Signify's firmware together. On the bridge a Hue bulb's soft off keeps its stored
brightness and a raise from off starts at the bottom ([Hue internals](../internals.md#tested-behavior)); on ZHA the
same bulb given the plain ZCL call is left at level 1 after a soft off and raises from its stored level
([ZHA internals](../../zha/internals.md)). So the bridge sends Hue bulbs more than the plain call, and what it sends
another brand can't be seen.

## 2. `product_data.certified`

It is the one routing core's hue integration does by device: it trusts `mirek_valid` (color temperature mode) only from
a certified light, as "non-official lights do not" set it
([`v2/light.py`](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/hue/v2/light.py#L160-L164)),
and skips its availability workaround for one
([`v2/entity.py`](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/hue/v2/entity.py#L166-L170)).
It decides how a light's state reads, not the call. Whether a Friends of Hue light reports `certified` true is
unverified, so it can't stand for Signify's firmware: `hue` keys on the manufacturer, `Signify Netherlands B.V.`,
which core registers from `product_data.manufacturer_name`
([`v2/device.py`](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/hue/v2/device.py#L64-L71)).

## 3. Per-light data changes the payload, not the call

A light's gamut (aiohue leaves `gamut` None for many non-Hue lights,
[`v2/models/feature.py`](https://github.com/home-assistant-libs/aiohue/blob/4.9.0/aiohue/v2/models/feature.py#L310-L311)),
where `colors.clamp_to_gamut` sends the xy unclamped; its `mirek_schema`; and its features, which drop fields
(`fields_dropped`, `not_dimmable`). None needs a class. `product_archetype`, `min_dim_level`, `dynamics` and `mode`
route nothing.

## 4. Hue Smooth Dimming sent every brand the same calls

With no branch on the light's maker: a target is any light entity of the hue integration on a v2 bridge
(`_resolve_bridge`, `_iter_targets`,
[`bridge.py`](https://github.com/jasonmx/hue-smooth-dimming/blob/9f48dcfdc24295c1fe74833947270e479efeb30c/custom_components/hue_dimmer/bridge.py#L21-L75)).
Its set attributes and set scene write each light with aiohue's `lights.set_state` (`_write_light`,
[`bridge.py`](https://github.com/jasonmx/hue-smooth-dimming/blob/9f48dcfdc24295c1fe74833947270e479efeb30c/custom_components/hue_dimmer/bridge.py#L134-L143);
[`scenes.py`](https://github.com/jasonmx/hue-smooth-dimming/blob/9f48dcfdc24295c1fe74833947270e479efeb30c/custom_components/hue_dimmer/scenes.py#L35-L49)),
its raise and lower send `set_state(on, brightness, transition_time)` and its stop `set_dimming_delta`
([`transitions.py`](https://github.com/jasonmx/hue-smooth-dimming/blob/9f48dcfdc24295c1fe74833947270e479efeb30c/custom_components/hue_dimmer/transitions.py#L90-L108)),
and its get attributes reads aiohue's cache, sending nothing
([`bridge.py`](https://github.com/jasonmx/hue-smooth-dimming/blob/9f48dcfdc24295c1fe74833947270e479efeb30c/custom_components/hue_dimmer/bridge.py#L94-L111)).
DeviceSide sends the same requests (`bridge.set_state`; `stop`'s `{"dimming_delta": {"action": "stop"}}` through
`bridge.put`, the body `set_dimming_delta` builds). A user's report has another brand's Zigbee Light Link dimmers
running its set attributes and set scene
([#617](https://github.com/DeviceSide/DeviceSide/issues/617); set scene's request:
[jasonmx/hue-smooth-dimming#22](https://github.com/jasonmx/hue-smooth-dimming/issues/22)).

What DeviceSide adds to those calls: the saturation fades, one `set_state` with an xy and a duration, the two fields Hue
Smooth Dimming sent apart; and `stop`'s xy halt and soft-off cut, writes mid-transition measured only on Hue bulbs.

## 5. Müller Licht: why one report earns no key

#62497's one tint loris came with no Zigbee strings. Its candidate zigbee-herdsman-converters definition, the tint panel
404028/44435, matches on the model string `RGB-CCT` alone, with no `MLI` manufacturer fingerprint, and 44435 also names
a second definition
([`muller_licht.ts`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/devices/muller_licht.ts#L152-L172)),
so a model key would rest on two guesses, and one report of one product is no ground to refuse the maker whole
([contrary evidence](../../../evidence.md#levels)). It earns a key on a Hue diagnostics `product_data` of a Müller
Licht light (its identity), or a second Müller Licht report on another model (the maker, whose tint lights'
fingerprints carry `MLI`:
[`muller_licht.ts`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/03b37655f540668d94975c47550f249fc0d16e26/src/devices/muller_licht.ts#L333-L354)).
Müller Licht lights made by Tuya (a `_TZ…` string) stay in `other` either way.
