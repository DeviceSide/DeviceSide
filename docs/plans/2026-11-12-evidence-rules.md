# Evidence rules: verify, then trust

## Coordination

Intent: Replace the evidence machinery (four levels, the release flag, retests per adapter per change, Stale tests,
siblings, shared-code proof, `Covers` gating, the wire and scope traces) with a short set of tenets and two levels,
Verified and Documented, plus a runtime `experimental` flag. Releases gate on one maintainer sign-off per changed
integration. The new rules take effect before v0.1.0, which replaces the 36 stale-record reruns and the watched lab
session with about five sign-offs.
Touches: CLAUDE.md, docs/evidence.md (new), docs/design.md, CONTRIBUTING.md, docs/device-compatibility.md,
.github/ISSUE_TEMPLATE/device_report.yml, .github/pull_request_template.md, TODO.md, README.md (regenerated),
custom_components/deviceside/{__init__.py, core/scope.py, core/dispatcher.py, core/wire.py, core/zcl_write.py},
the transports and scopes under integrations/, scripts/check_release.py, scripts/gen_compat.py,
.github/workflows/{tests,cut-release-candidate,cut-release}.yml, and their tests.
Tests-with: the ha-rig PR in step 3 pairs with the runtime PR (step 2), because step 2 removes the events the rig
subscribes to.
Depends-on: none. This plan lifts the v0.1.0 freeze at `075895f`. No RC is cut until step 5 lands.

## Principle: the rig is a dumb executor (Jason, 2026-11-12)

DeviceSide decides the facts and logic of what needs testing: which integrations need a sign-off, the step files that
say what to send and expect. The rig executes the test plan it is given and writes records. It holds no rule of its
own about what is proven, covered or stale.

## Why

The `## Release flag` section of CLAUDE.md is 858 words, over half the file. It changed in 10 commits in a week, and
each rule brought code to enforce it. The rules ask for more precision than a few lab devices can give. Examples are
clause-level coverage of `core/` diffs, observed-pass lending by call-sequence prefix, and per-firmware re-proving.
They also re-prove facts that nothing has contradicted. Measured (code lines, without comments or docstrings):
DeviceSide's runtime is about 6k lines, out of about 39k across both repos. The rest is mostly tests and machinery for
deciding when to test.

## The rules (settled with Jason, 2026-11-12)

### Tenets

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

### Levels and the experimental flag

- **Verified:** a maintainer has verified the call on a real device, by rig record or by manual test. How it was
  tested is the maintainer's choice; the rig is a tool, not a requirement.
- **Documented:** a call that reaches the same capability as a Verified item, differing only in addressing, where no
  known class of devices departs. Unit tests pin the payload. A field is never Documented, because it changes the
  call. The PR that claims Documented argues the sibling case, and review checks it. A bug on the Verified sibling
  reopens its Documented siblings in the same fix.
- Nothing ships unflagged unless it is Verified or Documented. Built and unit-tested code that the maintainer can't
  exercise, and that isn't Documented, ships behind `experimental` as untested ("Help us test" on the cards). A
  sign-off covers only what was exercised; it never signs off untested code.
- **`experimental`** is a flag, not a level. In code it keeps today's per-axis marker, `experimental(...)`, beside
  `verified(...)` and `documented(...)`; `experimental=True` on the scope flags the whole adapter. A flagged item may be
  tested and soaking, or untested: the cards tell which from the evidence (a record or `_manual.md` line, or none).
  Removing the flag is one line, `experimental("switch")` to `documented("switch")`. A flagged item is refused unless the user turns on the Experimental
  features option. Every new feature (action, integration, domain, capability or field) starts flagged, so it soaks in
  RCs and with opted-in users. A repo maintainer removes the flag. The directional bar is five working reports from
  users other than the maintainer and no open bugs. Nothing counts the reports in code.
- **Contrary evidence:** a report of misbehavior doesn't change the level. The maintainer root-causes it, and the fix,
  the updated fact or a demotion lands with the finding.
