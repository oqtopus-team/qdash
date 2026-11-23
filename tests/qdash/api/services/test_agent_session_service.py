"""Tests for policy-governed local agent sessions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from qdash.api.services.flow_service import FlowService
    from qdash.api.services.task_file_service import TaskFileService
from fastapi import HTTPException
from pydantic import ValidationError

from qdash.api.schemas.agent_session import (
    AgentCandidateReference,
    AgentCandidateResponse,
    ApplyAgentCandidateRequest,
    CommitAgentCandidateRequest,
    CommitAgentCandidateSetRequest,
    CreateAgentSessionRequest,
    EvaluateCandidateGateRequest,
    ExecuteAgentActionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.schemas.task_file import ListTaskInfoResponse, TaskInfo
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentModelIdentity,
    AgentSessionPolicy,
    NumericBounds,
)
from qdash.datamodel.calibration_session import (
    CalibrationPipelineRunStatus,
    CalibrationRunIdentity,
    CalibrationRunKind,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentActionDocument, AgentSessionDocument
from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from tests.qdash.api._legacy_records import make_standalone_agent_session


@pytest.fixture
def service(init_db) -> AgentSessionService:
    """Create a service with a chip in the active test database."""
    ChipDocument(
        project_id="project-1",
        chip_id="chip-001",
        username="tester",
        size=4,
        system_info=SystemInfoModel(),
    ).insert()
    QubitDocument(
        project_id="project-1",
        username="tester",
        qid="Q00",
        chip_id="chip-001",
        data={},
        system_info=SystemInfoModel(),
    ).insert()
    return AgentSessionService()


def _create_session(
    service: AgentSessionService,
    *,
    max_actions: int = 10,
    quality_gates: dict[str, NumericBounds] | None = None,
    task_quality_gates: dict[str, dict[str, NumericBounds]] | None = None,
    allowed_tasks: list[str] | None = None,
    allowed_overrides: dict[str, NumericBounds] | None = None,
):
    """Create a session; ``quality_gates`` stores legacy session-wide gates on the record.

    New sessions cannot request session-wide gates, so a test of their legacy meaning writes
    them to the stored policy the way a session approved before task gates holds them.
    """
    session = service.create_session(
        project_id="project-1",
        username="tester",
        body=CreateAgentSessionRequest(
            chip_id="chip-001",
            policy=AgentSessionPolicy(
                qids=["Q00", "Q01"],
                allowed_tasks=allowed_tasks or ["CheckQubitSpectroscopy"],
                allowed_overrides=allowed_overrides
                or {
                    "drive_amplitude": NumericBounds(minimum=0.01, maximum=0.2),
                    "qubit_frequency": NumericBounds(minimum=3.0, maximum=6.0),
                },
                task_quality_gates=task_quality_gates or {},
                max_actions=max_actions,
            ),
            skill_name="single-qubit-bringup",
            skill_version="1",
            skill_hash="sha256:test",
            model=AgentModelIdentity(provider="local", model_id="local-model"),
        ),
    )
    if quality_gates:
        _store_legacy_quality_gates(session.session_id, quality_gates)
    return service.get_session(project_id="project-1", session_id=session.session_id)


def _store_legacy_quality_gates(session_id: str, gates: dict[str, NumericBounds]) -> None:
    doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert doc is not None
    doc.policy = doc.policy.model_copy(update={"quality_gates": gates})
    doc.save()


def _run_task_action(
    *,
    idempotency_key: str = "action-1",
    expected_state_version: int = 0,
    qids: list[str] | None = None,
    task_name: str = "CheckQubitSpectroscopy",
    drive_amplitude: float = 0.1,
) -> SubmitAgentActionRequest:
    return SubmitAgentActionRequest(
        idempotency_key=idempotency_key,
        expected_state_version=expected_state_version,
        action_type=AgentActionType.RUN_TASK,
        task_name=task_name,
        qids=qids or ["Q00"],
        parameter_overrides={"drive_amplitude": drive_amplitude},
        diagnosis="No f01 candidate was found.",
    )


def _catalog(monkeypatch: pytest.MonkeyPatch) -> TaskFileService:
    """A task catalog holding the task the agent actions run."""
    monkeypatch.setattr("qdash.api.services.catalog_task_run.get_default_backend", lambda: "qubex")
    monkeypatch.setattr(
        "qdash.api.services.catalog_task_run.get_available_backends", lambda: ["qubex"]
    )
    monkeypatch.setattr(
        "qdash.api.services.catalog_task_run.is_task_available", lambda *_args: True
    )
    task = TaskInfo(
        name="CheckQubitSpectroscopy",
        class_name="CheckQubitSpectroscopy",
        task_type="qubit",
        file_path="qubex/check_qubit_spectroscopy.py",
        input_parameters={
            "drive_amplitude": {"user_override": "allowed", "value_type": "float"},
            "shots": {"user_override": "allowed", "value_type": "int"},
            "qubit_frequency": {"user_override": "forbidden", "value_type": "float"},
        },
        run_parameters={"readout_duration": {"value_type": "float"}},
    )
    return cast(
        "TaskFileService",
        SimpleNamespace(
            list_task_info=lambda *_args, **_kwargs: ListTaskInfoResponse(tasks=[task])
        ),
    )


def test_create_session_persists_bounded_scope(service: AgentSessionService) -> None:
    """Creating a session preserves the approved scope and starts at version zero."""
    session = _create_session(service)

    assert session.project_id == "project-1"
    assert session.chip_id == "chip-001"
    assert session.policy.qids == ["Q00", "Q01"]
    assert session.state_version == 0
    assert session.action_count == 0
    assert session.status.value == "active"


def test_submit_action_authorizes_allowed_task(service: AgentSessionService) -> None:
    """An in-scope proposal is authorized but explicitly remains unexecuted."""
    session = _create_session(service)

    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    updated = service.get_session(project_id="project-1", session_id=session.session_id)

    assert action.decision == AgentActionDecision.AUTHORIZED
    assert action.execution_status == "not_started"
    assert action.state_version_before == 0
    assert action.state_version_after == 1
    assert updated.state_version == 1
    assert updated.action_count == 1


def test_get_action_resolves_actions_that_stored_the_qdash_execution_id(
    service: AgentSessionService,
) -> None:
    """Actions dispatched before the fix kept the QDash execution ID as operation_id."""
    session = _create_session(service)
    submitted = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    action = AgentActionDocument.find_one({"action_id": submitted.action_id}).run()
    assert action is not None
    action.operation_id = "20260713-001"
    action.execution_status = "queued"
    action.save()
    ExecutionHistoryDocument(
        project_id="project-1",
        username="tester",
        name="agent execution",
        execution_id="20260713-001",
        calib_data_path="",
        note={"flow_run_id": "prefect-flow-run-1"},
        status="completed",
        tags=[],
        chip_id="chip-001",
        message="",
        system_info=SystemInfoModel(),
    ).insert()

    resolved = service.get_action(
        project_id="project-1",
        session_id=session.session_id,
        action_id=submitted.action_id,
    )

    assert resolved.execution_id == "20260713-001"
    assert resolved.execution_status == "completed"


def test_get_action_resolves_prefect_operation_to_qdash_execution(
    service: AgentSessionService,
) -> None:
    """Agent audit keeps Prefect and QDash identifiers as separate fields."""
    session = _create_session(service)
    submitted = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    action = AgentActionDocument.find_one({"action_id": submitted.action_id}).run()
    assert action is not None
    action.operation_id = "prefect-flow-run-1"
    action.execution_status = "queued"
    action.save()
    ExecutionHistoryDocument(
        project_id="project-1",
        username="tester",
        name="agent execution",
        execution_id="20260713-001",
        calib_data_path="",
        note={"flow_run_id": "prefect-flow-run-1"},
        status="completed",
        tags=[],
        chip_id="chip-001",
        message="",
        system_info=SystemInfoModel(),
    ).insert()

    resolved = service.get_action(
        project_id="project-1",
        session_id=session.session_id,
        action_id=submitted.action_id,
    )

    assert resolved.operation_id == "prefect-flow-run-1"
    assert resolved.execution_id == "20260713-001"
    assert resolved.execution_status == "completed"


@pytest.mark.parametrize(
    ("value", "accepted", "reason"),
    [
        (0.01, True, "passed deterministic bounds gate"),
        (0.2, True, "passed deterministic bounds gate"),
        (0.009, False, "below the minimum bound"),
        (0.201, False, "above the maximum bound"),
    ],
)
def test_candidate_gate_uses_session_bounds_without_mutating_state(
    service: AgentSessionService,
    value: float,
    accepted: bool,
    reason: str,
) -> None:
    """Candidate evaluation uses policy bounds and does not consume session state."""
    session = _create_session(service)

    result = service.evaluate_candidate_gate(
        project_id="project-1",
        session_id=session.session_id,
        body=EvaluateCandidateGateRequest(
            parameter_name="drive_amplitude",
            value=value,
        ),
    )
    unchanged = service.get_session(project_id="project-1", session_id=session.session_id)

    assert result.accepted is accepted
    assert reason in result.reason
    assert result.minimum == 0.01
    assert result.maximum == 0.2
    assert unchanged.state_version == 0
    assert unchanged.action_count == 0


def test_candidate_gate_rejects_parameter_outside_session_policy(
    service: AgentSessionService,
) -> None:
    """A candidate cannot select a parameter absent from the server-side policy."""
    session = _create_session(service)

    result = service.evaluate_candidate_gate(
        project_id="project-1",
        session_id=session.session_id,
        body=EvaluateCandidateGateRequest(parameter_name="frequency", value=5.0),
    )

    assert not result.accepted
    assert "not allowed by the session policy" in result.reason
    assert result.minimum is None
    assert result.maximum is None


def test_candidate_gate_request_rejects_non_finite_value() -> None:
    """Non-finite candidates are rejected before an unsafe JSON response can be produced."""
    with pytest.raises(ValidationError):
        EvaluateCandidateGateRequest(
            parameter_name="drive_amplitude",
            value=float("nan"),
        )


def _attach_completed_task_result(
    *,
    session_id: str,
    action_id: str,
    output_parameters: dict[str, object],
    quality_metrics: dict[str, float] | None = None,
    sequence: int = 1,
    task_name: str = "CheckQubitSpectroscopy",
) -> None:
    action = AgentActionDocument.find_one({"session_id": session_id, "action_id": action_id}).run()
    assert action is not None
    action.operation_id = f"operation-{sequence}"
    action.execution_id = f"execution-{sequence}"
    action.execution_status = "completed"
    action.save()

    TaskResultHistoryDocument(
        project_id="project-1",
        username="tester",
        task_id=f"task-result-{sequence}",
        name=task_name,
        upstream_id="",
        status="completed",
        message="completed",
        input_parameters={},
        output_parameters=output_parameters,
        output_parameter_names=list(output_parameters),
        run_parameters={},
        quality_metrics=quality_metrics or {},
        note={},
        figure_path=[],
        json_figure_path=[],
        raw_data_path=[],
        start_at=None,
        end_at=None,
        elapsed_time=None,
        task_type="qubit",
        system_info=SystemInfoModel(),
        qid="Q00",
        execution_id=f"execution-{sequence}",
        tags=["agent-session:" + session_id],
        chip_id="chip-001",
    ).insert()


def test_list_action_candidates_uses_authoritative_task_result(
    service: AgentSessionService,
) -> None:
    """Candidate values and provenance come from the dispatched task result."""
    session = _create_session(service)
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=action.action_id,
        output_parameters={
            "drive_amplitude": {
                "parameter_name": "drive_amplitude",
                "value": 0.12,
                "error": 0.01,
                "unit": "a.u.",
            },
            "diagnostic_score": {"value": 0.99},
            "label": "ignored",
        },
    )

    candidates = service.list_action_candidates(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
    )
    unchanged = service.get_session(project_id="project-1", session_id=session.session_id)

    assert candidates.total == 2
    drive = next(item for item in candidates.items if item.parameter_name == "drive_amplitude")
    assert drive.accepted
    assert drive.value == 0.12
    assert drive.error == 0.01
    assert drive.unit == "a.u."
    assert drive.execution_id == "execution-1"
    assert drive.task_id == "task-result-1"
    diagnostic = next(
        item for item in candidates.items if item.parameter_name == "diagnostic_score"
    )
    assert not diagnostic.accepted
    assert "not allowed" in diagnostic.reason
    assert unchanged.state_version == 1
    assert unchanged.action_count == 1


@pytest.mark.parametrize(
    ("quality_metrics", "accepted", "reason"),
    [
        ({"r2": 0.95}, True, "quality gates"),
        ({"r2": 0.85}, False, "below the minimum bound"),
        ({}, False, "is missing"),
    ],
)
def test_list_action_candidates_applies_session_quality_gates(
    service: AgentSessionService,
    quality_metrics: dict[str, float],
    accepted: bool,
    reason: str,
) -> None:
    """Server-owned result quality must pass in addition to candidate bounds."""
    session = _create_session(
        service,
        quality_gates={"r2": NumericBounds(minimum=0.9)},
    )
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=action.action_id,
        output_parameters={"drive_amplitude": {"value": 0.12}},
        quality_metrics=quality_metrics,
    )

    candidate = service.list_action_candidates(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
    ).items[0]

    assert candidate.accepted is accepted
    assert reason in candidate.reason
    assert candidate.quality_metrics == quality_metrics


def _run_without_overrides(task_name: str, key: str, version: int) -> SubmitAgentActionRequest:
    return SubmitAgentActionRequest(
        idempotency_key=key,
        expected_state_version=version,
        action_type=AgentActionType.RUN_TASK,
        task_name=task_name,
        qids=["Q00"],
    )


RABI_AND_RB = ["CheckRabi", "RandomizedBenchmarking"]
RABI_AND_RB_BOUNDS = {
    "maximum_rabi_frequency": NumericBounds(minimum=2000.0, maximum=3000.0),
    "average_gate_fidelity": NumericBounds(minimum=0.9, maximum=1.0),
}


def _measure_rabi_and_rb(
    service: AgentSessionService,
    session_id: str,
    *,
    rabi_metrics: dict[str, float],
    rb_metrics: dict[str, float],
) -> tuple[AgentCandidateResponse, AgentCandidateResponse]:
    rabi = service.submit_action(
        project_id="project-1",
        session_id=session_id,
        body=_run_without_overrides("CheckRabi", "rabi", 0),
    )
    _attach_completed_task_result(
        session_id=session_id,
        action_id=rabi.action_id,
        output_parameters={"maximum_rabi_frequency": {"value": 2681.29}},
        quality_metrics=rabi_metrics,
        task_name="CheckRabi",
    )
    rb = service.submit_action(
        project_id="project-1",
        session_id=session_id,
        body=_run_without_overrides("RandomizedBenchmarking", "rb", 1),
    )
    _attach_completed_task_result(
        session_id=session_id,
        action_id=rb.action_id,
        output_parameters={"average_gate_fidelity": {"value": 0.995}},
        quality_metrics=rb_metrics,
        sequence=2,
        task_name="RandomizedBenchmarking",
    )

    def only(action_id: str) -> AgentCandidateResponse:
        items = service.list_action_candidates(
            project_id="project-1", session_id=session_id, action_id=action_id
        ).items
        assert len(items) == 1
        return items[0]

    return only(rabi.action_id), only(rb.action_id)


def test_task_quality_gate_checks_only_its_own_task(service: AgentSessionService) -> None:
    """A gate of RandomizedBenchmarking neither rejects nor annotates a CheckRabi result."""
    session = _create_session(
        service,
        allowed_tasks=RABI_AND_RB,
        allowed_overrides=RABI_AND_RB_BOUNDS,
        task_quality_gates={"RandomizedBenchmarking": {"r2": NumericBounds(minimum=0.9)}},
    )
    rabi, rb = _measure_rabi_and_rb(
        service, session.session_id, rabi_metrics={"r2": 0.99723}, rb_metrics={"r2": 0.95}
    )

    assert rabi.accepted, rabi.reason
    assert rabi.applied_quality_gates == []
    assert rabi.reason == "candidate passed deterministic bounds gate"
    assert rb.accepted, rb.reason
    assert [
        (g.metric_name, g.scope.value, g.task_name, g.minimum) for g in rb.applied_quality_gates
    ] == [("r2", "task", "RandomizedBenchmarking", 0.9)]
    assert rb.reason == "candidate passed deterministic bounds and quality gates"


def test_missing_metric_of_an_applicable_task_gate_still_rejects(
    service: AgentSessionService,
) -> None:
    """A task gate fails closed when its own task's result lacks the metric."""
    session = _create_session(
        service,
        allowed_tasks=RABI_AND_RB,
        allowed_overrides=RABI_AND_RB_BOUNDS,
        task_quality_gates={
            "CheckRabi": {"r2": NumericBounds(minimum=0.98)},
            "RandomizedBenchmarking": {"r2": NumericBounds(minimum=0.9)},
        },
    )
    rabi, rb = _measure_rabi_and_rb(
        service, session.session_id, rabi_metrics={"r2": 0.97}, rb_metrics={}
    )

    assert not rabi.accepted
    assert rabi.reason == (
        "Quality metric 'r2' for task 'CheckRabi' candidate is below the minimum bound"
    )
    assert not rb.accepted
    assert rb.reason == (
        "Required quality metric 'r2' for task 'RandomizedBenchmarking' is missing"
    )


