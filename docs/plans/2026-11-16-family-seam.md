# Family seam: ownership below the integration

Date: 2026-11-16. Status: in progress.

## Why

Ownership is a path prefix per integration (`PATHS` in `scripts/gen_codeowners.py`). Zigbee2MQTT and ZHA each front
many vendors' firmware, and a vendor is not a path in either: its rules sit in an order-sensitive `RULES`, its levels
in shared constants, its calls as branches inside adapters. So nobody can be handed "Tuya on Zigbee2MQTT" without
being handed the whole package. This plan makes a vendor a path, a **family**, so ownership of it is one tuple.

User-visible failure prevented: a device-owner's fix waits on a maintainer who doesn't own the device, or a
contributor's change for one vendor reclasses another vendor's devices unnoticed.

## Decisions (locked with the repo maintainer)

1. Families live inside each integration (`integrations/<x>/families/<family>/`), not across integrations: proof
   follows the call and the class, and the calls differ per stack.
2. What two stacks do share, the device's own Zigbee strings and sourced firmware facts, lives once in a **catalog**,
   `custom_components/deviceside/zigbee/<family>.py`: patterns and facts only, no levels, no calls, no HA imports. A
   catalog file exists only where two stacks read the same Zigbee string (today: Tuya).
3. Every vendor class moves into a family on both Zigbee stacks (Zigbee2MQTT: hue, tuya, sengled, gledopto; ZHA: hue,
   tuya, sengled, sonoff). The integration keeps the transport, the default class `other` and the precedence between
   families. Families are opt-in: Control4, Hue, Shelly and Matter are untouched.
4. A family maintainer may `/merge` a PR whose every file they own, including level changes (Verified, lifting the
   experimental flag). They may not add, change or remove a `harms`-bearing entry (`NoKnownMethod`, `NotBuilt`): the
   gate refuses, and an integration or repo maintainer merges it.
5. The seam covers code, unit tests and new research (`docs/integrations/<x>/research/<family>/`). Test records,
   `index.md`, `internals.md` and `devices.yaml` stay whole and the integration's; existing dated research stays where
   it is. A `TODO.md` item tracks per-family records.
6. An integration's maintainers own everything in its families too. A family with `maintainers=()` is simply the
   integration's.
7. Only a repo maintainer changes any `maintainers` tuple; a `/merge` PR that changes one is refused.
8. The gate's rule becomes "the commenter owns every file the PR changes" (generated output aside), replacing
   "confined to one integration's package": a catalog change touches both stacks' families.
