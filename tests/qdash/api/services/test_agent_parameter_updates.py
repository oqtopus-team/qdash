"""Parameter updates under a session's approved ``parameter_updates`` authority.

A person approves update authority once with the session. QDash then lets the agent commit,
and with ``apply_backend`` apply, a passing candidate without a per-update approval, but only
when its own records ground the update: the creator's ``auto`` session, the approved
parameter, task, and qubit, a recorded ``pass`` assessment of exactly that measurement, the
mechanical gates, and the current state. Failed, uncertain, or unexplained results stop
before any update and before the next dependent measurement.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from qdash.api.schemas.agent_session import (
    ApplyAgentCandidateRequest,
    CommitAgentCandidateRequest,
    CreateAgentSessionRequest,
    RecordAgentDecisionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.services.agent_session_audit import AgentSessionAuditService
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import (
    AgentActionType,
    AgentAutonomy,
    AgentCandidateAcceptanceBasis,
    AgentCandidateRejection,
    AgentDecisionAssessment,
    AgentDecisionNextAction,
    AgentEvaluationMode,
    AgentInterventionAttempt,
    AgentInterventionDecision,
    AgentInterventionReason,
    AgentInterventionResponseRecord,
    AgentInterventionStatus,
    AgentModelIdentity,
    AgentParameterUpdatePolicy,
    AgentSessionPolicy,
    AgentSessionStatus,
    NumericBounds,
)
from qdash.datamodel.evaluation import EvaluationOutputModel, EvaluationVerdictModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_parameter_state import apply_lock_key
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentBackendApplyLockDocument,
    AgentCandidateCommitDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.evaluation import EvaluationDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.api.services.flow_service import FlowService

PROJECT = "project-1"
OWNER = "alice"
FREQUENCY = NumericBounds(minimum=7.0, maximum=8.0)


@pytest.fixture
def service(init_db) -> AgentSessionService:
    """A service with a chip and one qubit in the active test database."""
    ChipDocument(
        project_id=PROJECT,
        chip_id="chip-001",
        username=OWNER,
        size=4,
        system_info=SystemInfoModel(),
    ).insert()
    QubitDocument(
        project_id=PROJECT,
        username=OWNER,
        qid="Q00",
        chip_id="chip-001",
        data={},
        system_info=SystemInfoModel(),
    ).insert()
    return AgentSessionService()


audit = AgentSessionAuditService()


def _policy(
    *,
    updates: AgentParameterUpdatePolicy | None = None,
    autonomy: AgentAutonomy = AgentAutonomy.AUTO,
    task_quality_gates: dict[str, dict[str, NumericBounds]] | None = None,
    overrides: dict[str, NumericBounds] | None = None,
    evaluation: AgentEvaluationMode | None = None,
) -> AgentSessionPolicy:
    return AgentSessionPolicy(
        evaluation=evaluation,
        qids=["Q00"],
        allowed_tasks=["CheckChevron", "CheckRabi"],
        allowed_overrides={"qubit_frequency": FREQUENCY} if overrides is None else overrides,
        task_quality_gates=task_quality_gates or {},
        autonomy=autonomy,
        max_actions=4,
        parameter_updates=updates,
    )


GRANT = AgentParameterUpdatePolicy(parameters=["qubit_frequency"], tasks=["CheckChevron"])


def _session(
    service: AgentSessionService,
    updates: AgentParameterUpdatePolicy | None = GRANT,
    **policy: Any,
) -> str:
    return service.create_session(
        project_id=PROJECT,
        username=OWNER,
        body=CreateAgentSessionRequest(
            chip_id="chip-001", policy=_policy(updates=updates, **policy)
        ),
    ).session_id


def _version(session_id: str) -> int:
    doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert doc is not None
    return doc.state_version


def _measure(
    service: AgentSessionService,
    session_id: str,
    task: str,
    *,
    status: str = "completed",
    value: float | None = 7.45,
    key: str | None = None,
    repeat_of: str | None = None,
    quality: dict[str, float] | None = None,
    extra_outputs: dict[str, dict[str, Any]] | None = None,
) -> str:
    action = service.submit_action(
        project_id=PROJECT,
        session_id=session_id,
        username=OWNER,
        body=SubmitAgentActionRequest(
            idempotency_key=key or f"{task}-{_version(session_id)}",
            expected_state_version=_version(session_id),
            action_type=AgentActionType.RUN_TASK,
            task_name=task,
            qids=["Q00"],
            autonomous=True,
            repeat_of_action_id=repeat_of,
        ),
    )
    assert action.decision == "authorized", action.reason
    doc = AgentActionDocument.find_one({"action_id": action.action_id}).run()
    assert doc is not None
    sequence = AgentActionDocument.find({"session_id": session_id}).count()
    doc.operation_id = f"operation-{session_id}-{sequence}"
    doc.execution_id = f"execution-{session_id}-{sequence}"
    doc.execution_status = status
    doc.save()
    outputs = {} if value is None else {"qubit_frequency": {"value": value, "unit": "GHz"}}
    outputs.update(extra_outputs or {})
    TaskResultHistoryDocument(
        project_id=PROJECT,
        username=OWNER,
        task_id=f"task-{session_id}-{sequence}",
        name=task,
        upstream_id="",
        status="completed" if status == "completed" else "failed",
        message=status,
        input_parameters={},
        output_parameters=outputs,
        output_parameter_names=list(outputs),
        run_parameters={},
        quality_metrics=quality or {},
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
        execution_id=doc.execution_id,
        tags=[],
        chip_id="chip-001",
    ).insert()
    return action.action_id


def _task_id(action_id: str) -> str:
    action = AgentActionDocument.find_one({"action_id": action_id}).run()
    assert action is not None
    result = TaskResultHistoryDocument.find_one({"execution_id": action.execution_id}).run()
    assert result is not None
    return result.task_id


def _decide(
    session_id: str,
    action_id: str,
    assessment: AgentDecisionAssessment | None = AgentDecisionAssessment.PASS,
    *,
    next_action: AgentDecisionNextAction = AgentDecisionNextAction.PROPOSE_COMMIT,
    key: str | None = None,
    supersedes: str | None = None,
    model: AgentModelIdentity | None = None,
) -> str:
    return audit.record_decision(
        project_id=PROJECT,
        session_id=session_id,
        username=OWNER,
        body=RecordAgentDecisionRequest(
            idempotency_key=key or f"decision-{action_id}-{assessment}-{next_action.value}",
            assessment=assessment,
            interpretation="Chevron peak at 7.45 GHz inside the approved range.",
            next_action=next_action,
            evidence_action_ids=[action_id],
            supersedes_decision_id=supersedes,
            model=model,
        ),
    ).decision_id


def _commit(
    service: AgentSessionService,
    session_id: str,
    action_id: str,
    decision_id: str | None,
    *,
    user: str = OWNER,
    key: str = "commit-1",
    version: int | None = None,
    autonomous: bool = True,
    parameter: str = "qubit_frequency",
) -> Any:
    return service.commit_action_candidate(
        project_id=PROJECT,
        session_id=session_id,
        action_id=action_id,
        parameter_name=parameter,
        username=user,
        body=CommitAgentCandidateRequest(
            idempotency_key=key,
            expected_state_version=_version(session_id) if version is None else version,
            task_id=_task_id(action_id),
            autonomous=autonomous,
            decision_id=decision_id,
        ),
    )


def _refused(call: Any, status: int, match: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        call()
    assert exc_info.value.status_code == status, exc_info.value.detail
    assert match in str(exc_info.value.detail), exc_info.value.detail


def _stored_frequency() -> Any:
    qubit = QubitDocument.find_one({"qid": "Q00"}).run()
    assert qubit is not None
    return qubit.data.get("qubit_frequency")


def _resume_intervention(
    session_id: str,
    cites: list[str],
    *,
    key: str = "iv",
    at: Any = None,
    decision: AgentInterventionDecision = AgentInterventionDecision.RESUME,
) -> None:
    """A person answered an intervention of the session whose attempts cite ``cites``."""
    AgentInterventionDocument(
        intervention_id=f"{key}-{session_id}",
        project_id=PROJECT,
        session_id=session_id,
        chip_id="chip-001",
        idempotency_key=f"{key}-{session_id}",
        request_hash="x",
        created_by=OWNER,
        reason=AgentInterventionReason.UNKNOWN_OUTCOME,
        summary="failed",
        question="continue?",
        attempts=[AgentInterventionAttempt(action_id=action_id) for action_id in cites],
        session_status_at_open=AgentSessionStatus.ACTIVE,
        session_state_version_at_open=0,
        status=(
            AgentInterventionStatus.RESUMED
            if decision == AgentInterventionDecision.RESUME
            else AgentInterventionStatus.STOPPED
        ),
        response=AgentInterventionResponseRecord(
            response_id=f"r-{key}",
            decision=decision,
            guidance="Fault cleared; repeat it once.",
            responded_by="expert",
            responded_at=at if at is not None else now() + timedelta(seconds=1),
            expected_state_version=0,
        ),
    ).insert()


def _evaluate(
    action_id: str,
    *,
    status: str = "completed",
    diagnosis: dict[str, Any] | None = None,
    disagree: bool = False,
    key: str = "ev-1",
    at: Any = None,
    requested_at: Any = None,
) -> None:
    """Record an evaluation of the action's task result, completed at ``at`` (now)."""
    completed_at = at if at is not None else now()
    EvaluationDocument(
        evaluation_id=key,
        run_id="run-1",
        project_id=PROJECT,
        chip_id="chip-001",
        task_id=_task_id(action_id),
        task_name="CheckChevron",
        qid="Q00",
        status=status,
        requested_at=requested_at if requested_at is not None else completed_at,
        completed_at=None if status in ("pending", "running") else completed_at,
        output=(
            EvaluationOutputModel(diagnosis=diagnosis, model="vllm/qcal-vlm")
            if diagnosis is not None
            else None
        ),
        verdicts=(
            [EvaluationVerdictModel(agree=False, username="reviewer", updated_at=completed_at)]
            if disagree
            else []
        ),
    ).insert()


