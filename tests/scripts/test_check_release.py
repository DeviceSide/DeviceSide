"""scripts/check_release.py: the coverage bar on every adapter, and no experimental adapter in a release."""

import ast
import json
import re
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from custom_components.deviceside.actions import discover
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.scope import AdapterScope, IntegrationInfo, experimental, reported, verified
from scripts import check_release as cr

# Every fake adapter is defined here, so this file is each one's module.
THIS_FILE = str(Path(__file__).relative_to(cr.REPO))


class FakeAdapter:
    def __init__(self, scope: AdapterScope):
        self.scope = scope


class FakeRegistry:
    def __init__(self, adapters: dict[tuple[str, str], AdapterScope], integrations=()):
        self._adapters = {key: FakeAdapter(scope) for key, scope in adapters.items()}
        for (action, integration), adapter in self._adapters.items():
            adapter.action, adapter.integration = action, integration
        self.integrations = {info.key: info for info in integrations}

    def matrix(self):
        yield "turn_off_for", "shelly", None
        for (action, integration), adapter in sorted(self._adapters.items()):
            yield action, integration, adapter


REGISTRY = FakeRegistry(
    {("turn_on_for", "shelly"): AdapterScope(), ("turn_on_for", "matter"): AdapterScope(experimental=True)}
)


def coverage(tmp_path: Path, covered: int, statements: int = 100) -> Path:
    path = tmp_path / "coverage.json"
    summary = {"covered_lines": covered, "num_statements": statements}
    path.write_text(json.dumps({"files": {THIS_FILE: {"summary": summary}}}))
    return path


def test_coverage_under_the_bar_is_an_error_experimental_or_not(tmp_path):
    data = json.loads(coverage(tmp_path, 94).read_text())
    assert cr.coverage_errors(REGISTRY, data) == [
        f"{THIS_FILE}: 94.0% line coverage, under 95% (code of matter / turn_on_for, shelly / turn_on_for)",
    ]
    assert cr.coverage_errors(REGISTRY, json.loads(coverage(tmp_path, 95).read_text())) == []
    assert cr.coverage_errors(REGISTRY, json.loads(coverage(tmp_path, 0, statements=0).read_text())) == []


def test_a_module_missing_from_coverage_is_an_error():
    [error] = cr.coverage_errors(FakeRegistry({("turn_on_for", "shelly"): AdapterScope()}), {"files": {}})
    assert "0.0% line coverage" in error


def test_main_prints_the_table_and_the_step_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert cr.main(["--coverage", str(coverage(tmp_path, 100))], REGISTRY) == 0
    assert capsys.readouterr().out.splitlines() == ["matter / turn_on_for  experimental", "shelly / turn_on_for"]
    assert summary.read_text().splitlines()[-2:] == [
        "| matter / turn_on_for | experimental |",
        "| shelly / turn_on_for |  |",
    ]


def test_release_fails_on_an_experimental_adapter(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert cr.main([], REGISTRY) == 0
    assert cr.main(["--release"], REGISTRY) == 1
    assert "matter / turn_on_for is experimental" in capsys.readouterr().err
    assert cr.main(["--release"], FakeRegistry({("turn_on_for", "shelly"): AdapterScope()})) == 0
    assert cr.main(["--coverage", str(coverage(tmp_path, 50))], REGISTRY) == 1


def test_release_passes_experimental_scope_items(monkeypatch):
    """Items behind the Experimental features option ship; only the adapter-level flag keeps code out."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    scope = AdapterScope(domains=verified("light") | experimental("switch"), capabilities=experimental("Light"))
    assert cr.main(["--release"], FakeRegistry({("turn_on_for", "shelly"): scope})) == 0


@pytest.mark.parametrize("argv", [[], ["--release"], ["--records"]])
def test_an_integration_that_failed_to_import_is_an_error(monkeypatch, capsys, argv):
    """Its adapters are missing from the registry, so no gate would see them."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    broken = IntegrationInfo(
        key="zha", title="zha", ha_domain="zha", maintainers=(), available=False, unavailable_reason="No module"
    )
    registry = FakeRegistry({("turn_on_for", "shelly"): AdapterScope(experimental=True)}, [broken])
    monkeypatch.setattr(cr, "record_errors", lambda registry, shared=None: [])
    assert cr.main(argv, registry) == 1
    assert "error: zha: failed to import (No module)" in capsys.readouterr().err.splitlines()


