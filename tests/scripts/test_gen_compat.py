"""scripts/gen_compat.py: evidence from the records and `_manual.json`, models from devices.yaml, the README cards, the
page's generated block, and the stale check."""

import copy
import re
from types import SimpleNamespace

import pytest
import yaml
from homeassistant.const import Platform

from custom_components.deviceside.actions import discover
from custom_components.deviceside.core.scope import (
    AdapterScope,
    Caveat,
    CaveatKind,
    Level,
    NoKnownMethod,
    NotBuilt,
    documented,
    labs,
    labs_fields,
    verified,
)
from scripts import check_release as cr
from scripts import gen_compat as gc
from scripts import gen_features as gf

from .record_files import (
    bound,
    device,
    manual,
    old_device,
    old_group,
    old_test,
    ran,
    record_v1,
    record_v2,
    signoff,
    skipped,
    write,
)

LIGHT = frozenset({Platform.LIGHT})
# The classes the tests' scopes hold, each with its domains, as a Shelly-like integration declares them: a relay can be
# a switch or a light; the rest are lights. `hue` and `other` are Hue's, which classes scenes too.
CLASSES = {
    "Switch": frozenset({Platform.SWITCH, Platform.LIGHT}),
    **dict.fromkeys(("Light", "CCT", "RGB", "RGBCCT"), LIGHT),
    **dict.fromkeys(("hue", "other"), frozenset({Platform.LIGHT, Platform.SCENE})),
    "Hidden": LIGHT,  # one devices.yaml gives no phrase
}

URL = gc.PAGE_URL
DATA = {
    "requires": {"zha": "Zigbee 3.0"},
    "models": [
        {"name": "Hue lamp", "ids": ["LTA009", "9290024684"], "type": "bulb"},
        {"name": "Plug", "ids": ["P1"], "type": "plug"},
    ],
    "capabilities": {
        "zha": {
            "light": {"phrase": "lights", "section": "Lights"},
            "switch": {"phrase": "plugs", "section": "Zigbee plugs"},
            "Switch": {
                "phrase": "relays",
                "section": "Relays",
                "domains": {"light": "relays as lights", "switch": "relays"},
            },
            "Light": {"phrase": "dimmers", "section": "Dimmers"},
            "CCT": {"phrase": "CCT controllers", "section": "Dimmers"},
            "RGB": {"phrase": "RGB controllers", "section": "Dimmers"},
            "RGBCCT": {"phrase": "bulbs", "section": "Bulbs"},
        },
        "hue": {
            "light": {"phrase": "lights", "section": "Lights"},
            "switch": {"phrase": "plugs", "section": "Zigbee plugs"},
            "scene": {"phrase": "scenes", "section": "Scenes"},
        },
    },
    "no_known_method": [{"what": "Old plug", "integrations": ["zha"], "reason": "No timer", "source": "https://x.y/z"}],
}
PROSE = "# Page\n\n"


def records_dir(root, integration):
    return root / "docs" / "integrations" / integration / "test-records"


def record(root, integration, name, *, result="pass", devices=None, tests=None):
    """A format 1 record (converted from markdown): the run's `devices`, and `tests` without devices."""
    action, *options = name.split("-")
    data = record_v1(integration, action, result=result, devices=devices, tests=tests, options=options)
    return write(records_dir(root, integration) / f"{name}.json", data)


def record2(root, integration, name, *tests, result="pass"):
    """A format 2 record: the devices each test reached."""
    action, *options = name.split("-")
    data = record_v2(integration, action, list(tests), result=result, options=options)
    return write(records_dir(root, integration) / f"{name}.json", data)


class FakeRegistry:
    integrations = {
        "zha": SimpleNamespace(title="ZHA", maintainers=("jasonmx",), capability=None, classes={}, default_class=None),
        "hue": SimpleNamespace(
            title="Hue", maintainers=("jasonmx", "other"), capability=None, classes={}, default_class=None
        ),
    }

    def __init__(self, *adapters):
        self._adapters = adapters
        # The cards read a class's domains, so each class a scope names is declared, as the registry holds it.
        self.integrations = {
            key: SimpleNamespace(**vars(info) | {"classes": dict(info.classes)})
            for key, info in self.integrations.items()
        }
        for adapter in adapters:
            scope = adapter.scope
            named = (scope.capabilities or {}).keys() | scope.no_known_method.keys() | scope.not_built.keys()
            self.integrations[adapter.integration].classes |= {name: CLASSES[name] for name in named}

    def matrix(self):
        yield "stop", "hue", None
        for adapter in self._adapters:
            yield adapter.action, adapter.integration, adapter


def adapter(integration, action, scope=None):
    return SimpleNamespace(integration=integration, action=action, scope=scope or AdapterScope())


def data(registry=None, **changes):
    return gc.load_raw({**DATA, **changes}, registry or FakeRegistry())


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "REPO", tmp_path)
    monkeypatch.setattr(cr, "BUNDLES", tmp_path / "docs" / "integrations")
    return tmp_path


def what_it_tested(path):
    return gc.tested(cr.load(path))


def test_a_format_1_record_tested_its_runs_devices_and_a_group_is_no_model(root):
    devices = [old_device("LTA009", "1.2"), old_device("LCA016", "0x01"), old_group(), old_group("Group", "Z2M 2.1")]
    path = record(root, "hue", "stop", devices=devices)
    assert what_it_tested(path) == [gc.Tested("LTA009", "1.2"), gc.Tested("LCA016", "0x01"), gc.GROUP, gc.GROUP]
    assert what_it_tested(record(root, "hue", "set_scene", devices=[])) == []


def test_a_format_2_record_tested_each_passing_tests_devices_with_their_classes(root):
    signify = device("LTA009", "1.2", "hue", manufacturer="Signify Netherlands B.V.")  # read, not yet on the cards
    path = record2(
        root,
        "hue",
        "stop",
        ran("light", signify),
        ran("light", device("LCA016", "0x01", "hue"), device("LTA009", "1.2", "hue"), group=True),
        skipped(),
    )
    assert what_it_tested(path) == [
        gc.Tested("LTA009", "1.2", "hue", domain="light"),
        gc.Tested(None, domain="light"),  # a group
    ]


def test_a_model_a_record_names_must_be_in_models_yaml(root):
    record(root, "zha", "stop", devices=[old_device("NEW1", "1")])
    with pytest.raises(SystemExit, match="stop.json: model 'NEW1' is in neither docs/models.yaml"):
        gc.check_models(FakeRegistry(), data())


@pytest.mark.parametrize(
    "test",
    [
        ran("light", device("NEW2", "1", None)),  # a null class, which credits nothing
        ran("light", device("NEW2", "1"), result="fail"),  # a failing test
    ],
    ids=["null class", "failing"],
)
def test_every_model_a_record_names_must_be_in_models_yaml_whether_or_not_it_credits(root, test):
    record2(root, "zha", "stop", test, result=test["result"])
    with pytest.raises(SystemExit, match="model 'NEW2' is in neither docs/models.yaml"):
        gc.check_models(FakeRegistry(), data())


def test_a_record_naming_a_class_fails_on_an_integration_that_names_none(root):
    """On the PR that lands it, not first at the cut (check_release --signoffs)."""
    record2(root, "zha", "stop", ran("light", device("P1", "1", "Switch")))
    with pytest.raises(SystemExit, match="stop.json test 1 .*: a class, but zha names no classes"):
        gc.check_models(FakeRegistry(), data())
    classed = adapter("zha", "stop", AdapterScope(capabilities=verified("Switch")))
    gc.check_models(classed_registry(classed), data())  # an integration that names classes takes it


def test_a_fact_rows_models_must_be_in_models_yaml_and_a_dotfile_is_skipped(root):
    facts = {"format": 2, "integration": "zha", "facts": [{
        "date": "2026-11-14", "suite": "stop", "test": "t[r]", "kind": "automated", "result": "pass",
        "devices": [device("NEW3", "1")],
    }]}  # fmt: skip
    write(records_dir(root, "zha") / "_facts.json", facts)
    (records_dir(root, "zha") / ".DS_Store").write_bytes(b"\0")
    with pytest.raises(SystemExit, match="_facts.json: model 'NEW3' is in neither docs/models.yaml"):
        gc.check_models(FakeRegistry(), data())


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"models": [{"name": "Lamp", "ids": ["L1"], "type": "lamp"}]}, "type 'lamp' is not one of"),
        ({"models": [{"name": "Plug", "ids": [8979], "type": "plug"}]}, "must be a string; quote it"),
        (
            {"models": [{"name": "A", "ids": ["X"], "type": "plug"}, {"name": "B", "ids": ["X"], "type": "plug"}]},
            "twice",
        ),
        (
            {"no_known_method": [{"what": "X", "integrations": ["zha"], "reason": "", "source": "https://s"}]},
            "needs a reason",
        ),
        ({"models": [{"name": "Lamp", "ids": "L1", "type": "bulb"}]}, "ids must be a list"),
        ({"models": [{"ids": ["L1"], "type": "bulb"}]}, "needs a name"),
        (
            {"models": [{"name": "A", "ids": ["X"], "type": "plug"}, {"name": "A", "ids": ["Y"], "type": "plug"}]},
            "name 'A'",
        ),
        ({"capabilities": {"zha": {"switch": {"section": "S"}}}}, "needs a phrase"),
        (
            {"no_known_method": [{"what": "X", "integrations": "zha", "reason": "r", "source": "https://s"}]},
            "must be a list",
        ),
        ({"no_known_method": [{"what": "X", "integrations": ["zha"], "reason": "r", "source": "s"}]}, "https URL"),
        (
            {"no_known_method": [{"what": "X", "integrations": ["tuya"], "reason": "r", "source": "https://s"}]},
            "no integr",
        ),
        ({"models": [{"name": "Lamp", "ids": ["L1"], "type": "bulb", "colour": "red"}]}, "unknown key colour"),
        ({"capabilities": {"zha": {"switch": {"phrase": "p", "section": "S", "level": 1}}}}, "unknown key level"),
        ({"no_known_method": [{**DATA["no_known_method"][0], "why": "x"}]}, "unknown key why"),
        ({"capabilities": {"zha": None}}, "capabilities zha must be a mapping"),
        ({"capabilities": {"zha": ["switch"]}}, "capabilities zha must be a mapping"),
    ],
)
def test_devices_yaml_is_validated(changes, error):  # a clean error, never a KeyError
    with pytest.raises(SystemExit, match=error):
        data(FakeRegistry(adapter("zha", "turn_on_for")), **changes)


def test_records_are_the_action_and_its_options(root):
    for name in ["turn_on_for", "turn_on_for-predicted_state", "turn_on_for_x", "turn_off_for"]:
        record(root, "zha", name)
    names = [path.name for path in gc.passing("zha", "turn_on_for")]
    assert names == ["turn_on_for-predicted_state.json", "turn_on_for.json"]


def test_an_adapter_flagged_whole_holds_every_item_in_labs(root):
    # Every domain in Labs flags every call, so its Verified field shows Labs too.
    scope = AdapterScope(domains=labs("light", "switch"), fields=verified("brightness"))
    assert {level for level, *_ in gc.items(scope)} == {Level.LABS}


MANUAL = (signoff(signed_by="jasonmx", devices=(("P1", None), ("LTA009", None)), calls=bound("stop", "turn_on_for")),)


def manual_file(root, integration="zha", rows=MANUAL):
    write(records_dir(root, integration) / "_manual.json", manual(integration, *rows))


def test_a_manual_row_is_evidence_for_the_actions_it_passed(root):
    manual_file(root)
    flagged = adapter("zha", "stop", AdapterScope(domains=labs("light")))
    assert gc.Evidence.of(flagged).tested == [
        (gc.MANUAL, gc.Tested("P1", rig=False)),
        (gc.MANUAL, gc.Tested("LTA009", rig=False)),
    ]
    assert cr.manual_rows("zha", "lower_hue") == []
    assert cr.manual_rows("hue", "stop") == []


