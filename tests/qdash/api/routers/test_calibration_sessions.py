"""Calibration sessions: explicit grouping of pipeline runs and agent sessions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from qdash.api.services.flow_service.execution import EXECUTION_IN_PROGRESS_DETAIL
from qdash.api.services.flow_service.prefect_gateway import SystemDeployment
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentSessionStatus
from qdash.datamodel.calibration_plan import APPROVED_PLAN_CONTRACT, APPROVED_PLAN_CONTRACT_KEY
from qdash.datamodel.calibration_session import (
    CalibrationAdmission,
    CalibrationChildKind,
    CalibrationPipelineRunStatus,
    CalibrationRunKind,
)
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.user import UserDocument
from tests.qdash.api.routers.test_calibration_pipeline import calibrated_qubit_data, good_spec

if TYPE_CHECKING:
    from collections.abc import Iterator

CHIP = "64Qv3"
OTHER_CHIP = "16Qv1"
GATEWAY = "qdash.api.services.flow_service.prefect_gateway.PrefectGateway"


def _user(username: str, token: str) -> UserDocument:
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=token,
        default_project_id="lab-a",
        system_info=SystemInfoModel(),
    )
    user.insert()
    return user


def _member(project_id: str, user: UserDocument, role: ProjectRole) -> None:
    ProjectMembershipDocument(
        project_id=project_id,
        user_id=user.user_id,
        username=user.username,
        role=role,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="owner",
    ).insert()


def _headers(user: str = "owner", project_id: str = "lab-a") -> dict[str, str]:
    """Headers signed in as ``user`` (whose access token is ``<user>-token``)."""
    return {"Authorization": f"Bearer {user}-token", "X-Project-Id": project_id}


def _chip(project_id: str, chip_id: str) -> None:
    ChipDocument(
        chip_id=chip_id,
        username="owner",
        project_id=project_id,
        size=64,
        system_info=SystemInfoModel(),
    ).insert()
    for i in range(8):
        QubitDocument(
            project_id=project_id,
            username="owner",
            chip_id=chip_id,
            qid=str(i),
            status="pending",
            data=calibrated_qubit_data(),
            system_info={},
        ).insert()


@pytest.fixture
def lab(init_db):
    """Two projects; ``owner`` and ``colleague`` edit lab-a, ``viewer`` reads it."""
    owner = _user("owner", "owner-token")
    colleague = _user("colleague", "colleague-token")
    viewer = _user("viewer", "viewer-token")
    for project_id in ("lab-a", "lab-b"):
        ProjectDocument(
            project_id=project_id,
            name=project_id,
            owner_user_id=owner.user_id,
            owner_username="owner",
        ).insert()
        _chip(project_id, CHIP)
        for name, task_type in [
            ("CheckRabi", "qubit"),
            ("CheckT1", "qubit"),
            ("CheckT2Echo", "qubit"),
        ]:
            TaskDocument(
                project_id=project_id,
                username="owner",
                name=name,
                backend="qubex",
                description=name,
                task_type=task_type,
            ).insert()
    _chip("lab-a", OTHER_CHIP)
    _member("lab-a", owner, ProjectRole.OWNER)
    _member("lab-a", colleague, ProjectRole.EDITOR)
    _member("lab-a", viewer, ProjectRole.VIEWER)
    _member("lab-b", owner, ProjectRole.OWNER)


DEPLOYMENT_ID = UUID("00000000-0000-0000-0000-0000000000d1")
# The schema a deployment of the current pipeline flow records for ``approved_plan``.
PLAN_READY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spec": {"type": "object"},
        "approved_plan": {
            "anyOf": [{"type": "object"}, {"type": "null"}],
            "default": None,
            APPROVED_PLAN_CONTRACT_KEY: APPROVED_PLAN_CONTRACT,
        },
    },
}


@contextmanager
def prefect(
    flow_run_ids: list[str] | None = None,
    *,
    side_effect: Any = None,
    parameter_schema: Any = PLAN_READY_SCHEMA,
) -> Iterator[AsyncMock]:
    """Patch Prefect so each created flow run gets the next ID from ``flow_run_ids``.

    The pipeline deployment reports ``parameter_schema`` as its registered parameter schema;
    by default one that accepts an approved plan.
    """
    create = AsyncMock(side_effect=side_effect or list(flow_run_ids or ["flow-run-1"]))
    deployment = SystemDeployment(id=DEPLOYMENT_ID, parameter_schema=parameter_schema)
    with (
        patch(f"{GATEWAY}.read_deployment_id", new=AsyncMock(return_value="deployment-1")),
        patch(f"{GATEWAY}.read_deployment", new=AsyncMock(return_value=deployment)),
        patch(f"{GATEWAY}.create_flow_run", new=create),
    ):
        yield create


def _create_session(test_client, chip_id: str = CHIP, user: str = "owner") -> str:
    response = test_client.post(
        "/calibration-sessions",
        headers=_headers(user),
        json={"chip_id": chip_id, "objective": "Bring up qubits 0 and 1"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["calibration_session_id"])


def _run(
    test_client,
    session_id: str | None,
    key: str | None = "run-1",
    *,
    user: str = "owner",
    chip_id: str = CHIP,
    spec: dict[str, Any] | None = None,
):
    body: dict[str, Any] = {"chip_id": chip_id, "spec": spec or good_spec()}
    if session_id is not None:
        body["calibration_session_id"] = session_id
    if key is not None:
        body["idempotency_key"] = key
    return test_client.post("/calibration-pipelines/execute", headers=_headers(user), json=body)


def _release_locks() -> None:
    ExecutionLockDocument.get_motor_collection().delete_many({})


def _step_execution(
    execution_id: str,
    flow_run_id: str,
    step_index: int,
    status: str,
    *,
    chip_id: str = CHIP,
    project_id: str = "lab-a",
) -> None:
    """An execution the pipeline flow records for one calibration step (replacing the row
    QDash pre-created for it, as the flow's adoption does)."""
    ExecutionHistoryDocument.get_motor_collection().delete_many(
        {"project_id": project_id, "execution_id": execution_id}
    )
    ExecutionHistoryDocument(
        project_id=project_id,
        username="owner",
        name=f"coarse-then-coherence_step{step_index}",
        execution_id=execution_id,
        calib_data_path="/tmp",
        note={
            "flow_run_id": flow_run_id,
            "step_index": step_index,
            "pipeline": {
                "name": "coarse-then-coherence",
                "steps": [
                    {"index": 1, "name": "OneQubitCheck", "type": "OneQubitCheck"},
                    {"index": 2, "name": "FilterByStatus", "kind": "transform"},
                    {"index": 3, "name": "coherence", "type": "CustomOneQubit"},
                ],
            },
        },
        status=status,
        tags=["pipeline"],
        chip_id=chip_id,
        start_at=now() + timedelta(seconds=step_index),
        message="",
        system_info=SystemInfoModel(),
    ).insert()


class TestSessions:
    def test_create_get_and_list(self, test_client, lab):
        session_id = _create_session(test_client)
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers())
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["created_by"] == "owner"
        assert body["status"] == "open"
        assert body["pipeline_runs"] == []
        assert body["agent_sessions"] == []
        assert body["close_blockers"] == []

        listed = test_client.get(
            "/calibration-sessions", headers=_headers(), params={"chip_id": CHIP}
        ).json()
        assert [item["calibration_session_id"] for item in listed["items"]] == [session_id]
        # Another project does not see it.
        other = test_client.get(
            f"/calibration-sessions/{session_id}", headers=_headers(project_id="lab-b")
        )
        assert other.status_code == 404

    def test_viewer_cannot_create_and_unknown_chip_is_404(self, test_client, lab):
        viewer = test_client.post(
            "/calibration-sessions",
            headers=_headers("viewer"),
            json={"chip_id": CHIP, "objective": "x"},
        )
        assert viewer.status_code == 403
        missing = test_client.post(
            "/calibration-sessions", headers=_headers(), json={"chip_id": "nope", "objective": "x"}
        )
        assert missing.status_code == 404


