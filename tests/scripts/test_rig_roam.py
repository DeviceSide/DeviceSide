"""Roaming (tests/rig/roam.py), against the Lab fake: each move, the rename, the stale-entry removal, the Hue home
saved and restored, a bulb that never joins, and recovery from wherever a crash leaves the bulbs."""

import asyncio
import json

import pytest

from scripts import check_private
from tests.rig import baseline, client, roam
from tests.rig.client import HAError, Z2MRemoveError
from tests.rig.home import HomeRecord
from tests.rig.journal import Journal
from tests.rig.profile import Profile, normalize_ieee
from tests.rig.roam import Roamer, RoamError
from tests.scripts.rig_fakes import LAB_A, LAB_B, LAB_BULBS, LAB_OPTIONS, FakeBridge, FakeHA, Lab, lab_profile

A, B, OPTIONS, BULBS = LAB_A, LAB_B, LAB_OPTIONS, LAB_BULBS


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(roam, "POLL_S", 0)
    for name, value in (("Z2M_SETTLE_S", 0), ("Z2M_ANSWER_S", 0.05), ("Z2M_POLL_S", 0), ("Z2M_CRASH_WATCH_S", 0.05)):
        monkeypatch.setattr(client, name, value)


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


async def test_a_z2m_join_reads_the_bulb_once_so_its_state_has_a_color_mode(lab):
    lab.ha.respond = lambda ha, service, data: {}
    await roamer(lab).go("zigbee2mqtt")
    reads = [call[2] for call in lab.ha.calls if call[:2] == ("device_side", "get_attributes")]
    assert reads == [{"entity_id": "light.lab_a"}, {"entity_id": "light.lab_b"}]


async def test_a_post_join_read_that_goes_unanswered_is_asked_again(lab, monkeypatch):
    first = lambda ha, service, data: {}  # noqa: E731
    failures = []

    def respond(ha, service, data):
        if service == "get_attributes" and data["entity_id"] == "light.lab_a" and not failures:
            failures.append(1)
            raise HAError("no genOnOff reply from Zigbee2MQTT")
        return first(ha, service, data)

    lab.ha.respond = respond
    printed = []
    await roamer(lab, out=printed.append).go("zigbee2mqtt")
    reads = [call[2]["entity_id"] for call in lab.ha.calls if call[:2] == ("device_side", "get_attributes")]
    assert reads == ["light.lab_a", "light.lab_a", "light.lab_b"]
    assert not [line for line in printed if line.startswith("Could not read")]


async def test_a_post_join_read_that_never_answers_is_reported_after_three_tries(lab):
    def respond(ha, service, data):
        raise HAError("no genOnOff reply from Zigbee2MQTT")

    lab.ha.respond = respond
    printed = []
    await roamer(lab, out=printed.append).go("zigbee2mqtt")
    reads = [call[2]["entity_id"] for call in lab.ha.calls if call[:2] == ("device_side", "get_attributes")]
    assert reads.count("light.lab_a") == 3
    assert any(line.startswith("Could not read light.lab_a") for line in printed)


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
    saved = HomeRecord(tmp_path).get(A[2:])["hue"]
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
    assert not journal.path.exists() and HomeRecord(tmp_path).all() == {}


async def test_a_home_half_put_back_keeps_the_first_home_through_the_next_move(lab, tmp_path):
    first = Journal(tmp_path / "first.json")
    await roamer(lab, first).go("zha")  # a run dies on ZHA
    lab.bridge.fail[("PUT", "room")] = "bridge busy"
    await Roamer.from_journal(lab.ha, lab.bridge, first).go("hue")  # its recovery can't put the room back
    rooms = lab.bridge.resources["room"]["r1"]["children"]
    assert rooms == [{"rid": "other-device", "rtype": "device"}]
    assert HomeRecord(tmp_path).get(A[2:])["hue"]["rooms"] == ["r1"]

    second = Journal(tmp_path / "second.json")
    await roamer(lab, second).go("zha")  # the next run leaves Hue from outside r1, and dies too
    assert HomeRecord(tmp_path).get(A[2:])["hue"]["rooms"] == ["r1"]

    del lab.bridge.fail[("PUT", "room")]
    await Roamer.from_journal(lab.ha, lab.bridge, second).go("hue")
    await Roamer.from_journal(lab.ha, lab.bridge, first).go("hue")
    device_a = await lab.bridge.device_id_by_ieee(A)
    assert {"rid": device_a, "rtype": "device"} in lab.bridge.resources["room"]["r1"]["children"]
    assert HomeRecord(tmp_path).all() == {}
    assert not first.path.exists() and not second.path.exists()


