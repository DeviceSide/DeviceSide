"""ZHA set_attributes: MoveTo commands with the ExecuteIfOff override, one light at a time, then update_entity."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import probatio
import pytest
from homeassistant.core import Context, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.util.color import color_xy_to_hs

from custom_components.deviceside.const import ADAPTER_BACKSTOP_S, DOMAIN
from custom_components.deviceside.integrations.zha import set_attributes as adapter
from custom_components.deviceside.integrations.zha import zcl

from ...conftest import advance, call, refusal, result, wall_clock_now
from ...fixtures.zha import IEEE, add_zha_entity, zha_entry, zha_group

pytestmark = pytest.mark.usefixtures("setup_production")

SENT = {"status": "sent", "integration": "zha"}
OVERRIDE = {"transition_time": 4, "options_mask": 1, "options_override": 1}
ONOFF = {"supported_color_modes": ["onoff"]}
DIMMABLE = {"supported_color_modes": ["brightness"]}
CT = {"supported_color_modes": ["color_temp"], "min_color_temp_kelvin": 2202, "max_color_temp_kelvin": 6535}
COLOR = {**CT, "supported_color_modes": ["color_temp", "xy"]}
HS = {"supported_color_modes": ["hs"]}


@pytest.fixture(autouse=True)
def level_read(monkeypatch):
    """zcl.read_attributes, reading CurrentLevel 127 (50 %) unless a test sets its own."""
    read = AsyncMock(return_value={zcl.CURRENT_LEVEL: 127})
    monkeypatch.setattr(zcl, "read_attributes", read)
    return read


@pytest.fixture(autouse=True)
def no_fade_wait(monkeypatch):
    """The refresh's wait for the commands' fade, off so tests don't sleep; the tests of it set their own."""
    monkeypatch.setattr(adapter, "FADE_WAIT_S", 0.0)


def sent(commands) -> list[tuple[int, int, dict]]:
    """Each command as (cluster, command, params), after checking it went to the bulb's in cluster as a server one."""
    for command in commands:
        assert {k: command.data[k] for k in ("ieee", "endpoint_id", "cluster_type", "command_type")} == {
            "ieee": IEEE,
            "endpoint_id": 11,
            "cluster_type": "in",
            "command_type": "server",
        }
    return [(command.data["cluster_id"], command.data["command"], command.data["params"]) for command in commands]


def level(value: int) -> tuple[int, int, dict]:
    return 0x0008, 0x00, {"level": value, **OVERRIDE}


def mireds(value: int) -> tuple[int, int, dict]:
    return 0x0300, 0x0A, {"color_temp_mireds": value, **OVERRIDE}


def xy(x: float, y: float) -> tuple[int, int, dict]:
    return 0x0300, 0x07, {"color_x": round(x * 65535), "color_y": round(y * 65535), **OVERRIDE}


def bulb(hass, attributes: dict, entity_id: str = "light.bulb") -> str:
    return add_zha_entity(hass, zha_entry(hass), entity_id, attributes=attributes)


@pytest.mark.parametrize(
    ("data", "attributes", "expected"),
    [
        pytest.param({"brightness": 40}, DIMMABLE, [level(102)], id="brightness"),
        pytest.param(
            {"brightness": 40, "color_temp_kelvin": 2700}, CT, [level(102), mireds(370)], id="brightness_and_ct"
        ),
        pytest.param({"xy_color": [0.369, 0.445]}, COLOR, [xy(0.369, 0.445)], id="xy"),
    ],
)
async def test_writes_with_the_override(hass, commands, refreshes, data, attributes, expected):
    bulb(hass, attributes)

    assert await call(hass, "set_attributes", {"entity_id": "light.bulb", **data}) == {"light.bulb": SENT}
    assert sent(commands) == expected
    assert [refresh.data for refresh in refreshes] == [{"entity_id": "light.bulb"}]