class TestPipelineRuns:
    def test_pipeline_without_session_gets_an_automatic_one(self, test_client, lab):
        with prefect(["flow-run-plain"]) as create:
            response = _run(test_client, None, key=None)
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["flow_run_id"] == "flow-run-plain"
        session_id = body["calibration_session_id"]
        assert session_id.startswith("cs-auto-")
        assert body["pipeline_run_id"] == body["calibration_run_id"]
        assert create.await_count == 1
        [record] = CalibrationPipelineRunDocument.find_all().to_list()
        assert record.calibration_session_id == session_id
        assert record.run_kind == CalibrationRunKind.PIPELINE
        assert record.status == CalibrationPipelineRunStatus.DISPATCHED
        # The worker receives the run before it starts, and the pre-created step names it.
        assert create.await_args is not None
        context = create.await_args.kwargs["context"]
        # With the launch's dispatch token, which only this flow run receives.
        assert context["qdash_calibration_run"] == {
            "calibration_session_id": session_id,
            "run_id": record.run_id,
            "dispatch_token": record.dispatch_token,
        }
        assert record.dispatch_token not in response.text
        execution = ExecutionHistoryDocument.find_one({"execution_id": body["execution_id"]}).run()
        assert execution is not None
        assert execution.note["calibration_session_id"] == session_id
        assert execution.note["calibration_run_id"] == record.run_id
        session = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers())
        assert session.json()["origin"] == "automatic"
        assert session.json()["created_by"] == "owner"

    def test_unkeyed_requests_are_new_runs_and_a_key_replays_one(self, test_client, lab):
        with prefect(["flow-run-a", "flow-run-b", "flow-run-c"]) as create:
            first = _run(test_client, None, key=None)
            _release_locks()
            second = _run(test_client, None, key=None)
            _release_locks()
            keyed = _run(test_client, None, key="k")
            _release_locks()
            again = _run(test_client, None, key="k")
        assert {r.status_code for r in (first, second, keyed, again)} == {202}
        # Without a key every request is a new run in a new automatic session.
        assert first.json()["calibration_session_id"] != second.json()["calibration_session_id"]
        # A keyed retry reaches the same session and run and launches nothing.
        assert again.json()["calibration_session_id"] == keyed.json()["calibration_session_id"]
        assert again.json()["calibration_run_id"] == keyed.json()["calibration_run_id"]
        assert again.json()["replayed"] is True
        assert create.await_count == 3
        assert CalibrationSessionDocument.find_all().count() == 3

    def test_a_named_session_takes_a_server_key_and_a_decision_needs_one(self, test_client, lab):
        session_id = _create_session(test_client)
        with prefect(["flow-run-a"]) as create:
            response = _run(test_client, session_id, key=None)
            assert response.status_code == 202, response.text
            assert response.json()["calibration_session_id"] == session_id
            body = {"chip_id": CHIP, "spec": good_spec(), "decision_id": "d-1"}
            refused = test_client.post(
                "/calibration-pipelines/execute", headers=_headers(), json=body
            )
            assert refused.status_code == 422
        assert create.await_count == 1

    def test_an_invalid_spec_leaves_no_automatic_session(self, test_client, lab):
        with prefect() as create:
            response = _run(test_client, None, key="k", spec={"name": "x", "steps": "no"})
        assert response.status_code == 422
        create.assert_not_awaited()
        assert CalibrationSessionDocument.find_all().count() == 0
        assert CalibrationPipelineRunDocument.find_all().count() == 0

    def test_one_run_groups_every_step_execution_of_its_flow_run(self, test_client, lab):
        session_id = _create_session(test_client)
        with prefect(["flow-run-a"]):
            response = _run(test_client, session_id)
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["calibration_session_id"] == session_id
        assert body["replayed"] is False
        first_execution = body["execution_id"]

        # The flow adopts the pre-created row for step 1 and records step 3 itself.
        _step_execution(first_execution, "flow-run-a", 1, "completed")
        _step_execution("step-3-exec", "flow-run-a", 3, "running")
        # Neither another flow run's execution nor one on another chip with the same
        # flow run ID belongs to the run.
        _step_execution("unrelated", "flow-run-b", 1, "completed")
        _step_execution("other-chip", "flow-run-a", 1, "completed", chip_id=OTHER_CHIP)

        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        [run] = detail["pipeline_runs"]
        assert run["dispatch_status"] == "dispatched"
        assert run["flow_run_id"] == "flow-run-a"
        assert run["execution_id"] == first_execution
        assert [e["execution_id"] for e in run["executions"]] == [first_execution, "step-3-exec"]
        steps = {step["index"]: step for step in run["pipeline"]["steps"]}
        assert steps[1]["execution_id"] == first_execution
        # The plan carries no transform-recording marker, as in runs recorded before
        # transforms had executions: its filter is reported as not recorded, never pending.
        assert steps[2]["status"] == "not_recorded"
        assert steps[3]["execution_id"] == "step-3-exec"
        assert run["pipeline"]["status"] == "running"
        assert detail["close_blockers"] == [f"pipeline run {run['run_id']} is running"]

    def test_retry_with_the_same_key_returns_the_recorded_run(self, test_client, lab):
        session_id = _create_session(test_client)
        with prefect(["flow-run-a", "flow-run-b"]) as create:
            first = _run(test_client, session_id)
            _release_locks()
            again = _run(test_client, session_id)
            changed = _run(test_client, session_id, spec={**good_spec(), "name": "other"})
        assert first.status_code == 202 and again.status_code == 202, again.text
        assert again.json()["replayed"] is True
        assert again.json()["flow_run_id"] == first.json()["flow_run_id"] == "flow-run-a"
        assert again.json()["pipeline_run_id"] == first.json()["pipeline_run_id"]
        assert changed.status_code == 409
        assert create.await_count == 1
        assert CalibrationPipelineRunDocument.find_all().count() == 1

    def test_failed_launch_stays_unknown_and_is_never_relaunched(self, test_client, lab):
        session_id = _create_session(test_client)
        with prefect(side_effect=RuntimeError("prefect timed out")) as create:
            failed = _run(test_client, session_id)
        assert failed.status_code == 500
        assert "may have started" in failed.json()["detail"]
        [record] = CalibrationPipelineRunDocument.find_all().to_list()
        assert record.status == CalibrationPipelineRunStatus.UNKNOWN

        with prefect(["flow-run-late"]) as retry:
            again = _run(test_client, session_id)
        assert again.status_code == 409
        assert "unknown" in again.json()["detail"]
        retry.assert_not_awaited()
        assert create.await_count == 1
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        assert detail["unknown_runs"] == [record.run_id]

    def test_launch_that_never_reported_back_is_not_relaunched(self, test_client, lab):
        session_id = _create_session(test_client)
        CalibrationPipelineRunDocument(
            run_id="cpr-crashed",
            project_id="lab-a",
            calibration_session_id=session_id,
            chip_id=CHIP,
            idempotency_key="run-1",
            request_hash=_hash(good_spec()),
            requested_by="owner",
            dispatch_token="t",
            updated_at=now() - timedelta(hours=1),
        ).insert()
        with prefect() as create:
            again = _run(test_client, session_id)
        assert again.status_code == 409
        create.assert_not_awaited()
        run = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()[
            "pipeline_runs"
        ][0]
        assert run["dispatch_status"] == "unknown"

    def test_busy_hardware_refuses_before_a_named_session_records_anything(self, test_client, lab):
        session_id = _create_session(test_client)
        with prefect(["flow-run-busy", "flow-run-a"]) as create:
            # An unrelated run holds the chip.
            assert _run(test_client, None, key=None).status_code == 202
            executions = ExecutionHistoryDocument.find_all().count()
            before = _session_doc(session_id)
            refused = _run(test_client, session_id)
            assert refused.status_code == 409
            assert refused.json()["detail"] == EXECUTION_IN_PROGRESS_DETAIL
            # No run, reservation, admission count, or execution; nothing reached Prefect.
            assert (
                CalibrationPipelineRunDocument.find({"calibration_session_id": session_id}).count()
                == 0
            )
            after = _session_doc(session_id)
            assert after.child_count == before.child_count
            assert after.pending_children == []
            assert ExecutionHistoryDocument.find_all().count() == executions
            assert create.await_count == 1
            _release_locks()
            retried = _run(test_client, session_id)
        assert retried.status_code == 202, retried.text
        assert retried.json()["flow_run_id"] == "flow-run-a"
        assert retried.json()["replayed"] is False
        assert create.await_count == 2
        [record] = CalibrationPipelineRunDocument.find(
            {"calibration_session_id": session_id}
        ).to_list()
        assert record.status == CalibrationPipelineRunStatus.DISPATCHED
        assert record.attempts == 1

    def test_busy_hardware_refuses_before_an_automatic_session_is_created(self, test_client, lab):
        with prefect(["flow-run-busy"]) as create:
            assert _run(test_client, None, key=None).status_code == 202
            sessions = CalibrationSessionDocument.find_all().count()
            executions = ExecutionHistoryDocument.find_all().count()
            unkeyed = _run(test_client, None, key=None)
            keyed = _run(test_client, None, key="k")
        assert unkeyed.status_code == keyed.status_code == 409
        assert create.await_count == 1
        assert CalibrationSessionDocument.find_all().count() == sessions
        assert CalibrationPipelineRunDocument.find_all().count() == 1
        assert ExecutionHistoryDocument.find_all().count() == executions

    def test_a_retry_replays_its_run_while_that_run_holds_the_chip(self, test_client, lab):
        with prefect(["flow-run-a"]) as create:
            first = _run(test_client, None, key="k")
            # The lock is still held by the first run's own execution.
            again = _run(test_client, None, key="k")
        assert first.status_code == again.status_code == 202, again.text
        assert again.json()["replayed"] is True
        assert again.json()["flow_run_id"] == "flow-run-a"
        assert again.json()["calibration_run_id"] == first.json()["calibration_run_id"]
        assert create.await_count == 1

    def test_a_claim_taken_after_the_preflight_still_refuses_the_launch(self, test_client, lab):
        from qdash.api.services.flow_service.execution import ExecutionCoordinator

        with prefect(["flow-run-busy", "flow-run-a"]) as create:
            assert _run(test_client, None, key=None).status_code == 202
            executions = ExecutionHistoryDocument.find_all().count()
            # Another run claims the chip between the preflight check and the claim.
            with patch.object(ExecutionCoordinator, "ensure_available", return_value=None):
                late = _run(test_client, None, key="k")
            assert late.status_code == 409
            assert late.json()["detail"] == EXECUTION_IN_PROGRESS_DETAIL
            assert create.await_count == 1
            assert ExecutionHistoryDocument.find_all().count() == executions
            # The late refusal is recorded as rejected, as before the preflight existed.
            [rejected] = CalibrationPipelineRunDocument.find({"idempotency_key": "k"}).to_list()
            assert rejected.status == CalibrationPipelineRunStatus.REJECTED
            assert rejected.attempts == 1
            # Its retry while the chip is still busy is refused before another attempt.
            assert _run(test_client, None, key="k").status_code == 409
            [still] = CalibrationPipelineRunDocument.find({"idempotency_key": "k"}).to_list()
            assert still.attempts == 1
            _release_locks()
            retried = _run(test_client, None, key="k")
        assert retried.status_code == 202, retried.text
        assert retried.json()["calibration_run_id"] == rejected.run_id
        assert create.await_count == 2

    def test_missing_deployment_is_a_refusal(self, test_client, lab):
        from qdash.api.services.flow_service.prefect_gateway import SystemDeploymentUnavailable

        session_id = _create_session(test_client)
        with patch(
            f"{GATEWAY}.read_deployment_id",
            new=AsyncMock(side_effect=SystemDeploymentUnavailable("missing")),
        ):
            response = _run(test_client, session_id)
        assert response.status_code == 503
        [record] = CalibrationPipelineRunDocument.find_all().to_list()
        assert record.status == CalibrationPipelineRunStatus.REJECTED

    def test_invalid_spec_records_nothing(self, test_client, lab):
        session_id = _create_session(test_client)
        spec = good_spec()
        spec["targets"] = {"qids": ["99"]}
        with prefect() as create:
            response = _run(test_client, session_id, spec=spec)
        assert response.status_code == 422
        create.assert_not_awaited()
        assert CalibrationPipelineRunDocument.find_all().count() == 0


