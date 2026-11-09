# Contributing

Everybody is invited and welcome to contribute. Devices implement the same standards differently, so the most useful
help is evidence from devices the maintainer doesn't own: what works, what doesn't, and the calls that make it work.

## Principles

- **Claims follow evidence.** A feature is listed as working on a device only when a test record shows it passing
  there.
- **Requests bring proof.** A device request comes with a YAML call that already works on the device, its model and
  firmware, and a promise to test the release candidate.
- **A bug means a claim is broken.** A bug report is for a device and feature the [compatibility page](docs/compatibility.md)
  list. Anything else is a device report or a request.
- **Adapters have an owner who answers.** Each adapter has a maintainer who fixes it and reruns its tests. The
  maintainer of DeviceSide may drop an adapter that nobody maintains, or that keeps breaking.

## Support levels

Each part of an adapter (one action on one integration) has one of these, for the entity domains, device components
and fields it takes:

- **Verified:** a passing test record from the maintainer's rig, which runs each action against real devices.
- **Reported:** no record, but a user reported it working, and unit tests pin the call DeviceSide sends. It ships in
  stable releases.
- **Documented:** no record yet for one domain or capability of an otherwise tested adapter (a Shelly RGBW strip, a
  Matter light), but DeviceSide sends it the same call as a Verified one, differing only in what it addresses, and
  the vendor or standard documents that call identically for both. It ships in stable releases. A bug on it is a
  real bug, so please report it; a passing record makes it Verified.
- **Experimental:** built and unit-tested, but not yet proven on a device. It ships in stable releases switched off:
  DeviceSide refuses it until you turn on **Experimental features** in its options. Please report how it went, either
  way: a working report makes it Reported.

A change to proven code that the rig hasn't rerun yet keeps the whole adapter in release candidates only. A record
older than its adapter's code blocks the next release until the test is rerun.

## How to help

1. **Report a device.** Tried DeviceSide on a device that isn't listed? Open a
   [device report](https://github.com/jasonmx/DeviceSide/issues/new?template=device_report.yml) and say whether it
   worked. A "works" report counts as much as a "doesn't work" one. In Home Assistant, **Settings > Devices & services > DeviceSide > Configure > Report a device test result**
   opens the same form with your device's details filled in.
2. **Propose a device.** For a device, integration or feature DeviceSide doesn't cover, open a
   [proposal](https://github.com/jasonmx/DeviceSide/issues/new?template=propose_device_or_integration.yml). It needs a YAML
   call that already does the job on your device (an MQTT publish, a ZHA cluster command and so on), the device's
   model and firmware, and your promise to test the release candidate that adds it. **Configure > Propose a device
   or integration** fills in the device's details.
3. **Contribute an adapter.** Code with unit tests, plus your agreement to maintain the adapter. It ships as
   Experimental until a test record or a working report proves it. Contact the maintainer before you start. Read
   [What gets built](#what-gets-built) and [Developing](#developing) first. The
   [hardware the rig lacks](docs/hardware-the-rig-lacks.md) lists built features waiting for a tester.
4. **Report a bug.** Only for a device and feature the [compatibility page](docs/compatibility.md) lists: open a
   [bug report](https://github.com/jasonmx/DeviceSide/issues/new?template=report_bug.yml). A failure on any other device
   is a device report. **Configure > Report a bug** fills in the versions, and the device's details if you pick one.

## What gets built

- **On-device features only.** Our goal is to unlock features that already exist on devices and are hard to access in HA. We never simulate features with Home Assistant timers or loops.
- **Features with broad appeal.** We focus on features that users keep asking for in community forums and feature requests, and which are supportable by at least one of the [top-30 Home Assistant integration](https://analytics.home-assistant.io/integrations/). That keeps us focused on the most important features, while keeping the codebase simple and easy to maintain.
- **Gap fillers.** We build features that are missing from or really hard to use in HA. We avoid replicating what Core and the automation editor already do well.
- **New integrations and entity domains.** Contributors are welcome to add new integrations (e.g. TP-Link, Z-Wave) and new entity domains (e.g. fans, climate), subject to the broad appeal principle above.
- **Accessible to non-tech users.** We create simple actions that are easily understood by humans. For example, we end dimming transitions with a `stop` action, because `set brightness_step: 0` is not intuitive.

## Developing

- An adapter leaves `experimental` on a passing test record that covers its whole scope bar its Documented, Reported and
  Experimental items (see [Support levels](#support-levels)). The maintainer's rig is kept outside this repo.
- If you use a coding agent, point it at [CLAUDE.md](CLAUDE.md). It holds the repo's rules.
- Open pull requests against `main`, or against a `release/vX.Y.Z` branch when one exists for the fix.
- Set up with `uv sync`. To add a dependency, use `uv add --dev`, not `uv pip install`.
- Run `.venv/bin/pytest` and `pre-commit run --all-files` before you push. CI runs both.
- If you use Claude, run `/audit-code` on your diff before opening a pull request. Else ask for an audit in the PR.
- New work (an action, integration, entity domain, device component or field) starts as an Experimental item, `Level.EXPERIMENTAL` in the adapter's scope: it ships behind the Experimental features option until it is proven. `experimental=True` on the adapter is only for a behavior change to proven code that the maintainer's rig can't rerun. Every adapter needs 95% line coverage either way.