- **Caveats** (decided 2026-11-12): one field, `AdapterScope.caveat`, with a reason (an issue URL), set and cleared by
  a repo maintainer. It is not a level: levels are about evidence, caveats about risk and people. One setup warning,
  one card mark and one release-notes line, worded per caveat:
  - ⚠️ **Untested fix:** changed, and nobody could test it before the release. It ships live, with a call for testers in
    the release notes. A sign-off clears it, including a maintainer's `_manual.md` line citing a user's working report.
  - ⚠️ **Unmaintained:** nobody is fixing it. It ships live. Cleared when someone fixes the adapter or adopts the
    integration.
  - No Deprecated caveat: a deprecation gets a hand-written note in that release's notes.
- Removed: Reported, the release flag (as a release gate), Stale tests, `siblings`, observed-pass lending, the
  firmware-fact ledger, shared-code proof, `Covers` gating, and the separate `unmaintained` and `stale_tests` fields
  (folded into `caveat`).

### Release gate (option B)

- Each integration whose package (`custom_components/deviceside/integrations/<x>/`) changed since the last release tag
  needs a sign-off at or after its last change. A sign-off is a passing test record or a `_manual.md` line whose commit
  has the package's last change as an ancestor. Any change counts, flags included; a sign-off may say "no call
  changed".
- Who signs off: any of the integration's maintainers, or a repo maintainer when none responds.
- **Prefer the rig.** Where the rig covers an integration, the sign-off is a rig run: it is repeatable and catches
  what a person doesn't. A manual line is the fallback for integrations the rig can't reach, or when the rig is
  broken. A manual sign-off on a rig-covered integration says why in its PR. This is guidance for maintainers, not a
  gate check. No separate level for rig evidence: the cards keep their ✔ for rig-tested models, and
  `--signoffs` prints each sign-off's kind (record or manual), so the RC audit sees any manual one.
- `core/`, `actions/` and `scripts/` changes need no device sign-off: unit tests, the RC soak and tenet 5 cover them.
- **RCs need no sign-off.** The gate runs only at `cut-release`. An RC's notes list each integration changed without a
  sign-off, with a link to the device report form, so an RC can carry an unsigned fix for others to test.
- If an integration has no sign-off at `cut-release`, the cut fails unless a changed adapter of it carries a caveat.
  A repo maintainer picks whichever is most likely to work for users (tenet 1): hold the fix back (revert it, or leave
  it out of the release branch) when the current code mostly works; ship it marked ⚠️ Untested fix when the current
  code is broken and the fix is low-risk; or put it behind `experimental` when it is risky. Review checks that the
  right adapters carry the caveat.
- Records keep a `Covers` row as information if the rig writes one. Nothing checks it.

### Logging guidance (CONTRIBUTING, Fast track step 4)

> **Log for the first bug report.** A user's debug log is often all you'll get.
> - **DEBUG:** each call you send, and each branch you take on a device's reply (a retry, a fallback, a read-back that
>   failed, a skipped step), with the values that decided it.
> - **INFO:** a lasting change you make to another system's settings, such as a Zigbee2MQTT option.
> - **WARNING:** the device didn't get the command, or HA may now show the wrong state. Name the action, integration
>   and entity, and the cause (timeout or error). End with the consequence: "…, so HA may show the old values".
> - **Never:** device addressing (IEEE, MAC, bridge resource IDs) or tokens. Users paste logs into public issues.

This is drawn from the current 76 log calls (41 warning, 25 debug, 3 info, 6 exception). The per-call DEBUG line
replaces the wire trace and lives in the shared transport helpers, so adapters get it for free.

### State changes at the switchover (decided 2026-11-12)

- **The seven release-flagged adapters** (`stop` and `set_attributes` on Hue, ZHA and Zigbee2MQTT, plus Zigbee2MQTT
  `lower_hue`) ship to everyone: the flag is dropped, and they don't move behind `experimental`. They all have rig
  records. Their v0.1.0 sign-offs are rig runs (see Prefer the rig). The watched lab session in TODO.md shrinks to
  whatever those sign-off runs need, and no longer exists to clear flags.
- **Untested `Level.EXPERIMENTAL` items** (the `switch` domain on ZHA and Zigbee2MQTT `turn_on_for` and
  `get_attributes`; Shelly dimming on `Light`, `CCT`, `RGB` and `RGBW`) become Documented behind `experimental` where
  they meet the Documented test, with the argument made in the PR. Any that don't meet it ship in v0.1.0 behind
  `experimental` as untested (Jason, 2026-11-12), not removed from the scope.
