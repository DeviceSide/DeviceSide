"""scripts/owner_notice.py: one comment naming the code a PR's author doesn't maintain, kept current, never blocking."""

import json

import pytest

from scripts import owner_notice as on
from scripts import owners as ow

PKG = "custom_components/deviceside/integrations/acme/"
TUYA = PKG + "families/tuya/"
ACME = ow.Group(ow.Package("acme"), "acme", ("alice",))
FAMILY = ow.Group(ow.Package("acme", "tuya"), "acme", ("tina",), ("alice",))
SHARED = ow.Group(None, None, ("root",))


def posted(*comments):
    return [(index, body) for index, body in comments]


def test_the_first_push_creates_the_notice_and_mentions_everyone_but_the_author():
    result = on.plan({ACME: [PKG + "a.py"], FAMILY: [TUYA + "b.py", TUYA + "c.py"]}, "root", [])
    assert result == on.Plan(
        "create",
        None,
        "<!-- owner-notice mentioned=alice,tina -->\nThis pull request changes code that its author, `root`, doesn't "
        "maintain. Its maintainers may want to review it; nothing here blocks the merge (CLAUDE.md, Maintainers).\n\n"
        "- `acme`: @alice (1 file)\n- `acme`'s `tuya` family: @tina, and `acme`'s @alice (2 files)",
        None,
    )


def test_an_integration_maintainer_in_their_own_family_mentions_the_family_alone():
    assert on.plan({FAMILY: [TUYA + "b.py"]}, "alice", []).body.startswith("<!-- owner-notice mentioned=tina -->")


def test_nothing_foreign_posts_nothing():
    assert on.plan({}, "alice", []) == on.Plan("none", None, "", None)


def test_shared_code_is_left_to_codeowners():
    assert on.plan({SHARED: ["core/x.py"]}, "alice", []) == on.Plan("none", None, "", None)


def test_a_push_that_changes_nothing_leaves_the_notice():
    first = on.plan({ACME: [PKG + "a.py"]}, "root", []).body
    assert on.plan({ACME: [PKG + "a.py"]}, "root", posted((7, first))) == on.Plan("none", 7, first, None)


def test_more_files_in_the_same_groups_update_it_without_a_mention():
    first = on.plan({ACME: [PKG + "a.py"]}, "root", []).body
    result = on.plan({ACME: [PKG + "a.py", PKG + "b.py"]}, "root", posted((7, first)))
    assert (result.notice, result.comment, result.mention) == ("update", 7, None)
    assert "(2 files)" in result.body


def test_a_new_group_updates_it_and_mentions_only_the_new_handles():
    first = on.plan({ACME: [PKG + "a.py"]}, "root", []).body
    result = on.plan({ACME: [PKG + "a.py"], FAMILY: [TUYA + "b.py"]}, "root", posted((7, first)))
    assert (result.notice, result.comment) == ("update", 7)
    assert result.body.startswith("<!-- owner-notice mentioned=alice,tina -->")
    assert result.mention == (
        "<!-- owner-notice:mention -->\n@tina: this pull request now also changes code you maintain; the owner notice "
        "above lists it."
    )


def test_a_handle_mentioned_once_is_not_mentioned_again():
    both = on.plan({ACME: [PKG + "a.py"], FAMILY: [TUYA + "b.py"]}, "root", []).body
    narrowed = on.plan({ACME: [PKG + "a.py"]}, "root", posted((7, both)))
    assert narrowed.body.startswith("<!-- owner-notice mentioned=alice,tina -->")
    again = on.plan({ACME: [PKG + "a.py"], FAMILY: [TUYA + "b.py"]}, "root", posted((7, narrowed.body)))
    assert (again.notice, again.mention) == ("update", None)


def test_dropping_the_last_foreign_file_clears_the_notice():
    first = on.plan({ACME: [PKG + "a.py"]}, "root", []).body
    result = on.plan({}, "root", posted((7, first)))
    assert result == on.Plan(
        "update",
        7,
        "<!-- owner-notice mentioned=alice -->\nThis pull request now changes only code its author, `root`, maintains.",
        None,
    )
    assert on.plan({}, "root", posted((7, result.body))).notice == "none"


def test_the_oldest_notice_is_the_one_kept_and_mention_comments_are_not_notices():
    first = on.plan({ACME: [PKG + "a.py"]}, "root", []).body
    comments = posted((9, first.replace("alice", "zed")), (7, first), (8, on.MENTION + "\n@zed: x"))
    assert on.plan({ACME: [PKG + "a.py"]}, "root", comments).comment == 7


def test_only_the_bots_comments_count():
    marker = "<!-- owner-notice mentioned=alice -->\nx"
    lines = [json.dumps([1, "mallory", marker]), json.dumps([2, on.BOT, "hello"]), "", json.dumps([3, on.BOT, marker])]
    assert on.earlier("\n".join(lines)) == [(2, "hello"), (3, marker)]


@pytest.fixture
def pr(repo, monkeypatch):
    """`main` with `acme` (alice) and its `tuya` family (tina), and a `pr` branch off it."""
    monkeypatch.chdir(repo.path)
    repo.commit(
        ow.INIT.format(key="acme"), 'INTEGRATION = IntegrationInfo(key="acme", title="A", maintainers=("alice",))\n'
    )
    repo.commit(TUYA + "__init__.py", 'FAMILY = Family(key="tuya", maintainers=("tina",))\n')
    repo.commit(PKG + "bridge.py", "x = 1\n")
    repo.git("checkout", "-q", "-b", "pr")
    return repo


def run(tmp_path, author, comments=()):
    posted_file = tmp_path / "posted.jsonl"
    posted_file.write_text("".join(json.dumps(comment) + "\n" for comment in comments))
    output = tmp_path / "output"
    output.write_text("")
    args = ["main", "pr", "--author", author, "--posted", str(posted_file), "--out", str(tmp_path)]
    assert on.main(args) == 0
    return output.read_text(), (tmp_path / "notice.md").read_text(), (tmp_path / "mention.md").read_text()


def test_main_reads_owners_at_the_base_and_skips_generated_output(pr, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    # The PR names its author a maintainer and regenerates CODEOWNERS: the base's owners still apply.
    pr.commit(ow.INIT.format(key="acme"), 'INTEGRATION = IntegrationInfo(key="acme", title="A", maintainers=("mo",))\n')
    pr.commit(TUYA + "rules.py", "x = 2\n")
    pr.commit(".github/CODEOWNERS", "* @mo\n")
    outputs, notice, mention = run(tmp_path, "mo")
    assert outputs == "notice=create\ncomment=\nmention=false\n"
    assert notice.startswith("<!-- owner-notice mentioned=alice,tina -->")
    assert "- `acme`: @alice (1 file)\n- `acme`'s `tuya` family: @tina, and `acme`'s @alice (1 file)" in notice
    assert mention == ""


def test_main_says_nothing_to_an_owner(pr, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    pr.commit(PKG + "bridge.py", "x = 2\n")
    assert run(tmp_path, "alice") == ("notice=none\ncomment=\nmention=false\n", "", "")


def test_main_updates_the_bots_notice(pr, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    pr.commit(PKG + "bridge.py", "x = 2\n")
    first = on.plan({ACME: [PKG + "bridge.py"]}, "mo", []).body
    pr.commit(TUYA + "rules.py", "x = 2\n")
    outputs, notice, mention = run(tmp_path, "mo", [[41, on.BOT, first]])
    assert outputs == "notice=update\ncomment=41\nmention=true\n"
    assert mention.startswith(on.MENTION + "\n@tina:")
