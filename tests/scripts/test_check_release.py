"""scripts/check_release.py: the coverage bar, a sign-off for each changed integration, the classes' coverage check,
and the call for testers."""

import json
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

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
    """Commit a record of the rig's format citing the commit, and return the new head. Its Package row cites the
    package tree at the commit, or `tree` when given one, or none when `tree` is None."""
    if tree == "package":
        tree = tree_of(repo, commit, integration)
    package = f"| Package | `{tree}` |\n" if tree else ""
    text = (
        f"# Fake · {name}\n\n| | |\n|---|---|\n| Result | {result} |\n| Ran | 4 passed, 0 skipped |\n"
        f"| Source | rig run (`scripts/rig.py`), commit `{commit[:7]}` |\n{package}"
    )
    return repo.commit(f"docs/integrations/{integration}/test-records/{name}", text)


@pytest.mark.parametrize("name", ["_facts.md", "_manual.md"])
def test_a_file_named_with_a_leading_underscore_is_never_a_record(fake_repo, name):
    """The rig's fact results (`_facts.md`) and the manual sign-offs sit beside the records; neither is one."""
    write_record(fake_repo, name, fake_repo.commit(), tree=None)
    assert cr.record_signoff("fake") == (None, None)


def test_every_rig_record_in_the_repo_cites_a_commit_the_check_can_read():
    """The rig writes the Source and Result rows and --signoffs parses them: a change to either breaks this."""
    found = list(cr.BUNDLES.glob("*/test-records/[!_]*.md"))
    assert found
    assert [path.name for path in found if not cr.CITED_COMMIT.search(path.read_text())] == []
    assert [path.name for path in found if cr.result(path) is None] == []


# Manual sign-offs.

MANUAL = f"{RECORDS}/_manual.md"


def manual(*rows: str) -> str:
    return "# Fake · manual sign-offs\n\nProse is ignored.\n\n" + "\n".join([*cr.MANUAL_HEADER[:2], *rows]) + "\n"


def manual_row(commit: str, tester: str = "a", devices: str = "`LCA001`", passed: str = "`turn_on_for`") -> str:
    return f"| 2026-11-12 | `{commit[:7]}` | @{tester} | {devices} | {passed} |"


def test_a_manual_row_by_a_maintainer_or_repo_maintainer_is_a_signoff(fake_repo):
    sha = fake_repo.commit()
    fake_repo.commit(
        MANUAL, manual(manual_row(sha), manual_row(sha, tester="r", devices="-", passed="no call changed"))
    )
    found, errors = cr.manual_signoffs("fake", ("a", "r"))
    assert errors == []
    assert found == [
        cr.SignOff("manual", f"{MANUAL}:7", sha[:7], "a"),
        cr.SignOff("manual", f"{MANUAL}:8", sha[:7], "r"),
    ]


@pytest.mark.parametrize(
    ("devices", "passed"),
    [("LCA001", "`turn_on_for`"), ("-", "`turn_on_for`"), ("`LCA001`", "no call changed"), ("-", "no calls changed")],
)
def test_a_manual_row_out_of_format_is_an_error_and_no_signoff(fake_repo, devices, passed):
    sha = fake_repo.commit()
    bad = manual_row(sha, devices=devices, passed=passed)
    fake_repo.commit(MANUAL, manual(bad))
    assert cr.manual_signoffs("fake", ("a",)) == ([], [f"{MANUAL}:7: not a row of `{cr.MANUAL_HEADER[0]}`: {bad}"])


def test_a_manual_row_by_anyone_else_is_an_error_and_no_signoff(fake_repo):
    sha = fake_repo.commit()
    fake_repo.commit(MANUAL, manual(manual_row(sha, tester="b")))
    assert cr.manual_signoffs("fake", ("a",)) == (
        [],
        [f"{MANUAL}:7: tester @b is neither a maintainer of fake nor a repo one"],
    )


