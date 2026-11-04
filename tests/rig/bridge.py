"""A small Hue bridge client for rig tests: CLIP v2 reads and writes made behind Home Assistant's back. CLIP v2 only:
the v1 API stranded a bulb on old firmware (docs/integration-internals.md, Hue tested behavior).

A rig case uses it to act as another actor (the Hue app, a dimmer, a motion rule), so Device Side sees a change it
did not make and Home Assistant did not send.
"""

import aiohttp

from .profile import normalize_ieee

REQUEST_TIMEOUT_S = 10


class BridgeError(Exception):
    """A bridge write the bridge refused, or could not be made. `status` is the HTTP status, where one came back."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class HueBridge:
    def __init__(self, host: str, app_key: str):
        self.base = f"https://{host}/clip/v2/resource"
        self.headers = {"hue-application-key": app_key}
        self._session: aiohttp.ClientSession | None = None

    async def get(self, resource_type: str, resource_id: str | None = None) -> list[dict]:
        """The resources of a type (or the one with `resource_id`), as CLIP v2's `data` list."""
        return await self._request("GET", resource_type, resource_id)

    async def post(self, resource_type: str, body: dict) -> list[dict]:
        """Create a resource, or run an action such as a device search; returns the bridge's `data` list."""
        return await self._request("POST", resource_type, None, body)

    async def put(self, resource_type: str, resource_id: str, body: dict) -> None:
        """PUT `body` to the resource; raises BridgeError on an HTTP error or any error the bridge lists."""
        await self._request("PUT", resource_type, resource_id, body)

    async def delete(self, resource_type: str, resource_id: str) -> None:
        """Delete a resource. A device delete makes the bridge send the bulb a Leave."""
        await self._request("DELETE", resource_type, resource_id)

    async def device_id_by_ieee(self, ieee: str) -> str | None:
        """The bridge device whose Zigbee connectivity reports `ieee` (any common spelling), or None."""
        wanted = normalize_ieee(ieee)
        for connectivity in await self.get("zigbee_connectivity"):
            if normalize_ieee(connectivity.get("mac_address", "")) == wanted:
                return connectivity["owner"]["rid"]
        return None

    async def _request(self, method: str, resource_type: str, resource_id: str | None, body: dict | None = None):
        if self._session is None:
            # The bridge's certificate is self-signed; the system resolver, as HAClient's, resolves mDNS names.
            connector = aiohttp.TCPConnector(ssl=False, resolver=aiohttp.ThreadedResolver())
            self._session = aiohttp.ClientSession(
                connector=connector, headers=self.headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S)
            )
        name = f"{resource_type}/{resource_id}" if resource_id else resource_type
        url = f"{self.base}/{name}"
        try:
            async with self._session.request(method, url, json=body) as response:
                reply = await response.json(content_type=None)
                status = response.status
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise BridgeError(f"{method} {name}: {type(err).__name__}: {err}") from None
        listed = reply.get("errors", []) if isinstance(reply, dict) else []
        errors = [error.get("description", error) for error in listed]
        if status >= 400 or errors:
            raise BridgeError(f"{method} {name} got {status}: {'; '.join(map(str, errors))}", status)
        return reply.get("data", []) if isinstance(reply, dict) else []

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
