"""scripts/check_release.py: the coverage bar on every adapter, and no experimental adapter in a release."""

import ast
import json
import sys
import types
from pathlib import Path

import pytest

from custom_components.deviceside.actions import discover
from custom_components.deviceside.core.scope import AdapterScope, experimental, reported, verified
from scripts import check_release as cr

# Every fake adapter is defined here, so this file is each one's module.
THIS_FILE = str(Path(__file__).relative_to(cr.REPO))


class FakeAdapter:
    def __init__(self, scope: AdapterScope):
        self.scope = scope


class FakeRegistry:
    def __init__(self, adapters: dict[tuple[str, str], AdapterScope]):
        self._adapters = {key: FakeAdapter(scope) for key, scope in adapters.items()}

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
        f"matter / turn_on_for: 94.0% line coverage of {THIS_FILE}, under 95%",
        f"shelly / turn_on_for: 94.0% line coverage of {THIS_FILE}, under 95%",
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
    assert summary.read_text().splitlines()[-2:] == ["| matter / turn_on_for | yes |", "| shelly / turn_on_for |  |"]


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


def test_main_reads_the_real_registry(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert cr.main([]) == 0
    assert "shelly / turn_on_for" in capsys.readouterr().out


PACKAGE = "custom_components/deviceside/integrations/fake"
ADAPTER = f"{PACKAGE}/turn_on_for.py"


class FakeRecordsRegistry:
    """One adapter, fake / turn_on_for, whose class's module is the repository's adapter module."""

    def __init__(self, repo, monkeypatch, experimental: bool = False):
        module = types.ModuleType("fake_turn_on_for")
        module.__file__ = str(repo.path / ADAPTER)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        cls = type("FakeTurnOnFor", (FakeAdapter,), {"__module__": module.__name__})
        self.adapter = cls(AdapterScope(experimental=experimental))
        self.adapter.action, self.adapter.integration = "turn_on_for", "fake"

    def matrix(self):
        yield "turn_on_for", "fake", self.adapter


def write_record(repo, name: str, commit: str | None, result: str | None = "pass") -> str:
    """Commit docs/test-records/fake/<name> citing the commit (or no commit), with the result (or no Result row), and
    return the new head."""
    source = f"rig run (`scripts/rig.py`), commit `{commit[:7]}`" if commit else "probe script"
    row = f"| Result | {result} |\n" if result else ""
    text = f"# Fake · turn_on_for\n\n| | |\n|---|---|\n{row}| Source | {source} |\n"
    return repo.commit(f"docs/test-records/fake/{name}", text)


@pytest.fixture
def tested(repo, monkeypatch):
    """The fake integration: its adapter, the helpers it imports, an unrelated module and a core one, with a record
    citing them. Returns (repo, the commit the record cites)."""
    monkeypatch.setattr(cr, "REPO", repo.path)
    monkeypatch.setattr(cr, "RECORDS", repo.path / "docs" / "test-records")
    for path, text in [
        (f"{PACKAGE}/__init__.py", "from .turn_on_for import FakeTurnOnFor\nfrom .other import Other\n"),
        (f"{PACKAGE}/shared.py", "from . import nested\n"),
        (f"{PACKAGE}/nested.py", ""),
        (f"{PACKAGE}/addressing.py", "from ...core import scope\n"),
        (f"{PACKAGE}/other.py", ""),
        ("custom_components/deviceside/core/scope.py", ""),
        (ADAPTER, "from . import shared\nfrom .addressing import address\nfrom ..zha import zcl\n"),
    ]:
        tested_at = repo.commit(path, text)
    write_record(repo, "turn_on_for.md", tested_at)
    return repo, tested_at


def test_adapter_code_is_the_module_and_what_it_imports_from_its_package(tested):
    repo, _ = tested
    code = cr.adapter_code(repo.path / ADAPTER)
    assert [path.name for path in code] == ["__init__.py", "addressing.py", "nested.py", "shared.py", "turn_on_for.py"]


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
    repo, _ = tested
    repo.commit(f"{PACKAGE}/other.py")
    repo.commit("custom_components/deviceside/core/scope.py")
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == []


@pytest.mark.parametrize("changed", [ADAPTER, f"{PACKAGE}/nested.py", f"{PACKAGE}/__init__.py"])
def test_a_change_to_the_adapters_code_after_its_record_is_an_error(tested, monkeypatch, changed):
    repo, sha = tested
    repo.commit(changed)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == [
        f"fake / turn_on_for: docs/test-records/fake/turn_on_for.md cites {sha[:7]}; changed since: {changed}"
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
    ],
    ids=["dropped", "reflowed", "set_and_dropped"],
)
def test_a_change_to_the_experimental_flag_alone_leaves_the_record_fresh(tested, monkeypatch, after):
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
    ],
    ids=["another_argument", "a_comment", "a_renamed_keyword", "a_computed_value"],
)
def test_a_change_beside_the_flag_is_still_a_change(tested, monkeypatch, after):
    repo, _ = tested
    sha = repo.commit(ADAPTER, FLAGGED)
    write_record(repo, "turn_on_for.md", sha)
    repo.commit(ADAPTER, after)
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == [
        f"fake / turn_on_for: docs/test-records/fake/turn_on_for.md cites {sha[:7]}; changed since: {ADAPTER}"
    ]


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


