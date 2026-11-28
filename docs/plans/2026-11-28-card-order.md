# Card order: one repo-maintainer-owned list

## Context

PR #664 (TP-Link) renumbered `docs/integrations/control4/devices.yaml` `column_order` 6 → 7, which pinged @skialpine
for a file they own. It wasn't a stray edit: `tests/test_card_order.py` asserts `CARD_ORDER[-1] == "control4"`, so a
new integration *must* slot before Control4, and with integer `column_order` in every bundle that means renumbering
Control4's file. Today the order has two homes: each bundle's `column_order` (owned by that integration's maintainers;
read by `scripts/gen_features.py` `columns()`, which orders the feature table and README cards) and
`core/registry.py` `CARD_ORDER` (shared code, repo maintainer; read at runtime by `coverage.py`), kept equal by the
test. Card order is a repo-maintainer decision, so it should live only in a file a repo maintainer owns, and adding an
integration should never touch another integration's files.

Note: #611 first made `CARD_ORDER` the source, then restored `column_order` ("keep the cards' order mechanism").
This plan reverses that restoration.

## Options considered

- **A (recommended): `CARD_ORDER` is the only order.** Drop `column_order` from the bundles; `gen_features.columns()`
  sorts by `CARD_ORDER`. Owned by a repo maintainer via `core/`; inserting a key renumbers nothing; Control4-last is
  just its position in the tuple. One home, already shipped at runtime.
- B: a shared `docs/card-order.yaml`. Still needs `CARD_ORDER` at runtime (bundles/docs aren't shipped), so two homes
  stay, plus a new file.
- C: line-level ownership of `column_order` in `owners.py`/owner-notice. New mechanism; the bundle still renumbers.
- D: a rule (alphabetical, Control4 last). Removes the choice the user wants a repo maintainer to make.

## Change (option A)

1. `custom_components/deviceside/core/registry.py`: `CARD_ORDER` comment says it is the order of the README cards, the
   feature table and the coverage view, set by a repo maintainer; no mention of `column_order`.
2. `scripts/gen_features.py`: `columns()` keeps `column` (the label) from the bundle, orders by `CARD_ORDER`; an
   integration missing from `CARD_ORDER` is a `SystemExit` naming `core/registry.py`. Docstring updated.
3. `scripts/gen_compat.py`: drop `"column_order"` from the allowed bundle keys (line ~223) and from the **Data**
   docstring paragraph, so a leftover key fails.
4. Every `docs/integrations/*/devices.yaml`: delete the `column_order:` line.
5. `tests/test_card_order.py`: becomes "every registered integration is in `CARD_ORDER` exactly once, and nothing
   else is" (`AdapterRegistry` integrations). Drop the Control4-last assertion (the tuple states it).
6. Tests: `tests/scripts/test_gen_features.py` (columns order and missing-key error, ~245–250, ~342) and
   `tests/scripts/test_gen_compat.py` bundle fixtures (~660–828) drop `column_order`; ordering tests monkeypatch
   `CARD_ORDER`, as `tests/test_coverage.py:255` does.
7. `docs/design.md` ~264: "the integrations' order is `registry.CARD_ORDER`", copy clause gone. CONTRIBUTING / the
   new-integration docs: rg for `column_order` and say a new integration's PR adds its key to `CARD_ORDER` (repo
   maintainer review, which a new integration needs anyway).
8. Regenerated output (`gen_compat.py`, `gen_features.py`) must come out byte-identical: order is unchanged.

Ownership: this PR touches every bundle's `devices.yaml` (one deleted line each), so owner-notice will name the
integration maintainers once. Per the maintainer rules, ask Jason how to handle that notice before the push.

## Sequencing with #664

Land this first on its own `wt/card-order` branch. #664 then merges main, drops its Control4 hunk and its own
`column_order`, and adds `"tplink"` before `"control4"` in `CARD_ORDER`; its owner-notice no longer names
@skialpine. Tell #664's session (`agent-find --pr 664`) and comment on #664 for @skialpine that the change is gone.

## Verification

- `.venv/bin/pytest -n auto --transcripts=check`
- `scripts/gen_compat.py --check`, `scripts/gen_features.py --check`, `scripts/check_docs.py`: no diff in generated files.
- `rg column_order` returns nothing.
- Negative check: remove a key from `CARD_ORDER` locally; `test_card_order` and `gen_features` both fail naming it.

## Coordination

Intent: make `core/registry.py` `CARD_ORDER` the only integration order (cards, feature table, coverage view), so card
order is a repo-maintainer decision and a new integration never edits another's bundle.
Touches: `custom_components/deviceside/core/registry.py`, `scripts/gen_features.py`, `scripts/gen_compat.py`,
`docs/integrations/*/devices.yaml`, `tests/test_card_order.py`, `tests/scripts/test_gen_features.py`,
`tests/scripts/test_gen_compat.py`, `docs/design.md`, `CONTRIBUTING.md`.
Depends-on: none.

Model: sonnet. The plan settles the design, and tests plus `--check` catch a wrong ordering.
