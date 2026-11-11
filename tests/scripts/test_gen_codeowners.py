"""scripts/gen_codeowners.py: the owner owns everything, then each integration's paths go to its maintainers."""

from types import SimpleNamespace

import pytest

from scripts import gen_codeowners as gco


def info(*maintainers, available=True):
    return SimpleNamespace(maintainers=maintainers, available=available, unavailable_reason="No module named x")


def registry(**integrations):
    return SimpleNamespace(integrations=integrations)


@pytest.fixture
def repo(tmp_path):
    for path in (
        "custom_components/deviceside/integrations/hue",
        "custom_components/deviceside/integrations/control4",
        "tests/integrations/control4",
        "docs/integrations/control4",
        ".github",
    ):
        (tmp_path / path).mkdir(parents=True)
    (tmp_path / "tests" / "fixtures").mkdir()
    (tmp_path / "tests" / "fixtures" / "control4.py").write_text("")
    return tmp_path


def test_the_owner_comes_first_then_each_integrations_existing_paths_to_its_maintainers(repo):
    text = gco.generate(registry(hue=info("jasonmx"), control4=info("alice", "bob")), repo)
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert lines == [
        "* @jasonmx",
        "/custom_components/deviceside/integrations/control4/ @alice @bob @jasonmx",
        "/tests/integrations/control4/ @alice @bob @jasonmx",
        "/tests/fixtures/control4.py @alice @bob @jasonmx",
        "/docs/integrations/control4/ @alice @bob @jasonmx",
        # hue has no tests, fixture or doc bundle here: only its package.
        "/custom_components/deviceside/integrations/hue/ @jasonmx",
    ]


def test_an_integration_that_failed_to_import_is_an_error(repo):
    with pytest.raises(SystemExit, match="hue failed to import"):
        gco.generate(registry(hue=info(available=False)), repo)


def test_an_integration_without_a_package_is_an_error(repo):
    with pytest.raises(SystemExit, match="zha: no package"):
        gco.generate(registry(zha=info("jasonmx")), repo)


def test_check_fails_on_a_stale_or_hand_edited_file_until_it_is_regenerated(repo, capsys):
    fake = registry(control4=info("alice"))
    assert gco.main(["--check"], fake, repo) == 1  # missing
    assert gco.main([], fake, repo) == 0
    assert gco.main(["--check"], fake, repo) == 0
    path = repo / ".github" / "CODEOWNERS"
    path.write_text(path.read_text().replace("@alice", "@mallory"))
    assert gco.main(["--check"], fake, repo) == 1
    assert "CODEOWNERS out of date" in capsys.readouterr().err


def test_the_committed_file_is_current():
    assert gco.main(["--check"]) == 0
