"""scripts/pr_gate.py: which outside pull requests pass, which are exempt, and what a close or reopen sends."""

import json
import subprocess

import pytest

from scripts import pr_gate
from scripts.pr_gate import Issue, PullRequest

REPO = "owner/Repo"


def pr(**overrides) -> PullRequest:
    fields = {
        "number": 400,
        "author": "alice",
        "author_type": "User",
        "association": "CONTRIBUTOR",
        "files": ["custom_components/deviceside/integrations/x/__init__.py"],
        "body": "",
    }
    return PullRequest(**{**fields, **overrides})


ASSIGNED = {7: Issue(False, frozenset({"alice"}))}


@pytest.mark.parametrize(
    ("overrides", "issues", "override", "outcome", "reason"),
    [
        ({"association": "OWNER"}, {}, False, "exempt", "author association OWNER"),
        ({"association": "MEMBER"}, {}, False, "exempt", "author association MEMBER"),
        ({"association": "COLLABORATOR"}, {}, False, "exempt", "author association COLLABORATOR"),
        ({"author_type": "Bot", "association": "NONE"}, {}, False, "exempt", "bot author"),
        ({}, {}, True, "exempt", "reopened by a maintainer"),
        ({"files": ["README.md", "docs/guide.md"]}, {}, False, "exempt", "prose-only change"),
        ({"files": ["docs/design.md"]}, {}, False, "close", "no assigned issue referenced"),
        ({"files": ["CLAUDE.md"]}, {}, False, "close", "no assigned issue referenced"),
        ({"files": ["docs/test-records/shelly/a.md"]}, {}, False, "close", "no assigned issue referenced"),
        ({"files": ["docs/audits/v0.1.0rc1.md"]}, {}, False, "close", "no assigned issue referenced"),
        ({"files": [".github/pull_request_template.md"]}, {}, False, "close", "no assigned issue referenced"),
        ({"files": ["README.md", "scripts/x.py"]}, {}, False, "close", "no assigned issue referenced"),
        ({"files": ["docs/devices.yaml"]}, {}, False, "close", "no assigned issue referenced"),
        ({"files": []}, {}, False, "close", "no assigned issue referenced"),
        ({}, {}, False, "close", "no assigned issue referenced"),
        ({}, ASSIGNED, False, "pass", "author is assigned to #7"),
        ({}, {7: Issue(False, frozenset())}, False, "close", "no assigned issue referenced"),
        ({}, {7: Issue(False, frozenset({"bob"}))}, False, "close", "no assigned issue referenced"),
        ({}, {7: Issue(True, frozenset({"alice"}))}, False, "close", "no assigned issue referenced"),
        (
            {},
            {3: Issue(False, frozenset({"bob"})), 7: Issue(False, frozenset({"bob", "alice"}))},
            False,
            "pass",
            "author is assigned to #7",
        ),
    ],
)
def test_decide(overrides, issues, override, outcome, reason):
    assert pr_gate.decide(pr(**overrides), issues, override) == pr_gate.Verdict(outcome, reason)


@pytest.mark.parametrize(
    ("number", "manual", "outcome"), [(351, False, "exempt"), (351, True, "close"), (352, False, "close")]
)
def test_prs_opened_before_the_gate_are_held_until_a_manual_run(number, manual, outcome):
    assert pr_gate.decide(pr(number=number), {}, manual=manual).outcome == outcome


def test_a_renamed_binding_file_is_gated():
    """A rename lists its old path too, so moving docs/design.md to docs/notes.md isn't prose-only."""
    assert not pr_gate.prose_only(["docs/notes.md", "docs/design.md"])
    assert pr_gate.prose_only(["docs/notes.md", "docs/old.md"])


@pytest.mark.parametrize(
    ("body", "closing", "expected"),
    [
        ("", [], []),
        ("Part of #12", [], [12]),
        ("Closes #12, see #3 and #12", [12], [12, 3]),
        ("See https://github.com/owner/repo/issues/9 and https://github.com/Owner/Repo/pull/10", [], [9, 10]),
        ("Elsewhere: https://github.com/other/repo/issues/9 and other/repo#8", [], []),
        ("No ref in abc#5, &#39; or a heading ##5", [], []),
        (None, [4], [4]),
    ],
)
def test_referenced(body, closing, expected):
    assert pr_gate.referenced(body, closing, REPO) == expected


