"""scripts/gen_compat.py: levels from the records, models from the Device row and devices.yaml, the README cards, the
evidence block, and the stale check."""

from types import SimpleNamespace

import pytest
import yaml

from custom_components.deviceside.core.scope import AdapterScope, documented, experimental, reported, verified
from scripts import check_release as cr
from scripts import gen_compat as gc

URL = gc.PAGE_URL
DATA = {
    "integrations": {"zha": {"requires": "Zigbee 3.0"}},
    "models": [
        {"name": "Hue lamp", "ids": ["LTA009", "9290024684"], "type": "bulb"},
        {"name": "Plug", "ids": ["P1"], "type": "plug"},
    ],
    "capabilities": {
        "zha": {
            "switch": {"phrase": "plugs", "section": "Zigbee plugs"},
            "Light": {"phrase": "dimmers", "section": "Dimmers"},
            "CCT": {"phrase": "CCT controllers", "section": "Dimmers"},
        }
    },
    "doesnt_work": [{"what": "Old plug", "integrations": ["zha"], "reason": "No timer", "source": "https://x.y/z"}],
    "reports": [],
}
PROSE = "# Page\n\n" + "".join(
    f"### {heading}\n\n" for heading in ("Hue lamp", "Plug", "Zigbee plugs", "Dimmers", "Old plug", "Native groups")
)

REPORT = {"integration": "zha", "model": "P1", "firmware": "1.2", "deviceside": "0.1.0"}


def record(root, integration, name, *, result="pass", device="Hue lamp (`LTA009`), firmware `1.2.3`"):
    path = root / "docs" / "test-records" / integration / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# t\n\n| | |\n|---|---|\n| Result | {result} |\n| Device | {device} |\n")
    return path


class FakeRegistry:
    integrations = {"zha": SimpleNamespace(title="ZHA"), "hue": SimpleNamespace(title="Hue")}

    def __init__(self, *adapters):
        self._adapters = adapters

    def matrix(self):
        yield "stop", "hue", None
        for adapter in self._adapters:
            yield adapter.action, adapter.integration, adapter


def adapter(integration, action, scope=None, *, experimental=False):
    return SimpleNamespace(
        integration=integration, action=action, scope=scope or AdapterScope(experimental=experimental)
    )


def data(registry=None, **changes):
    return gc.load_raw({**DATA, **changes}, registry or FakeRegistry())


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "REPO", tmp_path)
    monkeypatch.setattr(cr, "RECORDS", tmp_path / "docs" / "test-records")
    return tmp_path


def test_entries_are_model_ids_with_their_firmware_and_groups_are_not_models(root):
    path = record(
        root,
        "hue",
        "stop",
        device="Hue lamp (`LTA009`), firmware `1.2`; LCA016, firmware `0x01`; Zone, firmware `unknown`; "
        "Group, firmware `Zigbee2MQTT 2.1`; a temporary group holding only it",
    )
    assert gc.entries(path) == [("LTA009", "1.2"), ("LCA016", "0x01"), "group", "group", "group"]


def test_a_record_with_no_device_lists_no_models(root):
    assert gc.entries(record(root, "hue", "set_scene", device="none")) == []


def test_a_device_row_that_cannot_be_read_is_an_error(root):
    with pytest.raises(SystemExit, match="can't read Device entry"):
        gc.entries(record(root, "hue", "stop", device="a lamp"))
    path = record(root, "hue", "lower_hue")
    path.write_text("| Result | pass |\n")
    with pytest.raises(SystemExit, match="no Device row"):
        gc.entries(path)


