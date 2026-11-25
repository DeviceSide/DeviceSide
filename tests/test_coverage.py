"""The Device coverage view: each cell is the dispatcher's own decision (dispatcher.judge) on the entity, the rows are
the entities a call could reach, and the counts, the legend and the Labs line read the cells."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
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
from custom_components.deviceside.coverage import COLUMNS, Cell, Mark

from .conftest import allow_labs, call, refusal
from .fakes.fake_integration import LIMITS, FakeSetAttributes, FakeTurnOffFor, FakeTurnOnFor
from .fixtures.fake import add_fake_entity, add_fake_native_group, fake_config_entry

pytestmark = pytest.mark.usefixtures("setup_integration")

TIMER_OFF = "turn off with timer"
TIMER_ON = "turn on with timer"
SWITCH = ' <ha-icon icon="mdi:toggle-switch-variant"></ha-icon>'  # the domain's default icon
ANYWHERE = frozenset({"light", "switch"})
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
        "Set while off": Mark.VERIFIED,
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

    # Verified and Documented count, a, b, the group (two features each), the light (three).
    assert (found.features_now, found.devices_now) == (9, 4)
    # Labs: switch.c's two features, on one device.
    assert (found.features_in_labs, found.devices_in_labs) == (2, 1)


@pytest.mark.usefixtures("classed", "household")
async def test_the_table_has_a_column_per_feature_and_a_blank_where_it_does_not_run(hass):
    found = await coverage.collect(hass)

    text = coverage.table(hass, found)

    assert text.splitlines()[:3] == [
        "| | " + " | ".join(column.heading for column in COLUMNS) + " |",
        "|---|:-:|:-:|:-:|:-:|:-:|:-:|",
        "| **Fake** | | | | | | |",
    ]
    assert f"| a{SWITCH} |  |  |  | 🟢 | 🟢 |  |" in text
    assert f"| d{SWITCH} |" not in text
    assert f"| c{SWITCH} |  |  |  | ⚪ | ⚪ |  |" in text
    assert f"| fake group{SWITCH} <small>Group</small> |  |  |  | 🟡 | 🟡 |  |" in text
    assert "🔴" not in text


async def test_a_name_with_markup_is_shown_as_it_is(hass, fake):
    add_fake_entity(hass, fake, "light.odd", attributes={"friendly_name": "A | <b>lamp</b> *1*"})

    assert coverage._plain("A | <b>lamp</b> *1*") == "A \\| &lt;b&gt;lamp&lt;/b&gt; \\*1\\*"


def test_the_legend_explains_each_mark():
    assert coverage.legend().split("\n\n") == [
        "🟢 Verified: works, tested on a real device",
        "🟡 Documented: should work, same call pattern as a tested device",
        "⚪ Labs: not yet passed on a real device, or held back to soak. Turn on Labs below to use it",
    ]


# The Configure step


async def open_coverage(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "coverage"})


@pytest.mark.usefixtures("classed", "household")
async def test_the_step_shows_the_matrix_with_the_labs_checkbox_under_it(hass, setup_integration):
    result = await open_coverage(hass, setup_integration)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "coverage_view"
    holders = result["description_placeholders"]
    assert (holders["features"], holders["devices"]) == ("9", "4")
    assert holders["legend"] == coverage.legend()
    assert f"| c{SWITCH} |" in holders["table"]
    assert result["data_schema"]({}) == {"labs": False}
    strings = json.loads((Path(coverage.__file__).parent / "translations" / "en.json").read_text())["options"]
    step = strings["step"]["coverage_view"]
    assert step["description"].format(**holders).startswith("DeviceSide runs 9 features on 4 of your devices now.")
    assert step["data_description"]["labs"].format(**holders) == (
        "Turn on Labs: adds 2 features on 1 devices. "
        "Labs features may misbehave, change or be withdrawn without notice."
    )
    assert strings["step"]["init"]["menu_options"]["coverage"] == "Device coverage"


@pytest.mark.usefixtures("classed", "household")
async def test_submitting_saves_labs_and_reloads_only_when_it_changed(hass, setup_integration):
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await open_coverage(hass, setup_integration)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"labs": False})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        reload.assert_not_called()

        result = await open_coverage(hass, setup_integration)
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"labs": True})
        reload.assert_called_once_with(setup_integration.entry_id)
    assert setup_integration.options == {"labs": True}

    result = await open_coverage(hass, setup_integration)
    assert result["data_schema"]({}) == {"labs": True}  # the current option is the default


async def test_the_other_options_survive_a_save_here(hass, setup_integration):
    hass.config_entries.async_update_entry(setup_integration, options={"predicted_state": False, "labs": False})
    result = await open_coverage(hass, setup_integration)

    await hass.config_entries.options.async_configure(result["flow_id"], {"labs": True})

    assert setup_integration.options == {"predicted_state": False, "labs": True}


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
async def test_the_step_waits_while_an_integration_is_listing_its_devices(hass, setup_integration, listing):
    result = await open_coverage(hass, setup_integration)

    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "waiting_for_devices"
    assert result["step_id"] == "coverage"
    strings = json.loads((Path(coverage.__file__).parent / "translations" / "en.json").read_text())
    assert strings["options"]["progress"]["waiting_for_devices"] == "Waiting for Zigbee2MQTT to list its devices."

    listing.set()
    result = await finish_progress(hass, result["flow_id"])
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "coverage_view"


@pytest.mark.usefixtures("classed", "household", "listing")
async def test_the_step_waits_no_longer_than_the_bound_for_a_device_list_that_never_comes(
    hass, setup_integration, monkeypatch
):
    monkeypatch.setattr(coverage, "WAIT_S", 0.05)
    result = await open_coverage(hass, setup_integration)
    assert result["type"] is FlowResultType.SHOW_PROGRESS

    await asyncio.sleep(0.1)
    result = await finish_progress(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM  # what it has
    assert result["description_placeholders"]["features"] == "9"


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
    text = strings["options"]["step"]["coverage_view"]["data_description"]["labs"].format(**holders)
    assert text == "Labs features may misbehave, change or be withdrawn without notice."
