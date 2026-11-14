#!/usr/bin/env python3
"""One-off: convert every markdown test record to JSON format 1 (docs/test-records.schema.json), and `_facts.md` to
`_facts.json`, removing each `.md`. Run once by step 5b of the device-classes plan, then deleted.

A record keeps all its data: Result, Date, Source, Package, Home Assistant, Options, its Device row as record-level
`devices` (a group as the old reader called one: firmware `unknown`, or named Group or Zone), and its Tests table, the
Capability cell as a test's `classes`. Dropped, as derived: the title (the integration and the file name), the Ran row
(counted from the tests, and checked against them here), the note on `not observed`, and the fact-case bullets, which
quote `_facts.md` (each quote is checked against it here; a case they list becomes `"fact": true`). Zigbee2MQTT's
product codes become the Zigbee model IDs docs/models.yaml pairs them with. The action comes from the record's step
file. Fails on anything it can't read, so nothing is lost silently.
"""

import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
BUNDLES = REPO / "docs" / "integrations"
# Zigbee2MQTT's product code -> the Zigbee model ID (the Basic cluster's), as docs/models.yaml pairs them.
ZIGBEE_MODEL = {"9290018217": "LWA012", "9290024684": "LTA009", "8720169392182": "LCA016"}

KEY_ROW = re.compile(r"^\| (?P<key>[A-Za-z ]+) \| (?P<value>.*) \|$")
ENTRY = re.compile(r"^(?P<name>.*?)(?: \(`(?P<model>[^`]+)`\))?, firmware `(?P<firmware>[^`]+)`$")
SOURCE = re.compile(r"^rig run \(`scripts/rig\.py`\), commit `(?P<commit>[0-9a-f]{7,40})`$")
TARGET = re.compile(r"^`(?P<domain>[a-z_]+)` \((?P<role>[a-z_]+)\)$")
ABSENT = re.compile(r"^(?P<role>[a-z_]+): none in the profile$")
BARE = re.compile(r"^(?P<role>[a-z_]+)$")
TEST_ROW = re.compile(r"^\| `(?P<id>[^`]+)` \| (?P<cells>.*) \|$")
BULLET = re.compile(r"^- `(?P<id>[^`]+)`: (?P<quote>.*)$")
QUOTE = re.compile(r"^last on file (?P<date>\S+), on (?P<devices>.*): (?P<result>pass|fail)$")
RAN = re.compile(r"^(?P<passed>\d+) passed, (?P<skipped>\d+) skipped$")
FACTS_NOTE = "Fact cases run only when asked (--facts), and their results go to [`_facts.md`](_facts.md), never here:"
OBSERVED_NOTE = "Tests marked `not observed` had nobody watching."
FACTS_INTRO = (
    "What the rig's fact cases found, dated. Rows are only ever added: each is a fact, which stands until evidence "
    "contradicts it."
)
FACTS_HEADER = "| Date | Suite | Test | Kind | Devices | Result |"


def fail(path: Path, message: str) -> None:
    raise SystemExit(f"{path.relative_to(REPO)}: {message}")


def check_models() -> None:
    """The mapping is docs/models.yaml's: each pair is one model's ids."""
    models = yaml.safe_load((REPO / "docs" / "models.yaml").read_text())["models"]
    for code, model_id in ZIGBEE_MODEL.items():
        if not any({code, model_id} <= set(model["ids"]) for model in models):
            raise SystemExit(f"docs/models.yaml doesn't pair {code} with {model_id}")


def model_id(integration: str, model: str) -> str:
    return ZIGBEE_MODEL.get(model, model) if integration == "zigbee2mqtt" else model


def device(path: Path, integration: str, item: str) -> dict:
    """A Device-row entry: a model with its firmware and, where the record gave one distinct from the model, the
    name HA's registry gives the model; or a group, as gen_compat's old reader called one."""
    if not (entry := ENTRY.match(item.strip())):
        fail(path, f"can't read Device entry {item!r}")
    name, model, firmware = entry["name"], entry["model"], entry["firmware"]
    if firmware == "unknown" or name.lower() in ("group", "zone"):
        if model:
            fail(path, f"a group entry with a model: {item!r}")
        return {"name": name, "firmware": None if firmware == "unknown" else firmware, "group": True}
    found = {"model": model_id(integration, model or name)}
    if model and name != model:
        found["name"] = name
    return found | {"firmware": firmware}


