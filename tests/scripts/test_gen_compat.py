"""scripts/gen_compat.py: levels from the records, models from the Device row and devices.yaml, the README cards, the
evidence block, and the stale check."""

from types import SimpleNamespace

import pytest
import yaml

from custom_components.deviceside.actions import discover
from custom_components.deviceside.core.scope import AdapterScope, documented, experimental, reported, verified
from scripts import check_release as cr
from scripts import gen_compat as gc
from scripts import gen_features as gf

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

REPORT = {
    "integration": "zha",
    "model": "P1",
    "item": "light",
    "firmware": "1.2",
    "deviceside": "0.1.0",
}


def report(**over):
    return {**REPORT, "issue": f"{gc.ISSUE_URL}1", **over}


def record(root, integration, name, *, result="pass", device="Hue lamp (`LTA009`), firmware `1.2.3`"):
    path = root / "docs" / "integrations" / integration / "test-records" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# t\n\n| | |\n|---|---|\n| Result | {result} |\n| Device | {device} |\n")
    return path


class FakeRegistry:
    integrations = {
        "zha": SimpleNamespace(title="ZHA", maintainers=("jasonmx",)),
        "hue": SimpleNamespace(title="Hue", maintainers=("jasonmx", "other")),
    }

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
    monkeypatch.setattr(cr, "BUNDLES", tmp_path / "docs" / "integrations")
    # Freshness needs git history and an adapter's source: every record is fresh unless a test says otherwise.
    monkeypatch.setattr(gc, "code_of", lambda adapter: [])
    monkeypatch.setattr(gc, "staleness", lambda record, code: None)
    return tmp_path


def test_entries_are_model_ids_with_their_firmware_and_groups_are_not_models(root):
    path = record(
        root,
        "hue",
        "stop",
        device="Hue lamp (`LTA009`), firmware `1.2`; LCA016, firmware `0x01`; Zone, firmware `unknown`; "
        "Group, firmware `Zigbee2MQTT 2.1`",
    )
    assert gc.entries(path) == [("LTA009", "1.2"), ("LCA016", "0x01"), "group", "group"]


def test_a_record_with_no_device_lists_no_models(root):
    assert gc.entries(record(root, "hue", "set_scene", device="none")) == []


@pytest.mark.parametrize("device", ["a lamp", "a temporary group holding only it"])
def test_a_device_entry_that_cannot_be_read_is_an_error(root, device):
    with pytest.raises(SystemExit, match="can't read Device entry"):
        gc.entries(record(root, "hue", "stop", device=device))


def test_a_missing_device_row_is_an_error(root):
    path = record(root, "hue", "lower_hue")
    path.write_text("| Result | pass |\n")
    with pytest.raises(SystemExit, match="no Device row"):
        gc.entries(path)


