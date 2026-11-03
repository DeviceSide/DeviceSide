"""The rig's profiles and connection settings. Shared by scripts/rig.py, the rig engine and the household check.

A profile (`profiles/<name>.yaml`, gitignored) is one test setup on the HA instance .env.rig connects to: the entities
the rig may move, by integration and role, the automations and switches it pauses while it runs, and the bulbs it
roams between Zigbee networks (tests/rig/roam.py).

Pure file reading, no HA or pytest imports, so the runner's preflight can load it before anything mutates.
"""

import os
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

RIG_DIR = Path(__file__).parent
REPO = RIG_DIR.parents[1]


def main_checkout(repo: Path = REPO) -> Path:
    """The main checkout, which holds the gitignored household files for every linked worktree; else `repo`."""
    try:
        common = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return repo
    return Path(common).parent


MAIN_CHECKOUT = main_checkout()
PROFILES_DIR = MAIN_CHECKOUT / RIG_DIR.relative_to(REPO) / "profiles"
EXAMPLE = RIG_DIR / "profile.example.yaml"  # the tracked template a profile is copied from
# The single file profiles replaced; a run refuses while it is there, and the household check still reads it.
LEGACY_INVENTORY = MAIN_CHECKOUT / RIG_DIR.relative_to(REPO) / "inventory.yaml"
ENV_FILE = MAIN_CHECKOUT / ".env.rig"

PAUSABLE = ("automation", "switch")

# A native group's roles: `group_color` is one whose members all take color.
GROUP_ROLES = frozenset({"group", "group_color"})
ZHA_GROUP_MIN = 2  # ZHA makes no light entity for a group with fewer members
ROLES = frozenset(
    {"light_onoff", "light_wrapped", "light_dimmable", "light_ct", "light_color", "switch_plug", "scene"} | GROUP_ROLES
)

# Seconds either side of a duration within which a device may flip. Zigbee and Matter hop through a mesh.
TOLERANCE_S = {"shelly": 2.0, "hue": 2.0, "zigbee2mqtt": 3.0, "zha": 3.0, "matter": 3.0}

# Seconds after a move ends, or a stop, that an integration's adapters still predict a light's brightness rather
# than read it (Hue: API_SETTLE_SECONDS; Zigbee2MQTT: fade.SETTLE_SECONDS). A case waits them out on its lights, so
# it starts from what HA shows.
SETTLE_S = {"hue": 15.0, "zigbee2mqtt": 2.0}

# The order in which roaming bulbs visit the networks a run needs, moving directly from one to the next, after their
# home, where a run starts and ends.
CYCLE = ("hue", "zha", "zigbee2mqtt")
# The homes a roaming bulb may have: roam.py saves and puts back a bulb's rooms and scenes on Hue only.
HOMES = ("hue",)
# The key of a profile's `pause:` list that every run pauses, whatever integrations it holds.
PAUSE_ALL = "all"


def normalize_ieee(ieee: str) -> str:
    """An IEEE address as bare lowercase hex: Hue writes `00:17:88:...`, Z2M `0x0017...`, ZHA `00:17:...`."""
    return ieee.lower().removeprefix("0x").replace(":", "")


def colon_ieee(ieee: str) -> str:
    """ZHA's and the Hue bridge's spelling: `00:17:88:...`."""
    bare = normalize_ieee(ieee)
    return ":".join(bare[i : i + 2] for i in range(0, 16, 2))


def hex_ieee(ieee: str) -> str:
    """Zigbee2MQTT's spelling: `0x0017...`."""
    return f"0x{normalize_ieee(ieee)}"


@dataclass(frozen=True, slots=True)
class RigEntity:
    entity_id: str
    roles: frozenset[str]
    powered_by: str | None = None  # the profile's switch this entity draws power through
    members: tuple[str, ...] = ()  # a group's member lights, for a group light without an entity_id attribute


