"""scripts/check_maintainer_merge.py: a maintainer's `/merge` merges a PR confined to their integration's package."""

import pytest

from scripts import check_maintainer_merge as cmm
from scripts import gen_codeowners

PATHS = cmm.package_paths()
PKG = "custom_components/deviceside/integrations/acme/"
INIT = cmm.INIT.format(key="acme")
SCOPE = PKG + "raise_brightness.py"
README = "# DeviceSide\n\nIntro.\n\n<!-- devices:start -->\nold cards\n<!-- devices:end -->\n"


def init(maintainers=("alice",)):
    return f'INTEGRATION = IntegrationInfo(key="acme", title="Acme", maintainers={maintainers!r})\n'


@pytest.fixture
def pr(repo, monkeypatch):
    """`main` with an `acme` integration maintained by alice, and a `pr` branch off it."""
    monkeypatch.chdir(repo.path)
    repo.commit(INIT, init())
    repo.commit(SCOPE, "scope = AdapterScope(experimental=True)\n")
    repo.commit(cmm.README, README)
    repo.git("branch", "pr")
    repo.git("checkout", "-q", "pr")
    return repo


def check(commenter="alice"):
    return cmm.check("main", "pr", commenter, PATHS)


def refused(commenter="alice"):
    with pytest.raises(cmm.Refused) as err:
        check(commenter)
    return str(err.value)


def test_the_paths_match_gen_codeowners():
    assert PATHS == gen_codeowners.PATHS


@pytest.mark.parametrize(
    "path",
    [SCOPE, "tests/integrations/acme/test_x.py", "tests/fixtures/acme.py", "docs/integrations/acme/test-records/r.md"],
)
def test_a_maintainer_merges_a_change_anywhere_in_their_package(pr, path):
    pr.commit(path, "x = 1\n")
    assert check() == "acme"


def test_regenerated_output_rides_along(pr):
    pr.commit(SCOPE, "scope = AdapterScope(experimental=False)\n")  # lifting the flag is the maintainer's call
    pr.commit(cmm.README, README.replace("old cards", "new cards"))
    pr.commit("docs/device-compatibility.md", "cards\n")
    pr.commit(".github/CODEOWNERS", "* @x\n")
    assert check() == "acme"


def test_someone_else_is_refused(pr):
    pr.commit(SCOPE, "x = 1\n")
    assert refused("mallory") == "@mallory isn't a maintainer of `acme`"


def test_a_pr_that_adds_its_commenter_as_maintainer_is_refused(pr):
    pr.commit(INIT, init(("alice", "mallory")))
    assert refused("mallory") == "@mallory isn't a maintainer of `acme`"
    assert refused("alice") == "it changes `acme`'s maintainers"


def test_a_new_integration_is_refused(pr):
    pr.commit(cmm.INIT.format(key="newco"), init())
    assert refused() == "`newco` isn't an integration on the base branch yet"


@pytest.mark.parametrize("path", ["custom_components/deviceside/core/x.py", ".github/workflows/x.yml", "docs/x.md"])
def test_a_file_outside_the_package_is_refused(pr, path):
    pr.commit(SCOPE, "x = 1\n")
    pr.commit(path, "x\n")
    assert refused() == f"it changes files outside an integration's package: {path}"


def test_two_packages_are_refused(pr):
    pr.commit(SCOPE, "x = 1\n")
    pr.commit("tests/fixtures/other.py", "x = 1\n")
    assert refused() == "it changes more than one integration's package"


def test_generated_output_alone_is_refused(pr):
    pr.commit("docs/device-compatibility.md", "cards\n")
    assert refused() == "it changes no integration's package"


def test_readme_text_outside_its_blocks_is_refused(pr):
    pr.commit(SCOPE, "x = 1\n")
    pr.commit(cmm.README, README.replace("Intro.", "My intro."))
    assert refused() == "it changes README.md outside its generated blocks"


@pytest.mark.parametrize(
    "text",
    [
        'scope = AdapterScope(experimental=True, caveat=Caveat("https://x/1"))\n',
        'c = core.Caveat("why")\n',
    ],
)
def test_setting_a_caveat_is_refused(pr, text):
    pr.commit(SCOPE, text)
    assert refused() == f"it sets or clears a caveat in {SCOPE}"


def test_clearing_a_caveat_is_refused(repo, monkeypatch):
    monkeypatch.chdir(repo.path)
    repo.commit(INIT, init())
    repo.commit(SCOPE, 'scope = AdapterScope(caveat=Caveat("why"))\n')
    repo.git("checkout", "-q", "-b", "pr")
    repo.commit(SCOPE, "scope = AdapterScope()\n")
    assert refused() == f"it sets or clears a caveat in {SCOPE}"


def test_unparseable_python_is_refused(pr):
    pr.commit(SCOPE, "def (:\n")
    assert refused().startswith(f"{SCOPE} doesn't parse")


def test_an_unreadable_maintainers_list_is_refused(pr):
    pr.commit(INIT, "INTEGRATION = IntegrationInfo(key=KEY, title='Acme', maintainers=('alice',))\n")
    assert refused() == "it changes `acme`'s maintainers"


def test_an_empty_pr_is_refused(pr):
    assert refused() == "it changes nothing"


def test_main_reports_the_reason(pr, tmp_path, monkeypatch, capsys):
    pr.commit(SCOPE, "x = 1\n")
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert cmm.main(["main", "pr", "--commenter", "mallory"]) == 1
    message = "A repo maintainer needs to merge this: @mallory isn't a maintainer of `acme`."
    assert output.read_text() == f"reason={message}\n"
    assert capsys.readouterr().out == message + "\n"
    assert cmm.main(["main", "pr", "--commenter", "alice"]) == 0
