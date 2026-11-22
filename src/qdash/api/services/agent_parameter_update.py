"""Checks for parameter updates made under a session's ``parameter_updates`` authority.

A person approves a session's update authority once, when the session is created
(``AgentSessionPolicy.parameter_updates``). The agent may then commit, and with
``apply_backend`` apply, the candidates of passing measurements without asking again. These
checks are what keeps that authority narrow:

- only the signed-in creator of the ``auto`` session uses it, and only for the approved
  parameters, tasks, and qubits;
- every update rests on an explicit ``pass`` assessment the agent recorded for exactly that
  measurement, on every existing evaluation of the result being completed with a reliable fit
  and a ``SUCCESS`` diagnosis and no reviewer disagreeing, and on QDash's own mechanical
  gates: the task completed (so its own checks, such as an R² threshold, passed), the
  candidate is inside the approved bounds, and the session's quality gates hold;
- the stored value must still be the one recorded when the measurement was proposed, and the
  commit writes with a compare-and-set against exactly that value
  (``qdash.dbmodel.agent_parameter_state``).

Unresolved evidence stops the session. A run of the session that settled without
completing, a result any decision assessed ``fail`` or ``inconclusive``, an evaluation that
failed, was cancelled or interrupted, has no diagnosis, judged the fit unreliable, reported a
status other than ``SUCCESS``, completed without both a fit-reliability and a diagnosis
answer, or that a reviewer disputed, and, for a granted task, a result whose candidates
cannot be read, carry no granted parameter, or were rejected, each refuse every autonomous
step, commit, and apply of the session (``unresolved_evidence``). An evaluation still
pending or running only makes the session wait. Only a person clears unresolved evidence: an
intervention answered with ``resume`` that cites exactly that action in its attempts,
answered at or after the latest of all the action's problems was recorded. An answer given
before a later failure, diagnosis, or reviewer verdict of the same action does not cover it.
Repeating the task, recording a new ``pass``, or answering an unrelated intervention does not
clear it, and the answer never makes the result committable.

A dependent step (a different task on the same qubit) also waits while the newest valid
result of another granted task has an accepted granted candidate that is not committed or,
with ``apply_backend``, not applied (``dependency_refusal``). A person's answer does not skip
that: the value is committed and applied, through this authority or the reviewed calls.

The ``pass`` is the agent's reading, recorded as ``agent_reported``. The gates are mechanical
and are not a scientific verdict either; the audit says which is which.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from bunnet import SortDirection
from fastapi import HTTPException, status

from qdash.api.services.agent_session_gate import (
    IN_FLIGHT_BACKEND_STATUSES,
    SETTLED_EXECUTION_STATUSES,
    autonomous_session_refusal,
)
from qdash.datamodel.agent_session import (
    AgentDecisionAssessment,
    AgentDecisionNextAction,
    AgentInterventionDecision,
    AgentInterventionStatus,
    AgentParameterUpdatePolicy,
)
from qdash.dbmodel.agent_parameter_state import (
    StoredParameter,
    parameter_matches,
    read_parameter,
)
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCandidateCommitDocument,
    AgentDecisionDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from qdash.api.schemas.agent_session import AgentCandidateResponse
    from qdash.dbmodel.evaluation import EvaluationDocument

    CandidatesOf = Callable[[str], Sequence[AgentCandidateResponse]]
    EvaluationsOf = Callable[[AgentActionDocument], Sequence[EvaluationDocument]]

EVIDENCE_SCHEMA = "qdash.agent-update-evidence.v2"
# Where an autonomous run_task of a granted task records the stored values it measured from.
BASELINE_METADATA_KEY = "parameter_baseline"
# Next steps a pass decision may name when it leads to an update.
UPDATE_NEXT_ACTIONS = frozenset(
    {
        AgentDecisionNextAction.PROPOSE_COMMIT,
        AgentDecisionNextAction.NEXT_TASK,
        AgentDecisionNextAction.COMPLETE,
    }
)
UNCERTAIN_ASSESSMENTS = frozenset(
    {AgentDecisionAssessment.FAIL, AgentDecisionAssessment.INCONCLUSIVE}
)
# Evaluation statuses that are still producing evidence.
PENDING_EVALUATION_STATUSES = frozenset({"pending", "running"})
# The positive answers an evaluation must give before its result can ground an update.
RELIABLE_FIT = "reliable"
SUCCESS_DIAGNOSIS = "SUCCESS"
# Intervention states that hold a person's resume answer.
RESUMED_INTERVENTION_STATUSES = frozenset(
    {AgentInterventionStatus.RESUME_AUTHORIZED, AgentInterventionStatus.RESUMED}
)
# Commit statuses that hold, or are about to hold, a value.
LIVE_COMMIT_STATUSES = ("reserving", "committing", "committed")
EVIDENCE_NOTE = (
    "The pass assessment is the agent's reading of the result. QDash checked task "
    "completion, the approved bounds, the session's quality gates, and the completion and "
    "diagnosis of any evaluation of the result; those are mechanical checks, not a "
    "scientific verdict."
)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _utc(value: Any) -> datetime | None:
    """A stored timestamp as an aware UTC datetime; QDash stores naive UTC."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: Any) -> str | None:
    parsed = _utc(value)
    return parsed.isoformat() if parsed is not None else None