def _hash(spec: dict[str, Any]) -> str:
    from qdash.api.services.calibration_session_service import pipeline_request_hash

    return pipeline_request_hash(CHIP, spec, None)


class TestAccess:
    def test_runs_attach_only_to_an_open_own_session_on_the_chip(self, test_client, lab):
        session_id = _create_session(test_client)
        with prefect() as create:
            # A colleague may read it but not start work in it.
            assert _run(test_client, session_id, user="colleague").status_code == 403
            assert (
                test_client.get(
                    f"/calibration-sessions/{session_id}", headers=_headers("colleague")
                ).status_code
                == 200
            )
            # Another chip, another project, an unknown ID.
            assert _run(test_client, session_id, chip_id=OTHER_CHIP).status_code == 422
            other_project = test_client.post(
                "/calibration-pipelines/execute",
                headers=_headers(project_id="lab-b"),
                json={
                    "chip_id": CHIP,
                    "spec": good_spec(),
                    "calibration_session_id": session_id,
                    "idempotency_key": "k",
                },
            )
            assert other_project.status_code == 404
            assert _run(test_client, "cs-unknown").status_code == 404
        create.assert_not_awaited()
        assert CalibrationPipelineRunDocument.find_all().count() == 0

    def test_agent_session_attaches_with_the_same_checks(self, test_client, lab):
        session_id = _create_session(test_client)
        policy = {"qids": ["0"], "allowed_tasks": ["CheckRabi"]}

        def create(user: str = "owner", chip_id: str = CHIP, cs: str | None = session_id):
            body: dict[str, Any] = {"chip_id": chip_id, "policy": policy}
            if cs is not None:
                body["calibration_session_id"] = cs
            return test_client.post("/agent-sessions", headers=_headers(user), json=body)

        assert create(user="colleague").status_code == 403
        assert create(chip_id=OTHER_CHIP).status_code == 422
        assert create(cs="cs-unknown").status_code == 404
        plain = create(cs=None)
        assert plain.status_code == 201
        # Started alone, it gets an automatic session of its own and is admitted to it.
        automatic = plain.json()["calibration_session_id"]
        assert automatic.startswith("cs-auto-") and automatic != session_id
        assert plain.json()["calibration_admission"] == "admitted"
        auto_doc = CalibrationSessionDocument.find_one({"calibration_session_id": automatic}).run()
        assert auto_doc is not None and auto_doc.origin == "automatic"
        assert auto_doc.created_by == "owner" and auto_doc.chip_id == CHIP
        attached = create()
        assert attached.status_code == 201, attached.text
        assert attached.json()["calibration_session_id"] == session_id
        assert AgentSessionDocument.find_all().count() == 2

        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        assert [child["session_id"] for child in detail["agent_sessions"]] == [
            attached.json()["session_id"]
        ]
        assert detail["agent_sessions"][0]["status"] == "active"
        assert detail["close_blockers"] == [
            f"agent session {attached.json()['session_id']} is active"
        ]


