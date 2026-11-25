# The bridge's color mode misread on other brands' lights: core #62497 and #93459

Research note, 2026-11-25. Reading only: the two Home Assistant core issues, their comments and the PR that closed the
second, read with `gh` on 2026-11-25. No probe was run. Handles are GitHub logins, written without a mention.

**Question.** Which lights did these issues show reporting color temperature mode wrong through a Hue bridge, on what
firmware, and what did core's maintainer find? This is the source for Hue's Gledopto class and for Müller Licht's
record ([internals](../internals.md#device-classes)).

**Answer.** Gledopto lights, on three models named across two issues and several reporters, all three "(pro)" in
zigbee-herdsman-converters, and a non-Pro MR16 (model not given) too: after a color temperature write, a later bridge event carried xy and cleared
or contradicted `mirek_valid`, so Home Assistant showed a color. A Müller Licht tint light and a LivarnoLux strip were
reported the same way, once each, with no Zigbee strings. Core's maintainer saw the second event in the bridge's own
events; reporters disagreed on whether the Hue app showed it. His own Gledopto Pro strip controller didn't show it.

## core #62497: "Incorrect Color mode for 3rd party lights in Hue integration"

[Issue](https://github.com/home-assistant/core/issues/62497), opened 2021-12-21 by `Seba-VT` on Home Assistant
2021.12.4 (last working 2021.11.x), closed 2022-03-23 by `marcelveldt` (core's hue code owner).

### Reporters and lights

| Reporter | Lights | Firmware | Bridge firmware | Hue app showed it |
|---|---|---|---|---|
| `Seba-VT` | Gledopto bulbs ("GLEDOPTO 6W Bulb"; later "new GL-B-007P bulbs", added to the Hue app only) and Gledopto strip controllers (model not given) | bulbs "v3.0.0 according to the HUE app" | 1.48.1948086000 | yes: "the HUE app is reporting it wrong", also with Home Assistant off the network (2022-01-07); earlier, only when changed from Home Assistant (2021-12-21) |
| `snowatom-dk` | Gledopto GL-S-004P (MR16, 120 degree), "pro hardware"; later "Gledopto MR16 bulb non-Pro version" too (2022-02-17) | 10976801 ("taken from the Hue App") | 1.49.1949107040 | no: "Hue app always works with these bulbs" (2022-01-16) |
| `MobilettoSoft` | LivarnoLux Color Led Strip | not given | not given | not given |
| `szuek` | Müller "tint loris 45x45" | v2.5.3 | "latest firmware 1.50.195xx" | yes: "the hue app itself shows the state wrong as well"; the Hue Essentials app showed it right |

zigbee-herdsman-converters describes GL-S-004P as "Zigbee 4W MR16 Bulb RGB+CCT (pro)" and GL-B-007P as "Zigbee 6W
E26/E27 Bulb RGB+CCT (pro)" ([`gledopto.ts`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/afdaa028a0972d801da762196ddfb2df631ea0cc/src/devices/gledopto.ts)).
No comment gives a light's Zigbee manufacturer or model string as the bridge reports it, nor Hue diagnostics.

### The maintainer's findings, in order

- 2021-12-23: on "a Gledopto (pro) strip controller" he "can't see the behavior": "The color mode switches correctly
  between xy and color_temp." 2022-01-08: "I have the Gledopto PRO strip controller and that one doesn't have the
  issue. So I think the issue is with the non-pro Gledopto hardware" (`snowatom-dk` answered that their MR16 is pro).
- 2022-01-14, from `Seba-VT`'s logs of a debug build printing each raw bridge event: "after setting a color
  temperature we receive 2 events. The first event is correct and contains the correct "mirek value" and
  "mirek_valid" which results in color temperature mode. Within 1 second after that we receive a second event with xy
  color values for this same light so the colormode is changed to xy again". He concluded the lights "emit the wrong
  values on the zigbee stack", and that before 2021.12 it "worked by accident" as state was polled, not evented.
- 2022-01-16, `snowatom-dk`'s log of one GL-S-004P after one `color_temp` write: an event with `mirek=459,
  mirek_valid=True` and xy (0.5077, 0.415), then about 9 s later one with `mirek=None, mirek_valid=False` and xy
  (0.0, 0.0), which core read as `xy` mode. He called it "2 different issues then with both Gledopto bulbs".
- 2022-01-17, on `Seba-VT`'s new GL-B-007P: "Issue remains the same", which he then called "a bug in the new Hue
  API". The same day `Seba-VT` reported the bulbs working on ZHA (a ConBee II). 2022-01-18: Signify answered that
  third-party support "isn't high on their priority list", and he put the ZHA result down to ZHA's "device specific
  quirk" for a bug "in the light itself".
- 2022-01-25: "the Hue bridge periodically pings all lights on the zigbee mesh for their state. Due to a rounding
  issue, the Hue bridge assumes the color changed while it didn't."
- 2022-02-24, answering the LivarnoLux report's "all third party lights": "Not true, I have tested a few 3rd party
  lights including a Gledopto Pro led controller and those didn't have the issue."
- 2022-03-23, closing: "Signify confirmed to us that if this issue exists it is 100% caused by the (3rd party)
  manufacturer", core removed its workaround and "now rel[ies] 100% on what the bridge tells us", and an issue where
  the Hue app shows the right value should be filed anew.

## core #93459: "Gledopto connected via Hue Bridge jumps to RGB color when setting color-temperature in HA"

[Issue](https://github.com/home-assistant/core/issues/93459), opened 2023-05-24 by `juliusvaart` on core-2023.5.4,
filed anew as #62497's closing asked: a Gledopto GL-C-008P, firmware 11076802, an RGBCCT LED strip controller
(zigbee-herdsman-converters: "Zigbee LED Controller RGB+CCT (pro)"). A color temperature write showed as a blue color
in Home Assistant, while the Hue app, Hue Essentials and iConnectHue showed the right color temperature and the strip
itself was right. `SucubusJenny` had the same "since I got the controller", model not given. `marcelveldt`:
"Managed to reproduce the issue." Closed 2023-07-26 by
[PR #97263](https://github.com/home-assistant/core/pull/97263), "Fix invalid ColorMode on (some) 3rd party Hue Color
lights": "Some 3rd party lights do not correctly set the "mirek_valid" flag, causing our ColorMode selection to
fallback to xy. Remove the redundant check and simply assume ColorTemperature if/when the colortemperature value is
not None."

## What this does and doesn't show

- **Shown:** Gledopto lights on three models (GL-S-004P, GL-B-007P, GL-C-008P), three reporters naming a model and
  two years, with the bridge's events contradicting a color temperature write. All three are "(pro)" models; a
  non-Pro MR16 (model not given) was reported too, so the reports don't split along Pro. The one light that didn't
  show it is the maintainer's own Gledopto Pro strip controller, model and firmware not given.
- **Disputed:** whether the Hue app shows it. `Seba-VT` and `szuek` said yes; `snowatom-dk` and `juliusvaart`
  said no.
- **Not shown:** any light's Zigbee strings as the bridge reports them (`product_data`). The Müller Licht and
  LivarnoLux reports are one light each, with no model string.
