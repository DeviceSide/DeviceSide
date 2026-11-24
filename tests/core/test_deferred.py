"""The register's one mechanical condition (docs/deferred.md, Device facts across integrations): which integrations'
families read a Zigbee catalog module. A third one reopens that entry."""

import ast
from importlib.util import resolve_name
from pathlib import Path

from custom_components.deviceside.core.registry import AdapterRegistry

REPO = Path(__file__).resolve().parents[2]
CATALOG = "custom_components.deviceside.zigbee"


def imported(path: Path) -> set[str]:
    """The absolute names of the modules a source file imports from (`from x import y` gives x and x.y)."""
    package = ".".join(path.parent.relative_to(REPO).parts)
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def reads_catalog(path: Path) -> bool:
    return any(name == CATALOG or name.startswith(f"{CATALOG}.") for name in imported(path))


def test_only_zha_and_zigbee2mqtt_families_read_the_zigbee_catalog():
    registry = AdapterRegistry.discover()
    readers = {
        key
        for key, info in registry.integrations.items()
        for family in info.families
        if any(
            reads_catalog(source)
            for source in (REPO / f"custom_components/deviceside/integrations/{key}/families/{family.key}").rglob(
                "*.py"
            )
        )
    }
    assert readers == {"zha", "zigbee2mqtt"}, (
        f"integrations whose families read a zigbee/ catalog module are now {sorted(readers)}. A new reader meets a "
        "Revisit when condition of docs/deferred.md's 'Device facts across integrations' entry: reopen it. Either way, "
        "update this set with a repo maintainer."
    )