POSITIVE = {
    "fit_reliability": {"assessment": "Reliable"},
    "calibration_diagnosis": {"status": "SUCCESS"},
}


# --------------------------------------------------------------------------- the policy


def test_update_authority_is_opt_in_explicit_and_inside_the_approved_scope() -> None:
    assert _policy().parameter_updates is None
    with pytest.raises(ValidationError, match="requires autonomy auto"):
        _policy(updates=GRANT, autonomy=AgentAutonomy.CONFIRM_EACH)
    with pytest.raises(ValidationError, match="must be allowed tasks"):
        _policy(
            updates=AgentParameterUpdatePolicy(parameters=["qubit_frequency"], tasks=["CheckT1"])
        )
    # A grant names which parameters may change; it needs no numeric bounds to authorize it.
    unbounded = _policy(
        updates=AgentParameterUpdatePolicy(parameters=["drag_amplitude"], tasks=["CheckRabi"])
    )
    assert "drag_amplitude" not in unbounded.allowed_overrides
    open_ended = AgentSessionPolicy(
        qids=["Q00"],
        allowed_tasks=["CheckChevron"],
        allowed_overrides={"qubit_frequency": NumericBounds(minimum=7.0)},
        autonomy=AgentAutonomy.AUTO,
    )
    granted = AgentSessionPolicy.model_validate(
        {**open_ended.model_dump(), "parameter_updates": GRANT}
    )
    assert granted.allowed_overrides == {"qubit_frequency": NumericBounds(minimum=7.0)}
    # A session stored before the field existed reads as no authority.
    stored = {
        key: value for key, value in _policy().model_dump().items() if key != "parameter_updates"
    }
    assert AgentSessionPolicy.model_validate(stored).parameter_updates is None


def test_request_shapes_keep_authority_explicit() -> None:
    with pytest.raises(ValidationError, match="decision_id is required"):
        CommitAgentCandidateRequest(
            idempotency_key="k", expected_state_version=0, task_id="t", autonomous=True
        )
    with pytest.raises(ValidationError, match="only valid for an autonomous commit"):
        CommitAgentCandidateRequest(
            idempotency_key="k", expected_state_version=0, task_id="t", decision_id="d"
        )
    with pytest.raises(ValidationError, match="cannot push to GitHub"):
        ApplyAgentCandidateRequest(
            idempotency_key="k", expected_state_version=0, autonomous=True, push_to_github=True
        )


# --------------------------------------------------------------------------- commits


