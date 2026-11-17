"""scripts/check_release.py: the coverage bar, a sign-off for each changed integration, the classes' coverage check,
and the call for testers."""

import ast
import json
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
from homeassistant.const import Platform

from custom_components.deviceside.actions import discover
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.scope import (
    AdapterScope,
    Caveat,
    CaveatKind,
    IntegrationInfo,
    experimental,
    verified,
)
from scripts import check_release as cr

from .record_files import (
    device,
    manual,
    old_test,
    ran,
    record_v1,
    record_v2,
    signoff,
    skipped,
    text,
)

ANYWHERE = frozenset(
    {Platform.LIGHT, Platform.SWITCH, Platform.SCENE}
)  # a test class's domains: every one a test scope serves

ISSUE = "https://github.com/DeviceSide/DeviceSide/issues/9"


class FakeAdapter:
    def __init__(self, scope: AdapterScope):
        self.scope = scope


class FakeRegistry:
    """Adapters by (action, integration), each of a class whose module is `<package>/<action>.py` under the root, and
    the integrations' infos, each maintained by @a."""

    def __init__(self, root: Path, monkeypatch, adapters: dict[tuple[str, str], AdapterScope]):
        self.adapters = {}
        for (action, integration), scope in adapters.items():
            module = types.ModuleType(f"fake_{integration}_{action}")
            module.__file__ = str(root / cr.package(integration) / f"{action}.py")
            monkeypatch.setitem(sys.modules, module.__name__, module)
            cls = type(f"Fake{action}", (FakeAdapter,), {"__module__": module.__name__})
            self.adapters[(action, integration)] = adapter = cls(scope)
            adapter.action, adapter.integration = action, integration
        keys = sorted({integration for _, integration in adapters})
        self.integrations = {
            key: IntegrationInfo(key=key, title=key.title(), ha_domain=key, maintainers=("a",)) for key in keys
        }

    def matrix(self):
        yield "turn_off_for", "fake", None
        for (action, integration), adapter in sorted(self.adapters.items()):
            yield action, integration, adapter


@pytest.fixture
def fake_repo(repo, monkeypatch):
    """The repository the check reads: point it at the throwaway one."""
    monkeypatch.setattr(cr, "REPO", repo.path)
    monkeypatch.setattr(cr, "BUNDLES", repo.path / "docs" / "integrations")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return repo


# Import failures and the real registry.


def test_a_real_import_failure_reaches_the_gate(monkeypatch, capsys):
    """Its adapters are missing from the registry, so no gate would see them: the failure is an error itself."""
    registry = AdapterRegistry(discover(), ["custom_components.deviceside.integrations.missing"])
    assert cr.main([], registry) == 1
    assert "error: missing: failed to import (" in capsys.readouterr().err


def test_main_reads_the_real_registry(capsys):
    assert cr.main([]) == 0
    assert capsys.readouterr().err == ""


def test_json_needs_signoffs():
    with pytest.raises(SystemExit):
        cr.main(["--json"])


# Coverage.


def coverage(path: Path, files: dict[str, int]) -> Path:
    """A coverage.json with each file's covered lines out of 100."""
    summaries = {
        name: {"summary": {"covered_lines": covered, "num_statements": 100}} for name, covered in files.items()
    }
    path.write_text(json.dumps({"files": summaries}))
    return path


CORE = "custom_components/deviceside/core"
HUE = "custom_components/deviceside/integrations/hue"


def touch(repo, *files: str) -> None:
    """Write empty files into the repository without committing them: the coverage bar reads only the tree."""
    for file in files:
        (repo.path / file).parent.mkdir(parents=True, exist_ok=True)
        (repo.path / file).write_text("")


def test_the_bar_covers_every_module_under_core_and_integrations_bar_init(fake_repo, tmp_path):
    modules = [f"{CORE}/__init__.py", f"{CORE}/dispatcher.py", f"{HUE}/__init__.py", f"{HUE}/transport.py"]
    touch(fake_repo, *modules, "custom_components/deviceside/actions/stop.py")
    report = {f"{CORE}/dispatcher.py": 94, f"{HUE}/transport.py": 95, "custom_components/deviceside/actions/stop.py": 0}
    assert cr.coverage_errors(json.loads(coverage(tmp_path / "c.json", report).read_text())) == [
        f"{CORE}/dispatcher.py: 94.0% line coverage, under 95%"
    ]


def test_a_module_missing_from_coverage_is_an_error(fake_repo):
    touch(fake_repo, f"{HUE}/transport.py")
    assert cr.coverage_errors({"files": {}}) == [f"{HUE}/transport.py: 0.0% line coverage, under 95%"]


def test_a_module_with_no_statements_is_covered(fake_repo):
    touch(fake_repo, f"{HUE}/const.py")
    empty = {"files": {f"{HUE}/const.py": {"summary": {"covered_lines": 0, "num_statements": 0}}}}
    assert cr.coverage_errors(empty) == []


