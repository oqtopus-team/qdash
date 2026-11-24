"""One run of a calibration session, read with its whole flow run's current state."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import CalibrationSessionStatus
from qdash.datamodel.run import RunDispatchStatus, RunFlowEndState, RunKind
from qdash.dbmodel.calibration_session import CalibrationSessionDocument
from qdash.dbmodel.run import RunDocument
from tests.qdash.api.routers.test_calibration_sessions import (
    CHIP,
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
        self.states: dict[str, str | None] = {}
        self.calls: list[list[str]] = []
        self.fail = False

    def __call__(self, flow_run_ids: Sequence[str]) -> Mapping[str, str | None]:
        self.calls.append(list(flow_run_ids))
        if self.fail:
            raise TimeoutError("prefect timed out")
        return {fid: self.states[fid] for fid in flow_run_ids if fid in self.states}


@pytest.fixture
def flows() -> Iterator[FakePrefect]:
    fake = FakePrefect()
    with patch(READER, new=fake):
        yield fake


def _launch(test_client, session_id: str | None, key: str, flow_run_id: str) -> RunDocument:
    with prefect([flow_run_id]):
        response = _run(test_client, session_id, key)
    assert response.status_code == 202, response.text
    _release_locks()
    [run] = RunDocument.find({"idempotency_key": key}).to_list()
    return run


def _get(test_client, session_id: str, run_id: str, **headers: str):
    return test_client.get(
        f"/calibration-sessions/{session_id}/runs/{run_id}", headers=_headers(**headers)
    )


def _session_status(session_id: str) -> CalibrationSessionStatus:
    doc = CalibrationSessionDocument.find_one({"calibration_session_id": session_id}).run()
    assert doc is not None
    return doc.status


class TestFlowStatus:
    def test_a_manual_session_run_follows_the_whole_flow_and_stays_open(self, test_client, flows):
        session_id = _create_session(test_client)
        run = _launch(test_client, session_id, "m-1", "fr-manual")
        # The first step's execution completed; the flow goes on to its next step.
        _step_execution(str(run.execution_id), "fr-manual", 1, "completed")
        flows.states["fr-manual"] = "RUNNING"

        body = _get(test_client, session_id, run.run_id).json()
        assert body["run_id"] == run.run_id
        assert body["calibration_session_id"] == session_id
        assert body["flow_status"] == "running"
        assert body["prefect_state"] == "RUNNING"
        assert body["flow_end_state"] is None
        assert body["executions"][0]["status"] == "completed"
        assert body["observed_at"]

        flows.states["fr-manual"] = "COMPLETED"
        body = _get(test_client, session_id, run.run_id).json()
        assert body["flow_status"] == "completed"
        assert body["flow_end_state"] == "completed"
        assert flows.calls == [["fr-manual"], ["fr-manual"]]
        # Reading changes nothing: the manual session stays open, nothing is recorded.
        assert _session_status(session_id) == CalibrationSessionStatus.OPEN
        stored = RunDocument.find_one({"run_id": run.run_id}).run()
        assert stored is not None
        assert stored.flow_end_state is None

    @pytest.mark.parametrize("prefect_state", ["FAILED", "CANCELLED", "CRASHED"])
    def test_terminal_failures_are_reported_apart(self, test_client, flows, prefect_state):
        session_id = _create_session(test_client)
        run = _launch(test_client, session_id, "m-end", "fr-end")
        _step_execution(str(run.execution_id), "fr-end", 1, "completed")
        flows.states["fr-end"] = prefect_state

        body = _get(test_client, session_id, run.run_id).json()
        assert body["flow_status"] == prefect_state.lower()
        assert body["flow_end_state"] == prefect_state.lower()

    @pytest.mark.parametrize("transient", ["SCHEDULED", "PENDING", "PAUSED", "CANCELLING"])
    def test_states_prefect_may_leave_are_running(self, test_client, flows, transient):
        session_id = _create_session(test_client)
        run = _launch(test_client, session_id, "m-wait", "fr-wait")
        flows.states["fr-wait"] = transient

        body = _get(test_client, session_id, run.run_id).json()
        assert body["flow_status"] == "running"
        assert body["prefect_state"] == transient

    def test_a_restarted_flow_is_running_whatever_an_earlier_read_recorded(
        self, test_client, flows
    ):
        session_id = _create_session(test_client)
        run = _launch(test_client, session_id, "m-again", "fr-again")
        RunDocument.get_motor_collection().update_one(
            {"run_id": run.run_id},
            {"$set": {"flow_end_state": RunFlowEndState.COMPLETED.value}},
        )
        flows.states["fr-again"] = "RUNNING"

        body = _get(test_client, session_id, run.run_id).json()
        assert body["flow_status"] == "running"
        assert body["flow_end_state"] is None

    def test_prefect_unreadable_is_unavailable_not_running_or_ended(self, test_client, flows):
        session_id = _create_session(test_client)
        run = _launch(test_client, session_id, "m-down", "fr-down")
        _step_execution(str(run.execution_id), "fr-down", 1, "completed")
        RunDocument.get_motor_collection().update_one(
            {"run_id": run.run_id},
            {"$set": {"flow_end_state": RunFlowEndState.COMPLETED.value}},
        )
        flows.states["fr-down"] = "COMPLETED"
        flows.fail = True

        response = _get(test_client, session_id, run.run_id)
        assert response.status_code == 200
        body = response.json()
        assert body["flow_status"] == "unavailable"
        assert body["flow_end_state"] is None
        assert body["prefect_state"] is None
        assert "could not be read" in body["flow_status_reason"]

    def test_a_flow_run_prefect_does_not_report_is_unknown(self, test_client, flows):
        session_id = _create_session(test_client)
        run = _launch(test_client, session_id, "m-gone", "fr-gone")

        body = _get(test_client, session_id, run.run_id).json()
        assert body["flow_status"] == "unknown"
        assert body["flow_end_state"] is None

    def test_launch_outcomes_are_decided_without_prefect(self, test_client, flows):
        with prefect(side_effect=RuntimeError("prefect timed out")):
            response = _run(test_client, None, "lost")
        assert response.status_code >= 500
        _release_locks()
        [lost] = RunDocument.find({"idempotency_key": "lost"}).to_list()
        assert lost.status == RunDispatchStatus.UNKNOWN
        session_id = str(lost.calibration_session_id)

        body = _get(test_client, session_id, lost.run_id).json()
        assert body["flow_status"] == "unknown"

        RunDocument.get_motor_collection().update_one(
            {"run_id": lost.run_id}, {"$set": {"status": RunDispatchStatus.REJECTED.value}}
        )
        assert _get(test_client, session_id, lost.run_id).json()["flow_status"] == "not_launched"
        RunDocument.get_motor_collection().update_one(
            {"run_id": lost.run_id},
            {"$set": {"status": RunDispatchStatus.DISPATCHING.value, "updated_at": now()}},
        )
        assert _get(test_client, session_id, lost.run_id).json()["flow_status"] == "dispatching"
        assert flows.calls == []

    def test_an_automatic_session_is_not_closed_by_reading_its_ended_run(self, test_client, flows):
        run = _launch(test_client, None, "auto", "fr-auto")
        session_id = str(run.calibration_session_id)
        flows.states["fr-auto"] = "COMPLETED"

        body = _get(test_client, session_id, run.run_id).json()
        assert body["flow_status"] == "completed"
        assert _session_status(session_id) == CalibrationSessionStatus.OPEN


class TestLookup:
    def test_a_run_past_the_detail_page_is_found(self, test_client, flows):
        from qdash.api.services.calibration_session_service import MAX_DETAIL_CHILDREN

        session_id = _create_session(test_client)
        oldest = _launch(test_client, session_id, "old", "fr-old")
        base = now() - timedelta(hours=2)
        RunDocument.get_motor_collection().update_one(
            {"run_id": oldest.run_id}, {"$set": {"requested_at": base}}
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
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers())
        listed = {run["run_id"] for run in detail.json()["pipeline_runs"]}
        assert oldest.run_id not in listed
        flows.states["fr-old"] = "RUNNING"

        body = _get(test_client, session_id, oldest.run_id).json()
        assert body["run_id"] == oldest.run_id
        assert body["flow_status"] == "running"

    def test_runs_are_scoped_to_their_session_and_project(self, test_client, flows):
        first = _create_session(test_client)
        second = _create_session(test_client)
        run = _launch(test_client, first, "scoped", "fr-scoped")
        flows.states["fr-scoped"] = "RUNNING"

        assert _get(test_client, first, run.run_id, user="viewer").status_code == 200
        assert _get(test_client, second, run.run_id).status_code == 404
        assert _get(test_client, first, "cpr-missing").status_code == 404
        # The owner is a member of lab-b too; lab-a's session is not found from there.
        assert _get(test_client, first, run.run_id, project_id="lab-b").status_code == 404
        assert test_client.get(f"/calibration-sessions/{first}/runs/{run.run_id}").status_code in {
            401,
            403,
        }
        assert flows.calls == [["fr-scoped"]]
