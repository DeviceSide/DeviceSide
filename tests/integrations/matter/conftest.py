from ...conftest import unload_mock_entries
from ...fixtures.matter import mock_chip  # noqa: F401 - re-exported as a fixture

unload_mock_matter_entries = unload_mock_entries("matter")