def update_authority(session: AgentSessionDocument, username: str) -> AgentParameterUpdatePolicy:
    """The session's update authority for ``username``, or a refusal.

    ``username`` is the request's authenticated user, never a value the agent supplies.
    """
    autonomous_session_refusal(session, username)
    updates = session.policy.parameter_updates
    if updates is None:
        raise _conflict(
            "The session's approval did not grant parameter updates. Commit or apply with the "
            "reviewed call a person approves each time, or start a session whose approval "
            "grants them."
        )
    return updates


def _session_decisions(project_id: str, session_id: str) -> list[AgentDecisionDocument]:
    return cast(
        "list[AgentDecisionDocument]",
        AgentDecisionDocument.find(
            {"project_id": project_id, "session_id": session_id},
            sort=[("recorded_at", SortDirection.ASCENDING)],
        ).run(),
    )


# --------------------------------------------------------------------------- evaluations


def _evaluation_facts(evaluation: EvaluationDocument) -> dict[str, Any]:
    output = evaluation.output
    diagnosis = output.diagnosis if output is not None else None
    usable = diagnosis if isinstance(diagnosis, dict) and diagnosis else None
    fit = usable.get("fit_reliability") if usable else None
    fit_assessment = fit.get("assessment") if isinstance(fit, dict) else None
    calibration = usable.get("calibration_diagnosis") if usable else None
    calibration_status = calibration.get("status") if isinstance(calibration, dict) else None
    return {
        "evaluation_id": evaluation.evaluation_id,
        "status": str(evaluation.status),
        "diagnosis_present": usable is not None,
        "fit_reliability": str(fit_assessment).strip().lower()[:64] if fit_assessment else None,
        "calibration_status": (
            str(calibration_status).strip().upper()[:64] if calibration_status else None
        ),
        "fallback_model": bool(output.fallback) if output is not None else False,
        "reviewer_disagreed": any(verdict.agree is False for verdict in evaluation.verdicts),
        "completed_at": _iso(evaluation.completed_at),
        "provenance": "evaluator_reported",
    }


@dataclass(frozen=True)
class EvaluationProblem:
    """Why an evaluation cannot ground an update.

    ``kind`` is ``wait`` (still running), ``unusable`` (failed, interrupted, cancelled,
    without a diagnosis, negative, or disputed), or ``insufficient`` (completed, but without
    both positive answers an update needs). ``unusable`` and ``insufficient`` both stop the
    session until a person answers; they differ only in the refusal a commit reports.
    """

    kind: str
    detail: str
    at: datetime | None


