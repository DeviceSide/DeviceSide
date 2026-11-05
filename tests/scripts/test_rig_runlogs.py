"""scripts/rig.py's log capture and --debug-logs: Z2M's and HA's logs written next to the report, kept or deleted by
how the run ended, and the debug levels raised for the run's integrations and put back. Against the fakes."""

import asyncio
import datetime
import importlib.util
import re
from pathlib import Path

import pytest

from tests.rig import baseline, engine
from tests.rig.baseline import Baseline
from tests.rig.engine import load_step_file
from tests.rig.journal import Journal
from tests.rig.runlogs import DebugLevels, RunLogs, coordinator_crashes, device_side_lines, ha_domains, since
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


def suites(tmp_path: Path, *integrations: str, expected_log: str = "") -> list[rig.Suite]:
    path = tmp_path / "steps.yaml"
    head = f"expected_log: [{expected_log!r}]\n" if expected_log else ""
    path.write_text(head + fakes.RESTORED_MIDWAY)
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


async def go(tmp_path: Path, *integrations: str, expected_log: str = "", **kwargs) -> int:
    return await rig.run_rig(
        {"HA_ADMIN_TOKEN": "a"}, suites(tmp_path, *integrations, expected_log=expected_log),
        fakes.profile("zigbee2mqtt"), None, None, True, None, **kwargs,
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


CRASHED = (
    "23:08:40.100 debug   [zh:ember:uart:ash] Timer expired waiting for ACK\n"
    "23:08:46.200 error   [zh:ember:uart:ash] ASH_NCP_FATAL_ERROR\n"
    "23:08:46.300 error   [zh:ember] Adapter disconnected\n"
    "23:08:47.000 info    [z2m] Stopping\n"
    "23:30:01.000 error   [zh:ember:uart:ash] ASH_NCP_FATAL_ERROR\n"
    "23:31:00.000 info    [z2m] Delivery failed, ASH_NCP_FATAL_ERROR quoted at info isn't one\n"
)


def test_coordinator_crashes_are_counted_once_each_with_their_times():
    assert coordinator_crashes(CRASHED) == (["23:08:46", "23:30:01"], 1)
    assert coordinator_crashes("10:00:00.000 info    [z2m] fine\n") == ([], 0)


def test_a_clean_run_whose_coordinator_crashed_says_so_and_keeps_the_log(tmp_path):
    printed = []
    logs = RunLogs(tmp_path, "rig run", datetime.datetime.now(), out=printed.append)
    logs.z2m_path.write_text(CRASHED)
    logs.written.append(logs.z2m_path)
    logs.settle(clean=True)
    assert "Z2M's coordinator crashed 2 times (23:08:46, 23:30:01)." in printed
    assert "Z2M logged 1 ACK timeout with its coordinator." in printed
    assert logs.z2m_path.exists() and f"Log: {logs.z2m_path}" in printed


def test_a_clean_run_with_no_crash_still_deletes_its_logs(tmp_path):
    logs = RunLogs(tmp_path, "rig run", datetime.datetime.now(), out=lambda _: None)
    logs.z2m_path.write_text("10:00:00.000 info    [z2m] fine\n")
    logs.written.append(logs.z2m_path)
    logs.settle(clean=True)
    assert not logs.z2m_path.exists()


WARNED = (
    f"{FUTURE} WARNING (MainThread) [custom_components.device_side.core.dispatcher] stop on zha timed out after 5s\n"
    f"{FUTURE} ERROR (MainThread) [custom_components.device_side] Error setting up entry\n"
    "Traceback (most recent call last):\n"
    f"{FUTURE} INFO (MainThread) [custom_components.device_side.core] loaded\n"
    f"{FUTURE} WARNING (MainThread) [custom_components.device_side_extra] another integration\n"
    f"{FUTURE} ERROR (MainThread) [homeassistant.components.zha] not ours\n"
)


def test_device_side_warnings_and_errors_are_picked_out_of_the_ha_log():
    unexpected, matched = device_side_lines(WARNED)
    assert [line.split("[", 1)[1] for line in unexpected] == [
        "custom_components.device_side.core.dispatcher] stop on zha timed out after 5s",
        "custom_components.device_side] Error setting up entry",
    ]
    assert matched == 0
    assert device_side_lines(WARNED, [re.compile(r"dispatcher\] stop on zha timed out")]) == ([unexpected[1]], 1)


async def test_an_unexpected_device_side_warning_fails_a_clean_run_and_keeps_its_logs(
    tmp_path, monkeypatch, ha, capsys
):
    phases(monkeypatch, ha)
    ha.ha_log = WARNED
    assert await go(tmp_path, "zigbee2mqtt") == 1
    out = capsys.readouterr().out
    assert "HA's log has 2 DeviceSide warnings or errors no step file expects:" in out
    assert "stop on zha timed out after 5s" in out
    assert sorted(logs(tmp_path)) == ["ha.log", "z2m.log"]


async def test_a_warning_a_step_file_expects_is_counted_and_fails_nothing(tmp_path, monkeypatch, ha, capsys):
    phases(monkeypatch, ha)
    ha.ha_log = WARNED.splitlines(keepends=True)[0]
    assert await go(tmp_path, "zigbee2mqtt", expected_log="stop on zha timed out") == 0
    assert "HA's log has 1 DeviceSide warning or error the step files expect." in capsys.readouterr().out
    assert logs(tmp_path) == {}


def test_a_log_with_nothing_from_the_start_on_has_no_run_lines():
    assert since("2000-01-01 00:00:00.000 INFO old\n", datetime.datetime.now()) is None


async def test_a_log_with_nothing_from_the_start_on_is_kept_whole_and_not_checked(tmp_path, monkeypatch, ha, capsys):
    phases(monkeypatch, ha, crash=True)
    ha.ha_log = WARNED.replace(FUTURE, "2000-01-01 00:00:00.000")
    with pytest.raises(RuntimeError):
        await go(tmp_path, "zigbee2mqtt")
    assert logs(tmp_path)["ha.log"] == ha.ha_log
    assert "so its DeviceSide warnings aren't checked" in capsys.readouterr().out


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
    orphan = Journal.start(tmp_path)
    await DebugLevels(Baseline.of(ha, orphan, "debug"), lambda _: None).raise_levels(["device_side", "mqtt"], z2m=True)
    assert (ha.ha_levels["device_side"], ha.ha_levels["mqtt"], ha.z2m_level) == (10, 10, "debug")

    await rig.recover(ha, ha, orphan, out=lambda _: None)  # it holds the orphan's lock meanwhile

    assert (ha.ha_levels["device_side"], ha.ha_levels["mqtt"], ha.z2m_level) == (30, 30, "warning")
    assert not (tmp_path / baseline.NAME).exists()


async def test_a_level_that_cant_be_raised_is_printed_and_the_rest_go_on(ha):
    printed = []
    await DebugLevels(Baseline.of(ha, None, "debug"), printed.append).raise_levels(["matter", "mqtt"], z2m=False)
    assert printed == ["matter stays as it is: HA doesn't report matter"]
    assert ha.ha_levels["mqtt"] == 10


async def test_the_brief_warns_when_z2m_wont_send_debug_lines(ha, capsys):
    await rig.warn_z2m_debug(ha)
    assert "log_debug_to_mqtt_frontend is off" in capsys.readouterr().out
    ha.z2m_debug_to_mqtt = True
    await rig.warn_z2m_debug(ha)
    assert capsys.readouterr().out == ""
