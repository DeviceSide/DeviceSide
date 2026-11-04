# device_side

Design: `docs/design.md`; use its glossary's terms in code and docs. Progress to v0.1.0: `TODO.md`; tick items off
in the PR that finishes them.

When an action should raise, skip a target, or what its response holds: match core, per `docs/action-behavior.md`.

**The repo is public:** no household entity IDs, device names, MACs or hostnames anywhere in it, commit messages included.

**No personal tooling:** deploy hosts, SSH aliases, and private stacks belong in gitignored files (`.env.rig`, `notes/`, `CLAUDE.local.md`), not in committed code, docs or commit messages.

## Release flag

`experimental=True` on an adapter's `AdapterScope` keeps it out of a stable release: `cut-release` fails while any
adapter has it (`scripts/check_release.py --release`). Every adapter module needs ≥95% line coverage, experimental or
not; CI checks it.

**Setting it:** for a new action, field or attribute, or integration (including ports), and for a behavior change to
a released adapter that the rig can't exercise. Leave it off for refactors, performance work and fixes the rig run
before each RC covers. When unsure, ask.

**Clearing it:** a PR citing a passing test record (`docs/test-records/<integration>/<action>*.md`) that covers the
adapter's whole scope: `AdapterScope.domains`, `.capabilities`, `.fields`, and each of `.options` on and off.

**Proof follows the call.** A record proves the call an adapter sends and the capability it reaches (Shelly: the RPC
component), whatever entity domain the target shows: a relay exposed as a `switch` or an on/off `light` rides one
record. A capability or field nobody has tested is left out of scope and refused, never added on a sibling's proof.
A native group path is proven once any action of the same adapter class has passed through it and the command has
passed on one light (PR #204).

## Releasing

The cut workflows enforce the tag rules, green CI, the RC audit (its record comes from `/rc-audit`) and the release
flag; see their headers. The steps they don't check:

1. **Each RC:** a rig run at its head; its test records cite the commit, so no sign-off is needed. Then install the
   RC through HACS (the rig deploys a checkout, not the release); it loads and the log is clean.
2. **Before the release:** the README feature table is current.
3. Merge `release/vX.Y.Z` into `main`. Check that every issue the release fixes closed with it: closing keywords
   only take effect on `main`.
4. Dispatch `cut-release` from `main` with `vX.Y.Z`.
5. Cut the next version's branch, `release/vA.B.C`, from `main` and set `manifest.json` to `A.B.C`; its first tag
   is `vA.B.Crc1`.

## Pull requests

- Base: whichever is newer, `main` or the latest `release/vX.Y.Z` branch.
- Setup: `uv sync`. Test dependencies live in the `dev` group of `pyproject.toml`; never `uv pip install` into `.venv`, as the next sync removes it.
- Before each push: `.venv/bin/pytest` and `pre-commit run --all-files` (ruff and the household check).
- Before opening the PR: `/audit-code` on the diff, then fix its findings and carry on to the PR; stop for Jason
  only on a big judgment call. Judge each finding by the codebase's long-term health, not the PR's convenience:
  fix it now unless it is genuinely out of scope, and then say where it is tracked.

## Layout

- `custom_components/device_side/core/`: registry, resolver, dispatcher, action registration
- `custom_components/device_side/actions/`: one module per action
- `custom_components/device_side/integrations/<integration>/`: one adapter module per action
- `tests/{core,actions,integrations,rig}`: mirror the above; `rig/` drives the live HA, only via `scripts/rig.py`,
  on a profile (`tests/rig/profiles/<name>.yaml`, gitignored)
- `scripts/`: rig runner, household check, deploy, release checks (coverage and the release flag, tags, RC audits)
- `docs/test-records/<integration>/`: test records. Design detail lives in `docs/design.md`; running the rig and
  writing step files in `docs/rig.md`.

## Conventions

- Async throughout; `_LOGGER = logging.getLogger(__name__)`; actions registered once in `async_setup`.
- American English, matching HA. The version lives in `manifest.json`.
