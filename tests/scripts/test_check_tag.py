"""scripts/check_tag.py: which tag may be cut from which branch, and the commit it goes on."""

import json

import pytest

from scripts import check_tag


def ship(repo, version: str) -> str:
    """Commit manifest.json with this version, as the commit a cut-* workflow tags has it."""
    return repo.commit(str(check_tag.MANIFEST), json.dumps({"domain": "deviceside", "version": version}))


@pytest.fixture
def released(repo):
    ship(repo, "0.0.1")
    repo.git("tag", "v0.0.1")
    repo.git("tag", "v0.0.10rc1")  # an RC never counts as the latest release
    repo.commit()
    return repo


@pytest.mark.parametrize(
    ("tag", "branch"),
    [
        ("v0.0.2rc1", "main"),
        ("v0.1.0rc3", "main"),
        ("v0.0.2rc1", "release/v0.0.2"),
    ],
)
def test_rc_allowed(released, tag, branch):
    ship(released, tag[1:].split("rc")[0])
    assert check_tag.errors(released.path, tag, branch) == []


def test_rc_goes_on_the_head(released):
    head = ship(released, "0.0.2")
    assert check_tag.target(released.path, "v0.0.2rc1") == (head, [])


def test_release_goes_on_its_latest_rc(released):
    rc10 = ship(released, "0.0.2")
    released.git("tag", "v0.0.2rc9", "HEAD~1")  # rc10 is the latest by number, not by string
    released.git("tag", "v0.0.2rc10")
    released.git("tag", "v0.0.3rc1")
    ship(released, "0.0.3")  # main moved on during the soak
    assert check_tag.errors(released.path, "v0.0.2", "main") == []
    assert check_tag.target(released.path, "v0.0.2") == (rc10, [])


@pytest.mark.parametrize(
    ("tag", "branch", "error"),
    [
        ("v0.0.2rc1", "release/v0.0.3", "v0.0.2rc1 must be cut from main or release/v0.0.2, not release/v0.0.3"),
        ("v0.0.2rc1", "wt/topic", "must be cut from main or release/v0.0.2"),
        ("v0.0.1rc2", "main", "v0.0.1rc2 is not above the latest release, v0.0.1"),
        ("v0.0.2", "release/v0.0.2", "a release is dispatched from main only, not release/v0.0.2"),
        ("v0.0.2", "main", "v0.0.2 has no RC to release; cut v0.0.2rc1 first"),
        ("v0.0.1", "main", "v0.0.1 is not above the latest release, v0.0.1"),
        ("v0.0.2-test", "main", "matches neither"),
        ("v0.0.10rc1", "release/v0.0.10", "v0.0.10rc1 already exists"),
    ],
)
def test_refused(released, tag, branch, error):
    ship(released, "0.0.2")
    assert any(error in problem for problem in check_tag.errors(released.path, tag, branch))


def test_first_rc_needs_no_earlier_tag(repo):
    ship(repo, "0.0.1")
    assert check_tag.errors(repo.path, "v0.0.1rc1", "main") == []


@pytest.mark.parametrize(
    ("manifest", "error"),
    [
        ('{"version": "0.0.1"}', "manifest.json has version '0.0.1', not '0.1.0'"),
        ('{"version": "0.1.0rc1"}', "has version '0.1.0rc1', not '0.1.0'"),
        ("{", "manifest.json can't be read"),
        (None, "manifest.json can't be read"),
    ],
)
def test_rc_manifest_version_must_be_the_tags(repo, manifest, error):
    if manifest is None:
        repo.commit()
    else:
        repo.commit(str(check_tag.MANIFEST), manifest)
    assert [problem for problem in check_tag.errors(repo.path, "v0.1.0rc1", "main") if error in problem]


def test_release_reads_the_manifest_at_its_rc(released):
    released.git("tag", "v0.0.2rc1")  # on a head whose manifest is still 0.0.1
    ship(released, "0.0.2")  # main's head is right, but it isn't what ships
    assert check_tag.errors(released.path, "v0.0.2", "main") == [
        f"{check_tag.MANIFEST} has version '0.0.1', not '0.0.2'"
    ]


def test_main(released, capsys):
    head = ship(released, "0.0.2")
    assert check_tag.main(["v0.0.2rc1", "release/v0.0.2"], released.path) == 0
    assert capsys.readouterr().out == f"{head}\n"
    assert check_tag.main(["v0.0.2rc1", "main", "extra"], released.path) == 2
    assert check_tag.main(["v0.0.1", "main"], released.path) == 1
    assert "error: v0.0.1 already exists" in capsys.readouterr().err