async def test_color_on_an_hs_only_bulb_sends_hue_and_saturation(hass, commands, refreshes):
    bulb(hass, HS)

    await call(hass, "set_attributes", {"entity_id": "light.bulb", "xy_color": [0.369, 0.445]})

    hue, saturation = color_xy_to_hs(0.369, 0.445)
    assert sent(commands) == [
        (0x0300, 0x06, {"hue": round(hue * 254 / 360), "saturation": round(saturation * 254 / 100), **OVERRIDE})
    ]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param({"min_brightness": 60}, [level(152)], id="min_raises"),
        pytest.param({"max_brightness": 30}, [level(76)], id="max_lowers"),
    ],
)
async def test_limits_clamp_the_current_level(hass, commands, refreshes, level_read, data, expected):
    bulb(hass, DIMMABLE)

    assert await call(hass, "set_attributes", {"entity_id": "light.bulb", **data}) == {"light.bulb": SENT}
    assert sent(commands) == expected
    level_read.assert_awaited_once_with(hass, (IEEE, 11), 0x0008, (0x0000,))


async def test_within_limits_sends_nothing(hass, commands, refreshes):
    bulb(hass, DIMMABLE)

    data = {"entity_id": "light.bulb", "min_brightness": 20, "max_brightness": 80}
    response = await call(hass, "set_attributes", data)

    assert response == {"light.bulb": result("zha", "unchanged", detail="within_limits")}
    assert not commands
    assert not refreshes


async def test_a_field_the_light_cant_take_is_dropped(hass, commands, refreshes):
    bulb(hass, CT)

    response = await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40, "hs_color": [30, 80]})

    assert response == {"light.bulb": {**SENT, "detail": "fields_dropped"}}
    assert sent(commands) == [level(102)]


@pytest.mark.parametrize(
    ("attributes", "data"),
    [
        pytest.param(ONOFF, {"min_brightness": 40}, id="onoff_light_limits"),
        pytest.param(DIMMABLE, {"rgb_color": [255, 0, 0], "color_temp_kelvin": 2700}, id="every_field_dropped"),
    ],
)
async def test_a_light_that_takes_no_field_is_unchanged(hass, commands, refreshes, level_read, attributes, data):
    bulb(hass, attributes)

    response = await call(hass, "set_attributes", {"entity_id": "light.bulb", **data})

    assert response == {"light.bulb": result("zha", "unchanged", detail="fields_dropped")}
    assert not commands
    level_read.assert_not_awaited()


async def test_a_failed_refresh_still_reports_sent(hass, commands):
    bulb(hass, DIMMABLE)

    async def handler(service: ServiceCall) -> None:
        raise ValueError("entity gone")

    hass.services.async_register("homeassistant", "update_entity", handler)

    assert await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40}) == {"light.bulb": SENT}


async def test_a_command_error_rejects_that_light(hass, refreshes):
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.gone", ieee="00:00:00:00:00:00:00:01", attributes=DIMMABLE)
    add_zha_entity(hass, entry, "light.bulb", attributes=DIMMABLE)

    # A plain handler, since a mock service can't raise.
    async def handler(service: ServiceCall) -> None:
        if service.data["ieee"] != IEEE:
            raise ValueError(f"Device with IEEE {service.data['ieee']} not found")

    hass.services.async_register("zha", "issue_zigbee_cluster_command", handler)

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "set_attributes", {"entity_id": ["light.bulb", "light.gone"], "brightness": 40})

    assert raised.value.translation_key == "targets_failed"
    assert raised.value.translation_placeholders["summary"] == "light.gone: error"
    # Its first command failed, so nothing landed to refresh.
    assert [refresh.data["entity_id"] for refresh in refreshes] == ["light.bulb"]


async def test_a_later_command_failing_still_refreshes_the_light(hass, refreshes):
    bulb(hass, COLOR)

    async def handler(service: ServiceCall) -> None:
        if service.data["command"] == zcl.MOVE_TO_COLOR_TEMP:
            raise ValueError("no answer")

    hass.services.async_register("zha", "issue_zigbee_cluster_command", handler)

    with pytest.raises(HomeAssistantError):
        await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40, "color_temp_kelvin": 2700})

    assert [refresh.data["entity_id"] for refresh in refreshes] == ["light.bulb"]


