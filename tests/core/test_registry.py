"""Registry building: guarded integration import, adapter validation, matrix iteration."""

import importlib
import logging
from dataclasses import replace
from itertools import product
from types import SimpleNamespace

import pytest

from custom_components.deviceside import actions
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.scope import (
    Family,
    FamilyScope,
    IntegrationInfo,
    Level,
    NoKnownMethod,
    NotBuilt,
    OwnCall,
    experimental,
    verified,
)

from ..conftest import FAKE_INTEGRATIONS
from ..fakes.fake_integration import ADAPTERS, INTEGRATION, FakeSetAttributes, FakeTurnOffFor, FakeTurnOnFor


def _registry(adapters=ADAPTERS, info=INTEGRATION) -> AdapterRegistry:
    """A registry of the fake integration alone, with these adapters and this info."""
    return AdapterRegistry(actions.discover(), [SimpleNamespace(INTEGRATION=info, ADAPTERS=adapters)])


def test_broken_integration_is_recorded_unavailable_and_others_load():
    registry = AdapterRegistry(actions.discover(), FAKE_INTEGRATIONS)

    broken = registry.integrations["broken_integration"]
    assert not broken.available
    assert "fakelib" in broken.unavailable_reason
    assert [info.key for info in registry.available_integrations()] == ["fake", "fake_special"]
    assert registry.adapter("turn_on_for", "fake").integration == "fake"


@pytest.mark.parametrize(
    ("missing", "level"),
    [("fakelib", logging.DEBUG), ("homeassistant.components.fake.gone", logging.WARNING), (None, logging.DEBUG)],
)
def test_import_failure_warns_only_when_our_code_is_out_of_step(monkeypatch, caplog, missing, level):
    def fail(module):
        raise ImportError(f"no {missing}", name=missing)

    discovered = actions.discover()
    monkeypatch.setattr(importlib, "import_module", fail)
    with caplog.at_level(logging.DEBUG, logger="custom_components.deviceside.core.registry"):
        registry = AdapterRegistry(discovered, ["custom_components.deviceside.integrations.fake"])

    assert not registry.integrations["fake"].available
    assert [record.levelno for record in caplog.records] == [level]


def test_matrix_lists_every_pair_sorted():
    discovered = actions.discover()
    registry = AdapterRegistry(discovered, FAKE_INTEGRATIONS)
    matrix = list(registry.matrix())

    keys = sorted(action.key for action in discovered)
    integrations = ["broken_integration", "fake", "fake_special"]
    assert [(action, integration) for action, integration, _ in matrix] == list(product(keys, integrations))
    assert [(action, integration) for action, integration, adapter in matrix if adapter is not None] == [
        ("set_attributes", "fake"),
        ("turn_off_for", "fake"),
        ("turn_on_for", "fake"),
        ("turn_on_for", "fake_special"),
    ]


def test_adapter_for_unknown_action_is_refused():
    class Stray(FakeTurnOnFor):
        action = "no_such_action"

    with pytest.raises(ValueError, match="unknown action"):
        _registry([Stray])


CLASSED = replace(INTEGRATION, capability=lambda hass, target: "hue", classes=frozenset({"hue", "tuya", "other"}))
NO_METHOD = NoKnownMethod("Tuya plug", "It never switches on", "https://example.com/source")
NOT_BUILT = NotBuilt("It would stay on", "https://example.com/source")


class Classed(FakeTurnOnFor):
    scope = replace(FakeTurnOnFor.scope, capabilities=verified("hue") | experimental("other"))


def test_an_integration_naming_classes_needs_them_in_every_scope():
    _registry([Classed], CLASSED)
    with pytest.raises(ValueError, match="names classes, but its scope holds none"):
        _registry([Classed, FakeTurnOffFor], CLASSED)


@pytest.mark.parametrize(
    "scope",
    [
        pytest.param(replace(FakeTurnOnFor.scope, capabilities=verified("hue")), id="capabilities"),
        pytest.param(replace(FakeTurnOnFor.scope, no_known_method={"tuya": NO_METHOD}), id="no_known_method"),
        pytest.param(replace(FakeTurnOnFor.scope, not_built={"tuya": NOT_BUILT}), id="not_built"),
    ],
)
def test_an_integration_naming_no_classes_needs_them_in_no_scope(scope):
    class Stray(FakeTurnOnFor):
        pass

    Stray.scope = scope
    with pytest.raises(ValueError, match="holds classes, but fake names none"):
        _registry([Stray])