def test_a_format_2_row_credits_the_actions_it_passed(root):
    """A row from before transcripts names its actions in `passed`: it signs off nothing, but credits as it did."""
    manual_file(root, rows=[signoff(signed_by="jasonmx", devices=(("P1", None),), passed=("stop",))])
    flagged = adapter("zha", "stop", AdapterScope(domains=labs("light")))
    assert gc.Evidence.of(flagged).tested == [(gc.MANUAL, gc.Tested("P1", rig=False))]


def test_a_manual_group_row_is_one_group_by_hand_never_its_members_models(root):
    row = signoff(signed_by="jasonmx", devices=(("P1", None), ("LTA009", None)), calls=bound("stop"), group=True)
    manual_file(root, rows=[row])
    flagged = adapter("zha", "stop", AdapterScope(domains=labs("light")))
    assert gc.Evidence.of(flagged).tested == [(gc.MANUAL, gc.Tested(None, rig=False))]
    # A hand-tested group is no rig-tested one: it reaches Works without a check mark.
    assert zha_card(adapter("zha", "stop")).tested == [f"[native groups]({URL}#native-groups)"]
    manual_file(root, rows=[signoff(devices=(("NEW", None),), calls=bound("stop"), group=True)])
    with pytest.raises(SystemExit, match="model 'NEW' is in neither docs/models.yaml"):
        gc.check_models(FakeRegistry(), data())


def test_a_manual_group_with_a_null_class_member_credits_nothing_in_a_classed_integration(root):
    rows = [
        signoff(devices=(("P1", "Switch"), ("LTA009", None)), calls=bound("stop"), group=True),
        signoff(devices=(("P1", "Switch"), ("LTA009", "Light")), calls=bound("turn_on_for"), group=True),
    ]
    manual_file(root, rows=rows)
    scope = AdapterScope(capabilities=verified("Switch", "Light"))
    assert classed_card(adapter("zha", "stop", scope)).tested == []
    assert classed_card(adapter("zha", "turn_on_for", scope)).tested == [f"[native groups]({URL}#native-groups)"]
    flagged = AdapterScope(capabilities=verified("Switch") | labs("Light"))
    assert classed_card(adapter("zha", "turn_on_for", flagged)).tested == []


def test_a_manual_row_names_models_in_models_yaml(root):
    manual_file(root, rows=[signoff(devices=(("NEW", None),), calls=bound("stop"))])
    with pytest.raises(SystemExit, match="model 'NEW' is in neither docs/models.yaml"):
        gc.check_models(FakeRegistry(), data())


def zha_card(*adapters, **changes):
    registry = FakeRegistry(*adapters)
    return gc.card("zha", registry, list(adapters), data(registry, **changes))


def test_a_card_lists_tested_models_once_each_by_their_name_then_native_groups(root):
    record(root, "zha", "stop", devices=[old_device("P1", "1"), old_device("LTA009", "1")])
    record(root, "zha", "turn_on_for", devices=[old_device("9290024684", "2"), old_group("Group", "x")])
    card = zha_card(adapter("zha", "stop"), adapter("zha", "turn_on_for"))
    assert card.tested == [
        f"[Hue lamp]({URL}#hue-lamp) ✔",  # bulbs before plugs; two ids, one model
        f"[Plug]({URL}#plug) ✔",
        f"[native groups]({URL}#native-groups) ✔",
    ]
    # A format 1 record names no device's domain or class, so its models take a line of their own per feature set,
    # after the lines that work, with the features they were tested on; native groups first.
    assert card.render().splitlines() == [
        "**ZHA** (Zigbee 3.0)",
        "",
        f"- [native groups]({URL}#native-groups) ✔: 🟢 turn on with timer",
        f"- [lights]({URL}#lights): 🟢 turn on with timer",
        f"- [Hue lamp]({URL}#hue-lamp) ✔: 🟢 turn on with timer",
        f"- [Plug]({URL}#plug) ✔: 🟢 stop",
        f"- [Old plug]({URL}#old-plug): 🔴",
    ]


def test_a_model_tested_by_hand_works_without_the_rig_mark(root):
    manual_file(root)
    record(root, "zha", "turn_on_for", devices=[old_device("LTA009", "1")])
    card = zha_card(adapter("zha", "stop"), adapter("zha", "turn_on_for"))
    assert card.tested == [f"[Hue lamp]({URL}#hue-lamp) ✔", f"[Plug]({URL}#plug)"]


def test_a_model_keeps_each_actions_records_firmware_and_rig_and_by_hand(root):
    manual_file(root)  # names P1 and LTA009 on stop, by hand
    path = record(root, "zha", "stop", devices=[old_device("LTA009", "1.2")])
    reached = zha_card(adapter("zha", "stop")).reached["Hue lamp"]
    manual = "docs/integrations/zha/test-records/_manual.json"
    proof = reached.by_action["stop"]
    assert proof.records == [path.relative_to(root).as_posix(), manual]
    assert proof.firmware == ["1.2"]  # a manual row names none
    assert (proof.rig, proof.by_hand, reached.rig, reached.by_hand) == (True, True, True, True)


def test_a_card_puts_flagged_adapters_under_labs_and_leaves_out_failing_records(root):
    record(root, "zha", "stop")
    record(root, "zha", "turn_on_for", result="fail", devices=[old_device("P1", "1")])
    scope = AdapterScope(domains=labs("light", "switch"), fields=verified("brightness"))
    card = zha_card(
        adapter("zha", "stop", scope),
        adapter("zha", "turn_on_for"),
        adapter("zha", "lower_hue", AdapterScope(domains=labs("light"))),
        adapter("zha", "raise_hue", AdapterScope(domains=labs("light"))),
    )
    assert card.tested == []
    # An adapter flagged whole is in Labs on every domain, evidence or not; stop rides the smooth move.
    assert card.lines[:2] == [
        f"[lights]({URL}#lights): 🟢 turn on with timer · ⚪ smooth hue",
        f"[plugs]({URL}#zigbee-plugs): ⚪ stop",
    ]


def test_an_adapter_flagged_on_a_domain_counts_only_records_whose_passing_tests_all_target_unflagged_ones(root):
    manual_file(root)
    light = old_test("light")
    record(root, "zha", "turn_on_for", tests=[light, old_test(None, "skipped")])
    record(root, "zha", "turn_on_for-option", devices=[old_device("P1", "1")], tests=[light, old_test("switch")])
    record(root, "zha", "stop", tests=[old_test(None)])  # a passing test with no domain
    scope = AdapterScope(domains=verified("light") | labs("switch"))
    card = zha_card(*(adapter("zha", action, scope) for action in ("turn_on_for", "stop")))
    # Not Plug, whose format 1 record also passed on a switch, nor the manual rows; Hue lamp from the light-only one.
    assert card.tested == [f"[Hue lamp]({URL}#hue-lamp) ✔"]


def test_a_format_2_record_puts_under_works_only_the_models_whose_tests_reached_an_unflagged_domain(root):
    record2(root, "zha", "turn_on_for", ran("light", device("LTA009")), ran("switch", device("P1", "1")))
    scope = AdapterScope(domains=verified("light") | labs("switch"))
    # The same run as format 1 would add no model, as it can't say which test reached which.
    assert zha_card(adapter("zha", "turn_on_for", scope)).tested == [f"[Hue lamp]({URL}#hue-lamp) ✔"]


def test_a_pass_on_a_flagged_capability_puts_no_model_under_works(root):
    # Shelly smooth dimming: a pass on a Gen3 Dimmer's Light component must not make it work.
    record(root, "zha", "raise_brightness", devices=[old_device("P1", "1")])
    record(root, "zha", "turn_on_for")
    dimming = AdapterScope(capabilities=verified("RGBCCT") | labs("Light"))
    card = zha_card(adapter("zha", "raise_brightness", dimming), adapter("zha", "turn_on_for"))
    assert card.tested == [f"[Hue lamp]({URL}#hue-lamp) ✔"]  # from the unflagged adapter alone
    flagged_field = AdapterScope(fields=verified("brightness") | labs("transition"))
    assert zha_card(adapter("zha", "raise_brightness", flagged_field)).tested == []


def test_documented_and_flagged_classes_share_an_entry_per_feature_set_and_name_their_features(root):
    dimming = AdapterScope(capabilities=verified("Switch") | labs("Light", "CCT"))
    timer = AdapterScope(
        domains=verified("light") | documented("switch"),
        capabilities=verified("Switch") | documented("Light"),
    )
    card = zha_card(
        adapter("zha", "raise_brightness", dimming),
        adapter("zha", "stop", dimming),
        adapter("zha", "turn_on_for", timer),
    )
    # One line per class, its features by status; stop rides the smooth move, so it isn't named. A relay, a light or a
    # switch, is named per domain, its timer at the switch domain's Documented level there. CCT, left out of the timer's
    # scope, isn't built yet there: the card leaves the feature out. Lines sort alphabetically, devices.yaml's entry
    # last, as it names no class or feature.
    assert card.lines == [
        f"[CCT controllers]({URL}#dimmers): ⚪ smooth dimming",
        f"[dimmers]({URL}#dimmers): 🟡 turn on with timer · ⚪ smooth dimming",
        f"[relays]({URL}#relays): 🟡 turn on with timer",
        f"[relays as lights]({URL}#relays): 🟢 turn on with timer, smooth dimming",
        f"[Old plug]({URL}#old-plug): 🔴",
    ]
    assert card.render().splitlines()[2:] == [f"- {line}" for line in card.lines]


def test_a_class_line_runs_at_the_weaker_of_its_domain_and_class(root):
    """A call runs at the weaker of its domain and class (AdapterScope.level): a Verified class on a Labs
    domain is in Labs there; a class Verified on one domain alone is in Labs on the rest (OnDomains)."""
    timer = AdapterScope(
        domains=verified("light") | labs("switch"),
        capabilities=verified("Switch") | verified("Light", domains=("light",)),
    )
    card = classed_card(adapter("zha", "turn_on_for", timer))
    assert card.lines[:2] == [
        f"[dimmers]({URL}#dimmers), [relays as lights]({URL}#relays): 🟢 turn on with timer",
        f"[relays]({URL}#relays): ⚪ turn on with timer",
    ]


def test_a_class_whose_domains_show_different_features_splits_per_domain_on_the_card(root):
    """A relay, a switch or a light, takes the timer as either, and dimming only as a light. One entry
    would list dimming for every relay, so each of its domains gets its own, grouped with the entries of its feature
    set: as a light with the dimmers, as a switch alone."""
    dimming = AdapterScope(capabilities=verified("RGBCCT") | documented("Switch", "Light"))
    timer = AdapterScope(
        domains=verified("light", "switch"), capabilities=verified("RGBCCT") | documented("Switch", "Light")
    )
    capabilities = copy.deepcopy(DATA["capabilities"])
    capabilities["zha"]["RGBCCT"]["phrase"] = "multicolor bulbs"
    card = zha_card(
        adapter("zha", "raise_brightness", dimming),
        adapter("zha", "turn_on_for", timer),
        capabilities=capabilities,
    )
    assert card.lines[:3] == [
        f"[dimmers]({URL}#dimmers), [relays as lights]({URL}#relays): 🟡 turn on with timer, smooth dimming",
        f"[multicolor bulbs]({URL}#bulbs): 🟢 turn on with timer, smooth dimming",
        f"[relays]({URL}#relays): 🟡 turn on with timer",
    ]
    # Where both domains show the same features, the class keeps one line, by its phrase.
    both = zha_card(adapter("zha", "turn_on_for", timer), capabilities=capabilities)
    assert both.lines[0] == f"[dimmers]({URL}#dimmers), [relays]({URL}#relays): 🟡 turn on with timer"
    # A class that splits needs a phrase for each domain it shows.
    del capabilities["zha"]["Switch"]["domains"]
    with pytest.raises(SystemExit, match="zha Switch shows other features on each of its domains"):
        zha_card(
            adapter("zha", "raise_brightness", dimming), adapter("zha", "turn_on_for", timer), capabilities=capabilities
        )


