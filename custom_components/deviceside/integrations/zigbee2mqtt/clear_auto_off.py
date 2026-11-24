"""Zigbee2MQTT clear_auto_off: disables the persistent auto-off set_auto_off arms (families/sonoff), by one publish of
Z2M's `inching_control_set`. It serves only its classes' own calls (AdapterScope.own_calls_only) and refuses every other
class as not built."""

from typing import ClassVar

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .adapter import Z2MAdapter
from .addressing import not_addressable
from .classes import class_scope
from ...core.adapter import OwnCallsOnly
from ...core.models import Request, Target
from ...core.scope import AdapterScope, verified


class Z2MClearAutoOff(OwnCallsOnly, Z2MAdapter[Request]):
    """Disable a device's own auto-off; its own call goes out under the set check (Z2MAdapter.execute_own), so a set
    Zigbee2MQTT logs as failed is `rejected`, else `sent`: the setting can't be read back."""

    action: ClassVar[str] = "clear_auto_off"
    integration: ClassVar[str] = "zigbee2mqtt"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=verified(Platform.LIGHT, Platform.SWITCH),
        **class_scope("clear_auto_off"),
        own_calls_only=True,
        confirmable=False,
        native_groups=False,
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or not_addressable(hass, target)