def test_a_real_import_failure_reaches_the_gate(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    registry = AdapterRegistry(discover(), ["custom_components.deviceside.integrations.missing"])
    assert cr.main([], registry) == 1
    assert "error: missing: failed to import" in capsys.readouterr().err


def test_main_reads_the_real_registry(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert cr.main([]) == 0
    assert "shelly / turn_on_for" in capsys.readouterr().out


PACKAGE = "custom_components/deviceside/integrations/fake"
ADAPTER = f"{PACKAGE}/turn_on_for.py"
CORE = "custom_components/deviceside/core"
ADAPTER_IMPORTS = (
    "from . import shared\nfrom .addressing import address\nfrom ..zha import zcl\nfrom ...actions.ramp import Ramp\n"
)


class FakeRecordsRegistry:
    """One adapter, fake / turn_on_for, whose class's module is the repository's adapter module."""

    def __init__(self, repo, monkeypatch, experimental: bool = False, scope: AdapterScope | None = None):
        module = types.ModuleType("fake_turn_on_for")
        module.__file__ = str(repo.path / ADAPTER)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        cls = type("FakeTurnOnFor", (FakeAdapter,), {"__module__": module.__name__})
        self.adapter = cls(scope or AdapterScope(experimental=experimental))
        self.adapter.action, self.adapter.integration = "turn_on_for", "fake"
        self.integrations = {"fake": IntegrationInfo(key="fake", title="Fake", ha_domain="fake", maintainers=("a",))}

    def matrix(self):
        yield "turn_on_for", "fake", self.adapter


def write_record(repo, name: str, commit: str | None, result: str | None = "pass") -> str:
    """Commit docs/integrations/fake/test-records/<name> citing the commit (or no commit), with the result (or no Result
    row), and return the new head."""
    source = f"rig run (`scripts/rig.py`), commit `{commit[:7]}`" if commit else "probe script"
    row = f"| Result | {result} |\n" if result else ""
    text = f"# Fake · turn_on_for\n\n| | |\n|---|---|\n{row}| Source | {source} |\n"
    return repo.commit(f"docs/integrations/fake/test-records/{name}", text)


@pytest.fixture
def tested(repo, monkeypatch):
    """The fake integration: its adapter, the helpers it imports, the group helper its package imports, a sibling
    adapter, an unrelated module, the core modules it reaches and some it doesn't, an action module and the package's
    constants, with a record citing them. Returns (repo, the commit the record cites)."""
    monkeypatch.setattr(cr, "REPO", repo.path)
    monkeypatch.setattr(cr, "BUNDLES", repo.path / "docs" / "integrations")
    init = (
        "from .groups import expand_group\nfrom .other import Other\nfrom .turn_on_for import FakeTurnOnFor\n"
        "from ...core.scope import IntegrationInfo\n\nADAPTERS = [FakeTurnOnFor, Other]\n"
    )
    scope = (
        "from typing import TYPE_CHECKING\n\nfrom ..const import DOMAIN\nfrom .models import Target\n\n"
        "if TYPE_CHECKING:\n    from .dispatcher import Dispatcher\n"
    )
    for path, text in [
        (f"{PACKAGE}/__init__.py", init),
        (f"{PACKAGE}/groups.py", "from .members import members\n"),
        (f"{PACKAGE}/members.py", ""),
        (f"{PACKAGE}/shared.py", "from . import nested\n"),
        (f"{PACKAGE}/nested.py", ""),
        (f"{PACKAGE}/addressing.py", "from ...core import scope\n"),
        (f"{PACKAGE}/other.py", "from .unrelated import thing\n"),
        (f"{PACKAGE}/unrelated.py", ""),
        (f"{CORE}/__init__.py", ""),
        (f"{CORE}/scope.py", scope),
        (f"{CORE}/models.py", ""),
        (f"{CORE}/dispatcher.py", ""),
        (f"{CORE}/unused.py", ""),
        ("custom_components/deviceside/actions/ramp.py", ""),
        ("custom_components/deviceside/const.py", ""),
        (ADAPTER, ADAPTER_IMPORTS),
    ]:
        tested_at = repo.commit(path, text)
    write_record(repo, "turn_on_for.md", tested_at)
    return repo, tested_at


def test_adapter_code_is_the_module_and_what_it_or_its_package_imports_bar_sibling_adapters(tested):
    repo, _ = tested
    code = cr.adapter_code(repo.path / ADAPTER)
    assert [str(path.relative_to(repo.path)) for path in code] == [
        f"{CORE}/__init__.py",
        f"{CORE}/models.py",
        f"{CORE}/scope.py",
        f"{PACKAGE}/__init__.py",
        f"{PACKAGE}/addressing.py",
        f"{PACKAGE}/groups.py",
        f"{PACKAGE}/members.py",
        f"{PACKAGE}/nested.py",
        f"{PACKAGE}/shared.py",
        ADAPTER,
    ]


@pytest.mark.parametrize("test", ["TYPE_CHECKING", "typing.TYPE_CHECKING"])
def test_core_code_under_type_checking_alone_is_not_the_adapters(tested, test):
    repo, _ = tested
    repo.commit(
        f"{CORE}/models.py", f"if {test}:\n    from .dispatcher import Dispatcher\nelse:\n    from .unused import x\n"
    )
    names = [path.name for path in cr.adapter_code(repo.path / ADAPTER)]
    assert "unused.py" in names
    assert "dispatcher.py" not in names


def test_the_bar_covers_every_module_of_the_adapters_code_bar_init(tested, monkeypatch):
    repo, _ = tested
    registry = FakeRecordsRegistry(repo, monkeypatch)
    files = {str(path.relative_to(repo.path)): 100 for path in cr.adapter_code(repo.path / ADAPTER)}
    files |= {
        f"{PACKAGE}/__init__.py": 0,
        f"{CORE}/__init__.py": 0,
        f"{PACKAGE}/members.py": 90,
        f"{CORE}/models.py": 94,
    }
    report = {"files": {name: {"summary": {"covered_lines": n, "num_statements": 100}} for name, n in files.items()}}
    assert cr.coverage_errors(registry, report) == [
        f"{CORE}/models.py: 94.0% line coverage, under 95% (code of fake / turn_on_for)",
        f"{PACKAGE}/members.py: 90.0% line coverage, under 95% (code of fake / turn_on_for)",
    ]


def test_a_sibling_adapter_the_adapter_imports_is_its_code(tested):
    repo, _ = tested
    repo.commit(ADAPTER, "from .other import Other\n")
    assert "other.py" in [path.name for path in cr.adapter_code(repo.path / ADAPTER)]


@pytest.mark.parametrize(
    ("path", "text", "name"),
    [
        (ADAPTER, "from .missing import thing\n", ".missing"),
        (f"{PACKAGE}/groups.py", "from . import gone\n", ".gone"),
        (ADAPTER, "from ...core.missing import thing\n", "...core.missing"),
        (f"{CORE}/scope.py", "from . import gone\n", ".gone"),
        (f"{PACKAGE}/groups.py", "from ...core import gone\n", "...core.gone"),
    ],
)
def test_an_import_adapter_code_cannot_resolve_raises_naming_it(tested, path, text, name):
    repo, _ = tested
    repo.commit(path, text)
    with pytest.raises(ValueError, match=rf"{path.rpartition('/')[2]}: can't resolve `from {re.escape(name)}`"):
        cr.adapter_code(repo.path / ADAPTER)


@pytest.mark.parametrize(
    ("path", "text", "name"),
    [
        (
            ADAPTER,
            "from custom_components.deviceside.core.scope import AdapterScope\n",
            "custom_components.deviceside.core.scope",
        ),
        (
            f"{PACKAGE}/groups.py",
            "import custom_components.deviceside.core.scope\n",
            "custom_components.deviceside.core.scope",
        ),
        (
            f"{CORE}/scope.py",
            "def f():\n    from custom_components.deviceside import const\n",
            "custom_components.deviceside",
        ),
        (ADAPTER, "from custom_components import deviceside\n", "custom_components.deviceside"),
    ],
)
def test_an_absolute_import_of_the_component_raises_naming_it(tested, path, text, name):
    repo, _ = tested
    repo.commit(path, text)
    with pytest.raises(ValueError, match=rf"{path.rpartition('/')[2]}: absolute import of `{re.escape(name)}`"):
        cr.adapter_code(repo.path / ADAPTER)


def test_an_absolute_import_of_another_package_is_not_the_components():
    assert cr.absolute_component_imports(ast.parse("import custom_components.deviceside_other").body[0]) == []


def test_a_change_to_the_packages_group_helper_stales_the_record(tested, monkeypatch):
    repo, _ = tested
    repo.commit(f"{PACKAGE}/members.py", "MEMBERS = 1\n")
    [error] = cr.record_errors(FakeRecordsRegistry(repo, monkeypatch))
    assert error.endswith(f"changed since: {PACKAGE}/members.py")


def test_records_are_the_action_and_its_options(tested):
    repo, sha = tested
    for name in ["turn_on_for-predicted_state.md", "turn_on_for_x.md", "turn_off_for.md", "color_modes.md"]:
        write_record(repo, name, sha)
    names = [path.name for path in cr.records("fake", "turn_on_for")]
    assert names == ["turn_on_for-predicted_state.md", "turn_on_for.md"]


def test_the_observed_calls_file_is_never_a_record(tested):
    """The rig keeps each integration's observed results in `_observed.md`, beside the records: no action's record
    check may read it, as no action is named with a leading underscore."""
    repo, sha = tested
    write_record(repo, "_observed.md", sha)
    actions = [action.key for action in discover()]
    assert actions
    assert "_observed.md" not in [path.name for name in actions for path in cr.records("fake", name)]


def test_a_record_as_new_as_the_code_passes(tested, monkeypatch):
    """Code the adapter doesn't reach may change: a sibling adapter's, core code it doesn't import or imports only for
    type checking, an action's, and the rest of the component."""
    repo, _ = tested
    for path in [
        f"{PACKAGE}/other.py",
        f"{CORE}/unused.py",
        f"{CORE}/dispatcher.py",
        "custom_components/deviceside/actions/ramp.py",
        "custom_components/deviceside/const.py",
    ]:
        repo.commit(path)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == []


@pytest.mark.parametrize(
    "changed",
    [ADAPTER, f"{PACKAGE}/nested.py", f"{PACKAGE}/__init__.py", f"{CORE}/scope.py", f"{CORE}/models.py"],
)
def test_a_change_to_the_adapters_code_after_its_record_is_an_error(tested, monkeypatch, changed):
    repo, sha = tested
    repo.commit(changed)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == [
        f"fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for.md cites {sha[:7]}; "
        f"changed since: {changed}"
    ]


FLAGGED = """from . import shared
from .addressing import address
from ..zha import zcl

scope = AdapterScope(  # the scope
    experimental=True, domains=DOMAINS, confirmable=True
)
ramp = ramp_scope(BRIGHTNESS, experimental=False)
"""


@pytest.mark.parametrize(
    "after",
    [
        FLAGGED.replace("experimental=True, ", ""),
        FLAGGED.replace(
            "scope = AdapterScope(  # the scope\n    experimental=True, domains=DOMAINS, confirmable=True\n)",
            "scope = AdapterScope(domains=DOMAINS, confirmable=True)  # the scope",
        ),
        FLAGGED.replace("experimental=True", "experimental=False").replace(", experimental=False)", ")"),
        FLAGGED.replace("experimental=True, ", 'unmaintained="https://github.com/o/r/issues/1", '),
        FLAGGED.replace("experimental=True, ", "unmaintained=None, "),
        FLAGGED.replace("experimental=True, ", 'stale_tests="https://github.com/o/r/issues/2", '),
    ],
    ids=["dropped", "reflowed", "set_and_dropped", "unmaintained_set", "unmaintained_none", "stale_tests_set"],
)
def test_a_change_to_the_flags_alone_leaves_the_record_fresh(tested, monkeypatch, after):
    repo, _ = tested
    sha = repo.commit(ADAPTER, FLAGGED)
    write_record(repo, "turn_on_for.md", sha)
    repo.commit(ADAPTER, after)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == []


@pytest.mark.parametrize(
    "after",
    [
        FLAGGED.replace("experimental=True, ", "").replace("confirmable=True", "confirmable=False"),
        FLAGGED.replace("experimental=True, ", "").replace("# the scope", "# the call"),
        FLAGGED.replace("experimental=True", "verified=True"),
        FLAGGED.replace("experimental=False", "experimental=load()"),
        FLAGGED.replace("experimental=True, ", "unmaintained=REASON, "),
    ],
    ids=["another_argument", "a_comment", "a_renamed_keyword", "a_computed_value", "unmaintained_computed"],
)
def test_a_change_beside_the_flag_is_still_a_change(tested, monkeypatch, after):
    repo, _ = tested
    sha = repo.commit(ADAPTER, FLAGGED)
    write_record(repo, "turn_on_for.md", sha)
    repo.commit(ADAPTER, after)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == [
        f"fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for.md cites {sha[:7]}; "
        f"changed since: {ADAPTER}"
    ]


INFO = 'INTEGRATION = IntegrationInfo(key="fake", title="Fake", max_concurrency=4)\n'
WITH_MAINTAINERS = INFO.replace('title="Fake", ', 'title="Fake", maintainers=("a",), ')


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (INFO, WITH_MAINTAINERS),
        (WITH_MAINTAINERS, WITH_MAINTAINERS.replace('("a",)', '("a", "b")')),
        (WITH_MAINTAINERS, INFO.replace("IntegrationInfo(", "IntegrationInfo(\n    ").replace("=4)", "=4,\n)")),
    ],
    ids=["added", "another_handle", "dropped_and_reflowed"],
)
def test_a_change_to_the_maintainers_alone_leaves_the_record_fresh(tested, monkeypatch, before, after):
    repo, _ = tested
    init = f"{PACKAGE}/__init__.py"
    sha = repo.commit(init, before)
    write_record(repo, "turn_on_for.md", sha)
    repo.commit(init, after)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == []


