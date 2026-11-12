"""scripts/check_release.py: the coverage bar, a sign-off for each changed integration, and the call for testers."""

import json
import sys
import types
from pathlib import Path

import pytest

from custom_components.deviceside.actions import discover
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.scope import AdapterScope, Caveat, CaveatKind, IntegrationInfo
from scripts import check_release as cr

ISSUE = "https://github.com/DeviceSide/DeviceSide/issues/9"


class FakeAdapter:
    def __init__(self, scope: AdapterScope):
        self.scope = scope


class FakeRegistry:
    """Adapters by (action, integration), each of a class whose module is `<package>/<action>.py` under the root, and
    the integrations' infos, maintained by @a unless given."""

    def __init__(self, root: Path, monkeypatch, adapters: dict[tuple[str, str], AdapterScope], integrations=()):
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
        self.integrations |= {info.key: info for info in integrations}

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


@pytest.mark.parametrize("argv", [[], ["--signoffs"]])
def test_an_integration_that_failed_to_import_is_an_error(fake_repo, monkeypatch, capsys, argv):
    """Its adapters are missing from the registry, so no gate would see them."""
    broken = IntegrationInfo(
        key="zha", title="zha", ha_domain="zha", maintainers=(), available=False, unavailable_reason="No module"
    )
    fake_repo.commit()
    assert cr.main(argv, FakeRegistry(fake_repo.path, monkeypatch, {}, [broken])) == 1
    assert "error: zha: failed to import (No module)" in capsys.readouterr().err.splitlines()


def test_a_real_import_failure_reaches_the_gate(monkeypatch, capsys):
    registry = AdapterRegistry(discover(), ["custom_components.deviceside.integrations.missing"])
    assert cr.main([], registry) == 1
    assert "error: missing: failed to import" in capsys.readouterr().err


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


def test_the_bar_covers_every_module_under_core_and_integrations_bar_init(fake_repo, tmp_path):
    for module in [f"{CORE}/__init__.py", f"{CORE}/dispatcher.py", f"{HUE}/__init__.py", f"{HUE}/transport.py"]:
        fake_repo.commit(module, "")
    fake_repo.commit("custom_components/deviceside/actions/stop.py", "")
    report = {f"{CORE}/dispatcher.py": 94, f"{HUE}/transport.py": 95, "custom_components/deviceside/actions/stop.py": 0}
    assert cr.coverage_errors(json.loads(coverage(tmp_path / "c.json", report).read_text())) == [
        f"{CORE}/dispatcher.py: 94.0% line coverage, under 95%"
    ]


def test_a_module_missing_from_coverage_is_an_error(fake_repo):
    fake_repo.commit(f"{HUE}/transport.py", "")
    assert cr.coverage_errors({"files": {}}) == [f"{HUE}/transport.py: 0.0% line coverage, under 95%"]


def test_a_module_with_no_statements_is_covered(fake_repo):
    fake_repo.commit(f"{HUE}/const.py", "")
    empty = {"files": {f"{HUE}/const.py": {"summary": {"covered_lines": 0, "num_statements": 0}}}}
    assert cr.coverage_errors(empty) == []


def test_main_fails_under_the_bar(fake_repo, monkeypatch, tmp_path, capsys):
    fake_repo.commit(f"{HUE}/transport.py", "")
    registry = FakeRegistry(fake_repo.path, monkeypatch, {})
    assert cr.main(["--coverage", str(coverage(tmp_path / "c.json", {f"{HUE}/transport.py": 100}))], registry) == 0
    assert cr.main(["--coverage", str(coverage(tmp_path / "c.json", {f"{HUE}/transport.py": 50}))], registry) == 1
    assert "under 95%" in capsys.readouterr().err


# Records.

RECORDS = "docs/integrations/fake/test-records"


def write_record(repo, name: str, commit: str, result: str = "pass", integration: str = "fake") -> str:
    """Commit a record of the rig's format citing the commit, and return the new head."""
    text = (
        f"# Fake · {name}\n\n| | |\n|---|---|\n| Result | {result} |\n| Ran | 4 passed, 0 skipped |\n"
        f"| Source | rig run (`scripts/rig.py`), commit `{commit[:7]}` |\n"
    )
    return repo.commit(f"docs/integrations/{integration}/test-records/{name}", text)