@dataclass(frozen=True, slots=True)
class RoamBulb:
    """A bulb the rig moves round CYCLE, renamed to `entity_id` on every network it joins."""

    ieee: str  # as bare lowercase hex (normalize_ieee); finds the bulb on every network
    entity_id: str
    roles: frozenset[str]
    z2m_options: dict = field(default_factory=dict)  # set again after each Z2M join: Z2M's remove drops them
    home: str = "hue"  # the network a run starts it from and ends it on


# What a rig-made group, zone or scene is called on its network, before HA's entity is renamed to its fixed ID.
RIG_PREFIX = "ds-rig-"
HUE_NAME_MAX = 32  # the longest name the Hue bridge takes for a zone or scene


@dataclass(frozen=True, slots=True)
class RoamGroup:
    """A native group of roam bulbs the rig makes on every network it visits: a Z2M group, a ZHA group or a Hue
    zone, renamed to `entity_id`; on Hue, with a scene in the zone renamed to `scene`, which takes the scene role."""

    entity_id: str
    roles: frozenset[str]
    members: tuple[str, ...]  # bulb entity IDs
    scene: str | None = None

    def made_on(self, network: str) -> bool:
        """Whether the rig makes this group on `network`: not a one-member group on ZHA, which gives a group a light
        entity only from two members, so the role has no entity there and its cases skip."""
        return network != "zha" or len(self.members) >= ZHA_GROUP_MIN


def rig_name(entity_id: str) -> str:
    """The native name of a rig-made group or scene with this fixed entity ID: `ds-rig-` and its object ID."""
    return RIG_PREFIX + entity_id.partition(".")[2].replace("_", "-")


