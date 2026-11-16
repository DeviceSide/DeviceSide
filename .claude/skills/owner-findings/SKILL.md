---
name: owner-findings
description: Route an audit's findings to the maintainers of the code they're in, amending the report and drafting one issue per owner group with a Critical or High. Use after any audit-code report in this repo, including the one rc-audit writes, or when asked whose code an audit's findings are in.
---

Arguments: optionally the report (a path such as `docs/audits/<rc>.md`, else the audit report just produced in this
session), `--as <login>`, `--base <rev>`. The rule for when to run it: `CLAUDE.md`, Maintainers ("Changing someone
else's code"). This skill reads the report and amends it; it never edits code.

1. **Resolve** the runner: `--as`, else `gh api user --jq .login`, else ask once; with no answer, the runner owns
   nothing, and say so. Then the base the fixes would merge into: `--base`, else the audited target's base branch
   (a PR's `gh pr view <n> --json baseRefName`), else `origin/main`; for an RC, the branch it is cut from
   (`origin/main` or `origin/release/vX.Y.Z`). `git fetch origin <branch>` first. Say both in one line.
2. **Look up owners:** collect every finding's files from its `file:line` references and run once
   `.venv/bin/python scripts/owners.py --rev <base> --as <login> --json <paths>` (no `--as` when the runner owns
   nothing). Each row is an owner group the runner isn't a direct maintainer of: `owner` (the slug, `""` for shared
   code), `package`, `integration`, `direct` and `enclosing` handles, and `paths`. Rows with the same `owner` are one
   owner group (a catalog file gives one row per integration sharing it): merge their handles. A finding is in someone
   else's code when any of its files is in a group's `paths`; one in several groups is asked about and drafted once,
   under the first. A finding with no `file:line` is the runner's to place. Generated output (README, the
   compatibility page, CODEOWNERS) gets no row: a finding there belongs to its inputs' owners.
3. **Amend the report:**
   - an Owner column in every findings table: each group's `package` and `@` its `direct` handles, blank for the
     runner's own code;
   - right after the verdict, a section **In code you don't maintain**: one entry per owner group, its `package`, its
     handles (`direct`, then `enclosing`, the integration's), and its finding ids. Leave it out when there are none;
   - the fix batches drop those findings; each owner group with a Critical or High gets a drafted issue instead.
     Mediums and Lows stay in the report alone: no issue, no fix, until one bites someone.
4. **Draft one issue per owner group with a Critical or High:** a title naming the `package` and the audit; each
   Critical and High with its `file:line`,
   severity and the fix the audit proposed; the labels and assignees from
   `.venv/bin/python scripts/owners.py --rev <base> [--as <login>] --issue <that group's paths>` (`--as` left out as
   in step 2). Show the drafts. File
   them only when the runner says to, first creating a missing `integration:<key>` label as `route-issue.yml` does:
   `gh label create <label> --color c5def5 --description "Routed to the integration's maintainers" --force`.
5. **In an RC** (the report is `docs/audits/<rc>.md`): for each owner group with a Critical or High whose choice no
   earlier pass's prose records, ask the runner once, naming the `package`, the handles and the finding ids. The choices, which the runner may vary for any one
   finding; never pick one yourself:
   - **the owner fixes it:** that choice is the runner's word to file its issue (step 4); the status stays `open`,
     and the RC waits;
   - **the runner fixes it:** no issue for it; the fix PR names the owner; the runner decides on ⚠️ Untested fix
     (`docs/evidence.md`) when nobody can test the device before the release;
   - **waived:** `status: waived` with the runner's reason, in their words.

   Write `owner: <slug>` (the row's `owner`) on each such finding in the frontmatter, and each finding's choice in the
   current pass's prose. A group whose every Critical and High the runner fixes or waives gets no issue. A shared-code
   group (`owner` is `""`) is the repo maintainers': write no `owner:` and ask no owner question for it, as
   `rc-audit`'s own fix-or-waive decision covers it.
6. **Report** what changed: the owner groups, the choices, and the issues filed or still drafted.
