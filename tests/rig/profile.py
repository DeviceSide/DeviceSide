"""The rig's profiles and connection settings. Shared by scripts/rig.py, the rig engine and the household check.

A profile (`profiles/<name>.yaml`, gitignored) is one test setup on the HA instance .env.rig connects to: the entities
the rig may move, by integration and role, the automations and switches it pauses while it runs, and the bulbs it
roams between Zigbee networks (tests/rig/roam.py).

Pure file reading, no HA or pytest imports, so the runner's preflight can load it before anything mutates.
"""

import os
import subprocess
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
ROLES = frozenset(
    {"light_onoff", "light_wrapped", "light_dimmable", "light_ct", "light_color", "switch_plug", "scene"} | GROUP_ROLES
)

# Seconds either side of a duration within which a device may flip. Zigbee and Matter hop through a mesh.
TOLERANCE_S = {"shelly": 2.0, "hue": 2.0, "zigbee2mqtt": 3.0, "zha": 3.0, "matter": 3.0}

# Seconds after a move ends, or a stop, that an integration's adapters still predict a light's brightness rather
# than read it (Hue: API_SETTLE_SECONDS; Zigbee2MQTT: fade.SETTLE_SECONDS). A case waits them out on its lights, so
# it starts from what HA shows.
SETTLE_S = {"hue": 15.0, "zigbee2mqtt": 2.0}

# The networks a roaming bulb visits, in the order it visits them: the only route the A60 move probe proved
# (docs/plans/2026-10-31-a60-move-probe.md). Hue is home, where a run starts and ends.
CYCLE = ("hue", "zha", "zigbee2mqtt")


def normalize_ieee(ieee: str) -> str:
    """An IEEE address as bare lowercase hex: Hue writes `00:17:88:...`, Z2M `0x0017...`, ZHA `00:17:...`."""
    return ieee.lower().removeprefix("0x").replace(":", "")


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


@dataclass(slots=True)
class Profile:
    integrations: dict[str, list[RigEntity]] = field(default_factory=dict)
    # Automations and switches turned off while the rig runs: whatever would fight the tests on these entities.
    pause: tuple[str, ...] = ()
    name: str = ""
    roam: tuple[RoamBulb, ...] = ()

    @classmethod
    def load(cls, path: Path) -> Profile:
        raw = read_mapping(path)
        profile = cls(pause=pause_list(path, raw.pop("pause", None) or []), name=path.stem)
        profile.roam = roam_bulbs(path, raw.pop("roam", None) or {})
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
        """List each roaming bulb under every network it visits: while it is there, it is that network's entity."""
        if both := sorted(listed & {bulb.entity_id for bulb in self.roam}):
            raise ValueError(f"{path.name}: {', '.join(both)} roams, so it can't also be listed under an integration")
        for network in CYCLE if self.roam else ():
            self.integrations.setdefault(network, []).extend(RigEntity(b.entity_id, b.roles) for b in self.roam)

    def entity(self, integration: str, role: str) -> str | None:
        return next((e.entity_id for e in self.integrations.get(integration, ()) if role in e.roles), None)

    def members(self, integration: str, entity_id: str) -> tuple[str, ...]:
        return next((e.members for e in self.integrations.get(integration, ()) if e.entity_id == entity_id), ())

    def power(self) -> dict[str, str]:
        """Each entity that draws power through another, mapped to its supply, across every integration."""
        return {e.entity_id: e.powered_by for entities in self.integrations.values() for e in entities if e.powered_by}


def roam_bulbs(path: Path, raw: object) -> tuple[RoamBulb, ...]:
    """A profile's `roam: {bulbs: [...]}`, each IEEE and entity ID used once."""
    if not isinstance(raw, dict) or set(raw) - {"bulbs"}:
        raise ValueError(f"{path.name}: roam must be a mapping with a bulbs list")
    bulbs = tuple(roam_bulb(path, item) for item in raw.get("bulbs") or [])
    for name, key in (("IEEE", "ieee"), ("entity ID", "entity_id")):
        values = [getattr(bulb, key) for bulb in bulbs]
        if len(set(values)) != len(values):
            raise ValueError(f"{path.name}: two roam bulbs share an {name}")
    return bulbs


def roam_bulb(path: Path, item: object) -> RoamBulb:
    """One roam bulb: its IEEE, fixed light entity ID, roles and Z2M options."""
    if not isinstance(item, dict) or not {"ieee", "entity_id"} <= set(item):
        raise ValueError(f"{path.name}: each roam bulb needs an ieee and an entity_id")
    entity_id, ieee = str(item["entity_id"]), normalize_ieee(str(item["ieee"]))
    if unknown := set(item) - {"ieee", "entity_id", "roles", "z2m_options"}:
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
    return RoamBulb(ieee, entity_id, roles, options)


def pause_list(path: Path, entity_ids: object) -> tuple[str, ...]:
    """A profile's `pause:`, a list of automations and switches."""
    if not isinstance(entity_ids, list) or not all(isinstance(entity_id, str) for entity_id in entity_ids):
        raise ValueError(f"{path.name}: pause must be a list of entity IDs")
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
