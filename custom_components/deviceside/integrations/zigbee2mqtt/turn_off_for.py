"""Zigbee2MQTT turn_off_for: only Tuya's datapoint countdown, one publish `{"state": "OFF", "countdown": N}`, which the
device toggles back on at zero (families/tuya/datapoint.py). No other Zigbee device has a call for it, so the adapter
serves only its classes' own calls (AdapterScope.own_calls_only) and refuses every other class as not built."""

from typing import ClassVar

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .adapter import Z2MAdapter
from .addressing import not_addressable
from .classes import class_scope
from ...core.adapter import OwnCallsOnly
from ...core.models import Target, TimedRequest
from ...core.scope import AdapterScope, verified


class Z2MTurnOffFor(OwnCallsOnly, Z2MAdapter[TimedRequest]):
    """Turn a Tuya datapoint device off for a duration by its countdown; its own call goes out under the set check
    (Z2MAdapter.execute_own), so a set Zigbee2MQTT logs as failed is `rejected`, else `sent`."""

    action: ClassVar[str] = "turn_off_for"
    integration: ClassVar[str] = "zigbee2mqtt"
    scope: ClassVar[AdapterScope] = AdapterScope(
        # The class decides the level: the datapoint classes are in Labs (families/tuya).
        domains=verified(Platform.LIGHT, Platform.SWITCH),
        # The datapoint classes' own calls, each with its limits; every other class is out of scope.
        **class_scope("turn_off_for"),
        own_calls_only=True,
        confirmable=False,
        # A Z2M group's call isn't the countdown, so a group falls back to its members.
        native_groups=False,
    )

    def supports(self, hass: HomeAssistant, request: TimedRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or not_addressable(hass, target)