def test_a_classs_scene_domain_joins_its_light_line(root):
    """A scene is classed by its lights, so a class that is a light and a scene shows one line, named by
    its phrase, with set scene among its features; a class that is only scenes keeps its own line."""
    phrase = {"phrase": "lights", "section": "Lights"}
    data = gc.Data(
        requires={},
        models={},
        capabilities={"x": {"hue": phrase, "other": {"phrase": "others", "section": "Lights"}}},
        no_known_method=[],
    )
    scenes = {"smart": {"phrase": "smart scenes", "section": "Scenes"}}
    data.capabilities["x"] |= scenes
    found = {
        ("hue", "light"): {"works": {"raise_brightness"}},
        ("hue", "scene"): {"works": {"set_scene"}},
        ("smart", "scene"): {"works": {"set_scene"}},
    }
    domains = {"hue": frozenset({Platform.LIGHT, Platform.SCENE}), "smart": frozenset({Platform.SCENE})}
    lines = gc.class_lines("x", found, data, domains, ["light", "scene"], {})
    assert [(line.sections, line.shape, line.items) for line in lines] == [
        ({"Lights": ["lights"]}, ((("works", ("smooth dimming", "set scene"))),), [("hue", "light"), ("hue", "scene")]),
        ({"Scenes": ["smart scenes"]}, ((("works", ("set scene",))),), [("smart", "scene")]),
    ]


def test_classes_of_one_section_say_their_shared_ending_once():
    led = f"{URL}#led"
    assert gc.merged(["CCT LED controllers", "RGB LED controllers"], led) == f"[LED controllers (CCT, RGB)]({led})"
    assert gc.merged(["dimmers"], f"{URL}#dimmers") == f"[dimmers]({URL}#dimmers)"
    # A phrase that is all ending has no prefix to list, so the phrases are listed whole.
    assert (
        gc.merged(["LED controllers", "RGB LED controllers"], led) == f"[LED controllers, RGB LED controllers]({led})"
    )


def test_classes_that_share_a_phrase_say_it_once():
    """Zigbee2MQTT's countdown plugs: a class per maker string, one phrase for them all."""
    phrase = {"phrase": "countdown plugs", "section": "Plugs"}
    data = gc.Data(requires={}, models={}, capabilities={"x": {"a": phrase, "b": phrase}}, no_known_method=[])

    found = {("a", "light"): {"works": {"stop"}}, ("b", "light"): {"works": {"stop"}}}
    (line,) = gc.class_lines("x", found, data, {"a": LIGHT, "b": LIGHT}, ["light"], {})
    assert line.sections == {"Plugs": ["countdown plugs"]}
    assert line.items == [("a", "light"), ("b", "light")]


def test_a_card_drops_its_integrations_name_where_a_name_leads():
    card = gc.Card("Hue")
    assert card.short("Hue Bridge v1") == "Bridge v1"
    assert card.short("Huey lamp") == "Huey lamp"
    assert card.short("WiZ Hue") == "WiZ Hue"


def test_stop_alone_is_named():
    assert gc.features({"stop"}) == ("stop",)
    assert gc.features({"stop", "lower_brightness", "get_attributes", "custom"}) == (
        "smooth dimming",
        "get attributes",
        "custom",
    )


def test_a_class_the_card_lists_without_an_entry_is_an_error(root):
    scope = AdapterScope(capabilities=verified("Switch") | documented("Hidden"))
    with pytest.raises(SystemExit, match="no entry for zha Hidden, which the card lists"):
        zha_card(adapter("zha", "turn_on_for", scope))


# DATA as files: the shared models.yaml, and a bundle per FakeRegistry integration.
BUNDLE = {
    "zha": {
        "column": "ZHA",
        "column_order": 1,
        "requires": "Zigbee 3.0",
        "capabilities": DATA["capabilities"]["zha"],
        "no_known_method": [{"what": "Old plug", "reason": "No timer", "source": "https://x.y/z"}],
    },
    "hue": {"column": "Hue", "column_order": 2},
}


def write_bundles(root, monkeypatch, bundles=BUNDLE, shared=None):
    monkeypatch.setattr(gf, "BUNDLES", root / "docs" / "integrations")
    models = root / "models.yaml"
    models.write_text(yaml.safe_dump(shared if shared is not None else {"models": DATA["models"]}))
    for key, data in bundles.items():
        folder = root / "docs" / "integrations" / key
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "devices.yaml").write_text(yaml.safe_dump(data))
        # The page holds a heading for every section the bundle's classes and no-known-method entries link.
        sections = {item["section"] for item in data.get("capabilities", {}).values()}
        broken = data.get("no_known_method")
        sections |= (
            {entry["what"] for entry in broken if isinstance(entry, dict)} if isinstance(broken, list) else set()
        )
        (folder / "index.md").write_text(f"# {key}\n\n" + "".join(f"### {section}\n\n" for section in sorted(sections)))
    return models


def write_files(root, registry, monkeypatch):
    page, readme = root / "page.md", root / "README.md"
    models = write_bundles(root, monkeypatch)
    page.write_text(PROSE + "<!-- evidence:start -->\n<!-- evidence:end -->\n")
    readme.write_text("# R\n\n<!-- devices:start -->\n<!-- devices:end -->\n\nAfter.\n")
    return lambda argv: gc.main(argv, registry, page, readme, models)


def test_check_fails_on_a_stale_readme_or_page_until_they_are_regenerated(root, capsys, monkeypatch):
    registry = FakeRegistry(adapter("zha", "stop"))
    device = record(root, "zha", "stop")
    run = write_files(root, registry, monkeypatch)
    assert run(["--check"]) == 1  # nothing generated yet
    assert "page.md and README.md out of date" in capsys.readouterr().err
    assert run([]) == 0
    assert run(["--check"]) == 0
    assert (root / "README.md").read_text().endswith("<!-- devices:end -->\n\nAfter.\n")
    assert (root / "page.md").read_text().startswith(PROSE)
    device.write_text(device.read_text().replace("1.2.3", "9.9.9"))
    assert run(["--check"]) == 1
    assert "page.md out of date" in capsys.readouterr().err
    assert run([]) == 0
    assert "9.9.9" in (root / "page.md").read_text()


def test_a_bundle_merges_in_as_its_integrations_own_and_its_page_holds_its_sections(root, monkeypatch):
    models = write_bundles(root, monkeypatch)
    (root / "docs" / "integrations" / "zha" / "index.md").write_text("# ZHA\n\n### Dimmers\n")
    data = gc.load(FakeRegistry(), models)
    assert data.requires == {"zha": "Zigbee 3.0"}
    assert data.no_known_method[0]["integrations"] == ["zha"]
    # A class's or blocker's section on the integration's page links there; the rest answer on the generated page.
    assert data.url("zha", "Dimmers") == f"{gc.DOCS_URL}docs/integrations/zha/index.md#dimmers"
    assert data.url("zha", "Zigbee plugs") == f"{URL}#zigbee-plugs"
    assert data.url("hue", "Dimmers") == f"{URL}#dimmers"


@pytest.mark.parametrize("section", ["Hue lamp", "Native groups"])
def test_a_models_or_native_groups_link_goes_to_the_generated_page_whatever_the_integrations_pages_hold(
    root, monkeypatch, section
):
    models = write_bundles(root, monkeypatch)
    (root / "docs" / "integrations" / "zha" / "index.md").write_text(f"# ZHA\n\n### {section}\n")
    data = gc.load(FakeRegistry(), models)
    assert data.model_url(section) == f"{URL}#{gf.slug(section)}"


def test_a_card_title_links_to_its_integrations_page(root, monkeypatch):
    data = gc.load(FakeRegistry(), write_bundles(root, monkeypatch))
    card = gc.card("zha", FakeRegistry(), [], data)
    assert card.render().startswith(f"**[ZHA]({gc.DOCS_URL}docs/integrations/zha/index.md)** (Zigbee 3.0)")


@pytest.mark.parametrize(
    ("bundles", "shared", "error"),
    [
        ({"zha": BUNDLE["zha"]}, None, "no docs/integrations/hue/devices.yaml; add the hue bundle"),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "bogus": []}},
            None,
            "hue/devices.yaml: unknown key bogus",
        ),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "models": {"a": 1}}},
            None,
            "hue/devices.yaml: models must be a list",
        ),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "models": [DATA["models"][0]]}},
            None,
            "is listed twice",
        ),
        (BUNDLE, {"models": [], "capabilities": {}}, "docs/models.yaml: unknown key capabilities"),
        (BUNDLE, {"models": {"a": 1}}, "docs/models.yaml: models must be a list"),
        ({**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "requires": ""}}, None, "hue/devices.yaml needs a req"),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "no_known_method": [DATA["no_known_method"][0]]}},
            None,
            "a no_known_method entry is hue's own; drop its integrations",
        ),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "no_known_method": {"a": 1}}},
            None,
            "hue/devices.yaml: no_known_method must",
        ),
    ],
)
def test_a_missing_bundle_or_a_misplaced_key_fails_naming_the_file(root, monkeypatch, bundles, shared, error):
    models = write_bundles(root, monkeypatch, bundles, shared)
    with pytest.raises(SystemExit, match=error):
        gc.load(FakeRegistry(), models)


def test_a_bundles_own_model_is_loaded_and_credits_a_device(root, monkeypatch):
    own = {"name": "Own lamp", "ids": ["OWN1"], "type": DATA["models"][0]["type"]}
    bundles = {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "models": [own]}}
    data = gc.load(FakeRegistry(), write_bundles(root, monkeypatch, bundles))
    record(root, "hue", "stop", devices=[old_device("OWN1", "1")])
    gc.check_models(FakeRegistry(), data)  # a record naming it passes
    assert data.model("OWN1", "x")["section"] == "Own lamp"
    with pytest.raises(SystemExit, match="'NOPE' is in neither docs/models.yaml nor a bundle's devices.yaml"):
        data.model("NOPE", "x")


def test_a_record_naming_another_bundles_model_fails(root, monkeypatch):
    own = {"name": "Own lamp", "ids": ["OWN1"], "type": DATA["models"][0]["type"]}
    bundles = {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "models": [own]}}
    data = gc.load(FakeRegistry(), write_bundles(root, monkeypatch, bundles))
    record(root, "zha", "stop", devices=[old_device("OWN1", "1")])
    with pytest.raises(SystemExit, match="'OWN1' is in docs/integrations/hue/devices.yaml; a model two integrations"):
        gc.check_models(FakeRegistry(), data)


def test_a_model_in_both_files_fails_naming_them(root, monkeypatch):
    bundles = {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "models": [{**DATA["models"][0], "name": "Dup"}]}}
    with pytest.raises(SystemExit, match="listed twice: in docs/models.yaml and docs/integrations/hue/devices.yaml"):
        gc.load(FakeRegistry(), write_bundles(root, monkeypatch, bundles))


def test_an_integration_without_a_user_page_fails(root, monkeypatch):
    models = write_bundles(root, monkeypatch)
    (root / "docs" / "integrations" / "hue" / "index.md").unlink()
    with pytest.raises(SystemExit, match="no docs/integrations/hue/index.md; add the hue bundle's user page"):
        gc.load(FakeRegistry(), models)


@pytest.mark.parametrize(
    "heading", ["## Tested devices", "### Should work", "## Try it: Labs", "### Verified plugs", "## tested devices"]
)
def test_an_integration_page_heading_that_states_a_level_fails_naming_the_file(root, monkeypatch, heading):
    models = write_bundles(root, monkeypatch)
    (root / "docs" / "integrations" / "hue" / "index.md").write_text(f"# Hue\n\n## Device classes\n\n{heading}\n")
    with pytest.raises(SystemExit, match=f"docs/integrations/hue/index.md: '{heading}' states a level"):
        gc.load(FakeRegistry(), models)