class TestClose:
    def test_close_waits_for_children_and_then_refuses_new_ones(self, test_client, lab):
        session_id = _create_session(test_client)
        created = test_client.post(
            "/agent-sessions",
            headers=_headers(),
            json={
                "chip_id": CHIP,
                "policy": {"qids": ["0"], "allowed_tasks": ["CheckRabi"]},
                "calibration_session_id": session_id,
            },
        )
        agent_id = created.json()["session_id"]
        close = f"/calibration-sessions/{session_id}/close"
        assert test_client.post(close, headers=_headers(), json={}).status_code == 409
        assert test_client.post(close, headers=_headers("colleague"), json={}).status_code == 403

        agent = AgentSessionDocument.find_one({"session_id": agent_id}).run()
        assert agent is not None
        agent.status = AgentSessionStatus.COMPLETED
        agent.save()
        closed = test_client.post(close, headers=_headers(), json={"closing_note": "done"})
        assert closed.status_code == 200, closed.text
        assert closed.json()["status"] == "closed"
        assert closed.json()["closed_by"] == "owner"
        # The agent session's own record is untouched by the close.
        untouched = AgentSessionDocument.find_one({"session_id": agent_id}).run()
        assert untouched is not None
        assert untouched.status == AgentSessionStatus.COMPLETED

        with prefect() as launch:
            assert _run(test_client, session_id).status_code == 409
        launch.assert_not_awaited()
        again = test_client.post(
            "/agent-sessions",
            headers=_headers(),
            json={
                "chip_id": CHIP,
                "policy": {"qids": ["0"], "allowed_tasks": ["CheckRabi"]},
                "calibration_session_id": session_id,
            },
        )
        assert again.status_code == 409

    def test_unknown_runs_need_acknowledgment(self, test_client, lab):
        session_id = _create_session(test_client)
        with prefect(side_effect=RuntimeError("lost")):
            _run(test_client, session_id)
        close = f"/calibration-sessions/{session_id}/close"
        assert test_client.post(close, headers=_headers(), json={}).status_code == 409
        closed = test_client.post(
            close, headers=_headers(), json={"acknowledge_unknown_runs": True}
        )
        assert closed.status_code == 200, closed.text
        assert len(closed.json()["closed_with_unknown_runs"]) == 1

    def test_a_child_reserved_after_the_close_read_the_session_fails_the_close(
        self, test_client, lab
    ):
        from qdash.api.services.calibration_session_service import CalibrationSessionService

        session_id = _create_session(test_client)
        original = CalibrationSessionService._blockers

        def blockers_then_start_a_child(self, doc):
            found = original(self, doc)
            # A run is reserved after the close read the session and its children.
            CalibrationSessionService().reserve_child(
                project_id="lab-a",
                calibration_session_id=session_id,
                chip_id=CHIP,
                username="owner",
                kind=CalibrationChildKind.AGENT_SESSION,
                child_id="late-agent",
            )
            return found

        with patch.object(CalibrationSessionService, "_blockers", blockers_then_start_a_child):
            response = test_client.post(
                f"/calibration-sessions/{session_id}/close", headers=_headers(), json={}
            )
        assert response.status_code == 409
        doc = _session_doc(session_id)
        assert doc.status == "open"
        assert [r.child_id for r in doc.pending_children] == ["late-agent"]


POLICY = {"qids": ["0"], "allowed_tasks": ["CheckRabi"]}


def _session_doc(session_id: str) -> CalibrationSessionDocument:
    doc = CalibrationSessionDocument.find_one({"calibration_session_id": session_id}).run()
    assert doc is not None
    return doc


