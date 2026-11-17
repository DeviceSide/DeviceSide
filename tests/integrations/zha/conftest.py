import logging
import re
import sys
from types import SimpleNamespace

import probatio
import pytest
from homeassistant.core import Context, ServiceCall
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.util.color import color_hs_to_xy
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.deviceside.const import DOMAIN
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import get_runtime
from custom_components.deviceside.integrations.zha import INTEGRATION, zcl
from custom_components.deviceside.integrations.zha.fade import transition_cache

from ...conftest import Clock, leaked, unload_mock_entries
from ...conftest import call as call_service
from ...fixtures.zha import HUE, IEEE, ZIGPY_TYPES, Gateway, add_zha_entity, gateway_of, zha_entry, zha_group

SENT = {"status": "sent", "integration": "zha"}
# The Zigbee strings of the Sengled E11-G13, which drops a level while off (zcl.DROPS_WHILE_OFF).
E11_G13 = ("sengled", "E11-G13")
# Another brand's bulb, which no rule places: the default class.
IKEA = ("IKEA of Sweden", "TRADFRI bulb E27 WS opal 980lm")
A, B = "00:00:00:00:00:00:00:0a", "00:00:00:00:00:00:00:0b"
COLOR_MODES = ["color_temp", "xy"]
# MoveToLevel to 1 with ExecuteIfOff: a light that is off, put at the bottom before a raise.
BOTTOM = (0x0008, 0x00, {"level": 1, "transition_time": 0, "options_mask": 1, "options_override": 1})
# The same with ExecuteIfOff at 60 %: bulb()'s default level, put back once a soft off has run.
RESTORE_60 = (0x0008, 0x00, {"level": 152, "transition_time": 0, "options_mask": 1, "options_override": 1})


unload_mock_zha_entries = unload_mock_entries("zha")

# A ZHA IEEE as HA and zha write it (00:17:88:01:02:03:04:05), which a log line never names (docs/logging.md).
_IEEE = re.compile(r"\b(?:[0-9a-fA-F]{2}:){7}[0-9a-fA-F]{2}\b")


@pytest.fixture(autouse=True)
def no_ieee_logged(caplog):
    """Every ZHA test runs at DEBUG and fails if a log line names a device's IEEE."""
    caplog.set_level(logging.DEBUG, logger="custom_components.deviceside")
    yield
    assert not leaked(caplog, _IEEE.search)


@pytest.fixture(autouse=True)
def zha_gateway(hass, monkeypatch) -> Gateway:
    """zha's gateway in hass.data, as zha sets it up, holding the zigpy devices add_zha_entity fabricates, and the
    zigpy.types zcl imports: zcl's helpers run for real against them (tests/fixtures/zha.py). The fixtures' lights
    have no Hue cluster unless a test adds one."""
    gateway = gateway_of(hass)
    monkeypatch.setitem(hass.data, "zha", SimpleNamespace(gateway_proxy=SimpleNamespace(gateway=gateway)))
    monkeypatch.setitem(sys.modules, "zigpy.types", ZIGPY_TYPES)
    return gateway


@pytest.fixture
def zha_groups(zha_gateway) -> dict:
    """The fake zha gateway's groups by ID; the gateway answers get_group from it."""
    return zha_gateway.groups


@pytest.fixture
def clock(hass, setup_production) -> Clock:
    clock = Clock()
    transition_cache(hass).clock = clock
    return clock


@pytest.fixture
def commands(hass):
    return async_mock_service(hass, "zha", "issue_zigbee_cluster_command")


@pytest.fixture
def group_commands(hass):
    return async_mock_service(hass, "zha", "issue_zigbee_group_command")


@pytest.fixture
def admin_command(hass) -> list[ServiceCall]:
    """ZHA's real registration of its cluster and group commands: admin services, which check the caller's context.
    The calls that reached either."""
    calls: list[ServiceCall] = []

    async def handler(service: ServiceCall) -> None:
        calls.append(service)

    schema = probatio.Schema({}, extra=probatio.ALLOW_EXTRA)
    for service in ("issue_zigbee_cluster_command", "issue_zigbee_group_command"):
        async_register_admin_service(hass, "zha", service, handler, schema)
    return calls


