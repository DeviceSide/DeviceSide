# DeviceSide

Design: `docs/design.md`; use its glossary's terms in code and docs. Progress to v0.1.0: `TODO.md`; tick items off
in the PR that finishes them.

When an action should raise, skip a target, or what its response holds: match core, per `docs/action-behavior.md`.

Scope comes from the design, the device's capabilities and the `experimental` flag (Evidence below), never from the
README: it records what ships, so its "not X" means not yet. Reword such a line to the real state, and update the README
after the work lands.

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

## Evidence

1. User experience is the north star: actions make devices do what users expect, quickly.
2. Probe before you build: when unsure how a device responds, run a cheap probe and record what it shows.
3. Verify, then trust: a verified fact stands across firmware, HA and code changes until evidence contradicts it.
4. Surprises reopen facts: root-cause a bug, record the finding, and log so the first report holds the diagnosis.
5. Proof follows the call: code that sends the same call inherits its evidence; unit tests pin the call.
6. Simplify relentlessly: a new rule or guardrail names the user-visible failure it prevents and what it replaces.
7. Maintainers judge sufficiency: gates check that a sign-off exists, not how thorough it was.

The levels (Verified, Documented), the `experimental` flag, caveats, the release gate and the sign-off format:
[`docs/evidence.md`](docs/evidence.md), whose Transition note lists the old gates that still run.

## Maintainers

An integration's package (`integrations/<x>/`, `tests/integrations/<x>/`, its fixture, its bundle
`docs/integrations/<x>/`) belongs to the GitHub handles in its `IntegrationInfo.maintainers`, one or more. A PR confined
to one package needs one maintainer's approval and green CI; anything outside it (`core/`, shared docs,
`docs/models.yaml`) needs a repo maintainer. Repo maintainers merge every PR. Integration maintainers hold Triage, so
GitHub ignores their names in `.github/CODEOWNERS` (from `scripts/gen_codeowners.py`) until one gets write access. A
contributor PR follows CONTRIBUTING's Fast track.

**Caveats** (⚠️ Untested fix, ⚠️ Unmaintained) are set and cleared by a repo maintainer: `docs/evidence.md`.

## Releasing

Work lands on `main`. RCs are cut from it, and `cut-release` tags the version's latest RC, so what ships is what
soaked while `main` moves on. The cut workflows enforce the tag rules, green CI, the RC audit (its record comes from
`/rc-audit`) and, in `cut-release`, the release gate (`docs/evidence.md`, which says when sign-offs must land; until
step 4 lands, the old checks its Transition lists); see their headers. The steps they don't check:

1. **Each RC:** install it through HACS (the rig deploys a checkout, not the release); it loads and the log is clean.
2. Dispatch `cut-release` from `main` with `vX.Y.Z`.
3. Set `manifest.json` on `main` to the next version.

To fix an RC or a release without what `main` has gained since, cut `release/vX.Y.Z` from its tag, land the fix
there, cut the next RC from it, and merge the branch back into `main`.

## Pull requests

- Base: `main`, or a `release/vX.Y.Z` fix branch when one exists for the change.
- Setup: `uv sync`. Test dependencies live in the `dev` group of `pyproject.toml`; never `uv pip install` into `.venv`, as the next sync removes it.
- Before each push: `.venv/bin/pytest` and `pre-commit run --all-files` (ruff and the household check).
- Audits: as the global `## Code audits` rule says. The binding-rule surface that puts an Opus auditor on the PR
  audit is `docs/evidence.md`, the `experimental` flag and `AdapterScope`, `Level.DOCUMENTED`,
  `scripts/check_release.py`, `docs/integrations/*/test-records/`, and rule text in `CLAUDE.md` or `docs/design.md`.

## Layout

- `custom_components/deviceside/core/`: registry, resolver, dispatcher, action registration
- `custom_components/deviceside/actions/`: one module per action
- `custom_components/deviceside/integrations/<integration>/`: one adapter module per action
- `tests/{core,actions,integrations,scripts}`: mirror the above
- `scripts/`: household check, generated docs (device cards, device compatibility page, README feature table), release checks
  (coverage, the release flag, record freshness, tags, RC audits)
- `docs/integrations/<integration>/`: the integration's bundle (see Where facts go); the rig writes its `test-records/`.
  Design detail lives in `docs/design.md`.

The rig, which drives the live HA and writes the records, is a private repo kept out of this one: no rig code or rig
docs here; the rig's test plan, its step files, lives in `tests/rig/steps/`, named for the action they test, landed with
that action. Before adding a case, name what it catches that no existing case or unit test does: a different call shape,
a live-reply branch, or a firmware fact. When the rig is attached to the session, its `CLAUDE.md` says how to run it.

## Conventions

- Async throughout; actions registered once in `async_setup`.
- Logging: [`docs/logging.md`](docs/logging.md): levels, the per-call DEBUG line, and never a device address.
- American English, matching HA. The version lives in `manifest.json`.