@dataclass(slots=True)
class Profile:
    integrations: dict[str, list[RigEntity]] = field(default_factory=dict)
    # Automations and switches turned off while the rig runs, whatever would fight the tests on these entities: by
    # integration key, the run holding it pausing its list, and under PAUSE_ALL, those every run pauses.
    pause: dict[str, tuple[str, ...]] = field(default_factory=dict)
    name: str = ""
    roam: tuple[RoamBulb, ...] = ()
    roam_groups: tuple[RoamGroup, ...] = ()
    roam_networks: tuple[str, ...] = ()  # where the roaming bulbs may go, in CYCLE order, their home included

    @classmethod
    def load(cls, path: Path) -> Profile:
        raw = read_mapping(path)
        profile = cls(pause=pause_section(path, raw.pop("pause", None) or []), name=path.stem)
        profile.roam, profile.roam_groups, profile.roam_networks = roam_section(path, raw.pop("roam", None) or {})
        for integration, entities in raw.items():
            if integration not in TOLERANCE_S:
                raise ValueError(f"{path.name}: unknown integration {integration!r}; use {', '.join(TOLERANCE_S)}")
            profile.integrations[integration] = []
            for item in entities or []:
                roles = frozenset(item.get("roles", ()))
                if unknown := roles - ROLES:
                    raise ValueError(f"{path.name}: {item['entity_id']} has unknown roles {sorted(unknown)}")
                members = item.get("members", [])
                if not isinstance(members, list) or not all(isinstance(member, str) for member in members):
                    raise ValueError(f"{path.name}: {item['entity_id']} members must be a list of entity IDs")
                members = tuple(members)
                if members and not roles & GROUP_ROLES:
                    raise ValueError(f"{path.name}: {item['entity_id']} lists members but has no group role")
                profile.integrations[integration].append(
                    RigEntity(item["entity_id"], roles, item.get("powered_by"), members)
                )
        listed = {entity.entity_id for entities in profile.integrations.values() for entity in entities}
        profile.add_roaming(path, listed)
        for entity_id, supply in profile.power().items():
            if supply not in listed:
                raise ValueError(f"{path.name}: {entity_id} is powered_by {supply}, which the profile doesn't list")
        return profile

    def add_roaming(self, path: Path, listed: set[str]) -> None:
        """List each roaming bulb and rig-made group under every network the profile lets it visit, and each rig-made
        scene under Hue: while the bulbs are there, they are that network's entities. On any other network their
        roles find no entity, so those cases skip."""
        if both := sorted(listed & self.made_entities):
            raise ValueError(f"{path.name}: {', '.join(both)} roams, so it can't also be listed under an integration")
        made = {role for group in self.roam_groups for role in group.roles}
        made |= {"scene"} if any(group.scene for group in self.roam_groups) else set()
        for network in self.roam_networks:
            # The fixed entity would win (entity() takes the first), leaving the rig-made one unused.
            if taken := sorted(made & {role for e in self.integrations.get(network, ()) for role in e.roles}):
                raise ValueError(f"{path.name}: {network} lists a fixed {', '.join(taken)}, which roam.groups makes")
        for network in self.roam_networks if self.roam else ():
            entities = self.integrations.setdefault(network, [])
            entities.extend(RigEntity(b.entity_id, b.roles) for b in self.roam)
            entities.extend(
                RigEntity(g.entity_id, g.roles, members=g.members) for g in self.roam_groups if g.made_on(network)
            )
            if network == "hue":
                entities.extend(RigEntity(g.scene, frozenset({"scene"})) for g in self.roam_groups if g.scene)

    @property
    def roam_home(self) -> str | None:
        """The roaming bulbs' home, which they share (roam_section), or None with no roaming bulbs."""
        return self.roam[0].home if self.roam else None

    def paused_by(self, integrations: Iterable[str] | None = None) -> tuple[str, ...]:
        """What a run holding `integrations` (None: all of them) pauses: the PAUSE_ALL list, then each one's."""
        keys = [PAUSE_ALL, *(sorted(self.pause) if integrations is None else sorted(integrations))]
        return tuple(dict.fromkeys(entity for key in keys for entity in self.pause.get(key, ())))

    @property
    def made_entities(self) -> frozenset[str]:
        """The roaming bulbs' lights and the rig-made groups and scenes: entities HA has under these IDs only once the
        run has moved or made them."""
        bulbs = {bulb.entity_id for bulb in self.roam}
        return frozenset(bulbs | {e for group in self.roam_groups for e in (group.entity_id, group.scene) if e})

    def entity(self, integration: str, role: str) -> str | None:
        return next((e.entity_id for e in self.integrations.get(integration, ()) if role in e.roles), None)

    def members(self, integration: str, entity_id: str) -> tuple[str, ...]:
        return next((e.members for e in self.integrations.get(integration, ()) if e.entity_id == entity_id), ())

    def power(self) -> dict[str, str]:
        """Each entity that draws power through another, mapped to its supply, across every integration."""
        return {e.entity_id: e.powered_by for entities in self.integrations.values() for e in entities if e.powered_by}


def roam_section(path: Path, raw: object) -> tuple[tuple[RoamBulb, ...], tuple[RoamGroup, ...], tuple[str, ...]]:
    """A profile's `roam: {networks: [...], bulbs: [...], groups: [...]}`: the networks the bulbs may visit, each
    bulb's home among them and shared by all, as they move together; each IEEE and entity ID used once, and each
    group role on one group, since a run uses only the first."""
    if not raw:
        return (), (), ()
    if not isinstance(raw, dict) or set(raw) - {"networks", "bulbs", "groups"}:
        raise ValueError(
            f"{path.name}: roam must be a mapping with a networks list, a bulbs list and an optional groups list"
        )
    bulbs = tuple(roam_bulb(path, item) for item in raw.get("bulbs") or [])
    networks = roam_networks(path, raw.get("networks"), bulbs)
    if len({bulb.ieee for bulb in bulbs}) != len(bulbs):
        raise ValueError(f"{path.name}: two roam bulbs share an IEEE")
    groups = tuple(roam_group(path, item, bulbs) for item in raw.get("groups") or [])
    ids = [bulb.entity_id for bulb in bulbs]
    ids += [entity for group in groups for entity in (group.entity_id, group.scene) if entity]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path.name}: two roam bulbs, groups or scenes share an entity ID")
    for role in sorted(GROUP_ROLES):
        if len([group for group in groups if role in group.roles]) > 1:
            raise ValueError(f"{path.name}: two roam groups have the {role} role; a run uses only the first")
    return bulbs, groups, networks