def test_level_words_in_prose_pass_the_heading_check_but_a_heading_fails():
    gc.check_headings("hue", "# Hue\n\nLabs and Verified in prose pass; a heading doesn't.\n")
    with pytest.raises(SystemExit, match="docs/integrations/hue/index.md: '## Try it: Labs' states a level"):
        gc.check_headings("hue", "# Hue\n\n## Try it: Labs\n")


def test_the_checked_in_readme_and_page_match_the_real_records():
    """Both are generated: run the real check so local pytest catches a record or scope that drifts them."""
    assert gc.main(["--check"]) == 0


def test_the_legend_leads_the_cards_and_lists_only_the_marks_they_use(root):
    registry = FakeRegistry(adapter("zha", "turn_on_for"))
    text = gc.cards(gc.card_list(registry, data(registry)))
    # The fixture's Old plug has no known method; nothing is tested, Documented, in Labs or caveated.
    assert "🟢 works<br>\n🔴 no known command works on it\n\n**ZHA**" in text
    assert text.index("Details per integration are in [docs/integrations.md](") < text.index("</details>")
    assert gc.legend("🟢 ✔ 🟡 ⚪ 🔴 🔧 ⚠️") == (
        "🟢 works · ✔ verified on automated rig<br>\n"
        "🟡 should work: same call pattern as a tested device<br>\n"
        "⚪ Labs: built but not yet proven. Enable Labs in Configure > Settings<br>\n"
        "🔴 no known command works on it<br>\n"
        f"🔧 untested fix: please try it and [report whether it works]({gc.REPORT_URL})<br>\n"
        "⚠️ unmaintained: use at your own risk"
    )


def test_every_action_has_a_card_name_from_the_feature_table():
    """The cards' names come from the README table's rows, so an action can't be named on one and not the other."""
    assert set(gc.FEATURES) == {action.key for action in discover()}
    assert gc.FEATURES["raise_hue"] == "smooth hue"
    assert list(gc.FEATURES)[-1] == "stop" == gc.FEATURES["stop"]


ISSUE_REASON = "https://github.com/DeviceSide/DeviceSide/issues/40"


def unmaintained(reason: str) -> Caveat:
    return Caveat(CaveatKind.UNMAINTAINED, reason)


def untested_fix(reason: str) -> Caveat:
    return Caveat(CaveatKind.UNTESTED_FIX, reason)


def test_a_card_marks_unmaintained_adapters_by_reason_flagged_ones_included(root):
    card = zha_card(
        adapter("zha", "turn_on_for", AdapterScope(caveat=unmaintained(ISSUE_REASON))),
        adapter("zha", "turn_off_for", AdapterScope(caveat=unmaintained(ISSUE_REASON))),
        adapter("zha", "stop", AdapterScope(caveat=unmaintained(ISSUE_REASON))),
        adapter("zha", "get_attributes", AdapterScope(caveat=unmaintained("the maintainer left"))),
        adapter("zha", "set_scene", AdapterScope(domains=labs("light"), caveat=unmaintained(ISSUE_REASON))),
        adapter("zha", "raise_hue"),
    )
    # A warning names every feature, stop beside the others.
    assert card.render().splitlines()[2:4] == [
        f"- [⚠️ Unmaintained]({ISSUE_REASON}): turn on with timer, turn off with timer, set scene, stop",
        "- ⚠️ Unmaintained (the maintainer left): get attributes",
    ]


def heading(card):
    return card.render().splitlines()[0]


def test_a_card_whose_adapters_are_all_unmaintained_says_so_in_its_heading(root):
    card = zha_card(
        adapter("zha", "turn_on_for", AdapterScope(caveat=unmaintained(ISSUE_REASON))),
        adapter("zha", "stop", AdapterScope(domains=labs("light"), caveat=unmaintained("gone"))),
    )
    assert heading(card).endswith(" · ⚠️ Unmaintained")
    # One maintained adapter, flagged or not, carries no mark.
    for scope in (AdapterScope(), AdapterScope(domains=labs("light"))):
        card = zha_card(
            adapter("zha", "turn_on_for", AdapterScope(caveat=unmaintained(ISSUE_REASON))),
            adapter("zha", "stop", scope),
        )
        assert "Unmaintained" not in heading(card)
    assert "Unmaintained" not in heading(zha_card())


def test_a_card_marks_unmaintained_ones_after_untested_fixes(root):
    card = zha_card(
        adapter("zha", "turn_on_for", AdapterScope(caveat=untested_fix(ISSUE_REASON))),
        adapter("zha", "turn_off_for", AdapterScope(caveat=unmaintained("gone"))),
        adapter("zha", "set_scene", AdapterScope(domains=labs("light"), caveat=untested_fix(ISSUE_REASON))),
    )
    lines = card.render().splitlines()
    marks = [line for line in lines if line.startswith(("- ⚠️", "- [⚠️", "- [🔧"))]
    assert marks == [
        f"- [🔧 Untested fix]({ISSUE_REASON}): turn on with timer, set scene",
        "- ⚠️ Unmaintained (gone): turn off with timer",
    ]
    # An untested fix is not unmaintained: the heading still names the maintainers.
    assert "formerly maintained" not in heading(card)
    assert "⚠️" not in zha_card(adapter("zha", "stop")).render()  # no caveat, no mark


# Classes (docs/evidence.md, Device classes).


def classed_registry(*adapters) -> FakeRegistry:
    """FakeRegistry whose zha names the classes Switch, Light and CCT."""
    registry = FakeRegistry(*adapters)
    registry.integrations = {
        **registry.integrations,
        "zha": SimpleNamespace(
            title="ZHA",
            maintainers=("jasonmx",),
            capability=len,
            default_class=None,
            classes={name: CLASSES[name] for name in ("Switch", "Light", "CCT")},
        ),
    }
    return registry


def classed_card(*adapters, **changes):
    registry = classed_registry(*adapters)
    return gc.card("zha", registry, list(adapters), data(registry, **changes))


def test_an_adapter_flagged_on_a_class_counts_only_format_1_records_whose_tests_reached_unflagged_ones(root):
    # Shelly smooth dimming: a pass on a Gen3 Dimmer's Light must not make it work; one on RGBCCT alone does.
    record(root, "zha", "raise_brightness", devices=[old_device("P1", "1")], tests=[old_test(classes=["Light"])])
    record(root, "zha", "lower_brightness", tests=[old_test(classes=["Switch"])])
    record(root, "zha", "stop", tests=[old_test(classes=[])])  # a dash reached no class
    record(root, "zha", "lower_hue", devices=[old_device("P1", "1")], tests=[old_test()])  # no Capability column
    dimming = AdapterScope(capabilities=verified("Switch") | labs("Light"))
    actions = ("raise_brightness", "lower_brightness", "stop", "lower_hue")
    card = classed_card(*(adapter("zha", action, dimming) for action in actions))
    assert card.tested == [f"[Hue lamp]({URL}#hue-lamp) ✔"]


def test_a_mixed_class_format_2_record_puts_under_works_only_the_models_that_reached_an_unflagged_class(root):
    # A Shelly-like run: a relay on Switch and a bulb on a flagged class, in one record. Format 1 would credit neither.
    record2(
        root,
        "zha",
        "turn_on_for",
        ran("switch", device("P1", "1", "Switch"), role="switch_plug"),
        ran("light", device("LTA009", "2", "Light")),
    )
    lights = verified("light", "switch")
    flagged = AdapterScope(domains=lights, capabilities=verified("Switch") | labs("Light"))
    assert classed_card(adapter("zha", "turn_on_for", flagged)).tested == [f"[Plug]({URL}#plug) ✔"]
    both = AdapterScope(domains=lights, capabilities=verified("Switch", "Light"))
    assert classed_card(adapter("zha", "turn_on_for", both)).tested == [
        f"[Hue lamp]({URL}#hue-lamp) ✔",
        f"[Plug]({URL}#plug) ✔",
    ]


def test_a_class_held_on_some_domains_alone_credits_works_only_from_a_test_in_one(root):
    """Zigbee2MQTT's `hue` on lights alone: a Hue plug's pass, a switch, never shows it as working (OnDomains)."""
    record2(
        root,
        "zha",
        "turn_on_for",
        ran("switch", device("P1", "1", "Light"), role="switch_plug"),
        ran("light", device("LTA009", "2", "Light")),
    )
    scope = AdapterScope(
        domains=verified("light", "switch"), capabilities=verified("Light", domains=("light",)) | verified("Switch")
    )
    tested = adapter("zha", "turn_on_for", scope)
    assert classed_card(tested).tested == [f"[Hue lamp]({URL}#hue-lamp) ✔"]
    # A manual row names no domain, so it counts where its class is unflagged in some domain, as the coverage check
    # lets it cover any (#440's review, L1).
    manual_file(root, rows=[signoff(signed_by="jasonmx", devices=(("P1", "Light"),), calls=bound("turn_on_for"))])
    assert classed_card(tested).tested == [f"[Hue lamp]({URL}#hue-lamp) ✔", f"[Plug]({URL}#plug)"]


def test_a_null_class_device_never_reaches_works_where_the_integration_names_classes(root):
    # A Shelly 1 Mini Gen4 whose class the run didn't name: no adapter flag needed to keep it off Works.
    record2(
        root,
        "zha",
        "turn_on_for",
        ran("switch", device("P1", "1", None), role="switch_plug"),
        ran("light", device("LTA009", "1", "Light"), device("P1", "1", None), group=True, role="group"),
        ran("light", device("LTA009", "2", "Light")),
    )
    manual_file(root, rows=[signoff(signed_by="jasonmx", devices=(("P1", None),), calls=bound("turn_on_for"))])
    unflagged = AdapterScope(domains=verified("light", "switch"), capabilities=verified("Switch", "Light"))
    assert classed_card(adapter("zha", "turn_on_for", unflagged)).tested == [f"[Hue lamp]({URL}#hue-lamp) ✔"]
    flagged_domain = AdapterScope(domains=verified("light") | labs("switch"), capabilities=verified("Light", "Switch"))
    assert classed_card(adapter("zha", "turn_on_for", flagged_domain)).tested == [f"[Hue lamp]({URL}#hue-lamp) ✔"]
    # An integration that names no classes has only null ones, and they count.
    record2(root, "hue", "turn_on_for", ran("switch", device("P1", "1"), role="switch_plug"))
    plain = gc.card("hue", FakeRegistry(), [adapter("hue", "turn_on_for")], data())
    assert plain.tested == [f"[Plug]({URL}#plug) ✔"]


def test_a_scenes_test_credits_native_groups_never_its_members(root):
    members = (device("LTA009", "1"), device("P1", "1"))
    record2(root, "hue", "set_scene", ran("scene", *members, group=True, role="scene"))
    scope = AdapterScope(domains=verified("scene"))
    card = gc.card("hue", FakeRegistry(), [adapter("hue", "set_scene", scope)], data())
    assert card.tested == [f"[native groups]({URL}#native-groups) ✔"]
    assert card.groups.by_action["set_scene"].records == ["docs/integrations/hue/test-records/set_scene.json"]


def test_a_mixed_groups_test_puts_native_groups_on_the_card_never_its_members(root):
    """The members' classes credit coverage (check_release's tests); the card gains "native groups" alone."""
    members = (device("P1", "1", "Switch"), device("LTA009", "2", "Light"))
    record2(root, "zha", "turn_on_for", ran("light", *members, group=True, role="group"))
    scope = AdapterScope(capabilities=verified("Switch", "Light", "CCT"))
    card = classed_card(adapter("zha", "turn_on_for", scope))
    assert card.tested == [f"[native groups]({URL}#native-groups) ✔"]


