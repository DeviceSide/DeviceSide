"""scripts/rig.py's log capture and --debug-logs: Z2M's and HA's logs written next to the report, kept or deleted by
how the run ended, and the debug levels raised for the run's integrations and put back. Against the fakes."""

import asyncio
import datetime
import importlib.util
from pathlib import Path

import pytest

from tests.rig import engine
from tests.rig.engine import load_step_file
from tests.rig.journal import Journal
from tests.rig.runlogs import DebugLevels, ha_domains, since
from tests.scripts import rig_fakes as fakes

REPO = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("rig_for_logs", REPO / "scripts" / "rig.py")
rig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rig)

FUTURE = "2999-01-01 00:00:00.000"


class LoggedHA(fakes.FakeHA):
    async def close(self):
        pass


@pytest.fixture
def ha(monkeypatch, tmp_path) -> LoggedHA:
    ha = LoggedHA({})

    async def connect(env):
        return ha, ha

    monkeypatch.setattr(rig, "connect", connect)
    monkeypatch.setattr(rig, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(rig, "write_report", lambda result, directory, title: directory / "report.md")
    ha.ha_log = f"2000-01-01 00:00:00.000 INFO before the run\n{FUTURE} ERROR in the run\nTraceback: boom\n"
    return ha


def suites(tmp_path: Path, *integrations: str) -> list[rig.Suite]:
    path = tmp_path / "steps.yaml"
    path.write_text(fakes.RESTORED_MIDWAY)
    return [rig.Suite(load_step_file(path), integration) for integration in integrations]


def phases(monkeypatch, ha: LoggedHA, crash: bool = False, during=None):
    """engine.run as a recorder of what `during` sees; Z2M logs two lines in it, and it crashes if asked."""

    async def run(phase_suites, *args, **kwargs):
        ha.z2m_logging.put_nowait('{"level":"info","namespace":"z2m","message":"first"}')
        ha.z2m_logging.put_nowait('{"level":"warning","namespace":"z2m:mqtt","message":"second"}')
        await asyncio.sleep(0.01)
        if during:
            during()
        if crash:
            raise RuntimeError("crash")
        return engine.RunResult([])

    async def wait_for_targets(*args, **kwargs):
        pass

    monkeypatch.setattr(rig, "run", run)
    monkeypatch.setattr(rig, "wait_for_targets", wait_for_targets)


async def go(tmp_path: Path, *integrations: str, **kwargs) -> int:
    return await rig.run_rig(
        {"HA_ADMIN_TOKEN": "a"}, suites(tmp_path, *integrations), fakes.profile("zigbee2mqtt"), None, None, True, None,
        **kwargs,
    )  # fmt: skip


def logs(tmp_path: Path) -> dict[str, str]:
    return {path.name.split(".", 1)[1]: path.read_text() for path in sorted((tmp_path / "reports").glob("*.log"))}


async def test_z2m_lines_are_written_in_order_and_kept_after_a_crash(tmp_path, monkeypatch, ha, capsys):
    seen = []
    phases(monkeypatch, ha, crash=True, during=lambda: seen.append(logs(tmp_path)["z2m.log"]))
    with pytest.raises(RuntimeError, match="crash"):
        await go(tmp_path, "zigbee2mqtt")

    during = seen[0].splitlines()  # written as they arrived, while the run went on
    assert [line.split(" ", 1)[1] for line in during] == [
        "info    [z2m] first",
        "warning [z2m:mqtt] second",
    ]
    assert logs(tmp_path)["z2m.log"] == seen[0]
    assert str(next((tmp_path / "reports").glob("*.z2m.log"))) in capsys.readouterr().out


async def test_the_ha_log_is_trimmed_to_the_runs_start(tmp_path, monkeypatch, ha):
    phases(monkeypatch, ha, crash=True)
    with pytest.raises(RuntimeError):
        await go(tmp_path, "zigbee2mqtt")
    assert logs(tmp_path)["ha.log"] == f"{FUTURE} ERROR in the run\nTraceback: boom\n"


def test_a_log_with_nothing_from_the_start_on_is_kept_whole():
    log = "2000-01-01 00:00:00.000 INFO old\n"
    assert since(log, datetime.datetime.now()) == log


async def test_a_clean_run_deletes_its_logs(tmp_path, monkeypatch, ha):
    phases(monkeypatch, ha)
    assert await go(tmp_path, "zigbee2mqtt") == 0
    assert logs(tmp_path) == {}


async def test_debug_logs_keeps_a_clean_runs_logs_and_raises_then_restores_levels(tmp_path, monkeypatch, ha):
    raised = []
    phases(monkeypatch, ha, during=lambda: raised.append((dict(ha.ha_levels), ha.z2m_level)))
    assert await go(tmp_path, "zigbee2mqtt", debug_logs=True) == 0

    levels, z2m = raised[0]
    assert (levels["device_side"], levels["mqtt"], levels["hue"], levels["zha"], z2m) == (10, 10, 20, 30, "debug")
    assert (ha.ha_levels, ha.z2m_level) == ({"device_side": 30, "hue": 20, "zha": 30, "mqtt": 30}, "warning")
    assert sorted(logs(tmp_path)) == ["ha.log", "z2m.log"]


async def test_a_roaming_run_raises_hue_zha_and_mqtt(tmp_path, monkeypatch, ha):
    phases(monkeypatch, ha)
    assert ha_domains({"shelly"}, roaming=False) == ["device_side", "shelly"]
    assert ha_domains({"zigbee2mqtt"}, roaming=True) == ["device_side", "hue", "mqtt", "zha"]


async def test_a_failed_fetch_is_printed_and_the_result_stands(tmp_path, monkeypatch, ha, capsys):
    phases(monkeypatch, ha)
    ha.ha_log = OSError("no log")
    assert await go(tmp_path, "zigbee2mqtt") == 0
    assert "HA's log isn't captured: no log" in capsys.readouterr().out


async def test_a_failed_z2m_subscription_is_printed_and_the_run_goes_on(tmp_path, monkeypatch, ha, capsys):
    phases(monkeypatch, ha)

    def refuse(topic):
        raise OSError("no mqtt")

    monkeypatch.setattr(ha, "_mqtt_messages", refuse)
    assert await go(tmp_path, "zigbee2mqtt") == 0
    assert "Z2M's log isn't captured: no mqtt" in capsys.readouterr().out


async def test_recover_puts_back_the_levels_a_crash_left(tmp_path, ha):
    journal = Journal(tmp_path / "journal.json")
    await DebugLevels(ha, journal, lambda _: None).raise_levels(["device_side", "mqtt"], z2m=True)
    assert journal.get("log_levels") == {"ha": {"device_side": "WARNING", "mqtt": "WARNING"}, "z2m": "warning"}
    assert ha.z2m_level == "debug"

    await rig.recover(ha, ha, Journal(journal.path), out=lambda _: None)

    assert (ha.ha_levels["device_side"], ha.ha_levels["mqtt"], ha.z2m_level) == (30, 30, "warning")
    assert not journal.path.exists()


async def test_a_level_ha_no_longer_reports_is_skipped(tmp_path, ha):
    journal = Journal(tmp_path / "journal.json")
    levels = DebugLevels(ha, journal, lambda _: None)
    await levels.raise_levels(["device_side", "mqtt"], z2m=False)
    del ha.ha_levels["mqtt"]
    ha.log_level_calls.clear()

    await levels.restore()

    assert ha.log_level_calls == [("device_side", "WARNING")]
    assert not journal.path.exists()


async def test_a_z2m_already_at_debug_is_left_alone(tmp_path, ha):
    ha.z2m_level = "debug"
    levels = DebugLevels(ha, None, lambda _: None)
    await levels.raise_levels([], z2m=True)
    assert levels.saved == {}


async def test_the_brief_warns_when_z2m_wont_send_debug_lines(ha, capsys):
    await rig.warn_z2m_debug(ha)
    assert "log_debug_to_mqtt_frontend is off" in capsys.readouterr().out
    ha.z2m_debug_to_mqtt = True
    await rig.warn_z2m_debug(ha)
    assert capsys.readouterr().out == ""