def test_a_passing_measurement_commits_once_without_approval_and_records_its_evidence(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    decision = _decide(session_id, chevron)
    committed = _commit(service, session_id, chevron, decision)

    assert committed.status == "committed"
    assert committed.authority == "session_policy"
    assert committed.decision_id == decision
    assert committed.committed_by == OWNER
    assert committed.before_snapshot is None
    assert committed.after_snapshot is not None
    assert committed.after_snapshot["value"] == 7.45
    evidence = committed.assessment_evidence
    assert evidence["assessment"]["provenance"] == "agent_reported"
    assert evidence["assessment"]["assessment"] == "pass"
    assert evidence["gates"]["provenance"] == "server_computed"
    assert evidence["gates"]["minimum"] == 7.0
    assert evidence["gates"]["applied_quality_gates"] == []
    assert evidence["gates"]["acceptance_basis"] == "session_bounds"
    assert evidence["gates"]["task_checks"] == {
        "source": "task_definition",
        "enforced_by": "workflow",
    }
    assert evidence["authority"] == {
        "kind": "session_policy",
        "granted_by": OWNER,
        "parameters": ["qubit_frequency"],
        "tasks": ["CheckChevron"],
        "apply_backend": False,
    }
    assert "not a scientific verdict" in evidence["note"]
    assert _stored_frequency()["value"] == 7.45

    # A replay returns the same record; a new key cannot commit the candidate twice.
    replay = _commit(service, session_id, chevron, decision, version=committed.state_version_before)
    assert replay.commit_id == committed.commit_id
    _refused(
        lambda: _commit(service, session_id, chevron, decision, key="again"),
        409,
        "already committed",
    )

    timeline = audit.read_audit(project_id=PROJECT, session_id=session_id, cursor=None, limit=200)
    event = next(item for item in timeline.events if item.kind == "candidate_commit")
    assert event.actor_kind == "agent"
    assert event.data["authority"] == "session_policy"
    assert event.data["assessment_evidence"]["assessment"]["decision_id"] == decision
    assert "approved update authority" in event.summary


def test_a_scoped_update_names_the_model_of_its_decision_and_a_reviewed_one_a_person(
    service: AgentSessionService,
) -> None:
    model = AgentModelIdentity(provider="vllm", model_id="qwen3-32b", host="qdash-web-agent")
    session_id = _session(service)
    policy = service.get_session(project_id=PROJECT, session_id=session_id).policy
    chevron = _measure(service, session_id, "CheckChevron")
    committed = _commit(service, session_id, chevron, _decide(session_id, chevron, model=model))

    assert committed.assessment_evidence["assessment"]["model"] == model.model_dump()
    assert committed.committed_by == OWNER
    # Reporting a model grants nothing: the approval is the session's, unchanged.
    assert service.get_session(project_id=PROJECT, session_id=session_id).policy == policy
    timeline = audit.read_audit(project_id=PROJECT, session_id=session_id, cursor=None, limit=200)
    event = next(item for item in timeline.events if item.kind == "candidate_commit")
    assert event.model == model
    assert "model" not in event.missing


def test_a_scoped_update_without_a_reported_model_says_so(service: AgentSessionService) -> None:
    session_id = _session(service)
    measured = _measure(service, session_id, "CheckChevron")
    committed = _commit(service, session_id, measured, _decide(session_id, measured))
    assert committed.assessment_evidence["assessment"]["model"] is None
    timeline = audit.read_audit(project_id=PROJECT, session_id=session_id, cursor=None, limit=200)
    event = next(item for item in timeline.events if item.kind == "candidate_commit")
    assert event.model is None
    assert "model" in event.missing


def test_a_reviewed_commit_is_a_persons_act_without_a_model(service: AgentSessionService) -> None:
    reviewed = _session(service, updates=None)
    measured = _measure(service, reviewed, "CheckChevron")
    _commit(service, reviewed, measured, None, autonomous=False)
    timeline = audit.read_audit(project_id=PROJECT, session_id=reviewed, cursor=None, limit=200)
    event = next(item for item in timeline.events if item.kind == "candidate_commit")
    assert event.actor == OWNER
    assert event.actor_kind == "human"
    assert event.model is None
    assert "model" not in event.missing


def test_sessions_without_the_grant_and_other_users_never_commit_autonomously(
    service: AgentSessionService,
) -> None:
    plain = _session(service, updates=None)
    chevron = _measure(service, plain, "CheckChevron")
    decision = _decide(plain, chevron)
    _refused(
        lambda: _commit(service, plain, chevron, decision), 409, "did not grant parameter updates"
    )
    assert _stored_frequency() is None

    granted = _session(service)
    action = _measure(service, granted, "CheckChevron")
    passed = _decide(granted, action)
    for user in ("bob", ""):
        _refused(
            lambda user=user: _commit(service, granted, action, passed, user=user),
            403,
            f"belongs to {OWNER}",
        )
    assert AgentCandidateCommitDocument.find({}).count() == 0

    # The reviewed path, approved per call, is unchanged.
    reviewed = _commit(service, plain, chevron, None, user="bob", autonomous=False)
    assert reviewed.status == "committed"
    assert reviewed.authority == "reviewed"
    assert reviewed.assessment_evidence == {}


def test_out_of_scope_tasks_parameters_and_rejected_values_are_refused(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    rabi = _measure(service, session_id, "CheckRabi", value=7.45)
    _refused(
        lambda: _commit(service, session_id, rabi, _decide(session_id, rabi)),
        409,
        "does not grant updates from CheckRabi",
    )

    other = _session(
        service, task_quality_gates={"CheckChevron": {"r2": NumericBounds(minimum=0.9)}}
    )
    low = _measure(service, other, "CheckChevron", quality={"r2": 0.5})
    _refused(
        lambda: _commit(service, other, low, _decide(other, low)), 409, "Candidate gate rejected"
    )
    third = _session(service)
    outside = _measure(service, third, "CheckChevron", value=9.1)
    _refused(
        lambda: _commit(service, third, outside, _decide(third, outside)),
        409,
        "Candidate gate rejected",
    )
    assert _stored_frequency() is None


def test_a_grant_without_bounds_commits_on_the_task_checks_and_nothing_else(
    service: AgentSessionService,
) -> None:
    session_id = _session(service, overrides={})
    chevron = _measure(service, session_id, "CheckChevron", value=7.45)
    candidates = service.list_action_candidates(
        project_id=PROJECT, session_id=session_id, action_id=chevron
    ).items
    assert [(c.accepted, c.acceptance_basis, c.minimum, c.maximum) for c in candidates] == [
        (True, AgentCandidateAcceptanceBasis.TASK_CHECKS, None, None)
    ]
    committed = _commit(service, session_id, chevron, _decide(session_id, chevron))
    assert committed.status == "committed"
    gates = committed.assessment_evidence["gates"]
    assert gates["acceptance_basis"] == "task_checks"
    assert (gates["minimum"], gates["maximum"]) == (None, None)
    assert "no numeric bounds" in gates["candidate_reason"]
    assert _stored_frequency()["value"] == 7.45

    # The grant covers only its tasks: the same parameter from CheckRabi is not accepted.
    rabi = _measure(service, session_id, "CheckRabi", value=7.5)
    from_rabi = service.list_action_candidates(
        project_id=PROJECT, session_id=session_id, action_id=rabi
    ).items
    assert [(c.accepted, c.acceptance_basis) for c in from_rabi] == [(False, None)]
    assert "not allowed by the session policy" in from_rabi[0].reason


INCIDENTAL_AMPLITUDE = {"control_amplitude": {"value": 0.00706107, "unit": "a.u."}}


def test_an_ungranted_incidental_output_neither_blocks_nor_widens_the_granted_update(
    service: AgentSessionService,
) -> None:
    # As reported: CheckChevron granted for qubit_frequency only, no numeric bounds, and its
    # control_amplitude estimate outside the session's scope.
    session_id = _session(service, overrides={})
    chevron = _measure(
        service,
        session_id,
        "CheckChevron",
        value=8.269908677,
        extra_outputs=INCIDENTAL_AMPLITUDE,
    )
    candidates = {
        c.parameter_name: c
        for c in service.list_action_candidates(
            project_id=PROJECT, session_id=session_id, action_id=chevron
        ).items
    }
    frequency, amplitude = candidates["qubit_frequency"], candidates["control_amplitude"]
    assert (frequency.accepted, frequency.acceptance_basis, frequency.rejection) == (
        True,
        AgentCandidateAcceptanceBasis.TASK_CHECKS,
        None,
    )
    assert (amplitude.accepted, amplitude.rejection) == (
        False,
        AgentCandidateRejection.NOT_IN_SCOPE,
    )
    assert "not granted from CheckChevron and no approved bounds" in amplitude.reason
    assert "not evidence against this result" in amplitude.reason

    # The amplitude is never committed under the grant, and asking does not widen it.
    _refused(
        lambda: _commit(
            service,
            session_id,
            chevron,
            _decide(session_id, chevron),
            parameter="control_amplitude",
            key="amplitude",
        ),
        409,
        "Parameter 'control_amplitude' is not allowed by the session policy",
    )
    committed = _commit(service, session_id, chevron, _decide(session_id, chevron))
    assert committed.status == "committed"
    assert _stored_frequency()["value"] == 8.269908677
    assert _measure(service, session_id, "CheckRabi")
    stored = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert stored is not None
    assert stored.policy.parameter_updates is not None
    assert stored.policy.parameter_updates.parameters == ["qubit_frequency"]
    assert stored.policy.allowed_overrides == {}


def test_a_rejected_granted_output_still_stops_beside_an_incidental_one(
    service: AgentSessionService,
) -> None:
    # Bounds approved with a stored session keep applying, and keep their reason code.
    bounded = _session(service)
    outside = _measure(
        service, bounded, "CheckChevron", value=9.5, extra_outputs=INCIDENTAL_AMPLITUDE
    )
    rejections = {
        c.parameter_name: c.rejection
        for c in service.list_action_candidates(
            project_id=PROJECT, session_id=bounded, action_id=outside
        ).items
    }
    assert rejections == {
        "qubit_frequency": AgentCandidateRejection.OUTSIDE_BOUNDS,
        "control_amplitude": AgentCandidateRejection.NOT_IN_SCOPE,
    }
    _refused(lambda: _measure(service, bounded, "CheckRabi"), 409, "was rejected")
    _refused(
        lambda: _commit(service, bounded, outside, _decide(bounded, outside)),
        409,
        "Candidate gate rejected",
    )

    gated = _session(
        service,
        overrides={},
        task_quality_gates={"CheckChevron": {"r2": NumericBounds(minimum=0.9)}},
    )
    low = _measure(
        service,
        gated,
        "CheckChevron",
        value=8.27,
        quality={"r2": 0.5},
        extra_outputs=INCIDENTAL_AMPLITUDE,
    )
    rejections = {
        c.parameter_name: c.rejection
        for c in service.list_action_candidates(
            project_id=PROJECT, session_id=gated, action_id=low
        ).items
    }
    assert rejections["qubit_frequency"] == AgentCandidateRejection.QUALITY_GATE
    _refused(lambda: _measure(service, gated, "CheckRabi"), 409, "was rejected")
    assert _stored_frequency() is None


def test_a_grant_without_bounds_still_fails_closed_on_its_task_gate(
    service: AgentSessionService,
) -> None:
    session_id = _session(
        service,
        overrides={},
        task_quality_gates={"CheckChevron": {"r2": NumericBounds(minimum=0.9)}},
    )
    chevron = _measure(service, session_id, "CheckChevron", value=7.45)
    (candidate,) = service.list_action_candidates(
        project_id=PROJECT, session_id=session_id, action_id=chevron
    ).items
    assert not candidate.accepted
    assert candidate.acceptance_basis is None
    assert candidate.reason == ("Required quality metric 'r2' for task 'CheckChevron' is missing")
    _refused(
        lambda: _commit(service, session_id, chevron, _decide(session_id, chevron)),
        409,
        "Candidate gate rejected",
    )
    assert _stored_frequency() is None


def test_update_evidence_records_only_the_task_gates_it_was_checked_against(
    service: AgentSessionService,
) -> None:
    session_id = _session(
        service,
        task_quality_gates={
            "CheckChevron": {"r2": NumericBounds(minimum=0.9)},
            "CheckRabi": {"r2": NumericBounds(minimum=0.99)},
        },
    )
    chevron = _measure(service, session_id, "CheckChevron", quality={"r2": 0.95})
    committed = _commit(service, session_id, chevron, _decide(session_id, chevron))

    assert committed.status == "committed"
    assert committed.assessment_evidence["gates"]["applied_quality_gates"] == [
        {
            "metric_name": "r2",
            "scope": "task",
            "task_name": "CheckChevron",
            "minimum": 0.9,
            "maximum": None,
        }
    ]


@pytest.mark.parametrize(
    "assessment",
    [AgentDecisionAssessment.FAIL, AgentDecisionAssessment.INCONCLUSIVE, None],
)
def test_only_an_explicit_pass_grounds_an_update(
    service: AgentSessionService, assessment: AgentDecisionAssessment | None
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    decision = _decide(session_id, chevron, assessment)
    _refused(lambda: _commit(service, session_id, chevron, decision), 409, "only an explicit pass")
    assert _stored_frequency() is None


def test_an_uncertain_result_is_never_committed_even_after_a_later_pass(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    doubt = _decide(
        session_id,
        chevron,
        AgentDecisionAssessment.INCONCLUSIVE,
        next_action=AgentDecisionNextAction.REQUEST_HUMAN,
    )
    later = _decide(session_id, chevron, key="later-pass", supersedes=doubt)
    _refused(
        lambda: _commit(service, session_id, chevron, later),
        409,
        "never committed under the session's authority",
    )
    # A later non-pass decision also withdraws an earlier pass.
    other = _session(service)
    action = _measure(service, other, "CheckChevron")
    passed = _decide(other, action)
    _decide(other, action, None, next_action=AgentDecisionNextAction.STOP, key="stop")
    _refused(lambda: _commit(service, other, action, passed), 409, "without a pass assessment")
    assert _stored_frequency() is None


def test_missing_foreign_and_superseded_decisions_are_refused(service: AgentSessionService) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _refused(
        lambda: _commit(service, session_id, chevron, "invented"),
        409,
        "not a decision of this session",
    )

    other = _session(service)
    other_action = _measure(service, other, "CheckChevron")
    foreign = _decide(other, other_action)
    _refused(
        lambda: _commit(service, session_id, chevron, foreign),
        409,
        "not a decision of this session",
    )

    first_pass = _decide(session_id, chevron, key="first-pass")
    _decide(session_id, chevron, key="correction", supersedes=first_pass)
    _refused(lambda: _commit(service, session_id, chevron, first_pass), 409, "superseded")

    second = _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="second")
    _refused(lambda: _commit(service, session_id, second, first_pass), 409, "does not cite action")
    assert _stored_frequency() is None


def test_stale_superseded_and_concurrent_updates_are_refused(service: AgentSessionService) -> None:
    session_id = _session(service)
    first = _measure(service, session_id, "CheckChevron")
    second = _measure(service, session_id, "CheckChevron", repeat_of=first, key="repeat")
    _refused(
        lambda: _commit(service, session_id, first, _decide(session_id, first)),
        409,
        "only the newest result",
    )

    # A running measurement of the session blocks the update.
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": first}, {"$set": {"execution_status": "running"}}
    )
    decision = _decide(session_id, second)
    _refused(lambda: _commit(service, session_id, second, decision), 409, "still running")
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": first}, {"$set": {"execution_status": "completed"}}
    )

    # Someone changed the stored value after the measurement was proposed.
    QubitDocument.get_motor_collection().update_one(
        {"qid": "Q00"},
        {
            "$set": {
                "data.qubit_frequency": {
                    "value": 7.2,
                    "calibrated_at": now() + timedelta(seconds=5),
                }
            }
        },
    )
    _refused(lambda: _commit(service, session_id, second, decision), 409, "may be stale")
    QubitDocument.get_motor_collection().update_one({"qid": "Q00"}, {"$set": {"data": {}}})

    # Two commits decided from one state version: one wins, the other changes nothing.
    version = _version(session_id)
    winner = _commit(service, session_id, second, decision, version=version)
    assert winner.status == "committed"
    _refused(
        lambda: _commit(service, session_id, second, decision, key="loser", version=version),
        409,
        "state version mismatch",
    )


def test_a_paused_or_expired_session_commits_nothing(service: AgentSessionService) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    decision = _decide(session_id, chevron)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id}, {"$set": {"status": AgentSessionStatus.WAITING_FOR_HUMAN.value}}
    )
    _refused(lambda: _commit(service, session_id, chevron, decision), 409, "not active")
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id},
        {"$set": {"status": "active", "expires_at": now() - timedelta(seconds=1)}},
    )
    _refused(lambda: _commit(service, session_id, chevron, decision), 409, "not active")
    assert _stored_frequency() is None