def test_the_refresh_budget_is_inside_the_adapters_backstop():
    assert adapter.REFRESH_BUDGET_S < ADAPTER_BACKSTOP_S


async def test_a_refresh_past_its_budget_is_given_up_and_the_results_kept(hass, commands, monkeypatch, caplog):
    monkeypatch.setattr(adapter, "REFRESH_BUDGET_S", 0.05)
    bulb(hass, DIMMABLE)

    async def hang(service: ServiceCall) -> None:
        await asyncio.sleep(10)

    hass.services.async_register("homeassistant", "update_entity", hang)

    response = await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40})

    assert response["light.bulb"]["status"] == "sent"
    assert "ran past" in caplog.text


async def test_the_refreshes_wait_outside_the_concurrency_slots(hass):
    """Three lights under max_concurrency=2: every light's commands go before any refresh's wait holds a slot."""
    entry = zha_entry(hass)
    events: list[str] = []
    for n in range(3):
        add_zha_entity(hass, entry, f"light.l{n}", ieee=f"00:00:00:00:00:00:00:0{n}", attributes=DIMMABLE)

    async def command(service: ServiceCall) -> None:
        events.append("command")

    async def update(service: ServiceCall) -> None:
        events.append("refresh")

    hass.services.async_register("zha", "issue_zigbee_cluster_command", command)
    hass.services.async_register("homeassistant", "update_entity", update)

    await call(hass, "set_attributes", {"entity_id": ["light.l0", "light.l1", "light.l2"], "brightness": 40})

    assert events == ["command"] * 3 + ["refresh"] * 3


async def test_a_failed_level_read_rejects_that_light(hass, commands, level_read):
    bulb(hass, DIMMABLE)
    level_read.side_effect = LookupError("Attribute 0x0000 not read")

    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, "set_attributes", {"entity_id": "light.bulb", "min_brightness": 60})

    assert raised.value.translation_placeholders["summary"] == "light.bulb: error"
    assert not commands


async def test_non_admin_caller_is_refused_by_zha(hass, refreshes, hass_read_only_user):
    bulb(hass, DIMMABLE)
    calls: list[ServiceCall] = []

    async def handler(service: ServiceCall) -> None:
        calls.append(service)

    schema = probatio.Schema({}, extra=probatio.ALLOW_EXTRA)
    async_register_admin_service(hass, "zha", "issue_zigbee_cluster_command", handler, schema)

    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            DOMAIN,
            "set_attributes",
            {"entity_id": "light.bulb", "brightness": 40},
            blocking=True,
            return_response=True,
            context=Context(user_id=hass_read_only_user.id),
        )

    assert raised.value.translation_placeholders["summary"] == "light.bulb: admin_required"
    assert not calls


async def test_entity_without_a_light_unique_id_is_not_addressable(hass, commands):
    add_zha_entity(hass, zha_entry(hass), "light.quirk", unique_id=f"{IEEE}-1-6-child_lock", attributes=DIMMABLE)

    assert await refusal(hass, "set_attributes", {"entity_id": "light.quirk", "brightness": 40}) == "not_addressable"


async def test_a_model_that_drops_writes_while_off_is_refused(hass, commands):
    bulb(hass, DIMMABLE)
    device_id = er.async_get(hass).async_get("light.bulb").device_id
    dr.async_get(hass).async_update_device(device_id, model="E11-G13")

    data = {"entity_id": "light.bulb", "brightness": 40}
    assert await refusal(hass, "set_attributes", data) == "execute_if_off_unsupported"
    assert not commands


A, B = "00:00:00:00:00:00:00:0a", "00:00:00:00:00:00:00:0b"


