"""Roaming (tests/rig/roam.py), against the Lab fake: each move, the rename, the stale-entry removal, the Hue home
saved and restored, a bulb that never joins, and recovery from wherever a crash leaves the bulbs."""

import json

import pytest

from scripts import check_private
from tests.rig import roam
from tests.rig.journal import Journal
from tests.rig.profile import Profile
from tests.rig.roam import Roamer, RoamError
from tests.scripts.rig_fakes import LAB_A, LAB_B, LAB_BULBS, LAB_OPTIONS, FakeBridge, FakeHA, Lab, lab_profile

A, B, OPTIONS, BULBS = LAB_A, LAB_B, LAB_OPTIONS, LAB_BULBS


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(roam, "POLL_S", 0)


@pytest.fixture
def lab() -> Lab:
    return Lab(FakeHA({}), FakeBridge(), {A: "light.lab_a", B: "light.lab_b"})


def roamer(lab: Lab, journal: Journal | None = None, out=None) -> Roamer:
    return Roamer(lab.ha, lab.bridge, BULBS, journal, out=(out if out is not None else lambda _: None))


async def where(lab: Lab) -> list[str | None]:
    found = roamer(lab)
    return [await found.locate(bulb) for bulb in BULBS]


async def test_the_bulbs_move_together_round_the_cycle_keeping_their_entity_ids(lab):
    moving = roamer(lab)
    for network, identifier in (("zha", "zha"), ("zigbee2mqtt", "mqtt"), ("hue", "hue")):
        await moving.go(network)
        assert await where(lab) == [network, network]
        for entity_id in ("light.lab_a", "light.lab_b"):
            assert lab.device_of(entity_id)["identifiers"][0][0] == identifier
    assert not lab.ha.zha_open and not lab.ha.z2m_open
    assert lab.searches == 1  # one Hue search for both bulbs
    zha = [call[2] for call in lab.ha.calls if call[:2] == ("zha", "permit")]
    assert {"duration": roam.JOIN_S} in zha and zha[-1] == {"duration": 0}


async def test_a_z2m_join_sets_the_bulbs_options_again(lab):
    await roamer(lab).go("zigbee2mqtt")
    assert lab.ha.z2m_options == {A: OPTIONS}


async def test_the_stale_entry_holding_the_fixed_id_is_removed_then_the_new_light_renamed(lab):
    printed = []
    await roamer(lab, out=printed.append).go("zha")
    assert "Removed light.lab_a's stale registry entry." in printed
    assert any(line.startswith("Renamed light.zha_bulb_") and line.endswith("to light.lab_a.") for line in printed)
    assert [e for e in lab.ha.entity_devices if e.startswith("light.zha_")] == []


async def test_a_light_already_under_its_fixed_id_is_left_alone(lab):
    await roamer(lab).go("zha")
    calls = len(lab.ha.calls)
    await roamer(lab).go("zha")
    assert len(lab.ha.calls) == calls


async def test_the_fixed_id_held_by_another_device_stops_the_move(lab):
    other = lab.ha.join("zha", "00:17:88:01:0a:bc:de:99")
    lab.ha.entity_devices["light.lab_a"] = other  # the fixed ID now belongs to an unrelated bulb
    with pytest.raises(RoamError, match="light.lab_a belongs to another device"):
        await roamer(lab).go("zha")
    assert lab.ha.entity_devices["light.lab_a"] == other


