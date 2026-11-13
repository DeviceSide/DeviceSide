"""Reading back what a device kept after a write it accepted."""

import logging
from collections.abc import Awaitable, Callable

from .adapter import Adapter
from .models import EntityResult, Status, Target

_LOGGER = logging.getLogger(__name__)


async def read_back[HeldT](
    adapter: Adapter,
    target: Target,
    read: Callable[[Target], Awaitable[HeldT]],
    judge: Callable[[HeldT], EntityResult],
) -> EntityResult:
    """Read what the device kept after an accepted write and let `judge` rule on it.

    A failed read-back reports SENT: the device accepted the write.
    """
    try:
        held = await read(target)
    except Exception as err:  # noqa: BLE001 - an integration's library errors can't be imported here
        _LOGGER.debug(
            "%s on %s read-back failed for %s: %r", adapter.action, adapter.integration, target.entity_id, err
        )
        return adapter.result(target, Status.SENT, detail="readback_failed")
    return judge(held)