def test_legacy_session_wide_gate_keeps_its_approved_meaning(
    service: AgentSessionService,
) -> None:
    """A stored session-wide gate is neither loosened nor narrowed to one task."""
    session = _create_session(
        service,
        allowed_tasks=RABI_AND_RB,
        allowed_overrides=RABI_AND_RB_BOUNDS,
        quality_gates={"average_gate_fidelity": NumericBounds(minimum=0.99)},
    )
    assert session.policy.quality_gates == {"average_gate_fidelity": NumericBounds(minimum=0.99)}
    assert session.policy.task_quality_gates == {}
    rabi, rb = _measure_rabi_and_rb(
        service, session.session_id, rabi_metrics={"r2": 0.99723}, rb_metrics={"r2": 0.95}
    )

    for candidate in (rabi, rb):
        assert not candidate.accepted
        assert candidate.reason == (
            "Required quality metric 'average_gate_fidelity' by the session-wide gate is missing"
        )
        assert [(g.scope.value, g.task_name) for g in candidate.applied_quality_gates] == [
            ("all_tasks", None)
        ]


def _create_request(policy: dict[str, object]) -> CreateAgentSessionRequest:
    return CreateAgentSessionRequest.model_validate(
        {
            "chip_id": "chip-001",
            "policy": {
                "qids": ["Q00"],
                "allowed_tasks": RABI_AND_RB,
                "allowed_overrides": {"maximum_rabi_frequency": {"minimum": 2000, "maximum": 3000}},
                **policy,
            },
        }
    )