async def test_home_is_saved_on_leaving_and_put_back_on_the_new_ids(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    moving = roamer(lab, journal)
    await moving.go("zha")
    saved = journal.get("roam")["home"]["light.lab_a"]
    assert saved["rooms"] == ["r1"] and saved["zones"] == ["z1"] and list(saved["scenes"]) == ["s1"]
    resources = lab.bridge.resources
    assert resources["room"]["r1"]["children"] == [{"rid": "other-device", "rtype": "device"}]

    await moving.go("zigbee2mqtt")
    await moving.go("hue")

    device_a = await lab.bridge.device_id_by_ieee(A)
    light_a = next(s["rid"] for s in resources["device"][device_a]["services"] if s["rtype"] == "light")
    assert {"rid": device_a, "rtype": "device"} in resources["room"]["r1"]["children"]
    assert len(resources["room"]["r1"]["children"]) == 3
    assert {"rid": light_a, "rtype": "light"} in resources["zone"]["z1"]["children"]
    actions = resources["scene"]["s1"]["actions"]
    assert Lab.action("other-light", 10) in actions and Lab.action(light_a, 50) in actions and len(actions) == 3
    assert resources["device"][device_a]["metadata"]["name"] == "Lamp light.lab_a"
    assert not journal.path.exists()


async def test_the_journal_names_the_move_in_flight_before_the_release(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    seen = []
    deleted = lab.bridge.on_delete

    def on_delete(device_id):
        seen.append(json.loads(journal.path.read_text())["roam"])
        deleted(device_id)

    lab.bridge.on_delete = on_delete
    await roamer(lab, journal).go("zha")
    assert seen[0]["move"] == {"from": "hue", "to": "zha", "bulbs": ["light.lab_a", "light.lab_b"]}
    assert seen[0]["bulbs"][0] == {"ieee": A[2:], "entity_id": "light.lab_a", "z2m_options": OPTIONS}
    assert set(seen[0]["home"]) == {"light.lab_a", "light.lab_b"}
    roamed = journal.get("roam")
    assert roamed["move"] is None and roamed["at"] == {"light.lab_a": "zha", "light.lab_b": "zha"}


async def test_a_bulb_that_never_joins_aborts_with_the_reset_instruction_and_closes_joining(lab, tmp_path, monkeypatch):
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    lab.stuck.add(A[2:])
    journal = Journal(tmp_path / "journal.json")
    with pytest.raises(RoamError, match=r"light.lab_a did not join ZHA within 0.05 s\. Reset it over Bluetooth"):
        await roamer(lab, journal).go("zha")
    assert not lab.ha.zha_open
    roamed = journal.get("roam")
    assert roamed["at"]["light.lab_a"] is None and roamed["move"]["to"] == "zha"
    assert "light.lab_a" in roamed["home"]


async def test_z2m_joining_is_closed_even_when_a_bulb_never_joins(lab, monkeypatch):
    await roamer(lab).go("zha")
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    lab.stuck.add(B[2:])
    with pytest.raises(RoamError, match="light.lab_b did not join Z2M"):
        await roamer(lab).go("zigbee2mqtt")
    assert not lab.ha.z2m_open
    assert await where(lab) == ["zigbee2mqtt", None]


async def test_an_open_network_is_closed_before_the_bulbs_are_released(lab):
    lab.ha.z2m_open = True
    await roamer(lab).go("zha")
    assert await where(lab) == ["zha", "zha"]
    topics = [json.loads(c[2]["payload"]) for c in lab.ha.calls if c[0] == "mqtt"]
    assert topics[0] == {"time": 0}


async def test_a_hue_search_still_running_stops_the_move_before_any_release(lab, monkeypatch):
    monkeypatch.setattr(roam, "HUE_SEARCH_S", -15)
    lab.bridge.resources["zigbee_device_discovery"]["disc"]["status"] = "active"
    with pytest.raises(RoamError, match="still searching"):
        await roamer(lab).go("zha")
    assert await where(lab) == ["hue", "hue"]


async def crash(lab: Lab, journal: Journal, place: str, monkeypatch) -> None:
    """Leave the bulbs where a run killed at `place` would."""
    moving = roamer(lab, journal)
    if place == "mid-move to ZHA":
        lab.stuck |= {A[2:], B[2:]}
        with monkeypatch.context() as patch:
            patch.setattr(roam, "JOIN_S", 0)
            with pytest.raises(RoamError):
                await moving.go("zha")
        lab.stuck.clear()
        lab.add("zha", A[2:])  # it joined once joining had closed: still under its generated ID
        lab.add("zha", B[2:])
        return
    await moving.go("zha")
    if place == "on Z2M":
        await moving.go("zigbee2mqtt")


@pytest.mark.parametrize("place", ["on ZHA", "on Z2M", "mid-move to ZHA"])
async def test_recovery_moves_the_bulbs_home_from_wherever_a_crash_left_them(lab, tmp_path, monkeypatch, place):
    journal = Journal(tmp_path / "journal.json")
    await crash(lab, journal, place, monkeypatch)

    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), lambda _: None).go(roam.HOME)

    assert await where(lab) == ["hue", "hue"]
    assert lab.device_of("light.lab_a")["identifiers"][0][0] == "hue"
    assert len(lab.bridge.resources["room"]["r1"]["children"]) == 3
    assert not journal.path.exists()


