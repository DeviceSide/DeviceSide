"""ZHA's refusal entries (refusals.py): the classes turn_on_for refuses because today's call would harm them. The
integration's, as the entries are: a family's own tests cover its rules and levels."""

from homeassistant.const import Platform

from custom_components.deviceside import actions
from custom_components.deviceside.core.errors import Reason
from custom_components.deviceside.core.scope import NotBuilt
from custom_components.deviceside.integrations.zha import ADAPTERS
from custom_components.deviceside.integrations.zha.refusals import REFUSALS

FAILURE_HARMS = {action.key: action.failure_harms for action in actions.discover()}


def test_turn_on_for_alone_refuses_classes_and_harms_there_alone():
    """No ZHA class has no known method: each refused one has a call that would work, not built yet. turn_on_for's
    failure harms, so core refuses a target it can't class too; no other ZHA adapter does."""
    assert REFUSALS.keys() == {"turn_on_for"}
    assert set(REFUSALS["turn_on_for"]) == {
        "tuya_countdown_harmed",
        "tuya_countdown",
        "tuya_zcl",
        "tuya_mcu",
        "sengled",
        "sonoff_swv",
        "other",
        "hue",
        "ikea",
        "ikea_timer_harmed",
    }
    assert all(isinstance(entry, NotBuilt) for entry in REFUSALS["turn_on_for"].values())
    assert [adapter.action for adapter in ADAPTERS if adapter.scope.harms(FAILURE_HARMS[adapter.action])] == [
        "turn_on_for"
    ]


def test_each_entry_is_in_its_adapter_s_scope():
    scopes = {adapter.action: adapter.scope for adapter in ADAPTERS}

    assert {action: dict(scope.not_built) for action, scope in scopes.items() if scope.not_built} == REFUSALS
    assert not any(scope.no_known_method for scope in scopes.values())


def test_turn_on_for_serves_hue_and_ikea_alone():
    """Every other class is one of the entries: none is served past its refusal, and none is merely left out."""
    served = next(adapter.scope.capabilities for adapter in ADAPTERS if adapter.action == "turn_on_for")

    assert set(served) == {"hue", "ikea"}


def test_turn_on_for_serves_no_switch_and_no_other_brand():
    """Plugs and switches of every brand are not built on it (docs/evidence.md, On trial): research predicts most fail
    (research/2026-11-14-timed-on-call-patterns.md), and no switch has a pass. Hue's bulbs keep their level; every
    other brand's light is not built, as no pass or research admits the default class."""
    scope = next(adapter.scope for adapter in ADAPTERS if adapter.action == "turn_on_for")

    for name in ("hue", "ikea"):
        assert REFUSALS["turn_on_for"][name].domains == {Platform.SWITCH}
        assert scope.refusal((name,), domain=Platform.SWITCH, failure_harms=True)[0] == Reason.NOT_BUILT
        assert scope.refusal((name,), domain=Platform.LIGHT, failure_harms=True) is None
        assert "plugs and switches ignore the timer" in REFUSALS["turn_on_for"][name].reason
    assert REFUSALS["turn_on_for"]["other"].domains is None
    for domain in (Platform.LIGHT, Platform.SWITCH):
        assert scope.refusal(("other",), domain=domain, failure_harms=True)[0] == Reason.NOT_BUILT


def test_get_attributes_reads_no_switch():
    """No ZHA action serves a switch, so neither does its read (docs/evidence.md, "A read serves only")."""
    scope = next(adapter.scope for adapter in ADAPTERS if adapter.action == "get_attributes")

    assert set(scope.domains) == {Platform.LIGHT}
