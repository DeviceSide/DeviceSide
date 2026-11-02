"""The rig-made ds-rig-* groups, zones and scenes (tests/rig/roam.py), against the Lab fake: made on each visit and
renamed to their fixed entity IDs, journaled first, removed before the bulbs move and by recovery, and the profile's
roam.groups that define them."""

import json

import pytest

from scripts import check_private
from tests.rig import roam
from tests.rig.journal import Journal
from tests.rig.profile import Profile, RoamGroup
from tests.rig.roam import Roamer, RoamError
from tests.scripts.rig_fakes import LAB_A, LAB_B, LAB_BULBS, FakeBridge, FakeHA, Lab, lab_profile

A, B, BULBS = LAB_A, LAB_B, LAB_BULBS
GROUP = RoamGroup("light.test_group", frozenset({"group"}), ("light.lab_a", "light.lab_b"), "scene.test_relax")
COLOR = RoamGroup("light.test_color_group", frozenset({"group_color"}), ("light.lab_a",))
GROUPS_YAML = (
    "  groups:\n"
    "    - entity_id: light.test_group\n      roles: [group]\n      members: all\n      scene: scene.test_relax\n"
    "    - entity_id: light.test_color_group\n      roles: [group_color]\n      members: [light.lab_a]\n"
)
FIXED = ("light.test_group", "light.test_color_group")


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(roam, "POLL_S", 0)
    monkeypatch.setattr(roam, "ZHA_LEAVE_GAP_S", 0)
    monkeypatch.setattr(roam, "GONE_S", 0)


@pytest.fixture
def lab() -> Lab:
    return Lab(FakeHA({}), FakeBridge(), {A: "light.lab_a", B: "light.lab_b"})


def roamer(lab: Lab, journal: Journal | None = None, out=None, groups=(GROUP, COLOR)) -> Roamer:
    return Roamer(lab.ha, lab.bridge, BULBS, journal, out=(out if out is not None else lambda _: None), groups=groups)


def entity(lab: Lab, entity_id: str) -> dict | None:
    return lab.ha.entity_meta.get(entity_id)


def bridge_named(lab: Lab, kind: str) -> dict[str, dict]:
    items = lab.bridge.resources.get(kind, {}).values()
    return {item["metadata"]["name"]: item for item in items if "metadata" in item}


def lights_of(lab: Lab) -> list[str]:
    """The Hue light IDs of light.lab_a and light.lab_b, from HA's registry (a Hue light's unique_id)."""
    return [lab.ha.entity_meta[entity_id]["unique_id"] for entity_id in ("light.lab_a", "light.lab_b")]


async def test_on_hue_a_zone_per_group_and_a_scene_in_it_take_their_fixed_ids(lab):
    printed = []
    await roamer(lab, out=printed.append).make_groups("hue")

    zones, scenes = bridge_named(lab, "zone"), bridge_named(lab, "scene")
    light_a, light_b = lights_of(lab)
    zone = zones["ds-rig-test-group"]
    assert zone["children"] == [{"rid": light_a, "rtype": "light"}, {"rid": light_b, "rtype": "light"}]
    assert zones["ds-rig-test-color-group"]["children"] == [{"rid": light_a, "rtype": "light"}]
    assert entity(lab, "light.test_group") == {
        "platform": "hue",
        "unique_id": f"grouped-{zone['id']}",
        "disabled_by": None,
    }
    scene = scenes["ds-rig-test-relax"]
    assert scene["group"] == {"rid": zone["id"], "rtype": "zone"}
    assert scene["actions"][0] == {
        "target": {"rid": light_a, "rtype": "light"},
        "action": {"on": {"on": True}, "dimming": {"brightness": 40.0}, "color_temperature": {"mirek": 366}},
    }
    assert entity(lab, "scene.test_relax")["unique_id"] == scene["id"]
    assert "Made Hue zone ds-rig-test-group as light.test_group." in printed


async def test_a_scene_sets_no_color_temperature_on_a_light_without_one(lab):
    light_b = lights_of(lab)[1]
    del lab.bridge.resources["light"][light_b]["color_temperature"]
    await roamer(lab).make_groups("hue")
    actions = bridge_named(lab, "scene")["ds-rig-test-relax"]["actions"]
    assert actions[1]["action"] == {"on": {"on": True}, "dimming": {"brightness": 40.0}}


