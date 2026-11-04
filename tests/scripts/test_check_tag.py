"""scripts/check_tag.py: which tag may be cut from which branch."""

import json

import pytest

from scripts import check_tag


def ship(repo, version: str) -> None:
    """Write manifest.json with this version into the working tree, as the checkout cut-* tags from has it."""
    path = repo.path / check_tag.MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"domain": "device_side", "version": version}))


@pytest.fixture
def released(repo):
    repo.commit()
    repo.git("tag", "v0.0.1")
    repo.git("tag", "v0.0.10rc1")  # an RC never counts as the latest release
    repo.commit()
    return repo


@pytest.mark.parametrize(
    ("tag", "branch"),
    [
        ("v0.0.2rc1", "release/v0.0.2"),
        ("v0.0.2rc3", "main"),
        ("v0.0.2", "main"),
        ("v0.1.0", "main"),
    ],
)
def test_allowed(released, tag, branch):
    ship(released, tag[1:].split("rc")[0])
    assert check_tag.errors(released.path, tag, branch) == []


@pytest.mark.parametrize(
    ("tag", "branch", "error"),
    [
        ("v0.0.2rc1", "release/v0.0.3", "v0.0.2rc1 must be cut from release/v0.0.2 or, as a hotfix, from main"),
        ("v0.0.2rc1", "wt/topic", "must be cut from release/v0.0.2"),
        ("v0.0.3rc1", "main", "a hotfix RC from main must be v0.0.2rcN, not v0.0.3rc1"),
        ("v0.0.2", "release/v0.0.2", "a release is cut from main only, not release/v0.0.2"),
        ("v0.0.1", "main", "v0.0.1 is not above the latest release, v0.0.1"),
        ("v0.0.2-test", "main", "matches neither"),
        ("v0.0.10rc1", "release/v0.0.10", "v0.0.10rc1 already exists"),
    ],
)
def test_refused(released, tag, branch, error):
    ship(released, "0.0.2")
    assert any(error in problem for problem in check_tag.errors(released.path, tag, branch))


def test_first_release_needs_no_earlier_tag(repo):
    repo.commit()
    ship(repo, "0.0.1")
    assert check_tag.errors(repo.path, "v0.0.1", "main") == []
    assert check_tag.errors(repo.path, "v0.0.1rc1", "main") == []


@pytest.mark.parametrize(
    ("tag", "branch", "manifest", "error"),
    [
        ("v0.1.0", "main", '{"version": "0.0.1"}', "manifest.json has version '0.0.1', not '0.1.0'"),
        ("v0.1.0rc1", "release/v0.1.0", '{"version": "0.0.1"}', "has version '0.0.1', not '0.1.0'"),
        ("v0.1.0rc1", "release/v0.1.0", '{"version": "0.1.0rc1"}', "has version '0.1.0rc1', not '0.1.0'"),
        ("v0.1.0", "main", "{", "manifest.json can't be read"),
        ("v0.1.0", "main", None, "manifest.json can't be read"),
    ],
)
def test_manifest_version_must_be_the_tags(released, tag, branch, manifest, error):
    if manifest is not None:
        ship(released, "")
        (released.path / check_tag.MANIFEST).write_text(manifest)
    assert [problem for problem in check_tag.errors(released.path, tag, branch) if error in problem]


def test_main(released, capsys):
    ship(released, "0.0.2")
    assert check_tag.main(["v0.0.2rc1", "release/v0.0.2"], released.path) == 0
    assert check_tag.main(["v0.0.2rc1", "main", "extra"], released.path) == 2
    assert check_tag.main(["v0.0.1", "main"], released.path) == 1
    assert "error: v0.0.1 already exists" in capsys.readouterr().err
