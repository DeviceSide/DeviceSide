"""ZHA's families as the integration composes them: the order between rule groups, and the fields a rule may test."""

import pytest

from custom_components.deviceside.core.registry import check_families
from custom_components.deviceside.core.rules import Rule, compose
from custom_components.deviceside.integrations.zha import INTEGRATION, classes, rules
from custom_components.deviceside.integrations.zha.families import FAMILIES, RULES, hue, sengled, sonoff, tuya


def test_the_integration_holds_the_four_families_and_the_registry_s_checks_pass():
    assert INTEGRATION.families is FAMILIES
    assert [family.key for family in FAMILIES] == ["hue", "tuya", "sengled", "sonoff"]
    check_families(INTEGRATION)


def test_the_rule_groups_run_in_the_integration_s_order():
    """Tuya's datapoint rules before its ZCL ones, and every Tuya rule before Sengled's (families/__init__.py)."""
    assert RULES == (*hue.RULES, *tuya.DATAPOINT_RULES, *tuya.ZCL_RULES, *sengled.RULES, *sonoff.RULES)


def test_every_rule_names_a_class_but_the_default():
    assert {rule.capability for rule in RULES} == classes.CLASSES - {classes.OTHER}


def test_a_rule_tests_the_fields_zha_reads():
    """zigpy's two strings and the On/Off cluster's quirk, as rules.read gives them; a mistyped one fails where rules
    are composed, at import."""
    assert rules.FIELDS == rules.read("Maker", "Model", "zigpy.zcl").keys() == {"manufacturer", "model", "quirk"}
    with pytest.raises(ValueError, match=r"tests \['identity'\]"):
        compose(rules.FIELDS, (hue.FAMILY, (Rule("hue", {"identity": "Philips/LCT001"}),)))
