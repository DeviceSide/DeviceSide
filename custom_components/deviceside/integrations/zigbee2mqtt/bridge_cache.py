"""Zigbee2MQTT's bridge topics, subscribed for the entry's life rather than per call.

Each fresh subscription costs a call HA's subscribe cooldown (0.1 s) plus a broker round trip, and a group action
read bridge/groups two or three times in series. Held here instead:

- bridge/devices and bridge/groups, the latest of each as Z2M publishes it (retained, and republished whenever a
  device or group changes, lib/extension/bridge.ts), parsed once per payload.
- The options response topics, routed to whichever `ensure_options` call is waiting on the reply's transaction.

The response topics carry no retained message, so nothing shows they are live; the retained bridge/state, subscribed
after them, does. Queued after them, it reaches the broker in their batch or a later one (HA sends a batch once the
last is acknowledged), and on a reconnect HA resubscribes in topic order, which puts bridge/state after them too: its
arrival shows they are subscribed (PR #69's barrier, made once per connection rather than per call). A disconnect
clears everything until the resubscribe brings it back, so a cache whose subscriptions died with the MQTT client reads
fresh, as before.

bridge/info is never held: its values must be fresh, and its arrival is each call's barrier for its own subscriptions.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .addressing import bridge_topic
from ...core.runtime import DATA

_LOGGER = logging.getLogger(__name__)

_KEY = "zigbee2mqtt_bridge_cache"
HELD = ("devices", "groups")
KINDS = ("device", "group")
# Retained by Z2M ("online"), and after the response topics in both subscribe orders.
_BARRIER = "state"


class BridgeCache:
    """The held bridge topics, and the options replies awaited by transaction."""

    def __init__(self) -> None:
        self._payloads: dict[str, str] = {}
        self._parsed: dict[str, tuple[str, Any]] = {}
        self.pending: dict[str, asyncio.Future[dict]] = {}
        # Whether the response topics are subscribed, so a request's reply reaches `pending`.
        self.replies_live = False
        self._unsubscribes: list[Callable[[], None]] = []

    def parsed(self, suffix: str) -> Any | None:
        """The latest bridge/<suffix>, parsed once per payload; None when none has arrived since the last connect."""
        if (payload := self._payloads.get(suffix)) is None:
            return None
        memo = self._parsed.get(suffix)
        if memo is None or memo[0] is not payload:
            memo = self._parsed[suffix] = (payload, json.loads(payload))
        return memo[1]

    def _keeper(self, suffix: str) -> Callable[[mqtt.ReceiveMessage], None]:
        @callback
        def received(msg: mqtt.ReceiveMessage) -> None:
            # An empty payload clears a retained topic.
            if msg.payload:
                self._payloads[suffix] = msg.payload
            else:
                self._payloads.pop(suffix, None)

        return received

    @callback
    def _on_barrier(self, _msg: mqtt.ReceiveMessage) -> None:
        self.replies_live = True

    @callback
    def _on_connection(self, connected: bool) -> None:
        if not connected:
            self.replies_live = False
            self._payloads.clear()
            self._parsed.clear()

    @callback
    def stop(self) -> None:
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()
        self.replies_live = False
        self._payloads.clear()
        self._parsed.clear()

    async def subscribe(self, hass: HomeAssistant) -> None:
        # In this order, so the barrier follows the response topics in HA's batch.
        for kind in KINDS:
            self._unsubscribes.append(
                await mqtt.async_subscribe(hass, bridge_topic(f"response/{kind}/options"), reply_router(self.pending))
            )
        for suffix in HELD:
            self._unsubscribes.append(await mqtt.async_subscribe(hass, bridge_topic(suffix), self._keeper(suffix)))
        self._unsubscribes.append(await mqtt.async_subscribe(hass, bridge_topic(_BARRIER), self._on_barrier))
        self._unsubscribes.append(mqtt.async_subscribe_connection_status(hass, self._on_connection))


def reply_router(pending: dict[str, asyncio.Future[dict]]) -> Callable[[mqtt.ReceiveMessage], None]:
    """A response-topic callback resolving the pending future of the reply's transaction; others are ignored."""

    @callback
    def received(msg: mqtt.ReceiveMessage) -> None:
        try:
            answer = json.loads(msg.payload)
        except ValueError:
            return
        if isinstance(answer, dict) and (reply := pending.get(answer.get("transaction"))) and not reply.done():
            reply.set_result(answer)

    return received


def get(hass: HomeAssistant) -> BridgeCache | None:
    """The running cache, or None before MQTT is up, after unload, or outside an entry (a test, a removal)."""
    if (runtime := hass.data.get(DATA)) is None:
        return None
    return runtime.integration_state.get(_KEY)


async def async_setup(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Hold the bridge topics once MQTT is set up, until the entry unloads. Runs as the entry's background task."""
    if not await mqtt.async_wait_for_mqtt_client(hass):
        return
    cache = BridgeCache()
    state = hass.data[DATA].integration_state

    @callback
    def unload() -> None:
        cache.stop()
        if state.get(_KEY) is cache:
            del state[_KEY]

    # Before subscribing, so an unload mid-way still drops what was subscribed.
    entry.async_on_unload(unload)
    try:
        await cache.subscribe(hass)
    except Exception as err:  # noqa: BLE001 - each caller reads fresh, as without the cache
        _LOGGER.warning("Couldn't subscribe to Zigbee2MQTT's bridge, so each action reads it fresh: %s", err)
        cache.stop()
        return
    state[_KEY] = cache
