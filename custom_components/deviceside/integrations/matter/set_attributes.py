"""Matter set_attributes: Level and Color Control MoveTo commands with the ExecuteIfOff override, so a light that is
off stores the values and stays off, then a read of the attributes that confirms what the light kept.

It reads back because a light answers SUCCESS to a command the ExecuteIfOff gate blocked, and some ignore the stored
level on the next On; an OnLevel the user set wins over it by the spec (docs/integrations/matter/internals.md,
set_attributes)."""

import asyncio
import logging
from dataclasses import dataclass
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
    EXECUTE_IF_OFF,
    color_path,
    level_path,
    light_reason,
    make_command,
    matter_client,
    node_id_from_unique_id,
    on_level_path,
    onoff_endpoint,
)
from .classes import LIGHT_ACTIONS
from .fade import cancel_restore, light_lock
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
    XY_SCALE,
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

# The write fade is core/zcl.py's, so a call looks alike on every transport; ExecuteIfOff is addressing's.
_OPTIONS = {"transitionTime": WRITE_FADE_TENTHS, **EXECUTE_IF_OFF}
# A light reads a value back within one step of the one sent: it rounds to its own resolution.
_STEP = 1

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
            fields = {"colorX": round(x * XY_SCALE), "colorY": round(y * XY_SCALE)}
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
                ("CurrentX", color_path(ep_id, CURRENT_X), round(x * XY_SCALE)),
                ("CurrentY", color_path(ep_id, CURRENT_Y), round(y * XY_SCALE)),
            ]
        case MoveToHueAndSaturation(hue, saturation):
            return [
                ("CurrentHue", color_path(ep_id, CURRENT_HUE), hue),
                ("CurrentSaturation", color_path(ep_id, CURRENT_SATURATION), saturation),
            ]


@dataclass(frozen=True, slots=True)
class _Sent:
    """What a light's read-back needs once its commands went out: what to compare, and whether OnLevel is read."""

    client: object
    node_id: int
    ep_id: int
    expected: list[Expected]
    off_with_level: bool
    dropped: bool


def _kept(read: object, sent: int) -> bool:
    return isinstance(read, int) and not isinstance(read, bool) and abs(read - sent) <= _STEP


class MatterSetAttributes(Adapter[SetAttributesRequest]):
    """Send each light its MoveTo commands one after another, never the WithOnOff variants, then read the attributes.

    The ExecuteIfOff override makes a light that is off store the values and stay off (the research file's
    2026-11-24 Level and Color Control notes: docs/integrations/matter/research/2026-11-24-level-color.md).
    The light is CONFIRMED when CurrentLevel and the color attributes read within one step of what was sent, read
    WRITE_FADE_WAIT_S after every light's commands went out so a mid-fade value isn't read (the wait holds no
    concurrency slot); otherwise SENT with
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
        return super().supports(hass, request, target) or light_reason(hass, target)

    async def execute(
        self, hass: HomeAssistant, request: SetAttributesRequest, targets: list[Target]
    ) -> list[EntityResult]:
        # Two passes (plan Decision 14): each light's commands in its slot, then one wait outside every slot, then
        # each light's read-back in a slot of its own, so a slot isn't held through the wait.
        sent: dict[str, _Sent] = {}

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
                # Nothing is sent yet, so a read that fails raises and rejects the light, as on ZHA.
                current_level = (await client.read_attribute(node_id=node_id, attribute_path=path))[path]
            commands_sent, dropped = commands(request, modes, attrs, current_level)
            if not commands_sent:
                return self.result(target, Status.UNCHANGED, detail="fields_dropped" if dropped else "within_limits")
            if any(isinstance(command, MoveToLevel) for command in commands_sent):
                # A level of ours supersedes a soft off's pending restore, which would put the start level back over it.
                cancel_restore(hass, target.entity_id)
            for command in commands_sent:
                cluster, name, fields = _wire(command)
                _LOGGER.debug("%s: sending matter %s.%s %s", target.reported_id, cluster, name, fields)
                await client.send_device_command(
                    node_id=node_id, endpoint_id=ep_id, command=make_command(cluster, name, **fields)
                )
            # OnLevel decides only the level the next On comes up at: it matters to a write that sets one.
            off_with_level = (
                target.state is not None
                and target.state.state == STATE_OFF
                and any(isinstance(command, MoveToLevel) for command in commands_sent)
            )
            expected = [item for command in commands_sent for item in _expected(command, ep_id)]
            sent[target.reported_id] = _Sent(client, node_id, ep_id, expected, off_with_level, dropped)
            # Replaced by the read-back's result below.
            return self.result(target, Status.SENT)

        # Under the light's lock, so a soft off's restore job can't run between the cancel and the send.
        results = await self.gather(hass, targets, send, hold=lambda target: light_lock(hass, target))
        if not sent:
            return results
        await asyncio.sleep(WRITE_FADE_WAIT_S)
        read_backs = await self.gather(
            hass,
            [target for target in targets if target.reported_id in sent],
            lambda target: self._read_back(target, sent[target.reported_id]),
        )
        by_id = {result.entity_id: result for result in read_backs}
        return [by_id.get(result.entity_id, result) for result in results]

    async def _read_back(self, target: Target, light: _Sent) -> EntityResult:
        on_level = on_level_path(light.ep_id)

        async def read(_: Target) -> dict[str, object]:
            paths = [path for _, path, _ in light.expected] + ([on_level] if light.off_with_level else [])
            values = await asyncio.gather(
                *(light.client.read_attribute(node_id=light.node_id, attribute_path=path) for path in paths)
            )
            return {path: value.get(path) for path, value in zip(paths, values, strict=True)}

        def judge(values: dict[str, object]) -> EntityResult:
            return self._judge(target, values, light.expected, on_level, light.dropped)

        return await read_back(self, target, read, judge)

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