def test_new_session_rejects_a_session_wide_quality_gate() -> None:
    """Creation refuses a gate that would check every task, before anything is stored."""
    with pytest.raises(ValidationError) as caught:
        _create_request({"quality_gates": {"average_gate_fidelity": {"minimum": 0.99}}})

    message = str(caught.value)
    assert "would check results of every task" in message
    assert "task_quality_gates" in message


@pytest.mark.parametrize(
    ("gates", "expected"),
    [
        (
            {"CheckRabi": {"average_gate_fidelity": {"minimum": 0.99}}},
            "does not record as a quality metric (recorded: r2)",
        ),
        (
            {"CheckT1": {"r2": {"minimum": 0.9}}},
            "task_quality_gates tasks must be allowed tasks: CheckT1",
        ),
        ({"CheckRabi": {}}, "needs at least one metric for: CheckRabi"),
    ],
)
def test_new_session_rejects_impossible_task_quality_gates(
    gates: dict[str, object], expected: str
) -> None:
    """A gate on an output parameter, an unscoped task, or no metric is refused up front."""
    with pytest.raises(ValidationError) as caught:
        _create_request({"task_quality_gates": gates})

    assert expected in str(caught.value)


def test_new_session_stores_task_quality_gates(service: AgentSessionService) -> None:
    """A valid task-scoped gate is stored as approved and read back unchanged."""
    session = service.create_session(
        project_id="project-1",
        username="tester",
        body=_create_request({"task_quality_gates": {"CheckRabi": {"r2": {"minimum": 0.9}}}}),
    )

    assert session.policy.task_quality_gates == {"CheckRabi": {"r2": NumericBounds(minimum=0.9)}}
    assert session.policy.quality_gates == {}


