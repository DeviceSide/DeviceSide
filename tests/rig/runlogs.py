"""What a run leaves for diagnosis: Zigbee2MQTT's and Home Assistant's logs (RunLogs), and the opt-in debug levels
that make them say more (DebugLevels).

Z2M's frontend keeps only its last 1000 lines and HA's log restarts with HA, so a failure read later finds nothing.
Both logs are captured for every run, next to its report; they are deleted after a clean run unless asked for, or
unless Z2M's coordinator crashed during it, or HA's log shows a device_side warning or error no step file of the run
expects: such a line also fails the run.
"""

import asyncio
import contextlib
import datetime
import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from .baseline import Apply, Baseline
from .client import HAClient
from .engine import report_path

Z2M_LOGGING_TOPIC = "zigbee2mqtt/bridge/logging"
HA_DOMAINS = {"hue": "hue", "zha": "zha", "zigbee2mqtt": "mqtt", "shelly": "shelly", "matter": "matter"}
ROAM_INTEGRATIONS = ("hue", "zha", "zigbee2mqtt")
STAMPED = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")
# Z2M's error lines when its coordinator crashes (EmberZNet over USB, 3 Nov: ERROR_EXCEEDED_MAXIMUM_ACK_TIMEOUT_COUNT),
# logged at any level; Z2M restarts. The ACK timeouts that lead up to one show at debug only.
CRASH_MARKS = ("ASH_NCP_FATAL_ERROR", "Adapter disconnected")
ACK_TIMEOUT = "Timer expired waiting for ACK"
CRASH_GAP_S = 60  # crash lines closer than this are one crash
# HA's log line: `2026-11-04 12:00:00.123 WARNING (MainThread) [custom_components.device_side.core.dispatcher] ...`
DEVICE_SIDE_LINE = re.compile(r"^\S+ \S+ (?:WARNING|ERROR|CRITICAL) \(.*?\) \[custom_components\.device_side[.\]]")


def coordinator_crashes(log: str) -> tuple[list[str], int]:
    """From a captured Z2M log (z2m_line's format): the time of each coordinator crash, and how many ACK timeouts it
    logged."""
    crashes: list[str] = []
    last: datetime.datetime | None = None
    acks = 0
    for line in log.splitlines():
        stamp, _, rest = line.partition(" ")
        level, _, message = rest.strip().partition(" ")
        acks += ACK_TIMEOUT in message
        if level != "error" or not any(mark in message for mark in CRASH_MARKS):
            continue
        try:
            at = datetime.datetime.strptime(stamp[:8], "%H:%M:%S")
        except ValueError:
            continue
        if last is None or not 0 <= (at - last).total_seconds() < CRASH_GAP_S:
            crashes.append(stamp[:8])
        last = at
    return crashes, acks


def device_side_lines(log: str, expected: Iterable[re.Pattern[str]] = ()) -> tuple[list[str], int]:
    """From a captured HA log: device_side's warning and error lines that no `expected` pattern is found in, and how
    many lines one was. A traceback's lines after its first aren't counted: the first names the logger."""
    patterns = tuple(expected)
    unexpected: list[str] = []
    matched = 0
    for line in log.splitlines():
        if not DEVICE_SIDE_LINE.match(line):
            continue
        if any(pattern.search(line) for pattern in patterns):
            matched += 1
        else:
            unexpected.append(line)
    return unexpected, matched


def z2m_line(raw: str, now: datetime.datetime) -> str:
    """One `bridge/logging` payload as a log line, with the time it arrived."""
    try:
        entry = json.loads(raw)
        text = f"{entry['level']:<7} [{entry.get('namespace', '')}] {entry['message']}"
    except ValueError, KeyError, TypeError:
        text = raw
    return f"{now:%H:%M:%S.%f}"[:-3] + f" {text}\n"


def since(log: str, start: datetime.datetime) -> str | None:
    """The lines of HA's log from `start` on; a line with no timestamp (a traceback) goes with the line before it.
    None for a log with no line from `start` (HA logs in another time zone, say)."""
    wanted = f"{start:%Y-%m-%d %H:%M:%S}"
    lines = log.splitlines(keepends=True)
    kept: list[str] = []
    keeping = False
    for line in lines:
        if match := STAMPED.match(line):
            keeping = keeping or match.group(1) >= wanted
        if keeping:
            kept.append(line)
    return "".join(kept) if kept else None