# --------------------------------------------------------------------------- applies


class _FlowService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute_agent_candidate_apply(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return type("Operation", (), {"execution_id": f"apply-{len(self.calls)}"})()


async def _apply(
    service: AgentSessionService,
    session_id: str,
    commit_id: str,
    flow: _FlowService,
    *,
    key: str = "apply-1",
    autonomous: bool = True,
    user: str = OWNER,
) -> Any:
    return await service.apply_candidate_to_backend(
        project_id=PROJECT,
        session_id=session_id,
        commit_id=commit_id,
        body=ApplyAgentCandidateRequest(
            idempotency_key=key, expected_state_version=_version(session_id), autonomous=autonomous
        ),
        flow_service=cast("FlowService", flow),
        username=user,
    )


async def _refused_async(call: Any, status: int, match: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await call()
    assert exc_info.value.status_code == status, exc_info.value.detail
    assert match in str(exc_info.value.detail), exc_info.value.detail


@pytest.mark.asyncio
async def test_apply_needs_the_explicit_grant_and_a_commit_of_that_authority(
    service: AgentSessionService,
) -> None:
    flow = _FlowService()
    commit_only = _session(service)
    chevron = _measure(service, commit_only, "CheckChevron")
    committed = _commit(service, commit_only, chevron, _decide(commit_only, chevron))
    await _refused_async(
        lambda: _apply(service, commit_only, committed.commit_id, flow), 409, "not backend applies"
    )

    granted = _session(service, updates=GRANT.model_copy(update={"apply_backend": True}))
    reviewed_action = _measure(service, granted, "CheckChevron")
    reviewed = _commit(service, granted, reviewed_action, None, user="bob", autonomous=False)
    await _refused_async(
        lambda: _apply(service, granted, reviewed.commit_id, flow), 409, "Only a commit made under"
    )
    assert flow.calls == []

    action = _measure(service, granted, "CheckChevron", repeat_of=reviewed_action, key="again")
    own = _commit(service, granted, action, _decide(granted, action), key="own")
    await _refused_async(
        lambda: _apply(service, granted, own.commit_id, flow, user="bob"),
        403,
        f"belongs to {OWNER}",
    )
    queued = await _apply(service, granted, own.commit_id, flow)
    assert queued.backend_status == "queued"
    assert queued.backend_authority == "session_policy"
    assert queued.backend_requested_by == OWNER
    assert flow.calls == [
        {
            "project_id": PROJECT,
            "session_id": granted,
            "commit_id": own.commit_id,
            "push_to_github": False,
        }
    ]
    replay = await _apply(service, granted, own.commit_id, flow)
    assert replay.backend_operation_id == queued.backend_operation_id
    assert len(flow.calls) == 1

    # A failed apply is an unknown error: it is not retried under the session's authority.
    AgentCandidateCommitDocument.get_motor_collection().update_one(
        {"commit_id": own.commit_id}, {"$set": {"backend_status": "failed"}}
    )
    await _refused_async(
        lambda: _apply(service, granted, own.commit_id, flow, key="retry"), 409, "needs a person"
    )
    # The reviewed apply remains available for a person.
    retried = await _apply(
        service, granted, own.commit_id, flow, key="reviewed", autonomous=False, user="bob"
    )
    assert retried.backend_authority == "reviewed"
    assert retried.backend_requested_by == "bob"


@pytest.mark.asyncio
async def test_apply_refuses_a_value_that_is_no_longer_stored(service: AgentSessionService) -> None:
    flow = _FlowService()
    session_id = _session(service, updates=GRANT.model_copy(update={"apply_backend": True}))
    chevron = _measure(service, session_id, "CheckChevron")
    committed = _commit(service, session_id, chevron, _decide(session_id, chevron))
    QubitDocument.get_motor_collection().update_one(
        {"qid": "Q00"}, {"$set": {"data.qubit_frequency.value": 7.3}}
    )
    await _refused_async(
        lambda: _apply(service, session_id, committed.commit_id, flow), 409, "no longer the value"
    )
    assert flow.calls == []


# --------------------------------------------------------------------------- dependent steps


def test_a_dependent_step_waits_for_the_update_it_needs(service: AgentSessionService) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, "is not committed")
    _commit(service, session_id, chevron, _decide(session_id, chevron))
    assert _measure(service, session_id, "CheckRabi")


QUESTIONABLE = [
    ("failed", None, None, "did not complete"),
    ("completed", 7.45, AgentDecisionAssessment.INCONCLUSIVE, "was assessed inconclusive"),
    ("completed", 7.45, AgentDecisionAssessment.FAIL, "was assessed fail"),
    ("completed", 9.5, None, "was rejected"),
    ("completed", None, None, "carries none of the approved update parameters"),
]


def _questionable(
    service: AgentSessionService,
    status: str,
    value: float | None,
    assessment: AgentDecisionAssessment | None,
) -> tuple[str, str]:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron", status=status, value=value)
    if assessment is not None:
        _decide(session_id, chevron, assessment, next_action=AgentDecisionNextAction.REQUEST_HUMAN)
    return session_id, chevron


@pytest.mark.parametrize(("status", "value", "assessment", "match"), QUESTIONABLE)
def test_a_questionable_result_stops_every_step_until_a_person_answers_about_it(
    service: AgentSessionService,
    status: str,
    value: float | None,
    assessment: AgentDecisionAssessment | None,
    match: str,
) -> None:
    session_id, chevron = _questionable(service, status, value, assessment)
    # Neither a dependent step nor a repeat of the same task starts.
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, match)
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="repeat"),
        409,
        f"attemptActionIds [{chevron}]",
    )
    # A new pass from the model does not clear it, and still commits nothing.
    if status == "completed" and value == 7.45:
        later = _decide(session_id, chevron, key="later-pass")
        _refused(
            lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="r2"),
            409,
            match,
        )
        _refused(lambda: _commit(service, session_id, chevron, later), 409, "never committed")
    # Answers that do not cite this action, or that stopped, clear nothing.
    _resume_intervention(session_id, ["another-action"], key="unrelated")
    _resume_intervention(session_id, [], key="uncited")
    _resume_intervention(
        session_id, [chevron], key="stopped", decision=AgentInterventionDecision.STOP
    )
    _refused(lambda: _measure(service, session_id, "CheckRabi", key="rabi-2"), 409, match)
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="r3"),
        409,
        match,
    )
    assert _stored_frequency() is None


