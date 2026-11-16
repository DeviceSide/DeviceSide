"""AdapterScope levels: each domain, class and field carries one; a call's level is the weakest it touches. A class
with no known method, or that isn't served, is refused.

The scopes of the real adapters are checked here too: the invariants the dispatcher's gate relies on.
"""

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from custom_components.deviceside.core.adapter import Adapter
from custom_components.deviceside.core.errors import Reason
from custom_components.deviceside.core.registry import AdapterRegistry
from custom_components.deviceside.core.scope import (
    AdapterScope,
    DurationLimits,
    Family,
    FamilyScope,
    Level,
    NoKnownMethod,
    NotBuilt,
    OnDomains,
    OwnCall,
    Unplaced,
    documented,
    experimental,
    family_scope,
    verified,
)

PACKAGE = Path(__file__).resolve().parents[2] / "custom_components" / "deviceside"
# What reads the Experimental features option: only the option's definition, the entry setup and the dispatcher may.
OPTION_NAMES = {"CONF_EXPERIMENTAL", "EXPERIMENTAL_DEFAULT", "experimental_features"}
OPTION_READERS = {"const.py", "__init__.py", "config_flow.py", "core/runtime.py", "core/dispatcher.py"}


def test_levels_order_weakest_first():
    assert Level.EXPERIMENTAL < Level.DOCUMENTED < Level.VERIFIED


def test_helpers_merge_into_one_mapping():
    assert verified("a") | documented("c") | experimental("d") == {
        "a": Level.VERIFIED,
        "c": Level.DOCUMENTED,
        "d": Level.EXPERIMENTAL,
    }


def test_defaults_are_a_verified_light_with_every_capability():
    scope = AdapterScope()

    assert scope.domains == {"light": Level.VERIFIED}
    assert scope.level("light", ("anything",)) is Level.VERIFIED


@pytest.mark.parametrize(
    ("domain", "classes", "level"),
    [
        ("switch", (None,), Level.EXPERIMENTAL),  # a class the integration couldn't name fails safe
        ("switch", ("Switch",), Level.VERIFIED),
        ("switch", ("Light",), Level.DOCUMENTED),  # the weaker class lowers a Verified domain
        ("light", ("Switch",), Level.DOCUMENTED),  # and a Documented domain lowers a Verified class
        ("switch", ("Switch", "Light"), Level.DOCUMENTED),  # a native group takes its weakest member's
        ("switch", ("Switch", None), Level.EXPERIMENTAL),
        ("switch", (), Level.VERIFIED),  # an empty group has no class to weigh
    ],
)
def test_level_is_the_weakest_item_touched(domain, classes, level):
    scope = AdapterScope(
        domains=verified("switch") | documented("light"),
        capabilities=verified("Switch") | documented("Light"),
    )

    assert scope.level(domain, classes) is level


@pytest.mark.parametrize(
    ("fields", "level"),
    [
        ((), Level.VERIFIED),
        (("brightness",), Level.VERIFIED),
        (("brightness", "transition"), Level.EXPERIMENTAL),
    ],
)
def test_level_folds_in_the_fields_the_call_carries(fields, level):
    scope = AdapterScope(fields=verified("brightness") | experimental("transition"))

    assert scope.level("light", (), fields) is level


def test_a_class_outside_the_scope_counts_as_experimental():
    """The gate must not raise on a class the refusal didn't stop."""
    scope = AdapterScope(capabilities=verified("RGBCCT"))

    assert scope.level("light", ("Switch",)) is Level.EXPERIMENTAL


BROKEN = NoKnownMethod("Tuya plug", "It never switches on", "https://example.com/source", harms=False)


@pytest.mark.parametrize(
    ("classes", "reason"),
    [
        (("hue",), None),
        ((None,), None),  # unnamed: the gate weighs it, as Experimental
        ((), None),
        (("tuya_mcu",), (Reason.NOT_BUILT, None)),  # named, in neither capabilities nor no_known_method
        (("tuya_zcl",), (Reason.NO_KNOWN_METHOD, "It never switches on")),  # with the reason the user reads
        (("hue", "tuya_mcu"), (Reason.NOT_BUILT, None)),  # one member refuses the group
        (("tuya_mcu", "tuya_zcl", "hue"), (Reason.NO_KNOWN_METHOD, "It never switches on")),  # no known method wins
    ],
)
def test_a_class_with_no_known_method_or_not_served_is_refused(classes, reason):
    scope = AdapterScope(capabilities=verified("hue"), no_known_method={"tuya_zcl": BROKEN})

    assert scope.refusal(classes) == reason


HARMS = NoKnownMethod("Tuya plug", "It stays on", "https://example.com/source", harms=True)


