# Evidence

What DeviceSide must know about a device before a feature ships, and what a release needs. This page is the one home
for these rules; other docs point here. Settled in [the evidence-rules plan](plans/2026-11-12-evidence-rules.md);
device classes in [the device-classes plan](plans/2026-11-14-device-classes.md).

## Tenets

1. **User experience is the north star.** Actions make devices do what users expect, predictably and with low
   latency, and DeviceSide offers only what's likely to meet that bar. If that holds, nothing else matters.
2. **Probe before you build.** When unsure how a device responds to a call, run a cheap probe rather than assume.
   Record what it shows as a fact (the bundle's `internals.md`, dated). Where its source goes depends on whether a
   shipped call depends on the fact staying true:
   - **Yes: a fact test.** The rig re-runs it (`--facts`) when that call changes, and `test-records/_facts.json` keeps
     each dated result. A watched test covers what only a person can see.
   - **No: `research/`.** The fact decided scope or design, and no shipped call depends on it. A dated file, never
     edited; if evidence suggests it has changed, repeat the probe by hand in a new file.

   *Example:* a bulb set to red while off must come on red, with no flash of its old color. HA's state can't show the
   flash, and the call sequence DeviceSide sends decides it, so it's a watched fact test (`set_attributes`,
   `sets_color_while_off`). A Hue bulb's timer can't be stopped through the bridge, so Hue ships no `turn_on_for`. No
   call depends on that, so it lives in `research/`.
3. **Verify, then trust.** A verified fact stands across firmware, HA and code changes until evidence contradicts it.
   Nobody goes looking for things to re-prove.
4. **Surprises reopen facts.** A bug or unexplained behavior triggers a root-cause dive. The finding joins the fact
   base and is then trusted in turn. Log so that the first bug report already holds the diagnosis: what DeviceSide
   sent, what the device answered, and which way DeviceSide went because of it.
