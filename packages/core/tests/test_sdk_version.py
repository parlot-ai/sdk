"""Tests for parlot-core SDK version resolution, session stamping, and client transport headers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from importlib import metadata

from parlot.core.attrs import ATTR_PARLOT_SDK_VERSION, ATTR_SESSION_METADATA_SDK_VERSION
from parlot.core import sdk_version as sdk_version_mod
from parlot.core.sdk_version import (
    resolve_parlot_sdk_version,
    stamp_session_sdk_version,
)
from parlot.core.provider import (
    HEADER_SDK_NAME,
    HEADER_SDK_VERSION,
    HEADER_INGESTION_VERSION,
    INGESTION_PROTOCOL_VERSION,
    build_parlot_client_headers,
    build_otlp_http_exporter,
)
from parlot.core.session import SessionState, set_active_session, clear_active_session


@pytest.fixture(autouse=True)
def _reset_sdk_version_cache():
    sdk_version_mod._cached_version = None
    clear_active_session()
    yield
    sdk_version_mod._cached_version = None
    clear_active_session()


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


def test_stamp_session_sdk_version_sets_attrs_and_state_metadata():
    span = SimpleNamespace(attributes={})

    def set_attribute(key, value):
        span.attributes[key] = value

    span.set_attribute = set_attribute
    state = SessionState(session_id="sess-1")
    set_active_session(span, state)

    with patch.object(metadata, "version", return_value="0.2.0"):
        stamp_session_sdk_version(span)

    assert span.attributes[ATTR_PARLOT_SDK_VERSION] == "0.2.0"
    assert span.attributes[ATTR_SESSION_METADATA_SDK_VERSION] == "0.2.0"
    assert state.custom_metadata[ATTR_SESSION_METADATA_SDK_VERSION] == "0.2.0"


def test_stamp_session_sdk_version_supports_dict_span():
    attrs: dict[str, str] = {}
    with patch.object(metadata, "version", return_value="0.2.0"):
        stamp_session_sdk_version(attrs)

    assert attrs[ATTR_PARLOT_SDK_VERSION] == "0.2.0"
    assert attrs[ATTR_SESSION_METADATA_SDK_VERSION] == "0.2.0"


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
    assert ATTR_SESSION_METADATA_SDK_VERSION not in span.attributes


def test_build_parlot_client_headers():
    with patch.object(metadata, "version", return_value="0.3.5"):
        headers = build_parlot_client_headers("test-api-key")

    assert headers[HEADER_SDK_NAME] == "parlot-python"
    assert headers[HEADER_SDK_VERSION] == "0.3.5"
    assert headers[HEADER_INGESTION_VERSION] == INGESTION_PROTOCOL_VERSION
    assert headers["Authorization"] == "Bearer test-api-key"


def test_build_parlot_client_headers_without_api_key():
    with patch.object(metadata, "version", side_effect=metadata.PackageNotFoundError("parlot-core")):
        headers = build_parlot_client_headers()

    assert headers[HEADER_SDK_NAME] == "parlot-python"
    assert headers[HEADER_SDK_VERSION] == "unknown"
    assert headers[HEADER_INGESTION_VERSION] == "1"
    assert "Authorization" not in headers


def test_build_otlp_http_exporter_includes_headers():
    with patch.object(metadata, "version", return_value="0.4.0"):
        exporter = build_otlp_http_exporter(
            endpoint="http://localhost:8787",
            api_key="secret-key",
        )

    assert exporter._headers[HEADER_SDK_NAME] == "parlot-python"
    assert exporter._headers[HEADER_SDK_VERSION] == "0.4.0"
    assert exporter._headers[HEADER_INGESTION_VERSION] == "1"
    assert exporter._headers["Authorization"] == "Bearer secret-key"
