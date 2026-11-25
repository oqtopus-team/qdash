"""Automatic calibration sessions close once everything started in them has ended."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from qdash.api.services.calibration_session_lifecycle import (
    SYSTEM_CLOSE_ACTOR,
    CalibrationSessionLifecycle,
)
from qdash.api.services.calibration_session_service import CalibrationSessionService
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentSessionStatus
from qdash.datamodel.calibration_session import (
    CalibrationChildKind,
    CalibrationSessionCloseOrigin,
    CalibrationSessionOrigin,
    CalibrationSessionStatus,
)
from qdash.datamodel.run import RunDispatchStatus, RunFlowEndState, RunKind
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import CalibrationSessionDocument
from qdash.dbmodel.run import RunDocument
from qdash.repository.run_ledger import record_worker_run
from tests.qdash.api.routers.test_calibration_sessions import (
    CHIP,
    GATEWAY,
    POLICY,
    _agent_action,
    _create_session,
    _headers,
    _release_locks,
    _run,
    _step_execution,
    lab,  # noqa: F401 - fixture
    prefect,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

pytestmark = pytest.mark.usefixtures("lab")

READER = "qdash.api.services.calibration_session_lifecycle.read_prefect_flow_states"


class FakePrefect:
    """Prefect flow run state types by flow run ID; a missing ID is not reported."""

    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.calls: list[list[str]] = []
        self.fail = False

    def __call__(self, flow_run_ids: Sequence[str]) -> Mapping[str, str | None]:
        self.calls.append(list(flow_run_ids))
        if self.fail:
            raise RuntimeError("prefect unreachable")
        return {fid: self.states[fid] for fid in flow_run_ids if fid in self.states}


@pytest.fixture
def flows() -> Iterator[FakePrefect]:
    fake = FakePrefect()
    with patch(READER, new=fake):
        yield fake


def _session(session_id: str) -> CalibrationSessionDocument:
    doc = CalibrationSessionDocument.find_one({"calibration_session_id": session_id}).run()
    assert doc is not None
    return doc


def _only_run(session_id: str) -> RunDocument:
    [run] = RunDocument.find({"calibration_session_id": session_id}).to_list()
    return run


def _launch(test_client, key: str, flow_run_id: str) -> str:
    """Launch a pipeline without a session; the automatic session it gets."""
    with prefect([flow_run_id]):
        response = _run(test_client, None, key)
    assert response.status_code == 202, response.text
    _release_locks()
    return str(_only_run_by_key(key).calibration_session_id)


def _only_run_by_key(key: str) -> RunDocument:
    [run] = RunDocument.find({"idempotency_key": key}).to_list()
    return run


def _sweep() -> list[Any]:
    return CalibrationSessionLifecycle().sweep()


def _assert_auto_closed(session_id: str) -> CalibrationSessionDocument:
    doc = _session(session_id)
    assert doc.status == CalibrationSessionStatus.CLOSED
    assert doc.close_origin == CalibrationSessionCloseOrigin.AUTOMATIC
    assert doc.closed_by == SYSTEM_CLOSE_ACTOR
    assert doc.closed_at is not None
    assert doc.closing_note.startswith("Closed automatically")
    return doc


class TestWholeFlowRun:
    def test_a_completed_step_does_not_close_while_the_flow_runs(self, test_client, flows):
        session_id = _launch(test_client, "multi", "fr-multi")
        run = _only_run(session_id)
        assert _session(session_id).origin == CalibrationSessionOrigin.AUTOMATIC
        # The first step finished; the flow goes on to its next step.
        _step_execution(str(run.execution_id), "fr-multi", 1, "completed")
        flows.states["fr-multi"] = "RUNNING"
        [check] = _sweep()
        assert not check.closed
        assert any("has not ended: Prefect reports it running" in r for r in check.waiting_on)
        assert _session(session_id).status == CalibrationSessionStatus.OPEN
        assert _only_run(session_id).flow_end_state is None

        flows.states["fr-multi"] = "COMPLETED"
        [check] = _sweep()
        assert check.closed
        doc = _assert_auto_closed(session_id)
        assert "1 completed" in doc.closing_note
        assert _only_run(session_id).flow_end_state == RunFlowEndState.COMPLETED

    @pytest.mark.parametrize(
        ("prefect_state", "ended"),
        [
            ("FAILED", RunFlowEndState.FAILED),
            ("CANCELLED", RunFlowEndState.CANCELLED),
            ("CRASHED", RunFlowEndState.CRASHED),
        ],
    )
    def test_final_failure_and_cancellation_close_and_are_recorded_apart(
        self, test_client, flows, prefect_state, ended
    ):
        session_id = _launch(test_client, f"k-{prefect_state}", f"fr-{prefect_state}")
        flows.states[f"fr-{prefect_state}"] = prefect_state
        [check] = _sweep()
        assert check.closed
        doc = _assert_auto_closed(session_id)
        assert f"1 {ended.value}" in doc.closing_note
        assert _only_run(session_id).flow_end_state == ended

    @pytest.mark.parametrize("transient", ["SCHEDULED", "PENDING", "PAUSED", "CANCELLING"])
    def test_a_flow_run_retrying_or_waiting_keeps_its_session_open(
        self, test_client, flows, transient
    ):
        session_id = _launch(test_client, "retry", "fr-retry")
        # AwaitingRetry and Late are SCHEDULED state types.
        flows.states["fr-retry"] = transient
        [check] = _sweep()
        assert not check.closed
        assert _only_run(session_id).flow_end_state is None
        flows.states["fr-retry"] = "FAILED"
        [check] = _sweep()
        assert check.closed

    def test_a_flow_run_prefect_does_not_report_never_closes_however_old(self, test_client, flows):
        session_id = _launch(test_client, "gone", "fr-gone")
        RunDocument.get_motor_collection().update_one(
            {"calibration_session_id": session_id},
            {"$set": {"updated_at": now() - timedelta(days=30)}},
        )
        # No execution was ever recorded, and Prefect does not know the flow run.
        [check] = _sweep()
        assert not check.closed
        assert _session(session_id).status == CalibrationSessionStatus.OPEN

    def test_a_prefect_read_failure_keeps_the_session_open(self, test_client, flows):
        session_id = _launch(test_client, "down", "fr-down")
        flows.states["fr-down"] = "COMPLETED"
        flows.fail = True
        [check] = _sweep()
        assert not check.closed
        flows.fail = False
        [check] = _sweep()
        assert check.closed
        assert _session(session_id).status == CalibrationSessionStatus.CLOSED


class TestDispatchOutcomes:
    def test_dispatching_and_unknown_runs_block_without_acknowledgment(self, test_client, flows):
        with prefect(side_effect=RuntimeError("prefect timed out")):
            response = _run(test_client, None, "lost")
        assert response.status_code >= 500
        _release_locks()
        run = _only_run_by_key("lost")
        assert run.status == RunDispatchStatus.UNKNOWN
        [check] = _sweep()
        assert not check.closed
        assert any("unknown dispatch outcome" in r for r in check.waiting_on)

        # A launch still in flight blocks too, and so does its stale form (unknown).
        RunDocument.get_motor_collection().update_one(
            {"run_id": run.run_id},
            {"$set": {"status": RunDispatchStatus.DISPATCHING.value, "updated_at": now()}},
        )
        [check] = _sweep()
        assert any("is being dispatched" in r for r in check.waiting_on)
        RunDocument.get_motor_collection().update_one(
            {"run_id": run.run_id}, {"$set": {"updated_at": now() - timedelta(hours=1)}}
        )
        [check] = _sweep()
        assert not check.closed
        assert _session(str(run.calibration_session_id)).status == CalibrationSessionStatus.OPEN

    def test_a_refused_launch_stays_open_for_its_same_key_retry(self, test_client, flows):
        from qdash.api.services.flow_service.prefect_gateway import SystemDeploymentUnavailable

        with patch(
            f"{GATEWAY}.read_deployment_id",
            new=AsyncMock(side_effect=SystemDeploymentUnavailable("missing")),
        ):
            assert _run(test_client, None, "refused").status_code == 503
        _release_locks()
        run = _only_run_by_key("refused")
        session_id = str(run.calibration_session_id)
        assert run.status == RunDispatchStatus.REJECTED
        [check] = _sweep()
        assert not check.closed
        assert any("refused before launch" in r for r in check.waiting_on)

        # The same key launches it, in the same automatic session.
        with prefect(["fr-refused"]):
            retried = _run(test_client, None, "refused")
        assert retried.status_code == 202, retried.text
        _release_locks()
        run = _only_run_by_key("refused")
        assert run.status == RunDispatchStatus.DISPATCHED
        assert run.calibration_session_id == session_id
        flows.states["fr-refused"] = "COMPLETED"
        [check] = _sweep()
        assert check.closed


def _agent_session(
    test_client, *, calibration_session_id: str | None = None, expires_in: int = 3600
) -> tuple[str, str]:
    body: dict[str, Any] = {"chip_id": CHIP, "policy": POLICY, "expires_in_seconds": expires_in}
    if calibration_session_id is not None:
        body["calibration_session_id"] = calibration_session_id
    created = test_client.post("/agent-sessions", headers=_headers(), json=body)
    assert created.status_code == 201, created.text
    agent_id = str(created.json()["session_id"])
    agent = AgentSessionDocument.find_one({"session_id": agent_id}).run()
    assert agent is not None and agent.calibration_session_id is not None
    return agent_id, agent.calibration_session_id


def _set_agent(agent_id: str, **fields: Any) -> None:
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": agent_id}, {"$set": fields}
    )


def _settle_action(agent_id: str) -> None:
    from qdash.dbmodel.agent_session import AgentActionDocument

    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": f"action-{agent_id}"}, {"$set": {"execution_status": "completed"}}
    )


class TestAutomaticAgentSessionParent:
    def test_closes_only_after_the_agent_ends_and_its_operations_settle(self, test_client, flows):
        agent_id, session_id = _agent_session(test_client)
        assert _session(session_id).origin == CalibrationSessionOrigin.AUTOMATIC
        [check] = _sweep()
        assert not check.closed
        assert f"agent session {agent_id} is active" in check.waiting_on

        _set_agent(agent_id, status=AgentSessionStatus.COMPLETED.value)
        # A measurement that passed the gate before the end has not settled.
        _agent_action(
            agent_id,
            "dispatching",
            dispatch_token="t",
            dispatch_confirmed=True,
            dispatch_reserved_at=now(),
        )
        [check] = _sweep()
        assert not check.closed
        assert any("is dispatching" in r for r in check.waiting_on)

        _settle_action(agent_id)
        [check] = _sweep()
        assert check.closed
        doc = _assert_auto_closed(session_id)
        assert "Agent sessions: 1 completed" in doc.closing_note

    def test_expiry_with_a_queued_measurement_waits_for_it(self, test_client, flows):
        agent_id, _ = _agent_session(test_client)
        _set_agent(agent_id, expires_at=now() - timedelta(minutes=1))
        _agent_action(agent_id, "queued", operation_id="fr-queued")
        [check] = _sweep()
        assert not check.closed
        assert any("is queued" in r for r in check.waiting_on)
        assert (
            AgentSessionDocument.find_one({"session_id": agent_id}).run().status  # type: ignore[union-attr]
            == AgentSessionStatus.EXPIRED
        )
        _settle_action(agent_id)
        [check] = _sweep()
        assert check.closed

    @pytest.mark.parametrize(
        ("kind", "status"),
        [
            ("candidate_commit", "committing"),
            ("backend_apply", "applying"),
        ],
    )
    def test_an_unsettled_commit_or_apply_blocks(self, test_client, flows, kind, status):
        from qdash.api.services import calibration_session_lifecycle as lifecycle

        agent_id, _ = _agent_session(test_client)
        _set_agent(agent_id, status=AgentSessionStatus.CANCELLED.value)
        op = {"kind": kind, "id": "commit-1", "status": status}
        with patch.object(lifecycle, "in_flight_operations", return_value=[op]):
            [check] = _sweep()
        assert not check.closed
        assert any(f"is {status}" in r for r in check.waiting_on)
        [check] = _sweep()
        assert check.closed

    def test_an_agent_action_run_must_end_too(self, test_client, flows):
        agent_id, session_id = _agent_session(test_client)
        _set_agent(agent_id, status=AgentSessionStatus.COMPLETED.value)
        RunDocument(
            run_id="cpr-action-a1",
            project_id="lab-a",
            calibration_session_id=session_id,
            chip_id=CHIP,
            run_kind=RunKind.AGENT_ACTION,
            agent_session_id=agent_id,
            action_id="a1",
            idempotency_key="agent-action:a1",
            idempotency_scope="agent-action:a1",
            request_hash="",
            requested_by="owner",
            status=RunDispatchStatus.DISPATCHED,
            dispatch_token="t",
            flow_run_id="fr-action",
        ).insert()
        flows.states["fr-action"] = "RUNNING"
        [check] = _sweep()
        assert not check.closed
        flows.states["fr-action"] = "COMPLETED"
        [check] = _sweep()
        assert check.closed


class TestManualSessions:
    def test_a_manual_session_stays_open_when_all_its_runs_ended(self, test_client, flows):
        session_id = _create_session(test_client)
        with prefect(["fr-manual"]):
            assert _run(test_client, session_id, "m-1").status_code == 202
        _release_locks()
        flows.states["fr-manual"] = "COMPLETED"
        assert _sweep() == []
        assert CalibrationSessionLifecycle().reconcile([_session(session_id)]) == []
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers())
        assert detail.json()["status"] == "open"
        assert flows.calls == []

    def test_a_manual_close_records_its_origin(self, test_client, flows):
        session_id = _create_session(test_client)
        closed = test_client.post(
            f"/calibration-sessions/{session_id}/close", headers=_headers(), json={}
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["close_origin"] == "manual"
        assert closed.json()["closed_by"] == "owner"


class TestConcurrency:
    @pytest.mark.parametrize("finalized", [False, True])
    def test_a_child_started_during_the_check_prevents_the_close(
        self, test_client, flows, finalized
    ):
        from qdash.api.services import calibration_session_lifecycle as lifecycle

        session_id = _launch(test_client, "race", "fr-race")
        flows.states["fr-race"] = "COMPLETED"
        original = lifecycle._children
        reserved: list[str] = []

        def reserve_meanwhile(doc: CalibrationSessionDocument):
            found = original(doc)
            reservation = CalibrationSessionService().reserve_child(
                project_id="lab-a",
                calibration_session_id=session_id,
                chip_id=CHIP,
                username="owner",
                kind=CalibrationChildKind.PIPELINE_RUN,
                child_id="cpr-late",
            )
            reserved.append(reservation.reservation_id)
            if finalized:
                # Its record was written and its start finalized before the close: only the
                # count tells the close about it.
                assert CalibrationSessionService.finalize_child(
                    project_id="lab-a",
                    calibration_session_id=session_id,
                    reservation_id=reservation.reservation_id,
                )
            return found

        with patch.object(lifecycle, "_children", side_effect=reserve_meanwhile):
            [check] = _sweep()
        assert not check.closed
        doc = _session(session_id)
        assert doc.status == CalibrationSessionStatus.OPEN
        if not finalized:
            # The reservation was not cleared; its request can still finalize it.
            assert CalibrationSessionService.finalize_child(
                project_id="lab-a", calibration_session_id=session_id, reservation_id=reserved[0]
            )

    def test_an_explicit_addition_after_the_close_is_refused_not_lost(self, test_client, flows):
        session_id = _launch(test_client, "first", "fr-first")
        flows.states["fr-first"] = "COMPLETED"
        [check] = _sweep()
        assert check.closed
        with prefect(["fr-second"]) as create:
            added = _run(test_client, session_id, "second")
        assert added.status_code == 409
        assert "is closed" in added.json()["detail"]
        create.assert_not_awaited()

    def test_a_pending_reservation_blocks(self, test_client, flows):
        session_id = _launch(test_client, "pending", "fr-pending")
        flows.states["fr-pending"] = "COMPLETED"
        CalibrationSessionService().reserve_child(
            project_id="lab-a",
            calibration_session_id=session_id,
            chip_id=CHIP,
            username="owner",
            kind=CalibrationChildKind.AGENT_SESSION,
            child_id="agent-starting",
        )
        [check] = _sweep()
        assert not check.closed
        assert "agent session agent-starting is being started" in check.waiting_on


class TestRecoveryAndIdempotence:
    def test_one_sweep_reconciles_missed_completions_with_one_prefect_read(
        self, test_client, flows
    ):
        sessions = [_launch(test_client, f"missed-{i}", f"fr-missed-{i}") for i in range(3)]
        for i in range(3):
            flows.states[f"fr-missed-{i}"] = "COMPLETED"
        checks = _sweep()
        assert all(check.closed for check in checks)
        assert len(checks) == 3
        assert len(flows.calls) == 1
        assert sorted(flows.calls[0]) == sorted(f"fr-missed-{i}" for i in range(3))
        for session_id in sessions:
            _assert_auto_closed(session_id)

    def test_repeating_the_check_changes_nothing(self, test_client, flows):
        session_id = _launch(test_client, "twice", "fr-twice")
        flows.states["fr-twice"] = "COMPLETED"
        [check] = _sweep()
        assert check.closed
        first = _assert_auto_closed(session_id)
        assert _sweep() == []
        assert CalibrationSessionLifecycle().reconcile([first]) == []
        again = _session(session_id)
        assert again.closed_at == first.closed_at
        assert again.closing_note == first.closing_note
        # Flow runs already seen to end are not read again.
        flows.calls.clear()
        CalibrationSessionLifecycle().reconcile([again])
        assert flows.calls == []

    def test_a_detail_read_closes_an_ended_automatic_session(self, test_client, flows):
        session_id = _launch(test_client, "read", "fr-read")
        flows.states["fr-read"] = "COMPLETED"
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers())
        body = detail.json()
        assert body["status"] == "closed"
        assert body["close_origin"] == "automatic"
        assert body["closed_by"] == SYSTEM_CLOSE_ACTOR
        assert body["pipeline_runs"][0]["flow_end_state"] == "completed"

    def test_the_session_list_reads_no_flow_run(self, test_client, flows):
        _launch(test_client, "listed", "fr-listed")
        listed = test_client.get("/calibration-sessions", headers=_headers())
        assert listed.status_code == 200
        assert flows.calls == []

    def test_the_least_recently_checked_sessions_go_first(self, test_client, flows):
        older = _launch(test_client, "older", "fr-older")
        newer = _launch(test_client, "newer", "fr-newer")
        first = CalibrationSessionLifecycle().sweep(limit=1)
        assert [c.calibration_session_id for c in first] == [older]
        second = CalibrationSessionLifecycle().sweep(limit=1)
        assert [c.calibration_session_id for c in second] == [newer]

    def test_a_session_with_nothing_recorded_stays_open(self, test_client, flows):
        from qdash.repository.calibration_run import insert_or_load_automatic_session

        # The worker counts its run with the session, then writes the run.
        insert_or_load_automatic_session(
            calibration_session_id="cs-flow-unwritten",
            project_id="lab-a",
            chip_id=CHIP,
            username="owner",
            objective="Workflow x",
            child_count=1,
        )
        [check] = _sweep()
        assert not check.closed
        assert check.waiting_on == ["nothing has been recorded in it yet"]

    def test_runs_past_the_detail_page_keep_the_session_open(self, test_client, flows):
        from qdash.api.services.calibration_session_service import MAX_DETAIL_CHILDREN

        session_id = _launch(test_client, "many", "fr-many-0")
        base = now() - timedelta(hours=2)
        RunDocument.get_motor_collection().update_one(
            {"calibration_session_id": session_id}, {"$set": {"requested_at": base}}
        )
        for index in range(1, MAX_DETAIL_CHILDREN + 1):
            RunDocument(
                run_id=f"cpr-many-{index:03d}",
                project_id="lab-a",
                calibration_session_id=session_id,
                chip_id=CHIP,
                run_kind=RunKind.WORKFLOW,
                idempotency_key=f"many-{index}",
                request_hash="h",
                requested_by="owner",
                status=RunDispatchStatus.DISPATCHED,
                dispatch_token="t",
                flow_run_id=f"fr-many-{index}",
                requested_at=base + timedelta(seconds=index),
            ).insert()
            flows.states[f"fr-many-{index}"] = "COMPLETED"
        # Only the oldest run, outside the most recent page, still runs.
        flows.states["fr-many-0"] = "RUNNING"
        [check] = _sweep()
        assert not check.closed
        assert len(check.waiting_on) == 1
        flows.states["fr-many-0"] = "COMPLETED"
        [check] = _sweep()
        assert check.closed
        assert f"{MAX_DETAIL_CHILDREN + 1} completed" in _session(session_id).closing_note


class TestWorkerRecordedRuns:
    def test_a_scheduled_flow_run_closes_its_session_when_the_flow_ends(self, test_client, flows):
        identity = record_worker_run(
            project_id="lab-a",
            chip_id=CHIP,
            username="owner",
            flow_run_id="fr-cron",
            flow_name="nightly",
            run_name="nightly",
            auto_scheduled=True,
        )
        session_id = str(identity.calibration_session_id)
        assert session_id == "cs-flow-fr-cron"
        flows.states["fr-cron"] = "RUNNING"
        [check] = _sweep()
        assert not check.closed
        # A Prefect retry of the same flow run reaches the same run and session.
        again = record_worker_run(
            project_id="lab-a",
            chip_id=CHIP,
            username="owner",
            flow_run_id="fr-cron",
            flow_name="nightly",
            run_name="nightly",
            auto_scheduled=True,
        )
        assert again.run_id == identity.run_id
        flows.states["fr-cron"] = "SCHEDULED"  # AwaitingRetry
        [check] = _sweep()
        assert not check.closed
        flows.states["fr-cron"] = "COMPLETED"
        [check] = _sweep()
        assert check.closed
        _assert_auto_closed(session_id)


class TestLegacySessions:
    def test_an_automatic_session_from_before_is_closed_only_on_evidence(self, test_client, flows):
        for name, flow_run_id in (("ended", "fr-legacy-ended"), ("silent", None)):
            CalibrationSessionDocument(
                calibration_session_id=f"cs-auto-legacy-{name}",
                project_id="lab-a",
                chip_id=CHIP,
                objective="Pipeline legacy",
                created_by="owner",
                origin=CalibrationSessionOrigin.AUTOMATIC,
                child_count=1,
                created_at=now() - timedelta(days=60),
            ).insert()
            RunDocument(
                run_id=f"cpr-legacy-{name}",
                project_id="lab-a",
                calibration_session_id=f"cs-auto-legacy-{name}",
                chip_id=CHIP,
                idempotency_key=name,
                request_hash="h",
                requested_by="owner",
                status=RunDispatchStatus.DISPATCHED,
                dispatch_token="t",
                flow_run_id=flow_run_id,
                requested_at=now() - timedelta(days=60),
                updated_at=now() - timedelta(days=60),
            ).insert()
        flows.states["fr-legacy-ended"] = "COMPLETED"
        checks = {c.calibration_session_id: c for c in _sweep()}
        assert checks["cs-auto-legacy-ended"].closed
        # Dispatched without a recorded flow run: whether it ended is unknown.
        assert not checks["cs-auto-legacy-silent"].closed
        assert _session("cs-auto-legacy-silent").status == CalibrationSessionStatus.OPEN

    def test_a_session_recorded_before_origins_is_manual_and_never_closed(self, test_client, flows):
        CalibrationSessionDocument.get_motor_collection().insert_one(
            {
                "calibration_session_id": "cs-old-manual",
                "project_id": "lab-a",
                "chip_id": CHIP,
                "objective": "old",
                "created_by": "owner",
                "status": "open",
                "child_count": 0,
                "pending_children": [],
                "admitted_reservation_ids": [],
                "created_at": now(),
                "updated_at": now(),
            }
        )
        assert _sweep() == []
        assert _session("cs-old-manual").status == CalibrationSessionStatus.OPEN


def _auto_session_with_runs(
    name: str, flow_run_ids: Sequence[str], *, created_at: Any = None
) -> str:
    """An automatic session holding one dispatched run per flow run ID."""
    session_id = f"cs-auto-{name}"
    CalibrationSessionDocument(
        calibration_session_id=session_id,
        project_id="lab-a",
        chip_id=CHIP,
        objective=f"Pipeline {name}",
        created_by="owner",
        origin=CalibrationSessionOrigin.AUTOMATIC,
        child_count=len(flow_run_ids),
        created_at=created_at or now(),
    ).insert()
    if flow_run_ids:
        RunDocument.insert_many(
            [
                RunDocument(
                    run_id=f"cpr-{name}-{index}",
                    project_id="lab-a",
                    calibration_session_id=session_id,
                    chip_id=CHIP,
                    idempotency_key=f"{name}-{index}",
                    request_hash="h",
                    requested_by="owner",
                    status=RunDispatchStatus.DISPATCHED,
                    dispatch_token="t",
                    flow_run_id=flow_run_id,
                )
                for index, flow_run_id in enumerate(flow_run_ids)
            ]
        )
    return session_id


class TestCurrentEvidenceAtClose:
    def test_an_end_seen_earlier_does_not_close_a_flow_run_running_again(self, test_client, flows):
        session_id = _auto_session_with_runs("restart", ["fr-a", "fr-b"])
        flows.states.update({"fr-a": "COMPLETED", "fr-b": "RUNNING"})
        [check] = _sweep()
        assert not check.closed
        recorded = {run.flow_run_id: run.flow_end_state for run in RunDocument.find().to_list()}
        assert recorded == {"fr-a": RunFlowEndState.COMPLETED, "fr-b": None}

        # The first flow run is resumed in Prefect, then the other one finishes.
        flows.states.update({"fr-a": "RUNNING", "fr-b": "COMPLETED"})
        [check] = _sweep()
        assert not check.closed
        assert check.waiting_on == [
            "run cpr-restart-0 (flow run fr-a) has not ended: Prefect reports it running"
        ]
        recorded = {run.flow_run_id: run.flow_end_state for run in RunDocument.find().to_list()}
        assert recorded == {"fr-a": None, "fr-b": RunFlowEndState.COMPLETED}
        assert _session(session_id).status == CalibrationSessionStatus.OPEN

        flows.states["fr-a"] = "FAILED"
        [check] = _sweep()
        assert check.closed
        assert "Runs: 1 completed, 1 failed." in _assert_auto_closed(session_id).closing_note

    @pytest.mark.parametrize("how", ["missing", "error"])
    def test_an_unreadable_flow_run_blocks_even_after_it_was_seen_to_end(
        self, test_client, flows, how
    ):
        session_id = _auto_session_with_runs(f"seen-{how}", ["fr-x", "fr-y"])
        flows.states.update({"fr-x": "COMPLETED", "fr-y": "RUNNING"})
        assert not _sweep()[0].closed
        flows.states["fr-y"] = "COMPLETED"
        if how == "missing":
            del flows.states["fr-x"]
        else:
            flows.fail = True
        [check] = _sweep()
        assert not check.closed
        expected = "Prefect does not report it" if how == "missing" else "could not be read"
        assert any(expected in reason for reason in check.waiting_on)
        assert _session(session_id).status == CalibrationSessionStatus.OPEN


class TestBoundedFairReads:
    def test_a_blocked_prefix_over_the_budget_does_not_starve_later_sessions(
        self, test_client, flows
    ):
        from qdash.api.services.calibration_session_lifecycle import (
            FLOW_RUNS_PER_READ,
            MAX_FLOW_RUN_READS,
        )

        budget = FLOW_RUNS_PER_READ * MAX_FLOW_RUN_READS
        old = now() - timedelta(days=1)
        # 1001 flow runs still running, in sessions older than the one that ended.
        blocked = [
            _auto_session_with_runs(
                f"blocked-{n}",
                [f"fr-blocked-{n}-{i}" for i in range(size)],
                created_at=old + timedelta(seconds=n),
            )
            for n, size in enumerate([200, 200, 200, 200, 200, 1])
        ]
        for n, size in enumerate([200, 200, 200, 200, 200, 1]):
            for i in range(size):
                flows.states[f"fr-blocked-{n}-{i}"] = "RUNNING"
        ended = _auto_session_with_runs("ended", ["fr-ended"])
        flows.states["fr-ended"] = "COMPLETED"

        checks = {c.calibration_session_id: c for c in _sweep()}
        assert len(flows.calls) <= MAX_FLOW_RUN_READS
        assert sum(len(call) for call in flows.calls) <= budget
        assert all(len(call) <= FLOW_RUNS_PER_READ for call in flows.calls)
        assert not checks[ended].closed
        assert "did not fit" in checks[ended].waiting_on[0]

        flows.calls.clear()
        checks = {c.calibration_session_id: c for c in _sweep()}
        assert checks[ended].closed
        assert not checks[blocked[-1]].closed
        assert sum(len(call) for call in flows.calls) <= budget
        _assert_auto_closed(ended)

    def test_a_session_with_more_flow_runs_than_a_check_reads_stays_open(
        self, test_client, flows, monkeypatch
    ):
        from qdash.api.services import calibration_session_lifecycle as lifecycle

        monkeypatch.setattr(lifecycle, "FLOW_RUNS_PER_READ", 2)
        monkeypatch.setattr(lifecycle, "MAX_FLOW_RUN_READS", 1)
        session_id = _auto_session_with_runs("huge", ["fr-h-0", "fr-h-1", "fr-h-2"])
        small = _auto_session_with_runs("small", ["fr-s"])
        flows.states.update({f"fr-h-{i}": "COMPLETED" for i in range(3)} | {"fr-s": "COMPLETED"})
        checks = {c.calibration_session_id: c for c in _sweep()}
        assert "more flow runs than one check reads (2)" in checks[session_id].waiting_on[0]
        assert checks[small].closed
        assert flows.calls == [["fr-s"]]


class TestSweeper:
    @pytest.mark.asyncio
    async def test_the_interval_is_fixed_and_injectable_and_shutdown_waits(self):
        import asyncio
        import threading

        from qdash.api.services.calibration_session_lifecycle import (
            SWEEP_INTERVAL_SECONDS,
            run_lifecycle_sweeper,
        )

        assert SWEEP_INTERVAL_SECONDS == 60.0
        started = threading.Event()
        finished = threading.Event()

        class Blocking:
            def sweep(self, *, stop: threading.Event) -> list[Any]:
                started.set()
                # A sweep stops between sessions once asked to.
                assert stop.wait(timeout=5)
                finished.set()
                return []

        task = run_lifecycle_sweeper(Blocking(), interval_seconds=0.01)  # type: ignore[arg-type]
        assert task is not None
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.wait({task})
        assert finished.is_set()
        assert task.cancelled()


def test_no_environment_setting_controls_the_sweep():
    from qdash.api.services import calibration_session_lifecycle as lifecycle

    assert not hasattr(lifecycle, "SWEEP_INTERVAL_ENV")
    assert not hasattr(lifecycle, "sweep_interval_seconds")


@pytest.mark.parametrize("phase", ["_prepare", "_decide"])
def test_failed_checks_yield_to_later_sessions(test_client, flows, monkeypatch, phase):
    old = now() - timedelta(days=1)
    blocked = {
        _auto_session_with_runs(f"error-{n}", [f"fr-error-{n}"], created_at=old) for n in range(50)
    }
    healthy = _auto_session_with_runs("healthy-after-errors", ["fr-healthy"])
    flows.states["fr-healthy"] = "COMPLETED"
    checker = CalibrationSessionLifecycle()
    original = getattr(checker, phase)

    def fail_selected(item, *args):
        doc = item if phase == "_prepare" else item.doc
        if doc.calibration_session_id in blocked:
            raise RuntimeError("persistent session error")
        return original(item, *args)

    monkeypatch.setattr(checker, phase, fail_selected)
    first = checker.sweep()
    assert len(first) == 50
    assert all(not check.closed for check in first)
    second = checker.sweep()
    assert any(check.calibration_session_id == healthy and check.closed for check in second)
    assert all(_session(sid).status == CalibrationSessionStatus.OPEN for sid in blocked)


def test_shared_flow_ids_are_read_once_within_budget(test_client, flows, monkeypatch):
    from qdash.api.services import calibration_session_lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "FLOW_RUNS_PER_READ", 2)
    monkeypatch.setattr(lifecycle, "MAX_FLOW_RUN_READS", 1)
    for n in range(3):
        _auto_session_with_runs(f"shared-{n}", ["fr-shared-0", "fr-shared-1"])
    flows.states.update({"fr-shared-0": "RUNNING", "fr-shared-1": "RUNNING"})
    checks = _sweep()
    assert len(checks) == 3
    assert all(not check.closed for check in checks)
    assert flows.calls == [["fr-shared-0", "fr-shared-1"]]
