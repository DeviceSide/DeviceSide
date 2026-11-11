"""The issue forms follow GitHub's issue-form schema, and the options menu prefills only fields they have.

GitHub doesn't reject a broken form on push: it drops it from the template chooser, and a prefill naming an id the
form lacks is ignored without a word. So both are checked here.
"""

import re
from pathlib import Path

import pytest
import yaml

from custom_components.deviceside.config_flow import ISSUE_FORMS

TEMPLATES = Path(__file__).parents[1] / ".github" / "ISSUE_TEMPLATE"
FORMS = sorted(path for path in TEMPLATES.glob("*.yml") if path.name != "config.yml")

# Per GitHub's syntax for issue forms: the attributes and validations each element type takes.
ATTRIBUTES = {
    "markdown": {"value"},
    "input": {"label", "description", "placeholder", "value"},
    "textarea": {"label", "description", "placeholder", "value", "render"},
    "dropdown": {"label", "description", "multiple", "options", "default"},
    "checkboxes": {"label", "description", "options"},
}
ID = re.compile(r"^[A-Za-z0-9_-]+$")


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_there_are_forms():
    assert FORMS


@pytest.mark.parametrize("path", FORMS, ids=lambda path: path.name)
def test_a_form_follows_the_schema(path: Path):
    form = load(path)
    assert set(form) <= {"name", "description", "title", "labels", "assignees", "projects", "type", "body"}
    assert isinstance(form["name"], str) and form["name"]
    assert isinstance(form["description"], str) and form["description"]
    ids = []
    for element in form["body"]:
        kind, attributes = element["type"], element["attributes"]
        assert set(element) <= {"type", "id", "attributes", "validations"}, element
        assert set(attributes) <= ATTRIBUTES[kind], element
        text = {key: value for key, value in attributes.items() if key not in ("options", "multiple", "default")}
        assert all(isinstance(value, str) for value in text.values()), element
        assert set(element.get("validations", {})) <= {"required"}, element
        if kind == "markdown":
            continue
        assert isinstance(attributes["label"], str) and attributes["label"], element
        if "id" in element:
            assert ID.match(element["id"]), element["id"]
            ids.append(element["id"])
        if kind == "checkboxes":
            options = attributes["options"]
            assert isinstance(options, list) and options, element
            for option in options:
                assert set(option) <= {"label", "required"} and isinstance(option["label"], str), option
        if kind == "dropdown":
            options = attributes["options"]
            assert isinstance(options, list) and all(isinstance(option, str) for option in options), element
            assert len(set(options)) == len(options), element
    assert len(set(ids)) == len(ids), ids


@pytest.mark.parametrize("form", ISSUE_FORMS, ids=lambda form: form.step)
def test_the_menu_prefills_only_fields_its_form_has(form):
    template = load(TEMPLATES / form.template)
    fields = {element["id"] for element in template["body"] if element["type"] in ("input", "textarea")}
    assert set(form.fields) <= fields
    assert template["title"] == f"{form.title}: "


def test_the_device_report_lists_every_integration_for_routing():
    """Each integration's title, sorted, then the catch-all: route_issue.py matches the choices by title."""
    from custom_components.deviceside.core.registry import AdapterRegistry
    from scripts import route_issue

    [dropdown] = [element for element in load(TEMPLATES / "device_report.yml")["body"] if element["type"] == "dropdown"]
    assert dropdown["attributes"]["label"] == route_issue.LABEL
    titles = sorted(info.title for info in AdapterRegistry.discover().available_integrations())
    assert dropdown["attributes"]["options"] == [*titles, route_issue.OTHER]


def test_the_menu_lists_the_forms_in_the_chooser_s_order():
    """GitHub's template chooser sorts the forms by file name; the options menu matches it."""
    assert [form.template for form in ISSUE_FORMS] == [path.name for path in FORMS]
