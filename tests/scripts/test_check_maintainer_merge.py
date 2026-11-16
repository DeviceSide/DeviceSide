"""scripts/check_maintainer_merge.py: a maintainer's `/merge` merges a PR whose every file they own."""

import pytest

from custom_components.deviceside.core.registry import AdapterRegistry
from scripts import check_maintainer_merge as cmm
from scripts import gen_codeowners, route_issue

PATHS = cmm.package_paths()
PKG = "custom_components/deviceside/integrations/acme/"
INIT = cmm.INIT.format(key="acme")
SCOPE = PKG + "raise_brightness.py"
README = "# DeviceSide\n\nIntro.\n\n<!-- devices:start -->\nold cards\n<!-- devices:end -->\n"
ACME = cmm.Package("acme")
TUYA = cmm.Package("acme", "tuya")
FAMILY = PKG + "families/tuya/"
ENTRY = 'ENTRY = DoesntWork("Plugs", "why", "https://x/1", harms=True)\n'


def init(maintainers=("alice",)):
    return f'INTEGRATION = IntegrationInfo(key="acme", title="Acme", maintainers={maintainers!r})\n'


def family(key="tuya", maintainers=("tina",), body='SCOPE = FamilyScope(capabilities=experimental("tuya_zcl"))\n'):
    return f"FAMILY = Family(key={key!r}, maintainers={maintainers!r}, classes=CLASSES)\n{body}"


def family_init(integration="acme", name="tuya"):
    return cmm.FAMILY_INIT.format(key=integration, family=name)


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
    assert PATHS == (gen_codeowners.PATHS, gen_codeowners.FAMILY_PATHS, gen_codeowners.CATALOG_PATHS)


@pytest.mark.parametrize(
    "path",
    [SCOPE, "tests/integrations/acme/test_x.py", "tests/fixtures/acme.py", "docs/integrations/acme/test-records/r.md"],
)
def test_a_maintainer_merges_a_change_anywhere_in_their_package(pr, path):
    pr.commit(path, "x = 1\n")
    assert check() == [ACME]


def test_regenerated_output_rides_along(pr):
    pr.commit(SCOPE, "scope = AdapterScope(experimental=False)\n")  # lifting the flag is the maintainer's call
    pr.commit(cmm.README, README.replace("old cards", "new cards"))
    pr.commit("docs/device-compatibility.md", "cards\n")
    pr.commit(".github/CODEOWNERS", "* @x\n")
    assert check() == [ACME]


def test_someone_else_is_refused(pr):
    pr.commit(SCOPE, "x = 1\n")
    assert refused("mallory") == "@mallory isn't a maintainer of `acme`"


def test_a_pr_that_adds_its_commenter_as_maintainer_is_refused(pr):
    pr.commit(INIT, init(("alice", "mallory")))
    assert refused("mallory") == "@mallory isn't a maintainer of `acme`"
    assert refused("alice") == f"it changes a `maintainers` value in {INIT}"


def test_a_new_integration_is_refused(pr):
    pr.commit(cmm.INIT.format(key="newco"), init())
    assert refused() == "`newco` isn't an integration on the base branch yet"


@pytest.mark.parametrize("path", ["custom_components/deviceside/core/x.py", ".github/workflows/x.yml", "docs/x.md"])
def test_a_file_outside_the_package_is_refused(pr, path):
    pr.commit(SCOPE, "x = 1\n")
    pr.commit(path, "x\n")
    assert refused() == f"it changes files outside an integration's package: {path}"


def test_a_second_package_is_refused_unless_the_commenter_maintains_it_too(repo, monkeypatch):
    monkeypatch.chdir(repo.path)
    repo.commit(INIT, init(("alice", "bob")))
    repo.commit(cmm.INIT.format(key="other"), init(("alice",)).replace("acme", "other"))
    repo.git("checkout", "-q", "-b", "pr")
    repo.commit(SCOPE, "x = 1\n")
    repo.commit("tests/fixtures/other.py", "x = 1\n")
    assert check() == [ACME, cmm.Package("other")]
    assert refused("bob") == "@bob isn't a maintainer of `other`"


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
    assert refused() == "it leaves `acme`'s maintainers unreadable"


def test_a_second_integration_binding_is_refused(pr):
    pr.commit(INIT, init() + init(("alice", "mallory")))
    assert refused() == f"it changes a `maintainers` value in {INIT}"


def test_deleting_the_package_is_refused(pr):
    pr.git("rm", "-q", "-r", PKG)
    pr.git("commit", "-q", "-m", "delete")
    assert refused() == f"it changes a `maintainers` value in {INIT}"


def test_a_path_with_a_space_is_read_whole(pr):
    path = f"README.md {PKG}evil.sh"
    pr.commit(path, "x\n")
    assert refused() == f"it changes files outside an integration's package: {path}"


