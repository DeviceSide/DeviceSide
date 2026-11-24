"""Parse a Matter entity's node address from its unique_id, and check OnOff cluster features.

No imports from homeassistant.components.matter or chip.clusters at module level: those packages
require matter_server and chip to be installed, but the adapter must import cleanly in test
environments where only the core homeassistant package is present.  All matter-specific operations
are accessed either through hass.config_entries or via deferred imports confined to two
helper functions (make_on_with_timed_off, and make_command for Level and Color Control).
"""

from homeassistant.core import HomeAssistant

from ...core.errors import Reason
from ...core.models import Target
from ...core.zcl import (
    COLOR_CLUSTER,
    CURRENT_LEVEL,
    LEVEL_CLUSTER,
    ON_LEVEL,
    ON_OFF,
    ON_OFF_CLUSTER,
    ON_TIME,
    READBACK_SLACK_TENTHS,
)

_MATTER_DOMAIN = "matter"

# The Options override of a Level or Color Control command: optionsMask picks the Options bits this command overrides,
# optionsOverride their values, and bit 0 is ExecuteIfOff. With it set, a light that is off stores the value and stays
# off; with neither set, the light's own Options apply (a lit light, or a stop with nothing running).
EXECUTE_IF_OFF = {"optionsMask": 1, "optionsOverride": 1}
NO_OVERRIDE = {"optionsMask": 0, "optionsOverride": 0}

# OnOff cluster constants (Matter spec, cluster 0x0006)
_FEATUREMAP_ATTR_ID = 65532  # 0xFFFC
_LT_FEATURE_BIT = 0x0001  # Lighting (LT) is bit 0; bit 1 (0x2) is DeadFrontBehavior


def node_id_from_unique_id(unique_id: str) -> int | None:
    """Parse the Matter node_id (int) from an entity unique_id.

    Matter unique_ids are constructed in homeassistant/components/matter/entity.py as:
        {node_device_id}-{endpoint_id}-{key}-{cluster_id}-{attr_id}
    where node_device_id = {fab_hex16}-{node_hex16}-{postfix}.

    fab_hex16 and node_hex16 are exactly 16 hex chars with no hyphens, so parts[0] is always
    fab_hex16 and parts[1] is always node_hex16 regardless of the postfix value.
    """
    parts = unique_id.split("-")
    if len(parts) < 7:
        return None
    try:
        return int(parts[1], 16)
    except ValueError:
        return None


def onoff_endpoint(unique_id: str) -> int | None:
    """The endpoint_id (int) of an OnOff.OnOff entity's unique_id, or None for any other entity.

    A target is addressed only when its unique_id ends in cluster 6, attribute 0: HA puts other switches on the
    plug's endpoint (e.g. Eve's child lock), and those must not be addressed as the endpoint's OnOff. See
    docs/integrations/matter/internals.md, Addressing.
    """
    parts = unique_id.split("-")
    if len(parts) < 7:
        return None
    try:
        if (int(parts[-2]), int(parts[-1])) != (ON_OFF_CLUSTER, ON_OFF):
            return None
        return int(parts[-4])
    except ValueError:
        return None


def matter_client(hass: HomeAssistant, config_entry_id: str | None = None):
    """Return the MatterClient for a given config entry, or None.

    When config_entry_id is supplied, the client for that specific entry is returned.
    When omitted, the first loaded Matter entry is used (production: there is only one).

    Reads hass.config_entries directly to stay independent of homeassistant.components.matter.
    In production, entry.runtime_data is a MatterEntryData whose .adapter.matter_client is
    the python-matter-server MatterClient.  In tests the fixture provides a mock in that slot.
    """
    if config_entry_id is not None:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or not hasattr(entry, "runtime_data"):
            return None
        return entry.runtime_data.adapter.matter_client

    entries = hass.config_entries.async_loaded_entries(_MATTER_DOMAIN)
    if not entries or not hasattr(entries[0], "runtime_data"):
        return None
    return entries[0].runtime_data.adapter.matter_client


def _attr_path(endpoint_id: int, cluster_id: int, attr_id: int) -> str:
    """An attribute's path as python-matter-server keys it: "{endpoint}/{cluster}/{attribute}"."""
    return f"{endpoint_id}/{cluster_id}/{attr_id}"


def _onoff_attr_path(endpoint_id: int, attr_id: int) -> str:
    return _attr_path(endpoint_id, ON_OFF_CLUSTER, attr_id)


def lt_feature(node, endpoint_id: int) -> bool:
    """True if the OnOff cluster on the endpoint has the Lighting (LT) feature bit set.

    Reads the node's raw attribute cache. Sync and cheap: no I/O. MatterEndpoint.get_attribute_value
    would need a real chip.clusters descriptor.
    """
    feature_map = node.node_data.attributes.get(_onoff_attr_path(endpoint_id, _FEATUREMAP_ATTR_ID))
    return isinstance(feature_map, int) and bool(feature_map & _LT_FEATURE_BIT)


def has_level(node, endpoint_id: int) -> bool:
    """True if the endpoint has a Level Control server: its CurrentLevel is in the node's attribute cache.

    CurrentLevel is mandatory on the cluster, and the server reports every attribute it holds, so the key is present
    exactly when the server is. Sync, no I/O, like lt_feature.
    """
    return _attr_path(endpoint_id, LEVEL_CLUSTER, CURRENT_LEVEL) in node.node_data.attributes


def color_features(node, endpoint_id: int) -> int:
    """The endpoint's Color Control FeatureMap from the node's attribute cache; 0 when unreported or not an int."""
    feature_map = node.node_data.attributes.get(color_feature_map_path(endpoint_id))
    return feature_map if isinstance(feature_map, int) else 0


