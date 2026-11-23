"""The shared audit event keeps its public name and import path in its own module."""

from __future__ import annotations

from pydantic.json_schema import models_json_schema

from qdash.api.schemas import agent_session, audit, calibration_session


def test_agent_session_module_re_exports_the_shared_event() -> None:
    assert agent_session.AgentAuditEvent is audit.AgentAuditEvent


def test_both_audit_responses_use_one_event_component() -> None:
    _, schema = models_json_schema(
        [
            (agent_session.AgentSessionAuditResponse, "serialization"),
            (calibration_session.CalibrationSessionAuditResponse, "serialization"),
        ],
        ref_template="#/components/schemas/{model}",
    )
    defs = schema["$defs"]
    assert "AgentAuditEvent" in defs
    assert not [name for name in defs if name != "AgentAuditEvent" and "AuditEvent" in name]
    event_ref = {"$ref": "#/components/schemas/AgentAuditEvent"}
    for response in ("AgentSessionAuditResponse", "CalibrationSessionAuditResponse"):
        assert defs[response]["properties"]["events"]["items"] == event_ref