def test_a_model_a_record_names_must_be_in_devices_yaml(root):
    record(root, "zha", "stop", device="Bulb (`NEW1`), firmware `1`")
    with pytest.raises(SystemExit, match="model 'NEW1' is not in docs/devices.yaml"):
        gc.row("stop", adapter("zha", "stop"), data())


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"models": [{"name": "Lamp", "ids": ["L1"], "type": "lamp"}]}, "type 'lamp' is not one of"),
        ({"models": [{"name": "Plug", "ids": [8979], "type": "plug"}]}, "must be a string; quote it"),
        (
            {"models": [{"name": "A", "ids": ["X"], "type": "plug"}, {"name": "B", "ids": ["X"], "type": "plug"}]},
            "twice",
        ),
        ({"capabilities": {"tuya": {}}}, "no integration 'tuya'"),
        (
            {"doesnt_work": [{"what": "X", "integrations": ["zha"], "reason": "", "source": "https://s"}]},
            "needs a reason",
        ),
        ({"reports": [{"integration": "zha", "model": "P1", "issue": "https://example.com/1"}]}, "issue URL"),
        ({"reports": [{"integration": "zha", "model": "ZZ", "issue": f"{gc.ISSUE_URL}1"}]}, "'ZZ' is not in"),
        (
            {"reports": [{"integration": "zha", "model": "P1", "worked": ["set_scene"], "issue": f"{gc.ISSUE_URL}1"}]},
            "zha has no set_scene adapter",
        ),
        ({"extra": 1}, "unknown key extra"),
        ({"integrations": {"zha": {}}}, "integrations zha needs a requires"),
        ({"models": [{"name": "Lamp", "ids": "L1", "type": "bulb"}]}, "ids must be a list"),
        ({"models": [{"ids": ["L1"], "type": "bulb"}]}, "needs a name"),
        (
            {"models": [{"name": "A", "ids": ["X"], "type": "plug"}, {"name": "A", "ids": ["Y"], "type": "plug"}]},
            "name 'A'",
        ),
        ({"capabilities": {"zha": {"switch": {"section": "S"}}}}, "needs a phrase"),
        (
            {"doesnt_work": [{"what": "X", "integrations": "zha", "reason": "r", "source": "https://s"}]},
            "must be a list",
        ),
        ({"doesnt_work": [{"what": "X", "integrations": ["zha"], "reason": "r", "source": "s"}]}, "https URL"),
        ({"reports": [{"model": "P1", "issue": f"{gc.ISSUE_URL}1"}]}, "needs a integration"),
        ({"reports": [{"integration": "tuya", "model": "P1", "issue": f"{gc.ISSUE_URL}1"}]}, "no integration 'tuya'"),
        (
            {"reports": [{"integration": "zha", "model": "P1", "worked": "x", "issue": f"{gc.ISSUE_URL}1"}]},
            "worked must",
        ),
        ({"reports": [{**REPORT, "issue": f"{gc.ISSUE_URL}1", "firmware": ""}]}, "needs firmware"),
        ({"reports": [{"integration": "zha", "model": "P1", "issue": f"{gc.ISSUE_URL}1"}]}, "needs firmware"),
        ({"reports": [{**REPORT, "issue": f"{gc.ISSUE_URL}1", "firmware": 1.1}]}, "needs firmware, as a quoted"),
    ],
)
def test_devices_yaml_is_validated(changes, error):  # a clean error, never a KeyError
    with pytest.raises(SystemExit, match=error):
        data(FakeRegistry(adapter("zha", "turn_on_for")), **changes)


def test_a_passing_record_on_a_released_adapter_is_verified(root):
    record(root, "zha", "stop")
    record(root, "zha", "stop-predicted_state", device="Zone, firmware `unknown`")
    line = gc.row("stop", adapter("zha", "stop"), data())
    assert line.startswith("| `stop` | Verified | `LTA009`, firmware `1.2.3`<br>group |")
    assert "[predicted state](test-records/zha/stop-predicted_state.md)" in line
    assert line.endswith("[record](test-records/zha/stop.md) | |")


def test_an_experimental_adapter_or_a_failing_record_is_experimental(root):
    record(root, "zha", "stop")
    record(root, "hue", "stop", result="fail")
    assert "| Experimental (in RCs only) |" in gc.row("stop", adapter("zha", "stop", experimental=True), data())
    line = gc.row("stop", adapter("hue", "stop"), data())
    assert line == f"| `stop` | {gc.NO_RECORD} | none |  | |"


def test_reports_fill_the_reports_column_of_their_action(root):
    issue = f"{gc.ISSUE_URL}12"
    reports = [{**REPORT, "worked": ["turn_on_for"], "failed": ["stop"], "issue": issue}]
    loaded = data(FakeRegistry(adapter("zha", "turn_on_for"), adapter("zha", "stop")), reports=reports)
    assert gc.reports_cell("zha", "turn_on_for", loaded) == f"✅ [#12]({issue}) `P1`"
    assert gc.reports_cell("zha", "stop", loaded) == f"❌ [#12]({issue}) `P1`"
    assert gc.reports_cell("hue", "stop", loaded) == ""


