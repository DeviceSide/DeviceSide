"""scripts/gen_codeowners.py: the repo maintainers own everything, then each integration's paths to its maintainers,
and a family's or the catalog's to theirs where they add an owner."""

from types import SimpleNamespace

import pytest

from scripts import gen_codeowners as gco


def info(*maintainers, available=True, families=(), title="Title"):
    return SimpleNamespace(
        maintainers=maintainers,
        available=available,
        unavailable_reason="No module named x",
        families=families,
        title=title,
    )


def family(key, *maintainers):
    return SimpleNamespace(key=key, maintainers=maintainers)


def registry(**integrations):
    return SimpleNamespace(
        integrations=integrations,
        available_integrations=lambda: [i for i in integrations.values() if i.available],
    )


FORM = """\
body:
  - type: dropdown
    attributes:
      options:
        # integrations:start
        - Stale
        # integrations:end
        - Other or not sure
"""


@pytest.fixture
def repo(tmp_path):
    for path in (
        "custom_components/deviceside/integrations/hue",
        "custom_components/deviceside/integrations/control4",
        "tests/integrations/control4",
        "docs/integrations/control4",
        ".github/ISSUE_TEMPLATE",
    ):
        (tmp_path / path).mkdir(parents=True)
    (tmp_path / ".github" / "ISSUE_TEMPLATE" / "device_report.yml").write_text(FORM)
    (tmp_path / "tests" / "fixtures").mkdir()
    (tmp_path / "tests" / "fixtures" / "control4.py").write_text("")
    (tmp_path / "custom_components" / "deviceside" / "manifest.json").write_text('{"codeowners": ["@jasonmx"]}')
    return tmp_path


def test_the_repo_maintainers_come_first_then_each_integrations_existing_paths_to_its_maintainers(repo):
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