def test_a_model_a_record_names_must_be_in_models_yaml(root):
    record(root, "zha", "stop", device="Bulb (`NEW1`), firmware `1`")
    with pytest.raises(SystemExit, match="model 'NEW1' is not in docs/models.yaml"):
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
        (
            {"reports": [{"integration": "zha", "model": "P1", "item": "light", "issue": "https://example.com/1"}]},
            "issue URL",
        ),
        (
            {"reports": [{"integration": "zha", "model": "ZZ", "item": "light", "issue": f"{gc.ISSUE_URL}1"}]},
            "'ZZ' is not in",
        ),
        (
            {
                "reports": [
                    {
                        "integration": "zha",
                        "model": "P1",
                        "item": "light",
                        "worked": ["set_scene"],
                        "issue": f"{gc.ISSUE_URL}1",
                    }
                ]
            },
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
        ({"reports": [{"model": "P1", "item": "light", "issue": f"{gc.ISSUE_URL}1"}]}, "needs an integration"),
        (
            {"reports": [{"integration": "tuya", "model": "P1", "item": "light", "issue": f"{gc.ISSUE_URL}1"}]},
            "no integration 'tuya'",
        ),
        (
            {
                "reports": [
                    {"integration": "zha", "model": "P1", "item": "light", "worked": "x", "issue": f"{gc.ISSUE_URL}1"}
                ]
            },
            "worked must",
        ),
        ({"reports": [{**REPORT, "issue": f"{gc.ISSUE_URL}1", "firmware": ""}]}, "needs firmware"),
        (
            {"reports": [{"integration": "zha", "model": "P1", "item": "light", "issue": f"{gc.ISSUE_URL}1"}]},
            "needs firmware",
        ),
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
    assert "[predicted state](integrations/zha/test-records/stop-predicted_state.md)" in line
    assert line.endswith("[record](integrations/zha/test-records/stop.md) | |")


def test_an_experimental_adapter_or_a_failing_record_is_experimental(root):
    record(root, "zha", "stop")
    record(root, "hue", "stop", result="fail")
    assert "| Experimental (in RCs only) |" in gc.row("stop", adapter("zha", "stop", experimental=True), data())
    line = gc.row("stop", adapter("hue", "stop"), data())
    assert line == f"| `stop` | {gc.NO_RECORD} | none |  | |"


def test_only_a_fresh_passing_base_record_is_verified(root, monkeypatch):
    record(root, "zha", "stop-predicted_state")
    line = gc.row("stop", adapter("zha", "stop"), data())
    assert line.startswith(f"| `stop` | {gc.NO_RECORD} | `LTA009`")
    base = record(root, "zha", "stop")
    monkeypatch.setattr(gc, "staleness", lambda record, code: "changed since: x.py" if record == base else None)
    assert gc.row("stop", adapter("zha", "stop"), data()).startswith(f"| `stop` | {gc.STALE} | `LTA009`")


def test_reports_fill_the_reports_column_of_their_action(root):
    issue = f"{gc.ISSUE_URL}12"
    reports = [{**REPORT, "worked": ["turn_on_for"], "failed": ["stop"], "issue": issue}]
    loaded = data(FakeRegistry(adapter("zha", "turn_on_for"), adapter("zha", "stop")), reports=reports)
    assert gc.reports_cell("zha", "turn_on_for", loaded) == f"✅ [#12]({issue}) `P1`"
    assert gc.reports_cell("zha", "stop", loaded) == f"❌ [#12]({issue}) `P1`"
    assert gc.reports_cell("hue", "stop", loaded) == ""


def test_documented_capabilities_get_a_row_and_are_in_rcs_only_on_an_experimental_adapter(root):
    caps = verified("Switch") | documented("Light", "CCT")
    sibs = {"Light": "Switch", "CCT": "Switch"}
    released = adapter("zha", "stop", AdapterScope(capabilities=caps, siblings=sibs))
    flagged = adapter("zha", "stop", AdapterScope(experimental=True, capabilities=caps, siblings=sibs))
    assert gc.level_rows("stop", released, data()) == [
        "| `stop` | Documented | none (untested: Light, CCT components) | | |"
    ]
    [row] = gc.level_rows("stop", flagged, data())
    assert row.startswith("| `stop` | Experimental (in RCs only) |")
    assert gc.level_rows("stop", adapter("zha", "stop"), data()) == []


def test_reported_documented_and_experimental_items_each_get_a_row_strongest_first():
    scope = AdapterScope(
        domains=verified("light") | experimental("switch"),
        capabilities=reported("Light") | documented("CCT") | experimental("RGB"),
        siblings={"CCT": "Light"},
        fields=verified("brightness") | experimental("transition"),
    )
    assert gc.level_rows("turn_on_for", adapter("zha", "turn_on_for", scope), data()) == [
        "| `turn_on_for` | Reported | none (reported by users: Light components) | | |",
        "| `turn_on_for` | Documented | none (untested: CCT components) | | |",
        "| `turn_on_for` | Experimental | none (untested, behind Experimental features: "
        "switch entities; "
        "RGB components; transition fields) | | |",
    ]


def test_the_evidence_groups_by_integration_skips_unsupported_pairs_and_lists_what_doesnt_work(root):
    record(root, "zha", "stop")
    registry = FakeRegistry(adapter("zha", "stop"), adapter("hue", "lower_hue"))
    text = gc.evidence(registry, data(registry))
    assert text.index("### ZHA") < text.index("### Hue")  # the feature table's column order
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
        f"[Hue lamp]({URL}#hue-lamp) ✔",  # bulbs before plugs; two ids, one model
        f"[Plug]({URL}#plug) ✔",
        f"[native groups]({URL}#native-groups) ✔",
    ]
    assert card.render().splitlines()[:3] == [
        "**ZHA** (Zigbee 3.0) · maintained by [@jasonmx](https://github.com/jasonmx)",
        "",
        f"- 🟢 {' · '.join(card.lines['works'])}",
    ]