def test_commit_action_candidate_revalidates_and_audits_parameter_write(
    service: AgentSessionService,
) -> None:
    """A gated task-result candidate is committed once with before/after snapshots."""
    session = _create_session(service, max_actions=1)
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=action.action_id,
        output_parameters={
            "drive_amplitude": {
                "value": 0.12,
                "error": 0.01,
                "unit": "a.u.",
            }
        },
    )
    body = CommitAgentCandidateRequest(
        idempotency_key="commit-1",
        expected_state_version=1,
        task_id="task-result-1",
    )

    committed = service.commit_action_candidate(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
        parameter_name="drive_amplitude",
        username="reviewer",
        body=body,
    )
    retried = service.commit_action_candidate(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
        parameter_name="drive_amplitude",
        username="reviewer",
        body=body,
    )
    updated_session = service.get_session(
        project_id="project-1",
        session_id=session.session_id,
    )
    qubit = QubitDocument.find_one(
        {"project_id": "project-1", "chip_id": "chip-001", "qid": "Q00"}
    ).run()

    assert committed.status == "committed"
    assert committed.before_snapshot is None
    assert committed.after_snapshot is not None
    assert committed.after_snapshot["value"] == 0.12
    assert committed.execution_id == "execution-1"
    assert committed.task_id == "task-result-1"
    assert committed.committed_by == "reviewer"
    assert retried.commit_id == committed.commit_id
    assert updated_session.state_version == 2
    assert updated_session.action_count == 1
    assert qubit is not None
    assert qubit.data["drive_amplitude"]["value"] == 0.12
    assert qubit.data["drive_amplitude"]["execution_id"] == "execution-1"