def test_documented_capabilities_get_a_row_and_are_in_rcs_only_on_an_experimental_adapter(root):
    caps = verified("Switch") | documented("Light", "CCT")
    released = adapter("zha", "stop", AdapterScope(capabilities=caps))
    flagged = adapter("zha", "stop", AdapterScope(experimental=True, capabilities=caps))
    assert gc.level_rows("stop", released) == ["| `stop` | Documented | none (untested: Light, CCT components) | | |"]
    [row] = gc.level_rows("stop", flagged)
    assert row.startswith("| `stop` | Experimental (in RCs only) |")
    assert gc.level_rows("stop", adapter("zha", "stop")) == []


def test_reported_documented_and_experimental_items_each_get_a_row_strongest_first():
    scope = AdapterScope(
        domains=verified("light") | experimental("switch"),
        capabilities=reported("Light") | documented("CCT") | experimental("RGB"),
        fields=verified("brightness") | experimental("transition"),
    )
    assert gc.level_rows("turn_on_for", SimpleNamespace(scope=scope)) == [
        "| `turn_on_for` | Reported | none (reported by users: Light components) | | |",
        "| `turn_on_for` | Documented | none (untested: CCT components) | | |",
        "| `turn_on_for` | Experimental | none (untested, behind Experimental features: switch entities; "
        "RGB components; transition fields) | | |",
    ]


def test_the_evidence_groups_by_integration_skips_unsupported_pairs_and_lists_what_doesnt_work(root):
    record(root, "zha", "stop")
    registry = FakeRegistry(adapter("zha", "stop"), adapter("hue", "lower_hue"))
    text = gc.evidence(registry, data(registry))
    assert text.index("### Hue") < text.index("### ZHA")
    assert f"`lower_hue` | {gc.NO_RECORD}" in text
    assert text.count("`stop`") == 1
    assert "| Old plug | No timer | [source](https://x.y/z) |" in text


def test_an_unflagged_adapter_with_no_verified_call_has_only_its_level_rows(root):
    registry = FakeRegistry(adapter("zha", "turn_on_for", AdapterScope(domains=experimental("switch"))))
    text = gc.evidence(registry, data(registry))
    assert f"`turn_on_for` | {gc.IN_RCS}" not in text
    assert (
        "| `turn_on_for` | Experimental | none (untested, behind Experimental features: switch entities) | | |" in text
    )


def zha_card(*adapters, **changes):
    registry = FakeRegistry(*adapters)
    return gc.card("zha", registry, list(adapters), data(registry, **changes))


def test_a_card_lists_tested_models_once_each_by_their_name_then_native_groups(root):
    record(root, "zha", "stop", device="Plug (`P1`), firmware `1`; Hue lamp (`LTA009`), firmware `1`")
    record(root, "zha", "turn_on_for", device="Hue lamp (`9290024684`), firmware `2`; Group, firmware `x`")
    card = zha_card(adapter("zha", "stop"), adapter("zha", "turn_on_for"))
    assert card.lines["works"] == [
        f"[Hue lamp]({URL}#hue-lamp)",  # bulbs before plugs; two ids, one model
        f"[Plug]({URL}#plug)",
        f"[native groups]({URL}#native-groups)",
    ]
    assert card.render().splitlines()[:3] == ["**ZHA** (Zigbee 3.0)", "", f"- ✅ {' · '.join(card.lines['works'])}"]


def test_a_card_leaves_out_flagged_adapters_and_failing_records(root):
    record(root, "zha", "stop")
    record(root, "zha", "turn_on_for", result="fail", device="Plug (`P1`), firmware `1`")
    scope = AdapterScope(experimental=True, domains=verified("light") | documented("switch"))
    card = zha_card(adapter("zha", "stop", scope), adapter("zha", "turn_on_for"))
    assert card.lines["works"] == []
    assert card.lines["should"] == []


def test_a_model_only_users_report_shows_with_a_badge_per_report(root):
    issue = f"{gc.ISSUE_URL}7"
    reports = [{**REPORT, "worked": ["turn_on_for"], "issue": issue}]
    card = zha_card(adapter("zha", "turn_on_for"), reports=reports)
    assert card.lines["works"] == [f"[Plug]({URL}#plug) [👥]({issue})"]