def test_a_group_test_counts_toward_works_only_when_every_members_class_is_unflagged(root):
    members = (device("P1", "1", "Switch"), device("LTA009", "2", "Light"))
    record2(root, "zha", "turn_on_for", ran("light", *members, group=True, role="group"))
    groups = f"[native groups]({URL}#native-groups) ✔"
    flagged = AdapterScope(capabilities=verified("Switch") | labs("Light"))
    assert classed_card(adapter("zha", "turn_on_for", flagged)).tested == []
    # Its members are no models of their own: the group's call isn't theirs.
    both = AdapterScope(capabilities=verified("Switch", "Light"))
    assert classed_card(adapter("zha", "turn_on_for", both)).tested == [groups]


def test_a_manual_device_counts_for_a_class_flagged_adapter_only_with_an_unflagged_class(root):
    rows = [
        signoff(signed_by="jasonmx", devices=(("P1", "Switch"), ("LTA009", "Light")), calls=bound("stop")),
        signoff(signed_by="jasonmx", devices=(("LTA009", None),), calls=bound("stop")),  # no class: none
    ]
    manual_file(root, rows=rows)
    scope = AdapterScope(capabilities=verified("Switch") | labs("Light"))
    assert classed_card(adapter("zha", "stop", scope)).tested == [f"[Plug]({URL}#plug)"]
    flagged_domain = AdapterScope(domains=verified("light") | labs("switch"), capabilities=verified("Switch"))
    assert classed_card(adapter("zha", "stop", flagged_domain)).tested == []  # a row names no domain


def test_a_class_with_fields_in_labs_on_it_credits_no_model_and_the_others_still_do(root):
    # A record doesn't say which fields a test sent, so a pass on a class_labs class may have carried the Labs field.
    record2(
        root,
        "zha",
        "turn_on_for",
        ran("light", device("LTA009", "1", "Light")),
        ran("light", device("P1", "1", "CCT")),
    )
    manual_file(root, rows=[signoff(signed_by="jasonmx", devices=(("P1", "CCT"),), calls=bound("turn_on_for"))])
    scope = AdapterScope(
        fields=verified("transition"),
        capabilities=verified("Light", "CCT"),
        class_labs=labs_fields("transition", classes=("CCT",)),
    )
    assert classed_card(adapter("zha", "turn_on_for", scope)).tested == [f"[Hue lamp]({URL}#hue-lamp) ✔"]


def test_a_class_an_adapter_serves_in_neither_axis_shows_nothing_for_it(root):
    broken = {"RGB": NoKnownMethod("Old plug", "No timer", "https://x.y/z")}
    card = classed_card(
        adapter("zha", "turn_on_for", AdapterScope(capabilities=verified("Switch", "Light", "CCT", "RGB"))),
        adapter("zha", "set_attributes", AdapterScope(capabilities=verified("Switch"))),
        adapter("zha", "turn_off_for", AdapterScope(capabilities=verified("Switch"), no_known_method=broken)),
    )
    # Light and CCT, in neither axis of the other two adapters, aren't built yet there: the card leaves those
    # features out, and names nothing as not built.
    assert card.lines == [
        f"[CCT controllers, dimmers]({URL}#dimmers): 🟢 turn on with timer",
        f"[relays]({URL}#relays): 🟢 turn on with timer, turn off with timer, set without turning on",
        f"[Old plug]({URL}#old-plug): 🔴",
    ]


def test_a_scopes_no_known_method_reaches_the_card_and_the_not_supported_table_with_its_actions(root):
    broken = {"RGB": NoKnownMethod("Old plug", "No timer", "https://x.y/z")}
    scope = AdapterScope(capabilities=verified("Switch"), no_known_method=broken)
    adapters = (adapter("zha", "turn_on_for", scope), adapter("zha", "turn_off_for", scope))
    registry = classed_registry(*adapters)
    registry.integrations["zha"].classes["RGB"] = LIGHT
    found = data(registry, no_known_method=[])
    # One entry per integration and entry, whichever adapters list it.
    assert gc.card("zha", registry, list(adapters), found).lines == [
        f"[relays]({URL}#relays): 🟢 turn on with timer, turn off with timer",
        f"[RGB controllers]({URL}#dimmers): 🔴 turn on with timer, turn off with timer",
    ]
    (row,) = gc.refusals(registry, found, [])
    assert (row.what, row.integrations, row.actions, row.refused) == (
        "Old plug",
        ["zha"],
        {"turn_off_for", "turn_on_for"},
        True,
    )
    # A class devices.yaml gives no phrase is named by the entry's `what`.
    scope = AdapterScope(capabilities=verified("Switch"), no_known_method={"Hidden": broken["RGB"]})
    registry = classed_registry(adapter("zha", "turn_on_for", scope))
    registry.integrations["zha"].classes["Hidden"] = LIGHT
    assert gc.card("zha", registry, list(registry._adapters), found).lines[0] == (
        f"[Old plug]({URL}#old-plug): 🔴 turn on with timer"
    )


def test_a_harmful_not_built_entry_is_left_off_the_card_and_sourced_under_not_supported(root):
    """The card leaves it out, as any feature not built yet; the page's Not supported table keeps why and where."""
    unbuilt = {"CCT": NotBuilt("No timer yet", "https://x.y/z")}
    scope = AdapterScope(capabilities=verified("Switch"), not_built=unbuilt)
    adapters = (adapter("zha", "turn_on_for", scope), adapter("zha", "turn_off_for", scope))
    registry = classed_registry(*adapters)
    found = data(registry, no_known_method=[])
    card = gc.card("zha", registry, list(adapters), found)
    assert card.lines == [f"[relays]({URL}#relays): 🟢 turn on with timer, turn off with timer"]  # no CCT line
    (row,) = gc.refusals(registry, found, [])
    assert (row.what, row.reason, row.source, row.refused) == (
        "CCT controllers",
        "No timer yet",
        "https://x.y/z",
        False,
    )
    assert row.actions == {"turn_off_for", "turn_on_for"}
    assert row.id is None  # no matrix cell links a class that isn't built yet


@pytest.mark.parametrize(
    ("name", "entry", "message"),
    [
        (
            "CCT",
            NotBuilt("No timer yet", "http://x.y/z"),
            "not_built zha CCT: source must be an https",
        ),
        ("CCT", NotBuilt("", "https://x.y/z"), "not_built zha CCT needs a reason"),
        ("Hidden", NotBuilt("No timer yet", "https://x.y/z"), "no entry for zha Hidden, which a scope"),
    ],
    ids=["non_https_source", "empty_reason", "no_phrase"],
)
def test_a_scopes_not_built_entry_needs_a_reason_an_https_source_and_a_phrase(root, name, entry, message):
    scope = AdapterScope(capabilities=verified("Light"), not_built={name: entry})
    registry = classed_registry(adapter("zha", "turn_on_for", scope))
    with pytest.raises(SystemExit, match=message):
        gc.code_unbuilt("zha", list(registry._adapters), data(registry))


def test_a_shared_not_built_entry_is_left_off_its_cards_and_sourced_under_not_supported(root):
    """models.yaml's `not_built`: a device today's call harms, on an integration that doesn't class it yet."""
    shared = [{"what": "Old plug", "integrations": ["zha"], "reason": "It stays on", "source": "https://x.y/z"}]
    registry = FakeRegistry(adapter("zha", "turn_on_for"))
    found = data(registry, no_known_method=[], not_built=shared)
    card = gc.card("zha", registry, list(registry._adapters), found)
    assert card.lines == [f"[lights]({URL}#lights): 🟢 turn on with timer"]
    (row,) = gc.refusals(registry, found, [])
    assert (row.what, row.reason, row.integrations, row.refused) == ("Old plug", "It stays on", ["zha"], False)
    with pytest.raises(SystemExit, match="not_built 'Old plug': source must be an https URL"):
        data(registry, not_built=[{**shared[0], "source": "x.y/z"}])


def test_main_warns_on_each_coverage_gap_and_still_passes(root, capsys, monkeypatch):
    registry = classed_registry(adapter("zha", "stop", AdapterScope(capabilities=verified("Switch"))))
    run = write_files(root, registry, monkeypatch)
    assert run([]) == 0
    assert run(["--check"]) == 0
    assert capsys.readouterr().err.count("warning: zha stop: `Switch` is Verified but no record reaches it\n") == 2


def test_a_declared_class_no_scope_holds_has_no_line(root):
    registry = classed_registry(adapter("zha", "stop", AdapterScope(capabilities=verified("Light"))))
    registry.integrations["zha"].classes = {"Light": LIGHT, "Hidden": LIGHT}
    card = gc.card("zha", registry, list(registry._adapters), data(registry))
    assert card.lines == [f"[dimmers]({URL}#dimmers): 🟢 stop", f"[Old plug]({URL}#old-plug): 🔴"]


def test_a_tested_model_follows_the_line_of_the_class_and_domain_a_test_reached_it_on(root):
    """No line of models apart. A model goes on its class's line in the test's domain, else on its class's
    line (a Shelly relay shown as a light), and rig-tested ones end ✔; native groups get a line of their own."""
    record2(
        root,
        "zha",
        "turn_on_for",
        ran("switch", device("P1", "1", "Switch"), role="switch_plug"),
        ran("switch", device("LTA009", "1", "Light"), role="switch_plug"),  # no Light line on switch
        ran("light", device("LTA009", "1", "Light"), device("P1", "1", "Switch"), group=True, role="group"),
    )
    scope = AdapterScope(domains=verified("light", "switch"), capabilities=verified("Switch", "Light"))
    dimming = AdapterScope(capabilities=verified("Light") | labs("Switch"))
    card = classed_card(adapter("zha", "turn_on_for", scope), adapter("zha", "raise_brightness", dimming))
    # Native groups first, then tested lines, then alphabetically.
    assert card.lines == [
        f"[native groups]({URL}#native-groups) ✔: 🟢 turn on with timer",
        f"[dimmers]({URL}#dimmers) ([Hue lamp]({URL}#hue-lamp) ✔): 🟢 turn on with timer, smooth dimming",
        f"[relays]({URL}#relays) ([Plug]({URL}#plug) ✔): 🟢 turn on with timer",
        f"[relays as lights]({URL}#relays): 🟢 turn on with timer · ⚪ smooth dimming",
        f"[Old plug]({URL}#old-plug): 🔴",
    ]
    # A class named as its one model gives it once.
    capabilities = copy.deepcopy(DATA["capabilities"])
    capabilities["zha"]["Switch"] = {"phrase": "Plug", "section": "Plug"}
    relays = AdapterScope(domains=verified("light", "switch"), capabilities=verified("Switch") | labs("Light"))
    card = classed_card(adapter("zha", "turn_on_for", relays), capabilities=capabilities)
    assert card.lines[0] == f"[Plug]({URL}#plug) ✔: 🟢 turn on with timer"


def test_a_feature_whose_actions_differ_in_status_names_its_parts():
    """Never one feature under two statuses."""
    dimming = {"should": {"lower_brightness", "stop"}, "labs": {"raise_brightness", "turn_on_for"}}
    assert gc.shape(dimming) == (
        ("should", ("smooth dimming down",)),
        ("labs", ("turn on with timer", "smooth dimming up")),
    )
    auto = {"works": {"set_auto_off", "clear_auto_off"}, "should": {"set_auto_on"}}
    assert gc.shape(auto) == (("works", ("auto-off",)), ("should", ("auto-on",)))
    assert gc.shape({"works": {"raise_brightness", "lower_brightness"}}) == (("works", ("smooth dimming",)),)