@pytest.mark.parametrize(
    "after",
    [WITH_MAINTAINERS.replace('("a",)', "HANDLES"), WITH_MAINTAINERS.replace('("a",)', '("a", 1)')],
    ids=["a_name", "a_non_handle"],
)
def test_maintainers_that_are_not_a_tuple_of_strings_are_a_change(tested, monkeypatch, after):
    repo, _ = tested
    init = f"{PACKAGE}/__init__.py"
    sha = repo.commit(init, INFO)
    write_record(repo, "turn_on_for.md", sha)
    repo.commit(init, after)
    [error] = cr.record_errors(FakeRecordsRegistry(repo, monkeypatch))
    assert error.endswith(f"changed since: {init}")


def test_code_the_check_cannot_parse_at_the_cited_commit_is_a_change(tested, monkeypatch):
    repo, _ = tested
    sha = repo.commit(ADAPTER, FLAGGED + "def broken(:\n")
    write_record(repo, "turn_on_for.md", sha)
    repo.commit(ADAPTER, FLAGGED)
    [error] = cr.record_errors(FakeRecordsRegistry(repo, monkeypatch))
    assert error.endswith(f"changed since: {ADAPTER}")


def test_a_module_new_since_the_record_is_a_change(tested, monkeypatch):
    repo, _ = tested
    repo.commit(f"{PACKAGE}/extra.py", "")
    repo.commit(f"{PACKAGE}/nested.py", "from . import extra\n")
    [error] = cr.record_errors(FakeRecordsRegistry(repo, monkeypatch))
    assert error.endswith(f"changed since: {PACKAGE}/extra.py, {PACKAGE}/nested.py")


