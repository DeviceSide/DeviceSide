"""scripts/gen_compat.py: levels from the records, models from the Device row, groups, the stale-page check."""

from types import SimpleNamespace

import pytest

from custom_components.deviceside.core.scope import AdapterScope
from scripts import check_release as cr
from scripts import gen_compat as gc


def record(root, integration, name, *, result="pass", device="Hue lamp (`LTA009`), firmware `1.2.3`"):
    path = root / "docs" / "test-records" / integration / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# t\n\n| | |\n|---|---|\n| Result | {result} |\n| Device | {device} |\n")
    return path


class FakeRegistry:
    integrations = {"zha": SimpleNamespace(title="ZHA"), "hue": SimpleNamespace(title="Hue")}

    def __init__(self, *adapters):
        self._adapters = adapters

    def matrix(self):
        yield "stop", "hue", None
        for adapter in self._adapters:
            yield adapter.action, adapter.integration, adapter


def adapter(integration, action, *, experimental=False):
    return SimpleNamespace(integration=integration, action=action, scope=AdapterScope(experimental=experimental))


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "REPO", tmp_path)
    monkeypatch.setattr(cr, "RECORDS", tmp_path / "docs" / "test-records")
    return tmp_path


def test_models_are_listed_with_their_firmware_and_groups_are_not_models(root):
    path = record(
        root,
        "hue",
        "stop",
        device="Hue lamp (`LTA009`), firmware `1.2`; LCA016, firmware `0x01`; Zone, firmware `unknown`; "
        "Group, firmware `Zigbee2MQTT 2.1`; a temporary group holding only it",
    )
    assert gc.models(path) == ["`LTA009`, firmware `1.2`", "`LCA016`, firmware `0x01`", "group", "group", "group"]


def test_a_record_with_no_device_lists_no_models(root):
    assert gc.models(record(root, "hue", "set_scene", device="none")) == []


def test_a_device_row_that_cannot_be_read_is_an_error(root):
    with pytest.raises(SystemExit, match="can't read Device entry"):
        gc.models(record(root, "hue", "stop", device="a lamp"))
    path = record(root, "hue", "lower_hue")
    path.write_text("| Result | pass |\n")
    with pytest.raises(SystemExit, match="no Device row"):
        gc.models(path)


def test_a_passing_record_on_a_released_adapter_is_verified(root):
    record(root, "zha", "stop")
    record(root, "zha", "stop-predicted_state", device="Zone, firmware `unknown`")
    line = gc.row("stop", adapter("zha", "stop"))
    assert line.startswith("| `stop` | Verified | `LTA009`, firmware `1.2.3`<br>group |")
    assert "[predicted state](test-records/zha/stop-predicted_state.md)" in line
    assert "[record](test-records/zha/stop.md)" in line


def test_an_experimental_adapter_or_a_failing_record_is_experimental(root):
    record(root, "zha", "stop")
    record(root, "hue", "stop", result="fail")
    assert "| Experimental |" in gc.row("stop", adapter("zha", "stop", experimental=True))
    line = gc.row("stop", adapter("hue", "stop"))
    assert line.startswith("| `stop` | Experimental | none |  | |")


def test_the_page_groups_by_integration_title_and_skips_unsupported_pairs(root):
    record(root, "zha", "stop")
    text = gc.generate(FakeRegistry(adapter("zha", "stop"), adapter("hue", "lower_hue")))
    assert text.index("## Hue") < text.index("## ZHA")
    assert "`lower_hue` | Experimental" in text
    assert text.count("`stop`") == 1


def test_check_fails_on_a_stale_page_until_it_is_regenerated(root, capsys):
    path = root / "docs" / "compatibility.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    registry = FakeRegistry(adapter("zha", "stop"))
    device = record(root, "zha", "stop")
    assert gc.main(["--check"], registry, path) == 1  # no page yet
    assert gc.main([], registry, path) == 0
    assert gc.main(["--check"], registry, path) == 0
    device.write_text(device.read_text().replace("1.2.3", "9.9.9"))
    assert gc.main(["--check"], registry, path) == 1
    assert "out of date" in capsys.readouterr().err
    assert gc.main([], registry, path) == 0
    assert "9.9.9" in path.read_text()
    assert gc.main(["--check"], registry, path) == 0