def devices(path: Path, integration: str, cell: str) -> list[dict]:
    return [] if cell == "none" else [device(path, integration, item) for item in cell.split("; ")]


def step_file(integration: str, suite: str) -> dict:
    for folder in (REPO / "tests" / "rig" / "steps", REPO / "tests" / "integrations" / integration / "rig"):
        if (path := folder / f"{suite}.yaml").is_file():
            return yaml.safe_load(path.read_text())
    raise SystemExit(f"no step file for {integration} {suite}")


def test(path: Path, row: re.Match, capability: bool) -> dict:
    cells = [cell.strip() for cell in row["cells"].split(" | ")]
    if len(cells) != 2 + capability:
        fail(path, f"a Tests row of {len(cells)} cells: {row[0]}")
    target, result = cells[0], cells[-1]
    if result not in ("pass", "fail", "skipped", "not observed"):
        fail(path, f"result {result!r}")
    found: dict = {"id": row["id"]}
    if match := TARGET.match(target):
        found |= {"domain": match["domain"], "role": match["role"]}
    elif match := ABSENT.match(target):
        found |= {"role": match["role"], "absent": True}
    elif match := BARE.match(target):
        found["role"] = match["role"]
    else:
        fail(path, f"can't read Target {target!r}")
    if found.pop("absent", False):
        if result != "skipped":
            fail(path, f"{row['id']}: none in the profile, but {result}")
        found |= {"result": result, "reason": "none in the profile"}
    found["result"] = result
    if capability:
        cell = cells[1]
        classes = [] if cell == "-" else re.findall(r"`([^`]+)`", cell)
        if cell != "-" and ", ".join(f"`{name}`" for name in classes) != cell:
            fail(path, f"can't read Capability {cell!r}")
        found["classes"] = classes
    return found


def facts_rows(path: Path) -> list[dict]:
    """`_facts.md`'s rows, each device with its model as docs/models.yaml names it, and no class: the file
    recorded none."""
    integration = path.parent.parent.name
    lines = path.read_text().splitlines()
    title = lines[0]
    if not title.startswith("# ") or not title.endswith(" · facts") or lines[2] != FACTS_INTRO:
        fail(path, "unexpected heading")
    if lines[4] != FACTS_HEADER or lines[5] != "|---|---|---|---|---|---|":
        fail(path, "unexpected table header")
    rows = []
    for line in lines[6:]:
        cells = [cell.strip() for cell in line.strip("|").split(" | ")]
        if len(cells) != 6:
            fail(path, f"can't read row {line!r}")
        date, suite, test_id, kind, cell, result = cells
        if not (suite.startswith("`") and test_id.startswith("`")) or kind not in ("automated", "observed"):
            fail(path, f"can't read row {line!r}")
        found = devices(path, integration, cell)
        if any(item.get("group") for item in found):
            fail(path, f"a group in a fact row: {line!r}")
        rows.append(
            {
                "date": date,
                "suite": suite.strip("`"),
                "test": test_id.strip("`"),
                "kind": kind,
                "result": result,
                "devices": found,
                "devices_cell": cell,
            }
        )
    return rows


