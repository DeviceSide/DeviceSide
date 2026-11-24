"""identifier_values: a device's identifier values under a domain, whatever the identifiers' length."""

from types import SimpleNamespace

from custom_components.deviceside.core.identifiers import identifier_values


def values(identifiers: set[tuple[str, ...]], domain: str) -> list[str]:
    return sorted(identifier_values(SimpleNamespace(identifiers=identifiers), domain))


def test_a_pair_gives_its_value():
    assert values({("mqtt", "a"), ("zha", "b")}, "mqtt") == ["a"]


def test_a_longer_identifier_is_read_by_its_first_two_parts():
    assert values({("mqtt", "a", "x"), ("mqtt", "b", "x", "y")}, "mqtt") == ["a", "b"]


def test_a_shorter_identifier_is_skipped():
    assert values({("mqtt",), ("mqtt", "a")}, "mqtt") == ["a"]


def test_another_domains_identifiers_are_skipped_whatever_their_length():
    assert values({("homekit", "a", "b", "c"), ("zha", "d")}, "mqtt") == []