async def test_bulbs_split_across_networks_meet_on_the_way_home(lab):
    await roamer(lab).go("zha")
    await Roamer(lab.ha, lab.bridge, BULBS[1:], None, out=lambda _: None).go("zigbee2mqtt")
    assert await where(lab) == ["zha", "zigbee2mqtt"]
    printed = []
    await roamer(lab, out=printed.append).go("hue")
    assert await where(lab) == ["hue", "hue"]
    moves = [line for line in printed if line.startswith("Moving")]
    assert moves == [
        "Moving light.lab_a from ZHA to Z2M.",
        "Moving light.lab_a, light.lab_b from Z2M to Hue.",
    ]
    assert lab.searches == 1


async def test_a_bulb_on_no_network_stops_with_the_reset_instruction(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    await roamer(lab, journal).go("zha")
    await lab.ha.zha_remove("00:17:88:01:0a:bc:de:f1")  # light.lab_b leaves, and nothing is open
    with pytest.raises(RoamError, match=r"Not on any Zigbee network: light.lab_b\. Reset it over Bluetooth"):
        await Roamer.from_journal(lab.ha, lab.bridge, journal).go(roam.HOME)
    assert await where(lab) == ["zha", None]
    assert journal.get("roam")["home"]


def test_the_route_starts_and_ends_at_home():
    assert roam.route() == ["hue", "zha", "zigbee2mqtt", "hue"]


def test_a_profile_lists_each_roaming_bulb_under_every_network(tmp_path):
    profile = Profile.load(lab_profile(tmp_path))
    assert [bulb.ieee for bulb in profile.roam] == [A[2:], B[2:]]
    assert profile.roam[0].z2m_options == OPTIONS
    for network in ("hue", "zha", "zigbee2mqtt"):
        assert profile.entity(network, "light_color") == "light.lab_a"
        assert profile.entity(network, "light_dimmable") == "light.lab_b"
    assert profile.entity("shelly", "light_color") is None
    lines = roam.plan_lines(profile.roam)
    assert lines[0] == "Roams light.lab_a, light.lab_b together: Hue -> ZHA -> Z2M -> Hue."


@pytest.mark.parametrize(
    ("extra", "error"),
    [
        (f'    - ieee: "{A.upper()}"\n      entity_id: light.lab_c\n', "two roam bulbs share an IEEE"),
        ('    - ieee: "0x0017"\n      entity_id: light.lab_c\n', "isn't 16 hex digits"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: light.lab_a\n', "share an entity ID"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: switch.x\n', "must be a light"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      roles: [group]\n', "not a group"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      roles: [bulb]\n', "unknown roles"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      zigbee: 1\n', "unknown keys"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      z2m_options: [a]\n', "must be a mapping"),
        ("    - entity_id: light.c\n", "needs an ieee and an entity_id"),
        ("  groups: []\n", "roam must be a mapping with a bulbs list"),
    ],
)
def test_a_profile_refuses_a_bad_roam_bulb(tmp_path, extra, error):
    with pytest.raises(ValueError, match=error):
        Profile.load(lab_profile(tmp_path, extra))


def test_a_roaming_bulb_cant_also_be_a_fixed_entity(tmp_path):
    path = lab_profile(tmp_path, "zha:\n  - entity_id: light.lab_a\n    roles: [light_ct]\n")
    with pytest.raises(ValueError, match="light.lab_a roams"):
        Profile.load(path)


def test_the_household_check_flags_a_roaming_bulbs_entity_id_and_ieee_in_any_spelling(tmp_path):
    terms = check_private.private_terms([lab_profile(tmp_path)], tmp_path / "none", tmp_path / "none")
    committed = tmp_path / "doc.md"
    committed.write_text(f"light.lab_b\nZ2M {A}\nZHA 00:17:88:01:0a:bc:de:f1\n")
    hits = check_private.find([committed], terms)
    assert [hit.split(": ", 1)[1] for hit in hits] == ["light.lab_b", A[2:], "00:17:88:01:0a:bc:de:f1"]


async def test_recovery_on_the_target_network_finishes_the_rename_and_options_a_crash_cut_short(
    lab, tmp_path, monkeypatch
):
    journal = Journal(tmp_path / "journal.json")
    await roamer(lab, journal).go("zha")

    async def killed(self, network, bulb):
        raise KeyboardInterrupt  # killed between the join and the rename

    with monkeypatch.context() as patch:
        patch.setattr(Roamer, "adopt", killed)
        with pytest.raises(KeyboardInterrupt):
            await roamer(lab, Journal(journal.path)).go("zigbee2mqtt")
    assert lab.device_of("light.lab_a") is None and lab.ha.z2m_options == {}

    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), lambda _: None).go("zigbee2mqtt")

    assert lab.device_of("light.lab_a")["identifiers"][0][0] == "mqtt"
    assert lab.ha.z2m_options == {A: OPTIONS}
    assert Journal(journal.path).get("roam")["move"] is None


