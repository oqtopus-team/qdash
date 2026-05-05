"""Tests for automatic AI triage scheduling."""

from unittest.mock import MagicMock, patch

from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import QubitTaskModel, TaskStatusModel
from qdash.workflow.engine.task.ai_triage import enqueue_ai_triage_note


def _execution_model() -> ExecutionModel:
    return ExecutionModel(
        username="test",
        name="test-execution",
        execution_id="test-exec-001",
        chip_id="test-chip",
        calib_data_path="/tmp/calib",
        tags=[],
        note={},
        status=ExecutionStatusModel.RUNNING,
        start_at=None,
        end_at=None,
        elapsed_time=None,
        message="",
        system_info=SystemInfoModel(),
    )


def _task(
    name: str,
    qid: str,
    status: TaskStatusModel = TaskStatusModel.COMPLETED,
) -> QubitTaskModel:
    return QubitTaskModel(
        name=name,
        qid=qid,
        status=status,
    )


def _config() -> MagicMock:
    config = MagicMock()
    config.enabled = True
    config.analysis.enabled = True
    config.analysis.ai_triage_tasks = ["CheckQubitSpectroscopy", "CheckResonatorSpectroscopy"]
    return config


@patch("qdash.workflow.engine.task.ai_triage._EXECUTOR")
@patch("qdash.common.copilot.config.load_copilot_config")
def test_enqueue_skips_non_representative_resonator_spectroscopy(
    mock_load_config: MagicMock,
    mock_executor: MagicMock,
) -> None:
    """Only the representative MUX resonator result should receive AI triage."""
    mock_load_config.return_value = _config()

    enqueue_ai_triage_note(_task("CheckResonatorSpectroscopy", "17"), _execution_model())

    mock_executor.submit.assert_not_called()


@patch("qdash.workflow.engine.task.ai_triage._EXECUTOR")
@patch("qdash.common.copilot.config.load_copilot_config")
def test_enqueue_accepts_representative_resonator_spectroscopy(
    mock_load_config: MagicMock,
    mock_executor: MagicMock,
) -> None:
    """Representative MUX resonator result is scheduled asynchronously."""
    mock_load_config.return_value = _config()

    enqueue_ai_triage_note(_task("CheckResonatorSpectroscopy", "16"), _execution_model())

    mock_executor.submit.assert_called_once()


@patch("qdash.workflow.engine.task.ai_triage._EXECUTOR")
@patch("qdash.common.copilot.config.load_copilot_config")
def test_enqueue_accepts_failed_ai_triage_task(
    mock_load_config: MagicMock,
    mock_executor: MagicMock,
) -> None:
    """Configured AI triage tasks are scheduled even when the result failed."""
    mock_load_config.return_value = _config()

    enqueue_ai_triage_note(
        _task("CheckQubitSpectroscopy", "4", status=TaskStatusModel.FAILED),
        _execution_model(),
    )

    mock_executor.submit.assert_called_once()