def evaluation_problem(facts: dict[str, Any]) -> EvaluationProblem | None:
    """Classify one evaluation's facts; None when it supports an update."""
    label = f"Evaluation {facts['evaluation_id']}"
    at = _utc(facts.get("completed_at"))
    status_value = facts["status"]
    if status_value in PENDING_EVALUATION_STATUSES:
        return EvaluationProblem("wait", f"{label} of this result is still {status_value}", at)
    if facts["reviewer_disagreed"]:
        return EvaluationProblem("unusable", f"A reviewer disagreed with {label.lower()}", at)
    if status_value != "completed":
        return EvaluationProblem("unusable", f"{label} ended {status_value}", at)
    if not facts["diagnosis_present"]:
        return EvaluationProblem("unusable", f"{label} completed without a diagnosis", at)
    fit = facts["fit_reliability"]
    diagnosis = facts["calibration_status"]
    if fit is not None and fit != RELIABLE_FIT:
        return EvaluationProblem("unusable", f"{label} judged the fit {fit}", at)
    if diagnosis is not None and diagnosis != SUCCESS_DIAGNOSIS:
        return EvaluationProblem("unusable", f"{label} reported {diagnosis}", at)
    if fit is None or diagnosis is None:
        missing = " and ".join(
            name
            for name, value in (("fit_reliability", fit), ("calibration_diagnosis", diagnosis))
            if value is None
        )
        return EvaluationProblem(
            "insufficient", f"{label} has no {missing} answer, so it does not support an update", at
        )
    return None


# --------------------------------------------------------------------------- dispositions


def _dispositions(project_id: str, session_id: str) -> dict[str, list[tuple[str, datetime]]]:
    """A person's resume answers, by each run_task action the intervention cites.

    Only an intervention answered with ``resume`` counts, and it covers only the actions its
    attempts (or its own action reference) name; QDash checked those references when the
    intervention was opened.
    """
    interventions = cast(
        "list[AgentInterventionDocument]",
        AgentInterventionDocument.find({"project_id": project_id, "session_id": session_id}).run(),
    )
    covered: dict[str, list[tuple[str, datetime]]] = {}
    for item in interventions:
        response = item.response
        if (
            response is None
            or response.decision != AgentInterventionDecision.RESUME
            or item.status not in RESUMED_INTERVENTION_STATUSES
        ):
            continue
        answered = _utc(response.responded_at)
        if answered is None:
            continue
        cited = {attempt.action_id for attempt in item.attempts if attempt.action_id}
        if item.action_id:
            cited.add(item.action_id)
        for action_id in cited:
            covered.setdefault(action_id, []).append((item.intervention_id, answered))
    return covered


@dataclass(frozen=True)
class _ActionProblem:
    """Unresolved evidence of one action, and when its latest part was recorded.

    ``since`` is the latest time any of the action's problems was recorded: a person's answer
    clears the action only when it was given at or after ``since``, so an earlier answer never
    covers a later failure. ``since`` is None when QDash cannot tell when a problem was
    recorded; then no answer covers it.
    """

    detail: str | None
    since: datetime | None
    wait: str | None = None


def _label(action: AgentActionDocument) -> str:
    qid = action.qids[0] if action.qids else "?"
    return f"{action.task_name} on {qid} (action {action.action_id})"


def _evaluation_recorded_at(evaluation: EvaluationDocument) -> datetime | None:
    """The latest time anything about ``evaluation`` changed, or None when unprovable.

    A settled evaluation records ``completed_at`` when its status and diagnosis are written,
    and every reviewer verdict records ``updated_at``. The time is unprovable, and None, when
    a settled evaluation has no ``completed_at`` or when any extant reviewer verdict (current,
    per reviewer, or history) has no ``updated_at``: that verdict may have been written after
    every known time, so no answer can be shown to come after it. An absent verdict is fine.
    """
    completed = _utc(evaluation.completed_at)
    if completed is None and str(evaluation.status) not in PENDING_EVALUATION_STATUSES:
        return None
    verdicts = [
        *evaluation.verdicts,
        *evaluation.verdict_history,
        *([evaluation.verdict] if evaluation.verdict is not None else []),
    ]
    verdict_stamps = [_utc(item.updated_at) for item in verdicts]
    if any(stamp is None for stamp in verdict_stamps):
        return None
    stamps = [
        stamp
        for stamp in (
            completed,
            _utc(evaluation.started_at),
            _utc(evaluation.requested_at),
            *verdict_stamps,
        )
        if stamp is not None
    ]
    return max(stamps) if stamps else None


