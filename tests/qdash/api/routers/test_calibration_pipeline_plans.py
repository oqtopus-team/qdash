"""Stored calibration pipeline plans: create, read, and run by reference."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from qdash.api.services.calibration_pipeline_service import CalibrationPipelineService
from qdash.api.services.flow_service.prefect_gateway import (
    SystemDeployment,
    SystemDeploymentUnavailable,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_plan import APPROVED_PLAN_CONTRACT_KEY, review_digest
from qdash.dbmodel.calibration_pipeline_plan import CalibrationPipelinePlanDocument
from qdash.dbmodel.calibration_session import CalibrationSessionDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.run import RunDocument
from tests.qdash.api.routers.test_calibration_pipeline import good_spec
from tests.qdash.api.routers.test_calibration_sessions import (  # noqa: F401 - fixture
    CHIP,
    DEPLOYMENT_ID,
    GATEWAY,
    OTHER_CHIP,
    PLAN_READY_SCHEMA,
    _headers,
    _release_locks,
    lab,
    prefect,
)

pytestmark = pytest.mark.usefixtures("lab")


def _create(test_client, spec: dict[str, Any] | None = None, key: str = "plan-1", **body: Any):
    return test_client.post(
        "/calibration-pipelines/plans",
        headers=_headers(body.pop("user", "owner")),
        json={
            "chip_id": body.pop("chip_id", CHIP),
            "spec": spec or good_spec(),
            **body,
            "idempotency_key": key,
        },
    )


def _execute(test_client, plan: dict[str, Any], key: str | None = "run-1", **fields: Any):
    body: dict[str, Any] = {
        "chip_id": fields.pop("chip_id", plan["chip_id"]),
        "expected_review_digest": fields.pop("digest", plan["review_digest"]),
        **fields,
    }
    user = body.pop("user", "owner")
    if key is not None:
        body["idempotency_key"] = key
    return test_client.post(
        f"/calibration-pipelines/plans/{plan['plan_id']}/execute",
        headers=_headers(user),
        json=body,
    )


def _expire(plan_id: str) -> None:
    doc = CalibrationPipelinePlanDocument.find_one({"plan_id": plan_id}).run()
    assert doc is not None
    CalibrationPipelinePlanDocument.get_motor_collection().update_one(
        {"plan_id": plan_id}, {"$set": {"expires_at": now() - timedelta(seconds=1)}}
    )


class TestCreate:
    def test_create_stores_a_reviewed_plan_and_starts_nothing(self, test_client):
        with prefect() as create_flow_run:
            response = _create(test_client)
        assert response.status_code == 201, response.text
        plan = response.json()
        assert plan["plan_id"].startswith("cpp-")
        assert plan["review_digest"].startswith("sha256:v1:")
        assert len(plan["review_digest"].split(":")[-1]) == 64
        # The spec's own short digest stays what /validate calls plan_digest.
        assert plan["spec_digest"] and plan["spec_digest"] != plan["review_digest"]
        assert plan["expired"] is False
        assert plan["replayed"] is False
        assert plan["target_qids"] == ["0", "1"]
        # The default task list is written into the stored spec.
        first = plan["spec"]["steps"][0]
        assert [call["name"] for call in first["tasks"]] == plan["steps"][0]["tasks"]
        assert first["tasks"][0]["name"] == "CheckRabi"
        create_flow_run.assert_not_awaited()
        assert RunDocument.find_all().count() == 0
        stored = CalibrationPipelinePlanDocument.find_one({"plan_id": plan["plan_id"]}).run()
        assert stored is not None
        assert review_digest(stored.review) == plan["review_digest"]

        read = test_client.get(
            f"/calibration-pipelines/plans/{plan['plan_id']}", headers=_headers()
        )
        assert read.status_code == 200
        assert read.json()["review_digest"] == plan["review_digest"]
        assert read.json()["steps"] == plan["steps"]

    def test_mux_targets_are_expanded_to_their_qubits(self, test_client):
        spec = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": ["2"]}}
        response = _create(test_client, spec)
        assert response.status_code == 201, response.text
        assert response.json()["target_qids"] == ["0", "1", "3"]

    def test_invalid_spec_stores_nothing(self, test_client):
        spec = {**good_spec(), "targets": {"qids": ["99"]}}
        response = _create(test_client, spec)
        assert response.status_code == 422
        assert response.json()["detail"]["problems"][0]["path"] == "targets.qids[0]"
        assert CalibrationPipelinePlanDocument.find_all().count() == 0

    def test_oversized_spec_stores_nothing(self, test_client):
        spec = {**good_spec(), "tags": ["x" * 300_000]}
        response = _create(test_client, spec)
        assert response.status_code == 422
        assert CalibrationPipelinePlanDocument.find_all().count() == 0

    def test_repeated_creation_returns_the_same_plan(self, test_client):
        first = _create(test_client).json()
        again = _create(test_client)
        assert again.status_code == 201
        assert again.json()["plan_id"] == first["plan_id"]
        assert again.json()["replayed"] is True
        assert CalibrationPipelinePlanDocument.find_all().count() == 1

    def test_same_key_with_other_content_conflicts(self, test_client):
        first = _create(test_client).json()
        changed = _create(test_client, {**good_spec(), "name": "other"})
        assert changed.status_code == 409
        stored = CalibrationPipelinePlanDocument.find_one({"plan_id": first["plan_id"]}).run()
        assert stored is not None and stored.spec["name"] == "coarse-then-coherence"

    def test_expired_plan_is_never_revived_by_its_key(self, test_client):
        first = _create(test_client).json()
        _expire(first["plan_id"])
        again = _create(test_client)
        assert again.status_code == 410
        assert CalibrationPipelinePlanDocument.find_all().count() == 1
        read = test_client.get(
            f"/calibration-pipelines/plans/{first['plan_id']}", headers=_headers()
        )
        assert read.json()["expired"] is True
        # A new key is a new plan with a new ID.
        fresh = _create(test_client, key="plan-2").json()
        assert fresh["plan_id"] != first["plan_id"]

    def test_viewer_cannot_create_or_read(self, test_client):
        plan = _create(test_client).json()
        assert _create(test_client, user="viewer", key="v").status_code == 403
        read = test_client.get(
            f"/calibration-pipelines/plans/{plan['plan_id']}", headers=_headers("viewer")
        )
        assert read.status_code == 403

    def test_plans_are_hidden_from_other_users_and_projects(self, test_client):
        plan = _create(test_client).json()
        path = f"/calibration-pipelines/plans/{plan['plan_id']}"
        assert test_client.get(path, headers=_headers("colleague")).status_code == 404
        assert test_client.get(path, headers=_headers("owner", "lab-b")).status_code == 404
        assert test_client.get(path + "x", headers=_headers()).status_code == 404
        with prefect() as create_flow_run:
            assert _execute(test_client, plan, user="colleague").status_code == 404
        create_flow_run.assert_not_awaited()
        # The same key in another user's scope is that user's own creation.
        other = _create(test_client, user="colleague").json()
        assert other["plan_id"] != plan["plan_id"]


class TestExecute:
    def test_execute_runs_the_approved_plan(self, test_client):
        plan = _create(test_client).json()
        with prefect() as create_flow_run:
            response = _execute(test_client, plan)
        assert response.status_code == 202, response.text
        data = response.json()
        assert data["plan_id"] == plan["plan_id"]
        assert data["review_digest"] == plan["review_digest"]
        assert data["replayed"] is False
        parameters = create_flow_run.call_args.kwargs["parameters"]
        assert parameters["spec"] == plan["spec"]
        approved = parameters["approved_plan"]
        assert approved["plan_id"] == plan["plan_id"]
        assert approved["review_digest"] == plan["review_digest"]
        assert review_digest(approved["review"]) == plan["review_digest"]
        [run] = RunDocument.find_all().to_list()
        assert run.plan_id == plan["plan_id"]
        assert run.review_digest == plan["review_digest"]
        assert run.approved_plan == approved["review"]
        assert run.spec == plan["spec"]
        assert run.run_name == "coarse-then-coherence"

    def test_supported_deployment_receives_the_approved_plan(self, test_client):
        plan = _create(test_client).json()
        with prefect() as create_flow_run:
            response = _execute(test_client, plan)
        assert response.status_code == 202, response.text
        kwargs = create_flow_run.call_args.kwargs
        # The run goes to the deployment whose schema was checked.
        assert kwargs["deployment_id"] == DEPLOYMENT_ID
        assert kwargs["parameters"]["approved_plan"]["plan_id"] == plan["plan_id"]

    @pytest.mark.parametrize(
        "schema",
        [
            pytest.param(None, id="no-schema-recorded"),
            pytest.param({}, id="empty-schema"),
            pytest.param("not a schema", id="malformed-schema"),
            pytest.param({"properties": ["approved_plan"]}, id="malformed-properties"),
            pytest.param(
                {"type": "object", "properties": {"spec": {"type": "object"}}},
                id="old-worker-without-approved-plan",
            ),
            pytest.param(
                {"properties": {"approved_plan": {"type": "object"}}},
                id="approved-plan-without-contract",
            ),
            pytest.param(
                {"properties": {"approved_plan": {APPROVED_PLAN_CONTRACT_KEY: 0}}},
                id="other-contract",
            ),
            pytest.param(
                {"properties": {"approved_plan": {APPROVED_PLAN_CONTRACT_KEY: True}}},
                id="bool-contract",
            ),
            pytest.param(
                {"properties": {"approved_plan": {APPROVED_PLAN_CONTRACT_KEY: "1"}}},
                id="string-contract",
            ),
        ],
    )
    def test_deployment_without_the_contract_is_never_dispatched(self, test_client, schema):
        plan = _create(test_client).json()
        session_count = CalibrationSessionDocument.find_all().count()
        with prefect(parameter_schema=schema) as create_flow_run:
            response = _execute(test_client, plan)
        assert response.status_code == 503, response.text
        assert "does not accept approved plans" in response.json()["detail"]
        create_flow_run.assert_not_awaited()
        # Refused before anything is recorded, reserved, or grouped.
        assert RunDocument.find_all().count() == 0
        assert CalibrationSessionDocument.find_all().count() == session_count
        assert ExecutionLockDocument.find_all().count() == 0

    def test_missing_deployment_is_never_dispatched(self, test_client):
        plan = _create(test_client).json()
        missing = AsyncMock(side_effect=SystemDeploymentUnavailable("pipeline"))
        with prefect() as create_flow_run, patch(f"{GATEWAY}.read_deployment", new=missing):
            response = _execute(test_client, plan)
        assert response.status_code == 503
        create_flow_run.assert_not_awaited()
        assert RunDocument.find_all().count() == 0

    def test_deployment_replaced_before_dispatch_is_still_checked(self, test_client):
        plan = _create(test_client).json()
        ready = SystemDeployment(id=DEPLOYMENT_ID, parameter_schema=PLAN_READY_SCHEMA)
        old = SystemDeployment(id=DEPLOYMENT_ID, parameter_schema={"properties": {}})
        # Accepted when the request is checked, then re-registered from older code.
        swapped = AsyncMock(side_effect=[ready, old])
        with prefect() as create_flow_run, patch(f"{GATEWAY}.read_deployment", new=swapped):
            response = _execute(test_client, plan)
        assert response.status_code == 503
        create_flow_run.assert_not_awaited()
        [run] = RunDocument.find_all().to_list()
        assert run.status == "rejected"

    def test_spec_execute_ignores_the_plan_contract(self, test_client):
        # A spec run sends no approved plan, so an older deployment still runs it.
        with prefect(parameter_schema=None) as create_flow_run:
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=_headers(),
                json={"chip_id": CHIP, "spec": good_spec()},
            )
        assert response.status_code == 202, response.text
        assert "approved_plan" not in create_flow_run.call_args.kwargs["parameters"]

    def test_spec_execute_sends_no_approved_plan(self, test_client):
        with prefect() as create_flow_run:
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=_headers(),
                json={"chip_id": CHIP, "spec": good_spec()},
            )
        assert response.status_code == 202, response.text
        assert "approved_plan" not in create_flow_run.call_args.kwargs["parameters"]
        assert response.json()["plan_id"] is None
        [run] = RunDocument.find_all().to_list()
        assert run.plan_id is None and run.approved_plan is None

    def test_mismatched_digest_chip_or_backend_dispatches_nothing(self, test_client):
        plan = _create(test_client).json()
        other = "sha256:v1:" + "0" * 64
        with prefect() as create_flow_run:
            assert _execute(test_client, plan, digest=other).status_code == 409
            assert _execute(test_client, plan, key="k2", chip_id=OTHER_CHIP).status_code == 422
            assert _execute(test_client, plan, key="k3", backend_name="fake").status_code == 422
            assert _execute(test_client, plan, key="k4", digest="abc").status_code == 422
        create_flow_run.assert_not_awaited()
        assert RunDocument.find({"status": "dispatched"}).count() == 0

    def test_expired_plan_dispatches_nothing(self, test_client):
        plan = _create(test_client).json()
        _expire(plan["plan_id"])
        with prefect() as create_flow_run:
            response = _execute(test_client, plan)
        assert response.status_code == 410
        create_flow_run.assert_not_awaited()

    def test_viewer_cannot_execute(self, test_client):
        plan = _create(test_client).json()
        with prefect() as create_flow_run:
            assert _execute(test_client, plan, user="viewer").status_code == 403
        create_flow_run.assert_not_awaited()

    def test_drift_of_the_mux_expansion_is_refused(self, test_client):
        spec = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": []}}
        plan = _create(test_client, spec).json()
        original = CalibrationPipelineService.initial_target_qids

        def fewer(self, project_id, chip_id, parsed):
            qids, problem = original(self, project_id, chip_id, parsed)
            return (qids or [])[:-1], problem

        with (
            prefect() as create_flow_run,
            patch.object(CalibrationPipelineService, "initial_target_qids", fewer),
        ):
            response = _execute(test_client, plan)
        assert response.status_code == 409
        assert "target_qids" in response.json()["detail"]
        create_flow_run.assert_not_awaited()

    def test_drift_of_the_stored_calls_is_refused(self, test_client):
        plan = _create(test_client).json()
        spec = plan["spec"]
        spec["steps"][2]["tasks"][0]["run"] = {"shots": 1}
        CalibrationPipelinePlanDocument.get_motor_collection().update_one(
            {"plan_id": plan["plan_id"]}, {"$set": {"spec": spec}}
        )
        with prefect() as create_flow_run:
            response = _execute(test_client, plan)
        assert response.status_code == 409
        assert "no longer resolves" in response.json()["detail"]
        assert "spec" in response.json()["detail"]
        create_flow_run.assert_not_awaited()

    def test_replay_after_expiry_and_deletion_returns_the_recorded_run(self, test_client):
        plan = _create(test_client).json()
        with prefect(["flow-run-a", "flow-run-b"]) as create_flow_run:
            first = _execute(test_client, plan)
            _release_locks()
            _expire(plan["plan_id"])
            expired = _execute(test_client, plan)
            CalibrationPipelinePlanDocument.get_motor_collection().delete_many({})
            deleted = _execute(test_client, plan)
        assert first.status_code == 202, first.text
        for again in (expired, deleted):
            assert again.status_code == 202, again.text
            assert again.json()["replayed"] is True
            assert again.json()["pipeline_run_id"] == first.json()["pipeline_run_id"]
            assert again.json()["plan_id"] == plan["plan_id"]
            assert again.json()["review_digest"] == plan["review_digest"]
        assert create_flow_run.await_count == 1
        # The audit keeps what was approved after the plan is gone.
        [run] = RunDocument.find_all().to_list()
        assert review_digest(run.approved_plan or {}) == plan["review_digest"]

    def test_unknown_outcome_is_never_dispatched_again(self, test_client):
        plan = _create(test_client).json()
        with prefect(side_effect=RuntimeError("prefect timed out")) as create_flow_run:
            failed = _execute(test_client, plan)
        assert failed.status_code == 500
        with prefect(["flow-run-late"]) as retry:
            again = _execute(test_client, plan)
        assert again.status_code == 409
        assert "unknown" in again.json()["detail"]
        retry.assert_not_awaited()
        assert create_flow_run.await_count == 1

    def test_plan_and_spec_requests_do_not_share_a_key(self, test_client):
        plan = _create(test_client).json()
        with prefect(["flow-run-a", "flow-run-b"]):
            spec_run = test_client.post(
                "/calibration-pipelines/execute",
                headers=_headers(),
                json={"chip_id": CHIP, "spec": plan["spec"], "idempotency_key": "run-1"},
            )
            _release_locks()
            plan_run = _execute(test_client, plan)
        assert spec_run.status_code == 202, spec_run.text
        assert plan_run.status_code == 409
        assert "different request" in plan_run.json()["detail"]