9. Rename, last stage: "Not supported" is the umbrella; its two kinds get names that say why. `NotSupported` becomes
   `NotBuilt` (`not_built`, "Not built yet"); `DoesntWork` becomes `NoKnownMethod` (`no_known_method`, "No known
   method"). The response reason codes, translation keys, card sections and `docs/models.yaml` keys follow. `integration_not_supported` and `target_not_supported` keep their names. Dated research, plans and
   audits are not edited.

## Design

### Core (`custom_components/deviceside/core/`)

- `OwnCall` (scope.py): a class's own call as a first-class value, replacing the branch on
  `request.limits == COUNTDOWN_LIMITS`. Fields: `send`, an async callable `(adapter, hass, request, target) ->
  EntityResult`, and `limits: DurationLimits | None`. Compared by identity.
- `AdapterScope.own_calls` becomes `Mapping[str, OwnCall]`. `AdapterScope.own_call(classes) -> OwnCall | None` joins
  `limits(classes)`; `apart` and the `own_call` refusal are unchanged in behavior.
- Dispatcher: a run is keyed by its dropped fields and its `OwnCall` (or None), and carries it. `_run_adapter` calls
  `adapter.execute_own(hass, request, targets, call)` when the run has one, else `execute`. Duration clamping still
  uses the call's limits.
- `Adapter.execute_own`: default runs `call.send` per target through `gather`; an adapter overrides it to wrap sends
  the way its `execute` does (Zigbee2MQTT's `checked`).
- `TimedRequest.limits` is removed if nothing reads it once the branch is gone.
- `Family` (scope.py): `key`, `maintainers: tuple[str, ...] = ()`, `classes: frozenset[str]`, `scopes: Mapping[str,
  FamilyScope]` by action key. `FamilyScope`: `capabilities`, `no_known_method`, `not_built`, `own_calls`, each a
  mapping by class, all default empty. An action a family gives no scope leaves its classes out of that adapter's
  scope, so they are refused as not built, as leaving a class out does today.
- `family_scope(families, action) -> FamilyScope`: the families' parts for one action merged; a class in two families
  raises. An adapter builds its scope from it plus the integration's own entry for `other`.
- `IntegrationInfo.families: tuple[Family, ...] = ()`. The registry checks, when it is non-empty: keys unique and
  shaped like a package name; maintainers valid handles (may be empty); the families' classes disjoint; every class
  the integration declares belongs to exactly one family, except the default class; every class a family's scopes
  name is one of its own.
- Behavior is unchanged for every call: this stage is a refactor. Existing tests pass unedited except where they
  construct `own_calls` or read `request.limits`.

### Catalog (`custom_components/deviceside/zigbee/tuya.py`)

Named regex patterns and identities both stacks read, each with its source in a comment: the datapoint manufacturer
pattern (`_TZE…`), the ZCL manufacturer pattern (`_TZ3000_…`, `_TYZB01_…`), the datapoint model (`TS0601`), the ZCL
model pattern (`TS` and four digits), and the maker string reported harmed on the countdown with its model. Unit
tests in `tests/zigbee/test_tuya.py` pin example strings against each pattern. Both stacks' Tuya families import
these; neither restates them.

### An integration with families (Zigbee2MQTT and ZHA)

```
integrations/<x>/
  rules.py                 the rule type and matcher (integration's)
  families/__init__.py     FAMILIES, and RULES: the precedence between families' rule groups (integration's)
  families/<family>/       FAMILY = Family(...) as a literal call, its class names, rule groups, per-action levels,
                           harms entries, own calls, and code only its classes need
  classes.py               `other`, its levels, `capability`, placement (integration's)
tests/integrations/<x>/
  families/<family>/       the family's unit tests
  test_classification.py   the integration's snapshot (below)
```

- A family exports one or more named rule groups. Order inside a group is the family's; order between groups is the
  integration's, in `families/__init__.py`, with the reason for each constraint beside it (the current `classes.py`
  docstrings' "rule order" text moves there). The composed `RULES` is exactly today's order: no device changes class.
- A family's rule names only that family's classes (checked where rules are composed).
- Dependency direction: adapters and `classes.py` import families; families import the integration's transport
  modules (`bridge`, `zcl`, `addressing`, `rules`) and the catalog, never an adapter module. No import cycles.
- A vendor's facts live in its family. A whole alternate call is an `OwnCall` (Zigbee2MQTT's Tuya countdown); a
  per-class parameter an adapter needs (ZHA's `COUNTS_SECONDS`, Zigbee2MQTT's Hue native control) is exported by the
  family and imported by the adapter. Integration-owned modules name no vendor's class constant except by importing
  it from its family.
- `FAMILY = Family(key=..., maintainers=(...), ...)` has `key` and `maintainers` as literals, so the gate reads them
  with `ast` and no import. Every family starts with `maintainers=()`.
- Classification snapshot, `tests/integrations/<x>/test_classification.py`, the integration's: a table of devices
  (the fields the rules read, and the expected class) covering every class and every cross-family trap the rule-order
  text names (a Tuya device under another vendor's definition, a TS011F's manufacturer string against the ZCL manufacturer pattern, the registry
  fallbacks). It is how the integration's maintainer protects other families: a family change that reclasses a
  listed device fails until this file, outside the family, is edited.

### Gate, CODEOWNERS, routing (`scripts/`)

- `gen_codeowners.py`: `PATHS` stays the integration's; `FAMILY_PATHS` adds
  `custom_components/deviceside/integrations/{key}/families/{family}/`, `tests/integrations/{key}/families/{family}/`
  and `docs/integrations/{key}/research/{family}/`; `CATALOG_PATHS` adds `custom_components/deviceside/zigbee/{family}.py`
  and `tests/zigbee/test_{family}.py`. A family line lists the family's maintainers, then the integration's, then the
  repo's; a catalog line the maintainers of every family of that key and of their integrations. A line is written
  only when it names an owner the enclosing line doesn't, so today's CODEOWNERS is unchanged.
- `check_maintainer_merge.py`: each changed file has an owner set at the base branch (family: its maintainers and its
  integration's; catalog: as above; integration package: its maintainers; generated output: anyone passing the rest;
  anything else: nobody). The PR passes when the commenter is in every file's set. It still refuses a PR that changes
  README outside generated blocks or sets or clears a caveat, and now one that changes any `maintainers` value in a
  changed Python file, and, for a commenter who is not a maintainer of the file's integration, one that adds, changes
  or removes a `NoKnownMethod(...)` or `NotBuilt(...)` call in it (compared as AST dumps, as caveats are). Its
  docstring states what it can't see (a rule change that moves devices out of a harmed class), as it does for caveats.
- Family maintainers are read by parsing `families/<family>/__init__.py`; a test checks the parse against the
  registry, as `test_route_issue.py` does for integrations.

### Docs and rules

- `docs/design.md` glossary: Family, Catalog; Maintainer extended to families; Not supported as the umbrella with its
  two kinds (final names from the rename stage).
- `CLAUDE.md`: Maintainers section (families, the owns-every-file rule, what a family maintainer can't merge) and
  "Where facts go" (family code, catalog, family research).
- `docs/evidence.md`: who may sign off a family's classes and who changes a harms entry.
- `CONTRIBUTING.md`, `docs/device-compatibility.md` (maintainers wording), `docs/repo-maintainers.md` (appointing a
  family maintainer), `TODO.md` (per-family records and docs).
- Each integration's `internals.md` points to `families/__init__.py` for the rule order instead of `classes.py`.

## Stages

1. Core and catalog, with the smallest change to Zigbee2MQTT's `turn_on_for` that keeps it working on `OwnCall`.
2. In parallel, on disjoint files: Zigbee2MQTT families; ZHA families; gate, CODEOWNERS and docs.
3. The rename (Decision 9), across the whole repo.
4. An audit of the diff against this plan's intent, and fixes.

Each stage ends with `.venv/bin/pytest` and `pre-commit run --all-files` green. No stage changes what any call sends
or which class any device gets; no hardware run is needed (Evidence 8: no decision takes its result), and unit tests
pin the calls (Evidence 5).

## Intent checks (what the audit verifies)

- No device changes class and no call changes: `RULES` composes to the same order; every adapter's scope holds the
  same classes at the same levels with the same harms entries as before.
- Handing a vendor to someone is one edit: a `maintainers` tuple in one family's `__init__.py`, after which
  CODEOWNERS regenerates and the gate lets them merge a PR confined to that family.
- A family maintainer cannot, alone: touch another family, the transport, the precedence list or the snapshot; change
  a harms entry; change a maintainers tuple; set a caveat.
- A catalog edit that would reclass a device on the other stack fails that stack's tests.
- Integrations without families see no change in code, CODEOWNERS or gate behavior.
- No vendor fact has two homes: the catalog's patterns are not restated in either stack.
