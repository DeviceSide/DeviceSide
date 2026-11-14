"""LevelFade's own contracts, which the integrations built on it rely on: what a refusal passes on, the guard held
from the read to the set, and the default duration."""

from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.deviceside.actions.ramp import RampRequest
from custom_components.deviceside.core.adapter import Adapter
from custom_components.deviceside.core.level_fade import LevelFade, Reading
from custom_components.deviceside.core.models import Status
from custom_components.deviceside.core.scope import DurationLimits

LAMP = SimpleNamespace(reported_id="light.lamp", entity_id="light.lamp")


class PlainFade(LevelFade):
    """A lit light at 40 %, with every step it takes recorded in order."""

    action = "raise_brightness"
    integration = "fake"
    fade_limits = DurationLimits(min_s=0.5, max_s=60)
    lit = True

    def __init__(self) -> None:
        self.steps: list = []

    def unaddressable(self, target):
        return "not_addressable"

    heading_there = False

    async def read(self, hass, target, end):
        self.steps.append(("read", end))
        return Reading(self.lit, 40.0, self.heading_there)

    async def fade_to(self, hass, target, end, seconds):
        self.steps.append(("set", end, seconds))

    @asynccontextmanager
    async def guard(self, hass, target):
        self.steps.append("guard taken")
        try:
            yield
        finally:
            self.steps.append("guard released")

    async def gather(self, hass, targets, send, hold=None):
        """Adapter.gather's hand-off, recorded: it is what gives each target its hold, its slot, its deadline and its
        own result."""
        self.steps.append("gather")
        results = []
        for target in targets:
            async with hold(target) if hold else nullcontext():
                results.append(await send(target))
        return results


class PlainLower(PlainFade):
    action = "lower_brightness"


def ramp(up: bool = True, **kwargs) -> RampRequest:
    return RampRequest(attribute="brightness", up=up, sweep_time=4, **kwargs)


def test_a_fade_without_its_limits_cant_be_created():
    """The registry creates every adapter at load, so a missing fade_limits fails there, not on a user's call."""

    class NoLimits(LevelFade):
        action = "raise_brightness"
        integration = "fake"
        unaddressable = PlainFade.unaddressable
        read = PlainFade.read
        fade_to = PlainFade.fade_to

    with pytest.raises(TypeError, match="fade_limits"):
        NoLimits()


def test_a_fade_takes_its_share_of_the_sweep_time():
    assert PlainFade().seconds(distance=25, sweep_time=4) == 1.0


def test_a_fade_runs_at_least_the_devices_shortest():
    assert PlainFade().seconds(distance=5, sweep_time=4) == 0.5


def test_a_scope_refusal_comes_before_the_integrations_own():
    with patch.object(Adapter, "supports", return_value="domain_not_tested"):
        assert PlainFade().supports(None, ramp(), None) == "domain_not_tested"


def test_a_target_the_integration_cant_address_is_refused():
    with patch.object(Adapter, "supports", return_value=None):
        assert PlainFade().supports(None, ramp(), None) == "not_addressable"


def test_nothing_left_to_send_passes_a_target_it_cant_address():
    """The dispatcher reports it unchanged with fields_dropped, so a light lacking brightness isn't raised."""
    with patch.object(Adapter, "supports", return_value=None):
        assert PlainFade().supports(None, ramp(dropped=True), None) is None


async def test_the_guard_is_held_from_the_read_to_the_set():
    """An integration whose stop takes the same guard can't slip in between them."""
    fade = PlainFade()

    [result] = await fade.execute(None, ramp(), [LAMP])

    assert result.status is Status.SENT
    assert fade.steps == ["gather", "guard taken", ("read", 100), ("set", 100, 2.4), "guard released"]


async def test_the_guard_is_gathers_hold_not_taken_inside_the_send():
    """gather() takes it before the slot, so a fade waiting on its light holds no slot another light could use."""
    fade = PlainFade()

    async def gather_without_hold(hass, targets, send, hold=None):
        return [await send(target) for target in targets]

    with patch.object(fade, "gather", gather_without_hold):
        await fade.execute(None, ramp(), [LAMP])

    assert "guard taken" not in fade.steps


async def test_the_guard_is_released_when_nothing_is_sent(caplog):
    """Lowering a light that is off: unchanged, and the debug log says what the device reported."""
    fade = PlainLower()
    fade.lit = False
    caplog.set_level("DEBUG")

    [result] = await fade.execute(None, ramp(up=False), [LAMP])

    assert (result.status, result.detail) == (Status.UNCHANGED, "off")
    assert fade.steps == ["gather", "guard taken", ("read", 0.0), "guard released"]
    assert "lower_brightness on fake: light.lamp reads lit=False level=40.0, end 0.0: nothing sent (off)" in caplog.text


async def test_a_raise_from_unlit_starts_from_zero_whatever_level_is_read():
    """The level of a light that isn't lit is ignored, so the whole range is the distance."""
    fade = PlainFade()
    fade.lit = False

    await fade.execute(None, ramp(), [LAMP])

    assert ("set", 100, 4.0) in fade.steps


async def test_less_than_a_step_left_is_at_the_limit():
    """Half a percent to go is under the device's resolution: nothing to send."""
    fade = PlainFade()

    [result] = await fade.execute(None, ramp(limit=40.5), [LAMP])

    assert (result.status, result.detail) == (Status.UNCHANGED, "at_limit")
    assert fade.steps == ["gather", "guard taken", ("read", 40.5), "guard released"]


async def test_a_light_already_at_the_limit_is_unchanged(caplog):
    fade = PlainFade()
    caplog.set_level("DEBUG")

    [result] = await fade.execute(None, ramp(limit=40), [LAMP])

    assert (result.status, result.detail) == (Status.UNCHANGED, "at_limit")
    assert (
        "raise_brightness on fake: light.lamp reads lit=True level=40.0, end 40: nothing sent (at_limit)" in caplog.text
    )


@pytest.mark.parametrize(("adapter", "up", "end"), [(PlainFade, True, 100.0), (PlainLower, False, 0.0)])
async def test_a_fade_already_heading_for_the_end_is_left_running(caplog, adapter, up, end):
    """Nothing sent, logged, and ahead of off and at_limit."""
    fade = adapter()
    fade.heading_there = True
    fade.lit = up
    caplog.set_level("DEBUG")

    [result] = await fade.execute(None, ramp(up=up), [LAMP])

    assert (result.status, result.detail) == (Status.UNCHANGED, "already_fading")
    assert fade.steps == ["gather", "guard taken", ("read", end), "guard released"]
    assert f"light.lamp reads lit={up} level=40.0, end {end}: nothing sent (already_fading)" in caplog.text


async def test_a_reading_heads_nowhere_unless_the_integration_says_so():
    assert Reading(True, 40.0).heading_there is False


@pytest.mark.parametrize(("asked", "clamped", "seconds"), [(0.1, 0.5, 0.5), (600, 60, 36.0)])
async def test_a_sweep_time_outside_the_devices_range_is_clamped_and_reported(asked, clamped, seconds):
    """Clamped to what a full-range fade can take, and the fade is timed at the clamped speed."""
    fade = PlainFade()

    [result] = await fade.execute(None, RampRequest("brightness", True, asked), [LAMP])

    assert result.clamped_to == clamped
    assert ("set", 100, seconds) in fade.steps


async def test_a_sweep_time_in_range_is_not_reported():
    [result] = await PlainFade().execute(None, ramp(), [LAMP])

    assert result.clamped_to is None