def flag_reads(tree: ast.AST, flag: str = "experimental") -> list[int]:
    """Lines that read the flag: anything but a `<flag>=` argument or parameter, passing a parameter of that name
    straight on as `<flag>=<flag>`, or calling a bare helper of that name (`experimental(...)` from `core.scope`, which
    marks items Experimental and reads no flag)."""
    passed_on = {
        id(keyword.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == flag
    } | {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    return [
        node.lineno
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr == flag)
        or (isinstance(node, ast.Constant) and node.value == flag)
        or (isinstance(node, ast.MatchClass) and flag in node.kwd_attrs)
        or (
            isinstance(node, ast.Name)
            and node.id == flag
            and isinstance(node.ctx, ast.Load)
            and id(node) not in passed_on
        )
    ]


@pytest.mark.parametrize(
    ("code", "line"),
    [
        ("scope.experimental", 1),
        ("getattr(scope, 'experimental')", 1),
        ("def ramp(*, experimental):\n    return 1 if experimental else 2", 2),
        ("match scope:\n    case AdapterScope(experimental=True):\n        pass", 2),
    ],
)
def test_a_read_of_the_flag_is_found(code, line):
    assert flag_reads(ast.parse(code)) == [line]


def stray_flags(trees: list[ast.AST], flag: str = "experimental") -> list[int]:
    """Lines passing `<flag>=` to anything but `AdapterScope` or a bare-named helper taking that parameter: the check
    drops the argument as a no-op, so it must never reach outside code."""
    takers = {"AdapterScope", "IntegrationInfo"} | {
        node.name
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and any(arg.arg == flag for arg in node.args.args + node.args.kwonlyargs)
    }
    return [
        node.lineno
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(keyword.arg == flag for keyword in node.keywords)
        and not (isinstance(node.func, ast.Name) and node.func.id in takers)
    ]


@pytest.mark.parametrize(
    ("code", "strays"),
    [
        ("AdapterScope(experimental=True)", []),
        ("def ramp(*, experimental):\n    pass\nramp(experimental=False)", []),
        ("client.send(x, experimental=True)", [1]),
        ("def fade_scope(*, experimental):\n    pass\nclient.fade_scope(experimental=True)", [3]),
    ],
)
def test_a_stray_flag_is_found(code, strays):
    assert stray_flags([ast.parse(code)]) == strays


INTEGRATION_CODE = sorted((cr.REPO / "custom_components").rglob("*.py"))
# The one function reading `unmaintained` and `stale_tests`, setup's warning, and `maintainers`, registration's check:
# neither changes a call.
SETUP = cr.REPO / "custom_components" / "deviceside" / "__init__.py"
REGISTRATION = cr.REPO / "custom_components" / "deviceside" / "core" / "registry.py"
READERS = {
    "unmaintained": (SETUP, "warn_marked"),
    "stale_tests": (SETUP, "warn_marked"),
    "maintainers": (REGISTRATION, "check_maintainers"),
}


def without_reader(path: Path, flag: str) -> ast.Module:
    """The module's tree, less the one function allowed to read the flag."""
    tree = ast.parse(path.read_text())
    if READERS.get(flag, (None,))[0] == path:
        tree.body = [node for node in tree.body if getattr(node, "name", None) != READERS[flag][1]]
    return tree


@pytest.mark.parametrize("flag", cr.FLAGS)
def test_the_flags_only_reach_a_scope(flag):
    assert stray_flags([ast.parse(path.read_text()) for path in INTEGRATION_CODE], flag) == []


@pytest.mark.parametrize("flag", cr.FLAGS)
def test_no_call_reads_the_flags(flag):
    """The records check ignores the flags because no call reads them; a read would make them a change. Setup reads
    `unmaintained` and `stale_tests`, to warn, registration reads `maintainers`, to check them, and nothing else reads
    them.
    """
    reads = [
        f"{path.relative_to(cr.REPO)}:{line}"
        for path in INTEGRATION_CODE
        for line in flag_reads(without_reader(path, flag), flag)
    ]
    assert reads == []


@pytest.mark.parametrize("flag", READERS)
def test_the_one_reader_reads_its_flag(flag):
    """The exemptions above stay honest: setup is where the warning lives, registration where the check does."""
    path, function = READERS[flag]
    [reader] = [node for node in ast.parse(path.read_text()).body if getattr(node, "name", None) == function]
    assert flag_reads(reader, flag)


def test_every_record_of_the_adapter_must_be_new(tested, monkeypatch):
    repo, sha = tested
    write_record(repo, "turn_on_for-predicted_state.md", sha)
    repo.commit(ADAPTER)
    write_record(repo, "turn_on_for.md", repo.git("rev-parse", "HEAD"))
    [error] = cr.record_errors(FakeRecordsRegistry(repo, monkeypatch))
    assert error.startswith(
        "fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for-predicted_state.md cites"
    )


def test_a_record_citing_an_unmerged_branch_compares_trees(tested, monkeypatch):
    repo, sha = tested
    repo.git("checkout", "-q", "-b", "rig", sha)
    branch = repo.commit(f"{PACKAGE}/other.py")
    repo.git("checkout", "-q", "main")
    write_record(repo, "turn_on_for.md", branch)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == []


def test_a_failing_git_diff_stops_the_check(tested, monkeypatch):
    repo, _ = tested
    real = cr.git
    monkeypatch.setattr(cr, "git", lambda *args: real(*args) if args[0] != "diff" else real("diff", "no-such-ref"))
    with pytest.raises(SystemExit, match="git diff .* failed"):
        cr.record_errors(FakeRecordsRegistry(repo, monkeypatch))


def test_a_missing_unciting_or_unknown_record_is_an_error(tested, monkeypatch):
    repo, _ = tested
    registry = FakeRecordsRegistry(repo, monkeypatch)
    write_record(repo, "turn_on_for.md", None)
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for.md cites no commit"
    ]
    write_record(repo, "turn_on_for.md", "0" * 40)
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for.md cites commit 0000000, "
        "which git can't find"
    ]
    repo.git("rm", "-q", "docs/integrations/fake/test-records/turn_on_for.md")
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: no test record docs/integrations/fake/test-records/turn_on_for.md"
    ]