@pytest.mark.parametrize(("status", "value", "assessment", "match"), QUESTIONABLE)
def test_an_answer_citing_the_action_allows_the_repeat_it_addresses_once(
    service: AgentSessionService,
    status: str,
    value: float | None,
    assessment: AgentDecisionAssessment | None,
    match: str,
) -> None:
    session_id, chevron = _questionable(service, status, value, assessment)
    _resume_intervention(session_id, [chevron])
    repeat = _measure(
        service,
        session_id,
        "CheckChevron",
        repeat_of=chevron,
        status=status,
        value=value,
        key="recovery",
    )
    if assessment is not None:
        _decide(session_id, repeat, assessment, next_action=AgentDecisionNextAction.REQUEST_HUMAN)
    # The repeat came out questionable too: it needs its own answer; the first one is spent.
    _refused(
        lambda: _measure(service, session_id, "CheckRabi", key="rabi-2"),
        409,
        f"attemptActionIds [{repeat}]",
    )
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=repeat, key="again"),
        409,
        match,
    )
    assert _stored_frequency() is None


@pytest.mark.parametrize(("status", "value", "assessment", "match"), QUESTIONABLE)
def test_an_answer_citing_the_action_lets_the_plan_continue_but_grants_no_commit(
    service: AgentSessionService,
    status: str,
    value: float | None,
    assessment: AgentDecisionAssessment | None,
    match: str,
) -> None:
    session_id, chevron = _questionable(service, status, value, assessment)
    _resume_intervention(session_id, [chevron])
    assert _measure(service, session_id, "CheckRabi", key="after-answer")
    if status == "completed" and value == 7.45:
        later = _decide(session_id, chevron, key="pass-after-answer")
        _refused(lambda: _commit(service, session_id, chevron, later), 409, "never committed")
    assert _stored_frequency() is None


def test_an_answer_given_before_the_problem_was_recorded_does_not_cover_it(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _resume_intervention(session_id, [chevron], at=now() - timedelta(seconds=30))
    _decide(
        session_id,
        chevron,
        AgentDecisionAssessment.INCONCLUSIVE,
        next_action=AgentDecisionNextAction.REQUEST_HUMAN,
    )
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, "was assessed inconclusive")


def test_successful_results_may_be_measured_again(service: AgentSessionService) -> None:
    session_id = _session(service)
    first = _measure(service, session_id, "CheckChevron")
    # A valid, not yet committed result: the repeat simply supersedes it.
    second = _measure(service, session_id, "CheckChevron", repeat_of=first, key="refine")
    _commit(service, session_id, second, _decide(session_id, second))
    # A committed result may also be measured again.
    assert _measure(service, session_id, "CheckChevron", repeat_of=second, key="third")


@pytest.mark.asyncio
async def test_unresolved_evidence_of_another_task_stops_commits_and_applies(
    service: AgentSessionService,
) -> None:
    session_id = _session(service, updates=GRANT.model_copy(update={"apply_backend": True}))
    rabi = _measure(service, session_id, "CheckRabi")
    chevron = _measure(service, session_id, "CheckChevron")
    passed = _decide(session_id, chevron)
    committed = _commit(service, session_id, chevron, passed)
    _decide(session_id, rabi, AgentDecisionAssessment.FAIL, key="rabi-fail")
    flow = _FlowService()
    await _refused_async(
        lambda: _apply(service, session_id, committed.commit_id, flow),
        409,
        f"attemptActionIds [{rabi}]",
    )
    assert flow.calls == []

    other = _session(service)
    rabi_2 = _measure(service, other, "CheckRabi", key="rabi")
    chevron_2 = _measure(service, other, "CheckChevron", key="chevron")
    _decide(other, rabi_2, AgentDecisionAssessment.INCONCLUSIVE, key="rabi-doubt")
    _refused(
        lambda: _commit(service, other, chevron_2, _decide(other, chevron_2), key="c2"),
        409,
        f"attemptActionIds [{rabi_2}]",
    )


def test_a_failed_step_blocks_downstream_steps_in_sessions_without_update_authority(
    service: AgentSessionService,
) -> None:
    session_id = _session(service, updates=None)
    _measure(service, session_id, "CheckChevron", status="failed", value=None)
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, "did not complete")
    # Without update authority a completed result does not wait for a commit.
    other = _session(service, updates=None)
    _measure(service, other, "CheckChevron")
    assert _measure(service, other, "CheckRabi")


def test_a_dependent_step_waits_for_the_granted_backend_apply(service: AgentSessionService) -> None:
    session_id = _session(service, updates=GRANT.model_copy(update={"apply_backend": True}))
    chevron = _measure(service, session_id, "CheckChevron")
    committed = _commit(service, session_id, chevron, _decide(session_id, chevron))
    _refused(
        lambda: _measure(service, session_id, "CheckRabi"), 409, "not applied to the backend yet"
    )
    collection = AgentCandidateCommitDocument.get_motor_collection()
    collection.update_one(
        {"commit_id": committed.commit_id}, {"$set": {"backend_status": "applying"}}
    )
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, "still in progress")
    collection.update_one(
        {"commit_id": committed.commit_id}, {"$set": {"backend_status": "failed"}}
    )
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, "apply of commit")
    collection.update_one(
        {"commit_id": committed.commit_id}, {"$set": {"backend_status": "applied"}}
    )
    assert _measure(service, session_id, "CheckRabi")


