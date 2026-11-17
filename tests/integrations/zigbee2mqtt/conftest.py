import asyncio
import itertools
import json
import logging
import re
from dataclasses import replace
from types import SimpleNamespace

import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.deviceside.core.models import Target
from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.runtime import DATA, get_runtime
from custom_components.deviceside.core.scope import Unplaced
from custom_components.deviceside.integrations.zigbee2mqtt import (
    INTEGRATION,
    bridge,
    bridge_cache,
    classes,
    members,
    native_control,
    read,
    set_attributes,
    set_check,
)
from custom_components.deviceside.integrations.zigbee2mqtt.fade import transition_cache
from custom_components.deviceside.integrations.zigbee2mqtt.turn_on_for import Z2MTurnOnFor

from ...conftest import Clock, leaked, unload_mock_entries
from ...conftest import call as call_service
from ...fixtures.zigbee2mqtt import GROUPS, IEEE, INFO, Broker, add_z2m_entity, add_z2m_group, z2m_entry

unload_mock_mqtt_entries = unload_mock_entries("mqtt")

# What names a Z2M device in a log line (docs/logging.md): an IEEE, a device's MQTT topic, or Z2M's own failure line,
# which carries its friendly name and IEEE.
_ADDRESSED = re.compile(r"0x[0-9a-fA-F]{16}|zigbee2mqtt/(?!bridge/)|Publish 'set' '")


def friendly_names(broker) -> set[str]:
    """The friendly names the broker knows: its devices', and those bridge/info, devices and groups list."""
    config = (broker.retained.get(INFO) or {}).get("config", {})
    listed = [*config.get("devices", {}).values(), *config.get("groups", {}).values()]
    for suffix in ("devices", "groups"):
        if isinstance(entries := broker.retained.get(f"zigbee2mqtt/bridge/{suffix}"), list):
            listed += [entry for entry in entries if isinstance(entry, dict)]
    return {name for name, _ in broker.devices.values()} | {
        name for entry in listed if (name := entry.get("friendly_name"))
    }


@pytest.fixture(autouse=True)
def no_addresses_logged(request, caplog):
    """Every Zigbee2MQTT test runs at DEBUG and fails if a log line names a device's address: one of _ADDRESSED, or
    a friendly name the test's broker knows as Z2M's own text names a device: quoted, or ahead of an endpoint."""
    caplog.set_level(logging.DEBUG, logger="custom_components.deviceside")
    # Taken now, so the broker outlives this fixture's check.
    broker = request.getfixturevalue("broker") if "broker" in request.fixturenames else None
    yield
    names = friendly_names(broker) if broker is not None else set()
    named = re.compile("|".join(rf"'{re.escape(n)}'|(?<![\w/]){re.escape(n)}/\d" for n in names)) if names else None
    assert not leaked(caplog, lambda line: _ADDRESSED.search(line) or (named is not None and named.search(line)))


@pytest.fixture
def harmless(monkeypatch):
    """turn_on_for without its not_built entries, as if today's call harmed no class, for a test of its call
    alone on a group bridge/groups doesn't list: the dispatcher otherwise refuses it as class_unknown
    (test_classes.py), and still counts it as Experimental. The classes stay refused, left out of the scope."""
    monkeypatch.setattr(Z2MTurnOnFor, "scope", replace(Z2MTurnOnFor.scope, not_built={}))


@pytest.fixture(autouse=True)
def publish_via_service(monkeypatch):
    """Route mqtt.async_publish to the handler a test registered as the mqtt.publish service (the broker, or a failure).

    The real mqtt integration isn't set up in unit tests, so its async_publish would refuse every publish. The handler
    is run directly, not through `hass.services.async_call`, so the publish is no service call in a transcript.
    """

    async def async_publish(hass, topic: str, payload: str, *args, **kwargs) -> None:
        if (service := hass.services.async_services_internal().get("mqtt", {}).get("publish")) is None:
            raise ServiceNotFound("mqtt", "publish")
        call = ServiceCall(hass, "mqtt", "publish", {"topic": topic, "payload": payload})
        if (running := hass.async_run_hass_job(service.job, call)) is not None:
            await running

    monkeypatch.setattr(bridge.mqtt, "async_publish", async_publish)


