"""ZHA's refusal entries (refusals.py): the classes turn_on_for refuses because today's call would harm them. The
integration's, as the entries are: a family's own tests cover its rules and levels."""

from custom_components.deviceside import actions
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
    }
    assert all(isinstance(entry, NotBuilt) for entry in REFUSALS["turn_on_for"].values())
    assert [adapter.action for adapter in ADAPTERS if adapter.scope.harms(FAILURE_HARMS[adapter.action])] == [
        "turn_on_for"
    ]


def test_each_entry_is_in_its_adapter_s_scope():
    scopes = {adapter.action: adapter.scope for adapter in ADAPTERS}

    assert {action: dict(scope.not_built) for action, scope in scopes.items() if scope.not_built} == REFUSALS
    assert not any(scope.no_known_method for scope in scopes.values())


def test_turn_on_for_serves_hue_and_the_default_class_alone():
    """Every other class is one of the entries: none is served past its refusal, and none is merely left out."""
    served = next(adapter.scope.capabilities for adapter in ADAPTERS if adapter.action == "turn_on_for")

    assert set(served) == {"other", "hue"}
