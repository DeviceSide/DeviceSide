"""scripts/owners.py: who owns a path, read at a rev without importing; the gate, routing and the notice share it."""

import json

import pytest

from custom_components.deviceside.core import registry
from custom_components.deviceside.core.registry import AdapterRegistry
from scripts import gen_codeowners
from scripts import owners as ow

PATHS = ow.package_paths()
PKG = "custom_components/deviceside/integrations/acme/"
TUYA_DIR = PKG + "families/tuya/"
CATALOG = "custom_components/deviceside/zigbee/tuya.py"
REPO = tuple(sorted(gen_codeowners.REPO_MAINTAINERS))

ACME = ow.Package("acme")
TUYA = ow.Package("acme", "tuya")
HUE = ow.Package("acme", "hue")
SHARED = ow.Package(None, "tuya")
ACME_GROUP = ow.Group(ACME, "acme", ("alice",))
TUYA_GROUP = ow.Group(TUYA, "acme", ("tina",), ("alice",))
HUE_GROUP = ow.Group(HUE, "acme", ("alice",))
CATALOG_ACME = ow.Group(SHARED, "acme", ("tina",), ("alice",))
CATALOG_ZETA = ow.Group(SHARED, "zeta", ("zed",), ("zoe",))
SHARED_CODE = ow.Group(None, None, REPO)


def integration(key, maintainers):
    return f"INTEGRATION = IntegrationInfo(key={key!r}, title={key.title()!r}, maintainers={maintainers!r})\n"


def family(key, maintainers):
    return f"FAMILY = Family(key={key!r}, maintainers={maintainers!r}, classes=CLASSES)\n"


@pytest.fixture
def tree(repo, monkeypatch):
    """`main`: `acme` (alice) with a `tuya` family (tina) and a `hue` one with no maintainers of its own, `zeta`
    (zoe) with a `tuya` family (zed), and the catalog file the `tuya` families share."""
    monkeypatch.chdir(repo.path)
    repo.commit(ow.INIT.format(key="acme"), integration("acme", ("alice",)))
    repo.commit(ow.INIT.format(key="zeta"), integration("zeta", ("zoe",)))
    repo.commit(ow.FAMILY_INIT.format(key="acme", family="tuya"), family("tuya", ("tina",)))
    repo.commit(ow.FAMILY_INIT.format(key="acme", family="hue"), family("hue", ()))
    repo.commit(ow.FAMILY_INIT.format(key="zeta", family="tuya"), family("tuya", ("zed",)))
    repo.commit(CATALOG, 'DATAPOINT = "_TZE"\n')
    return repo


def at_main():
    return ow.commit("main")


def test_the_paths_match_gen_codeowners():
    assert PATHS == (gen_codeowners.PATHS, gen_codeowners.FAMILY_PATHS, gen_codeowners.CATALOG_PATHS)


def test_the_family_key_shape_matches_the_registry():
    """The lookup is stdlib-only, so it restates the registry's pattern."""
    assert ow.NAMES["family"] == registry.FAMILY_KEY.pattern


def test_a_path_with_a_trailing_newline_matches_no_file_template():
    assert ow.match("tests/fixtures/acme.py\n", PATHS.integration) is None
    assert ow.match("tests/fixtures/acme.py", PATHS.integration) == {"key": "acme"}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (PKG + "bridge.py", [ACME_GROUP]),
        ("tests/integrations/acme/test_classification.py", [ACME_GROUP]),
        (TUYA_DIR + "rules.py", [TUYA_GROUP]),
        ("tests/integrations/acme/families/tuya/test_rules.py", [TUYA_GROUP]),
        ("docs/integrations/acme/research/tuya/2026-11-16-probe.md", [TUYA_GROUP]),
        # A family that names no maintainers is its integration's.
        (PKG + "families/hue/rules.py", [HUE_GROUP]),
        # A family that isn't on the rev is its integration's.
        (PKG + "families/newco/__init__.py", [ACME_GROUP]),
        (CATALOG, [CATALOG_ACME, CATALOG_ZETA]),
        # Shared code, and an integration that isn't on the rev yet: the repo maintainers'.
        ("custom_components/deviceside/core/scope.py", [SHARED_CODE]),
        ("custom_components/deviceside/integrations/newint/bridge.py", [SHARED_CODE]),
        # A catalog file no family on the rev shares.
        ("custom_components/deviceside/zigbee/sonoff.py", [SHARED_CODE]),
        # Generated output follows its inputs.
        ("README.md", []),
        (".github/CODEOWNERS", []),
    ],
)
def test_each_path_has_its_owner_groups(tree, path, expected):
    assert list(ow.owned([path], at_main(), PATHS)) == expected