def test_commit_candidate_set_updates_final_set_once(
    service: AgentSessionService,
) -> None:
    """All accepted final candidates are persisted in one audited candidate set commit."""
    session = _create_session(service, max_actions=2)
    first = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    second = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(idempotency_key="action-2", expected_state_version=1),
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=first.action_id,
        output_parameters={"drive_amplitude": {"value": 0.12, "unit": "a.u."}},
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=second.action_id,
        output_parameters={"qubit_frequency": {"value": 4.8, "unit": "GHz"}},
        sequence=2,
    )
    body = CommitAgentCandidateSetRequest(
        idempotency_key="candidate-set-commit-1",
        expected_state_version=2,
        candidates=[
            AgentCandidateReference(
                action_id=first.action_id,
                parameter_name="drive_amplitude",
                task_id="task-result-1",
            ),
            AgentCandidateReference(
                action_id=second.action_id,
                parameter_name="qubit_frequency",
                task_id="task-result-2",
            ),
        ],
    )

    committed = service.commit_candidate_set(
        project_id="project-1",
        session_id=session.session_id,
        username="reviewer",
        body=body,
    )
    retried = service.commit_candidate_set(
        project_id="project-1",
        session_id=session.session_id,
        username="reviewer",
        body=body,
    )
    updated_session = service.get_session(
        project_id="project-1",
        session_id=session.session_id,
    )
    qubit = QubitDocument.find_one(
        {"project_id": "project-1", "chip_id": "chip-001", "qid": "Q00"}
    ).run()

    assert committed.status == "committed"
    assert retried.commit_id == committed.commit_id
    assert [candidate.parameter_name for candidate in committed.candidates] == [
        "drive_amplitude",
        "qubit_frequency",
    ]
    assert committed.before_snapshot == {
        "drive_amplitude": None,
        "qubit_frequency": None,
    }
    drive_snapshot = cast("dict[str, object]", committed.after_snapshot["drive_amplitude"])
    frequency_snapshot = cast("dict[str, object]", committed.after_snapshot["qubit_frequency"])
    assert drive_snapshot["value"] == 0.12
    assert frequency_snapshot["value"] == 4.8
    assert updated_session.state_version == 3
    assert qubit is not None
    assert qubit.data["drive_amplitude"]["value"] == 0.12
    assert qubit.data["qubit_frequency"]["value"] == 4.8


def test_commit_candidate_set_rejects_set_before_any_write(
    service: AgentSessionService,
) -> None:
    """One rejected candidate prevents the complete final set from being persisted."""
    session = _create_session(service, max_actions=2)
    first = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    second = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(idempotency_key="action-2", expected_state_version=1),
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=first.action_id,
        output_parameters={"drive_amplitude": {"value": 0.12}},
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=second.action_id,
        output_parameters={"qubit_frequency": {"value": 8.0}},
        sequence=2,
    )

    with pytest.raises(HTTPException) as exc_info:
        service.commit_candidate_set(
            project_id="project-1",
            session_id=session.session_id,
            username="reviewer",
            body=CommitAgentCandidateSetRequest(
                idempotency_key="candidate-set-commit-rejected",
                expected_state_version=2,
                candidates=[
                    AgentCandidateReference(
                        action_id=first.action_id,
                        parameter_name="drive_amplitude",
                        task_id="task-result-1",
                    ),
                    AgentCandidateReference(
                        action_id=second.action_id,
                        parameter_name="qubit_frequency",
                        task_id="task-result-2",
                    ),
                ],
            ),
        )

    unchanged = service.get_session(project_id="project-1", session_id=session.session_id)
    qubit = QubitDocument.find_one(
        {"project_id": "project-1", "chip_id": "chip-001", "qid": "Q00"}
    ).run()
    assert exc_info.value.status_code == 409
    assert unchanged.state_version == 2
    assert qubit is not None
    assert "drive_amplitude" not in qubit.data
    assert "qubit_frequency" not in qubit.data