def has_color(node, endpoint_id: int) -> bool:
    """True if the endpoint has a Color Control server: its FeatureMap is in the node's attribute cache (global to
    every cluster, so present exactly when the server is). Sync, no I/O, like has_level."""
    return color_feature_map_path(endpoint_id) in node.node_data.attributes


def node_for(hass: HomeAssistant, target: Target):
    """The target's MatterNode from the client's cache, sync and with no I/O, or None: an unparsable unique ID, no
    loaded Matter entry, or a node the server doesn't hold."""
    if (node_id := node_id_from_unique_id(target.entry.unique_id)) is None:
        return None
    if (client := matter_client(hass, target.entry.config_entry_id)) is None:
        return None
    try:
        return client.get_node(node_id)
    except Exception:  # noqa: BLE001 - node lookup can raise if the node no longer exists
        return None


def unsupported_reason(hass: HomeAssistant, target: Target) -> str | None:
    """Why DeviceSide can't address this entity's OnOff endpoint, or None: it needs a reachable node whose endpoint has
    the Lighting (LT) feature."""
    ep_id = onoff_endpoint(target.entry.unique_id)
    if ep_id is None or (node := node_for(hass, target)) is None:
        return Reason.NOT_ADDRESSABLE
    if not lt_feature(node, ep_id):
        return "no_lt_feature"
    return None


def light_reason(hass: HomeAssistant, target: Target) -> str | None:
    """Why a light action can't run on this entity, or None: unsupported_reason's, then not_dimmable for an endpoint
    with no Level Control server (plan Decision 11: Level and Color Control are on the OnOff entity's endpoint)."""
    if reason := unsupported_reason(hass, target):
        return reason
    # unsupported_reason found the endpoint and the node.
    return None if has_level(node_for(hass, target), onoff_endpoint(target.entry.unique_id)) else "not_dimmable"


def ontime_attr_path(endpoint_id: int) -> str:
    """Attribute path for OnOff.OnTime on the given endpoint, for python-matter-server's read_attribute."""
    return _onoff_attr_path(endpoint_id, ON_TIME)


def onoff_attr_path(endpoint_id: int) -> str:
    """Attribute path for OnOff.OnOff on the given endpoint, for python-matter-server's read_attribute."""
    return _onoff_attr_path(endpoint_id, ON_OFF)


def level_path(endpoint_id: int, attr_id: int = CURRENT_LEVEL) -> str:
    """Attribute path for a Level Control attribute (CurrentLevel by default)."""
    return _attr_path(endpoint_id, LEVEL_CLUSTER, attr_id)


def on_level_path(endpoint_id: int) -> str:
    return level_path(endpoint_id, ON_LEVEL)


def color_path(endpoint_id: int, attr_id: int) -> str:
    """Attribute path for a Color Control attribute: CURRENT_HUE, CURRENT_SATURATION, CURRENT_X, CURRENT_Y,
    COLOR_TEMPERATURE, or the FeatureMap."""
    return _attr_path(endpoint_id, COLOR_CLUSTER, attr_id)


def color_feature_map_path(endpoint_id: int) -> str:
    return color_path(endpoint_id, _FEATUREMAP_ATTR_ID)


async def read_timer(client, node_id: int, endpoint_id: int) -> tuple[object, object]:
    """OnTime (tenths of a second) and OnOff, read live, one path per read; a value the device leaves out is None.

    A timer runs only while both say so: OnTime > 0 alone is not enough, as a device may hold a stale OnTime while off.
    An error propagates.
    """
    values = []
    for path in (ontime_attr_path(endpoint_id), onoff_attr_path(endpoint_id)):
        answer = await client.read_attribute(node_id=node_id, attribute_path=path)
        values.append(answer.get(path))
    return values[0], values[1]


def timer_running(on_time: object, on_off: object) -> bool:
    return isinstance(on_time, int) and on_time > 0 and on_off is True


def timer_matches(read_on_time: object, on_off: object, on_time: int) -> bool:
    """Whether the timer running is the one just sent for `on_time` tenths: OnTime read straight back lies within
    READBACK_SLACK_TENTHS under it. A device keeps the longer of a running timer and a new one (the spec's
    max(OnTime, onTime)), so a shorter call during a longer timer reads above it and isn't confirmed."""
    return timer_running(read_on_time, on_off) and on_time - READBACK_SLACK_TENTHS <= read_on_time <= on_time


def make_command(cluster: str, command: str, **fields):
    """Create a chip.clusters.Objects.<cluster>.Commands.<command> object from its field names, for example
    make_command("LevelControl", "MoveToLevel", level=1, transitionTime=0, optionsMask=1, optionsOverride=1).

    Lazy import, as in make_on_with_timed_off. Used for LevelControl (MoveToLevel, MoveToLevelWithOnOff, Stop) and
    ColorControl (MoveToHueAndSaturation, MoveToColor, MoveToColorTemperature, MoveHue, EnhancedMoveHue,
    MoveSaturation, StopMoveStep).
    """
    from chip.clusters import Objects as clusters  # noqa: PLC0415

    return getattr(getattr(clusters, cluster).Commands, command)(**fields)


def make_on_with_timed_off(on_off_control: int, on_time: int, off_wait_time: int):
    """Create an OnOff.Commands.OnWithTimedOff command object.

    chip.clusters is imported here rather than at module level so the adapter module loads
    cleanly when chip is not installed.  Tests inject a sys.modules mock for chip.clusters
    so the lazy import resolves to the mock without the real package being present.
    """
    from chip.clusters import Objects as clusters  # noqa: PLC0415

    return clusters.OnOff.Commands.OnWithTimedOff(
        onOffControl=on_off_control,
        onTime=on_time,
        offWaitTime=off_wait_time,
    )
