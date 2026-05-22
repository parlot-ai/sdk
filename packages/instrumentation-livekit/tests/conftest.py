"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from parlot.instrumentation.livekit._session import _parlot_job_bootstrap


@pytest.fixture(autouse=True)
def reset_job_bootstrap_context() -> Iterator[None]:
    """Isolate ContextVar bootstrap state between tests."""
    _parlot_job_bootstrap.set(None)
    yield
    _parlot_job_bootstrap.set(None)
