"""Pytest config. Integration tests (live DB) are skipped unless RUN_INTEGRATION=1,
so the default validation gate stays infra-free and deterministic.
"""
from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_INTEGRATION") == "1":
        return
    skip_integration = pytest.mark.skip(reason="set RUN_INTEGRATION=1 to run live-DB tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
