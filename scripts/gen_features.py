#!/usr/bin/env python3
"""Generate the feature table at the top of docs/device-compatibility.md: per feature and integration, an icon for each
kind of target that is built (light, switch, native group, native scene), and a lone prohibited sign for a feature
that is not possible on the whole integration.

Each icon links to the docs: a cell's to its integration's page, `docs/integrations/<integration>/index.md` (the
feature's section when it has one), a prohibited sign's to the section of docs/integrations.md that says why, a legend
entry's to the heading that explains it.

The columns come from each integration's bundle: `column` (the table's label) and `column_order` in
`docs/integrations/<integration>/devices.yaml`. An integration without one is an error naming the file to add.

What is built comes from each adapter's `AdapterScope`: an amber icon for what works with the Labs option
off, a grey one for what works only with it on. Only NO_PATH, the known blockers, is kept by hand, one whole cell
each. A blank cell means possible on some device, or not built yet.

Usage: scripts/gen_features.py [--check]

--check exits 1 when the table in docs/device-compatibility.md differs from what the adapters generate.
"""

import argparse
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from custom_components.deviceside.const import DOCS_URL  # noqa: E402
from custom_components.deviceside.core.registry import AdapterRegistry, served_domains  # noqa: E402
from custom_components.deviceside.core.scope import Level  # noqa: E402
from custom_components.deviceside.features import FEATURE_ACTIONS  # noqa: E402
from scripts.check_release import BUNDLES, adapters  # noqa: E402

README = REPO / "README.md"
PAGE_FILE = "docs/device-compatibility.md"
PAGE = REPO / PAGE_FILE
START = "<!-- features:start -->"
END = "<!-- features:end -->"
# Absolute: the raw file, so GitHub shows the icon inline rather than linking its SVG page.
ICON_URL = "https://raw.githubusercontent.com/DeviceSide/DeviceSide/main/docs/icons/{}.svg"
# A doc link, absolute: one form for every link in the table. Without a link of its own, GitHub links each icon to its
# SVG file.
DOC_URL = DOCS_URL + "{}#{}"
INTEGRATIONS = "docs/integrations.md"
# The integrations.md section explaining every NO_PATH entry to users; keep the two in step.
IMPOSSIBLE = "what-cant-be-done-and-why"
# The integrations.md section explaining a cell shown from a ridden action's adapter (`ridden`).
RIDDEN = "home-assistant-scenes"