class FakeGh:
    """Answers `gh` calls from a table keyed on their arguments, and records the writes."""

    def __init__(self, pull, files, closing=(), issues=None, events=(), permission=None):
        self.writes = []
        self.reads = {
            f"api repos/{REPO}/pulls/400": pull,
            f"api --paginate --slurp repos/{REPO}/pulls/400/files": [files],
            f"api --paginate --slurp repos/{REPO}/issues/400/events": [list(events)],
            "graphql": {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "closingIssuesReferences": {
                                "nodes": [{"number": n, "repository": {"nameWithOwner": repo}} for n, repo in closing]
                            }
                        }
                    }
                }
            },
        }
        for number, issue in (issues or {}).items():
            self.reads[f"api repos/{REPO}/issues/{number}"] = issue
        if permission:
            self.reads[f"api repos/{REPO}/collaborators/{permission[0]}/permission"] = {"permission": permission[1]}

    def __call__(self, *args):
        if args[0] == "pr":
            self.writes.append(args)
            return ""
        key = "graphql" if args[:2] == ("api", "graphql") else " ".join(args)
        if key not in self.reads:
            raise subprocess.CalledProcessError(1, ["gh", *args])
        return json.dumps(self.reads[key])


def pull(body="", state="open", merged=False, login="alice", association="CONTRIBUTOR"):
    user = {"login": login, "type": "User"}
    return {"user": user, "author_association": association, "body": body, "state": state, "merged": merged}


CODE = [{"filename": "scripts/x.py"}]


@pytest.fixture
def run(monkeypatch, capsys):
    def run(fake, *extra):
        monkeypatch.setattr(pr_gate, "gh", fake)
        assert pr_gate.main(["--pr", "400", "--repo", REPO, *extra]) == 0
        return capsys.readouterr().out

    return run


def test_unassigned_pr_is_commented_and_closed(run):
    fake = FakeGh(pull("Adds Control4"), CODE)
    out = run(fake)
    assert "close (no assigned issue referenced)" in out
    (comment, close) = fake.writes
    assert comment[:4] == ("pr", "comment", "400", "--repo")
    body = comment[-1]
    assert f"https://github.com/{REPO}/issues/new?template=propose_device_or_integration.yml" in body
    assert "reopens automatically" in body
    assert "—" not in body  # public text: no em-dashes
    assert close == ("pr", "close", "400", "--repo", REPO)


def test_dry_run_writes_nothing(run):
    fake = FakeGh(pull(), CODE)
    assert "close" in run(fake, "--dry-run")
    assert fake.writes == []


def test_closing_reference_to_an_assigned_issue_passes(run):
    issue = {"assignees": [{"login": "alice"}]}
    fake = FakeGh(pull(), CODE, closing=[(7, REPO), (8, "other/repo")], issues={7: issue})
    assert "pass (author is assigned to #7)" in run(fake)
    assert fake.writes == []


def test_a_referenced_pr_and_a_missing_issue_dont_count(run):
    as_pr = {"assignees": [{"login": "alice"}], "pull_request": {}}
    fake = FakeGh(pull("Part of #5, see #6"), CODE, issues={5: as_pr})
    assert "close" in run(fake)


def test_renames_count_their_old_path(run):
    fake = FakeGh(pull(), [{"filename": "docs/notes.md", "previous_filename": "docs/design.md"}])
    assert "close" in run(fake, "--dry-run")


def test_merged_pr_is_left_alone(run):
    fake = FakeGh(pull(state="closed", merged=True), CODE)
    assert "merged, nothing to do" in run(fake)
    assert fake.writes == []


def test_closed_failing_pr_is_not_commented_again(run):
    fake = FakeGh(pull(state="closed"), CODE)
    run(fake)
    assert fake.writes == []


@pytest.mark.parametrize(("closer", "reopens"), [("github-actions[bot]", True), ("owner", False)])
def test_a_pr_the_gate_closed_reopens_once_it_passes(run, closer, reopens):
    events = [{"event": "closed", "actor": {"login": "github-actions[bot]"}}, {"event": "reopened"}]
    events.append({"event": "closed", "actor": {"login": closer}})
    issue = {"assignees": [{"login": "alice"}]}
    fake = FakeGh(pull("Closes #7", state="closed"), CODE, issues={7: issue}, events=events)
    run(fake)
    assert fake.writes == ([("pr", "reopen", "400", "--repo", REPO)] if reopens else [])


@pytest.mark.parametrize(
    ("sender", "permission", "closes"),
    [
        ("owner", ("owner", "admin"), False),
        ("owner", ("owner", "read"), True),
        ("eve", None, True),
        ("alice", None, True),
    ],
)
def test_a_maintainer_reopen_is_an_override(run, sender, permission, closes):
    fake = FakeGh(pull(), CODE, permission=permission)
    run(fake, "--sender", sender)
    assert bool(fake.writes) == closes


def test_issue_lookups_are_capped(run, monkeypatch):
    body = " ".join(f"#{n}" for n in range(1, 50))
    fake = FakeGh(pull(body), CODE, issues={30: {"assignees": [{"login": "alice"}]}})
    assert "close" in run(fake, "--dry-run")


def test_repo_is_required(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(SystemExit):
        pr_gate.main(["--pr", "1"])


def test_gh_runs_the_cli(monkeypatch):
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert pr_gate.gh("api", "x") == "ok"
    assert seen == [["gh", "api", "x"]]