@pytest.mark.parametrize("name", ["_facts.md", "_manual.md"])
def test_a_file_named_with_a_leading_underscore_is_never_a_record(fake_repo, name):
    """The rig's fact results (`_facts.md`) and the manual sign-offs sit beside the records; neither is one."""
    write_record(fake_repo, name, fake_repo.commit())
    assert cr.record_signoffs("fake") == []


def test_every_rig_record_in_the_repo_cites_a_commit_the_check_can_read():
    """The rig writes the Source and Result rows and --signoffs parses them: a change to either breaks this."""
    found = list(cr.BUNDLES.glob("*/test-records/[!_]*.md"))
    assert found
    assert [path.name for path in found if not cr.CITED_COMMIT.search(path.read_text())] == []
    assert [path.name for path in found if cr.result(path) is None] == []


# Manual sign-offs.

MANUAL = f"{RECORDS}/_manual.md"


def manual(*rows: str) -> str:
    return "# Fake · manual sign-offs\n\nProse is ignored.\n\n" + "\n".join([*cr.MANUAL_HEADER, *rows]) + "\n"


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
        for error in cr.manual_signoffs(key, (*info.maintainers, *cr.REPO_MAINTAINERS))[1]
    ]
    assert errors == []


# The release gate.

FAKE = "custom_components/deviceside/integrations/fake"
OTHER = "custom_components/deviceside/integrations/other"


@pytest.fixture
def released(fake_repo):
    """fake and other, each with two adapter modules and a helper, released as v0.1.0, with a later RC tag."""
    for package in (FAKE, OTHER):
        for module in ("__init__.py", "turn_on_for.py", "stop.py", "transport.py"):
            fake_repo.commit(f"{package}/{module}", "")
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
    line = f"fake: changed at {change[:7]}; no sign-off at or after it, and no Untested fix on fake / stop"
    assert out.splitlines() == ["Since v0.1.0:", line]
    assert err.splitlines() == [f"error: {line}"]


def test_a_passing_record_at_or_after_the_last_change_signs_off(released, monkeypatch, capsys):
    change = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", change)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0
    assert capsys.readouterr().out.splitlines()[1] == (
        f"fake: changed at {change[:7]}; signed off by record {RECORDS}/stop.md at {change[:7]}"
    )
    after = released.commit("README.md")  # a later commit outside the package
    write_record(released, "stop.md", after)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 0


def test_a_record_before_the_last_change_or_not_passing_is_no_signoff(released, monkeypatch, capsys):
    before = released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", before)
    last = released.commit(f"{FAKE}/transport.py")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert f"({RECORDS}/stop.md at {before[:7]}: predates the last change {last[:7]})" in capsys.readouterr().out
    write_record(released, "turn_on_for.md", released.git("rev-parse", "HEAD"), result="fail")
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1


def test_a_record_citing_a_commit_off_the_branch_is_no_signoff(released, monkeypatch, capsys):
    """Ancestry, not trees: a run on a branch that lacks the last change didn't test it."""
    released.git("checkout", "-q", "-b", "side", "v0.1.0")
    side = released.commit("side.txt")
    released.git("checkout", "-q", "main")
    released.commit(f"{FAKE}/stop.py")
    write_record(released, "stop.md", side)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    write_record(released, "stop.md", "0" * 40)  # one git can't find
    capsys.readouterr()
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert f"({RECORDS}/stop.md at 0000000: not in this checkout; cite a commit on main)" in capsys.readouterr().out


def test_a_signoff_whose_package_differs_from_heads_is_none(released, monkeypatch, capsys):
    """A run on a branch that changed the package again tested other code."""
    released.commit(f"{FAKE}/stop.py")
    released.git("checkout", "-q", "-b", "side")
    side = released.commit(f"{FAKE}/stop.py")
    released.git("checkout", "-q", "main")
    write_record(released, "stop.md", side)
    assert cr.main(["--signoffs"], registry(released, monkeypatch)) == 1
    assert f"({RECORDS}/stop.md at {side[:7]}: the package differs from HEAD's)" in capsys.readouterr().out


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