def test_a_paused_session_cannot_be_bypassed_with_a_new_auto_session(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id},
        {
            "$set": {
                "status": AgentSessionStatus.WAITING_FOR_HUMAN.value,
                "active_intervention_id": "iv-1",
            }
        },
    )
    _refused(lambda: _session(service), 409, f"{session_id} on chip-001 is paused for a person")
    # A reviewed session, approved per call, and another user's session are not blocked.
    assert _session(service, updates=None, autonomy=AgentAutonomy.CONFIRM_EACH)
    assert service.create_session(
        project_id=PROJECT,
        username="bob",
        body=CreateAgentSessionRequest(chip_id="chip-001", policy=_policy()),
    ).session_id


# --------------------------------------------------------------------------- evaluations


@pytest.mark.parametrize(
    ("status", "diagnosis", "disagree", "match"),
    [
        ("failed", None, False, "ended failed"),
        ("cancelled", None, False, "ended cancelled"),
        ("interrupted", None, False, "ended interrupted"),
        ("completed", None, False, "completed without a diagnosis"),
        ("completed", {}, False, "completed without a diagnosis"),
        (
            "completed",
            {**POSITIVE, "fit_reliability": {"assessment": "Unreliable"}},
            False,
            "judged the fit unreliable",
        ),
        (
            "completed",
            {**POSITIVE, "calibration_diagnosis": {"status": "FIT_FAILED"}},
            False,
            "reported FIT_FAILED",
        ),
        ("completed", POSITIVE, True, "A reviewer disagreed"),
    ],
)
def test_an_unusable_evaluation_refuses_the_update_and_stops_the_session(
    service: AgentSessionService,
    status: str,
    diagnosis: dict[str, Any] | None,
    disagree: bool,
    match: str,
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _evaluate(chevron, status=status, diagnosis=diagnosis, disagree=disagree)
    _refused(
        lambda: _commit(service, session_id, chevron, _decide(session_id, chevron)), 409, match
    )
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, match)
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="repeat"),
        409,
        f"attemptActionIds [{chevron}]",
    )
    assert _stored_frequency() is None


@pytest.mark.parametrize(
    ("status", "diagnosis", "match"),
    [
        ("running", None, "still running"),
        ("pending", None, "still pending"),
        (
            "completed",
            {"fit_reliability": {"assessment": "Reliable"}},
            "has no calibration_diagnosis answer",
        ),
        (
            "completed",
            {"calibration_diagnosis": {"status": "SUCCESS"}},
            "has no fit_reliability answer",
        ),
    ],
)
def test_a_pending_or_partial_evaluation_does_not_support_an_update(
    service: AgentSessionService, status: str, diagnosis: dict[str, Any] | None, match: str
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _evaluate(chevron, status=status, diagnosis=diagnosis)
    _refused(
        lambda: _commit(service, session_id, chevron, _decide(session_id, chevron)), 409, match
    )
    assert _stored_frequency() is None


def test_evidence_says_whether_an_evaluation_existed(service: AgentSessionService) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _evaluate(chevron, diagnosis=POSITIVE)
    supported = _commit(service, session_id, chevron, _decide(session_id, chevron))
    assert supported.assessment_evidence["evaluation_state"] == "supported"
    facts = supported.assessment_evidence["evaluations"]
    assert [(item["fit_reliability"], item["calibration_status"]) for item in facts] == [
        ("reliable", "SUCCESS")
    ]

    QubitDocument.get_motor_collection().update_one({"qid": "Q00"}, {"$set": {"data": {}}})
    other = _session(service)
    action = _measure(service, other, "CheckChevron")
    unevaluated = _commit(service, other, action, _decide(other, action), key="c2")
    # A new session records evaluation off: no evaluation was asked for, none is missing.
    assert unevaluated.assessment_evidence["evaluation_mode"] == "off"
    assert unevaluated.assessment_evidence["evaluation_state"] == "not_requested"
    assert unevaluated.assessment_evidence["evaluations"] == []
    assert supported.assessment_evidence["evaluations"][0]["evaluator_model"] == "vllm/qcal-vlm"

    # A session approved before evaluation modes keeps its record: no mode, state none.
    QubitDocument.get_motor_collection().update_one({"qid": "Q00"}, {"$set": {"data": {}}})
    legacy = _session(service)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": legacy}, {"$unset": {"policy.evaluation": ""}}
    )
    stored = AgentSessionDocument.find_one({"session_id": legacy}).run()
    assert stored is not None and stored.policy.evaluation is None
    action = _measure(service, legacy, "CheckChevron")
    old = _commit(service, legacy, action, _decide(legacy, action), key="c3")
    assert old.assessment_evidence["evaluation_mode"] is None
    assert old.assessment_evidence["evaluation_state"] == "none"


def test_a_required_evaluation_must_exist_complete_and_support_the_update(
    service: AgentSessionService,
) -> None:
    session_id = _session(service, evaluation=AgentEvaluationMode.REQUIRED)
    chevron = _measure(service, session_id, "CheckChevron")
    decision = _decide(session_id, chevron)
    # No evaluation: refused, and nothing is written.
    _refused(
        lambda: _commit(service, session_id, chevron, decision),
        409,
        "requires an evaluation of each result before an update",
    )
    # A spoofed request field cannot switch the approved mode off.
    with pytest.raises(HTTPException):
        service.commit_action_candidate(
            project_id=PROJECT,
            session_id=session_id,
            action_id=chevron,
            parameter_name="qubit_frequency",
            username=OWNER,
            body=CommitAgentCandidateRequest.model_validate(
                {
                    "idempotency_key": "spoof",
                    "expected_state_version": _version(session_id),
                    "task_id": _task_id(chevron),
                    "autonomous": True,
                    "decision_id": decision,
                    "evaluation": "off",
                }
            ),
        )
    assert _stored_frequency() is None
    # A pending evaluation makes the update wait.
    _evaluate(chevron, status="pending", key="ev-pending")
    _refused(lambda: _commit(service, session_id, chevron, decision), 409, "wait for it")
    EvaluationDocument.get_motor_collection().delete_one({"evaluation_id": "ev-pending"})

    _evaluate(chevron, diagnosis=POSITIVE)
    committed = _commit(service, session_id, chevron, decision)
    assert committed.status == "committed"
    evidence = committed.assessment_evidence
    assert (evidence["evaluation_mode"], evidence["evaluation_state"]) == (
        "required",
        "supported",
    )


def test_a_reviewed_commit_of_a_required_session_also_needs_the_evaluation(
    service: AgentSessionService,
) -> None:
    session_id = _session(service, updates=None, evaluation=AgentEvaluationMode.REQUIRED)
    chevron = _measure(service, session_id, "CheckChevron")
    _refused(
        lambda: _commit(service, session_id, chevron, None, autonomous=False),
        409,
        "requires an evaluation of each result before a commit",
    )
    _evaluate(chevron, status="failed")
    _refused(
        lambda: _commit(service, session_id, chevron, None, autonomous=False),
        409,
        "requires a completed evaluation",
    )
    assert _stored_frequency() is None


