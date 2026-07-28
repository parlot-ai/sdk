"""Tests for parlot-core SDK version resolution and session stamping."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from importlib import metadata

from parlot.core.attrs import ATTR_PARLOT_SDK_VERSION
from parlot.core import sdk_version as sdk_version_mod
from parlot.core.sdk_version import (
    resolve_parlot_sdk_version,
    stamp_session_sdk_version,
)


@pytest.fixture(autouse=True)
def _reset_sdk_version_cache():
    sdk_version_mod._cached_version = None
    yield
    sdk_version_mod._cached_version = None


def test_resolve_reads_parlot_core_metadata():
    with patch.object(metadata, "version", return_value="0.1.0"):
        assert resolve_parlot_sdk_version() == "0.1.0"


def test_resolve_caches_after_first_call():
    with patch.object(metadata, "version", return_value="1.2.3") as version_mock:
        assert resolve_parlot_sdk_version() == "1.2.3"
        assert resolve_parlot_sdk_version() == "1.2.3"
        version_mock.assert_called_once_with("parlot-core")


def test_resolve_returns_empty_when_package_missing():
    with patch.object(
        metadata,
        "version",
        side_effect=metadata.PackageNotFoundError("parlot-core"),
    ):
        assert resolve_parlot_sdk_version() == ""


def test_resolve_truncates_long_version():
    with patch.object(metadata, "version", return_value="x" * 100):
        assert len(resolve_parlot_sdk_version()) == 64


def test_stamp_session_sdk_version_sets_attr():
    span = SimpleNamespace(attributes={})

    def set_attribute(key, value):
        span.attributes[key] = value

    span.set_attribute = set_attribute

    with patch.object(metadata, "version", return_value="0.1.0"):
        stamp_session_sdk_version(span)

    assert span.attributes[ATTR_PARLOT_SDK_VERSION] == "0.1.0"


def test_stamp_session_sdk_version_skips_when_unresolved():
    span = SimpleNamespace(attributes={})

    def set_attribute(key, value):
        span.attributes[key] = value

    span.set_attribute = set_attribute

    with patch.object(
        metadata,
        "version",
        side_effect=metadata.PackageNotFoundError("parlot-core"),
    ):
        stamp_session_sdk_version(span)

    assert ATTR_PARLOT_SDK_VERSION not in span.attributes