def test_a_card_leaves_out_flagged_adapters_and_failing_records(root):
    record(root, "zha", "stop")
    record(root, "zha", "turn_on_for", result="fail", device="Plug (`P1`), firmware `1`")
    scope = AdapterScope(
        experimental=True, domains=verified("light") | documented("switch"), siblings={"switch": "light"}
    )
    card = zha_card(adapter("zha", "stop", scope), adapter("zha", "turn_on_for"))
    assert card.lines["works"] == []
    assert card.lines["should"] == []


def test_a_model_only_users_report_shows_with_a_badge_per_report(root):
    issue = f"{gc.ISSUE_URL}7"
    reports = [{**REPORT, "worked": ["turn_on_for"], "issue": issue}]
    card = zha_card(adapter("zha", "turn_on_for"), reports=reports)
    assert card.lines["works"] == [f"[Plug]({URL}#plug) ([report]({issue}))"]


def test_a_report_on_a_flagged_adapter_stays_out_of_the_card(root):
    reports = [{**REPORT, "worked": ["turn_on_for"], "issue": f"{gc.ISSUE_URL}7"}]
    card = zha_card(adapter("zha", "turn_on_for", experimental=True), reports=reports)
    assert card.lines["works"] == []


def test_untested_classes_share_an_entry_per_feature_set_and_name_their_features(root):
    dimming = AdapterScope(capabilities=verified("Switch") | experimental("Light", "CCT"))
    timer = AdapterScope(
        domains=verified("light") | documented("switch"),
        capabilities=verified("Switch") | documented("Light"),
        siblings={"switch": "light", "Light": "Switch"},
    )
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
        f"- 🔴 {card.lines['no'][0]}",
    ]


