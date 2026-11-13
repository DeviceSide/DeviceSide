"""scripts/check_protected.py: README outside its generated blocks is the maintainers'; a manifest change is flagged."""

import pytest

from scripts import check_protected as cp

MAINTAINERS = frozenset({"jasonmx"})
README = """# DeviceSide

Intro.

<!-- features:start -->
old table
<!-- features:end -->

<!-- devices:start -->
old cards
<!-- devices:end -->
"""


@pytest.fixture
def pr(repo, monkeypatch):
    """A repo with README and manifest on main, and a `pr` branch off it; returns the repo."""
    monkeypatch.chdir(repo.path)
    repo.commit(cp.README, README)
    repo.commit(cp.MANIFEST, '{"after_dependencies": ["mqtt"]}\n')
    repo.git("branch", "pr")
    return repo


def on_pr(repo, file, text):
    repo.git("checkout", "-q", "pr")
    repo.commit(file, text)
    repo.git("checkout", "-q", "main")


def test_a_contributor_may_regenerate_the_blocks(pr):
    on_pr(pr, cp.README, README.replace("old table", "new table").replace("old cards", "new cards"))
    assert cp.check("main", "pr", "alice", MAINTAINERS) == (True, False)


def test_a_contributor_editing_outside_the_blocks_fails(pr):
    on_pr(pr, cp.README, README.replace("Intro.", "My intro."))
    assert cp.check("main", "pr", "alice", MAINTAINERS) == (False, False)


def test_removing_a_marker_counts_as_an_edit_outside_the_blocks(pr):
    on_pr(pr, cp.README, README.replace("<!-- devices:end -->\n", ""))
    assert cp.check("main", "pr", "alice", MAINTAINERS)[0] is False


def test_a_repo_maintainer_may_edit_both(pr):
    on_pr(pr, cp.README, "rewritten\n")
    on_pr(pr, cp.MANIFEST, "{}\n")
    assert cp.check("main", "pr", "jasonmx", MAINTAINERS) == (True, False)


def test_a_contributor_changing_the_manifest_is_flagged_not_failed(pr):
    on_pr(pr, cp.MANIFEST, '{"after_dependencies": ["mqtt", "zwave_js"]}\n')
    assert cp.check("main", "pr", "alice", MAINTAINERS) == (True, True)


def test_renovate_changing_the_manifest_is_not_flagged(pr):
    on_pr(pr, cp.MANIFEST, '{"requirements": ["x==2"]}\n')
    assert cp.check("main", "pr", "renovate[bot]", MAINTAINERS) == (True, False)


def test_main_moving_on_isnt_blamed_on_the_pr(pr):
    pr.commit(cp.README, README.replace("Intro.", "Newer intro."))
    pr.commit(cp.MANIFEST, "{}\n")
    assert cp.check("main", "pr", "alice", MAINTAINERS) == (True, False)


def test_main_writes_the_output_and_fails_on_the_readme(pr, tmp_path, monkeypatch, capsys):
    on_pr(pr, cp.README, "rewritten\n")
    on_pr(pr, cp.MANIFEST, "{}\n")
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert cp.main(["main", "pr", "--author", "alice"]) == 1
    assert output.read_text() == "manifest=true\n"
    out = capsys.readouterr().out
    assert "::warning file=custom_components/deviceside/manifest.json" in out
    assert "::error file=README.md" in out
    monkeypatch.delenv("GITHUB_OUTPUT")
    assert cp.main(["main", "pr", "--author", "jasonmx"]) == 0


def test_the_maintainers_come_from_gen_codeowners():
    from scripts import gen_codeowners

    assert cp.repo_maintainers() == frozenset(gen_codeowners.REPO_MAINTAINERS)


def test_no_maintainers_list_stops(tmp_path):
    (tmp_path / "x.py").write_text("OTHER = 1\n")
    with pytest.raises(SystemExit, match="no REPO_MAINTAINERS"):
        cp.repo_maintainers(tmp_path / "x.py")


def test_a_file_missing_at_a_revision_reads_as_empty(pr):
    assert cp.show("main", "nope.md") == ""