def test_evaluation_off_still_refuses_an_existing_negative_evaluation(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    stored = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert stored is not None and stored.policy.evaluation == AgentEvaluationMode.OFF
    chevron = _measure(service, session_id, "CheckChevron")
    _evaluate(
        chevron,
        diagnosis={
            "fit_reliability": {"assessment": "Unreliable"},
            "calibration_diagnosis": {"status": "SUCCESS"},
        },
    )
    _refused(
        lambda: _commit(service, session_id, chevron, _decide(session_id, chevron)),
        409,
        "judged the fit unreliable",
    )
    assert _stored_frequency() is None


# --------------------------------------------------------------------------- stored value


def test_a_change_without_calibrated_at_since_the_proposal_is_detected(
    service: AgentSessionService,
) -> None:
    QubitDocument.get_motor_collection().update_one(
        {"qid": "Q00"}, {"$set": {"data.qubit_frequency": {"value": 7.1, "unit": "GHz"}}}
    )
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    QubitDocument.get_motor_collection().update_one(
        {"qid": "Q00"}, {"$set": {"data.qubit_frequency.value": 7.2}}
    )
    _refused(
        lambda: _commit(service, session_id, chevron, _decide(session_id, chevron)),
        409,
        "may be stale",
    )
    assert _stored_frequency() == {"value": 7.2, "unit": "GHz"}


def test_an_action_without_a_recorded_baseline_is_not_committed_autonomously(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": chevron}, {"$unset": {"metadata.parameter_baseline": ""}}
    )
    _refused(
        lambda: _commit(service, session_id, chevron, _decide(session_id, chevron)),
        409,
        "recorded no stored qubit_frequency",
    )
    assert _stored_frequency() is None


def _external_write(value: float) -> None:
    """Another writer (a workflow result, a manual edit) saves the qubit's frequency."""
    QubitDocument.update_calib_data(
        username="bob",
        qid="Q00",
        chip_id="chip-001",
        output_parameters={"qubit_frequency": {"value": value, "unit": "GHz"}},
        project_id=PROJECT,
    )


def test_an_external_write_after_validation_is_never_overwritten(
    service: AgentSessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    decision = _decide(session_id, chevron)
    reserve = AgentSessionService._reserve_commit

    def reserve_then_external_write(*args: Any, **kwargs: Any) -> Any:
        result = reserve(*args, **kwargs)
        _external_write(7.3)
        return result

    monkeypatch.setattr(
        AgentSessionService, "_reserve_commit", staticmethod(reserve_then_external_write)
    )
    _refused(lambda: _commit(service, session_id, chevron, decision), 409, "nothing was written")
    assert _stored_frequency() == {"value": 7.3, "unit": "GHz"}
    commit = AgentCandidateCommitDocument.find_one({"session_id": session_id}).run()
    assert commit is not None
    assert commit.status == "failed"
    assert commit.after_snapshot is None


def test_a_reviewed_commit_also_writes_with_compare_and_set(
    service: AgentSessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qdash.dbmodel.agent_parameter_state import read_parameter as read

    session_id = _session(service, updates=None)
    chevron = _measure(service, session_id, "CheckChevron")

    def read_then_external_write(*args: Any) -> Any:
        stored = read(*args)
        _external_write(7.3)
        return stored

    monkeypatch.setattr(
        "qdash.api.services.agent_session_service.read_parameter", read_then_external_write
    )
    _refused(
        lambda: _commit(service, session_id, chevron, None, autonomous=False),
        409,
        "nothing was written",
    )
    assert _stored_frequency() == {"value": 7.3, "unit": "GHz"}


def test_a_commit_leaves_other_parameters_written_meanwhile(
    service: AgentSessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    decision = _decide(session_id, chevron)
    reserve = AgentSessionService._reserve_commit

    def reserve_then_other_write(*args: Any, **kwargs: Any) -> Any:
        result = reserve(*args, **kwargs)
        QubitDocument.get_motor_collection().update_one(
            {"qid": "Q00"}, {"$set": {"data.t1": {"value": 80.0}}}
        )
        return result

    monkeypatch.setattr(
        AgentSessionService, "_reserve_commit", staticmethod(reserve_then_other_write)
    )
    committed = _commit(service, session_id, chevron, decision)
    assert committed.status == "committed"
    qubit = QubitDocument.find_one({"qid": "Q00"}).run()
    assert qubit is not None
    assert qubit.data["t1"] == {"value": 80.0}
    assert qubit.data["qubit_frequency"]["value"] == 7.45


# --------------------------------------------------------------------------- apply lease


@pytest.mark.asyncio
async def test_backend_applies_on_a_chip_are_serialized(service: AgentSessionService) -> None:
    flow = _FlowService()
    grant = GRANT.model_copy(update={"apply_backend": True})
    first_session = _session(service, updates=grant)
    first_action = _measure(service, first_session, "CheckChevron")
    first = _commit(service, first_session, first_action, _decide(first_session, first_action))
    queued = await _apply(service, first_session, first.commit_id, flow)
    assert queued.backend_status == "queued"
    lock = AgentBackendApplyLockDocument.find_one({"lock_key": apply_lock_key("chip-001")}).run()
    assert lock is not None
    assert lock.commit_id == first.commit_id

    # Another reviewed apply on the chip waits and leaves its commit unrequested.
    second_session = _session(service, updates=None)
    second_action = _measure(service, second_session, "CheckChevron")
    reviewed = _commit(service, second_session, second_action, None, autonomous=False, key="c2")
    await _refused_async(
        lambda: _apply(service, second_session, reviewed.commit_id, flow, autonomous=False),
        409,
        f"commit {first.commit_id} on chip chip-001 has not settled",
    )
    stored = AgentCandidateCommitDocument.find_one({"commit_id": reviewed.commit_id}).run()
    assert stored is not None
    assert stored.backend_status == "not_started"
    assert stored.backend_apply_idempotency_key is None
    assert len(flow.calls) == 1

    # Once the first apply settled, a lease its worker failed to release is stale.
    AgentCandidateCommitDocument.get_motor_collection().update_one(
        {"commit_id": first.commit_id}, {"$set": {"backend_status": "applied"}}
    )
    retried = await _apply(
        service, second_session, reviewed.commit_id, flow, autonomous=False, key="apply-2"
    )
    assert retried.backend_status == "queued"
    lock = AgentBackendApplyLockDocument.find_one({"lock_key": apply_lock_key("chip-001")}).run()
    assert lock is not None
    assert lock.commit_id == reviewed.commit_id


@pytest.mark.asyncio
async def test_a_refused_dispatch_releases_the_lease(service: AgentSessionService) -> None:
    class _FailingFlow(_FlowService):
        async def execute_agent_candidate_apply(self, **kwargs: object) -> object:
            raise RuntimeError("deployment unavailable")

    session_id = _session(service, updates=GRANT.model_copy(update={"apply_backend": True}))
    chevron = _measure(service, session_id, "CheckChevron")
    committed = _commit(service, session_id, chevron, _decide(session_id, chevron))
    with pytest.raises(RuntimeError, match="deployment unavailable"):
        await _apply(service, session_id, committed.commit_id, _FailingFlow())
    assert AgentBackendApplyLockDocument.find({}).count() == 0


# --------------------------------------------------------------------------- incomplete evidence


@pytest.mark.parametrize(
    ("diagnosis", "match"),
    [
        ({"fit_reliability": {"assessment": "Reliable"}}, "has no calibration_diagnosis answer"),
        ({"calibration_diagnosis": {"status": "SUCCESS"}}, "has no fit_reliability answer"),
    ],
)
@pytest.mark.asyncio
async def test_an_incomplete_evaluation_stops_commits_applies_and_every_step(
    service: AgentSessionService, diagnosis: dict[str, Any], match: str
) -> None:
    session_id = _session(service, updates=GRANT.model_copy(update={"apply_backend": True}))
    chevron = _measure(service, session_id, "CheckChevron")
    committed = _commit(service, session_id, chevron, _decide(session_id, chevron))
    # An evaluation recorded after the commit completed without both answers.
    _evaluate(chevron, diagnosis=diagnosis)
    flow = _FlowService()
    await _refused_async(
        lambda: _apply(service, session_id, committed.commit_id, flow),
        409,
        f"attemptActionIds [{chevron}]",
    )
    assert flow.calls == []
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, match)
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="repeat"),
        409,
        f"attemptActionIds [{chevron}]",
    )

    # Before any commit, the commit itself is refused and the session stops too.
    QubitDocument.get_motor_collection().update_one({"qid": "Q00"}, {"$set": {"data": {}}})
    other = _session(service)
    action = _measure(service, other, "CheckChevron", key="other")
    _evaluate(action, diagnosis=diagnosis, key="ev-other")
    passed = _decide(other, action)
    _refused(lambda: _commit(service, other, action, passed, key="c2"), 409, match)
    _refused(lambda: _measure(service, other, "CheckRabi", key="rabi"), 409, match)
    _refused(
        lambda: _measure(service, other, "CheckChevron", repeat_of=action, key="again"),
        409,
        f"attemptActionIds [{action}]",
    )
    # A person's answer allows the repeat, but never makes this result committable.
    _resume_intervention(other, [action])
    _refused(lambda: _commit(service, other, action, passed, key="c3"), 409, match)
    assert _measure(service, other, "CheckChevron", repeat_of=action, key="recovery")
    assert _stored_frequency() is None


@pytest.mark.parametrize("later_requested_first", [False, True])
def test_an_earlier_answer_never_clears_a_later_failed_evaluation(
    service: AgentSessionService, later_requested_first: bool
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    start = now()
    first_done = start - timedelta(seconds=60)
    later_done = start + timedelta(seconds=60)
    # Evaluations are read by request time; either may come first.
    first_requested = start - timedelta(seconds=90 if not later_requested_first else 30)
    later_requested = start - timedelta(seconds=30 if not later_requested_first else 90)
    _evaluate(chevron, status="failed", key="ev-a", at=first_done, requested_at=first_requested)
    _evaluate(
        chevron,
        diagnosis={**POSITIVE, "calibration_diagnosis": {"status": "FIT_FAILED"}},
        key="ev-b",
        at=later_done,
        requested_at=later_requested,
    )
    # The expert answered after the first failure but before the second one.
    _resume_intervention(session_id, [chevron], key="early", at=start)
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="r1"),
        409,
        f"attemptActionIds [{chevron}]",
    )
    _refused(lambda: _measure(service, session_id, "CheckRabi", key="rabi"), 409, "FIT_FAILED")
    # An answer at exactly the latest problem covers both; it grants no commit.
    _resume_intervention(session_id, [chevron], key="matching", at=later_done)
    assert _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="r2")
    assert _stored_frequency() is None


