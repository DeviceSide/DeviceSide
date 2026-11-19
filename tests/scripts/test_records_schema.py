"""docs/test-records.schema.json: the repository's test records hold to it, and it takes the shapes docs/evidence.md
(Sign-off format) describes and rejects the rest."""

import copy

import pytest
import yaml
from jsonschema import Draft202012Validator

from scripts import check_release as cr

from .record_files import bound, device, manual, ran, record_v1, record_v2, record_v3, signoff, skipped, write

STEPS = cr.REPO / "tests"


def files():
    return [path for folder in sorted(cr.BUNDLES.glob("*/test-records")) for path in cr.listed(folder.parent.name)]


def test_the_schema_is_a_valid_json_schema():
    Draft202012Validator.check_schema(cr.validator().schema)


def test_every_test_records_file_in_the_repo_is_json_and_holds_to_the_schema():
    """The rig writes the records and maintainers the manual rows; gen_compat and check_release read them."""
    assert files()
    assert [path.name for path in files() if path.suffix != ".json"] == []
    for path in files():
        cr.load(path)  # names the file and the error


def test_every_record_is_its_step_files_action_and_options():
    """A record's file name is its suite's, the step file's, which says what it tests."""
    for path in files():
        if path.name.startswith("_"):
            continue
        integration = path.parent.parent.name
        found = [STEPS / "rig" / "steps" / path.with_suffix(".yaml").name]
        found.append(STEPS / "integrations" / integration / "rig" / path.with_suffix(".yaml").name)
        (step,) = (step for step in found if step.is_file())
        steps, record = yaml.safe_load(step.read_text()), cr.load(path)
        assert (record["action"], record.get("options")) == (steps["action"], steps.get("options")), path.name


# Shapes the schema takes, and ones it rejects.

HUE = device("LWA012", "1.163.1", "hue")
RECORD = record_v3(
    "zigbee2mqtt",
    "turn_on_for",
    [
        ran("light", HUE, role="light_dimmable"),
        ran("light", HUE, group=True, role="group"),
        skipped(),
        {"id": "t[light_ct] observed", "role": "light_ct", "result": "skipped", "fact": True},
    ],
)
PACKAGED = record_v2("zigbee2mqtt", "turn_on_for", RECORD["tests"])  # format 2: bound to the package tree
MEMBER = {"model": "LWA012", "firmware": "1.163.1", "class": "hue"}  # a group member without its manufacturer
OLD = record_v1("zha", "stop", tests=[{"id": "t[r]", "role": "r", "domain": "light", "result": "pass", "classes": []}])
FACTS = {
    "format": 2,
    "integration": "shelly",
    "facts": [
        {
            "date": "2026-11-11",
            "suite": "set_auto_off",
            "test": "takes_the_bounds[switch_plug]",
            "kind": "automated",
            "result": "pass",
            "devices": [{"model": "S3SW-001X8EU", "manufacturer": None, "firmware": "1", "class": "Switch"}],
        }
    ],
}
MIXED = (("S3SW-001X8EU", "Switch"), ("S3BL-C010007AEU", "RGBCCT"))  # a relay and a bulb, each on its class
MANUAL = manual("shelly", signoff(devices=MIXED), signoff(calls=bound("set_auto_off")))
MANUAL_V2 = manual("shelly", signoff(devices=MIXED, passed=["turn_on_for"]))  # format 2: the actions, not their calls


def errors(data):
    return [error.message for error in cr.validator().iter_errors(data)]


@pytest.mark.parametrize(
    "data",
    [RECORD, PACKAGED, OLD, FACTS, MANUAL, MANUAL_V2],
    ids=["format 3", "format 2", "format 1", "facts", "manual", "manual format 2"],
)
def test_the_schema_takes_each_kind_of_file(data):
    assert errors(data) == []


def changed(data, change):
    data = copy.deepcopy(data)
    change(data)
    return data


def test_a_converted_fact_row_says_so_lacks_a_class_and_keeps_a_name():
    """A row converted from _facts.md has no manufacturer or class; one the rig writes has both, so it says which."""
    row = {"model": "S3SW-001X8EU", "name": "Shelly 1 Mini Gen3", "firmware": "1"}
    assert errors(changed(FACTS, lambda d: d["facts"][0].update(converted=True, devices=[row]))) == []
    assert "'class' is a required property" in errors(changed(FACTS, lambda d: d["facts"][0].update(devices=[row])))
    classed = changed(FACTS, lambda d: d["facts"][0].update(converted=True))
    assert any("should not be valid" in message for message in errors(classed))


def test_a_passing_record_holds_no_failing_test():
    """A record's result is its tests': a pass with a failing test would sign off a run that failed."""
    failing = changed(RECORD, lambda d: d["tests"][0].update(result="fail"))
    assert any("is not one of ['pass', 'skipped', 'not observed']" in message for message in errors(failing))
    assert errors(changed(failing, lambda d: d.update(result="fail"))) == []
    assert errors(changed(OLD, lambda d: d["tests"][0].update(result="fail"))) != []  # format 1 alike


