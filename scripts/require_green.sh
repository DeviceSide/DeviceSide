#!/usr/bin/env bash
# Exit 0 only when every required workflow ran on <sha> for a push and every workflow run attached to <sha>
# concluded success: the rule a release gate needs before tagging. The cut-* release workflows are left out, so a
# gate never waits on itself or on an earlier refused cut. Of several runs of one workflow and event (a nightly
# rerun), the latest counts. Every page of runs is read, so scheduled runs can't push the required ones out of view.
# Needs GH_TOKEN and GITHUB_REPOSITORY, as a workflow step has them.
#
# Usage: scripts/require_green.sh <sha>
set -euo pipefail

# Workflow names, as each file's `name:` gives them. A renamed workflow fails the gate until it is renamed here.
required=(Tests Lint)

sha=${1:?usage: scripts/require_green.sh <sha>}
runs=$(gh api --paginate "repos/$GITHUB_REPOSITORY/actions/runs?head_sha=$sha&per_page=100" --jq '.workflow_runs[]' \
  | jq -rs '
    [.[] | select(.path | startswith(".github/workflows/cut-") | not)]
    | group_by([.path, .event]) | map(max_by(.created_at))[]
    | "\(.conclusion // .status)\t\(.name) (\(.event))"')

if [ -z "$runs" ]; then
  echo "::error::No workflow run on $sha; push it and let CI finish first."
  exit 1
fi
echo "$runs"
for wf in "${required[@]}"; do
  if ! printf '%s\n' "$runs" | cut -f2 | grep -qxF -- "$wf (push)"; then
    echo "::error::$wf did not run on $sha for a push."
    exit 1
  fi
done
if not_green=$(printf '%s\n' "$runs" | grep -v '^success'); then
  echo "::error::Not every run on $sha concluded success:"
  echo "$not_green"
  exit 1
fi
