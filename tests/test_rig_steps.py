"""The rig's step files load, call a registered action and name only registered integrations.

Shared ones live in `tests/rig/steps/`; an integration's own in `tests/integrations/<x>/rig/`, which run on `<x>` alone,
so each needs `<x>`'s adapter of its action and may name no other integration. The rig's parser lives in the rig, and
its CI checks them in full only on a rig PR or its daily run; this catches a broken file, a misspelled action or
integration in the PR that brings it.
"""

from pathlib import Path

import pytest
import yaml

from custom_components.deviceside.core.registry import AdapterRegistry

TESTS = Path(__file__).parent
STEP_FILES = sorted((TESTS / "rig" / "steps").glob("*.yaml")) + sorted((TESTS / "integrations").glob("*/rig/*.yaml"))


@pytest.mark.parametrize("path", STEP_FILES, ids=lambda path: path.relative_to(TESTS).as_posix())
def test_a_step_file_loads_and_calls_a_registered_action(path):
    raw = yaml.safe_load(path.read_text())
    registry = AdapterRegistry.discover()
    own = path.parent.parent.name if path.parent.name == "rig" else None  # the integration whose own file it is
    allowed = {own} if own else set(registry.integrations)
    assert {"action", "rig_seconds", "tests"} <= raw.keys()
    assert raw["action"] in registry.actions
    assert own is None or registry.adapter(raw["action"], own), f"{own} has no {raw['action']} adapter"
    assert raw["tests"]
    for test in raw["tests"]:  # a misspelled `only:` would drop the test, its observed run or a step from every suite
        named = set(test.get("only", [])) | set((test.get("observe") or {}).get("only", []))
        for step in test.get("setup", []) + test.get("steps", []):  # and a class selector's, which would go inert
            named |= {*step.get("only", []), *step.get("classes", {}), *step.get("except_classes", {})}
        assert named <= allowed, test["name"]