async def test_a_journal_from_before_the_home_record_has_its_home_read_in(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    await roamer(lab, journal).go("zha")
    old = {entry["entity_id"]: entry["hue"] for entry in HomeRecord(tmp_path).all().values()}
    (tmp_path / "device_side-rig.home.json").unlink()
    journal.update(roam=journal.get("roam") | {"home": old})

    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path)).go("hue")
    device_a = await lab.bridge.device_id_by_ieee(A)
    assert {"rid": device_a, "rtype": "device"} in lab.bridge.resources["room"]["r1"]["children"]
    assert not journal.path.exists()


async def test_the_journal_names_the_move_in_flight_before_the_release(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    seen = []
    deleted = lab.bridge.on_delete

    def on_delete(resource_type, resource_id):
        seen.append(json.loads(journal.path.read_text())["roam"] | {"home": HomeRecord(tmp_path).all()})
        deleted(resource_type, resource_id)

    lab.bridge.on_delete = on_delete
    await roamer(lab, journal).go("zha")
    assert seen[0]["move"] == {
        "from": {"light.lab_a": "hue", "light.lab_b": "hue"},
        "to": "zha",
        "bulbs": ["light.lab_a", "light.lab_b"],
    }
    assert seen[0]["bulbs"][0] == {"ieee": A[2:], "entity_id": "light.lab_a", "z2m_options": OPTIONS, "home": "hue"}
    assert set(seen[0]["home"]) == {A[2:], B[2:]}
    roamed = journal.get("roam")
    assert roamed["move"] is None and roamed["at"] == {"light.lab_a": "zha", "light.lab_b": "zha"}


async def test_a_bulb_that_never_joins_aborts_with_the_reset_instruction_and_closes_joining(lab, tmp_path, monkeypatch):
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    lab.stuck.add(A[2:])
    journal = Journal(tmp_path / "journal.json")
    with pytest.raises(
        RoamError,
        match=r"light.lab_a did not join ZHA within 0.05 s\. Not on any Zigbee network: light.lab_a\. Reset it over",
    ):
        await roamer(lab, journal).go("zha")
    assert not lab.ha.zha_open
    roamed = journal.get("roam")
    assert roamed["at"]["light.lab_a"] is None and roamed["move"]["to"] == "zha"
    assert A[2:] in HomeRecord(tmp_path).all()


async def test_z2m_joining_is_closed_even_when_a_bulb_never_joins(lab, monkeypatch):
    await roamer(lab).go("zha")
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    lab.stuck.add(B[2:])
    with pytest.raises(
        RoamError,
        match=r"coordinator only\. Not on any Zigbee network: light.lab_b\. It may have missed ZHA.s",
    ):
        await roamer(lab).go("zigbee2mqtt")
    assert not lab.ha.z2m_open
    assert await where(lab) == ["zigbee2mqtt", None]


@pytest.mark.parametrize(("network", "identifier"), [("zha", "zha"), ("zigbee2mqtt", "mqtt")])
async def test_a_bulb_that_missed_the_hue_leave_is_searched_back_released_alone_and_joins(
    lab, monkeypatch, network, identifier
):
    monkeypatch.setattr(roam, "MISSED_HUE_LEAVE_S", 0)
    lab.deaf[A[2:]] = 1
    printed = []
    moving = roamer(lab, out=printed.append)
    await moving.go(network)
    assert await where(lab) == [network, network]
    assert lab.device_of("light.lab_a")["identifiers"][0][0] == identifier
    assert f"light.lab_a not on {roam.NAMES[network]}; searching Hue in case the bridge's Leave missed it." in printed
    assert "Back on Hue: light.lab_a. Releasing each alone." in printed
    assert lab.searches == 1
    assert moving.arrived == ["light.lab_b", "light.lab_a"]  # so the next move releases light.lab_a first
    assert [e for e in lab.ha.entity_devices if e.startswith("light.hue_")] == []  # no generated ID left behind
    assert not lab.ha.zha_open and not lab.ha.z2m_open


async def test_the_wait_for_a_straggler_runs_from_the_last_join_not_the_window_opening(lab, monkeypatch):
    monkeypatch.setattr(roam, "MISSED_HUE_LEAVE_S", 0.3)
    lab.stuck |= {A[2:], B[2:]}

    def serially(network):  # light.lab_a joins at 0.2 s, light.lab_b at 0.45 s: past 0.3 s from the opening
        loop = asyncio.get_running_loop()
        for ieee, delay in ((A[2:], 0.2), (B[2:], 0.45)):
            loop.call_later(delay, lambda ieee=ieee: (lab.stuck.discard(ieee), lab.opened(network)))

    lab.ha.on_open = serially
    await roamer(lab).go("zha")
    assert await where(lab) == ["zha", "zha"]
    assert lab.searches == 0


async def test_a_bulb_that_misses_the_hue_leave_again_gets_no_second_retry(lab, monkeypatch):
    monkeypatch.setattr(roam, "MISSED_HUE_LEAVE_S", 0)
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    lab.deaf[A[2:]] = 2
    with pytest.raises(RoamError, match=r"light.lab_a did not join Z2M .* Not on any Zigbee network: light.lab_a\."):
        await roamer(lab).go("zigbee2mqtt")
    assert lab.searches == 1
    joins = [json.loads(c[2]["payload"]) for c in lab.ha.calls if c[2].get("topic", "").endswith("/permit_join")]
    opens = [payload for payload in joins if payload["time"] > 0]
    assert len(opens) == 2 and not lab.ha.z2m_open


async def test_a_bulb_from_hue_on_no_network_after_the_search_stops_the_move(lab, monkeypatch):
    monkeypatch.setattr(roam, "MISSED_HUE_LEAVE_S", 0)
    lab.stuck.add(A[2:])
    with pytest.raises(RoamError, match=r"light.lab_a did not join ZHA .* Not on any Zigbee network: light.lab_a\."):
        await roamer(lab).go("zha")
    assert lab.searches == 1  # the one search back; no second window for a bulb Hue didn't have
    assert await where(lab) == [None, "zha"]


async def test_a_bulb_listed_on_z2m_isnt_searched_back_to_hue(lab, monkeypatch):
    monkeypatch.setattr(roam, "MISSED_HUE_LEAVE_S", 0)
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    lab.ha.z2m_failing[normalize_ieee(A)] = roam.REINTERVIEWS + 1  # it joined; its interviews fail
    with pytest.raises(RoamError, match=r"Still or again on a network: light.lab_a on Z2M"):
        await roamer(lab).go("zigbee2mqtt")
    assert lab.searches == 0


async def test_a_bulb_from_another_network_isnt_searched_back_to_hue(lab, monkeypatch):
    await roamer(lab).go("zha")
    monkeypatch.setattr(roam, "MISSED_HUE_LEAVE_S", 0)
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    lab.stuck.add(B[2:])
    with pytest.raises(RoamError, match=r"Not on any Zigbee network: light.lab_b"):
        await roamer(lab).go("zigbee2mqtt")
    assert lab.searches == 0


async def test_recovery_moves_a_bulb_a_crash_left_on_hue_mid_retry(lab, tmp_path, monkeypatch):
    monkeypatch.setattr(roam, "MISSED_HUE_LEAVE_S", 0)
    lab.deaf[A[2:]] = 1
    journal = Journal(tmp_path / "journal.json")
    released = Roamer.release
    releases = []

    async def crash_on_the_second(self, network, bulb):
        releases.append(bulb.entity_id)
        if releases.count("light.lab_a") == 2:
            raise KeyboardInterrupt
        await released(self, network, bulb)

    with monkeypatch.context() as patch:
        patch.setattr(Roamer, "release", crash_on_the_second)
        with pytest.raises(KeyboardInterrupt):
            await roamer(lab, journal).go("zigbee2mqtt")
    assert Journal(journal.path).get("roam")["at"]["light.lab_a"] == "hue"
    assert await where(lab) == ["hue", "zigbee2mqtt"]

    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), lambda _: None).go("zigbee2mqtt")
    assert await where(lab) == ["zigbee2mqtt", "zigbee2mqtt"]
    assert lab.device_of("light.lab_a")["identifiers"][0][0] == "mqtt"


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

    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), lambda _: None).go("hue")

    assert await where(lab) == ["hue", "hue"]
    assert lab.device_of("light.lab_a")["identifiers"][0][0] == "hue"
    assert len(lab.bridge.resources["room"]["r1"]["children"]) == 3
    assert not journal.path.exists()


