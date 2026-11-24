"""Zigbee2MQTT set_auto_off: a persistent auto-off by inching, which only some Zigbee firmware has (Sonoff's relays,
families/sonoff). It is a setting the device keeps, written by one publish of Z2M's `inching_control_set`. No other
Zigbee device has a call for it, so the adapter serves only its classes' own calls (AdapterScope.own_calls_only) and
refuses every other class as not built."""

from typing import ClassVar

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .adapter import Z2MAdapter
from .addressing import not_addressable
from .classes import class_scope
from ...core.adapter import OwnCallsOnly
from ...core.models import Target, TimedRequest
from ...core.scope import AdapterScope, verified


class Z2MSetAutoOff(OwnCallsOnly, Z2MAdapter[TimedRequest]):
    """Arm a device's own auto-off for a duration; its own call goes out under the set check (Z2MAdapter.execute_own),
    so a set Zigbee2MQTT logs as failed is `rejected`, else `sent`: the setting can't be read back."""

    action: ClassVar[str] = "set_auto_off"
    integration: ClassVar[str] = "zigbee2mqtt"
    scope: ClassVar[AdapterScope] = AdapterScope(
        # The class decides the level: the inching classes are in Labs (families).
        domains=verified(Platform.LIGHT, Platform.SWITCH),
        **class_scope("set_auto_off"),
        own_calls_only=True,
        confirmable=False,
        # A Z2M group's call isn't the composite, so a group falls back to its members.
        native_groups=False,
    )

    def supports(self, hass: HomeAssistant, request: TimedRequest, target: Target) -> str | None:
        return super().supports(hass, request, target) or not_addressable(hass, target)