@pytest.mark.parametrize(
    "entries", [{"no_known_method": {"tuya_zcl": NO_METHOD}}, {"not_built": {"tuya_zcl": NOT_BUILT}}]
)
def test_a_scope_holds_only_classes_its_integration_declares(entries):
    class Typo(FakeTurnOnFor):
        scope = replace(Classed.scope, **entries)

    with pytest.raises(ValueError, match=r"doesn't declare \(IntegrationInfo.classes\): \['tuya_zcl'\]"):
        _registry([Typo], CLASSED)


def test_the_default_class_is_never_verified():
    """docs/evidence.md, Device classes: it holds every device not yet placed, so no record proves it."""
    defaulted = replace(CLASSED, default_class="other")
    _registry([Classed], defaulted)

    class Lifted(FakeTurnOnFor):
        scope = replace(Classed.scope, capabilities=verified("hue", "other"))

    with pytest.raises(ValueError, match="holds fake's default class 'other' as Verified"):
        _registry([Lifted], defaulted)
    _registry([Lifted], CLASSED)  # with no default class, any class may be Verified


def test_the_default_class_is_a_declared_one():
    with pytest.raises(ValueError, match="default_class 'ikea' is none of its classes"):
        _registry([Classed], replace(CLASSED, default_class="ikea"))


def test_shelly_names_no_default_class_and_zigbee2mqtt_holds_its_below_verified():
    registry = AdapterRegistry.discover()
    assert registry.integrations["shelly"].default_class is None
    z2m = [adapter for _, key, adapter in registry.matrix() if key == "zigbee2mqtt" and adapter is not None]
    assert z2m
    assert all(adapter.scope.capabilities["other"] < Level.VERIFIED for adapter in z2m)


@pytest.mark.parametrize(
    "info",
    [replace(INTEGRATION, classes=frozenset({"hue"})), replace(CLASSED, classes=frozenset())],
    ids=["classes_alone", "capability_alone"],
)
def test_capability_and_classes_come_together(info):
    with pytest.raises(ValueError, match="capability and classes come together"):
        _registry([FakeTurnOnFor], info)


@pytest.mark.parametrize(
    ("maintainers", "error"),
    [
        ((), "non-empty tuple"),
        (["jasonmx"], "non-empty tuple"),
        (("@jasonmx",), "not GitHub handles"),
        (("jason mx",), "not GitHub handles"),
        (("-jasonmx",), "not GitHub handles"),
        (("a" * 40,), "not GitHub handles"),
        (("jasonmx", "jasonmx"), "twice"),
    ],
)
def test_an_integration_must_name_its_maintainers_by_handle(maintainers, error):
    with pytest.raises(ValueError, match=error):
        _registry(info=replace(INTEGRATION, maintainers=maintainers))


def test_several_maintainers_are_accepted():
    registry = _registry(info=replace(INTEGRATION, maintainers=("jasonmx", "a-b", "a" * 39)))
    assert registry.integrations["fake"].maintainers == ("jasonmx", "a-b", "a" * 39)


# Two families holding every class of CLASSED but its default one, `other`.
HUE_FAMILY = Family(
    key="hue", classes=frozenset({"hue"}), scopes={"turn_on_for": FamilyScope(capabilities=verified("hue"))}
)
TUYA_FAMILY = Family(
    key="tuya",
    maintainers=("a-b",),
    classes=frozenset({"tuya"}),
    scopes={"turn_on_for": FamilyScope(capabilities=experimental("tuya"))},
)
WITH_FAMILIES = replace(CLASSED, default_class="other", families=(HUE_FAMILY, TUYA_FAMILY))


def test_a_family_scope_for_an_unknown_action_is_refused():
    typo = replace(HUE_FAMILY, scopes={"turn_on_fro": FamilyScope()})
    with pytest.raises(ValueError, match="family 'hue' holds scopes for unknown actions"):
        _registry([Classed], replace(WITH_FAMILIES, families=(typo, TUYA_FAMILY)))


def test_a_family_scope_for_an_action_the_integration_has_no_adapter_for_is_refused():
    """A real action, so no typo: the family's levels for it would be read by nothing, with nothing saying so."""
    unread = replace(HUE_FAMILY, scopes={**HUE_FAMILY.scopes, "stop": FamilyScope(capabilities=verified("hue"))})
    with pytest.raises(ValueError, match=r"family 'hue' holds scopes for actions fake has no adapter for: \['stop'\]"):
        _registry([Classed], replace(WITH_FAMILIES, families=(unread, TUYA_FAMILY)))


def test_families_that_split_the_classes_between_them_are_accepted():
    registry = _registry([Classed], WITH_FAMILIES)
    assert [family.key for family in registry.integrations["fake"].families] == ["hue", "tuya"]
    # No maintainers is fine: the integration's own every family of it.
    assert HUE_FAMILY.maintainers == ()