@pytest.fixture(autouse=True)
def numbered_transactions(monkeypatch):
    """bridge.py's options-request transactions, numbered per test (`000...01`) instead of random, so a request's
    bytes are the same on every run."""
    numbers = itertools.count(1)
    monkeypatch.setattr(bridge, "uuid4", lambda: SimpleNamespace(hex=f"{next(numbers):032x}"))


@pytest.fixture
def broker(hass, monkeypatch):
    fake = Broker()
    fake.retained[INFO] = {"config": {"devices": {IEEE: {"friendly_name": "bulb"}}, "groups": {}}}
    fake.retained["zigbee2mqtt/bridge/state"] = {"state": "online"}
    monkeypatch.setattr(bridge.mqtt, "async_subscribe", fake.subscribe)
    monkeypatch.setattr(bridge, "_RETAINED_TIMEOUT_S", 0.1)
    monkeypatch.setattr(bridge, "_REPLY_TIMEOUT_S", 0.1)
    monkeypatch.setattr(read, "_REPLY_TIMEOUT_S", 0.1)
    monkeypatch.setattr(native_control, "_REPLY_CAP_S", 0.05)
    monkeypatch.setattr(set_attributes, "_FADE_WAIT_S", 0.0)
    monkeypatch.setattr(set_attributes, "_RETRY_S", 0.0)
    hass.services.async_register("mqtt", "publish", fake.publish)

    # The dispatcher lists a group's members from bridge/groups as the running cache would hold it, once the entry is
    # set up; a test's own cache stays, once it holds bridge/groups.
    def held(hass):
        if (cache := bridge_cache.get(hass)) is not None and cache.parsed("groups") is not None:
            return cache
        return HeldGroups(fake) if DATA in hass.data else None

    monkeypatch.setattr(members, "bridge_cache", SimpleNamespace(get=held))
    monkeypatch.setattr(classes, "bridge_cache", SimpleNamespace(get=held))
    return fake


async def call(hass, service: str, data: dict, return_response: bool = True):
    """The response, each entry's class checked and left out, so a test states only what its action decides: every
    Zigbee2MQTT result names the class its device is, or a group's members', unless one isn't placed yet
    (docs/action-behavior.md). A group's `member_capabilities` is checked against the rule, not rebuilt: each key is
    one of the members the group lists, with an available state of its own, never the group, and maps to the class
    that member has classed alone. A test that states the map in full calls the service directly."""
    response = await call_service(hass, service, data, return_response)
    registry = get_runtime(hass).registry
    for entity_id, entry in (response or {}).items():
        target = resolve(hass, registry, entity_id)
        listed = (INTEGRATION.expand_group(hass, target) or []) if target.is_group else [target]
        found = [INTEGRATION.capability(hass, member) for member in listed]
        known = bool(found) and not any(name is None or isinstance(name, Unplaced) for name in found)
        if not target.is_group:
            assert entry.pop("capability", None) == (found[0] if known else None), entity_id
            continue
        assert entry.pop("capabilities", None) == (sorted(set(found)) if known else None), entity_id
        by_member = entry.pop("member_capabilities", {})
        assert set(by_member) <= {member.reported_id for member in listed}, (entity_id, by_member)
        for member, name in by_member.items():
            state = hass.states.get(member)
            assert member != entity_id and state is not None and state.state != "unavailable", (entity_id, member)
            assert INTEGRATION.capability(hass, resolve(hass, registry, member)) == name, (entity_id, member)
            assert name in found, (entity_id, member)
    return response


