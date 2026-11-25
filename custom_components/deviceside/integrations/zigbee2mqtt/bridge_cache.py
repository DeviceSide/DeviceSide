"""Zigbee2MQTT's bridge topics, subscribed for the entry's life rather than per call: one cache per instance (base
topic), as each has its own bridge topics, and its group IDs and friendly names mean nothing on another's.
The caches follow HA's registry (addressing.follow_bases), so an instance added or removed while HA runs gets or loses
its own (docs/integrations/zigbee2mqtt/internals.md#addressing).

Each fresh subscription costs a call HA's subscribe cooldown (0.1 s) plus a broker round trip, and a group action
read bridge/groups two or three times in series. Held here instead:

- bridge/devices, bridge/groups and bridge/info, the latest of each as Z2M publishes it, parsed once per payload. All
  three are retained; Z2M republishes devices and groups whenever a device or group changes (lib/extension/bridge.ts),
  and info on every settings change and on start, so a user's change of an option reaches the cache (probe in
  docs/integrations/zigbee2mqtt/internals.md#tested-behavior).
- The options response topics, routed to whichever `ensure_options` call is waiting on the reply's transaction.
- bridge/logging, whose error lines go to whichever calls listen (`listen_log`): a set's failure is logged there and
  nowhere else (set_check.py). Each line is parsed only while a call listens.

The response topics and bridge/logging carry no retained message, so nothing shows they are live; the retained
bridge/state, subscribed after them, does. Queued after them, it reaches the broker in their batch or a later one
(HA sends a batch once the last is acknowledged), and on a reconnect HA resubscribes in topic order, which puts
bridge/state after them too: its arrival shows they are subscribed (PR #69's barrier, made once per connection rather
than per call). A disconnect clears everything until the resubscribe brings it back, so a cache whose subscriptions
died with the MQTT client reads fresh, as before.

Z2M republishes bridge/info just before it answers an options request (microseconds apart on the rig), so the held
bridge/info usually has the new value by the time the reply arrives. Nothing promises that order, so `ensure_options`
also writes each confirmed entity's options through to `confirmed` (the reply's `data.to`, else what it sent over the
options before), which `settings` reads over bridge/info's. Z2M writes the setting before it publishes either, so any
bridge/info arriving later holds it too: each new one drops the overlay.
"""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .addressing import bridge_topic, follow_bases
from ...core.errors import describe
from ...core.runtime import DATA

_LOGGER = logging.getLogger(__name__)

_KEY = "zigbee2mqtt_bridge_caches"  # {base topic: BridgeCache}, the running ones
HELD = ("devices", "groups", "info")
KINDS = ("device", "group")
# Retained by Z2M ("online"), and after the response topics in both subscribe orders.
_BARRIER = "state"
LOG = "logging"


