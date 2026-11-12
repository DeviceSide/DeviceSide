# Evidence

What DeviceSide must know about a device before a feature ships, and what a release needs. This page is the one home
for these rules; other docs point here. Settled in [the evidence-rules plan](plans/2026-11-12-evidence-rules.md).

## Transition

These rules apply from 2026-11-12, but the code that enforces the old ones is removed in steps 2–5 of the plan. Until
each step lands, its old gate keeps running, and work satisfies it. The old rules are in CLAUDE.md at `075895f`
(§ Release flag) and in `scripts/check_release.py`'s docstring.

- **Runtime (step 2):** `Level.REPORTED` and `Level.EXPERIMENTAL`, the `experimental=True` release flag, the
  `unmaintained`, `stale_tests` and `siblings` fields, and the wire and scope traces.
- **Release gate (step 4):** `check_release.py --release` (the release flag, Stale tests) and `--records` (record
  freshness, `FLAGS`, shared coverage, `Covers`, report retests), and the coverage bar over `adapter_code`.
- **Cards (step 5):** `gen_compat.py`'s Reported tier, siblings, Unmaintained and Stale tests marks, and its
  record-freshness rule for Verified.

No RC is cut until step 5 lands.

## Tenets

1. **User experience is the north star.** Actions make devices do what users expect, quickly. If that holds, nothing
   else matters.