# Icon key -> alt text in a cell, in the order a cell shows them.
ICONS = {"light": "light", "switch": "switch", "group": "native group", "scene": "native scene"}
# (label, README section anchor, integration page section, device cards' name, actions): a cell is built only for
# what every one of the row's actions takes. A smooth move is unusable without `stop`, so its rows include it. A cell's
# icons link to the section of the integration's page, or to the page when it has none. The device cards (gen_compat)
# name each action's feature by its row's card name.
FEATURES = (
    (
        "Turn on with timer",
        "turn-on-with-timer",
        "Turn on with timer",
        "turn on with timer",
        FEATURE_ACTIONS["turn on with timer"],
    ),
    (
        "Turn off with timer",
        "turn-off-with-timer",
        "Turn off with timer",
        "turn off with timer",
        FEATURE_ACTIONS["turn off with timer"],
    ),
    (
        "Auto-off/on (aka inching)",
        "auto-off-aka-inching-and-auto-on",
        "Auto-off/on",
        "auto-off/on",
        FEATURE_ACTIONS["auto-off/on"],
    ),
    (
        "Smooth dimming",
        "smooth-dimming",
        "Smooth dimming",
        "smooth dimming",
        FEATURE_ACTIONS["smooth dimming"],
    ),
    (
        "Smooth saturation change",
        "smooth-color-changes",
        "Smooth color changes",
        "smooth saturation",
        FEATURE_ACTIONS["smooth saturation"],
    ),
    (
        "Smooth hue change",
        "smooth-color-changes",
        "Smooth color changes",
        "smooth hue",
        FEATURE_ACTIONS["smooth hue"],
    ),
    (
        "Set brightness, color or CT<br>without turning on",
        "set-brightness-color-temperature-or-color-without-turning-on",
        "Flash-free turn-on",
        "set without turning on",
        FEATURE_ACTIONS["set without turning on"],
    ),
    (
        "Set scene without turning on",
        "set-scene-without-turning-on",
        "Flash-free turn-on",
        "set scene",
        FEATURE_ACTIONS["set scene"],
    ),
    ("Get attributes", "get-attributes", "Get attributes", "get attributes", FEATURE_ACTIONS["get attributes"]),
)
# (icons, alt text, label, file, anchor): the legend, in order. Each icon links to the heading that explains it; a
# heading of the page itself links within it.
LEGEND = (
    (("light",), "light", "lights", PAGE_FILE, "tested-devices"),
    (("switch",), "switch", "switches", PAGE_FILE, "tested-devices"),
    (("group",), "native group", "groups", PAGE_FILE, "native-groups"),
    (("scene",), "native scene", "scenes", "README.md", "set-scene-without-turning-on"),
    (
        ("light-grey", "switch-grey"),
        "Labs",
        "Labs",
        PAGE_FILE,
        "levels-of-proof",
    ),
    (("no",), "not possible", "not possible", INTEGRATIONS, IMPOSSIBLE),
)
# (feature label, integration) cells where the feature is impossible on the integration for every device we know of,
# and we've found no device where it's possible: so never "not built yet", and never beside a built icon (generate
# fails). Users read why in docs/integrations.md, at IMPOSSIBLE. A feature that only some devices can't do stays
# blank, and that page says so.
NO_PATH = {
    # Matter `OnWithTimedOff` is on-then-off only: there is no off-then-on timer to send. Zigbee's is the same, so a
    # Zigbee group, and a Zigbee device but Tuya's, has no call for it either; that is only some of an integration's
    # targets, as Tuya's datapoint countdown serves turn off with timer on Zigbee2MQTT, so no Zigbee cell is marked.
    ("Turn off with timer", "matter"),
    # Hue bridge timers ignore a manual on or off, so they can't be cancelled the way users expect.
    ("Turn off with timer", "hue"),
    ("Turn on with timer", "hue"),
    # CLIP v2 has no rule engine, so the bridge can't store "off N seconds after any turn-on".
    ("Auto-off/on (aka inching)", "hue"),
    # A hue rotation isn't a straight line in xy, so it can't be one bridge command.
    ("Smooth hue change", "hue"),
}


def bundle(integration: str) -> dict:
    """The integration's `devices.yaml`, parsed. Missing, it is an error naming the file to add."""
    path, name = BUNDLES / integration / "devices.yaml", f"docs/integrations/{integration}/devices.yaml"
    if not path.is_file():
        raise SystemExit(f"no {name}; add the {integration} bundle (devices.yaml and index.md)")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{name} must be a mapping")
    return data


def page(integration: str) -> str:
    """The integration's user page, relative to the repository."""
    return f"docs/integrations/{integration}/index.md"


def columns(integrations: Iterable[str]) -> dict[str, str]:
    """Integration -> its column label, in `column_order`, from each bundle."""
    found = {}
    for key in integrations:
        data = bundle(key)
        label, order = data.get("column"), data.get("column_order")
        if not isinstance(label, str) or not label or not isinstance(order, int) or isinstance(order, bool):
            raise SystemExit(f"docs/integrations/{key}/devices.yaml needs a column and a column_order")
        found[key] = (order, label)
    return {key: label for key, (_, label) in sorted(found.items(), key=lambda item: item[1])}


def integration_columns(registry: AdapterRegistry) -> dict[str, str]:
    """Every integration's column, those of integrations without adapters included."""
    return columns(sorted({*registry.integrations, *(adapter.integration for _, adapter in adapters(registry))}))