def test_every_manual_row_in_the_repo_is_in_format():
    """`_manual.md` files are written by hand, so the real ones are held to the format too."""
    registry = AdapterRegistry.discover()
    errors = [
        error
        for key, info in registry.integrations.items()
        for error in cr.manual_signoffs(key, (*info.maintainers, *cr.REPO_MAINTAINERS), info.capability is not None)[1]
    ]
    assert errors == []


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
    write_record(released, "stop.md", change)
    write_record(released, "turn_on_for.md", change)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert capsys.readouterr().out.splitlines()[1] == (
        f"fake: changed at {change[:7]}; signed off by record {RECORDS} at {change[:7]}"
    )
    after = released.commit("README.md")  # a later commit outside the package
    write_record(released, "stop.md", after)
    write_record(released, "turn_on_for.md", after)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_records_citing_different_trees_are_a_partial_run_and_no_signoff(released, monkeypatch, capsys):
    """A run of one action doesn't sign off the rest; rerunning the others completes the run."""
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", change)
    write_record(released, "turn_on_for.md", change)
    later = released.commit(f"{FAKE}/transport.py")
    write_record(released, "lifecycle.md", later)
    old, new = tree_of(released, change), tree_of(released, later)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert (
        f"records cover 2 package versions ({old}: 2, {new}: 1); a sign-off is one run of one package)"
        in capsys.readouterr().out
    )
    write_record(released, "stop.md", later)
    write_record(released, "turn_on_for.md", later)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_records_at_two_commits_with_one_tree_are_one_run(released, monkeypatch, capsys):
    """A rerun of one action on main completes a run made on the branch: the package is what they share."""
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", change)
    write_record(released, "turn_on_for.md", released.commit("README.md"))  # a later commit, the same package
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert f"signed off by record {RECORDS} at {change[:7]}" in capsys.readouterr().out