async def test_a_zone_light_ha_adds_disabled_is_enabled_as_it_is_renamed(lab):
    lab.zones_disabled_by = "integration"
    await roamer(lab).make_groups("hue")
    assert entity(lab, "light.test_group")["disabled_by"] is None


async def test_on_zha_a_group_of_each_bulbs_light_endpoint(lab):
    moving = roamer(lab)
    await moving.go("zha")
    await moving.make_groups("zha")
    groups = {group["name"]: group for group in await lab.ha.zha_groups()}
    assert groups["ds-rig-test-group"]["members"] == [
        {"ieee": "00:17:88:01:0a:bc:de:f0", "endpoint_id": 11},
        {"ieee": "00:17:88:01:0a:bc:de:f1", "endpoint_id": 11},
    ]
    group_id = groups["ds-rig-test-group"]["group_id"]
    assert entity(lab, "light.test_group")["unique_id"] == f"light_zha_group_0x{group_id:04x}"
    assert "scene.test_relax" not in lab.ha.entity_meta  # a scene is Hue's only


async def test_on_z2m_a_group_of_the_bulbs_found_by_its_device(lab):
    moving = roamer(lab)
    await moving.go("zigbee2mqtt")
    await moving.make_groups("zigbee2mqtt")
    assert lab.ha.z2m_groups == {"ds-rig-test-group": [A, B], "ds-rig-test-color-group": [A]}
    assert entity(lab, "light.test_group")["platform"] == "mqtt"
    assert lab.ha.entity_devices["light.test_group"] == f"z2m-group-{lab.ha.z2m_group_ids['ds-rig-test-group']}"


@pytest.mark.parametrize(("network", "following"), [("hue", "zha"), ("zha", "zigbee2mqtt"), ("zigbee2mqtt", "hue")])
async def test_the_groups_go_before_the_bulbs_move_on(lab, tmp_path, network, following):
    journal = Journal(tmp_path / "journal.json")
    moving = roamer(lab, journal)
    await moving.go(network)
    await moving.make_groups(network)
    made = [made["entity_id"] for made in journal.get("roam")["made"]]
    expected = ["light.test_group", *(["scene.test_relax"] if network == "hue" else [])]
    expected += [] if network == "zha" else ["light.test_color_group"]  # one member: ZHA gives it no entity
    assert made == expected

    await moving.go(following)

    assert not any(entity(lab, fixed) for fixed in (*FIXED, "scene.test_relax"))
    assert bridge_named(lab, "zone") == {} and bridge_named(lab, "scene") == {}
    assert lab.ha.zha_group_names == {} and lab.ha.z2m_groups == {}
    assert (Journal(journal.path).get("roam") or {}).get("made", []) == []