def test_a_scenes_test_is_a_groups():
    """A scene's one call is the scene's, not its members' (Decision 27), so its test carries `group`."""
    scene = {"id": "t[scene]", "domain": "scene", "role": "scene", "result": "pass", "devices": [HUE]}
    assert "'group' is a required property" in errors(changed(RECORD, lambda d: d["tests"].append(scene)))
    assert errors(changed(RECORD, lambda d: d["tests"].append(scene | {"group": True}))) == []
    old = {"id": "t[scene]", "domain": "scene", "role": "scene", "result": "pass"}
    assert "'group' is a required property" in errors(changed(OLD, lambda d: d["tests"].append(old)))
    assert errors(changed(OLD, lambda d: d["tests"].append(old | {"group": True}))) == []
    unrun = {"id": "t[scene]", "role": "scene", "result": "skipped", "reason": "none in the profile"}
    assert errors(changed(RECORD, lambda d: d["tests"].append(unrun))) == []


@pytest.mark.parametrize("role", ["group", "group_color"])
def test_a_group_roles_test_is_a_groups(role):
    """Without `group`, a group's test would credit each member as tested on its own."""
    test = ran("light", HUE, role=role)
    assert "'group' is a required property" in errors(changed(RECORD, lambda d: d["tests"].append(test)))
    assert errors(changed(RECORD, lambda d: d["tests"].append(test | {"group": True}))) == []
    assert errors(changed(RECORD, lambda d: d["tests"].append(skipped(role)))) == []


def test_a_passing_record_holds_a_passing_test():
    """An all-skipped run made no call, so it signs nothing off."""
    unrun = changed(RECORD, lambda d: d.update(tests=[skipped()]))
    assert any("does not contain items" in message for message in errors(unrun))
    assert errors(changed(unrun, lambda d: d.update(result="fail"))) == []
    old = changed(OLD, lambda d: d["tests"][0].update(result="skipped", reason="none in the profile"))
    assert any("does not contain items" in message for message in errors(old))  # format 1 alike


def test_a_manufacturer_is_a_string_or_null():
    """Null where none was reported or recorded; a string names the maker the run tested."""
    named = changed(RECORD, lambda d: d["tests"][0]["devices"][0].update(manufacturer="Signify Netherlands B.V."))
    assert errors(named) == []
    assert RECORD["tests"][0]["devices"][0]["manufacturer"] is None
    assert MANUAL["signoffs"][0]["devices"][0]["manufacturer"] is None
    assert errors(changed(MANUAL, lambda d: d["signoffs"][0]["devices"][0].update(manufacturer="Shelly"))) == []
    assert errors(changed(FACTS, lambda d: d["facts"][0]["devices"][0].update(manufacturer=None))) == []


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (changed(RECORD, lambda d: d.update(devices=[])), "should not be valid"),  # record-level devices are format 1's
        (changed(RECORD, lambda d: d.pop("calls")), "'calls' is a required property"),
        (changed(RECORD, lambda d: d.update(package="0123456789ab")), "should not be valid"),  # format 2's binding
        (changed(RECORD, lambda d: d.update(calls="abc1234")), "does not match"),  # a full blob id, never abbreviated
        (changed(PACKAGED, lambda d: d.pop("package")), "'package' is a required property"),
        (changed(PACKAGED, lambda d: d.update(calls=RECORD["calls"])), "should not be valid"),
        (changed(RECORD, lambda d: d["tests"][0].pop("devices")), "'devices' is a required property"),
        (changed(RECORD, lambda d: d["tests"][0].pop("domain")), "'domain' is a required property"),
        (changed(RECORD, lambda d: d["tests"][0]["devices"][0].pop("class")), "'class' is a required property"),
        (changed(RECORD, lambda d: d["tests"][0]["devices"][0].pop("manufacturer")), "'manufacturer' is a required"),
        (changed(RECORD, lambda d: d["tests"][1].update(devices=[MEMBER])), "'manufacturer' is a required"),  # group
        (changed(RECORD, lambda d: d["tests"][0]["devices"][0].update(manufacturer="")), "should be non-empty"),
        (changed(RECORD, lambda d: d["tests"][0].update(classes=["hue"])), "'classes' was unexpected"),
        (changed(RECORD, lambda d: d["tests"][2].pop("reason")), "is not valid under any of the given schemas"),
        (changed(RECORD, lambda d: d["tests"][2].update(devices=[HUE])), "should not be valid"),
        (changed(RECORD, lambda d: d["tests"][3].update(result="pass")), "'skipped' was expected"),
        (changed(RECORD, lambda d: d["tests"][0].update(result="passed")), "is not one of"),
        (changed(RECORD, lambda d: d.update(format=4)), "is not one of"),
        (changed(RECORD, lambda d: d.update(ran="1 passed")), "'ran' was unexpected"),  # counts are derived
        (changed(RECORD, lambda d: d["source"].update(commit="main")), "does not match"),
        (changed(OLD, lambda d: d.pop("devices")), "'devices' is a required property"),
        (changed(OLD, lambda d: d["tests"][0].update(devices=[HUE])), "'devices' was unexpected"),
        (changed(OLD, lambda d: d["devices"].append({"firmware": "1"})), "'model' is a required property"),
        (changed(MANUAL, lambda d: d["signoffs"][1].update(passed=["stop"])), "should not be valid"),  # format 2's
        (changed(MANUAL, lambda d: d["signoffs"][0].pop("calls")), "'calls' is a required property"),
        (changed(MANUAL, lambda d: d["signoffs"][0].update(calls={})), "should be non-empty"),
        (changed(MANUAL, lambda d: d["signoffs"][0].update(calls={"turn_on_for": "abc"})), "does not match"),
        (changed(MANUAL, lambda d: d["signoffs"][0].update(calls={"Stop": RECORD["calls"]})), "does not match"),
        (changed(MANUAL, lambda d: d["signoffs"][0].update(no_call_changed=True)), "was unexpected"),
        (changed(MANUAL, lambda d: d["signoffs"][0].pop("devices")), "'devices' is a required property"),
        (changed(MANUAL_V2, lambda d: d["signoffs"][0].pop("passed")), "'passed' is a required property"),
        (changed(MANUAL_V2, lambda d: d["signoffs"][0].update(calls=bound("stop"))), "should not be valid"),
        (changed(MANUAL, lambda d: d["signoffs"][0]["devices"][0].update(firmware=None)), "is not of type 'string'"),
        (changed(MANUAL, lambda d: d["signoffs"][0]["devices"][0].pop("manufacturer")), "'manufacturer' is a required"),
        (changed(FACTS, lambda d: d["facts"][0].update(kind="watched")), "is not one of"),
        (changed(FACTS, lambda d: d["facts"][0].update(devices=[])), "should be non-empty"),
    ],
)
def test_the_schema_rejects_a_file_out_of_format(data, error):
    assert any(error in message for message in errors(data)), errors(data)