async def test_recovery_joins_bulbs_released_mid_move_and_on_no_network_straight_home(lab, tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.json")
    lab.stuck |= {A[2:], B[2:]}
    with monkeypatch.context() as patch:
        patch.setattr(roam, "JOIN_S", 0)
        with pytest.raises(RoamError):
            await roamer(lab, journal).go("zha")
    lab.stuck.clear()  # still searching: they join whatever opens next
    assert await where(lab) == [None, None]

    printed = []
    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), printed.append).go("hue")

    assert "Moving light.lab_a, light.lab_b from no network (a move cut short) to Hue." in printed
    assert await where(lab) == ["hue", "hue"]
    assert lab.device_of("light.lab_a")["identifiers"][0][0] == "hue"
    assert len(lab.bridge.resources["room"]["r1"]["children"]) == 3
    assert not journal.path.exists()


async def test_bulbs_split_across_networks_go_home_in_one_move(lab):
    await roamer(lab).go("zha")
    await Roamer(lab.ha, lab.bridge, BULBS[1:], None, out=lambda _: None).go("zigbee2mqtt")
    assert await where(lab) == ["zha", "zigbee2mqtt"]
    printed = []
    await roamer(lab, out=printed.append).go("hue")
    assert await where(lab) == ["hue", "hue"]
    moves = [line for line in printed if line.startswith("Moving")]
    assert moves == ["Moving light.lab_a, light.lab_b from ZHA and Z2M to Hue."]  # one direct move, one search
    assert lab.searches == 1


