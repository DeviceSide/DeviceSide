"""The rig's step files load and call a registered action.

The rig's parser is private, and its CI checks them in full only on a rig run or its daily run; this catches a broken
file or a misspelled action in the PR that brings it.
"""

from pathlib import Path

import pytest
import yaml

from custom_components.deviceside.core.registry import AdapterRegistry

STEP_FILES = sorted((Path(__file__).parent / "rig" / "steps").glob("*.yaml"))


@pytest.mark.parametrize("path", STEP_FILES, ids=lambda path: path.name)
def test_a_step_file_loads_and_calls_a_registered_action(path):
    raw = yaml.safe_load(path.read_text())
    assert {"action", "rig_seconds", "tests"} <= raw.keys()
    assert raw["action"] in AdapterRegistry.discover().actions
    assert raw["tests"]