def test_main_fails_under_the_bar(fake_repo, monkeypatch, tmp_path, capsys):
    touch(fake_repo, f"{HUE}/transport.py")
    registry = FakeRegistry(fake_repo.path, monkeypatch, {})
    assert cr.main(["--coverage", str(coverage(tmp_path / "c.json", {f"{HUE}/transport.py": 100}))], registry) == 0
    assert cr.main(["--coverage", str(coverage(tmp_path / "c.json", {f"{HUE}/transport.py": 50}))], registry) == 1
    assert "under 95%" in capsys.readouterr().err


# Records.

RECORDS = "docs/integrations/fake/test-records"


def tree_of(repo, commit: str, integration: str = "fake") -> str:
    """The integration's package tree at the commit, as the rig cites it."""
    return repo.git("rev-parse", "--short=12", f"{commit}:custom_components/deviceside/integrations/{integration}")


def write_record(
    repo, name: str, commit: str, result: str = "pass", integration: str = "fake", tree: str | None = "package"
) -> str:
    """Commit a format 2 record citing the commit, and return the new head. It cites the package tree at the commit, or
    `tree` when given one; with `tree` None it is format 1, converted from markdown."""
    if tree == "package":
        tree = tree_of(repo, commit, integration)
    action, *options = Path(name).stem.lstrip("_").split("-")
    if action == "config_entry":  # the rig names a suite that is no action's for the action it ran in it
        action, options = "stop", []
    if tree is None:
        data = record_v1(integration, action, result=result, commit=commit, options=options)
    else:
        data = record_v2(
            integration, action, [ran("light")], result=result, commit=commit, package=tree, options=options
        )
    return repo.commit(f"docs/integrations/{integration}/test-records/{name}", text(data))


@pytest.mark.parametrize("name", ["_facts.json", "_manual.json"])
def test_a_file_named_with_a_leading_underscore_is_never_a_record(fake_repo, name):
    """The rig's fact results (`_facts.json`) and the manual sign-offs sit beside the records; neither is one."""
    write_record(fake_repo, name, fake_repo.commit(), tree="0123456789ab")
    assert cr.record_signoff("fake") == (None, None, ())


# Manual sign-offs.

MANUAL = f"{RECORDS}/_manual.json"


def manual_file(*rows: dict) -> str:
    return text(manual("fake", *rows))


def test_a_manual_row_by_a_maintainer_or_repo_maintainer_is_a_signoff(fake_repo):
    sha = fake_repo.commit()
    fake_repo.commit(MANUAL, manual_file(signoff(sha), signoff(sha, tester="r", passed=None)))
    found, errors = cr.manual_signoffs("fake", ("a", "r"))
    assert errors == []
    assert found == [
        cr.SignOff("manual", f"{MANUAL} row 1", sha[:7], "a"),
        cr.SignOff("manual", f"{MANUAL} row 2", sha[:7], "r", vouches=True),
    ]


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"devices": ["LCA001"]}, "'LCA001' is not of type 'object'"),
        ({"devices": [{"model": "LCA001", "manufacturer": None}]}, "'class' is a required property"),
        ({"devices": []}, "should be non-empty"),
        ({"passed": []}, "should be non-empty"),
        ({"no_call_changed": True}, "should not be valid"),  # with devices and passed
        ({"tester": "@a"}, "does not match"),
        ({"devices": None, "passed": None}, "is not of type 'array'"),
    ],
)
def test_a_manual_row_out_of_format_stops_the_check_naming_the_file(fake_repo, change, error):
    """`_manual.json` is written by hand: the schema holds it to the format, and a row it rejects is no sign-off."""
    fake_repo.commit(MANUAL, manual_file(signoff(fake_repo.commit()) | change))
    with pytest.raises(SystemExit, match=f"{MANUAL}: .*{error}"):
        cr.manual_signoffs("fake", ("a",))


def test_a_manual_row_by_anyone_else_is_an_error_and_no_signoff(fake_repo):
    sha = fake_repo.commit()
    fake_repo.commit(MANUAL, manual_file(signoff(sha, tester="b")))
    assert cr.manual_signoffs("fake", ("a",)) == (
        [],
        [f"{MANUAL} row 1: tester @b is neither a maintainer of fake nor a repo one"],
    )


def test_every_manual_row_in_the_repo_is_in_format():
    """`_manual.json` files are written by hand, so the real ones are held to the format too."""
    registry = AdapterRegistry.discover()
    errors = [
        error
        for key, info in registry.integrations.items()
        for error in cr.manual_signoffs(key, (*info.maintainers, *cr.REPO_MAINTAINERS), key in cr.classed(registry))[1]
    ]
    assert errors == []


def test_names_classes_is_the_integrations_capability_for_every_adapter():
    """gen_compat and check_release read "names classes" from the scope; it must agree with IntegrationInfo."""
    registry = AdapterRegistry.discover()
    found = {(name, cr.names_classes(adapter)) for name, adapter in cr.adapters(registry)}
    expected = {
        (name, registry.integrations[adapter.integration].capability is not None)
        for name, adapter in cr.adapters(registry)
    }
    assert found == expected
    assert cr.classed(registry) == {key for key, info in registry.integrations.items() if info.capability is not None}


# The release gate.

FAKE = "custom_components/deviceside/integrations/fake"
OTHER = "custom_components/deviceside/integrations/other"