def test_every_no_known_method_entry_states_whether_its_call_harms():
    """No default (plan Decision 30): an entry that left it out would pass as harmless and let an unplaced target
    through the call that harms its class."""
    with pytest.raises(TypeError):
        NoKnownMethod("Tuya plug", "It stays on", "https://example.com/source")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        NoKnownMethod("Tuya plug", "It stays on", "https://example.com/source", True)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("classes", "reason"),
    [
        ((Unplaced("hue"),), (Reason.CLASS_UNKNOWN, None)),  # it could still move into the harmed class
        ((None,), (Reason.CLASS_UNKNOWN, None)),  # unnamed, or a group of unknown membership
        (("hue", Unplaced("hue")), (Reason.CLASS_UNKNOWN, None)),  # one member refuses the group
        ((Unplaced("tuya_zcl"), "tuya_zcl"), (Reason.CLASS_UNKNOWN, None)),  # before no known method
        (("tuya_zcl",), (Reason.NO_KNOWN_METHOD, "It stays on")),
        (("hue",), None),
    ],
)
def test_where_the_call_harms_a_class_one_not_yet_placed_is_refused(classes, reason):
    scope = AdapterScope(capabilities=verified("hue"), no_known_method={"tuya_zcl": HARMS})

    assert scope.harms
    assert scope.refusal(classes) == reason


UNBUILT = NotBuilt("It would stay on", "https://example.com/source", harms=True)


@pytest.mark.parametrize(
    ("classes", "reason"),
    [
        ((Unplaced("hue"),), (Reason.CLASS_UNKNOWN, None)),  # it could still move into the harmed class
        ((None,), (Reason.CLASS_UNKNOWN, None)),  # unnamed, or a group of unknown membership
        (("hue", Unplaced("hue")), (Reason.CLASS_UNKNOWN, None)),
        ((Unplaced("tuya_zcl"),), (Reason.CLASS_UNKNOWN, None)),
        (("tuya_zcl",), (Reason.NOT_BUILT, "It would stay on")),  # placed: with the reason
        (("tuya_mcu",), (Reason.NOT_BUILT, None)),  # left out, with no entry
        (("hue",), None),
    ],
)
def test_a_not_built_class_the_call_harms_refuses_one_not_yet_placed(classes, reason):
    """Plan Decision 70: a not built yet class today's call would harm refuses unplaced and None targets as
    class_unknown, exactly as a harms no known method entry does."""
    scope = AdapterScope(capabilities=verified("hue"), not_built={"tuya_zcl": UNBUILT})

    assert scope.harms
    assert scope.refusal(classes) == reason


def test_a_not_built_entry_harms_and_stays_out_of_the_other_two():
    with pytest.raises(TypeError):
        NotBuilt("It would stay on", "https://example.com/source")  # type: ignore[call-arg]
    for other in ({"capabilities": verified("tuya_zcl")}, {"no_known_method": {"tuya_zcl": BROKEN}}):
        with pytest.raises(ValueError, match="not_built names classes"):
            AdapterScope(**{"capabilities": {}, **other}, not_built={"tuya_zcl": UNBUILT})
    # An unharmed not built yet class needs no entry: leaving it out refuses it the same way.
    with pytest.raises(ValueError, match=r"not_built entries \['tuya_zcl'\] don't harm"):
        AdapterScope(capabilities=verified("hue"), not_built={"tuya_zcl": replace(UNBUILT, harms=False)})


def test_elsewhere_an_unplaced_class_is_the_class_it_names():
    scope = AdapterScope(capabilities=verified("hue"), no_known_method={"tuya_zcl": BROKEN})

    assert not scope.harms
    assert scope.refusal((Unplaced("hue"),)) is None
    assert scope.refusal((Unplaced("tuya_zcl"),)) == (Reason.NO_KNOWN_METHOD, "It never switches on")
    assert scope.level("light", (Unplaced("hue"),)) is Level.VERIFIED
    assert Unplaced("hue") == "hue"
    assert hash(Unplaced("hue")) == hash("hue")
    assert repr(Unplaced("hue")) == "Unplaced('hue')"


def test_a_scope_without_classes_refuses_none():
    assert AdapterScope().refusal(("anything",)) is None


def test_a_class_is_never_both_served_and_no_known_method():
    with pytest.raises(ValueError, match="classes the scope serves"):
        AdapterScope(capabilities=verified("hue"), no_known_method={"hue": BROKEN})


