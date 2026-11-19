"""scripts/check_release.py: the coverage bar, a sign-off for each action whose calls changed, the classes' coverage
check, and the call for testers."""

import json
import subprocess
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
    Level,
    labs,
    verified,
)
from scripts import check_release as cr

from .conftest import from_template
from .record_files import (
    BLOB,
    bound,
    device,
    manual,
    old_test,
    ran,
    record_v1,
    record_v2,
    record_v3,
    signoff,
    skipped,
    text,
)

ANYWHERE = frozenset(
    {Platform.LIGHT, Platform.SWITCH, Platform.SCENE}
)  # a test class's domains: every one a test scope serves

ISSUE = "https://github.com/DeviceSide/DeviceSide/issues/9"


class FakeAdapter:
    def __init__(self, action: str, integration: str, scope: AdapterScope):
        self.action, self.integration, self.scope = action, integration, scope


class FakeRegistry:
    """Adapters by (action, integration), and the integrations' infos, each maintained by @a."""

    def __init__(self, adapters: dict[tuple[str, str], AdapterScope]):
        self.adapters = {key: FakeAdapter(*key, scope) for key, scope in adapters.items()}
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


def test_json_and_reruns_exclude_each_other():
    with pytest.raises(SystemExit):
        cr.main(["--signoffs", "--json", "--reruns"])


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


def test_main_fails_under_the_bar(fake_repo, tmp_path, capsys):
    touch(fake_repo, f"{HUE}/transport.py")
    registry = FakeRegistry({})
    assert cr.main(["--coverage", str(coverage(tmp_path / "c.json", {f"{HUE}/transport.py": 100}))], registry) == 0
    assert cr.main(["--coverage", str(coverage(tmp_path / "c.json", {f"{HUE}/transport.py": 50}))], registry) == 1
    assert "under 95%" in capsys.readouterr().err


# Transcripts.

FAKE = "custom_components/deviceside/integrations/fake"


def segment(action: str = "stop", call: str = "a", integration: str = "fake", reply=None) -> dict:
    """A transcript segment: one run of the action, its one wire call `call`."""
    targets = [["light.x", "light.x", False]]
    request = {"dropped": [], "own": None, "request": {}, "targets": targets}
    return {"action": action, "integration": integration, "request": request, "result": [], "wire": [[call, reply]]}


def pin(repo, action: str, *calls: str, integration: str = "fake", also: str | None = None) -> str:
    """Commit the action's transcript, a segment per call (with none, remove it), with a change to `also` (a source
    file) in the same commit; return the commit."""
    path = repo.path / cr.transcript_path(integration, action)
    if calls:
        path.parent.mkdir(parents=True, exist_ok=True)
        segments = sorted((segment(action, call, integration) for call in calls), key=json.dumps)
        path.write_text(json.dumps(segments, indent=1, sort_keys=True) + "\n")
    else:
        path.unlink()
    if also:
        touch(repo, also)
        (repo.path / also).write_text(f"{repo.git('rev-parse', 'HEAD')}\n")
    repo.git("add", "-A")
    repo.git("commit", "-qm", f"pin {integration} {action}")
    return repo.git("rev-parse", "HEAD")


def blob(repo, action: str, integration: str = "fake", rev: str = "HEAD") -> str:
    """The blob of the action's transcript at the revision, as evidence cites it."""
    return repo.git("rev-parse", f"{rev}:{cr.transcript_path(integration, action)}")


def test_segments_hold_when_every_old_segment_is_in_the_new_unchanged():
    old = [segment(call="a"), segment(call="b")]
    assert cr.segments_hold(old, [segment(call="b"), segment(call="c"), segment(call="a")])  # added, reordered
    assert cr.segments_hold(old, [dict(reversed(seg.items())) for seg in old])  # key order is no change
    assert not cr.segments_hold(old, [segment(call="a")])  # removed
    assert not cr.segments_hold(old, [segment(call="a"), segment(call="b", reply="ok")])  # a reply changed
    assert cr.segments_hold([], [segment()])


def test_a_transcript_is_a_blob_holding_a_list_of_segments(fake_repo):
    pin(fake_repo, "stop", "a")
    assert cr.transcript(blob(fake_repo, "stop")) == [segment()]
    for other in ("[]\n", "{}\n", "not json\n", "[1]\n"):
        fake_repo.commit("other.json", other)
        assert cr.transcript(fake_repo.git("rev-parse", "HEAD:other.json")) is None, other
    assert cr.transcript("0" * 40) is None  # git doesn't have it
    assert cr.transcript(fake_repo.git("rev-parse", "HEAD")) is None  # a commit, no blob


# Records.

RECORDS = "docs/integrations/fake/test-records"
MANUAL = f"{RECORDS}/_manual.json"


