"""The rig's profiles and connection settings. Shared by scripts/rig.py, the rig engine and the household check.

A profile (`profiles/<name>.yaml`, gitignored) is one test setup on the HA instance .env.rig connects to: the entities
the rig may move, by integration and role, and the automations and switches it pauses while it runs.

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
EXAMPLE = "example"  # profiles/example.yaml, the tracked template; never a profile itself
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


@dataclass(frozen=True, slots=True)
class RigEntity:
    entity_id: str
    roles: frozenset[str]
    powered_by: str | None = None  # the profile's switch this entity draws power through
    members: tuple[str, ...] = ()  # a group's member lights, for a group light without an entity_id attribute


@dataclass(slots=True)
class Profile:
    integrations: dict[str, list[RigEntity]] = field(default_factory=dict)
    # Automations and switches turned off while the rig runs: whatever would fight the tests on these entities.
    pause: tuple[str, ...] = ()
    name: str = ""

    @classmethod
    def load(cls, path: Path) -> Profile:
        raw = read_mapping(path)
        profile = cls(pause=pause_list(path, raw.pop("pause", None) or []), name=path.stem)
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
        for entity_id, supply in profile.power().items():
            if supply not in listed:
                raise ValueError(f"{path.name}: {entity_id} is powered_by {supply}, which the profile doesn't list")
        return profile

    def entity(self, integration: str, role: str) -> str | None:
        return next((e.entity_id for e in self.integrations.get(integration, ()) if role in e.roles), None)

    def members(self, integration: str, entity_id: str) -> tuple[str, ...]:
        return next((e.members for e in self.integrations.get(integration, ()) if e.entity_id == entity_id), ())

    def power(self) -> dict[str, str]:
        """Each entity that draws power through another, mapped to its supply, across every integration."""
        return {e.entity_id: e.powered_by for entities in self.integrations.values() for e in entities if e.powered_by}


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
    """Every profile in `directory`, by name; the tracked example is not one."""
    return sorted(path for path in directory.glob("*.yaml") if path.stem != EXAMPLE)


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