def _action_problem(
    action: AgentActionDocument,
    *,
    decisions: list[AgentDecisionDocument],
    updates: AgentParameterUpdatePolicy | None,
    candidates_of: CandidatesOf,
    evaluations_of: EvaluationsOf,
) -> _ActionProblem | None:
    """The unresolved evidence of one settled run, or None.

    Every problem of the run is collected, not just the first one, and the latest time any
    of them was recorded becomes ``since``. An evaluation still pending or running makes the
    run wait; an evaluation that completed without both positive answers is unresolved
    evidence, like a failed one.
    """
    label = _label(action)
    settled_at = _utc(action.created_at)
    details: list[str] = []
    stamps: list[datetime | None] = []
    waiting: list[str] = []

    def stop(detail: str, at: datetime | None) -> None:
        details.append(detail)
        stamps.append(at)

    completed = action.execution_status == "completed"
    if not completed:
        stop(f"{label} did not complete ({action.execution_status})", settled_at)
    uncertain = [
        item
        for item in decisions
        if action.action_id in item.evidence_action_ids and item.assessment in UNCERTAIN_ASSESSMENTS
    ]
    for item in uncertain:
        stamps.append(_utc(item.recorded_at))
    if uncertain:
        latest = uncertain[-1]
        assessed = latest.assessment.value if latest.assessment else ""
        details.append(f"{label} was assessed {assessed} (decision {latest.decision_id})")
    for evaluation in evaluations_of(action):
        problem = evaluation_problem(_evaluation_facts(evaluation))
        if problem is None:
            continue
        if problem.kind == "wait":
            waiting.append(f"{problem.detail} ({label})")
            continue
        stop(f"{problem.detail} ({label})", _evaluation_recorded_at(evaluation))
    if completed and updates is not None and action.task_name in updates.tasks:
        try:
            candidates = candidates_of(action.action_id)
        except HTTPException as exc:
            stop(f"The result of {label} cannot be read ({exc.detail})", settled_at)
        else:
            granted = [item for item in candidates if item.parameter_name in updates.parameters]
            if not granted:
                stop(
                    f"The result of {label} carries none of the approved update parameters "
                    f"({', '.join(updates.parameters)})",
                    settled_at,
                )
            for candidate in granted:
                if not candidate.accepted:
                    stop(
                        f"The {candidate.parameter_name} candidate of {label} was rejected "
                        f"({candidate.reason})",
                        settled_at,
                    )
    wait = waiting[0] if waiting else None
    if details:
        known = [stamp for stamp in stamps if stamp is not None]
        since = max(known) if known and len(known) == len(stamps) else None
        return _ActionProblem("; ".join(details), since, wait)
    if wait is not None:
        return _ActionProblem(None, None, wait)
    return None


@dataclass(frozen=True)
class EvidenceReview:
    """The session's settled runs, sorted into unresolved, resolved, and valid ones."""

    refusal: str | None
    resolved: frozenset[str]


