# Owner notices: warn a package's maintainers before someone else changes it

Date: 2026-11-16. Status: built on `claude/owner-notices-plan`; stage 3's audit pending. Depends on PR #447 (the family seam,
`docs/plans/2026-11-16-family-seam.md`) merging first.

## Settled with the repo maintainer (2026-11-16)

Each recommendation below was accepted as written; implementation starts once #447 merges.

1. **Evidence 6 for controls 1 and 3.** No PR so far has changed a package without its maintainer hearing:
   Control4's history is its maintainer's own, and #447 leaves Control4 alone. The failure rests on a mechanism, not
   an incident: GitHub drops Triage handles from CODEOWNERS review requests, and `rc-audit` audits every commit in the
   range, whoever owns it. Is a failure that normal use reaches, through a known mechanism, enough evidence? It meets
   the severity rubric's "a path a normal user action reaches". *Recommend yes.*
2. **Who the notice mentions when a repo maintainer changes a family:** the family's maintainers only, or the
   integration's as well? *Recommend both:* the integration's maintainers own the family too (#447, Decision 6).
3. **A family label for routed issues** (`family:<key>`)? *Recommend no:* a family key such as `tuya` exists on two
   integrations, so the label would need the integration in it anyway. `integration:<key>` plus the family's
   maintainers as assignees already routes it, and every family has `maintainers=()` today (Evidence 6: no failure
   yet).
4. **`check_audit.py`: check the new `owner` field?** *Recommend no.* A cross-ownership finding's choice is already
   its `status` (below), and the notice workflow mentions the owner on the fix PR. A check would only prove that a
   field was typed.
5. **When a skill can't tell who runs it** (no `gh` login, no answer): *recommend* treating the runner as owning no
   package. Every package finding is then listed as someone else's: the warning errs loud, never silent.
6. **Notice workflow as its own file or a job in `protected-files.yml`?** *Recommend its own file.* The notice never
   fails, unlike protected-files, and it has a concurrency group, which protected-files' header rules out for itself.

## Why

Integration and family maintainers hold Triage (`docs/repo-maintainers.md`), so GitHub ignores their CODEOWNERS
lines and never requests their review. A repo maintainer can merge any PR, and an integration maintainer can `/merge`
a PR to their own families. The audit skills report and don't fix, but whoever acts on the findings can batch a fix
into another maintainer's package (`audit-code` §5 "Close by proposing how to land the fixes" batches by file, not by
owner). Today the owner can find out after the release.

Three controls close this, none of them blocking. Requiring the owner's approval would let an absent maintainer hold a
release, and ⚠️ Unmaintained (`docs/evidence.md`) already covers that case.

Evidence 6, one sentence per control:

- **1. Findings name their owner.** Prevents a fix to a device class the fixer can't test from shipping unseen by
  the maintainer who can test it, when nobody noticed whose package the finding was in. Replaces the reader's guess
  from the path.
- **2. No cross-ownership fix by default.** Prevents the same failure where the reader did notice but the skill's
  fix batches carried the change anyway. Replaces `audit-code`'s owner-blind fix batches and `rc-audit`'s two-way
  fix-or-waive choice for someone else's package.
- **3. PR notice.** Prevents any change to a package (an audit fix, a hand edit, a repo-wide refactor) merging without
  its maintainer hearing of it. Replaces the CODEOWNERS review request that Triage suppresses.

None is dropped. All three rest on question 1.

## Decisions

1. **One lookup, `scripts/owners.py`.** The owner code in `check_maintainer_merge.py` (`Templates`, `package_paths`,
   `match`, `Package`, `maintainers`, `family_maintainers`, `integrations_with`, `package_of`, `owners`, `GENERATED`)
   and the `ast` parsers in `route_issue.py` (`literals`, `parse`, `parse_family`, `Integration`, `Family`) move there.
   `check_protected.repo_maintainers` does too. The gate, `route_issue.py`, the notice script and the skills (through
   its CLI) all import or call it. It stays standard-library only and reads a rev with `git show`, never importing an
   integration, so it can run from the base branch on a PR's files.