def test_every_repo_maintainer_owns_everything_and_each_package_once(repo, monkeypatch):
    monkeypatch.setattr(gco, "REPO_MAINTAINERS", ("jasonmx", "carol"))
    text = gco.generate(registry(hue=info("carol", "dave")), repo)
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert lines == [
        "* @jasonmx @carol",
        "/custom_components/deviceside/integrations/hue/ @carol @dave @jasonmx",
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


def test_an_empty_repo_maintainers_is_an_error(repo, monkeypatch):
    monkeypatch.setattr(gco, "REPO_MAINTAINERS", ())
    with pytest.raises(SystemExit, match="REPO_MAINTAINERS is empty"):
        gco.generate(registry(hue=info("carol")), repo)


def test_manifest_codeowners_must_match_the_repo_maintainers_in_either_mode(repo, monkeypatch, capsys):
    fake = registry(control4=info("alice"))
    monkeypatch.setattr(gco, "REPO_MAINTAINERS", ("jasonmx", "carol"))
    assert gco.main([], fake, repo) == 1
    assert not (repo / ".github" / "CODEOWNERS").exists()
    assert gco.main(["--check"], fake, repo) == 1
    assert "don't match REPO_MAINTAINERS" in capsys.readouterr().err
    (repo / "custom_components" / "deviceside" / "manifest.json").write_text('{"codeowners": ["@jasonmx", "@carol"]}')
    assert gco.main([], fake, repo) == 0


@pytest.fixture
def stacks(repo):
    """Two integrations with a `tuya` and a `hue` family each, and the catalog file the `tuya` ones share."""
    for path in (
        "custom_components/deviceside/integrations/hue/families/tuya",
        "custom_components/deviceside/integrations/hue/families/hue",
        "custom_components/deviceside/integrations/control4/families/tuya",
        "custom_components/deviceside/integrations/control4/families/hue",
        "tests/integrations/control4/families/tuya",
        "docs/integrations/control4/research/tuya",
        "custom_components/deviceside/zigbee",
        "tests/zigbee",
    ):
        (repo / path).mkdir(parents=True)
    (repo / "custom_components/deviceside/zigbee/tuya.py").write_text("")
    (repo / "tests/zigbee/test_tuya.py").write_text("")
    return repo


def test_families_without_maintainers_of_their_own_add_no_line(stacks):
    plain = registry(hue=info("jasonmx"), control4=info("alice"))
    with_families = registry(
        hue=info("jasonmx", families=(family("tuya"), family("hue", "jasonmx"))),
        control4=info("alice", families=(family("tuya", "alice"), family("hue"))),
    )
    # The catalog's owners are then alice and the repo maintainer's, whom `*` gives it: only alice adds a line.
    catalog = (
        "\n/custom_components/deviceside/zigbee/tuya.py @alice @jasonmx\n/tests/zigbee/test_tuya.py @alice @jasonmx\n"
    )
    assert gco.generate(with_families, stacks) == gco.generate(plain, stacks) + catalog
    solo = registry(hue=info("jasonmx", families=(family("tuya"),)))
    assert gco.generate(solo, stacks) == gco.generate(registry(hue=info("jasonmx")), stacks)


def test_a_familys_existing_paths_follow_its_integrations_then_the_catalog(stacks):
    text = gco.generate(
        registry(
            hue=info("jasonmx", families=(family("tuya", "zed"), family("hue"))),
            control4=info("alice", "bob", families=(family("tuya", "tina", "alice"), family("hue"))),
        ),
        stacks,
    )
    assert text.split("\n\n", 1)[1].splitlines() == [
        "/custom_components/deviceside/integrations/control4/ @alice @bob @jasonmx",
        "/tests/integrations/control4/ @alice @bob @jasonmx",
        "/tests/fixtures/control4.py @alice @bob @jasonmx",
        "/docs/integrations/control4/ @alice @bob @jasonmx",
        "/custom_components/deviceside/integrations/control4/families/tuya/ @tina @alice @bob @jasonmx",
        "/tests/integrations/control4/families/tuya/ @tina @alice @bob @jasonmx",
        "/docs/integrations/control4/research/tuya/ @tina @alice @bob @jasonmx",
        "",
        "/custom_components/deviceside/integrations/hue/ @jasonmx",
        # hue's family has no tests or research folder here: only its package.
        "/custom_components/deviceside/integrations/hue/families/tuya/ @zed @jasonmx",
        "",
        "/custom_components/deviceside/zigbee/tuya.py @tina @alice @zed @bob @jasonmx",
        "/tests/zigbee/test_tuya.py @tina @alice @zed @bob @jasonmx",
    ]


def test_the_shared_catalog_files_go_to_the_reading_integrations_never_a_family(stacks):
    """`control4` reads the catalog through its `tuya` family; `hue`'s only family has no catalog file."""
    (stacks / "custom_components/deviceside/zigbee/reasons.py").write_text("")
    (stacks / "tests/zigbee/test_reasons.py").write_text("")
    text = gco.generate(
        registry(
            hue=info("jasonmx", "dave", families=(family("hue", "zed"),)),
            control4=info("alice", families=(family("tuya", "tina"),)),
        ),
        stacks,
    )
    assert text.endswith(
        "/custom_components/deviceside/zigbee/tuya.py @tina @alice @jasonmx\n"
        "/tests/zigbee/test_tuya.py @tina @alice @jasonmx\n"
        "/custom_components/deviceside/zigbee/reasons.py @alice @jasonmx\n"
        "/tests/zigbee/test_reasons.py @alice @jasonmx\n"
    )


def test_a_family_without_a_package_is_an_error(stacks):
    with pytest.raises(SystemExit, match="hue: no package for family sengled"):
        gco.generate(registry(hue=info("jasonmx", families=(family("sengled"),))), stacks)


def test_the_dropdown_options_are_the_sorted_titles_between_the_markers(repo):
    fake = registry(hue=info(title="Hue"), control4=info(title="Control4"))
    assert gco.main([], fake, repo) == 0
    assert (repo / ".github" / "ISSUE_TEMPLATE" / "device_report.yml").read_text() == FORM.replace(
        "        - Stale\n", "        - Control4\n        - Hue\n"
    )


def test_check_fails_on_a_hand_edited_dropdown_until_it_is_regenerated(repo, capsys):
    fake = registry(control4=info("alice", title="Control4"))
    assert gco.main([], fake, repo) == 0
    assert gco.main(["--check"], fake, repo) == 0
    path = repo / ".github" / "ISSUE_TEMPLATE" / "device_report.yml"
    path.write_text(path.read_text().replace("- Control4", "- Control5"))
    assert gco.main(["--check"], fake, repo) == 1
    assert "device_report.yml out of date" in capsys.readouterr().err
    assert gco.main([], fake, repo) == 0
    assert "- Control4" in path.read_text()


def test_a_form_without_both_markers_is_an_error(repo):
    path = repo / ".github" / "ISSUE_TEMPLATE" / "device_report.yml"
    path.write_text(path.read_text().replace("# integrations:end", "# nothing"))
    with pytest.raises(SystemExit, match="integrations:start"):
        gco.main([], registry(control4=info()), repo)


def test_the_committed_files_are_current():
    assert gco.main(["--check"]) == 0