def test_a_later_decision_or_reviewer_verdict_reopens_an_answered_action(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _evaluate(chevron, status="failed", key="ev-a", at=now() - timedelta(seconds=60))
    _resume_intervention(session_id, [chevron], key="first", at=now() - timedelta(seconds=30))
    # The answer covers the failed evaluation...
    assert _measure(service, session_id, "CheckRabi", key="rabi")
    # ...but not an uncertain assessment recorded after it.
    _decide(
        session_id,
        chevron,
        AgentDecisionAssessment.INCONCLUSIVE,
        next_action=AgentDecisionNextAction.REQUEST_HUMAN,
    )
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="r1"),
        409,
        "was assessed inconclusive",
    )
    _resume_intervention(session_id, [chevron], key="second", at=now() + timedelta(seconds=5))
    assert _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="r2")

    # A reviewer disagreeing later with an evaluation that was positive reopens it too.
    other = _session(service)
    action = _measure(service, other, "CheckChevron", key="other")
    _evaluate(action, status="failed", key="ev-c", at=now() - timedelta(seconds=60))
    _evaluate(action, diagnosis=POSITIVE, key="ev-d", at=now() - timedelta(seconds=50))
    _resume_intervention(other, [action], key="third", at=now() - timedelta(seconds=30))
    assert _measure(service, other, "CheckRabi", key="other-rabi")
    EvaluationDocument.get_motor_collection().update_one(
        {"evaluation_id": "ev-d"},
        {
            "$set": {
                "verdicts": [
                    EvaluationVerdictModel(
                        agree=False, username="reviewer", updated_at=now() + timedelta(seconds=5)
                    ).model_dump()
                ]
            }
        },
    )
    _refused(
        lambda: _measure(service, other, "CheckChevron", repeat_of=action, key="o1"),
        409,
        "A reviewer disagreed",
    )


def test_a_settled_evaluation_without_a_completion_time_is_never_covered(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _evaluate(chevron, status="failed", key="ev-a")
    EvaluationDocument.get_motor_collection().update_one(
        {"evaluation_id": "ev-a"}, {"$set": {"completed_at": None}}
    )
    _resume_intervention(session_id, [chevron], at=now() + timedelta(days=1))
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="r1"),
        409,
        "cannot tell when",
    )


def _untimed_verdicts(monkeypatch: pytest.MonkeyPatch, key: str, verdicts: dict[str, Any]) -> None:
    """Serve evaluation ``key`` with reviewer verdicts a legacy or damaged record may carry.

    The stored model requires ``updated_at``, so a verdict without a provable time is built
    without validation, as a lenient read of an old document would return it.
    """
    original = AgentSessionService._evaluations_of

    def read(action: Any) -> list[EvaluationDocument]:
        return [
            item.model_copy(update=verdicts) if item.evaluation_id == key else item
            for item in original(action)
        ]

    monkeypatch.setattr(AgentSessionService, "_evaluations_of", staticmethod(read))


def _verdict(updated_at: Any) -> EvaluationVerdictModel:
    return EvaluationVerdictModel.model_construct(
        agree=True, note=None, issues=[], username="reviewer", updated_at=updated_at
    )


@pytest.mark.parametrize("field", ["verdict", "verdicts", "verdict_history"])
@pytest.mark.parametrize("mixed", [False, True], ids=["untimed", "known-and-untimed"])
def test_an_untimed_reviewer_verdict_makes_a_failed_evaluation_uncoverable(
    service: AgentSessionService, monkeypatch: pytest.MonkeyPatch, field: str, mixed: bool
) -> None:
    session_id = _session(service)
    rabi = _measure(service, session_id, "CheckRabi")
    chevron = _measure(service, session_id, "CheckChevron")
    passed = _decide(session_id, chevron)
    # The evaluation failed at a known time, but one extant verdict has no provable time.
    _evaluate(rabi, status="failed", key="ev-a", at=now() - timedelta(seconds=60))
    known = _verdict(now() - timedelta(seconds=50))
    untimed = _verdict(None) if mixed else _verdict("not-a-time")
    if field == "verdict":
        update: dict[str, Any] = {"verdict": untimed}
        if mixed:
            update["verdicts"] = [known]
    else:
        update = {field: [known, untimed] if mixed else [untimed]}
    _untimed_verdicts(monkeypatch, "ev-a", update)
    # A later answer cannot be shown to come after the untimed verdict.
    _resume_intervention(session_id, [rabi], at=now() + timedelta(days=1))
    _refused(
        lambda: _measure(service, session_id, "CheckChevron", repeat_of=chevron, key="c2"),
        409,
        "cannot tell when",
    )
    _refused(
        lambda: _measure(service, session_id, "CheckRabi", repeat_of=rabi, key="r1"),
        409,
        "cannot tell when",
    )
    _refused(lambda: _commit(service, session_id, chevron, passed), 409, "cannot tell when")
    assert _stored_frequency() is None


@pytest.mark.parametrize("verdicts", ["absent", "timed"])
def test_a_failed_evaluation_with_absent_or_timed_verdicts_is_covered_by_a_later_answer(
    service: AgentSessionService, monkeypatch: pytest.MonkeyPatch, verdicts: str
) -> None:
    session_id = _session(service)
    rabi = _measure(service, session_id, "CheckRabi")
    chevron = _measure(service, session_id, "CheckChevron")
    passed = _decide(session_id, chevron)
    _evaluate(rabi, status="failed", key="ev-a", at=now() - timedelta(seconds=60))
    latest = now() - timedelta(seconds=20)
    if verdicts == "timed":
        _untimed_verdicts(
            monkeypatch,
            "ev-a",
            {
                "verdict": _verdict(latest),
                "verdicts": [_verdict(now() - timedelta(seconds=40))],
                "verdict_history": [_verdict(now() - timedelta(seconds=50)), _verdict(latest)],
            },
        )
        # An answer before the latest verdict does not cover it.
        _resume_intervention(session_id, [rabi], key="early", at=now() - timedelta(seconds=30))
        _refused(lambda: _commit(service, session_id, chevron, passed), 409, "attemptActionIds")
    _resume_intervention(session_id, [rabi], key="late", at=now() - timedelta(seconds=10))
    committed = _commit(service, session_id, chevron, passed)
    assert committed.status == "committed"


def test_an_answer_covers_a_failure_but_waits_for_a_running_evaluation(
    service: AgentSessionService,
) -> None:
    session_id = _session(service)
    chevron = _measure(service, session_id, "CheckChevron")
    _evaluate(chevron, status="failed", key="ev-a", at=now() - timedelta(seconds=60))
    _evaluate(chevron, status="running", key="ev-b", requested_at=now() - timedelta(seconds=50))
    _resume_intervention(session_id, [chevron], at=now() - timedelta(seconds=30))
    _refused(lambda: _measure(service, session_id, "CheckRabi"), 409, "still running")