def flag_reads(tree: ast.AST) -> list[int]:
    """Lines that read `experimental`: anything but an `experimental=` argument or parameter, passing a parameter
    of that name straight on as `experimental=experimental`, or calling the bare `experimental(...)` helper from
    `core.scope`, which marks items Experimental and reads no flag."""
    passed_on = {
        id(keyword.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "experimental"
    } | {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    return [
        node.lineno
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr == "experimental")
        or (isinstance(node, ast.Constant) and node.value == "experimental")
        or (isinstance(node, ast.MatchClass) and "experimental" in node.kwd_attrs)
        or (
            isinstance(node, ast.Name)
            and node.id == "experimental"
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


def stray_flags(trees: list[ast.AST]) -> list[int]:
    """Lines passing `experimental=` to anything but `AdapterScope` or a bare-named helper taking that parameter: the
    check drops the argument as a no-op, so it must never reach outside code."""
    takers = {"AdapterScope"} | {
        node.name
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(arg.arg == "experimental" for arg in node.args.args + node.args.kwonlyargs)
    }
    return [
        node.lineno
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(keyword.arg == "experimental" for keyword in node.keywords)
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


def test_the_flag_only_reaches_a_scope():
    assert stray_flags([ast.parse(path.read_text()) for path in (cr.REPO / "custom_components").rglob("*.py")]) == []


def test_nothing_in_the_integration_reads_the_flag():
    """The records check ignores `experimental` because no runtime path reads it; a read would make it a change."""
    reads = [
        f"{path.relative_to(cr.REPO)}:{line}"
        for path in (cr.REPO / "custom_components").rglob("*.py")
        for line in flag_reads(ast.parse(path.read_text()))
    ]
    assert reads == []


def test_every_record_of_the_adapter_must_be_new(tested, monkeypatch):
    repo, sha = tested
    write_record(repo, "turn_on_for-predicted_state.md", sha)
    repo.commit(ADAPTER)
    write_record(repo, "turn_on_for.md", repo.git("rev-parse", "HEAD"))
    [error] = cr.record_errors(FakeRecordsRegistry(repo, monkeypatch))
    assert error.startswith("fake / turn_on_for: docs/test-records/fake/turn_on_for-predicted_state.md cites")


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
    assert cr.record_errors(registry) == ["fake / turn_on_for: docs/test-records/fake/turn_on_for.md cites no commit"]
    write_record(repo, "turn_on_for.md", "0" * 40)
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: docs/test-records/fake/turn_on_for.md cites commit 0000000, which git can't find"
    ]
    repo.git("rm", "-q", "docs/test-records/fake/turn_on_for.md")
    assert cr.record_errors(registry) == ["fake / turn_on_for: no test record in docs/test-records/fake/"]


def test_a_fresh_record_that_did_not_pass_is_an_error(tested, monkeypatch):
    repo, tested_at = tested
    registry = FakeRecordsRegistry(repo, monkeypatch)
    write_record(repo, "turn_on_for.md", tested_at, result="fail")
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: docs/test-records/fake/turn_on_for.md did not pass (result: fail)"
    ]
    write_record(repo, "turn_on_for.md", tested_at, result=None)
    assert cr.record_errors(registry) == [
        "fake / turn_on_for: docs/test-records/fake/turn_on_for.md has no readable Result row"
    ]
    write_record(repo, "turn_on_for.md", tested_at)
    assert cr.record_errors(registry) == []


def test_every_record_of_the_adapter_must_pass(tested, monkeypatch):
    repo, tested_at = tested
    write_record(repo, "turn_on_for-predicted_state.md", tested_at, result="fail")
    assert cr.record_errors(FakeRecordsRegistry(repo, monkeypatch)) == [
        "fake / turn_on_for: docs/test-records/fake/turn_on_for-predicted_state.md did not pass (result: fail)"
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
    repo.git("rm", "-q", "docs/test-records/fake/turn_on_for.md")
    assert cr.record_errors(registry) == ["fake / turn_on_for: no test record in docs/test-records/fake/"]
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
    found = [path for path in cr.RECORDS.glob("*/*.md") if path.read_text().count("rig run (`scripts/rig.py")]
    assert found
    assert [path.name for path in found if not cr.CITED_COMMIT.search(path.read_text())] == []
    assert [path.name for path in found if cr.result(path) is None] == []
