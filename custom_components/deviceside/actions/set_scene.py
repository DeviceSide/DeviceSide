from typing import TYPE_CHECKING, ClassVar

from homeassistant.const import Platform
from homeassistant.core import DOMAIN as HA_DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall

from .set_attributes import SetAttributes
from ..core import ha_scene
from ..core.action import Action, Ride, Routed
from ..core.models import ActionKind, Request

if TYPE_CHECKING:
    from ..core.dispatcher import Dispatcher


class SetScene(Action[Request]):
    """Write a scene's settings to its lights without turning them on; lights already on change straight away.

    A Home Assistant scene is routed here (core/ha_scene.py): each light through set_attributes, so it serves every
    integration that has it; any other scene goes to its integration's set_scene adapter.
    """

    key: ClassVar[str] = "set_scene"
    kind: ClassVar[ActionKind] = ActionKind.COMMAND
    domains: ClassVar[frozenset[str]] = frozenset({Platform.SCENE})
    rides: ClassVar[Ride] = Ride(SetAttributes.key, Platform.SCENE, HA_DOMAIN)

    @classmethod
    def parse(cls, hass: HomeAssistant, call: ServiceCall) -> Request:
        return Request()

    @classmethod
    def claims(cls, hass: HomeAssistant, entity_id: str) -> bool:
        return ha_scene.is_ha_scene(hass, entity_id)

    @classmethod
    def route(cls, hass: HomeAssistant, request: Request, claimed: dict[str, bool], dispatcher: Dispatcher) -> Routed:
        return ha_scene.route(hass, request, claimed, dispatcher)


ACTION = SetScene