@pytest.fixture
def released(fake_repo):
    """fake and other, each with two adapter modules and a helper, released as v0.1.0, with a later RC tag."""
    modules = ("__init__.py", "turn_on_for.py", "stop.py", "transport.py")
    touch(fake_repo, *(f"{package}/{module}" for package in (FAKE, OTHER) for module in modules))
    fake_repo.commit()
    fake_repo.git("tag", "v0.1.0")
    fake_repo.commit()
    fake_repo.git("tag", "v0.2.0rc1")  # an RC is never the last release
    return fake_repo


def registry(repo, monkeypatch, **scopes: AdapterScope) -> FakeRegistry:
    """fake's two adapters, with the scopes given by action, and other's turn_on_for."""
    adapters = {(action, "fake"): scopes.get(action, AdapterScope()) for action in ("turn_on_for", "stop")}
    return FakeRegistry(repo.path, monkeypatch, adapters | {("turn_on_for", "other"): AdapterScope()})


def test_the_last_release_is_the_latest_release_tag_under_head(released):
    assert cr.last_release() == "v0.1.0"
    released.git("tag", "v0.0.9", "HEAD~1")
    assert cr.last_release() == "v0.1.0"


def test_an_unchanged_integration_needs_no_signoff(released, monkeypatch, capsys):
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert capsys.readouterr().out == "Since v0.1.0:\n"


def test_a_changed_integration_with_no_signoff_fails(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    out, err = capsys.readouterr()
    line = f"fake: changed at {change[:7]}; no sign-off of its package, and no Untested fix on fake / stop"
    assert out.splitlines() == ["Since v0.1.0:", line]
    assert err.splitlines() == [f"error: {line}"]


def test_every_record_passing_at_the_package_as_it_ships_signs_off(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    write_record(released, "turn_on_for.json", change)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert capsys.readouterr().out.splitlines()[1] == (
        f"fake: changed at {change[:7]}; signed off by record {RECORDS} at {change[:7]}"
    )
    after = released.commit("README.md")  # a later commit outside the package
    write_record(released, "stop.json", after)
    write_record(released, "turn_on_for.json", after)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_change_reopens_only_the_records_it_exercises(released, monkeypatch, capsys):
    """Tenet 9: a change to one adapter's module reopens that action's record and no other's, and a rerun of that
    suite alone completes the sign-off, the records then citing two package trees."""
    run = released.commit(f"{FAKE}/transport.py")
    write_record(released, "stop.json", run)
    write_record(released, "turn_on_for.json", run)
    fix = released.commit(f"{FAKE}/stop.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "(stop.json: reopened by a change since its run (stop.py): rerun, or" in capsys.readouterr().out
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["stop"]}
    write_record(released, "stop.json", fix)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert f"signed off by record {RECORDS}" in capsys.readouterr().out


def test_a_shared_module_or_a_suite_that_is_no_actions_reopens_on_any_change(released, monkeypatch, capsys):
    """A helper serves every adapter, so its change reopens every record; a suite with no adapter (`config_entry.json`)
    has no module to compare, so any change to the package reopens it."""
    run = released.commit(f"{FAKE}/stop.py")
    for name in ("stop.json", "turn_on_for.json", "config_entry.json"):
        write_record(released, name, run)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    capsys.readouterr()
    released.commit(f"{FAKE}/stop.py")
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["config_entry", "stop"]}
    released.commit(f"{FAKE}/transport.py")
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["config_entry", "stop", "turn_on_for"]}


def test_a_suite_that_is_no_actions_is_reopened_by_any_adapters_change_though_it_ran_an_action(
    released, monkeypatch, capsys
):
    """The rig writes `config_entry.json` with the action it ran (`stop` here): it stands for no action's change."""
    run = released.commit(f"{FAKE}/stop.py")
    for name in ("stop.json", "turn_on_for.json", "config_entry.json"):
        write_record(released, name, run)
    assert json.loads((released.path / RECORDS / "config_entry.json").read_text())["action"] == "stop"
    released.commit(f"{FAKE}/turn_on_for.py")  # another adapter's module
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["config_entry", "turn_on_for"]}
    write_record(released, "config_entry.json", released.git("rev-parse", "HEAD").strip())
    write_record(released, "turn_on_for.json", released.git("rev-parse", "HEAD").strip())
    released.commit(f"{FAKE}/stop.py")  # its own action's module
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["config_entry", "stop"]}


def test_a_no_call_changed_row_keeps_the_records_of_the_actions_it_names(released, monkeypatch, capsys):
    """A refactor of a shared helper reopens every record; a row naming an action keeps that action's record, from
    the row's commit on, and signs off nothing by itself."""
    run = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", run)
    write_record(released, "turn_on_for.json", run)
    refactor = released.commit(f"{FAKE}/transport.py")
    released.commit(MANUAL, manual_file(signoff(refactor, passed=None, actions=["stop"])))
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["turn_on_for"]}
    released.commit(MANUAL, manual_file(signoff(refactor, passed=None, actions=["stop", "turn_on_for"])))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert f"signed off by record {RECORDS}" in capsys.readouterr().out
    # A later change to stop's own module is past what the row vouched for.
    released.commit(f"{FAKE}/stop.py")
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["stop"]}