def _age_reservations(session_id: str, minutes: int = 10) -> None:
    """Make every pending reservation of the session older than a request takes."""
    doc = _session_doc(session_id)
    for index in range(len(doc.pending_children)):
        CalibrationSessionDocument.get_motor_collection().update_one(
            {"calibration_session_id": session_id},
            {"$set": {f"pending_children.{index}.reserved_at": now() - timedelta(minutes=minutes)}},
        )


def _close_directly(session_id: str, *, acknowledge: bool = False):
    """Close through the service, as a concurrent request would."""
    from qdash.api.schemas.calibration_session import CloseCalibrationSessionRequest
    from qdash.api.services.calibration_session_service import CalibrationSessionService

    return CalibrationSessionService().close(
        project_id="lab-a",
        calibration_session_id=session_id,
        username="owner",
        body=CloseCalibrationSessionRequest(acknowledge_unknown_runs=acknowledge),
    )


def _create_agent_directly(session_id: str):
    from qdash.api.schemas.agent_session import CreateAgentSessionRequest
    from qdash.api.services.agent_session_service import AgentSessionService

    return AgentSessionService().create_session(
        project_id="lab-a",
        username="owner",
        body=CreateAgentSessionRequest.model_validate(
            {"chip_id": CHIP, "policy": POLICY, "calibration_session_id": session_id}
        ),
    )


class TestAgentStartReservation:
    def test_close_between_reservation_and_record_is_refused(self, test_client, lab):
        from fastapi import HTTPException

        session_id = _create_session(test_client)
        original = AgentSessionDocument.insert
        refusals: list[HTTPException] = []

        def close_then_insert(self, *args, **kwargs):
            # The child is counted and reserved, its record not written yet.
            try:
                _close_directly(session_id, acknowledge=True)
            except HTTPException as exc:
                refusals.append(exc)
            return original(self, *args, **kwargs)

        with patch.object(AgentSessionDocument, "insert", close_then_insert):
            created = test_client.post(
                "/agent-sessions",
                headers=_headers(),
                json={"chip_id": CHIP, "policy": POLICY, "calibration_session_id": session_id},
            )
        assert created.status_code == 201, created.text
        [refusal] = refusals
        assert refusal.status_code == 409
        assert "is being started" in str(refusal.detail)
        doc = _session_doc(session_id)
        assert doc.status == "open"
        assert doc.pending_children == []
        assert doc.child_count == 1

    def test_crash_before_the_record_stays_explicit_until_acknowledged(self, test_client, lab):
        session_id = _create_session(test_client)
        with (
            patch.object(AgentSessionDocument, "insert", side_effect=RuntimeError("crash")),
            pytest.raises(RuntimeError),
        ):
            _create_agent_directly(session_id)
        [reservation] = _session_doc(session_id).pending_children
        close = f"/calibration-sessions/{session_id}/close"

        recent = test_client.post(close, headers=_headers(), json={})
        assert recent.status_code == 409
        assert "being started" in recent.json()["detail"]

        _age_reservations(session_id)
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        assert [r["child_id"] for r in detail["unknown_starts"]] == [reservation.child_id]
        assert detail["close_blockers"] == []
        unacknowledged = test_client.post(close, headers=_headers(), json={})
        assert unacknowledged.status_code == 409
        assert f"agent session {reservation.child_id}" in unacknowledged.json()["detail"]

        closed = test_client.post(
            close, headers=_headers(), json={"acknowledge_unknown_runs": True}
        )
        assert closed.status_code == 200, closed.text
        assert [r["child_id"] for r in closed.json()["closed_with_unknown_starts"]] == [
            reservation.child_id
        ]
        assert _session_doc(session_id).pending_children == []

    def test_record_written_after_an_acknowledged_close_is_cancelled(self, test_client, lab):
        session_id = _create_session(test_client)
        original = AgentSessionDocument.insert

        def stall_past_a_close(self, *args, **kwargs):
            # The request hangs past the stale limit; the person closes acknowledging it.
            _age_reservations(session_id)
            _close_directly(session_id, acknowledge=True)
            return original(self, *args, **kwargs)

        with patch.object(AgentSessionDocument, "insert", stall_past_a_close):
            late = test_client.post(
                "/agent-sessions",
                headers=_headers(),
                json={"chip_id": CHIP, "policy": POLICY, "calibration_session_id": session_id},
            )
        assert late.status_code == 409
        assert "rejected and cancelled before it could operate" in late.json()["detail"]
        [agent] = AgentSessionDocument.find_all().to_list()
        assert agent.status == AgentSessionStatus.CANCELLED
        assert agent.calibration_admission == CalibrationAdmission.REJECTED
        doc = _session_doc(session_id)
        assert doc.status == "closed"
        assert [r.child_id for r in doc.closed_with_unknown_starts] == [agent.session_id]

    def test_a_record_known_not_written_releases_the_reservation(self, test_client, lab):
        from pymongo.errors import DuplicateKeyError

        session_id = _create_session(test_client)
        with (
            patch.object(AgentSessionDocument, "insert", side_effect=DuplicateKeyError("dup")),
            pytest.raises(DuplicateKeyError),
        ):
            _create_agent_directly(session_id)
        assert _session_doc(session_id).pending_children == []
        closed = test_client.post(
            f"/calibration-sessions/{session_id}/close", headers=_headers(), json={}
        )
        assert closed.status_code == 200, closed.text