def test_classes_of_one_section_say_their_shared_ending_once():
    led = f"{URL}#led"
    assert gc.merged(["CCT LED controllers", "RGB LED controllers"], led) == f"[LED controllers (CCT, RGB)]({led})"
    assert gc.merged(["dimmers"], f"{URL}#dimmers") == f"[dimmers]({URL}#dimmers)"
    # A phrase that is all ending has no prefix to list, so the phrases are listed whole.
    assert (
        gc.merged(["LED controllers", "RGB LED controllers"], led) == f"[LED controllers, RGB LED controllers]({led})"
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
    scope = AdapterScope(capabilities=verified("Switch") | documented("RGB"), siblings={"RGB": "Switch"})
    with pytest.raises(SystemExit, match="no entry for zha RGB, which a scope holds as Documented"):
        zha_card(adapter("zha", "turn_on_for", scope))


# DATA as files: the shared models.yaml, and a bundle per FakeRegistry integration.
BUNDLE = {
    "zha": {
        "column": "ZHA",
        "column_order": 1,
        "requires": "Zigbee 3.0",
        "capabilities": DATA["capabilities"]["zha"],
        "doesnt_work": [{"what": "Old plug", "reason": "No timer", "source": "https://x.y/z"}],
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
        (folder / "index.md").write_text(f"# {key}\n")
    return models


def write_files(root, registry, monkeypatch):
    page, readme = root / "page.md", root / "README.md"
    models = write_bundles(root, monkeypatch)
    page.write_text(PROSE + "## Evidence\n\n<!-- evidence:start -->\n<!-- evidence:end -->\n")
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


def test_a_card_linking_to_a_missing_heading_fails(root, monkeypatch):
    run = write_files(root, FakeRegistry(adapter("zha", "stop")), monkeypatch)
    page = root / "page.md"
    page.write_text(page.read_text().replace("### Dimmers\n", ""))
    with pytest.raises(SystemExit, match="no heading for Dimmers"):
        run([])


def test_a_heading_inside_the_evidence_block_does_not_count(root, monkeypatch):
    run = write_files(root, FakeRegistry(adapter("zha", "stop")), monkeypatch)
    page = root / "page.md"
    text = page.read_text().replace("### Old plug\n", "")
    page.write_text(text.replace("<!-- evidence:start -->\n", "<!-- evidence:start -->\n### Old plug\n"))
    with pytest.raises(SystemExit, match="no heading for Old plug"):
        run([])


def test_a_bundle_merges_in_as_its_integrations_own_and_its_page_holds_its_sections(root, monkeypatch):
    models = write_bundles(root, monkeypatch)
    (root / "docs" / "integrations" / "zha" / "index.md").write_text("# ZHA\n\n### Dimmers\n")
    data = gc.load(FakeRegistry(), models)
    assert data.requires == {"zha": "Zigbee 3.0"}
    assert data.doesnt_work[0]["integrations"] == ["zha"]
    # A section on the integration's page links there; the rest fall back to the shared page.
    assert data.url("zha", "Dimmers") == f"{gc.BLOB_URL}docs/integrations/zha/index.md#dimmers"
    assert data.url("zha", "Zigbee plugs") == f"{URL}#zigbee-plugs"
    assert data.url("hue", "Dimmers") == f"{URL}#dimmers"
    page = PROSE.replace("### Dimmers\n\n", "") + "<!-- evidence:start -->\n<!-- evidence:end -->\n"
    gc.check_sections(page, data)  # Dimmers is on the ZHA page
    with pytest.raises(SystemExit, match="no heading for Dimmers"):
        gc.check_sections(page, gc.load(FakeRegistry(), write_bundles(root, monkeypatch)))


def test_a_models_section_on_another_integrations_page_links_there(root, monkeypatch):
    models = write_bundles(root, monkeypatch)
    (root / "docs" / "integrations" / "zha" / "index.md").write_text("# ZHA\n\n### Hue lamp\n")
    data = gc.load(FakeRegistry(), models)
    # Every card showing the model links its heading on the ZHA page, which is where the check found it.
    assert data.url("hue", "Hue lamp") == f"{gc.BLOB_URL}docs/integrations/zha/index.md#hue-lamp"
    assert data.url("zha", "Hue lamp") == f"{gc.BLOB_URL}docs/integrations/zha/index.md#hue-lamp"
    page = PROSE.replace("### Hue lamp\n\n", "") + "<!-- evidence:start -->\n<!-- evidence:end -->\n"
    gc.check_sections(page, data)
    # A class's section isn't a model's: another integration's page doesn't hold it.
    (root / "docs" / "integrations" / "zha" / "index.md").write_text("# ZHA\n\n### Dimmers\n")
    assert gc.load(FakeRegistry(), models).url("hue", "Dimmers") == f"{URL}#dimmers"


def test_a_card_title_links_to_its_integrations_page(root, monkeypatch):
    data = gc.load(FakeRegistry(), write_bundles(root, monkeypatch))
    card = gc.card("zha", FakeRegistry(), [], data)
    assert card.render().startswith(f"**[ZHA]({gc.BLOB_URL}docs/integrations/zha/index.md)** (Zigbee 3.0)")


@pytest.mark.parametrize(
    ("bundles", "shared", "error"),
    [
        ({"zha": BUNDLE["zha"]}, None, "no docs/integrations/hue/devices.yaml; add the hue bundle"),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "models": []}},
            None,
            "hue/devices.yaml: unknown key models",
        ),
        (BUNDLE, {"models": [], "capabilities": {}}, "docs/models.yaml: unknown key capabilities"),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "reports": [{**REPORT, "issue": "x"}]}},
            None,
            "a reports entry is hue's own; drop its integration",
        ),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "doesnt_work": [DATA["doesnt_work"][0]]}},
            None,
            "a doesnt_work entry is hue's own; drop its integrations",
        ),
        (
            {**BUNDLE, "hue": {"column": "Hue", "column_order": 2, "reports": {"a": 1}}},
            None,
            "hue/devices.yaml: reports must",
        ),
    ],
)
def test_a_missing_bundle_or_a_misplaced_key_fails_naming_the_file(root, monkeypatch, bundles, shared, error):
    models = write_bundles(root, monkeypatch, bundles, shared)
    with pytest.raises(SystemExit, match=error):
        gc.load(FakeRegistry(), models)