def test_a_row_vouches_only_for_the_change_its_commit_made(released, monkeypatch, capsys):
    """A row carries a record across its own commit's change, never across an earlier one it didn't see; a second
    row carries it across the next."""
    run = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", run)
    write_record(released, "turn_on_for.json", run)
    released.commit(f"{FAKE}/turn_on_for.py")  # a call change nobody vouched for
    trivial = released.commit(f"{FAKE}/transport.py")
    both = ["stop", "turn_on_for"]
    released.commit(MANUAL, manual_file(signoff(trivial, passed=None, actions=both)))
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["turn_on_for"]}
    write_record(released, "turn_on_for.json", trivial)
    second = released.commit(f"{FAKE}/transport.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    capsys.readouterr()
    rows = (signoff(trivial, passed=None, actions=both), signoff(second, passed=None, actions=both))
    released.commit(MANUAL, manual_file(*rows))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_an_adapter_changed_since_the_release_needs_a_record(released, monkeypatch, capsys):
    """A new or changed adapter is another adapter's module to every existing record, so those stand; it still needs a
    record of its own before the records sign off."""
    run = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", run)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    capsys.readouterr()
    added = released.commit(f"{FAKE}/turn_on_for.py")
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["turn_on_for"]}
    write_record(released, "turn_on_for.json", added)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_rename_reopens_by_both_names(released, monkeypatch, capsys):
    run = released.commit(f"{FAKE}/transport.py", "helper\n" * 20)
    write_record(released, "stop.json", run)
    write_record(released, "turn_on_for.json", run)
    released.git("mv", f"{FAKE}/transport.py", f"{FAKE}/wire.py")
    released.git("commit", "-qm", "rename")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "(transport.py, wire.py)" in capsys.readouterr().out


def test_json_and_reruns_exclude_each_other():
    with pytest.raises(SystemExit):
        cr.main(["--signoffs", "--json", "--reruns"])


def test_no_adapter_module_imports_another_adapters():
    """What `stands` rests on: a record holds through a change to another adapter's module only because no adapter
    module uses another's code. Code two adapters share lives in a module that is neither's, whose change reopens
    both (docs/evidence.md, Release gate)."""
    registry = AdapterRegistry.discover()
    for key in registry.integrations:
        own = cr.modules(registry, key)
        for module in own.values():
            source = (cr.REPO / cr.package(key) / module).read_text()
            assert not imported_modules(source, key) & (set(own.values()) - {module}), (
                f"{key}/{module} imports another adapter's module"
            )


def imported_modules(source: str, key: str) -> set[str]:
    """The package's modules the source imports, as paths inside the package: relative or absolute, a module or a
    name from one."""
    dotted = cr.package(key).rstrip("/").replace("/", ".")
    targets = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            base = f"{dotted}.{node.module or ''}".rstrip(".") if node.level == 1 else node.module or ""
            targets += [base, *(f"{base}.{alias.name}" for alias in node.names)]
        elif isinstance(node, ast.Import):
            targets += [alias.name for alias in node.names]
    return {target.removeprefix(f"{dotted}.").replace(".", "/") + ".py" for target in targets}


@pytest.mark.parametrize(
    "source",
    [
        "from .stop import x",
        "from . import stop",
        "from .stop import x as y",
        "from . import transport, stop",
        "from custom_components.deviceside.integrations.fake.stop import x",
        "import custom_components.deviceside.integrations.fake.stop",
    ],
)
def test_the_import_check_sees_each_way_to_import_a_module(source):
    assert "stop.py" in imported_modules(source, "fake")
    assert "stop.py" not in imported_modules("from .transport import stop_all", "fake")


