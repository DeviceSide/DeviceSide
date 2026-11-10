"""Live ZCL attribute reads through Zigbee2MQTT's generic `read` payload, one cluster at a time.

Z2M publishes a read's result only in the device's state, under the payload's state_property. Every state publish
carries Z2M's whole cached state, deep-merged, so a key it caches would ride in every later publish holding a past
read, and each read itself is preceded by one such publish. The key is therefore kept out of the cache with the
device's filtered_cache option, which `reader` adds first: then only a read's own reply carries it.

A read also updates the state Z2M keeps from the attributes it reads, as a report would: reading CurrentLevel sets
Z2M's brightness.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from homeassistant.components import mqtt
from homeassistant.components.light import ColorMode, brightness_supported
from homeassistant.core import HomeAssistant, callback

from . import bridge
from .addressing import bridge_topic, state_topic, topic, z2m_address
from .bridge import ensure_options, first_payload, publish, wait
from ...core.models import Target

_LOGGER = logging.getLogger(__name__)

READ_KEY = "deviceside_read"
_FILTERED_CACHE = "filtered_cache"
# Z2M publishes a reply within a quarter second when the bulb answers; the same wait as turn_on_for's state.
_REPLY_TIMEOUT_S = 5.0
# What Z2M's error line says when the coordinator's frame went unacknowledged: ... failed (Delivery failed for '1').
_DELIVERY_FAILED = "Delivery failed"


class DeliveryFailed(RuntimeError):
    """Z2M logged a read as undelivered: routine radio noise on a busy mesh, so a read is tried once more."""


def clusters(target: Target) -> dict[str, list[str]]:
    """The clusters and attributes to read for a light, by its supported color modes.

    One unsupported attribute fails a cluster's whole read, so only the color mode's own are asked for: a color
    temperature bulb has no hue or saturation, and some have no EnhancedColorMode.
    """
    modes = set((target.state and target.state.attributes.get("supported_color_modes")) or ())
    wanted = {"genOnOff": ["onOff", "onTime"]}
    if brightness_supported(modes):
        wanted["genLevelCtrl"] = ["currentLevel"]
    color = []
    if ColorMode.COLOR_TEMP in modes:
        color.append("colorTemperature")
    if ColorMode.XY in modes:
        color += ["currentX", "currentY"]
    if ColorMode.HS in modes:
        color += ["currentHue", "currentSaturation"]
    if color:
        wanted["lightingColorCtrl"] = ["colorMode", *color]
    return wanted


class Reader:
    """Reads devices one after another over one subscription to Z2M's log, which reports a failed read."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._reply: asyncio.Future[tuple[dict, dict]] | None = None
        self._expected: set[str] = set()
        self._failure: tuple[str, ...] = ()  # what Z2M's error line names for the read in flight

    @callback
    def _on_log(self, msg: mqtt.ReceiveMessage) -> None:
        # Z2M logs a failed read as: Publish 'set' 'read' to '<name>' failed: ... ZCL command <ieee>/<endpoint>
        # <cluster>.read([...]) failed (<status>).
        if self._reply is None or self._reply.done():
            return
        try:
            entry = json.loads(msg.payload)
            message = entry["message"]
        except ValueError, TypeError, KeyError:
            return
        if entry.get("level") == "error" and all(part in message for part in self._failure):
            self._reply.set_exception((DeliveryFailed if _DELIVERY_FAILED in message else RuntimeError)(message))

    @callback
    def _on_state(self, msg: mqtt.ReceiveMessage) -> None:
        # A retained message is old state the broker resends on subscribe, not Z2M's answer.
        if msg.retain or self._reply is None or self._reply.done():
            return
        try:
            state = json.loads(msg.payload)
            value = state.get(READ_KEY)
        except ValueError, AttributeError:
            return
        if isinstance(value, dict) and set(value) == self._expected:
            self._reply.set_result((value, state))

    async def read(self, target: Target) -> dict:
        """The light's attributes from every cluster `clusters` names, merged, read one cluster after another.

        CurrentLevel is the light's level as `_level` takes it. Raises when a read fails: at once when Z2M logs the
        error (after one more try when it logs a delivery failure), else after the timeout.
        """
        attributes: dict = {}
        state: dict = {}
        async with self._subscribed(target):
            for cluster, names in clusters(target).items():
                if cluster == "genLevelCtrl":
                    if (level := await self._level(target, attributes["onOff"], state)) is not None:
                        attributes["currentLevel"] = level
                    continue
                reply, state = await self._read(target, cluster, names)
                attributes |= reply
        return attributes

    async def level(self, target: Target) -> int | None:
        """The light's level as `_level` takes it, after reading whether it is on; raises when a read fails."""
        async with self._subscribed(target):
            reply, state = await self._read(target, "genOnOff", ["onOff"])
            return await self._level(target, reply["onOff"], state)

    async def read_cluster(self, target: Target, cluster: str, names: list[str]) -> dict:
        """These attributes of one cluster; raises when the read fails, as read does."""
        async with self._subscribed(target):
            reply, _state = await self._read(target, cluster, names)
        return reply

    async def _level(self, target: Target, on: bool, state: dict) -> int | None:
        """CurrentLevel read live while the light is on; while off, Z2M's brightness from the state of the OnOff reply.

        Z2M's brightness is the level an off light comes back at; the bulb's own isn't. After an off with a transition
        it holds the minimum, and Z2M restores the level it kept on the next on; just after a plain off, a Hue bulb's
        own fade still dims it. Reading it would also overwrite Z2M's brightness with it.
        """
        if not on:
            return state.get("brightness")
        reply, _state = await self._read(target, "genLevelCtrl", ["currentLevel"])
        return reply["currentLevel"]

    @asynccontextmanager
    async def _subscribed(self, target: Target) -> AsyncIterator[None]:
        # HA's light entity already subscribes to the state topic, so this subscription is live at once.
        unsubscribe = await mqtt.async_subscribe(self.hass, state_topic(target), self._on_state)
        try:
            yield
        finally:
            unsubscribe()

    async def _read(self, target: Target, cluster: str, names: list[str]) -> tuple[dict, dict]:
        """The cluster's reply and the state Z2M published it in, over a subscription to the state topic.

        A read Z2M logs as undelivered is sent once more, under the same subscription; any other failure, or a second
        delivery failure, raises.
        """
        try:
            return await self._attempt(target, cluster, names)
        except DeliveryFailed:
            _LOGGER.debug("Read of %s.%s on %s was not delivered; reading once more", cluster, names, target.entity_id)
            return await self._attempt(target, cluster, names)

    async def _attempt(self, target: Target, cluster: str, names: list[str]) -> tuple[dict, dict]:
        self._reply, self._expected = self.hass.loop.create_future(), set(names)
        self._failure = (f"{z2m_address(target.device)}/", f"{cluster}.read(")
        payload = {"read": {"cluster": cluster, "attributes": names, "state_property": READ_KEY}}
        try:
            await publish(self.hass, topic(target, "set"), payload)
            return await wait(self._reply, _REPLY_TIMEOUT_S, f"no {cluster} reply from Zigbee2MQTT")
        finally:
            self._reply = None