def test_a_class_held_on_some_domains_alone_is_experimental_on_the_rest():
    """A Hue bulb's record proves nothing about a Hue plug: `hue` on lights alone leaves a Hue switch flagged."""
    scope = AdapterScope(
        domains=verified("light", "switch"),
        capabilities=verified("hue", domains=("light",)) | documented("other"),
    )

    assert scope.capabilities["hue"] == OnDomains(Level.VERIFIED, frozenset({"light"}))
    assert scope.level("light", ["hue"]) is Level.VERIFIED
    assert scope.level("switch", ["hue"]) is Level.EXPERIMENTAL
    assert scope.level("switch", ["other"]) is Level.DOCUMENTED  # an entry on every domain, as before
    assert scope.class_entries() == [
        ("hue", Level.VERIFIED, frozenset({"light"})),
        ("other", Level.DOCUMENTED, None),
    ]
    assert scope.refusal(["hue"]) is None  # served, so not refused: gated by its level


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        (lambda: AdapterScope(capabilities=verified("hue", domains=("switch",))), "domains the scope doesn't serve"),
        (lambda: AdapterScope(domains=verified("light", domains=("light",))), "domains take no domains"),
        (lambda: AdapterScope(fields=verified("brightness", domains=("light",))), "fields take no domains"),
    ],
)
def test_only_a_class_is_held_on_domains_the_scope_serves(scope, message):
    with pytest.raises(ValueError, match=message):
        scope()


OWN = DurationLimits(min_s=1, max_s=10, step_s=1)


async def _send(adapter, hass, request, target):
    raise AssertionError("no scope test sends")


TIMED = OwnCall(_send, OWN)
UNTIMED = OwnCall(_send)


def test_a_class_with_a_call_of_its_own_gets_its_limits_and_keeps_a_group_apart():
    scope = AdapterScope(
        duration=DurationLimits(min_s=0, max_s=100),
        capabilities=verified("A") | experimental("B", "C"),
        own_calls={"B": TIMED, "C": UNTIMED},
    )

    assert scope.own_call(["B"]) is scope.own_call([Unplaced("B")]) is TIMED
    assert scope.own_call(["C"]) is UNTIMED
    assert scope.own_call(["A"]) is scope.own_call([None]) is None
    assert scope.limits(["B"]) is OWN
    assert scope.limits([Unplaced("B")]) is OWN
    # One whose own call keeps the scope's limits, and one with no call of its own, get the scope's.
    assert scope.limits(["C"]) is scope.duration
    assert scope.limits(["A"]) is scope.duration
    assert scope.limits([None]) is scope.duration
    assert scope.apart(["A", "B"]) and scope.apart(["C"])
    assert not scope.apart(["A", None])
    # A listed group with such a member falls back to its members; the member itself, and any other group, run.
    assert scope.refusal(["A", "B"], group=True) == (Reason.OWN_CALL, None)
    assert scope.refusal(["B"]) is None
    assert scope.refusal(["A"], group=True) is None


def test_a_call_of_its_own_is_for_a_class_the_scope_serves():
    with pytest.raises(ValueError, match="own_calls names classes the scope doesn't serve"):
        AdapterScope(capabilities=verified("A"), own_calls={"B": TIMED})
    with pytest.raises(ValueError, match="own_calls names classes the scope doesn't serve"):
        AdapterScope(own_calls={"B": TIMED})


def test_an_own_call_is_compared_by_identity():
    """The dispatcher keys a run by it: an equal copy is another call, and classes share a run only on one object."""
    assert OwnCall(_send, OWN) != TIMED
    assert len({TIMED, OwnCall(_send, OWN), TIMED}) == 2


BROKEN = NoKnownMethod("Plug D", "It never switches on", "https://example.com/d", harms=False)
UNBUILT = NotBuilt("It would stay on", "https://example.com/e", harms=True)
FAMILIES = (
    Family(
        key="first",
        classes=frozenset({"A", "B", "D"}),
        scopes={
            "turn_on_for": FamilyScope(
                capabilities=verified("A") | experimental("B"), no_known_method={"D": BROKEN}, own_calls={"B": TIMED}
            ),
            "stop": FamilyScope(capabilities=documented("A")),
        },
    ),
    Family(
        key="second",
        maintainers=("a-b",),
        classes=frozenset("CE"),
        scopes={"turn_on_for": FamilyScope(capabilities=documented("C"), not_built={"E": UNBUILT})},
    ),
)


def test_family_scope_merges_the_families_parts_for_one_action():
    merged = family_scope(FAMILIES, "turn_on_for")

    assert merged == FamilyScope(
        capabilities=verified("A") | experimental("B") | documented("C"),
        no_known_method={"D": BROKEN},
        not_built={"E": UNBUILT},
        own_calls={"B": TIMED},
    )
    # An adapter builds its scope from the parts, each under AdapterScope's field of the same name.
    scope = AdapterScope(
        capabilities=merged.capabilities,
        no_known_method=merged.no_known_method,
        not_built=merged.not_built,
        own_calls=merged.own_calls,
    )
    assert scope.own_call(["B"]) is TIMED
    assert scope.refusal(["E"]) == (Reason.NOT_BUILT, "It would stay on")