def test_the_gates_set_is_every_groups_handles(tree):
    rev = at_main()
    assert ow.owners(ACME, rev) == {"alice"}
    assert ow.owners(TUYA, rev) == {"tina", "alice"}
    assert ow.owners(HUE, rev) == {"alice"}
    assert ow.owners(SHARED, rev) == {"tina", "alice", "zed", "zoe"}
    with pytest.raises(ow.NotOnRev) as err:
        ow.owners(ow.Package("newint"), rev)
    assert err.value.key == "newint"


@pytest.mark.parametrize(
    ("login", "paths", "expected"),
    [
        # A repo maintainer: every package, never shared code.
        (REPO[0], [PKG + "bridge.py", "custom_components/deviceside/core/scope.py"], [ACME_GROUP]),
        # An integration maintainer in their own family is warned; in a family with no maintainers, not.
        ("alice", [TUYA_DIR + "rules.py"], [TUYA_GROUP]),
        ("alice", [PKG + "families/hue/rules.py"], []),
        # A family maintainer on the shared catalog: the other stack's family.
        ("tina", [CATALOG], [CATALOG_ZETA]),
        # A partial owner sees only what they don't own.
        ("alice", [PKG + "bridge.py", TUYA_DIR + "rules.py"], [TUYA_GROUP]),
        # Someone who owns nothing: every group, shared code included.
        ("mallory", [TUYA_DIR + "rules.py", "scripts/x.py"], [TUYA_GROUP, SHARED_CODE]),
    ],
)
def test_foreign_groups_are_those_whose_direct_maintainers_leave_the_login_out(tree, login, paths, expected):
    assert list(ow.foreign(login, paths, at_main(), PATHS)) == expected


def test_owners_are_read_at_the_rev_not_the_head(tree):
    base = at_main()
    tree.git("checkout", "-q", "-b", "pr")
    tree.commit(ow.INIT.format(key="acme"), integration("acme", ("alice", "mallory")))
    assert list(ow.foreign("mallory", [PKG + "bridge.py"], base, PATHS)) == [ACME_GROUP]
    assert list(ow.foreign("mallory", [PKG + "bridge.py"], ow.commit("pr"), PATHS)) == []


def test_a_route_labels_each_integration_and_assigns_the_direct_maintainers():
    assert ow.route([TUYA_GROUP, CATALOG_ZETA, ACME_GROUP]) == (
        ["integration:acme", "integration:zeta"],
        ["tina", "zed", "alice"],
    )
    assert ow.route([SHARED_CODE]) == ([], list(REPO))


def test_the_label_is_the_one_route_issue_writes():
    from scripts import route_issue

    known = {"Acme": route_issue.Integration("acme", "Acme", ("alice",))}
    assert route_issue.route("### Integration\n\nAcme\n", known)[0] == ow.route([ACME_GROUP])[0]


@pytest.mark.parametrize(
    ("package", "slug", "text"),
    [
        (ACME, "acme", "`acme`"),
        (TUYA, "acme/tuya", "`acme`'s `tuya` family"),
        (SHARED, "zigbee/tuya", "the `tuya` catalog"),
    ],
)
def test_a_package_names_itself(package, slug, text):
    assert (package.slug, str(package)) == (slug, text)