def keys(adapter, registry: AdapterRegistry, labs: bool = False) -> set[str]:
    """The icon keys an adapter covers: its domains at any Level but Labs (Verified and Documented ship with
    the option off) where some class that isn't in Labs can be on it (a class entry held on the domain, which
    the class declares in `IntegrationInfo.classes`; with no classes named, any domain), plus `group` when it takes
    lights and the dispatcher passes it native groups, natively or expanded to their members
    (`_expand_native_groups`). Empty when the adapter is flagged whole (every domain in Labs), or the scope
    lists capabilities and every one is in Labs: then no call works with the option off. With `labs`,
    what it covers with the option on: every domain. Either way, only domains it serves some class on
    (`served_domains`)."""
    capabilities = adapter.scope.capabilities
    if not labs and (
        adapter.scope.all_labs
        or (capabilities is not None and all(level is Level.LABS for _, level, _ in adapter.scope.class_entries()))
    ):
        return set()
    info = registry.integrations[adapter.integration]
    served = served_domains(adapter, info)
    found = {
        domain
        for domain, level in adapter.scope.domains.items()
        if (labs or level is not Level.LABS) and domain in served
    }
    declared = info.classes
    if not labs and capabilities is not None and declared:
        found = {
            domain
            for domain in found
            if any(
                level is not Level.LABS and (on is None or domain in on) and domain in declared.get(name, ())
                for name, level, on in adapter.scope.class_entries()
            )
        }
    groups = adapter.scope.native_groups or registry.integrations[adapter.integration].expand_group is not None
    if groups and "light" in found:
        found.add("group")
    return found


def lent(registry: AdapterRegistry, integration: str) -> dict[str, str]:
    """The actions the integration has no adapter for but takes from the action they ride (`Action.rides`): riding key
    -> ridden key, where the integration has the ridden action's adapter."""
    have = {adapter.action for _, adapter in adapters(registry) if adapter.integration == integration}
    return {
        key: action.rides.action
        for key, action in registry.actions.items()
        if action.rides and key not in have and action.rides.action in have
    }


def built(
    registry: AdapterRegistry, labs: bool = False, cols: dict[str, str] | None = None
) -> dict[tuple[str, str], set[str]]:
    """(feature label, integration) -> icon keys every one of the row's actions covers, with the Labs option
    on when `labs`. Every integration has a column. An action the integration has no adapter for takes the cell of
    the action it rides (`lent`)."""
    by_pair = {(adapter.action, adapter.integration): adapter for _, adapter in adapters(registry)}
    actions = {action for action, _ in by_pair}
    if cols is None:
        cols = integration_columns(registry)
    cells = {}
    for label, _, _, _, row_actions in FEATURES:
        if missing := [action for action in row_actions if action not in actions]:
            raise SystemExit(f"{label}: no adapter anywhere for {', '.join(missing)}; was it renamed?")
        for integration in cols:
            lend = lent(registry, integration)
            found = [
                by_pair.get((action, integration)) or by_pair.get((lend.get(action), integration))
                for action in row_actions
            ]
            cells[label, integration] = (
                set.intersection(*(keys(adapter, registry, labs) for adapter in found)) if all(found) else set()
            )
    return cells


def ridden(registry: AdapterRegistry, cols: dict[str, str]) -> set[tuple[str, str]]:
    """The (feature label, integration) cells shown from a ridden action's adapter (`lent`): every action of the row
    is looked up as the integration's own or lent (a missing one empties the cell, as in `built`), and one is lent."""
    found = set()
    for label, _, _, _, row_actions in FEATURES:
        for integration in cols:
            lend = lent(registry, integration)
            if any(action in lend for action in row_actions):
                found.add((label, integration))
    return found


def img(name: str, text: str, href: str) -> str:
    return f'<a href="{href}"><img src="{ICON_URL.format(name)}" height="20" alt="{text}" title="{text}"></a>'


def href(file: str, anchor: str | None) -> str:
    if file == PAGE_FILE:
        return f"#{anchor}"
    return DOC_URL.format(file, anchor) if anchor else DOC_URL.format(file, "").removesuffix("#")


def cell(have: set[str], blocked: bool = False, in_labs: set[str] = frozenset(), link: str = "", why: str = "") -> str:
    """An icon per built key, amber, or grey when it works only with the Labs option on, linking to
    `link`; or, for a `blocked` cell, one prohibited sign linking to `why`, and nothing else."""
    if blocked:
        return img("no", "not possible", why)
    icons = []
    for key in ICONS:
        if key in have:
            icons.append(img(key, ICONS[key], link))
        elif key in in_labs:
            icons.append(img(f"{key}-grey", f"{ICONS[key]}: Labs", link))
    return " ".join(icons)


def cell_link(integration: str, topic: str) -> str:
    """The link for a feature on an integration: its page's section on the feature, else the page."""
    if not (path := REPO / page(integration)).is_file():
        raise SystemExit(f"no {page(integration)}; add the {integration} bundle's user page")
    found = anchors(path.read_text())
    return href(page(integration), slug(topic) if slug(topic) in found else None)