def review_evidence(
    *,
    session: AgentSessionDocument,
    actions: list[AgentActionDocument],
    candidates_of: CandidatesOf,
    evaluations_of: EvaluationsOf,
) -> EvidenceReview:
    """Whether unresolved evidence stops the session, and which runs a person resolved.

    ``actions`` are the session's authorized run_task actions with fresh run status, oldest
    first. A run with unresolved evidence stops every autonomous step, commit, and apply of
    the session until a person answers an intervention that cites it with ``resume``.
    """
    decisions = _session_decisions(session.project_id, session.session_id)
    dispositions = _dispositions(session.project_id, session.session_id)
    updates = session.policy.parameter_updates
    resolved: set[str] = set()
    for action in actions:
        if action.execution_status == "not_started" or (
            action.execution_status not in SETTLED_EXECUTION_STATUSES
        ):
            continue
        problem = _action_problem(
            action,
            decisions=decisions,
            updates=updates,
            candidates_of=candidates_of,
            evaluations_of=evaluations_of,
        )
        if problem is None:
            continue
        if problem.detail is not None:
            since = problem.since
            answered = since is not None and any(
                at >= since for _, at in dispositions.get(action.action_id, [])
            )
            if not answered:
                untimed = (
                    " QDash cannot tell when part of this evidence was recorded, so no answer "
                    "covers it; end the session and start a new one after a person reviews it."
                    if since is None
                    else ""
                )
                return EvidenceReview(
                    f"{problem.detail}. QDash stops this session's autonomous steps, commits, "
                    "and applies until a person answers an intervention about it: call "
                    f"qdash_request_agent_human with attemptActionIds [{action.action_id}]. "
                    "Repeating the task, a new assessment, or an answer to an intervention "
                    "that does not cite this action, or that was given before the latest "
                    f"problem was recorded, does not clear it.{untimed}",
                    frozenset(resolved),
                )
        if problem.wait is not None:
            return EvidenceReview(
                f"{problem.wait}; wait for it before the next autonomous step or update",
                frozenset(resolved),
            )
        resolved.add(action.action_id)
    return EvidenceReview(None, frozenset(resolved))


# --------------------------------------------------------------------------- commits


@dataclass(frozen=True)
class CommitGrounds:
    """What an autonomous commit rests on: its frozen evidence and the value it replaces."""

    evidence: dict[str, Any]
    baseline: StoredParameter


def record_baseline(
    session: AgentSessionDocument, task_name: str | None, qid: str | None
) -> dict[str, Any] | None:
    """The stored granted values a granted task measures from, for the action's metadata."""
    updates = session.policy.parameter_updates
    if updates is None or not task_name or not qid or task_name not in updates.tasks:
        return None
    baseline: dict[str, Any] = {}
    for name in updates.parameters:
        stored = read_parameter(session.project_id, session.chip_id, qid, name)
        if stored is None:
            return None
        baseline[name] = stored.as_record()
    return baseline