class HeldGroups(bridge_cache.BridgeCache):
    """A bridge cache holding bridge/groups and bridge/devices, as the broker has them now, for members.expand_group
    and the classifier."""

    def __init__(self, broker) -> None:
        super().__init__()
        self.broker = broker

    def parsed(self, suffix: str):
        return self.broker.retained.get({"groups": GROUPS, "devices": DEVICES}.get(suffix))


DEVICES = "zigbee2mqtt/bridge/devices"
LOGGING = "zigbee2mqtt/bridge/logging"
XY = ["color_temp", "xy"]
# Strings of the shapes the lab probe saw (research/2026-11-14-lab-probe.md, §1): the Zigbee manufacturer a Tuya
# device reports in bridge/devices, and the vendor and definition Z2M registers for a TS011F.
TUYA = "_TZ3000_abcdefgh"
TUYA_MCU = "_TZE200_abcdefgh"
PLUG = ("Tuya", "TS011F_plug_1")
# A light's color cluster mid-hue-cycle: in hs mode (0), at x 0.3 and y 0.4.
COLOR = {"colorMode": 0, "currentX": 19661, "currentY": 26214}


@pytest.fixture
def clock(hass, setup_production) -> Clock:
    clock = Clock()
    transition_cache(hass).clock = clock
    return clock


class REGISTRY:
    """light()'s default Zigbee strings: the registry's vendor, and ZIGBEE_MODEL."""


# A Zigbee model no rule matches.
ZIGBEE_MODEL = "bulb"


def light(
    hass,
    broker,
    entity_id: str = "light.lamp",
    ieee: str = IEEE,
    *,
    state: str = "on",
    brightness: int | None = 153,  # 60 %
    hs: tuple[float, float] | None = (200.0, 60.0),
    modes: list[str] | None = None,
    color_hs: bool = True,
    color: dict | None = None,
    manufacturer: str | None = "Philips",
    model_id: str | None = None,
    zigbee: tuple[str | None, str | None] | None | type[REGISTRY] = REGISTRY,
    interviewed: bool | None = None,
    color_mode: str = "xy",
) -> str:
    """A Z2M color light HA lists with xy, whose definition exposes color_hs, answering color reads with COLOR.

    Its bridge/devices entry holds the Zigbee manufacturer and model `zigbee` names. By default, REGISTRY, the
    registry's manufacturer and ZIGBEE_MODEL: an interviewed device of that vendor that shows no Tuya string. None
    writes an entry with neither, as Zigbee2MQTT lists a device mid-interview, which the classifier can't place by
    them. `interview_completed` is `interviewed`, by default whether `zigbee` names any string.
    """
    name = entity_id.split(".")[1]
    entries = hass.config_entries.async_entries("mqtt")
    entry = entries[0] if entries else z2m_entry(hass)
    attributes: dict = {"supported_color_modes": XY if modes is None else modes}
    if state == "on":
        attributes |= {"brightness": brightness, "hs_color": hs, "color_mode": color_mode}
    add_z2m_entity(
        hass,
        entry,
        entity_id,
        ieee=ieee,
        state=state,
        attributes=attributes,
        name=name,
        manufacturer=manufacturer,
        model_id=model_id,
    )
    broker.devices[ieee] = (name, {"lightingColorCtrl": {**COLOR, **(color or {})}})
    broker.retained[INFO]["config"]["devices"].setdefault(ieee, {})
    features = [{"name": "state"}, {"name": "brightness"}] + ([{"name": "color_hs"}] if color_hs else [])
    device = {"ieee_address": ieee, "definition": {"exposes": [{"type": "light", "features": features}]}}
    if zigbee is REGISTRY:
        zigbee = (manufacturer, ZIGBEE_MODEL)
    # Its own Zigbee manufacturer and model, which the classifier reads; Z2M holds null for one it hasn't read.
    device |= dict(zip(("manufacturer", "model_id"), zigbee or (None, None), strict=True))
    device["interview_completed"] = zigbee is not None if interviewed is None else interviewed
    broker.retained.setdefault(DEVICES, []).append(device)
    return entity_id


