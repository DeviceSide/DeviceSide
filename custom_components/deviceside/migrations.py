"""The Hue Smooth Dimming repair: DeviceSide's actions are drop-ins for Hue Smooth Dimming's (docs/action-behavior.md,
Replacing hue_dimmer). Users may run both while they move their automations, so the repair only gives the renames and
deletes nothing. It stays as long as Hue Smooth Dimming can be installed.

The check deletes its issue once no `hue_dimmer` entry is left, so a finished move clears a stale issue on the next
start. HA keeps an ignored issue ignored when it is created again, so an ignored repair doesn't come back.
"""

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, REPO_URL

HUE_DIMMER_DOMAIN = "hue_dimmer"
HUE_DIMMER_ISSUE = "migrate_hue_dimmer"
# The README's "Coming from Hue Smooth Dimming?" box, which the repair's text follows.
HUE_DIMMER_URL = REPO_URL + "#coming-from-hue-smooth-dimming"


@callback
def async_check_hue_dimmer(hass: HomeAssistant) -> None:
    if hass.config_entries.async_entries(HUE_DIMMER_DOMAIN):
        ir.async_create_issue(
            hass,
            DOMAIN,
            HUE_DIMMER_ISSUE,
            is_fixable=False,
            is_persistent=False,
            learn_more_url=HUE_DIMMER_URL,
            severity=ir.IssueSeverity.WARNING,
            translation_key=HUE_DIMMER_ISSUE,
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, HUE_DIMMER_ISSUE)
