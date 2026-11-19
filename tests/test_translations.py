"""translations/en.json is the only source of the strings the code raises and shows, and hassfest checks its schema,
not that each key the code uses is in it. The keys are collected from the source, so a new one is caught."""

import ast
import json
from pathlib import Path

import pytest

from custom_components.deviceside.core.errors import LABS_OFF, Reason, TargetNotSupported

PACKAGE = Path(__file__).parents[1] / "custom_components" / "deviceside"
STRINGS = json.loads((PACKAGE / "translations" / "en.json").read_text())

# What the code raises or creates, by the section of en.json that holds it.
_USED: dict[str, set[str]] = {"exceptions": set(), "issues": set(), "options.step": set()}
# A translation_key the AST can't read: errors.py builds it from the reason, which _target_not_supported_keys covers.
_UNREAD: set[tuple[str, str]] = set()


def _steps(flow: ast.ClassDef) -> set[str]:
    return {
        item.name.removeprefix("async_step_")
        for item in flow.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name.startswith("async_step_")
    }


def _collect() -> None:
    trees = {path: ast.parse(path.read_text()) for path in PACKAGE.rglob("*.py")}
    # Module string constants (LEGACY_ISSUE = "legacy_device_side"), which a translation_key may name.
    constants = {
        node.targets[0].id: node.value.value
        for tree in trees.values()
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("OptionsFlow"):
                _USED["options.step"] |= _steps(node)
            if not isinstance(node, ast.Call):
                continue
            section = "issues" if getattr(node.func, "attr", "") == "async_create_issue" else "exceptions"
            for keyword in node.keywords:
                if keyword.arg != "translation_key":
                    continue
                if isinstance(keyword.value, ast.Constant):
                    _USED[section].add(keyword.value.value)
                elif isinstance(keyword.value, ast.Name) and keyword.value.id in constants:
                    _USED[section].add(constants[keyword.value.id])
                else:
                    _UNREAD.add((path.relative_to(PACKAGE).as_posix(), ast.unparse(keyword.value)))


_collect()


def _target_not_supported_keys() -> set[str]:
    return {
        TargetNotSupported("light.x", reason, why, integration).translation_key
        for reason in (*Reason, LABS_OFF)
        for why, integration in ((None, None), ("why", None), (None, "Zigbee2MQTT"), ("why", "Zigbee2MQTT"))
    }


def test_the_collection_finds_what_the_code_raises():
    """Pinned as literals, so a call the AST stops reading can't leave the membership test passing on nothing."""
    assert {
        "not_loaded",
        "invalid_duration",
        "nothing_to_set",
        "targets_failed",
        "no_entities_matched",
    } <= _USED["exceptions"]
    assert _USED["issues"] == {"legacy_device_side", "legacy_device_side_calls", "migrate_hue_dimmer"}
    assert _USED["options.step"] == {
        "init",
        "settings",
        "report_device",
        "report_link",
        "propose_device",
        "proposal_link",
    }
    assert _target_not_supported_keys() == {
        "labs_off",
        "own_call",
        "class_unknown",
        "not_built",
        "no_known_method",
        "target_not_supported",
    }
    assert _UNREAD == {("core/errors.py", "key")}


@pytest.mark.parametrize("section", ["exceptions", "issues", "options.step"])
def test_every_key_the_code_uses_is_in_en_json(section):
    held = STRINGS
    for part in section.split("."):
        held = held[part]
    used = _USED[section] | (_target_not_supported_keys() if section == "exceptions" else set())

    assert used - held.keys() == set()
