"""Shelly get_attributes: on/off timer, brightness, color temperature and color from <Component>.GetStatus, and the
persistent auto-off / auto-on from <Component>.GetConfig."""

import asyncio
import logging
from datetime import datetime
from typing import ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .addressing import CAPABILITIES, SIBLINGS, RpcComponent, address, unsupported_reason
from .rpc import get_config, get_status
from ...core.adapter import Adapter
from ...core.color import rgb_row
from ...core.models import EntityResult, Request, Status, Target
from ...core.scope import AdapterScope, verified
from ...core.timer import timer_row

_LOGGER = logging.getLogger(__name__)


_DIMMABLE = frozenset({"Light", "CCT", "RGB", "RGBW", "RGBCCT"})
# The clock skew the timer's time left absorbs; more means the device's clock isn't synced.
_SKEW_S = 5.0


def status_row(component: str, status: dict, now: datetime) -> dict:
    """One target's row from its GetStatus. The bulb keeps brightness, ct and rgb while off, so they read then too.

    The time left is the device's timer_started_at against HA's clock, both SNTP-synced; the clamp to [0, duration]
    absorbs up to _SKEW_S of skew. Beyond that the device's clock isn't synced (an unsynced Gen2 reports
    timer_started_at as seconds since boot), so the time left can't be read and the row has no timer.
    """
    row: dict = {}
    # Brightness is the device's percent, as Hue's row is. A field the status lacks leaves its row out.
    if component in _DIMMABLE and "brightness" in status:
        row["brightness"] = status["brightness"]
    if component == "RGBCCT":
        # The status carries ct and rgb in either mode; only the active one is reported, as core does.
        if status.get("mode") == "cct" and "ct" in status:
            row["color_temp_kelvin"] = status["ct"]
        elif status.get("mode") == "rgb" and "rgb" in status:
            row.update(rgb_row(*status["rgb"]))
    elif component == "CCT":
        if "ct" in status:
            row["color_temp_kelvin"] = status["ct"]
    elif component in ("RGB", "RGBW") and "rgb" in status:
        row.update(rgb_row(*status["rgb"]))
    if "timer_started_at" in status and "timer_duration" in status:
        duration = status["timer_duration"]
        remaining = status["timer_started_at"] + duration - now.timestamp()
        if -_SKEW_S <= remaining <= duration + _SKEW_S:
            row["timer"] = timer_row("off" if status["output"] else "on", min(max(remaining, 0), duration), now)
        else:
            _LOGGER.debug("Shelly timer_started_at %s is off HA's clock: no timer row", status["timer_started_at"])
    return row


def config_row(config: dict) -> dict:
    """auto_off and auto_on from one target's GetConfig: {"duration": seconds} when enabled, None when disabled.

    A key the config lacks, or an enabled one without its delay, is left out of the row, as it is when the config
    can't be read: absent means unknown.
    """
    row: dict = {}
    for key in ("auto_off", "auto_on"):
        if key not in config or (config[key] and f"{key}_delay" not in config):
            continue
        row[key] = {"duration": config[f"{key}_delay"]} if config[key] else None
    return row


class ShellyGetAttributes(RpcComponent, Adapter[Request]):
    """A GetStatus and a GetConfig per target, concurrently. A GetStatus error raises; a GetConfig error only leaves
    the auto_off and auto_on rows out, so one unread setting doesn't lose the rest of the row."""

    action: ClassVar[str] = "get_attributes"
    integration: ClassVar[str] = "shelly"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=verified("light", "switch"),
        # A relay shown as a light sends the same Switch.GetStatus.
        capabilities=CAPABILITIES,
        siblings=SIBLINGS,
        confirmable=True,
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or unsupported_reason(target)

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
            else:
                row |= config_row(config)
            if not row:
                # Nothing was read, so nothing is confirmed.
                _LOGGER.warning("get_attributes read nothing from %s's status", target.entity_id)
                return self.result(target, Status.REJECTED, detail="error")
            return self.result(target, Status.CONFIRMED, data=row)

        return await self.gather(hass, targets, read)