2. **Probe before you build.** When unsure how a device responds to a call, run a cheap probe rather than assume.
   Record what it shows as a fact (the bundle's `internals.md`, dated).
3. **Verify, then trust.** A verified fact stands across firmware, HA and code changes until evidence contradicts it.
   Nobody goes looking for things to re-prove.
4. **Surprises reopen facts.** A bug or unexplained behavior triggers a root-cause dive. The finding joins the fact
   base and is then trusted in turn. Log so that the first bug report already holds the diagnosis: what DeviceSide
   sent, what the device answered, and which way DeviceSide went because of it.
5. **Proof follows the call.** Evidence is about how a device responds to a call. Any code that sends the same call
   inherits it, and unit tests pin the call.
6. **Simplify relentlessly.** Prefer fewer calls, fewer round trips and less machinery. A guardrail stays until
   evidence shows the failure it guards against doesn't happen; meanwhile, look for ways to make it cheaper. A new
   rule or guardrail names the user-visible failure it prevents and what it replaces.
7. **Maintainers judge sufficiency.** Tooling records evidence, and maintainers decide what's enough. Gates check that a
   sign-off exists, not how thorough it was.

*Example (tenets 4 and 5):* the rig found that a Tuya TS011F plug stores the Zigbee timed-on timer as a countdown and
never switches on ([integrations](integrations.md#zigbee-plugs-and-switches)). That reopened "a Zigbee switch takes the
light's timed-on call", so the `switch` domain stays untested on ZHA and Zigbee2MQTT `turn_on_for` while the `light`
domain keeps its proof.

## Levels

A scope item (an entity domain, capability or field of an adapter) is Verified, Documented, or untested; an untested
item ships only behind `experimental`.

- **Verified:** a maintainer has verified the call on a real device, by rig record or by manual test. How it was
  tested is the maintainer's choice; the rig is a tool, not a requirement.
- **Documented:** a call that reaches the same capability as a Verified item, differing only in addressing, where no
  known class of devices departs. Unit tests pin the payload. A field is never Documented, because it changes the
  call. The PR that claims Documented argues the sibling case, and review checks it. A bug on the Verified sibling
  reopens its Documented siblings in the same fix.

Nothing ships unflagged unless it is Verified or Documented. Built and unit-tested code that the maintainer can't
exercise, and that isn't Documented, ships behind `experimental` as untested ("Help us test" on the cards). A sign-off
covers only what was exercised; it never signs off untested code.

**Contrary evidence:** a report of misbehavior doesn't change the level. The maintainer root-causes it, and the fix,
the updated fact or a demotion lands with the finding.

*Example:* Shelly's `turn_on_for` and `turn_off_for` calls are Verified on the `Switch` and `RGBCCT` components and Documented on `Light`, `CCT`,
`RGB` and `RGBW`: the same call, addressed to another component, which Shelly's API documents identically
(`integrations/shelly/addressing.py`).

## The experimental flag

`experimental` is a flag, not a level. In code it is the per-axis marker `experimental(...)`, beside `verified(...)` and
`documented(...)`; `experimental=True` on an `AdapterScope` flags the whole adapter. A flagged item is refused unless
the user turns on the Experimental features option. It may be tested and soaking, or untested: the cards tell which
from the evidence (a record or `_manual.md` line, or none).

Every new feature (action, integration, domain, capability or field) starts flagged, so it soaks in RCs and with
opted-in users. A repo maintainer removes the flag. The directional bar is five working reports from users other than
the maintainer and no open bugs; nothing counts the reports in code.

*Example:* Shelly dimming on `Light` is `experimental("Light")`: a user's report of a Gen3 Dimmer jumping on
`DimStop` keeps it from Documented. Once a maintainer verifies it on a dimmer, it soaks flagged; once a repo
maintainer judges it has soaked, their PR makes it `verified("Light")`.

## Caveats

`AdapterScope.caveat` holds a reason (an issue URL), set and cleared by a repo maintainer. It is not a level: levels
are about evidence, caveats about risk and people. Each gives one setup warning, one card mark and one release-notes
line:

- **⚠️ Untested fix:** changed, and nobody could test it before the release. It ships live, with a call for testers
  in the release notes. A sign-off clears it, including a maintainer's `_manual.md` line citing a user's working
  report.
- **⚠️ Unmaintained:** nobody is fixing it. It ships live. Cleared when someone fixes the adapter or adopts the
  integration.

A deprecation gets a hand-written note in that release's notes, not a caveat.

*Example:* a low-risk fix to a broken adapter whose devices no maintainer has lands before the cut. It ships with ⚠️ Untested fix and
the issue URL; a user's working report, cited in a maintainer's `_manual.md` line, clears it.

## Release gate

Each integration whose package (`custom_components/deviceside/integrations/<x>/`) changed since the last release tag
needs a sign-off at or after its last change. Any change counts, flags included.

- **A sign-off** is a passing test record, or a `_manual.md` line, whose commit has the package's last change as an
  ancestor. It may say "no call changed". It comes from one of the integration's maintainers, or a repo maintainer
  when none responds.
- **Prefer the rig.** Where the rig covers an integration, the sign-off is a rig run: it is repeatable and catches what
  a person doesn't. A manual line is the fallback for integrations the rig can't reach, or when the rig is broken; a
  manual sign-off on a rig-covered integration says why in its PR. This is guidance, not a gate check. Rig evidence is
  no separate level: the cards keep their ✔ for rig-tested models, and `--signoffs` prints each sign-off's kind (record
  or manual) for the RC audit.
- `core/`, `actions/` and `scripts/` changes need no device sign-off: unit tests, the RC soak and tenet 5 cover them.
- **RCs need no sign-off.** The gate runs only at `cut-release`. An RC's notes list each integration changed without a
  sign-off, with a link to the device report form, so an RC can carry an unsigned fix for others to test.
- **No sign-off at the cut:** `cut-release` fails unless a changed adapter of that integration carries a caveat. A
  repo maintainer picks whichever is most likely to work for users (tenet 1): hold the fix back (revert it, or leave
  it out of the release branch) when the current code mostly works; ship it marked ⚠️ Untested fix when the current
  code is broken and the fix is low-risk; or put it behind `experimental` when it is risky. Review checks that the
  right adapters carry the caveat.
- Records keep a `Covers` row as information if the rig writes one. Nothing checks it.
- **Coverage:** every module under `core/` and `integrations/`, bar `__init__.py`, needs at least 95% line coverage;
  CI checks it.

*Example:* all five integrations changed since v0.0.1, so v0.1.0 needs five sign-offs. A passing Hue rig record
whose commit follows Hue's last change signs off Hue; an integration with no change would need none.

### Sign-off format

A rig sign-off is the test record the rig writes, `docs/integrations/<x>/test-records/<action>*.md`, with its commit
and Result. A manual sign-off is a row of the bundle's `test-records/_manual.md`, added in a PR: date, commit, tester,
model ids (`docs/models.yaml`, never a household's device names) and what passed.

    | Date | Commit | Tester | Devices | Passed |
    |---|---|---|---|---|
    | 2026-11-12 | `1a2b3c4` | @handle | `S3SW-001X8EU`, `S3BL-C010007AEU` | `turn_on_for`, `set_auto_off` |

*Example:* a log-wording change in a Shelly adapter signs off with `no call changed` in Passed.
