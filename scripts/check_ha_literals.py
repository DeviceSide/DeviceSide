#!/usr/bin/env python3
"""Flag a string literal where Home Assistant already defines the name (CLAUDE.md, "A name HA defines").

Read from the AST, so a call split over lines is seen whole. A literal is flagged only in a position that carries
HA's meaning, and only when it is one of HA's names (the fixed map below); a vendor payload is not such a position:

- `hass.services.async_call(domain, service, data)`: the domain, the service, and a literal data dict's keys;
- a comparison with `.domain` or `.platform`, and a `domains=` keyword argument;
- a comparison with `.state` of an entity state (`state.state == "on"`);
- an `.attributes.get("...")` or `.attributes["..."]` key.

A line that needs a literal says why on the same line: `# ha-literal: <reason>`.

0-255 guard: HA's `ATTR_BRIGHTNESS` is a 0-255 byte, DeviceSide's brightness a percent (`BRIGHTNESS_FIELD`).
Every use of `ATTR_BRIGHTNESS` (its import aside) says why 0-255 is right on that line: `# ha-255: <why>`.

Usage: scripts/check_ha_literals.py FILE ...   (pre-commit passes the staged Python files)
"""

import ast
import re
import sys
from pathlib import Path

DOMAINS = {"light": "Platform.LIGHT", "switch": "Platform.SWITCH", "scene": "Platform.SCENE"}
SERVICES = {"turn_on": "SERVICE_TURN_ON", "turn_off": "SERVICE_TURN_OFF", "toggle": "SERVICE_TOGGLE"}
STATES = {"on": "STATE_ON", "off": "STATE_OFF"}
# homeassistant.components.light's names (and homeassistant.const's ATTR_ENTITY_ID).
ATTRIBUTES = {
    "entity_id": "ATTR_ENTITY_ID",
    "brightness": "ATTR_BRIGHTNESS",
    "color_mode": "ATTR_COLOR_MODE",
    "supported_color_modes": "ATTR_SUPPORTED_COLOR_MODES",
    "hs_color": "ATTR_HS_COLOR",
    "xy_color": "ATTR_XY_COLOR",
    "rgb_color": "ATTR_RGB_COLOR",
    "rgbw_color": "ATTR_RGBW_COLOR",
    "rgbww_color": "ATTR_RGBWW_COLOR",
    "color_name": "ATTR_COLOR_NAME",
    "color_temp_kelvin": "ATTR_COLOR_TEMP_KELVIN",
    "min_color_temp_kelvin": "ATTR_MIN_COLOR_TEMP_KELVIN",
    "max_color_temp_kelvin": "ATTR_MAX_COLOR_TEMP_KELVIN",
    "transition": "ATTR_TRANSITION",
    "effect": "ATTR_EFFECT",
    "white": "ATTR_WHITE",
}
DOMAIN_ATTRS = {"domain", "platform"}
EXEMPT = re.compile(r"#\s*ha-literal:\s*\S")
BYTE_MARK = re.compile(r"#\s*ha-255:\s*\S")


def _strings(node: ast.AST) -> list[ast.Constant]:
    """Every string constant under `node`."""
    return [n for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _is_attr(node: ast.AST, names: set[str]) -> bool:
    return isinstance(node, ast.Attribute) and node.attr in names


def _is_entity_state(node: ast.AST) -> bool:
    """`state.state` or `x.state.state`: an HA state object's state string."""
    if not (isinstance(node, ast.Attribute) and node.attr == "state"):
        return False
    inner = node.value
    return (isinstance(inner, ast.Name) and inner.id == "state") or _is_attr(inner, {"state"})


def _use(literal: ast.Constant, names: dict[str, str]) -> tuple[int, str] | None:
    if literal.value in names:
        return literal.lineno, f"`{literal.value!r}` is HA's {names[literal.value]}"
    return None


Slot = tuple[ast.AST, dict[str, str]]  # a node that should not be a literal, and HA's names for it


def _call_slots(node: ast.Call) -> list[Slot]:
    slots: list[Slot] = [(s, DOMAINS) for kw in node.keywords if kw.arg == "domains" for s in _strings(kw.value)]
    func = node.func
    if not isinstance(func, ast.Attribute):
        return slots
    if func.attr == "async_call":
        slots += [(arg, names) for arg, names in zip(node.args, (DOMAINS, SERVICES), strict=False)]
        by_keyword = {"domain": DOMAINS, "service": SERVICES}
        slots += [(kw.value, by_keyword[kw.arg]) for kw in node.keywords if kw.arg in by_keyword]
        blobs = node.args[2:3] + [kw.value for kw in node.keywords if kw.arg in {"service_data", "data"}]
        slots += [(key, ATTRIBUTES) for blob in blobs if isinstance(blob, ast.Dict) for key in blob.keys if key]
    if func.attr == "get" and _is_attr(func.value, {"attributes"}) and node.args:
        slots.append((node.args[0], ATTRIBUTES))
    return slots


def _compare_slots(node: ast.Compare) -> list[Slot]:
    operands = [node.left, *node.comparators]
    slots: list[Slot] = []
    for subject in operands:
        if _is_attr(subject, DOMAIN_ATTRS):
            names = DOMAINS
        elif _is_entity_state(subject):
            names = STATES
        else:
            continue
        slots += [(s, names) for other in operands if other is not subject for s in _strings(other)]
    return slots


def _flag_candidates(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, message) for each literal in an HA-meaning position, before the escape comments are applied."""
    slots: list[Slot] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            slots += _call_slots(node)
        elif isinstance(node, ast.Compare):
            slots += _compare_slots(node)
        elif isinstance(node, ast.Subscript) and _is_attr(node.value, {"attributes"}):
            slots.append((node.slice, ATTRIBUTES))
    return [
        hit
        for literal, names in slots
        if isinstance(literal, ast.Constant) and isinstance(literal.value, str) and (hit := _use(literal, names))
    ]


def violations(path: Path) -> list[str]:
    source = path.read_text()
    tree = ast.parse(source)
    lines = source.splitlines()
    found = []
    for line, message in sorted(set(_flag_candidates(tree))):
        if EXEMPT.search(lines[line - 1]):
            continue
        found.append(f"{path}:{line}: {message}; use it, or say why on the line: `# ha-literal: <reason>`")
    for node in ast.walk(tree):
        is_byte = (isinstance(node, ast.Name) and node.id == "ATTR_BRIGHTNESS") or _is_attr(node, {"ATTR_BRIGHTNESS"})
        if is_byte and not BYTE_MARK.search(lines[node.lineno - 1]):
            found.append(
                f"{path}:{node.lineno}: ATTR_BRIGHTNESS is HA's 0-255 byte, DeviceSide's brightness is a percent "
                "(`BRIGHTNESS_FIELD`); say why 0-255 is right here: `# ha-255: <why>`"
            )
    return sorted(found)


def main(paths: list[str]) -> int:
    found = [line for path in paths if path.endswith(".py") for line in violations(Path(path))]
    print("\n".join(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
