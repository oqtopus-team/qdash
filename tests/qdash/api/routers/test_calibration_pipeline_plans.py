"""Stored calibration pipeline plans: create, read, and run by reference."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from qdash.api.schemas.calibration_pipeline import (
    PipelinePlanUnprocessableResponse,
    PipelineProblemsDetail,
    RequestFieldError,
)
from qdash.api.services.calibration_pipeline_service import CalibrationPipelineService
from qdash.api.services.flow_service.prefect_gateway import (
    SystemDeployment,
    SystemDeploymentUnavailable,
)
from qdash.common.config import topology as topology_config
from qdash.common.config.topology import load_topology
from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_plan import APPROVED_PLAN_CONTRACT_KEY, review_digest
from qdash.dbmodel.calibration_pipeline_plan import CalibrationPipelinePlanDocument
from qdash.dbmodel.calibration_session import CalibrationSessionDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.run import RunDocument
from tests.qdash.api.routers.test_calibration_pipeline import good_spec
from tests.qdash.api.routers.test_calibration_sessions import (  # noqa: F401 - fixture
    CHIP,
    DEPLOYMENT_ID,
    GATEWAY,
    OTHER_CHIP,
    PLAN_READY_SCHEMA,
    _chip,
    _headers,
    _release_locks,
    lab,
    prefect,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("lab", "chip_config")

# A chip of lab-a whose topology defines MUXes 0 and 1 while its wiring lists only MUX 0.
TOPOLOGY_CHIP = "topo-2mux"
TOPOLOGY_ID = "test-two-mux"
PLAN_SERVICE = "qdash.api.services.calibration_pipeline_plan_service"


def _wiring(chip_id: str, muxes: list[int]) -> str:
    rows = "".join(
        f"  - mux: {mux}\n    ctrl: [C{mux}A-0, C{mux}A-1, C{mux}A-2, C{mux}A-3]\n"
        f"    read_out: R{mux}A-0\n    read_in: R{mux}A-1\n"
        for mux in muxes
    )
    return f"{chip_id}:\n{rows}"


@pytest.fixture
def chip_config(lab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: F811
    """A synthetic configuration tree, so MUX targets resolve without any real chip config.

    ``CONFIG_PATH`` holds the wiring (MUX 0 for both chips; the legacy chip also MUX 1) and
    topology directory holds one topology with MUXes 0 and 1, both read by the real
    resolution code.
    """
    qubex = tmp_path / "qubex-config"
    for chip_id, muxes in ((CHIP, [0, 1]), (TOPOLOGY_CHIP, [0])):
        wiring = qubex / chip_id / "config" / "wiring.yaml"
        wiring.parent.mkdir(parents=True)
        wiring.write_text(_wiring(chip_id, muxes), encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(qubex))
    topologies = tmp_path / "topologies"
    topologies.mkdir(parents=True)
    qubits = ", ".join(f"{q}: {{row: {q // 4}, col: {q % 4}}}" for q in range(8))
    (topologies / f"{TOPOLOGY_ID}.yaml").write_text(
        f"id: {TOPOLOGY_ID}\nname: Two MUXes\ngrid_size: 4\nnum_qubits: 8\n"
        "muxes: {0: [0, 1, 2, 3], 1: [4, 5, 6, 7]}\n"
        f"qubits: {{{qubits}}}\ncouplings: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(topology_config, "_topologies_dir", lambda: topologies)
    load_topology.cache_clear()
    _chip("lab-a", TOPOLOGY_CHIP)
    chip = ChipDocument.find_one({"project_id": "lab-a", "chip_id": TOPOLOGY_CHIP}).run()
    assert chip is not None
    chip.topology_id = TOPOLOGY_ID
    chip.save()
    yield
    load_topology.cache_clear()


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


def _drop_qubit(chip_id: str, qid: str) -> None:
    QubitDocument.get_motor_collection().delete_one(
        {"project_id": "lab-a", "chip_id": chip_id, "qid": qid}
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

    def test_a_legacy_chip_skips_muxes_its_wiring_does_not_list(self, test_client, tmp_path):
        wiring = tmp_path / "qubex-config" / CHIP / "config" / "wiring.yaml"
        wiring.write_text(_wiring(CHIP, [0]), encoding="utf-8")
        spec = {**good_spec(), "targets": {"mux_ids": [0, 1], "exclude_qids": []}}
        response = _create(test_client, spec)
        assert response.status_code == 201, response.text
        assert response.json()["target_qids"] == ["0", "1", "2", "3"]

    def test_a_topology_mux_without_wiring_stores_nothing(self, test_client):
        spec = {**good_spec(), "targets": {"mux_ids": [0, 1], "exclude_qids": []}}
        with prefect() as create_flow_run:
            response = _create(test_client, spec, chip_id=TOPOLOGY_CHIP)
        assert response.status_code == 422, response.text
        [problem] = response.json()["detail"]["problems"]
        assert problem["path"] == "targets.mux_ids"
        assert "MUXes [1]" in problem["message"] and "wiring" in problem["message"]
        assert CalibrationPipelinePlanDocument.find_all().count() == 0
        create_flow_run.assert_not_awaited()
        # The wired MUX alone resolves through the topology, and an excluded unwired MUX
        # needs no wiring, as on the worker.
        wired = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": ["0"]}}
        assert _create(test_client, wired, chip_id=TOPOLOGY_CHIP, key="p2").json()[
            "target_qids"
        ] == ["1", "2", "3"]
        excluded = {
            **good_spec(),
            "targets": {"mux_ids": [0, 1], "exclude_qids": ["4", "5", "6", "7"]},
        }
        response = _create(test_client, excluded, chip_id=TOPOLOGY_CHIP, key="p3")
        assert response.status_code == 201, response.text

    @pytest.mark.parametrize("chip_id", [TOPOLOGY_CHIP, CHIP])
    def test_a_mux_member_without_a_qubit_record_stores_nothing(self, test_client, chip_id):
        _drop_qubit(chip_id, "2")
        spec = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": []}}
        with prefect() as create_flow_run:
            response = _create(test_client, spec, chip_id=chip_id)
        assert response.status_code == 422, response.text
        [problem] = response.json()["detail"]["problems"]
        assert problem["path"] == "targets.mux_ids"
        assert "['2']" in problem["message"] and "qubit record" in problem["message"]
        assert CalibrationPipelinePlanDocument.find_all().count() == 0
        create_flow_run.assert_not_awaited()
        assert RunDocument.find_all().count() == 0
        # Excluding the member without a record targets the rest of its MUX.
        excluded = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": ["2"]}}
        response = _create(test_client, excluded, chip_id=chip_id, key="p2")
        assert response.status_code == 201, response.text
        assert response.json()["target_qids"] == ["0", "1", "3"]
        # A qubit in no selected MUX and without a record is still not on the chip.
        stray = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": ["99"]}}
        response = _create(test_client, stray, chip_id=chip_id, key="p3")
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["problems"][0]["path"] == "targets.exclude_qids[0]"

    def test_a_legacy_unwired_mux_needs_no_qubit_records(self, test_client, tmp_path):
        wiring = tmp_path / "qubex-config" / CHIP / "config" / "wiring.yaml"
        wiring.write_text(_wiring(CHIP, [0]), encoding="utf-8")
        _drop_qubit(CHIP, "5")
        spec = {**good_spec(), "targets": {"mux_ids": [0, 1], "exclude_qids": []}}
        response = _create(test_client, spec)
        assert response.status_code == 201, response.text
        assert response.json()["target_qids"] == ["0", "1", "2", "3"]

    def test_unreadable_wiring_stores_nothing(self, test_client, tmp_path):
        (tmp_path / "qubex-config" / CHIP / "config" / "wiring.yaml").unlink()
        spec = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": []}}
        response = _create(test_client, spec)
        assert response.status_code == 422
        assert response.json()["detail"]["problems"][0]["path"] == "targets.mux_ids"
        assert CalibrationPipelinePlanDocument.find_all().count() == 0

    def test_written_out_default_tasks_are_checked_unlike_validate(self, test_client):
        # /validate leaves an omitted task list to the template; a plan names its calls,
        # so a default task the backend does not provide refuses the plan.
        original = CalibrationPipelineService.task_types

        def without_hpi(self, project_id, backend_name):
            types = original(self, project_id, backend_name)
            types.pop("CreateHPIPulse", None)
            return types

        with patch.object(CalibrationPipelineService, "task_types", without_hpi):
            validated = test_client.post(
                "/calibration-pipelines/validate",
                headers=_headers(),
                json={"chip_id": CHIP, "spec": good_spec()},
            )
            response = _create(test_client)
        assert validated.status_code == 200 and validated.json()["valid"] is True
        assert response.status_code == 422
        [problem] = response.json()["detail"]["problems"]
        assert problem["path"] == "steps[0].tasks[1]"
        assert "CreateHPIPulse" in problem["message"]
        assert CalibrationPipelinePlanDocument.find_all().count() == 0

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

    def test_replay_never_reads_the_plan(self, test_client):
        plan = _create(test_client).json()
        with prefect(["flow-run-a", "flow-run-b"]) as create_flow_run:
            first = _execute(test_client, plan)
            _release_locks()
            unreadable = RuntimeError("plan collection unavailable")
            with patch(f"{PLAN_SERVICE}.find_plan", side_effect=unreadable) as lookup:
                again = _execute(test_client, plan)
        assert first.status_code == 202, first.text
        assert again.status_code == 202, again.text
        assert again.json()["replayed"] is True
        assert again.json()["pipeline_run_id"] == first.json()["pipeline_run_id"]
        lookup.assert_not_called()
        assert create_flow_run.await_count == 1
        [run] = RunDocument.find_all().to_list()
        assert run.run_name == "coarse-then-coherence"

    def test_a_mux_that_lost_its_wiring_is_never_dispatched(self, test_client, tmp_path):
        spec = {**good_spec(), "targets": {"mux_ids": [0, 1], "exclude_qids": []}}
        wiring = tmp_path / "qubex-config" / TOPOLOGY_CHIP / "config" / "wiring.yaml"
        wiring.write_text(_wiring(TOPOLOGY_CHIP, [0, 1]), encoding="utf-8")
        plan = _create(test_client, spec, chip_id=TOPOLOGY_CHIP).json()
        assert plan["target_qids"] == [str(q) for q in range(8)]
        wiring.write_text(_wiring(TOPOLOGY_CHIP, [0]), encoding="utf-8")
        with prefect() as create_flow_run:
            response = _execute(test_client, plan)
        assert response.status_code == 422, response.text
        assert "MUXes [1]" in response.json()["detail"]["problems"][0]["message"]
        create_flow_run.assert_not_awaited()
        assert RunDocument.find_all().count() == 0

    def test_a_qubit_record_removed_after_approval_is_never_dispatched(self, test_client):
        spec = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": []}}
        plan = _create(test_client, spec, chip_id=TOPOLOGY_CHIP).json()
        assert plan["target_qids"] == ["0", "1", "2", "3"]
        _drop_qubit(TOPOLOGY_CHIP, "2")
        with prefect() as create_flow_run:
            response = _execute(test_client, plan)
        assert response.status_code == 422, response.text
        [problem] = response.json()["detail"]["problems"]
        assert problem["path"] == "targets.mux_ids"
        assert "['2']" in problem["message"]
        create_flow_run.assert_not_awaited()
        assert RunDocument.find_all().count() == 0
        assert CalibrationSessionDocument.find_all().count() == 0
        assert ExecutionLockDocument.find_all().count() == 0

    def test_replay_survives_a_qubit_record_removed_after_dispatch(self, test_client):
        spec = {**good_spec(), "targets": {"mux_ids": [0], "exclude_qids": []}}
        plan = _create(test_client, spec, chip_id=TOPOLOGY_CHIP).json()
        with prefect(["flow-run-a", "flow-run-b"]) as create_flow_run:
            first = _execute(test_client, plan)
            _release_locks()
            _drop_qubit(TOPOLOGY_CHIP, "2")
            again = _execute(test_client, plan)
        assert first.status_code == 202, first.text
        assert again.status_code == 202, again.text
        assert again.json()["replayed"] is True
        assert again.json()["pipeline_run_id"] == first.json()["pipeline_run_id"]
        assert create_flow_run.await_count == 1

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


class TestUnprocessableResponses:
    def test_both_endpoints_document_every_422_shape(self, test_client):
        paths = test_client.app.openapi()["paths"]
        for path in (
            "/calibration-pipelines/plans",
            "/calibration-pipelines/plans/{plan_id}/execute",
        ):
            content = paths[path]["post"]["responses"]["422"]["content"]
            ref = content["application/json"]["schema"]["$ref"]
            assert ref.endswith("/PipelinePlanUnprocessableResponse")

    def test_every_422_body_decodes_as_documented(self, test_client):
        plan = _create(test_client).json()
        bodies = [
            # Body validation, domain problems, and a plan mismatch.
            test_client.post(
                "/calibration-pipelines/plans", headers=_headers(), json={"chip_id": CHIP}
            ),
            _create(test_client, {**good_spec(), "targets": {"qids": ["99"]}}, key="bad"),
            _execute(test_client, plan, chip_id=OTHER_CHIP),
            test_client.post(
                f"/calibration-pipelines/plans/{plan['plan_id']}/execute",
                headers=_headers(),
                json={"chip_id": CHIP},
            ),
        ]
        assert [body.status_code for body in bodies] == [422] * 4
        details = [
            PipelinePlanUnprocessableResponse.model_validate(body.json()).detail for body in bodies
        ]
        assert isinstance(details[0], list) and isinstance(details[0][0], RequestFieldError)
        assert isinstance(details[1], PipelineProblemsDetail) and details[1].problems
        assert isinstance(details[2], str) and OTHER_CHIP in details[2]
        assert isinstance(details[3], list)