def write_record(
    repo, name: str, result: str = "pass", integration: str = "fake", calls: str | None = None, format_: int = 3
) -> str:
    """Commit a record of the suite, citing the commit before it (provenance), bound to HEAD's transcript of its
    action or to `calls` (format 3), to a package tree (2) or converted from markdown (1); return the new head."""
    action, *options = Path(name).stem.lstrip("_").split("-")
    if action == "config_entry":  # the rig names a suite that is no action's for the action it ran in it
        action, options = "stop", []
    commit = repo.git("rev-parse", "HEAD")
    if format_ == 1:
        data = record_v1(integration, action, result=result, commit=commit, options=options)
    elif format_ == 2:
        data = record_v2(integration, action, [ran("light")], result=result, commit=commit, options=options)
    else:
        calls = calls or blob(repo, action, integration)
        data = record_v3(
            integration, action, [ran("light")], result=result, commit=commit, calls=calls, options=options
        )
    return repo.commit(f"docs/integrations/{integration}/test-records/{name}", text(data))


def manual_file(*rows: dict) -> str:
    return text(manual("fake", *rows))


@pytest.mark.parametrize("name", ["_facts.json", "_manual.json"])
def test_a_file_named_with_a_leading_underscore_is_never_a_record(fake_repo, name):
    """The rig's fact results (`_facts.json`) and the manual sign-offs sit beside the records; neither is one."""
    fake_repo.commit()
    write_record(fake_repo, name, calls=BLOB)
    assert cr.records("fake") == []


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("_manual.json", "not the kind of file its name says"),  # a record under the manual sign-offs' name
        ("../../other/test-records/stop.json", "integration 'fake', in other's bundle"),
    ],
)
def test_a_file_of_the_wrong_kind_or_integration_stops_the_check(fake_repo, name, error):
    pin(fake_repo, "stop", "a")
    write_record(fake_repo, name, calls=BLOB)
    with pytest.raises(SystemExit, match=error):
        cr.manual_signoffs("fake", ("a",)) if name.startswith("_") else cr.suites("other", "stop")


def test_a_json_file_named_with_another_leading_underscore_stops_the_check_naming_it(fake_repo):
    """Only `_manual.json` and `_facts.json` take the `_`: any other would drop out of the sign-off unseen."""
    pin(fake_repo, "stop", "a")
    write_record(fake_repo, "stop.json")
    write_record(fake_repo, "_stop.json", calls=BLOB)
    with pytest.raises(SystemExit, match=f"{RECORDS}/_stop.json: a leading `_` is for _manual.json and _facts.json"):
        cr.records("fake")
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
    pin(fake_repo, "stop", "a")
    write_record(fake_repo, name)
    path = fake_repo.path / RECORDS / name
    data = {key: value for key, value in (json.loads(path.read_text()) | change).items() if value is not None}
    path.write_text(text(data))
    with pytest.raises(SystemExit, match=f"{RECORDS}/{name}: {error}"):
        cr.suites("fake", "stop")


def test_a_record_whose_name_and_options_agree_is_the_actions(fake_repo):
    """A suite named for no action (`config_entry`) is none's evidence, whatever action it ran."""
    pin(fake_repo, "stop", "a")
    for name in ("stop.json", "stop-predicted_state.json", "config_entry.json", "stop_x.json"):
        write_record(fake_repo, name, calls=BLOB)
    assert [path.name for path in cr.passing("fake", "stop")] == ["stop-predicted_state.json", "stop.json"]


def test_a_dotfile_in_the_records_folder_is_ignored(fake_repo):
    """An editor's or the OS's file (`.DS_Store`, a swap file) is no record, and blocks no sign-off."""
    pin(fake_repo, "stop", "a")
    write_record(fake_repo, "stop.json")
    (fake_repo.path / RECORDS / ".DS_Store").write_bytes(b"\0")
    (fake_repo.path / RECORDS / ".stop.json.swp").write_text("x")
    assert [path.name for path in cr.records("fake")] == ["stop.json"]
    assert cr.foreign_files("fake") == []


# Manual rows.


def test_a_manual_row_by_a_maintainer_or_repo_maintainer_is_a_row(fake_repo):
    sha = fake_repo.commit()
    fake_repo.commit(MANUAL, manual_file(signoff(sha, calls=bound("stop", blob="1" * 40)), signoff(sha, signed_by="r")))
    found, errors = cr.manual_signoffs("fake", ("a", "r"))
    assert errors == []
    assert found == [
        cr.Row(f"{MANUAL} row 1", sha[:7], "a", ("stop",), {"stop": "1" * 40}),
        cr.Row(f"{MANUAL} row 2", sha[:7], "r", ("turn_on_for",), bound("turn_on_for")),
    ]


def test_a_format_2_row_names_its_actions_and_binds_no_calls(fake_repo):
    fake_repo.commit(MANUAL, manual_file(signoff(passed=("stop",))))
    assert cr.manual_signoffs("fake", ("a",)) == ([cr.Row(f"{MANUAL} row 1", "1a2b3c4", "a", ("stop",), None)], [])


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"devices": ["LCA001"]}, "'LCA001' is not of type 'object'"),
        ({"devices": [{"model": "LCA001", "manufacturer": None}]}, "'class' is a required property"),
        ({"devices": []}, "should be non-empty"),
        ({"calls": {}}, "should be non-empty"),
        ({"no_call_changed": True}, "was unexpected"),
        ({"passed": ["stop"]}, "should not be valid"),  # format 2's, in a format 3 file
        ({"signed_by": "@a"}, "does not match"),
    ],
)
def test_a_manual_row_out_of_format_stops_the_check_naming_the_file(fake_repo, change, error):
    """`_manual.json` is written by hand: the schema holds it to the format, and a row it rejects is no sign-off."""
    fake_repo.commit(MANUAL, manual_file(signoff(fake_repo.commit()) | change))
    with pytest.raises(SystemExit, match=f"{MANUAL}: .*{error}"):
        cr.manual_signoffs("fake", ("a",))