def test_no_card_line_names_a_feature_twice():
    block = gc.README.read_text().split(gc.CARDS[0])[1].split(gc.CARDS[1])[0]
    lines = [line for line in block.splitlines() if line.startswith("- ")]
    assert lines
    icons = {icon for _, icon, _ in gc.OUTCOMES}
    for line in lines:
        # A line's features follow its names, each part "<icon> <features>"; the fold's sit in a parenthesis per group.
        if line.startswith(f"- {gc.LABS} "):
            groups = re.findall(r"\(([^()]*)\)(?=;|$)", line)
            assert groups, line
        else:
            groups = [line.rsplit(": ", 1)[1]]
        for group in groups:
            # The fold's Labs part carries no icon of its own.
            parts = [part.split(" ", 1)[1] if part.split(" ", 1)[0] in icons else part for part in group.split(" · ")]
            labels = [label for part in parts for label in part.split(", ")]
            assert len(labels) == len(set(labels)), line


def test_a_line_holding_every_class_of_its_section_names_the_section(root):
    """By its devices.yaml `sections` phrase, per domain where it gives one."""
    timer = AdapterScope(capabilities=verified("Light", "CCT"))
    sections = {"zha": {"Dimmers": {"phrase": "dimmable lights", "domains": {"switch": "dimmer switches"}}}}
    card = classed_card(adapter("zha", "turn_on_for", timer), sections=sections)
    assert card.lines[0] == f"[dimmable lights]({URL}#dimmers): 🟢 turn on with timer"
    # A class of the section on another line keeps each class named; so does a section with no phrase.
    split = AdapterScope(capabilities=verified("Light") | labs("CCT"))
    card = classed_card(adapter("zha", "turn_on_for", split), sections=sections)
    assert card.lines[:2] == [
        f"[CCT controllers]({URL}#dimmers): ⚪ turn on with timer",
        f"[dimmers]({URL}#dimmers): 🟢 turn on with timer",
    ]
    assert classed_card(adapter("zha", "turn_on_for", timer)).lines[0] == (
        f"[CCT controllers, dimmers]({URL}#dimmers): 🟢 turn on with timer"
    )
    with pytest.raises(SystemExit, match="sections zha Nowhere: no class in capabilities has that section"):
        data(sections={"zha": {"Nowhere": {"phrase": "x"}}})


def test_a_class_refused_on_every_action_has_no_line(root):
    """A class whose only entries are not built yet stays off the card."""
    unbuilt = {"CCT": NotBuilt("No timer yet", "https://x.y/z")}
    adapters = (
        adapter("zha", "turn_on_for", AdapterScope(capabilities=verified("Light"), not_built=unbuilt)),
        adapter("zha", "raise_brightness", AdapterScope(capabilities=verified("Light"))),
    )
    registry = classed_registry(*adapters)
    card = gc.card("zha", registry, list(adapters), data(registry, no_known_method=[]))
    assert card.lines == [f"[dimmers]({URL}#dimmers): 🟢 turn on with timer, smooth dimming"]


def brand_registry(*adapters) -> FakeRegistry:
    """classed_registry, with ZHA's classes in families: brands, as Zigbee2MQTT's and ZHA's are."""
    registry = classed_registry(*adapters)
    info = registry.integrations["zha"]
    info.classes |= {"hue": LIGHT, "other": LIGHT, "RGB": LIGHT}
    info.families = (
        SimpleNamespace(key="Beta", classes={"Light": LIGHT}),
        SimpleNamespace(key="acme", classes={"CCT": LIGHT, "RGB": LIGHT, "Switch": CLASSES["Switch"]}),
    )
    return registry


def test_lines_sort_by_brand_then_tested_then_other_last(root):
    """Brands (families) alphabetically, case-insensitive, then other brands (no family), then native
    groups; within a brand, tested lines first, "other …" last, the rest alphabetically, and so do a line's names."""
    record2(
        root,
        "zha",
        "turn_on_for",
        ran("switch", device("P1", "1", "Switch"), role="switch_plug"),
        ran("light", device("LTA009", "1", "Light"), device("P1", "1", "Switch"), group=True, role="group"),
    )
    timer = AdapterScope(
        domains=verified("light", "switch"),
        capabilities=verified("Switch", "Light") | documented("other", "CCT", "RGB"),
    )
    dimming = AdapterScope(capabilities=labs("CCT", "other", "Light"))
    capabilities = copy.deepcopy(DATA["capabilities"])
    capabilities["zha"]["CCT"]["phrase"] = "other Acme lights"
    capabilities["zha"]["other"] = {"phrase": "other brands", "section": "Lights"}
    adapters = (adapter("zha", "turn_on_for", timer), adapter("zha", "raise_brightness", dimming))
    registry = brand_registry(*adapters)
    card = gc.card("zha", registry, list(adapters), data(registry, capabilities=capabilities))
    # acme before Beta: brands sort case-insensitively.
    assert card.lines == [
        f"[native groups]({URL}#native-groups) ✔: 🟢 turn on with timer",  # native groups first
        f"[relays]({URL}#relays) ([Plug]({URL}#plug) ✔): 🟢 turn on with timer",  # acme's tested line first
        f"[RGB controllers]({URL}#dimmers): 🟡 turn on with timer",
        f"[other Acme lights]({URL}#dimmers): 🟡 turn on with timer · ⚪ smooth dimming",
        f"[dimmers]({URL}#dimmers): 🟢 turn on with timer · ⚪ smooth dimming",  # Beta
        f"[other brands]({URL}#lights): 🟡 turn on with timer · ⚪ smooth dimming",
        f"[Old plug]({URL}#old-plug): 🔴",
    ]


def test_a_models_variants_are_children_of_one_parent_line(root):
    """A section with `variants` is a parent line naming the model and what to check; each child names
    its variants (", or " between two) with ✔ for a rig-tested model, never its name, and merges only with its own
    section's classes."""
    record2(root, "zha", "turn_on_for", ran("switch", device("P1", "1", "Switch"), role="switch_plug"))
    timer = AdapterScope(
        domains=verified("light", "switch"), capabilities=verified("Switch") | labs("CCT", "RGB", "Light")
    )
    capabilities = copy.deepcopy(DATA["capabilities"])
    for name, phrase in (("Switch", "maker A"), ("CCT", "maker B"), ("RGB", "no setting")):
        capabilities["zha"][name] = {"phrase": phrase, "section": "Plug"}
    sections = {"zha": {"Plug": {"phrase": "Plugs", "variants": "check Manufacturer on its page"}}}
    adapters = (adapter("zha", "turn_on_for", timer),)
    registry = classed_registry(*adapters)
    registry.integrations["zha"].classes["RGB"] = LIGHT
    card = gc.card("zha", registry, list(adapters), data(registry, capabilities=capabilities, sections=sections))
    assert card.lines[:2] == [
        f"[Plugs]({URL}#plug): check Manufacturer on its page\n"
        f"  - [maker A]({URL}#plug) ✔: 🟢 turn on with timer\n"
        f"  - [maker B, or no setting]({URL}#plug): ⚪ turn on with timer",
        f"[dimmers]({URL}#dimmers): ⚪ turn on with timer",  # same features, another section: its own line
    ]
    assert card.render().splitlines()[2:5] == [
        f"- [Plugs]({URL}#plug): check Manufacturer on its page",
        f"  - [maker A]({URL}#plug) ✔: 🟢 turn on with timer",
        f"  - [maker B, or no setting]({URL}#plug): ⚪ turn on with timer",
    ]


def brand_lines(families=(), **capabilities) -> list[str]:
    """Each class with its (phrase, section, status), as `class_lines` and `ordered` put them on a card."""
    entries = {name: {"phrase": phrase, "section": section} for name, (phrase, section, _) in capabilities.items()}
    data = gc.Data(requires={}, models={}, capabilities={"x": entries}, no_known_method=[])
    found = {(name, "light"): {status: {"stop"}} for name, (_, _, status) in capabilities.items()}
    brand = gc.brands(SimpleNamespace(families=families))
    lines = gc.class_lines("x", found, data, dict.fromkeys(capabilities, LIGHT), ["light"], {}, brand)
    return [line.plain() for line in gc.ordered(lines, brand, set())]


def test_classes_of_two_brands_never_share_a_line():
    """The same features, but one class is acme's and one no family's."""
    acme = (SimpleNamespace(key="acme", classes={"a": LIGHT, "b": LIGHT}),)
    shown = brand_lines(acme, a=("bulbs", "A", "works"), b=("plugs", "A", "works"), c=("lamps", "C", "works"))
    assert shown == ["bulbs, plugs", "lamps"]


def test_without_families_the_other_brands_section_sorts_last():
    """Hue's "scenes with other brands' lights" after its own lines, and on a line of its own."""
    shown = brand_lines(
        a=("zebra lights", "Device classes", "works"), b=("scenes with other brands' lights", "Other brands", "works")
    )
    assert shown == ["zebra lights", "scenes with other brands' lights"]


def test_a_lines_phrases_sort_like_lines_and_variants_join_with_or():
    line = gc.Line((), {"S": ["other makers", "Beta", "_TZ3000_b", "alpha"]})
    (line,) = gc.ordered([line], lambda cls, section: (0, ""), set())
    # Plain words before maker strings, which keep their "_"; "other …" last.
    assert line.sections == {"S": ["alpha", "Beta", "_TZ3000_b", "other makers"]}
    line.variant = True
    data = gc.Data(requires={}, models={}, capabilities={}, no_known_method=[])
    assert line.name(gc.Card("X"), "x", data, set()) == f"[alpha, Beta, _TZ3000_b, or other makers]({URL}#s)"
    variant = gc.Line((), {"S": ["_TZ3000_gjnozsaz", "no countdown setting"]}, variant=True)
    (variant,) = gc.ordered([variant], lambda cls, section: (0, ""), set())
    assert variant.name(gc.Card("X"), "x", data, set()) == f"[no countdown setting, or _TZ3000_gjnozsaz]({URL}#s)"
    # A parent's children sort the same way: "other …" last.
    children = [gc.Line((), {"S": ["other makers"]}, variant=True), gc.Line((), {"S": ["zeta"]}, variant=True)]
    (parent,) = gc.ordered([gc.Line((), {"S": ["plugs"]}, note="check", children=children)], lambda *_: (0, ""), set())
    assert [child.plain() for child in parent.children] == ["zeta", "other makers"]


# The fold and the cap (docs/evidence.md, The Labs flag).


def labs_card(*adapters, broken=None, **changes):
    registry = classed_registry(*adapters)
    registry.integrations["zha"].classes["RGBCCT"] = LIGHT
    return gc.card("zha", registry, list(adapters), data(registry, **changes))


def timer_labs(*classes, **scope):
    return adapter("zha", "turn_on_for", AdapterScope(capabilities=labs(*classes), **scope))


def test_two_lines_that_show_only_labs_fold_into_one_last_line(root):
    dimming = adapter("zha", "raise_brightness", AdapterScope(capabilities=labs("Light")))
    card = labs_card(timer_labs("Light", "CCT"), dimming)
    # CCT controllers and dimmers are one section but show different features, so two lines; the fold goes after
    # devices.yaml's entry, and the cap counts it as the one Labs line it is.
    assert card.lines == [
        f"[Old plug]({URL}#old-plug): 🔴",
        f"⚪ [CCT controllers]({URL}#dimmers) (turn on with timer);"
        f" [dimmers]({URL}#dimmers) (turn on with timer, smooth dimming)",
    ]
    assert (card.total, len(card.labs_lines)) == (2, 1)


def test_one_labs_line_stays_as_it_is(root):
    card = labs_card(timer_labs("CCT"))
    assert card.lines == [f"[CCT controllers]({URL}#dimmers): ⚪ turn on with timer", f"[Old plug]({URL}#old-plug): 🔴"]
    assert (card.total, len(card.labs_lines)) == (2, 1)


def test_lines_with_the_same_features_share_one_parenthesis_in_their_order(root):
    """Classes of two brands never share a line (`brands`), so each is its own, and the fold joins them."""
    adapters = (timer_labs("Light", "CCT"),)
    registry = brand_registry(*adapters)
    card = gc.card("zha", registry, list(adapters), data(registry))
    assert card.lines[-1] == (f"⚪ [CCT controllers]({URL}#dimmers), [dimmers]({URL}#dimmers) (turn on with timer)")


