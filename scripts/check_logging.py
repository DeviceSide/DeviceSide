#!/usr/bin/env python3
"""Flag log calls that break docs/logging.md's "What a line may name".

Two rules, read from the AST so a call split over lines is seen whole:

- A caught exception is logged with `%r` (or `{err!r}`), never `%s`: its text is often the diagnosis.
- No argument names a device address: IEEE or MAC addresses, MQTT topics, friendly names, Hue resource IDs, Zigbee
  node IDs or tokens. Name the entity instead (Hue: `bridge.entity_name`; Zigbee2MQTT: `addressing.entity_name`).

A line that needs an exception says why on the same line: `# log-ok: <reason>`.

Usage: scripts/check_logging.py FILE ...   (pre-commit passes the staged Python files)
"""

import ast
import re
import sys
from pathlib import Path

LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
EXCEPTION_NAMES = {"err", "exc", "error", "exception"}
# Parts of an identifier (split on _ and case) that mark a device address or a secret.
ADDRESS_WORDS = {"ieee", "mac", "topic", "token", "address", "addr", "rid", "friendly", "resource", "node"}
# Calls that turn an address into an entity name, and attributes that already are one: their insides are fine.
LOOKUPS = {"entity_name", "group_entity_id"}
ENTITY_ATTRS = {"entity_id", "reported_id"}
PLACEHOLDER = re.compile(r"%(?:\([^)]*\))?[-#0 +]*[\d*]*(?:\.[\d*]+)?[a-zA-Z]")
EXEMPT = re.compile(r"#\s*log-ok:\s*\S")


def _is_log_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in LOG_METHODS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"_LOGGER", "logger", "LOGGER"}
    )


def _words(identifier: str) -> set[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", identifier)
    return {part.lower() for part in spaced.split("_") if part}


def _caught_names(tree: ast.AST) -> dict[ast.AST, frozenset[str]]:
    """Each node -> names bound by the `except ... as name` clauses around it."""
    found: dict[ast.AST, frozenset[str]] = {}

    def walk(node: ast.AST, names: frozenset[str]) -> None:
        found[node] = names
        inner = names | {node.name} if isinstance(node, ast.ExceptHandler) and node.name else names
        for child in ast.iter_child_nodes(node):
            walk(child, inner)

    walk(tree, frozenset())
    return found


def _address_in(node: ast.AST) -> str | None:
    """The first identifier under `node` that names a device address, skipping entity lookups and entity IDs."""
    if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
        if (node.func.id if isinstance(node.func, ast.Name) else node.func.attr) in LOOKUPS:
            return None
    if isinstance(node, ast.Attribute) and node.attr in ENTITY_ATTRS:
        return None
    if isinstance(node, ast.Name | ast.Attribute) and not isinstance(node.ctx, ast.Store):
        ident = node.id if isinstance(node, ast.Name) else node.attr
        if _words(ident) & ADDRESS_WORDS:
            return ident
    return next((found for child in ast.iter_child_nodes(node) if (found := _address_in(child))), None)


def violations(path: Path) -> list[str]:
    source = path.read_text()
    tree = ast.parse(source)
    lines = source.splitlines()
    caught_at = _caught_names(tree)
    found = []
    for node in ast.walk(tree):
        if not _is_log_call(node) or not node.args:
            continue
        end = node.end_lineno or node.lineno
        if any(EXEMPT.search(lines[n - 1]) for n in range(node.lineno, end + 1)):
            continue
        where = f"{path}:{node.lineno}"
        names = caught_at.get(node, frozenset()) | EXCEPTION_NAMES

        def is_caught(arg: ast.AST, names: frozenset[str] = names) -> bool:
            return isinstance(arg, ast.Name) and arg.id in names

        fmt, *args = node.args
        if isinstance(fmt, ast.Constant) and isinstance(fmt.value, str):
            holders = PLACEHOLDER.findall(fmt.value)
            found.extend(
                f"{where}: caught exception logged with %s; use %r"
                for index, arg in enumerate(args)
                if is_caught(arg) and index < len(holders) and holders[index].endswith("s")
            )
        found.extend(
            f"{where}: caught exception logged without !r"
            for part in ast.walk(fmt)
            if isinstance(part, ast.FormattedValue) and is_caught(part.value) and part.conversion != ord("r")
        )
        for arg in node.args:
            if isinstance(arg, ast.Constant):
                continue
            if ident := _address_in(arg):
                found.append(f"{where}: logs `{ident}`, a device address; name the entity instead")
    return found


def main(paths: list[str]) -> int:
    found = [line for path in paths if path.endswith(".py") for line in violations(Path(path))]
    print("\n".join(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