def test_each_option_of_the_scope_needs_its_record(tested, monkeypatch):
    repo, sha = tested
    registry = FakeRecordsRegistry(repo, monkeypatch)
    registry.adapter.scope = AdapterScope(options=frozenset({"predicted_state", "soft_off"}))
    write_record(repo, "turn_on_for-soft_off.md", sha)
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: no test record docs/integrations/fake/test-records/turn_on_for-predicted_state.md"
    ]
    write_record(repo, "turn_on_for-predicted_state.md", sha)
    repo.git("rm", "-q", "docs/integrations/fake/test-records/turn_on_for.md")
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: no test record docs/integrations/fake/test-records/turn_on_for.md"
    ]


def test_a_fresh_record_that_did_not_pass_is_an_error(tested, monkeypatch):
    repo, tested_at = tested
    registry = FakeRecordsRegistry(repo, monkeypatch)
    write_record(repo, "turn_on_for.md", tested_at, result="fail")
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for.md did not pass (result: fail)"
    ]
    write_record(repo, "turn_on_for.md", tested_at, result=None)
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for.md has no readable Result row"
    ]
    write_record(repo, "turn_on_for.md", tested_at)
    assert cr.record_errors(registry) == []


def test_every_record_of_the_adapter_must_pass(tested, monkeypatch):
    repo, tested_at = tested
    write_record(repo, "turn_on_for-predicted_state.md", tested_at, result="fail")
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == [
        "fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for-predicted_state.md "
        "did not pass (result: fail)"
    ]


def test_a_failing_record_of_an_experimental_or_unproven_adapter_is_exempt(tested, monkeypatch):
    repo, tested_at = tested
    write_record(repo, "turn_on_for.md", tested_at, result="fail")
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch, experimental=True)) == []
    registry = FakeRecordsRegistry(repo, monkeypatch)
    registry.adapter.scope = AdapterScope(domains=reported("light"))
    assert cr.record_errors(registry) == []


def test_an_experimental_adapter_is_exempt(tested, monkeypatch):
    repo, _ = tested
    repo.commit(ADAPTER)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch, experimental=True)) == []


@pytest.mark.parametrize(
    "scope",
    [
        AdapterScope(domains=experimental("light")),
        AdapterScope(domains=reported("light")),
        AdapterScope(domains=verified("light"), capabilities=experimental("Light") | reported("CCT")),
    ],
)
def test_an_adapter_with_no_verified_call_needs_no_record(tested, monkeypatch, scope):
    repo, _ = tested
    registry = FakeRecordsRegistry(repo, monkeypatch)
    repo.git("rm", "-q", "docs/integrations/fake/test-records/turn_on_for.md")
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: no test record docs/integrations/fake/test-records/turn_on_for.md"
    ]
    registry.adapter.scope = scope
    assert cr.record_errors(registry) == []


