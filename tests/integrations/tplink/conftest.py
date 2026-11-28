from ...conftest import unload_mock_entries

# python-kasa stays out of the test environment on purpose: the integration must load without it.
unload_mock_tplink_entries = unload_mock_entries("tplink")
