# DeviceSide

Design: `docs/design.md`; use its glossary's terms in code and docs. Progress to v0.1.0: `TODO.md`; tick items off
in the PR that finishes them.

When an action should raise, skip a target, or what its response holds: match core, per `docs/action-behavior.md`.

Scope comes from the design, the device's capabilities and the release flag below, never from the README: it records
what ships, so its "not X" means not yet. Reword such a line to the real state, and update the README after the work lands.

**The repo is public:** no household entity IDs, device names, MACs or hostnames anywhere in it, commit messages included.

**No personal tooling:** deploy hosts, SSH aliases, and private stacks belong in gitignored files (`.private-terms`, `notes/`, `CLAUDE.local.md`), not in committed code, docs or commit messages.

## Where facts go

One fact, one home; elsewhere, point to it. A device fact cites its source: a record, report, research file or upstream
link. `<x>` is `docs/integrations/<integration>/`, the integration's bundle; a fact spanning integrations goes in the
shared home named in parentheses.

| Fact | Home |
|---|---|
| User-facing limits and device classes | `<x>/index.md` (shared: `docs/device-compatibility.md`) |
| Wire calls, measurements, upstream defects | `<x>/internals.md` (shared: `docs/internals.md`, core HA: `docs/defects.md`) |
| Classes, doesn't-work entries, accepted device reports | `<x>/devices.yaml` (shared doesn't-work: `docs/models.yaml`; `scripts/gen_compat.py` regenerates the cards) |
| Models across integrations | `docs/models.yaml` |
| Dated sources, never edited after | `<x>/research/` |
| Run evidence | `<x>/test-records/` |
| Why the code does something | the module docstring |
| Rule evidence | the PR body |

## Release flag

`experimental=True` on an adapter's `AdapterScope` keeps it out of a stable release: `cut-release` fails while any
adapter has it (`scripts/check_release.py --release`). Every module of an adapter's code (`adapter_code` in that script,
bar `__init__.py`) needs ≥95% line coverage, experimental or not; CI checks it.

