"""Shared fixtures for parlot-core tests."""

from __future__ import annotations

import pytest

from parlot.core.ingest_gate import reset_parlot_ingest_gate_for_tests
from parlot.core.otlp_quota import reset_parlot_quota_log_for_tests


@pytest.fixture(autouse=True)
def _reset_parlot_ingest_gate() -> None:
    """Keep the process-wide free-plan ingest latch from leaking across tests."""
    reset_parlot_ingest_gate_for_tests()
    reset_parlot_quota_log_for_tests()
    yield
    reset_parlot_ingest_gate_for_tests()
    reset_parlot_quota_log_for_tests()
