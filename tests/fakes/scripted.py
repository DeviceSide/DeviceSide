"""A scripted adapter shared by the fake integrations: tests set outcomes per entity and read back what was sent."""

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass, field

from custom_components.deviceside.core.adapter import Adapter
from custom_components.deviceside.core.models import EntityResult, Status, Target


@dataclass
class Script:
    outcomes: dict[str, Status | Exception] = field(default_factory=dict)
    calls: list[tuple[str, str, object, list[str]]] = field(default_factory=list)
    execute_error: Exception | None = None
    delay: float = 0
    # Per entity, over delay.
    delays: dict[str, float] = field(default_factory=dict)
    active: int = 0
    max_active: int = 0
    # Per entity, the lock gather() takes as its hold; entities sharing one are one device.
    holds: dict[str, asyncio.Lock] = field(default_factory=dict)
    started: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.__init__()


SCRIPT = Script()


class ScriptedAdapter(Adapter):
    async def execute(self, hass, request, targets: list[Target]) -> list[EntityResult]:
        SCRIPT.calls.append((self.integration, self.action, request, [target.entity_id for target in targets]))
        if SCRIPT.execute_error is not None:
            raise SCRIPT.execute_error

        async def send(target: Target) -> EntityResult:
            SCRIPT.started.append(target.entity_id)
            SCRIPT.active += 1
            SCRIPT.max_active = max(SCRIPT.max_active, SCRIPT.active)
            try:
                await asyncio.sleep(SCRIPT.delays.get(target.entity_id, SCRIPT.delay))
                outcome = SCRIPT.outcomes.get(target.entity_id, Status.SENT)
                if isinstance(outcome, Exception):
                    raise outcome
                return self.result(target, outcome)
            finally:
                SCRIPT.active -= 1

        def hold(target: Target):
            return SCRIPT.holds.get(target.entity_id) or nullcontext()

        return await self.gather(hass, targets, send, hold=hold)