@pytest.mark.parametrize(
    ("families", "error"),
    [
        pytest.param(
            (replace(HUE_FAMILY, key="Hue"), TUYA_FAMILY), "'Hue' is not shaped like a package name", id="key"
        ),
        pytest.param(
            (replace(HUE_FAMILY, key="hue-2"), TUYA_FAMILY), "not shaped like a package name", id="key_hyphen"
        ),
        pytest.param((HUE_FAMILY, replace(TUYA_FAMILY, key="hue")), "family 'hue' is declared twice", id="key_twice"),
        pytest.param(
            (replace(HUE_FAMILY, maintainers=("@a-b",)), TUYA_FAMILY), "family 'hue': .*not GitHub handles", id="handle"
        ),
        pytest.param(
            (replace(HUE_FAMILY, maintainers=("a-b", "a-b")), TUYA_FAMILY), "family 'hue': .*twice", id="handle_twice"
        ),
        pytest.param(
            (replace(HUE_FAMILY, maintainers=["a-b"]), TUYA_FAMILY),
            "family 'hue': maintainers must be a tuple",
            id="list",
        ),
        pytest.param(
            (HUE_FAMILY, replace(TUYA_FAMILY, classes=frozenset({"tuya", "hue"}))),
            r"family 'tuya' holds classes family 'hue' holds: \['hue'\]",
            id="class_in_two",
        ),
        pytest.param((HUE_FAMILY,), r"classes \['tuya'\] are in no family", id="class_in_none"),
        pytest.param(
            (HUE_FAMILY, replace(TUYA_FAMILY, classes=frozenset({"tuya", "other"}))),
            "family 'tuya' holds the default class 'other'",
            id="default_class",
        ),
        pytest.param(
            (HUE_FAMILY, replace(TUYA_FAMILY, classes=frozenset({"tuya", "tuya_zcl"}))),
            r"family 'tuya' holds classes fake doesn't declare \(IntegrationInfo.classes\): \['tuya_zcl'\]",
            id="undeclared_class",
        ),
        *(
            pytest.param(
                (replace(HUE_FAMILY, scopes={"stop": FamilyScope(**{part: {"tuya": entry}})}), TUYA_FAMILY),
                r"family 'hue': its scopes name classes that aren't its own: \['tuya'\]",
                id=f"foreign_{part}",
            )
            for part, entry in (("capabilities", Level.EXPERIMENTAL), ("own_calls", OwnCall(None)))
        ),
    ],
)
def test_families_are_checked(families, error):
    with pytest.raises(ValueError, match=error):
        _registry([Classed], replace(WITH_FAMILIES, families=families))


def test_an_integration_without_families_is_checked_for_none():
    """Families are opt-in: the classes of an integration that has none need no family."""
    _registry([Classed], replace(WITH_FAMILIES, families=()))


def test_production_discovery_imports_cleanly():
    registry = AdapterRegistry.discover()
    assert set(registry.actions) == {
        "clear_auto_off",
        "clear_auto_on",
        "get_attributes",
        "lower_brightness",
        "lower_hue",
        "lower_saturation",
        "raise_brightness",
        "raise_hue",
        "raise_saturation",
        "set_attributes",
        "set_auto_off",
        "set_auto_on",
        "set_scene",
        "stop",
        "turn_off_for",
        "turn_on_for",
    }
    assert registry.integrations["shelly"].available
    assert registry.integrations["hue"].available
    assert registry.adapter("turn_on_for", "shelly") is not None
    assert registry.adapter("turn_off_for", "shelly") is not None
    assert all(info.maintainers for info in registry.available_integrations())


def test_each_adapter_takes_its_actions_kind_which_ends_its_warnings():
    registry = AdapterRegistry.discover()

    query, command = registry.adapter("get_attributes", "hue"), registry.adapter("stop", "hue")
    setting = registry.adapter("set_auto_off", "shelly")

    assert query.consequence == "so its attributes aren't reported"
    assert command.consequence == "so HA may show the old values"
    assert setting.consequence == "so the device may keep its old setting"


def test_call_resolvers_are_keyed_by_ha_domain():
    registry = AdapterRegistry.discover()

    assert set(registry.call_resolvers()) == {"hue", "zha", "mqtt"}


def test_two_call_resolvers_for_one_ha_domain_are_refused():
    registry = AdapterRegistry(actions.discover(), FAKE_INTEGRATIONS)
    for info in registry.available_integrations():
        registry.integrations[info.key] = replace(info, ha_domain="shared", call_resolver=object())

    with pytest.raises(ValueError, match="ha_domain shared"):
        registry.call_resolvers()


