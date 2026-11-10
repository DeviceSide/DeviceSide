"""scripts/gen_features.py: icons from scopes, groups, the row intersection, NO_PATH, icon links, its failures, the
stale check."""

from types import SimpleNamespace

import pytest

from custom_components.deviceside.core.scope import AdapterScope, documented, experimental, reported, verified
from scripts import gen_features as gf

LIGHT = '<img src="https://raw.githubusercontent.com/jasonmx/DeviceSide/main/docs/icons/light.svg"'
SWITCH = "/switch.svg"
GROUP = "/group.svg"


class FakeRegistry:
    def __init__(self, *adapters, expand=()):
        self._adapters = adapters
        self.integrations = {key: SimpleNamespace(expand_group=(len if key in expand else None)) for key in gf.COLUMNS}

    def matrix(self):
        yield "stop", "hue", None
        for adapter in self._adapters:
            yield adapter.action, adapter.integration, adapter


def adapter(integration, action, **scope):
    return SimpleNamespace(integration=integration, action=action, scope=AdapterScope(**scope))


def every_row(integration="shelly", **scope):
    """An adapter for every action the table names, so no row fails as renamed."""
    actions = {action for *_, row in gf.FEATURES for action in row}
    return [adapter(integration, action, **scope) for action in sorted(actions)]


@pytest.fixture
def no_blockers(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {})


def headings():
    """A heading for every row's anchor, so a test README passes the anchor check."""
    return "".join(f"## {anchor.replace('-', ' ')}\n" for _, anchor, _, _ in gf.FEATURES)


def row(text, label):
    return next(line for line in text.splitlines() if line.startswith(f"| [{label}]"))


def cells(text, label):
    return row(text, label).split(" | ")[1:]


def test_domains_show_at_any_level_and_group_follows_native_groups_or_expand_group(no_blockers):
    registry = FakeRegistry(expand={"zha"})
    zha = adapter("zha", "stop", domains=verified("light"))
    z2m = adapter("zigbee2mqtt", "stop", domains=verified("light"), native_groups=True)
    matter = adapter("matter", "stop", domains=verified("switch") | documented("light"), siblings={"light": "switch"})
    reported_light = adapter("matter", "stop", domains=reported("light"))
    assert gf.keys(zha, registry) == {"light", "group"}
    assert gf.keys(z2m, registry) == {"light", "group"}
    assert gf.keys(matter, registry) == {"light", "switch"}
    assert gf.keys(reported_light, registry) == {"light"}


def test_an_experimental_domain_shows_no_icon_and_takes_its_group_with_it(no_blockers):
    """The table shows what works with the Experimental features option off."""
    registry = FakeRegistry(expand={"zha"})
    assert gf.keys(adapter("zha", "stop", domains=verified("light") | experimental("switch")), registry) == {
        "light",
        "group",
    }
    assert gf.keys(adapter("zha", "stop", domains=experimental("light")), registry) == set()


def test_capabilities_that_are_all_experimental_show_no_icon(no_blockers):
    registry = FakeRegistry()
    assert gf.keys(adapter("shelly", "stop", capabilities=experimental("Light", "CCT")), registry) == set()
    assert gf.keys(adapter("shelly", "stop", capabilities=verified("RGBCCT") | experimental("Light")), registry) == {
        "light"
    }


def test_a_group_needs_the_adapter_to_take_lights(no_blockers):
    registry = FakeRegistry(expand={"hue"})
    assert gf.keys(adapter("hue", "set_scene", domains=verified("scene")), registry) == {"scene"}


def test_a_cell_is_the_intersection_across_its_rows_actions(no_blockers):
    adapters = every_row(domains=verified("light", "switch"))
    # Smooth dimming needs stop too; a light-only stop narrows the cell to light.
    adapters = [a for a in adapters if a.action != "stop"] + [adapter("shelly", "stop", domains=verified("light"))]
    text = gf.generate(FakeRegistry(*adapters))
    dimming = cells(text, "Smooth dimming")[2]
    assert LIGHT in dimming and SWITCH not in dimming
    assert SWITCH in cells(text, "Turn on with timer")[2]


def test_a_missing_action_on_an_integration_empties_its_cell(no_blockers):
    adapters = every_row(domains=verified("light")) + [adapter("zha", "raise_brightness")]
    assert cells(gf.generate(FakeRegistry(*adapters)), "Smooth dimming")[0] == ""


