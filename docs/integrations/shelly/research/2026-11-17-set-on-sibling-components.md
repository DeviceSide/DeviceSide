# Shelly `<Component>.Set` on the RGBCCT siblings: official docs check (2026-11-17)

Question: does Shelly's official Gen2+ documentation describe `Light.Set`, `CCT.Set`, `RGB.Set` and `RGBW.Set`
identically to `RGBCCT.Set` for the fields DeviceSide's `set_attributes` sends (brightness, ct, rgb,
`transition_duration`), and what does each page say about a Set that omits `on`? This is the check
`integrations/shelly/set_attributes.py` records as not done ("the docs host was out of reach").

Marks: **[V]** verified in the official docs. **[U]** unofficial source. **[GAP]** not found.
Source: `https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/<Component>`, fetched 2026-11-17 (the host
was reachable). The fetch tool summarizes pages, so the quotes below are the tool's extracts of each Set section;
re-read the live page before relying on a quote's exact wording.

## Bottom line

1. **No page, RGBCCT included, says what a Set without `on` does to the output or to an off device.** [GAP] for all
   five. The pages only say `on` is optional and that at least one of the listed fields is required. The Verified
   RGBCCT behavior (output untouched, values stored) rests on the rig probe of 8 Nov, not on the docs.
2. For the **brightness-only** call, Light, CCT, RGB and RGBW document `brightness` exactly as RGBCCT does
   ("Brightness level 0%-100%. Can not be used together with `offset`."), with `on` optional and brightness
   alone satisfying the "at least one of" rule. [V]
3. `ct` is documented on CCT and RGBCCT only; `rgb` on RGB, RGBW and RGBCCT; `white` on RGBW only. RGBCCT has no
   `white` field; CCT and RGB have no `mode`. [V]

## Light.Set (`/gen2/ComponentsAndServices/Light`)

| Field | Documented | Mark |
|---|---|---|
| `on` | boolean, optional: "True for light on, false otherwise." | [V] |
| `brightness` | number, optional: "Brightness level 0%-100%. Can not be used together with `offset`." | [V] |
| `transition_duration` | number, optional: "Transition time in seconds - time between change from current brightness level to desired brightness level in request." | [V] |
| `ct` / `rgb` / `white` | not on this page | [V] absent |
| Required rule | "At least one of the `on`, `brightness` or `offset` parameters is required." | [V] |
| `on` omitted | not described | [GAP] |

## CCT.Set (`/gen2/ComponentsAndServices/CCT`)

| Field | Documented | Mark |
|---|---|---|
| `on` | boolean, optional: "True for light on, false otherwise." | [V] |
| `brightness` | number, optional: "Brightness level 0%-100%. Can not be used together with `offset`." | [V] |
| `ct` | number, optional: "Color temperature level (in Kelvin)." | [V] |
| `transition_duration` | number, optional: covers both "current brightness level to desired brightness level" and "current color temperature level to desired color temperature level" | [V] |
| `mode` | not on this page (RGBCCT has it) | [V] absent |
| Required rule | "At least one of the `on`, `brightness`, `ct` or `offset` parameters is required." | [V] |
| `on` omitted | not described | [GAP] |

## RGB.Set (`/gen2/ComponentsAndServices/RGB`)

| Field | Documented | Mark |
|---|---|---|
| `on` | boolean, optional: "True for output on, false otherwise." | [V] |
| `brightness` | number, optional: "Brightness level 0%-100%. Can not be used together with `offset`." | [V] |
| `rgb` | array of number, optional: "Red, Green, Blue [r,g,b] - each value represents level between 0..255." | [V] |
| `transition_duration` | number, optional: "Transition time in seconds - time between change from current brightness level and color." | [V] |
| Required rule | "At least one of the `on`, `brightness`, `rgb` or `offset` parameters is required." | [V] |
| `on` omitted | not described | [GAP] |

## RGBW.Set (`/gen2/ComponentsAndServices/RGBW`)

| Field | Documented | Mark |
|---|---|---|
| `on` | boolean, optional: "True for output on, false otherwise." | [V] |
| `brightness` | number, optional: "Brightness level 0%-100%. Can not be used together with `offset`." | [V] |
| `rgb` | array of number, optional, [r,g,b] 0..255 | [V] |
| `white` | number, optional: "White level [0, 255]. Can not be used together with `offset_white`." (also `offset_white`, -255..255) | [V] |
| `transition_duration` | number, optional: seconds, from current brightness and color to the requested ones | [V] |
| Required rule | at least one of `on`, `brightness`, `rgb`, `white`, `offset`, `offset_white` | [V] |
| `on` omitted | not described | [GAP] |

## RGBCCT.Set (`/gen2/ComponentsAndServices/RGBCCT`), the reference

| Field | Documented | Mark |
|---|---|---|
| `on` | boolean, optional | [V] |
| `brightness` | number, optional: 0% to 100%, not with `offset` | [V] |
| `rgb` | array of number, optional, 0..255 each | [V] |
| `ct` | number, optional, Kelvin | [V] |
| `mode` | string, optional: operating mode of the light output | [V] |
| `transition_duration` | number, optional, seconds | [V] |
| Required rule | "At least one of the `on`, `brightness`, `ct`, `rgb`, `mode` or `offset` parameters is required." | [V] |
| `on` omitted | not described | [GAP] |

All five pages also list `toggle_after` ("Requires `on` to be present in the request."), `offset` and `tag`
identically. `set_attributes` sends none of those.

## Conclusion for `set_attributes`

| Component | Brightness-only Set (what `COMPONENT_FIELDS` sends today) | Fields that would need porting |
|---|---|---|
| Light | Documented identically to RGBCCT, differing only in addressing: `brightness`, optional `on` | none |
| CCT | same | `ct` is documented (Kelvin) but the call differs from RGBCCT's: no `mode` field, so the mode switch RGBCCT sends has no CCT counterpart in the docs; no record covers `CCT.Set {ct}` |
| RGB | same | `rgb` is documented as RGBCCT's is, but DeviceSide's color conversion (hs/xy to rgb, brightness split) is not ported to it |
| RGBW | same | `rgb` as RGB, plus `white` (0..255), which RGBCCT lacks: a new mapping |

Caveat that bounds "identically": the docs are silent on `on` omitted for every component, RGBCCT included. What
makes RGBCCT's no-`on` Set Verified is the 8 Nov rig probe. The siblings are therefore "documented identically" only
in field names, types and optionality (the form of the call), not in the no-`on` behavior, which no page documents.
Whether that satisfies docs/evidence.md's Documented (sibling) is the maintainers' call: the call's shape is
identical in the docs; the omitted-`on` outcome for Light, CCT, RGB and RGBW remains [GAP] and is inherited from
RGBCCT only by the "same call, same class" reasoning (CLAUDE.md, Evidence 5).