def test_an_integration_without_a_user_page_fails(root, monkeypatch):
    models = write_bundles(root, monkeypatch)
    (root / "docs" / "integrations" / "hue" / "index.md").unlink()
    with pytest.raises(SystemExit, match="no docs/integrations/hue/index.md; add the hue bundle's user page"):
        gc.load(FakeRegistry(), models)


def test_the_checked_in_readme_and_page_match_the_real_records():
    """Both are generated: run the real check so local pytest catches a record or scope that drifts them."""
    assert gc.main(["--check"]) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"models": [{"name": "Lamp", "ids": ["L1"], "type": "bulb", "colour": "red"}]},
        {"capabilities": {"zha": {"switch": {"phrase": "plugs", "section": "Zigbee plugs", "level": 1}}}},
        {"doesnt_work": [{**DATA["doesnt_work"][0], "why": "x"}]},
        {"reports": [{**REPORT, "issue": f"{gc.ISSUE_URL}1", "works": ["turn_on_for"]}]},
    ],
)
def test_an_unknown_key_in_an_entry_is_an_error(changes):
    with pytest.raises(SystemExit, match="unknown key"):
        data(FakeRegistry(adapter("zha", "turn_on_for")), **changes)


def test_a_report_names_an_item_in_its_actions_scope():
    reports = [{**REPORT, "item": "Light", "worked": ["turn_on_for"], "issue": f"{gc.ISSUE_URL}1"}]
    with pytest.raises(SystemExit, match="has no item 'Light' in scope"):
        data(FakeRegistry(adapter("zha", "turn_on_for")), reports=reports)


@pytest.mark.parametrize("helper", [experimental, documented])
def test_a_working_report_on_an_item_left_below_reported_is_an_error(helper):
    scope = AdapterScope(
        domains=verified("light") | helper("switch"), siblings={"switch": "light"} if helper is documented else {}
    )
    reports = [{**REPORT, "item": "switch", "worked": ["turn_on_for"], "issue": f"{gc.ISSUE_URL}1"}]
    with pytest.raises(SystemExit, match="promote it to Level.REPORTED"):
        data(FakeRegistry(adapter("zha", "turn_on_for", scope)), reports=reports)


def test_a_report_on_a_scope_with_capabilities_must_name_a_capability():
    scope = AdapterScope(domains=verified("light"), capabilities=experimental("Light"))
    reports = [{**REPORT, "item": "light", "worked": ["turn_on_for"], "issue": f"{gc.ISSUE_URL}1"}]
    with pytest.raises(SystemExit, match="has no item 'light' in scope"):
        data(FakeRegistry(adapter("zha", "turn_on_for", scope)), reports=reports)


def test_a_failed_report_may_name_an_experimental_item():
    scope = AdapterScope(domains=verified("light") | experimental("switch"))
    reports = [{**REPORT, "item": "switch", "failed": ["turn_on_for"], "issue": f"{gc.ISSUE_URL}1"}]
    assert data(FakeRegistry(adapter("zha", "turn_on_for", scope)), reports=reports).reports


def test_a_reported_item_needs_a_working_report_unless_its_adapter_is_flagged():
    scope = AdapterScope(domains=verified("light") | reported("switch"))
    with pytest.raises(SystemExit, match="none says zha turn_on_for works on switch"):
        data(FakeRegistry(adapter("zha", "turn_on_for", scope)))
    flagged = AdapterScope(experimental=True, domains=reported("switch"))
    assert data(FakeRegistry(adapter("zha", "turn_on_for", flagged))).reports == []


def test_a_documented_row_holds_every_documented_item_with_its_reported_siblings_reports():
    issue = f"{gc.ISSUE_URL}9"
    scope = AdapterScope(
        capabilities=verified("Switch") | reported("RGB") | documented("Light", "CCT"),
        siblings={"Light": "Switch", "CCT": "RGB"},
    )
    reports = [
        report(item="RGB", worked=["stop"], issue=issue),
        report(item="Switch", worked=["stop"], issue=f"{gc.ISSUE_URL}8"),
    ]
    loaded = data(FakeRegistry(adapter("zha", "stop", scope)), reports=reports)
    # Only RGB's report: Light rides the Verified Switch, whose reports no Documented row needs.
    assert gc.level_rows("stop", adapter("zha", "stop", scope), loaded) == [
        f"| `stop` | Reported | none (reported by users: RGB components) | | ✅ [#9]({issue}) `P1` |",
        f"| `stop` | Documented | none (untested: Light, CCT components) | | ✅ [#9]({issue}) `P1` |",
    ]