def group(hass, broker, **members: dict) -> str:
    """Z2M group 7, light.room, of light.one (0x01) and light.two (0x02), each set up by light() with its options."""
    for ieee, (name, options) in zip(("0x01", "0x02"), members.items(), strict=True):
        light(hass, broker, f"light.{name}", ieee, **options)
    add_z2m_group(hass, hass.config_entries.async_entries("mqtt")[0], "light.room", group_id=7, name="room")
    hass.states.async_set("light.room", "on", {"supported_color_modes": XY, "hs_color": (200.0, 60.0)})
    broker.retained[GROUPS] = [{"id": 7, "members": [{"ieee_address": "0x01"}, {"ieee_address": "0x02"}]}]
    return "light.room"


def interviewed(ieee: str, manufacturer: str, model_id: str) -> dict:
    """A device's bridge/devices entry once Zigbee2MQTT has interviewed it."""
    return {"ieee_address": ieee, "manufacturer": manufacturer, "model_id": model_id, "interview_completed": True}


def target(hass, entity_id: str) -> Target:
    """The target of a registered entity, built without the dispatcher."""
    entry = er.async_get(hass).async_get(entity_id)
    device = dr.async_get(hass).async_get(entry.device_id)
    return Target(entity_id, "light", "zigbee2mqtt", entry, device, None, hass.states.get(entity_id))


@pytest.fixture
def live(hass, setup_production, broker, monkeypatch):
    """The bridge cache with its response topics and bridge/logging live, as once MQTT is up, so sets are checked
    (set_check.py)."""
    cache = bridge_cache.BridgeCache()
    cache.replies_live = True
    hass.data[DATA].integration_state[bridge_cache._KEY] = cache
    broker.subscribers.setdefault(LOGGING, []).append(cache._on_log)
    for kind in bridge_cache.KINDS:
        reply_topic = f"zigbee2mqtt/bridge/response/{kind}/options"
        broker.subscribers.setdefault(reply_topic, []).append(bridge_cache.reply_router(cache.pending))
    monkeypatch.setattr(set_check, "BOUND_S", 0.05)
    return cache


def log(broker, message: str, level: str = "error") -> None:
    """A line on Zigbee2MQTT's bridge/logging."""
    broker.deliver(LOGGING, json.dumps({"level": level, "message": message}))


def answer(broker, on: str, *, line: str | None = None, state: str | None = None) -> None:
    """Have Z2M answer each set published to `on`: a log line, and or a state publish under the friendly name."""

    def on_set(topic: str, payload: dict) -> None:
        if topic != on:
            return
        loop = asyncio.get_running_loop()
        if line is not None:
            loop.call_soon(log, broker, line)
        if state is not None:
            loop.call_soon(broker.deliver, f"zigbee2mqtt/{state}", json.dumps({"state": "ON"}))

    broker.on_set = on_set


async def failure(hass, service: str, data: dict) -> str:
    """The summary a call raises targets_failed with."""
    with pytest.raises(HomeAssistantError) as raised:
        await call(hass, service, data)
    assert raised.value.translation_key == "targets_failed"
    return raised.value.translation_placeholders["summary"]


def commands(broker) -> list[tuple[str, dict]]:
    """Every command and get published to a light or group, leaving out bridge requests and reads."""
    return [
        (p["topic"], p["payload"])
        for p in broker.published
        if not p["topic"].startswith("zigbee2mqtt/bridge/") and "read" not in p["payload"]
    ]


SENT = {"status": "sent", "integration": "zigbee2mqtt"}
SET = f"zigbee2mqtt/{IEEE}/set"
GET = f"zigbee2mqtt/{IEEE}/get"
# An off light is put here first, so a fade from off starts at the bottom, not the level it kept.
BOTTOM = {"state": "ON", "brightness": 1, "transition": 0}
