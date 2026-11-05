"""The persistent auto-off / auto-on setting: set_auto_off and set_auto_on write it, clear_auto_off and clear_auto_on
remove it. Unlike turn_on_for's per-command timer, it applies to every turn-on (or turn-off) from any source."""

from typing import ClassVar

import probatio
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .turn_on_for import parse_duration
from ..core.action import Action
from ..core.models import ActionKind, Request, TimedRequest


class SetAuto(Action[TimedRequest]):
    """Store a delay the device applies after every turn-on (auto-off) or turn-off (auto-on)."""

    kind: ClassVar[ActionKind] = ActionKind.SETTING
    domains: ClassVar[frozenset[str]] = frozenset({"light", "switch"})
    fields: ClassVar[dict] = {probatio.Required("duration"): cv.positive_time_period}

    @classmethod
    def parse(cls, hass: HomeAssistant, call: ServiceCall) -> TimedRequest:
        return TimedRequest(duration_s=parse_duration(call))


class ClearAuto(Action[Request]):
    """Remove the stored setting, as core's clear_ services do (sonos.clear_sleep_timer); never a zero duration."""

    kind: ClassVar[ActionKind] = ActionKind.SETTING
    domains: ClassVar[frozenset[str]] = frozenset({"light", "switch"})

    @classmethod
    def parse(cls, hass: HomeAssistant, call: ServiceCall) -> Request:
        return Request()