def test_a_manual_row_must_name_its_signer_as_signed_by():
    """`tester`, the field's old name, is no longer accepted: a row without `signed_by` fails, with or without it."""
    old = changed(MANUAL, lambda d: d["signoffs"][0].update(tester=d["signoffs"][0].pop("signed_by")))
    neither = changed(MANUAL, lambda d: d["signoffs"][0].pop("signed_by"))
    for data in (old, neither):
        assert any("'signed_by' is a required property" in message for message in errors(data)), errors(data)


def test_a_manual_row_may_rest_on_reports_and_give_firmware():
    issue = "https://github.com/DeviceSide/DeviceSide/issues/12"
    row = changed(MANUAL, lambda d: d["signoffs"][0].update(reports=[issue]))
    assert errors(changed(row, lambda d: d["signoffs"][0]["devices"][0].update(firmware="1.2"))) == []
    for reports, error in [
        ([], "should be non-empty"),
        ([issue, issue], "has non-unique elements"),
        (["https://github.com/someone/else/issues/12"], "does not match"),
        ([issue + "#issuecomment-1"], "does not match"),
        (["https://github.com/DeviceSide/DeviceSide/pull/12"], "does not match"),
    ]:
        found = errors(changed(row, lambda d, reports=reports: d["signoffs"][0].update(reports=reports)))
        assert any(error in message for message in found), (reports, found)


def test_manual_and_facts_files_parse_by_their_names(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "BUNDLES", tmp_path / "docs" / "integrations")
    folder = cr.test_records_dir("shelly")
    write(folder / cr.MANUAL, MANUAL)
    write(folder / cr.FACTS, FACTS)
    assert cr.manual_rows("shelly", "turn_on_for") == [
        (False, [("S3SW-001X8EU", "Switch"), ("S3BL-C010007AEU", "RGBCCT")])
    ]
    assert cr.manual_rows("shelly", "stop") == []
    assert cr.load(folder / cr.FACTS)["facts"][0]["devices"][0]["class"] == "Switch"
    write(folder / cr.FACTS, MANUAL)  # sign-offs under the facts' name
    with pytest.raises(SystemExit, match="_facts.json: not the kind of file its name says"):
        cr.load(folder / cr.FACTS)
    (folder / "stop.json").write_text("{")
    with pytest.raises(SystemExit, match="stop.json: not JSON"):
        cr.load(folder / "stop.json")


def test_a_manual_row_may_be_a_group_only_alongside_devices():
    assert errors(manual("shelly", signoff(devices=MIXED, group=True))) == []
    bare = {key: value for key, value in signoff(group=True).items() if key != "devices"}
    assert errors(manual("shelly", bare)) != []