def test_the_cli_prints_a_line_per_group(tree, capsys):
    assert ow.main([PKG + "bridge.py", TUYA_DIR + "a.py", TUYA_DIR + "b.py", CATALOG, "--rev", "main"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "`acme`: @alice (1 path)",
        "`acme`'s `tuya` family: @tina, and `acme`'s @alice (2 paths)",
        "the `tuya` catalog (`acme`'s `tuya` family): @tina, and `acme`'s @alice (1 path)",
        "the `tuya` catalog (`zeta`'s `tuya` family): @zed, and `zeta`'s @zoe (1 path)",
    ]


def test_the_cli_gives_the_skills_the_foreign_rows_as_json(tree, capsys):
    assert ow.main([PKG + "bridge.py", CATALOG, "--as", "tina", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {
            "owner": "acme",
            "package": "`acme`",
            "integration": "acme",
            "direct": ["alice"],
            "enclosing": [],
            "paths": [PKG + "bridge.py"],
        },
        {
            "owner": "zigbee/tuya",
            "package": "the `tuya` catalog (`zeta`'s `tuya` family)",
            "integration": "zeta",
            "direct": ["zed"],
            "enclosing": ["zoe"],
            "paths": [CATALOG],
        },
    ]


def test_the_cli_routes_an_issue(tree, capsys):
    assert ow.main([TUYA_DIR + "rules.py", "--as", "alice", "--issue"]) == 0
    assert capsys.readouterr().out == "labels=integration:acme\nassignees=tina\n"


# The parsers.


def test_the_family_parse_matches_the_registry():
    """Reading each family's `__init__.py` without importing it gives what the registry holds, families or none."""
    expected = {
        (info.key, found.key): ow.Family(found.key, found.maintainers)
        for info in AdapterRegistry.discover().available_integrations()
        for found in info.families
    }
    inits = sorted((ow.REPO / ow.INTEGRATIONS).glob("*/families/*/__init__.py"))
    parsed = {(init.parents[2].name, init.parent.name): ow.parse_family(init.read_text(), init) for init in inits}
    assert parsed == expected


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("X = 1\n", "no FAMILY = Family"),
        ('FAMILY = Family(key="a")\n', "needs key= and maintainers="),
        ('FAMILY = Family(key="a", maintainers=HANDLES)\n', "key and maintainers must be literals"),
        ('FAMILY = Family(key="a", maintainers=-"b")\n', "key and maintainers must be literals"),
        ('FAMILY = Family(key="a", maintainers=())\nFAMILY = Family(key="a", maintainers=())\n', "bound 2 times"),
        ('FAMILY = dict(key="a", maintainers=())\n', "no FAMILY = Family"),
        ('FAMILY = Family(key="a", maintainers="tina")\n', "maintainers must be a tuple or list of strings"),
        ('FAMILY = Family(key="a", maintainers=("tina", 1))\n', "maintainers must be a tuple or list of strings"),
        ('FAMILY = Family(key=("a",), maintainers=())\n', "key must be a string"),
    ],
)
def test_an_unreadable_family_is_an_error(source, error):
    with pytest.raises(SystemExit, match=error):
        ow.parse_family(source, "x/__init__.py")


def test_a_family_reads_under_an_attribute_call():
    assert ow.parse_family('FAMILY = scope.Family(key="a", maintainers=["tina"])\n', "x") == ow.Family("a", ("tina",))


def test_the_repo_maintainers_come_from_gen_codeowners():
    assert ow.repo_maintainers() == frozenset(gen_codeowners.REPO_MAINTAINERS)


def test_no_repo_maintainers_list_stops(tmp_path):
    (tmp_path / "x.py").write_text("OTHER = 1\n")
    with pytest.raises(SystemExit, match="no REPO_MAINTAINERS"):
        ow.repo_maintainers(tmp_path / "x.py")


def test_a_file_missing_at_a_revision_reads_as_empty(tree):
    assert ow.show("main", "nope.md") == ""