@asynccontextmanager
async def reader(hass: HomeAssistant, devices: list[Target]) -> AsyncIterator[Reader]:
    """A Reader for these devices, once each has the read key filtered from Z2M's cache; raises if one can't.

    The key goes into each device's filtered_cache, after the user's own entries.
    """
    reading = Reader(hass)
    # HA debounces subscribes, so the log's subscription isn't live when async_subscribe returns. The retained
    # bridge/state, subscribed next, reaches the broker in the same batch or a later one: its arrival shows the log is
    # subscribed, before the first read. ensure_options may subscribe to nothing (the bridge cache), so it can't be the
    # barrier. A read pays this one subscribe; reads aren't hold-to-dim.
    unsubscribe = await mqtt.async_subscribe(hass, bridge_topic("logging"), reading._on_log)
    try:
        online: asyncio.Future[str] = hass.loop.create_future()
        unsubscribe_state = await mqtt.async_subscribe(hass, bridge_topic("state"), first_payload(online))
        try:
            await wait(online, bridge._RETAINED_TIMEOUT_S, "no bridge/state from Zigbee2MQTT")
        finally:
            unsubscribe_state()
        by_address = {z2m_address(device.device): device for device in devices}

        def added(address: str) -> None:
            _LOGGER.info(
                "Added %s to Zigbee2MQTT's %s for %s, so DeviceSide reads it live",
                READ_KEY,
                _FILTERED_CACHE,
                by_address[address].entity_id,
            )

        await ensure_options(hass, "device", list(by_address), _with_read_key, added)
        yield reading
    finally:
        unsubscribe()


def _with_read_key(options: dict) -> dict:
    cached_out = options.get(_FILTERED_CACHE) or []
    return {} if READ_KEY in cached_out else {_FILTERED_CACHE: [*cached_out, READ_KEY]}
