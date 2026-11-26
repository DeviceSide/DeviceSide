"""The coverage view in Settings: each cell is the dispatcher's own decision (dispatcher.judge) on the entity, the rows
are the entities a call could reach, and the counts, the legend and the Labs line read the cells."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.homeassistant.scene import DATA_PLATFORM as SCENE_PLATFORM
from homeassistant.components.homeassistant.scene import SceneConfig
from homeassistant.core import State
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside import coverage
from custom_components.deviceside.actions import discover
from custom_components.deviceside.core.dispatcher import Outcome, judge
from custom_components.deviceside.core.models import TimedRequest
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.core.scope import (
    AdapterScope,
    NoKnownMethod,
    NotBuilt,
    OwnCall,
    Unplaced,
    documented,
    labs,
    verified,
)
from custom_components.deviceside.coverage import COLUMNS, Cell, Coverage, Mark, Row

from .conftest import allow_labs, call, refusal
from .fakes.fake_integration import LIMITS, FakeSetAttributes, FakeTurnOffFor, FakeTurnOnFor
from .fakes.scripted import ScriptedAdapter
from .fixtures.fake import add_fake_entity, add_fake_native_group, add_ha_group, fake_config_entry

pytestmark = pytest.mark.usefixtures("setup_integration")

TIMER_OFF = "turn off with timer"
TIMER_ON = "turn on with timer"
SWITCH = '<ha-icon icon="mdi:toggle-switch-variant"></ha-icon> '  # the domain's default icon
ANYWHERE = frozenset({"light", "switch", "scene"})
# A class at each level, one with no known method and one not built yet (as test_dispatcher's GATED).
GATED = AdapterScope(
    domains=verified("light", "switch"),
    duration=LIMITS,
    capabilities=verified("A") | documented("B") | labs("C"),
    no_known_method={"D": NoKnownMethod("Plug D", "It never switches on", "https://example.com/d")},
    not_built={"E": NotBuilt("It ignores the timer", "https://example.com/e")},
    native_groups=True,
)


def by_name(hass, target):
    """A class per entity from its object id's first letter: switch.a is class "A"; switch.pending_a is "A", not yet
    placed."""
    name = target.entity_id.partition(".")[2]
    if name.startswith("pending_"):
        return Unplaced(name.removeprefix("pending_")[0].upper())
    return name[0].upper()


@pytest.fixture
def fake(hass):
    return fake_config_entry(hass)


@pytest.fixture
def classed(hass, setup_integration):
    """The fake integration naming classes A to E from the object id, its adapters' scopes holding them."""
    registry = get_runtime(hass).registry
    info = registry.integrations["fake"]
    registry.integrations["fake"] = replace(info, capability=by_name, classes=dict.fromkeys("ABCDE", ANYWHERE))
    with (
        patch.object(FakeTurnOffFor, "scope", GATED),
        patch.object(FakeTurnOnFor, "scope", GATED),
        patch.object(FakeSetAttributes, "scope", replace(GATED, duration=None, fields=verified("brightness"))),
    ):
        yield
    registry.integrations["fake"] = info


def target_of(hass, entity_id):
    return resolve(hass, get_runtime(hass).registry, entity_id)


def cell_of(hass, entity_id, feature=TIMER_OFF):
    column = next(column for column in COLUMNS if column.features == (feature,))
    return coverage.cell(hass, get_runtime(hass).registry, target_of(hass, entity_id), column)


@pytest.mark.usefixtures("classed")
@pytest.mark.parametrize(
    ("entity_id", "cell", "reason"),
    [
        pytest.param("switch.a", Cell(Mark.VERIFIED), None, id="verified"),
        pytest.param("switch.b", Cell(Mark.DOCUMENTED), None, id="documented"),
        pytest.param("switch.c", Cell(Mark.LABS), "labs_off", id="labs"),
        pytest.param("switch.d", None, "no_known_method", id="refused"),
        pytest.param("switch.e", None, "not_built", id="not_built"),
    ],
)
async def test_a_cell_is_what_a_call_on_the_entity_does(hass, fake, reset_script, entity_id, cell, reason):
    add_fake_entity(hass, fake, entity_id)
    allow_labs(hass, False)

    assert cell_of(hass, entity_id) == cell
    # The same decision a call makes: the dispatcher's own, which runs it, or refuses it where the cell is empty.
    registry = get_runtime(hass).registry
    gate = judge(
        hass, registry, registry.adapter("turn_off_for", "fake"), target_of(hass, entity_id), TimedRequest(5), False
    )
    data = {"entity_id": entity_id, "duration": 5}
    if reason is None:
        assert gate.outcome is Outcome.RUNS
        assert (await call(hass, "turn_off_for", data))[entity_id]["status"] == "sent"
    else:
        assert gate.reason == reason
        assert await refusal(hass, "turn_off_for", data) == reason


