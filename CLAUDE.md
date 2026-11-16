# DeviceSide

Design: `docs/design.md`; use its glossary's terms in code and docs. Progress to v0.1.0: `TODO.md`; tick items off
in the PR that finishes them.

When an action should raise, skip a target, or what its response holds: match core, per `docs/action-behavior.md`.

Scope comes from the design, the device's capabilities and the `experimental` flag (Evidence below), never from the
README: it records what ships, so its "not X" means not yet. Reword such a line to the real state, and update the README
after the work lands.

**The repo is public:** no household entity IDs, device names, MACs or hostnames anywhere in it, commit messages included.

**Until v0.1.0 ships, fix the architecture now:** this window is the cheap time for hard architectural choices,
which get much harder with dozens of package contributors and thousands of users. Given the choice between touching
less code and fewer binding surfaces, or the right long-term fix, take the long-term fix. (Removed once v0.1.0 ships:
`TODO.md`, v0.1.0.)

**No personal tooling:** deploy hosts, SSH aliases, and private stacks belong in gitignored files (`.private-terms`, `notes/`, `CLAUDE.local.md`), not in committed code, docs or commit messages.

## Where facts go

One fact, one home; elsewhere, point to it. A device fact cites its source: a record, report, research file or upstream
link. `<x>` is `docs/integrations/<integration>/`, the integration's bundle; a fact spanning integrations goes in the
shared home named in parentheses.

| Fact | Home |
|---|---|
| User-facing limits and device classes | `<x>/index.md` (shared: `docs/device-compatibility.md`) |
| Wire calls, measurements, upstream defects | `<x>/internals.md` (shared: `docs/internals.md`, core HA: `docs/defects.md`) |
| A vendor's rules, levels and calls, on an integration with families | its family: `integrations/<x>/families/<family>/` |
| Zigbee strings two integrations' families share | the catalog: `custom_components/deviceside/zigbee/<family>.py` |
| Classes, levels, no known method and not built yet entries | the package's code: `IntegrationInfo.classes` and the scopes' `no_known_method` and `not_built` (on an integration with families, the entries are in its `integrations/<x>/refusals.py`; `scripts/gen_compat.py` regenerates the cards; entries not yet moved: `<x>/devices.yaml`, shared `docs/models.yaml`) |
| A class's card phrase and section | `<x>/devices.yaml` |
| Models across integrations | `docs/models.yaml` |
| Dated sources, never edited after | `<x>/research/` (a family's new ones: `<x>/research/<family>/`; shared: `docs/research/`) |
| Run evidence | `<x>/test-records/*.json`, in the shape `docs/test-records.schema.json` gives |
| Why the code does something | the module docstring, a few lines, linking `internals.md` for the evidence |
| Rule evidence | the PR body |
| Repo settings and repo-maintainer steps | `docs/repo-maintainers.md` |

`index.md` holds only what changes what a user does or expects, in the shape of Hue's page (Shelly's for "Try it":
what was tried, on what, one report per class). Timings, odds and why a limit exists go in `internals.md`. A behavior
every integration shares is in `docs/integrations.md`: add your value there, don't restate it.

## Evidence

1. User experience is the north star: actions make devices do what users expect, quickly.
2. Probe before you build: when unsure how a device responds, run a cheap probe and record what it shows.
3. Verify, then trust: a verified fact stands across firmware, HA and code changes until evidence contradicts it.
4. Surprises reopen facts: root-cause a bug, record the finding, and log so the first report holds the diagnosis.
5. Proof follows the call and the class: code that sends the same call to the same class of device inherits its
   evidence; unit tests pin the call.
6. Simplify relentlessly: a new guardrail needs evidence its failure happens; a new rule or guardrail names the
   user-visible failure it prevents and what it replaces.
7. Maintainers judge sufficiency: gates check that a sign-off exists, not how thorough it was.
8. Test to decide: a hardware run needs a decision its result takes (a design choice, a foundation, lifting a flag, a
   surprise, a release), run at the last point that can take it: the release's run for a device the rig or a
   maintainer reaches, so no merge waits on a run; the contributor's PR for their own devices. No plan gates a step
   on a run without naming the decision.
9. Retest what the change exercises: only the rig cases whose call or reply handling changed. The gate reopens a
   record when its own adapter's module or a shared one changed; a `no_call_changed` row at that change keeps it.

