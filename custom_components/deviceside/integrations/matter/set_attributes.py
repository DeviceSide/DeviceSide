"""Matter set_attributes: Level and Color Control MoveTo commands with the ExecuteIfOff override, so a light that is
off stores the values and stays off, then a read of the attributes that confirms what the light kept."""

import asyncio
import logging
from typing import ClassVar

from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_XY_COLOR,
)
from homeassistant.const import STATE_OFF, Platform
from homeassistant.core import HomeAssistant

from .addressing import (
    color_path,
    has_level,
    level_path,
    make_command,
    matter_client,
    node_for,
    node_id_from_unique_id,
    on_level_path,
    onoff_endpoint,
    unsupported_reason,
)
from .classes import LIGHT_ACTIONS
from ...actions.set_attributes import LIMITS, SetAttributesRequest
from ...core.adapter import Adapter
from ...core.fields import BRIGHTNESS_FIELD
from ...core.models import EntityResult, Status, Target
from ...core.readback import read_back
from ...core.scope import AdapterScope, labs
from ...core.zcl import (
    COLOR_TEMPERATURE,
    CURRENT_HUE,
    CURRENT_SATURATION,
    CURRENT_X,
    CURRENT_Y,
    WRITE_FADE_TENTHS,
    WRITE_FADE_WAIT_S,
)
from ...core.zcl_write import (
    Command,
    MoveToColor,
    MoveToColorTemp,
    MoveToHueAndSaturation,
    MoveToLevel,
    commands,
    wants_level,
)

_LOGGER = logging.getLogger(__name__)

# The write fade is core/zcl.py's, so a call looks alike on every transport. OptionsMask and OptionsOverride of 1 set
# the Options bitmap's ExecuteIfOff bit for this command only: a light that is off stores the value and stays off.
_OPTIONS = {"transitionTime": WRITE_FADE_TENTHS, "optionsMask": 1, "optionsOverride": 1}
# A light reads a value back within one step of the one sent: it rounds to its own resolution.
_STEP = 1
# ColorControl's CurrentX and CurrentY are the CIE coordinate times 65536 (spec 3.2.7.5).
_XY_SCALE = 65535

Wire = tuple[str, str, dict[str, int]]
# What read-back compares: (attribute name for the log, path, value sent).
Expected = tuple[str, str, int]


def _wire(command: Command) -> Wire:
    """The command as (cluster, command, fields), with the fade and the override."""
    match command:
        case MoveToLevel(level):
            return "LevelControl", "MoveToLevel", {"level": level, **_OPTIONS}
        case MoveToColorTemp(mireds):
            return "ColorControl", "MoveToColorTemperature", {"colorTemperatureMireds": mireds, **_OPTIONS}
        case MoveToColor(x, y):
            fields = {"colorX": round(x * _XY_SCALE), "colorY": round(y * _XY_SCALE)}
            return "ColorControl", "MoveToColor", {**fields, **_OPTIONS}
        case MoveToHueAndSaturation(hue, saturation):
            return "ColorControl", "MoveToHueAndSaturation", {"hue": hue, "saturation": saturation, **_OPTIONS}


def _expected(command: Command, ep_id: int) -> list[Expected]:
    """The attributes the command sets, with the values it sent."""
    match command:
        case MoveToLevel(level):
            return [("CurrentLevel", level_path(ep_id), level)]
        case MoveToColorTemp(mireds):
            return [("ColorTemperatureMireds", color_path(ep_id, COLOR_TEMPERATURE), mireds)]
        case MoveToColor(x, y):
            return [
                ("CurrentX", color_path(ep_id, CURRENT_X), round(x * _XY_SCALE)),
                ("CurrentY", color_path(ep_id, CURRENT_Y), round(y * _XY_SCALE)),
            ]
        case MoveToHueAndSaturation(hue, saturation):
            return [
                ("CurrentHue", color_path(ep_id, CURRENT_HUE), hue),
                ("CurrentSaturation", color_path(ep_id, CURRENT_SATURATION), saturation),
            ]


def _kept(read: object, sent: int) -> bool:
    return isinstance(read, int) and not isinstance(read, bool) and abs(read - sent) <= _STEP