def record(path: Path, facts: list[dict]) -> dict:
    integration, suite = path.parent.parent.name, path.stem
    lines = path.read_text().splitlines()
    if not lines[0].startswith("# ") or not lines[0].endswith(f" · {suite}"):
        fail(path, f"title {lines[0]!r}")
    keys: dict[str, str] = {}
    index = 1
    while index < len(lines) and not lines[index].startswith("## Tests"):
        line = lines[index]
        index += 1
        if line in ("", "| | |", "|---|---|"):
            continue
        if not (row := KEY_ROW.match(line)) or row["key"] in keys:
            fail(path, f"can't read {line!r}")
        keys[row["key"]] = row["value"]
    known = {"Result", "Ran", "Date", "Source", "Package", "Home Assistant", "Device", "Options"}
    if extra := set(keys) - known:
        fail(path, f"rows with no home: {', '.join(sorted(extra))}")
    if not (source := SOURCE.match(keys["Source"])):
        fail(path, f"can't read Source {keys['Source']!r}")
    steps = step_file(integration, suite)
    options = sorted(steps.get("options") or [])
    if (keys.get("Options") or None) != (", ".join(options) or None):
        fail(path, f"Options {keys.get('Options')!r}, but the step file has {options}")
    found: dict = {"format": 1, "integration": integration, "action": steps["action"]}
    if options:
        found["options"] = options
    found |= {"result": keys["Result"], "date": keys["Date"], "source": {"kind": "rig", "commit": source["commit"]}}
    if "Package" in keys:
        if not (tree := re.fullmatch(r"`([0-9a-f]{12,40})`", keys["Package"])):
            fail(path, f"can't read Package {keys['Package']!r}")
        found["package"] = tree[1]
    found |= {"home_assistant": keys["Home Assistant"], "devices": devices(path, integration, keys["Device"])}

    # The Tests table, then the notes after it.
    rest = lines[index + 1 :]
    while rest and rest[0] == "":
        rest = rest[1:]
    header = rest[0]
    capability = header == "| Test | Target | Capability | Result |"
    if not capability and header != "| Test | Target | Result |":
        fail(path, f"Tests header {header!r}")
    rest = rest[2:]
    tests = []
    while rest and rest[0].startswith("|"):
        if not (row := TEST_ROW.match(rest[0])):
            fail(path, f"can't read {rest[0]!r}")
        tests.append(test(path, row, capability))
        rest = rest[1:]
    fact_ids = set()
    notes = [line for line in rest if line]
    while notes:
        line = notes.pop(0)
        if line == OBSERVED_NOTE:
            if not any(t["result"] == "not observed" for t in tests):
                fail(path, "the not-observed note with no such test")
        elif line == FACTS_NOTE:
            while notes and (bullet := BULLET.match(notes[0])):
                notes.pop(0)
                fact_ids.add(bullet["id"])
                if bullet["quote"] != "none on file":
                    quote = QUOTE.match(bullet["quote"])
                    if not quote or not any(
                        (row["suite"], row["test"], row["date"], row["devices_cell"], row["result"])
                        == (suite, bullet["id"], quote["date"], quote["devices"], quote["result"])
                        for row in facts
                    ):
                        fail(path, f"a fact quote _facts.md doesn't hold: {line!r}")
        else:
            fail(path, f"text with no home: {line!r}")
    for item in tests:
        if item["id"] in fact_ids:
            if item["result"] != "skipped":
                fail(path, f"fact case {item['id']} is {item['result']}")
            item["fact"] = True
    if fact_ids - {item["id"] for item in tests}:
        fail(path, f"fact bullets for no test: {sorted(fact_ids)}")
    if "Ran" in keys:
        ran = RAN.match(keys["Ran"])
        counts = [sum(t["result"] == outcome for t in tests) for outcome in ("pass", "skipped")]
        if not ran or [int(ran["passed"]), int(ran["skipped"])] != counts:
            fail(path, f"Ran {keys['Ran']!r}, but the tests count {counts}")
    found["tests"] = tests
    return found


def dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    check_models()
    for folder in sorted(BUNDLES.glob("*/test-records")):
        integration = folder.parent.name
        facts_md = folder / "_facts.md"
        facts = facts_rows(facts_md) if facts_md.is_file() else []
        for path in sorted(folder.glob("*.md")):
            if path.name.startswith("_"):
                if path != facts_md:
                    fail(path, "an underscore file this converter doesn't know")
                continue
            dump(path.with_suffix(".json"), record(path, facts))
            path.unlink()
        if facts_md.is_file():
            rows = [{key: value for key, value in row.items() if key != "devices_cell"} for row in facts]
            dump(folder / "_facts.json", {"format": 2, "integration": integration, "facts": rows})
            facts_md.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