def test_a_group_sits_where_its_last_line_does_so_the_other_brands_group_comes_last(root):
    """Lines in card order: acme's CCT (smooth dimming), Beta's Light (timer, smooth dimming), other brands (smooth
    dimming). The smooth-dimming group holds the first and last, so it follows the group of the middle line."""
    dimming = adapter("zha", "raise_brightness", AdapterScope(capabilities=labs("CCT", "Light", "other")))
    timer = adapter("zha", "turn_on_for", AdapterScope(capabilities=labs("Light")))
    registry = brand_registry(dimming, timer)
    capabilities = copy.deepcopy(DATA["capabilities"])
    capabilities["zha"]["other"] = {"phrase": "other brands", "section": "Lights"}
    card = gc.card("zha", registry, [dimming, timer], data(registry, capabilities=capabilities))
    assert card.lines[-1] == (
        f"⚪ [dimmers]({URL}#dimmers) (turn on with timer, smooth dimming);"
        f" [CCT controllers]({URL}#dimmers), [other brands]({URL}#lights) (smooth dimming)"
    )


def test_a_no_known_method_part_stays_inside_its_parenthesis(root):
    broken = {"CCT": NoKnownMethod("Old plug", "No timer", "https://x.y/z")}
    off = adapter("zha", "turn_off_for", AdapterScope(capabilities=labs("RGBCCT"), no_known_method=broken))
    card = labs_card(timer_labs("CCT", "RGBCCT"), off)
    assert card.lines[-1] == (
        f"⚪ [bulbs]({URL}#bulbs) (turn on with timer, turn off with timer);"
        f" [CCT controllers]({URL}#dimmers) (turn on with timer · 🔴 turn off with timer)"
    )
    assert len(card.labs_lines) == 1


def test_a_mixed_line_is_no_labs_line_and_never_folds_with_one(root):
    """🟡 · ⚪ makes a real claim: it neither folds nor counts, so the one ⚪-only line beside it stays as it is."""
    timer = adapter("zha", "turn_on_for", AdapterScope(capabilities=documented("Light") | labs("CCT")))
    dimming = adapter("zha", "raise_brightness", AdapterScope(capabilities=labs("Light")))
    card = labs_card(timer, dimming)
    assert card.lines[:2] == [
        f"[CCT controllers]({URL}#dimmers): ⚪ turn on with timer",
        f"[dimmers]({URL}#dimmers): 🟡 turn on with timer · ⚪ smooth dimming",
    ]
    assert (card.total, card.labs_lines) == (3, [card.lines[0]])


def test_a_variants_children_never_fold(root):
    timer = AdapterScope(
        domains=verified("light", "switch"), capabilities=verified("Switch") | labs("CCT", "RGB", "Light")
    )
    capabilities = copy.deepcopy(DATA["capabilities"])
    for name, phrase in (("Switch", "maker A"), ("CCT", "maker B"), ("RGB", "no setting")):
        capabilities["zha"][name] = {"phrase": phrase, "section": "Plug"}
    sections = {"zha": {"Plug": {"phrase": "Plugs", "variants": "check Manufacturer on its page"}}}
    adapters = (
        adapter("zha", "turn_on_for", timer),
        adapter("zha", "raise_brightness", AdapterScope(capabilities=labs("Light", "RGBCCT"))),
    )
    registry = classed_registry(*adapters)
    registry.integrations["zha"].classes.update({"RGB": LIGHT, "RGBCCT": LIGHT})
    card = gc.card("zha", registry, list(adapters), data(registry, capabilities=capabilities, sections=sections))
    parent = next(line for line in card.lines if line.startswith(f"[Plugs]({URL}#plug)"))
    assert "  - [maker B, or no setting]" in parent and "⚪ turn on with timer" in parent
    # The children stay under their parent and count as lines; the two top-level lines fold.
    assert sum(line.startswith("⚪ ") for line in card.lines) == 1
    assert (card.total, len(card.labs_lines)) == (5, 2)


def test_the_model_keeps_the_unfolded_lines_with_parents_and_per_feature_status(root):
    timer = AdapterScope(
        domains=verified("light", "switch"), capabilities=verified("Switch") | labs("CCT", "RGB", "Light")
    )
    capabilities = copy.deepcopy(DATA["capabilities"])
    for name, phrase in (("Switch", "maker A"), ("CCT", "maker B"), ("RGB", "no setting")):
        capabilities["zha"][name] = {"phrase": phrase, "section": "Plug"}
    sections = {"zha": {"Plug": {"phrase": "Plugs", "variants": "check Manufacturer on its page"}}}
    adapters = (
        adapter("zha", "turn_on_for", timer),
        adapter("zha", "raise_brightness", AdapterScope(capabilities=labs("Light", "RGBCCT"))),
    )
    registry = classed_registry(*adapters)
    registry.integrations["zha"].classes.update({"RGB": LIGHT, "RGBCCT": LIGHT})
    card = gc.card("zha", registry, list(adapters), data(registry, capabilities=capabilities, sections=sections))
    # The fold touches the rendered lines only: the model still holds every top-level line, children under their parent.
    assert len(card.entries) > len(card.lines) - 1
    (parent,) = (line for line in card.entries if line.children)
    assert all(child.parent is parent and child.variant for child in parent.children)
    assert parent.children[0].features == {"turn on with timer": (("works", "turn on with timer"),)}


def test_a_feature_whose_actions_differ_has_a_status_per_part():
    statuses = {"should": {"lower_brightness", "stop"}, "labs": {"raise_brightness", "stop"}}
    assert gc.feature_statuses(statuses) == {
        "smooth dimming": (("should", "smooth dimming down"), ("labs", "smooth dimming up")),
        "stop": (("should", "stop"), ("labs", "stop")),
    }
    assert gc.shape(statuses) == (
        ("should", ("smooth dimming down",)),
        ("labs", ("smooth dimming up",)),
    )  # the README line still folds stop


def share(total, labs_lines):
    return [gc.Card("c", total=total, labs_lines=["⚪ x"] * labs_lines)]


def test_the_cap_fails_over_a_quarter_and_names_the_share_and_the_lines():
    assert gc.LABS_SHARE_MAX == 0.25
    gc.check_share(share(100, 25))
    gc.check_share(share(0, 0))
    with pytest.raises(SystemExit, match=r"26 of 100 card lines \(26%\) are in Labs, over the 25% cap[\s\S]*⚪ x"):
        gc.check_share(share(100, 26))


def test_the_cap_counts_every_card_together():
    """A card of nothing but Labs lines passes beside a large tried one: the share is over all the cards."""
    tried, labs_lines = gc.Card("a", total=96), gc.Card("b", total=4, labs_lines=["⚪ x"] * 4)
    with pytest.raises(SystemExit, match=r"4 of 4 card lines"):
        gc.check_share([labs_lines])
    gc.check_share([tried, labs_lines])  # 4 of 100
    with pytest.raises(SystemExit, match=r"30 of 100 card lines"):
        gc.check_share(
            [gc.Card("a", total=50, labs_lines=["⚪ x"] * 15), gc.Card("b", total=50, labs_lines=["⚪ x"] * 15)]
        )


def test_the_cap_runs_in_a_plain_run_and_in_check(root, monkeypatch):
    registry = classed_registry(adapter("zha", "stop", AdapterScope(capabilities=labs("Switch"))))
    run = write_files(root, registry, monkeypatch)
    for argv in ([], ["--check"]):
        with pytest.raises(SystemExit, match="of 2 card lines"):  # the Labs line and devices.yaml's entry
            run(argv)


# The page: tested devices, the matrix per integration, and what is not supported.


def page_of(*adapters, registry=None, **changes):
    """The generated block, and the registry and data it came from."""
    registry = registry or classed_registry(*adapters)
    found = data(registry, **changes)
    # The integrations' pages hold every section their classes and entries link, as write_bundles writes them.
    found.pages = {
        key: {gf.slug(item["section"]) for item in items.values()} | {"old-plug"}
        for key, items in found.capabilities.items()
    }
    return gc.evidence(registry, found), registry, found


def table_after(block, heading):
    """The table lines under the heading, up to the first line that isn't one after them."""
    found = []
    for line in block.split(f"{heading}\n", 1)[1].splitlines():
        if line.startswith("|"):
            found.append(line)
        elif found:
            break
    return found


def test_a_matrix_cell_links_its_proof_by_status(root):
    record2(root, "zha", "turn_on_for", ran("light", device("LTA009", "1", "Light")))
    timer = AdapterScope(domains=verified("light"), capabilities=verified("Light") | documented("CCT") | labs("Switch"))
    refusing = AdapterScope(
        capabilities=verified("Light"), no_known_method={"RGB": NoKnownMethod("Old plug", "No timer", "https://x.y/z")}
    )
    adapters = (adapter("zha", "turn_on_for", timer), adapter("zha", "get_attributes", refusing))
    registry = classed_registry(*adapters)
    registry.integrations["zha"].classes["RGB"] = LIGHT
    block, *_ = page_of(*adapters, registry=registry)
    zha = f"{gc.DOCS_URL}docs/integrations/zha/index.md"
    assert table_after(block, "### ZHA") == [
        "| Class | turn on with timer | get attributes |",
        "|---|---|---|",
        # 🟢: its record; the model is a link to its heading, which is on this page.
        # (A Verified class no record reaches shows no link: the coverage check warns of it.)
        "| [dimmers](integrations/zha/index.md#dimmers) ([Hue lamp](#hue-lamp) ✔)"
        " | 🟢 [record](integrations/zha/test-records/turn_on_for.json) | 🟢 |",
        # 🟡 and ⚪: the class's section on its integration's page.
        "| [CCT controllers](integrations/zha/index.md#dimmers) | 🟡 [why](integrations/zha/index.md#dimmers) | |",
        "| [relays](integrations/zha/index.md#relays) | ⚪ [why](integrations/zha/index.md#relays) | |",
        # 🔴: its row under Not supported; the devices.yaml entry that names no class is a row of its own.
        "| [RGB controllers](integrations/zha/index.md#dimmers) | | 🔴 [why](#old-plug) |",
        "| [Old plug](integrations/zha/index.md#old-plug) | 🔴 [why](#old-plug) | 🔴 [why](#old-plug) |",
    ]
    assert zha not in block  # the page's own links are relative
    assert '<a id="old-plug"></a>Old plug' in block


def test_a_feature_whose_actions_differ_shows_its_parts_each_with_its_proof(root):
    record2(root, "zha", "lower_brightness", ran("light", device("LTA009", "1", "Light")))
    lower = adapter("zha", "lower_brightness", AdapterScope(capabilities=verified("Light")))
    raise_ = adapter("zha", "raise_brightness", AdapterScope(capabilities=labs("Light")))
    block, *_ = page_of(lower, raise_)
    assert table_after(block, "### ZHA")[2] == (
        "| [dimmers](integrations/zha/index.md#dimmers) ([Hue lamp](#hue-lamp) ✔)"
        " | 🟢 down [record](integrations/zha/test-records/lower_brightness.json)"
        " · ⚪ up [why](integrations/zha/index.md#dimmers) |"
    )


def test_a_variants_children_are_indented_under_their_parent_row(root):
    block, *_ = page_of(
        adapter(
            "zha", "turn_on_for", AdapterScope(domains=verified("light", "switch"), capabilities=labs("Switch", "CCT"))
        ),
        capabilities={
            "zha": {
                **DATA["capabilities"]["zha"],
                "Switch": {"phrase": "maker A", "section": "Plug"},
                "CCT": {"phrase": "no setting", "section": "Plug"},
            }
        },
        sections={"zha": {"Plug": {"phrase": "Plugs", "variants": "check Manufacturer on its page"}}},
        no_known_method=[],
    )
    rows = table_after(block, "### ZHA")
    assert rows[2].startswith("| [Plugs](integrations/zha/index.md#plug): check Manufacturer on its page |")
    assert all(row.startswith("| &emsp;[") for row in rows[3:])


