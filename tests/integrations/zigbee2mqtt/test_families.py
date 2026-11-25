"""Zigbee2MQTT's families as the integration composes them: the order between rule groups, the fields a rule may
test, and the class the registry alone places."""

import pytest

from custom_components.deviceside.core.registry import check_families
from custom_components.deviceside.core.rules import Rule, compose
from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION, native_control, rules
from custom_components.deviceside.integrations.zigbee2mqtt.families import (
    FAMILIES,
    REGISTRY_PLACED,
    RULES,
    aqara,
    check_registry_placed,
    gledopto,
    hue,
    ikea,
    sengled,
    sonoff,
    tuya,
)
from custom_components.deviceside.zigbee.standard_lights import STANDARD_LIGHT


def test_the_integration_holds_the_seven_families_and_the_registry_s_checks_pass():
    assert INTEGRATION.families is FAMILIES
    assert [family.key for family in FAMILIES] == ["hue", "ikea", "tuya", "sonoff", "sengled", "gledopto", "aqara"]
    check_families(INTEGRATION)


def test_the_rule_groups_run_in_the_integration_s_order():
    """Tuya's Zigbee-string rules before the vendor rules, its registry rules last (families/__init__.py), then the
    standard lights' rule, after every family's."""
    assert RULES[:-1] == (
        *hue.RULES,
        *tuya.ZIGBEE_RULES,
        *ikea.RULES,
        *sonoff.RULES,
        *sengled.RULES,
        *gledopto.RULES,
        *aqara.RULES,
        *tuya.REGISTRY_RULES,
    )
    assert RULES[-1].capability == STANDARD_LIGHT
    assert RULES[-1].conditions.keys() == {"definition_model"}


def test_a_rule_tests_the_fields_zigbee2mqtt_reads():
    """The registry's and bridge/devices', as rules.read gives them; a mistyped one fails where rules are composed."""
    assert rules.FIELDS == {
        "manufacturer",
        "model",
        "model_id",
        "zigbee_manufacturer",
        "zigbee_model",
        "definition_model",
        "exposes",
    }
    with pytest.raises(ValueError, match=r"tests \['vendor'\]"):
        compose(rules.FIELDS, (hue.FAMILY, (Rule("hue", {"vendor": "Philips"}),)))


def test_hue_is_placed_by_the_registry_alone():
    """Why a registry `hue` is placed without the Zigbee strings (classes.placed); the check runs at import."""
    assert REGISTRY_PLACED == {"hue"}
    check_registry_placed(RULES, REGISTRY_PLACED)


@pytest.mark.parametrize(
    "placed",
    [
        pytest.param("sengled", id="behind_a_zigbee_string_rule"),
        pytest.param("tuya_mcu", id="its_own_rule_reads_the_zigbee_strings"),
        pytest.param("other", id="no_rule"),
    ],
)
def test_a_class_the_registry_alone_can_t_place_is_refused(placed):
    with pytest.raises(ValueError, match=f"'{placed}' can't be placed by the registry alone"):
        check_registry_placed(RULES, {placed})


def test_native_control_reads_the_hue_family_s_vendor_string():
    """One home for the string that says a device is Hue's: the family's rule and the option's mechanism share it."""
    assert native_control.HUE_MANUFACTURER is hue.HUE_MANUFACTURER