def test_a_report_on_a_flagged_adapter_stays_out_of_the_card(root):
    reports = [{**REPORT, "worked": ["turn_on_for"], "issue": f"{gc.ISSUE_URL}7"}]
    card = zha_card(adapter("zha", "turn_on_for", experimental=True), reports=reports)
    assert card.lines["works"] == []


def test_untested_classes_share_an_entry_per_feature_set_and_name_their_features(root):
    dimming = AdapterScope(capabilities=verified("Switch") | experimental("Light", "CCT"))
    timer = AdapterScope(domains=verified("light") | documented("switch"), capabilities=documented("Light"))
    card = zha_card(
        adapter("zha", "raise_brightness", dimming),
        adapter("zha", "stop", dimming),
        adapter("zha", "turn_on_for", timer),
    )
    assert card.lines["should"] == [f"[plugs]({URL}#zigbee-plugs), [dimmers]({URL}#dimmers): turn on with timer"]
    # stop rides the smooth move, so it isn't named. Two classes of one section share a link.
    assert card.lines["help"] == [f"[dimmers, CCT controllers]({URL}#dimmers): smooth dimming"]
    assert card.lines["no"] == [f"[Old plug]({URL}#old-plug)"]
    # A bullet per class entry, in OUTCOMES order.
    assert card.render().splitlines()[2:] == [
        f"- 🟡 {card.lines['should'][0]}",
        f"- 🙋 {card.lines['help'][0]}",
        f"- ⛔ {card.lines['no'][0]}",
    ]


def test_classes_of_one_section_say_their_shared_ending_once():
    assert (
        gc.merged(["CCT LED controllers", "RGB LED controllers"], "LED") == f"[LED controllers (CCT, RGB)]({URL}#led)"
    )
    assert gc.merged(["dimmers"], "Dimmers") == f"[dimmers]({URL}#dimmers)"
    # A phrase that is all ending has no prefix to list, so the phrases are listed whole.
    assert gc.merged(["LED controllers", "RGB LED controllers"], "LED") == (
        f"[LED controllers, RGB LED controllers]({URL}#led)"
    )


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


def test_an_untested_item_without_a_class_is_an_error(root):
    scope = AdapterScope(capabilities=verified("Switch") | documented("RGB"))
    with pytest.raises(SystemExit, match="no entry for zha RGB, which a scope holds as Documented"):
        zha_card(adapter("zha", "turn_on_for", scope))


def write_files(root, registry):
    page, readme, devices = root / "page.md", root / "README.md", root / "devices.yaml"
    page.write_text(PROSE + "## Evidence\n\n<!-- evidence:start -->\n<!-- evidence:end -->\n")
    readme.write_text("# R\n\n<!-- devices:start -->\n<!-- devices:end -->\n\nAfter.\n")
    devices.write_text(yaml.safe_dump(DATA))
    return lambda argv: gc.main(argv, registry, page, readme, devices)


def test_check_fails_on_a_stale_readme_or_page_until_they_are_regenerated(root, capsys):
    registry = FakeRegistry(adapter("zha", "stop"))
    device = record(root, "zha", "stop")
    run = write_files(root, registry)
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


def test_a_card_linking_to_a_missing_heading_fails(root):
    run = write_files(root, FakeRegistry(adapter("zha", "stop")))
    page = root / "page.md"
    page.write_text(page.read_text().replace("### Dimmers\n", ""))
    with pytest.raises(SystemExit, match="no heading for Dimmers"):
        run([])


def test_a_heading_inside_the_evidence_block_does_not_count(root):
    run = write_files(root, FakeRegistry(adapter("zha", "stop")))
    page = root / "page.md"
    text = page.read_text().replace("### Old plug\n", "")
    page.write_text(text.replace("<!-- evidence:start -->\n", "<!-- evidence:start -->\n### Old plug\n"))
    with pytest.raises(SystemExit, match="no heading for Old plug"):
        run([])


def test_the_checked_in_readme_and_page_match_the_real_records():
    """Both are generated: run the real check so local pytest catches a record or scope that drifts them."""
    assert gc.main(["--check"]) == 0
