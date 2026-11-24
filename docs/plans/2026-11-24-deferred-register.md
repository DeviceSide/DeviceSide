# Deferred register: one home for work decided against for now

## Coordination

Intent: give deferred work one home, `docs/deferred.md`, where every entry names what reopens it; retire `TODO.md`
and the "After v0.1.0" issues, so open issues are only committed work.
Touches: docs/deferred.md, TODO.md, CLAUDE.md, docs/evidence.md, docs/integrations/zigbee2mqtt/internals.md, .claude/skills/release/SKILL.md, tests/core/

## Why

Deferred work sits in four places: "After v0.1.0" issues (#433, #434, #515), `TODO.md`'s "After v0.1.0" section,
unbuilt plans in `docs/plans/`, and `NotBuilt` entries in code. The last is derived and can't go stale; it stays as
it is. The rest move to one register. An issue is committed work with a clear done, and the list burns to zero.

## Decisions (settled with Jason, 2026-11-24; don't redesign)

1. **The register is one file, `docs/deferred.md`**, not a file per entry. Its own entry says when to split it: past
   30 entries, or when merge conflicts in it become routine.
2. **Entry shape**, one `##` per entry: what it is (two or three lines), **Why not now**, **Revisit when** (observable
   conditions, any one suffices), **Plan** (link, when one exists). An entry with no observable condition isn't
   added. The word is "deferred", never "backlog", and never "not built yet" (the glossary's term for a class).
3. **Device gaps stay in code** (`NotBuilt`, `NoKnownMethod`): never restated in the register.
4. **Issues are committed work.** A proposal nobody has committed to is a register entry, by PR. A user's device or
   feature request stays an issue (its forms are unchanged).
5. **Reviewed at each RC**: the release skill lists entries whose condition has been met, and deletes those nobody
   defends.
6. **One tripwire test**, for the one condition that is mechanical: the set of integrations whose families read a
   `zigbee/` catalog module is pinned as a literal (`zha`, `zigbee2mqtt`). Its failure message names the register
   entry and says to update the set with a repo maintainer. The "second true-copy family" condition is a judgment,
   so it has no test.
7. **Design stays out of `docs/design.md`**: scope comes from the design, so deferred work written there would read
   as in scope.
8. **`TODO.md`'s open items**: #515 and the two below go to the register; the Shelly color item becomes an issue;
   the forum items are done and dropped; the family-seam audit's Mediums and Low are dropped from tracking (they stay
   in #447's audit record).

## Entries

| Entry | Why not now | Revisit when | Plan |
|---|---|---|---|
| Device facts across integrations (was #433) | Two integrations share Zigbee calls, with one copied ban; signatures can't be frame-pinned on Zigbee2MQTT, where the converter builds the frame | a third integration reads a `zigbee/` catalog module (the tripwire); three PRs have argued Documented by hand (`docs/evidence.md`, tenet 5) on a call another integration holds evidence for; a ban or reason is fixed on one Zigbee integration and missed on the other | `docs/plans/2026-11-14-device-facts-across-integrations.md` |
| Attended units probe (was #434) | Depends on the Tuya datapoint countdown (#437) and its cancel path | #437 has landed and a device report leaves a timed device's units unsettled (**proposed by Claude; Jason confirms in PR review**) | `docs/plans/2026-11-14-units-probe.md` |
| Repair notice on a first Labs call (was #515) | No evidence yet that the report rate limits lifting Labs flags; the Labs option already asks for reports | at the second release after v0.1.0, a Labs class still has no device report | `docs/plans/2026-11-18-experimental-listing.md`, Decision 6 |
| Per-family test records and docs | No family maintainer signs off their own classes yet | a family maintainer signs off their own classes | none; `TODO.md`'s text carries the shape |
| Rig kit for maintained adapters | Maintainers sign off by hand (`docs/evidence.md`) | a maintainer needs to commit records for hardware the rig lacks | none |
| Shared IKEA family rules and tests across Zigbee integrations (from #532) | One family is a near-copy; sharing rules lets one integration's family maintainer change the other's classification | a second family's rule file is a near-copy on both integrations | none |
| Split this register into a file per entry | Six entries | past 30 entries, or routine merge conflicts | none |

Carry each entry's detail over from its issue body or `TODO.md` text; the table above is the brief, not the copy.

## Steps (one PR)

1. **Register**: write `docs/deferred.md` from Decisions 2 and the entries. Public file: no household names, no
   personal tooling.
2. **Rules**:
   - `CLAUDE.md` line 3: replace "Progress to v0.1.0: `TODO.md`; tick items off in the PR that finishes them." with a
     pointer: deferred work and what reopens it is in `docs/deferred.md`; an issue is committed work.
   - `CLAUDE.md`: delete the "Until v0.1.0 ships, fix the architecture now" paragraph (its own text says so).
   - `CLAUDE.md`, "Where facts go": a row, "Work decided against for now, and what reopens it | `docs/deferred.md`".
   - `docs/evidence.md`: one line beside tenet 5's hand-argument rule pointing to the register's device-facts entry.
     Binding-rule surface: add the pointer only, change no rule's meaning.
   - `.claude/skills/release/SKILL.md`: the RC step of Decision 5.
3. **Retire `TODO.md`**: delete it; fix `docs/integrations/zigbee2mqtt/internals.md`'s link to it (point at the
   register entry or the issue the linked item became).
4. **Tripwire**: the test of Decision 6, beside the registry's tests.
5. **GitHub, in the turn that merges** (read every comment on each first):
   - close #433, #434 and #515, each with a comment linking its register entry;
   - file "Shelly RGB and RGBW color" from `TODO.md`'s text, with the fix-shape and model comment;
   - trim #416's body to what still holds: the anchors named after integrations, and `services.yaml` forcing a repo
     maintainer onto an integration maintainer's adapter PR. Its "lists drift silently" point is closed by
     `test_target_filter_lists_exactly_the_integrations_and_domains_served`.

## Checks

`.venv/bin/pytest -n auto --transcripts=check`, `uvx pre-commit run --all-files`,
`.venv/bin/python scripts/gen_features.py --check`, `.venv/bin/python scripts/gen_compat.py --check`,
`tests/scripts/test_doc_anchors.py` for the moved links.

## Out of scope

#437 (another session is building it). #416's implementation. The shared Zigbee reasons
(`docs/plans/2026-11-24-shared-zigbee-reasons.md`); both plans add a "Where facts go" row, resolved by merge.
