"""Matter stop: Level Stop and StopMoveStep to each light, then two reads of where it halted, 0.2 s apart (plan
Decisions 8 and 10; docs/integrations/matter/research/2026-11-24-level-color.md)."""

import asyncio
import logging
from dataclasses import dataclass
from typing import ClassVar

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .addressing import (
    NO_OVERRIDE,
    color_features,
    color_path,
    has_color,
    level_path,
    light_reason,
    make_command,
    matter_client,
    node_for,
    node_id_from_unique_id,
    onoff_attr_path,
    onoff_endpoint,
)
from .classes import LIGHT_ACTIONS
from .fade import cancel_restore, hue_moves, light_lock
from ...core.adapter import Adapter
from ...core.models import EntityResult, Request, Status, Target
from ...core.readback import read_back
from ...core.scope import AdapterScope, labs
from ...core.zcl import CURRENT_HUE, CURRENT_LEVEL, CURRENT_SATURATION, HUE_SATURATION

_LOGGER = logging.getLogger(__name__)

# Two reads this far apart say whether the light still moves: a light that kept fading reads differently, one that
# halted reads the same. A fade slower than a step per 0.2 s (a long hue cycle) can read the same and is confirmed
# while still moving (internals.md, stop). 0.2 s is two of a transition's 0.1 s units (core/zcl.py).
READ_GAP_S = 0.2


@dataclass(frozen=True, slots=True)
class _Halted:
    """What a halted light's two reads need: where to read, and which attributes say it still moves."""

    client: object
    node_id: int
    ep_id: int
    paths: list[str]


class MatterStop(Adapter[Request]):
    """Level Stop to each light, plus StopMoveStep on one with a Color Control server, always: with nothing moving
    they change nothing, and no state of ours says what a light was told (a saturation move isn't tracked).

    The sends go first, so a stop doesn't overshoot by a read's round trip; then one OnOff read. A light that reads on
    has its pending soft-off restore cancelled, so a halted soft off stays on at the halt level. A light that reads off
    is UNCHANGED with off, and its restore, if any, still runs (a soft off that finished before the stop). Either way
    the stop ends its hue cycle. It holds the light's lock (fade.light_lock) so it can't slip between a move's read and
    its send.

    The read-back reads CurrentLevel, and CurrentSaturation and CurrentHue on a light with the HS feature, twice
    READ_GAP_S apart, outside every slot but the reads'. Equal reads are CONFIRMED; unequal ones are SENT with
    still_fading, as the light kept moving; a light that reads off is UNCHANGED with off; a read that failed is SENT
    with readback_failed.
    """

    action: ClassVar[str] = "stop"
    integration: ClassVar[str] = "matter"
    scope: ClassVar[AdapterScope] = AdapterScope(
        domains=labs(Platform.LIGHT), capabilities=LIGHT_ACTIONS, confirmable=True
    )

    def supports(self, hass: HomeAssistant, request: Request, target: Target) -> str | None:
        return super().supports(hass, request, target) or light_reason(hass, target)

    async def execute(self, hass: HomeAssistant, request: Request, targets: list[Target]) -> list[EntityResult]:
        halted: dict[str, _Halted] = {}

        async def halt(target: Target) -> EntityResult:
            node_id = node_id_from_unique_id(target.entry.unique_id)
            ep_id = onoff_endpoint(target.entry.unique_id)
            client = matter_client(hass, target.entry.config_entry_id)  # supports() refused the targets without one
            node = node_for(hass, target)
            await self._send(client, target, node_id, ep_id, "LevelControl", "Stop")
            paths = [level_path(ep_id, CURRENT_LEVEL)]
            if has_color(node, ep_id):
                await self._send(client, target, node_id, ep_id, "ColorControl", "StopMoveStep")
                if color_features(node, ep_id) & HUE_SATURATION:
                    paths += [color_path(ep_id, CURRENT_SATURATION), color_path(ep_id, CURRENT_HUE)]
            hue_moves(hass).discard(target.entity_id)
            if (await client.read_attribute(node_id=node_id, attribute_path=onoff_attr_path(ep_id))).get(
                onoff_attr_path(ep_id)
            ) is not True:
                return self.result(target, Status.UNCHANGED, detail="off")  # its soft-off restore, if any, still runs
            cancel_restore(hass, target.entity_id)
            halted[target.reported_id] = _Halted(client, node_id, ep_id, paths)
            return self.result(target, Status.SENT)

        results = await self.gather(hass, targets, halt, hold=lambda target: light_lock(hass, target))
        if not halted:
            return results
        confirmed = await asyncio.gather(
            *(
                self._read_back(hass, target, halted[target.reported_id])
                for target in targets
                if target.reported_id in halted
            )
        )
        by_id = {result.entity_id: result for result in confirmed}
        return [by_id.get(result.entity_id, result) for result in results]

    async def _send(self, client: object, target: Target, node_id: int, ep_id: int, cluster: str, command: str) -> None:
        _LOGGER.debug("%s: sending matter %s.%s %s", target.reported_id, cluster, command, NO_OVERRIDE)
        await client.send_device_command(
            node_id=node_id, endpoint_id=ep_id, command=make_command(cluster, command, **NO_OVERRIDE)
        )

    async def _read(self, hass: HomeAssistant, target: Target, light: _Halted) -> dict[str, object]:
        """OnOff and the halted attributes, in a slot of their own, so the gap between two reads holds none."""
        paths = [onoff_attr_path(light.ep_id), *light.paths]
        async with self.slot(hass):
            return {
                path: (await light.client.read_attribute(node_id=light.node_id, attribute_path=path)).get(path)
                for path in paths
            }

    async def _read_back(self, hass: HomeAssistant, target: Target, light: _Halted) -> EntityResult:
        async def read_twice(_: Target) -> tuple[dict[str, object], dict[str, object]]:
            first = await self._read(hass, target, light)
            await asyncio.sleep(READ_GAP_S)
            return first, await self._read(hass, target, light)

        def judge(reads: tuple[dict[str, object], dict[str, object]]) -> EntityResult:
            first, second = reads
            if second[onoff_attr_path(light.ep_id)] is not True:
                return self.result(target, Status.UNCHANGED, detail="off")
            if any(first[path] != second[path] for path in light.paths):
                _LOGGER.debug("%s: still moving after the stop: read %s, then %s", target.reported_id, first, second)
                return self.result(target, Status.SENT, detail="still_fading")
            return self.result(target, Status.CONFIRMED)

        return await read_back(self, target, read_twice, judge)