def test_a_documented_class_on_a_reported_sibling_carries_its_reports(root):
    issue = f"{gc.ISSUE_URL}9"
    scope = AdapterScope(
        capabilities=reported("RGB") | verified("Switch") | documented("Light", "CCT"),
        siblings={"Light": "Switch", "CCT": "RGB"},
    )
    reports = [{**REPORT, "item": "RGB", "worked": ["turn_on_for"], "issue": issue}]
    card = zha_card(adapter("zha", "turn_on_for", scope), reports=reports)
    assert card.lines["works"] == [f"[Plug]({URL}#plug) ([report]({issue}))"]
    # Same features, different proof: two entries, the reported one linked.
    assert card.lines["should"] == [
        f"[dimmers]({URL}#dimmers): turn on with timer",
        f"[CCT controllers]({URL}#dimmers): turn on with timer ([report]({issue}))",
    ]


def test_the_legend_leads_the_cards_and_no_extension_mark_shows(root):
    registry = FakeRegistry(adapter("zha", "turn_on_for"))
    text = gc.cards(registry, data(registry))
    assert text.index(gc.CARDS_LEGEND) < text.index("**ZHA**")
    assert gc.CARDS_LEGEND == (
        "🟢 works · ✔ verified on automated rig · 🟡 should work: same call pattern as a tested device · "
        "🙋 testers wanted · 🔴 doesn't work · ⚠️ unmaintained: no one is fixing it; use at your own risk"
    )
    assert "👥" not in text
    assert text.index("Details per integration are in [docs/integrations.md](") < text.index("</details>")
    assert "🧩" not in text


def test_a_class_held_by_actions_of_different_proof_never_shares_a_bare_entry_with_a_report(root):
    issue = f"{gc.ISSUE_URL}9"
    on_verified = AdapterScope(capabilities=verified("Switch") | documented("Light"), siblings={"Light": "Switch"})
    on_reported = AdapterScope(capabilities=reported("RGB") | documented("Light"), siblings={"Light": "RGB"})
    reports = [report(item="RGB", worked=["turn_off_for"], issue=issue)]
    card = zha_card(
        adapter("zha", "turn_on_for", on_verified), adapter("zha", "turn_off_for", on_reported), reports=reports
    )
    assert card.lines["should"] == [
        f"[dimmers]({URL}#dimmers): turn on with timer",
        f"[dimmers]({URL}#dimmers): turn off with timer ([report]({issue}))",
    ]


def test_a_level_row_shows_the_reports_on_its_items_only():
    issue, other = f"{gc.ISSUE_URL}9", f"{gc.ISSUE_URL}10"
    scope = AdapterScope(
        capabilities=reported("RGB", "CCT") | verified("Switch") | documented("Light"),
        siblings={"Light": "RGB"},
    )
    reports = [
        report(item="RGB", worked=["stop"], issue=issue),
        report(item="CCT", worked=["stop"], issue=other),
        report(item="Switch", failed=["stop"], issue=f"{gc.ISSUE_URL}11"),
    ]
    registry = FakeRegistry(adapter("zha", "stop", scope))
    rows = gc.level_rows("stop", registry._adapters[0], data(registry, reports=reports))
    assert rows[0].endswith(f"| | ✅ [#9]({issue}) `P1`<br>✅ [#10]({other}) `P1` |")
    assert rows[1].endswith(f"| | ✅ [#9]({issue}) `P1` |")  # Light rides RGB