@pytest.mark.asyncio
async def test_apply_candidate_to_backend_dispatches_once(
    service: AgentSessionService,
) -> None:
    """A committed candidate is idempotently dispatched to the worker apply flow."""
    session = _create_session(service)
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=action.action_id,
        output_parameters={"drive_amplitude": {"value": 0.12}},
    )
    committed = service.commit_action_candidate(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
        parameter_name="drive_amplitude",
        username="reviewer",
        body=CommitAgentCandidateRequest(
            idempotency_key="commit-apply",
            expected_state_version=1,
            task_id="task-result-1",
        ),
    )

    calls: list[dict[str, object]] = []

    class FakeFlowService:
        async def execute_agent_candidate_apply(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return type("Operation", (), {"execution_id": "backend-operation-1"})()

    body = ApplyAgentCandidateRequest(
        idempotency_key="apply-1",
        expected_state_version=2,
        push_to_github=True,
    )
    queued = await service.apply_candidate_to_backend(
        project_id="project-1",
        session_id=session.session_id,
        commit_id=committed.commit_id,
        body=body,
        flow_service=cast("FlowService", FakeFlowService()),
    )
    retried = await service.apply_candidate_to_backend(
        project_id="project-1",
        session_id=session.session_id,
        commit_id=committed.commit_id,
        body=body,
        flow_service=cast("FlowService", FakeFlowService()),
    )

    assert queued.backend_status == "queued"
    assert queued.backend_operation_id == "backend-operation-1"
    assert retried.backend_operation_id == queued.backend_operation_id
    assert calls == [
        {
            "project_id": "project-1",
            "session_id": session.session_id,
            "commit_id": committed.commit_id,
            "push_to_github": True,
        }
    ]


def test_commit_action_candidate_rejects_failed_gate_without_state_change(
    service: AgentSessionService,
) -> None:
    """A bounds failure cannot update calibration data or advance session state."""
    session = _create_session(service)
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    _attach_completed_task_result(
        session_id=session.session_id,
        action_id=action.action_id,
        output_parameters={"drive_amplitude": {"value": 0.5}},
    )

    with pytest.raises(HTTPException) as exc_info:
        service.commit_action_candidate(
            project_id="project-1",
            session_id=session.session_id,
            action_id=action.action_id,
            parameter_name="drive_amplitude",
            username="reviewer",
            body=CommitAgentCandidateRequest(
                idempotency_key="commit-rejected",
                expected_state_version=1,
                task_id="task-result-1",
            ),
        )

    unchanged = service.get_session(project_id="project-1", session_id=session.session_id)
    qubit = QubitDocument.find_one(
        {"project_id": "project-1", "chip_id": "chip-001", "qid": "Q00"}
    ).run()

    assert exc_info.value.status_code == 409
    assert "gate rejected" in str(exc_info.value.detail)
    assert unchanged.state_version == 1
    assert unchanged.action_count == 1
    assert qubit is not None
    assert "drive_amplitude" not in qubit.data


def test_list_action_candidates_waits_for_authoritative_result(
    service: AgentSessionService,
) -> None:
    """Candidate extraction cannot fall back to a value supplied by the agent."""
    session = _create_session(service)
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.list_action_candidates(
            project_id="project-1",
            session_id=session.session_id,
            action_id=action.action_id,
        )

    assert exc_info.value.status_code == 409
    assert "has not produced an operation" in str(exc_info.value.detail)


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (_run_task_action(qids=["Q99"]), "outside the session scope"),
        (_run_task_action(task_name="CheckT1"), "not allowed"),
        (_run_task_action(drive_amplitude=0.5), "outside the allowed bounds"),
    ],
)
def test_submit_action_rejects_policy_violation(
    service: AgentSessionService,
    body: SubmitAgentActionRequest,
    reason: str,
) -> None:
    """Platform policy rejects targets, tasks, and parameter values outside the grant."""
    session = _create_session(service)

    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=body,
    )

    assert action.decision == AgentActionDecision.REJECTED
    assert reason in action.reason
    assert action.execution_status == "not_started"


def test_submit_action_rejects_stale_state_version(service: AgentSessionService) -> None:
    """A proposal based on an old observation cannot advance session state."""
    session = _create_session(service)
    service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.submit_action(
            project_id="project-1",
            session_id=session.session_id,
            body=_run_task_action(idempotency_key="action-2"),
        )

    assert exc_info.value.status_code == 409
    assert "version mismatch" in str(exc_info.value.detail)


def test_submit_action_is_idempotent(service: AgentSessionService) -> None:
    """Retrying the same proposal returns its audit record without consuming budget twice."""
    session = _create_session(service)
    body = _run_task_action()

    first = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=body,
    )
    second = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=body,
    )
    updated = service.get_session(project_id="project-1", session_id=session.session_id)

    assert second.action_id == first.action_id
    assert updated.action_count == 1


def test_submit_action_rejects_reused_idempotency_key(service: AgentSessionService) -> None:
    """An idempotency key cannot be reused for a different payload."""
    session = _create_session(service)
    service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.submit_action(
            project_id="project-1",
            session_id=session.session_id,
            body=_run_task_action(
                expected_state_version=1,
                drive_amplitude=0.11,
            ),
        )

    assert exc_info.value.status_code == 409
    assert "different action" in str(exc_info.value.detail)


def test_request_human_transitions_session(service: AgentSessionService) -> None:
    """An authorized escalation moves the session to a fail-safe waiting state."""
    session = _create_session(service)

    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=SubmitAgentActionRequest(
            idempotency_key="human-1",
            expected_state_version=0,
            action_type=AgentActionType.REQUEST_HUMAN,
            diagnosis="The signal is outside all known failure modes.",
        ),
    )
    updated = service.get_session(project_id="project-1", session_id=session.session_id)

    assert action.decision == AgentActionDecision.AUTHORIZED
    assert updated.status.value == "waiting_for_human"
    assert service.list_actions(project_id="project-1", session_id=session.session_id).total == 1


def test_execute_action_request_rejects_direct_parameter_update() -> None:
    """Agent execution cannot bypass the staged candidate gate."""
    with pytest.raises(ValidationError, match="update_params=false"):
        ExecuteAgentActionRequest(
            source_execution_id="execution-1",
            update_params=True,
        )


