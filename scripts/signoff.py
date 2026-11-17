"""Print a `_manual.json` row signing off actions by their call transcripts at HEAD.

    scripts/signoff.py <integration> <action>... --tester <handle> --device <model,manufacturer,class>... [--group]

Paste the printed row into `signoffs` in docs/integrations/<integration>/test-records/_manual.json (format 3). Its
`calls` binds each action to the blob of HEAD's transcript, tests/integrations/<integration>/calls/<action>.json:
sign off the commit you tested, with the transcripts it holds. Every field only a person knows is a required flag, so
the row printed is complete. A device is `model,manufacturer,class`; `-` for a manufacturer or class leaves it null.
docs/evidence.md (Sign-off format) says what each field holds."""

import argparse
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from scripts.check_release import blob_at, git, transcript_path  # noqa: E402


def parse_device(text: str) -> dict:
    model, _, rest = text.partition(",")
    manufacturer, _, cls = rest.rpartition(",")
    if not (model and manufacturer and cls):
        raise argparse.ArgumentTypeError(f"{text!r}: expected model,manufacturer,class (`-` for none)")
    return {
        "model": model,
        "manufacturer": None if manufacturer == "-" else manufacturer,
        "class": None if cls == "-" else cls,
    }


def row(
    integration: str,
    actions: list[str],
    tester: str,
    devices: list[dict],
    registry: AdapterRegistry,
    group: bool = False,
) -> dict:
    """The sign-off row, or SystemExit naming what is wrong: an unknown integration or action, or an action with no
    transcript at HEAD."""
    if integration not in registry.integrations:
        raise SystemExit(f"unknown integration {integration!r}: one of {', '.join(sorted(registry.integrations))}")
    calls = {}
    for action in sorted(set(actions)):
        if registry.adapter(action, integration) is None:
            raise SystemExit(f"{integration} has no {action!r} action")
        if (blob := blob_at("HEAD", integration, action)) is None:
            raise SystemExit(
                f"{integration} / {action} has no transcript at HEAD ({transcript_path(integration, action)}): "
                "commit the transcripts first (scripts/gen_transcripts.py)"
            )
        calls[action] = blob
    return {
        "date": datetime.date.today().isoformat(),
        "commit": git("rev-parse", "HEAD"),
        "tester": tester,
        "devices": devices,
        **({"group": True} if group else {}),
        "calls": calls,
    }


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("integration")
    parser.add_argument("actions", nargs="+", metavar="action")
    parser.add_argument("--tester", required=True, help="the tester's GitHub handle, without the @")
    parser.add_argument(
        "--device",
        action="append",
        required=True,
        type=parse_device,
        dest="devices",
        metavar="model,manufacturer,class",
        help="a device tested (repeatable); `-` for a manufacturer or class that is null",
    )
    parser.add_argument("--group", action="store_true", help="the devices are a native group's or a scene's members")
    args = parser.parse_args(argv)
    registry = registry or AdapterRegistry.discover()
    print(json.dumps(row(args.integration, args.actions, args.tester, args.devices, registry, args.group), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