async def test_a_zha_group_writes_each_member(hass, zha_groups, commands, refreshes):
    zha_light_group(hass, zha_groups)

    response = await call(hass, "set_attributes", {"entity_id": "light.zha_group", "brightness": 40})

    assert response == {"light.a": SENT, "light.b": SENT}
    assert sorted(command.data["ieee"] for command in commands) == [A, B]
    assert sorted(refresh.data["entity_id"] for refresh in refreshes) == ["light.a", "light.b"]


@pytest.fixture
def zha_lights(monkeypatch):
    """The zha library's light behind each HA entity, by entity_id, reached as HA's entity_data.entity."""
    loaded: dict[str, SimpleNamespace] = {}

    def ha_entity(hass, entity_id):
        return SimpleNamespace(entity_data=SimpleNamespace(entity=loaded[entity_id])) if entity_id in loaded else None

    monkeypatch.setattr(adapter, "ha_entity", ha_entity)
    return loaded


async def test_a_level_write_replaces_the_level_zha_kept_for_the_next_on(hass, commands, refreshes, zha_lights):
    """The library kept 254 from before an off with a transition; the next plain on would send it."""
    bulb(hass, DIMMABLE)
    zha_lights["light.bulb"] = SimpleNamespace(_off_brightness=254)

    await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40})

    assert zha_lights["light.bulb"]._off_brightness == 102


async def test_the_level_is_kept_when_a_later_color_command_fails(hass, refreshes, zha_lights):
    bulb(hass, COLOR)
    zha_lights["light.bulb"] = SimpleNamespace(_off_brightness=254)

    async def handler(service: ServiceCall) -> None:
        if service.data["command"] == zcl.MOVE_TO_COLOR_TEMP:
            raise ValueError("no answer")

    hass.services.async_register("zha", "issue_zigbee_cluster_command", handler)

    with pytest.raises(HomeAssistantError):
        await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40, "color_temp_kelvin": 2700})

    assert zha_lights["light.bulb"]._off_brightness == 102


@pytest.mark.parametrize(
    ("kept", "data", "attributes", "after"),
    [
        pytest.param(None, {"brightness": 40}, DIMMABLE, None, id="nothing_kept"),
        pytest.param(254, {"color_temp_kelvin": 2700}, CT, 254, id="no_level_written"),
    ],
)
async def test_the_kept_level_is_left(hass, commands, refreshes, zha_lights, kept, data, attributes, after):
    bulb(hass, attributes)
    zha_lights["light.bulb"] = SimpleNamespace(_off_brightness=kept)

    await call(hass, "set_attributes", {"entity_id": "light.bulb", **data})

    assert zha_lights["light.bulb"]._off_brightness == after


async def test_an_unloaded_entity_still_writes(hass, commands, refreshes, zha_lights):
    bulb(hass, DIMMABLE)

    assert await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40}) == {"light.bulb": SENT}


def zha_light_group(hass, zha_groups):
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.zha_group", unique_id="light_zha_group_0x0002", attributes=DIMMABLE)
    add_zha_entity(hass, entry, "light.a", ieee=A, attributes=DIMMABLE)
    add_zha_entity(hass, entry, "light.b", ieee=B, attributes=DIMMABLE)
    zha_groups[2] = zha_group((A, 11), (B, 11))


async def test_a_group_write_replaces_the_groups_kept_level_and_its_members(
    hass, zha_groups, commands, refreshes, zha_lights
):
    zha_light_group(hass, zha_groups)
    for entity_id in ("light.zha_group", "light.a", "light.b"):
        zha_lights[entity_id] = SimpleNamespace(_off_brightness=254)

    await call(hass, "set_attributes", {"entity_id": "light.zha_group", "brightness": 40})

    assert {entity_id: light._off_brightness for entity_id, light in zha_lights.items()} == dict.fromkeys(
        ("light.zha_group", "light.a", "light.b"), 102
    )


async def test_a_group_clamp_leaves_the_groups_kept_level(hass, zha_groups, commands, refreshes, zha_lights):
    zha_light_group(hass, zha_groups)
    zha_lights["light.zha_group"] = SimpleNamespace(_off_brightness=254)
    zha_lights["light.a"] = SimpleNamespace(_off_brightness=254)

    await call(hass, "set_attributes", {"entity_id": "light.zha_group", "max_brightness": 40})

    assert zha_lights["light.zha_group"]._off_brightness == 254
    assert zha_lights["light.a"]._off_brightness == 102  # clamped from the CurrentLevel read of 127


