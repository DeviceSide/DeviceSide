import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.util.color import color_hs_to_xy

from custom_components.deviceside.integrations.hue.transition_cache import transition_cache

from ...fixtures.hue import HueBridge, add_hue_entity, add_hue_group, hue_entry, light_action


class Clock:
    """A transition cache clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(hass) -> Clock:
    clock = Clock()
    transition_cache(hass).clock = clock
    return clock


@pytest.fixture
def bridge() -> HueBridge:
    return HueBridge()


@pytest.fixture(autouse=True)
async def unload_mock_hue_entries(hass):
    """Mark mocked hue entries not loaded before teardown, so HA doesn't run the real hue unload on them."""
    yield
    for entry in hass.config_entries.async_entries("hue"):
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


async def setup_room(hass, bridge):
    """Two lights on at 20 % in room-1, with a scene; the HA entities core's hue integration would make."""
    bridge.light("one", on=True, brightness=20.0)
    bridge.light("two", on=True, brightness=20.0)
    bridge.room("1", ["one", "two"], brightness=20.0)
    bridge.scene("scene-1", [light_action("one", on={"on": True})])
    entry = await hue_entry(hass, bridge)
    members = [
        add_hue_entity(hass, entry, f"light.{light_id}", light_id, state="on", attributes={"brightness": 51})
        for light_id in ("one", "two")
    ]
    add_hue_group(hass, entry, "light.room", "1", members)
    hass.states.async_set("light.room", "on", {"is_hue_group": True, "entity_id": members, "brightness": 51})
    add_hue_entity(hass, entry, "scene.relax", "scene-1")
    return entry


def light_event(light_id: str, *, brightness: float | None = None, on: bool | None = None, **extra) -> dict:
    event: dict = {"id": light_id, "type": "light", **extra}
    if brightness is not None:
        event["dimming"] = {"brightness": brightness}
    if on is not None:
        event["on"] = {"on": on}
    return event


SENT = {"status": "sent", "integration": "hue"}


def percent(value: float) -> int:
    """HA's 0-255 brightness for a Hue percent; multiples of 20 % convert exactly both ways."""
    return round(value * 255 / 100)


async def lamp(hass, bridge, *, state: str = "on", brightness_pct: float | None = 60.0, **light) -> str:
    bridge.light("light-1", on=state == "on", **light)
    entry = await hue_entry(hass, bridge)
    attributes = {"brightness": percent(brightness_pct)} if state == "on" and brightness_pct is not None else {}
    return add_hue_entity(hass, entry, "light.lamp", "light-1", state=state, attributes=attributes)


async def room(hass, bridge, *, state: str = "on", brightness_pct: float = 60.0) -> str:
    on = state == "on"
    bridge.light("one", on=on, brightness=brightness_pct)
    bridge.light("two", on=on, brightness=brightness_pct)
    bridge.room("grouped-1", ["one", "two"], brightness=brightness_pct)
    entry = await hue_entry(hass, bridge)
    members = [add_hue_entity(hass, entry, f"light.{light_id}", light_id, state=state) for light_id in ("one", "two")]
    add_hue_group(hass, entry, "light.room", "grouped-1", members)
    attributes = {"is_hue_group": True, "entity_id": members} | ({"brightness": percent(brightness_pct)} if on else {})
    hass.states.async_set("light.room", state, attributes)
    return "light.room"


def fade_put(brightness: float, duration_ms: int, on: bool | None = None) -> dict:
    put: dict = {"dimming": {"brightness": brightness}, "dynamics": {"duration": duration_ms}}
    return put | ({"on": {"on": on}} if on is not None else {})


# No brightness: the bridge keeps the stored one, so the next plain turn_on comes back at it rather than the minimum.
SOFT_OFF_3S = {"on": {"on": False}, "dynamics": {"duration": 3000}}
STOP = {"dimming_delta": {"action": "stop"}}


async def mixed_room(hass, bridge, one_pct: float | None, two_pct: float | None) -> str:
    """A room whose lights are on at the given percent, or off for None."""
    for light_id, pct in (("one", one_pct), ("two", two_pct)):
        bridge.light(light_id, on=pct is not None, brightness=pct or 40.0)
    lit = [pct for pct in (one_pct, two_pct) if pct is not None]
    bridge.room("grouped-1", ["one", "two"], brightness=sum(lit) / len(lit) if lit else 0.0)
    entry = await hue_entry(hass, bridge)
    for light_id, pct in (("one", one_pct), ("two", two_pct)):
        attributes = {"brightness": percent(pct)} if pct is not None else {}
        add_hue_entity(hass, entry, f"light.{light_id}", light_id, state="on" if pct else "off", attributes=attributes)
    add_hue_group(hass, entry, "light.room", "grouped-1", ["light.one", "light.two"])
    return "light.room"


def report_off(bridge, *light_ids: str) -> None:
    """What the bridge reports at the start of a soft off: each light off, at once."""
    for light_id in light_ids:
        bridge.api.lights[light_id].on.on = False


def hs_xy(hue: float, saturation: float) -> tuple[float, float]:
    return color_hs_to_xy(hue, saturation)


def xy_put(xy: tuple[float, float], duration_ms: int) -> dict:
    """A saturation fade's write: an xy and a duration, no on."""
    return {
        "color": {"xy": {"x": pytest.approx(xy[0], abs=1e-4), "y": pytest.approx(xy[1], abs=1e-4)}},
        "dynamics": {"duration": duration_ms},
    }


def xy_halt(xy: tuple[float, float]) -> dict:
    """A saturation stop's fields: the predicted xy at once."""
    return {
        "color": {"xy": {"x": pytest.approx(xy[0], abs=1e-4), "y": pytest.approx(xy[1], abs=1e-4)}},
        "dynamics": {"duration": 0},
    }


async def color_lamp(hass, bridge, hs: tuple[float, float] = (200.0, 50.0), *, state: str = "on", **light) -> str:
    """light.lamp, a color bulb at 60 % showing the hs color."""
    return await lamp(hass, bridge, state=state, xy=hs_xy(*hs), **light)


async def color_room(hass, bridge, colors: dict[str, tuple[float, float] | None], *, on: bool = True) -> str:
    """light.room over one light per entry, all at 60 %: a color bulb at the hs color, or an ambiance bulb for None."""
    for light_id, hs in colors.items():
        bridge.light(light_id, on=on, brightness=60.0, xy=hs_xy(*hs) if hs else None)
    bridge.room("grouped-1", list(colors), brightness=60.0)
    entry = await hue_entry(hass, bridge)
    members = [
        add_hue_entity(hass, entry, f"light.{light_id}", light_id, state="on" if on else "off") for light_id in colors
    ]
    add_hue_group(hass, entry, "light.room", "grouped-1", members)
    return "light.room"
