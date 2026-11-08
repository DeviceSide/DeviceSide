"""Fabricate Shelly entities the way the core shelly integration registers them, with a mocked RPC device."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

MAC = "AABBCCDDEEFF"

# The Documented components, as (RPC key, component) for a parametrize.
DOCUMENTED_COMPONENTS = [("light:0", "Light"), ("cct:0", "CCT"), ("rgb:0", "RGB"), ("rgbw:0", "RGBW")]


# The light values a Set stores, which GetStatus reports back.
LIGHT_KEYS = ("brightness", "ct", "mode", "rgb")

# When a fixture timer starts, on the device's clock: 2026-10-27T12:00:00Z.
TIMER_STARTED_AT = 1793102400.0

# A component's auto-off / auto-on settings as the device ships them (Switch.GetConfig): disabled, delay 60 s.
FACTORY_CONFIG = {"auto_on": False, "auto_on_delay": 60.0, "auto_off": False, "auto_off_delay": 60.0}


def timer_running(status: dict | None = None, config: dict | None = None, halt: dict | None = None):
    """call_rpc side effect: Set returns the API's result; GetStatus reports `status` (an RGBCCT bulb's brightness,
    mode, ct and rgb, say) under the output, the light values Sets stored, any timer the last Set started (at
    TIMER_STARTED_AT) and the `transition` a Set with transition_duration started. DimStop ends that transition,
    leaving the light on at `halt` (its brightness, say), as the bulb does mid-fade. GetConfig reports
    FACTORY_CONFIG under `config` and what each SetConfig wrote."""
    sets: dict[tuple[str, int], dict] = {}
    configs: dict[tuple[str, int], dict] = {}

    def respond(method: str, params: dict) -> dict | None:
        component, _, verb = method.partition(".")
        key = (component, params["id"])
        if verb == "GetStatus":
            return {"id": params["id"], "output": False, **(status or {}), **sets.get(key, {})}
        if verb == "GetConfig":
            return {"id": params["id"], **FACTORY_CONFIG, **(config or {}), **configs.get(key, {})}
        if verb == "SetConfig":
            configs.setdefault(key, {}).update(params["config"])
            return {"restart_required": False}
        if verb == "DimStop":
            held = sets.setdefault(key, {})
            if held.pop("transition", None) is not None:
                held |= {"output": True, **(halt or {})}
            return None
        light = {k: v for k, v in params.items() if k in LIGHT_KEYS}
        if "on" not in params:
            # A light Set without `on` stores the values and leaves the output as it is.
            sets.setdefault(key, {}).update(light)
            return None
        stored = {k: v for k, v in sets.get(key, {}).items() if k in LIGHT_KEYS}
        sets[key] = {**stored, **light, "output": params["on"]}
        if "toggle_after" in params:
            sets[key] |= {"timer_started_at": TIMER_STARTED_AT, "timer_duration": params["toggle_after"]}
        if "transition_duration" in params:
            target = {"output": params["on"], **light}
            sets[key]["transition"] = {
                "target": target,
                "started_at": TIMER_STARTED_AT,
                "duration": params["transition_duration"],
            }
        return {"was_on": not params["on"]}

    return respond


def failing(call_rpc: AsyncMock, verb: str, after: int = 0) -> None:
    """Make the device raise on `verb` (GetConfig, SetConfig...) once it has answered it `after` times."""
    respond, seen = call_rpc.side_effect, []

    async def side_effect(method: str, params: dict) -> dict:
        if method.endswith(f".{verb}"):
            seen.append(method)
            if len(seen) > after:
                raise ConnectionError("device unreachable")
        return respond(method, params)

    call_rpc.side_effect = side_effect


def shelly_device(
    hass: HomeAssistant,
    gen1: bool = False,
    mac: str = MAC,
    status: dict | None = None,
    config: dict | None = None,
    halt: dict | None = None,
) -> tuple[MockConfigEntry, AsyncMock]:
    """A loaded Shelly entry whose runtime_data.rpc.device.call_rpc is the returned mock; status, config and halt as
    timer_running's."""
    call_rpc = AsyncMock(side_effect=timer_running(status, config, halt))
    entry = MockConfigEntry(domain="shelly", unique_id=mac)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    rpc = None if gen1 else SimpleNamespace(device=SimpleNamespace(call_rpc=call_rpc))
    entry.runtime_data = SimpleNamespace(rpc=rpc, block=SimpleNamespace() if gen1 else None)
    return entry, call_rpc


def add_shelly_entity(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    entity_id: str,
    key: str,
    state: str = "off",
    attributes: dict | None = None,
) -> str:
    """key is the RPC key (switch:0, light:0, rgbcct:0) or, for Gen1 and non-timer entities, any unique_id suffix."""
    domain, object_id = entity_id.split(".")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, connections={(dr.CONNECTION_NETWORK_MAC, entry.unique_id)}
    )
    er.async_get(hass).async_get_or_create(
        domain,
        "shelly",
        f"{entry.unique_id}-{key}",
        suggested_object_id=object_id,
        config_entry=entry,
        device_id=device.id,
    )
    hass.states.async_set(entity_id, state, attributes or {})
    return entity_id