async def test_a_bulb_on_no_network_stops_with_the_reset_instruction(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    await roamer(lab, journal).go("zha")
    await lab.ha.zha_remove("00:17:88:01:0a:bc:de:f1")  # light.lab_b leaves, and nothing is open
    with pytest.raises(RoamError, match=r"Not on any Zigbee network: light.lab_b\. Reset it over Bluetooth"):
        await Roamer.from_journal(lab.ha, lab.bridge, journal).go("hue")
    assert await where(lab) == ["zha", None]
    assert HomeRecord(tmp_path).all()


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
        (f'    - ieee: "{A.upper()}"\n      entity_id: light.lab_c\n      home: hue\n', "two roam bulbs share an IEEE"),
        ('    - ieee: "0x0017"\n      entity_id: light.lab_c\n      home: hue\n', "isn't 16 hex digits"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: light.lab_a\n      home: hue\n', "share an entity ID"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: switch.x\n      home: hue\n', "must be a light"),
        (
            '    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      home: hue\n      roles: [group]\n',
            "not a group",
        ),
        (
            '    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      home: hue\n      roles: [bulb]\n',
            "unknown roles",
        ),
        (
            '    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      home: hue\n      zigbee: 1\n',
            "unknown keys",
        ),
        (
            '    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      home: hue\n      z2m_options: [a]\n',
            "must be a mapping",
        ),
        ("    - entity_id: light.c\n      home: hue\n", "needs an ieee, an entity_id and a home"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: light.c\n', "needs an ieee, an entity_id and a home"),
        ('    - ieee: "0x0017880100000003"\n      entity_id: light.c\n      home: zha\n', "only hue homes are"),
        ("  zones: []\n", "roam must be a mapping with a networks list"),
    ],
)
def test_a_profile_refuses_a_bad_roam_bulb(tmp_path, extra, error):
    with pytest.raises(ValueError, match=error):
        Profile.load(lab_profile(tmp_path, extra))


@pytest.mark.parametrize(
    ("networks", "error"),
    [
        ("zha, zigbee2mqtt", "light.lab_a's home, hue, isn't in roam networks"),
        ("hue, thread", "roam needs networks"),
        ("", "roam needs networks"),
    ],
)
def test_a_profile_refuses_bad_roam_networks(tmp_path, networks, error):
    with pytest.raises(ValueError, match=error):
        Profile.load(lab_profile(tmp_path, networks=networks))


def test_a_profile_lists_roaming_bulbs_only_under_its_declared_networks(tmp_path):
    profile = Profile.load(lab_profile(tmp_path, networks="zigbee2mqtt, hue"))
    assert profile.roam_networks == ("hue", "zigbee2mqtt")
    assert profile.entity("zigbee2mqtt", "light_color") == "light.lab_a"
    assert profile.entity("zha", "light_color") is None


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


def overrides(lab: Lab) -> list[dict]:
    """Each Z2M options request that touched a light's HA override, in order."""
    return [
        json.loads(call[2]["payload"])["options"]["homeassistant"]
        for call in lab.ha.calls
        if call[:2] == ("mqtt", "publish")
        and call[2]["topic"].endswith("/device/options")
        and "homeassistant" in json.loads(call[2]["payload"])["options"]
    ]


@pytest.fixture
def withheld(lab, monkeypatch) -> Lab:
    """Z2M holds light.lab_a's light published, which HA has lost (#208)."""
    monkeypatch.setattr(roam, "REDISCOVER_S", 0.02)
    lab.ha.z2m_withheld.add(normalize_ieee(A))
    return lab


async def test_a_z2m_light_ha_lost_comes_back_by_an_override_set_then_cleared(withheld):
    printed = []
    await roamer(withheld, out=printed.append).go("zigbee2mqtt")
    assert withheld.device_of("light.lab_a")["identifiers"][0][0] == "mqtt"  # it took the fixed ID
    assert overrides(withheld) == [{"light": {"icon": "mdi:lightbulb"}}, {"light": {"icon": None}}]
    assert withheld.ha.z2m_options[A]["homeassistant"] == {"light": {"icon": None}}  # cleared: the payload as it was
    assert any(line.startswith("HA shows no light for light.lab_a on Z2M") for line in printed)