class TestPipelineStartReservation:
    def test_close_while_a_run_is_being_claimed_is_refused(self, test_client, lab):
        from fastapi import HTTPException

        from qdash.api.services.run_ledger import RunLedger

        session_id = _create_session(test_client)
        original = RunLedger._claim
        refusals: list[HTTPException] = []

        def close_then_claim(**kwargs):
            try:
                _close_directly(session_id, acknowledge=True)
            except HTTPException as exc:
                refusals.append(exc)
            return original(**kwargs)

        with (
            patch.object(RunLedger, "_claim", staticmethod(close_then_claim)),
            prefect(["flow-run-a"]) as create,
        ):
            response = _run(test_client, session_id)
        assert response.status_code == 202, response.text
        assert create.await_count == 1
        [refusal] = refusals
        assert "run cpr-" in str(refusal.detail) and "being started" in str(refusal.detail)
        assert _session_doc(session_id).status == "open"
        assert _session_doc(session_id).pending_children == []

    def test_a_request_whose_reservation_a_close_cleared_never_launches(self, test_client, lab):
        from qdash.api.services.run_ledger import RunLedger

        session_id = _create_session(test_client)
        original = RunLedger._claim

        def stall_past_a_close(**kwargs):
            # A reservation this old was never launched, so the close needs no acknowledgment.
            _age_reservations(session_id)
            _close_directly(session_id)
            return original(**kwargs)

        with (
            patch.object(RunLedger, "_claim", staticmethod(stall_past_a_close)),
            prefect(["flow-run-a"]) as create,
        ):
            response = _run(test_client, session_id)
        assert response.status_code == 409
        assert "closed" in response.json()["detail"]
        create.assert_not_awaited()
        [record] = CalibrationPipelineRunDocument.find_all().to_list()
        assert record.status == CalibrationPipelineRunStatus.REJECTED
        assert _session_doc(session_id).status == "closed"

    def test_failure_before_launch_releases_and_rejects(self, test_client, lab):
        from qdash.api.services.calibration_session_service import CalibrationSessionService

        session_id = _create_session(test_client)
        original = CalibrationSessionService.finalize_child
        calls: list[str] = []

        def lose_the_first_answer(**kwargs):
            # The removal's answer is lost; whether it was applied is unknown.
            calls.append(kwargs["reservation_id"])
            if len(calls) == 1:
                raise RuntimeError("lost")
            return original(**kwargs)

        with (
            patch.object(
                CalibrationSessionService, "finalize_child", staticmethod(lose_the_first_answer)
            ),
            prefect(["flow-run-a"]) as create,
            pytest.raises(RuntimeError),
        ):
            _run(test_client, session_id)
        create.assert_not_awaited()
        [record] = CalibrationPipelineRunDocument.find_all().to_list()
        assert record.status == CalibrationPipelineRunStatus.REJECTED
        assert _session_doc(session_id).pending_children == []
        with prefect(["flow-run-a"]) as retry:
            again = _run(test_client, session_id)
        assert again.status_code == 202, again.text
        assert retry.await_count == 1

    def test_a_crashed_request_before_launch_is_recovered_as_not_started(self, test_client, lab):
        session_id = _create_session(test_client)
        old = now() - timedelta(minutes=30)
        CalibrationSessionDocument.get_motor_collection().update_one(
            {"calibration_session_id": session_id},
            {
                "$inc": {"child_count": 1},
                "$push": {
                    "pending_children": {
                        "reservation_id": "csr-crashed",
                        "kind": "pipeline_run",
                        "child_id": "cpr-crashed",
                        "reserved_by": "owner",
                        "reserved_at": old,
                    }
                },
            },
        )
        CalibrationPipelineRunDocument(
            run_id="cpr-crashed",
            reservation_id="csr-crashed",
            project_id="lab-a",
            calibration_session_id=session_id,
            chip_id=CHIP,
            idempotency_key="run-1",
            request_hash=_hash(good_spec()),
            requested_by="owner",
            dispatch_token="t",
            requested_at=old,
            updated_at=old,
        ).insert()
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        assert detail["pipeline_runs"][0]["dispatch_status"] == "rejected"
        assert detail["unknown_runs"] == [] and detail["close_blockers"] == []
        with prefect(["flow-run-a"]) as create:
            retried = _run(test_client, session_id)
        assert retried.status_code == 202, retried.text
        assert create.await_count == 1


class TestExhaustiveClose:
    def test_a_running_run_past_the_listed_page_blocks_the_close(self, test_client, lab):
        from qdash.api.services.calibration_session_service import MAX_DETAIL_CHILDREN

        session_id = _create_session(test_client)
        base = now() - timedelta(hours=2)
        for index in range(MAX_DETAIL_CHILDREN + 1):
            CalibrationPipelineRunDocument(
                run_id=f"cpr-{index:03d}",
                project_id="lab-a",
                calibration_session_id=session_id,
                chip_id=CHIP,
                idempotency_key=f"k-{index}",
                request_hash="h",
                requested_by="owner",
                dispatch_token="t",
                # The oldest is still being dispatched; the rest were refused.
                status=(
                    CalibrationPipelineRunStatus.DISPATCHING
                    if index == 0
                    else CalibrationPipelineRunStatus.REJECTED
                ),
                requested_at=base + timedelta(seconds=index),
                updated_at=now(),
            ).insert()
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        assert len(detail["pipeline_runs"]) == MAX_DETAIL_CHILDREN
        assert detail["pipeline_run_total"] == MAX_DETAIL_CHILDREN + 1
        assert "cpr-000" not in [run["run_id"] for run in detail["pipeline_runs"]]
        assert detail["close_blockers"] == ["pipeline run cpr-000 is being dispatched"]
        close = test_client.post(
            f"/calibration-sessions/{session_id}/close", headers=_headers(), json={}
        )
        assert close.status_code == 409

    def test_an_active_agent_session_past_the_listed_page_blocks_the_close(self, test_client, lab):
        from qdash.api.services.calibration_session_service import MAX_DETAIL_CHILDREN
        from qdash.datamodel.agent_session import AgentSessionPolicy

        session_id = _create_session(test_client)
        base = now() - timedelta(hours=2)
        for index in range(MAX_DETAIL_CHILDREN + 1):
            AgentSessionDocument(
                session_id=f"agent-{index:03d}",
                project_id="lab-a",
                chip_id=CHIP,
                created_by="owner",
                policy=AgentSessionPolicy.model_validate(POLICY),
                status=AgentSessionStatus.ACTIVE if index == 0 else AgentSessionStatus.COMPLETED,
                created_at=base + timedelta(seconds=index),
                expires_at=now() + timedelta(hours=1),
                calibration_session_id=session_id,
            ).insert()
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        assert len(detail["agent_sessions"]) == MAX_DETAIL_CHILDREN
        assert detail["agent_session_total"] == MAX_DETAIL_CHILDREN + 1
        assert "agent-000" not in [a["session_id"] for a in detail["agent_sessions"]]
        assert detail["close_blockers"] == ["agent session agent-000 is active"]
        close = test_client.post(
            f"/calibration-sessions/{session_id}/close", headers=_headers(), json={}
        )
        assert close.status_code == 409


def _agent_action(session_id: str, execution_status: str, **fields: Any) -> None:
    from qdash.datamodel.agent_session import AgentActionDecision, AgentActionType
    from qdash.dbmodel.agent_session import AgentActionDocument

    AgentActionDocument(
        action_id=f"action-{session_id}",
        session_id=session_id,
        project_id="lab-a",
        idempotency_key="k",
        request_hash="h",
        action_type=AgentActionType.RUN_TASK,
        task_name="CheckRabi",
        qids=["0"],
        decision=AgentActionDecision.AUTHORIZED,
        reason="",
        execution_status=execution_status,
        state_version_before=0,
        state_version_after=1,
        **fields,
    ).insert()