def test_a_reported_field_is_refused_until_a_report_can_name_one():
    scope = AdapterScope(domains=verified("light"), fields=reported("brightness"))
    with pytest.raises(SystemExit, match="field as Reported"):
        data(FakeRegistry(adapter("zha", "turn_on_for", scope)))


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"integrations": {"zha": {"requires": "x", "extra": 1}}}, "unknown key extra"),
        ({"capabilities": {"zha": None}}, "capabilities zha must be a mapping"),
        ({"capabilities": {"zha": ["switch"]}}, "capabilities zha must be a mapping"),
        ({"capabilities": ["zha"]}, "capabilities must be a mapping"),
        ({"models": {"a": 1}}, "models must be a list"),
        ({"capabilities": {"zha": {"switch": {"phrase": "p", "section": "S", "type": "plug"}}}}, "unknown key type"),
    ],
)
def test_devices_yaml_shapes_and_unknown_keys_fail_cleanly(changes, error):
    with pytest.raises(SystemExit, match=error):
        data(**changes)


def test_a_pipe_in_a_doesnt_work_entry_stays_in_its_cell(root):
    broken = [{"what": "A | B", "integrations": ["zha"], "reason": "x | y", "source": "https://x.y/z"}]
    registry = FakeRegistry(adapter("zha", "stop"))
    assert "| A \\| B | x \\| y | [source]" in gc.evidence(registry, data(registry, doesnt_work=broken))


def test_every_action_has_a_card_name_from_the_feature_table():
    """The cards' names come from the README table's rows, so an action can't be named on one and not the other."""
    assert set(gc.FEATURES) == {action.key for action in discover()}
    assert gc.FEATURES["raise_hue"] == "smooth hue"
    assert list(gc.FEATURES)[-1] == "stop" == gc.FEATURES["stop"]


ISSUE_REASON = f"{gc.ISSUE_URL}40"


def test_a_card_names_every_maintainer_with_a_profile_link(root):
    registry = FakeRegistry(adapter("hue", "stop"))
    card = gc.card("hue", registry, [adapter("hue", "stop")], data(registry))
    assert card.render().splitlines()[0] == (
        "**Hue** · maintained by [@jasonmx](https://github.com/jasonmx), [@other](https://github.com/other)"
    )


def test_a_card_marks_unmaintained_adapters_by_reason_and_leaves_out_flagged_ones(root):
    card = zha_card(
        adapter("zha", "turn_on_for", AdapterScope(unmaintained=ISSUE_REASON)),
        adapter("zha", "turn_off_for", AdapterScope(unmaintained=ISSUE_REASON)),
        adapter("zha", "stop", AdapterScope(unmaintained="the maintainer left")),
        adapter("zha", "set_scene", AdapterScope(experimental=True, unmaintained=ISSUE_REASON)),
        adapter("zha", "get_attributes"),
    )
    assert card.render().splitlines()[2:4] == [
        f"- [⚠️ Unmaintained]({ISSUE_REASON}): turn on with timer, turn off with timer",
        "- ⚠️ Unmaintained (the maintainer left): stop",
    ]


def test_an_unmaintained_entry_names_stop_beside_other_features(root):
    card = zha_card(
        adapter("zha", "turn_on_for", AdapterScope(unmaintained=ISSUE_REASON)),
        adapter("zha", "stop", AdapterScope(unmaintained=ISSUE_REASON)),
    )
    assert f"- [⚠️ Unmaintained]({ISSUE_REASON}): turn on with timer, stop" in card.render().splitlines()


def test_a_maintained_card_has_no_unmaintained_entry(root):
    assert gc.UNMAINTAINED not in zha_card(adapter("zha", "stop")).render()


def test_every_evidence_row_of_an_unmaintained_adapter_is_marked(root):
    record(root, "zha", "stop")
    scope = AdapterScope(domains=verified("light") | experimental("switch"), unmaintained="a | b")
    unmaintained = adapter("zha", "stop", scope)
    assert gc.row("stop", unmaintained, data()).startswith("| `stop` ⚠️ Unmaintained (a \\| b) | Verified |")
    [level_row] = gc.level_rows("stop", unmaintained, data())
    assert level_row.startswith("| `stop` ⚠️ Unmaintained (a \\| b) | Experimental |")
    linked = adapter("zha", "stop", AdapterScope(unmaintained=ISSUE_REASON))
    assert gc.row("stop", linked, data()).startswith(f"| `stop` [⚠️ Unmaintained]({ISSUE_REASON}) | Verified |")