async def test_a_bulb_with_its_own_light_override_keeps_it_through_the_rediscovery(withheld):
    own = {"homeassistant": {"light": {"supported_color_modes": ["xy"]}}}
    await Roamer(withheld.ha, withheld.bridge, [roam.Bulb(A[2:], "light.lab_a", own)], out=lambda _: None).go(
        "zigbee2mqtt"
    )
    assert withheld.ha.z2m_options[A]["homeassistant"]["light"] == {"icon": None, "supported_color_modes": ["xy"]}


async def test_a_z2m_join_whose_light_shows_changes_no_override(lab):
    await roamer(lab).go("zigbee2mqtt")
    assert overrides(lab) == []


async def test_a_light_still_missing_after_the_override_stops_the_move(withheld, monkeypatch):
    monkeypatch.setattr(roam, "ENTITY_S", 0.02)
    withheld.ha.z2m_republishes = False
    with pytest.raises(RoamError, match="even 0.02 s after Z2M published its discovery again"):
        await roamer(withheld).go("zigbee2mqtt")


async def test_an_override_z2m_never_takes_stops_the_move(withheld, monkeypatch):
    monkeypatch.setattr(client, "Z2M_REQUEST_TIMEOUT_S", 0.02)
    withheld.ha.z2m_ignores.add("device/options")
    with pytest.raises(RoamError, match="Z2M didn't take its options: Zigbee2MQTT did not set"):
        await roamer(withheld).go("zigbee2mqtt")


async def test_a_release_the_network_never_takes_stops_the_move(lab, monkeypatch):
    monkeypatch.setattr(roam, "RELEASE_S", 0.02)
    await roamer(lab).go("zha")
    lab.ha.on_leave = None
    lab.ha._leave = lambda integration, ieee: None  # ZHA keeps the device
    with pytest.raises(RoamError, match="light.lab_a is still on ZHA 0.02 s after its removal"):
        await roamer(lab).go("zigbee2mqtt")


async def test_a_bulb_still_missing_after_the_hue_search_gets_one_more(lab):
    printed = []
    moving = roamer(lab, out=printed.append)
    await moving.go("zigbee2mqtt")
    lab.late.add(B[2:])
    await moving.go("hue")
    assert await where(lab) == ["hue", "hue"]
    assert lab.searches == 2
    assert "light.lab_b not on Hue after the search; searching once more." in printed


async def test_a_bulb_missing_after_both_hue_searches_stops_the_move(lab):
    moving = roamer(lab)
    await moving.go("zigbee2mqtt")
    lab.stuck.add(B[2:])
    with pytest.raises(
        RoamError,
        match=r"light.lab_b did not join Hue within 2 searches\. Not on any Zigbee network: light.lab_b\. Reset it",
    ):
        await moving.go("hue")
    assert lab.searches == 2


async def test_a_device_that_joins_the_hue_search_and_isnt_ours_is_named_and_left(lab):
    printed = []
    moving = roamer(lab, out=printed.append)
    await moving.go("zigbee2mqtt")
    lab.strangers = 1
    await moving.go("hue")
    named = [line for line in printed if "isn't a roaming bulb" in line]
    assert named == [
        "A device that isn't a roaming bulb joined the Hue bridge during the search: Hue motion sensor (SML001, "
        "device stranger-2). Check it in the Hue app; the rig leaves it there."
    ]
    assert "stranger-2" in lab.bridge.resources["device"]


async def test_the_run_waits_out_the_hue_search_before_it_ends(lab):
    moving = roamer(lab)
    await moving.go("zigbee2mqtt")
    lab.search_s = 0.05
    await moving.go("hue")
    assert lab.bridge.resources["zigbee_device_discovery"]["disc"]["status"] == "ready"


async def test_recovery_names_a_device_that_joined_the_search_a_crash_cut_short(lab, tmp_path, monkeypatch):
    journal = Journal(tmp_path / "journal.json")
    await roamer(lab, journal).go("zigbee2mqtt")
    lab.strangers = 1
    lab.search_s = 0.05

    async def killed(self, network, bulb):
        raise KeyboardInterrupt  # killed after the join, while the search is still open

    with monkeypatch.context() as patch:
        patch.setattr(Roamer, "adopt", killed)
        with pytest.raises(KeyboardInterrupt):
            await roamer(lab, Journal(journal.path)).go("hue")

    printed = []
    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), printed.append).go("hue")
    assert sum("isn't a roaming bulb" in line for line in printed) == 1
    assert not journal.path.exists()


async def test_a_bulb_goes_home_from_zha_in_one_direct_move(lab):
    await roamer(lab).go("zha")
    printed = []
    await roamer(lab, out=printed.append).go("hue")
    assert [line for line in printed if line.startswith("Moving")] == [
        "Moving light.lab_a, light.lab_b from ZHA to Hue."
    ]
    assert await where(lab) == ["hue", "hue"]
    assert lab.searches == 1 and not lab.ha.z2m_open