async def call(hass, service: str, data: dict, return_response: bool = True):
    """The response, each entry's class checked and left out, so a test states only what its action decides: every
    ZHA result names the class its device is, or a ZHA group's members' (docs/action-behavior.md)."""
    return checked(hass, await call_service(hass, service, data, return_response))


async def call_as(hass, user, action: str, data: dict) -> dict:
    """Call one of our actions as this user, as the frontend or an automation would; the classes checked, as call's."""
    return checked(
        hass,
        await hass.services.async_call(
            DOMAIN, action, data, blocking=True, return_response=True, context=Context(user_id=user.id)
        ),
    )


def checked(hass, response: dict | None) -> dict | None:
    """The response with each entry's class popped once checked against the classifier's."""
    for entity_id, entry in (response or {}).items():
        target = resolve(hass, get_runtime(hass).registry, entity_id)
        if isinstance(target, str):
            continue
        listed = (INTEGRATION.expand_group(hass, target) or []) if target.is_group else [target]
        found = [INTEGRATION.capability(hass, member) for member in listed]
        known = bool(found) and None not in found
        if target.is_group:
            assert entry.pop("capabilities", None) == (sorted(set(found)) if known else None), entity_id
        else:
            assert entry.pop("capability", None) == (found[0] if known else None), entity_id
    return response


@pytest.fixture
def refreshes(hass):
    return async_mock_service(hass, "homeassistant", "update_entity")


def bulb(
    hass,
    entity_id: str = "light.bulb",
    ieee: str = IEEE,
    *,
    state: str = "on",
    brightness: int = 153,  # 60 %
    hs: tuple[float, float] = (200.0, 60.0),
    modes: list[str] | None = None,
    strings: tuple[str, str] = HUE,
    color_mode: str = "xy",
) -> str:
    entries = hass.config_entries.async_entries("zha")
    entry = entries[0] if entries else zha_entry(hass)
    attributes: dict = {"supported_color_modes": COLOR_MODES if modes is None else modes}
    if state == "on":
        attributes |= {"brightness": brightness, "hs_color": hs, "color_mode": color_mode}
    add_zha_entity(hass, entry, entity_id, ieee=ieee, state=state, attributes=attributes, strings=strings)
    return entity_id


def sent(commands) -> list[tuple[int, int, dict]]:
    return [(command.data["cluster_id"], command.data["command"], command.data["params"]) for command in commands]


def to(commands) -> list[str]:
    return [command.data["ieee"] for command in commands]


@pytest.fixture
def two_light_group(hass, zha_groups):
    """light.zha_group, ZHA group 2, of light.a and light.b."""
    entry = zha_entry(hass)
    add_zha_entity(hass, entry, "light.zha_group", unique_id="light_zha_group_0x0002")
    zha_groups[2] = zha_group((A, 11), (B, 11))
    return entry


# The A60's ColorCapabilities: hue and saturation, enhanced hue, color loop, xy and color temperature (probe 13a).
A60_CAPABILITIES = 0x1F
# A color light with xy and color temperature only.
XY_ONLY = 0x18


@pytest.fixture
def bulbs(zha_gateway) -> Gateway:
    """Every light, for raise, lower and stop: OnOff reads off (a soft off has run), ColorCapabilities reads the A60's,
    and CurrentLevel answers only where a test sets a light's own, so a fade's ramp is fitted to a read only then."""
    zha_gateway.answers[zcl.ON_OFF_CLUSTER] = {zcl.ON_OFF: False}
    zha_gateway.answers[zcl.COLOR_CLUSTER] = {zcl.COLOR_CAPABILITIES: A60_CAPABILITIES}
    return zha_gateway


def on_off_reads(gateway: Gateway) -> list:
    """The OnOff reads among the reads, leaving out the Level reads each brightness fade fits its ramp to."""
    return [read for read in gateway.reads if read[1] == zcl.ON_OFF_CLUSTER]


def xy(hue: float, saturation: float) -> dict:
    x, y = color_hs_to_xy(hue, saturation)
    return {"color_x": round(x * 65535), "color_y": round(y * 65535)}
