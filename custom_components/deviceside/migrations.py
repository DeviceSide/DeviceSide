"""Repairs that move users to DeviceSide from what came before it.

- `legacy_device_side`: v0.0.1 shipped under the domain `device_side`. Marketplace installs `deviceside` beside it
  and leaves the old folder and its config entry in place, so HA keeps loading v0.0.1. HA has no domain-rename
  migration, and the v0.0.1 entry holds no data or options, so the fix removes the old copy and the user renames their
  `device_side.` calls. The fix also removes v0.0.1's two actions, so nothing calls the old code and no restart is
  needed. Delete this check in v0.2.0, with the next.
- `legacy_device_side_calls`: once v0.0.1's entry is gone, lists the automations and scripts that still call
  `device_side.`, each with its edit link. HA's own `service_not_found` repair appears only after an automation
  fails, skips scripts, and says to remove the action rather than rename it. HA gives no automations-calling-an-action
  helper, so the check walks each automation's and script's `raw_config`. It runs once HA has started, after the Fix,
  and whenever an automation or script is added, removed or replaced: a reload replaces each one whose config changed,
  and a registered one's state passes through a `restored` placeholder rather than none, so both count.
- `migrate_hue_dimmer`: DeviceSide's actions are drop-ins for Hue Smooth Dimming's (docs/action-behavior.md,
  Replacing hue_dimmer). Users may run both while they move their automations, so the repair only gives the renames
  and deletes nothing. It stays as long as Hue Smooth Dimming can be installed.

A check deletes its issue when its condition is false, so a fixed state clears a stale issue on the next start. HA
keeps an ignored issue ignored when it is created again, so an ignored repair doesn't come back.
"""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from homeassistant.components.automation import DATA_COMPONENT as AUTOMATIONS
from homeassistant.components.automation.const import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.components.script.const import DOMAIN as SCRIPT_DOMAIN
from homeassistant.const import ATTR_RESTORED, CONF_ACTION, CONF_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback, split_entity_id
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.start import async_at_started

from .const import DOMAIN, REPO_URL

LEGACY_DOMAIN = "device_side"
LEGACY_ISSUE = "legacy_device_side"
LEGACY_CALLS_ISSUE = "legacy_device_side_calls"
# v0.0.1's only actions (its services.yaml).
LEGACY_SERVICES = ("turn_on_for", "turn_off_for")
HUE_DIMMER_DOMAIN = "hue_dimmer"
HUE_DIMMER_ISSUE = "migrate_hue_dimmer"
# The README's "Coming from Hue Smooth Dimming?" box, which the repair's text follows.
HUE_DIMMER_URL = REPO_URL + "#coming-from-hue-smooth-dimming"


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


def _calls_legacy(config: Any) -> bool:
    """Whether a raw automation or script config holds an action (or its old name, service) of `device_side`."""
    if isinstance(config, dict):
        return any(
            (key in (CONF_ACTION, CONF_SERVICE) and isinstance(value, str) and value.startswith(f"{LEGACY_DOMAIN}."))
            or _calls_legacy(value)
            for key, value in config.items()
        )
    if isinstance(config, list):
        return any(_calls_legacy(item) for item in config)
    return False


def _link(name: str, path: str | None) -> str:
    name = name.replace("[", "\\[").replace("]", "\\]")
    return f"- [{name}]({path})" if path else f"- {name}"


def _legacy_callers(hass: HomeAssistant) -> Iterator[tuple[str, str | None]]:
    """Each automation and script calling `device_side.`: its name, and its editor path when it has an id."""
    for domain, component in (
        (AUTOMATION_DOMAIN, hass.data.get(AUTOMATIONS)),
        (SCRIPT_DOMAIN, hass.data.get(SCRIPT_DOMAIN)),
    ):
        for entity in component.entities if component else ():
            if _calls_legacy(getattr(entity, "raw_config", None)):
                path = f"/config/{domain}/edit/{entity.unique_id}" if entity.unique_id else None
                yield str(entity.name or entity.entity_id), path


@callback
def async_check_legacy_calls(hass: HomeAssistant) -> None:
    # While v0.0.1's entry is there, its actions still work and the legacy_device_side repair covers them.
    callers = (
        [] if hass.config_entries.async_entries(LEGACY_DOMAIN) else sorted(_legacy_callers(hass), key=lambda c: c[0])
    )
    if callers:
        ir.async_create_issue(
            hass,
            DOMAIN,
            LEGACY_CALLS_ISSUE,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=LEGACY_CALLS_ISSUE,
            translation_placeholders={"items": "\n".join(_link(name, path) for name, path in callers)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, LEGACY_CALLS_ISSUE)


def _is_placeholder(state: State | None) -> bool:
    return state is None or bool(state.attributes.get(ATTR_RESTORED))


@callback
def _is_replaced(data: EventStateChangedData) -> bool:
    """An automation or script added, removed or replaced, rather than one running or toggled."""
    return split_entity_id(data["entity_id"])[0] in (AUTOMATION_DOMAIN, SCRIPT_DOMAIN) and (
        _is_placeholder(data["old_state"]) or _is_placeholder(data["new_state"])
    )


@callback
def async_watch_legacy_calls(hass: HomeAssistant) -> None:
    """Check for `device_side.` calls once HA has started (automations and scripts are loaded), then whenever one is
    added, removed or replaced. Listens for the rest of the HA run, like the services."""

    @callback
    def changed(_event: Event[EventStateChangedData]) -> None:
        async_check_legacy_calls(hass)

    @callback
    def started(_hass: HomeAssistant) -> None:
        async_check_legacy_calls(hass)
        hass.bus.async_listen(EVENT_STATE_CHANGED, changed, event_filter=_is_replaced)

    async_at_started(hass, started)


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
    """Remove every `device_side` config entry and its two actions, then v0.0.1's folder if the guard passes. False
    when a folder is left, for the user to delete: the guard refused it, or it couldn't be deleted."""
    for entry in hass.config_entries.async_entries(LEGACY_DOMAIN):
        await hass.config_entries.async_remove(entry.entry_id)
    for service in LEGACY_SERVICES:
        if hass.services.has_service(LEGACY_DOMAIN, service):
            hass.services.async_remove(LEGACY_DOMAIN, service)
    async_check_legacy_calls(hass)
    return await hass.async_add_executor_job(_remove_folder, legacy_folder(hass))