async def test_the_bulbs_leave_last_joined_first_so_no_leave_goes_through_a_bulb_already_gone(lab, tmp_path):
    # A bulb often joins through one that joined before it; removing that parent first lost the later bulb's Leave.
    journal = Journal(tmp_path / "journal.json")
    await roamer(lab, journal).go("zha")
    assert journal.get("roam")["arrived"] == ["light.lab_a", "light.lab_b"]
    await Roamer.from_journal(lab.ha, lab.bridge, journal, out=lambda _: None).go("zigbee2mqtt")
    removed = [c[2]["ieee"] for c in lab.ha.calls if c[1] == "remove"]
    assert [normalize_ieee(ieee) for ieee in removed] == [normalize_ieee(B), normalize_ieee(A)]


def test_a_bulb_whose_join_wasnt_seen_is_released_first(lab):
    rig = roamer(lab)
    rig.arrived = ["light.lab_a"]
    assert [bulb.entity_id for bulb in rig.release_order(rig.bulbs)] == ["light.lab_b", "light.lab_a"]
    rig.arrived = ["light.lab_b", "light.lab_a"]
    assert [bulb.entity_id for bulb in rig.release_order(rig.bulbs)] == ["light.lab_a", "light.lab_b"]


async def test_a_bulb_that_missed_its_leave_is_recorded_where_it_stayed_and_recovery_moves_it_again(
    lab, tmp_path, monkeypatch
):
    journal = Journal(tmp_path / "journal.json")
    await roamer(lab, journal).go("zha")
    released = Roamer.release

    async def deaf_b(self, network, bulb):
        if bulb.entity_id != "light.lab_b":  # light.lab_b ignores the Leave and stays on ZHA
            await released(self, network, bulb)

    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    with monkeypatch.context() as patch:
        patch.setattr(Roamer, "release", deaf_b)
        with pytest.raises(RoamError, match=r"Still or again on a network: light.lab_b on ZHA .*--recover moves it"):
            await roamer(lab, Journal(journal.path)).go("zigbee2mqtt")
    assert Journal(journal.path).get("roam")["at"]["light.lab_b"] == "zha"

    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), lambda _: None).go("hue")
    assert await where(lab) == ["hue", "hue"]


async def test_a_z2m_remove_that_cant_be_delivered_stops_with_the_power_cycle_instruction(lab, monkeypatch):
    await roamer(lab).go("zigbee2mqtt")

    async def undeliverable(ieee):
        raise Z2MRemoveError(f"Zigbee2MQTT did not remove {ieee} within 30 s", restarted=False)

    monkeypatch.setattr(lab.ha, "z2m_remove_device", undeliverable)
    with pytest.raises(
        RoamError, match=r"Z2M couldn't remove light.lab_a \(.*\): it didn't take the Leave\. Switch its lamp"
    ):
        await roamer(lab).go("hue")
    assert await where(lab) == ["zigbee2mqtt", "zigbee2mqtt"]


async def test_a_bulb_whose_z2m_interview_failed_is_interviewed_again_and_joins(lab):
    lab.ha.z2m_failing[normalize_ieee(A)] = 1  # the interview on joining fails, as the desk bulb's did on 3 Nov
    printed = []
    await roamer(lab, out=printed.append).go("zigbee2mqtt")
    assert await where(lab) == ["zigbee2mqtt", "zigbee2mqtt"]
    assert [normalize_ieee(ieee) for ieee in lab.ha.z2m_interviews] == [normalize_ieee(A)]
    assert "Z2M's interview of light.lab_a failed; asking for another (1)." in printed


async def test_a_bulb_whose_z2m_interviews_keep_failing_is_asked_a_bounded_number_of_times(lab, monkeypatch):
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    monkeypatch.setattr(roam, "REINTERVIEW_GAP_S", 0)
    lab.ha.z2m_failing[normalize_ieee(A)] = roam.REINTERVIEWS + 1
    with pytest.raises(
        RoamError,
        match=r"light.lab_a did not join Z2M within 0.05 s, open on the coordinator only\. Still or again on",
    ):
        await roamer(lab).go("zigbee2mqtt")
    assert len(lab.ha.z2m_interviews) == roam.REINTERVIEWS
    assert not lab.ha.z2m_open


async def test_z2m_logs_at_info_during_a_join_and_goes_back_to_its_own_level(lab):
    levels = []
    lab.ha.on_open = lambda network: (levels.append(lab.ha.z2m_level), lab.opened(network))
    await roamer(lab).go("zigbee2mqtt")
    assert levels == ["info"]
    assert lab.ha.z2m_level == "warning"