@pytest.mark.usefixtures("classed")
async def test_a_group_whose_member_takes_its_own_call_shows_the_members_mark(hass, fake):
    """A call on the group runs the member (the dispatcher's fallback), so the cell is the member's, not own_call's."""
    add_fake_entity(hass, fake, "switch.e")
    add_fake_native_group(hass, fake, "switch.fake_group", ["switch.e"])
    own = OwnCall(AsyncMock(), LIMITS)
    scope = replace(GATED, capabilities=verified("E"), not_built={}, own_calls={"E": own})

    with patch.object(FakeTurnOffFor, "scope", scope):
        assert cell_of(hass, "switch.fake_group") == Cell(Mark.VERIFIED)


@pytest.mark.usefixtures("classed")
@pytest.mark.parametrize(
    ("entity_id", "on_for", "expected"),
    [
        pytest.param("switch.a", {"domains": labs("switch")}, Cell(Mark.LABS), id="a Labs one makes it Labs"),
        pytest.param(
            "switch.d", {"capabilities": verified("D"), "no_known_method": {}}, None, id="one refused leaves it empty"
        ),
        pytest.param(
            "switch.e", {"capabilities": verified("E"), "not_built": {}}, None, id="one not built leaves it empty"
        ),
    ],
)
async def test_a_feature_riding_several_actions_takes_its_weakest(hass, fake, entity_id, on_for, expected):
    add_fake_entity(hass, fake, entity_id)
    column = coverage.Column(("both timers",), "Timers")

    with (
        patch.dict(coverage.FEATURE_ACTIONS, {"both timers": ("turn_on_for", "turn_off_for")}),
        patch.object(FakeTurnOnFor, "scope", replace(GATED, **on_for)),
    ):
        assert coverage.cell(hass, get_runtime(hass).registry, target_of(hass, entity_id), column) == expected


@pytest.mark.parametrize(
    ("saturation", "hue", "expected"),
    [
        pytest.param(Cell(Mark.VERIFIED), Cell(Mark.LABS), Cell(Mark.LABS), id="the weaker of the two"),
        pytest.param(None, Cell(Mark.DOCUMENTED), Cell(Mark.DOCUMENTED), id="no saturation shows the hue"),
        pytest.param(Cell(Mark.LABS), None, Cell(Mark.LABS), id="no hue (refused, say) shows the saturation"),
        pytest.param(None, None, None, id="both empty is empty"),
    ],
)
def test_smooth_color_takes_the_weaker_of_saturation_and_hue(hass, saturation, hue, expected):
    column = next(column for column in COLUMNS if column.heading == "Smooth color")
    by_feature = {"smooth saturation": saturation, "smooth hue": hue}

    with patch.object(coverage, "_feature_cell", lambda _hass, _registry, _target, feature: by_feature[feature]):
        assert coverage.cell(hass, None, None, column) == expected


def test_every_action_has_a_minimal_request(hass):
    for action in discover():
        request = coverage.minimal_request(hass, action)
        if action.key == "set_attributes":
            assert request.fields_present() == {"brightness"}
        if isinstance(request, TimedRequest):
            assert request.duration_s == 5


# The rows


@pytest.fixture
def household(hass, fake):
    """Lights and switches of each kind of row: one of each level, a refused one and one not built (no cell, so
    no row), a native group over a Verified and a Documented member, and each kind that is left out."""
    registry = er.async_get(hass)
    for entity_id in ("switch.a", "switch.b", "switch.c", "switch.d", "switch.e", "light.a_lamp"):
        add_fake_entity(hass, fake, entity_id)
    for entity_id, changes in (
        ("switch.a_config", {"entity_category": er.EntityCategory.CONFIG}),
        ("switch.a_disabled", {"disabled_by": er.RegistryEntryDisabler.USER}),
        ("switch.a_hidden", {"hidden_by": er.RegistryEntryHider.USER}),
    ):
        add_fake_entity(hass, fake, entity_id)
        registry.async_update_entity(entity_id, **changes)
    add_fake_entity(hass, fake, "switch.pending_a")
    add_fake_native_group(hass, fake, "switch.fake_group", ["switch.a", "switch.b"])
    # An entity no integration DeviceSide has serves.
    registry.async_get_or_create("light", "elsewhere", "x", suggested_object_id="elsewhere")
    return registry