class MatterSetAttributes(Adapter[SetAttributesRequest]):
    """Send each light its MoveTo commands one after another, never the WithOnOff variants, then read the attributes.

    The ExecuteIfOff override makes a light that is off store the values and stay off (the research file's
    2026-11-24 Level and Color Control notes: docs/integrations/matter/research/2026-11-24-level-color.md).
    The light is CONFIRMED when CurrentLevel and the color attributes read within one step of what was sent, read
    WRITE_FADE_WAIT_S after the last command so a mid-fade value isn't read; otherwise SENT with
    attributes_not_reported, or readback_failed when a read raised. An off light whose OnLevel is set is SENT with
    on_level_set whatever it reads: the next On goes to OnLevel, not to the values stored (DeviceSide never writes
    OnLevel, a setting of the device's). A field the light can't take is dropped and the result says so, as on Hue.
    """

    action: ClassVar[str] = "set_attributes"
    integration: ClassVar[str] = "matter"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=labs(Platform.LIGHT),
        fields=labs(
            BRIGHTNESS_FIELD,
            ATTR_COLOR_TEMP_KELVIN,
            ATTR_HS_COLOR,
            ATTR_RGB_COLOR,
            ATTR_XY_COLOR,
            *LIMITS,
        ),
        capabilities=LIGHT_ACTIONS,
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: SetAttributesRequest, target: Target) -> str | None:
        if reason := super().supports(hass, request, target) or unsupported_reason(hass, target):
            return reason
        # unsupported_reason found the endpoint and the node.
        node = node_for(hass, target)
        return None if has_level(node, onoff_endpoint(target.entry.unique_id)) else "not_dimmable"

    async def execute(
        self, hass: HomeAssistant, request: SetAttributesRequest, targets: list[Target]
    ) -> list[EntityResult]:
        async def send(target: Target) -> EntityResult:
            node_id = node_id_from_unique_id(target.entry.unique_id)
            ep_id = onoff_endpoint(target.entry.unique_id)
            client = matter_client(hass, target.entry.config_entry_id)  # supports() refused the targets without one
            # supported_color_modes stays in the state while the light is off.
            attrs = dict(target.state.attributes) if target.state else {}
            modes = set(attrs.get(ATTR_SUPPORTED_COLOR_MODES) or ())
            current_level = None
            if wants_level(request, modes):
                path = level_path(ep_id)
                current_level = (await client.read_attribute(node_id=node_id, attribute_path=path)).get(path)
                if not isinstance(current_level, int):
                    return self.result(target, Status.SENT, detail="readback_failed")
            sent, dropped = commands(request, modes, attrs, current_level)
            if not sent:
                return self.result(target, Status.UNCHANGED, detail="fields_dropped" if dropped else "within_limits")
            for command in sent:
                cluster, name, fields = _wire(command)
                _LOGGER.debug("%s: sending matter %s.%s %s", target.reported_id, cluster, name, fields)
                await client.send_device_command(
                    node_id=node_id, endpoint_id=ep_id, command=make_command(cluster, name, **fields)
                )
            expected = [item for command in sent for item in _expected(command, ep_id)]
            off = target.state is not None and target.state.state == STATE_OFF
            await asyncio.sleep(WRITE_FADE_WAIT_S)

            async def read(_: Target) -> dict[str, object]:
                paths = [path for _, path, _ in expected] + ([on_level_path(ep_id)] if off else [])
                return {
                    path: (await client.read_attribute(node_id=node_id, attribute_path=path)).get(path)
                    for path in paths
                }

            def judge(values: dict[str, object]) -> EntityResult:
                return self._judge(target, values, expected, on_level_path(ep_id), dropped)

            return await read_back(self, target, read, judge)

        return await self.gather(hass, targets, send)

    def _judge(
        self, target: Target, values: dict[str, object], expected: list[Expected], on_level: str, dropped: bool
    ) -> EntityResult:
        if values.get(on_level) is not None:
            _LOGGER.debug("%s: OnLevel is %s, so the next on goes to it", target.reported_id, values[on_level])
            return self.result(target, Status.SENT, detail="on_level_set")
        if not all(_kept(values[path], value) for _, path, value in expected):
            _LOGGER.debug(
                "%s: sent %s, read %s",
                target.reported_id,
                {name: value for name, _, value in expected},
                {name: values[path] for name, path, _ in expected},
            )
            return self.result(target, Status.SENT, detail="attributes_not_reported")
        return self.result(target, Status.CONFIRMED, detail="fields_dropped" if dropped else None)
