# Device classes: evidence, routing and refusals per class of device

## Coordination

Intent: Give every integration one way to say which class of device a target is, and make the class carry the
evidence. A class holds its own level (Verified, Documented, flagged), its own "doesn't work" entries, and its own
"not yet supported" state. The cards are generated from that data. A CI check fails when a Verified class has no
record behind it. The default call path runs for unknown devices behind `experimental`, and known exceptions are
refused in code and named on the cards.
Touches: docs/evidence.md, docs/design.md, CLAUDE.md (tenet 5's line), docs/device-compatibility.md, CONTRIBUTING.md,
TODO.md, README.md (regenerated), custom_components/deviceside/core/{scope.py, adapter.py, registry.py,
dispatcher.py, errors.py}, the five integration packages and their bundles, scripts/gen_compat.py, and their tests.
Tests-with: the ha-rig PR (step 2) writes the class each test reached into the records. It lands, and Shelly is rerun
on it, before the core PR (step 3), whose coverage check reads that column.
Depends-on: none. #350 (Control4) gets no comment and no change until step 8. It is `experimental=True` throughout, so
none of these steps blocks it.

## Why

- **The gap nobody flagged.** Every Zigbee2MQTT record is a Philips Hue bulb. `domains=verified("light")` still makes
  every Z2M light Verified, so an IKEA or Innr bulb runs unflagged and shows as tested on the cards. Nothing compares a
  scope's `verified(...)` with the models its records reached, so neither a maintainer nor Claude was told. ZHA, Hue
  and Matter have the same gap.
- **Zigbee breaks "same call, same result".** The timed-on research
  ([2026-11-14](../integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)) found five distinct call
  patterns for one action. Even devices that get the identical standard call differ in firmware: Hue replaces a
  running timer where the spec says extend, and some IKEA and Hue models turn on and never off. Tenet 5 assumed the
  call decides the result. On multi-vendor protocols, the call and the firmware family decide it together.
- **"Doesn't work" isn't enforced.** `devices.yaml` `doesnt_work` reaches the cards but not the code, so a listed
  device is still sent the call. On Z2M, 49 Tuya plug definitions have no `on_time` converter. Our call becomes a
  permanent plain On, and we report `sent`.
- **Refusals are hand-rolled per adapter.** Hue repeats a `bridge_v1` check in five adapters and a `smart_scene` check
  in one. The card's "Bridge v2/Pro" is a typed `requires:` line. Each is a fact with two homes.
- **Shelly already does most of this.** `capability()`, per-capability levels, the experimental gate and the card
  tiers all exist. The plan generalizes them and moves them to the integration, rather than adding a new mechanism.

## Tenets behind the design (to settle with Jason)

These refine `docs/evidence.md`; they don't replace its tenets.

1. **Proof follows the call and the class** (refines tenet 5). Evidence is about how a class of devices responds to a
   call. A class is the set of devices that get the same call and run the same firmware family, as the integration's
   `capability()` names it. Code that sends the same call to the same class inherits the evidence.
2. **Unknown is flagged, never Verified.** A device the classifier can't place falls in the integration's default
   class, which no record reaches until one does. So it runs only behind `experimental`. A misclassification can only
   make something more cautious.
3. **Three ways a class can't take an action, each shown differently.**
   - *Doesn't work:* it fails the call we send. Refused in code, listed with a reason and source.
   - *Not yet supported:* it needs a call we haven't built. Refused, listed as not yet supported.
   - *Untested:* the default call may work. Runs behind `experimental`.
4. **One fact, one home, in code.** Classes, levels and doesn't-work entries live in the package's code. The cards are
   generated from it. `devices.yaml` keeps only presentation: each class's phrase and section.
5. **The split rule.**
   - A different gateway or API is a separate integration, with a `detect` hook on the same `ha_domain`, as Z2M is
     beside MQTT. Example: a Hue v1 bridge.
   - A different device behind the same API is a class.
   - A class that needs a different payload is a branch inside the adapter.
   - An adapter splits only if a class needs a different result contract. Today that never happens. A different
     duration limit becomes a per-class setting first.
6. **Build only what Z2M needs.** Z2M is the most varied integration, so it sets the bar. Rules match on
   manufacturer and model until a real departure needs firmware. No matcher, setting or tier is added ahead of an
   integration that uses it.

## Design

### Core

- **`IntegrationInfo.capability(hass, target) -> str | None`** names the target's class. It's sync and cheap, with no
  I/O, and may read the registry device, the config entry, or integration data such as a Control4 Director item. It
  replaces `Adapter.capability()` and Shelly's `RpcComponent` mixin. Every adapter of the integration sees the same
  class.
- **Capability names a device class, not a call pattern.** Patterns are per action: a timed-on pattern means nothing
  to a fade. Each adapter maps the classes it serves to its own branch in `execute`. This replaces the
  `pattern:class` names suggested in discussion.
- **Registry rule.** An integration with `capability` needs `scope.capabilities` on every adapter. One without needs it
  on none. The check moves from per adapter to per integration, so an adapter can't silently skip the axis.
- **`AdapterScope.doesnt_work: Mapping[str, DoesntWork]`**, keyed by class, each entry with what, reason and source.
  It is per adapter because a TS011F fails `turn_on_for` but answers `get_attributes`. The dispatcher refuses with a
  new `Reason.DOESNT_WORK`, raised for a named target and skipped for an indirect one, as the existing raise rule
  does. Doesn't-work classes are deliberately left out of `capabilities`.
- **Not yet supported** is a class the integration names, in neither `capabilities` nor `doesnt_work`. The existing
  `capability_not_tested` refusal covers it. Rename it `not_supported` in the same PR, as the old name misdescribes
  it.
- **Native groups** take the weakest level among their members' classes. A member in `doesnt_work` or not supported
  refuses the group, unless the integration can expand it.

### Records and the coverage check

- The rig writes the class each test reached into the record's Tests table, as a Capability column, from
  `IntegrationInfo.capability`. `_manual.md` rows gain a Capabilities column.
- **`gen_compat --check` adds the coverage check.** Every class an adapter's scope holds as Verified must appear in a
  passing record test, or a manual row, for that action. The failure names the gap, for example: "zigbee2mqtt
  turn_on_for: `other` is Verified but no record reaches it". CI runs it on every PR, so the gap is caught before
  review.
- With the class known per test, the Works tier can credit a model only to the classes it reached. The fail-safe rule
  in `gen_compat`'s docstring, where any flagged capability adds no models, goes away.

### Cards

Per integration, the tiers are: Works (models and classes with records), Should work (Documented classes),
Experimental (flagged classes), Not yet supported (classes the integration names with no adapter in scope), and
Doesn't work (generated from `doesnt_work`). `devices.yaml` keeps `column`, `column_order` and the class phrases.
`doesnt_work` and, eventually, `requires` move to code.

## Steps

Each step is one PR off `main`, in order, with pytest, pre-commit and the regenerated files as usual. Steps 1 and 3 are
on the binding-rule surface: Opus audit, repo maintainer. Steps 4–7 are package PRs, each with a rig rerun as its
sign-off. That rerun is the test of the framework on the current repo scope.

1. **Rules and design (docs only).**
   - `docs/evidence.md`: the tenets above; the definition of a class; doesn't work vs not yet supported vs untested;
     the split rule; the coverage check; an example from Z2M.
   - `docs/design.md`: glossary entries for Class, Doesn't work and Not yet supported, and the Core contract for
     `IntegrationInfo.capability` and the refusals.
   - `CLAUDE.md`: tenet 5's line.
   - `docs/device-compatibility.md`: the new tier.
   - CONTRIBUTING: the Fast track asks a new integration to name its classes, or to say it has one.
   - TODO.md: this plan's steps.
2. **Rig (ha-rig, private).** Write the Capability column from today's `Adapter.capability()`, and from
   `IntegrationInfo.capability` once step 3 lands. Rerun Shelly so its records carry the column.
3. **Core.**
   - `IntegrationInfo.capability`, the registry rule, `doesnt_work` and `Reason.DOESNT_WORK`, and the rename.
   - Shelly moves from its mixin to `IntegrationInfo.capability`. Its scopes don't change.
   - `gen_compat`: the new tiers, `doesnt_work` read from code, and the coverage check. The check applies only to
     integrations that define `capability`, so Shelly alone at first.
   - `models.yaml`'s shared `doesnt_work` (the TS011F) stays until steps 4 and 5 move it.
4. **Zigbee2MQTT (the driver).**
   - Classes: `hue` (Philips), `tuya_zcl` (TS011F, TS000x and their white labels), `tuya_mcu` (TS0601), and `other`.
   - Scopes: `hue` Verified wherever records reach it. `other` is flagged on fades, `stop`, `set_attributes` and
     `turn_on_for`. `get_attributes` and `stop` can argue Documented in the PR.
   - `turn_on_for` leaves the two Tuya classes out of scope, so they're refused as not supported. That ends the
     silent permanent On. The TS011F's entry follows the probe in Decision 3.
   - First, a cheap probe: what HA's device registry holds for a white-label Tuya device under Z2M, to pick the
     detection signal (manufacturer, model, or Z2M's `countdown` expose). Record it in `internals.md`.
   - Rig rerun on the Hue bulbs. The records reach `hue`, so `other` must stay flagged until a non-Hue bulb is run.
5. **ZHA.** The same class shape. ZHA exposes the raw `_TZ…` manufacturer, so Tuya detection is direct. Rig rerun.
6. **Hue.** Classes: `hue` and `other` (third-party lights on the bridge), plus `bridge_v1` (not yet supported) and
   `smart_scene` (doesn't work, on `set_scene`). Remove the five `bridge_v1` checks and the `smart_scene` check.
   `requires:` can then be generated or kept as display. Rig rerun.
7. **Matter.** Its only record is a WiZ plug, so the class split (for example `wiz` and `other`) is the maintainer's
   call in the PR. Manual or rig sign-off.
8. **Close out.**
   - Remove `models.yaml`'s shared `doesnt_work` once nothing reads it.
   - Regenerate the README.
   - Tick TODO.
   - Then comment on #350: the classes it will need to leave `experimental`, and what its manual records should note
     (the Director's driver or proxy type).

## Deferred until something needs it

- Per-class `duration` limits: needed by the Tuya countdown pattern (whole seconds, 43,200 s cap) once it's built.
- Firmware matching in the classifier: needed the first time a firmware boundary decides behavior, such as the Sonoff
  ZBMINIR2 at 1.1.0.
- Building Tuya patterns B and C, and a non-Hue bulb on the rig. The second is the one that lifts `other`'s flag on
  Z2M and ZHA.

## Decisions (Jason, 2026-11-14)

1. **Lands before v0.1.0.** Features that non-Hue bulb owners on Z2M, ZHA and Hue use unflagged today move behind
   `experimental` in v0.1.0.
2. **Third-party lights on a Hue bridge get the `other` class.** Step 6 decides per action whether `other` is flagged or
   Documented, by an Opus model's judgment, and argues each choice in the PR body. The bar is `docs/evidence.md`'s
   Documented test: same capability, differing only in addressing, and no known class of devices departs.
3. **Probe the TS011F before calling it "doesn't work".** The research suggests it may run the timer, but read our
   tenths as whole seconds: a 15 s request toggled one after 150 s. Before steps 4 and 5 settle its entry, probe one on
   the rig. Try off then 0x42 `{on_time N, off_wait 0}` in tenths and in seconds, and the Tuya recipe: plain On, then
   `{N s, N s}`. Read state and `onTime` each second. Record the result in `internals.md`. If a recipe works, the
   TS011F is `tuya_zcl`, not yet supported (pattern B, deferred), not doesn't work. Its doesn't-work entry stays only
   if no recipe works. Whichever way it goes, the shared entry becomes one code entry per integration (ZHA and Z2M),
   which `gen_compat` merges on the cards.
4. No release-note line: DeviceSide isn't widely released yet.