@pytest.mark.usefixtures("classed", "household")
async def test_the_rows_are_the_entities_a_call_could_reach(hass):
    found = await coverage.collect(hass)

    assert [(row.entity_id, row.group) for row in found.rows] == [
        ("switch.a", False),
        ("light.a_lamp", False),
        ("switch.b", False),
        ("switch.c", False),
        ("switch.fake_group", True),
    ]
    by_id = {row.entity_id: row for row in found.rows}
    assert {heading: cell.mark for heading, cell in by_id["switch.a"].cells.items()} == {
        "Timed on": Mark.VERIFIED,
        "Timed off": Mark.VERIFIED,
    }
    assert {heading: cell.mark for heading, cell in by_id["light.a_lamp"].cells.items()} == {
        "Flash-free turn-on": Mark.VERIFIED,
        "Timed on": Mark.VERIFIED,
        "Timed off": Mark.VERIFIED,
    }
    # A group takes its weakest member's.
    assert by_id["switch.fake_group"].cells["Timed off"] == Cell(Mark.DOCUMENTED)
    # An entity whose only outcomes are refusals (d) or not built (e) has no row.
    assert "switch.d" not in by_id
    assert "switch.e" not in by_id


@pytest.mark.usefixtures("classed", "household")
async def test_a_zha_style_group_is_left_out(hass, monkeypatch):
    monkeypatch.setattr(coverage, "_GROUPS_ON_COORDINATOR", frozenset({"fake"}))

    assert "switch.fake_group" not in [row.entity_id for row in (await coverage.collect(hass)).rows]


@pytest.mark.usefixtures("classed", "household")
async def test_integrations_follow_the_cards_order_and_those_on_no_card_come_last(hass, fake, monkeypatch):
    add_fake_entity(hass, fake, "switch.a_second", identifier="special-1")

    async def order() -> list[str]:
        rows = (await coverage.collect(hass)).rows
        return list(dict.fromkeys(row.integration for row in rows))

    monkeypatch.setattr(coverage, "CARD_ORDER", ("fake_special", "fake"))
    assert await order() == ["fake_special", "fake"]
    monkeypatch.setattr(coverage, "CARD_ORDER", ("fake", "fake_special"))
    assert await order() == ["fake", "fake_special"]
    monkeypatch.setattr(coverage, "CARD_ORDER", ("fake_special",))
    assert await order() == ["fake_special", "fake"]


@pytest.mark.usefixtures("classed", "household")
async def test_the_counts_and_the_labs_line_read_the_cells(hass):
    found = await coverage.collect(hass)

    # Verified and Documented count: a, b, the group and the light.
    assert found.devices_now == 4
    # Labs: switch.c's two features, on one device.
    assert found.devices_in_labs == 1


@pytest.mark.usefixtures("classed", "household")
async def test_the_table_has_a_column_per_feature_and_a_blank_where_it_does_not_run(hass):
    found = await coverage.collect(hass)

    text = coverage.table(hass, found)

    assert text.splitlines()[:3] == [
        "| | <center>Smooth dimming</center> | <center>Smooth color</center> | "
        "<center>Flash\u2011free turn\u2011on</center> | <center>Timed on</center> | "
        "<center>Timed off</center> | <center>Auto off/on</center> |",
        "|---|:-:|:-:|:-:|:-:|:-:|:-:|",
        "| **Fake** | | | | | | |",
    ]
    assert f"| {SWITCH}a |  |  |  | 🟢 | 🟢 |  |" in text
    assert f"| {SWITCH}d |" not in text
    assert f"| {SWITCH}c |  |  |  | ⚪ | ⚪ |  |" in text
    assert f"| {SWITCH}fake group <small>Group</small> |  |  |  | 🟡 | 🟡 |  |" in text
    assert "🔴" not in text


