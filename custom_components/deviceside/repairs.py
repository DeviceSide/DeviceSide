"""Fix flows for DeviceSide's repairs (migrations.py says why each exists)."""

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant

from .migrations import LEGACY_ISSUE, async_remove_legacy, legacy_folder


class LegacyDeviceSideFlow(ConfirmRepairFlow):
    """Confirm, then remove v0.0.1's entries and folder."""

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> RepairsFlowResult:
        if user_input is None:
            return await super().async_step_confirm()
        try:
            await async_remove_legacy(self.hass)
        except OSError:
            # The entries are gone by now; the folder is left for the user to delete.
            return self.async_abort(
                reason="remove_failed", description_placeholders={"folder": str(legacy_folder(self.hass))}
            )
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    if issue_id == LEGACY_ISSUE:
        return LegacyDeviceSideFlow()
    return ConfirmRepairFlow()