class TestEndedAgentInFlight:
    def _agent(self, test_client, session_id: str) -> str:
        created = test_client.post(
            "/agent-sessions",
            headers=_headers(),
            json={"chip_id": CHIP, "policy": POLICY, "calibration_session_id": session_id},
        )
        assert created.status_code == 201, created.text
        return str(created.json()["session_id"])

    def test_an_ended_session_dispatching_a_measurement_blocks_the_close(self, test_client, lab):
        session_id = _create_session(test_client)
        agent_id = self._agent(test_client, session_id)
        AgentSessionDocument.get_motor_collection().update_one(
            {"session_id": agent_id}, {"$set": {"status": AgentSessionStatus.COMPLETED.value}}
        )
        # It passed the gate before the end and has no execution yet.
        _agent_action(
            agent_id,
            "dispatching",
            dispatch_token="t",
            dispatch_confirmed=True,
            dispatch_reserved_at=now(),
        )
        close = f"/calibration-sessions/{session_id}/close"
        refused = test_client.post(close, headers=_headers(), json={})
        assert refused.status_code == 409
        assert (
            f"agent session {agent_id} measurement action-{agent_id} is dispatching"
            in (refused.json()["detail"])
        )

    def test_a_session_expiring_while_its_measurement_is_queued_blocks_the_close(
        self, test_client, lab
    ):
        from qdash.dbmodel.agent_session import AgentActionDocument

        session_id = _create_session(test_client)
        agent_id = self._agent(test_client, session_id)
        AgentSessionDocument.get_motor_collection().update_one(
            {"session_id": agent_id}, {"$set": {"expires_at": now() - timedelta(minutes=1)}}
        )
        _agent_action(agent_id, "queued", operation_id="flow-run-q")
        close = f"/calibration-sessions/{session_id}/close"
        refused = test_client.post(close, headers=_headers(), json={})
        assert refused.status_code == 409
        assert "is queued" in refused.json()["detail"]
        expired = AgentSessionDocument.find_one({"session_id": agent_id}).run()
        assert expired is not None and expired.status == AgentSessionStatus.EXPIRED

        AgentActionDocument.get_motor_collection().update_one(
            {"action_id": f"action-{agent_id}"}, {"$set": {"execution_status": "completed"}}
        )
        closed = test_client.post(close, headers=_headers(), json={})
        assert closed.status_code == 200, closed.text


def _agent_doc(session_id: str) -> AgentSessionDocument:
    doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert doc is not None
    return doc


def _only_agent() -> AgentSessionDocument:
    [agent] = AgentSessionDocument.find_all().to_list()
    return agent


