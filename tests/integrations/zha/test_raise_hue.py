"""ZHA raise_hue: EnhancedMoveHue up, a cycle at a rate the bulb runs until a stop."""

import pytest

from custom_components.deviceside.integrations.zha.fade import hue_moves

from .conftest import SENT, A, B, bulb, sent
from ...conftest import call

pytestmark = pytest.mark.usefixtures("setup_production", "clock", "bulbs")


async def test_a_cycle_in_the_sweep_time(hass, commands):
    bulb(hass)

    assert await call(hass, "raise_hue", {"entity_id": "light.bulb"}) == {"light.bulb": SENT}
    assert sent(commands) == [(0x0300, 0x41, {"move_mode": 1, "rate": 13107})]
    assert hue_moves(hass) == {"light.bulb"}


@pytest.mark.parametrize(
    ("sweep_time", "rate", "clamped_to"),
    [
        pytest.param(0.5, 65535, 1.0, id="under_a_second"),
        pytest.param(1.0, 65535, None, id="one_second"),
        pytest.param(65535, 1, None, id="the_longest_cycle"),
        pytest.param(70000, 1, 65535.0, id="over_the_longest_cycle"),
    ],
)
async def test_a_cycle_outside_1_to_65535_s_is_clamped(hass, commands, sweep_time, rate, clamped_to):
    bulb(hass)

    response = await call(hass, "raise_hue", {"entity_id": "light.bulb", "sweep_time": sweep_time})

    assert sent(commands) == [(0x0300, 0x41, {"move_mode": 1, "rate": rate})]
    expected = SENT if clamped_to is None else {**SENT, "clamped_to": clamped_to}
    assert response == {"light.bulb": expected}


async def test_a_groups_members_get_one_enhanced_move_hue_groupcast(hass, two_light_group, commands, group_commands):
    bulb(hass, "light.a", A)
    bulb(hass, "light.b", B)

    response = await call(hass, "raise_hue", {"entity_id": "light.zha_group"})

    assert response == {"light.a": SENT, "light.b": SENT}
    # A groupcast's args are positional: move_mode, then rate, as the unicast's named params.
    assert [command.data for command in group_commands] == [
        {"group": 2, "cluster_id": 0x0300, "command": 0x41, "args": [1, 13107]}
    ]
    assert not commands
    assert hue_moves(hass) == {"light.a", "light.b"}
