# DeviceSide

Design: `docs/design.md`; use its glossary's terms in code and docs. Progress to v0.1.0: `TODO.md`; tick items off
in the PR that finishes them.

When an action should raise, skip a target, or what its response holds: match core, per `docs/action-behavior.md`.

A PR that teaches a device fact adds it to `docs/device-compatibility.md`, citing its source; an accepted device report
goes into `docs/devices.yaml` (`scripts/gen_compat.py` regenerates the README cards from both).

Scope comes from the design, the device's capabilities and the release flag below, never from the README: it records
what ships, so its "not X" means not yet. Reword such a line to the real state, and update the README after the work lands.

**The repo is public:** no household entity IDs, device names, MACs or hostnames anywhere in it, commit messages included.

**No personal tooling:** deploy hosts, SSH aliases, and private stacks belong in gitignored files (`.private-terms`, `notes/`, `CLAUDE.local.md`), not in committed code, docs or commit messages.

## Release flag

`experimental=True` on an adapter's `AdapterScope` keeps it out of a stable release: `cut-release` fails while any
adapter has it (`scripts/check_release.py --release`). Every adapter module needs ≥95% line coverage, experimental or
not; CI checks it.

**Experimental items, not the flag, carry new work** (PR #307). A new action, integration (including ports), domain,
capability or field ships as `Level.EXPERIMENTAL` once built and unit-tested: in stable releases, refused at runtime
until the user turns on the Experimental features option. The dispatcher is the only gate: adapters never read the
option, and turning it on never changes how any other item behaves. A bug in an Experimental item is never
`severity:high`.

**Setting it:** for a behavior change to a Verified item that the rig can't exercise. Leave it off for refactors,
performance work and fixes to adapters the rig can retest before the next RC. When unsure, ask.

**Clearing it:** a PR citing a passing test record (`docs/test-records/<integration>/<action>*.md`) that covers the
adapter's whole scope bar its Documented, Reported and Experimental items: `AdapterScope.domains`, `.capabilities`,
`.fields`, and each of `.options` on and off.

**Proof follows the call.** A record proves the call an adapter sends and the capability it reaches (Shelly: the RPC
component), whatever entity domain the target shows: a relay exposed as a `switch` or an on/off `light` rides one
record. A native group path is proven once any action of the same adapter class has passed through it and the command has
passed on one light (PR #204).

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
Fields are never Documented: a field changes the call. A Documented item stands only while its sibling does: a change
to its call, or its Reported sibling falling to Experimental, makes it Experimental until a record or a new report on
the sibling. A record promotes the item to Verified. Anything else untested is Experimental, or out of
scope and refused, never Documented on a sibling's proof.

**Reported.** A scope item ships as `Level.REPORTED` on an accepted working user report of the item's call, when unit
tests pin the payload. It has no record, so no freshness check; a change to its call makes it Experimental until a
new report or a record. Fields may be Reported. A record promotes it to Verified.

## Releasing

Work lands on `main`. RCs are cut from it, and `cut-release` tags the version's latest RC, so what ships is what
soaked while `main` moves on. The cut workflows enforce the tag rules, green CI, the RC audit (its record comes from
`/rc-audit`), the release flag, and test records that pass and are no older than their adapter's code
(`check_release.py --records`, so each adapter changed since its last rig run, beyond its `experimental` flag, needs a
new one); see their headers.
The steps they don't check:

1. **Each RC:** install it through HACS (the rig deploys a checkout, not the release); it loads and the log is clean.
2. Dispatch `cut-release` from `main` with `vX.Y.Z`.
3. Set `manifest.json` on `main` to the next version.

To fix an RC or a release without what `main` has gained since, cut `release/vX.Y.Z` from its tag, land the fix
there, cut the next RC from it, and merge the branch back into `main`.

## Pull requests

- Base: `main`, or a `release/vX.Y.Z` fix branch when one exists for the change.
- Setup: `uv sync`. Test dependencies live in the `dev` group of `pyproject.toml`; never `uv pip install` into `.venv`, as the next sync removes it.
- Before each push: `.venv/bin/pytest` and `pre-commit run --all-files` (ruff and the household check).
- Audits, for PRs that change code (scripts and CI workflows included; a docs- or config-only PR skips them): run
  `audit-code` in the same turn you reach it, delegated as its "As a gate" section says. The binding-rule surface
  that puts an Opus auditor on the pre-merge gate is the release flag and `AdapterScope`, `Level.DOCUMENTED`,
  `scripts/check_release.py`, `docs/test-records/`, and rule text in `CLAUDE.md` or `docs/design.md`.
  Each audit is a step, not a stopping point: fix its findings
  and carry on; stop for Jason only on a big judgment call. Judge each finding by the codebase's long-term health,
  not the PR's convenience: fix it now unless it is genuinely out of scope, and then say where it is tracked.
  - Before opening the PR: on the diff, then open the PR.
  - Before merging: a clean run over the whole PR diff, then merge. Skip it only for a single-commit PR that needed
    no fixes after its first audit.

## Layout

- `custom_components/deviceside/core/`: registry, resolver, dispatcher, action registration
- `custom_components/deviceside/actions/`: one module per action
- `custom_components/deviceside/integrations/<integration>/`: one adapter module per action
- `tests/{core,actions,integrations,scripts}`: mirror the above
- `scripts/`: household check, generated docs (device cards, device compatibility page, README feature table), release checks
  (coverage, the release flag, record freshness, tags, RC audits)
- `docs/test-records/<integration>/`: test records, written by the rig. Design detail lives in `docs/design.md`.

The rig, which drives the live HA and writes the records, is a private repo kept out of this one: don't add rig code,
step files or rig docs here. When it is attached to the session, its `CLAUDE.md` says how to run it.

## Conventions

- Async throughout; `_LOGGER = logging.getLogger(__name__)`; actions registered once in `async_setup`.
- American English, matching HA. The version lives in `manifest.json`.