def test_a_non_ascii_path_in_the_package_is_allowed(pr):
    pr.commit("docs/integrations/acme/café.md", "x\n")
    assert check() == [ACME]


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
    assert capsys.readouterr().out == "Every file it changes is in `acme`, which @alice owns.\n"


@pytest.fixture
def families(repo, monkeypatch):
    """`main` with `acme` (alice) and `zeta` (zoe), each with a `tuya` family (tina; on zeta, zed) beside a `hue` one
    with no maintainers of its own, and the catalog file the `tuya` families share; then a `pr` branch."""
    monkeypatch.chdir(repo.path)
    repo.commit(INIT, init())
    repo.commit(cmm.INIT.format(key="zeta"), init(("zoe",)).replace("acme", "zeta").replace("Acme", "Zeta"))
    repo.commit(family_init(), family() + ENTRY)
    repo.commit(family_init(name="hue"), family("hue", ()))
    repo.commit(family_init("zeta"), family(maintainers=("zed",)))
    repo.commit(PKG + "families/__init__.py", "RULES = (*hue.RULES, *tuya.RULES)\n")
    repo.commit(PKG + "bridge.py", "x = 1\n")
    repo.commit("tests/integrations/acme/test_classification.py", "DEVICES = ()\n")
    repo.commit(CATALOG, 'DATAPOINT = "_TZE"\n')
    repo.git("checkout", "-q", "-b", "pr")
    return repo


CATALOG = "custom_components/deviceside/zigbee/tuya.py"


@pytest.mark.parametrize(
    "path",
    [
        FAMILY + "rules.py",
        "tests/integrations/acme/families/tuya/test_rules.py",
        "docs/integrations/acme/research/tuya/2026-11-16-probe.md",
    ],
)
def test_a_family_maintainer_merges_a_change_confined_to_their_family(families, path):
    families.commit(path, "x = 1\n")
    assert check("tina") == [TUYA]
    assert check("alice") == [TUYA]  # the integration's maintainers own its families too
    assert refused("zed") == "@zed isn't a maintainer of `acme` or of `acme`'s `tuya` family"


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (FAMILY.replace("tuya", "hue") + "rules.py", "@tina isn't a maintainer of `acme` or of `acme`'s `hue` family"),
        (PKG + "bridge.py", "@tina isn't a maintainer of `acme`"),
        (PKG + "families/__init__.py", "@tina isn't a maintainer of `acme`"),
        ("tests/integrations/acme/test_classification.py", "@tina isn't a maintainer of `acme`"),
        ("docs/integrations/acme/research/2026-11-16-probe.md", "@tina isn't a maintainer of `acme`"),
        # A family that isn't on the base branch is its integration's.
        (FAMILY.replace("tuya", "newco") + "__init__.py", "@tina isn't a maintainer of `acme`"),
        ("docs/integrations/acme/research/newco/probe.md", "@tina isn't a maintainer of `acme`"),
        (
            cmm.FAMILY_INIT.format(key="zeta", family="tuya"),
            "@tina isn't a maintainer of `zeta` or of `zeta`'s `tuya` family",
        ),
    ],
)
def test_a_family_maintainer_is_refused_outside_their_family(families, path, reason):
    families.commit(FAMILY + "rules.py", "x = 1\n")
    families.commit(path, "x = 3\n")
    assert refused("tina") == reason


def test_a_family_maintainer_changes_a_level(families):
    families.commit(family_init(), family(body='SCOPE = FamilyScope(capabilities=verified("tuya_zcl"))\n') + ENTRY)
    assert check("tina") == [TUYA]


@pytest.mark.parametrize(
    "entries",
    [
        "",
        ENTRY.replace("why", "another reason"),
        ENTRY.replace("harms=True", "harms=False"),
        ENTRY + 'OTHER = scope.NotSupported("why", "https://x/2", harms=True)\n',
    ],
)
def test_only_an_integration_maintainer_changes_a_doesnt_work_or_not_supported_entry(families, entries):
    families.commit(family_init(), family() + entries)
    assert refused("tina") == (
        f"it adds, changes or removes a doesn't-work or not-yet-supported entry in {family_init()}; a maintainer of "
        "the integration can merge it too"
    )
    assert check("alice") == [TUYA]


def test_moving_an_entry_within_its_file_is_no_change(families):
    families.commit(family_init(), ENTRY + family())
    assert check("tina") == [TUYA]


@pytest.mark.parametrize("commenter", ["tina", "alice"])
def test_nobody_changes_a_familys_maintainers(families, commenter):
    families.commit(family_init(), family(maintainers=("tina", "mallory")) + ENTRY)
    assert refused("mallory") == "@mallory isn't a maintainer of `acme` or of `acme`'s `tuya` family"
    assert refused(commenter) == f"it changes a `maintainers` value in {family_init()}"