5. **Proof follows the call and the class.** Evidence is about how a class of devices responds to a call
   ([device classes](#device-classes)). Any code that sends the same call to the same class inherits it, and unit tests
   pin the call. So does a no known method entry: it may cover every action that sends that call to that class or
   identity, such as `turn_on_for`, `set_auto_off` and `turn_off_for` where they send the same frame.
6. **Simplify relentlessly.** Prefer fewer calls, fewer round trips and less machinery. A new guardrail needs
   evidence that its failure happens (a probe, record or report), and names the user-visible failure it prevents and
   what it replaces; until then, log so the first report would show the failure. An existing guardrail stays until
   evidence shows its failure doesn't happen; meanwhile, look for ways to make it cheaper. A new rule names the
   user-visible failure it prevents and what it replaces.
7. **Maintainers judge sufficiency.** Tooling records evidence, and maintainers decide what's enough. Gates check that a
   sign-off exists, not how thorough it was.
8. **Test to decide.** Every hardware run costs time and needs a person at hand, even one nobody watches, so run one
   only when its result takes a decision. Five decisions do:
   - *a design choice:* tenet 2's probe, before the build. A call already seen working on the device (your own
     automation, an upstream integration that ships it, a research file recording a run) needs none: cite it in
     the bundle's `internals.md`. A vendor's document alone still needs the probe;
   - *a foundation:* before further steps build on a design no verified fact covers, one run of the rig cases whose
     failure would discard that work;
   - *lifting a flag* ([the experimental flag](#the-experimental-flag));
   - *a surprise:* the run that root-causes it (tenet 4);
   - *a release:* the sign-off, due before the last RC, or the one that clears a caveat ([release gate](#release-gate)).

   Run a test at the last point that can still take its decision. For a device the rig or a maintainer can reach,
   that is the release's run, so merging a PR waits for none: unit tests pin the call, a new item starts flagged, the
   gate runs at the cut, and the code may change again before then. For a contributor's own devices, it is their pull
   request, as no later run is sure to reach them: one test of the finished build, at the commit whose calls ship
   ([CONTRIBUTING](../CONTRIBUTING.md), Fast track). It shows the build works, which a maintainer needs to merge it
   and, later, to lift its flag. A plan gates a step on a run only by naming the decision its result takes. This
   prevents a release held up by runs whose results changed nothing, and replaces the practice of a rig run per step
   or per PR.
9. **Retest what the change exercises.** After a run, a change reopens only the evidence for actions whose call, or
   whose handling of the device's reply, it changes (tenet 5), wherever the code it edits lives. A machine decides
   which: evidence binds to the action's [call transcript](#release-gate), what the unit tests saw it send and make of
   the replies, and stands while every call path it was tested on is still there, unchanged. A refactor that keeps
   every call reopens nothing, and a fix for a failing case reruns its suite, not the integration's run. This prevents
   the same passing cases being rerun at each small change, and replaces judging staleness by source changes, which
   reopened evidence on a cosmetic edit and missed a call change made in `core/`.

*Example (tenets 8 and 9):* after Zigbee2MQTT's run, a refactor of a shared helper lands, and CI finds every
transcript unchanged: every record stands. A fix to `stop`'s call lands next. Its transcript changes, which
reopens `stop`'s evidence alone, and a rerun of the `stop` suite completes the sign-off.

*Example (tenets 4 and 5):* the rig found that a Tuya TS011F plug doesn't run the Zigbee timed-on timer it is given.
That reopened "a Zigbee switch takes the light's timed-on call", and with research predicting most plugs and switches
fail it, no class without a switch pass is on trial there: `turn_on_for` refuses every switch class that call would
reach without a pass as not built on ZHA and Zigbee2MQTT, and `hue` stays Verified on lights. A lab probe then
root-caused it: the plug runs the timer only Tuya's way, and given the light's call one plug stayed off while another
switched on about ten times later than asked and stayed on ([internals](internals.md#tested-behavior)). Research also
found that even lights given the identical call differ by firmware: Hue replaces a running timer where the spec keeps
the longer one, and some IKEA and Hue models turn on and never off
([2026-11-14](integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)). So a Hue bulb's record proves
the call on the `hue` class, not on every Zigbee light.

## Levels

A scope item (an entity domain, class or field of an adapter) is Verified, Documented or Experimental; an
Experimental item is refused unless Experimental features is on. To flag a whole adapter, flag its
domains ([the experimental flag](#the-experimental-flag)).

- **Verified:** a maintainer has verified the call on a real device, by rig record or by manual test. How it was
  tested is the maintainer's choice; the rig is a tool, not a requirement.
- **Documented:** no known class departs, and the class takes either
  - **a sibling's call:** it differs from a Verified class's call only in addressing, and siblings share one vendor's
    firmware, whose documentation gives the call identically for both (Shelly's components). A class spanning vendors
    (`other`, a vendor-wide family) is never Documented by a sibling's pass, as a pass on one vendor's firmware proves
    nothing about another's. The PR argues the sibling case, and a bug on the sibling reopens its Documented siblings
    in the same fix. A field is never Documented, as it changes the call.
  - **a certified read:** certification sends the same read to every device the class holds, as the class keys on
    a marker certified devices carry and known uncertified ones don't, and on the one part the test runs on. A write
    never qualifies, as the test's field values are its own. The PR names the marker and what slips past it
    ([Matter](integrations/matter/internals.md#what-decides-the-call)).

A sign-off covers only what was exercised; it never signs off untested code.

**Contrary evidence.** A report changes a level only through a maintainer (tenet 7):

- **A failed report on a class on trial** is the class's result, handled as
  [on trial](#no-known-method-not-built-yet-on-trial) says. The rest of this list is for a Verified or Documented class.
- **A credible report of a harmful failure on DeviceSide's own call** lets an integration maintainer refuse the
  identity it names on that action, on the report alone, citing it. It's not built yet if a known or plausible call
  would serve that identity, otherwise no known method ([below](#no-known-method-not-built-yet-on-trial)).
- **The identity is the narrowest one a class rule can key on:** model ID with manufacturer string, plus firmware
  where that decides. A vendor is not normally refused whole on a single report; split off the exception. A rule
  keyed on a vendor needs research.
- **Not evidence against the device:** a failure on a different call (an external converter's), or a report that
  contradicts the identity's own passing record. The maintainer retests, or weighs the two.
- **Anything else** changes no level until a maintainer root-causes it. The fix, or the demotion, lands with the
  finding.

*Examples:* ZHA's `_TZ3000_typdpbpg` reads tenths as seconds, and Tuya's call would serve it: not built yet. Z2M
#25434's `_TZ3000_dg7fdg92` failed under a converter's plain `onOff()`, a different call, so it is no evidence
against the device: it keeps `tuya_countdown`'s level, on trial, until a pass on its maker string.

*Example:* Shelly's `turn_on_for` and `turn_off_for` calls are Verified on the `Switch` and `RGBCCT` components and
Documented on `Light`, `CCT`, `RGB` and `RGBW`: the same call, addressed to another component, which Shelly's API
documents identically (`integrations/shelly/addressing.py`).

## Device classes

A **class** is the set of devices that get the same call and run the same firmware family. The integration declares
its classes (`IntegrationInfo.classes`) and names each target's (`IntegrationInfo.capability`; in code a scope's
`capabilities`), and every adapter of the integration sees the same one; an adapter maps the classes it serves to its
own branch. A scope holds a level per class, so each class stands on its own evidence: a record on one class proves
nothing about another, except that it puts the class's kin on trial ([below](#no-known-method-not-built-yet-on-trial)).
On a single-vendor API the class is what the call addresses (Shelly: the RPC component). On a multi-vendor protocol the
call and the firmware family decide the result together, so the class follows the vendor (Zigbee2MQTT: `hue`,
`tuya_zcl`, `tuya_ts011f`, `tuya_countdown`, `tuya_mcu`, `sengled`, `gledopto`, `ikea`, `other`), and, where evidence is
per identity, the identity: a Zigbee2MQTT countdown plug's maker string with a record of its own is a class of its own.
The classes split this way from one class, the rest of it among them, are **kin**: they get the same call on the same
firmware family, and differ only in whose evidence they hold.

- **Unknown is flagged, never Verified.** A device no rule matches gets the default class
  (`IntegrationInfo.default_class`), which the registry refuses at Verified in any scope, so placing a device there
  can only make DeviceSide more cautious. Its one exception: where a call is known to harm, a class DeviceSide can't
  name yet is refused ([below](#no-known-method-not-built-yet-on-trial)). As it spans vendors, the default class is Documented only by a
  [certified read](#levels), never by a sibling's pass; it is otherwise `experimental(...)` where research predicts
  most of it accepts the call (Zigbee 3.0 certification and the dimming commands:
  [internals](internals.md#shared)), and is otherwise not built yet
  ([below](#no-known-method-not-built-yet-on-trial)).
  Nothing lifts it: a record on a device outside the named classes adds a new class named for its maker
  (Zigbee2MQTT: `innr` for an Innr bulb), as the default class holds every device no rule matches, and one maker's
  record proves nothing about the rest.
- **A level per class and domain.** A class's level holds on every domain the adapter serves, unless its entry names
  some (`verified(..., domains=...)`, core's `OnDomains`): on the rest its class has no entry, so it counts as
  Experimental. A record on a class in one domain proves nothing about it in another: Zigbee2MQTT's `hue` is Verified
  on lights, as every record ran on a bulb, and a Hue plug, a switch, is not built on `turn_on_for`. A `NotBuilt`
  entry can name domains too, refusing its class on those alone while its capability entry serves the rest.
- **A class names its domains.** Each class declares the entity domains whose features its devices have (a TS011F
  plug: switch, even where Zigbee2MQTT shows it as a light; Gledopto: light; other brands: light and switch). The
  guarantee is per action: a scope never holds a class on an action that serves none of its domains, so an action for
  lights alone refuses a plug as not built yet, and its card leaves the plug off (the registry checks). An action
  that serves one of them admits the class in every domain it serves, at the class's level there: one serving
  switches takes a TS011F that Home Assistant shows as a light. An entry held on some domains with `only=True` admits
  the class there alone and refuses it elsewhere as not built yet. A class whose domains show different features gets
  a card line per domain ("other brands' lights", "other brands' plugs and switches"), except scenes, which join the class's light line as "set scene".
- **A read serves only what another action does.** Get attributes reads state back around DeviceSide's other
  actions, so it admits only the classes, on the domains, that another of the integration's actions admits (the
  registry checks): no other action serves a Tuya ZCL switch yet, so it reads a Tuya ZCL device as a light alone. A
  class it would read with nothing to return is a `no_known_method` entry instead (a Tuya countdown plug's time left).
- **One axis per integration.** An integration that names classes holds them in every adapter's scope, and only the
  classes it declares; one that names none holds them in none (the registry checks). A new integration names its
  classes, or its PR argues that it has one: that no known device behind it answers the same call differently.
- **One fact, one home, in code.** Classes, levels, and no known method (`no_known_method`) and not built yet
  (`not_built`) entries live in the integration's package, and the cards are generated from them; where each
  piece goes is CLAUDE.md's [Where facts go](../CLAUDE.md#where-facts-go).
- **Groups.** A native group takes the weakest level among its members' classes. When a member's class is refused,
  takes a call of its own, or is Experimental while Experimental features is off, the group falls back to its members:
  it gets no entry of its own, its members answer for it, each judged on its own, and it is refused only when none of
  them ran. One whose members the integration can't list can't fall back: it counts as Experimental, and is refused
  whole while Experimental features is off, and with it on where a call is known to harm
  ([below](#no-known-method-not-built-yet-on-trial)). The rules: `core/dispatcher.py`'s module docstring, Native groups.

### No known method, not built yet, on trial

Three ways a class isn't served to everyone on an action, each handled differently. The first two are the kinds of not
supported, where DeviceSide can't do the action for the class, each named for why:

- **No known method:** no known call works on the class: a device limit as far as anyone knows, which the label
  tells users not to ask DeviceSide to build. A method is a call that does what was asked and fails without harm, so
  a class whose only known call is unsafe has none; the entry's reason says which. The adapter's scope lists it in
  `no_known_method`, with what, why and a source; the dispatcher refuses it (`no_known_method`), and the card marks
  it 🔴. It is per adapter, as one class can fail one action's call and answer another's.
- **Not built yet:** a call that would work on the class is known or plausible, and nobody has built it. That includes a
  class not admitted on trial (below), as research predicts most of it fails the default call or no pass (on it or its
  kin) or research admits it, while another call is known or plausible. The integration names it, and the adapter's
  scope holds it in neither `capabilities` nor `no_known_method`. It is refused (`not_built`), and the card leaves it
  out, as no one can list every feature that could be built.
- **On trial (Experimental):** a class still behind the flag, admitted on a reason to expect the call works: a pass on a
  device of the class (the builder's own probe or run counts, tenet 2), a pass of the exact call it would get on its kin
  ([above](#device-classes)), or research predicting most of the class accepts it. Without any of these, or with
  research predicting most fail, it stays not built. A trial admits only what its evidence names: a pass, on the class
  or its kin, admits a class only where it is one firmware family, and research admits the vendors or identities it
  names, not the class around them; the rest of the class stays not built. On an action whose failure harms, turning on
  Experimental features is the user's consent to its trials, so a class on trial there runs with the option on. An
  identity reported harmed there is split off as not built (`NotBuilt`, below), and a target not yet placed is still
  refused (`class_unknown`, below). On a failed report, the maintainer triaging it takes on the fix, keeping the trial,
  or makes the class not built, as their time allows; one they stop fixing becomes not built. A not built class returns
  with a contributor's PR and a passing run on their own device. The class is in scope as `experimental(...)` and runs
  behind the flag.

Harm is a separate safety axis, which the action decides (below). On an action whose failure harms, a class not
built yet that today's call would harm gets an entry of its own in the scope's `not_built` (`NotBuilt`, with why and a
source), which the card leaves out, as it does any other. Any other class not built yet needs no entry, as
leaving it out refuses it, and the registry refuses a `not_built` entry on an action whose failure doesn't harm.

- **Split off the exception, not the class.** When devices are known to depart from a class's call, a rule moves them
  into a class of their own, at the level their own evidence supports. The rest of the class keeps its level. The whole
  class drops a level only when no rule can tell the departing devices apart. Split off the exception only once a pass,
  on the class or its kin, shows the rest of the class works; a failure in a class with neither is the class's result,
  not an exception.
- **Key a class on what decides the outcome:** the integration's routing where it picks the call, otherwise the
  device's identity.
- **When today's call harms a class.** A failure harms when it is deferred and unattended: the device ends in an
  on or off state the user didn't ask for, after they've stopped watching, with no visible cue. So the timed and
  scheduled on/off actions harm when they fail (`turn_on_for`, `turn_off_for`, `set_auto_off`, `set_auto_on`,
  `clear_auto_off`, `clear_auto_on`); dimming and color (`raise_brightness`, `lower_brightness`, `raise_hue`,
  `lower_hue`, `raise_saturation`, `lower_saturation`), `stop`, `set_attributes` and `set_scene` don't, as a wrong
  result shows at once and one tap fixes it; and `get_attributes` only reads, so it never harms. The action states it
  (`Action.failure_harms`), for every adapter of that action.
- **Where a call is known to harm, a class not yet known is refused.** An adapter whose action's failure harms and
  whose scope holds a `no_known_method` or `not_built` entry refuses a target whose class rests on information
  DeviceSide doesn't have yet, even with Experimental features on: a group whose membership isn't listed, or a device
  not yet placed (its identifying strings haven't been received, so they could still move it into a harmed class). A
  target DeviceSide can't class at all is refused the same way. A group with a member not yet placed falls back to
  its members, so only that member is refused. A device no rule matches gets the default class, and one placed there
  from full information isn't refused but runs at its class's level, as does every target of an action no class is
  harmed by (one it can't class, as Experimental; Unknown is flagged, never Verified, above). The refusal is
  `class_unknown`; for a target not yet placed it clears once the integration has reported what it lacked. How core
  applies it: `core/dispatcher.py`'s module docstring, Planning, and `AdapterScope.refusal`; when a device counts as
  placed: each integration's page, as [Zigbee2MQTT's](integrations/zigbee2mqtt/index.md#device-classes). ZHA, Hue
  and Matter mark their entries in steps 7 to 9 of the [device classes plan](plans/2026-11-14-device-classes.md).

A refused target raises when named and is skipped when it came indirectly, as `supports()` refusals do
([action-behavior.md](action-behavior.md)).

### The split rule

- A different gateway or API is a separate integration, with a `detect` hook on the same `ha_domain`, as Zigbee2MQTT is
  beside MQTT.
- A different device behind the same API is a class.
- A class that needs a different payload gets a call of its own: an `OwnCall` in `AdapterScope.own_calls`, which the
  dispatcher hands the adapter (`Adapter.execute_own`) in place of `execute`, so a native group with a member of it
  falls back to its members.
- An adapter splits only when a class needs a different result contract. A different duration limit is a per-class
  setting first (the `OwnCall`'s own `DurationLimits`).

No matcher, per-class setting or card tier is built before an integration needs it (tenet 6): Zigbee2MQTT, the most
varied integration, sets the bar. Classes match on manufacturer and model until a firmware boundary decides behavior.

### The coverage check

Every class an adapter's scope holds as Verified needs a passing record test, or a `_manual.json` row, for that action
that reached it; one held on some domains alone needs it in each of them, from a test in that domain (a manual row names
no domain, so it covers each). A record names the class each test's devices reached, and a manual row each device's. A
native group's test credits each member's class, from its members' entries (the response's `member_capabilities`,
[action-behavior.md](action-behavior.md#what-a-response-looks-like)), as the one call reached each member (a null one
credits none; the cards add "native groups", never the members' models). A group with a null-class member is on no card,
as "native groups" needs every member's class named and unflagged, while its named members still count here; a manual
row credits every class it lists to every action it passed, so a row whose actions reached different classes is split. A
manual row may carry `group`, as a rig group test does: its devices are the members, credited as a group test's are; the
evidence table shows it as "group, by hand", and the card "native groups", with no ✔ from it. A scene's test is a
group's, its members the scene's lights. A null class credits none, here or on the cards, as does a test that didn't
pass. `scripts/gen_compat.py` warns on each gap on every PR, so a developer sees it early, and names it, for example
"zigbee2mqtt turn_on_for: `hue` is Verified but no record reaches it"; `scripts/check_release.py --signoffs` fails on it
at `cut-release`, with the other release gates. Like every gate, it checks that evidence exists, not that it suffices
(tenet 7), and it applies to integrations that name classes.

*Example:* with Zigbee2MQTT's classes `hue`, `ikea`, `tuya_zcl`, `tuya_ts011f`, `tuya_mcu`, `sengled`, `gledopto` and
`other` (and the countdown plugs' below), and only Hue bulbs in its records, `turn_on_for` can be Verified on `hue`
alone. Research names IKEA's lights as running the timer, so `ikea` is `experimental(...)` on lights, with the two
bulbs reported to stay on split off as not built; the other makers it names have a report or so each, too few to put them on trial, so `other`
is not built yet, with an entry, as today's call would leave some of it on. A record on an Innr bulb adds an `innr` class, Verified on its own
evidence, and `other` stays as it is. The Tuya classes, which Tuya's own countdown call drives but the Zigbee timer
leaves on (Zigbee2MQTT turns it into a plain on), are not built yet, each with an entry; the TS011F plugs the
countdown call is built for take it Verified on each maker string with a record of its own, its own class, so the
check asks each string for its record, and the rest of `tuya_countdown` takes it on trial, as those strings are its
kin, with the string reported harmed split off as not built, with an entry. The Sengled, which ignores today's call,
needs a call that isn't built, so it is not built yet too.

## The experimental flag

Experimental is the lowest [level](#levels), and the flag is that level: the item is not yet judged ready for
everyone. In code it is the per-axis marker `experimental(...)`, beside `verified(...)` and `documented(...)`. A call
takes the weakest level among the items it touches, its domain always among them, so an adapter whose domains are all
`experimental(...)` is flagged whole. A flagged item is refused unless the user turns on the Experimental features
option. The dispatcher is the only gate: adapters never read the option, and turning it on never changes how any
other item behaves.

Every new feature (action, integration, domain, capability or field) starts flagged, and soaks behind the flag with
users who opt in. A class is admitted behind the flag only on the evidence [on
trial](#no-known-method-not-built-yet-on-trial) names (a pass on the class or its kin, or research), which also handles
a failed report; without it, it stays not built. A passing rig record or `_manual.json` sign-off on a flagged item is
evidence a maintainer can use to lift its flag for the next release, skipping that soak; it is not a requirement to lift
it. Whether to lift is the maintainer's judgment, by how complex the feature is and how complete its tests are: a
developer may run the first few rig cases before the full suite exists, so a flagged item may have passing runs and stay
flagged. Lifting makes `experimental(...)` into `verified(...)` (an adapter flagged whole: its domains); a flagged item
that qualifies as Documented becomes `documented(...)` in a PR that argues the sibling case ([Levels](#levels)). Lifting
a flag is a change to the integration's package, so one of its maintainers approves it, as for any change there
([CLAUDE.md](../CLAUDE.md#maintainers)). A [family](design.md#glossary)'s maintainers set their own classes' levels the
same way, but change no refusal entry ([CLAUDE.md](../CLAUDE.md#maintainers)).

For an item no maintainer can test, users' working reports can verify it through a maintainer's `_manual.json`
sign-off, whose PR body cites them ([CLAUDE.md](../CLAUDE.md#where-facts-go): rule evidence goes in the PR body). The
maintainer judges how many are enough (tenet 7); nothing counts them in code.

The cards never credit a tested model from a pass on a flagged item while its flag stands, and keep Experimental lines
(⚪ with no 🟢 or 🟡, though 🔴 may sit beside it) to at most a quarter of all card lines, counted across every card,
folding two or more top-level ones on a card into one "⚪ on trial" line (`scripts/gen_compat.py`, which fails over
the cap).

*Example:* Shelly dimming on `Light` is `experimental("Light")`: a user's report of a Gen3 Dimmer jumping on
`DimStop` keeps it from Documented. A passing `raise_brightness` run on a Gen3 Dimmer credits no model on the card and
lets a Shelly maintainer lift the flag, once they judge the tests complete: their PR makes it `verified("Light")`.

## Caveats

`AdapterScope.caveat` holds a reason (an issue URL), set and cleared by a repo maintainer. It is not a level: levels
are about evidence, caveats about risk and people. Each gives one setup warning, one card mark and one release-notes
line:

- **🔧 Untested fix:** changed, and nobody could test it before the release. It ships live, with a call for testers
  in the release notes. A sign-off clears it, including a maintainer's `_manual.json` row citing a user's working
  report.
- **⚠️ Unmaintained:** nobody is fixing it. It ships live. Cleared when someone fixes the adapter or adopts the
  integration. An integration whose maintainers are all gone gets it on every adapter.

A deprecation gets a hand-written note in that release's notes, not a caveat.

*Example:* a low-risk fix to a broken adapter whose devices no maintainer has lands before the cut. It ships with
🔧 Untested fix and the issue URL; a user's working report, cited in a maintainer's `_manual.json` row, clears it.

## Release gate

Each action whose calls changed since the last release tag needs a sign-off. An action's **call transcript**,
`tests/integrations/<x>/calls/<action>.json`, holds a **segment** for each distinct way the unit tests run it: the
request, each call sent at the wire with its reply, and the result. [`tests/transcripts.py`](../tests/transcripts.py)
records them and gives the normalization rules; CI fails a PR whose transcripts don't match its code. An action has
changed when HEAD's transcript no longer holds every segment of the tag's, or the tag has none: a segment changed or
removed counts, wherever the code that changed it lives (an integration's package, `core/`, `actions/`); a segment
added (a new test, a new class's own call) doesn't, nor does a source change that leaves every segment as it was. A
flag lifted or a class added changes no call; the [coverage check](#the-coverage-check) holds those. An action whose
adapter has `native_groups` needs a segment run on a group, which `--transcripts` enforces: without one, a change to
what it does on a group reopens no evidence.

- **Evidence binds to a transcript** by the git blob id of the one it was tested against (`calls`), and **stands**
  while HEAD's transcript of the action holds every segment of it. A blob is its content's hash, so a run on a PR
  branch still resolves once the PR squash-merges with that transcript unchanged, and its records or row can land in
  the same PR. Any later edit to the transcript on the branch, even an added segment, leaves the run's blob on the
  branch alone, gone after the squash: retest and reprint the row with `scripts/signoff.py`, or rerun the suite, at
  the transcript that merges. A blob git doesn't have stands for nothing.
- **A sign-off** of an action is either of:
  - **its rig records:** the plain `<action>.json` and every `<action>-<option>.json`, each format 3, passing and
    standing. A record with an option set ran only that option, so the plain call needs its own, and a failing
    option's run isn't outvoted by the others.
  - **a `_manual.json` row** whose `calls` names the action and stands, from one of the integration's maintainers, or
    a repo maintainer when none responds.

  An integration's actions may mix the two. A format 1 or 2 record, or a format 2 row, signs nothing off. Either
  must also hold every segment HEAD's transcript has that the tag's lacks (added or changed since the release), so a
  run that never sent the changed call can't sign off its change; with no tag's transcript, standing is enough.
- **A call changed on purpose** reopens its action's evidence: regenerate the transcripts with
  `scripts/gen_transcripts.py` and commit them with the change. A reopened action needs only its own suites rerun,
  which `check_release.py --signoffs --reruns` lists. A suite that is no action's (`config_entry.json`) has no
  transcript and is outside the gate.
- **Prefer the rig.** Where the rig covers an integration, the sign-off is a rig run: it is repeatable and catches what
  a person doesn't. A manual row is the fallback for integrations the rig can't reach, or when the rig is broken; a
  manual sign-off on a rig-covered integration says why in its PR. This is guidance, not a gate check. Rig evidence is
  no separate level: the cards keep their ✔ for rig-tested models, and `--signoffs` prints each sign-off's kind (record
  or manual) for the RC audit.
- **RCs need no sign-off.** The gate runs only at `cut-release`. An RC's notes list each integration with a changed
  action that has no sign-off, with a link to the device report form, so an RC can carry an unsigned fix for others
  to test. But `cut-release` checks the latest RC's commit, so land the sign-offs or Untested fix caveats before the
  last RC.
- **No sign-off at the cut:** `cut-release` fails unless each changed action without one carries 🔧 Untested fix on
  its adapter; no other caveat, nor the `experimental` flag alone, stands in. A repo maintainer picks whichever is most
  likely to work for users (tenet 1): hold the fix back (revert it, or leave it out of the release branch) when the
  current code mostly works; ship it marked 🔧 Untested fix when the current code is broken and the fix is low-risk;
  or, when it is risky, put it behind `experimental` and mark it 🔧 Untested fix.
- **Coverage:** every module under `core/` and `integrations/`, bar `__init__.py`, needs at least 95% line coverage;
  CI checks it.

*Example:* v0.0.1 has no transcripts, so every action is changed and v0.1.0 needs a sign-off of each. After v0.1.0, a
fix to Hue's `stop` call needs a sign-off of Hue `stop` alone, and a `core/` refactor that leaves every transcript as it
was needs none.

### Sign-off format

Test records are JSON files in the bundle's `test-records/`, one schema for all of them:
[`docs/test-records.schema.json`](test-records.schema.json), the format's one home, which CI checks every file against
and which gives each field. A file there that isn't JSON is an error. The rules it serves:

- **A rig record**, `<suite>.json`, is named for its step file (`<action>.json`, or `<action>-<option>.json` for a run
  with an option set), and credits the action its name gives only when its `action` and `options` agree; a leading
  `_` is `_manual.json`'s and `_facts.json`'s alone. Format 3 cites the transcript its run tested (`calls`), which is
  what a sign-off is checked by. It passes only when no test failed and one passed; counts are derived from the tests,
  never stored.
- **A test names the devices it reached** and the class the call reached on each, as the action's result reports it
  ([action-behavior.md](action-behavior.md#what-a-response-looks-like)), or null where the integration named none;
  always null on an integration that names no classes. A Zigbee device is named by its Zigbee model ID on every
  integration, and with its manufacturer string, as one model ID carries many makers' strings; every model a file
  names must be in `docs/models.yaml` or its bundle's `devices.yaml`. A native group's test, and a scene's, lists the members and carries `group`.
- **Formats 1 and 2** sign nothing off, and a rerun replaces them with format 3. Format 2 is bound to the package tree
  (`package`) instead of the calls, and credits classes and the cards as format 3 does. Format 1 is a markdown record
  converted once (device-classes plan, step 5b): the run's devices sit on the record, not on each test, and it credits
  the cards as the markdown did.
- **`_manual.json`**: a maintainer's hand tests, a row each, added in a PR: each device a model id (never a household's
  device name) with the class it reached, and the actions that passed on all of them, each with its transcript's blob
  (`calls`). `scripts/signoff.py` prints the row from HEAD's transcripts, so run it at the commit you tested; the row's
  `commit` is a record of that, which nothing checks. A format 2 row (`passed`) credits classes and the cards, and signs
  nothing off. A row whose actions targeted a native group or a scene carries `group`, its devices the members. The
  model is the device's own (its label, the vendor's app or HA's device page), never a driver's or bridge's name, as
  on Control4's Director; the manufacturer is as the schema's `manufacturer` gives it.
- **`_facts.json`**: the fact cases' results, a row each, only ever added. A row converted from markdown says so and
  has no class.

*Example:* if `stop.json` fails, is format 2, or ran before a change to `stop`'s calls, `stop` has no rig sign-off until
its suite is rerun; the other actions' records stand through that change.

*Example:* a Shelly run in which a relay and a bulb each pass `turn_on_for` credits `S3SW-001X8EU` to `Switch` and
`S3BL-C010007AEU` to `RGBCCT`, each only under its own class; a maintainer's hand test of both is one `_manual.json`
row naming each with its class. A log-wording change needs neither, as it leaves the transcripts as they were.
