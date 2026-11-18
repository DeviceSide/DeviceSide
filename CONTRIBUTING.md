# Contributing

Everybody is invited and welcome to contribute.

## How to help

* **Add what's missing:** propose a call sequence you've got working reliably on your own devices, including for new integrations. Share your working YAML at Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Propose a device or integration, or [build it yourself](#fast-track-build-it-yourself).
* **Adopt an integration or device family:** help us build faster by taking on an existing integration (e.g. Zigbee2MQTT, ZHA) or an integration's family (e.g. IKEA devices on ZHA). We'll gladly bring you on as a co-maintainer or primary maintainer, depending on how involved you want to be. Open an issue to get in touch.
* **Test your devices:** if you discover a device that works on DeviceSide and isn't on the [compatible list](https://github.com/DeviceSide/DeviceSide/blob/main/docs/device-compatibility.md) or doesn't work as expected, please tell us. Go to Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test result or bug.
* **Report bugs:** for a bug that isn't about a device, open a [blank issue](https://github.com/DeviceSide/DeviceSide/issues/new).

## Development principles

- **Actions run on devices.** We unlock features that exist on devices and are hard for users to access in HA. We don't simulate features with timers or loops in HA.
- **Features with broad appeal.** We focus on features that users keep asking for in community forums and feature requests, and which are supportable by at least one of the [top-30 Home Assistant integration](https://analytics.home-assistant.io/integrations/). That keeps us focused on the most features that the most users care about, while keeping the codebase easy to maintain.
- **New integrations and entity domains.** We welcome them when they meet the broad appeal criterion above, so the wider HA community benefits.
- **Feature gaps.** We focus on features that are missing from or unintuitive in HA. We avoid replicating what Core and the automation editor already do well. We also fill design gaps between an upstream integration and HA, where a device can do something HA's entity doesn't expose (e.g. HS color on Zigbee2MQTT lights).
- **Tested on real devices.** Between Home Assistant and a device's hardware sit undocumented behaviors and design gaps that can quietly break a feature. So we test each key assumption on real devices before it ships to everyone, even when the vendor's documentation backs it ([evidence rules](docs/evidence.md)).

## Fast track: build it yourself

If you want to build a change and test it on your own devices, open a pull request directly. You don't need an issue first. If you're unsure it fits, ask in the draft (step 3). If you use a coding agent, point it at [CLAUDE.md](CLAUDE.md): it holds the repo's rules.

Every code pull request follows these steps:

1. **Check the fit** against the development principles above.
2. **Find your path** below and touch only what it lists. Your integration's package is `custom_components/deviceside/integrations/<x>/`, `tests/integrations/<x>/`, `tests/fixtures/<x>.py` and the docs bundle `docs/integrations/<x>/` (CLAUDE.md's ["Where facts go"](CLAUDE.md#where-facts-go) says which fact goes in which file). Each path lists the files it changes, beside the regenerated ones (the cards, the feature table, CODEOWNERS, the call transcripts), and who merges it. `<x>` is the integration's key and `<family>` the family's; `scripts/owners.py` says who maintains a path ([CLAUDE.md's Maintainers](CLAUDE.md#maintainers)).

   <details>
   <summary><b>A device or maker string in an existing class</b></summary>

   - **The rule that places it:** the integration's `classes.py`, or, on an integration with families (Zigbee2MQTT, ZHA), the family's `RULES` (as in `integrations/zigbee2mqtt/families/gledopto/__init__.py`), or the catalog module the rule reads (`custom_components/deviceside/zigbee/<family>.py`).
   - **Its test,** beside the rule's: `tests/integrations/<x>/test_classes.py`, the family's `tests/integrations/<x>/families/<family>/`, or the catalog's `tests/zigbee/test_<family>.py`.
   - **The classification snapshot** (`tests/integrations/<x>/test_classification.py`), only if the change moves a device it lists out of its class.
   - **The model you tested,** in your bundle's `devices.yaml` (`models`), or in `docs/models.yaml` when another integration already lists it (move the entry there from its bundle). A model is credited on the card only by a `_manual.json` row on an item that isn't flagged; your own run goes in Testing evidence.

   Merge: the family's maintainers when every file is the family's or the catalog's; the integration's when the snapshot or the bundle changes; a repo maintainer for `docs/models.yaml`.

   </details>

   <details>
   <summary><b>A new class (e.g. Innr bulbs)</b></summary>

   For devices that answer a class's call differently ([device classes](docs/evidence.md#device-classes)). To split devices off a class, [split off the exception](docs/evidence.md#no-known-method-not-built-yet-on-trial); a class that needs a different payload gets a call of its own ([the split rule](docs/evidence.md#the-split-rule)).

   - **Its rule,** as for a device above, **and its entity domains:** `IntegrationInfo.classes` (in the integration's `classes.py`), or the family's `Family.classes`.
   - **Its place in every adapter's scope:** a level in `capabilities` (a family's in its `FamilyScope`); a `no_known_method` entry where no known call works on it, or the only one known is unsafe (if another call is known or plausible, it is not built yet), or a `not_built` one where the action's failure harms and today's call would harm it, in `integrations/<x>/refusals.py` on an integration with families; or left out, as not built yet.
   - **Its card phrase and section** in your bundle's `devices.yaml` (`capabilities`), and a row in the classification snapshot where the integration has one.
   - **Its tests,** as for a device above.

   Merge: the integration's maintainers.

   </details>

   <details>
   <summary><b>A new family (e.g. Aqara devices on Zigbee2MQTT)</b></summary>

   A vendor's classes on an integration with families (Zigbee2MQTT, ZHA): [Family](docs/design.md#glossary) in design.md's glossary, and its row in the ["Writing an integration" table](docs/design.md#core-contract).

   - **`integrations/<x>/families/<family>/__init__.py`:** `FAMILY = Family(key=…, maintainers=(), classes=…, scopes=…)`, with a `FamilyScope` per action that serves its classes, and its `RULES`.
   - **`integrations/<x>/families/__init__.py`:** the family in `FAMILIES`, and its rule group's place in `RULES`, with a comment where the order matters.
   - **Each class** as for a new class, above: its `devices.yaml` entry, its snapshot row, and any refusal entry in `refusals.py`.
   - **Its tests** in `tests/integrations/<x>/families/<family>/`. The integration's own tests must pass without them: CI's `pytest-without-family-tests` leaves out every family's tests and the catalog's.
   - **Its research** in `docs/integrations/<x>/research/<family>/`.
   - **A catalog module,** `custom_components/deviceside/zigbee/<family>.py`, with its test in `tests/zigbee/test_<family>.py`, only when both Zigbee integrations read the same strings: patterns and facts only (`zigbee/__init__.py`).

   Leave `maintainers=()`. To maintain the family, say so in the pull request, and a repo maintainer appoints you ([Maintaining a family](#maintaining-a-family)). Merge: a repo maintainer, as `/merge` refuses a pull request that adds a `Family(...)`.

   </details>

   <details>
   <summary><b>A new action on an existing integration</b></summary>

   An action DeviceSide has (`custom_components/deviceside/actions/`) that your integration doesn't serve yet:

   - **Its adapter,** `integrations/<x>/<action>.py`, with its `AdapterScope`.
   - **Its unit tests,** `tests/integrations/<x>/test_<action>.py`, and its call transcript, `tests/integrations/<x>/calls/<action>.json`: what it sends on the wire and what it makes of the replies, so the tests pin each payload.
   - **A boundary in `tests/integrations/<x>/wire.py`,** if it sends through one the file doesn't name yet.
   - **The action's target filter** in `custom_components/deviceside/services.yaml`: your integration's HA domain, with the entity domains the adapter serves.

   A brand-new action (not yet in `actions/`, `services.yaml`, `strings.json` and `icons.json`) is a shared change: its own pull request first (step 3). Merge: a repo maintainer, as `services.yaml` is shared.

   </details>

   <details>
   <summary><b>A new integration</b></summary>

   - **Your package,** with a bundle (`index.md`, `internals.md` and `devices.yaml`) and a test fixture (`tests/fixtures/<x>.py`). `IntegrationInfo.maintainers` names you, and once the pull request merges you're its maintainer ([what that means](#maintaining-an-integration)).
   - **`tests/integrations/<x>/wire.py`,** naming your wire boundary (`tests/transcripts.py` says how). Unit tests pin each payload you send: they record what each action sends on the wire, and what it makes of the replies, as its call transcript (`tests/integrations/<x>/calls/`). The transcript records a call through a Home Assistant service by itself, and any other call only at a boundary `wire.py` names; no check catches a missing one.
   - **These shared files,** which the repo maintainers review:
     - `custom_components/deviceside/services.yaml`: the integration's HA domain in each action's target filter
     - `.github/ISSUE_TEMPLATE/device_report.yml`: its title in the Integration dropdown
     - `docs/integrations.md`: a link to its page
     - `scripts/gen_features.py`: a `NO_PATH` entry for each feature impossible on every device of the integration, with the reason, and its explanation in `docs/integrations.md`'s "What can't be done, and why"
     - `docs/models.yaml`: a model you tested that another integration already lists (move the entry there from its bundle)
     - `pyproject.toml` and `uv.lock`: any library its tests need, added with `uv add --dev <lib>` (CI installs with `uv sync --locked`)
     - only if it adds a user option: `const.py`, `config_flow.py` (the options form), `strings.json` and `translations/en.json` under `custom_components/deviceside/`, and `__init__.py` and `core/runtime.py` too if core reads it; an option only your integration reads, your `setup` reads from the entry (as Zigbee2MQTT's `lifecycle.py` does)

     If you also need changes to `README.md` outside its auto-generated sections (the feature table and device cards), propose them in a separate pull request that changes only `README.md`. If your integration needs a change to `manifest.json`, say so in the pull request.

   - **What your integration can declare:** each hook and field, what it buys and where its rules live, in [design.md's "Writing an integration" table](docs/design.md#core-contract).
   - **Name your classes** if devices behind your integration answer the same call differently by maker or firmware (the table's [`capability` row](docs/design.md#core-contract)), each with its own level in every scope's `capabilities`, the default class never Verified; otherwise argue in the pull request that it has one class ([device classes](docs/evidence.md#device-classes)).
   - **Use the integration's own groups** if it has groups that take one command for all their lights (a Hue zone, a Zigbee2MQTT group, a Control4 light group): declare `is_group`, `expand_group` and `native_groups` (the table's [Groups row](docs/design.md#core-contract)); `expand_group` has no I/O, so cache the membership in `setup` if it needs a fetch. Unit-test each `native_groups` action on one of your groups. Without them, a group runs as a plain light: no group icon in the feature table, no credit on the card, and no fallback to its members.
   - **Keep your lifecycle in your package** (the table's [`setup`, `remove` row](docs/design.md#core-contract)): register your integration's teardown with `entry.async_on_unload`, and put none of it in the component root.
   - **Log for the first bug report**, following [docs/logging.md](docs/logging.md): a user's debug log is often all you'll get.

   Merge: a repo maintainer.

   </details>

3. **Open a draft pull request, one concern each.** Open it early, against `main` (or a `release/vX.Y.Z` branch when one exists for the fix), and fill in the template as you go: CI runs on drafts, and the maintainers of the code it changes hear of it. Apart from the shared files your path lists, any change outside your integration's package (`core/`, `actions/`, `scripts/`, shared docs, another integration) goes in its own small pull request first, and yours says `Depends on #N`. Each pull request passes CI on its own; don't stack one on another's unmerged branch. If you need a helper that another integration has, copy it into your package or propose the move in its own pull request. If a core base class doesn't fit, ask for the hook (a draft pull request or an issue) before working around it; don't carry state around it, or depend on Home Assistant's private names or side effects.

4. **Ship behind `experimental`.** Every new action, domain, capability (class level) and field starts flagged, as `experimental(...)` in its scope; a new integration flags every adapter's domains ([evidence rules](docs/evidence.md)). A class goes behind the flag only on the evidence [on trial](docs/evidence.md#no-known-method-not-built-yet-on-trial) names (your own probe or passing run counts); without it, it stays not built.
5. **Probe what you don't know.** If you bring a call sequence you have seen work on the device (your own automation, an upstream integration that ships it), cite it in your bundle's `internals.md` and build. If you're finding out whether or how the device takes the call, or you have only the vendor's documentation, probe first, before you build, and record what you find in your bundle's `internals.md`, dated ([evidence rules](docs/evidence.md#tenets), tenets 2 and 8).
6. **Test on your own devices.** This is the test that matters: yours may be the only hardware run your devices get before users do. With the Experimental features option on, test each item at the commit whose calls you'll ship, and put the results in the pull request's Testing evidence section; put measurements in your bundle's `internals.md`, dated, with the firmware, HA and library versions. If review changes a call, or how you read the device's reply, test that item again. A `_manual.json` row from `scripts/signoff.py` can land in the same pull request.
7. **Pass CI.** Set up with `uv sync`. CI runs the unit tests with their call transcripts (`.venv/bin/pytest -n auto --transcripts=check`), at least 95% line coverage on every module under `core/` and `integrations/` bar `__init__.py`, `pre-commit run --all-files`, and the generated-file checks; each failure names the command that fixes it. Running them locally saves a round trip.
8. **Audit once, on the final diff:** if you use Claude, run `/audit-code` on it; otherwise ask for an audit in the pull request. After a fix, audit only the fix. Fix every Critical and High finding. List each Medium and Low with its fix snippet for the maintainer, unless its fix is a line your change already touches. A finding about how a device *might* behave is a probe to run, not code to write: handle it if the probe shows it, otherwise make sure the log would show it ([docs/logging.md](docs/logging.md)) and list it as open.
9. **Mark it ready** once its Testing evidence and the audit are in. A maintainer's `/merge` refuses a draft.

## Maintaining an integration

Each integration has one or more maintainers, named in its `IntegrationInfo.maintainers`. Whoever builds a new integration usually becomes its first; to join or take over one, open an issue saying which.

- **What you look after:** its package (`custom_components/deviceside/integrations/<x>/`, `tests/integrations/<x>/`, its test fixture and its docs bundle, `docs/integrations/<x>/`). Its bug reports are labeled `integration:<x>` and assigned to you to triage, a failed report on a class still behind the flag included ([on trial](docs/evidence.md#no-known-method-not-built-yet-on-trial)).
- **What you merge:** a pull request whose every file is in a package you maintain, your own included. Once you've reviewed it, comment `/merge <sha>` with the head commit you reviewed (its first 7 characters are enough): it merges once its checks pass, so a branch behind `main` needs no update. A push after your comment cancels it (a bot comment says so); review the new head and comment again. Regenerated shared files (the README's cards and feature table, `docs/device-compatibility.md`, `.github/CODEOWNERS`) don't stop it, as CI checks they match their inputs. `/merge` refuses, saying why, a pull request that conflicts with `main` (its author merges `main` in), changes a file you don't maintain (such as `core/`, shared docs, `docs/models.yaml`, or the README outside its generated blocks), adds an integration or family or changes its `maintainers`, or sets or clears a caveat; a repo maintainer merges those. Nothing reaches users before a release candidate, whose audit reviews every change since the last release.
- **Access:** once your integration merges, a repo maintainer invites you to the repo's Triage role, so reports can be assigned to you and you can label, close and reopen issues and pull requests. `/merge` needs no role: it checks you're in `IntegrationInfo.maintainers` on `main`.
- **Removing the flag:** you lift an item's flag when you judge it ready for everyone, by how complex it is and how complete its tests are: `experimental("Light")` becomes `verified("Light")` (for an adapter flagged whole, its domains: `experimental("light")` becomes `verified("light")`). It's a change to your package, so you approve it. A passing rig record or `_manual.json` sign-off lets you lift it for the next release without the flagged soak, but doesn't oblige you to: a first few rig cases may pass before the full suite exists. Users' working reports, cited in your `_manual.json` row, can verify an item you can't test ([evidence rules](docs/evidence.md#the-experimental-flag)).
- **Sign-offs:** before a release, each action whose call transcripts changed since the last one, whatever code changed them, needs a sign-off: passing rig records where the rig covers it, else a row in your bundle's `test-records/_manual.json`, printed by `scripts/signoff.py`, added in a pull request. Who signs off, the format, and what happens without one: [release gate](docs/evidence.md#release-gate).
- **Stepping back:** if no one is fixing an adapter, a repo maintainer may give it the ⚠️ Unmaintained caveat: it stays live, with a setup warning and a mark on its card, until someone fixes it or adopts the integration. To stop being a maintainer, open an issue.

## Maintaining a family

On an integration that fronts many vendors (Zigbee2MQTT, ZHA), each vendor's classes are a family, in `integrations/<x>/families/<family>/`, which can have maintainers of its own, named in its `Family.maintainers`; the integration's maintainers still own every family in it. To maintain one, open an issue saying which; a repo maintainer appoints you.

- **What you look after:** the family's code, its tests (`tests/integrations/<x>/families/<family>/`), its new research (`docs/integrations/<x>/research/<family>/`), and the Zigbee strings it shares with the same family on the other Zigbee integration (`custom_components/deviceside/zigbee/<family>.py`). Those belong to the maintainers of either family and of either integration, so you merge a change to them without the other integration's maintainer, unless it fails that integration's tests or classification snapshot, which are theirs to change.
- **What you merge:** a pull request whose every file you own, with `/merge <sha>`, as an integration's maintainer does: a device or maker string in one of your existing classes with no change to the bundle, your classes' levels (you lift a flag when you judge it ready), or an own call (the Fast track's [step 2](#fast-track-build-it-yourself) lists each path's files).
- **What needs the integration's maintainer:** anything else in the integration: a new class (its card phrase and snapshot row are theirs), its transport, another family, the rule order in `families/__init__.py`, the classification snapshot in `tests/integrations/<x>/test_classification.py` (so a rule change that moves a device it lists is theirs to merge), its test records and pages, and its `refusals.py`, which holds every no known method and not built yet entry, your classes' included ([why](CLAUDE.md#maintainers)).