def test_a_tested_model_has_a_heading_with_a_table_of_its_integrations_features_firmware_and_how(root):
    record2(root, "zha", "stop", ran("light", device("LTA009", "1.2.3", "Light")))
    manual_file(root, rows=[signoff(devices=(("P1", "Switch"),), calls=bound("stop"))])
    block, *_ = page_of(adapter("zha", "stop", AdapterScope(capabilities=verified("Light", "Switch"))))
    assert block.index("### Hue lamp") < block.index("### Plug") < block.index("### Native groups")  # bulbs first
    assert "Bulb. Model IDs: `LTA009`, `9290024684`." in block
    assert table_after(block, "### Hue lamp") == [
        "| Integration | Features tested | Firmware | How |",
        "|---|---|---|---|",
        "| [ZHA](#zha) | [stop](integrations/zha/test-records/stop.json) | `1.2.3` | ✔ rig |",
    ]
    # A hand test names no firmware, and says it was by hand.
    assert table_after(block, "### Plug")[2] == (
        "| [ZHA](#zha) | [stop](integrations/zha/test-records/_manual.json) | | by hand |"
    )


def test_a_row_resting_on_reports_shows_by_report_linking_them_and_its_firmware(root):
    """A sign-off of users' reports credits its class as a hand test does, and links the issues, not the file."""
    issues = [f"https://github.com/DeviceSide/DeviceSide/issues/{number}" for number in (7, 9)]
    row = signoff(devices=(("P1", "Switch"),), calls=bound("stop"), reports=issues[:1])
    row["devices"][0]["firmware"] = "2.0"
    manual_file(root, rows=[row])
    stop = adapter("zha", "stop", AdapterScope(capabilities=verified("Switch")))
    block, registry, found = page_of(stop)
    assert (
        table_after(block, "### Plug")[2] == f"| [ZHA](#zha) | [stop]({issues[0]}) | `2.0` | [by report]({issues[0]}) |"
    )
    assert f"[by report]({issues[0]})" in "\n".join(table_after(block, "### ZHA"))
    (card,) = gc.card_list(registry, found)
    assert list(card.reached) == ["Plug"]
    manual_file(root, rows=[row | {"reports": issues}])
    block, *_ = page_of(stop)
    both = f"by report [#7]({issues[0]}) [#9]({issues[1]})"
    assert table_after(block, "### Plug")[2] == f"| [ZHA](#zha) | stop: {both} | `2.0` | {both} |"


def test_native_groups_have_a_heading_with_their_tested_features_per_integration(root):
    stop = adapter("zha", "stop")
    block, *_ = page_of(stop)
    assert "### Native groups\n\nNo native group has been tested yet." in block
    record2(root, "zha", "stop", ran("light", device("LTA009", "1"), group=True, role="group"))
    block, *_ = page_of(stop)
    assert table_after(block, "### Native groups") == [
        "| Integration | Features tested | How |",
        "|---|---|---|",
        "| [ZHA](#zha) | [stop](integrations/zha/test-records/stop.json) | ✔ rig |",
    ]


def test_not_supported_merges_entries_across_integrations_and_numbers_the_anchors_of_one_name(root):
    shared = [
        {"what": "Old plug", "integrations": ["zha", "hue"], "reason": "No timer", "source": "https://x.y/z"},
        {"what": "Old plug", "integrations": ["hue"], "reason": "A | B", "source": "https://x.y/other"},
    ]
    stays_on = [{"what": "Odd plug", "integrations": ["zha"], "reason": "It stays on", "source": "https://x.y/on"}]
    registry = FakeRegistry(adapter("zha", "stop"), adapter("hue", "stop"))
    found = data(registry, no_known_method=shared, not_built=stays_on)
    block = gc.evidence(registry, found)
    assert table_after(block, "## Not supported") == [
        "| Devices | Integrations | Features | Why | Source |",
        "|---|---|---|---|---|",
        "| Odd plug | ZHA | | It stays on | [source](https://x.y/on) |",  # sorted by name; no anchor: no cell links it
        '| <a id="old-plug"></a>Old plug | ZHA, Hue | | No timer | [source](https://x.y/z) |',
        '| <a id="old-plug-1"></a>Old plug | Hue | | A \\| B | [source](https://x.y/other) |',
    ]


def test_a_field_proven_less_than_its_feature_is_a_footnote_under_the_matrix(root):
    scope = AdapterScope(domains=verified("light"), fields=verified("brightness") | labs("transition"))
    block, *_ = page_of(adapter("zha", "lower_brightness", scope))
    assert "\nFields proven less than their feature:\n- smooth dimming: ⚪ `transition`\n" in block
    whole = AdapterScope(domains=labs("light"), fields=labs("transition"))
    assert "Fields proven" not in page_of(adapter("zha", "lower_brightness", whole))[0]


def test_a_field_in_labs_on_some_classes_is_a_footnote_naming_them(root):
    scope = AdapterScope(
        fields=verified("brightness", "transition"),
        capabilities=verified("Light", "CCT") | labs("Switch"),
        class_labs=labs_fields("transition", classes=("CCT", "Switch"))
        | labs_fields("brightness", "transition", classes=("Light",)),
    )
    block, *_ = page_of(adapter("zha", "lower_brightness", scope))
    # Switch is in Labs throughout, so its field is proven no less than its feature there.
    assert (
        "\nFields proven less than their feature:\n"
        "- smooth dimming: ⚪ `transition` on [CCT controllers](integrations/zha/index.md#dimmers)\n"
        "- smooth dimming: ⚪ `brightness`, `transition` on [dimmers](integrations/zha/index.md#dimmers)\n"
    ) in block


def test_a_caveat_is_under_its_integrations_heading(root):
    scope = AdapterScope(caveat=unmaintained(ISSUE_REASON))
    block, *_ = page_of(adapter("zha", "turn_on_for", scope))
    assert f"### ZHA\n\n- [⚠️ Unmaintained]({ISSUE_REASON}): turn on with timer\n\n| Class |" in block


def test_a_dead_link_in_the_page_or_the_cards_is_named(root, monkeypatch):
    found = gc.load(FakeRegistry(), write_bundles(root, monkeypatch))
    pages = f"{gc.DOCS_URL}docs/integrations/zha/index.md"
    gc.check_sections(
        '### Here\n[a](#here) <a id="there"></a> [b](#there) [c](https://x.y/z)', f"[d]({URL}#here)", found, []
    )
    gc.check_sections(f"[a](integrations/zha/index.md#dimmers) [b]({pages}#dimmers)", "", found, [])
    for shown, dead in (
        ("[a](#nowhere)", "nowhere"),
        (f"[a]({URL}#nowhere)", "nowhere"),
        (f"[a]({pages}#nowhere)", "docs/integrations/zha/index.md#nowhere"),
        ("[a](integrations/zha/test-records/none.json)", "integrations/zha/test-records/none.json"),
        ("[a](integrations/zha/index.md#nowhere)", "integrations/zha/index.md#nowhere"),
    ):
        with pytest.raises(SystemExit, match=f"no heading or file for {re.escape(dead)}"):
            gc.check_sections(shown, "", found, [])
    with pytest.raises(SystemExit, match="no heading or file for gone"):
        gc.check_sections("", f"[a]({URL}#gone)", found, [])  # a card's link counts too


def test_a_documented_or_labs_class_needs_its_section_on_its_integrations_page(root, monkeypatch):
    registry = FakeRegistry(adapter("zha", "stop", AdapterScope(domains=labs("light"))))
    run = write_files(root, registry, monkeypatch)
    index = root / "docs" / "integrations" / "zha" / "index.md"
    index.write_text(index.read_text().replace("### Lights\n\n", ""))
    with pytest.raises(SystemExit, match=r"no heading for Lights \(zha\) on the integration's page"):
        run([])
    # A Verified class's missing section is a dead card link all the same.
    registry = FakeRegistry(adapter("zha", "stop"))
    run = write_files(root, registry, monkeypatch)
    index.write_text(index.read_text().replace("### Lights\n\n", ""))
    with pytest.raises(SystemExit, match="no heading or file for lights"):
        run([])


def test_a_class_refused_by_two_actions_links_each_cell_to_its_own_row(root):
    refused = {
        "lower_brightness": NoKnownMethod("Old plug", "It ignores a ramp", "https://x.y/ramp"),
        "stop": NoKnownMethod("Old plug", "It ignores a stop", "https://x.y/stop"),
    }
    adapters = tuple(
        adapter("zha", action, AdapterScope(capabilities=verified("Switch"), no_known_method={"RGB": entry}))
        for action, entry in refused.items()
    )
    registry = classed_registry(*adapters)
    registry.integrations["zha"].classes["RGB"] = LIGHT
    block, *_ = page_of(*adapters, registry=registry, no_known_method=[])
    reasons = {
        re.search(r'id="([^"]+)"', row)[1]: row.split(" | ")[3] for row in table_after(block, "## Not supported")[2:]
    }
    (row,) = (row for row in table_after(block, "### ZHA") if row.startswith("| [RGB controllers]"))
    ramp, stop = (cell.split("(#")[1].rstrip(") |") for cell in row.split(" | ")[1:3])
    assert (reasons[ramp], reasons[stop]) == ("It ignores a ramp", "It ignores a stop")


def test_tested_devices_lists_a_model_a_row_names_though_no_card_credits_it(root):
    """A hand-tested model in a Labs class, and a hand-tested group a null-class member keeps off the cards, are on the
    page: it lists every model with a record row, and the matrix keeps the levels the code sets."""
    manual_file(
        root,
        rows=[
            signoff(devices=(("LTA009", "Light"),), calls=bound("stop")),
            signoff(devices=(("P1", "Switch"), ("LTA009", None)), calls=bound("stop"), group=True),
        ],
    )
    block, registry, found = page_of(adapter("zha", "stop", AdapterScope(capabilities=labs("Light", "Switch"))))
    (card,) = gc.card_list(registry, found)
    assert (card.reached, card.groups) == ({}, None)
    manual_link = "[stop](integrations/zha/test-records/_manual.json)"
    assert table_after(block, "### Hue lamp")[2] == f"| [ZHA](#zha) | {manual_link} | | by hand |"
    assert table_after(block, "### Native groups")[2] == f"| [ZHA](#zha) | {manual_link} | by hand |"
    assert "🟢" not in "\n".join(table_after(block, "### ZHA"))


def test_a_features_parts_read_in_the_same_order_in_the_matrix_and_under_tested_devices(root):
    for action in ("lower_brightness", "raise_brightness"):
        record2(root, "zha", action, ran("light", device("LTA009", "1", "Light")))
    scope = AdapterScope(capabilities=verified("Light"))
    block, *_ = page_of(adapter("zha", "lower_brightness", scope), adapter("zha", "raise_brightness", scope))
    parts = (
        "[up](integrations/zha/test-records/raise_brightness.json)"
        " [down](integrations/zha/test-records/lower_brightness.json)"
    )
    assert f"smooth dimming: {parts}" in table_after(block, "### Hue lamp")[2]
    assert parts in table_after(block, "### ZHA")[2]


def test_a_line_of_several_sections_links_one_why_per_cell_and_all_its_classes_in_its_name(root):
    adapters = (adapter("zha", "stop", AdapterScope(capabilities=labs("Light", "RGBCCT"))),)
    registry = classed_registry(*adapters)
    registry.integrations["zha"].classes["RGBCCT"] = LIGHT
    block, *_ = page_of(*adapters, registry=registry, no_known_method=[])
    (row,) = table_after(block, "### ZHA")[2:]
    name, stop = row.split(" | ")
    assert "index.md#dimmers" in name and "index.md#bulbs" in name
    assert stop.count("[why]") == 1