def roam_networks(path: Path, raw: object, bulbs: tuple[RoamBulb, ...]) -> tuple[str, ...]:
    """`roam: networks:`, in CYCLE order: where the bulbs may go, their one home among them."""
    if not isinstance(raw, list) or not raw or set(map(str, raw)) - set(CYCLE):
        raise ValueError(f"{path.name}: roam needs networks, a list of where its bulbs may go: {', '.join(CYCLE)}")
    networks = tuple(network for network in CYCLE if network in raw)
    for bulb in bulbs:
        if bulb.home not in networks:
            raise ValueError(f"{path.name}: roam bulb {bulb.entity_id}'s home, {bulb.home}, isn't in roam networks")
    if len({bulb.home for bulb in bulbs}) > 1:
        raise ValueError(f"{path.name}: the roam bulbs move together, so they need one home")
    return networks


def roam_bulb(path: Path, item: object) -> RoamBulb:
    """One roam bulb: its IEEE, fixed light entity ID, home, roles and Z2M options."""
    if not isinstance(item, dict) or not {"ieee", "entity_id", "home"} <= set(item):
        raise ValueError(f"{path.name}: each roam bulb needs an ieee, an entity_id and a home")
    entity_id, ieee, home = str(item["entity_id"]), normalize_ieee(str(item["ieee"])), str(item["home"])
    if unknown := set(item) - {"ieee", "entity_id", "home", "roles", "z2m_options"}:
        raise ValueError(f"{path.name}: roam bulb {entity_id} has unknown keys {sorted(unknown)}")
    if not entity_id.startswith("light."):
        raise ValueError(f"{path.name}: roam bulb {entity_id} must be a light")
    if len(ieee) != 16 or set(ieee) - set("0123456789abcdef"):
        raise ValueError(f"{path.name}: roam bulb {entity_id} has an IEEE that isn't 16 hex digits")
    roles = frozenset(item.get("roles", ()))
    if unknown := roles - ROLES:
        raise ValueError(f"{path.name}: {entity_id} has unknown roles {sorted(unknown)}")
    if roles & GROUP_ROLES:
        raise ValueError(f"{path.name}: roam bulb {entity_id} is a bulb, not a group")
    if not isinstance(options := item.get("z2m_options") or {}, dict):
        raise ValueError(f"{path.name}: roam bulb {entity_id} z2m_options must be a mapping")
    if home not in HOMES:
        raise ValueError(
            f"{path.name}: roam bulb {entity_id} has home {home}; only {', '.join(HOMES)} homes are supported so far, "
            "as Hue is where the rig saves and puts back a bulb's rooms and scenes"
        )
    return RoamBulb(ieee, entity_id, roles, options, home)


def roam_group(path: Path, item: object, bulbs: tuple[RoamBulb, ...]) -> RoamGroup:
    """One rig-made group: its fixed light entity ID, group roles, members (`all` or bulb entity IDs) and an optional
    scene's fixed entity ID."""
    if not isinstance(item, dict) or not {"entity_id", "members"} <= set(item):
        raise ValueError(f"{path.name}: each roam group needs an entity_id and members")
    entity_id = str(item["entity_id"])
    if unknown := set(item) - {"entity_id", "roles", "members", "scene"}:
        raise ValueError(f"{path.name}: roam group {entity_id} has unknown keys {sorted(unknown)}")
    if not entity_id.startswith("light."):
        raise ValueError(f"{path.name}: roam group {entity_id} must be a light")
    roles = frozenset(item.get("roles", ()))
    if not roles or roles - GROUP_ROLES:
        only = ", ".join(sorted(GROUP_ROLES))
        raise ValueError(f"{path.name}: roam group {entity_id} takes group roles only: {only}")
    members = group_members(path, entity_id, roles, item["members"], bulbs)
    scene = item.get("scene")
    if scene is not None and (not isinstance(scene, str) or not scene.startswith("scene.")):
        raise ValueError(f"{path.name}: roam group {entity_id} scene must be a scene entity ID")
    if scene is not None and "group" not in roles:
        raise ValueError(f"{path.name}: roam group {entity_id} has a scene, so it needs the group role")
    for fixed in filter(None, (entity_id, scene)):
        if len(rig_name(fixed)) > HUE_NAME_MAX:
            raise ValueError(f"{path.name}: {fixed} is too long: Hue would name it {rig_name(fixed)}")
    return RoamGroup(entity_id, roles, members, scene)