def _insert_then_crash():
    """An insert that writes the session, then a crash before its start is finalized."""
    original = AgentSessionDocument.insert

    def insert(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("crash after insert")

    return patch.object(AgentSessionDocument, "insert", insert)


class TestAgentAdmission:
    """An agent session created in a calibration session operates only once admitted."""

    def _operational_refusals(self, test_client, agent_id: str) -> list[int]:
        """Status codes of every path that can grant a side effect, for one session."""
        from qdash.datamodel.agent_session import AgentActionDecision, AgentActionType
        from qdash.dbmodel.agent_session import AgentActionDocument

        AgentActionDocument(
            action_id=f"authorized-{agent_id}",
            session_id=agent_id,
            project_id="lab-a",
            idempotency_key=f"seed-{agent_id}",
            request_hash="h",
            action_type=AgentActionType.RUN_TASK,
            task_name="CheckRabi",
            qids=["0"],
            decision=AgentActionDecision.AUTHORIZED,
            reason="",
            execution_status="not_started",
            state_version_before=0,
            state_version_after=0,
        ).insert()
        base = f"/agent-sessions/{agent_id}"
        responses = [
            test_client.post(
                f"{base}/actions",
                headers=_headers(),
                json={
                    "idempotency_key": "submit-1",
                    "expected_state_version": 0,
                    "action_type": "run_task",
                    "task_name": "CheckRabi",
                    "qids": ["0"],
                },
            ),
            test_client.post(
                f"{base}/actions/authorized-{agent_id}/execute", headers=_headers(), json={}
            ),
            test_client.post(
                f"{base}/commits/commit-x/apply",
                headers=_headers(),
                json={"idempotency_key": "apply-1", "expected_state_version": 0},
            ),
            test_client.post(
                f"{base}/interventions",
                headers=_headers(),
                json={
                    "idempotency_key": "pause-1",
                    "reason": "agent_request",
                    "summary": "s",
                    "question": "q",
                },
            ),
        ]
        return [response.status_code for response in responses]

    def test_an_attached_session_and_one_created_alone_are_both_admitted(self, test_client, lab):
        from qdash.api.services.agent_session_gate import pass_execution_gate

        session_id = _create_session(test_client)
        attached = test_client.post(
            "/agent-sessions",
            headers=_headers(),
            json={"chip_id": CHIP, "policy": POLICY, "calibration_session_id": session_id},
        )
        assert attached.status_code == 201, attached.text
        assert attached.json()["calibration_admission"] == "admitted"
        plain = test_client.post(
            "/agent-sessions", headers=_headers(), json={"chip_id": CHIP, "policy": POLICY}
        )
        # Created alone, it is admitted to its own automatic session through the same steps.
        assert plain.json()["calibration_admission"] == "admitted"
        automatic = _session_doc(plain.json()["calibration_session_id"])
        assert automatic.origin == "automatic"
        assert automatic.admitted_reservation_ids == [
            _agent_doc(plain.json()["session_id"]).calibration_reservation_id
        ]
        doc = _session_doc(session_id)
        assert doc.pending_children == []
        assert doc.admitted_reservation_ids == [
            _agent_doc(attached.json()["session_id"]).calibration_reservation_id
        ]
        assert pass_execution_gate("lab-a", attached.json()["session_id"])
        assert pass_execution_gate("lab-a", plain.json()["session_id"])

    def test_a_session_whose_record_lacks_admission_keeps_its_behavior(self, test_client, lab):
        from qdash.api.services.agent_session_gate import load_agent_session, pass_execution_gate
        from qdash.datamodel.agent_session import AgentSessionPolicy

        session_id = _create_session(test_client)
        AgentSessionDocument(
            session_id="legacy",
            project_id="lab-a",
            chip_id=CHIP,
            created_by="owner",
            policy=AgentSessionPolicy.model_validate(POLICY),
            expires_at=now() + timedelta(hours=1),
            calibration_session_id=session_id,
        ).insert()
        AgentSessionDocument.get_motor_collection().update_one(
            {"session_id": "legacy"},
            {"$unset": {"calibration_admission": "", "calibration_reservation_id": ""}},
        )
        assert load_agent_session("lab-a", "legacy").status == AgentSessionStatus.ACTIVE
        assert pass_execution_gate("lab-a", "legacy")

    def test_a_written_session_is_refused_everywhere_until_its_start_is_finalized(
        self, test_client, lab
    ):
        from qdash.api.services.agent_session_gate import pass_execution_gate

        session_id = _create_session(test_client)
        with _insert_then_crash(), pytest.raises(RuntimeError):
            _create_agent_directly(session_id)
        agent = _only_agent()
        assert agent.calibration_admission == CalibrationAdmission.PENDING
        assert agent.status == AgentSessionStatus.ACTIVE

        assert not pass_execution_gate("lab-a", agent.session_id)
        assert self._operational_refusals(test_client, agent.session_id) == [409] * 4
        listed = test_client.get("/agent-sessions", headers=_headers()).json()["items"]
        assert [(a["session_id"], a["calibration_admission"]) for a in listed] == [
            (agent.session_id, "pending")
        ]
        refused = test_client.post(
            f"/agent-sessions/{agent.session_id}/actions",
            headers=_headers(),
            json={
                "idempotency_key": "submit-2",
                "expected_state_version": 0,
                "action_type": "run_task",
                "task_name": "CheckRabi",
                "qids": ["0"],
            },
        )
        assert "is not admitted yet" in refused.json()["detail"]
        assert _agent_doc(agent.session_id).action_count == 0

    def test_late_record_after_acknowledged_close_then_crash_never_operates(self, test_client, lab):
        """The exact window: stall past the close, write the session, crash before finalizing."""
        from qdash.api.services.agent_session_gate import pass_execution_gate

        session_id = _create_session(test_client)
        original = AgentSessionDocument.insert

        def stall_close_insert_crash(self, *args, **kwargs):
            _age_reservations(session_id)
            _close_directly(session_id, acknowledge=True)
            original(self, *args, **kwargs)
            raise RuntimeError("crash before finalization")

        with (
            patch.object(AgentSessionDocument, "insert", stall_close_insert_crash),
            pytest.raises(RuntimeError),
        ):
            _create_agent_directly(session_id)
        raw = _only_agent()
        # Nothing decided it yet: it was written pending, and pending refuses the gate.
        assert raw.calibration_admission == CalibrationAdmission.PENDING
        assert not pass_execution_gate("lab-a", raw.session_id)

        # Discoverable through the list, but rejected and cancelled there.
        listed = test_client.get("/agent-sessions", headers=_headers()).json()["items"]
        assert [(a["status"], a["calibration_admission"]) for a in listed] == [
            ("cancelled", "rejected")
        ]
        assert self._operational_refusals(test_client, raw.session_id) == [409] * 4
        assert not pass_execution_gate("lab-a", raw.session_id)
        rejected = _agent_doc(raw.session_id)
        assert rejected.end_notification is not None
        assert _session_doc(session_id).admitted_reservation_ids == []

    def test_crash_after_the_winning_finalize_is_admitted_on_the_next_load(self, test_client, lab):
        from qdash.api.services.agent_session_gate import pass_execution_gate

        session_id = _create_session(test_client)
        with (
            patch(
                "qdash.api.services.agent_session_service.admit_calibration_child",
                side_effect=RuntimeError("crash after finalize"),
            ),
            pytest.raises(RuntimeError),
        ):
            _create_agent_directly(session_id)
        agent = _only_agent()
        assert agent.calibration_admission == CalibrationAdmission.PENDING
        assert _session_doc(session_id).admitted_reservation_ids == [
            agent.calibration_reservation_id
        ]
        # Undecided in its own record, so the raw gate still refuses it.
        assert not pass_execution_gate("lab-a", agent.session_id)

        read = test_client.get(f"/agent-sessions/{agent.session_id}", headers=_headers())
        assert read.json()["calibration_admission"] == "admitted"
        assert read.json()["status"] == "active"
        assert pass_execution_gate("lab-a", agent.session_id)
        # A close after it is admitted sees an active child, never a rejected one.
        refused = test_client.post(
            f"/calibration-sessions/{session_id}/close", headers=_headers(), json={}
        )
        assert refused.status_code == 409
        assert f"agent session {agent.session_id} is active" in refused.json()["detail"]

    def test_close_rejects_a_written_session_whose_old_reservation_is_pending(
        self, test_client, lab
    ):
        from qdash.api.services.agent_session_gate import pass_execution_gate

        session_id = _create_session(test_client)
        with _insert_then_crash(), pytest.raises(RuntimeError):
            _create_agent_directly(session_id)
        agent = _only_agent()
        close = f"/calibration-sessions/{session_id}/close"
        recent = test_client.post(close, headers=_headers(), json={})
        assert recent.status_code == 409
        assert "being started" in recent.json()["detail"]

        _age_reservations(session_id)
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=_headers()).json()
        # Never admitted, so nothing ran in it: not a blocker, not an unknown start.
        assert detail["close_blockers"] == []
        assert detail["unknown_starts"] == []
        assert [a["calibration_admission"] for a in detail["agent_sessions"]] == ["pending"]

        closed = test_client.post(close, headers=_headers(), json={})
        assert closed.status_code == 200, closed.text
        rejected = _agent_doc(agent.session_id)
        assert rejected.calibration_admission == CalibrationAdmission.REJECTED
        assert rejected.status == AgentSessionStatus.CANCELLED
        assert not pass_execution_gate("lab-a", agent.session_id)

    def test_a_finalize_racing_the_close_admits_or_rejects_never_both(self, test_client, lab):
        from qdash.api.services.calibration_session_service import CalibrationSessionService

        session_id = _create_session(test_client)
        with _insert_then_crash(), pytest.raises(RuntimeError):
            _create_agent_directly(session_id)
        agent = _only_agent()
        _age_reservations(session_id)
        original = CalibrationSessionService._blockers

        def finalize_during_close(self, doc):
            found = original(self, doc)
            # The stalled request finalizes after the close read the reservations.
            assert CalibrationSessionService.finalize_child(
                project_id="lab-a",
                calibration_session_id=session_id,
                reservation_id=str(agent.calibration_reservation_id),
                admit=True,
            )
            return found

        from fastapi import HTTPException

        with (
            patch.object(CalibrationSessionService, "_blockers", finalize_during_close),
            pytest.raises(HTTPException) as refused,
        ):
            _close_directly(session_id)
        assert refused.value.status_code == 409
        assert _session_doc(session_id).status == "open"
        read = test_client.get(f"/agent-sessions/{agent.session_id}", headers=_headers())
        assert read.json()["calibration_admission"] == "admitted"

    def test_unknown_close_message_says_admitted_runs_may_start_later(self, test_client, lab):
        session_id = _create_session(test_client)
        CalibrationPipelineRunDocument(
            run_id="cpr-stalled",
            project_id="lab-a",
            calibration_session_id=session_id,
            chip_id=CHIP,
            idempotency_key="k",
            request_hash="h",
            requested_by="owner",
            dispatch_token="t",
            requested_at=now() - timedelta(minutes=10),
            updated_at=now() - timedelta(minutes=10),
        ).insert()
        refused = test_client.post(
            f"/calibration-sessions/{session_id}/close", headers=_headers(), json={}
        )
        assert refused.status_code == 409
        assert "may still start after the close" in refused.json()["detail"]