2. **Direct owners.** Each changed path has one or more *owner groups*. A path in an integration's package has one,
   its maintainers. A path in a family has one, the family's maintainers, or the integration's if the family has none.
   A catalog file has one per family that shares it, each formed the same way. A path outside every package has one,
   the repo maintainers. Each group also lists its *enclosing* maintainers: a family's integration's, when the family
   has maintainers of its own. The gate's owner set is unchanged: the union of every group's direct and enclosing
   handles (repo maintainers aside).
3. **Someone else's package**: a group whose direct owners don't include the person. This is the one test both
   controls use: the skills apply it to the runner, the notice to the PR's author. An integration maintainer changing
   their own family hits it, and so does a family maintainer changing a catalog that the other stack's family shares.
   The gate's "owns every file" doesn't have to change.
4. **Owners are read from the base branch, always.** The gate does so already. The notice and the skills do too
   (`--rev <base>`), so a PR that adds its author to a `maintainers` tuple can't silence its own notice, and a fork's
   head is only ever data. A family or integration that isn't on the base yet has no owners of its own: its paths
   belong to the enclosing level, as in the gate.
5. **Skills learn the runner from `gh api user --jq .login`**, or an explicit `--as <login>`, or by asking. When none
   of these works, the runner owns no package (question 5). They never guess from the git author, whose name and
   email don't map to a login.
6. **The choice is the status.** In `rc-audit`, a Critical or High finding in someone else's package stays `open`
   while its owner fixes it (the RC waits), becomes `fixed` when either the owner or the runner fixes it (`fixed_in`
   says which), and becomes `waived` with a `reason`. Only the new `owner` field is added to the record.
7. **The rule has one home: `CLAUDE.md`, Maintainers.** Everything else points to it: both skills, the workflow
   header, `docs/repo-maintainers.md`.
8. **No exemptions without a failure** (Evidence 6). Bots aren't exempt: Renovate touches no package today. Repo-wide
   changes aren't either: one comment that lists every package is exactly the warning wanted. When a bot or a
   mechanical class of PR starts producing noise, that is the evidence for an exemption.

## Design

### `scripts/owners.py`

```python
@dataclass(frozen=True)
class Group:
    package: Package               # as today: key, family (catalog: key None)
    key: str | None                # the integration this group is read from; None for repo maintainers
    direct: tuple[str, ...]
    enclosing: tuple[str, ...]     # the family's integration's maintainers, when the family has its own

def groups(path: str, rev: str) -> list[Group]           # [] for generated output
def owners(package: Package, rev: str) -> set[str]       # the gate's set, unchanged; raises Refused as today
def foreign(login: str, paths: list[str], rev: str) -> dict[Group, list[str]]   # Decision 3; repo maintainers' groups
                                                                                # dropped when login is one
def route(groups: Iterable[Group]) -> tuple[list[str], list[str]]  # integration:<key> labels and assignees
```

CLI: `scripts/owners.py [--rev REV] [--as LOGIN] [--json] PATH...`. Without `--as`, it prints one line per group:
package, direct handles, enclosing handles, paths. With `--as`, it prints only the foreign groups. `--json` gives the
same rows for the skills. `--issue` prints the `labels=` and `assignees=` lines `route-issue.yml` already consumes.
`route_issue.route` keeps its form parsing and builds labels through `owners.route`, so a routed form issue and a
routed finding carry the same label.

`check_maintainer_merge.py` keeps `Refused`, `Marks`, `marks`, `held_by`, `check_maintainers`, `check`, `main`, and
imports the rest. Behavior is unchanged: its tests pass unedited apart from imports.

### Skills

**`audit-code`** (`.claude/skills/audit-code/SKILL.md`):

- §1: resolve the runner (Decision 5) and the base rev the fixes would merge into (the target's base branch, else
  `origin/main`), and say both in the resolve line.
- §4, after verification: run `scripts/owners.py --rev <base> --as <runner> --json` on the files of every finding.
  Each findings table gets an Owner column (the package, then `@handles`).
- §5: under the verdict, before section 1, add **"In packages you don't maintain"**: the foreign findings grouped by
  owner group, with the handles. It is left out when there are none.
- §5's close: foreign findings go into no fix batch. Each owner group gets one drafted issue (title, the findings,
  `owners.py --issue` labels and assignees), filed only when the runner says to, as §6 already requires.
- One line pointing to `CLAUDE.md`, Maintainers, for the rule.

**`rc-audit`** (`.claude/skills/rc-audit/SKILL.md`):

