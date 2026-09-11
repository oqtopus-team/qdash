"""Regression tests for failures before calibration tasks start."""

from unittest.mock import MagicMock

import pytest

from qdash.datamodel.execution import ExecutionStatusModel
from qdash.repository.inmemory import InMemoryExecutionRepository
from qdash.workflow.engine.config import CalibConfig
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.orchestrator import CalibOrchestrator


@pytest.mark.parametrize("skip_execution", [False, True])
@pytest.mark.parametrize("failure_stage", ["create", "connect"])
def test_backend_initialization_failure_is_persisted(monkeypatch, skip_execution, failure_stage):
    """Owned executions record the traceback; isolated workers leave their parent alone."""
    config = CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["0"],
        execution_id="exec-1",
        project_id="project-1",
        enable_github_pull=False,
        skip_execution=skip_execution,
    )
    repo = InMemoryExecutionRepository()
    service = ExecutionService.create(
        username=config.username,
        chip_id=config.chip_id,
        execution_id=config.execution_id,
        calib_data_path=config.calib_data_path,
        project_id=config.project_id,
        repository=repo,
    )
    service.save().start()
    orchestrator = CalibOrchestrator(config)
    monkeypatch.setattr(orchestrator, "_create_directories", MagicMock())
    monkeypatch.setattr(orchestrator, "_create_history_recorder", lambda: None)
    monkeypatch.setattr("qdash.workflow.engine.orchestrator.get_run_logger", MagicMock())
    monkeypatch.setattr("qdash.workflow.engine.orchestrator.TaskContext", MagicMock())
    monkeypatch.setattr(ExecutionService, "create", lambda **kwargs: service)
    error = ConnectionError("Instrument connection failed")
    backend = MagicMock()
    factory = MagicMock(return_value=backend)
    if failure_stage == "connect":
        backend.connect.side_effect = error
    else:
        factory.side_effect = error
    monkeypatch.setattr(orchestrator, "_create_backend", factory)

    with pytest.raises(ConnectionError) as caught:
        orchestrator.initialize()

    assert caught.value is error
    assert not orchestrator.is_initialized
    saved = repo.find_by_id(config.execution_id)
    assert saved is not None
    if skip_execution:
        assert saved.status == ExecutionStatusModel.RUNNING
        assert saved.message == ""
    else:
        assert saved.status == ExecutionStatusModel.FAILED
        assert saved.end_at is not None
        assert "Traceback (most recent call last)" in saved.message
        assert "ConnectionError: Instrument connection failed" in saved.message
        # A later cleanup without a reason must retain the diagnostic.
        service.reload().fail()
        assert service.reload().message == saved.message