class FlaggedLight:
    """A zha light whose transition flag is up until set down, or until `up_for_reads` looks at it have passed."""

    _off_brightness = None

    def __init__(self) -> None:
        self.flag = True
        self.up_for_reads: int | None = None

    @property
    def is_transitioning(self) -> bool:
        if self.up_for_reads is not None:
            if self.up_for_reads <= 0:
                self.flag = False
            self.up_for_reads -= 1
        return self.flag

    @is_transitioning.setter
    def is_transitioning(self, value: bool) -> None:
        self.flag = value
        self.up_for_reads = None


@pytest.fixture
def flagged_refreshes(hass):
    """update_entity calls, each recording whether zha's transition flag was up on light.bulb when it ran."""
    seen: list[bool] = []
    light = FlaggedLight()

    async def handler(service: ServiceCall) -> None:
        seen.append(light.is_transitioning)

    hass.services.async_register("homeassistant", "update_entity", handler)
    return light, seen


async def test_the_refresh_waits_for_zhas_transition_flag(hass, monkeypatch, commands, zha_lights, flagged_refreshes):
    """After an HA turn_off, zha skips update_entity until its flag clears; refreshing sooner leaves HA's color old."""
    monkeypatch.setattr(adapter, "TRANSITION_POLL_S", 0)
    light, seen = flagged_refreshes
    bulb(hass, CT)
    zha_lights["light.bulb"] = light
    light.up_for_reads = 5  # clears itself after five looks, with no clock involved

    response = await call(hass, "set_attributes", {"entity_id": "light.bulb", "color_temp_kelvin": 2700})

    assert response == {"light.bulb": SENT}
    assert seen == [False]


async def test_a_flag_past_the_wait_refreshes_again_once_it_clears(
    hass, monkeypatch, commands, zha_lights, flagged_refreshes
):
    """A long off fade keeps the flag up past the wait: refresh then anyway, and again once the flag clears."""
    monkeypatch.setattr(adapter, "TRANSITION_WAIT_S", 0)  # gives up at its first look, whatever the clock says
    light, seen = flagged_refreshes
    bulb(hass, CT)
    zha_lights["light.bulb"] = light
    start = wall_clock_now()

    await call(hass, "set_attributes", {"entity_id": "light.bulb", "color_temp_kelvin": 2700})
    await advance(hass, start, 1)  # still up: checked again later
    assert seen == [True]
    light.is_transitioning = False
    await advance(hass, start, 2)

    assert seen == [True, False]


async def test_the_late_refresh_gives_up_waiting_at_its_limit(
    hass, monkeypatch, commands, zha_lights, flagged_refreshes
):
    monkeypatch.setattr(adapter, "TRANSITION_WAIT_S", 0)  # gives up at its first look, whatever the clock says
    monkeypatch.setattr(adapter, "LATE_REFRESH_LIMIT_S", 0.0)
    light, seen = flagged_refreshes
    bulb(hass, CT)
    zha_lights["light.bulb"] = light
    start = wall_clock_now()

    await call(hass, "set_attributes", {"entity_id": "light.bulb", "color_temp_kelvin": 2700})
    await advance(hass, start, 1)
    await advance(hass, start, 2)

    assert seen == [True, True]


async def test_the_kept_level_is_replaced_before_the_refresh_waits(hass, commands, zha_lights):
    """A plain on during the refresh's wait must already find the written level."""
    bulb(hass, DIMMABLE)
    zha_lights["light.bulb"] = light = SimpleNamespace(_off_brightness=254, is_transitioning=False)
    kept_at_refresh: list[int] = []

    async def handler(service: ServiceCall) -> None:
        kept_at_refresh.append(light._off_brightness)

    hass.services.async_register("homeassistant", "update_entity", handler)

    await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40})

    assert kept_at_refresh == [102]


