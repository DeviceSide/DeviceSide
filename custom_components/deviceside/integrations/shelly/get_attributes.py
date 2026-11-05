"""Shelly get_attributes: on/off timer, brightness, color temperature and color from <Component>.GetStatus, and the
persistent auto-off / auto-on from <Component>.GetConfig."""

import asyncio
import logging
from datetime import datetime
from typing import ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .addressing import address, unsupported_reason
from .rpc import get_config, get_status
from ...core.adapter import Adapter
from ...core.color import rgb_row
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope
from ...core.timer import timer_row

_LOGGER = logging.getLogger(__name__)


def status_row(component: str, status: dict, now: datetime) -> dict:
    """One target's row from its GetStatus. The bulb keeps brightness, ct and rgb while off, so they read then too.

    The time left is the device's timer_started_at against HA's clock: both are SNTP-synced, and the clamp to
    [0, duration] bounds any skew.
    """
    row: dict = {}
    if component == "RGBCCT":
        # Brightness is the device's percent, as Hue's row is. The status carries ct and rgb in either mode; only
        # the active one is reported, as core does.
        row["brightness"] = status["brightness"]
        if status["mode"] == "cct":
            row["color_temp_kelvin"] = status["ct"]
        elif status["mode"] == "rgb":
            row.update(rgb_row(*status["rgb"]))
    if "timer_started_at" in status and "timer_duration" in status:
        duration = status["timer_duration"]
        remaining = min(max(status["timer_started_at"] + duration - now.timestamp(), 0), duration)
        row["timer"] = timer_row("off" if status["output"] else "on", remaining, now)
    return row


def config_row(config: dict) -> dict:
    """auto_off and auto_on from one target's GetConfig: {"duration": seconds} when enabled, None when disabled.

    A key the config lacks is left out of the row, as it is when the config can't be read: absent means unknown.
    """
    row: dict = {}
    for key in ("auto_off", "auto_on"):
        if key in config:
            row[key] = {"duration": config[f"{key}_delay"]} if config[key] else None
    return row


class ShellyGetAttributes(Adapter[Request]):
    """A GetStatus and a GetConfig per target, concurrently. A GetStatus error raises; a GetConfig error only leaves
    the auto_off and auto_on rows out, so one unread setting doesn't lose the rest of the row."""

    action: ClassVar[str] = "get_attributes"
    integration: ClassVar[str] = "shelly"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=frozenset({"light", "switch"}),
        # A relay shown as a light sends the same Switch.GetStatus; Light, CCT, RGB and RGBW stay out of scope until a
        # test record covers them.
        capabilities=frozenset({"Switch", "RGBCCT"}),
        confirmable=True,
        experimental=True,
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target, self.scope.capabilities)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        async def read(target: Target) -> EntityResult:
            status, config = await asyncio.gather(get_status(target), get_config(target), return_exceptions=True)
            if isinstance(status, BaseException):
                raise status
            if isinstance(config, BaseException) and not isinstance(config, Exception):
                raise config  # a cancellation, not a device error
            row = status_row(address(target).component, status, dt_util.utcnow())
            if isinstance(config, Exception):
                _LOGGER.debug("get_attributes GetConfig failed for %s: %r", target.entity_id, config)
                return self.result(target, Status.CONFIRMED, data=row, detail="config_unreadable")
            return self.result(target, Status.CONFIRMED, data=row | config_row(config))

        return await self.gather(hass, targets, read)
