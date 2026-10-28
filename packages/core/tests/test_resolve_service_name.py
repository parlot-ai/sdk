"""Tests for OTel service.name resolution."""

from __future__ import annotations

from opentelemetry.semconv.attributes import service_attributes

from parlot.core.provider import build_resource, resolve_service_name


def test_resolve_service_name_prefers_explicit():
    assert resolve_service_name("custom", agent_id="agent-a") == "custom"


def test_resolve_service_name_falls_back_to_agent_id():
    assert resolve_service_name(None, agent_id="hotel-receptionist") == (
        "hotel-receptionist"
    )
    assert resolve_service_name("  ", agent_id="hotel-receptionist") == (
        "hotel-receptionist"
    )


def test_resolve_service_name_unknown_when_empty():
    assert resolve_service_name(None, agent_id="") == "unknown"
    assert resolve_service_name("", agent_id="  ") == "unknown"


def test_build_resource_defaults_service_name_to_agent_id():
    resource = build_resource(agent_id="hotel-receptionist")
    assert resource.attributes[service_attributes.SERVICE_NAME] == (
        "hotel-receptionist"
    )
