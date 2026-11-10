"""Zigbee2MQTT's bridge: its groups, device features and entity options from retained topics, and options requests."""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback

from . import bridge_cache
from .addressing import bridge_topic, state_topic
from ...core.models import Target

_LOGGER = logging.getLogger(__name__)

# Retained topics arrive once HA's debounced subscribe reaches the broker; the reply takes one settings write.
_RETAINED_TIMEOUT_S = 2.0
_REPLY_TIMEOUT_S = 5.0


async def group_members(hass: HomeAssistant, group: str) -> list[str]:
    """The IEEE addresses of a Z2M group's members, from bridge/groups; none for a group it doesn't list."""
    groups = await retained(hass, "groups")
    members = next((g.get("members", []) for g in groups if str(g.get("id")) == group), [])
    return [member["ieee_address"] for member in members if member.get("ieee_address")]


async def has_feature(hass: HomeAssistant, ieees: list[str], name: str) -> bool:
    """Whether every one of these devices' Z2M definitions exposes a feature by this name, from bridge/devices: Z2M
    gives a group only the features its members share."""
    devices = await retained(hass, "devices")
    exposing = {
        device.get("ieee_address")
        for device in devices
        if _exposes(name, (device.get("definition") or {}).get("exposes", []))
    }
    return bool(ieees) and set(ieees) <= exposing


def _exposes(name: str, features: list[dict]) -> bool:
    """Whether the feature is in this exposes list, or nested in one of its composites (a light's features)."""
    return any(feature.get("name") == name or _exposes(name, feature.get("features", [])) for feature in features)


async def retained(hass: HomeAssistant, suffix: str) -> Any:
    """The parsed retained message on bridge/<suffix>; raises TimeoutError when Z2M hasn't published one.

    bridge/devices and bridge/groups come from the bridge cache when it holds them (bridge_cache.py), else from a fresh
    subscription, as bridge/info always does.
    """
    if (
        suffix in bridge_cache.HELD
        and (cache := bridge_cache.get(hass)) is not None
        and (held := cache.parsed(suffix)) is not None
    ):
        return held
    payload: asyncio.Future[str] = hass.loop.create_future()
    unsubscribe = await mqtt.async_subscribe(hass, bridge_topic(suffix), first_payload(payload))
    try:
        return json.loads(await wait(payload, _RETAINED_TIMEOUT_S, f"no bridge/{suffix} from Zigbee2MQTT"))
    finally:
        unsubscribe()


async def ensure_options(
    hass: HomeAssistant,
    kind: Literal["device", "group"],
    z2m_ids: list[str],
    wanted: Callable[[dict], dict],
    changed: Callable[[str], None],
) -> None:
    """Set each entity's options to what `wanted` returns from its current ones, where that is anything.

    Reads Z2M's settings on every call rather than caching them, so a user who changes an option is seen. Calls
    `changed` with each ID as Z2M confirms its options, so one set before a later failure is still reported; raises
    when bridge/info or a reply doesn't come, or a reply is an error.
    """
    section = f"{kind}s"
    # With the bridge cache's response subscriptions live, the reply is routed to its pending futures; otherwise this
    # call subscribes for its own.
    cache = bridge_cache.get(hass)
    shared = cache is not None and cache.replies_live
    pending: dict[str, asyncio.Future[dict]] = cache.pending if shared else {}
    transactions: list[str] = []

    info: asyncio.Future[str] = hass.loop.create_future()
    # HA debounces subscribes, so async_subscribe returns before the broker has them. Queued together, the two
    # reach the broker in one batch: the retained bridge/info arriving shows the reply topic is subscribed too,
    # before a request goes out. bridge/info is subscribed fresh even when the reply topic is the cache's, as its
    # values must be fresh and read.reader() relies on its arrival for the subscription it queues just before.
    unsubscribes = []
    if not shared:
        reply_topic = bridge_topic(f"response/{kind}/options")
        unsubscribes.append(await mqtt.async_subscribe(hass, reply_topic, bridge_cache.reply_router(pending)))
    unsubscribes.append(await mqtt.async_subscribe(hass, bridge_topic("info"), first_payload(info)))
    try:
        settings = json.loads(await wait(info, _RETAINED_TIMEOUT_S, "no bridge/info from Zigbee2MQTT"))
        for z2m_id in z2m_ids:
            if not (options := wanted(settings.get("config", {}).get(section, {}).get(z2m_id, {}))):
                continue
            transaction = uuid4().hex
            transactions.append(transaction)
            pending[transaction] = hass.loop.create_future()
            await publish(
                hass,
                bridge_topic(f"request/{kind}/options"),
                {"id": z2m_id, "options": options, "transaction": transaction},
            )
            answer = await wait(pending[transaction], _REPLY_TIMEOUT_S, "no reply from Zigbee2MQTT")
            if answer.get("status") != "ok":
                raise RuntimeError(answer.get("error") or f"status {answer.get('status')}")
            changed(z2m_id)
    finally:
        for unsubscribe in unsubscribes:
            unsubscribe()
        for transaction in transactions:
            pending.pop(transaction, None)


async def publish(hass: HomeAssistant, mqtt_topic: str, payload: dict) -> None:
    await mqtt.async_publish(hass, mqtt_topic, json.dumps(payload))


def first_payload(future: asyncio.Future[str]) -> Callable[[mqtt.ReceiveMessage], None]:
    """A subscription callback that resolves future with the first message's payload."""

    @callback
    def received(msg: mqtt.ReceiveMessage) -> None:
        if not future.done():
            future.set_result(msg.payload)

    return received


async def wait(future: asyncio.Future[Any], timeout: float, what: str) -> Any:
    """The future's result, or TimeoutError(what) when it takes longer than timeout."""
    try:
        async with asyncio.timeout(timeout):
            return await future
    except TimeoutError:
        raise TimeoutError(what) from None


async def state_reply(hass: HomeAssistant, target: Target) -> tuple[asyncio.Future[None] | None, Callable[[], None]]:
    """A future for Z2M's next state publish for the target, subscribed before the caller publishes, and its
    unsubscribe; no future when the target has no state topic or the subscribe failed."""
    if (light_topic := state_topic(target)) is None:
        return None, lambda: None
    published: asyncio.Future[None] = hass.loop.create_future()

    @callback
    def received(msg: mqtt.ReceiveMessage) -> None:
        # A retained message is old state the broker resends on subscribe, not Z2M's answer.
        if not msg.retain and not published.done():
            published.set_result(None)

    try:
        # HA's own light entity subscribes to this topic, so the subscription is live at once.
        return published, await mqtt.async_subscribe(hass, light_topic, received)
    except Exception as err:  # noqa: BLE001 - each caller goes on without the reply
        _LOGGER.debug("Couldn't subscribe to %s, so Zigbee2MQTT's answer isn't awaited: %s", light_topic, err)
        return None, lambda: None
