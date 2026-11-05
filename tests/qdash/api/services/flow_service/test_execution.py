"""Tests for the execution coordinator."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from qdash.api.services.flow_service.execution import (
    ExecutionCoordinator,
    FlowDispatchError,
)
from qdash.common.config.path_resolver import execution_calib_data_dir
from qdash.common.execution_resources import ExecutionResourceScope
from qdash.config import Settings
from qdash.datamodel.execution import ExecutionStatusModel
from qdash.repository import MongoExecutionLockRepository


def _lock(*, granted: bool = True, conflict: bool = False) -> MagicMock:
    return MagicMock(
        try_lock=MagicMock(return_value=granted),
        unlock=MagicMock(),
        has_conflict=MagicMock(return_value=conflict),
    )


def _coordinator(*, lock=None, executions=None, prefect=None, id_factory=None):
    return ExecutionCoordinator(
        lock_repository=lock,
        execution_repository=executions,
        prefect=prefect or AsyncMock(),
        id_factory=id_factory or MagicMock(return_value="20240101-001"),
    )


def _settings(client_url: str) -> Settings:
    return Settings.model_validate(
        {
            "env": "test",
            "client_url": client_url,
            "ui_port": 5714,
            "prefect_api_url": "http://prefect.example.test/api",
            "postgres_data_path": "/tmp/postgres",
            "mongo_data_path": "/tmp/mongo",
            "calib_data_path": "/tmp/calib",
        }
    )


def _saved_row(executions: MagicMock):
    return executions.save.call_args.args[0]


class TestExecutionCoordinatorAvailability:
    """availability() reports whether the hardware a run needs is free, without claiming it."""

    def test_available_when_no_conflict(self):
        coordinator = _coordinator(lock=_lock())

        assert coordinator.availability(
            project_id="proj-1",
            chip_id="chip-1",
            parameters={},
            workflow=False,
        ) == (True, None)

    def test_reports_the_scoped_conflict(self):
        coordinator = _coordinator(lock=_lock(conflict=True))
        available, reason = coordinator.availability(
            project_id="proj-1",
            chip_id="chip-1",
            parameters={},
            workflow=False,
        )

        assert available is False
        assert reason == (
            "Another calibration is using hardware required by this run. "
            "Wait for it to finish or select different targets."
        )

    def test_reports_the_whole_chip_conflict_for_a_workflow(self):
        coordinator = _coordinator(lock=_lock(conflict=True))
        available, reason = coordinator.availability(
            project_id="proj-1",
            chip_id="chip-1",
            parameters={},
            workflow=True,
        )

        assert available is False
        assert reason == (
            "This workflow requires the entire chip for its steps. "
            "Another calibration is using this chip; wait for it to finish."
        )

    def test_missing_lock_repository_answers_503(self):
        with pytest.raises(HTTPException) as exc_info:
            _coordinator(lock=None).availability(
                project_id="proj-1",
                chip_id="chip-1",
                parameters={},
                workflow=False,
            )

        assert exc_info.value.status_code == 503


class TestExecutionCoordinatorClaim:
    """_claim() claims the project execution lock for a run about to be dispatched."""

    def test_skips_without_a_lock_repository(self):
        result = _coordinator(lock=None)._claim(
            project_id="proj-1",
            username="user-1",
            chip_id="chip-1",
            parameters={},
            workflow=False,
        )

        assert result is None

    def test_skips_without_a_chip(self):
        lock = _lock()
        result = _coordinator(lock=lock)._claim(
            project_id="proj-1",
            username="user-1",
            chip_id="",
            parameters={},
            workflow=False,
        )

        assert result is None
        lock.try_lock.assert_not_called()

    def test_conflict_raises_409(self):
        with pytest.raises(HTTPException) as exc_info:
            _coordinator(lock=_lock(granted=False))._claim(
                project_id="proj-1",
                username="user-1",
                chip_id="chip-1",
                parameters={},
                workflow=False,
            )

        assert exc_info.value.status_code == 409
        assert "overlapping hardware resources" in str(exc_info.value.detail)

    def test_claims_the_whole_chip_for_a_workflow(self):
        lock = _lock()

        result = _coordinator(lock=lock)._claim(
            project_id="proj-1",
            username="user-1",
            chip_id="chip-1",
            parameters={},
            workflow=True,
        )

        assert result == "20240101-001"
        lock.try_lock.assert_called_once_with(
            project_id="proj-1",
            execution_id="20240101-001",
            chip_id="chip-1",
            resources=(),
            exclusive=True,
        )

    def test_claims_the_whole_chip_for_unresolved_targets(self):
        lock = _lock()

        _coordinator(lock=lock)._claim(
            project_id="proj-1",
            username="user-1",
            chip_id="chip-1",
            parameters={},
            workflow=False,
        )

        _, kwargs = lock.try_lock.call_args
        assert kwargs["exclusive"] is True
        assert kwargs["resources"] == ()


class TestExecutionCoordinatorRelease:
    """_release() releases a lock claimed for a run that never reached the flow process."""

    def test_ignores_a_missing_execution_id(self):
        lock = _lock()

        _coordinator(lock=lock)._release("proj-1", None)

        lock.unlock.assert_not_called()

    def test_ignores_a_missing_lock_repository(self):
        unlock = MagicMock()

        with patch.object(MongoExecutionLockRepository, "unlock", unlock):
            _coordinator(lock=None)._release("proj-1", "20240101-001")

        unlock.assert_not_called()

    def test_unlocks_the_claimed_execution(self):
        lock = _lock()

        _coordinator(lock=lock)._release("proj-1", "20240101-001")

        lock.unlock.assert_called_once_with(project_id="proj-1", execution_id="20240101-001")

    def test_logs_a_failed_unlock(self, caplog):
        lock = MagicMock(unlock=MagicMock(side_effect=RuntimeError("db error")))

        with caplog.at_level(logging.WARNING):
            _coordinator(lock=lock)._release("proj-1", "20240101-001")

        assert "Failed to release the execution lock" in caplog.text


class TestExecutionCoordinatorScheduledExecution:
    """_create_scheduled_execution() pre-creates a row before the flow starts."""

    def test_skips_without_a_chip_id(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _coordinator()._create_scheduled_execution(
                project_id="proj-1",
                username="user-1",
                chip_id=None,
                name="my_flow",
                flow_run_id="run-1",
            )

        assert result is None
        assert "Skipping scheduled execution pre-creation" in caplog.text

    def test_records_a_scheduled_row(self):
        executions = MagicMock()

        result = _coordinator(executions=executions)._create_scheduled_execution(
            project_id="proj-1",
            username="user-1",
            chip_id="chip-1",
            name="my_flow",
            flow_run_id="run-1",
            execution_id="20240101-001",
            tags=["daily"],
        )

        row = _saved_row(executions)
        assert result == "20240101-001"
        assert row.execution_id == "20240101-001"
        assert row.project_id == "proj-1"
        assert row.username == "user-1"
        assert row.name == "my_flow"
        assert row.chip_id == "chip-1"
        assert row.tags == ["daily"]
        assert row.note == {"flow_run_id": "run-1"}
        assert row.status == ExecutionStatusModel.SCHEDULED
        assert row.calib_data_path == str(execution_calib_data_dir("user-1", "20240101-001"))

    def test_reuses_the_claimed_execution_id(self):
        executions = MagicMock()
        id_factory = MagicMock(return_value="fresh-id")

        _coordinator(executions=executions, id_factory=id_factory)._create_scheduled_execution(
            project_id="proj-1",
            username="user-1",
            chip_id="chip-1",
            name="my_flow",
            flow_run_id="run-1",
            execution_id="20240101-001",
        )

        id_factory.assert_not_called()
        assert _saved_row(executions).execution_id == "20240101-001"

    def test_mints_an_id_when_none_is_claimed(self):
        executions = MagicMock()
        id_factory = MagicMock(return_value="fresh-id")

        result = _coordinator(
            executions=executions, id_factory=id_factory
        )._create_scheduled_execution(
            project_id="proj-1",
            username="user-1",
            chip_id="chip-1",
            name="my_flow",
            flow_run_id="run-1",
        )

        assert result == "fresh-id"
        id_factory.assert_called_once_with("user-1", "chip-1", project_id="proj-1")
        assert _saved_row(executions).execution_id == "fresh-id"

    def test_returns_none_when_the_fallback_repository_fails(self, caplog):
        with patch(
            "qdash.api.services.flow_service.execution.MongoExecutionRepository"
        ) as repository:
            repository.return_value.save.side_effect = RuntimeError("db unavailable")
            with caplog.at_level(logging.WARNING):
                result = _coordinator(executions=None)._create_scheduled_execution(
                    project_id="proj-1",
                    username="user-1",
                    chip_id="chip-1",
                    name="my_flow",
                    flow_run_id="run-1",
                )

        assert result is None
        assert "Failed to pre-create scheduled execution" in caplog.text


class TestExecutionCoordinatorDeployments:
    """Deployment lookups and deletions are delegated to Prefect."""

    @pytest.mark.asyncio
    async def test_reads_a_deployment_id(self):
        prefect = AsyncMock()
        prefect.read_deployment_id = AsyncMock(return_value="dep-1")

        result = await _coordinator(prefect=prefect).read_deployment_id("system/deployment")

        assert result == "dep-1"
        prefect.read_deployment_id.assert_called_once_with("system/deployment")

    @pytest.mark.asyncio
    async def test_deletes_a_deployment(self):
        prefect = AsyncMock()

        await _coordinator(prefect=prefect).delete_deployment("dep-1")

        prefect.delete_deployment.assert_called_once_with("dep-1")


class TestExecutionCoordinatorDispatchBackground:
    """dispatch_background() dispatches a run with no lock and no execution row."""

    @pytest.mark.asyncio
    async def test_returns_the_flow_run_id(self):
        prefect = AsyncMock()
        prefect.create_flow_run = AsyncMock(return_value="run-1")
        executions = MagicMock()

        result = await _coordinator(prefect=prefect, executions=executions).dispatch_background(
            deployment_id="dep-1",
            parameters={"qid": "0"},
        )

        assert result == "run-1"
        prefect.create_flow_run.assert_called_once_with(
            deployment_id="dep-1",
            parameters={"qid": "0"},
        )
        executions.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_wraps_prefect_failures(self):
        prefect = AsyncMock()
        prefect.create_flow_run = AsyncMock(side_effect=RuntimeError("prefect down"))

        with pytest.raises(FlowDispatchError, match="prefect down"):
            await _coordinator(prefect=prefect).dispatch_background(
                deployment_id="dep-1",
                parameters={},
            )


class TestExecutionCoordinatorDispatchRun:
    """dispatch_run() claims, dispatches, records and maps a run."""

    @pytest.mark.asyncio
    async def test_records_the_run_and_the_scheduled_row(self):
        prefect = AsyncMock()
        prefect.create_flow_run = AsyncMock(return_value="run-1")
        executions = MagicMock()
        lock = _lock()

        result = await _coordinator(lock=lock, executions=executions, prefect=prefect).dispatch_run(
            project_id="proj-1",
            username="user-1",
            chip_id="chip-1",
            name="my_flow",
            deployment_id="dep-1",
            parameters={},
            tags=["daily"],
            workflow=True,
        )

        assert result.flow_run_id == "run-1"
        assert result.execution_id == "20240101-001"
        assert "runs/flow-run/run-1" in result.flow_run_url
        assert result.qdash_ui_url.endswith("/execution/chip-1/20240101-001")
        assert lock.try_lock.call_args.kwargs["exclusive"] is True
        assert _saved_row(executions).note == {"flow_run_id": "run-1"}

    @pytest.mark.asyncio
    async def test_scopes_the_lock_to_the_requested_targets(self):
        prefect = AsyncMock()
        prefect.create_flow_run = AsyncMock(return_value="run-1")
        lock = _lock()
        scope = ExecutionResourceScope("chip-1", ("mux:0", "channel:Q00"), exclusive=False)

        with patch(
            "qdash.api.services.flow_service.execution.resolve_execution_resource_scope",
            return_value=scope,
        ):
            await _coordinator(lock=lock, executions=MagicMock(), prefect=prefect).dispatch_run(
                project_id="proj-1",
                username="user-1",
                chip_id="chip-1",
                name="my_flow",
                deployment_id="dep-1",
                parameters={"qid": "Q00"},
            )

        lock.try_lock.assert_called_once_with(
            project_id="proj-1",
            execution_id="20240101-001",
            chip_id="chip-1",
            resources=("mux:0", "channel:Q00"),
            exclusive=False,
        )

    @pytest.mark.asyncio
    async def test_releases_the_lock_when_prefect_fails(self):
        prefect = AsyncMock()
        prefect.create_flow_run = AsyncMock(side_effect=RuntimeError("prefect down"))
        lock = _lock()

        with pytest.raises(FlowDispatchError, match="prefect down"):
            await _coordinator(lock=lock, prefect=prefect).dispatch_run(
                project_id="proj-1",
                username="user-1",
                chip_id="chip-1",
                name="my_flow",
                deployment_id="dep-1",
                parameters={},
            )

        lock.unlock.assert_called_once_with(project_id="proj-1", execution_id="20240101-001")

    @pytest.mark.asyncio
    async def test_keeps_the_run_when_the_scheduled_row_fails(self):
        prefect = AsyncMock()
        prefect.create_flow_run = AsyncMock(return_value="run-1")
        executions = MagicMock()
        executions.save.side_effect = RuntimeError("db down")
        lock = _lock()

        result = await _coordinator(lock=lock, executions=executions, prefect=prefect).dispatch_run(
            project_id="proj-1",
            username="user-1",
            chip_id="chip-1",
            name="my_flow",
            deployment_id="dep-1",
            parameters={},
        )

        assert result.flow_run_id == "run-1"
        assert result.execution_id is None
        assert result.qdash_ui_url.endswith("/execution/chip-1")
        lock.unlock.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_lock_and_row_without_a_chip(self):
        prefect = AsyncMock()
        prefect.create_flow_run = AsyncMock(return_value="run-1")
        executions = MagicMock()
        lock = _lock()

        result = await _coordinator(lock=lock, executions=executions, prefect=prefect).dispatch_run(
            project_id="proj-1",
            username="user-1",
            chip_id="",
            name="my_flow",
            deployment_id="dep-1",
            parameters={},
        )

        assert result.execution_id is None
        assert result.qdash_ui_url.endswith("/execution")
        lock.try_lock.assert_not_called()
        executions.save.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("client_url", "origin"),
        [
            ("https://qdash.example.test:8443", "https://qdash.example.test:8443"),
            ("https://qdash.example.test:8443/", "https://qdash.example.test:8443"),
            ("", "http://localhost:5714"),
        ],
    )
    async def test_builds_urls_from_the_public_origin(self, client_url, origin):
        prefect = AsyncMock()
        prefect.create_flow_run = AsyncMock(return_value="run-1")

        with patch(
            "qdash.api.services.flow_service.execution.get_settings",
            return_value=_settings(client_url),
        ):
            result = await _coordinator(
                lock=_lock(), executions=MagicMock(), prefect=prefect
            ).dispatch_run(
                project_id="proj-1",
                username="user-1",
                chip_id="chip-1",
                name="my_flow",
                deployment_id="dep-1",
                parameters={},
            )

        assert result.flow_run_url == f"{origin}/prefect/runs/flow-run/run-1"
        assert result.qdash_ui_url == f"{origin}/execution/chip-1/20240101-001"
