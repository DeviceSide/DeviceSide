"""Fabricate Control4 light entities the way the core control4 integration registers them, with a mocked Director."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import unquote

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

CONTROLLER = "00:0f:ff:00:00:01"
ITEM = 100


class FakeDirector:
    """A Director holding one light's level, as the light proxy's variables report it; every item it is asked about
    is that one light.

    RAMP_TO_LEVEL sets the target and leaves the level where it is, as a ramp just begun does. SET_BRIGHTNESS_STOP
    halts a ramp in flight at `halt` (the level it had reached) and changes nothing on a light at rest. `legacy`
    lights report LIGHT_LEVEL alone, the variable core also reads and no tested light reports; `text` reports each
    value as text, as the Director does for a light that has never reported.
    """

    def __init__(
        self,
        brightness: float = 40,
        on: bool = True,
        halt: float | None = None,
        legacy: bool = False,
        log: list | None = None,
    ):
        # Each request as ("get" | command, item), in the order the Director took them; shared between Directors.
        self.log = log if log is not None else []
        # Set to hold every read until it is set, as a slow Director does.
        self.gate: asyncio.Event | None = None
        self.brightness = float(brightness) if on else 0.0
        self.target = self.brightness
        # The color temperature the Director shows, the one a light that is off will come on at, and the range the
        # light's capabilities give (None: it says it takes none).
        self.kelvin = 3200
        # Where the color temperature is heading; `current_lags` leaves the current one behind it, as the Director
        # does for most of a second after a write (Tested behavior).
        self.target_kelvin = 3200
        self.current_lags = False
        self.pending_kelvin: int | None = None
        self.kelvin_span: tuple[int, int] | None = (2203, 6536)
        self.color_mode = 1
        self.target_color_mode = 1
        self.halt = halt
        self.legacy = legacy
        self.text = False
        self.ignore_stop = False
        self.ignore_color = False
        # An on/off light as this fake models one: LIGHT_STATE alone. None has been read on hardware.
        self.on_off = False
        # The capabilities variable as the JSON text of the object, not the object.
        self.capabilities_as_text = False
        # Reads after a stop that still show the ramp, as a Director that hasn't heard from the light yet does.
        self.lag_reads = 0
        self._lagging: int | None = None
        self._lagging_color: list | None = None
        self.send_get_request = AsyncMock(side_effect=self._get)
        self.send_post_request = AsyncMock(side_effect=self._post)

    def _value(self, value: float):
        return str(value) if self.text else value

    async def _get(self, uri: str) -> str:
        item = int(uri.split("/")[4])
        self.log.append(("get", item))
        if self.gate is not None:
            await self.gate.wait()
        if self._lagging is not None:
            if self._lagging > 0:
                self._lagging -= 1
            else:
                self._lagging = None
                self._halt()
        if self._lagging_color is not None and "Current%20CCT" in uri:
            if self._lagging_color[0] > 0:
                self._lagging_color[0] -= 1
            else:
                self._show(self._lagging_color[1])
                self._lagging_color = None
        on = 1 if self.brightness > 0 else 0
        if self.on_off:
            rows = {"LIGHT_STATE": on}
        elif self.legacy:
            rows = {"LIGHT_LEVEL": self.brightness}
        else:
            rows = {
                "Brightness Percent": self.brightness,
                "LIGHT_STATE": on,
                "Brightness Target Percent": self.target,
                "Current CCT": self.kelvin,
                "Target CCT": self.target_kelvin,
                "Target Color Mode": self.target_color_mode,
                "Current Color Mode": self.color_mode,
            }
        found = [{"id": item, "varName": name, "value": self._value(value)} for name, value in rows.items()]
        if not self.legacy and not self.on_off:
            span = self.kelvin_span or (0, 0)
            capabilities = {
                "supports_color_correlated_temperature": self.kelvin_span is not None,
                "color_correlated_temperature_min": span[0],
                "color_correlated_temperature_max": span[1],
            }
            value = {"DynamicCapabilities": capabilities}
            if self.capabilities_as_text:
                value = json.dumps(value)
            found.append({"id": item, "varName": "Navigator Dynamic Capabilities", "value": value})
        wanted = [unquote(name) for name in uri.partition("varnames=")[2].split(",")]
        return json.dumps([row for row in found if row["varName"] in wanted])

    async def _post(self, uri: str, command: str, params: dict) -> str:
        self.log.append((command, int(uri.split("/")[4])))
        if command == "RAMP_TO_LEVEL":
            self.target = float(params["LEVEL"])
        elif command == "SET_COLOR_TARGET":
            # A light that is on shows it as its target at once here; on hardware that took up to 0.2 s, and the
            # current one first showed on reads sent 0.76-0.91 s after the command (Tested behavior), which only
            # `current_lags` models. One that is off shows it for a little over a second, then the old one until it
            # comes on; this models the light after that.
            kelvin = params["LIGHT_COLOR_TARGET_COLOR_CORRELATED_TEMPERATURE"]
            if self.brightness > 0 and not self.ignore_color and self.lag_reads:
                self._lagging_color = [self.lag_reads, kelvin]
            elif self.brightness > 0 and not self.ignore_color:
                self._show(kelvin)
            else:
                self.pending_kelvin = kelvin
        elif command == "SET_BRIGHTNESS_STOP" and not self.ignore_stop and self.target != self.brightness:
            if self.lag_reads:
                self._lagging = self.lag_reads
            else:
                self._halt()
        return "{}"

    def _show(self, kelvin: int) -> None:
        # The Director holds a color temperature in tens of kelvin, rounded down (Tested behavior).
        kelvin = kelvin // 10 * 10
        self.target_kelvin = kelvin
        if not self.current_lags:
            self.kelvin = kelvin

    def _halt(self) -> None:
        self.brightness = self.target = float(self.halt if self.halt is not None else self.brightness)


def failing(director: FakeDirector, method: str, after: int = 0) -> None:
    """Make the Director raise on `method` (send_get_request, send_post_request) once it has answered `after` times."""
    mock = getattr(director, method)
    respond, seen = mock.side_effect, []

    async def side_effect(*args):
        seen.append(args)
        if len(seen) > after:
            raise ConnectionError("director unreachable")
        return await respond(*args)

    mock.side_effect = side_effect


class BadToken(Exception):
    """pyControl4's error for an expired Director token, which the adapters know by its name alone."""


def control4_entry(hass: HomeAssistant, director: FakeDirector | None, controller: str = CONTROLLER) -> MockConfigEntry:
    """A loaded Control4 entry whose runtime_data.director is `director`."""
    entry = MockConfigEntry(domain="control4", unique_id=controller)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    entry.runtime_data = SimpleNamespace(director=director)
    return entry


def add_control4_light(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id: str,
    unique_id: str = str(ITEM),
    state: str = "on",
    attributes: dict | None = None,
) -> str:
    """unique_id is the Director item's id, as control4/light.py sets it."""
    domain, object_id = entity_id.split(".")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("control4", unique_id)}
    )
    er.async_get(hass).async_get_or_create(
        domain, "control4", unique_id, suggested_object_id=object_id, config_entry=entry, device_id=device.id
    )
    hass.states.async_set(entity_id, state, attributes or {"supported_color_modes": ["brightness"]})
    return entity_id