def test_icons_keep_a_fixed_order_with_alt_and_title(no_blockers):
    text = gf.generate(FakeRegistry(*every_row(domains=verified("switch", "light"), native_groups=True)))
    cell = cells(text, "Get attributes")[2]
    assert cell.index(LIGHT) < cell.index(SWITCH) < cell.index(GROUP)
    assert 'alt="native group" title="native group"' in cell


def test_no_path_renders_one_prohibited_sign(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {("Turn off with timer", "hue"): ("light", "group")})
    cell = cells(gf.generate(FakeRegistry(*every_row())), "Turn off with timer")[3]
    assert cell.count("<img") == 1 and "/no.svg" in cell
    assert 'alt="light, native group: not possible"' in cell


def test_a_partly_blocked_cell_puts_the_prohibited_sign_after_built_icons(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {("Smooth dimming", "shelly"): ("switch",)})
    cell = cells(gf.generate(FakeRegistry(*every_row(domains=verified("light")))), "Smooth dimming")[2]
    assert cell.index(LIGHT) < cell.index("/no.svg")
    assert 'alt="switch: not possible"' in cell


def test_a_blocked_key_that_is_built_fails(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {("Turn off with timer", "shelly"): ("light",)})
    with pytest.raises(SystemExit, match="Turn off with timer on Shelly: light is built"):
        gf.generate(FakeRegistry(*every_row()))


def test_a_no_path_entry_naming_no_row_fails(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {("Teleport", "hue"): ("light",)})
    with pytest.raises(SystemExit, match="names no README row or column"):
        gf.generate(FakeRegistry(*every_row()))


def test_a_no_path_key_with_no_icon_fails(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {("Turn off with timer", "hue"): ("lights",)})
    with pytest.raises(SystemExit, match="no icon lights"):
        gf.generate(FakeRegistry(*every_row()))


def test_slugs_match_githubs_anchors():
    assert gf.slug(" Auto-off (aka inching) and auto-on") == "auto-off-aka-inching-and-auto-on"
    assert gf.slug("Set brightness, color temperature or color without turning on") == (
        "set-brightness-color-temperature-or-color-without-turning-on"
    )


def test_a_row_linking_to_no_heading_fails(tmp_path, no_blockers):
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n\n## Smooth dimming\n\n{gf.START}\n{gf.END}\n")
    with pytest.raises(SystemExit, match="no heading for .*#turn-on-with-timer"):
        gf.main(["--check"], FakeRegistry(*every_row()), readme)


def test_an_action_with_no_adapter_anywhere_fails(no_blockers):
    adapters = [a for a in every_row() if a.action != "set_scene"]
    with pytest.raises(SystemExit, match="no adapter anywhere for set_scene"):
        gf.generate(FakeRegistry(*adapters))


def test_an_integration_with_no_column_fails(no_blockers):
    with pytest.raises(SystemExit, match="no README column for integration tuya"):
        gf.generate(FakeRegistry(*every_row(), adapter("tuya", "stop")))


def test_the_readme_needs_its_markers(tmp_path, no_blockers):
    readme = tmp_path / "README.md"
    readme.write_text("# x\n")
    with pytest.raises(SystemExit, match="needs one"):
        gf.main(["--check"], FakeRegistry(*every_row()), readme)


def test_check_fails_on_a_stale_table_until_it_is_regenerated(tmp_path, capsys, no_blockers):
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n\n{gf.START}\nold\n{gf.END}\n\nafter\n{headings()}")
    registry = FakeRegistry(*every_row())
    assert gf.main(["--check"], registry, readme) == 1
    assert "out of date" in capsys.readouterr().err
    assert gf.main([], registry, readme) == 0
    assert gf.main(["--check"], registry, readme) == 0
    text = readme.read_text()
    assert text.startswith("# x\n\n<!-- features:start -->")
    assert text.endswith(f"<!-- features:end -->\n\nafter\n{headings()}")
    assert "old" not in text


def test_the_checked_in_readme_matches_the_real_adapters():
    """The table is generated from the scopes: run the real check so local pytest catches a scope that drifts it."""
    assert gf.main(["--check"]) == 0


