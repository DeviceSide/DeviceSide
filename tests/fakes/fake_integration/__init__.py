"""Integration "fake": a generic integration with native groups whose members it can list."""

from dataclasses import replace

from custom_components.deviceside.core.resolver import resolve
from custom_components.deviceside.core.scope import AdapterScope, DurationLimits, IntegrationInfo, verified

from ..scripted import ScriptedAdapter

LIMITS = DurationLimits(min_s=1, max_s=100)


def is_group(hass, target) -> bool:
    return target.entry.unique_id.startswith("group:")


def expand_group(hass, target):
    registry = hass.data["deviceside"].registry
    members = target.state.attributes.get("fake_members", []) if target.state else []
    # Members it can list but not address on their own (Target.addressable).
    unaddressable = target.state.attributes.get("fake_unaddressable", []) if target.state else []
    return [
        replace(t, addressable=m not in unaddressable)
        for m in members
        if not isinstance(t := resolve(hass, registry, m, target.entity_id), str)
    ]


INTEGRATION = IntegrationInfo(
    key="fake",
    title="Fake",
    ha_domain="fake",
    maintainers=("jasonmx",),
    is_group=is_group,
    expand_group=expand_group,
    max_concurrency=2,
)


class FakeTurnOnFor(ScriptedAdapter):
    action = "turn_on_for"
    integration = "fake"
    scope = AdapterScope(
        domains=verified("light", "switch"),
        duration=LIMITS,
        fields=verified("brightness", "transition"),
    )


class FakeTurnOffFor(ScriptedAdapter):
    action = "turn_off_for"
    integration = "fake"
    scope = AdapterScope(domains=verified("switch"), duration=LIMITS, native_groups=True)


class FakeSetAttributes(ScriptedAdapter):
    action = "set_attributes"
    integration = "fake"
    scope = AdapterScope(fields=verified("brightness"))


ADAPTERS = [FakeTurnOnFor, FakeTurnOffFor, FakeSetAttributes]
