from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from typing import Any, Self

import probatio
from homeassistant.components.light.const import LIGHT_TURN_ON_SCHEMA
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ..const import LIGHT_FIELDS


class Status(StrEnum):
    UNSUPPORTED = "unsupported"
    REJECTED = "rejected"
    SENT = "sent"
    CONFIRMED = "confirmed"
    UNCHANGED = "unchanged"  # nothing sent: the target is where the call would leave it, or on its way; detail says why


# Statuses that mean the command did not reach the device. Neither reaches a response: the dispatcher raises or skips.
FAILED = frozenset({Status.UNSUPPORTED, Status.REJECTED})


class ActionKind(StrEnum):
    COMMAND = "command"
    SETTING = "setting"
    QUERY = "query"


# Brightness is a percent in every DeviceSide action. A brightness field that sets a level takes more than 0: 0 would
# mean off. Values below the device's lowest level are floored to it.
PERCENT = probatio.All(probatio.Coerce(float), probatio.Range(min=0, max=100))
POSITIVE_PERCENT = probatio.All(probatio.Coerce(float), probatio.Range(min=0, min_included=False, max=100))

# light.turn_on's own validators for the fields we accept, so ranges and the one-color-at-a-time rule never drift
# from core; brightness alone takes a percent. Plain-string keys (transition) become Optional markers so every field
# is a Marker.
LIGHT_FIELD_SCHEMA: dict[probatio.Marker, Any] = {
    (key if isinstance(key, probatio.Marker) else probatio.Optional(key)): (
        POSITIVE_PERCENT if str(key) == "brightness" else validator
    )
    for key, validator in LIGHT_TURN_ON_SCHEMA.items()
    if str(key) in LIGHT_FIELDS
}


@dataclass(frozen=True, slots=True)
class LightFields:
    brightness: float | None = None  # percent, above 0 and up to 100
    color_temp_kelvin: int | None = None
    hs_color: tuple[float, float] | None = None
    rgb_color: tuple[int, int, int] | None = None
    xy_color: tuple[float, float] | None = None
    transition: float | None = None

    @classmethod
    def from_data(cls, data: dict) -> LightFields:
        return cls(**{name: data[name] for name in LIGHT_FIELDS if name in data})

    def present(self) -> frozenset[str]:
        return frozenset(field.name for field in fields(self) if getattr(self, field.name) is not None)

    def brightness_255(self) -> int | None:
        """brightness on light.turn_on's 1-255 scale, never 0: that would turn the light off.

        Not brightness_pct: core rounds a small percent to 0.
        """
        if self.brightness is None:
            return None
        return max(1, round(self.brightness * 255 / 100))

    def as_turn_on_data(self) -> dict:
        """The fields as light.turn_on data."""
        data = {name: getattr(self, name) for name in sorted(self.present())}
        if self.brightness is not None:
            data["brightness"] = self.brightness_255()
        return data

    def without(self, names: frozenset[str]) -> LightFields:
        return replace(self, **{name: None for name in names if name in LIGHT_FIELDS})


@dataclass(frozen=True, slots=True)
class Request:
    """Base for an action's parsed call. Subclasses add their fields."""

    # The caller's context, set by the dispatcher: adapters forward it so an admin-only service checks the caller.
    context: Context | None = field(default=None, kw_only=True)

    def fields_present(self) -> frozenset[str]:
        """light.turn_on fields this request carries; adapters must have them in scope.fields."""
        return frozenset()

    def without(self, names: frozenset[str]) -> Self:
        """This request with the named fields dropped, for a target that can't take them."""
        return self

    def nothing_to_do(self) -> bool:
        """True once dropping fields has left the request nothing to send."""
        return False


@dataclass(frozen=True, slots=True)
class TimedRequest(Request):
    """A request with a duration the dispatcher clamps to each adapter's DurationLimits."""

    duration_s: float


@dataclass(frozen=True, slots=True)
class Target:
    entity_id: str
    domain: str
    integration: str
    entry: er.RegistryEntry
    device: dr.DeviceEntry | None
    config_entry: ConfigEntry
    state: State | None
    via_group: str | None = None
    # The switch_as_x light the caller named; the adapter sees the wrapped switch, results report the light.
    via_wrapper: str | None = None
    is_group: bool = False
    # The caller listed this entity_id. Anything reached through an area, device, label or group is indirect.
    named: bool = False

    @property
    def reported_id(self) -> str:
        """The entity_id results are keyed on: the one the caller targeted."""
        return self.via_wrapper or self.entity_id


@dataclass(slots=True)
class EntityResult:
    entity_id: str
    status: Status
    integration: str | None = None
    clamped_to: float | None = None
    detail: str | None = None
    data: dict | None = None

    def as_response(self) -> dict:
        """A command's status entry. A query's response is its data alone (dispatcher), so data is never here."""
        response: dict[str, Any] = {"status": self.status.value}
        for name in ("integration", "clamped_to", "detail"):
            if (value := getattr(self, name)) is not None:
                response[name] = value
        return response