@pytest.mark.parametrize(("bridge_device", "stale"), [("ghost", True), ("other-device", False)])
async def test_a_hue_entry_holding_the_fixed_id_is_stale_only_once_the_bridge_has_dropped_its_device(
    lab, bridge_device, stale
):
    await roamer(lab).go("zha")
    lab.bridge.resources["device"]["other-device"] = {"id": "other-device", "services": []}
    lab.ha.devices.append({"id": "ha-old", "identifiers": [["hue", bridge_device]]})
    lab.ha.entity_devices["light.lab_a"] = "ha-old"
    if stale:
        await roamer(lab).go("zigbee2mqtt")
        assert lab.device_of("light.lab_a")["identifiers"][0][0] == "mqtt"
    else:
        with pytest.raises(RoamError, match="light.lab_a belongs to another device"):
            await roamer(lab).go("zigbee2mqtt")


async def test_a_scene_or_room_deleted_while_away_is_skipped_with_a_line(lab):
    printed = []
    moving = roamer(lab, out=printed.append)
    await moving.go("zha")
    del lab.bridge.resources["scene"]["s1"]
    del lab.bridge.resources["zone"]["z1"]
    await moving.go("hue")
    assert sum(line.startswith("Could not put back light.lab_a's action in scene s1") for line in printed) == 1
    assert any(line.startswith("Could not put light.lab_a back in zone z1") for line in printed)
    assert len(lab.bridge.resources["room"]["r1"]["children"]) == 3


async def test_a_refused_bridge_write_is_reported_and_the_rest_put_back(lab):
    printed = []
    moving = roamer(lab, out=printed.append)
    await moving.go("zha")
    lab.bridge.fail[("PUT", "device")] = "metadata refused"
    await moving.go("hue")
    assert any("Could not put back light.lab_a's name" in line for line in printed)
    assert len(lab.bridge.resources["room"]["r1"]["children"]) == 3


async def test_a_join_ha_never_shows_a_light_for_stops_the_move(lab, monkeypatch):
    monkeypatch.setattr(roam, "ENTITY_S", 0.02)
    join = lab.ha.join
    lab.ha.join = lambda integration, ieee, entity_id=None: join(integration, ieee)  # a device with no entity
    with pytest.raises(RoamError, match="joined ZHA, but HA showed no light for it"):
        await roamer(lab).go("zha")


async def test_a_release_the_network_never_takes_stops_the_move(lab, monkeypatch):
    monkeypatch.setattr(roam, "RELEASE_S", 0.02)
    await roamer(lab).go("zha")
    lab.ha.on_leave = None
    lab.ha._leave = lambda integration, ieee: None  # ZHA keeps the device
    with pytest.raises(RoamError, match="light.lab_a is still on ZHA 0.02 s after its removal"):
        await roamer(lab).go("zigbee2mqtt")