class RunLogs:
    """The run's two logs, `<report stem>.z2m.log` and `<report stem>.ha.log`, in `directory`. Nothing here raises:
    a log that can't be fetched or written is printed, so it never hides the run's own error."""

    def __init__(
        self,
        directory: Path,
        title: str,
        start: datetime.datetime,
        keep: bool = False,
        out: Callable[[str], None] = print,
        expected: Iterable[re.Pattern[str]] = (),
    ):
        stem = report_path(directory, title).with_suffix("")
        self.z2m_path = stem.with_name(f"{stem.name}.z2m.log")
        self.ha_path = stem.with_name(f"{stem.name}.ha.log")
        self.start = start
        self.keep = keep
        self.out = out
        self.expected = tuple(expected)
        self.ha_dated = False  # whether the saved HA log was cut at the run's start
        self.written: list[Path] = []
        self._task: asyncio.Task | None = None

    async def start_z2m(self, ha: HAClient | None) -> None:
        """Append Z2M's log lines to the file as they arrive, from now on; returns once the subscription is live.
        Needs the admin connection."""
        if ha is None:
            self.out("Z2M's log isn't captured: it needs HA_ADMIN_TOKEN in .env.rig.")
            return
        ready = asyncio.Event()
        self._task = asyncio.create_task(self._pump(ha, ready))
        await ready.wait()

    async def _pump(self, ha: HAClient, ready: asyncio.Event) -> None:
        try:
            self.z2m_path.parent.mkdir(parents=True, exist_ok=True)
            async with ha._mqtt_messages(Z2M_LOGGING_TOPIC) as messages:
                with self.z2m_path.open("a") as file:
                    self.written.append(self.z2m_path)
                    ready.set()
                    while True:
                        file.write(z2m_line(await messages.get(), datetime.datetime.now()))
                        file.flush()  # a crash keeps what came before it
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            self.out(f"Z2M's log isn't captured: {err}")
        finally:
            ready.set()

    async def stop_z2m(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    async def save_ha(self, ha: HAClient | None) -> None:
        """HA's log from the run's start, written next to the report; all of it when no line is dated from the start."""
        if ha is None:
            self.out("HA's log isn't captured: it needs HA_ADMIN_TOKEN in .env.rig.")
            return
        try:
            whole = await ha.error_log()
            log = since(whole, self.start)
            self.ha_dated = log is not None
            self.ha_path.parent.mkdir(parents=True, exist_ok=True)
            self.ha_path.write_text(whole if log is None else log)
        except Exception as err:  # noqa: BLE001
            self.out(f"HA's log isn't captured: {err}")
            return
        self.written.append(self.ha_path)

    def z2m_crashes(self) -> list[str]:
        """Each coordinator crash in the captured Z2M log, printed with the ACK timeouts it shows."""
        if self.z2m_path not in self.written:
            return []
        try:
            crashes, acks = coordinator_crashes(self.z2m_path.read_text())
        except OSError as err:
            self.out(f"Z2M's log couldn't be read for crashes: {err}")
            return []
        if crashes:
            times = "once" if len(crashes) == 1 else f"{len(crashes)} times"
            self.out(f"Z2M's coordinator crashed {times} ({', '.join(crashes)}).")
        if acks:
            self.out(f"Z2M logged {acks} ACK timeout{'s' if acks > 1 else ''} with its coordinator.")
        return crashes

    def ha_warnings(self) -> list[str]:
        """Each device_side warning or error in the captured HA log that no step file of the run expects, printed."""
        if self.ha_path not in self.written:
            return []
        if not self.ha_dated:
            self.out("HA's log has no line dated from the run's start, so its device_side warnings aren't checked.")
            return []
        try:
            unexpected, matched = device_side_lines(self.ha_path.read_text(), self.expected)
        except OSError as err:
            self.out(f"HA's log couldn't be read for device_side warnings: {err}")
            return []
        if matched:
            self.out(f"HA's log has {_warnings(matched)} the step files expect.")
        if unexpected:
            self.out(f"HA's log has {_warnings(len(unexpected))} no step file expects:")
            for line in unexpected:
                self.out(f"  {line}")
        return unexpected

    def settle(self, clean: bool) -> bool:
        """Name each crash of Z2M's coordinator the run's Z2M log shows, and each device_side warning or error in HA's
        that no step file expects. After a clean run with neither, the files go unless `keep`; otherwise they stay, and
        their paths are printed. Whether HA's log had such a line: the caller fails the run on it."""
        crashes = self.z2m_crashes()
        unexpected = bool(self.ha_warnings())
        if clean and not self.keep and not crashes and not unexpected:
            for path in self.written:
                path.unlink(missing_ok=True)
            return False
        for path in self.written:
            self.out(f"Log: {path}")
        return unexpected


def _warnings(count: int) -> str:
    return f"{count} device_side warning or error" if count == 1 else f"{count} device_side warnings or errors"


def ha_domains(integrations: set[str], roaming: bool) -> list[str]:
    """The HA domains a debug run raises: device_side, and each integration's the run touches, a roaming run's
    Hue, ZHA and MQTT among them."""
    keys = set(integrations) | (set(ROAM_INTEGRATIONS) if roaming else set())
    return ["device_side", *sorted({HA_DOMAINS[key] for key in keys if key in HA_DOMAINS})]


class DebugLevels:
    """Debug log levels for the run, held in the baseline (tests/rig/baseline.py), which records each level before
    raising it: the last run out puts it back, and a crashed run's comes back with the next run's prune or --recover's.
    A level that can't be read or set is printed and left as it is: it never stops the run."""

    def __init__(self, baseline: Baseline, out: Callable[[str], None] = print):
        self.baseline = baseline
        self.ha = baseline.ha
        self.out = out

    async def raise_levels(self, domains: list[str], z2m: bool) -> None:
        """HA's `domains` and, with `z2m`, Zigbee2MQTT to debug."""
        for domain in domains:
            await self.hold("ha_log_level", domain, lambda _, d=domain: self.ha.set_log_level(d, "DEBUG"), domain)
        if z2m:
            await self.hold("z2m_log_level", "", lambda _: self.ha.z2m_set_log_level("debug"), "Z2M's log level")

    async def hold(self, kind: str, key: str, apply: Apply, what: str) -> None:
        try:
            await self.baseline.hold((kind, key, apply))
        except Exception as err:  # noqa: BLE001
            self.out(f"{what} stays as it is: {err}")

    async def restore(self) -> None:
        """Let go of the levels; whatever no other run holds raised goes back."""
        await self.baseline.release()
