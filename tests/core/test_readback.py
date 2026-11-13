"""read_back: the read after an accepted write. Its failure is still a sent write, and the log carries the cause."""

from types import SimpleNamespace

from custom_components.deviceside.core.models import EntityResult, Status
from custom_components.deviceside.core.readback import read_back

LAMP = SimpleNamespace(reported_id="light.lamp", entity_id="light.lamp")


class Fake:
    action = "stop"
    integration = "fake"

    def result(self, target, status, **kwargs):
        return EntityResult(target.reported_id, status, integration=self.integration, **kwargs)


async def test_what_the_device_kept_is_judged():
    async def read(target):
        return {"brightness": 40}

    result = await read_back(Fake(), LAMP, read, lambda held: Fake().result(LAMP, Status.CONFIRMED, data=held))

    assert (result.status, result.data) == (Status.CONFIRMED, {"brightness": 40})


async def test_a_failed_read_back_is_sent_and_logged_with_its_cause(caplog):
    """A timeout's message is empty, so the error is logged as it is, with the integration it came from."""

    async def read(target):
        raise TimeoutError

    caplog.set_level("DEBUG")
    result = await read_back(Fake(), LAMP, read, lambda held: None)

    assert (result.status, result.detail) == (Status.SENT, "readback_failed")
    assert "stop on fake read-back failed for light.lamp: TimeoutError()" in caplog.text