- Runs `audit-code` with the runner and base it resolves itself (the RC's branch: `origin/main` or
  `origin/release/vX.Y.Z`).
- The frontmatter finding gains `owner: <package>` (`control4`, `zigbee2mqtt/tuya`, the catalog's `zigbee/tuya`), or
  `""` for the runner's own.
- It asks once per owner group, not once per finding: "`control4` (@handles): H2, H4. Owner fixes, I fix, or
  waive?" The runner can override the choice for any finding in the group. It records each finding's choice in the
  pass's prose:
  - **the owner fixes it:** the group's issue is filed, the finding stays `open`, and the RC waits;
  - **the runner fixes it:** no issue is filed for it, because the notice on the fix PR is the owner's warning. The
    fix PR names the owner, and the runner sets ⚠️ Untested fix when nobody can test the owner's device before the
    release (`docs/evidence.md`, Caveats);
  - **waived**, with a reason: still the repo maintainers' decision, as the Then section says.
- Foreign Mediums and Lows: one drafted issue per owner group, as in `audit-code`, holding the group's findings that
  the runner doesn't fix. A group whose findings are all fixed by the runner gets no issue.
- Unchanged by design: nothing reminds the runner that an RC is waiting on an owner's fix. `check_audit.py` reports
  it as `open`. Revisit if RCs stall on it.
- `--fix-pass`: a fix commit that touches a foreign package with no recorded choice is reported as a finding, High
  because it breaches the binding rule.

### `.github/workflows/owner-notice.yml` and `scripts/owner_notice.py`

```yaml
on:
  pull_request_target: # zizmor: ignore[dangerous-triggers] runs only base-branch code; the PR head is read as data
    types: [opened, synchronize, reopened, edited]   # edited: the base branch can change
permissions: {}
concurrency:
  group: owner-notice-${{ github.event.pull_request.number }}
  cancel-in-progress: false    # not a gate, so a queued run being bumped costs nothing; serializes comment writes
jobs:
  notice:
    permissions: { contents: read, pull-requests: write }
```

- Steps follow `protected-files.yml`: check out the base with `fetch-depth: 0`, `persist-credentials: false`; set up
  Python 3.14; `git fetch` the event's head SHA; pass every event value through `env:`, never `${{ }}` in `run:`.
- The script, `scripts/owner_notice.py HEAD "$HEAD_SHA" --author "$AUTHOR" --posted <file>`, diffs the merge base to
  the head (`--no-renames`, as the gate does), drops generated output (`owners.GENERATED`: it follows its inputs) and
  the repo maintainers' groups (CODEOWNERS already requests their review), and calls `owners.foreign(author, ...)`.
- `<file>` holds the bodies of the bot's earlier notices. The workflow writes it from
  `gh api .../issues/$NUMBER/comments --paginate`, `github-actions[bot]` only, as protected-files does. The script
  writes `action=none|create|update`, `comment=<id>` and a body file to `$GITHUB_OUTPUT`, and the workflow posts or
  `PATCH`es. All the logic is in the script and tested there; the shell only moves bytes.
- **One comment, updated.** The body opens with a marker that records who has already been mentioned:
  `<!-- owner-notice mentioned=a,b -->`. It lists each foreign group (package, `@direct`, then the enclosing
  maintainers, and its file count) and says plainly that nothing blocks the merge, linking `CLAUDE.md#maintainers`.
  Each push recomputes it: same body, `none`; changed body, `update`; nothing foreign any more, `update` to "now
  changes only packages its author maintains". A mention added by an edit is assumed not to notify anyone, so a
  handle not yet in `mentioned` also gets a short comment of its own that mentions only the new handles. That works
  whether or not edits notify, so no probe decides it (the probe stage 1 planned is dropped).
- **Partial owners:** only the groups the author doesn't directly own are listed, so the author of a PR across their
  own integration and someone else's family sees just the family.
- **Author:** `pull_request.user.login`. Known gap: a repo maintainer who pushes commits to a package's maintainer's
  PR doesn't trigger a notice. The maintainer is the author and is on the PR already.
- **Drafts:** noticed too, since the warning is wanted before the work goes further.
- actionlint and zizmor run on it through pre-commit, and `workflow-lint.yml` adds zizmor's online audits.

### Rule text

`CLAUDE.md`, Maintainers, a new paragraph after the merge rule, binding:

> Changing someone else's package: before you change a package or family whose maintainers don't include you, tell
> them; never wait on their approval (⚠️ Unmaintained covers an absent maintainer). The audit skills route such
> findings to the owner, and `owner-notice.yml` mentions them on any PR that changes their package.
> `scripts/owners.py` says who owns a path.

Pointers to it: both skills, the workflow header, the `owners.py` docstring, `docs/repo-maintainers.md` (one line:
the notice needs no setting, and it is what the owners see in place of a review request).

### Binding-rule surface, named

- `CLAUDE.md`: the paragraph above. This puts the Opus auditor on the PR audit.
- `docs/evidence.md`: no change. Untested fix and Unmaintained are used as they stand.
- `scripts/check_release.py`: no change.
- `scripts/check_audit.py`: no change (question 4). An `owner` key is ignored the way any extra key is; one test pins
  that.
- `docs/design.md`: no change. "Owner group" is a term internal to the script, not a glossary term.

### Tests (`tests/scripts/`)

- `test_owners.py`: the owner-set and parse tests move here from `test_check_maintainer_merge.py` and
  `test_route_issue.py`, unchanged, on the existing `repo` fixture. New: `groups` for a package path, a family with and
  without maintainers, a catalog shared by two stacks, a path in a family not yet on the base, generated output, and a
  shared path; `foreign` for a repo maintainer, an integration maintainer in their own family, a family maintainer on
  a shared catalog, and a partial owner; owners read at the base, not the head (a head that adds the author to
  `maintainers` still gets a notice); the CLI's text, `--json` and `--issue` rows. The existing parse-against-registry
  check stays as it is.
- `test_owner_notice.py`: the first push gives `create`; a push that changes nothing gives `none`; a new foreign group
  gives `update` and a comment mentioning only the new handles; a push that drops the
  last foreign file gives `update` to the cleared text; only the bot's own markers count; generated output and shared
  files are never listed; a fork's head is only ever passed to `git show`.
- `test_check_maintainer_merge.py` and `test_route_issue.py` keep their behavior tests, with imports changed.

## Stages

1. **Lookup.** `scripts/owners.py`, with the gate and `route_issue.py` moved onto it (a refactor: the gate's tests
   pass on behavior unchanged), plus `test_owners.py`.
2. In parallel, on disjoint files:
   - the notice: `owner_notice.py`, `owner-notice.yml`, `test_owner_notice.py`;
   - the skills and the rules: both `SKILL.md` files, `CLAUDE.md`, `docs/repo-maintainers.md`.
3. An audit of the diff against the intent checks below, and fixes.

Each stage ends with `.venv/bin/pytest` and `pre-commit run --all-files` green. No device call changes, so no hardware
run is needed. `pull_request_target` runs the base branch's workflow, so the notice first acts on the first PR opened
after this merges. Nothing is gated on that PR: it is watched, and a wrong comment is a bug to fix (Evidence 4).

## Sequencing

#447 changes `check_maintainer_merge.py`, `route_issue.py`, `gen_codeowners.py` and their tests, which are exactly
the files stage 1 moves, and review fixes are still landing on it. So this plan's PR is based on `main` and carries
only this file. Implementation starts on `main` once #447 has merged, as one PR, or as stage 1 and then stage 2,
which share nothing but `owners.py`.

## Intent checks (what the audit verifies)

- One implementation: no owner computation or `maintainers=` parsing outside `scripts/owners.py` (`rg` for
  `parse_family`, `literal_eval`, `FAMILY_PATHS` readers).
- The gate decides every case of its tests exactly as before.
- A repo maintainer's PR to `control4`, an integration maintainer's PR to their own family, and a family maintainer's
  PR to a shared catalog each get one notice, mentioning the right handles. A package maintainer's PR to their own
  package gets none.
- Owners come from the base. No step runs the PR's code. Every event value reaches `run:` through `env:`.
- Three pushes to one PR leave one notice comment, plus a mention-only comment for each new handle.
- Nothing in the three controls can fail a merge or an RC tag that would pass today, beyond the RC waiting on a
  finding its runner chose to leave `open`.
- `rc-audit` asks one question per owner group, and a finding the runner chooses to fix gets no issue.
- The rule's text exists once, in `CLAUDE.md`, and every other mention links it.
