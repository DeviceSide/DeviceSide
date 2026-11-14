"""The Hue v1 (round) bridge, which DeviceSide never supports (plan Decision 32): a separate integration on the `hue`
domain, as a different gateway or API is (docs/evidence.md, The split rule), declared only to refuse its entities.

Its detect hook claims every entity of a v1 config entry, so no Hue adapter ever sees one and none needs a check of
its own. Why v1 can't be supported: research/2026-11-14-v1-api.md (index.md, the user's line).
"""

from homeassistant.const import CONF_API_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ...core.scope import IntegrationInfo

# What a named target's refusal says (core/errors.py, TargetNotSupported), after "can't take this action".
WHY = (
    "Hue v1 (round) bridges aren't supported: the v1 API can't change a light while it's off and has no push updates, "
    "and Signify ended support for the v1 bridge in 2020"
)


def detect(hass: HomeAssistant, entry: er.RegistryEntry, device: dr.DeviceEntry | None) -> bool:
    """True for an entity of a v1 bridge's config entry: core's hue integration stores the API version in the entry's
    data (`api_version`), 1 only for a bridge with no CLIP v2, as it moves a v2-capable bridge's entry to 2 itself
    (homeassistant/components/hue/migration.py)."""
    if entry.config_entry_id is None or (config := hass.config_entries.async_get_entry(entry.config_entry_id)) is None:
        return False
    return config.data.get(CONF_API_VERSION) == 1


V1_BRIDGE = IntegrationInfo(
    key="hue_v1",
    title="Hue v1 bridge",
    ha_domain="hue",
    maintainers=("jasonmx",),
    detect=detect,
    unsupported=WHY,
)