def test_a_maintainers_value_anywhere_in_a_python_file_is_refused(families):
    families.commit(FAMILY + "rules.py", 'x = Family(key="x", maintainers=("tina",))\n')
    assert refused("tina") == f"it changes a `maintainers` value in {FAMILY}rules.py"


@pytest.mark.parametrize(
    "text",
    [
        "FAMILY = Family(key=KEY, maintainers=('tina',), classes=CLASSES)\n" + ENTRY,
        "FAMILY = Family(key='hue', maintainers=('tina',), classes=CLASSES)\n" + ENTRY,
    ],
)
def test_an_unreadable_family_is_refused(families, text):
    families.commit(family_init(), text)
    assert refused("tina") == "it leaves the maintainers of `acme`'s `tuya` family unreadable"


def test_a_family_maintainer_sets_no_caveat(families):
    families.commit(FAMILY + "rules.py", 'c = Caveat("why")\n')
    assert refused("tina") == f"it sets or clears a caveat in {FAMILY}rules.py"


def test_the_catalog_is_its_families_and_their_integrations(families):
    families.commit(CATALOG, 'DATAPOINT = "_TZE2"\n')
    families.commit("tests/zigbee/test_tuya.py", "x = 1\n")
    for owner in ("tina", "zed", "alice", "zoe"):
        assert check(owner) == [cmm.Package(None, "tuya")]
    assert refused("mallory") == "@mallory isn't a maintainer of a `tuya` family or its integration"


def test_a_catalog_change_with_both_stacks_families_needs_an_owner_of_all_three(repo, monkeypatch):
    monkeypatch.chdir(repo.path)
    repo.commit(INIT, init())
    repo.commit(cmm.INIT.format(key="zeta"), init(("zoe",)).replace("acme", "zeta"))
    repo.commit(family_init(), family(maintainers=("tina", "both")))
    repo.commit(family_init("zeta"), family(maintainers=("zed", "both")))
    repo.commit(CATALOG, 'DATAPOINT = "_TZE"\n')
    repo.git("checkout", "-q", "-b", "pr")
    repo.commit(CATALOG, 'DATAPOINT = "_TZE2"\n')
    repo.commit(FAMILY + "rules.py", "x = 1\n")
    repo.commit(FAMILY.replace("acme", "zeta") + "rules.py", "x = 1\n")
    assert check("both") == [cmm.Package(None, "tuya"), TUYA, cmm.Package("zeta", "tuya")]
    assert refused("tina") == "@tina isn't a maintainer of `zeta` or of `zeta`'s `tuya` family"
    assert refused("alice") == "@alice isn't a maintainer of `zeta` or of `zeta`'s `tuya` family"


def test_a_catalog_entry_changes_only_with_every_sharing_integrations_maintainer(families):
    families.commit(CATALOG, ENTRY)
    assert refused("alice").startswith("it adds, changes or removes a doesn't-work or not-yet-supported entry")


def test_a_catalog_file_no_family_shares_is_nobodys(families):
    path = CATALOG.replace("tuya", "sengled")
    families.commit(path, "x = 1\n")
    assert refused("alice") == f"it changes files outside an integration's package: {path}"


def test_the_shared_zigbee_package_is_nobodys(families):
    path = "custom_components/deviceside/zigbee/__init__.py"
    families.commit(path, "x = 1\n")
    assert refused("alice") == f"it changes files outside an integration's package: {path}"


def test_main_names_what_the_commenter_owns(families, capsys):
    families.commit(FAMILY + "rules.py", "x = 1\n")
    families.commit(PKG + "bridge.py", "x = 2\n")
    assert cmm.main(["main", "pr", "--commenter", "alice"]) == 0
    assert capsys.readouterr().out == "Every file it changes is in `acme`, `acme`'s `tuya` family, which @alice owns.\n"


def test_the_family_parse_matches_the_registry():
    """Reading each family's `__init__.py` without importing it gives what the registry holds, families or none."""
    expected = {
        info.key: {found.key: route_issue.Family(found.key, found.maintainers) for found in info.families}
        for info in AdapterRegistry.discover().available_integrations()
        if info.families
    }
    assert route_issue.families() == expected


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("X = 1\n", "no FAMILY = Family"),
        ('FAMILY = Family(key="a")\n', "needs key= and maintainers="),
        ('FAMILY = Family(key="a", maintainers=HANDLES)\n', "key and maintainers must be literals"),
        ('FAMILY = Family(key="a", maintainers=())\nFAMILY = Family(key="a", maintainers=())\n', "bound 2 times"),
    ],
)
def test_an_unreadable_family_is_an_error_to_the_parser(source, error):
    with pytest.raises(SystemExit, match=error):
        route_issue.parse_family(source, "x/__init__.py")