The levels (Verified, Documented), device classes, the `experimental` flag, caveats, the release gate and the sign-off
format:
[`docs/evidence.md`](docs/evidence.md).

## Maintainers

An integration's package (`integrations/<x>/`, `tests/integrations/<x>/`, its fixture, its bundle
`docs/integrations/<x>/`) belongs to the GitHub handles in its `IntegrationInfo.maintainers`, one or more. A family
in it (`integrations/<x>/families/<family>/`, `tests/integrations/<x>/families/<family>/`,
`docs/integrations/<x>/research/<family>/`) belongs to the handles in its `Family.maintainers` as well, which may be
none; a catalog file (`custom_components/deviceside/zigbee/<family>.py` and its test) to the maintainers of every
family of that key and of those families' integrations.

A PR merges on one maintainer's approval or `/merge`, and green CI, when that maintainer owns every file it changes;
a file none of them owns (`core/`, shared docs, `docs/models.yaml`) needs a repo maintainer. Regenerated output follows
its inputs: such a PR that also regenerates shared generated files (README, `docs/device-compatibility.md`,
CODEOWNERS) still needs only its maintainer, as CI's `--check` proves them. It merges when the maintainer comments
`/merge <sha>`, even on their own PR (`scripts/check_maintainer_merge.py` says what it refuses), or when a repo
maintainer merges it; repo maintainers merge every other PR.

A family maintainer sets their classes' levels, and can't merge alone what protects other families: another family,
the integration's transport, `families/__init__.py` (the rule order between families), the classification snapshot,
a refusal entry, or a new class or family; an integration maintainer merges those (a new family, with its
`maintainers` tuple, a repo maintainer). Refusal entries (`NoKnownMethod`, `NotBuilt`) are kept
from a family by where they live: an integration with families holds every one in its `integrations/<x>/refusals.py`,
outside every family, and a `FamilyScope` can't hold one. Only a repo maintainer changes a `maintainers` tuple.

Integration and family maintainers hold Triage (`docs/repo-maintainers.md`), so GitHub ignores their names in
`.github/CODEOWNERS` (from `scripts/gen_codeowners.py`), as Triage isn't write access. A contributor PR follows
CONTRIBUTING's Fast track.

**Changing someone else's code:** before you change a package or family whose maintainers don't include you, its
maintainers hear of it first; never wait on their approval (⚠️ Unmaintained covers one who's gone).
`owner-notice.yml` mentions them on any PR that changes their code, standing in for the review request Triage doesn't
get. `scripts/owners.py` says who maintains a path, and `--as <login>` which of a finding's paths aren't yours.

**Caveats** (⚠️ Untested fix, ⚠️ Unmaintained) are set and cleared by a repo maintainer: `docs/evidence.md`.

## Releasing

Cutting, tagging and fixing RCs and releases: the `release` skill (`.claude/skills/release/SKILL.md`).

## Pull requests

- Base: `main`, or a `release/vX.Y.Z` fix branch when one exists for the change.
- Setup: `uv sync`. Test dependencies live in the `dev` group of `pyproject.toml`; never `uv pip install` into `.venv`, as the next sync removes it.
- Before each push: `.venv/bin/pytest` and `pre-commit run --all-files` (ruff and the household check).
- Audits: as the global `## Code audits` rule says. The binding-rule surface that puts an Opus auditor on the PR
  audit is `docs/evidence.md`, the `experimental` flag and `AdapterScope`, `Level.DOCUMENTED`,
  `scripts/check_release.py`, `docs/test-records.schema.json`, `docs/integrations/*/test-records/`, and rule text in
  `CLAUDE.md` or `docs/design.md`.

## The rig

The rig, which drives the live HA and writes the records in `docs/integrations/<integration>/test-records/`, is a
separate repo (jasonmx/ha-rig) kept out of this one: no rig code or rig docs here. The rig's test plan, its
step files, named for the action they test and landed with that action, has two homes: shared ones in `tests/rig/steps/`
need a repo maintainer; an integration's own in `tests/integrations/<x>/rig/`, run on `<x>` alone, belong to its
maintainers, and repo maintainers may adopt them into the shared files. Before adding a case, name what it catches that
no existing case or unit test does: a different call shape, a live-reply branch, or a firmware fact. When the rig is
attached to the session, its `CLAUDE.md` says how to run it.

## Conventions

- Logging: [`docs/logging.md`](docs/logging.md): levels, the per-call DEBUG line, and never a device address.
- American English, matching HA.
