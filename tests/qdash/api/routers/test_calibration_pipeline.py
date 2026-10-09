"""Tests for the calibration pipeline endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.user import UserDocument

CHIP = "64Qv3"


@pytest.fixture
def test_project(init_db):
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()
    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_user_id=user.user_id,
        owner_username="test_user",
    )
    project.insert()
    ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="test_user",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="test_user",
    ).insert()
    return project


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test_token", "X-Project-Id": "test_project"}


@pytest.fixture
def chip(test_project):
    """A 64-qubit chip with qubits 0-7 and the one- and two-qubit task definitions."""
    ChipDocument(
        chip_id=CHIP,
        username="test_user",
        project_id="test_project",
        size=64,
        system_info=SystemInfoModel(),
    ).insert()
    for i in range(8):
        QubitDocument(
            project_id="test_project",
            username="test_user",
            chip_id=CHIP,
            qid=str(i),
            status="pending",
            data={},
            system_info={},
        ).insert()
    for name, task_type in [
        ("CheckRabi", "qubit"),
        ("CheckT1", "qubit"),
        ("CheckT2Echo", "qubit"),
        ("CheckCrossResonance", "coupling"),
    ]:
        TaskDocument(
            project_id="test_project",
            username="test_user",
            name=name,
            backend="qubex",
            description=name,
            task_type=task_type,
        ).insert()


def good_spec() -> dict[str, Any]:
    return {
        "name": "coarse-then-coherence",
        "targets": {"qids": ["0", "1"]},
        "steps": [
            {"type": "OneQubitCheck", "mode": "scheduled"},
            {"type": "FilterByStatus"},
            {
                "type": "CustomOneQubit",
                "step_name": "coherence",
                "tasks": ["CheckT1", "CheckT2Echo"],
            },
        ],
        "task_run_parameters": {"CheckT1": {"shots": 2048}},
    }


class TestCatalog:
    def test_catalog_lists_step_types_and_tasks_by_type(self, test_client, chip, auth_headers):
        response = test_client.get("/calibration-pipelines/catalog", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["backend_name"] == "qubex"
        types = {entry["type"]: entry for entry in data["step_types"]}
        assert types["FilterByStatus"]["requires"] == ["one_qubit_check", "one_qubit_fine_tune"]
        assert types["OneQubitCheck"]["default_tasks"][0] == "CheckRabi"
        assert "CheckT1" in data["tasks"]["qubit"]
        assert "CheckCrossResonance" in data["tasks"]["coupling"]
        assert "scheduled" in data["one_qubit_modes"]
        assert "CalibrationPipelineSpec" in data["spec_schema"]["title"]

    def test_catalog_requires_authentication(self, test_client, chip):
        assert test_client.get("/calibration-pipelines/catalog").status_code == 401


class TestValidate:
    def test_valid_spec_resolves_steps_and_tasks(self, test_client, chip, auth_headers):
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": good_spec()},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True, data["problems"]
        assert data["problems"] == []
        assert [step["name"] for step in data["steps"]] == [
            "one_qubit_check",
            "filter_by_status",
            "coherence",
        ]
        assert data["steps"][1]["tasks"] == []
        assert data["steps"][2]["tasks"] == ["CheckT1", "CheckT2Echo"]
        assert data["targets"] == {"qids": ["0", "1"], "mux_ids": [], "exclude_qids": []}
        assert data["task_run_count"] == 5
        # The normalized spec carries the defaults the worker will use.
        assert data["spec"]["steps"][0]["configure"] is False

    def test_problems_carry_paths(self, test_client, chip, auth_headers):
        spec = good_spec()
        spec["targets"] = {"qids": ["0", "99"]}
        spec["steps"][2]["tasks"] = ["CheckT1", "CheckCrossResonance", "NoSuchTask"]
        spec["task_run_parameters"] = {"CheckDRAGPIPulse": {"shots": 1}}
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        problems = {problem["path"]: problem["message"] for problem in data["problems"]}
        assert "not on chip" in problems["targets.qids[1]"]
        assert "coupling task" in problems["steps[2].tasks[1]"]
        assert "not available" in problems["steps[2].tasks[2]"]
        assert "does not run" in problems["task_run_parameters.CheckDRAGPIPulse"]
        # Still resolved so the agent sees what it wrote.
        assert len(data["steps"]) == 3

    def test_shape_errors_are_problems_not_422(self, test_client, chip, auth_headers):
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={
                "chip_id": CHIP,
                "spec": {"targets": {"qids": ["0"]}, "steps": [{"type": "FilterByStatus"}]},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["spec"] is None
        assert any("needs one_qubit_check" in p["message"] for p in data["problems"])

    def test_unknown_chip_and_backend(self, test_client, chip, auth_headers):
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": "nope", "spec": good_spec(), "backend_name": "sim"},
        )
        data = response.json()
        paths = {problem["path"] for problem in data["problems"]}
        assert paths == {"chip_id", "backend_name"}

    def test_mux_targets_are_range_checked(self, test_client, chip, auth_headers):
        spec = good_spec()
        spec["targets"] = {"mux_ids": [0, 16], "exclude_qids": ["3", "42"]}
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        data = response.json()
        paths = {problem["path"] for problem in data["problems"]}
        assert paths == {"targets.mux_ids[1]", "targets.exclude_qids[1]"}
        assert data["targets"]["mux_ids"] == [0, 16]


def prefect_client_mock() -> tuple[MagicMock, MagicMock]:
    flow_run = MagicMock()
    flow_run.id = "flow-run-1"
    deployment = MagicMock()
    deployment.id = "deployment-1"
    client = MagicMock()
    client.read_deployment_by_name = AsyncMock(return_value=deployment)
    client.create_flow_run_from_deployment = AsyncMock(return_value=flow_run)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, client


class TestExecute:
    def test_execute_dispatches_the_system_deployment(self, test_client, chip, auth_headers):
        cm, client = prefect_client_mock()
        with patch("qdash.api.services.flow_service.get_client", return_value=cm):
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=auth_headers,
                json={"chip_id": CHIP, "spec": good_spec()},
            )
        assert response.status_code == 202, response.text
        data = response.json()
        assert data["flow_run_id"] == "flow-run-1"
        assert [step["name"] for step in data["steps"]][-1] == "coherence"

        client.read_deployment_by_name.assert_awaited_once_with(
            "calibration-pipeline/system-calibration-pipeline"
        )
        parameters = client.create_flow_run_from_deployment.call_args.kwargs["parameters"]
        assert parameters["project_id"] == "test_project"
        assert parameters["username"] == "test_user"
        assert parameters["chip_id"] == CHIP
        assert parameters["flow_name"] == "coarse-then-coherence"
        assert parameters["backend_name"] == "qubex"
        assert "pipeline" in parameters["tags"]
        # The worker gets the normalized spec, not the raw request body.
        assert parameters["spec"]["steps"][0]["configure"] is False
        assert parameters["spec"]["steps"][2]["mode"] == "synchronized"

    def test_execute_rejects_invalid_spec_before_dispatch(self, test_client, chip, auth_headers):
        cm, client = prefect_client_mock()
        spec = good_spec()
        spec["targets"] = {"qids": ["99"]}
        with patch("qdash.api.services.flow_service.get_client", return_value=cm):
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=auth_headers,
                json={"chip_id": CHIP, "spec": spec},
            )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["problems"][0]["path"] == "targets.qids[0]"
        client.create_flow_run_from_deployment.assert_not_called()

    def test_execute_without_worker_deployment_is_503(self, test_client, chip, auth_headers):
        cm, client = prefect_client_mock()
        client.read_deployment_by_name = AsyncMock(side_effect=RuntimeError("missing"))
        with patch("qdash.api.services.flow_service.get_client", return_value=cm):
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=auth_headers,
                json={"chip_id": CHIP, "spec": good_spec()},
            )
        assert response.status_code == 503

    def test_execute_requires_editor(self, test_client, chip, auth_headers, init_db):
        membership = ProjectMembershipDocument.find_one({"username": "test_user"}).run()
        assert membership is not None
        membership.role = ProjectRole.VIEWER
        membership.save()
        response = test_client.post(
            "/calibration-pipelines/execute",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": good_spec()},
        )
        assert response.status_code == 403