def group_members(
    path: Path, entity_id: str, roles: frozenset[str], raw: object, bulbs: tuple[RoamBulb, ...]
) -> tuple[str, ...]:
    """A roam group's members: `all`, or a list of roam bulbs; for group_color, each one takes color."""
    by_id = {bulb.entity_id: bulb for bulb in bulbs}
    members = list(by_id) if raw == "all" else raw
    if not isinstance(members, list) or not members or not all(isinstance(member, str) for member in members):
        raise ValueError(f"{path.name}: roam group {entity_id} members must be all or a list of roam bulbs")
    if strangers := [member for member in members if member not in by_id]:
        raise ValueError(f"{path.name}: roam group {entity_id} lists {', '.join(strangers)}, not a roam bulb")
    if "group_color" in roles and (white := [m for m in members if "light_color" not in by_id[m].roles]):
        raise ValueError(f"{path.name}: {entity_id} is a group_color, but {', '.join(white)} has no light_color role")
    return tuple(dict.fromkeys(members))


def pause_section(path: Path, raw: object) -> dict[str, tuple[str, ...]]:
    """A profile's `pause:`: a list, which every run pauses, or a mapping of lists by PAUSE_ALL or integration key."""
    if isinstance(raw, list):
        raw = {PAUSE_ALL: raw}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: pause must be a list of entity IDs, or a mapping of such lists")
    if unknown := sorted(map(str, set(raw) - {PAUSE_ALL, *TOLERANCE_S})):
        raise ValueError(f"{path.name}: pause has unknown keys {unknown}; use {PAUSE_ALL} or {', '.join(TOLERANCE_S)}")
    return {key: pause_list(path, entity_ids or []) for key, entity_ids in raw.items()}


def pause_list(path: Path, entity_ids: object) -> tuple[str, ...]:
    """One of `pause:`'s lists of automations and switches."""
    if not isinstance(entity_ids, list) or not all(isinstance(entity_id, str) for entity_id in entity_ids):
        raise ValueError(f"{path.name}: pause must be a list of entity IDs, or a mapping of such lists")
    if other := [entity_id for entity_id in entity_ids if entity_id.partition(".")[0] not in PAUSABLE]:
        raise ValueError(f"{path.name}: pause takes automations and switches only, got {', '.join(other)}")
    return tuple(entity_ids)


def read_mapping(path: Path) -> dict:
    """A profile file's top-level mapping; an error names the file, so a typo in one doesn't read as a traceback."""
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as err:
        raise ValueError(f"{path.name}: not valid YAML: {err}") from err
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: must be a mapping of pause and integration keys")
    return raw


def profile_paths(directory: Path = PROFILES_DIR) -> list[Path]:
    """Every profile in `directory`, by name."""
    return sorted(directory.glob("*.yaml"))


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """KEY=value lines from .env.rig, overridden by the process environment."""
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if (line := line.strip()) and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip("\"'")
    for key in (
        "HA_URL",
        "HA_TOKEN",
        "HA_ADMIN_TOKEN",
        "RIG_SYNC_CMD",
        "RIG_STATUS_CMD",
        "RIG_RESTART_CMD",
        "RIG_PAUSE",  # moved into the profile; still read, so a run set it in refuses rather than ignores it
        "HUE_BRIDGE_HOST",
        "HUE_APP_KEY",
    ):
        if key in os.environ:
            env[key] = os.environ[key]
    return env
