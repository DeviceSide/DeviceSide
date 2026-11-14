# Repo maintainers

What only a repo maintainer can do: the repo settings the workflows rely on, and the steps that come with merging. A
repo maintainer is a handle in `REPO_MAINTAINERS` (`scripts/gen_codeowners.py`), with admin on the repo. Who merges
what is in [CLAUDE.md](../CLAUDE.md#maintainers); cutting releases is in the `release` skill.

## When a new integration merges

Invite each handle in its `IntegrationInfo.maintainers` to the **Triage** role (Settings, Collaborators and teams).
`route-issue.yml` can only assign bug reports to someone with access to the repo. Triage doesn't let them push or
merge; `/merge` needs no role.

## Settings the workflows rely on

- **Ruleset on `main` and `release/*`:** changes go through a pull request, with no required approvals. The required
  checks (`lint`, `secrets-history`, `pytest`, `validate-hacs`, `validate`) must pass, and the branch must be up to
  date. Force pushes are blocked. There are no bypass actors.
- **Ruleset on tags:** only the deploy key can create, move or delete a tag, so release tags come from the cut
  workflows alone.
- **Actions allow-list (org):** selected actions, pinned by full SHA. A new action needs an entry there before a
  workflow can use it.

## `/merge`

`.github/workflows/maintainer-merge.yml` merges as a GitHub App; its header says why.

- **The App:** owned by the org and installed on this repo only. Repository permissions: Contents read and write, Pull
  requests read. Webhook off.
- **The `maintainer-merge` environment:** holds the variable `MAINTAINER_MERGE_APP_ID` and the secret
  `MAINTAINER_MERGE_APP_KEY` (the App's private key). Keep its deployment branches limited to `main`.
  `issue_comment` runs there, so the merge job still gets the key, but a workflow pushed on any other branch can't
  read it.
- **Switching it off:** disable the "Maintainer merge" workflow in the Actions tab. Every `/merge` stops at once, and
  repo maintainers merge everything until it's re-enabled.
- **If the key leaks:** generate a new key on the App's page, replace the secret, then delete the old key.
