"""The rig's journal: what a run changed and has not yet put back, kept on disk."""

import os

from tests.rig.journal import Journal, orphans


def test_a_journal_survives_a_new_reader_and_goes_once_empty(tmp_path):
    path = tmp_path / "journal.json"
    journal = Journal(path)
    assert not journal
    assert not path.exists()

    journal.update(paused=["automation.motion"], options={"opt": True})
    reread = Journal(path)
    assert reread.get("paused") == ["automation.motion"]
    assert reread.get("taken", {}) == {}

    journal.clear("paused")
    assert Journal(path).get("paused") is None
    assert Journal(path).get("options") == {"opt": True}

    journal.clear("options", "taken")
    assert not journal
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []  # nor a temp file


def test_a_journal_records_when_it_started_and_orphans_come_oldest_first(tmp_path):
    older, newer = Journal.start(tmp_path), Journal.start(tmp_path)
    newer.update(paused=["automation.b"])
    older.update(paused=["automation.a"])
    older.started = 1.0  # as if saved first
    older.save()
    assert set(Journal(older.path).sections) == {"paused"} and Journal(older.path).started == 1.0
    older.release()
    newer.release()

    found = orphans(tmp_path)
    assert [journal.path for journal in found] == [older.path, newer.path]
    for journal in found:
        journal.clear("paused")
        journal.release()
    assert list(tmp_path.iterdir()) == []


def test_a_journal_from_before_started_goes_by_its_files_age(tmp_path):
    path = tmp_path / "journal.json"
    path.write_text('{"paused": []}')
    os.utime(path, (5.0, 5.0))
    assert Journal(path).started == 5.0