async def test_a_z2m_left_at_debug_by_no_run_is_left_there_for_the_join_then_lowered(lab):
    lab.ha.z2m_level = "debug"
    levels = []
    lab.ha.on_open = lambda network: (levels.append(lab.ha.z2m_level), lab.opened(network))
    printed = []
    await roamer(lab, out=printed.append).go("zigbee2mqtt")
    assert levels == ["debug"]
    assert lab.ha.z2m_level == "info"
    assert "Z2M's log level is debug with no run holding it; it goes back to info." in printed


async def test_a_crash_mid_join_leaves_the_level_in_the_baseline_and_recovery_puts_it_back(lab, tmp_path):
    journal = Journal.start(tmp_path)
    moving = roamer(lab, journal)

    async def killed_mid_join():
        raise KeyboardInterrupt

    moving.baseline.release = killed_mid_join
    with pytest.raises(KeyboardInterrupt):
        await moving.go("zigbee2mqtt")
    assert lab.ha.z2m_level == "info"
    held = json.loads((tmp_path / baseline.NAME).read_text())
    assert held == {"z2m_log_level": {"original": "warning", "holders": [f"{journal.name}#join"]}}

    await baseline.Baseline(lab.ha, tmp_path, journal.name).release()  # as --recover does, holding the journal
    assert lab.ha.z2m_level == "warning"
    assert not (tmp_path / baseline.NAME).exists()


async def test_a_z2m_that_wont_set_its_level_doesnt_stop_the_move(lab):
    lab.ha.z2m_ignores.add("options")
    printed = []
    moving = roamer(lab, out=printed.append)

    async def fast_timeout(level):
        raise TimeoutError(f"Zigbee2MQTT did not set its log level to {level} within 0 s")

    moving.ha.z2m_set_log_level = fast_timeout
    await moving.go("zigbee2mqtt")
    assert await where(lab) == ["zigbee2mqtt", "zigbee2mqtt"]
    assert any(line.startswith("Z2M's log level stays as it is for the join") for line in printed)


async def test_asks_for_one_bulb_wait_out_the_gap(lab, monkeypatch):
    monkeypatch.setattr(roam, "JOIN_S", 0.05)
    lab.ha.z2m_failing[normalize_ieee(A)] = roam.REINTERVIEWS + 1
    with pytest.raises(RoamError):
        await roamer(lab).go("zigbee2mqtt")
    assert len(lab.ha.z2m_interviews) == 1  # the 20 s gap outlasts the window


# --- a bulb listed where it isn't; Z2M's coordinator crashing mid-remove ----------------------------------------------


async def test_a_bulb_live_on_zha_and_stale_on_z2m_is_found_on_zha_and_joins_z2m(lab):
    """4 Nov, 09:29: Z2M still listed the A60 after a crash cut its remove short, and the rig took it for on Z2M."""
    await roamer(lab).go("zha")
    lab.stale("zigbee2mqtt", A)
    printed = []
    await roamer(lab, out=printed.append).go("zigbee2mqtt")
    assert "Removed light.lab_a's stale Z2M listing: it isn't there." in printed
    assert any(line.startswith("Moving light.lab_a, light.lab_b from ZHA to Z2M") for line in printed)
    assert await where(lab) == ["zigbee2mqtt", "zigbee2mqtt"]
    assert lab.device_of("light.lab_a")["identifiers"][0][0] == "mqtt"


async def test_a_stale_zha_listing_is_removed_where_the_bulb_is_on_hue(lab):
    lab.stale("zha", A)
    printed = []
    assert await roamer(lab, out=printed.append).locate(BULBS[0]) == "hue"
    assert "Removed light.lab_a's stale ZHA listing: it isn't there." in printed
    assert await lab.ha.device_by_ieee("zha", A) is None and A[2:] not in lab.searching


async def test_a_stale_listing_on_the_target_is_removed_before_the_window_opens(lab, monkeypatch):
    """A stale Z2M entry would read as arrived the moment the window opened."""
    opened = []

    def watch(network):
        opened.append([normalize_ieee(i) for i in lab.ha.z2m_devices])
        lab.opened(network)

    lab.ha.on_open = watch
    located = Roamer.locate

    async def blind(self, bulb):  # the listing appears after settle looked: only move's purge can catch it
        found = await located(self, bulb)
        if bulb.entity_id == "light.lab_a" and not lab.stale_on:
            lab.stale("zigbee2mqtt", A)
        return found

    monkeypatch.setattr(Roamer, "locate", blind)
    await roamer(lab).go("zigbee2mqtt")
    assert opened[0] == []
    assert await where(lab) == ["zigbee2mqtt", "zigbee2mqtt"]


