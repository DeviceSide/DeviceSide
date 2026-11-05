# Contributing

Everybody is invited and welcome to contribute. Devices implement the same standards differently, so the most useful
help is evidence from devices the maintainer doesn't own: what works, what doesn't, and the calls that make it work.

## Principles

- **Claims follow evidence.** A feature is listed as working on a device only when a test record shows it passing
  there.
- **Requests bring proof.** A device request comes with a YAML call that already works on the device, its model and
  firmware, and a promise to test the release candidate.
- **A bug means a claim is broken.** A bug report is for a device and feature the [test records](docs/test-records/)
  list. Anything else is a device report or a request.
- **Adapters have an owner who answers.** Each adapter has a maintainer who fixes it and reruns its tests. The
  maintainer of DeviceSide may drop an adapter that nobody maintains, or that keeps breaking.

## Support levels

Each adapter (one action on one integration) has one of these, from its test records:

- **Verified:** a passing test record from the maintainer's rig, which runs each action against real devices.
- **Community:** a passing test record from a contributor who installed a release candidate through HACS. It can
  ship in a stable release, after the same soak as any other release candidate.
- **Experimental:** not yet covered by a passing test record. It ships in release candidates only, never in a
  stable release.

A record older than its adapter's code blocks the next release until the test is rerun. The Community level is new:
the first contributor to reach it sets up the test checklist with the maintainer.

## How to help

1. **Report a device.** Tried DeviceSide on a device that isn't listed? Open a
   [device report](https://github.com/jasonmx/DeviceSide/issues/new?template=device_report.yml) and say whether it
   worked. A "works" report counts as much as a "doesn't work" one.
2. **Request a device.** For a device, integration or feature DeviceSide doesn't cover, open a
   [device request](https://github.com/jasonmx/DeviceSide/issues/new?template=device_request.yml). It needs a YAML
   call that already does the job on your device (an MQTT publish, a ZHA cluster command and so on), the device's
   model and firmware, and your promise to test the release candidate that adds it.
3. **Contribute an adapter.** Code, plus a test record from a release candidate installed through HACS, plus your
   agreement to maintain the adapter. Contact the maintainer before you start, for the test checklist. Read
   [What gets built](#what-gets-built) and [Developing](#developing) first. The
   [hardware the rig lacks](docs/hardware-the-rig-lacks.md) lists built features waiting for a tester.
4. **Report a bug.** Only for a device and feature the [test records](docs/test-records/) list: open a
   [bug report](https://github.com/jasonmx/DeviceSide/issues/new?template=bug.yml). A failure on any other device
   is a device report.

## What gets built

- **On-device features only.** Our goal is to unlock features that already exist on devices and are hard to access in HA. We never simulate features with Home Assistant timers or loops.
- **Features with broad appeal.** We focus on features that users keep asking for in community forums and feature requests, and which are supportable by at least one of the [top-30 Home Assistant integration](https://analytics.home-assistant.io/integrations/). That keeps us focused on the most important features, while keeping the codebase simple and easy to maintain.
- **Gap fillers.** We build features that are missing from or really hard to use in HA. We avoid replicating what Core and the automation editor already do well.
- **New integrations and entity domains.** Contributors are welcome to add new integrations (e.g. TP-Link, Z-Wave) and new entity domains (e.g. fans, climate), subject to the broad appeal principle above.
- **Accessible to non-tech users.** We create simple actions that are easily understood by humans. For example, we end dimming transitions with a `stop` action, because `set brightness_step: 0` is not intuitive.

## Developing

- An adapter leaves `experimental` on a passing test record that covers its whole scope (see
  [Support levels](#support-levels)). The maintainer's rig is kept outside this repo.
- If you use a coding agent, point it at [CLAUDE.md](CLAUDE.md). It holds the repo's rules.
- Open pull requests against `main`, or against a `release/vX.Y.Z` branch when one exists for the fix.
- Set up with `uv sync`. To add a dependency, use `uv add --dev`, not `uv pip install`.
- Run `.venv/bin/pytest` and `pre-commit run --all-files` before you push. CI runs both.
- If you use Claude, run `/audit-code` on your diff before opening a pull request. Else ask for an audit in the PR.
- A new action, field or integration starts with `experimental=True` on its adapter, which keeps it out of stable releases until it is tested on hardware. Every adapter needs 95% line coverage either way. Fixes and refactors don't set it.
