"""ZHA get_attributes: on/off timer, brightness, color temperature and color, read live off each light."""

from typing import ClassVar

from homeassistant.core import HomeAssistant

from . import zcl
from .addressing import address, unsupported_reason
from ...core.adapter import Adapter
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope, experimental, verified
from ...core.zcl_row import zcl_row

_COLOR_MODES = frozenset({"color_temp", "hs", "xy"})

_COLOR_ATTRIBUTES = (
    zcl.CURRENT_HUE,
    zcl.CURRENT_SATURATION,
    zcl.CURRENT_X,
    zcl.CURRENT_Y,
    zcl.COLOR_TEMPERATURE,
    zcl.ENHANCED_CURRENT_HUE,
    zcl.ENHANCED_COLOR_MODE,
)


# Each read attribute under zigbee-herdsman's name, which zcl_row takes.
_NAMES = {
    zcl.ON_OFF_CLUSTER: {zcl.ON_OFF: "onOff", zcl.ON_TIME: "onTime"},
    zcl.LEVEL_CLUSTER: {zcl.CURRENT_LEVEL: "currentLevel"},
    zcl.COLOR_CLUSTER: {
        zcl.COLOR_MODE: "colorMode",
        zcl.CURRENT_HUE: "currentHue",
        zcl.CURRENT_SATURATION: "currentSaturation",
        zcl.CURRENT_X: "currentX",
        zcl.CURRENT_Y: "currentY",
        zcl.COLOR_TEMPERATURE: "colorTemperature",
        zcl.ENHANCED_CURRENT_HUE: "enhancedCurrentHue",
        zcl.ENHANCED_COLOR_MODE: "enhancedColorMode",
    },
}


def named(cluster_id: int, read: dict[int, int]) -> dict[str, int]:
    """A read keyed by attribute ID, under zigbee-herdsman's names."""
    names = _NAMES[cluster_id]
    return {names[attribute]: value for attribute, value in read.items() if attribute in names}


class ZHAGetAttributes(Adapter[Request]):
    """Read OnOff, then Level and Color as the light's supported_color_modes call for, one request at a time.

    Always live, never zigpy's cache: ZHA doesn't apply color temperature reports, so the cache goes stale after a
    raw command or a bound remote, while a live read mid-transition returns where the light is. The dispatcher
    expands a ZHA group into its members, one row each. A failed read raises, rejecting that light.
    """

    action: ClassVar[str] = "get_attributes"
    integration: ClassVar[str] = "zha"
    scope: ClassVar[AdapterScope] = AdapterScope(
        # Zigbee plugs rarely honor OnTime (see turn_on_for), so a switch's timer may never show: Experimental.
        domains=verified("light") | experimental("switch"),
        max_concurrency=2,
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        async def read(target: Target) -> EntityResult:
            addr = address(target.entry.unique_id)  # supports() refused the targets it can't address
            # supported_color_modes stays in the state while the light is off.
            modes = set(target.state.attributes.get("supported_color_modes") or ()) if target.state else set()
            read = await zcl.read_attributes(hass, addr, zcl.ON_OFF_CLUSTER, (zcl.ON_OFF,), optional=(zcl.ON_TIME,))
            attributes = named(zcl.ON_OFF_CLUSTER, read)
            if modes - {"onoff"}:
                read = await zcl.read_attributes(hass, addr, zcl.LEVEL_CLUSTER, (zcl.CURRENT_LEVEL,))
                attributes |= named(zcl.LEVEL_CLUSTER, read)
            if modes & _COLOR_MODES:
                read = await zcl.read_attributes(
                    hass, addr, zcl.COLOR_CLUSTER, (zcl.COLOR_MODE,), optional=_COLOR_ATTRIBUTES
                )
                attributes |= named(zcl.COLOR_CLUSTER, read)
            # In a hue mode the bulb's own x and y win, as ZHA shows them in every mode but color temperature.
            return self.result(target, Status.CONFIRMED, data=zcl_row(attributes, xy_first=True))

        return await self.gather(hass, targets, read)
