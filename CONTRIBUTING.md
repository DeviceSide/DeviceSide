# Contributing

Everybody is invited and welcome to contribute.

## How to help

* **Test devices for us:** if you discover a device that works on DeviceSide and isn't on the [compatible list](https://github.com/DeviceSide/DeviceSide/blob/main/docs/device-compatibility.md) or doesn't work as expected, please tell us. Go to Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test result or bug.
* **Share your know-how:** if you've got one of the features above working for other integrations (e.g. Z-Wave, TP-Link, Sonoff) or devices, help us add it to DeviceSide: Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Propose a device or integration.
* **Report bugs:** for a bug that isn't about a device, open a [blank issue](https://github.com/DeviceSide/DeviceSide/issues/new).

## Development principles

- **On-device features.** Our goal is to unlock features that already exist on devices and are hard to access in HA. We never simulate features with Home Assistant timers or loops.
- **Features with broad appeal.** We focus on features that users keep asking for in community forums and feature requests, and which are supportable by at least one of the [top-30 Home Assistant integration](https://analytics.home-assistant.io/integrations/). That keeps us focused on the most features that the most users care about, while keeping the codebase easy to maintain.
- **New integrations and entity domains.** Contributors are encouraged to propose and/or build new integrations (e.g. TP-Link, Z-Wave) and entity domains (e.g. fans, climate) into DeviceSide, subject to the broad appeal criterion above, so that the wider HA community can benefit from the features.
- **Feature gaps.** We focus on features that are missing from or unintuitive in HA. We avoid replicating what Core and the automation editor already do well. We also fill design gaps between an upstream integration and HA, where a device can do something HA's entity doesn't expose (e.g. HS color on Zigbee2MQTT lights).
- **Claims need evidence.** The connectivity chain from Home Assistant to a device's hardware is littered with undocumented behaviors and design gaps that can easily break a feature. Therefore, we verify key assumptions through testing on real devices, even when they're derived from official documents, before releasing a feature.

## Fast track: build it yourself

If you can build a change and test it on your own devices, open a pull request directly. You don't need an issue first. If you're unsure it fits, open a draft pull request early and ask. If you use a coding agent, point it at [CLAUDE.md](CLAUDE.md): it holds the repo's rules.

1. **Check the fit** against the development principles above.
2. **Keep one concern per pull request.** Any change outside your integration's package (`core/`, `actions/`, `scripts/`, shared docs, another integration) goes in its own small pull request first, and yours says `Depends on #N`. Each pull request passes CI on its own; don't stack one on another's unmerged branch. Don't refactor another integration's adapters: their test records go stale, and a rig rerun is needed before the next release. If you need a helper that another integration has, copy it into your package or propose the move in its own pull request.
3. **Stay in your package:** `custom_components/deviceside/integrations/<x>/`, `tests/integrations/<x>/`, `tests/fixtures/<x>.py` and the docs bundle `docs/integrations/<x>/` (CLAUDE.md's "Where facts go" says which fact goes in which file). A new integration also touches these shared files, which Jason reviews:
   - `custom_components/deviceside/services.yaml`: the integration's HA domain in each action's target filter
   - `.github/ISSUE_TEMPLATE/device_report.yml`: its title in the Integration dropdown
   - `docs/integrations.md`: a link to its page
   - `docs/models.yaml`: the models you tested
   - `scripts/gen_features.py`: a `NO_PATH` row for each feature the devices can't support, with the reason
   - `README.md`: the integration in the Requirements list
4. **Ship it Experimental.** New actions, domains, capabilities and fields start as `Level.EXPERIMENTAL`. Unit tests pin each payload you send, and every module of your adapter code needs at least 95% line coverage.
5. **Earn Reported with your own test.** Test each item on your devices at the commit whose calls you'll ship. File a [device report](https://github.com/DeviceSide/DeviceSide/issues/new?template=device_report.yml) giving that commit as the DeviceSide version, add it to `reports` in your bundle's `devices.yaml`, and set those items to `Level.REPORTED`. Fields stay Experimental for now. If review changes a call, test again and file a new report. Put measurements in your bundle's `internals.md`, dated, with the firmware, HA and library versions.
6. **Run the checks:** set up with `uv sync`, then run `.venv/bin/pytest` and `pre-commit run --all-files`. Regenerate the cards, the feature table and CODEOWNERS with `scripts/gen_compat.py`, `scripts/gen_features.py` and `scripts/gen_codeowners.py`; CI checks each one. `scripts/check_release.py --records` should list no adapter outside your package.
7. **Audit:** if you use Claude, run `/audit-code` on your diff; otherwise ask for an audit in the pull request. Fix every Critical and High finding and list the rest.
8. **Open the pull request** against `main` (or a `release/vX.Y.Z` branch when one exists for the fix) and fill in the template.

A new integration's pull request names you in its `IntegrationInfo.maintainers`, and once it merges you're its maintainer. Its next rung, Verified, comes with the rig kit, which lets maintainers commit test records from their own hardware.

## Maintaining an integration

Each integration in DeviceSide has one or more maintainers, named in its `IntegrationInfo.maintainers` and on its card in the [README](README.md#will-it-work-with-my-device). Whoever builds a new integration usually becomes its first maintainer; to join or take over an existing one, open an issue saying which.

- **What you look after:** the integration's package (`custom_components/deviceside/integrations/<x>/`, `tests/integrations/<x>/`, its test fixture and its docs bundle, `docs/integrations/<x>/`). Bug reports for it are labeled `integration:<x>` and assigned to you.
- **What you approve:** a pull request confined to your package needs one maintainer's approval and green CI. You're asked to review it, and Jason merges once you approve.
- **What needs Jason:** anything outside the package, such as shared code in `core/`, shared docs, and the inputs to the generated pages.
- **Access:** maintainers get the Triage role on the repo, so they can label, assign, close and reopen issues and pull requests. Jason merges every pull request.
- **Stepping back:** if no one is fixing an adapter, Jason may mark it ⚠️ Unmaintained. It stays live, setup warns, and its card shows the mark until someone fixes it or adopts the integration. Please say so in an issue if you can no longer maintain an integration.
