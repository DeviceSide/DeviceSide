import pytest
from homeassistant.util import dt as dt_util

from ...conftest import unload_mock_entries
from ...fixtures.matter import (
    NOW,
    mock_chip,  # noqa: F401 - re-exported as a fixture
)

unload_mock_matter_entries = unload_mock_entries("matter")


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(dt_util, "utcnow", lambda: NOW)
