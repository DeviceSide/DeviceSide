"""Zigbee2MQTT's families as the integration composes them: the rule type, the order between rule groups, and the
class the registry alone places."""

import pytest

from custom_components.deviceside.core.registry import check_families
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION, families
from custom_components.deviceside.integrations.zigbee2mqtt.families import FAMILIES, RULES, gledopto, hue, sengled, tuya
from custom_components.deviceside.integrations.zigbee2mqtt.rules import REGISTRY, Rule


@pytest.mark.parametrize(
    ("conditions", "error"),
    [({"vendor": "x"}, r"tests \['vendor'\]"), ({}, "tests nothing")],
)
def test_a_rule_tests_known_fields_and_at_least_one(conditions, error):
    with pytest.raises(ValueError, match=error):
        Rule("hue", conditions)


@pytest.mark.parametrize("capability", ["other", "ikea", "sengled"])
def test_a_family_s_rules_name_only_its_own_classes(capability):
    """Not the default class, an undeclared one, or another family's."""
    with pytest.raises(
        ValueError, match=rf"family 'hue': its rules name classes that aren't its own: \['{capability}'\]"
    ):
        families._group(hue.FAMILY, (*hue.RULES, Rule(capability, {"manufacturer": "x"})))


def test_the_integration_holds_the_four_families_and_the_registry_s_checks_pass():
    assert INTEGRATION.families is FAMILIES
    assert [family.key for family in FAMILIES] == ["hue", "tuya", "sengled", "gledopto"]
    check_families(INTEGRATION)


def test_the_rule_groups_run_in_the_integration_s_order():
    """Tuya's Zigbee-string rules before the vendor rules, its registry rules last (families/__init__.py)."""
    assert RULES == (*hue.RULES, *tuya.ZIGBEE_RULES, *sengled.RULES, *gledopto.RULES, *tuya.REGISTRY_RULES)


def test_hue_s_rule_comes_first_and_reads_the_registry_alone():
    """Why a registry `hue` is placed without the Zigbee strings (classes.placed): no Zigbee-string rule can come
    before it and override it, and no other rule names `hue`, so the class alone says the registry put it there."""
    assert families.REGISTRY_PLACED == {"hue"}
    assert RULES[0].capability == "hue"
    assert RULES[0].conditions.keys() <= REGISTRY
    assert all(rule.capability != "hue" for rule in RULES[1:])


def test_a_class_behind_a_zigbee_string_rule_can_t_be_placed_by_the_registry(monkeypatch):
    monkeypatch.setattr(families, "REGISTRY_PLACED", frozenset({"sengled"}))

    with pytest.raises(ValueError, match="'sengled' can't be placed by the registry alone"):
        families._check_registry_placed()