- **v0.1.0** ships under the new rules: about five sign-offs, one per integration changed since v0.0.1.

## Steps

Each step is one PR off `main`, in order. Measure line counts before and after, and put the deletions in each PR body.
The estimates below are code plus tests.

1. **Rules (docs only).**
   - New `docs/evidence.md`: the tenets, levels, flag, release gate and sign-off format, each with an example. It is
     the one home for these rules.
   - CLAUDE.md: replace `## Release flag` with `## Evidence` (about 10 lines: the tenets in one line each, then a
     pointer). Rewrite `## Releasing` for option B and drop the Stale tests paragraph from `## Maintainers`. Update the
     binding-rule surface in `## Pull requests` to name `docs/evidence.md`.
   - CONTRIBUTING: step 4 gains the logging bullet. Step 5 and "Graduation" become flag removal by a repo maintainer
     (directional bar). "Retests" becomes the sign-off. Link to `docs/evidence.md` instead of restating it.
   - `docs/design.md`: glossary (Level, Retest becomes Sign-off, drop Stale tests and Release flag, Experimental
     features) and Release gates.
   - `docs/device-compatibility.md`: "Levels of proof" covers two levels and the flag; "Help us test" becomes "Try
     it: Experimental features".
   - Device report form: one line on enabling debug logging (the integration page's "Enable debug logging", reproduce,
     disable, attach the log).
   - PR template: "Level of each new or changed item" becomes Verified/Documented plus flagged or not. Drop "Records
     staled".
   - TODO.md: lift the freeze; replace "Stale records rerun", "Watched lab session", "9d" and item 12 with this plan's
     steps and the sign-offs.
   - Add a **Transition** note at the top of `docs/evidence.md` listing the old gates still running until steps 2–5
     land. No RC is cut during the transition.
   - Run pre-commit and the Opus audit (binding-rule surface).
2. **Runtime (DeviceSide), about −300.**
   - `core/scope.py`: `Level` keeps `VERIFIED`, `DOCUMENTED` and `EXPERIMENTAL` (the per-item flag); drop
     `REPORTED`. `experimental` becomes a runtime gate: the `experimental(...)` marker and `experimental=True` both
     gate at runtime. Drop `stale_tests`, `siblings` and `_check_siblings`. Add `caveat` (Untested fix, Unmaintained) in place of `unmaintained`.
   - `core/dispatcher.py`: refuse a flagged item unless the option is on; drop the scope trace.
   - `core/wire.py`: becomes a `_LOGGER.debug` per call in the same helpers; drop both HA events.
   - `__init__.py`: one setup warning per caveat, replacing the unmaintained and stale-tests warnings.
   - Migrate the scopes: the seven adapters lose the flag. Untested items become Documented where they qualify, else
     stay `experimental(...)` (untested, flagged).
   - Update tests and regenerate the cards and feature table.
   - Pair with step 3 via `Tests-with`.
3. **Rig (ha-rig), about −1,000.** Plan it in ha-rig `docs/plans/`.
   - Drop the wire and scope taps in `client.py` and `engine.py`, `Covers` rendering, Shared-coverage capture,
     `observed.py` lending and blocking, and the firmware-fact ledger in `progress.py` and `coverage.py`.
   - Z2M BUSY call windows come from the rig's own step timestamps.
   - The rig decides nothing about what needs testing (principle below): delete `coverage.py`'s fingerprints,
     freshness check and observed hints, and `--coverage`. The rig runs the suites it is asked for.
   - Observed and firmware-fact cases are opt-in: a passed one stands as a fact, a default run leaves them out, and a
     maintainer adds them with an option. No hashing, lending or ledger.
   - The progress ledger stays only to resume an interrupted run, keyed by commit plus suite.
   - Leave roaming, concurrency and the repo merge for separate decisions.
