"""Every discovered action has a block in services.yaml, strings.json and icons.json, and nothing else does."""

import json
from pathlib import Path

import pytest
import yaml

from custom_components.deviceside.actions import discover
from custom_components.deviceside.core.registry import AdapterRegistry, served_domains

PACKAGE = Path(__file__).parents[2] / "custom_components" / "deviceside"


def _load_json(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text())


ACTIONS = discover()
ACTION_KEYS = {action.key for action in ACTIONS}
SERVICES_YAML = yaml.safe_load((PACKAGE / "services.yaml").read_text()) or {}
STRINGS = _load_json("strings.json")


def test_services_yaml_matches_features():
    assert set(SERVICES_YAML) == ACTION_KEYS


def test_strings_match_actions():
    assert set(STRINGS["services"]) == ACTION_KEYS


def test_icons_match_actions():
    assert set(_load_json("icons.json")["services"]) == ACTION_KEYS


def test_translation_is_a_copy_of_strings():
    assert _load_json("translations/en.json") == STRINGS


@pytest.mark.parametrize("action", ACTIONS, ids=lambda action: action.key)
def test_target_filter_lists_exactly_the_integrations_and_domains_served(action):
    """A domain the scope holds but serves no class on (every class refused there) stays out of the picker."""
    registry = AdapterRegistry.discover()
    in_scope: dict[str, set[str]] = {}
    for key, integration, adapter in registry.matrix():
        if key == action.key and adapter is not None:
            info = registry.integrations[integration]
            in_scope.setdefault(info.ha_domain, set()).update(served_domains(adapter, info))
    listed: dict[str, set[str]] = {}
    for entry in SERVICES_YAML[action.key]["target"]["entity"]:
        domains = entry["domain"]
        listed.setdefault(entry["integration"], set()).update([domains] if isinstance(domains, str) else domains)
    assert listed == in_scope


@pytest.mark.parametrize("action", ACTIONS, ids=lambda action: action.key)
def test_every_field_has_strings(action):
    fields = {marker.schema for marker in action.fields}
    assert set(STRINGS["services"][action.key].get("fields", {})) == fields
