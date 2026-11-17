"""Repairs that move users to DeviceSide from what came before it.

- `legacy_device_side`: v0.0.1 shipped under the domain `device_side`. Marketplace installs `deviceside` beside it
  and leaves the old folder and its config entry in place, so HA keeps loading v0.0.1. HA has no domain-rename
  migration, and the v0.0.1 entry holds no data or options, so the fix removes the old copy and the user renames their
  `device_side.` calls. Delete this check in v0.2.0.
- `migrate_hue_dimmer`: DeviceSide's actions are drop-ins for Hue Smooth Dimming's (docs/action-behavior.md,
  Replacing hue_dimmer). Users may run both while they move their automations, so the repair only gives the renames
  and deletes nothing. It stays as long as Hue Smooth Dimming can be installed.

A check deletes its issue when its condition is false, so a fixed state clears a stale issue on the next start. HA
keeps an ignored issue ignored when it is created again, so an ignored repair doesn't come back.
"""

import json
import shutil
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

LEGACY_DOMAIN = "device_side"
LEGACY_ISSUE = "legacy_device_side"
HUE_DIMMER_DOMAIN = "hue_dimmer"
HUE_DIMMER_ISSUE = "migrate_hue_dimmer"
# The README's "Coming from Hue Smooth Dimming?" box, which the repair's text follows.
HUE_DIMMER_URL = "https://github.com/DeviceSide/DeviceSide#coming-from-hue-smooth-dimming"


def legacy_folder(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("custom_components", LEGACY_DOMAIN))


def _is_legacy_folder(path: Path) -> bool:
    """The deletion guard: only a real folder whose manifest names `device_side` is v0.0.1's copy."""
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        return False
    return isinstance(manifest, dict) and manifest.get("domain") == LEGACY_DOMAIN


async def async_check_migrations(hass: HomeAssistant) -> None:
    await _async_check_legacy(hass)
    _check_hue_dimmer(hass)


async def _async_check_legacy(hass: HomeAssistant) -> None:
    folder = legacy_folder(hass)
    if hass.config_entries.async_entries(LEGACY_DOMAIN) or await hass.async_add_executor_job(folder.is_dir):
        ir.async_create_issue(
            hass,
            DOMAIN,
            LEGACY_ISSUE,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=LEGACY_ISSUE,
            translation_placeholders={"folder": str(folder)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, LEGACY_ISSUE)


def _check_hue_dimmer(hass: HomeAssistant) -> None:
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


def _remove_folder(path: Path) -> bool:
    """Delete v0.0.1's folder if the guard passes; whether no folder is left."""
    if _is_legacy_folder(path):
        try:
            shutil.rmtree(path)
        except OSError:
            pass
    return not path.is_dir()


async def async_remove_legacy(hass: HomeAssistant) -> bool:
    """Remove every `device_side` config entry, then v0.0.1's folder if the guard passes. False when a folder is
    left, for the user to delete: the guard refused it, or it couldn't be deleted."""
    for entry in hass.config_entries.async_entries(LEGACY_DOMAIN):
        await hass.config_entries.async_remove(entry.entry_id)
    return await hass.async_add_executor_job(_remove_folder, legacy_folder(hass))
