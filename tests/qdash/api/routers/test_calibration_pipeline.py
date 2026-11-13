"""Tests for the calibration pipeline endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from qdash.api.services.flow_service.prefect_gateway import SystemDeploymentUnavailable
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.user import UserDocument

CHIP = "64Qv3"


def calibrated_qubit_data() -> dict[str, Any]:
    """Calibration data that satisfies the one-qubit check and coherence tasks.

    The pipeline's CheckRabi writes the Rabi set and the pulse tasks write the
    pulse parameters, so only the spectroscopy-level values need to exist.
    """
    return {
        "qubit_frequency": {"value": 7.5, "unit": "GHz"},
        "resonator_frequency": {"value": 10.1, "unit": "GHz"},
        "readout_amplitude": {"value": 0.02, "unit": "a.u."},
    }


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
            data=calibrated_qubit_data(),
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
        "spec_version": 2,
        "name": "coarse-then-coherence",
        "targets": {"qids": ["0", "1"]},
        "steps": [
            {"type": "OneQubitCheck", "execution_mode": "parallel_by_mux"},
            {"type": "FilterByStatus"},
            {
                "type": "CustomOneQubit",
                "step_name": "coherence",
                "tasks": [
                    {"name": "CheckT1", "call_id": "t1_short", "run": {"shots": 2048}},
                    {"name": "CheckT1", "call_id": "t1_long", "run": {"shots": 4096}},
                    {"name": "CheckT2Echo"},
                ],
            },
        ],
    }


class TestCatalog:
    def test_catalog_lists_step_types_and_tasks_by_type(self, test_client, chip, auth_headers):
        response = test_client.get("/calibration-pipelines/catalog", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["backend_name"] == "qubex"
        types = {entry["type"]: entry for entry in data["step_types"]}
        assert types["FilterByStatus"]["requires"] == ["one_qubit_check", "one_qubit_fine_tune"]
        assert types["OneQubitCheck"]["default_tasks"][0]["name"] == "CheckRabi"
        assert types["OneQubitCheck"]["default_step_id"] == "one_qubit_check"
        assert "x90_fidelity" in types["OneQubitFineTune"]["step_metrics"]
        assert data["spec_version"] == 2
        assert "CheckT1" in data["tasks"]["qubit"]
        assert "CheckCrossResonance" in data["tasks"]["coupling"]
        assert "parallel_by_mux" in data["one_qubit_execution_modes"]
        assert "scheduled" not in data["one_qubit_execution_modes"]
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
        assert data["steps"][2]["tasks"] == ["CheckT1", "CheckT1", "CheckT2Echo"]
        assert [step["step_id"] for step in data["steps"]] == [
            "one_qubit_check",
            None,
            "coherence",
        ]
        # Each call shows its effective settings.
        calls = data["steps"][2]["calls"]
        assert [(call["call_id"], call["on_failure"]) for call in calls] == [
            ("t1_short", "stop"),
            ("t1_long", "stop"),
            ("CheckT2Echo", "stop"),
        ]
        assert calls[0]["settings"]["run"] == {"shots": {"value": 2048}}
        assert calls[1]["settings"]["run"] == {"shots": {"value": 4096}}
        assert data["targets"] == {"qids": ["0", "1"], "mux_ids": [], "exclude_qids": []}
        assert data["task_run_count"] == 6
        assert data["spec_version"] == 2
        assert isinstance(data["plan_digest"], str)
        assert data["warnings"] == []
        # The normalized spec carries the defaults the worker will use.
        assert data["spec"]["steps"][0]["configure"] is False

    def test_version_1_spec_is_rejected_with_a_converted_spec(
        self, test_client, chip, auth_headers
    ):
        legacy = {
            "name": "legacy",
            "targets": {"qids": ["0", "1"]},
            "steps": [
                {"type": "OneQubitCheck"},
                {"type": "CustomOneQubit", "step_name": "t1", "tasks": ["CheckT1", "CheckT1"]},
            ],
            "task_run_parameters": {"CheckT1": {"shots": 2048}},
        }
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": legacy},
        )
        data = response.json()
        assert data["valid"] is False
        assert data["spec_version"] == 1
        [problem] = data["problems"]
        assert problem["path"] == "spec_version"
        assert "migrated_spec" in problem["message"]
        migrated = data["migrated_spec"]
        assert migrated["spec_version"] == 2
        assert migrated["steps"][1]["tasks"] == [
            {"name": "CheckT1", "call_id": "CheckT1"},
            {"name": "CheckT1", "call_id": "CheckT1_2"},
        ]
        # Resubmitting the converted spec validates.
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": migrated},
        )
        assert response.json()["valid"] is True, response.json()["problems"]

    def test_version_1_legacy_mode_is_rejected_without_a_converted_spec(
        self, test_client, chip, auth_headers
    ):
        legacy: dict[str, Any] = {
            "targets": {"qids": ["0", "1"]},
            "steps": [
                {"type": "OneQubitCheck"},
                {
                    "type": "CustomOneQubit",
                    "step_name": "t1",
                    "tasks": ["CheckT1"],
                    "mode": "scheduled",
                },
            ],
        }
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": legacy},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["spec_version"] == 1
        # No converted spec is offered, and nothing tells the caller to submit one.
        assert data["migrated_spec"] is None
        [problem] = data["problems"]
        assert problem["path"] == "steps[1]"
        assert "steps[1].execution_mode='parallel_by_mux'" in problem["message"]
        assert "migrated_spec" not in problem["message"]

        # After the owner sets execution_mode, the spec converts and validates.
        legacy["steps"][1] = {
            "type": "CustomOneQubit",
            "step_name": "t1",
            "tasks": ["CheckT1"],
            "execution_mode": "parallel_by_mux",
        }
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": legacy},
        )
        migrated = response.json()["migrated_spec"]
        assert migrated["steps"][1]["execution_mode"] == "parallel_by_mux"
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": migrated},
        )
        assert response.json()["valid"] is True, response.json()["problems"]

    def test_version_1_repeated_builtin_steps_convert_to_unique_step_ids(
        self, test_client, chip, auth_headers
    ):
        legacy = {
            "targets": {"qids": ["0", "1"]},
            "steps": [
                {"type": "OneQubitCheck"},
                {"type": "FilterByStatus"},
                {"type": "OneQubitCheck"},
            ],
        }
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": legacy},
        )
        migrated = response.json()["migrated_spec"]
        assert [step.get("step_id") for step in migrated["steps"]] == [
            None,
            None,
            "one_qubit_check_2",
        ]
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": migrated},
        )
        assert response.json()["valid"] is True, response.json()["problems"]

    @pytest.mark.parametrize("step_type", ["OneQubitCheck", "OneQubitFineTune"])
    def test_configure_flag_conflict_is_a_problem_not_500(
        self, test_client, chip, auth_headers, step_type
    ):
        spec = good_spec()
        spec["steps"][0] = {
            "type": step_type,
            "configure": True,
            "tasks": [{"name": "Configure", "call_id": "explicit"}],
        }
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        problems = {problem["path"]: problem["message"] for problem in data["problems"]}
        assert "configure=True already runs Configure" in problems["steps[0]"]

    def test_deprecated_task_parameters_still_apply_with_a_warning(
        self, test_client, chip, auth_headers
    ):
        spec = good_spec()
        calls = spec["steps"][2]["tasks"]
        calls[0] = {"name": "CheckT1", "call_id": "t1_short"}
        calls[1]["update_calibration_parameters"] = True
        spec["task_parameters"] = {
            "CheckT1": {"run": {"shots": 2048}, "update_calibration_parameters": False}
        }
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        data = response.json()
        assert data["valid"] is True, data["problems"]
        warnings = {warning["path"]: warning["message"] for warning in data["warnings"]}
        assert list(warnings) == ["task_parameters"]
        assert "deprecated" in warnings["task_parameters"]
        assert "CheckT1" in warnings["task_parameters"]
        # Same effective settings as before the deprecation: the default fills
        # what a call omits, and a call's own values (including False/True) win.
        settings = [call["settings"] for call in data["steps"][2]["calls"]]
        assert settings[0] == {
            "run": {"shots": {"value": 2048}},
            "input": {},
            "update_calibration_parameters": False,
        }
        assert settings[1] == {
            "run": {"shots": {"value": 4096}},
            "input": {},
            "update_calibration_parameters": True,
        }
        # The normalized spec keeps the deprecated field, so the worker applies it.
        assert data["spec"]["task_parameters"]["CheckT1"]["update_calibration_parameters"] is False

    def test_configure_all_call_settings_replace_task_parameters(
        self, test_client, chip, auth_headers
    ):
        TaskDocument(
            project_id="test_project",
            username="test_user",
            name="ConfigureAll",
            backend="qubex",
            description="ConfigureAll",
            task_type="system",
        ).insert()
        spec = good_spec()
        spec["targets"] = {"mux_ids": [0]}
        spec["steps"].insert(
            0,
            {
                "type": "ConfigureAll",
                "call": {"name": "ConfigureAll", "run": {"configuration_mode": "ge-ef-cr"}},
            },
        )
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        data = response.json()
        assert data["valid"] is True, data["problems"]
        assert data["warnings"] == []
        configure_all = data["steps"][0]
        assert configure_all["tasks"] == ["ConfigureAll"]
        assert [call["call_id"] for call in configure_all["calls"]] == ["ConfigureAll"]
        assert configure_all["calls"][0]["settings"]["run"] == {
            "configuration_mode": {"value": "ge-ef-cr"}
        }
        assert data["spec"]["steps"][0]["call"]["name"] == "ConfigureAll"
        # ConfigureAll runs once for its MUXes; the per-target count is unchanged.
        assert data["task_run_count"] == 6

    def test_configure_all_call_problems_point_at_the_call(self, test_client, chip, auth_headers):
        spec = good_spec()
        spec["steps"].insert(0, {"type": "ConfigureAll", "call": {"name": "Configure"}})
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        data = response.json()
        assert data["valid"] is False
        problems = {problem["path"]: problem["message"] for problem in data["problems"]}
        assert "must name ConfigureAll" in problems["steps[0].call"]

    def test_configure_all_call_needs_the_task_on_the_backend(self) -> None:
        from unittest.mock import MagicMock

        from qdash.api.services.calibration_pipeline_service import CalibrationPipelineService
        from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec

        repository = MagicMock()
        repository.list_by_project.return_value = []
        service = CalibrationPipelineService(
            repository,
            default_backend=lambda: "fake",
            available_backends=lambda: ["fake"],
            backend_tasks=lambda _backend: ["CheckRabi"],
        )
        spec = CalibrationPipelineSpec.model_validate(
            {
                "spec_version": 2,
                "targets": {"mux_ids": [0]},
                "steps": [
                    {"type": "ConfigureAll", "call": {"name": "ConfigureAll"}},
                    # A default call is the template's own and is not judged.
                    {"type": "ConfigureAll", "step_id": "configure_all_default"},
                ],
            }
        )
        problems: list[Any] = []
        service._validate_tasks("test_project", "fake", spec, problems)
        assert [(problem.path, problem.message) for problem in problems] == [
            ("steps[0].call", "task 'ConfigureAll' is not available on backend 'fake'")
        ]

    def test_warnings_do_not_make_a_spec_invalid(self, test_client, chip, auth_headers):
        spec = good_spec()
        spec["steps"].append({"type": "FilterByStatus"})
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        data = response.json()
        assert data["valid"] is True, data["problems"]
        assert [warning["path"] for warning in data["warnings"]] == ["steps[3]"]

    def test_removed_mode_names_are_a_problem(self, test_client, chip, auth_headers):
        spec = good_spec()
        spec["steps"][0] = {"type": "OneQubitCheck", "execution_mode": "scheduled"}
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        data = response.json()
        assert data["valid"] is False
        assert any("execution_mode" in p["path"] for p in data["problems"]), data["problems"]

    def test_removed_mode_key_is_a_problem(self, test_client, chip, auth_headers):
        # A saved spec that still uses ``mode`` must not silently run the default.
        spec = good_spec()
        spec["steps"][2]["mode"] = "sequential"
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        data = response.json()
        assert data["valid"] is False
        assert any(p["path"].endswith("mode") for p in data["problems"]), data["problems"]

    def test_problems_carry_paths(self, test_client, chip, auth_headers):
        spec = good_spec()
        spec["targets"] = {"qids": ["0", "99"]}
        spec["steps"][2]["tasks"] = [
            {"name": "CheckT1"},
            {"name": "CheckCrossResonance"},
            {"name": "NoSuchTask"},
        ]
        spec["task_parameters"] = {"CheckDRAGPIPulse": {"run": {"shots": 1}}}
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
        assert "does not run" in problems["task_parameters.CheckDRAGPIPulse"]
        # Still resolved so the agent sees what it wrote.
        assert len(data["steps"]) == 3

    def test_shape_errors_are_problems_not_422(self, test_client, chip, auth_headers):
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={
                "chip_id": CHIP,
                "spec": {
                    "spec_version": 2,
                    "targets": {"qids": ["0"]},
                    "steps": [{"type": "FilterByStatus"}],
                },
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


def prefect_gateway_mocks() -> tuple[AsyncMock, AsyncMock]:
    read_deployment = AsyncMock(return_value="deployment-1")
    create_flow_run = AsyncMock(return_value="flow-run-1")
    return read_deployment, create_flow_run


class TestExecute:
    def test_execute_dispatches_the_system_deployment(self, test_client, chip, auth_headers):
        read_deployment, create_flow_run = prefect_gateway_mocks()
        with (
            patch(
                "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.read_deployment_id",
                new=read_deployment,
            ),
            patch(
                "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
                new=create_flow_run,
            ),
        ):
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=auth_headers,
                json={"chip_id": CHIP, "spec": good_spec()},
            )
        assert response.status_code == 202, response.text
        data = response.json()
        assert data["flow_run_id"] == "flow-run-1"
        assert [step["name"] for step in data["steps"]][-1] == "coherence"

        read_deployment.assert_awaited_once_with("calibration-pipeline/system-calibration-pipeline")
        parameters = create_flow_run.call_args.kwargs["parameters"]
        assert parameters["project_id"] == "test_project"
        assert parameters["username"] == "test_user"
        assert parameters["chip_id"] == CHIP
        assert parameters["flow_name"] == "coarse-then-coherence"
        assert parameters["backend_name"] == "qubex"
        assert "pipeline" in parameters["tags"]
        # The worker gets the normalized spec, not the raw request body.
        assert parameters["spec"]["steps"][0]["configure"] is False
        assert parameters["spec"]["steps"][2]["execution_mode"] == "parallel_by_round"
        assert parameters["spec"]["spec_version"] == 2
        assert [call["call_id"] for call in parameters["spec"]["steps"][2]["tasks"]] == [
            "t1_short",
            "t1_long",
            "CheckT2Echo",
        ]

    def test_execute_rejects_invalid_spec_before_dispatch(self, test_client, chip, auth_headers):
        _, create_flow_run = prefect_gateway_mocks()
        spec = good_spec()
        spec["targets"] = {"qids": ["99"]}
        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ):
            response = test_client.post(
                "/calibration-pipelines/execute",
                headers=auth_headers,
                json={"chip_id": CHIP, "spec": spec},
            )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["problems"][0]["path"] == "targets.qids[0]"
        create_flow_run.assert_not_called()

    def test_execute_without_worker_deployment_is_503(self, test_client, chip, auth_headers):
        unavailable = AsyncMock(side_effect=SystemDeploymentUnavailable("missing"))
        with patch(
            "qdash.api.services.flow_service.execution.ExecutionCoordinator.read_deployment_id",
            new=unavailable,
        ):
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


class TestPreflight:
    """Problems a task would raise before measuring are reported by the dry run."""

    def test_missing_calibration_data_is_a_problem(self, test_client, chip, auth_headers):
        spec = {
            "spec_version": 2,
            "targets": {"qids": ["0", "1"]},
            "steps": [
                {"type": "CustomOneQubit", "step_name": "t1", "tasks": [{"name": "CheckT1"}]}
            ],
        }
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        messages = [p["message"] for p in data["problems"] if p["path"] == "steps[0].tasks[0]"]
        assert any("'rabi_amplitude'" in m and "qubit(s) 0, 1" in m for m in messages), data[
            "problems"
        ]
        assert any("'hpi_amplitude'" in m for m in messages)

    def test_unreadable_task_catalog_fails_closed(self, test_client, chip, auth_headers):
        from fastapi import HTTPException

        from qdash.api.services.task_file_service import TaskFileService

        with patch.object(
            TaskFileService,
            "list_task_info",
            side_effect=HTTPException(status_code=404, detail="Backend directory not found"),
        ):
            response = test_client.post(
                "/calibration-pipelines/validate",
                headers=auth_headers,
                json={"chip_id": CHIP, "spec": good_spec()},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        messages = [p["message"] for p in data["problems"] if p["path"] == "backend_name"]
        assert any("task catalog" in m and "Backend directory not found" in m for m in messages), (
            data["problems"]
        )

    def test_task_readout_duration_must_match_the_session(self, test_client, chip, auth_headers):
        spec = good_spec()
        spec["task_parameters"] = {"CheckT1": {"run": {"readout_duration": 2048}}}
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        assert response.status_code == 200
        problems = {p["path"]: p["message"] for p in response.json()["problems"]}
        assert "session-scoped" in problems["task_parameters.CheckT1.run.readout_duration"]

        spec["default_run_parameters"] = {"readout_duration": 2048}
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        assert response.json()["valid"] is True, response.json()["problems"]

    def test_mux_targets_are_checked_per_qubit(self, test_client, chip, auth_headers):
        qubit = QubitDocument.find_one(
            {"project_id": "test_project", "chip_id": CHIP, "qid": "5"}
        ).run()
        assert qubit is not None
        qubit.set({"data": {}})
        spec = {
            "spec_version": 2,
            "targets": {"mux_ids": [1], "exclude_qids": ["7"]},
            "steps": [{"type": "OneQubitCheck"}],
        }
        response = test_client.post(
            "/calibration-pipelines/validate",
            headers=auth_headers,
            json={"chip_id": CHIP, "spec": spec},
        )
        data = response.json()
        assert data["valid"] is False
        messages = [p["message"] for p in data["problems"] if p["path"] == "steps[0].tasks[0]"]
        assert any("'control_frequency'" in m and "qubit(s) 5" in m for m in messages), data[
            "problems"
        ]