def test_a_manual_row_by_anyone_else_is_an_error_and_no_signoff(fake_repo):
    sha = fake_repo.commit()
    fake_repo.commit(MANUAL, manual_file(signoff(sha, signed_by="b")))
    assert cr.manual_signoffs("fake", ("a",)) == (
        [],
        [f"{MANUAL} row 1: signer @b is neither a maintainer of fake nor a repo one"],
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


def build_released(repo):
    touch(repo, f"{FAKE}/stop.py", f"{FAKE}/transport.py", f"{CORE}/dispatcher.py")
    pin(repo, "stop", "a")
    pin(repo, "turn_on_for", "a")
    pin(repo, "turn_on_for", "a", integration="other")
    repo.git("tag", "v0.1.0")
    repo.commit()
    repo.git("tag", "v0.2.0rc1")  # an RC is never the last release


@pytest.fixture
def released(fake_repo, tmp_path_factory):
    """fake's stop and turn_on_for and other's turn_on_for, each with a transcript of one segment, and a package,
    released as v0.1.0, with a later RC tag."""
    from_template(fake_repo, build_released, tmp_path_factory)
    return fake_repo


def registry(**scopes: AdapterScope) -> FakeRegistry:
    """fake's two adapters, with the scopes given by action, and other's turn_on_for."""
    adapters = {(action, "fake"): scopes.get(action, AdapterScope()) for action in ("turn_on_for", "stop")}
    return FakeRegistry(adapters | {("turn_on_for", "other"): AdapterScope()})


@pytest.fixture
def gate(capsys):
    """Run `--signoffs` with the options given on `registry()` (or one passed), returning its exit, the printed
    output (a list of lines, or the JSON) and its errors."""

    def run(*options: str, on: FakeRegistry | None = None):
        code = cr.main(["--signoffs", *options], on or registry())
        out, err = capsys.readouterr()
        return code, json.loads(out) if options else out.splitlines(), err.splitlines()

    return run


def test_the_last_release_is_the_latest_release_tag_under_head(released):
    assert cr.last_release() == "v0.1.0"
    released.git("tag", "v0.0.9", "HEAD~1")
    assert cr.last_release() == "v0.1.0"


def test_an_unchanged_action_needs_no_signoff(released, gate):
    assert gate() == (0, ["Since v0.1.0:"], [])


def test_a_package_or_core_change_that_keeps_every_transcript_needs_no_signoff(released, gate):
    """Tenet 9: evidence follows the calls. A refactor that sends the same calls, in the package or `core/`, changes no
    action."""
    released.commit(f"{FAKE}/stop.py")
    released.commit(f"{FAKE}/transport.py")
    released.commit(f"{CORE}/dispatcher.py")
    assert gate() == (0, ["Since v0.1.0:"], [])


def test_an_added_segment_changes_no_action(released, gate):
    """A test added, or a new call path (a new class's own call), reopens nothing."""
    pin(released, "stop", "a", "b")
    assert gate() == (0, ["Since v0.1.0:"], [])


def test_a_changed_segment_with_no_signoff_fails(released, gate):
    change = pin(released, "stop", "b", also=f"{CORE}/dispatcher.py")
    line = f"fake / stop: calls changed at {change[:7]}; no sign-off (stop.json: no record), and no Untested fix"
    assert gate() == (1, ["Since v0.1.0:", line], [f"error: {line}"])
    assert gate("--reruns")[1] == {"fake": ["stop"]}
    assert gate("--json")[1] == ["fake"]


def test_a_format_3_record_bound_to_heads_transcript_signs_off(released, gate):
    change = pin(released, "stop", "b")
    write_record(released, "stop.json")
    assert gate() == (
        0,
        [
            "Since v0.1.0:",
            f"fake / stop: calls changed at {change[:7]}; signed off by record {RECORDS}/stop.json at {change[:7]}",
        ],
        [],
    )


def test_a_cosmetic_package_edit_keeps_a_manual_row(released, gate):
    """The Control4 case: a refactor that rewrites the package's source but sends the same calls keeps the row."""
    change = pin(released, "stop", "b")
    released.commit(MANUAL, manual_file(signoff(change, calls=bound("stop", blob=blob(released, "stop")))))
    signed = f"fake / stop: calls changed at {change[:7]}; signed off by manual {MANUAL} row 1 at {change[:7]}, @a"
    assert gate() == (0, ["Since v0.1.0:", signed], [])
    released.commit(f"{FAKE}/stop.py")
    released.commit(f"{FAKE}/transport.py")
    assert gate() == (0, ["Since v0.1.0:", signed], [])


def test_a_core_change_that_changes_a_segment_reopens_the_evidence(released, gate):
    """What the old core/ exemption missed: a shared module that changes a call reopens every action whose calls it
    changed, and no other."""
    pin(released, "stop", "b")
    pin(released, "turn_on_for", "b")
    write_record(released, "stop.json")
    released.commit(MANUAL, manual_file(signoff(calls=bound("turn_on_for", blob=blob(released, "turn_on_for")))))
    assert gate()[0] == 0
    change = pin(released, "stop", "c", also=f"{CORE}/dispatcher.py")
    code, lines, _ = gate()
    assert code == 1
    assert lines[1] == (
        f"fake / stop: calls changed at {change[:7]}; no sign-off (stop.json: reopened: 1 of its 1 call segments"
        " changed or gone since), and no Untested fix"
    )
    assert "signed off by manual" in lines[2]
    assert gate("--reruns")[1] == {"fake": ["stop"]}
    write_record(released, "stop.json")
    assert gate()[0] == 0


def test_an_added_test_keeps_the_evidence_when_the_release_had_its_segment(released, gate):
    pin(released, "stop", "a", "c")
    released.git("tag", "v0.2.0")
    pin(released, "stop", "b")
    write_record(released, "stop.json")
    pin(released, "stop", "b", "c")
    assert gate()[0] == 0


def test_a_segment_added_since_the_release_needs_evidence_that_ran_it(released, gate):
    """Decision 14: a changed action's evidence must hold every segment HEAD gained since the tag, added or changed."""
    pin(released, "stop", "b")
    write_record(released, "stop.json")
    pin(released, "stop", "b", "c")
    code, lines, _ = gate()
    assert code == 1
    assert "(stop.json: 1 of HEAD's call segments added or changed since v0.1.0 aren't in its calls)" in lines[1]
    assert gate("--reruns")[1] == {"fake": ["stop"]}
    write_record(released, "stop.json")
    assert gate()[0] == 0


@pytest.mark.parametrize("kind", ["record", "manual"])
def test_a_run_from_before_a_released_segment_changed_does_not_sign_off_its_change(released, gate, kind):
    """The audit's case: a run bound to {a}, a test adding s, a release shipping {a, s}, then a fix s -> t. The run
    stands at HEAD ({a, t} holds {a}) but never sent t."""
    tested = blob(released, "stop")
    pin(released, "stop", "a", "s")
    released.git("tag", "v0.2.0")
    pin(released, "stop", "a", "t")
    if kind == "record":
        write_record(released, "stop.json", calls=tested)
        source = "stop.json"
    else:
        released.commit(MANUAL, manual_file(signoff(calls=bound("stop", blob=tested))))
        source = f"{MANUAL} row 1"
    code, lines, _ = gate()
    assert code == 1
    assert f"({source}: 1 of HEAD's call segments added or changed since v0.2.0 aren't in its calls)" in lines[1]
    write_record(released, "stop.json")  # a run of {a, t}
    assert gate()[0] == 0


@pytest.mark.parametrize("now", [("b",), ("b", "d")], ids=["removed", "changed"])
def test_a_removed_or_changed_segment_reopens_the_evidence(released, gate, now):
    pin(released, "stop", "b", "c")
    released.commit(MANUAL, manual_file(signoff(calls=bound("stop", blob=blob(released, "stop")))))
    pin(released, "stop", *now)
    code, lines, _ = gate()
    assert code == 1
    assert f"({MANUAL} row 1: reopened: 1 of its 2 call segments changed or gone since)" in lines[1]


def test_a_run_on_a_squash_merged_branch_still_resolves(released, gate):
    """A blob is content-addressed: the branch's transcript, landed unchanged by a squash merge, is main's, even once
    the branch and its commits are gone."""
    released.git("checkout", "-q", "-b", "side")
    ran_at = pin(released, "stop", "b", also=f"{FAKE}/stop.py")
    tested = blob(released, "stop")
    released.git("checkout", "-q", "main")
    released.git("merge", "--squash", "side")
    released.git("commit", "-qm", "squash side")
    released.git("branch", "-D", "side")
    released.git("reflog", "expire", "--expire=now", "--all")
    released.git("gc", "-q", "--prune=now")
    with pytest.raises(subprocess.CalledProcessError):  # the run's commit is gone
        released.git("cat-file", "-t", ran_at)
    write_record(released, "stop.json", calls=tested)
    assert gate()[0] == 0


def test_evidence_citing_a_blob_git_does_not_have_stands_for_nothing(released, gate):
    pin(released, "stop", "b")
    write_record(released, "stop.json", calls="0" * 40)
    code, lines, _ = gate()
    assert code == 1
    assert "(stop.json: calls 000000000000, which git doesn't have as a transcript)" in lines[1]


def test_a_record_of_another_actions_transcript_does_not_stand(released, gate):
    pin(released, "stop", "b")
    write_record(released, "stop.json", calls=blob(released, "turn_on_for"))
    assert "stop.json: reopened: 1 of its 1 call segments changed or gone since" in gate()[1][1]


@pytest.mark.parametrize(
    ("format_", "why"),
    [(1, "format 1, converted from markdown"), (2, "format 2, bound to the package, not the calls")],
)
def test_a_format_1_or_2_record_is_no_signoff_and_is_named(released, gate, format_, why):
    """Format 2 binds to the package tree, so it credits classes and cards but never signs off: the action needs a run
    bound to its calls."""
    pin(released, "stop", "b")
    write_record(released, "stop.json", format_=format_)
    code, lines, _ = gate()
    assert code == 1
    assert f"(stop.json: {why})" in lines[1]
    assert gate("--reruns")[1] == {"fake": ["stop"]}
    write_record(released, "stop.json")
    assert gate()[0] == 0


def test_a_failing_record_is_no_signoff_and_a_rerun_completes_it(released, gate):
    pin(released, "stop", "b")
    write_record(released, "stop.json", result="fail")
    assert "(stop.json: fails)" in gate()[1][1]
    write_record(released, "stop.json")
    assert gate()[0] == 0


def test_a_failing_option_record_blocks_the_action(released, gate):
    """Decision 11: a failing option run isn't outvoted by a passing plain one."""
    pin(released, "stop", "b")
    write_record(released, "stop.json")
    write_record(released, "stop-fast.json", result="fail")
    code, lines, _ = gate()
    assert code == 1 and "(stop-fast.json: fails)" in lines[1]
    assert gate("--reruns")[1] == {"fake": ["stop-fast"]}


def test_an_option_record_alone_is_no_record_of_the_plain_call(released, gate):
    pin(released, "stop", "b")
    write_record(released, "stop-fast.json")
    assert gate("--reruns")[1] == {"fake": ["stop"]}


def test_each_of_the_actions_records_must_stand(released, gate):
    """An option's record is the action's too: a reopened one is rerun, though the plain record stands."""
    pin(released, "stop", "b")
    write_record(released, "stop-fast.json")
    pin(released, "stop", "c")
    write_record(released, "stop.json")
    assert gate("--reruns")[1] == {"fake": ["stop-fast"]}
    write_record(released, "stop-fast.json")
    assert gate()[0] == 0


def test_a_suite_that_is_no_actions_is_outside_the_gate(released, gate):
    """`config_entry.json` credits no action, so whatever it holds, it neither signs off nor blocks one."""
    pin(released, "stop", "b")
    write_record(released, "stop.json")
    write_record(released, "config_entry.json", result="fail", format_=2)
    assert gate()[0] == 0


def test_each_changed_action_takes_its_own_evidence(released, gate):
    """Per action, from any mix: a record for one, a row for another, and an unchanged one needs neither."""
    stop = pin(released, "stop", "b")
    write_record(released, "stop.json")
    turn_on = pin(released, "turn_on_for", "b")
    released.commit(
        MANUAL, manual_file(signoff(turn_on, calls=bound("turn_on_for", blob=blob(released, "turn_on_for"))))
    )
    code, lines, _ = gate()
    assert (code, lines[1:]) == (
        0,
        [
            f"fake / stop: calls changed at {stop[:7]}; signed off by record {RECORDS}/stop.json at {stop[:7]}",
            f"fake / turn_on_for: calls changed at {turn_on[:7]}; signed off by manual {MANUAL} row 1 at"
            f" {turn_on[:7]}, @a",
        ],
    )


def test_a_row_signs_off_only_the_actions_its_calls_name(released, gate):
    pin(released, "stop", "b")
    pin(released, "turn_on_for", "b")
    released.commit(MANUAL, manual_file(signoff(calls=bound("turn_on_for", blob=blob(released, "turn_on_for")))))
    assert gate("--reruns")[1] == {"fake": ["stop"]}


def test_a_format_2_row_signs_off_nothing(released, gate):
    pin(released, "stop", "b")
    released.commit(MANUAL, manual_file(signoff(passed=("stop",))))
    code, lines, _ = gate()
    assert code == 1
    assert f"({MANUAL} row 1: format 2, which names the actions it passed but not their calls)" in lines[1]


def test_a_rows_commit_is_provenance_and_unchecked(released, gate):
    """A row stands by its calls; the commit it cites may be one git doesn't have (a deleted branch's)."""
    pin(released, "stop", "b")
    released.commit(MANUAL, manual_file(signoff("0" * 40, calls=bound("stop", blob=blob(released, "stop")))))
    assert gate()[0] == 0


@pytest.mark.parametrize("signer", [cr.REPO_MAINTAINERS[0], cr.REPO_MAINTAINERS[0].upper(), "A"])
def test_a_repo_maintainer_may_sign_off_and_handles_ignore_case(released, gate, signer):
    pin(released, "stop", "b")
    released.commit(MANUAL, manual_file(signoff(signed_by=signer, calls=bound("stop", blob=blob(released, "stop")))))
    assert gate()[0] == 0


def test_a_manual_row_error_fails_the_gate(released, gate):
    released.commit(MANUAL, manual_file(signoff(signed_by="b")))
    code, _, err = gate()
    assert code == 1
    assert any("signer @b is neither" in line for line in err)


def test_a_file_that_is_no_json_record_fails_by_name(released, gate):
    released.commit(f"{RECORDS}/probe.md", "| Result | pass |\n")
    code, _, err = gate()
    assert code == 1
    assert err == [
        f"error: {RECORDS}: probe.md: not test records, which are JSON (docs/test-records.schema.json); probe findings"
        " go in internals.md, manual sign-offs in _manual.json"
    ]


def test_an_action_the_tag_has_no_transcript_of_is_changed(released, gate):
    """A new adapter, or one whose tests ran no call at the release, has no pinned calls to hold."""
    added = pin(released, "raise_brightness", "a")
    on = FakeRegistry({("stop", "fake"): AdapterScope(), ("raise_brightness", "fake"): AdapterScope()})
    code, lines, _ = gate(on=on)
    assert code == 1
    assert lines[1].startswith(f"fake / raise_brightness: calls changed at {added[:7]}; no sign-off")


def test_an_action_with_no_transcript_at_head_has_nothing_to_stand_on(released, gate):
    released.commit(MANUAL, manual_file(signoff(calls=bound("stop", blob=blob(released, "stop")))))
    removed = pin(released, "stop")
    code, lines, _ = gate()
    assert code == 1
    assert lines[1] == (
        f"fake / stop: calls changed at {removed[:7]}; no sign-off (tests/integrations/fake/calls/stop.json: none at"
        f" HEAD, so no unit test pins its calls) (stop.json: no record) ({MANUAL} row 1: HEAD has no transcript to"
        " hold its calls), and no Untested fix"
    )


def test_a_reverted_change_is_unchanged(released, gate):
    pin(released, "stop", "b")
    released.git("revert", "--no-edit", "HEAD")
    assert gate() == (0, ["Since v0.1.0:"], [])


def test_a_base_git_cannot_resolve_fails(released, monkeypatch):
    """A git error fails closed: an unresolvable base must not read as no change."""
    monkeypatch.setattr(cr, "last_release", lambda: "v9.9.9")
    with pytest.raises(RuntimeError, match="v9.9.9"):
        cr.main(["--signoffs"], registry())


CAVEAT = AdapterScope(caveat=Caveat(CaveatKind.UNTESTED_FIX, ISSUE))


def test_untested_fix_on_the_changed_adapter_stands_in_for_the_signoff(released, gate):
    change = pin(released, "stop", "b")
    code, lines, _ = gate(on=registry(stop=CAVEAT))
    assert (code, lines[1]) == (0, f"fake / stop: calls changed at {change[:7]}; no sign-off, Untested fix stands in")
    # Still the rig's to run.
    assert gate("--reruns", on=registry(stop=CAVEAT))[1] == {"fake": ["stop"]}


@pytest.mark.parametrize(
    "scope",
    [AdapterScope(caveat=Caveat(CaveatKind.UNMAINTAINED, ISSUE)), AdapterScope(domains=labs("light"))],
    ids=["unmaintained", "labs"],
)
def test_no_other_caveat_nor_the_flag_stands_in(released, gate, scope):
    pin(released, "stop", "b")
    assert gate(on=registry(stop=scope))[0] == 1


def test_a_caveat_on_an_unchanged_adapter_does_not(released, gate):
    pin(released, "stop", "b")
    assert gate(on=registry(turn_on_for=CAVEAT))[0] == 1


def test_with_no_release_or_no_released_transcript_standing_is_enough(fake_repo, gate):
    """With no tag's transcript to diff against, evidence that stands at HEAD signs off, an added segment and all."""
    pin(fake_repo, "stop", "a")
    write_record(fake_repo, "stop.json")
    pin(fake_repo, "stop", "a", "b")
    on = FakeRegistry({("stop", "fake"): AdapterScope()})
    assert gate(on=on)[0] == 0
    fake_repo.git("tag", "v0.1.0")
    pin(fake_repo, "raise_brightness", "a")
    write_record(fake_repo, "raise_brightness.json")
    pin(fake_repo, "raise_brightness", "a", "b")
    on = FakeRegistry({("stop", "fake"): AdapterScope(), ("raise_brightness", "fake"): AdapterScope()})
    code, lines, _ = gate(on=on)
    assert code == 0 and "fake / raise_brightness: calls changed" in lines[1] and "signed off by record" in lines[1]


def test_with_no_release_every_action_is_changed(fake_repo, gate):
    pin(fake_repo, "stop", "a")
    pin(fake_repo, "turn_on_for", "a")
    pin(fake_repo, "turn_on_for", "a", integration="other")
    write_record(fake_repo, "stop.json")
    code, found, _ = gate("--reruns", on=registry(turn_on_for=CAVEAT))
    assert (code, found) == (1, {"fake": ["turn_on_for"], "other": ["turn_on_for"]})
    assert gate("--json", on=registry(turn_on_for=CAVEAT))[1] == ["fake", "other"]


def test_the_step_summary_lists_the_signoffs(released, monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    pin(released, "stop", "b")
    cr.main(["--signoffs"], registry(stop=CAVEAT))
    lines = summary.read_text().splitlines()
    assert lines[:3] == ["## Sign-offs", "", "- Since v0.1.0:"]
    assert lines[3].startswith("- fake / stop: calls changed at ")


# The call for testers.


def test_notes_call_for_testers_of_unsigned_integrations_and_untested_fixes(released, tmp_path):
    notes = tmp_path / "notes.md"
    pin(released, "turn_on_for", "b", integration="other")
    pin(released, "stop", "b")
    write_record(released, "stop.json")
    # No sign-off gate without --signoffs: an RC carries the unsigned change.
    assert cr.main(["--notes", str(notes)], registry(turn_on_for=CAVEAT)) == 0
    text = notes.read_text()
    assert text.startswith("## Help us test\n")
    assert f"]({cr.DEVICE_REPORT})" in text
    assert "\n- Other\n" in text
    assert "- Fake\n" not in text
    assert text.endswith(
        "## 🔧 Untested fix\n\nThese ship a fix nobody could test before the release. If you use one,"
        f" please [report whether it works]({cr.DEVICE_REPORT}).\n\n- fake / turn_on_for\n"
    )


def test_notes_are_empty_with_nothing_to_test(released, tmp_path):
    notes = tmp_path / "notes.md"
    assert cr.main(["--notes", str(notes)], registry()) == 0
    assert notes.read_text() == ""


# The coverage check.


def classed(**scopes: AdapterScope) -> FakeRegistry:
    """fake naming classes hue, ikea and other, with the scopes given by action."""
    found = FakeRegistry({(action, "fake"): scope for action, scope in scopes.items()})
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


def classes_record_v3(repo, action: str, *tests: dict) -> None:
    path = repo.path / RECORDS / f"{action}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text(record_v3("fake", action, list(tests))))


SCOPE = AdapterScope(capabilities=verified("hue", "ikea") | labs("other"))


def test_a_verified_class_no_format_1_record_reaches_is_a_gap(fake_repo):
    classes_record(fake_repo, "turn_on_for", ["hue"], [])  # a dash: none
    classes_record(fake_repo, "stop", ["hue", "ikea"])  # a group's cell credits each class it lists
    found = classed(turn_on_for=SCOPE, stop=SCOPE)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `ikea` is Verified but no record reaches it"]


def test_a_test_credits_its_devices_classes_and_a_group_test_each_members(fake_repo):
    """A mixed group: each member's class is credited from its own entry; a null class credits none, a device's or a
    member's."""
    classes_record_v3(
        fake_repo,
        "turn_on_for",
        ran("light", device("LTA009", "1", "hue")),
        ran("light", device("LWA012", "1", None)),
        skipped(),
    )
    members = (device("LTA009", "1", "hue"), device("LCA001", "1", None), device("LWA012", "1", "ikea"))
    classes_record_v3(fake_repo, "stop", ran("light", *members, group=True, role="group"))
    found = classed(turn_on_for=SCOPE, stop=SCOPE)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `ikea` is Verified but no record reaches it"]
    assert (cr.reached("fake", "turn_on_for"), cr.reached("fake", "stop")) == (
        {("hue", "light")},
        {("hue", "light"), ("ikea", "light")},
    )


def test_a_format_2_record_still_credits_its_classes(fake_repo):
    """It binds no calls, so it signs off nothing, but what it reached it reached (verify, then trust)."""
    path = fake_repo.path / RECORDS / "stop.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text(record_v2("fake", "stop", [ran("light", device("LTA009", "1", "ikea"))])))
    assert cr.reached("fake", "stop") == {("ikea", "light")}


def test_a_class_verified_on_some_domains_alone_needs_a_record_in_each(fake_repo):
    """A record in one domain proves nothing about the class in another (core/scope.py, OnDomains)."""
    scope = AdapterScope(domains=verified("light", "switch"), capabilities=verified("hue", domains=("light", "switch")))
    classes_record_v3(fake_repo, "turn_on_for", ran("light", device("LTA009", "1", "hue")))
    found = classed(turn_on_for=scope)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `hue` is Verified on switch but no record reaches it there"]
    # A manual row names no domain, so it covers each.
    (fake_repo.path / MANUAL).write_text(manual_file(signoff(devices=(("LCA001", "hue"),), calls=bound("turn_on_for"))))
    assert cr.coverage_gaps(found) == []


def test_a_row_resting_on_reports_credits_its_class_and_signs_off(fake_repo):
    """Users' reports a maintainer signs off on cover a class as the maintainer's own hand test does."""
    scope = AdapterScope(capabilities=verified("hue"))
    issue = "https://github.com/DeviceSide/DeviceSide/issues/12"
    (fake_repo.path / MANUAL).parent.mkdir(parents=True, exist_ok=True)
    row = signoff(devices=(("LCA001", "hue"),), calls=bound("turn_on_for"), reports=[issue])
    (fake_repo.path / MANUAL).write_text(manual_file(row))
    assert cr.coverage_gaps(classed(turn_on_for=scope)) == []
    found = cr.Row(f"{MANUAL} row 1", "1a2b3c4", "a", ("turn_on_for",), bound("turn_on_for"))
    assert cr.manual_signoffs("fake", ("a",), names_classes=True) == ([found], [])


def test_a_manual_group_row_credits_its_members_classes(fake_repo):
    (fake_repo.path / MANUAL).parent.mkdir(parents=True, exist_ok=True)
    members = (("LCA001", "hue"), ("LWA012", None), ("LTA009", "ikea"))
    (fake_repo.path / MANUAL).write_text(manual_file(signoff(devices=members, calls=bound("stop"), group=True)))
    assert cr.manual_rows("fake", "stop") == [(True, list(members))]
    assert cr.reached("fake", "stop") == {("hue", None), ("ikea", None)}


def test_a_failing_record_reaches_nothing_and_a_manual_row_with_a_class_does(fake_repo):
    classes_record(fake_repo, "turn_on_for", ["hue"], ["ikea"], result="fail")
    rows = [
        signoff(devices=(("LCA001", "hue"),), calls=bound("turn_on_for", "stop")),
        signoff(devices=(("LCA001", "ikea"),), calls=bound("stop")),  # another action's: nothing here
        signoff(),
    ]
    (fake_repo.path / MANUAL).write_text(manual_file(*rows))
    found = classed(turn_on_for=SCOPE)
    assert cr.coverage_gaps(found) == ["fake turn_on_for: `ikea` is Verified but no record reaches it"]
    actions = (("turn_on_for", "stop"), ("stop",), ("turn_on_for",))
    signed = [
        cr.Row(f"{MANUAL} row {number}", "1a2b3c4", "a", named, bound(*named))
        for number, named in enumerate(actions, 1)
    ]
    assert cr.manual_signoffs("fake", ("a",), names_classes=True) == (signed, [])
    # An integration that names no classes takes no class; a row naming none is fine.
    assert cr.manual_signoffs("fake", ("a",)) == (
        [signed[2]],
        [f"{MANUAL} row {number}: a class, but fake names no classes" for number in (1, 2)],
    )


def test_a_record_naming_a_class_on_an_integration_that_names_none_is_an_error(released, gate):
    """As a manual row's is: nothing there could have reached a class, so the record was read wrong."""
    pin(released, "stop", "b")
    write_record(released, "stop.json")
    write_record(released, "turn_on_for.json")
    path = released.path / RECORDS / "turn_on_for.json"
    data = json.loads(path.read_text())
    data["tests"].append(ran("light", device("LTA009", "1", "hue"), role="light_dimmable"))
    path.write_text(text(data))
    error = f"{RECORDS}/turn_on_for.json test 2 (t[light_dimmable]): a class, but fake names no classes"
    assert cr.record_class_errors("fake") == [error]
    code, _, err = gate()
    assert code == 1
    assert f"error: {error}" in err
    # Format 1 names its classes on the test; an integration that names classes takes them.
    classes_record(released, "stop", ["hue"])
    assert cr.record_class_errors("fake")[0].startswith(f"{RECORDS}/stop.json test 1 (t[r]): a class")
    assert cr.gates(classed(stop=SCOPE, turn_on_for=SCOPE))[2] == []


def test_an_adapter_flagged_whole_or_an_integration_naming_no_classes_has_no_gap(fake_repo):
    flagged = AdapterScope(domains=labs("light"), capabilities=verified("hue"))
    assert cr.coverage_gaps(classed(turn_on_for=flagged)) == []
    assert cr.coverage_gaps(FakeRegistry({("turn_on_for", "fake"): AdapterScope()})) == []


def default_classed(scope: AdapterScope) -> FakeRegistry:
    """`classed`, with `other` its default class."""
    found = classed(turn_on_for=scope)
    found.integrations["fake"] = replace(found.integrations["fake"], default_class="other")
    return found


def credit_other(repo) -> None:
    """A record test crediting model LTA009 and a manual row crediting model LCA001, each in the class `other`."""
    classes_record_v3(repo, "turn_on_for", ran("light", device("LTA009", "1", "other")))
    (repo.path / MANUAL).write_text(manual_file(signoff(devices=(("LCA001", "other"),), calls=bound("turn_on_for"))))


def test_a_model_credited_in_a_labs_default_class_warns(fake_repo):
    """Each source on its own: the record credits LTA009 and the manual row LCA001."""
    credit_other(fake_repo)
    assert cr.default_class_credits(default_classed(SCOPE)) == [
        "fake turn_on_for: LCA001 passed in the default class `other`, which is never Verified, so its pass can't lift"
        " a flag; name a class for it (docs/evidence.md, Device classes)",
        "fake turn_on_for: LTA009 passed in the default class `other`, which is never Verified, so its pass can't lift"
        " a flag; name a class for it (docs/evidence.md, Device classes)",
    ]


def test_a_documented_default_class_is_no_trap(fake_repo):
    credit_other(fake_repo)
    documented = AdapterScope(capabilities=verified("hue", "ikea") | {"other": Level.DOCUMENTED})
    assert cr.default_class_credits(default_classed(documented)) == []


def test_a_model_credited_in_a_named_class_does_not_warn(fake_repo):
    classes_record_v3(fake_repo, "turn_on_for", ran("light", device("LTA009", "1", "hue")))
    (fake_repo.path / MANUAL).write_text(
        manual_file(signoff(devices=(("LCA001", "ikea"),), calls=bound("turn_on_for")))
    )
    assert cr.default_class_credits(default_classed(SCOPE)) == []


def test_a_model_also_credited_in_a_named_class_by_another_source_is_silent(fake_repo):
    """LTA009 passes in `other` in a record and in `hue` in a manual row: the old pass is never edited."""
    classes_record_v3(fake_repo, "turn_on_for", ran("light", device("LTA009", "1", "other")))
    (fake_repo.path / MANUAL).write_text(manual_file(signoff(devices=(("LTA009", "hue"),), calls=bound("turn_on_for"))))
    assert cr.default_class_credits(default_classed(SCOPE)) == []


def test_signoffs_fail_on_a_gap(released, gate):
    classes_record(released, "turn_on_for", ["hue"])
    code, _, err = gate(on=classed(turn_on_for=SCOPE))
    assert code == 1
    assert "error: fake turn_on_for: `ikea` is Verified but no record reaches it" in err
