"""Core's classification rules: what a rule matches, and what composing the families' rule groups refuses."""

import pytest

from custom_components.deviceside.core.rules import Rule, compose, match
from custom_components.deviceside.core.scope import Family

FIELDS = frozenset({"manufacturer", "model", "exposes"})
ACME = Family(key="acme", classes=frozenset({"acme", "acme_plug"}))
BOLT = Family(key="bolt", classes=frozenset({"bolt"}))


@pytest.mark.parametrize(
    ("conditions", "device", "matched"),
    [
        pytest.param({"model": "A1"}, {"model": "A1"}, True, id="whole_string"),
        pytest.param({"model": "A1"}, {"model": "A12"}, False, id="not_a_prefix"),
        pytest.param({"model": "A1"}, {"model": "XA1"}, False, id="not_a_suffix"),
        pytest.param({"model": "A.*"}, {"model": "A12"}, True, id="pattern"),
        pytest.param({"model": "A1"}, {"model": None}, False, id="none"),
        pytest.param({"model": ".*"}, {"model": None}, False, id="none_matches_nothing"),
        pytest.param({"model": ".*"}, {}, False, id="field_the_device_lacks"),
        pytest.param({"exposes": "countdown"}, {"exposes": frozenset({"state", "countdown"})}, True, id="set_member"),
        pytest.param({"exposes": "countdown"}, {"exposes": frozenset({"countdown_l1"})}, False, id="set_whole_member"),
        pytest.param({"exposes": ".*"}, {"exposes": frozenset()}, False, id="empty_set"),
        pytest.param({"manufacturer": "Acme", "model": "A1"}, {"manufacturer": "Acme", "model": "A1"}, True, id="both"),
        pytest.param({"manufacturer": "Acme", "model": "A1"}, {"manufacturer": "Acme", "model": "A2"}, False, id="one"),
    ],
)
def test_a_rule_matches_when_every_condition_fully_matches(conditions, device, matched):
    assert Rule("acme", conditions).matches(device) is matched


def test_compose_joins_the_groups_in_the_order_given_and_the_first_match_wins():
    wide, narrow = Rule("acme", {"model": "X.*"}), Rule("bolt", {"model": "X1"})

    assert compose(FIELDS, (ACME, (wide,)), (BOLT, (narrow,))) == (wide, narrow)
    assert match((wide, narrow), {"model": "X1"}) == "acme"
    assert match((narrow, wide), {"model": "X1"}) == "bolt"
    assert match((wide, narrow), {"model": "Y1"}) is None


def test_a_family_may_have_several_groups():
    first, last = Rule("acme", {"model": "A1"}), Rule("acme_plug", {"model": "P1"})
    between = Rule("bolt", {"model": "B1"})

    assert compose(FIELDS, (ACME, (first,)), (BOLT, [between]), (ACME, (last,))) == (first, between, last)


@pytest.mark.parametrize("capability", ["bolt", "other", "acme_bulb"])
def test_a_rule_naming_a_class_that_isn_t_its_family_s_fails_composition(capability):
    """Another family's class, the default one, or one nobody declares."""
    with pytest.raises(ValueError, match=rf"family 'acme': a rule names '{capability}', which isn't its class"):
        compose(FIELDS, (BOLT, ()), (ACME, (Rule("acme", {"model": "A1"}), Rule(capability, {"model": "A2"}))))


def test_a_rule_testing_a_field_the_integration_doesn_t_read_fails_composition():
    """Another integration's field, or a mistyped one, would never match, and the class would silently lose its
    devices."""
    with pytest.raises(ValueError, match=r"family 'acme': a rule for 'acme' tests \['model_id'\], not among"):
        compose(FIELDS, (ACME, (Rule("acme", {"manufacturer": "Acme", "model_id": "A1"}),)))


def test_a_rule_testing_nothing_fails_composition():
    """It would match every device."""
    with pytest.raises(ValueError, match="family 'acme': a rule for 'acme' tests nothing"):
        compose(FIELDS, (ACME, (Rule("acme", {}),)))
