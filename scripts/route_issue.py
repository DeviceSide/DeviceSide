#!/usr/bin/env python3
"""Route an issue to the integrations its form names: an `integration:<key>` label each, and their maintainers as
assignees.

The device report form's Integration dropdown lists each integration's title (`IntegrationInfo.title`), then OTHER.
GitHub writes the choices into the issue body under the dropdown's label, comma-separated. The maintainers are read
from each integration's `__init__.py` by parsing it, not importing it, so the workflow runs on the standard library
alone; tests/scripts/test_route_issue.py checks both parses against the registry. A family's maintainers are read the
same way (`parse_family`), for scripts/check_maintainer_merge.py; the form names no family, so none is routed to.

Usage: scripts/route_issue.py   (reads ISSUE_BODY; appends `labels=` and `assignees=` to GITHUB_OUTPUT, or prints them)
"""

import ast
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTEGRATIONS = REPO / "custom_components" / "deviceside" / "integrations"
LABEL = "Integration"
OTHER = "Other or not sure"
EMPTY = "_No response_"  # what GitHub writes for an unanswered field


@dataclass(frozen=True)
class Integration:
    key: str
    title: str
    maintainers: tuple[str, ...]


@dataclass(frozen=True)
class Family:
    key: str
    maintainers: tuple[str, ...]


def read(init: Path) -> Integration:
    """The integration's key, title and maintainers, from the literal `INTEGRATION = IntegrationInfo(...)` call."""
    return parse(init.read_text(), init)


def names(node: ast.Assign | ast.AnnAssign) -> list[str | None]:
    """The names an assignment binds."""
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [getattr(target, "id", None) for target in targets]


def listed(fields: tuple[str, ...], suffix: str = "") -> str:
    """`key=, title= and maintainers=`, for an error."""
    items = [f"{name}{suffix}" for name in fields]
    return " and ".join([", ".join(items[:-1]), items[-1]] if len(items) > 1 else items)


def called(node: ast.expr) -> str | None:
    """The name a call calls, bare or as an attribute (`scope.Family(...)`); None for anything else."""
    return getattr(node.func, "id", getattr(node.func, "attr", None)) if isinstance(node, ast.Call) else None


def literals(text: str, init: Path | str, name: str, call: str, fields: tuple[str, ...]) -> dict:
    """The literal keyword `fields` of the module's one `<name> = <call>(...)` binding (`init` names the file in
    errors): each a string, but `maintainers`, a tuple or list of them. The registry takes the last binding, so a
    second one is refused rather than read past; a call to anything else, or a value of another shape, isn't read as
    owners."""
    body = ast.parse(text).body
    bindings = [node for node in body if isinstance(node, ast.Assign | ast.AnnAssign) and name in names(node)]
    if len(bindings) > 1:
        raise SystemExit(f"{init}: {name} is bound {len(bindings)} times")
    for node in bindings:
        if isinstance(node, ast.Assign) and names(node) == [name] and called(node.value) == call:
            try:
                kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in node.value.keywords if kw.arg in fields}
            except (ValueError, TypeError) as err:
                raise SystemExit(f"{init}: {listed(fields)} must be literals ({err})") from None
            if set(kwargs) != set(fields):
                raise SystemExit(f"{init}: {name} needs {listed(fields, '=')}")
            for field, value in kwargs.items():
                if field != "maintainers" and not isinstance(value, str):
                    raise SystemExit(f"{init}: {field} must be a string")
                if field == "maintainers" and not (
                    isinstance(value, tuple | list) and all(isinstance(handle, str) for handle in value)
                ):
                    raise SystemExit(f"{init}: maintainers must be a tuple or list of strings")
            return kwargs
    raise SystemExit(f"{init}: no {name} = {call}(...)")


def parse(text: str, init: Path | str) -> Integration:
    """`read`, on the text of an `__init__.py`."""
    kwargs = literals(text, init, "INTEGRATION", "IntegrationInfo", ("key", "title", "maintainers"))
    return Integration(kwargs["key"], kwargs["title"], tuple(kwargs["maintainers"]))


def parse_family(text: str, init: Path | str) -> Family:
    """A family's key and maintainers, from the literal `FAMILY = Family(...)` call in the text of its `__init__.py`
    (`integrations/<key>/families/<family>/`). scripts/check_maintainer_merge.py reads its owners with it;
    tests/scripts/test_route_issue.py checks the parse against the registry."""
    kwargs = literals(text, init, "FAMILY", "Family", ("key", "maintainers"))
    return Family(kwargs["key"], tuple(kwargs["maintainers"]))


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
    labels = [f"integration:{integration.key}" for integration in picked]
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