async def test_a_name_with_markup_is_shown_as_it_is(hass, fake):
    add_fake_entity(hass, fake, "light.odd", attributes={"friendly_name": "A | <b>lamp</b> *1*"})

    assert coverage._plain("A | <b>lamp</b> *1*") == "A \\| &lt;b&gt;lamp&lt;/b&gt; \\*1\\*"


def test_the_legend_entries_are_shared_with_the_readme_whose_labs_pointer_differs():
    """scripts/gen_compat.py renders these entries too, with its own pointer to where Labs is turned on."""
    assert coverage.legend_entries("Turn on Labs in Configure > Settings to try it") == [
        (coverage.Mark.VERIFIED, "🟢 Verified: works, tested on a real device"),
        (
            coverage.Mark.DOCUMENTED,
            "🟡 Documented: should work, uses a verified device's call or a standard call",
        ),
        (
            coverage.Mark.LABS,
            "⚪ Labs: built, but not yet shown to work. Turn on Labs in Configure > Settings to try it",
        ),
    ]


def test_the_legend_explains_each_mark():
    assert coverage.legend().split("<br>") == [
        "🟢 Verified: works, tested on a real device",
        "🟡 Documented: should work, uses a verified device's call or a standard call",
        "⚪ Labs: built, but not yet shown to work. Turn on Labs below to try it",
    ]


# The Settings step


async def open_coverage(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "settings"})


@pytest.mark.usefixtures("classed", "household")
async def test_settings_shows_the_matrix_with_the_options_under_it(hass, setup_integration):
    result = await open_coverage(hass, setup_integration)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "settings"
    holders = result["description_placeholders"]
    assert holders["coverage"] == (
        "DeviceSide works with 4 of your devices.\n\n"
        f"{coverage.legend()}\n\n{coverage.table(hass, await coverage.collect(hass))}"
    )
    assert f"| {SWITCH}c |" in holders["coverage"]
    assert result["data_schema"]({}) == {"predicted_state": True, "z2m_color_modes": True, "labs": False}
    assert [str(key) for key in result["data_schema"].schema] == ["labs", "predicted_state", "z2m_color_modes"]
    strings = json.loads((Path(coverage.__file__).parent / "translations" / "en.json").read_text())["options"]
    step = strings["step"]["settings"]
    assert step["description"] == "{coverage}"  # tags in a translation string break HA's frontend formatter
    assert step["data_description"]["labs"].format(**holders) == (
        "Turn on Labs: adds features on 1 of your devices. "
        "Try out new integrations, actions and action options, and unproven devices. "
        "Labs features may misbehave, change or be withdrawn without notice. "
        'Please report how they go with the "Report a device test result or bug" form.'
    )
    assert "coverage" not in strings["step"]["init"]["menu_options"]


@pytest.mark.usefixtures("classed", "household")
async def test_submitting_saves_the_options_and_reloads_only_when_one_changed(hass, setup_integration):
    saved = {"predicted_state": True, "z2m_color_modes": True}
    hass.config_entries.async_update_entry(setup_integration, options={**saved, "labs": False})
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await open_coverage(hass, setup_integration)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {**saved, "labs": False})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        reload.assert_not_called()

        result = await open_coverage(hass, setup_integration)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {**saved, "labs": True})
        reload.assert_called_once_with(setup_integration.entry_id)
    assert setup_integration.options == {**saved, "labs": True}

    result = await open_coverage(hass, setup_integration)
    assert result["data_schema"]({}) == {**saved, "labs": True}  # the current option is the default


@pytest.fixture
def listing(hass, setup_integration):
    """The fake integration still waiting to report its devices, until the test sets the event."""
    event = asyncio.Event()
    registry = get_runtime(hass).registry
    info = registry.integrations["fake"]
    registry.integrations["fake"] = replace(
        info, capability_ready=lambda hass: None if event.is_set() else event.wait()
    )
    yield event
    registry.integrations["fake"] = info


async def finish_progress(hass, flow_id):
    """Let the progress task finish, then take the step HA runs next (the view), as the frontend does."""
    await hass.async_block_till_done()
    return await hass.config_entries.options.async_configure(flow_id)