def test_a_record_without_a_package_row_is_no_signoff(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", change)
    write_record(released, "turn_on_for.md", change, tree=None)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert "(turn_on_for.md: no Package row: rerun with the rig)" in capsys.readouterr().out


def test_a_file_that_is_no_rig_record_fails_by_name(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", change)
    released.commit(f"{RECORDS}/probe.md", "| Result | pass |\n")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert (
        "probe.md: not rig records; probe findings go in internals.md, manual sign-offs in _manual.md"
        in capsys.readouterr().out
    )


def test_a_folder_of_rig_records_still_signs_off(released):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", change)
    write_record(released, "turn_on_for.md", change)
    assert cr.record_signoff("fake")[0] is not None


def test_a_failing_record_fails_the_run_and_a_rerun_completes_it(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", change)
    write_record(released, "turn_on_for.md", change, result="fail")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert f"(turn_on_for.md fails at package {tree_of(released, change)})" in capsys.readouterr().out
    write_record(released, "turn_on_for.md", change)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_record_citing_a_commit_git_does_not_have_signs_off_by_its_tree(released, monkeypatch, capsys):
    """The squash case: the run's commit was on a deleted branch, but the package it tested is the one on main."""
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", "0" * 40, tree=tree_of(released, change))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert f"signed off by record {RECORDS} at 0000000" in capsys.readouterr().out


def test_records_citing_one_tree_at_different_lengths_are_one_run(released, monkeypatch):
    """The rig cites 12 hex digits; a full tree id is the same package, not a second version."""
    change = released.commit(f"{FAKE}/stop.py")
    full = released.git("rev-parse", f"{change}:custom_components/deviceside/integrations/fake")
    write_record(released, "stop.md", change, tree=full)
    write_record(released, "turn_on_for.md", change)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_record_whose_package_tree_differs_from_heads_is_no_signoff(released, monkeypatch, capsys):
    """A run before the last change, or on a branch that changed the package differently, tested other code."""
    before = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", before)
    released.commit(f"{FAKE}/transport.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert f"({RECORDS} at package {tree_of(released, before)}: the package differs from HEAD's)" in (
        capsys.readouterr().out
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
    released.commit(MANUAL, manual(manual_row(change, tester="a", devices="-", passed="no call changed")))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert capsys.readouterr().out.splitlines()[1] == (
        f"fake: changed at {change[:7]}; signed off by manual {MANUAL}:7 at {change[:7]}, @a"
    )


def test_a_manual_row_off_the_branch_signs_off_when_the_package_is_equal(released, monkeypatch):
    """Ancestry is no longer asked: a commit on a side branch holding the package as HEAD does is enough."""
    released.git("checkout", "-q", "-b", "side", "v0.1.0")
    side = released.commit(f"{FAKE}/stop.py", "x\n")
    released.git("checkout", "-q", "main")
    released.commit(f"{FAKE}/stop.py", "x\n")
    released.commit(MANUAL, manual(manual_row(side)))
    assert side not in released.git("rev-list", "HEAD").split()
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_manual_row_at_a_commit_git_does_not_have_is_no_signoff(released, monkeypatch, capsys):
    released.commit(f"{FAKE}/stop.py")
    released.commit(MANUAL, manual(manual_row("0" * 40)))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert f"({MANUAL}:7 at 0000000: not in this checkout; cite a commit on main)" in capsys.readouterr().out


@pytest.mark.parametrize("tester", [cr.REPO_MAINTAINERS[0], cr.REPO_MAINTAINERS[0].upper(), "A"])
def test_a_repo_maintainer_may_sign_off_and_handles_ignore_case(released, monkeypatch, tester):
    change = released.commit(f"{FAKE}/stop.py")
    released.commit(MANUAL, manual(manual_row(change, tester=tester)))
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_manual_row_error_fails_the_gate(released, monkeypatch, capsys):
    sha = released.git("rev-parse", "HEAD")
    released.commit(MANUAL, manual(manual_row(sha, tester="b")))
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
    [AdapterScope(caveat=Caveat(CaveatKind.UNMAINTAINED, ISSUE)), AdapterScope(experimental=True)],
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
    write_record(released, "stop.md", change)
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
    write_record(released, "stop.md", released.git("rev-parse", "HEAD"))
    # No sign-off gate without --signoffs: an RC carries the unsigned change.
    assert cr.main(["--notes", str(notes)], registry(released, monkeypatch, turn_on_for=CAVEAT)) == 0
    text = notes.read_text()
    assert text.startswith("## Help us test\n")
    assert f"]({cr.DEVICE_REPORT})" in text
    assert "\n- Other\n" in text
    assert "- Fake\n" not in text
    assert text.endswith(
        "## ⚠️ Untested fix\n\nThese ship a fix nobody could test before the release. If you use one,"
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
        found.integrations["fake"], capability=lambda hass, target: "hue", classes=frozenset({"hue", "ikea", "other"})
    )
    return found


def classes_record(repo, action: str, *cells: str, result: str = "pass") -> None:
    """A record of the action whose Tests table has a test per Capability cell: passing, or (cell, result)."""
    rows = "".join(
        f"| `t{index}` | `light` (bulb) | {' | '.join((cell, 'pass') if isinstance(cell, str) else cell)} |\n"
        for index, cell in enumerate(cells)
    )
    path = repo.path / RECORDS / f"{action}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"| | |\n|---|---|\n| Result | {result} |\n\n| Test | Target | Capability | Result |\n{rows}")


SCOPE = AdapterScope(capabilities=verified("hue", "ikea") | experimental("other"))


def test_a_verified_class_no_record_reaches_is_a_gap(fake_repo, monkeypatch):
    classes_record(fake_repo, "turn_on_for", "`hue`", "-", ("`ikea`", "fail"))  # a dash or a failing test: none
    classes_record(fake_repo, "stop", "`hue`, `ikea`")  # a group's cell credits each class it lists
    found = classed(fake_repo, monkeypatch, turn_on_for=SCOPE, stop=SCOPE)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `ikea` is Verified but no record reaches it"]


def test_a_failing_record_reaches_nothing_and_a_manual_row_with_capabilities_does(fake_repo, monkeypatch):
    classes_record(fake_repo, "turn_on_for", "`hue`", "`ikea`", result="fail")
    sha = fake_repo.commit()
    rows = [
        "| Date | Commit | Tester | Devices | Capabilities | Passed |",
        "|---|---|---|---|---|---|",
        f"| 2026-11-12 | `{sha[:7]}` | @a | `LCA001` | `hue` | `turn_on_for`, `stop` |",
        f"| 2026-11-12 | `{sha[:7]}` | @a | `LCA001` | `ikea` | `stop` |",  # another action's: nothing here
        f"| 2026-11-12 | `{sha[:7]}` | @a | - | - | no call changed |",
    ]
    (fake_repo.path / MANUAL).write_text("\n".join(rows) + "\n")
    found = classed(fake_repo, monkeypatch, turn_on_for=SCOPE)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `ikea` is Verified but no record reaches it"]
    signoffs = [cr.SignOff("manual", f"{MANUAL}:{line}", sha[:7], "a") for line in (3, 4, 5)]
    assert cr.manual_signoffs("fake", ("a",), names_classes=True) == (signoffs, [])
    # An integration that names no classes takes no Capabilities cell.
    assert cr.manual_signoffs("fake", ("a",)) == (
        [],
        [f"{MANUAL}:{line}: a Capabilities cell, but fake names no classes" for line in (3, 4, 5)],
    )


def test_an_adapter_flagged_whole_or_an_integration_naming_no_classes_has_no_gap(fake_repo, monkeypatch):
    flagged = AdapterScope(experimental=True, capabilities=verified("hue"))
    assert cr.coverage_gaps(classed(fake_repo, monkeypatch, turn_on_for=flagged)) == []
    assert cr.coverage_gaps(FakeRegistry(fake_repo.path, monkeypatch, {("turn_on_for", "fake"): AdapterScope()})) == []


def test_signoffs_fail_on_a_gap(released, monkeypatch, capsys):
    classes_record(released, "turn_on_for", "`hue`")
    assert cr.main(["--signoffs"], classed(released, monkeypatch, turn_on_for=SCOPE)) == 1
    assert "error: fake turn_on_for: `ikea` is Verified but no record reaches it" in capsys.readouterr().err