@pytest.mark.asyncio
async def test_execute_action_rejects_ungranted_hardware_reconfiguration(
    service: AgentSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure cannot be inserted unless the session explicitly grants it."""
    session = _create_session(service)
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_action(
            project_id="project-1",
            session_id=session.session_id,
            action_id=action.action_id,
            body=ExecuteAgentActionRequest(
                source_execution_id="execution-1",
                reconfigure=True,
            ),
            flow_service=cast("FlowService", object()),
            task_file_service=_catalog(monkeypatch),
        )

    assert exc_info.value.status_code == 409
    assert "reconfiguration is not allowed" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_execute_authorized_action_runs_like_the_task_workbench(
    service: AgentSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An action is a catalog run: current inputs, and a session matching the task.

    Restoring a past execution's snapshot opened the Qubex session with its default
    readout_duration while the task kept the snapshot's, so CheckRabi refused to run.
    """
    session = _create_session(service)
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=_run_task_action(),
    )
    sent: dict[str, object] = {}

    class FakeFlowService:
        async def execute_single_task_from_snapshot(self, **kwargs: object) -> object:
            sent.update(kwargs)
            return type(
                "Operation", (), {"execution_id": "20260713-002", "flow_run_id": "operation-1"}
            )()

    result = await service.execute_action(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
        body=ExecuteAgentActionRequest(source_execution_id="execution-1"),
        flow_service=cast("FlowService", FakeFlowService()),
        task_file_service=_catalog(monkeypatch),
    )

    assert sent["task_name"] == "CheckQubitSpectroscopy"
    assert sent["qid"] == "Q00"
    # No snapshot: inputs come from the current calibration state.
    assert sent["source_execution_id"] is None
    assert sent["source_task_id"] is None
    assert sent["parameter_overrides"] == {"input": {"drive_amplitude": 0.1}}
    # The session opens with the readout_duration the task runs with.
    assert sent["default_run_parameters"] == {
        "readout_duration": {"value": 1024, "value_type": "float"}
    }
    assert sent["task_run_parameters"] == {"CheckQubitSpectroscopy": {}}
    assert sent["execution_name"] == "agent:CheckQubitSpectroscopy"
    assert sent["tags"] == [f"agent-session:{session.session_id}"]
    assert sent["update_calibration_parameters"] is False
    assert sent["update_params"] is False
    assert result.execution_status == "queued"
    assert result.operation_id == "operation-1"
    stored = AgentActionDocument.find_one({"action_id": action.action_id}).run()
    assert stored is not None
    assert stored.metadata["source_execution_id"] == "execution-1"
    assert (
        service.get_session(project_id="project-1", session_id=session.session_id).state_version
        == 1
    )
    # The dispatch is a run of the session's automatic calibration session, recorded before
    # the launch and handed to the worker, which stamps it on the execution.
    run_id = f"cpr-action-{action.action_id}"
    assert sent["ungrouped"] is False
    run = CalibrationPipelineRunDocument.find_one({"run_id": run_id}).run()
    assert run is not None
    # The flow run receives the dispatch token of the run's launch, its proof of the run.
    assert sent["calibration_run"] == CalibrationRunIdentity(
        calibration_session_id=session.calibration_session_id,
        run_id=run_id,
        dispatch_token=run.dispatch_token,
    )
    assert run.run_kind == CalibrationRunKind.AGENT_ACTION
    assert (run.agent_session_id, run.action_id) == (session.session_id, action.action_id)
    assert run.status == CalibrationPipelineRunStatus.DISPATCHED
    assert run.flow_run_id == "operation-1"
    assert run.requested_by == session.created_by


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "outcome"),
    [
        (409, CalibrationPipelineRunStatus.REJECTED),
        (500, CalibrationPipelineRunStatus.UNKNOWN),
    ],
)
async def test_a_failed_action_launch_settles_its_run_like_any_run(
    service: AgentSessionService,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    outcome: CalibrationPipelineRunStatus,
) -> None:
    session = _create_session(service)
    action = service.submit_action(
        project_id="project-1", session_id=session.session_id, body=_run_task_action()
    )

    class FailingFlowService:
        async def execute_single_task_from_snapshot(self, **kwargs: object) -> object:
            raise HTTPException(status_code=status_code, detail="refused")

    with pytest.raises(HTTPException):
        await service.execute_action(
            project_id="project-1",
            session_id=session.session_id,
            action_id=action.action_id,
            body=ExecuteAgentActionRequest(),
            flow_service=cast("FlowService", FailingFlowService()),
            task_file_service=_catalog(monkeypatch),
        )
    run = CalibrationPipelineRunDocument.find_one(
        {"run_id": f"cpr-action-{action.action_id}"}
    ).run()
    assert run is not None and run.status == outcome
    # The action itself failed and is never dispatched again.
    stored = AgentActionDocument.find_one({"action_id": action.action_id}).run()
    assert stored is not None and stored.execution_status == "failed"


