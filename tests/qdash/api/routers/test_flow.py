"""Tests for flow router endpoints."""

import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from qdash.api.services.flow_service.deployment_client import DeploymentServiceClient
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.flow import FlowDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument
from tests.qdash.api._operation_errors import ERRORS_LOGGER, assert_operation_failure


@pytest.fixture
def test_project(init_db):
    """Create a test project with owner membership."""
    # Create user
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    # Create project
    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_user_id=user.user_id,
        owner_username="test_user",
    )
    project.insert()

    # Create membership
    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="test_user",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="test_user",
    )
    membership.insert()

    return project


@pytest.fixture
def auth_headers():
    """Get authentication headers with project context."""
    return {
        "Authorization": "Bearer test_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def editor_auth_headers(test_project):
    """Create an editor user and return authentication headers."""
    user = UserDocument(
        username="editor_user",
        hashed_password="hashed",
        access_token="editor_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="editor_user",
        role=ProjectRole.EDITOR,
        status="active",
        invited_by="test_user",
    )
    membership.insert()

    return {
        "Authorization": "Bearer editor_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def sample_flow(test_project):
    """Create a sample flow in the database."""
    flow = FlowDocument(
        project_id="test_project",
        name="test_flow",
        username="test_user",
        chip_id="test_chip",
        description="A test flow",
        flow_function_name="run_test_flow",
        default_parameters={"username": "test_user", "chip_id": "test_chip", "qids": ["0", "1"]},
        file_path="/app/flows/test_user/test_flow.py",
        deployment_id="test-deployment-id",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        tags=["test"],
        folder="daily/t1",
    )
    flow.insert()
    return flow


class TestFlowRouter:
    """Tests for flow-related API endpoints."""

    def test_list_flows_empty(self, test_client, test_project, auth_headers):
        """Test listing flows when no flows exist."""
        response = test_client.get("/flows", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["flows"] == []

    def test_list_flows_with_data(self, test_client, test_project, auth_headers, sample_flow):
        """Test listing flows when flows exist."""
        response = test_client.get("/flows", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["flows"]) == 1
        assert data["flows"][0]["name"] == "test_flow"
        assert data["flows"][0]["created_by"] == "test_user"
        assert data["flows"][0]["folder"] == "daily/t1"
        assert data["flows"][0]["file_exists"] is False

    def test_list_flows_marks_existing_files(
        self, test_client, test_project, auth_headers, tmp_path
    ):
        """Test listing flows reports whether the source file still exists."""
        flow_path = tmp_path / "existing_flow.py"
        flow_path.write_text("from prefect import flow\n", encoding="utf-8")
        flow = FlowDocument(
            project_id="test_project",
            name="existing_flow",
            username="test_user",
            chip_id="test_chip",
            description="An existing flow",
            flow_function_name="run_existing_flow",
            file_path=str(flow_path),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=[],
        )
        flow.insert()

        response = test_client.get("/flows", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["flows"][0]["name"] == "existing_flow"
        assert data["flows"][0]["file_exists"] is True

    def test_list_flows_filters_by_project(self, test_client, test_project, auth_headers):
        """Test that listing flows only returns flows for the current project."""
        # Arrange: Create flows for different projects
        flow1 = FlowDocument(
            project_id="test_project",
            name="flow_project1",
            username="test_user",
            chip_id="chip1",
            flow_function_name="run_flow1",
            file_path="/app/flows/test_user/flow1.py",
        )
        flow1.insert()

        flow2 = FlowDocument(
            project_id="other_project",
            name="flow_project2",
            username="test_user",
            chip_id="chip2",
            flow_function_name="run_flow2",
            file_path="/app/flows/test_user/flow2.py",
        )
        flow2.insert()

        # Act
        response = test_client.get("/flows", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["flows"]) == 1
        assert data["flows"][0]["name"] == "flow_project1"

    def test_list_flows_includes_other_project_members_flows(
        self, test_client, test_project, editor_auth_headers, sample_flow
    ):
        """Test that project members can see flows created by other members."""
        response = test_client.get("/flows", headers=editor_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["flows"]) == 1
        assert data["flows"][0]["name"] == "test_flow"

    def test_list_flows_requires_authentication(self, test_client, test_project):
        """Test that listing flows without auth returns 401."""
        response = test_client.get("/flows")
        assert response.status_code == 401

    def test_list_flows_invalid_token(self, test_client, test_project):
        """Test that listing flows with invalid token returns 401."""
        headers = {
            "Authorization": "Bearer invalid_token",
            "X-Project-Id": "test_project",
        }
        response = test_client.get("/flows", headers=headers)
        assert response.status_code == 401


class TestFlowMove:
    """Tests for PATCH /flows/{name}/folder."""

    def test_move_flow_updates_only_the_folder(
        self, test_client, test_project, auth_headers, sample_flow
    ):
        response = test_client.patch(
            "/flows/test_flow/folder", headers=auth_headers, json={"folder": "/weekly/"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["folder"] == "weekly"
        stored = FlowDocument.find_one({"project_id": "test_project", "name": "test_flow"}).run()
        assert stored is not None
        assert stored.folder == "weekly"
        assert stored.file_path == sample_flow.file_path
        assert stored.deployment_id == sample_flow.deployment_id

    def test_move_flow_to_the_root(self, test_client, test_project, auth_headers, sample_flow):
        response = test_client.patch(
            "/flows/test_flow/folder", headers=auth_headers, json={"folder": ""}
        )

        assert response.status_code == 200, response.text
        assert response.json()["folder"] == ""

    def test_move_flow_rejects_a_bad_folder(
        self, test_client, test_project, auth_headers, sample_flow
    ):
        response = test_client.patch(
            "/flows/test_flow/folder", headers=auth_headers, json={"folder": "../x"}
        )

        assert response.status_code == 400

    def test_move_flow_not_found(self, test_client, test_project, auth_headers):
        response = test_client.patch(
            "/flows/missing/folder", headers=auth_headers, json={"folder": "a"}
        )

        assert response.status_code == 404


class TestFlowExecution:
    """Tests for flow execution endpoint."""

    def test_execute_flow_passes_project_id_and_flow_name(
        self, test_client, test_project, auth_headers, sample_flow
    ):
        """Test that execute_flow passes project_id and flow_name to Prefect parameters.

        project_id is passed for multi-tenancy support, allowing workflows to
        operate within the correct project context.
        """
        create_flow_run = AsyncMock(return_value="test-flow-run-id")

        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ):
            # Act
            response = test_client.post(
                "/flows/test_flow/execute",
                headers=auth_headers,
                json={"parameters": {}},
            )

        # Assert
        assert response.status_code == 200

        # Verify parameters passed to Prefect
        parameters = create_flow_run.call_args.kwargs["parameters"]

        # project_id should be passed for multi-tenancy
        assert "project_id" in parameters
        assert parameters["project_id"] == "test_project"

        # flow_name should be passed for display purposes
        assert "flow_name" in parameters
        assert parameters["flow_name"] == "test_flow"

    def test_execute_flow_merges_default_parameters(
        self, test_client, test_project, auth_headers, sample_flow
    ):
        """Test that execute_flow merges request parameters with default_parameters."""
        create_flow_run = AsyncMock(return_value="test-flow-run-id")

        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ):
            # Act: Execute with custom parameters
            response = test_client.post(
                "/flows/test_flow/execute",
                headers=auth_headers,
                json={"parameters": {"custom_param": "custom_value"}},
            )

        # Assert
        assert response.status_code == 200

        parameters = create_flow_run.call_args.kwargs["parameters"]

        # Default parameters should be present
        assert parameters.get("username") == "test_user"
        assert parameters.get("chip_id") == "test_chip"
        assert parameters.get("qids") == ["0", "1"]

        # Custom parameter should be merged
        assert parameters.get("custom_param") == "custom_value"

        # flow_name should be added
        assert parameters.get("flow_name") == "test_flow"

    def test_execute_flow_not_found(self, test_client, test_project, auth_headers):
        """Test that executing non-existent flow returns 404."""
        response = test_client.post(
            "/flows/nonexistent_flow/execute",
            headers=auth_headers,
            json={"parameters": {}},
        )
        assert response.status_code == 404

    def test_execute_flow_requires_authentication(self, test_client, test_project, sample_flow):
        """Test that executing flow without auth returns 401."""
        response = test_client.post(
            "/flows/test_flow/execute",
            json={"parameters": {}},
        )
        assert response.status_code == 401

    def test_execute_flow_wrong_project(self, test_client, test_project, auth_headers):
        """Test that executing another project's flow returns 404."""
        # Arrange: Create a flow for another project
        flow = FlowDocument(
            project_id="other_project",
            name="other_flow",
            username="test_user",
            chip_id="chip",
            flow_function_name="run_flow",
            file_path="/app/flows/test_user/other_flow.py",
            deployment_id="other-deployment-id",
        )
        flow.insert()

        # Act: Try to execute from test_project
        response = test_client.post(
            "/flows/other_flow/execute",
            headers=auth_headers,
            json={"parameters": {}},
        )

        # Assert: Should not find the flow (project isolation)
        assert response.status_code == 404

    def test_execute_flow_created_by_other_member_uses_requesting_user(
        self, test_client, test_project, editor_auth_headers, sample_flow
    ):
        """Test that project members can execute shared flows as themselves."""
        create_flow_run = AsyncMock(return_value="test-flow-run-id")

        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ):
            response = test_client.post(
                "/flows/test_flow/execute",
                headers=editor_auth_headers,
                json={"parameters": {}},
            )

        assert response.status_code == 200

        parameters = create_flow_run.call_args.kwargs["parameters"]
        assert parameters["username"] == "editor_user"
        assert parameters["project_id"] == "test_project"


class TestFlowExecutionRunRecording:
    """A run is recorded before its launch only when its chip is known before it."""

    @pytest.fixture
    def chipless_flow(self, test_project):
        flow = FlowDocument(
            project_id="test_project",
            name="chipless_flow",
            username="test_user",
            chip_id="",
            flow_function_name="run_chipless_flow",
            default_parameters={"qids": ["0"]},
            file_path="/app/flows/test_user/chipless_flow.py",
            deployment_id="chipless-deployment-id",
        )
        flow.insert()
        return flow

    @staticmethod
    def _recorded() -> tuple[int, int]:
        from qdash.dbmodel.calibration_session import (
            CalibrationPipelineRunDocument,
            CalibrationSessionDocument,
        )

        return (
            CalibrationSessionDocument.find({"project_id": "test_project"}).count(),
            CalibrationPipelineRunDocument.find({"project_id": "test_project"}).count(),
        )

    @pytest.mark.parametrize(
        "options",
        [
            {"idempotency_key": "tool-call-1"},
            {"calibration_session_id": "cs-anything"},
            {"idempotency_key": "tool-call-1", "calibration_session_id": "cs-anything"},
        ],
    )
    def test_chipless_flow_with_session_or_key_is_refused_before_launch(
        self, test_client, auth_headers, chipless_flow, options
    ):
        create_flow_run = AsyncMock(return_value="never")
        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ):
            response = test_client.post(
                "/flows/chipless_flow/execute",
                headers=auth_headers,
                json={"parameters": {}, **options},
            )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "names no chip" in detail
        assert "Nothing was started" in detail
        assert "parameters.chip_id" in detail
        create_flow_run.assert_not_awaited()
        assert self._recorded() == (0, 0)

    def test_chipless_flow_with_chip_parameter_is_recorded(
        self, test_client, auth_headers, chipless_flow
    ):
        create_flow_run = AsyncMock(return_value="flow-run-1")
        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ):
            response = test_client.post(
                "/flows/chipless_flow/execute",
                headers=auth_headers,
                json={"parameters": {"chip_id": "chip-a"}, "idempotency_key": "tool-call-1"},
            )

        assert response.status_code == 200
        assert response.json()["calibration_run_id"]
        create_flow_run.assert_awaited_once()
        assert self._recorded() == (1, 1)

    def test_chipless_flow_without_options_defers_recording_to_the_worker(
        self, test_client, auth_headers, chipless_flow
    ):
        from qdash.datamodel.calibration_session import CALIBRATION_RUN_CONTEXT_KEY

        create_flow_run = AsyncMock(return_value="flow-run-2")
        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ):
            response = test_client.post(
                "/flows/chipless_flow/execute", headers=auth_headers, json={"parameters": {}}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["calibration_run_id"] is None
        assert body["calibration_session_id"] is None
        create_flow_run.assert_awaited_once()
        context = create_flow_run.call_args.kwargs.get("context") or {}
        assert CALIBRATION_RUN_CONTEXT_KEY not in context
        assert self._recorded() == (0, 0)

    def test_known_chip_flow_with_key_is_recorded_and_replayed(
        self, test_client, auth_headers, sample_flow
    ):
        create_flow_run = AsyncMock(return_value="flow-run-3")
        with patch(
            "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
            new=create_flow_run,
        ):
            first = test_client.post(
                "/flows/test_flow/execute",
                headers=auth_headers,
                json={"parameters": {}, "idempotency_key": "tool-call-2"},
            )
            second = test_client.post(
                "/flows/test_flow/execute",
                headers=auth_headers,
                json={"parameters": {}, "idempotency_key": "tool-call-2"},
            )

        assert first.status_code == second.status_code == 200
        assert first.json()["calibration_run_id"] == second.json()["calibration_run_id"]
        assert second.json()["replayed"] is True
        create_flow_run.assert_awaited_once()

        from qdash.datamodel.calibration_session import CALIBRATION_RUN_CONTEXT_KEY
        from qdash.dbmodel.calibration_session import CalibrationPipelineRunDocument

        # Only the flow run QDash created receives the launch's dispatch token, and no
        # response carries it.
        run = CalibrationPipelineRunDocument.find_one(
            {"run_id": first.json()["calibration_run_id"]}
        ).run()
        assert run is not None
        handed = create_flow_run.call_args.kwargs["context"][CALIBRATION_RUN_CONTEXT_KEY]
        assert handed["run_id"] == run.run_id
        assert handed["dispatch_token"] == run.dispatch_token
        assert run.dispatch_token not in first.text
        assert run.dispatch_token not in second.text


class TestFlowExecutionOnBusyHardware:
    """A saved flow whose chip is already claimed is refused before anything is recorded."""

    CREATE = "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run"

    @staticmethod
    def _hold(chip_id: str, resources: tuple[str, ...] = (), exclusive: bool = True) -> None:
        from qdash.repository import MongoExecutionLockRepository

        assert MongoExecutionLockRepository().try_lock(
            project_id="test_project",
            execution_id="running-elsewhere",
            chip_id=chip_id,
            resources=resources,
            exclusive=exclusive,
        )

    @staticmethod
    def _recorded() -> tuple[int, int, int]:
        from qdash.dbmodel.calibration_session import CalibrationSessionDocument
        from qdash.dbmodel.execution_history import ExecutionHistoryDocument
        from qdash.dbmodel.run import RunDocument

        return (
            CalibrationSessionDocument.find_all().count(),
            RunDocument.find_all().count(),
            ExecutionHistoryDocument.find_all().count(),
        )

    @pytest.mark.parametrize("options", [{}, {"idempotency_key": "tool-call-busy"}])
    def test_a_claimed_chip_refuses_the_flow_before_it_is_recorded(
        self, test_client, auth_headers, sample_flow, options
    ):
        # Another execution holds only one MUX; a saved flow needs the whole chip.
        self._hold("test_chip", ("mux:0",), exclusive=False)
        create_flow_run = AsyncMock(return_value="never")
        with patch(self.CREATE, new=create_flow_run):
            response = test_client.post(
                "/flows/test_flow/execute",
                headers=auth_headers,
                json={"parameters": {}, **options},
            )

        assert response.status_code == 409
        assert "overlapping hardware resources" in response.json()["detail"]
        create_flow_run.assert_not_awaited()
        assert self._recorded() == (0, 0, 0)

    def test_a_claim_on_another_chip_does_not_refuse_the_flow(
        self, test_client, auth_headers, sample_flow
    ):
        self._hold("other_chip")
        create_flow_run = AsyncMock(return_value="flow-run-free")
        with patch(self.CREATE, new=create_flow_run):
            response = test_client.post(
                "/flows/test_flow/execute",
                headers=auth_headers,
                json={"parameters": {}, "idempotency_key": "tool-call-free"},
            )

        assert response.status_code == 200, response.text
        create_flow_run.assert_awaited_once()
        assert self._recorded() == (1, 1, 1)


class TestFlowTemplates:
    """Tests for flow template endpoints."""

    def test_every_shipped_template_declares_a_backend(
        self, test_client, test_project, auth_headers
    ):
        """Each entry in templates.json names the backend it runs on."""
        response = test_client.get("/flows/templates", headers=auth_headers)

        assert response.status_code == 200
        templates = response.json()
        assert templates
        assert {template["backend"] for template in templates} == {"qubex", "fake"}

    def test_list_templates_filters_by_backend(self, test_client, test_project, auth_headers):
        """The backend query keeps fake templates out of a qubex deployment and vice versa."""
        fake = test_client.get("/flows/templates", params={"backend": "fake"}, headers=auth_headers)
        qubex = test_client.get(
            "/flows/templates", params={"backend": "qubex"}, headers=auth_headers
        )

        assert fake.status_code == 200
        assert [template["id"] for template in fake.json()] == ["fake_calibration"]
        assert qubex.status_code == 200
        qubex_ids = [template["id"] for template in qubex.json()]
        assert "simple" in qubex_ids
        assert "fake_calibration" not in qubex_ids

    def test_get_full_calibration_template_includes_configure_all(
        self, test_client, test_project, auth_headers
    ):
        """Test that the full calibration template starts with ConfigureAll."""
        response = test_client.get("/flows/templates/full_calibration", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "full_calibration"
        assert "ConfigureAll -> 1Q Check" in data["description"]
        assert "ConfigureAll()," in data["code"]

    def test_get_fast_full_calibration_template_includes_shortened_tasks(
        self, test_client, test_project, auth_headers
    ):
        """Test that the fast full calibration template is registered and loadable."""
        response = test_client.get("/flows/templates/fast_full_calibration", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "fast_full_calibration"
        assert "Shortened full calibration" in data["description"]
        assert "Filter -> ConfigureAll -> 1Q fine-tune" in data["description"]
        assert 'ConfigureAll(step_id="configure_all_before_fine_tune")' in data["code"]
        fine_tune_tasks_block = data["code"].split("FAST_1Q_FINE_TUNE_TASKS", 1)[1].split("]", 1)[0]
        assert "CheckT1Average" not in fine_tune_tasks_block


class _RecordingDeploymentClient(DeploymentServiceClient):
    """Deployment client stub that records registrations instead of calling the service."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, str | None]] = []

    async def register(
        self,
        *,
        file_path: str,
        flow_function_name: str,
        deployment_name: str,
        old_deployment_id: str | None = None,
    ) -> str:
        """Record the registration."""
        self.calls.append(
            {
                "file_path": file_path,
                "flow_function_name": flow_function_name,
                "deployment_name": deployment_name,
                "old_deployment_id": old_deployment_id,
            }
        )
        return f"deployment-{len(self.calls)}"


@pytest.fixture
def flow_service_on_tmp(tmp_path, monkeypatch):
    """Route /flows saves to a real flow service on a temporary flow tree."""
    from qdash.api.dependencies import get_flow_repository, get_flow_service
    from qdash.api.main import app
    from qdash.api.services.flow_service.service import FlowService
    from qdash.api.services.flow_service.source_store import FlowSourceStore

    deployment = _RecordingDeploymentClient()
    store = FlowSourceStore(tmp_path / "user_flows")
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_flow_service] = lambda: FlowService(
        flow_repository=get_flow_repository(),
        source_store=store,
        deployment_client=deployment,
    )
    try:
        yield SimpleNamespace(deployment=deployment, store=store)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


FLOW_SOURCE = "from prefect import flow\n\n\n@flow\ndef first_calibration():\n    pass\n"


class TestFlowCreateOnly:
    """Tests for create-only saves used when a new flow is created."""

    def _request(self, **overrides):
        body = {
            "name": "first_calibration",
            "code": FLOW_SOURCE,
            "chip_id": "chip-1",
            "create_only": True,
        }
        body.update(overrides)
        return body

    def test_second_create_only_save_returns_409_and_keeps_the_flow(
        self, test_client, test_project, auth_headers, flow_service_on_tmp
    ):
        """Repeating a create-only save conflicts and leaves the first flow untouched."""
        first = test_client.post("/flows", json=self._request(), headers=auth_headers)
        assert first.status_code == 200
        stored = FlowDocument.find_by_project_and_name("test_project", "first_calibration")
        assert stored is not None
        file_path = Path(stored.file_path)

        second = test_client.post(
            "/flows",
            json=self._request(code=FLOW_SOURCE + "# overwrite\n", chip_id="chip-2"),
            headers=auth_headers,
        )

        assert second.status_code == 409
        assert second.json() == {
            "detail": "Flow 'first_calibration' already exists. Choose another name."
        }
        after = FlowDocument.find_by_project_and_name("test_project", "first_calibration")
        assert after is not None
        assert after.chip_id == "chip-1"
        assert after.deployment_id == stored.deployment_id
        assert file_path.read_text(encoding="utf-8") == FLOW_SOURCE
        assert len(flow_service_on_tmp.deployment.calls) == 1

    def test_save_without_create_only_overwrites_as_before(
        self, test_client, test_project, auth_headers, flow_service_on_tmp
    ):
        """The flow editor's save keeps overwriting an existing flow."""
        assert (
            test_client.post("/flows", json=self._request(), headers=auth_headers).status_code
            == 200
        )
        legacy = self._request(code=FLOW_SOURCE + "# edited\n", chip_id="chip-2")
        del legacy["create_only"]

        response = test_client.post("/flows", json=legacy, headers=auth_headers)

        assert response.status_code == 200
        after = FlowDocument.find_by_project_and_name("test_project", "first_calibration")
        assert after is not None
        assert after.chip_id == "chip-2"
        assert Path(after.file_path).read_text(encoding="utf-8").endswith("# edited\n")


UNFORMATTED_FLOW = "from prefect import flow\n@flow\ndef first_calibration( ):\n  pass\n"


class TestFlowFormat:
    """Formatting flow source formats data only; saves store the formatted source."""

    def test_format_returns_the_formatted_source_and_saves_nothing(
        self, test_client, test_project, auth_headers, flow_service_on_tmp
    ):
        response = test_client.post(
            "/flows/format", json={"source": UNFORMATTED_FLOW}, headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json() == {"status": "formatted", "source": FLOW_SOURCE, "diagnostic": None}
        assert FlowDocument.find_by_project_and_name("test_project", "first_calibration") is None
        assert not flow_service_on_tmp.store.exists(
            flow_service_on_tmp.store.path_for("test_project", "first_calibration")
        )
        assert flow_service_on_tmp.deployment.calls == []

    def test_format_reports_a_syntax_error_with_the_input(
        self, test_client, test_project, auth_headers
    ):
        source = "from prefect import flow\n\ndef broken(:\n"

        response = test_client.post("/flows/format", json={"source": source}, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "syntax_error"
        assert body["source"] == source
        assert body["diagnostic"]["line"] == 3

    def test_format_reports_an_unavailable_formatter(
        self, test_client, test_project, auth_headers, monkeypatch
    ):
        from qdash.api.lib import python_format

        def unavailable(_source):
            raise python_format.FormatterUnavailableError("Formatting took longer than 10 s")

        monkeypatch.setattr(
            "qdash.api.services.source_format_service.format_python_source", unavailable
        )

        response = test_client.post(
            "/flows/format", json={"source": "x = 1\n"}, headers=auth_headers
        )

        assert response.status_code == 503
        assert "longer than" in response.json()["detail"]

    def test_format_requires_an_editor(self, test_client, test_project):
        payload = {"source": "x = 1\n"}

        assert test_client.post("/flows/format", json=payload).status_code == 401
        assert (
            test_client.post("/flows/format", json=payload, headers=_viewer_headers()).status_code
            == 403
        )

    def test_save_validates_stores_and_returns_the_formatted_source(
        self, test_client, test_project, auth_headers, flow_service_on_tmp
    ):
        body = {"name": "first_calibration", "code": UNFORMATTED_FLOW, "chip_id": "chip-1"}

        response = test_client.post("/flows", json=body, headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["code"] == FLOW_SOURCE
        stored = FlowDocument.find_by_project_and_name("test_project", "first_calibration")
        assert stored is not None
        assert Path(stored.file_path).read_text(encoding="utf-8") == FLOW_SOURCE

    def test_save_still_rejects_a_syntax_error(
        self, test_client, test_project, auth_headers, flow_service_on_tmp
    ):
        body = {"name": "first_calibration", "code": "def broken(:\n", "chip_id": "chip-1"}

        response = test_client.post("/flows", json=body, headers=auth_headers)

        assert response.status_code == 400
        assert "syntax error" in response.json()["detail"]
        assert flow_service_on_tmp.deployment.calls == []


MANUAL_FLOW = """
from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets


def run_manual(username, chip_id):
    cal = CalibService(username, chip_id)
    return cal.run(
        QubitTargets(["0", "8"]),
        steps=[
            CustomOneQubit(
                execution_mode="manual",
                rounds=[["0", "8"]],
                tasks=[TaskCall(name="CheckRabi")],
            )
        ],
    )
"""


@pytest.fixture
def manual_flow(test_project, tmp_path):
    """A saved flow with manual rounds, its source file and its chip."""
    from qdash.dbmodel.chip import ChipDocument

    path = tmp_path / "manual_flow.py"
    path.write_text(MANUAL_FLOW, encoding="utf-8")
    ChipDocument(
        chip_id="test_chip",
        username="test_user",
        project_id="test_project",
        size=64,
        system_info=SystemInfoModel(),
    ).insert()
    flow = FlowDocument(
        project_id="test_project",
        name="manual_flow",
        username="test_user",
        chip_id="test_chip",
        flow_function_name="run_manual",
        file_path=str(path),
        deployment_id="manual-deployment",
    )
    flow.insert()
    return flow


def _viewer_headers() -> dict[str, str]:
    user = UserDocument(
        username="viewer_user",
        hashed_password="hashed",
        access_token="viewer_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="viewer_user",
        role=ProjectRole.VIEWER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="test_user",
    ).insert()
    return {"Authorization": "Bearer viewer_token", "X-Project-Id": "test_project"}


class TestFlowExecutionPlan:
    """GET /flows/{name}/execution-plan is a read-only, project-scoped preview."""

    def test_a_viewer_reads_the_plan_without_changing_the_flow(self, test_client, manual_flow):
        before = FlowDocument.find_by_project_and_name("test_project", "manual_flow")
        response = test_client.get("/flows/manual_flow/execution-plan", headers=_viewer_headers())

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["chip_id"] == "test_chip"
        assert body["runs"][0]["steps"][0]["rounds"] == [{"number": 1, "targets": ["0", "8"]}]
        assert body["target_override_allowed"] is False
        after = FlowDocument.find_by_project_and_name("test_project", "manual_flow")
        assert after is not None and before is not None
        assert after.updated_at == before.updated_at

    def test_the_plan_requires_authentication(self, test_client, manual_flow):
        assert test_client.get("/flows/manual_flow/execution-plan").status_code == 401

    def test_other_projects_and_chips_are_not_visible(self, test_client, manual_flow, auth_headers):
        other = test_client.get(
            "/flows/manual_flow/execution-plan",
            headers={**auth_headers, "X-Project-Id": "other_project"},
        )
        assert other.status_code in {403, 404}
        chip = test_client.get(
            "/flows/manual_flow/execution-plan",
            headers=auth_headers,
            params={"chip_id": "unknown_chip"},
        )
        assert chip.status_code == 404


class TestFlowSourceFailures:
    """Unexpected flow file failures return a safe message and the ID of the logged cause."""

    def _save(self, test_client, auth_headers):
        body = {"name": "first_calibration", "code": FLOW_SOURCE, "chip_id": "chip-1"}
        return test_client.post("/flows", json=body, headers=auth_headers)

    def test_read_failure_returns_code_message_and_logged_error_id(
        self, test_client, test_project, auth_headers, flow_service_on_tmp, caplog
    ):
        """A flow file that cannot be read answers 500 without the path or exception text."""
        assert self._save(test_client, auth_headers).status_code == 200
        stored = FlowDocument.find_by_project_and_name("test_project", "first_calibration")
        assert stored is not None
        file_path = Path(stored.file_path)
        file_path.unlink()
        file_path.mkdir()  # exists, but reading it raises IsADirectoryError

        with caplog.at_level(logging.ERROR, logger=ERRORS_LOGGER):
            response = test_client.get("/flows/first_calibration", headers=auth_headers)

        assert_operation_failure(
            response,
            caplog,
            code="flow_source_read_failed",
            message="Failed to read the flow file",
            cause=IsADirectoryError,
            hidden=(str(file_path), str(flow_service_on_tmp.store.base_dir), "Errno"),
        )

    def test_write_failure_returns_code_message_and_logged_error_id(
        self, test_client, test_project, auth_headers, flow_service_on_tmp, caplog
    ):
        """A flow file that cannot be written answers 500 and registers no deployment."""
        file_path = flow_service_on_tmp.store.path_for("test_project", "first_calibration")
        file_path.mkdir()

        with caplog.at_level(logging.ERROR, logger=ERRORS_LOGGER):
            response = self._save(test_client, auth_headers)

        assert_operation_failure(
            response,
            caplog,
            code="flow_source_write_failed",
            message="Failed to save the flow file",
            cause=IsADirectoryError,
            hidden=(str(file_path), "Errno"),
        )
        assert flow_service_on_tmp.deployment.calls == []
        assert FlowDocument.find_by_project_and_name("test_project", "first_calibration") is None

    def test_expected_errors_and_success_keep_their_payloads(
        self, test_client, test_project, auth_headers, flow_service_on_tmp
    ):
        """Not-found and success responses are unchanged by the structured 500s."""
        missing = test_client.get("/flows/unknown_flow", headers=auth_headers)
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Flow 'unknown_flow' not found"}

        saved = self._save(test_client, auth_headers)
        assert saved.status_code == 200
        assert set(saved.json()) == {"name", "file_path", "message", "code"}
        assert saved.json()["message"] == "Flow 'first_calibration' created successfully"

        fetched = test_client.get("/flows/first_calibration", headers=auth_headers)
        assert fetched.status_code == 200
        assert fetched.json()["code"] == FLOW_SOURCE
