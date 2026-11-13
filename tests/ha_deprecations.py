"""Collect HA's deprecation reports on DeviceSide's code across the run, so they surface before the HA version that
breaks them, which is often a year out.

HA's frame helper logs one when DeviceSide calls a deprecated API: "Detected that custom integration 'deviceside'
calls `x`, which is deprecated ... This will stop working in Home Assistant 2027.8.0". A report fails nothing: the
run lists them in its summary, and writes them as JSON to the path in DEVICESIDE_HA_DEPRECATIONS when that is set,
for the Tests workflow to file one issue per deprecated call (`.github/workflows/tests.yml`). Under xdist the workers
hand theirs to the controller.
"""

import json
import logging
import os
import re

import pytest

_FRAME_LOGGER = "homeassistant.helpers.frame"
_CALL = re.compile(r"`([^`]+)`")


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.reports: dict[str, str] = {}  # the deprecated call: the first report of it

    def emit(self, record: logging.LogRecord) -> None:
        # The frame helper's args are (integration type, integration, what, ...), in both its report formats.
        args = record.args if isinstance(record.args, tuple) else ()
        if len(args) < 3 or args[1] != "deviceside":
            return
        what = str(args[2])
        call = match[1] if (match := _CALL.search(what)) else what
        self.reports.setdefault(call, record.getMessage())


_collector = _Collector()


def pytest_configure(config: pytest.Config) -> None:
    logging.getLogger(_FRAME_LOGGER).addHandler(_collector)


def pytest_sessionfinish(session: pytest.Session) -> None:
    # Under xdist each worker collects its own; it hands them to the controller, which writes the summary.
    if hasattr(session.config, "workeroutput"):
        session.config.workeroutput["ha_deprecations"] = _collector.reports


@pytest.hookimpl(optionalhook=True)  # xdist's
def pytest_testnodedown(node, error) -> None:
    for call, message in getattr(node, "workeroutput", {}).get("ha_deprecations", {}).items():
        _collector.reports.setdefault(call, message)


def pytest_terminal_summary(terminalreporter) -> None:
    if hasattr(terminalreporter.config, "workeroutput"):
        return
    if path := os.environ.get("DEVICESIDE_HA_DEPRECATIONS"):
        with open(path, "w", encoding="utf-8") as file:
            json.dump([{"call": call, "message": message} for call, message in _collector.reports.items()], file)
    if _collector.reports:
        terminalreporter.section("HA deprecation reports")
        for message in _collector.reports.values():
            terminalreporter.write_line(message)