@pytest.mark.asyncio
async def test_an_action_of_a_legacy_session_stays_out_of_any_calibration_session(
    service: AgentSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _create_session(service)
    make_standalone_agent_session("project-1", session.session_id)
    action = service.submit_action(
        project_id="project-1", session_id=session.session_id, body=_run_task_action()
    )
    sent: dict[str, object] = {}

    class FakeFlowService:
        async def execute_single_task_from_snapshot(self, **kwargs: object) -> object:
            sent.update(kwargs)
            return type(
                "Operation", (), {"execution_id": "20260713-002", "flow_run_id": "operation-1"}
            )()

    await service.execute_action(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
        body=ExecuteAgentActionRequest(),
        flow_service=cast("FlowService", FakeFlowService()),
        task_file_service=_catalog(monkeypatch),
    )
    assert sent["calibration_run"] is None
    # The worker is told not to record it in an automatic session of its own either.
    assert sent["ungrouped"] is True
    assert CalibrationPipelineRunDocument.find_all().count() == 0


@pytest.mark.asyncio
async def test_execute_action_gives_integer_inputs_whole_numbers(
    service: AgentSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent overrides are floats; an integer input still passes the catalog check."""
    session = _create_session(
        service, allowed_overrides={"shots": NumericBounds(minimum=256, maximum=8192)}
    )
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=SubmitAgentActionRequest(
            idempotency_key="action-shots",
            expected_state_version=0,
            action_type=AgentActionType.RUN_TASK,
            task_name="CheckQubitSpectroscopy",
            qids=["Q00"],
            parameter_overrides={"shots": 2048.0},
            diagnosis="More shots to resolve the peak.",
        ),
    )
    sent: dict[str, object] = {}

    class FakeFlowService:
        async def execute_single_task_from_snapshot(self, **kwargs: object) -> object:
            sent.update(kwargs)
            return type("Operation", (), {"execution_id": "e", "flow_run_id": "op"})()

    await service.execute_action(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
        body=ExecuteAgentActionRequest(),
        flow_service=cast("FlowService", FakeFlowService()),
        task_file_service=_catalog(monkeypatch),
    )

    assert sent["parameter_overrides"] == {"input": {"shots": 2048}}


@pytest.mark.asyncio
async def test_execute_action_applies_the_workbench_override_rules(
    service: AgentSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An input the task forbids overriding is refused, and the action is marked failed."""
    session = _create_session(service)
    action = service.submit_action(
        project_id="project-1",
        session_id=session.session_id,
        body=SubmitAgentActionRequest(
            idempotency_key="action-forbidden",
            expected_state_version=0,
            action_type=AgentActionType.RUN_TASK,
            task_name="CheckQubitSpectroscopy",
            qids=["Q00"],
            parameter_overrides={"qubit_frequency": 4.5},
            diagnosis="Try a different frequency.",
        ),
    )

    with pytest.raises(HTTPException, match="do not allow overrides") as exc_info:
        await service.execute_action(
            project_id="project-1",
            session_id=session.session_id,
            action_id=action.action_id,
            body=ExecuteAgentActionRequest(),
            flow_service=cast("FlowService", object()),
            task_file_service=_catalog(monkeypatch),
        )

    assert exc_info.value.status_code == 400
    stored = AgentActionDocument.find_one({"action_id": action.action_id}).run()
    assert stored is not None
    assert stored.execution_status == "failed"


@pytest.mark.asyncio
async def test_with_grouping_off_a_session_stands_alone_and_its_actions_record_runs(
    service: AgentSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.config import get_settings

    monkeypatch.setattr(get_settings(), "calibration_session_grouping", "explicit")
    session = _create_session(service)
    # No automatic parent and no admission to wait for: the policy is the only authority.
    assert session.calibration_session_id is None
    assert session.calibration_admission is None
    assert CalibrationSessionDocument.find_all().count() == 0
    action = service.submit_action(
        project_id="project-1", session_id=session.session_id, body=_run_task_action()
    )
    sent: dict[str, object] = {}

    class FakeFlowService:
        async def execute_single_task_from_snapshot(self, **kwargs: object) -> object:
            sent.update(kwargs)
            return type(
                "Operation", (), {"execution_id": "20260713-002", "flow_run_id": "operation-1"}
            )()

    await service.execute_action(
        project_id="project-1",
        session_id=session.session_id,
        action_id=action.action_id,
        body=ExecuteAgentActionRequest(),
        flow_service=cast("FlowService", FakeFlowService()),
        task_file_service=_catalog(monkeypatch),
    )
    run = CalibrationPipelineRunDocument.find_one(
        {"run_id": f"cpr-action-{action.action_id}"}
    ).run()
    assert run is not None
    assert run.calibration_session_id is None and run.association == "none"
    assert (run.status, run.flow_run_id) == ("dispatched", "operation-1")
    assert sent["ungrouped"] is False
    assert sent["calibration_run"] == CalibrationRunIdentity(
        calibration_session_id=None,
        run_id=run.run_id,
        dispatch_token=run.dispatch_token,
    )


def test_with_grouping_off_a_named_closed_calibration_session_still_refuses_the_start(
    service: AgentSessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qdash.config import get_settings

    monkeypatch.setattr(get_settings(), "calibration_session_grouping", "explicit")
    CalibrationSessionDocument(
        calibration_session_id="cs-closed",
        project_id="project-1",
        chip_id="chip-001",
        objective="Done",
        created_by="tester",
        status="closed",
    ).insert()
    with pytest.raises(HTTPException) as refused:
        service.create_session(
            project_id="project-1",
            username="tester",
            body=CreateAgentSessionRequest(
                chip_id="chip-001",
                policy=AgentSessionPolicy(
                    qids=["Q00"], allowed_tasks=["CheckQubitSpectroscopy"], max_actions=1
                ),
                skill_name="single-qubit-bringup",
                calibration_session_id="cs-closed",
            ),
        )
    assert refused.value.status_code == 409
    assert AgentSessionDocument.find_all().count() == 0