**Experimental items, not the flag, carry new work** (PR #307). A new action, integration (including ports), domain,
capability or field ships as `Level.EXPERIMENTAL` once built and unit-tested: in stable releases, refused at runtime
until the user turns on the Experimental features option. The dispatcher is the only gate: adapters never read the
option, and turning it on never changes how any other item behaves.

**Setting it:** for a behavior change to a Verified item that the rig can't exercise. Leave it off for refactors,
performance work and fixes to adapters the rig can retest before the next RC. When unsure, ask.

**Clearing it:** a PR citing a passing test record (`docs/integrations/<integration>/test-records/<action>*.md`)
that covers the adapter's whole scope bar its Documented, Reported and Experimental items: `AdapterScope.domains`,
`.capabilities`, `.fields`, and each of `.options` on and off. `check_release.py --records` checks it against the
records' `Covers` rows.

**Proof follows the call.** A record proves the call an adapter sends and the capability it reaches (Shelly: the RPC
component), whatever entity domain the target shows: a relay exposed as a `switch` or an on/off `light` rides one
record. A native group path is proven once any action of the same adapter class has passed through it and the command has
passed on one device (PR #204). An observed pass in the integration's `test-records/_observed.md`, when present, proves
that a maker's devices, started from that state, respond as seen to that call sequence and to any sequence it begins with,
across firmware (an exception to once per firmware version), HA and code; an observed failure on a model, newer
than that model's latest pass covering the lent sequence, blocks lends to that model for sequences that begin with the
failed one.

**Shared code is proven once.** A change to `core/` needs no retest from each integration: one passing Verified record,
of any integration, whose run covered every clause the change touches at code where the module matches HEAD, proves it
for every adapter that reaches it. A change to a module's or class's own statements (constants, class attributes,
imports) runs at import in every run, so it is never cleared this way. A change inside an integration's package still
stales only that integration's records and retests. Format and rules: `scripts/check_release.py`'s docstring.

**Default to Documented.** A rig case earns its place only by catching what nothing else can: a call shape, a
branch the adapter takes on a live reply, or a device behavior that DeviceSide or its docs rely on. One Verified
case per call shape per adapter; every sibling that meets the test below rides it. A firmware fact (precedence,
bounds, timing) is proven once per firmware version, not per code change. Confirming a stored setting counts as
confirming the call.

**Documented.** A scope item ships without a record, as `Level.DOCUMENTED`, when all of these hold: the adapter
sends it the same call as a Verified or Reported item, differing only in addressing (component, endpoint, entity
domain); the vendor or standard documents that call identically for both, and no known class of devices departs from
it; a failure shows as `rejected` or `sent`, never a wrong device state, nor `confirmed` unless what it confirms is the
stored setting the call wrote, read back; and unit tests pin the payload.
Fields are never Documented: a field changes the call. A change to a Documented item's call alone makes it
Experimental until a record of it; a change it shares with its sibling rides the sibling's new record or report. It
falls with its Reported sibling (`AdapterScope.siblings` names the sibling and refuses one below Reported). A record
promotes the item to Verified. Anything else untested is Experimental, or out of scope and refused, never Documented
on a sibling's proof.

**Reported.** A maintainer can request moving an Experimental item to `Level.REPORTED` once it has five accepted working
user reports of its call from users other than the maintainer, and no open bugs, when unit tests pin the payload; review
checks the count, `gen_compat.py` doesn't. Its siblings sharing that call may move from Experimental to Documented on the
same evidence when they meet the Documented test. It has no record; after a change to its call, one working report at
the new code, the maintainer's included, keeps it Reported and is its retest (below). A field may be Reported once a
report can name one (`devices.yaml` reports name a domain or capability only; `gen_compat.py` refuses a Reported field
until then). A record promotes it to Verified. One working report on a Documented item promotes it to Reported.

**Retests.** Every change to an adapter that ships a call (Documented or better) is retested before release: a rig
record, a `_manual.md` line from one of its maintainers in a PR, or an accepted working report at a release tag. An
adapter with a Verified call still needs its records. Format and freshness: `scripts/check_release.py`'s docstring.

## Maintainers

An integration's package (`integrations/<x>/`, `tests/integrations/<x>/`, its fixture, its bundle
`docs/integrations/<x>/`) belongs to the GitHub handles in its `IntegrationInfo.maintainers`, one or more. A PR confined
to one package needs one maintainer's approval and green CI; anything outside it (`core/`, shared docs,
`docs/models.yaml`) needs a repo maintainer. Repo maintainers merge every PR. Integration maintainers hold Triage, so
GitHub ignores their names in `.github/CODEOWNERS` (from `scripts/gen_codeowners.py`) until one gets write access. A
contributor PR follows CONTRIBUTING's Fast track.

**Unmaintained:** `AdapterScope.unmaintained` (an issue URL or a reason), set per adapter at the repo maintainers' call.
The adapter stays live; setup warns and its card shows ⚠️ Unmaintained. An integration whose maintainers are all gone
gets it on every adapter. It clears when someone fixes the adapter or adopts the integration. Like `experimental`, it is
not a code change to the records check.

**Stale tests:** `AdapterScope.stale_tests` (an issue URL or a reason), set by hand on an adapter left without a fresh
retest at the cut. It ships live; setup warns, its card shows ⚠️ Stale tests, and the release notes link the device
report form to recruit testers. One accepted report at the new code (or any fresh retest) clears it, in the PR that
lands the retest. `cut-release` checks the latest RC's commit, so set `stale_tests`, or land the retest that clears it,
before the last RC.
Unmaintained stays separate: a call about a missing maintainer, not missing evidence.

## Releasing

Cutting, tagging and fixing RCs and releases: the `release` skill (`.claude/skills/release/SKILL.md`).

## Pull requests

- Base: `main`, or a `release/vX.Y.Z` fix branch when one exists for the change.
- Setup: `uv sync`. Test dependencies live in the `dev` group of `pyproject.toml`; never `uv pip install` into `.venv`, as the next sync removes it.
- Before each push: `.venv/bin/pytest` and `pre-commit run --all-files` (ruff and the household check).
- Audits: as the global `## Code audits` rule says. The binding-rule surface that puts an Opus auditor on the PR
  audit is the release flag and `AdapterScope`, `Level.DOCUMENTED`, `scripts/check_release.py`,
  `docs/integrations/*/test-records/`, and rule text in `CLAUDE.md` or `docs/design.md`.

## The rig

The rig, which drives the live HA and writes the records in `docs/integrations/<integration>/test-records/`, is a
private repo kept out of this one: don't add rig code, step files or rig docs here. When it is attached to the
session, its `CLAUDE.md` says how to run it.

## Conventions

- American English, matching HA.
