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
    row = printed(capsys, "fake", "stop", "--tester", "someone", "--device", DEVICE)
    assert row["calls"] == {"stop": head.git("rev-parse", "HEAD:tests/integrations/fake/calls/stop.json")}
    assert row["commit"] == head.git("rev-parse", "HEAD")
    assert row["tester"] == "someone"
    assert row["devices"] == [{"model": "LTA009", "manufacturer": "Signify Netherlands B.V.", "class": None}]


def test_the_row_validates_in_a_manual_file(head, capsys):
    row = printed(capsys, "fake", "stop", "--tester", "someone", "--device", DEVICE, "--device", "X1,Acme,ct")
    assert list(cr.validator().iter_errors(manual("fake", row))) == []


def test_the_blob_is_the_one_git_reads_back(head, capsys):
    row = printed(capsys, "fake", "stop", "--tester", "someone", "--device", DEVICE)
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
        signoff.main([*argv, "--tester", "someone", "--device", DEVICE], FakeRegistry())


@pytest.mark.parametrize("device", ["LTA009", "LTA009,Acme", "LTA009,,-", ",Acme,-", "LTA009,Acme,"])
def test_a_malformed_device_is_refused(head, device, capsys):
    with pytest.raises(SystemExit):
        signoff.main(["fake", "stop", "--tester", "t", "--device", device], FakeRegistry())
    assert "model,manufacturer,class" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["--device", DEVICE], ["--tester", "t"]])
def test_the_tester_and_a_device_are_required(head, argv):
    with pytest.raises(SystemExit):
        signoff.main(["fake", "stop", *argv], FakeRegistry())


def test_the_real_registry_names_its_integrations_in_the_error():
    with pytest.raises(SystemExit, match="control4"):
        signoff.main(["nope", "stop", "--tester", "t", "--device", DEVICE])


def test_a_row_the_script_didnt_print_is_checked_the_same():
    """The schema rejects a tester that is not a handle, so a hand-edited placeholder can't land."""
    row = sample_row(tester="<tester>")
    assert list(cr.validator().iter_errors(manual("fake", row)))


def test_a_manufacturer_may_contain_a_comma(head, capsys):
    row = printed(capsys, "fake", "stop", "--tester", "t", "--device", "LTA009,Acme, Inc.,ct")
    assert row["devices"] == [{"model": "LTA009", "manufacturer": "Acme, Inc.", "class": "ct"}]


def test_group_prints_the_flag_and_validates(head, capsys):
    row = printed(capsys, "fake", "stop", "--tester", "t", "--device", DEVICE, "--group")
    assert row["group"] is True
    assert list(cr.validator().iter_errors(manual("fake", row))) == []
    assert "group" not in printed(capsys, "fake", "stop", "--tester", "t", "--device", DEVICE)


def test_it_runs_by_its_path():
    done = subprocess.run(
        [
            sys.executable,
            str(cr.REPO / "scripts" / "signoff.py"),
            "control4",
            "nope",
            "--tester",
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