async def test_a_bulb_live_on_two_networks_stops_the_move(lab):
    lab.ha.join("zigbee2mqtt", A)  # Z2M lists it, online, and it answers
    with pytest.raises(RoamError, match=r"light.lab_a is live on both Hue and Z2M"):
        await roamer(lab).go("zha")
    assert await lab.ha.z2m_has_device(A)
    assert await lab.bridge.device_id_by_ieee(A) is not None


async def test_a_z2m_listing_marked_online_that_doesnt_answer_is_stale(lab):
    lab.stale("zigbee2mqtt", A)
    lab.ha.z2m_availability_on = False  # no availability to read; the read decides
    printed = []
    assert await roamer(lab, out=printed.append).locate(BULBS[0]) == "hue"
    assert "Removed light.lab_a's stale Z2M listing: it isn't there." in printed


async def test_a_dead_hue_listing_is_kept_and_stops_the_move(lab):
    link = next(c for c in lab.bridge.resources["zigbee_connectivity"].values() if c["mac_address"].endswith("f0"))
    link["status"] = "connectivity_issue"
    lab.ha.join("zha", "00:17:88:01:0a:bc:de:f0", "light.zha_bulb_9")
    with pytest.raises(RoamError, match=r"The Hue bridge lists light.lab_a, but can't reach it, and it is live on ZHA"):
        await roamer(lab).go("zigbee2mqtt")
    assert await lab.bridge.device_id_by_ieee(A) is not None


async def test_a_bulb_listed_but_live_nowhere_stops_the_move(lab):
    await roamer(lab).go("zigbee2mqtt")
    lab.ha.z2m_offline.add(normalize_ieee(A))
    with pytest.raises(RoamError, match=r"light.lab_a is listed on Z2M but live on none"):
        await roamer(lab).go("hue")
    assert await lab.ha.z2m_has_device(A)


async def test_a_z2m_remove_a_coordinator_crash_cut_short_is_tried_again_once_z2m_is_back(lab, monkeypatch):
    await roamer(lab).go("zigbee2mqtt")
    lab.ha.z2m_remove_fails[normalize_ieee(A)] = 1
    lab.ha.z2m_crash_on_remove = True
    printed = []
    await roamer(lab, out=printed.append).go("hue")
    assert any(line.startswith("Z2M restarted while removing light.lab_a") for line in printed)
    assert await where(lab) == ["hue", "hue"]


async def test_a_z2m_remove_that_fails_across_two_crashes_names_the_crash(lab):
    await roamer(lab).go("zigbee2mqtt")
    lab.ha.z2m_remove_fails[normalize_ieee(A)] = 2
    lab.ha.z2m_crash_on_remove = True
    with pytest.raises(RoamError, match=r"Z2M couldn't remove light.lab_a .*Z2M's coordinator crashed mid-remove; see"):
        await roamer(lab).go("hue")


async def test_a_z2m_remove_error_with_z2m_up_names_the_bulb(lab):
    await roamer(lab).go("zigbee2mqtt")
    lab.ha.z2m_remove_fails[normalize_ieee(A)] = 1
    with pytest.raises(RoamError, match=r"Z2M couldn't remove light.lab_a \(Failed to remove .*Switch its lamp"):
        await roamer(lab).go("hue")


async def test_a_failed_z2m_remove_of_a_bulb_live_elsewhere_deletes_the_record_and_releases_it_there(lab, monkeypatch):
    await roamer(lab).go("zha")
    lab.ha.join("zigbee2mqtt", A)
    lab.stale_on.add(("zigbee2mqtt", normalize_ieee(A)))
    lab.ha.z2m_remove_fails[normalize_ieee(A)] = 1
    rig = roamer(lab)
    rig.at = {"light.lab_a": "zigbee2mqtt"}
    lab.ha.z2m_offline.add(normalize_ieee(A))  # dead on Z2M from here on, as its failed remove shows
    await rig.release("zigbee2mqtt", BULBS[0])
    assert not await lab.ha.z2m_has_device(A) and await lab.ha.device_by_ieee("zha", A) is None


async def test_a_failed_z2m_remove_of_a_bulb_live_on_hue_saves_its_home_before_releasing_it(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    lab.ha.join("zigbee2mqtt", A)
    lab.stale_on.add(("zigbee2mqtt", normalize_ieee(A)))
    lab.ha.z2m_remove_fails[normalize_ieee(A)] = 1
    lab.ha.z2m_offline.add(normalize_ieee(A))
    rig = roamer(lab, journal)
    await rig.release("zigbee2mqtt", BULBS[0])
    assert await lab.bridge.device_id_by_ieee(A) is None
    assert HomeRecord(tmp_path).get(A[2:])["hue"]["rooms"] == ["r1"]
