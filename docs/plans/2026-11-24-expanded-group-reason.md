# Named expanded group raises its members' reason (#596)

## Context

On an adapter without `native_groups` (Z2M's `set_auto_off`, `clear_auto_off`, `turn_off_for`), core expands a
group into its members (`Dispatcher._expand_native_groups` → `_members_planned`, each `named=False`) and never records
the group. A named group none of whose members runs therefore gets no result of its own. A call that asked for a response
raises a plain `no_entities_matched`; one that didn't returns quietly. The real reason (`labs_off`, `not_built`, …) is
only in the "skipped targets" warning. `docs/action-behavior.md` (Commands and settings) says the group is refused, raised
if named, with its members' reason. The native-group fallback already does this (`fallen` + `_unanswered` + `_rank`);
expanded groups should take the same path.

## Coordination

Intent: A group core expands for an adapter that can't address it is refused, raised if named, with its members'
best-ranked reason when none of them runs, as a native group that fell back is.
Touches: custom_components/deviceside/core/dispatcher.py, tests/core/test_dispatcher.py, docs/action-behavior.md

## Decisions

1. **Reason**: the best-ranked skip among the group's members (`_rank`: labs_off, then a class's refusal, then any other,
   not_addressable last), matched the way the own_call branch of `_unanswered` matches skips today (member id, `_device_of`
   form, a stand-in's device targets).
2. **No member skipped** (each unavailable): no result for the group, as today. A response call still raises
   `no_entities_matched` (pinned by `tests/integrations/zigbee2mqtt/test_get_attributes.py:447`).
3. **Unnamed group** (area, label): gets its own skip entry with that reason, as a fallen native group does. It is
   logged, never raised.
4. A member that ran, was left nothing to do, or is a target of its own that ran answers for the group (the existing
   `answered` / `by_device` check). No adapter change, no transcript change.

## Change (one step: `core/dispatcher.py`)

- `_expand_native_groups` also returns the groups it expanded, each with its member list:
  `list[tuple[Target, list[Target]]]`. The per-bucket loop (around line 384) passes them on to `_plan`.
- `_plan` takes them and seeds `fallen` with one entry per expanded group, reason `None` (meaning "members' reason").
- `_unanswered`: generalize the own_call branch so it runs for `reason == Reason.OWN_CALL` **or** `reason is None`. The
  default when no member skip matched is `own_call` for the first and **no result** for `None` (`continue`). Widen the
  `fallen` type to `str | None` and update the docstrings (`_unanswered`, `_rank` "which member's skip a group refused
  for own_call, or expanded by core, takes", `_members_planned` "only _unanswered refuses a group").
- Module docstring, Native groups: the "For an adapter without native_groups…" bullet and Refusal priority each get a clause
  saying such a group is refused like a fallen one, with its members' ranked reason, and with nothing when each member was
  unavailable.

## Tests (`tests/core/test_dispatcher.py`, beside `test_native_group_expands_when_adapter_cannot_address_it…` ~line 1401)

Use the fake adapter with `native_groups` off (as the existing expand tests do) and `native_group(...)`:
1. A named group of two members the scope refuses (for example not_built) raises `TargetNotSupported` with that reason; no calls.
2. The same with Labs off and the members' class in Labs raises `labs_off`.
3. One member runs, the other is refused: the runner is in the response, the refused one is logged, nothing raises (unchanged behavior; pin it).
4. The same group as test 1, reached by area (`in_area`): not raised, and the warning lists the group with the reason.
5. A named group whose members are all unavailable: `return_response=True` still raises `no_entities_matched` (Decision 2).

Pin reasons as literals (`"not_built"`, `"labs_off"`), per CLAUDE.md Conventions.

## Docs

- `docs/action-behavior.md` (~line 108): after the fallback sentence, add that a group core expands for an adapter that
  can't address it is refused the same way, with its most useful member's reason.
- No README, design.md or deferred.md change (design.md's Groups row points to the docstring).

## Verification

- `.venv/bin/pytest -n auto --transcripts=check`: green, with no transcript change (none expected; a change means the fix
  touched a call).
- `uv run python scripts/check_ha_literals.py` if it's not already in the suite.
- No rig run: no call or reply handling changes (tenet 9).

## PR

`wt/expanded-group-reason` off `main`, `pr-draft <this plan>`. It is a `core/` change, so it needs a repo maintainer
(Jason). The audit at ready time goes to an Opus auditor (dispatch is a binding-rule-adjacent surface), then `owner-findings`.
Closes #596.