def test_main_fails_on_a_stale_record(tested, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    repo, _ = tested
    registry = FakeRecordsRegistry(repo, monkeypatch)
    assert cr.main(["--records"], registry) == 0
    repo.commit(ADAPTER)
    assert cr.main([], registry) == 0
    assert cr.main(["--records"], registry) == 1
    assert "changed since" in capsys.readouterr().err


def test_every_rig_record_in_the_repo_cites_a_commit_the_check_can_read():
    """The rig writes the Source row (scripts/rig.py) and --records parses it: a change to either breaks this."""
    found = [
        path for path in cr.BUNDLES.glob("*/test-records/*.md") if path.read_text().count("rig run (`scripts/rig.py")
    ]
    assert found
    assert [path.name for path in found if not cr.CITED_COMMIT.search(path.read_text())] == []
    assert [path.name for path in found if cr.result(path) is None] == []


# Retests and Stale tests: an adapter with no Verified call.

UNPROVEN = AdapterScope(domains=reported("light"))
MANUAL = "docs/integrations/fake/test-records/_manual.md"
REPORT_ISSUE = "https://github.com/DeviceSide/DeviceSide/issues/9"


def manual(*rows: str) -> str:
    return "# Fake · manual retests\n\nProse is ignored.\n\n" + "\n".join([*cr.MANUAL_HEADER, *rows]) + "\n"


def manual_row(commit: str, tester: str = "a", passed: str = "`turn_on_for`") -> str:
    return f"| 2026-11-11 | `{commit[:7]}` | @{tester} | `LCA001`, `SNSPL-10` | {passed} |"


def unproven(tested, monkeypatch, scope: AdapterScope = UNPROVEN) -> tuple:
    """The fake adapter with no Verified call and no record. Returns (repo, registry, the commit its code is at)."""
    repo, sha = tested
    repo.git("rm", "-q", "docs/integrations/fake/test-records/turn_on_for.md")
    repo.git("commit", "-q", "-m", "drop the record")
    return repo, FakeRecordsRegistry(repo, monkeypatch, scope=scope), sha


@pytest.mark.parametrize(
    ("scope", "needs"),
    [
        (AdapterScope(), False),  # Verified: its records gate it
        (AdapterScope(domains=reported("light")), True),
        (AdapterScope(domains=reported("light"), experimental=True), False),  # in RCs only
        (AdapterScope(domains=experimental("light")), False),  # nothing ships on
        (AdapterScope(domains=reported("light"), capabilities=experimental("Light")), False),
        (AdapterScope(domains=reported("light"), capabilities=experimental("Light") | reported("CCT")), True),
    ],
)
def test_an_adapter_with_a_shipping_call_and_no_verified_one_needs_a_retest(scope, needs):
    assert cr.needs_retest(scope) is needs


def test_an_adapter_never_retested_is_untested(tested, monkeypatch):
    _, registry, _ = unproven(tested, monkeypatch)
    assert cr.retest_errors(registry) == ([], ["fake / turn_on_for"])
    # No record is asked of it, as before.
    assert cr.record_errors(registry) == []


def test_a_manual_line_by_a_maintainer_at_the_code_is_a_retest(tested, monkeypatch):
    repo, registry, sha = unproven(tested, monkeypatch)
    repo.commit(MANUAL, manual(manual_row(sha)))
    assert cr.retest_errors(registry) == ([], [])
    assert cr.fresh_retest(registry.adapter, cr.manual_retests("fake", ("a",))[0]) == f"{MANUAL}:7"


def test_a_manual_line_older_than_the_code_or_for_another_action_is_no_retest(tested, monkeypatch):
    repo, registry, sha = unproven(tested, monkeypatch)
    repo.commit(MANUAL, manual(manual_row(sha, passed="`turn_off_for`")))
    assert cr.retest_errors(registry) == ([], ["fake / turn_on_for"])
    repo.commit(MANUAL, manual(manual_row(sha)))
    repo.commit(ADAPTER)
    assert cr.retest_errors(registry) == ([], ["fake / turn_on_for"])


def test_a_manual_line_out_of_format_or_by_a_non_maintainer_is_an_error(tested, monkeypatch):
    repo, registry, sha = unproven(tested, monkeypatch)
    bad = f"| 2026-11-11 | {sha[:7]} | @a | LCA001 | turn_on_for |"
    repo.commit(MANUAL, manual(bad, manual_row(sha, tester="b")))
    errors, untested = cr.retest_errors(registry)
    assert errors == [
        f"{MANUAL}:7: not a row of `{cr.MANUAL_HEADER[0]}`: {bad}",
        f"{MANUAL}:8: tester @b is not a maintainer of fake",
    ]
    assert untested == ["fake / turn_on_for"]
    assert cr.main(["--records"], registry) == 1


def write_report(repo, version: str, worked: list[str], item: str = "light") -> None:
    report = {
        "integration": "fake",
        "model": "LCA001",
        "item": item,
        "firmware": "1.0",
        "deviceside": version,
        "worked": worked,
        "issue": REPORT_ISSUE,
    }
    repo.commit("docs/integrations/fake/devices.yaml", yaml.safe_dump({"reports": [report]}))


def test_an_accepted_working_report_at_a_tag_of_the_code_is_a_retest(tested, monkeypatch):
    repo, registry, sha = unproven(tested, monkeypatch)
    repo.git("tag", "v0.2.0rc1", sha)
    write_report(repo, "0.2.0rc1", ["turn_on_for"])
    assert cr.retest_errors(registry) == ([], [])
    repo.commit(ADAPTER)
    assert cr.retest_errors(registry) == ([], ["fake / turn_on_for"])


@pytest.mark.parametrize(("version", "worked"), [("0.9.0", ["turn_on_for"]), ("0.2.0rc1", [])])
def test_a_report_at_an_unknown_version_or_not_working_is_no_retest(tested, monkeypatch, version, worked):
    repo, registry, sha = unproven(tested, monkeypatch)
    repo.git("tag", "v0.2.0rc1", sha)
    write_report(repo, version, worked)
    assert cr.retest_errors(registry) == ([], ["fake / turn_on_for"])


@pytest.mark.parametrize(
    "scope",
    [UNPROVEN, AdapterScope(domains=reported("light") | experimental("cover"))],
    ids=["not_held", "experimental"],
)
def test_a_report_on_an_item_the_adapter_does_not_ship_is_no_retest(tested, monkeypatch, scope):
    """Proof follows the call: a report on a cover can't retest a changed light call."""
    repo, registry, sha = unproven(tested, monkeypatch, scope)
    repo.git("tag", "v0.2.0rc1", sha)
    write_report(repo, "0.2.0rc1", ["turn_on_for"], item="cover")
    assert cr.retest_errors(registry) == ([], ["fake / turn_on_for"])


def test_a_fresh_passing_record_is_a_retest(tested, monkeypatch):
    repo, registry, sha = unproven(tested, monkeypatch)
    write_record(repo, "turn_on_for.md", sha, result="fail")
    assert cr.retest_errors(registry) == ([], ["fake / turn_on_for"])
    write_record(repo, "turn_on_for.md", sha)
    assert cr.retest_errors(registry) == ([], [])


def test_a_release_needs_an_untested_adapter_marked_stale_tests(tested, monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    repo, registry, sha = unproven(tested, monkeypatch)
    notes = tmp_path / "notes.md"
    assert cr.main(["--records"], registry) == 0
    assert "fake / turn_on_for  untested since its code changed" in capsys.readouterr().out
    # The RC cut lists it before it is marked, so a report at the RC can retest it, and passes.
    assert cr.main(["--records", "--notes", str(notes)], registry) == 0
    assert notes.read_text().endswith("\n- fake / turn_on_for\n")
    capsys.readouterr()
    assert cr.main(["--release", "--notes", str(notes)], registry) == 1
    assert "fake / turn_on_for changed since its last retest" in capsys.readouterr().err
    assert notes.read_text().endswith("\n- fake / turn_on_for\n")

    registry.adapter.scope = replace(UNPROVEN, stale_tests=REPORT_ISSUE)
    assert cr.main(["--release", "--notes", str(notes)], registry) == 0
    assert "fake / turn_on_for  stale tests" in capsys.readouterr().out
    assert notes.read_text().startswith("## ⚠️ Stale tests\n")
    assert f"]({cr.DEVICE_REPORT})" in notes.read_text()
    assert notes.read_text().endswith("\n- fake / turn_on_for\n")

    # A retest clears the mark, so the release asks for it gone.
    repo.commit(MANUAL, manual(manual_row(sha)))
    assert cr.main(["--release"], registry) == 1
    assert "fake / turn_on_for sets stale_tests but has a fresh retest" in capsys.readouterr().err


def test_every_manual_line_in_the_repo_is_in_format():
    """`_manual.md` files are written by hand, so the real ones are held to the format too."""
    registry = AdapterRegistry.discover()
    errors = [
        error for key, info in registry.integrations.items() for error in cr.manual_retests(key, info.maintainers)[1]
    ]
    assert errors == []


# Shared code proof: a run of one integration's record proves a core/ change for every adapter that reaches it.

MODELS = f"{CORE}/models.py"
PICK = '"""Models."""\n\n\ndef pick(value):\n    if value:\n        return 1\n    return 2\n'


class SharedRegistry(FakeRecordsRegistry):
    """The fake adapter, and the same adapter class under a second integration, `other`, whose record covers core."""

    def __init__(self, repo, monkeypatch, scope: AdapterScope | None = None, other: AdapterScope | None = None):
        super().__init__(repo, monkeypatch, scope=scope)
        self.other = type(self.adapter)(other or AdapterScope())
        self.other.action, self.other.integration = "turn_on_for", "other"
        self.integrations["other"] = IntegrationInfo(key="other", title="Other", ha_domain="other", maintainers=("b",))

    def matrix(self):
        yield "turn_on_for", "fake", self.adapter
        yield "turn_on_for", "other", self.other


def covering_record(repo, commit: str, rows: list[str], result: str = "pass") -> str:
    """Commit other's record citing the commit, with a Shared coverage table of the rows, and return the new head."""
    table = "\n".join([*cr.SHARED_HEADER, *rows])
    text = (
        f"# Other · turn_on_for\n\n| | |\n|---|---|\n| Result | {result} |\n"
        f"| Source | rig run (`scripts/rig.py`), commit `{commit[:7]}` |\n\n## Tests\n\n| a | b |\n\n"
        f"## Shared coverage\n\n{table}\n\n## Notes\n\n| not | coverage |\n"
    )
    return repo.commit("docs/integrations/other/test-records/turn_on_for.md", text)


@pytest.fixture
def shared(tested):
    """The fake record cites core/models.py as PICK. Returns (repo, that commit)."""
    repo, _ = tested
    sha = repo.commit(MODELS, PICK)
    write_record(repo, "turn_on_for.md", sha)
    return repo, sha


def stale_message(sha: str) -> list[str]:
    return [
        f"fake / turn_on_for: docs/integrations/fake/test-records/turn_on_for.md cites {sha[:7]}; "
        f"changed since: {MODELS}"
    ]


def checked(repo, monkeypatch, **scopes) -> list[str]:
    registry = SharedRegistry(repo, monkeypatch, **scopes)
    index, errors = cr.shared_coverage(registry)
    return cr.record_errors(registry, index) + errors


@pytest.mark.parametrize(
    ("after", "executed", "cleared"),
    [
        (PICK.replace("return 1", "return 3"), "1-7", True),
        (PICK.replace("return 1", "return 3"), "1-5, 7", False),
        # A multi-line statement counts as run when coverage.py marks any line of it.
        (PICK.replace("return 1", "return (\n            3\n        )"), "1-6, 9", True),
        # A comment, a blank line or a docstring needs nothing, but the run must have reached the module.
        (PICK.replace("    return 2", "    # two\n\n    return 2"), "4", True),
        (PICK.replace("Models.", "The models."), "4", True),
        # A deletion needs the code on each side of it run.
        (PICK.replace("    if value:\n        return 1\n", ""), "1-4", False),
        (PICK.replace("    if value:\n        return 1\n", ""), "4-5", True),
    ],
)
def test_a_core_change_another_integrations_run_covered_is_proven(shared, monkeypatch, after, executed, cleared):
    repo, sha = shared
    head = repo.commit(MODELS, after)
    covering_record(repo, head, [f"| `core/models.py` | {executed} |"])
    assert checked(repo, monkeypatch) == ([] if cleared else stale_message(sha))


def test_a_change_inside_the_package_is_never_cleared(shared, monkeypatch):
    repo, sha = shared
    head = repo.commit(f"{PACKAGE}/nested.py", "X = 1\n")
    covering_record(repo, head, ["| `core/models.py` | 1-7 |"])
    index = {f"{PACKAGE}/nested.py": [cr.SharedCoverage("r", head, frozenset({1}))]}
    assert not cr.shared_clears(sha, f"{PACKAGE}/nested.py", index)
    assert checked(repo, monkeypatch)[0].endswith(f"changed since: {PACKAGE}/nested.py")


@pytest.mark.parametrize(
    ("result", "other", "moved"),
    [
        ("fail", None, False),
        ("pass", AdapterScope(experimental=True), False),
        ("pass", AdapterScope(domains=reported("light")), False),
        # The run covered the module, but at code it has changed from since.
        ("pass", None, True),
    ],
)
def test_only_a_passing_released_verified_run_at_heads_module_covers(shared, monkeypatch, result, other, moved):
    repo, sha = shared
    head = repo.commit(MODELS, PICK.replace("return 1", "return 3"))
    covering_record(repo, head, ["| `core/models.py` | 1-8 |"], result=result)
    if moved:
        repo.commit(MODELS, PICK.replace("return 1", "return 4"))
    errors = checked(repo, monkeypatch, other=other)
    assert stale_message(sha)[0] in errors


def test_the_covering_runs_own_adapter_may_have_moved_on(shared, monkeypatch):
    repo, sha = shared
    head = repo.commit(MODELS, PICK.replace("return 1", "return 3"))
    covering_record(repo, head, ["| `core/models.py` | 1-7 |"])
    repo.commit(f"{PACKAGE}/nested.py", "X = 1\n")
    registry = SharedRegistry(repo, monkeypatch)
    index, _ = cr.shared_coverage(registry)
    assert cr.changed_since(sha, [MODELS], index) is None


def test_a_core_change_covered_clears_a_retest_too(shared, monkeypatch):
    repo, sha = shared
    repo.git("rm", "-q", "docs/integrations/fake/test-records/turn_on_for.md")
    repo.commit(MANUAL, manual(manual_row(sha)))
    registry = SharedRegistry(repo, monkeypatch, scope=UNPROVEN)
    head = repo.commit(MODELS, PICK.replace("return 1", "return 3"))
    assert cr.retest_errors(registry, cr.shared_coverage(registry)[0]) == ([], ["fake / turn_on_for"])
    covering_record(repo, head, ["| `core/models.py` | 1-7 |"])
    assert cr.retest_errors(registry, cr.shared_coverage(registry)[0]) == ([], [])


@pytest.mark.parametrize(
    "row",
    [
        "| `integrations/fake/nested.py` | 1-3 |",
        "| `core/models.py` | 5-3 |",
        "| `core/models.py` | |",
        "| core/models.py | 1 |",
    ],
)
def test_a_malformed_shared_coverage_row_is_an_error_and_covers_nothing(shared, monkeypatch, capsys, row):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    repo, sha = shared
    covering_record(repo, sha, [row])
    registry = SharedRegistry(repo, monkeypatch)
    index, errors = cr.shared_coverage(registry)
    assert index == {}
    assert errors == [
        f"docs/integrations/other/test-records/turn_on_for.md:16: not a row of `| Module | Executed lines |`: {row}"
    ]
    assert cr.main(["--records"], registry) == 1
    assert errors[0] in capsys.readouterr().err


def test_shared_coverage_reads_the_section_alone(shared, monkeypatch):
    repo, sha = shared
    covering_record(repo, sha, ["| `core/models.py` | 1-3, 5 |", "| `core/scope.py` | 2 |"])
    index, errors = cr.shared_coverage(SharedRegistry(repo, monkeypatch))
    source = "docs/integrations/other/test-records/turn_on_for.md"
    assert errors == []
    assert index == {
        MODELS: [cr.SharedCoverage(source, sha[:7], frozenset({1, 2, 3, 5}))],
        f"{CORE}/scope.py": [cr.SharedCoverage(source, sha[:7], frozenset({2}))],
    }


@pytest.mark.parametrize(
    ("before", "after", "headers"),
    [
        # An except clause is its own clause; a decorated def's header runs from its decorator.
        (
            "try:\n    x = 1\nexcept ValueError:\n    x = 2\n",
            "try:\n    x = 1\nexcept KeyError:\n    x = 2\n",
            [range(3, 4)],
        ),
        ("@a\ndef f(\n    y,\n):\n    return y\n", "@b\ndef f(\n    y,\n):\n    return y\n", [range(1, 5)]),
        (
            "match v:\n    case 1:\n        x = 1\n",
            "match v:\n    case 2:\n        x = 1\n",
            [range(2, 3)],
        ),
        ("x = 1\n", "x = 1  # one\n", [range(1, 2)]),
        ("x = 1\n# one\n", "x = 1\n# two\n", []),
    ],
)
def test_the_clauses_a_change_touches(repo, monkeypatch, before, after, headers):
    monkeypatch.setattr(cr, "REPO", repo.path)
    sha = repo.commit(MODELS, before)
    repo.commit(MODELS, after)
    assert cr.needed_headers(sha, MODELS) == headers


def test_a_module_head_cannot_parse_is_never_cleared(repo, monkeypatch):
    monkeypatch.setattr(cr, "REPO", repo.path)
    sha = repo.commit(MODELS, "x = 1\n")
    head = repo.commit(MODELS, "x = (\n")
    assert cr.needed_headers(sha, MODELS) is None
    assert not cr.shared_clears(sha, MODELS, {MODELS: [cr.SharedCoverage("r", head, frozenset({1}))]})