def check_commit(
    *,
    session: AgentSessionDocument,
    updates: AgentParameterUpdatePolicy,
    action: AgentActionDocument,
    candidate: AgentCandidateResponse,
    decision_id: str,
    session_run_tasks: list[AgentActionDocument],
    candidates_of: CandidatesOf,
    evaluations_of: EvaluationsOf,
) -> CommitGrounds:
    """Refuse an autonomous commit QDash cannot ground; else what to freeze with it."""
    task_name = action.task_name or ""
    qid = action.qids[0] if action.qids else ""
    if candidate.parameter_name not in updates.parameters:
        raise _conflict(
            f"The session's approval does not grant updates of '{candidate.parameter_name}' "
            f"(granted: {', '.join(updates.parameters)})"
        )
    if task_name not in updates.tasks:
        raise _conflict(
            f"The session's approval does not grant updates from {task_name} "
            f"(granted: {', '.join(updates.tasks)})"
        )
    if action.execution_status != "completed":
        raise _conflict(
            f"Action {action.action_id} did not complete ({action.execution_status}); only a "
            "completed measurement can supply an update"
        )
    if not candidate.accepted:
        raise _conflict(f"Candidate gate rejected the value: {candidate.reason}")

    running = [
        other.action_id
        for other in session_run_tasks
        if other.execution_status != "not_started"
        and other.execution_status not in SETTLED_EXECUTION_STATUSES
    ]
    if running:
        raise _conflict(
            f"Action {', '.join(running)} of the session is still running; wait for it before "
            "an update"
        )
    same_target = [
        other
        for other in session_run_tasks
        if other.task_name == task_name
        and qid in other.qids
        and other.execution_status in SETTLED_EXECUTION_STATUSES
        and other.execution_status != "not_started"
    ]
    if same_target and same_target[-1].action_id != action.action_id:
        raise _conflict(
            f"Action {same_target[-1].action_id} measured {task_name} on {qid} after action "
            f"{action.action_id}; only the newest result of a task and qubit is committed"
        )

    existing = AgentCandidateCommitDocument.find_one(
        {
            "project_id": session.project_id,
            "session_id": session.session_id,
            "action_id": action.action_id,
            "parameter_name": candidate.parameter_name,
            "status": {"$in": list(LIVE_COMMIT_STATUSES)},
        }
    ).run()
    if existing is not None:
        raise _conflict(
            f"Candidate '{candidate.parameter_name}' of action {action.action_id} was already "
            f"committed (commit {existing.commit_id})"
        )

    decisions = _session_decisions(session.project_id, session.session_id)
    decision = next((item for item in decisions if item.decision_id == decision_id), None)
    if decision is None:
        raise _conflict(f"Decision '{decision_id}' is not a decision of this session")
    if decision.recorded_by != session.created_by:
        raise _conflict("The decision was not recorded by the session's creator")
    if action.action_id not in decision.evidence_action_ids:
        raise _conflict(
            f"Decision {decision_id} does not cite action {action.action_id} as its evidence"
        )
    if decision.assessment != AgentDecisionAssessment.PASS:
        assessed = decision.assessment.value if decision.assessment else "not stated"
        raise _conflict(
            f"Decision {decision_id} assessed the result as {assessed}; only an explicit pass "
            "can ground an update. Ask a person with an intervention instead."
        )
    if decision.next_action not in UPDATE_NEXT_ACTIONS:
        raise _conflict(
            f"Decision {decision_id} chose {decision.next_action.value}, which does not lead "
            "to an update"
        )
    if any(item.supersedes_decision_id == decision_id for item in decisions):
        raise _conflict(f"Decision {decision_id} was superseded by a later decision")
    citing = [item for item in decisions if action.action_id in item.evidence_action_ids]
    uncertain = [item for item in citing if item.assessment in UNCERTAIN_ASSESSMENTS]
    if uncertain:
        first = uncertain[0]
        raise _conflict(
            f"Decision {first.decision_id} assessed action {action.action_id} as "
            f"{first.assessment.value if first.assessment else ''}; a failed or uncertain "
            "result is never committed under the session's authority, even after a person "
            "answers. Ask a person with an intervention."
        )
    position = citing.index(decision)
    if any(item.assessment != AgentDecisionAssessment.PASS for item in citing[position + 1 :]):
        raise _conflict(
            f"A decision recorded after {decision_id} cites action {action.action_id} without "
            "a pass assessment"
        )

    # Every existing evaluation of this result must support the update; none is no evidence.
    evaluations = list(evaluations_of(action))
    facts = [_evaluation_facts(evaluation) for evaluation in evaluations]
    for item in facts:
        problem = evaluation_problem(item)
        if problem is None:
            continue
        if problem.kind == "wait":
            raise _conflict(f"{problem.detail}; wait for it before an update")
        if problem.kind == "insufficient":
            raise _conflict(
                f"{problem.detail}. Only a completed evaluation with a reliable fit and a "
                "SUCCESS diagnosis supports an update under the session's authority; ask a "
                "person or commit with the reviewed call."
            )
        raise _conflict(
            f"{problem.detail}; the result is never committed under the session's authority. "
            "Ask a person with an intervention."
        )

    review = review_evidence(
        session=session,
        actions=session_run_tasks,
        candidates_of=candidates_of,
        evaluations_of=evaluations_of,
    )
    if review.refusal is not None:
        raise _conflict(review.refusal)

    recorded = action.metadata.get(BASELINE_METADATA_KEY)
    baseline = StoredParameter.from_record(
        recorded.get(candidate.parameter_name) if isinstance(recorded, dict) else None
    )
    if baseline is None:
        raise _conflict(
            f"Action {action.action_id} recorded no stored {candidate.parameter_name} when it "
            "was proposed, so QDash cannot tell whether its result is stale; commit it with "
            "the reviewed call or measure again"
        )
    current = read_parameter(session.project_id, session.chip_id, qid, candidate.parameter_name)
    if not parameter_matches(current, baseline):
        raise _conflict(
            f"The stored {candidate.parameter_name} of {qid} changed after action "
            f"{action.action_id} was proposed; its result may be stale. Measure again."
        )

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "authority": {
            "kind": "session_policy",
            "granted_by": session.created_by,
            "parameters": list(updates.parameters),
            "tasks": list(updates.tasks),
            "apply_backend": updates.apply_backend,
        },
        "assessment": {
            "provenance": "agent_reported",
            "decision_id": decision.decision_id,
            "assessment": decision.assessment.value,
            "next_action": decision.next_action.value,
            "recorded_by": decision.recorded_by,
            "recorded_at": _iso(decision.recorded_at),
            "interpretation": decision.interpretation[:1000],
            "evaluation_ids": list(decision.evaluation_ids),
            # The model the decision's host reported (client reported, not verified).
            "model": decision.model.model_dump(mode="json") if decision.model else None,
        },
        "gates": {
            "provenance": "server_computed",
            "execution_status": action.execution_status,
            "task_result_status": "completed",
            "task_result_id": candidate.task_id,
            "candidate_accepted": True,
            "candidate_reason": candidate.reason,
            "minimum": candidate.minimum,
            "maximum": candidate.maximum,
            "quality_metrics": dict(candidate.quality_metrics),
            "quality_gates": {
                name: bounds.model_dump() for name, bounds in session.policy.quality_gates.items()
            },
            "stored_value_unchanged_since_proposal": True,
        },
        # "none": no evaluation of the result existed; "supported": each one completed with
        # a reliable fit and a SUCCESS diagnosis and no reviewer disagreed.
        "evaluation_state": "supported" if facts else "none",
        "evaluations": facts,
        "note": EVIDENCE_NOTE,
    }
    return CommitGrounds(evidence=evidence, baseline=baseline)


