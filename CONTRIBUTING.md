# Contributing

Everybody is invited and welcome to contribute.

## How to help

* **Share your know-how:** if you've got a DeviceSide feature working for other integrations (e.g. Z-Wave, TP-Link, Sonoff) or devices on Home Assistant, help us add it to DeviceSide: Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Propose a device or integration. Or [build it yourself](#fast-track-build-it-yourself).
* **Test your devices:** if you discover a device that works on DeviceSide and isn't on the [compatible list](https://github.com/DeviceSide/DeviceSide/blob/main/docs/device-compatibility.md) or doesn't work as expected, please tell us. Go to Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test result or bug.
* **Report bugs:** for a bug that isn't about a device, open a [blank issue](https://github.com/DeviceSide/DeviceSide/issues/new).

## Development principles

- **On-device features.** Our goal is to unlock features that already exist on devices and are hard to access in HA. We never simulate features with Home Assistant timers or loops.
- **Features with broad appeal.** We focus on features that users keep asking for in community forums and feature requests, and which are supportable by at least one of the [top-30 Home Assistant integration](https://analytics.home-assistant.io/integrations/). That keeps us focused on the most features that the most users care about, while keeping the codebase easy to maintain.
- **New integrations and entity domains.** Contributors are encouraged to propose and/or build new integrations (e.g. TP-Link, Z-Wave) and entity domains (e.g. fans, climate) into DeviceSide, subject to the broad appeal criterion above, so that the wider HA community can benefit from the features.
- **Feature gaps.** We focus on features that are missing from or unintuitive in HA. We avoid replicating what Core and the automation editor already do well. We also fill design gaps between an upstream integration and HA, where a device can do something HA's entity doesn't expose (e.g. HS color on Zigbee2MQTT lights).
- **Claims need evidence.** The connectivity chain from Home Assistant to a device's hardware is littered with undocumented behaviors and design gaps that can easily break a feature. Therefore, we verify key assumptions through testing on real devices, even when they're derived from official documents, before it ships to everyone ([evidence rules](docs/evidence.md)).

## Fast track: build it yourself

If you can build a change and test it on your own devices, open a pull request directly. You don't need an issue first. If you're unsure it fits, open a draft pull request early and ask. If you use a coding agent, point it at [CLAUDE.md](CLAUDE.md): it holds the repo's rules.

1. **Check the fit** against the development principles above.
2. **Keep one concern per pull request.** Apart from a new integration's shared touch points in step 3, any change outside your integration's package (`core/`, `actions/`, `scripts/`, shared docs, another integration) goes in its own small pull request first, and yours says `Depends on #N`. Each pull request passes CI on its own; don't stack one on another's unmerged branch. If you need a helper that another integration has, copy it into your package or propose the move in its own pull request. If a core base class doesn't fit, ask for the hook (a draft pull request or an issue) before working around it; don't carry state around it, or depend on Home Assistant's private names or side effects.
3. **Stay in your package:** `custom_components/deviceside/integrations/<x>/`, `tests/integrations/<x>/`, `tests/fixtures/<x>.py` and the docs bundle `docs/integrations/<x>/` (CLAUDE.md's "Where facts go" says which fact goes in which file). A new integration also touches these shared files, which the repo maintainers review:
   - `custom_components/deviceside/services.yaml`: the integration's HA domain in each action's target filter
   - `.github/ISSUE_TEMPLATE/device_report.yml`: its title in the Integration dropdown
   - `docs/integrations.md`: a link to its page
   - `docs/models.yaml`: the models you tested
   - `scripts/gen_features.py`: a `NO_PATH` row for each feature the devices can't support, with the reason, and its explanation in `docs/integrations.md`'s "What can't be done, and why"
   - `pyproject.toml`: any library its tests need, in the `dev` group
   - `custom_components/deviceside/__init__.py`, `const.py`, `strings.json` and `translations/en.json`: only if it adds a setup hook or a user option

   If you also need changes to `README.md` outside its auto-generated sections (the feature table and device cards), propose them in a separate pull request that changes only `README.md`. If your integration needs a change to `manifest.json`, say so in the pull request.
4. **Ship it behind `experimental`.** Every new action, integration, domain, capability and field starts flagged, as `experimental(...)` in its scope ([evidence rules](docs/evidence.md)). Unit tests pin each payload you send, and every module under `core/` and `integrations/`, bar `__init__.py`, needs at least 95% line coverage.
   - **Log for the first bug report**, following [docs/logging.md](docs/logging.md): a user's debug log is often all you'll get.
5. **Test it on your devices.** Test each item at the commit whose calls you'll ship, with the Experimental features option turned on, and put the results in the pull request's Testing evidence section; if review changes a call, test again. Put measurements in your bundle's `internals.md`, dated, with the firmware, HA and library versions. It still lands flagged. Your passing rig records can land in the same pull request, as they cite the package they tested; a `_manual.md` line cites a commit on `main`, so it lands in a later pull request. They let a maintainer lift the flag for the next release instead of letting it soak with opted-in users; whether to is their judgment ([evidence rules](docs/evidence.md#the-experimental-flag)).
6. **Run the checks:** set up with `uv sync`, then run `.venv/bin/pytest` and `pre-commit run --all-files`. Regenerate the cards, the feature table and CODEOWNERS with `scripts/gen_compat.py`, `scripts/gen_features.py` and `scripts/gen_codeowners.py`; CI checks each one.
7. **Audit once, on the final diff:** if you use Claude, run `/audit-code` on it; otherwise ask for an audit in the pull request. After a fix, audit only the fix. Fix every Critical and High finding. Fix a Medium when its fix adds no new state, lock, timer, retry or constant; list the rest with their fix snippet for the maintainer. A finding about how a device *might* behave is a probe to run, not code to write: handle it if the probe shows it, otherwise make sure the log would show it ([docs/logging.md](docs/logging.md)) and list it as open.
8. **Open the pull request** against `main` (or a `release/vX.Y.Z` branch when one exists for the fix) and fill in the template.

A new integration's pull request names you in its `IntegrationInfo.maintainers`, and once it merges you're its maintainer: you merge your package's later pull requests yourself with `/merge <sha>` ([what you merge](#maintaining-an-integration)).

## Maintaining an integration

Each integration in DeviceSide has one or more maintainers, named in its `IntegrationInfo.maintainers` and on its card in the [README](README.md#will-it-work-with-my-device). Whoever builds a new integration usually becomes its first maintainer; to join or take over an existing one, open an issue saying which.

- **What you look after:** the integration's package (`custom_components/deviceside/integrations/<x>/`, `tests/integrations/<x>/`, its test fixture and its docs bundle, `docs/integrations/<x>/`). Bug reports for it are labeled `integration:<x>` and assigned to you.
- **What you merge:** a pull request confined to your package is yours to merge, your own included: once its checks are green and it's up to date with `main`, comment `/merge <sha>`, with the head commit you reviewed (its first 7 characters are enough), and the workflow merges it. That holds when it also regenerates shared generated files (the README's cards and feature table, `docs/device-compatibility.md`, `.github/CODEOWNERS`): CI checks they match their inputs, so only the inputs need review. The workflow refuses, and says why, a pull request that changes anything else, changes your integration's maintainers, or sets or clears a caveat; a repo maintainer merges those. Nothing reaches users before a release candidate, whose audit reviews every change since the last release.
- **What needs a repo maintainer:** anything outside the package, such as shared code in `core/`, shared docs, and the inputs to the generated pages.
- **Access:** when your integration merges, a repo maintainer invites you to the Triage role on the repo, so bug reports can be assigned to you and you can label, close and reopen issues and pull requests. Merging your package's pull requests needs no role: `/merge` checks you're in `IntegrationInfo.maintainers` on `main`. The repo maintainers (who hold admin on the repo, listed in `scripts/gen_codeowners.py`) merge every other pull request.
- **Removing the flag:** you lift an item's flag when you judge it ready for everyone, by how complex it is and how complete its tests are: `experimental("Light")` becomes `verified("Light")`, or `experimental=True` goes. A passing rig record or `_manual.md` sign-off lets you lift it for the next release without the flagged soak, but doesn't oblige you to: a first few rig cases may pass before the full suite exists. It's a change to your package, so you approve it. For an item you can't test, users' working reports, cited in your `_manual.md` line, can verify it ([evidence rules](docs/evidence.md#the-experimental-flag)).
- **Sign-offs:** each integration changed since the last release needs a sign-off before the release: a whole passing rig run where the rig covers it, else a line you add to your bundle's `test-records/_manual.md` in a pull request. Who signs off, the format, and what happens without one: [release gate](docs/evidence.md#release-gate).
- **Stepping back:** if no one is fixing an adapter, a repo maintainer may give it the ⚠️ Unmaintained caveat. It stays live, with a setup warning and a mark on its card, until someone fixes it or adopts the integration. Please open an issue if you want to stop being an integration's maintainer.
