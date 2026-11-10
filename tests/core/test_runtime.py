"""DeviceSideData.schedule and cancel_pending: delayed jobs keyed by the caller."""

from unittest.mock import MagicMock

from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from custom_components.deviceside.core.runtime import DEADLINE, DeviceSideData, get_runtime

from ..conftest import advance, wall_clock_now


def _runtime() -> DeviceSideData:
    return DeviceSideData(registry=MagicMock(), dispatcher=MagicMock())


def _recorder(ran: list[str], name: str):
    async def job() -> None:
        ran.append(name)

    return job


async def test_jobs_run_after_their_delays_and_leave_nothing_pending(hass):
    runtime, ran, start = _runtime(), [], wall_clock_now()

    runtime.schedule(hass, "k", [(1, _recorder(ran, "a")), (5, _recorder(ran, "b"))])
    assert len(runtime.pending["k"]) == 2

    await advance(hass, start, 1.5)
    assert ran == ["a"]
    assert len(runtime.pending["k"]) == 1
    await advance(hass, start, 5.5)
    assert ran == ["a", "b"]
    assert runtime.pending == {}


async def test_rescheduling_a_key_cancels_its_pending_jobs_only(hass):
    runtime, ran, start = _runtime(), [], wall_clock_now()

    runtime.schedule(hass, "k", [(1, _recorder(ran, "old"))])
    runtime.schedule(hass, "other", [(1, _recorder(ran, "other"))])
    runtime.schedule(hass, "k", [(2, _recorder(ran, "new"))])

    await advance(hass, start, 2.5)
    assert sorted(ran) == ["new", "other"]


async def test_no_jobs_leaves_nothing_pending(hass):
    runtime = _runtime()

    runtime.schedule(hass, "k", [])

    assert runtime.pending == {}


async def test_cancel_pending_cancels_every_key(hass):
    runtime, ran, start = _runtime(), [], wall_clock_now()
    runtime.schedule(hass, "a", [(1, _recorder(ran, "a"))])
    runtime.schedule(hass, "b", [(1, _recorder(ran, "b"))])

    runtime.cancel_pending()
    await advance(hass, start, 2)

    assert ran == []
    assert runtime.pending == {}


async def test_cancel_pending_leaves_must_run_jobs_to_run_at_their_time(hass):
    runtime, ran, start = _runtime(), [], wall_clock_now()
    runtime.schedule(hass, "restore", [(1, _recorder(ran, "restore"))], must_run=True)
    runtime.schedule(hass, "refresh", [(1, _recorder(ran, "refresh"))])

    runtime.cancel_pending()
    assert ran == []
    await advance(hass, start, 2)

    assert ran == ["restore"]
    assert runtime.pending == {}
    assert runtime.must_run == set()


async def test_a_plain_reschedule_replaces_a_must_run_job(hass):
    runtime, ran, start = _runtime(), [], wall_clock_now()
    runtime.schedule(hass, "k", [(1, _recorder(ran, "restore"))], must_run=True)
    runtime.schedule(hass, "k", [])  # a stop cancels the restore

    runtime.cancel_pending()
    await advance(hass, start, 2)

    assert ran == []
    assert runtime.must_run == set()


def test_listen_attaches_once_per_owner_and_replaces_a_new_owners():
    runtime = _runtime()
    detached: list[str] = []
    attached: list[str] = []

    def attach(name: str):
        def start():
            attached.append(name)
            return lambda: detached.append(name)

        return start

    first, second = object(), object()
    runtime.listen("k", first, attach("first"))
    runtime.listen("k", first, attach("again"))
    runtime.listen("k", second, attach("second"))
    runtime.listen("other", first, attach("other"))
    runtime.detach_all()

    assert attached == ["first", "second", "other"]
    assert detached == ["first", "second", "other"]
    assert runtime.listeners == {}


async def test_cancel_pending_with_must_run_takes_the_restores_too(hass):
    runtime, ran, start = _runtime(), [], wall_clock_now()
    runtime.schedule(hass, "restore", [(1, _recorder(ran, "restore"))], must_run=True)

    runtime.cancel_pending(must_run=True)
    await advance(hass, start, 2)

    assert ran == []
    assert runtime.pending == {}
    assert runtime.must_run == set()


async def test_ha_stopping_cancels_the_must_run_jobs(hass, setup_production):
    runtime, ran, start = get_runtime(hass), [], wall_clock_now()
    runtime.schedule(hass, "restore", [(1, _recorder(ran, "restore"))], must_run=True)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    await advance(hass, start, 2)

    assert ran == []
    assert runtime.pending == {}


async def test_a_job_runs_outside_the_deadline_of_the_run_that_scheduled_it(hass):
    runtime, seen, start = _runtime(), [], wall_clock_now()

    async def job() -> None:
        seen.append(DEADLINE.get())

    token = DEADLINE.set(1.0)
    try:
        runtime.schedule(hass, "k", [(1, job)])
    finally:
        DEADLINE.reset(token)
    await advance(hass, start, 1.5)

    assert seen == [None]


async def test_unloading_the_entry_leaves_a_must_run_job_to_run(hass, setup_production):
    runtime, ran, start = get_runtime(hass), [], wall_clock_now()
    runtime.schedule(hass, "restore", [(1, _recorder(ran, "restore"))], must_run=True)

    assert await hass.config_entries.async_unload(setup_production.entry_id)
    await advance(hass, start, 2)

    assert ran == ["restore"]
    assert runtime.pending == {}