# --------------------------------------------------------------------------- applies


def committed_value_is_stored(commit: AgentCandidateCommitDocument) -> bool:
    """Whether the qubit still stores exactly the value ``commit`` wrote."""
    if commit.after_snapshot is None:
        return False
    stored = read_parameter(commit.project_id, commit.chip_id, commit.qid, commit.parameter_name)
    return parameter_matches(stored, StoredParameter(present=True, value=commit.after_snapshot))


def check_apply(
    *,
    session: AgentSessionDocument,
    updates: AgentParameterUpdatePolicy,
    commit: AgentCandidateCommitDocument,
    session_run_tasks: list[AgentActionDocument],
    candidates_of: CandidatesOf,
    evaluations_of: EvaluationsOf,
) -> None:
    """Refuse an autonomous apply of anything but this authority's own current commit.

    This is an early refusal. The worker checks the stored value again while it holds the
    chip's apply lease, before and after it writes the files (``agent_candidate_apply``).
    """
    if not updates.apply_backend:
        raise _conflict(
            "The session's approval granted commits but not backend applies; apply with the "
            "reviewed call a person approves"
        )
    if commit.authority != "session_policy" or commit.committed_by != session.created_by:
        raise _conflict(
            "Only a commit made under the session's update authority is applied under it; "
            "apply a reviewed commit with the reviewed call"
        )
    if commit.backend_status != "not_started":
        raise _conflict(
            f"A backend apply of commit {commit.commit_id} was already requested "
            f"({commit.backend_status}); a failed apply needs a person and the reviewed call"
        )
    review = review_evidence(
        session=session,
        actions=session_run_tasks,
        candidates_of=candidates_of,
        evaluations_of=evaluations_of,
    )
    if review.refusal is not None:
        raise _conflict(review.refusal)
    if not committed_value_is_stored(commit):
        raise _conflict(
            f"The stored {commit.parameter_name} of {commit.qid} is no longer the value commit "
            f"{commit.commit_id} wrote; nothing was applied"
        )


# --------------------------------------------------------------------------- dependent steps


