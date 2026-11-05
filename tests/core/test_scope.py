"""AdapterScope levels: each domain and capability carries one; a call's level is the weakest it touches."""

import pytest

from custom_components.deviceside.core.scope import AdapterScope, Level, documented, verified


def test_helpers_merge_into_one_mapping():
    assert verified("a") | documented("b") == {"a": Level.VERIFIED, "b": Level.DOCUMENTED}


def test_defaults_are_a_verified_light_with_every_capability():
    scope = AdapterScope()

    assert scope.domains == {"light": Level.VERIFIED}
    assert scope.level("light", "anything") is Level.VERIFIED
    assert scope.documented_items() == []


@pytest.mark.parametrize(
    ("domain", "capability", "level"),
    [
        ("switch", None, Level.VERIFIED),
        ("switch", "Switch", Level.VERIFIED),
        ("switch", "Light", Level.DOCUMENTED),  # the weaker capability lowers a Verified domain
        ("light", "Switch", Level.DOCUMENTED),  # and a Documented domain lowers a Verified capability
    ],
)
def test_level_is_the_weakest_item_touched(domain, capability, level):
    scope = AdapterScope(
        domains=verified("switch") | documented("light"), capabilities=verified("Switch") | documented("Light")
    )

    assert scope.level(domain, capability) is level


def test_documented_items_lists_domains_then_capabilities():
    scope = AdapterScope(
        domains=verified("switch") | documented("light"), capabilities=verified("Switch") | documented("CCT", "RGB")
    )

    assert scope.documented_items() == ["light", "CCT", "RGB"]


def test_a_documented_field_is_refused():
    with pytest.raises(ValueError, match="fields are never Documented"):
        AdapterScope(fields=documented("brightness"))