def test_an_action_a_family_gives_no_scope_leaves_its_classes_out():
    """So the adapter's scope doesn't serve them, and they are refused as not built yet."""
    assert family_scope(FAMILIES, "stop") == FamilyScope(capabilities=documented("A"))
    assert family_scope(FAMILIES, "fade_brightness") == family_scope((), "stop") == FamilyScope()


def test_a_class_in_two_families_is_refused():
    twice = (*FAMILIES, Family(key="third", classes=frozenset("AF")))
    # Whichever action is asked for, as the third family's scope for another could hold the class.
    with pytest.raises(ValueError, match=r"families 'first' and 'third' both hold classes \['A'\]"):
        family_scope(twice, "stop")


def test_a_documented_field_is_refused():
    with pytest.raises(ValueError, match="fields are never Documented"):
        AdapterScope(fields=documented("brightness"))


@pytest.mark.parametrize("helper", [verified, experimental])
def test_a_field_may_be_verified_or_experimental(helper):
    assert AdapterScope(fields=helper("brightness")).fields == helper("brightness")


def test_an_unlisted_field_takes_its_level_from_fields():
    scope = AdapterScope(
        fields=verified("brightness") | experimental("color_temp_kelvin"), unlisted=frozenset({"color_temp_kelvin"})
    )
    assert scope.level("light", fields={"color_temp_kelvin"}) is Level.EXPERIMENTAL


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        pytest.param({"fields": experimental("duration")}, "never lacks", id="not_a_lackable_field"),
        pytest.param({"fields": {}}, "outside the scope's fields", id="not_in_fields"),
        pytest.param(
            {"fields": experimental("transition"), "drops": frozenset({"transition"})}, "the scope drops", id="dropped"
        ),
    ],
)
def test_unlisted_names_only_lackable_fields_in_scope_and_not_dropped(scope, message):
    unlisted = frozenset(scope["fields"]) or frozenset({"transition"})
    with pytest.raises(ValueError, match=message):
        AdapterScope(**scope, unlisted=unlisted)


def test_mappings_are_read_only_copies_and_the_scope_hashes():
    shared = verified("Switch")
    scope = AdapterScope(capabilities=shared)
    shared["Light"] = Level.VERIFIED

    assert "Light" not in scope.capabilities
    with pytest.raises(TypeError):
        scope.domains["switch"] = Level.VERIFIED
    assert hash(scope) == hash(scope)


def _adapters() -> list[Adapter]:
    return [adapter for _, _, adapter in AdapterRegistry.discover().matrix() if adapter is not None]


def test_only_the_dispatcher_and_entry_setup_read_the_experimental_option():
    """The dispatcher is the one gate: an adapter, action or other core module that read the option could change how
    a proven item behaves."""
    found = [
        f"{path.relative_to(PACKAGE)}:{node.lineno}"
        for path in PACKAGE.rglob("*.py")
        if path.relative_to(PACKAGE).as_posix() not in OPTION_READERS
        for node in ast.walk(ast.parse(path.read_text()))
        if (isinstance(node, ast.Name) and node.id in OPTION_NAMES)
        or (isinstance(node, ast.Attribute) and node.attr in OPTION_NAMES)
        or (isinstance(node, ast.alias) and node.name in OPTION_NAMES)
        or (isinstance(node, ast.Constant) and node.value == "experimental_features")
    ]
    assert found == []


def _covers(stop: AdapterScope | None, items: str, item: str, level: Level) -> bool:
    if stop is None:
        return False
    mapping = getattr(stop, items)
    if mapping is None:  # stop addresses every capability, as Verified
        return True
    return mapping.get(item, -1) >= level


def test_every_move_has_a_stop_at_least_as_strong():
    """A raise or lower that starts where stop is refused, or gated behind the option, can't be halted. Item levels
    and the adapter-level flag: group reach (native_groups against expand_group) and refusals in supports() that don't
    come from scope are not compared."""
    adapters = _adapters()
    stops = {adapter.integration: adapter.scope for adapter in adapters if adapter.action == "stop"}
    gaps = []
    for adapter in adapters:
        if not adapter.action.startswith(("raise_", "lower_")):
            continue
        stop = stops.get(adapter.integration)
        name = f"{adapter.integration} / {adapter.action}"
        if stop is not None and stop.experimental and not adapter.scope.experimental:
            gaps.append(f"{name}: stop is flagged experimental")
        for domain, level in adapter.scope.domains.items():
            if not _covers(stop, "domains", domain, level):
                gaps.append(f"{name}: domain {domain} ({level.name})")
        if adapter.scope.capabilities is None:
            if stop is None or stop.capabilities is not None:
                gaps.append(f"{name}: every capability, which stop doesn't cover")
            continue
        for capability, level in adapter.scope.capabilities.items():
            if not _covers(stop, "capabilities", capability, level):
                gaps.append(f"{name}: capability {capability} ({level.name})")
    assert gaps == []
