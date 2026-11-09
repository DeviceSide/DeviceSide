#!/usr/bin/env python3
"""Generate the README feature table: per feature and integration, an icon for each kind of target that is built
(light, switch, native group, native scene), and one prohibited sign for whatever can't be built, as far as we know.

What is built comes from each adapter's `AdapterScope`: an amber icon for what works with the Experimental features
option off, a grey one for what works only with it on. Only NO_PATH, the known blockers, is kept by hand. A blank cell
means possible but not built yet.

Usage: scripts/gen_features.py [--check]

--check exits 1 when the table in README.md differs from what the adapters generate.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.core.registry import AdapterRegistry  # noqa: E402
from custom_components.deviceside.core.scope import Level  # noqa: E402
from scripts.check_release import adapters  # noqa: E402

README = REPO / "README.md"
START = "<!-- features:start -->"
END = "<!-- features:end -->"
# Absolute: HACS renders the README inside Home Assistant, where relative image paths don't resolve.
ICON_URL = "https://raw.githubusercontent.com/jasonmx/DeviceSide/main/docs/icons/{}.svg"

# Icon key -> (alt text in a cell, legend label), in the order a cell shows them.
ICONS = {
    "light": ("light", "lights"),
    "switch": ("switch", "switches"),
    "group": ("native group", "native groups"),
    "scene": ("native scene", "native scene"),
}
COLUMNS = {"zha": "ZHA", "zigbee2mqtt": "Z2M", "shelly": "Shelly", "hue": "Hue Bridge", "matter": "Matter"}
# (label, README anchor, actions): a cell is built only for what every one of the row's actions takes. A smooth move
# is unusable without `stop`, so its rows include it.
FEATURES = (
    ("Turn on with timer", "turn-on-with-timer", ("turn_on_for",)),
    ("Turn off with timer", "turn-off-with-timer", ("turn_off_for",)),
    (
        "Auto-off/on (aka inching)",
        "auto-off-aka-inching-and-auto-on",
        ("set_auto_off", "set_auto_on", "clear_auto_off", "clear_auto_on"),
    ),
    ("Smooth dimming", "smooth-dimming", ("raise_brightness", "lower_brightness", "stop")),
    ("Smooth saturation change", "smooth-color-changes", ("raise_saturation", "lower_saturation", "stop")),
    ("Smooth hue change", "smooth-color-changes", ("raise_hue", "lower_hue", "stop")),
    (
        "Set brightness, color or CT<br>without turning on",
        "set-brightness-color-temperature-or-color-without-turning-on",
        ("set_attributes",),
    ),
    ("Set scene without turning on", "set-scene-without-turning-on", ("set_scene",)),
    ("Get attributes", "get-attributes", ("get_attributes",)),
)
# (feature label, integration) -> icon keys with a known blocker, so never "not built yet". See docs/design.md "Scope".
NO_PATH = {
    # Zigbee and Matter `OnWithTimedOff` is on-then-off only: there is no off-then-on timer to send.
    ("Turn off with timer", "zha"): ("light", "switch", "group"),
    ("Turn off with timer", "zigbee2mqtt"): ("light", "switch", "group"),
    ("Turn off with timer", "matter"): ("light", "switch"),
    # Hue bridge timers ignore a manual on or off, so they can't be cancelled the way users expect.
    ("Turn off with timer", "hue"): ("light", "group"),
    ("Turn on with timer", "hue"): ("light", "group"),
    # A hue rotation isn't a straight line in xy, so it can't be one bridge command.
    ("Smooth hue change", "hue"): ("light", "group"),
}


def keys(adapter, registry: AdapterRegistry, experimental: bool = False) -> set[str]:
    """The icon keys an adapter covers: its domains at any Level but Experimental (Documented and Reported ship with
    the option off), plus `group` when it takes lights and the dispatcher passes it native groups, natively or expanded
    to their members (`_expand_native_groups`). Empty when the scope lists capabilities and every one is Experimental:
    then no call works with the option off. With `experimental`, what it covers with the option on: every domain."""
    capabilities = adapter.scope.capabilities
    if (
        not experimental
        and capabilities is not None
        and all(level is Level.EXPERIMENTAL for level in capabilities.values())
    ):
        return set()
    found = {
        domain for domain, level in adapter.scope.domains.items() if experimental or level is not Level.EXPERIMENTAL
    }
    groups = adapter.scope.native_groups or registry.integrations[adapter.integration].expand_group is not None
    if groups and "light" in found:
        found.add("group")
    return found


def built(registry: AdapterRegistry, experimental: bool = False) -> dict[tuple[str, str], set[str]]:
    """(feature label, integration) -> icon keys every one of the row's actions covers, with the Experimental features
    option on when `experimental`."""
    by_pair = {(adapter.action, adapter.integration): adapter for _, adapter in adapters(registry)}
    actions = {action for action, _ in by_pair}
    extra = sorted({integration for _, integration in by_pair} - set(COLUMNS))
    if extra:
        raise SystemExit(f"no README column for integration {', '.join(extra)}; add it to COLUMNS")
    cells = {}
    for label, _, row_actions in FEATURES:
        if missing := [action for action in row_actions if action not in actions]:
            raise SystemExit(f"{label}: no adapter anywhere for {', '.join(missing)}; was it renamed?")
        for integration in COLUMNS:
            found = [by_pair.get((action, integration)) for action in row_actions]
            cells[label, integration] = (
                set.intersection(*(keys(adapter, registry, experimental) for adapter in found)) if all(found) else set()
            )
    return cells


def img(name: str, text: str) -> str:
    return f'<img src="{ICON_URL.format(name)}" height="20" alt="{text}" title="{text}">'


def cell(have: set[str], blocked: tuple[str, ...], trial: set[str] = frozenset()) -> str:
    """An icon per built key, amber, or grey when it works only with the Experimental features option on, then one
    prohibited sign naming every blocked key."""
    icons = []
    for key in ICONS:
        if key in have:
            icons.append(img(key, ICONS[key][0]))
        elif key in trial:
            icons.append(img(f"{key}-grey", f"{ICONS[key][0]}: Experimental"))
    if blocked:
        icons.append(img("no", f"{', '.join(ICONS[key][0] for key in ICONS if key in blocked)}: not possible"))
    return " ".join(icons)


def generate(registry: AdapterRegistry) -> str:
    cells = built(registry)
    trial = built(registry, experimental=True)
    labels = {label for label, _, _ in FEATURES}
    for (label, integration), blocked in NO_PATH.items():
        if label not in labels or integration not in COLUMNS:
            raise SystemExit(f"NO_PATH entry ({label!r}, {integration!r}) names no README row or column")
        if unknown := [key for key in blocked if key not in ICONS]:
            raise SystemExit(f"NO_PATH entry ({label!r}, {integration!r}): no icon {', '.join(unknown)}")
        if stale := [key for key in blocked if key in trial[label, integration]]:
            raise SystemExit(
                f"{label} on {COLUMNS[integration]}: {', '.join(stale)} is built, so not blocked; drop it from NO_PATH"
            )
    lines = [
        START,
        "<!-- Generated by scripts/gen_features.py from the adapters' scopes. Do not edit; run the script. -->",
        "",
        f"| Feature by Integration | {' | '.join(COLUMNS.values())} |",
        f"|:--- |{':---:|' * len(COLUMNS)}",
    ]
    for label, anchor, _ in FEATURES:
        row = [
            cell(cells[label, integration], NO_PATH.get((label, integration), ()), trial[label, integration])
            for integration in COLUMNS
        ]
        lines.append(f"| [{label}](#{anchor}) | {' | '.join(row)} |")
    legend = [f"{img(key, alt)} {label}" for key, (alt, label) in ICONS.items()]
    legend.append(f"{img('light-grey', 'Experimental')} grey: experimental")
    legend.append(f"{img('no', 'not possible')} can't be done, as far as we know")
    lines += ["", " &nbsp; ".join(legend), "", END]
    return "\n".join(lines)


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped bar hyphens, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(text: str) -> set[str]:
    """The anchors of a Markdown text's headings."""
    return {slug(line.lstrip("#")) for line in text.splitlines() if re.match(r"#{1,6} ", line)}


def check_anchors(text: str) -> None:
    """Every row links to a heading the README has, so a renamed heading fails here rather than leaving a dead link."""
    headings = anchors(text)
    if dead := sorted({anchor for _, anchor, _ in FEATURES} - headings):
        raise SystemExit(f"README.md has no heading for #{', #'.join(dead)}; fix FEATURES")


def splice(text: str, table: str) -> str:
    """The README with the text between the markers, markers included, replaced by the table."""
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise SystemExit(f"README.md needs one {START} before one {END}")
    return text[: text.index(START)] + table + text[text.index(END) + len(END) :]


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None, readme: Path = README) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the README table is out of date")
    args = parser.parse_args(argv)

    text = readme.read_text()
    new = splice(text, generate(registry or AdapterRegistry.discover()))
    check_anchors(text)
    if args.check:
        if new != text:
            print(
                f"error: the feature table in {readme.name} is out of date; run scripts/gen_features.py",
                file=sys.stderr,
            )
            return 1
        return 0
    readme.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
