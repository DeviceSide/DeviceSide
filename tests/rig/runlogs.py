"""What a run leaves for diagnosis: Zigbee2MQTT's and Home Assistant's logs (RunLogs), and the opt-in debug levels
that make them say more (DebugLevels).

Z2M's frontend keeps only its last 1000 lines and HA's log restarts with HA, so a failure read later finds nothing.
Both logs are captured for every run, next to its report; they are deleted after a clean run unless asked for, or
unless Z2M's coordinator crashed during it.
"""

import asyncio
import contextlib
import datetime
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

from .client import HAClient
from .engine import report_path
from .journal import Journal

Z2M_LOGGING_TOPIC = "zigbee2mqtt/bridge/logging"
HA_DOMAINS = {"hue": "hue", "zha": "zha", "zigbee2mqtt": "mqtt", "shelly": "shelly", "matter": "matter"}
ROAM_INTEGRATIONS = ("hue", "zha", "zigbee2mqtt")
LOG_SECTION = "log_levels"
STAMPED = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")
# Z2M's error lines when its coordinator crashes (EmberZNet over USB, 3 Nov: ERROR_EXCEEDED_MAXIMUM_ACK_TIMEOUT_COUNT),
# logged at any level; Z2M restarts. The ACK timeouts that lead up to one show at debug only.
CRASH_MARKS = ("ASH_NCP_FATAL_ERROR", "Adapter disconnected")
ACK_TIMEOUT = "Timer expired waiting for ACK"
CRASH_GAP_S = 60  # crash lines closer than this are one crash


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


def z2m_line(raw: str, now: datetime.datetime) -> str:
    """One `bridge/logging` payload as a log line, with the time it arrived."""
    try:
        entry = json.loads(raw)
        text = f"{entry['level']:<7} [{entry.get('namespace', '')}] {entry['message']}"
    except ValueError, KeyError, TypeError:
        text = raw
    return f"{now:%H:%M:%S.%f}"[:-3] + f" {text}\n"


def since(log: str, start: datetime.datetime) -> str:
    """The lines of HA's log from `start` on; a line with no timestamp (a traceback) goes with the line before it.
    A log with no line from `start` (HA logs in another time zone, say) is kept whole."""
    wanted = f"{start:%Y-%m-%d %H:%M:%S}"
    lines = log.splitlines(keepends=True)
    kept: list[str] = []
    keeping = False
    for line in lines:
        if match := STAMPED.match(line):
            keeping = keeping or match.group(1) >= wanted
        if keeping:
            kept.append(line)
    return "".join(kept) if kept else log


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
    ):
        stem = report_path(directory, title).with_suffix("")
        self.z2m_path = stem.with_name(f"{stem.name}.z2m.log")
        self.ha_path = stem.with_name(f"{stem.name}.ha.log")
        self.start = start
        self.keep = keep
        self.out = out
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
        """HA's log from the run's start, written next to the report."""
        if ha is None:
            self.out("HA's log isn't captured: it needs HA_ADMIN_TOKEN in .env.rig.")
            return
        try:
            log = since(await ha.error_log(), self.start)
            self.ha_path.parent.mkdir(parents=True, exist_ok=True)
            self.ha_path.write_text(log)
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

    def settle(self, clean: bool) -> None:
        """Name each crash of Z2M's coordinator the run's Z2M log shows. After a clean run with none, the files go
        unless `keep`; otherwise they stay, and their paths are printed."""
        crashes = self.z2m_crashes()
        if clean and not self.keep and not crashes:
            for path in self.written:
                path.unlink(missing_ok=True)
            return
        for path in self.written:
            self.out(f"Log: {path}")


def ha_domains(integrations: set[str], roaming: bool) -> list[str]:
    """The HA domains a debug run raises: device_side, and each integration's the run touches, a roaming run's
    Hue, ZHA and MQTT among them."""
    keys = set(integrations) | (set(ROAM_INTEGRATIONS) if roaming else set())
    return ["device_side", *sorted({HA_DOMAINS[key] for key in keys if key in HA_DOMAINS})]


class DebugLevels:
    """Debug log levels for the run: raised once, and put back from the journal's record, so `--recover` does the
    same after a crash. The record is written before the raise."""

    def __init__(self, ha: HAClient, journal: Journal | None = None, out: Callable[[str], None] = print):
        self.ha = ha
        self.journal = journal
        self.out = out
        self.saved: dict = (journal.get(LOG_SECTION) if journal else None) or {}

    def _save(self) -> None:
        if self.journal is not None:
            if self.saved:
                self.journal.update(**{LOG_SECTION: self.saved})
            else:
                self.journal.clear(LOG_SECTION)

    async def raise_levels(self, domains: list[str], z2m: bool) -> None:
        """HA's `domains` and, with `z2m`, Zigbee2MQTT to debug. A failure is printed and leaves that log as it is."""
        try:
            levels = await self.ha.log_levels()
        except Exception as err:  # noqa: BLE001
            self.out(f"HA's log levels stay as they are: {err}")
            levels = {}
        ha_saved = {
            domain: logging.getLevelName(levels[domain])
            for domain in domains
            if domain in levels and levels[domain] != logging.DEBUG
        }
        for domain in domains:
            if domain not in levels:
                self.out(f"HA doesn't report {domain}, so it stays as it is.")
        z2m_level = None
        if z2m:
            try:
                z2m_level = (await self.ha.z2m_info()).get("log_level")
            except Exception as err:  # noqa: BLE001
                self.out(f"Z2M's log level stays as it is: {err}")
        self.saved = {
            **({"ha": ha_saved} if ha_saved else {}),
            **({"z2m": z2m_level} if z2m_level not in (None, "debug") else {}),
        }
        self._save()
        for domain in ha_saved:
            try:
                await self.ha.set_log_level(domain, "DEBUG")
            except Exception as err:  # noqa: BLE001
                self.out(f"{domain} stays at {ha_saved[domain]}: {err}")
        if "z2m" in self.saved:
            try:
                await self.ha.z2m_set_log_level("debug")
            except Exception as err:  # noqa: BLE001
                self.out(f"Z2M's log level stays at {self.saved['z2m']}: {err}")

    async def restore(self) -> None:
        """Put back every level the record holds. A failure is printed and stays in the journal; a domain HA no
        longer reports (it restarted since) is skipped."""
        if not self.saved:
            return
        left: dict = {}
        if ha_saved := self.saved.get("ha"):
            try:
                reported = await self.ha.log_levels()
            except Exception as err:  # noqa: BLE001
                self.out(f"HA's log levels are still raised: {err}. --recover tries again.")
                left["ha"] = ha_saved
                reported = None
            for domain, level in ha_saved.items() if reported is not None else ():
                if domain not in reported:
                    continue
                try:
                    await self.ha.set_log_level(domain, level)
                except Exception as err:  # noqa: BLE001
                    self.out(f"{domain} is still at debug, not {level}: {err}. --recover tries again.")
                    left.setdefault("ha", {})[domain] = level
        if level := self.saved.get("z2m"):
            try:
                await self.ha.z2m_set_log_level(level)
            except Exception as err:  # noqa: BLE001
                self.out(f"Z2M's log level is still debug, not {level}: {err}. --recover tries again.")
                left["z2m"] = level
        self.saved = left
        self._save()
