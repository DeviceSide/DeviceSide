# Labs until tested: hardware evidence releases an item, a sourced call admits it

Copy this plan to `docs/plans/2026-11-24-labs-until-tested.md` as the first commit (`pr-draft` on that path), on
branch `wt/labs-until-tested` off `main`.

## Coordination

Intent: an item is in Labs until real-hardware evidence exists for it (the author's test or users' reports), so a
tested item ships unflagged and an untested one ships in Labs on a sourced call. Rewrites the rule text, and makes
the release gate, the coverage check and the cards agree with it.
Touches: `docs/evidence.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `docs/design.md`, `docs/device-compatibility.md`
(hand-written part), `docs/deferred.md`, `.github/pull_request_template.md`, `scripts/check_release.py`,
`scripts/gen_compat.py`, `tests/scripts/`, `.claude/skills/release/SKILL.md`, `docs/plans/`, README and other
generated files (regenerated).
Depends-on: none.

## Context

Jason decided to ship features he can't test locally. The rules as of `7db96314` assume otherwise:

- "Every new feature starts flagged, and soaks" (evidence.md, The Labs flag; CONTRIBUTING step 4 and Development
  principles; tenet 8's "a new item starts flagged").
- A passing record "is not a requirement to lift" a flag.
- A class enters Labs only on a pass on it or its kin, or research predicting most accept
  (evidence.md, In Labs).
- "A vendor's document alone still needs the probe" (tenets 2 and 8; CONTRIBUTING step 5).
- The release gate: "nor the Labs flag alone, stands in" for a sign-off. At `7db96314`,
  `check_release.py --signoffs` fails on matter `set_attributes` and zigbee2mqtt `set_auto_off`,
  `clear_auto_off` and `turn_off_for`: Labs-only, no device to test on.
- `gen_compat` fails when Labs lines pass a quarter of card lines (`LABS_SHARE_MAX`).

## Decisions (Jason, 2026-11-24)

1. **Labs entry: a sourced call.** A class or feature enters Labs on a cited reason to expect the call works: the
   vendor's documentation, an upstream integration that ships it, or research. No pass needed. Research predicting
   most of the class fails still keeps it not built. Every action, the ones whose failure harms included: turning on
   Labs stays the user's consent. Unchanged: an identity reported harmed is split off as `NotBuilt`, `class_unknown`,
   and the default class's rules.
2. **Labs exit: at least one hardware pass, and the maintainer judges whether it is enough** (tenet 7). The pass is
   the author's own test or a user's working report, recorded as a rig record or a `_manual.json` row (`reports`
   for users'). A pass is now required to lift; it was optional.
3. **Tested items ship unflagged by default.** What the author's test exercised ships straight to release. A
   maintainer may still flag a complex item to soak, as an exception, giving the reason in the PR. "Every new
   feature starts flagged" goes; the soak is no longer the default path.
4. **Documented stays as it is.** It rests on a hardware pass of the same call on the same firmware family (tenet 5).
5. **Drop the Labs cap.** `LABS_SHARE_MAX` and `check_share` go; the fold stays.
6. **Extend the coverage check in this PR.** See step 4 for what records can and can't prove.
7. **An all-Labs action passes the release gate.** An action none of whose calls runs with the Labs option off
   (its adapter flagged whole, or every class its scope serves in Labs in every domain) needs no sign-off at the cut
   and no caveat. A mixed action still needs one: a rerun on the devices the maintainer has gives it, as a sign-off
   must hold the gained segments, not have exercised them.

Claude's calls, for Jason to overrule in review:

8. **Fields stay a maintainer rule, unchecked.** A record doesn't say which fields a test sent, and the rig is
   another repo, so no check can ask a field for its record. Decision 2 binds fields as text; a `docs/deferred.md`
   entry records the check, reopened when a lift of a field with no record is found, or the record schema gains the
   fields sent.
9. **Tenet 2 keeps its name, "Probe before you build", scoped to a device you can reach.** With no device at hand,
   build from the source to Labs and cite it; the first report is the probe.
10. **Deferred "Repair notice on a first Labs call" gains a reopen trigger:** a Labs item that entered with no pass
    has no device report one release after it shipped. Untested Labs now depends on reports arriving.

## Steps

One PR; the rule text and the checks land together. Step 1 is text on the binding-rule surface, so the PR audit
takes an Opus auditor (CLAUDE.md, Pull requests).

### Step 1: rule text

The one statement, in evidence.md's The Labs flag, which every other file points to:

> An item is in Labs until a real device has passed it. The pass is the author's own test or a user's working report,
> on record; a maintainer judges whether it is enough. So an item tested before it merges ships unflagged, and one
> nobody can test yet ships in Labs, untested, until someone with the device reports.

- **`docs/evidence.md`**
  - Intro: "before a feature ships" becomes before it ships to everyone.
  - Tenet 2: Decision 9.
  - Tenet 8: the design-choice bullet's "A vendor's document alone still needs the probe" holds only for a device
    the builder can reach. "a new item starts flagged" becomes: a new item is flagged until its pass is on record.
    The contributor sentence: their test lets it ship unflagged (was "later, to lift its flag"). "lifting a Labs
    flag" stays a decision a run takes.
  - Levels: Labs's line says tested or not. Verified's definition already allows reports through a maintainer's
    row; say so there, pointing to The Labs flag.
  - In Labs bullet and the Not built yet bullet: Decision 1. Drop "a pass on the class or its kin" as a condition of
    entry; keep that a kin's pass admits kin, as one source among the three. "A not built class returns with a
    contributor's PR and a passing run" becomes: with a sourced call, or a passing run.
  - Unknown is flagged, never Verified: leave; check its "labs(...) where research predicts" wording still agrees.
  - The Labs flag, second paragraph: rewrite per Decisions 2 and 3. Drop "soaks behind the flag with users who opt
    in" as the default and "it is not a requirement to lift it". Keep who approves a lift and the family rule.
  - The "by report" paragraph: no longer only "for an item no maintainer can test"; it is one of the two sources.
  - Drop the cap sentence; keep the no-credit-while-flagged rule and the fold.
  - Release gate, "No sign-off at the cut": Decision 7, replacing "nor the Labs flag alone". The repo maintainer's
    third option (risky: Labs plus Untested fix) becomes Labs alone when that makes the action all-Labs.
  - The coverage check: step 4's rule.
  - Examples: the Shelly dimming example still holds; reword "once they judge the tests complete". Add one example
    of an untested Labs item (zigbee2mqtt inching: sourced from upstream issues, no maintainer device, lifts by
    report).
- **`CLAUDE.md`** Evidence: tenets 2 and 8 in one line each, matching. Keep the count at nine.
- **`CONTRIBUTING.md`**
  - Development principles, "Tested on real devices": released features are tested on real devices; what nobody
    has tested yet ships in Labs until someone with the device reports. First person, per the contributor-copy
    memory. No em-dash as a comma.
  - Step 4 "Ship behind `labs`" becomes "Set the level": Verified for what your test in step 6 exercised, `labs(...)`
    for the rest, on a sourced call.
  - Step 5: with no device, cite the source and ship in Labs.
  - Step 6: "With the Labs option on" applies only to flagged items.
  - Maintaining an integration, "Removing the flag": Decision 2. Maintaining a family: same wording.
  - "A device or maker string" path: "credited on the card only by a `_manual.json` row on an item that isn't in
    Labs" still holds; check it reads right beside the new step 4.
- **`docs/design.md`** glossary: Labs ("not yet judged ready for everyone" becomes not yet passed on a real
  device, or held back by a maintainer); Device report (it can release a Labs item).
- **`docs/device-compatibility.md`** Levels of proof: ⚪ Labs "built but not yet proven" becomes built from the
  maker's documentation or others' reports, and not yet tested by us on a real device; the closing paragraph
  already asks for reports. `gen_compat.py`'s `OUTCOMES` legend string for Labs to match.
- **`.github/pull_request_template.md`**: the level line asks, per Labs item, for its source, and per Verified item,
  for its test.
- **`docs/deferred.md`**: Decisions 8 and 10.
- **`.claude/skills/release/SKILL.md`**: wherever it restates the no-sign-off rule or the cap.
- `rg -n -i "soak|starts flagged|start flagged|quarter|LABS_SHARE|Labs flag alone"` over the repo bar `docs/plans/`,
  `docs/audits/` and `research/` must end with no stale statement. Old plans are never edited.

Check: `pre-commit run --all-files`; `scripts/gen_compat.py --check`.

### Step 2: drop the cap

Remove `LABS_SHARE_MAX`, `check_share`, `Card.labs_lines` if nothing else reads it, their docstring paragraph and
their tests in `tests/scripts/test_gen_compat.py`. The fold (`Line.in_labs`, the folding function) stays.

Check: `.venv/bin/pytest -n auto --transcripts=check`; `scripts/gen_compat.py --check` with no diff to the cards.

### Step 3: an all-Labs action passes the gate

In `scripts/check_release.py`, a changed action is exempt from the sign-off when no call of it runs with the Labs
option off: `scope.all_labs`, or the integration names classes and every class the scope holds is `Level.LABS` in
every domain it serves. Put the predicate on `AdapterScope` if the dispatcher or `gen_compat` already computes the
same thing (`rg` first; `Line.in_labs` and `all_labs` are the candidates), else beside `coverage_gaps`. `--signoffs`
prints such an action as "in Labs: no sign-off needed"; `--json` and `--reruns` leave it out; `--notes` lists it in
the call for testers, as that is how its report arrives. Class-Labs fields (`class_labs`) don't make an action
all-Labs.

Tests pin: flagged-whole adapter exempt; every-class-Labs adapter exempt; one Verified or Documented class not
exempt; the notes still name it.

Check: at the branch head, `check_release.py --signoffs` no longer lists matter `set_attributes` or zigbee2mqtt
`set_auto_off`, `clear_auto_off`, `turn_off_for`; shelly `set_attributes` and `turn_on_for` remain (mixed, for the
release's rig run).

### Step 4: extend the coverage check

Today `coverage_gaps` asks each Verified class for a record, on integrations that name classes. Extend it to an
integration that names none: each domain its adapter holds as Verified needs a passing test in that domain in a
passing record of the action, or a `_manual.json` row naming the action. Same warning in `gen_compat`, same failure
at `cut-release`. Fields: Decision 8.

At `7db96314` every adapter of a class-less integration with a Verified domain has a record, so this should add no
gap. If the implementer finds one, list it for Jason: don't demote a level or add a grandfather list.

Check: `.venv/bin/pytest -n auto --transcripts=check`; `scripts/gen_compat.py` prints no new warning.

## Verification

- `.venv/bin/pytest -n auto --transcripts=check`, `pre-commit run --all-files`, the generators' `--check`.
- No hardware run: no call changes, so no transcript changes (tenet 9).
- Owner notices: steps 1 to 4 touch no integration's package. If a bundle page restates the soak or the cap and is
  edited, the owner-notice rule for Jason's PRs applies.

## Out of scope

- Lifting or setting any item's level. The rule changes; each level changes in its own PR, on its own evidence.
- A check that a field's lift has a record (Decision 8).
- The first-call repair notice (Decision 10 only adds its trigger).
