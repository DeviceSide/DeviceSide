#!/usr/bin/env python3
"""Generate each action's `target:` block in services.yaml from the registry.

HA's UI picker filters an action's targets by integration and entity domain. Those lists are derivable: for each
adapter of the action, the adapter's integration's HA domain with the entity domains it serves (`served_domains`, so a
domain whose every class is refused stays out of the picker). A new integration therefore edits no target list by hand.

The file is rewritten as text, not round-tripped through PyYAML, which would drop the hand-written field anchors
(`&duration`, `&dimmable`, ...). Each action's `  target:` line and the deeper-indented lines after it are replaced;
everything else is byte-identical. Entries are one per HA domain, sorted by it, with no anchors.

Usage: scripts/gen_services.py [--check]

--check exits 1 when the committed file differs from what this generates.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.core.registry import AdapterRegistry, served_domains  # noqa: E402

SERVICES = REPO / "custom_components" / "deviceside" / "services.yaml"
ACTION_KEY = re.compile(r"^([a-z_][a-z0-9_]*):\s*$")
TARGET_LINE = re.compile(r"^  target:(\s.*)?$")


def targets(registry: AdapterRegistry) -> dict[str, dict[str, set[str]]]:
    """Each action key's entity domains served, by the HA domain of the integration serving them."""
    found: dict[str, dict[str, set[str]]] = {}
    for key, integration, adapter in registry.matrix():
        if adapter is not None:
            info = registry.integrations[integration]
            found.setdefault(key, {}).setdefault(info.ha_domain, set()).update(served_domains(adapter, info))
    return found


def block(entries: dict[str, set[str]]) -> str:
    """The `target:` block's lines: one entry per HA domain, sorted by it; a flow list for several domains."""
    lines = ["  target:", "    entity:"]
    for ha_domain, domains in sorted(entries.items()):
        ordered = sorted(domains)
        shown = ordered[0] if len(ordered) == 1 else f"[{', '.join(ordered)}]"
        lines += [f"      - domain: {shown}", f"        integration: {ha_domain}"]
    return "\n".join(lines) + "\n"


def _split(text: str) -> list[tuple[str | None, str]]:
    """The text as (action key, chunk) pairs, a chunk being a target block (key set) or the text around it (None)."""
    pieces: list[tuple[str | None, str]] = []
    plain: list[str] = []
    lines = text.splitlines(keepends=True)
    action: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if match := ACTION_KEY.match(line.rstrip("\n")):
            action = match.group(1)
        if action and TARGET_LINE.match(line.rstrip("\n")):
            if plain:
                pieces.append((None, "".join(plain)))
                plain = []
            start = i
            i += 1
            while i < len(lines) and lines[i].startswith("   "):
                i += 1
            pieces.append((action, "".join(lines[start:i])))
            action = None
            continue
        plain.append(line)
        i += 1
    if plain:
        pieces.append((None, "".join(plain)))
    return pieces


def authored(text: str) -> str:
    """The text with each action's target block removed: the hand-written part, for check_maintainer_merge.py."""
    return "".join(chunk for action, chunk in _split(text) if action is None)


def generate(text: str, registry: AdapterRegistry) -> str:
    wanted = targets(registry)
    pieces = _split(text)
    found = [action for action, _ in pieces if action]
    keys = set(yaml.safe_load(text) or {})
    if missing := keys - set(found):
        raise SystemExit(f"services.yaml: no `target:` for {', '.join(sorted(missing))}")
    if keys != set(wanted):
        raise SystemExit(
            f"services.yaml actions {sorted(keys)} differ from the registry's {sorted(wanted)}; add or remove the block"
        )
    result = "".join(block(wanted[action]) if action else chunk for action, chunk in pieces)
    before, after = yaml.safe_load(text), yaml.safe_load(result)
    for loaded in (before, after):
        for body in loaded.values():
            body.pop("target")
    if before != after:
        raise SystemExit("services.yaml: the splice changed more than the target blocks")
    for action, body in yaml.safe_load(result).items():
        listed = {entry["integration"]: entry["domain"] for entry in body["target"]["entity"]}
        shown = {ha: set([d] if isinstance(d, str) else d) for ha, d in listed.items()}
        if shown != wanted[action]:
            raise SystemExit(f"services.yaml: {action} targets {shown} differ from the registry's {wanted[action]}")
    return result


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None, repo: Path = REPO) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when services.yaml is out of date")
    args = parser.parse_args(argv)

    path = repo / SERVICES.relative_to(REPO)
    current = path.read_text()
    text = generate(current, registry or AdapterRegistry.discover())
    if current == text:
        return 0
    if args.check:
        print("error: services.yaml out of date; run scripts/gen_services.py", file=sys.stderr)
        return 1
    path.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