def generate(registry: AdapterRegistry) -> str:
    doc = (REPO / INTEGRATIONS).read_text()
    if IMPOSSIBLE not in anchors(doc):
        raise SystemExit(f"{INTEGRATIONS} has no heading for #{IMPOSSIBLE}; fix IMPOSSIBLE")
    why = href(INTEGRATIONS, IMPOSSIBLE)
    cols = integration_columns(registry)
    cells = built(registry, cols=cols)
    in_labs = built(registry, labs=True, cols=cols)
    lent_cells = ridden(registry, cols)
    labels = {label for label, *_ in FEATURES}
    for label, integration in NO_PATH:
        if label not in labels or integration not in cols:
            raise SystemExit(f"NO_PATH entry ({label!r}, {integration!r}) names no row or column")
        if found := in_labs[label, integration]:
            raise SystemExit(
                f"{label} on {cols[integration]}: {', '.join(sorted(found))} is built, so not impossible; "
                "drop it from NO_PATH"
            )
    lines = [
        START,
        "<!-- Generated by scripts/gen_features.py from the adapters' scopes. Do not edit; run the script. -->",
        "",
        f"| Feature by Integration | {' | '.join(cols.values())} |",
        f"|:--- |{':---:|' * len(cols)}",
    ]
    for label, anchor, topic, *_ in FEATURES:
        row = [
            cell(
                cells[label, integration],
                (label, integration) in NO_PATH,
                in_labs[label, integration],
                href(INTEGRATIONS, RIDDEN) if (label, integration) in lent_cells else cell_link(integration, topic),
                why,
            )
            for integration in cols
        ]
        lines.append(f"| [{label}]({DOC_URL.format('README.md', anchor)}) | {' | '.join(row)} |")
    legend = [
        f"{'&nbsp;'.join(img(icon, alt, href(file, anchor)) for icon in icons)} {label}"
        for icons, alt, label, file, anchor in LEGEND
    ]
    lines += ["", " &nbsp; ".join(legend), "", END]
    return "\n".join(lines)


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped bar hyphens, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchored(text: str) -> list[tuple[str, str, str]]:
    """(level-2 heading it sits under, or "" before the first; heading; GitHub's anchor) for each heading of a
    Markdown text. A level-2 heading is under itself. A repeated slug gets -1, -2 and so on, as GitHub numbers it."""
    seen, found, section = Counter(), [], ""
    for line in text.splitlines():
        if match := re.match(r"(#{1,6}) (.*)", line):
            heading, base = match[2].strip(), slug(match[2])
            if len(match[1]) == 2:
                section = heading
            found.append((section, heading, f"{base}-{seen[base]}" if seen[base] else base))
            seen[base] += 1
    return found


def anchors(text: str) -> set[str]:
    """The anchors of a Markdown text's headings."""
    return {anchor for _, _, anchor in anchored(text)}


def check_anchors(text: str) -> None:
    """Every row and legend entry links to a heading that exists, so a renamed heading fails here rather than leaving
    a dead link. `text` is the page the table goes in: the rows link to the README's headings, a legend entry to its
    file's (the page's own when the file is the page)."""
    if dead := sorted({anchor for _, anchor, *_ in FEATURES} - anchors(README.read_text())):
        raise SystemExit(f"README.md has no heading for #{', #'.join(dead)}; fix FEATURES")
    for _, _, _, file, anchor in LEGEND:
        if anchor not in anchors(text if file == PAGE_FILE else (REPO / file).read_text()):
            raise SystemExit(f"{file} has no heading for #{anchor}; fix LEGEND")


def splice(text: str, table: str) -> str:
    """The page with the text between the markers, markers included, replaced by the table."""
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise SystemExit(f"{PAGE_FILE} needs one {START} before one {END}")
    return text[: text.index(START)] + table + text[text.index(END) + len(END) :]


def main(argv: list[str] | None = None, registry: AdapterRegistry | None = None, page_path: Path = PAGE) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the feature table is out of date")
    args = parser.parse_args(argv)

    text = page_path.read_text()
    new = splice(text, generate(registry or AdapterRegistry.discover()))
    check_anchors(text)
    if args.check:
        if new != text:
            print(
                f"error: the feature table in {page_path.name} is out of date; run scripts/gen_features.py",
                file=sys.stderr,
            )
            return 1
        return 0
    page_path.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
