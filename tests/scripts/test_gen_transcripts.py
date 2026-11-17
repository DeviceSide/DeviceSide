"""scripts/gen_transcripts.py: runs the whole suite under `--transcripts=write`, from the repository root."""

import subprocess
import sys

from scripts import gen_transcripts as gt


def test_it_runs_the_whole_suite_in_write_mode(monkeypatch):
    seen = {}

    def run(command, cwd):
        seen.update(command=command, cwd=cwd)
        return subprocess.CompletedProcess(command, 3)

    monkeypatch.setattr(gt.subprocess, "run", run)
    assert gt.main([]) == 3
    assert seen["command"] == [sys.executable, "-m", "pytest", "-n", "auto", "--transcripts=write"]
    assert seen["cwd"] == gt.REPO


def test_extra_arguments_reach_pytest(monkeypatch):
    seen = []
    monkeypatch.setattr(
        gt.subprocess, "run", lambda command, cwd: seen.append(command) or subprocess.CompletedProcess(command, 0)
    )
    assert gt.main(["-q"]) == 0
    assert seen[0][-1] == "-q"
