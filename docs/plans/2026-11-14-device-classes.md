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
Tests-with: ha-rig #84 (step 2, merged) writes the Capability column. A second ha-rig change, after step 3, reads the
class from each result (Decision 6). It lands before step 4's lab run.
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
- **The coverage check.** Every class an adapter's scope holds as Verified must appear in a passing record test, or a
  manual row, for that action. Each gap is named, for example: "zigbee2mqtt turn_on_for: `hue` is Verified but no
  record reaches it". It warns on every PR (`gen_compat --check`), so a developer sees the gap early, and fails only
  at `cut-release` (`check_release.py`), where the other release gates run (Decision 7).
- With the class known per test, the Works tier can credit a model only to the classes it reached. The fail-safe rule
  in `gen_compat`'s docstring, where any flagged capability adds no models, goes away.

### Cards

Per integration, the tiers are: Works (models and classes with records), Should work (Documented classes),
Experimental (flagged classes), Not yet supported (classes the integration names with no adapter in scope), and
Doesn't work (generated from `doesnt_work`). `devices.yaml` keeps `column`, `column_order` and the class phrases.
`doesnt_work` and, eventually, `requires` move to code.

## Execution (Jason, 2026-11-14)

- **One implementer per step**, a subagent or session given this plan and the step, and **a separate reviewer
  subagent** per step. The reviewer gets the plan, the step number, the step's diff, CLAUDE.md and
  `docs/evidence.md`, never the implementer's conclusions. It judges the diff against this plan's intent and
  tenets. Its findings are fixed or answered before the next step starts, and a "Plan review" note goes in the step's
  last commit.
- Steps 1 and 3 are on the binding-rule surface, so they also get the Opus audit.
- **Branches:** stacked, one per step, `claude/device-classes-<n>-<name>`, each off the previous, so each can become
  its own PR in order.
- **Decisions the plan doesn't settle go to Jason**, asked directly, and are recorded below as they are made.
- **The rig:** the lab profile is available every step. It has the Hue bulbs on Hue, ZHA and Z2M, the TS011F plug and
  the Matter WiZ plug, and can take a Sengled bulb or the Shelly color bulb when needed. The house profile, which
  has the Shelly switch devices, is a day or two away. Each lab run is also that integration's v0.1.0 sign-off if its
  package doesn't change afterward.

## Steps

Each step is one PR, in order, with pytest, pre-commit and the regenerated files as usual.

1. **Rules and design (docs only).** Done: `claude/device-classes-1-rules`.
2. **Capability column.** Done: `claude/device-classes-2-capability-column`, ha-rig #84 merged.
3. **Lab probe, before any classifier code (1a).** The implementer first writes a probe spec, in this plan and to
   Jason. Jason runs it in the lab while step 4 (core) proceeds. Results go in each bundle's `internals.md`, dated.
   - **Registry strings:** what HA's device registry holds (manufacturer, model, `model_id`, firmware) for each lab
     device on Hue, ZHA, Z2M and Matter. Vendor and model strings only, never names, IDs or addresses.
   - **The TS011F probe** (Decision 3).
   - **The Tuya detection signal** on Z2M and ZHA.
   - **Sengled, once it's in the lab:** its strings on each network, and whether it honors 0x42. The research puts it
     in pattern E, no device timer.
4. **Core** (the plan's former step 3).
   - `IntegrationInfo.capability`, the registry rule, `doesnt_work` and `Reason.DOESNT_WORK`, and the rename.
   - The class in each result (Decision 6).
   - Shelly moves from its mixin to `IntegrationInfo.capability`. Its scopes don't change.
   - `gen_compat`: the new tiers, `doesnt_work` read from code, and the coverage check, warning only (Decision 7).
     `check_release.py`: the same check, failing.
   - Decision 5's rule in `docs/evidence.md`.
   - Exact instructions to Jason for the second ha-rig change, which reads the class from the result.
5. **Zigbee2MQTT (the driver).**
   - Classes from the probe's real strings: `hue`, `tuya_zcl`, `tuya_mcu`, `other`, and `sengled` if the Sengled needs
     its own rule. A one-off test bulb lifts its maker's class, never `other` (Decision 5).
   - Rules are data, so a later probe changes rule data, not structure.
   - Scopes as planned. `turn_on_for` refuses the Tuya classes as not supported. `sengled` on `turn_on_for` is not
     supported if the probe confirms it ignores 0x42. The TS011F's entry follows Decision 3.
   - **Lab run** on the branch tip, with the Sengled. It tests the classifier, the column, the coverage check, Works
     credited per class, and the refusals.
6. **Core fix-ups** from step 5's run, before ZHA and Hue copy the pattern. If a package changes, its lab run is
   repeated.
7. **ZHA.** The same shape. Lab run, with the Sengled.
8. **Hue.** Classes `hue`, `other`, `bridge_v1` (not supported) and `smart_scene` (doesn't work, on `set_scene`).
   `other` is decided per action (Decision 2). Lab run, with the Sengled on the bridge if it pairs. The `bridge_v1`
   refusal is unit-tested only.
9. **Matter.** Lab run on the WiZ plug.
10. **Close out.**
    - The house run: Shelly's switch devices, plus the color bulb unless it already ran in the lab.
    - Repeat any run on the list below.
    - Remove `models.yaml`'s shared `doesnt_work`, regenerate the README, and tick TODO.
    - Then, with Jason's go-ahead, comment on #350: the classes it will need to leave `experimental`, and what its
      manual records should note (the Director's driver or proxy type).

### Runs to repeat

A package changed after its lab run needs that run again before the release. None yet.

## Deferred until something needs it

- Per-class `duration` limits: needed by the Tuya countdown pattern (whole seconds, 43,200 s cap) once it's built.
- Firmware matching in the classifier: needed the first time a firmware boundary decides behavior, such as the Sonoff
  ZBMINIR2 at 1.1.0.
- Building Tuya patterns B and C, and a non-Hue bulb on the rig. The second lifts that maker's own class on Z2M and
  ZHA, never `other` (Decision 5).

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

## Decisions (Jason, 2026-11-14, during steps 1–2)

5. **The default class is never Verified.** `other` can be Documented per action where `docs/evidence.md`'s Documented
   test holds (no known class departs), and is otherwise `experimental(...)`. A record on a non-Hue device lifts a new
   named class for its maker (for example `ikea`), not `other`. Step 3 writes the rule into `docs/evidence.md`.
6. **The class a call used is reported in its response.** `IntegrationInfo.capability(hass, target)` stays as
   designed. Each target's result carries the class the dispatcher used: a command's beside `status` and
   `integration`, a query's in its entity's data, a native group's as its members' classes. The rig records that
   instead of classifying a stand-in target, so a record holds the class the call really reached. Step 3 adds the
   field; the rig then reads it (ha-rig, after step 3).
7. **The coverage check warns during development and fails at release.** `gen_compat --check` prints each gap on
   every PR, so a developer sees it early. `check_release.py` fails on it at `cut-release`, with the other release
   gates. No allowlist is needed while records catch up (Shelly's house rerun).