def test_an_experimental_domain_shows_a_grey_icon_after_the_amber_ones(no_blockers):
    adapters = every_row(domains=verified("light") | experimental("switch"))
    cell = cells(gf.generate(FakeRegistry(*adapters)), "Get attributes")[2]
    assert cell.index(LIGHT) < cell.index("/switch-grey.svg")
    assert SWITCH not in cell and 'alt="switch: Experimental"' in cell


def test_all_experimental_capabilities_show_grey(no_blockers):
    adapters = every_row(capabilities=experimental("Light"))
    cell = cells(gf.generate(FakeRegistry(*adapters)), "Get attributes")[2]
    assert "/light-grey.svg" in cell and LIGHT not in cell


def test_a_blocked_key_that_is_built_only_with_experimental_on_fails(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {("Get attributes", "shelly"): ("switch",)})
    with pytest.raises(SystemExit, match="is built, so not blocked"):
        gf.generate(FakeRegistry(*every_row(domains=verified("light") | experimental("switch"))))


DOCS = "https://github.com/jasonmx/DeviceSide/blob/main/docs/"


def test_repeated_headings_get_githubs_numbered_anchors():
    text = "# Doc\n## Shelly\n### Get attributes\n## ZHA\n### Get attributes\n### Auto-off/on\n"
    found = gf.headings(text)
    assert found["Shelly"] == {"Shelly": "shelly", "Get attributes": "get-attributes"}
    assert found["ZHA"] == {"ZHA": "zha", "Get attributes": "get-attributes-1", "Auto-off/on": "auto-offon"}
    assert found[""] == {"Doc": "doc"}


def test_a_cells_icons_link_to_the_features_subsection_or_else_the_integrations_section(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {("Turn off with timer", "zha"): ("light",)})
    text = gf.generate(
        FakeRegistry(*every_row(domains=verified("light")), *every_row("matter", domains=verified("light")))
    )
    shelly = cells(text, "Get attributes")[2]
    assert shelly.startswith(f'<a href="{DOCS}integrations.md#get-attributes"><img ')
    matter = cells(text, "Get attributes")[4]
    assert f'href="{DOCS}integrations.md#get-attributes-' in matter
    blocked = cells(text, "Turn off with timer")[0]
    assert blocked.startswith(f'<a href="{DOCS}integrations.md#what-cant-be-done-and-why"><img ')
    assert "/no.svg" in blocked


def test_a_prohibited_sign_links_to_why_while_the_cells_other_icons_link_to_the_feature(monkeypatch):
    monkeypatch.setattr(gf, "NO_PATH", {("Smooth dimming", "shelly"): ("switch",)})
    cell = cells(gf.generate(FakeRegistry(*every_row(domains=verified("light")))), "Smooth dimming")[2]
    feature, why = (
        f'href="{DOCS}integrations.md#smooth-dimming"',
        f'href="{DOCS}integrations.md#what-cant-be-done-and-why"',
    )
    assert cell.index(feature) < cell.index("/light.svg") < cell.index(why) < cell.index("/no.svg")
    assert cell.count(why) == 1


def test_a_missing_why_section_fails(monkeypatch, no_blockers):
    monkeypatch.setattr(gf, "IMPOSSIBLE", "nowhere")
    with pytest.raises(SystemExit, match="no heading for #nowhere; fix IMPOSSIBLE"):
        gf.generate(FakeRegistry(*every_row()))


def test_an_integration_missing_from_the_integrations_doc_fails(monkeypatch, no_blockers):
    monkeypatch.setattr(gf, "SECTIONS", {**gf.SECTIONS, "hue": "Philips"})
    with pytest.raises(SystemExit, match="no section for hue"):
        gf.generate(FakeRegistry(*every_row()))


def test_every_legend_icon_links_to_its_heading(no_blockers):
    legend = gf.generate(FakeRegistry(*every_row())).split("\n")[-3]
    assert legend.count("<a href=") == len(gf.LEGEND)
    assert f'<a href="{DOCS}device-compatibility.md#levels-of-proof">' in legend
    assert '<a href="#set-scene-without-turning-on">' in legend


def test_a_legend_link_to_no_heading_fails(tmp_path, monkeypatch, no_blockers):
    monkeypatch.setattr(gf, "LEGEND", (("no", "not possible", "x", "docs/design.md", "nowhere"),))
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n\n{gf.START}\n{gf.END}\n{headings()}")
    with pytest.raises(SystemExit, match="docs/design.md has no heading for #nowhere"):
        gf.main(["--check"], FakeRegistry(*every_row()), readme)