class BridgeCache:
    """The held bridge topics, and the options replies awaited by transaction."""

    def __init__(self, base: str, on_online: Callable[[str], None] = lambda _base: None) -> None:
        self.base = base  # of the Zigbee2MQTT instance whose bridge topics this holds
        self._on_online = on_online
        self._payloads: dict[str, str] = {}
        self._parsed: dict[str, tuple[str, Any]] = {}
        # bridge/devices by IEEE address, for the parsed list it was built from.
        self._devices: tuple[Any, dict[str, dict]] | None = None
        self.pending: dict[str, asyncio.Future[dict]] = {}
        # Options Z2M confirmed since its last bridge/info, by (section, Z2M ID): Z2M's whole options after the write.
        self.confirmed: dict[tuple[str, str], dict] = {}
        # Whether the response topics and bridge/logging are subscribed, so a request's reply reaches `pending` and a
        # log line the listeners.
        self.replies_live = False
        # Set once a bridge/devices that parses has arrived since the last connect (capability_ready).
        self.devices_ready = asyncio.Event()
        self._log_listeners: list[Callable[[str], None]] = []
        self._unsubscribes: list[Callable[[], None]] = []

    def parsed(self, suffix: str) -> Any | None:
        """The latest bridge/<suffix>, parsed once per payload; None when none has arrived since the last connect, or
        the latest doesn't parse (the caller reads fresh, which raises TimeoutError on it as on no message)."""
        if (payload := self._payloads.get(suffix)) is None:
            return None
        memo = self._parsed.get(suffix)
        if memo is None or memo[0] is not payload:
            try:
                parsed = json.loads(payload)
            except ValueError:
                # Not the payload: it opens with a device's IEEE and friendly name (docs/logging.md).
                _LOGGER.debug("Zigbee2MQTT's bridge/%s doesn't parse (%d characters)", suffix, len(payload))
                parsed = None
            memo = self._parsed[suffix] = (payload, parsed)
        return memo[1]

    def device(self, ieee: str) -> dict | None:
        """A device's entry in the held bridge/devices, by IEEE address, indexed once per payload: the classifier reads
        its Zigbee strings (classes.py). None while no bridge/devices is held, or when it doesn't list the device.
        Shared with every caller: read it, never change it."""
        if not isinstance(devices := self.parsed("devices"), list):
            return None
        if self._devices is None or self._devices[0] is not devices:
            index = {
                d["ieee_address"]: d for d in devices if isinstance(d, dict) and isinstance(d.get("ieee_address"), str)
            }
            self._devices = (devices, index)
        return self._devices[1].get(ieee)

    def settings(self, section: str, z2m_id: str) -> dict | None:
        """An entity's options: confirmed since the last bridge/info, else bridge/info's own; None when no bridge/info
        is held. Shared with every caller: read it, never change it."""
        if (info := self.parsed("info")) is None:
            return None
        if (options := self.confirmed.get((section, z2m_id))) is not None:
            return options
        return info.get("config", {}).get(section, {}).get(z2m_id, {})

    def _keeper(self, suffix: str) -> Callable[[mqtt.ReceiveMessage], None]:
        @callback
        def received(msg: mqtt.ReceiveMessage) -> None:
            # An empty payload clears a retained topic.
            if msg.payload:
                self._payloads[suffix] = msg.payload
            else:
                self._payloads.pop(suffix, None)
            if suffix == "info":
                self.confirmed.clear()
            if suffix == "devices" and self.parsed("devices") is not None:
                self.devices_ready.set()

        return received

    def listen_log(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """Call listener with the message of each error line Z2M logs, until the returned callable is called."""
        self._log_listeners.append(listener)
        return lambda: self._log_listeners.remove(listener)

    @callback
    def _on_log(self, msg: mqtt.ReceiveMessage) -> None:
        if self._log_listeners and (message := log_error(msg.payload)) is not None:
            for listener in list(self._log_listeners):
                listener(message)

    @callback
    def _on_barrier(self, msg: mqtt.ReceiveMessage) -> None:
        self.replies_live = True
        if _says_online(msg.payload):
            self._on_online(self.base)

    @callback
    def _on_connection(self, connected: bool) -> None:
        if not connected:
            self._clear()

    @callback
    def stop(self) -> None:
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()
        self._clear()

    def _clear(self) -> None:
        self.replies_live = False
        self.devices_ready.clear()
        self._payloads.clear()
        self._parsed.clear()
        self.confirmed.clear()

    async def subscribe(self, hass: HomeAssistant) -> None:
        # In this order, so the barrier follows the response topics and the log in HA's batch.
        for kind in KINDS:
            self._unsubscribes.append(
                await mqtt.async_subscribe(
                    hass, bridge_topic(self.base, f"response/{kind}/options"), reply_router(self.pending)
                )
            )
        self._unsubscribes.append(await mqtt.async_subscribe(hass, bridge_topic(self.base, LOG), self._on_log))
        for suffix in HELD:
            self._unsubscribes.append(
                await mqtt.async_subscribe(hass, bridge_topic(self.base, suffix), self._keeper(suffix))
            )
        self._unsubscribes.append(await mqtt.async_subscribe(hass, bridge_topic(self.base, _BARRIER), self._on_barrier))
        self._unsubscribes.append(mqtt.async_subscribe_connection_status(hass, self._on_connection))


def _says_online(payload: str) -> bool:
    """Whether a bridge/state payload says online: JSON `{"state": "online"}`, or the bare string of older Z2M."""
    if payload == "online":
        return True
    try:
        state = json.loads(payload)
    except ValueError:
        return False
    return isinstance(state, dict) and state.get("state") == "online"


def log_error(payload: str) -> str | None:
    """The message of a bridge/logging line at error level; None for any other level, or a line that doesn't parse."""
    try:
        entry = json.loads(payload)
        if entry.get("level") == "error" and isinstance(message := entry["message"], str):
            return message
    except ValueError, TypeError, KeyError, AttributeError:
        pass
    return None


# A failed ZCL command, as Z2M logs it: `... ZCL command <address> <cluster>.<command>(<payload>) failed (<cause>)`,
# the address a device's <ieee>/<endpoint> or a group's number.
_ZCL_FAILURE = re.compile(r"ZCL command \S+ (?P<call>\w+\.\w+)\(.*\) failed \((?P<cause>.*)\)'?$")
# Any other failed set: `Publish 'set' '<key>' to '<friendly name>' failed: '<error>'`.
_SET_FAILURE = re.compile(r"^Publish '\w+' '[^']*' to '(?P<name>.*?)' failed: '?(?:Error: )?(?P<error>.*?)'?$")
# The shapes Z2M and herdsman address a device or group in: a bracketed sender (`[ZCL GROUP groupId=7]`), the network
# address a delivery failed for (`for '<nwk>'`), the address fields of herdsman's timeout (`Timeout - <nwk> - <ep> -
# <tsn> - <cluster> - <command> after 10000ms`), an IEEE with its endpoint, and a group's number. Only these: the
# rest of a cause, quoted text and codes included (`'MAC no ack' (233)`), is the diagnosis.
_ADDRESSING = (
    (re.compile(r"~x~>\s*|\s*\[[^\]]*\]"), ""),
    (re.compile(r" for '\d+'"), ""),
    (re.compile(r"\bTimeout(?: - \d+)+"), "Timeout"),
    (re.compile(r"0x[0-9a-fA-F]{16}(?:/\d+)?"), "<device>"),
    (re.compile(r"\bgroupId=\d+"), "groupId=<group>"),
)


def scrub(text: str, *names: str, label: str = "device") -> str:
    """text Z2M wrote, for a log line (docs/logging.md): the addressing Z2M and herdsman put in it taken out, and each
    of names (a friendly name, the id a request used) replaced by <label> where Z2M names a device by it: quoted, or
    ahead of an endpoint (`lamp/11`). A bare word elsewhere is left, as a name can be one (`on`)."""
    for name in names:
        if name:
            text = text.replace(f"'{name}'", f"'<{label}>'")
            text = re.sub(rf"(?<![\w/]){re.escape(name)}/(?=\d)", f"<{label}>/", text)
    for pattern, replacement in _ADDRESSING:
        text = pattern.sub(replacement, text)
    return text.strip()


def cause(message: str) -> str:
    """What a Z2M failure line says went wrong (`genOnOff.read failed (UNSUPPORTED_ATTRIBUTE)`), for a log line.

    The line names the device by friendly name, IEEE or group number, which a log line never does, so it is never
    logged whole: a ZCL failure gives its call and cause, another failed set its error, each scrubbed. A line in a
    shape this doesn't know gives a generic phrase rather than its text.
    """
    if (match := _ZCL_FAILURE.search(message)) is not None:
        return f"{match['call']} failed ({scrub(match['cause'])})"
    if (match := _SET_FAILURE.match(message)) is not None:
        return scrub(match["error"], match["name"])
    return "a failure DeviceSide doesn't parse"


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


def get(hass: HomeAssistant, base: str) -> BridgeCache | None:
    """The running cache of the instance on this base topic, or None: before MQTT is up or its subscribe is done, when
    HA knows no bridge of it, after unload, or outside an entry (a test, a removal)."""
    if (runtime := hass.data.get(DATA)) is None:
        return None
    return runtime.integration_state.get(_KEY, {}).get(base)


def capability_ready(hass: HomeAssistant) -> Awaitable[None] | None:
    """Zigbee2MQTT's IntegrationInfo.capability_ready: a device is placed only once bridge/devices lists it
    (classes.placed), so None once every running cache holds one; else an awaitable that completes when they all do.
    A bridge with no cache yet (MQTT not up) isn't waited on: nothing says when its cache will start."""
    if (runtime := hass.data.get(DATA)) is None:
        return None
    waiting = [cache for cache in runtime.integration_state.get(_KEY, {}).values() if not cache.devices_ready.is_set()]
    return _devices_listed(waiting) if waiting else None


async def _devices_listed(caches: list[BridgeCache]) -> None:
    await asyncio.gather(*(cache.devices_ready.wait() for cache in caches))


async def async_setup(
    hass: HomeAssistant, entry: ConfigEntry, on_online: Callable[[str], None] = lambda _base: None
) -> None:
    """Hold each instance's bridge topics once MQTT is set up, until the entry unloads: one cache per base topic in
    addressing.bridge_bases, started and stopped as HA's registry gains and loses bridge entities (follow_bases).
    Runs as the entry's background task.

    Calls on_online, with the base topic, each time an instance's bridge/state says online, its retained message
    included, so at startup and whenever Z2M comes back.
    """
    if not await mqtt.async_wait_for_mqtt_client(hass):
        return
    entry.async_on_unload(follow_bases(hass, entry, partial(_start, hass, on_online), "bridge cache"))


async def _start(hass: HomeAssistant, on_online: Callable[[str], None], base: str) -> Callable[[], None]:
    """Subscribe a cache for the instance on this base topic and list it for get(); returns its stop."""
    cache = BridgeCache(base, on_online)
    try:
        await cache.subscribe(hass)
    except Exception as err:  # noqa: BLE001 - each caller reads fresh, as without the cache
        # Without the cache, a group's members can't be listed sync (members.expand_group), so every group counts
        # as a Labs item, and turn_on_for refuses it and every device but a Hue one for good (classes.placed).
        _LOGGER.warning(
            "Couldn't subscribe to Zigbee2MQTT's bridge, so each action reads it fresh, Zigbee2MQTT groups run "
            "only with Labs on, and turn on with timer refuses them and every device but Hue's: %s",
            describe(err),
        )
        cache.stop()
        return lambda: None
    except BaseException:
        # Cancelled: its bridge went, or the entry unloads, mid-subscribe.
        cache.stop()
        raise
    caches: dict[str, BridgeCache] = hass.data[DATA].integration_state.setdefault(_KEY, {})
    caches[base] = cache

    @callback
    def stop() -> None:
        cache.stop()
        if caches.get(base) is cache:
            del caches[base]

    return stop
