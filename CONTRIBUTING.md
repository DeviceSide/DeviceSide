# Contributing

Everybody is invited and welcome to contribute.

## How to help

* **Test devices for us:** if you discover a device that works on DeviceSide and isn't on the [compatible list](https://github.com/jasonmx/DeviceSide/blob/main/docs/device-compatibility.md) or doesn't work as expected, please tell us. Go to Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Report a device test result or bug.
* **Share your know-how:** if you've got one of the features above working for other integrations (e.g. Z-Wave, TP-Link, Sonoff) or devices, help us add it to DeviceSide: Integrations > [DeviceSide](https://my.home-assistant.io/redirect/integration/?domain=deviceside) > Configure > Propose a device or integration.
* **Report bugs:** for a bug that isn't about a device, open a [blank issue](https://github.com/jasonmx/DeviceSide/issues/new).

## Development principles

- **On-device features.** Our goal is to unlock features that already exist on devices and are hard to access in HA. We never simulate features with Home Assistant timers or loops.
- **Features with broad appeal.** We focus on features that users keep asking for in community forums and feature requests, and which are supportable by at least one of the [top-30 Home Assistant integration](https://analytics.home-assistant.io/integrations/). That keeps us focused on the most features that the most users care about, while keeping the codebase easy to maintain.
- **New integrations and entity domains.** Contributors are encouraged to propose and/or build new integrations (e.g. TP-Link, Z-Wave) and entity domains (e.g. fans, climate) into DeviceSide, subject to the broad appeal criterion above, so that the wider HA community can benefit from the features.
- **Feature gaps.** We focus on features that are missing from or unintuitive in HA. We avoid replicating what Core and the automation editor already do well.
- **Claims need evidence.** The connectivity chain from Home Assistant to a device's hardware is littered with undocumented behaviors and design gaps that can easily break a feature. Therefore, we verify key assumptions through testing on real devices, even when they're derived from official documents, before releasing a feature.

## Developing

- If you use a coding agent, point it at [CLAUDE.md](CLAUDE.md). It holds the repo's rules.
- Open pull requests against `main`, or against a `release/vX.Y.Z` branch when one exists for the fix.
- Set up with `uv sync`.
- Run `.venv/bin/pytest` and `pre-commit run --all-files` before you push. CI runs both.
- If you use Claude, run `/audit-code` on your diff before submitting a pull request for review. Else ask for an audit in the PR.
