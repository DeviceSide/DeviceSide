# Shared Zigbee refusal reasons (narrow #532)

## Coordination

Intent: one home for the three `turn_on_for` refusal reasons ZHA and Zigbee2MQTT copy, so a reason fixed on one
can't differ on the other. Closes #532.
Touches: custom_components/deviceside/zigbee/, custom_components/deviceside/integrations/zha/refusals.py, custom_components/deviceside/integrations/zigbee2mqtt/refusals.py, tests/zigbee/, CLAUDE.md, scripts/gen_codeowners.py, scripts/owners.py, .github/CODEOWNERS

## Why

`integrations/zha/refusals.py` and `integrations/zigbee2mqtt/refusals.py` hold three `NotBuilt` entries with
identical reason text: `OTHER`, the `(HUE, IKEA)` switch-domain entry, and `IKEA_TIMER_HARMED`. User-visible failure
prevented: the same device explained two ways, depending on the integration it is paired with.

## Decisions (settled with Jason, 2026-11-24; don't redesign)

1. **Reason text only.** Each `refusals.py` still builds its own `NotBuilt` entries (class, `source`, `domains`), so
   refusal entries stay the integration's, outside every family. No shared entry, no shared rule.
2. **Homes.** `IKEA_TIMER_HARMED`'s reason goes in the catalog, `zigbee/ikea.py`, beside `TIMER_HARMED_MODELS`. The
   two that aren't family-keyed go in a new `zigbee/reasons.py`.
3. **Ownership of `zigbee/reasons.py`** (and its test): the maintainers of every integration with a family that reads
   the `zigbee/` catalog, today ZHA's and Zigbee2MQTT's. It is not a family's file: a family maintainer can't merge a
   change to it alone, as it words refusals for every family's devices. Check how `scripts/owners.py` (`package_of`),
   `scripts/gen_codeowners.py` and `scripts/check_maintainer_merge.py` treat a `zigbee/` path that is no family's
   key before choosing the file's name; the gate must not read it as a family named `reasons`.
4. **Not shared**: the Tuya, Sengled and Sonoff reasons, which name what each integration's call does; the IKEA
   family rule files and their tests (deferred: `docs/deferred.md`, by the register plan).
5. **Tests pin the text once**, as literals, in `tests/zigbee/`; each integration's `test_refusals.py` asserts its
   entry uses the shared constant and drops its own copy of the literal.

## Steps (one PR)

1. Move the three reasons (Decision 2); both `refusals.py` import them. The comments explaining each entry stay with
   the entries, once where they are identical in meaning.
2. Ownership (Decision 3): the generator and gate change, regenerated `.github/CODEOWNERS`, and tests for the gate
   reading the new path.
3. Rules: `CLAUDE.md`, "Where facts go", a row: "A refusal reason two Zigbee integrations share | `zigbee/<family>.py`
   for a family's, `zigbee/reasons.py` otherwise; each integration's `refusals.py` builds its own entry from it". And
   the Maintainers section: one sentence giving `zigbee/reasons.py`'s owners (Decision 3). Rule text in `CLAUDE.md`
   is binding-rule surface: Opus auditor.
4. Tests (Decision 5).

## Checks

`.venv/bin/pytest -n auto --transcripts=check` (no call or reply handling changes, so transcripts must not move),
`uvx pre-commit run --all-files`, `.venv/bin/python scripts/gen_codeowners.py --check`,
`.venv/bin/python scripts/gen_compat.py --check` (the reasons feed the cards: output must be byte-identical).

## Owners

Jason maintains both integrations today; if the owner-notice comment names anyone else, ask him before the next push.