3b. **Step files move to DeviceSide** (decided 2026-11-12). The rig's `steps/<action>.yaml` move to DeviceSide
   `tests/rig/steps/`, landed with the action they test, so a new action needs no paired rig PR. The rig reads them
   from the target checkout. CLAUDE.md's "don't add rig code, step files or rig docs here" becomes "no rig code or rig
   docs here; step files live in `tests/rig/steps/`". Step files name roles, never entities; the household check
   covers them. The rig engine stays private.
   - **Done.** A record cites the commit, so a rig run with uncommitted step files goes ahead but writes no record or
     fact row and keeps no ledger; the ledger key is the commit and the suite, without the step-file digest.
     `tests/test_rig_steps.py` checks each file loads, calls a registered action and names registered integrations;
     the rig's CI parses them in full. The rig's own tests use fixture copies, not these.
4. **Release gate (`check_release.py`), about −1,100.**
   - Keep `--coverage`, with the bar on every module under `core/` and `integrations/` except `__init__.py`. That drops
     the `adapter_code` import graph; first check that no module falls below the bar, and if one does, raise it in this
     PR.
   - Add `--signoffs` (option B: package diff since the last tag, `git merge-base --is-ancestor`, tester in maintainers
     or `REPO_MAINTAINERS`). A changed integration passes with a sign-off or a caveat on one of its changed adapters.
     The output names each sign-off's kind and each caveat. A machine-readable form (`--signoffs --json`) lists
     the integrations that still need one; the rig takes that list as its run selection (a rig change after this
     step).
   - `--notes` writes the call for testers: integrations changed without a sign-off (RCs) and Untested fix caveats.
   - Drop `--release` and the rest of `--records`: freshness, `FLAGS`, shared coverage, `Covers`, report
     retests and Stale tests.
   - Update the three workflows and the docstring, which describes the checks and points to `docs/evidence.md` for the
     rules.
5. **Cards (`gen_compat.py`), about −400.**
   - Tiers: Works (Verified models and native groups), Should work (Documented classes), Experimental features
     (flagged items), Doesn't work.
   - Flagged items show as tested (soaking) or Help us test, from the evidence. Caveat marks replace the Unmaintained
     and Stale tests marks.
   - Drop Reported, siblings and the record-freshness rule for Verified.
   - Regenerate the README and `docs/device-compatibility.md`.
6. **v0.1.0.**
   - One sign-off per integration changed since v0.0.1 (`check_release.py --signoffs`), by rig run for every
     integration the rig covers (Hue, ZHA, Zigbee2MQTT, Shelly and Matter on today's profiles), and manual only as a
     fallback.
   - `/rc-audit` over the new range, then the RC, a HACS install, the release notes and `cut-release`.
7. **Test simplification plan**, the last step. In a new session, once steps 4 and 5 have landed:
   - **A fresh audit** of both repos' tests for what can be simplified, measured on the code that remains. The first
     audit (ha-rig `docs/plans/2026-11-12-test-consolidation.md`, branch `claude/test-consolidation-plan`) predates
     the rule changes and is stale: don't start from it.
   - **A proposed consolidation plan for Jason to review.** The session interviews Jason where it needs his call,
     before finalizing the plan, and changes no code until he approves it.
   - Constraints: the ≥95% coverage bar, no test dropped without naming what still catches its failure, and items
     ranked by lines saved per hour, each with its files, risk and how to verify (pytest plus a coverage diff).
   - The plan lands in DeviceSide `docs/plans/`, covering both repos. Test-only changes send no new call, so they
     need no sign-off, and the work needn't wait for step 6.

Total estimate: about 2,800 lines, before the test simplification (step 7) and the rig's roaming and
concurrency decisions.

## Verification

- Each step: `.venv/bin/pytest`, `pre-commit run --all-files`, coverage at least 95% on every module the bar covers,
  and the generated files clean.
- After step 2, a HA-log check on one Hue and one Z2M call: the DEBUG line shows the call, with no addressing.
- After step 4, run `check_release.py --signoffs` on `main`. It must list exactly the integrations changed since
  v0.0.1.

## Open decisions

None. Decided 2026-11-12: today's per-axis `experimental(...)` marker stays (not `bool | frozenset[str]`), and one
`caveat` field without Deprecated. Fixed unless review objects:
- The coverage bar over all of `core/` and `integrations/` instead of `adapter_code`.

## Handoff

Plan written on `claude/reduce-code-complexity-syqjth`. Next: step 1 in its own branch off `main`.
