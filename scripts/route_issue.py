#!/usr/bin/env python3
"""Route an issue to the integrations its form names: an `integration:<key>` label each, and their maintainers as
assignees.

The device report form's Integration dropdown lists each integration's title (`IntegrationInfo.title`), then OTHER.
GitHub writes the choices into the issue body under the dropdown's label, comma-separated. The maintainers are read
from each integration's `__init__.py` by `scripts/owners.py`'s parser, not imported, so the workflow runs on the
standard library alone. The form names no family, so none is routed to; an audit's finding is routed by
`scripts/owners.py --issue`, under the same label.

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
OTHER = "Other or not sure"
EMPTY = "_No response_"  # what GitHub writes for an unanswered field


def read(init: Path) -> Integration:
    """The integration's key, title and maintainers, from the literal `INTEGRATION = IntegrationInfo(...)` call."""
    return parse(init.read_text(), init)


def integrations(root: Path = INTEGRATIONS) -> dict[str, Integration]:
    """Every integration, by title."""
    found = [read(init) for init in sorted(root.glob("*/__init__.py"))]
    return {integration.title: integration for integration in found}


def chosen(body: str) -> list[str]:
    """The dropdown's choices: the text between its `### Integration` heading and the next heading."""
    body = body.replace("\r\n", "\n")  # a body edited on the web comes back with CRLF
    if not (match := re.search(rf"^### {LABEL}[ \t]*\n(.*?)(?=^### |\Z)", body, re.MULTILINE | re.DOTALL)):
        return []
    text = match[1].strip()
    return [] if text in ("", EMPTY) else [choice.strip() for choice in text.split(",") if choice.strip()]


def route(body: str, known: dict[str, Integration]) -> tuple[list[str], list[str]]:
    """The labels and assignees for the integrations chosen; OTHER and anything unknown route nowhere."""
    picked = [known[title] for title in dict.fromkeys(chosen(body)) if title in known]
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