async def test_each_group_is_journaled_before_it_is_made(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    seen = []
    posted = lab.bridge.on_post

    def on_post(resource_type, item):
        seen.append(json.loads(journal.path.read_text())["roam"]["made"][-1])
        posted(resource_type, item)

    lab.bridge.on_post = on_post
    await roamer(lab, journal).make_groups("hue")
    assert seen[0] == {
        "network": "hue",
        "kind": "zone",
        "name": "ds-rig-test-group",
        "entity_id": "light.test_group",
        "renamed": False,
    }
    assert all(made["renamed"] for made in journal.get("roam")["made"])


async def test_a_fixed_id_already_taken_stops_before_anything_is_made(lab, tmp_path):
    lab.ha.register("light.test_group", None, "template", "someone-elses")
    journal = Journal(tmp_path / "journal.json")
    with pytest.raises(RoamError, match="light.test_group is already in HA's entity registry"):
        await roamer(lab, journal).make_groups("hue")
    assert bridge_named(lab, "zone") == {}
    assert journal.get("roam") is None


async def test_a_group_left_on_the_network_stops_with_recover(lab):
    await lab.ha.z2m_group_add("ds-rig-test-group")
    moving = roamer(lab)
    await moving.go("zigbee2mqtt")
    with pytest.raises(RoamError, match="Z2M already has a group named ds-rig-test-group, which no run journaled"):
        await moving.make_groups("zigbee2mqtt")


async def test_an_entity_ha_keeps_after_its_group_goes_is_removed(lab):
    lab.ha.keeps_group_entities = True
    printed = []
    moving = roamer(lab, out=printed.append)
    await moving.go("zha")
    await moving.make_groups("zha")
    await moving.remove_groups()
    assert "light.test_group" not in lab.ha.entity_devices
    assert "Removed light.test_group, which HA kept after its group went." in printed


async def test_an_entity_of_another_platform_under_a_fixed_id_is_left_alone(lab):
    moving = roamer(lab, groups=(COLOR,))
    await moving.make_groups("hue")
    await lab.bridge.delete("zone", bridge_named(lab, "zone")["ds-rig-test-color-group"]["id"])
    lab.ha.register("light.test_color_group", None, "template", "someone-elses")
    await moving.remove_groups()
    assert entity(lab, "light.test_color_group")["platform"] == "template"
    assert moving.made == []


async def test_a_group_that_cant_be_removed_stays_journaled_and_is_retried(lab, tmp_path):
    journal = Journal(tmp_path / "journal.json")
    printed = []
    moving = roamer(lab, journal, printed.append, groups=(COLOR,))
    await moving.make_groups("hue")
    lab.bridge.fail[("DELETE", "zone")] = "busy"

    await moving.go("hue")

    assert any(line.startswith("Could not remove Hue zone ds-rig-test-color-group") for line in printed)
    assert [made["name"] for made in journal.get("roam")["made"]] == ["ds-rig-test-color-group"]
    del lab.bridge.fail[("DELETE", "zone")]
    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), lambda _: None).go(roam.HOME)
    assert bridge_named(lab, "zone") == {} and not journal.path.exists()


async def test_a_group_ha_never_shows_is_still_removed_by_name(lab, tmp_path, monkeypatch):
    monkeypatch.setattr(roam, "ENTITY_S", 0.02)
    journal = Journal(tmp_path / "journal.json")
    moving = roamer(lab, journal, groups=(GROUP,))
    await moving.go("zha")
    register, lab.ha.register = lab.ha.register, lambda *args, **kwargs: None  # HA never adds the group's light
    with pytest.raises(RoamError, match="HA showed no entity for the rig's ZHA group ds-rig-test-group"):
        await moving.make_groups("zha")
    lab.ha.register = register
    assert journal.get("roam")["made"][0]["renamed"] is False

    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), lambda _: None).go(roam.HOME)

    assert lab.ha.zha_group_names == {}
    assert not journal.path.exists()


@pytest.mark.parametrize("network", ["hue", "zha", "zigbee2mqtt"])
async def test_recovery_removes_the_groups_a_crash_left_then_brings_the_bulbs_home(lab, tmp_path, network):
    journal = Journal(tmp_path / "journal.json")
    moving = roamer(lab, journal)
    await moving.go(network)
    await moving.make_groups(network)

    await Roamer.from_journal(lab.ha, lab.bridge, Journal(journal.path), lambda _: None).go(roam.HOME)

    assert not any(entity(lab, fixed) for fixed in (*FIXED, "scene.test_relax"))
    assert bridge_named(lab, "zone") == {} and bridge_named(lab, "scene") == {}
    assert lab.ha.zha_group_names == {} and lab.ha.z2m_groups == {}
    assert not journal.path.exists()


async def test_a_zha_bulb_with_no_endpoint_in_its_unique_id_cant_join_a_group(lab):
    moving = roamer(lab, groups=(GROUP,))
    await moving.go("zha")
    lab.ha.entity_meta["light.lab_a"]["unique_id"] = "odd"
    with pytest.raises(RoamError, match="light.lab_a has no ZHA light endpoint"):
        await moving.make_groups("zha")


