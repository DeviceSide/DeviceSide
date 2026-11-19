#!/usr/bin/env python3
"""Route an issue to the integrations its form names: an `integration:<key>` label each, and their maintainers as
assignees.

The device report form's Integration dropdown lists each integration's title (`IntegrationInfo.title`), then OTHER.
GitHub writes the choices into the issue body under the dropdown's label, comma-separated. GitHub can't prefill a
dropdown, so the options menu's link leaves it for the user; the Devices lines it does prefill start with each
device's integration key (`config_flow._DeviceFacts.line`), so those route too, whatever the dropdown says. The
maintainers are read from each integration's `__init__.py` by `scripts/owners.py`'s parser, not imported, so the
workflow runs on the standard library alone. The form names no family, so none is routed to; an audit's finding is
routed by `scripts/owners.py --issue`, under the same label.

Usage: scripts/route_issue.py   (reads ISSUE_BODY; appends `labels=` and `assignees=` to GITHUB_OUTPUT, or prints them)
"""

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.owners import INTEGRATIONS as PACKAGES  # noqa: E402
from scripts.owners import LABEL as ROUTED  # noqa: E402
from scripts.owners import Integration, parse  # noqa: E402

INTEGRATIONS = REPO / PACKAGES
LABEL = "Integration"
DEVICES = "Devices"
SEPARATOR = " · "  # between a Devices line's fields, as config_flow._DeviceFacts.line writes them
OTHER = "Other or not sure"
EMPTY = "_No response_"  # what GitHub writes for an unanswered field


def read(init: Path) -> Integration:
    """The integration's key, title and maintainers, from the literal `INTEGRATION = IntegrationInfo(...)` call."""
    return parse(init.read_text(), init)


def integrations(root: Path = INTEGRATIONS) -> dict[str, Integration]:
    """Every integration, by title."""
    found = [read(init) for init in sorted(root.glob("*/__init__.py"))]
    return {integration.title: integration for integration in found}


def section(body: str, label: str) -> str:
    """The field's answer: the text between its `### <label>` heading and the next heading, blank when unanswered."""
    body = body.replace("\r\n", "\n")  # a body edited on the web comes back with CRLF
    if not (match := re.search(rf"^### {label}[ \t]*\n(.*?)(?=^### |\Z)", body, re.MULTILINE | re.DOTALL)):
        return ""
    text = match[1].strip()
    return "" if text == EMPTY else text


def chosen(body: str) -> list[str]:
    """The dropdown's choices."""
    return [choice.strip() for choice in section(body, LABEL).split(",") if choice.strip()]


def device_keys(body: str) -> list[str]:
    """The integration key that starts each Devices line; a line typed by hand gives its first field, which routes
    only if it is a key."""
    return [line.split(SEPARATOR)[0].strip() for line in section(body, DEVICES).splitlines() if line.strip()]


def route(body: str, known: dict[str, Integration]) -> tuple[list[str], list[str]]:
    """The labels and assignees for the integrations chosen in the dropdown (`known` is by title) or keyed on a
    Devices line; OTHER and anything unknown route nowhere."""
    by_key = {integration.key: integration for integration in known.values()}
    picked = list(
        dict.fromkeys(
            [known[title] for title in chosen(body) if title in known]
            + [by_key[key] for key in device_keys(body) if key in by_key]
        )
    )
    labels = [ROUTED.format(key=integration.key) for integration in picked]
    assignees = list(dict.fromkeys(handle for integration in picked for handle in integration.maintainers))
    return labels, assignees


def main() -> int:
    labels, assignees = route(os.environ.get("ISSUE_BODY", ""), integrations())
    lines = f"labels={','.join(labels)}\nassignees={','.join(assignees)}\n"
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as file:
            file.write(lines)
    else:
        sys.stdout.write(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
