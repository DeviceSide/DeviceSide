# Evidence

What DeviceSide must know about a device before a feature ships to everyone, and what a release needs. This page is the
one home for these rules; other docs point here.

## Tenets

1. **User experience is the north star.** Actions make devices do what users expect, predictably and with low
   latency, and DeviceSide offers only what's likely to meet that bar. If that holds, nothing else matters.
2. **Probe before you build.** When unsure how a device you can reach responds to a call, run a cheap probe and record
   what it shows, dated, in the bundle's `internals.md`. A fact a shipped call depends on is a **fact test**: the rig
   reruns it (`--facts`) when that call changes, and `test-records/_facts.json` keeps each result; a watched test covers
   what only a person can see. A fact that only decided scope or design goes in `research/`, a dated file never edited;
   if evidence suggests it has changed, repeat the probe by hand in a new file. With no device at hand, build from a
   source cited in `internals.md` (the vendor's documentation, an upstream integration that ships the call, or
   research), at the level tenet 10 gives; in Labs, the first device report is the probe. *Why:* assumed behavior is
   where features break.
3. **Verify, then trust.** A verified fact stands across firmware, HA and code changes until evidence contradicts it.
   Nobody goes looking for things to re-prove.
4. **Surprises reopen facts.** A bug or unexplained behavior gets a root-cause dive, and the finding joins the fact
   base. Log so the first bug report holds the diagnosis: what DeviceSide sent, what the device answered, and which way
   DeviceSide went. A layer that changes what DeviceSide sends (a converter's rewrite, a quirk) is such a finding even
   when meant: record it with its source in `internals.md`, and a maintainer decides whether to go around it, keep it as
   a class limit (`index.md`) or report it upstream. It is never closed as "by design".
5. **Proof follows the call and the class.** Evidence is about how a [class](#device-classes) responds to a call. Code
   that sends the same call to the same class inherits it, and unit tests pin the call. A no known method entry may
   likewise cover every action that sends that call to that class or identity (`turn_on_for`, `set_auto_off` and
   `turn_off_for` where they send the same frame). Across integrations a PR argues inheritance by hand
   ([deferred](deferred.md#device-facts-across-integrations)).
6. **Simplify relentlessly.** Prefer fewer calls, round trips and machinery. A new guardrail needs evidence its failure
   happens (a probe, record or report); until then, log so the first report would show the failure. A new rule or
   guardrail names the user-visible failure it prevents and what it replaces. An existing guardrail stays until evidence
   shows its failure doesn't happen; meanwhile, make it cheaper.
7. **Maintainers judge sufficiency.** Tooling records evidence; maintainers decide what's enough. Gates check that a
   sign-off exists, not how thorough it was.
8. **Test to decide.** A hardware run costs time and a person at hand, so run one only when its result takes a decision:
   a design choice (tenet 2's probe; a call already seen working on the device, in your own automation, an upstream
   integration or a research file's run, needs none, only a citation in the bundle's `internals.md`, while a vendor's
   document alone still needs the probe where a device is in reach); a foundation (before further steps build on a
   design no verified fact covers, the rig cases whose failure would discard that work); lifting a [Labs
   flag](#the-labs-flag); a surprise (tenet 4); or a release (the sign-off, due before the last RC, or the one that
   clears a caveat). Run it at the last point that can take its decision: for a device the rig or a maintainer can
   reach, the release's run, so no merge waits on one; for a contributor's own devices, their pull request, one test of
   the finished build at the commit whose calls ship ([CONTRIBUTING](../CONTRIBUTING.md), Fast track): a maintainer
   needs it to merge, and what it exercised ships unflagged. A plan gates a step on a run only by naming the decision.
   *Why:* a run whose result changes nothing only holds up the release.
9. **Retest what the change exercises.** A change reopens only the evidence for actions whose call, or handling of the
   device's reply, it changes, wherever the code lives. Evidence binds to the action's [call
   transcript](#release-gate) and stands while every call path it was tested on is there, unchanged: a refactor that
   keeps every call reopens nothing, and a fix for a failing case reruns its suite, not the integration's run. *Why:*
   judging staleness by source changes reopened evidence on cosmetic edits and missed call changes in `core/`.
10. **Include unless harmful.** An item ships outside Labs unless it is likely to harm, or no route in
    [Levels](#levels) admits it; one no route admits ships in Labs on a sourced call, or isn't built. *Why:* refusing a
    feature the user's device likely takes costs them more than a low-harm failure.
11. **Never withdraw silently.** A feature shipped outside Labs in a release (not an RC) is withdrawn (refused, flagged
    or dropped) only on a report or a root-caused finding, and the notes of the release that withdraws it say so.
    *Why:* an upgrade must not break a working setup without a word.

## Levels

A scope item (an entity domain, class or field of an adapter) is Verified, Documented or in Labs. A call takes the
weakest level among the items it touches. A sign-off covers only what was exercised; it never signs off untested code.

| Level | Route | Admits | Narrowed by |
|---|---|---|---|
| **Verified** | a pass | A maintainer verified the call on a real device, by rig record or manual test, or signed off users' working reports in a `_manual.json` row. How it was tested is the maintainer's choice. | [contrary evidence](#contrary-evidence) |
| **Documented** | **a sibling's call** | The class's call differs from a Verified class's only in addressing, both run one vendor's firmware, and its documentation gives the call identically for both (Shelly's components). The PR argues it. Never a class spanning vendors (`other`, a vendor-wide family), and never a field, as a field changes the call. | a bug on the sibling reopens its Documented siblings in the same fix |
| | **a certified read** | A read that certification sends to every device the class holds: the class keys on a marker certified devices carry and known uncertified ones don't, on the one part the test runs on. Never a write, as the test's field values are its own. The PR names the marker and what slips past it ([Matter](integrations/matter/internals.md#what-decides-the-call)). | contrary evidence |
| | **a pass-through request** | An action whose failure doesn't harm (`Action.failure_harms`), where a layer below DeviceSide picks the device's call (a bridge's firmware, a converter, a driver) from a request DeviceSide sends every device of the class alike; one it composes per device still counts. The bundle's `internals.md` shows two things. The request becomes the expected call: it is the request a Verified class gets through the same layer (Hue's bridge), or the layer's published source sends it (ZHC's standard converters, from a committed table naming the release). And other software's users sent it through that layer to every brand with no reported departure, or, where none sends it, the driver declares the capability the call is gated on. It covers only the fields they sent; a read that sends nothing needs no users. A raw call DeviceSide builds qualifies only on a class this route admits, where every known failure is visible to the caller. | at the narrowest key, cited: one report of a device failing the request, or misreading, on the report alone (the layer's upstream issues included); a departure the layer's source shows at its next bump. Splitting off a model shipped outside Labs is a withdrawal (tenet 11): a maintainer keeps it with a reason or excludes it with a source. |
| **Labs** | a sourced call | Built on a [sourced call](#no-known-method-not-built-yet-in-labs) no real device has passed and no Documented route admits, or held back by a maintainer. Refused unless the Labs option is on. | |

Documented also needs that no known class departs. A field can be in Labs on some classes alone (`labs_fields(...)`,
`AdapterScope.class_labs`) while it keeps its `fields` level on the rest: with the Labs option off it is dropped on
those classes (`fields_dropped`), not refused; with it on, the call is Labs.

## Device classes

A **class** is the set of devices that get the same call and run the same firmware family. The integration declares
its classes (`IntegrationInfo.classes`) and names each target's (`IntegrationInfo.capability`); every adapter sees the
same one and maps those it serves to its own branch. A scope holds a level per class, so a record on one class proves
nothing about another, except that it puts the class's kin in Labs ([In Labs](#no-known-method-not-built-yet-in-labs)).
On a single-vendor API the class is what the call addresses (Shelly: the RPC component); on a multi-vendor protocol it
follows the vendor (Zigbee2MQTT: `hue`, `tuya_countdown`, `other`) and, where evidence is per identity, the identity
(a countdown plug's maker string with a record of its own). Classes split from one class are **kin**: the same call on
the same firmware family, differing only in whose evidence they hold.

- **Unknown is never Verified.** A device no rule matches gets the default class (`IntegrationInfo.default_class`),
  which the registry refuses at Verified in any scope. Spanning vendors, it is Documented only by a certified read or a
  pass-through request; otherwise it is `labs(...)` where research predicts most of it accepts the call (Zigbee 3.0
  certification and the dimming commands: [internals](internals.md#shared)), else not built yet. No pass lifts it: a
  record on a device outside the named classes adds a class named for its maker (Zigbee2MQTT: `innr`), as one maker's
  record proves nothing about the rest. Where a call is known to harm, a target DeviceSide can't class yet is refused
  (`class_unknown`, below).
- **A level per class and domain.** A class's level holds on every domain the adapter serves unless its entry names
  some (`verified(..., domains=...)`, core's `OnDomains`); on the rest it has no entry and counts as a Labs item. A
  record in one domain proves nothing in another: Zigbee2MQTT's `hue` is Verified on lights, and a Hue plug is not
  built on `turn_on_for`. A `NotBuilt` entry can name domains too, refusing the class on those alone.
- **A class names its domains.** Each class declares the entity domains its devices' features belong to (a TS011F
  plug: switch, even where Zigbee2MQTT shows it as a light). A scope never holds a class on an action that serves none
  of its domains, so an action for lights alone refuses a plug as not built yet (the registry checks). An action that
  serves one admits the class in every domain it serves, at its level there; an entry with `only=True` admits it on
  its named domains alone and refuses it elsewhere as not built yet.
- **A read serves only what another action does.** `get_attributes` admits only the classes, on the domains, that
  another of the integration's actions admits (the registry checks). A class it would read with nothing to return is a
  `no_known_method` entry instead (a Tuya countdown plug's time left).
- **One axis per integration.** An integration that names classes holds them in every adapter's scope, and only those
  it declares; one that names none holds them in none (the registry checks). A new integration names its classes, or
  its PR argues it has one: no known device behind it answers the same call differently.
- **One fact, one home, in code.** Classes, levels and refusal entries live in the integration's package; the cards
  are generated from them.
- **Groups.** A native group takes the weakest level among its members' classes, or falls back to its members; when,
  and what an unlisted group does: `core/dispatcher.py`'s module docstring, Native groups.

### The split rule

- A different gateway or API is a separate integration, with a `detect` hook on the same `ha_domain` (Zigbee2MQTT
  beside MQTT).
- A different device behind the same API is a class.
- A class that needs a different payload gets an `OwnCall` in `AdapterScope.own_calls`, which the dispatcher hands
  the adapter (`Adapter.execute_own`) in place of `execute`, so a native group with a member of it falls back.
- An adapter splits only when a class needs a different result contract. A different duration limit is a per-class
  setting first (the `OwnCall`'s `DurationLimits`).
- **Split off the exception, not the class.** Devices known to depart from a class's call move into a class of their
  own, at their own evidence's level; the rest keeps its level. The whole class drops a level only when no rule can
  tell the departing devices apart. Split off an exception only once a pass, on the class or its kin, shows the rest
  works, or, in a class in Labs on a source, for an identity reported harmed; any other failure in a class with
  neither is the class's result.
- **Key a class on what decides the outcome:** the integration's routing where it picks the call, otherwise the
  device's identity. Classes match on manufacturer and model until a firmware boundary decides behavior.

No matcher, per-class setting or card tier is built before an integration needs it (tenet 6).

## No known method, not built yet, in Labs

| Kind | When | Where it lives | Result |
|---|---|---|---|
| **No known method** | No known call does what was asked and fails without harm: a device limit as far as anyone knows, so users shouldn't ask for it built (a class whose only known call is unsafe has none). Per adapter. | the scope's `no_known_method`: what, why, source | refused `no_known_method`; 🔴 on the compatibility page |
| **Not built yet** | A call that would work is known or plausible and unbuilt, including a class no source admits to Labs or that research predicts mostly fails today's call. | in neither `capabilities` nor `no_known_method` | refused `not_built`; off the card |
| **`NotBuilt` entry** | Not built yet, for a class today's call would harm, on an action whose failure harms (the registry refuses one elsewhere). | the scope's `not_built`: why, source | refused `not_built`; off the card |
| **`class_unknown`** | On an action whose failure harms and whose scope has a `no_known_method` or `not_built` entry, even with Labs on: a target whose class rests on information DeviceSide lacks (a group whose members aren't listed, a device not yet placed) or that it can't class. | `core/dispatcher.py`'s docstring (Planning), `AdapterScope.refusal`; when a device is placed: each integration's page ([Zigbee2MQTT's](integrations/zigbee2mqtt/index.md#device-classes)) | refused `class_unknown`; a target not yet placed clears once the integration reports what it lacked |

A group with a member not yet placed falls back to its members, so only that member is refused. A device placed in the
default class from full information runs at its class's level, as does every target of an action no class is harmed by
(one it can't class runs in Labs). A refused target raises when named and is skipped when it came indirectly
([action-behavior.md](action-behavior.md)).

**When today's call harms a class.** A failure harms when it is deferred and unattended: the device ends in an on or
off state the user didn't ask for, after they've stopped watching, with no visible cue. The timed and scheduled on/off
actions harm; dimming, color, `stop`, writes and scenes don't, as a wrong result shows at once and one tap fixes it;
a read never harms. Each action states it, for every adapter (`Action.failure_harms`).

**In Labs.** A class enters Labs on a sourced call, a cited reason to expect it works: the vendor's documentation, an
upstream integration that ships the call, or research, including a pass on a device of the class (the builder's own
probe or run counts) or of the exact call on its kin. No pass is needed. Without a source, or with research predicting
most of the class fails, it stays not built. Labs admits only what its source names: a pass admits the class only where
it is one firmware family; a document, upstream integration or research admits the vendors, models or identities it
names, not the class around them. On an action whose failure harms, turning on Labs is the user's consent, so a class
in Labs runs with the option on; an identity reported harmed is split off with a `NotBuilt` entry. On a failed report,
the maintainer triaging it fixes it, keeping the class in Labs, or makes the class not built, as their time allows; one
they stop fixing becomes not built. A not built class returns with a PR that brings a sourced call or a passing run.

## Contrary evidence

A report changes a level only through a maintainer (tenet 7):

- **A failed report on a class in Labs** is the class's result ([In Labs](#no-known-method-not-built-yet-in-labs)).
  The rest of this list is for a Verified or Documented class.
- **A credible report of a harmful failure on DeviceSide's own call** lets an integration maintainer refuse the
  identity it names on that action, on the report alone, citing it: not built yet if a known or plausible call would
  serve it, otherwise no known method.
- **The identity is the narrowest a class rule can key on:** model ID with manufacturer string, plus firmware where
  that decides. A vendor is not normally refused whole on one report; split off the exception. A rule keyed on a
  vendor needs research.
- **Not evidence against the device:** a failure on a different call (an external converter's), or a report that
  contradicts the identity's own passing record. The maintainer retests, or weighs the two.
- **Anything else** changes no level until a maintainer root-causes it. The fix or demotion lands with the finding,
  and a demotion of a shipped feature is a withdrawal (tenet 11).

## The Labs flag

Labs is the lowest [level](#levels), marked in code `labs(...)` beside `verified(...)` and `documented(...)`, and
`labs_fields(...)` for a field in Labs on some classes alone. A call's domain is always among the items it touches, so
an adapter whose domains are all `labs(...)` is flagged whole. A flagged item is refused unless the user turns on the
Labs option (a `labs_fields` field is dropped instead). The dispatcher is the only gate: adapters never read the
option, and turning it on changes how no other item behaves.

A new item ships at the level tenet 10 and [Levels](#levels) give. Nothing counts users' reports in code: a maintainer
judges whether a pass is enough (tenet 7). A maintainer may keep a complex tested item in Labs to soak with
users who opt in, as an exception, giving the reason in its PR. A field passes only on a test that sent it, which no
check can tell ([deferred](deferred.md#field-lifts-checked-against-a-record)). No pass lifts the default class.

Lifting a flag makes `labs(...)` into `verified(...)` on a pass (an adapter flagged whole: its domains) or into
`documented(...)` on a route its PR argues, or removes a `labs_fields(...)` entry. It changes the integration's
package, so one of its maintainers approves it; a [family](design.md#glossary)'s maintainers set their own classes'
levels the same way but change no refusal entry ([CLAUDE.md](../CLAUDE.md#maintainers)). Flagging a feature shipped
outside Labs is a withdrawal (tenet 11). The compatibility page never credits a model from a pass on a flagged item, and
the README folds a card's Labs-only lines (`scripts/gen_compat.py`).

## Caveats

`AdapterScope.caveat` holds a reason (an issue URL), set and cleared by a repo maintainer. It is not a level: levels
are about evidence, caveats about risk and people. Each gives one setup warning and one card mark:

- **🔧 Untested fix:** changed, and nobody could test it before the release. It ships live. A sign-off clears it,
  including a maintainer's `_manual.json` row citing a user's working report.
- **⚠️ Unmaintained:** nobody is fixing it. It ships live. Cleared when someone fixes the adapter or adopts the
  integration. An integration whose maintainers are all gone gets it on every adapter.

A deprecation, or any other withdrawal of a shipped feature (tenet 11), gets a hand-written note in that release's
notes, not a caveat.

*Example:* a low-risk fix to a broken adapter whose devices no maintainer has lands before the cut. It ships with
🔧 Untested fix and the issue URL; a user's working report, cited in a maintainer's `_manual.json` row, clears it.

## Release gate

Each action whose calls changed since the last release tag needs a sign-off, an all-Labs one aside. An action's
**call transcript**, `tests/integrations/<x>/calls/<action>.json`, holds a **segment** per distinct way the unit tests
run it: the request, each call sent at the wire with its reply, and the result
([`tests/transcripts.py`](../tests/transcripts.py); CI fails a PR whose transcripts don't match its code). An action has
changed when HEAD's transcript no longer holds every segment of the tag's, or the tag has none (tenet 9); a segment
added doesn't count. A flag lifted or a class added changes no call ([the coverage check](#the-coverage-check) holds
those). An action whose adapter has `native_groups` needs a segment run on a group.

- **Evidence binds to a transcript** by the git blob id of the one it was tested against (`calls`), and stands while
  HEAD's transcript holds every segment of it. A blob git doesn't have stands for nothing (branch runs and squash
  merges: `scripts/signoff.py`).
- **A sign-off** is the action's rig records (the plain `<action>.json` and every `<action>-<option>.json`, each format
  3, passing and standing; an option's record covers only that option) or a standing `_manual.json` row whose `calls`
  names the action, from one of the integration's maintainers, or a repo maintainer when none responds. An
  integration's actions may mix the two. Either must also hold every segment HEAD's transcript gained since the tag, so
  a run from before the change can't sign it off; with no tag's transcript, standing is enough.
- **A call changed on purpose** reopens its action's evidence: regenerate the transcripts with
  `scripts/gen_transcripts.py` and commit them with the change; only its own suites rerun (`check_release.py
  --signoffs --reruns`). A suite that is no action's (`config_entry.json`) is outside the gate.
- **Prefer the rig** where it covers an integration: it is repeatable and catches what a person doesn't. A manual
  sign-off on a rig-covered integration says why in its PR. Guidance, not a gate check; rig evidence is no level.
- **RCs need no sign-off:** the gate runs at `cut-release`. `cut-release` checks the latest RC's commit, so land
  sign-offs or Untested fix caveats before the last RC.
- **An all-Labs action needs no sign-off or caveat:** none of its calls runs with the Labs option off (its adapter
  flagged whole, or every class its scope serves in Labs in every domain it serves). A field in Labs on some classes
  alone doesn't make it all-Labs. A mixed action still needs a sign-off: a rerun on the devices a maintainer has gives
  it, as a sign-off must hold the gained segments, not have exercised them.
- **No sign-off at the cut:** `cut-release` fails unless each such changed action carries 🔧 Untested fix on its
  adapter; no other caveat stands in. A repo maintainer picks what is most likely to work for users (tenet 1): hold the
  fix back when the current code mostly works; ship it marked 🔧 Untested fix when the current code is broken and the
  fix is low-risk; or, when it is risky, put it behind the Labs flag, alone when that makes the action all-Labs, and
  marked 🔧 Untested fix otherwise.
- **Coverage:** every module under `core/` and `integrations/`, bar `__init__.py`, needs 95% line coverage (CI).

### Sign-off format

Test records are JSON files in the bundle's `test-records/`, each checked against
[`docs/test-records.schema.json`](test-records.schema.json), the format's one home, which gives each field and what
each format credits. The rules it serves:

- **A rig record**, `<suite>.json`, is named for its step file (`<action>.json` or `<action>-<option>.json`) and
  credits its action only when its `action` and `options` agree; a leading `_` is `_manual.json`'s and
  `_facts.json`'s alone. It passes only when no test failed and one passed. Format 3 cites the transcript its run tested
  (`calls`); formats 1 and 2 sign nothing off, and a rerun replaces them.
- **A test names the devices it reached** and the class the call reached on each, as the action's result reports it
  ([action-behavior.md](action-behavior.md#what-a-response-looks-like)), or null where the integration named none. A
  Zigbee device is named by its Zigbee model ID on every integration, with its manufacturer string, as one model ID
  carries many makers' strings. Every model a file names must be in `docs/models.yaml` or its bundle's `devices.yaml`.
  A native group's or a scene's test lists the members and carries `group`. A Home Assistant scene's test lists the
  lights it holds; one it holds off is listed with class null, as DeviceSide turns it off through core's
  `light.turn_off` and no response names its class, so on an integration that names classes it credits nothing.
- **`via` names the action whose adapter served a test's call** when it isn't the record's own (a Home Assistant
  scene's test in `set_scene.json`: `set_attributes`, which `set_scene` rides). Such a test credits nothing to the
  record's action, toward coverage or the cards, and a record signs its action off only when a test without `via`
  passed (a failing one fails the record, `via` or not); the riding action's proof is the ridden action's records.
- **`_manual.json`**: a maintainer's hand tests, a row each, added in a PR: each device a model ID with the class it
  reached and its firmware where known, and the actions that passed on all of them, each with its transcript's blob.
  `signed_by` is the maintainer who vouches for it. `scripts/signoff.py` prints the row from HEAD's transcripts, so run
  it at the commit you tested; `commit` records that, unchecked. A row may rest on users' working reports (`reports`,
  issues in this repo), its `commit` and `calls` then the release they ran (`signoff.py --at <tag>`). A format 2 row
  signs nothing off.
- **Model IDs come from the device:** its label, the vendor's app or HA's device page, never a household's device name
  or a driver's or bridge's name (as on Control4's Director); the manufacturer as the schema's `manufacturer` gives it.
- **`_facts.json`**: the fact cases' results, a row each, only ever added.

### The coverage check

Every class an adapter's scope holds as Verified needs, for that action, a passing record test that reached it, or a
`_manual.json` row naming it: one held on every domain, in any domain; one held on some domains alone, in each of them
(a manual row names no domain, so it covers each). On an integration that names no classes, each Verified domain needs
the same. `scripts/gen_compat.py` warns of each gap on
every PR and says what credits a class; `scripts/check_release.py --signoffs` fails on it at `cut-release`.

## Worked examples

- **Fact test or research (tenet 2).** A bulb set to red while off must come on red, with no flash of its old color.
  HA's state can't show the flash and DeviceSide's call sequence decides it, so it is a watched fact test
  (`set_attributes`, `sets_color_while_off`). A Hue bulb's timer can't be stopped through the bridge, so Hue ships no
  `turn_on_for`; no call depends on that, so it lives in `research/`.
- **Retest (tenets 8 and 9).** After Zigbee2MQTT's run, a refactor of a shared helper leaves every transcript unchanged:
  every record stands. A fix to `stop`'s call changes its transcript, reopening `stop`'s evidence alone, and a rerun
  of the `stop` suite signs it off.
- **Proof follows the class (tenets 4 and 5).** A Tuya TS011F plug ran the Zigbee timed-on timer only Tuya's way: given
  the light's call, one plug stayed off and another switched on about ten times later than asked and stayed on
  ([internals](internals.md#tested-behavior)). That reopened "a Zigbee switch takes the light's timed-on call", and
  with research predicting most plugs fail it, `turn_on_for` refuses every switch class without a pass as not built on
  ZHA and Zigbee2MQTT. Lights given the identical call differ by firmware too
  ([2026-11-14](integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)), so a Hue bulb's record proves
  the call on `hue`, not on every Zigbee light.
- **Contrary evidence.** ZHA's `_TZ3000_typdpbpg` reads tenths as seconds, and Tuya's call would serve it: not built
  yet. Z2M #25434's `_TZ3000_dg7fdg92` failed under a converter's plain `onOff()`, a different call, so it keeps
  `tuya_countdown`'s level, in Labs, until a pass on its maker string.
- **Documented routes.** Zigbee2MQTT's `standard_light` is Documented on the fades, `stop`, `set_attributes` and
  `get_attributes`; Paulmann's 924.70, reported failing a color read, stays in `other`
  ([the table and the bump](integrations/zigbee2mqtt/internals.md#standard_lights)). Hue's `other` is Documented on
  every action ([internals](integrations/hue/internals.md#device-classes)). Shelly's `turn_on_for` and `turn_off_for`
  are Documented on `Light`, `CCT`, `RGB` and `RGBW` as siblings of `Switch` and `RGBCCT`
  (`integrations/shelly/addressing.py`).
- **Lifting a flag.** Shelly dimming on `Light` is `labs("Light")`, as a report of a Gen3 Dimmer jumping on `DimStop`
  keeps it from Documented. A passing `raise_brightness` run on a Gen3 Dimmer lets a Shelly maintainer, once they judge
  it enough, make it `verified("Light")`. Zigbee2MQTT's auto-off on Tuya and Sonoff inching switches entered Labs on
  research into Z2M's definitions and users' upstream reports
  ([Zigbee2MQTT](integrations/zigbee2mqtt/index.md#tuya-inching-switches)); a user's working report, cited in a
  maintainer's `_manual.json` row, lifts it.
