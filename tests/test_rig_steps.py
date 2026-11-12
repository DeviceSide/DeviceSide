"""The rig's step files load, call a registered action and name only registered integrations.

The rig's parser is private, and its CI checks them in full only on a rig PR or its daily run; this catches a broken
file, a misspelled action or integration in the PR that brings it.
"""

from pathlib import Path

import pytest
import yaml

from custom_components.deviceside.core.registry import AdapterRegistry

STEP_FILES = sorted((Path(__file__).parent / "rig" / "steps").glob("*.yaml"))


@pytest.mark.parametrize("path", STEP_FILES, ids=lambda path: path.name)
def test_a_step_file_loads_and_calls_a_registered_action(path):
    raw = yaml.safe_load(path.read_text())
    registry = AdapterRegistry.discover()
    assert {"action", "rig_seconds", "tests"} <= raw.keys()
    assert raw["action"] in registry.actions
    assert raw["tests"]
    for test in raw["tests"]:  # a misspelled `only:` would drop the test, its observed run or a step from every suite
        named = set(test.get("only", [])) | set((test.get("observe") or {}).get("only", []))
        named |= {key for step in test.get("setup", []) + test.get("steps", []) for key in step.get("only", [])}
        assert named <= set(registry.integrations), test["name"]