@pytest.fixture
def timed_refreshes(hass):
    """update_entity calls, each as the loop time it ran at."""
    times: list[float] = []

    async def handler(service: ServiceCall) -> None:
        times.append(hass.loop.time())

    hass.services.async_register("homeassistant", "update_entity", handler)
    return times


async def test_the_refresh_waits_out_the_fade_when_the_flag_is_clear(hass, monkeypatch, commands, timed_refreshes):
    """A read inside the commands' fade keeps a mid-fade color temperature, as zha applies no color reports."""
    monkeypatch.setattr(adapter, "FADE_WAIT_S", 0.05)
    bulb(hass, CT)
    start = hass.loop.time()

    await call(hass, "set_attributes", {"entity_id": "light.bulb", "color_temp_kelvin": 2700})

    assert timed_refreshes[0] - start >= 0.05


async def test_the_flag_wait_counts_toward_the_fade_wait(
    hass, monkeypatch, commands, zha_lights, flagged_refreshes, timed_refreshes
):
    """A flag that already held the refresh longer than the fade wait adds nothing to it."""
    monkeypatch.setattr(adapter, "FADE_WAIT_S", 0.05)
    monkeypatch.setattr(adapter, "TRANSITION_POLL_S", 0.01)
    light, _seen = flagged_refreshes
    bulb(hass, CT)
    zha_lights["light.bulb"] = light
    light.up_for_reads = 12  # 12 polls of 10 ms, however slow the loop: past the 50 ms fade wait
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def spy(delay, *args):
        sleeps.append(delay)
        await real_sleep(delay, *args)

    monkeypatch.setattr(asyncio, "sleep", spy)

    await call(hass, "set_attributes", {"entity_id": "light.bulb", "color_temp_kelvin": 2700})

    assert len(timed_refreshes) >= 1
    assert set(sleeps) == {0.01}  # only polls: no further sleep for the fade


async def test_a_second_refresh_follows_and_a_later_call_replaces_it(hass, commands, refreshes):
    bulb(hass, CT)
    start = wall_clock_now()
    data = {"entity_id": "light.bulb", "color_temp_kelvin": 2700}

    await call(hass, "set_attributes", data)
    assert len(refreshes) == 1
    await advance(hass, start, 2)
    assert len(refreshes) == 2

    await call(hass, "set_attributes", data)  # refresh 3, and a second one scheduled
    await call(hass, "set_attributes", data)  # refresh 4, replacing that one
    await advance(hass, start, 4)

    assert len(refreshes) == 5  # only one second refresh ran for the two calls


@pytest.fixture
def missing(monkeypatch) -> set[str]:
    """The adapter's warned-once set, fresh for the test."""
    fresh: set[str] = set()
    monkeypatch.setattr(adapter, "_missing", fresh)
    return fresh


async def test_an_entity_without_zhas_library_light_is_warned_about_once(
    hass, commands, refreshes, monkeypatch, missing, caplog
):
    monkeypatch.setattr(adapter, "ha_entity", lambda hass, entity_id: SimpleNamespace())
    bulb(hass, DIMMABLE)

    for _ in range(2):
        await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40})

    assert caplog.text.count("entity_data.entity is missing") == 1


async def test_a_library_light_without_the_transition_flag_is_warned_about_once(
    hass, commands, refreshes, zha_lights, missing, caplog
):
    bulb(hass, DIMMABLE)
    zha_lights["light.bulb"] = SimpleNamespace(_off_brightness=None)

    for _ in range(2):
        await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40})

    assert caplog.text.count("SimpleNamespace.is_transitioning is missing") == 1
    assert len(refreshes) == 2


async def test_an_unloaded_entity_is_not_warned_about(hass, commands, refreshes, zha_lights, missing, caplog):
    bulb(hass, DIMMABLE)

    await call(hass, "set_attributes", {"entity_id": "light.bulb", "brightness": 40})

    assert "is missing" not in caplog.text