def test_an_import_that_raises_anything_marks_the_integration_unavailable_and_logs_it(monkeypatch, caplog):
    def fail(module):
        raise AttributeError("module 'homeassistant.components.fake' has no attribute 'gone'")

    discovered = actions.discover()
    monkeypatch.setattr(importlib, "import_module", fail)
    with caplog.at_level(logging.DEBUG, logger="custom_components.deviceside.core.registry"):
        registry = AdapterRegistry(discovered, ["custom_components.deviceside.integrations.fake"])

    info = registry.integrations["fake"]
    assert not info.available
    assert "AttributeError" in info.unavailable_reason
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert caplog.records[0].exc_info is not None


def _refused(**changes):
    """An integration declared only to refuse a gateway on the fake's domain (IntegrationInfo.unsupported)."""
    fields = {
        "key": "fake_old",
        "title": "Fake old gateway",
        "ha_domain": INTEGRATION.ha_domain,
        "maintainers": ("handle",),
        "detect": lambda hass, entry, device: True,
        "unsupported": "Old gateways aren't supported",
    }
    return IntegrationInfo(**(fields | changes))


def _with_unsupported(*refused) -> AdapterRegistry:
    module = SimpleNamespace(INTEGRATION=INTEGRATION, ADAPTERS=ADAPTERS, UNSUPPORTED=list(refused))
    return AdapterRegistry(actions.discover(), [module])


def test_an_unsupported_integration_is_kept_apart_from_the_integrations():
    # The cards, the release gate and CODEOWNERS read `integrations`; the refused one has nothing for them.
    registry = _with_unsupported(_refused())

    assert list(registry.unsupported) == ["fake_old"]
    assert "fake_old" not in registry.integrations
    assert all(integration != "fake_old" for _, integration, _ in registry.matrix())


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        pytest.param({"unsupported": ""}, "without a reason", id="no_reason"),
        pytest.param({"detect": None}, "needs a detect hook", id="no_detect"),
        pytest.param({"ha_domain": "elsewhere"}, "needs a detect hook", id="other_domain"),
        pytest.param({"key": INTEGRATION.key}, "declared twice", id="its_siblings_key"),
        pytest.param({"maintainers": ()}, "maintainers", id="no_maintainers"),
    ],
)
def test_an_unsupported_integration_must_only_refuse(changes, error):
    with pytest.raises(ValueError, match=error):
        _with_unsupported(_refused(**changes))


def test_an_unsupported_integration_is_declared_once():
    with pytest.raises(ValueError, match="declared twice"):
        _with_unsupported(_refused(), _refused())


def test_an_integration_with_adapters_cant_be_unsupported():
    with pytest.raises(ValueError, match="can't be unsupported"):
        _registry(info=replace(INTEGRATION, unsupported="no"))


def test_production_declares_the_hue_v1_bridge_unsupported():
    registry = AdapterRegistry.discover()

    assert list(registry.unsupported) == ["hue_v1"]
    assert registry.unsupported["hue_v1"].ha_domain == registry.integrations["hue"].ha_domain


def test_failure_harms_on_the_timed_and_auto_on_off_actions_alone():
    """docs/evidence.md, When today's call harms a class: the registry hands each adapter its action's."""
    assert {action.key for action in actions.discover() if action.failure_harms} == {
        "turn_on_for",
        "turn_off_for",
        "set_auto_off",
        "set_auto_on",
        "clear_auto_off",
        "clear_auto_on",
    }
    registry = AdapterRegistry(actions.discover(), FAKE_INTEGRATIONS)
    assert registry.adapter("turn_on_for", "fake").failure_harms
    assert not registry.adapter("set_attributes", "fake").failure_harms


@pytest.mark.parametrize(
    ("action", "integration", "harms"),
    [
        ("turn_on_for", "zha", True),  # its Tuya, Sengled and Sonoff not_built entries
        ("set_scene", "hue", False),  # a smart scene has no known method, but set_scene's failure doesn't harm
        ("turn_on_for", "shelly", False),  # no refusal entry, so no refused class an unplaced device could be in
    ],
)
def test_harms_is_derived_from_the_action_and_the_scope_s_entries(action, integration, harms):
    adapter = AdapterRegistry.discover().adapter(action, integration)

    assert adapter.scope.harms(adapter.failure_harms) is harms


def test_a_not_built_entry_only_on_an_action_whose_failure_harms():
    """A class not built yet that the call leaves unharmed needs no entry: leaving it out refuses it the same way."""

    class Unharmed(FakeSetAttributes):
        scope = replace(FakeSetAttributes.scope, capabilities=verified("hue"), not_built={"tuya": NOT_BUILT})

    class Harmed(FakeTurnOnFor):
        scope = replace(Classed.scope, not_built={"tuya": NOT_BUILT})

    with pytest.raises(ValueError, match=r"not_built entries \['tuya'\], but set_attributes's failure doesn't harm"):
        _registry([Unharmed, Classed], CLASSED)
    _registry([Harmed], CLASSED)
