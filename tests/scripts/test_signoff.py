"""scripts/signoff.py: the row it prints binds each action to HEAD's transcript blob and validates against the schema;
unknown integrations and actions, and a missing transcript, fail by name."""

import json
import subprocess
import sys

import pytest

from scripts import check_release as cr
from scripts import signoff

from .record_files import manual
from .record_files import signoff as sample_row

SEGMENTS = [{"integration": "fake", "action": "stop", "request": {}, "wire": [], "result": {}}]
DEVICE = "LTA009,Signify Netherlands B.V.,-"


class FakeRegistry:
    integrations = {"fake": object()}

    def adapter(self, action, integration):
        return object() if (action, integration) in {("stop", "fake"), ("turn_on_for", "fake")} else None


@pytest.fixture
def head(repo, monkeypatch):
    """A repository whose HEAD holds the transcript of `stop` only, which the script reads as the repository."""
    monkeypatch.setattr(cr, "REPO", repo.path)
    repo.commit("tests/integrations/fake/calls/stop.json", json.dumps(SEGMENTS))
    return repo


def printed(capsys, *argv) -> dict:
    assert signoff.main(list(argv), FakeRegistry()) == 0
    return json.loads(capsys.readouterr().out)


def test_the_row_binds_each_action_to_heads_blob(head, capsys):
    row = printed(capsys, "fake", "stop", "--signed-by", "someone", "--device", DEVICE)
    assert row["calls"] == {"stop": head.git("rev-parse", "HEAD:tests/integrations/fake/calls/stop.json")}
    assert row["commit"] == head.git("rev-parse", "HEAD")
    assert row["signed_by"] == "someone"
    assert row["devices"] == [{"model": "LTA009", "manufacturer": "Signify Netherlands B.V.", "class": None}]


def test_the_row_validates_in_a_manual_file(head, capsys):
    row = printed(capsys, "fake", "stop", "--signed-by", "someone", "--device", DEVICE, "--device", "X1,Acme,ct")
    assert list(cr.validator().iter_errors(manual("fake", row))) == []


def test_the_blob_is_the_one_git_reads_back(head, capsys):
    row = printed(capsys, "fake", "stop", "--signed-by", "someone", "--device", DEVICE)
    assert cr.transcript(row["calls"]["stop"]) == SEGMENTS


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["nope", "stop"], "unknown integration 'nope'"),
        (["fake", "fly"], "fake has no 'fly' action"),
        (["fake", "turn_on_for"], "fake / turn_on_for has no transcript at HEAD"),
    ],
)
def test_a_bad_request_fails_by_name(head, argv, message):
    with pytest.raises(SystemExit, match=message):
        signoff.main([*argv, "--signed-by", "someone", "--device", DEVICE], FakeRegistry())


@pytest.mark.parametrize("device", ["LTA009", "LTA009,Acme", "LTA009,,-", ",Acme,-", "LTA009,Acme,"])
def test_a_malformed_device_is_refused(head, device, capsys):
    with pytest.raises(SystemExit):
        signoff.main(["fake", "stop", "--signed-by", "t", "--device", device], FakeRegistry())
    assert "model,manufacturer,class" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["--device", DEVICE], ["--signed-by", "t"]])
def test_the_signer_and_a_device_are_required(head, argv):
    with pytest.raises(SystemExit):
        signoff.main(["fake", "stop", *argv], FakeRegistry())


def test_the_real_registry_names_its_integrations_in_the_error():
    with pytest.raises(SystemExit, match="control4"):
        signoff.main(["nope", "stop", "--signed-by", "t", "--device", DEVICE])


def test_a_row_the_script_didnt_print_is_checked_the_same():
    """The schema rejects a signer that is not a handle, so a hand-edited placeholder can't land."""
    row = sample_row(signed_by="<signer>")
    assert list(cr.validator().iter_errors(manual("fake", row)))


def test_a_manufacturer_may_contain_a_comma(head, capsys):
    row = printed(capsys, "fake", "stop", "--signed-by", "t", "--device", "LTA009,Acme, Inc.,ct")
    assert row["devices"] == [{"model": "LTA009", "manufacturer": "Acme, Inc.", "class": "ct"}]


def test_group_prints_the_flag_and_validates(head, capsys):
    row = printed(capsys, "fake", "stop", "--signed-by", "t", "--device", DEVICE, "--group")
    assert row["group"] is True
    assert list(cr.validator().iter_errors(manual("fake", row))) == []
    assert "group" not in printed(capsys, "fake", "stop", "--signed-by", "t", "--device", DEVICE)


def test_at_binds_the_tags_commit_and_blobs_and_reports_ride_along(head, capsys):
    """A sign-off of users' reports names the release they ran, not HEAD, which may have moved on."""
    tagged = head.git("rev-parse", "HEAD")
    head.git("tag", "v1.0.0")
    blob = head.git("rev-parse", "HEAD:tests/integrations/fake/calls/stop.json")
    head.commit("tests/integrations/fake/calls/stop.json", json.dumps([*SEGMENTS, *SEGMENTS]))
    issues = [f"https://github.com/DeviceSide/DeviceSide/issues/{number}" for number in (3, 4)]
    argv = ["fake", "stop", "--signed-by", "t", "--device", DEVICE, "--at", "v1.0.0", "--reports", *issues, issues[0]]
    row = printed(capsys, *argv)
    assert (row["commit"], row["calls"], row["reports"]) == (tagged, {"stop": blob}, issues)
    assert list(cr.validator().iter_errors(manual("fake", row))) == []
    assert "reports" not in printed(capsys, "fake", "stop", "--signed-by", "t", "--device", DEVICE)


def test_at_a_revision_that_names_no_commit_fails_by_name(head):
    with pytest.raises(SystemExit, match="--at 'v9.9.9' names no commit"):
        signoff.main(["fake", "stop", "--signed-by", "t", "--device", DEVICE, "--at", "v9.9.9"], FakeRegistry())


def test_it_runs_by_its_path():
    done = subprocess.run(
        [
            sys.executable,
            str(cr.REPO / "scripts" / "signoff.py"),
            "control4",
            "nope",
            "--signed-by",
            "t",
            "--device",
            DEVICE,
        ],
        capture_output=True,
        text=True,
        cwd="/",
    )
    assert "ModuleNotFoundError" not in done.stderr
    assert "control4 has no 'nope' action" in done.stderr
