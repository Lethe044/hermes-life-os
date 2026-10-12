"""Shared pytest setup."""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_day_start(monkeypatch):
    """A LIFE_OS_DAY_START_HOUR set in the developer's own shell would shift
    "today" for every test; tests that care set it themselves."""
    monkeypatch.delenv("LIFE_OS_DAY_START_HOUR", raising=False)