def test_an_option_record_alone_is_no_record_of_the_plain_call(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop-fast.json", change)
    assert cr.main(["--signoffs", "--reruns"], registry(released, monkeypatch)) == 1
    assert json.loads(capsys.readouterr().out) == {"fake": ["stop"]}


def test_a_row_naming_actions_is_no_signoff_without_their_records(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    released.commit(MANUAL, manual_file(signoff(change, passed=None, actions=["stop"])))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "names actions, so it keeps their records and signs off no package" in capsys.readouterr().out


def test_actions_go_only_on_a_no_call_changed_row(fake_repo):
    row = signoff(fake_repo.commit()) | {"actions": ["stop"]}
    fake_repo.commit(MANUAL, manual_file(row))
    with pytest.raises(SystemExit, match="should not be valid"):
        cr.manual_signoffs("fake", ("a",))


def test_a_record_whose_tree_git_does_not_have_stands_only_at_heads_package(released, monkeypatch, capsys):
    """A run on a branch since deleted: its tree can't be compared, so it is reopened unless it is HEAD's."""
    released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", released.git("rev-parse", "HEAD").strip(), tree="0123456789ab")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "package 0123456789ab, which git doesn't have" in capsys.readouterr().out


def test_records_at_two_commits_with_one_tree_are_one_run(released, monkeypatch, capsys):
    """A rerun of one action on main completes a run made on the branch: the package is what they share."""
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    write_record(released, "turn_on_for.json", released.commit("README.md"))  # a later commit, the same package
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert f"signed off by record {RECORDS} at {change[:7]}" in capsys.readouterr().out


def test_a_format_1_record_is_no_signoff_and_is_named(released, monkeypatch, capsys):
    """A record converted from markdown names a run's devices, not each test's: a sign-off takes format 2 alone."""
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    write_record(released, "turn_on_for.json", change, tree=None)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "(turn_on_for.json: format 1, converted from markdown, so no sign-off: rerun with the rig)" in (
        capsys.readouterr().out
    )
    write_record(released, "turn_on_for.json", change)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_record_the_schema_rejects_stops_the_check_naming_it(released, monkeypatch):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    path = released.path / RECORDS / "stop.json"
    released.commit(f"{RECORDS}/stop.json", path.read_text().replace('"package"', '"tree"'))
    with pytest.raises(SystemExit, match=f"{RECORDS}/stop.json: 'package' is a required property"):
        cr.main(["--signoffs"], registry(released, monkeypatch))


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("_manual.json", "not the kind of file its name says"),  # a record under the manual sign-offs' name
        ("../../other/test-records/stop.json", "integration 'fake', in other's bundle"),
    ],
)
def test_a_file_of_the_wrong_kind_or_integration_stops_the_check(released, name, error):
    write_record(released, name, released.commit(f"{FAKE}/stop.py"))
    with pytest.raises(SystemExit, match=error):
        cr.manual_signoffs("fake", ("a",)) if name.startswith("_") else cr.record_signoff("other")


def test_a_json_file_named_with_another_leading_underscore_stops_the_check_naming_it(released):
    """Only `_manual.json` and `_facts.json` take the `_`: any other would drop out of the sign-off unseen."""
    write_record(released, "stop.json", released.commit(f"{FAKE}/stop.py"))
    write_record(released, "_stop.json", released.commit())
    with pytest.raises(SystemExit, match=f"{RECORDS}/_stop.json: a leading `_` is for _manual.json and _facts.json"):
        cr.record_signoff("fake")
    with pytest.raises(SystemExit, match="_stop.json"):
        cr.passing("fake", "stop")


@pytest.mark.parametrize(
    ("name", "change", "error"),
    [
        ("stop.json", {"action": "turn_on_for"}, "action 'turn_on_for', options None, but its name says action 'stop'"),
        (
            "stop.json",
            {"options": ["predicted_state"]},
            r"action .stop., options \['predicted_state'\], but .* options None",
        ),
        (
            "stop-predicted_state.json",
            {"options": None},
            r"action .stop., options None, but .* options \['predicted_state'\]",
        ),
        ("stop-predicted_state.json", {"options": ["other"]}, r"action .stop., options \['other'\], but its name says"),
    ],
)
def test_a_record_whose_action_or_options_its_name_contradicts_stops_the_check(fake_repo, name, change, error):
    """A record credits the action its name says: one that tested another would credit a call never made."""
    write_record(fake_repo, name, fake_repo.commit(), tree="0123456789ab")
    path = fake_repo.path / RECORDS / name
    data = {key: value for key, value in (json.loads(path.read_text()) | change).items() if value is not None}
    path.write_text(text(data))
    with pytest.raises(SystemExit, match=f"{RECORDS}/{name}: {error}"):
        cr.passing("fake", "stop")


def test_a_record_whose_name_and_options_agree_is_the_actions(fake_repo):
    """A suite named for no action (`config_entry`) is none's evidence, whatever action it ran."""
    for name in ("stop.json", "stop-predicted_state.json", "config_entry.json", "stop_x.json"):
        write_record(fake_repo, name, fake_repo.commit(), tree="0123456789ab")
    assert [path.name for path in cr.passing("fake", "stop")] == ["stop-predicted_state.json", "stop.json"]