def test_a_profile_lists_each_group_under_every_network_and_the_scene_under_hue(tmp_path):
    profile = Profile.load(lab_profile(tmp_path, GROUPS_YAML))
    assert profile.roam_groups == (GROUP, COLOR)
    for network in ("hue", "zha", "zigbee2mqtt"):
        assert profile.entity(network, "group") == "light.test_group"
        assert profile.members(network, "light.test_group") == ("light.lab_a", "light.lab_b")
        # A one-member group has no ZHA entity, so ZHA's group_color cases skip.
        expected = None if network == "zha" else "light.test_color_group"
        assert profile.entity(network, "group_color") == expected
    assert profile.entity("hue", "scene") == "scene.test_relax"
    assert profile.entity("zha", "scene") is None
    lines = roam.plan_lines(profile.roam, profile.roam_groups)
    assert (
        "Makes ds-rig-test-group on each visit as light.test_group (light.lab_a, light.lab_b), with scene "
        "scene.test_relax (Hue); removed after it."
    ) in lines
    assert (
        "Makes ds-rig-test-color-group on each visit but ZHA's (one member; ZHA needs 2) as light.test_color_group "
        "(light.lab_a); removed after it."
    ) in lines
    assert roam.plan_lines(profile.roam, profile.roam_groups[1:], moving=False) == [
        "Makes ds-rig-test-color-group on Hue as light.test_color_group (light.lab_a); removed after it."
    ]


def group_yaml(**fields: str) -> str:
    item = {"entity_id": "light.lab_g", "roles": "[group]", "members": "all"} | fields
    lines = [f"      {key}: {value}" for key, value in item.items() if value is not None]
    return "  groups:\n    - " + "\n".join(lines).lstrip() + "\n"


@pytest.mark.parametrize(
    ("extra", "error"),
    [
        (group_yaml(members=None), "needs an entity_id and members"),
        (group_yaml(entity_id="switch.g"), "must be a light"),
        (group_yaml(roles="[light_ct]"), "takes group roles only"),
        (group_yaml(roles="[]"), "takes group roles only"),
        (group_yaml(members="[light.elsewhere]"), "lists light.elsewhere, not a roam bulb"),
        (group_yaml(members="[]"), "members must be all or a list"),
        (group_yaml(roles="[group_color]"), "light.lab_b has no light_color role"),
        (group_yaml(scene="light.x"), "scene must be a scene entity ID"),
        (group_yaml(roles="[group_color]", members="[light.lab_a]", scene="scene.x"), "needs the group role"),
        (group_yaml(colour="red"), "unknown keys"),
        (group_yaml(entity_id="light.a_very_long_name_for_a_group"), "too long: Hue would name it"),
        (group_yaml(entity_id="light.lab_a"), "share an entity ID"),
        (group_yaml(scene="scene.lab_g") + group_yaml(entity_id="light.lab_h").replace("  groups:\n", ""), "role"),
    ],
)
def test_a_profile_refuses_a_bad_roam_group(tmp_path, extra, error):
    with pytest.raises(ValueError, match=error):
        Profile.load(lab_profile(tmp_path, extra))


def test_a_roam_group_cant_also_be_a_fixed_entity(tmp_path):
    path = lab_profile(tmp_path, GROUPS_YAML + "hue:\n  - entity_id: scene.test_relax\n    roles: [scene]\n")
    with pytest.raises(ValueError, match="scene.test_relax roams"):
        Profile.load(path)


@pytest.mark.parametrize(("network", "role"), [("hue", "scene"), ("zigbee2mqtt", "group_color")])
def test_a_role_roam_groups_make_cant_also_be_on_a_fixed_entity(tmp_path, network, role):
    path = lab_profile(tmp_path, GROUPS_YAML + f"{network}:\n  - entity_id: light.fixed\n    roles: [{role}]\n")
    with pytest.raises(ValueError, match=f"{network} lists a fixed {role}, which roam.groups makes"):
        Profile.load(path)


def test_the_household_check_flags_a_roam_groups_and_scenes_entity_ids(tmp_path):
    terms = check_private.private_terms([lab_profile(tmp_path, GROUPS_YAML)], tmp_path / "none", tmp_path / "none")
    assert {"light.test_group", "light.test_color_group", "scene.test_relax"} <= set(terms)