def dependency_refusal(
    *,
    session: AgentSessionDocument,
    actions: list[AgentActionDocument],
    task_name: str,
    qid: str,
    candidates_of: CandidatesOf,
    resolved: frozenset[str],
    commits: list[AgentCandidateCommitDocument],
) -> str | None:
    """Why a step of ``task_name`` on ``qid`` waits for an earlier update, or None.

    Only the newest completed result of each other granted task on the qubit counts. A result
    a person resolved after unresolved evidence carries no update to wait for. A valid result
    waits until its accepted granted candidates are committed and, with ``apply_backend``,
    applied; no answer from a person skips that.
    """
    updates = session.policy.parameter_updates
    if updates is None:
        return None
    latest: dict[str, AgentActionDocument] = {}
    for action in actions:
        if (
            action.task_name
            and action.task_name != task_name
            and action.task_name in updates.tasks
            and qid in action.qids
            and action.execution_status == "completed"
        ):
            latest[action.task_name] = action
    for action in latest.values():
        if action.action_id in resolved:
            continue
        label = _label(action)
        candidates = candidates_of(action.action_id)
        for candidate in candidates:
            if candidate.parameter_name not in updates.parameters or not candidate.accepted:
                continue
            commit = next(
                (
                    item
                    for item in commits
                    if item.action_id == action.action_id
                    and item.parameter_name == candidate.parameter_name
                    and item.status == "committed"
                ),
                None,
            )
            if commit is None:
                return (
                    f"The accepted {candidate.parameter_name} of {label} is not committed. "
                    "Commit it with qdash_commit_agent_session_update after a pass "
                    "assessment, or ask a person, before a dependent step."
                )
            if updates.apply_backend and commit.backend_status != "applied":
                if commit.backend_status == "failed":
                    return (
                        f"The backend apply of commit {commit.commit_id} failed; a dependent "
                        "step waits until a person applies it with the reviewed call."
                    )
                return (
                    f"Commit {commit.commit_id} is not applied to the backend yet "
                    f"({commit.backend_status}); apply it and wait before a dependent step."
                )
    return None


def downstream_refusal(
    *,
    session: AgentSessionDocument,
    actions: list[AgentActionDocument],
    task_name: str,
    qid: str,
    candidates_of: CandidatesOf,
    evaluations_of: EvaluationsOf,
) -> str | None:
    """Why an autonomous step of ``task_name`` on ``qid`` must not start now, or None.

    The step waits for a backend apply of the session in flight, stops on unresolved evidence
    anywhere in the session (whatever task the step repeats), and waits for the committed
    and applied update of the other granted tasks it depends on.
    """
    commits = cast(
        "list[AgentCandidateCommitDocument]",
        AgentCandidateCommitDocument.find(
            {"project_id": session.project_id, "session_id": session.session_id}
        ).run(),
    )
    in_flight = [
        commit.commit_id
        for commit in commits
        if commit.backend_status in IN_FLIGHT_BACKEND_STATUSES
    ]
    if in_flight:
        return (
            f"The backend apply of commit {', '.join(in_flight)} is still in progress; wait "
            "for it (qdash_wait_agent_candidate_apply) before the next step"
        )
    review = review_evidence(
        session=session,
        actions=actions,
        candidates_of=candidates_of,
        evaluations_of=evaluations_of,
    )
    if review.refusal is not None:
        return review.refusal
    return dependency_refusal(
        session=session,
        actions=actions,
        task_name=task_name,
        qid=qid,
        candidates_of=candidates_of,
        resolved=review.resolved,
        commits=commits,
    )


def paused_session_overlap(
    project_id: str, chip_id: str, username: str, qids: list[str]
) -> AgentSessionDocument | None:
    """The creator's own session on the chip that is paused for a person and covers a qid."""
    from qdash.api.services.agent_session_gate import load_agent_session
    from qdash.datamodel.agent_session import AgentSessionStatus

    paused = cast(
        "list[AgentSessionDocument]",
        AgentSessionDocument.find(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "created_by": username,
                "status": AgentSessionStatus.WAITING_FOR_HUMAN.value,
                "policy.qids": {"$in": qids},
            }
        ).run(),
    )
    for doc in paused:
        # Loading applies the expiry, so an expired pause does not block.
        current = load_agent_session(project_id, doc.session_id)
        if current.status == AgentSessionStatus.WAITING_FOR_HUMAN:
            return current
    return None
