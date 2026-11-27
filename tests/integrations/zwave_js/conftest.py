from ...conftest import unload_mock_entries
from ...fixtures.zwave_js import mock_zwave_js_server  # noqa: F401 - re-exported as an autouse fixture

unload_mock_zwave_js_entries = unload_mock_entries("zwave_js")
