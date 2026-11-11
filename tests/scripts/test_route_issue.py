"""scripts/route_issue.py: the Integration dropdown's choices become labels and assignees, read without importing."""

import pytest

from custom_components.deviceside.core.registry import AdapterRegistry
from scripts import route_issue as ri

KNOWN = {
    "Hue": ri.Integration("hue", "Hue", ("jasonmx",)),
    "Control4": ri.Integration("control4", "Control4", ("alice", "jasonmx")),
}


def body(choices: str) -> str:
    return f"### Integration\n\n{choices}\n\n### Devices\n\nhue · lamp · LTA009 · 1.2\n"


@pytest.mark.parametrize(
    ("choices", "labels", "assignees"),
    [
        ("Hue", ["integration:hue"], ["jasonmx"]),
        ("Control4, Hue", ["integration:control4", "integration:hue"], ["alice", "jasonmx"]),
        ("Hue, Hue", ["integration:hue"], ["jasonmx"]),
        (ri.OTHER, [], []),
        ("Hue, Unknown", ["integration:hue"], ["jasonmx"]),
        (ri.EMPTY, [], []),
    ],
)
def test_choices_route_to_labels_and_maintainers(choices, labels, assignees):
    assert ri.route(body(choices), KNOWN) == (labels, assignees)


def test_a_body_without_the_dropdown_routes_nowhere():
    assert ri.route("### Devices\n\nHue\n", KNOWN) == ([], [])


def test_the_last_field_is_read_to_the_end():
    assert ri.chosen("### Notes\n\nx\n\n### Integration\n\nHue\n") == ["Hue"]


def test_the_parse_matches_the_registry():
    """Reading `__init__.py` without importing it gives what the registry holds."""
    registry = AdapterRegistry.discover()
    expected = {
        info.title: ri.Integration(info.key, info.title, info.maintainers) for info in registry.available_integrations()
    }
    assert ri.integrations() == expected


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("X = 1\n", "no INTEGRATION"),
        ('INTEGRATION = IntegrationInfo(key="a", title="A")\n', "needs key=, title= and maintainers="),
        ('INTEGRATION = IntegrationInfo(key="a", title="A", maintainers=HANDLES)\n', "must be literals"),
    ],
)
def test_an_unreadable_integration_is_an_error(tmp_path, source, error):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "__init__.py").write_text(source)
    with pytest.raises(SystemExit, match=error):
        ri.integrations(tmp_path)


def test_main_writes_the_step_outputs(tmp_path, monkeypatch):
    output = tmp_path / "out"
    monkeypatch.setenv("ISSUE_BODY", body("Hue"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert ri.main() == 0
    assert output.read_text() == "labels=integration:hue\nassignees=jasonmx\n"


def test_main_prints_without_a_step_output(monkeypatch, capsys):
    monkeypatch.setenv("ISSUE_BODY", body(ri.OTHER))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert ri.main() == 0
    assert capsys.readouterr().out == "labels=\nassignees=\n"