def test_a_file_that_is_no_json_record_fails_by_name(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    released.commit(f"{RECORDS}/probe.md", "| Result | pass |\n")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert (
        "probe.md: not test records, which are JSON (docs/test-records.schema.json); probe findings go in"
        " internals.md, manual sign-offs in _manual.json" in capsys.readouterr().out
    )


def test_a_dotfile_in_the_records_folder_is_ignored(released):
    """An editor's or the OS's file (`.DS_Store`, a swap file) is no record, and blocks no sign-off."""
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    (released.path / RECORDS / ".DS_Store").write_bytes(b"\0")
    (released.path / RECORDS / ".stop.json.swp").write_text("x")
    signoff, why, reruns = cr.record_signoff("fake")
    assert signoff is not None and why is None and reruns == ()
    assert [path.name for path in cr.records("fake")] == ["stop.json"]


def test_a_folder_of_rig_records_still_signs_off(released):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    write_record(released, "turn_on_for.json", change)
    assert cr.record_signoff("fake")[0] is not None


def test_a_failing_record_fails_the_run_and_a_rerun_completes_it(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    write_record(released, "turn_on_for.json", change, result="fail")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "(turn_on_for.json fails)" in capsys.readouterr().out
    write_record(released, "turn_on_for.json", change)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_record_citing_a_commit_git_does_not_have_signs_off_by_its_tree(released, monkeypatch, capsys):
    """The squash case: the run's commit was on a deleted branch, but the package it tested is the one on main."""
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", "0" * 40, tree=tree_of(released, change))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert f"signed off by record {RECORDS} at 0000000" in capsys.readouterr().out


def test_records_citing_one_tree_at_different_lengths_are_one_run(released, monkeypatch):
    """The rig cites 12 hex digits; a full tree id is the same package, not a second version."""
    change = released.commit(f"{FAKE}/stop.py")
    full = released.git("rev-parse", f"{change}:custom_components/deviceside/integrations/fake")
    write_record(released, "stop.json", change, tree=full)
    write_record(released, "turn_on_for.json", change)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_record_whose_package_tree_differs_from_heads_is_no_signoff(released, monkeypatch, capsys):
    """A run before the last change, or on a branch that changed the package differently, tested other code."""
    before = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", before)
    released.commit(f"{FAKE}/transport.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert (
        "(stop.json: reopened by a change since its run (transport.py): rerun, or a no_call_changed row at the change's"
        " commit names the action; turn_on_for: changed since the last release, with no record)"
        in capsys.readouterr().out
    )


def test_a_reverted_change_is_unchanged(released, monkeypatch, capsys):
    released.commit(f"{FAKE}/stop.py")
    released.git("revert", "--no-edit", "HEAD")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert capsys.readouterr().out == "Since v0.1.0:\n"


def test_a_base_git_cannot_resolve_fails(released, monkeypatch):
    """A git error fails closed: an unresolvable base must not read as no change."""
    monkeypatch.setattr(cr, "last_release", lambda: "v9.9.9")
    with pytest.raises(RuntimeError, match="v9.9.9"):
        cr.main(["--signoffs"], registry(released, monkeypatch))


def test_a_manual_row_at_the_last_change_signs_off_naming_the_tester(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    released.commit(MANUAL, manual_file(signoff(change, passed=None)))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert capsys.readouterr().out.splitlines()[1] == (
        f"fake: changed at {change[:7]}; signed off by manual {MANUAL} row 1 at {change[:7]}, @a"
    )


def test_a_bare_no_call_changed_row_vouches_for_its_commit_alone(released, monkeypatch, capsys):
    """After an unsigned call change, a row on a later log-wording change must not sign off the call change too."""
    released.commit(f"{FAKE}/stop.py")  # a call change nobody tested
    wording = released.commit(f"{FAKE}/transport.py")
    released.commit(MANUAL, manual_file(signoff(wording, passed=None)))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "no_call_changed vouches for its commit's change alone; the package before it needs a sign-off" in (
        capsys.readouterr().out
    )


def test_a_manual_row_off_the_branch_signs_off_when_the_package_is_equal(released, monkeypatch):
    """Ancestry is no longer asked: a commit on a side branch holding the package as HEAD does is enough."""
    released.git("checkout", "-q", "-b", "side", "v0.1.0")
    side = released.commit(f"{FAKE}/stop.py", "x\n")
    released.git("checkout", "-q", "main")
    released.commit(f"{FAKE}/stop.py", "x\n")
    released.commit(MANUAL, manual_file(signoff(side)))
    assert side not in released.git("rev-list", "HEAD").split()
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_manual_row_at_a_commit_git_does_not_have_is_no_signoff(released, monkeypatch, capsys):
    released.commit(f"{FAKE}/stop.py")
    released.commit(MANUAL, manual_file(signoff("0" * 40)))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert f"({MANUAL} row 1 at 0000000: not in this checkout; cite a commit on main)" in capsys.readouterr().out


@pytest.mark.parametrize("tester", [cr.REPO_MAINTAINERS[0], cr.REPO_MAINTAINERS[0].upper(), "A"])
def test_a_repo_maintainer_may_sign_off_and_handles_ignore_case(released, monkeypatch, tester):
    change = released.commit(f"{FAKE}/stop.py")
    released.commit(MANUAL, manual_file(signoff(change, tester=tester)))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_manual_row_error_fails_the_gate(released, monkeypatch, capsys):
    sha = released.git("rev-parse", "HEAD")
    released.commit(MANUAL, manual_file(signoff(sha, tester="b")))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "tester @b is neither" in capsys.readouterr().err


CAVEAT = AdapterScope(caveat=Caveat(CaveatKind.UNTESTED_FIX, ISSUE))


def test_untested_fix_on_the_changed_adapter_stands_in_for_the_signoff(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch, stop=CAVEAT)) == 0
    assert capsys.readouterr().out.splitlines()[1] == (
        f"fake: changed at {change[:7]}; no sign-off, Untested fix stands in on every changed adapter: fake / stop"
    )


@pytest.mark.parametrize(
    "scope",
    [AdapterScope(caveat=Caveat(CaveatKind.UNMAINTAINED, ISSUE)), AdapterScope(domains=experimental("light"))],
    ids=["unmaintained", "experimental"],
)
def test_no_other_caveat_nor_the_flag_stands_in(released, monkeypatch, scope):
    released.commit(f"{FAKE}/stop.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch, stop=scope)) == 1


def test_a_caveat_on_an_unchanged_adapter_does_not(released, monkeypatch):
    released.commit(f"{FAKE}/stop.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch, turn_on_for=CAVEAT)) == 1


def test_a_change_to_a_shared_module_needs_the_caveat_on_every_adapter_of_the_package(released, monkeypatch, capsys):
    released.commit(f"{FAKE}/transport.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch, turn_on_for=CAVEAT)) == 1
    assert "no Untested fix on fake / stop" in capsys.readouterr().out
    assert cr.main(["--signoffs"], registry(released, monkeypatch, turn_on_for=CAVEAT, stop=CAVEAT)) == 0


def test_with_no_release_every_integration_is_changed(fake_repo, monkeypatch, capsys):
    fake_repo.commit(f"{FAKE}/stop.py", "")
    fake_repo.commit(f"{OTHER}/turn_on_for.py", "")
    reg = registry(fake_repo, monkeypatch, stop=CAVEAT)
    assert cr.main(["--signoffs", "--json"], reg) == 1
    assert json.loads(capsys.readouterr().out) == ["fake", "other"]


def test_json_lists_the_changed_integrations_without_a_signoff(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    released.commit(f"{OTHER}/stop.py")
    write_record(released, "stop.json", change)
    assert cr.main(["--signoffs", "--json"], registry(released, monkeypatch)) == 1
    out, err = capsys.readouterr()
    assert json.loads(out) == ["other"]
    assert err.startswith("error: other: changed at")


def test_the_step_summary_lists_the_signoffs(released, monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    released.commit(f"{FAKE}/stop.py")
    cr.main(["--signoffs"], registry(released, monkeypatch, stop=CAVEAT))
    assert summary.read_text().splitlines()[:3] == ["## Sign-offs", "", "- Since v0.1.0:"]


# The call for testers.


def test_notes_call_for_testers_of_unsigned_integrations_and_untested_fixes(released, monkeypatch, tmp_path):
    notes = tmp_path / "notes.md"
    released.commit(f"{OTHER}/turn_on_for.py")
    released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", released.git("rev-parse", "HEAD"))
    # No sign-off gate without --signoffs: an RC carries the unsigned change.
    assert cr.main(["--notes", str(notes)], registry(released, monkeypatch, turn_on_for=CAVEAT)) == 0
    text = notes.read_text()
    assert text.startswith("## Help us test\n")
    assert f"]({cr.DEVICE_REPORT})" in text
    assert "\n- Other\n" in text
    assert "- Fake\n" not in text
    assert text.endswith(
        "## 🔧 Untested fix\n\nThese ship a fix nobody could test before the release. If you use one,"
        f" please [report whether it works]({cr.DEVICE_REPORT}).\n\n- fake / turn_on_for\n"
    )


def test_notes_are_empty_with_nothing_to_test(released, monkeypatch, tmp_path):
    notes = tmp_path / "notes.md"
    assert cr.main(["--notes", str(notes)], registry(released, monkeypatch)) == 0
    assert notes.read_text() == ""


# The coverage check.


def classed(repo, monkeypatch, **scopes: AdapterScope) -> FakeRegistry:
    """fake naming classes hue, ikea and other, with the scopes given by action."""
    found = FakeRegistry(repo.path, monkeypatch, {(action, "fake"): scope for action, scope in scopes.items()})
    found.integrations["fake"] = replace(
        found.integrations["fake"],
        capability=lambda hass, target: "hue",
        classes=dict.fromkeys({"hue", "ikea", "other"}, ANYWHERE),
    )
    return found


def classes_record(repo, action: str, *cells, result: str = "pass") -> None:
    """A format 1 record of the action with a test per Capability cell: a list of classes passing, or (classes,
    result)."""
    tests = [old_test(classes=cell) if isinstance(cell, list) else old_test(None, cell[1], cell[0]) for cell in cells]
    path = repo.path / RECORDS / f"{action}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text(record_v1("fake", action, result=result, tests=tests)))


def classes_record_v2(repo, action: str, *tests: dict) -> None:
    path = repo.path / RECORDS / f"{action}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text(record_v2("fake", action, list(tests))))


SCOPE = AdapterScope(capabilities=verified("hue", "ikea") | experimental("other"))


def test_a_verified_class_no_format_1_record_reaches_is_a_gap(fake_repo, monkeypatch):
    classes_record(fake_repo, "turn_on_for", ["hue"], [])  # a dash: none
    classes_record(fake_repo, "stop", ["hue", "ikea"])  # a group's cell credits each class it lists
    found = classed(fake_repo, monkeypatch, turn_on_for=SCOPE, stop=SCOPE)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `ikea` is Verified but no record reaches it"]


def test_a_format_2_test_credits_its_devices_classes_and_a_group_test_each_members(fake_repo, monkeypatch):
    """A mixed group: each member's class is credited from its own entry; a null class credits none, a device's or a
    member's."""
    classes_record_v2(
        fake_repo,
        "turn_on_for",
        ran("light", device("LTA009", "1", "hue")),
        ran("light", device("LWA012", "1", None)),
        skipped(),
    )
    members = (device("LTA009", "1", "hue"), device("LCA001", "1", None), device("LWA012", "1", "ikea"))
    classes_record_v2(fake_repo, "stop", ran("light", *members, group=True, role="group"))
    found = classed(fake_repo, monkeypatch, turn_on_for=SCOPE, stop=SCOPE)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `ikea` is Verified but no record reaches it"]
    assert (cr.reached("fake", "turn_on_for"), cr.reached("fake", "stop")) == (
        {("hue", "light")},
        {("hue", "light"), ("ikea", "light")},
    )


def test_a_class_verified_on_some_domains_alone_needs_a_record_in_each(fake_repo, monkeypatch):
    """A record in one domain proves nothing about the class in another (core/scope.py, OnDomains)."""
    scope = AdapterScope(domains=verified("light", "switch"), capabilities=verified("hue", domains=("light", "switch")))
    classes_record_v2(fake_repo, "turn_on_for", ran("light", device("LTA009", "1", "hue")))
    found = classed(fake_repo, monkeypatch, turn_on_for=scope)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `hue` is Verified on switch but no record reaches it there"]
    # A manual row names no domain, so it covers each.
    sha = fake_repo.commit()
    (fake_repo.path / MANUAL).write_text(
        manual_file(signoff(sha, devices=(("LCA001", "hue"),), passed=("turn_on_for",)))
    )
    assert cr.coverage_gaps(found) == []


def test_a_manual_group_row_credits_its_members_classes(fake_repo, monkeypatch):
    (fake_repo.path / MANUAL).parent.mkdir(parents=True, exist_ok=True)
    sha = fake_repo.commit()
    members = (("LCA001", "hue"), ("LWA012", None), ("LTA009", "ikea"))
    (fake_repo.path / MANUAL).write_text(manual_file(signoff(sha, devices=members, passed=("stop",), group=True)))
    assert cr.manual_rows("fake", "stop") == [(True, list(members))]
    assert cr.reached("fake", "stop") == {("hue", None), ("ikea", None)}


def test_a_failing_record_reaches_nothing_and_a_manual_row_with_a_class_does(fake_repo, monkeypatch):
    classes_record(fake_repo, "turn_on_for", ["hue"], ["ikea"], result="fail")
    sha = fake_repo.commit()
    rows = [
        signoff(sha, devices=(("LCA001", "hue"),), passed=("turn_on_for", "stop")),
        signoff(sha, devices=(("LCA001", "ikea"),), passed=("stop",)),  # another action's: nothing here
        signoff(sha, passed=None),
    ]
    (fake_repo.path / MANUAL).write_text(manual_file(*rows))
    found = classed(fake_repo, monkeypatch, turn_on_for=SCOPE)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `ikea` is Verified but no record reaches it"]
    signoffs = [
        cr.SignOff("manual", f"{MANUAL} row {number}", sha[:7], "a", vouches=number == 3) for number in (1, 2, 3)
    ]
    assert cr.manual_signoffs("fake", ("a",), names_classes=True) == (signoffs, [])
    # An integration that names no classes takes no class; a row naming none, or no call changed, is fine.
    assert cr.manual_signoffs("fake", ("a",)) == (
        [signoffs[2]],
        [f"{MANUAL} row {number}: a class, but fake names no classes" for number in (1, 2)],
    )


def test_a_record_naming_a_class_on_an_integration_that_names_none_is_an_error(released, monkeypatch, capsys):
    """As a manual row's is: nothing there could have reached a class, so the record was read wrong."""
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.json", change)
    write_record(released, "turn_on_for.json", change)
    path = released.path / RECORDS / "turn_on_for.json"
    data = json.loads(path.read_text())
    data["tests"].append(ran("light", device("LTA009", "1", "hue"), role="light_dimmable"))
    path.write_text(text(data))
    error = f"{RECORDS}/turn_on_for.json test 2 (t[light_dimmable]): a class, but fake names no classes"
    assert cr.record_class_errors("fake") == [error]
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert f"error: {error}" in capsys.readouterr().err
    # Format 1 names its classes on the test; an integration that names classes takes them.
    classes_record(released, "stop", ["hue"])
    assert cr.record_class_errors("fake")[0].startswith(f"{RECORDS}/stop.json test 1 (t[r]): a class")
    assert cr.gates(classed(released, monkeypatch, stop=SCOPE, turn_on_for=SCOPE))[2] == []


def test_an_adapter_flagged_whole_or_an_integration_naming_no_classes_has_no_gap(fake_repo, monkeypatch):
    flagged = AdapterScope(domains=experimental("light"), capabilities=verified("hue"))
    assert cr.coverage_gaps(classed(fake_repo, monkeypatch, turn_on_for=flagged)) == []
    assert cr.coverage_gaps(FakeRegistry(fake_repo.path, monkeypatch, {("turn_on_for", "fake"): AdapterScope()})) == []


def test_signoffs_fail_on_a_gap(released, monkeypatch, capsys):
    classes_record(released, "turn_on_for", ["hue"])
    assert cr.main(["--signoffs"], classed(released, monkeypatch, turn_on_for=SCOPE)) == 1
    assert "error: fake turn_on_for: `ikea` is Verified but no record reaches it" in capsys.readouterr().err
