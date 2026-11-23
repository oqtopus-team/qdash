"""The calibration session audit module keeps its public import surface.

Routers and the calibration session service import the audit from
``qdash.api.services.calibration_session_audit``; those names stay importable there.
"""

from __future__ import annotations

import pytest

from qdash.api.services import calibration_session_audit


def test_audit_service_exposes_its_public_operations() -> None:
    service = calibration_session_audit.CalibrationSessionAuditService()
    for operation in (
        "record_decision",
        "list_decisions",
        "search",
        "timeline",
        "read_audit",
        "export_audit",
    ):
        assert callable(getattr(service, operation))


@pytest.mark.parametrize("name", calibration_session_audit.__all__)
def test_public_names_stay_importable(name: str) -> None:
    assert getattr(calibration_session_audit, name) is not None


def test_public_constants_keep_their_values() -> None:
    assert calibration_session_audit.MAX_DECISIONS_PER_SESSION == 2000
    assert calibration_session_audit.MAX_DETAIL_DECISIONS == 200
    assert calibration_session_audit.MAX_TASKS_PER_EVENT == 100
    assert calibration_session_audit.MAX_SNAPSHOT_TASKS == 50
    assert {"check_run_decision", "SearchView", "requested_task_calls"} <= set(
        calibration_session_audit.__all__
    )
