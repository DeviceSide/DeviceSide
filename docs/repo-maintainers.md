# Repo maintainers

What only a [repo maintainer](design.md#glossary) can do: the repo settings the workflows rely on, and the steps that
come with merging. Who merges what is in [CLAUDE.md](../CLAUDE.md#maintainers); cutting releases is in the `release`
skill.

## When a new integration merges

Invite each handle in its `IntegrationInfo.maintainers` to the **Triage** role (Settings, Collaborators and teams).
`route-issue.yml` can only assign bug reports to someone with access to the repo. Triage doesn't let them push or
merge; `/merge` needs no role.

## Appointing a family maintainer

Add the handle to the family's `Family.maintainers` (`integrations/<x>/families/<family>/__init__.py`), run
`scripts/gen_codeowners.py`, and merge the PR yourself: `/merge` refuses any change to a `maintainers` tuple. Then
invite them to Triage, as for an integration's maintainers.

## Settings the workflows rely on

- **Ruleset on `main` and `release/*`:** changes go through a pull request, with no required approvals. The required
  checks (`lint`, `secrets-history`, `pytest`, `validate-hacs`, `validate`) must pass, and the branch must be up to
  date. Force pushes are blocked. There are no bypass actors. Add `pytest-without-family-tests` (`tests.yml`) to the
  required checks once it has run on `main`: it runs the tests with every family's and the catalog's left out, so a
  family maintainer's test code can't silence the integration's, and it guards a `/merge` only once it is required.
- **Ruleset on tags:** only a deploy key can create, move or delete a tag. The cut workflows'
  `RELEASE_TAG_DEPLOY_KEY` is the only one, so release tags come from those workflows alone.
- **Actions allow-list (org):** selected actions, pinned by full SHA. A new action needs an entry there before a
  workflow can use it.

## `/merge`

`.github/workflows/maintainer-merge.yml` merges as a GitHub App; its header says why.

- **The App:** owned by the org and installed on this repo only. Repository permissions: Contents read and write, Pull
  requests read. Webhook off.
- **The `maintainer-merge` environment:** holds the variable `MAINTAINER_MERGE_APP_ID` and the secret
  `MAINTAINER_MERGE_APP_KEY` (the App's private key). Keep its deployment branches limited to `main`.
  `issue_comment` runs on `main`, so the merge job still gets the key, but a workflow pushed on any other branch can't
  read it.
- **Switching it off:** disable the "Maintainer merge" workflow in the Actions tab, and cancel any run already in
  progress. No new `/merge` runs, and repo maintainers merge everything until it's re-enabled.
- **If the key leaks:** generate a new key on the App's page, replace the secret, then delete the old key.