@pytest.mark.usefixtures("classed", "household")
async def test_settings_waits_while_an_integration_is_listing_its_devices(hass, setup_integration, listing):
    result = await open_coverage(hass, setup_integration)

    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "waiting_for_devices"
    assert result["step_id"] == "settings"
    strings = json.loads((Path(coverage.__file__).parent / "translations" / "en.json").read_text())
    assert strings["options"]["progress"]["waiting_for_devices"] == "Waiting for Zigbee2MQTT to list its devices."

    listing.set()
    result = await finish_progress(hass, result["flow_id"])
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "settings"
    assert "works with 4 of your devices" in result["description_placeholders"]["coverage"]


@pytest.mark.usefixtures("classed", "household", "listing")
async def test_settings_waits_no_longer_than_the_bound_for_a_device_list_that_never_comes(
    hass, setup_integration, monkeypatch
):
    monkeypatch.setattr(coverage, "WAIT_S", 0.05)
    result = await open_coverage(hass, setup_integration)
    assert result["type"] is FlowResultType.SHOW_PROGRESS

    await asyncio.sleep(0.1)
    result = await finish_progress(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM  # what it has
    assert "works with 4 of your devices" in result["description_placeholders"]["coverage"]


def test_the_wait_is_ten_seconds():
    assert coverage.WAIT_S == 10


# Icons


async def icons_of(hass, entity_id):
    entry = er.async_get(hass).async_get(entity_id)
    return (await coverage._Icons.load(hass, {entry.platform})).of(er.async_get(hass).async_get(entity_id))


async def test_the_icon_is_the_entrys_own_else_the_originals_else_the_domains_default(hass, fake):
    registry = er.async_get(hass)
    for entity_id in ("light.chosen", "light.original", "light.plain", "switch.plain", "switch.outlet"):
        add_fake_entity(hass, fake, entity_id)
    registry.async_update_entity("light.chosen", icon="mdi:desk-lamp")
    registry.async_update_entity("light.original", original_icon="mdi:floor-lamp")
    registry.async_update_entity("light.chosen", original_icon="mdi:floor-lamp")
    registry.async_update_entity("switch.outlet", device_class="outlet")

    assert await icons_of(hass, "light.chosen") == "mdi:desk-lamp"
    assert await icons_of(hass, "light.original") == "mdi:floor-lamp"
    assert await icons_of(hass, "light.plain") == "mdi:lightbulb"
    assert await icons_of(hass, "switch.plain") == "mdi:toggle-switch-variant"
    assert await icons_of(hass, "switch.outlet") == "mdi:power-plug"


def test_an_integrations_icon_for_the_translation_key_comes_before_the_domains():
    icons = coverage._Icons(
        {"hue": {"light": {"room": {"default": "mdi:sofa"}}}}, {"light": {"_": {"default": "mdi:lightbulb"}}}
    )
    keyed = SimpleNamespace(
        platform="hue",
        domain="light",
        icon=None,
        original_icon=None,
        translation_key="room",
        device_class=None,
        original_device_class=None,
    )
    plain = SimpleNamespace(**{**vars(keyed), "translation_key": None})

    assert (icons.of(keyed), icons.of(plain)) == ("mdi:sofa", "mdi:lightbulb")


async def test_with_nothing_in_labs_the_labs_description_is_the_warning_alone(hass, setup_integration, fake):
    add_fake_entity(hass, fake, "switch.lonely")  # no class named, no Labs item anywhere
    result = await open_coverage(hass, setup_integration)

    holders = result["description_placeholders"]
    assert holders["labs_adds"] == ""
    strings = json.loads((Path(coverage.__file__).parent / "translations" / "en.json").read_text())
    text = strings["options"]["step"]["settings"]["data_description"]["labs"].format(**holders)
    assert text.startswith("Try out new integrations")


@pytest.mark.usefixtures("classed", "household")
async def test_labs_adds_is_said_only_while_labs_is_off(hass, setup_integration):
    off = await open_coverage(hass, setup_integration)
    assert off["description_placeholders"]["labs_adds"] == "Turn on Labs: adds features on 1 of your devices. "
    hass.config_entries.async_update_entry(setup_integration, options={"labs": True})

    on = await open_coverage(hass, setup_integration)

    assert on["description_placeholders"]["labs_adds"] == ""
    assert on["description_placeholders"]["coverage"]  # the Labs cells are still shown


# The scenes


SCENE_GATED = AdapterScope(
    domains=verified("scene"),
    capabilities=verified("A") | documented("B") | labs("C"),
    no_known_method={"D": NoKnownMethod("Smart scene", "It has no fixed settings", "https://example.com/d")},
    not_built={"E": NotBuilt("It is not built", "https://example.com/e")},
)


class FakeSetScene(ScriptedAdapter):
    action = "set_scene"
    integration = "fake"
    scope = SCENE_GATED


@pytest.fixture
def bridge_scenes(hass, classed):
    """The fake with a set_scene adapter, as Hue's, whose scenes are classed A to E from their object id."""
    registry = get_runtime(hass).registry
    adapter = FakeSetScene()
    adapter.kind = registry.adapter("set_attributes", "fake").kind
    registry._adapters[("set_scene", "fake")] = adapter
    yield
    del registry._adapters[("set_scene", "fake")]


def ha_scene(hass, entity_id: str, states: dict[str, dict | None]) -> str:
    """A Home Assistant scene with no registry entry, as a YAML scene with no id is: each light on with the attributes
    given, or off for None."""
    platform = hass.data.get(SCENE_PLATFORM) or SimpleNamespace(entities={})
    platform.entities[entity_id] = SimpleNamespace(
        scene_config=SceneConfig(
            None,
            entity_id,
            None,
            {light: State(light, "off" if a is None else "on", a or {}) for light, a in states.items()},
        )
    )
    hass.data[SCENE_PLATFORM] = platform
    hass.states.async_set(entity_id, "unknown")
    return entity_id


BRIGHT = {"brightness": 255}


async def marks(hass) -> list[Mark]:
    return sorted((await coverage.collect(hass)).scenes, key=coverage._WEAKEST.index)


@pytest.fixture
def lamps(hass, fake):
    """A light of each class: A is Verified, B Documented, C Labs, D refused, E not built."""
    for letter in "abcde":
        add_fake_entity(hass, fake, f"light.{letter}_lamp")


@pytest.mark.usefixtures("classed", "lamps")
async def test_a_scene_of_verified_lights_is_verified(hass):
    ha_scene(hass, "scene.evening", {"light.a_lamp": BRIGHT})

    assert await marks(hass) == [Mark.VERIFIED]
    assert er.async_get(hass).async_get("scene.evening") is None  # a YAML scene with no id has no registry entry


@pytest.mark.usefixtures("classed", "lamps")
@pytest.mark.parametrize(
    ("lights", "mark"),
    [
        pytest.param(("a", "b"), Mark.DOCUMENTED, id="documented"),
        pytest.param(("a", "b", "c"), Mark.LABS, id="labs, the weakest of three"),
        pytest.param(("b", "c"), Mark.LABS, id="labs under documented"),
        pytest.param(("b",), Mark.DOCUMENTED, id="all alike"),
    ],
)
async def test_the_mark_is_the_weakest_light(hass, lights, mark):
    ha_scene(hass, "scene.movie", {f"light.{letter}_lamp": BRIGHT for letter in lights})

    assert await marks(hass) == [mark]


@pytest.mark.usefixtures("classed", "lamps")
async def test_lights_a_call_would_skip_lower_no_mark(hass):
    elsewhere = er.async_get(hass).async_get_or_create("light", "elsewhere", "x", suggested_object_id="elsewhere")
    ha_scene(
        hass,
        "scene.party",
        {"light.a_lamp": BRIGHT, "light.d_lamp": BRIGHT, "light.e_lamp": BRIGHT, elsewhere.entity_id: BRIGHT},
    )

    # Refused, not built and unresolved lights lower no mark.
    assert await marks(hass) == [Mark.VERIFIED]


@pytest.mark.usefixtures("classed", "lamps")
async def test_a_light_with_a_missing_color_lowers_no_mark(hass):
    ha_scene(hass, "scene.color", {"light.a_lamp": BRIGHT})
    hass.data[SCENE_PLATFORM].entities["scene.color"].scene_config.states["light.b_lamp"] = State(
        "light.b_lamp",
        "on",
        {"brightness": 255, "color_mode": "hs"},  # names a color mode it holds no color for
    )

    assert await marks(hass) == [Mark.VERIFIED]


@pytest.mark.usefixtures("classed", "lamps")
async def test_lights_held_off_or_with_nothing_to_write_carry_no_mark(hass):
    ha_scene(hass, "scene.relax", {"light.a_lamp": BRIGHT, "light.b_lamp": None, "light.c_lamp": {}})

    assert await marks(hass) == [Mark.VERIFIED]  # c is on with nothing to write, b is off


@pytest.mark.usefixtures("classed", "lamps")
@pytest.mark.parametrize(
    "states",
    [
        pytest.param({"light.d_lamp": BRIGHT, "light.e_lamp": BRIGHT}, id="refused and not built"),
        pytest.param({"light.a_lamp": None, "light.b_lamp": None}, id="all held off"),
        pytest.param({"light.a_lamp": {}}, id="nothing to write"),
        pytest.param({}, id="no lights"),
    ],
)
async def test_a_scene_with_no_light_served_has_no_mark(hass, states):
    ha_scene(hass, "scene.dark", states)

    assert await marks(hass) == []


@pytest.mark.usefixtures("classed", "lamps")
async def test_an_ha_group_in_a_scene_is_judged_by_its_members(hass):
    add_ha_group(hass, "light.pair", ["light.a_lamp", "light.b_lamp"])
    ha_scene(hass, "scene.pair", {"light.pair": BRIGHT})

    assert await marks(hass) == [Mark.DOCUMENTED]


@pytest.mark.usefixtures("classed", "lamps")
async def test_a_field_the_adapter_holds_in_labs_puts_the_scene_in_labs(hass):
    """The scene's own write is judged for each light, so a color held in Labs is Labs, with Labs off."""
    ha_scene(hass, "scene.glow", {"light.a_lamp": {"color_mode": "hs", "hs_color": [10, 50]}})
    scope = replace(GATED, duration=None, fields=verified("brightness") | labs("hs_color"))

    with patch.object(FakeSetAttributes, "scope", scope):
        assert await marks(hass) == [Mark.LABS]


@pytest.mark.usefixtures("bridge_scenes")
async def test_a_bridge_scene_is_judged_on_its_set_scene_adapter(hass, fake):
    for name in ("a_x", "b_x", "c_x", "d_x", "e_x", "pending_a"):
        add_fake_entity(hass, fake, f"scene.{name}", state="scening")

    # D is a smart scene (no known method), E is not built, and pending_a is still being placed: no mark.
    assert await marks(hass) == [Mark.LABS, Mark.DOCUMENTED, Mark.VERIFIED]


@pytest.mark.usefixtures("bridge_scenes", "lamps")
async def test_a_disabled_or_hidden_scene_entry_is_left_out(hass, fake):
    for name, changes in (
        ("a_off", {"disabled_by": er.RegistryEntryDisabler.USER}),
        ("a_hidden", {"hidden_by": er.RegistryEntryHider.USER}),
    ):
        add_fake_entity(hass, fake, f"scene.{name}")
        er.async_get(hass).async_update_entity(f"scene.{name}", **changes)
    er.async_get(hass).async_get_or_create("scene", "homeassistant", "x", suggested_object_id="ha_off")
    er.async_get(hass).async_update_entity("scene.ha_off", disabled_by=er.RegistryEntryDisabler.USER)
    ha_scene(hass, "scene.ha_off", {"light.a_lamp": BRIGHT})
    ha_scene(hass, "scene.ha_on", {"light.a_lamp": BRIGHT})

    assert await marks(hass) == [Mark.VERIFIED]


def device_row():
    return Row("switch.a", "a", None, False, "fake", "device", {"Timed on": Cell(Mark.VERIFIED)})


@pytest.mark.parametrize(
    ("device_rows", "scenes", "line"),
    [
        pytest.param((), (), "DeviceSide works with 0 of your devices.", id="none"),
        pytest.param((device_row(),), (), "DeviceSide works with 1 of your devices.", id="no scene ends at devices"),
        pytest.param(
            (device_row(),),
            (Mark.VERIFIED,),
            "DeviceSide works with 1 of your devices and 1 of your scenes.",
            id="one scene",
        ),
        pytest.param(
            (),
            (Mark.VERIFIED, Mark.DOCUMENTED, Mark.LABS),
            "DeviceSide works with 0 of your devices and 2 of your scenes.",
            id="several, Labs not counted",
        ),
        pytest.param((), (Mark.LABS,), "DeviceSide works with 0 of your devices.", id="only Labs"),
    ],
)
def test_the_count_line_counts_the_scenes_that_run_now(hass, device_rows, scenes, line):
    assert coverage.section(hass, Coverage(device_rows, scenes)).startswith(line + "\n\n")
